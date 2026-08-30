"""
tailor.py — rewrites the .tex resume to better match a JD's language,
WITHOUT inventing anything. Runs only when ats_score puts a job below
your 85 threshold.

COST: uses Gemini (google-genai) by default, on Google's free tier —
no credit card, no subscription. Get a key at https://aistudio.google.com/apikey
and set GEMINI_API_KEY. IMPORTANT: don't enable billing on that Google
Cloud project — doing so removes the free tier entirely for that
project (Google's docs call this out explicitly). If you ever want to
switch to Claude instead (paid, higher quality on some JDs), set
ANTHROPIC_API_KEY instead/as well — Gemini is tried first if both are
set, since it's free.

Hard rule enforced in the prompt: the model may reorder the skills
list, re-emphasize truthful content, and rephrase bullet wording to
mirror JD terminology for a skill that's genuinely already there — it
may NOT add employers, dates, titles, degrees, tools, or achievements
that aren't already in the source resume. A diff is always written to
resumes/diffs/ so you can spot-check exactly what changed.
"""
import difflib
import os
from datetime import date

GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.6-flash")
# Google renames/retires free-tier model IDs periodically (this project
# already hit that once — 2.5-flash was retired for new users). If the
# primary model 404s, these are tried in order automatically; only a
# genuine 404/NOT_FOUND triggers the fallback, other errors (auth, rate
# limit) propagate immediately so they're not silently masked.
GEMINI_FALLBACK_MODELS = ["gemini-3.6-flash", "gemini-flash-latest",
                          "gemini-3.5-flash-lite", "gemini-2.5-flash"]

ANTHROPIC_MODEL = "claude-sonnet-5"

SYSTEM_PROMPT = """You are tailoring a candidate's LaTeX resume to better match a specific \
job description, for ATS keyword alignment. You will be given the current .tex source and \
a job description.

STRICT RULES — violating any of these makes the output unusable:
1. Do NOT add any employer, job title, date range, degree, certification, metric, or \
achievement that is not already present in the source .tex. Every fact must already exist \
in the input.
2. Do NOT remove any employer, role, or project — only reorder or re-emphasize.
3. You MAY reorder the Technical Skills lines so JD-relevant skills (that are already \
listed) appear first.
4. You MAY rephrase the Profile Summary sentence and bullet wording to use terminology the \
JD uses, ONLY when it describes the exact same underlying, already-true fact (e.g. \
"stakeholder management" and "cross-functional collaboration" can be treated as \
equivalent phrasing of the same real skill).
5. Do NOT change any numbers, percentages, dates, or proper nouns.
6. Keep the LaTeX structure, commands, and preamble byte-for-byte identical — only edit \
text inside \\resumeItem{...}, \\listOfSkills{...}, and the Profile Summary paragraph.
7. Return ONLY the complete, compilable .tex file. No commentary, no markdown fences.

If you cannot improve the match without breaking a rule above, return the input unchanged."""


def is_available() -> bool:
    return bool(os.environ.get("GEMINI_API_KEY") or os.environ.get("ANTHROPIC_API_KEY"))


def _build_user_prompt(tex_source: str, jd_text: str, missing_skills: list,
                        company: str, role_title: str) -> str:
    return f"""Job title: {role_title}
Company: {company}
Job description:
{jd_text[:6000]}

Skills the JD mentions that the current resume text doesn't surface clearly: \
{', '.join(missing_skills) if missing_skills else '(none flagged)'}

Current .tex source:
{tex_source}"""


def _call_gemini(user_prompt: str) -> str:
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    config = types.GenerateContentConfig(system_instruction=SYSTEM_PROMPT)

    candidates = [GEMINI_MODEL] + [m for m in GEMINI_FALLBACK_MODELS if m != GEMINI_MODEL]
    last_err = None
    for model_name in candidates:
        try:
            resp = client.models.generate_content(
                model=model_name, contents=user_prompt, config=config,
            )
            return (resp.text or "").strip()
        except Exception as e:
            last_err = e
            if "NOT_FOUND" in str(e) or "404" in str(e):
                continue  # this model ID is gone — try the next candidate
            raise  # a different failure (auth, rate limit) shouldn't be hidden
    raise RuntimeError(f"All Gemini model candidates failed. Last error: {last_err}")


def _call_anthropic(user_prompt: str) -> str:
    import anthropic
    client = anthropic.Anthropic()
    resp = client.messages.create(
        model=ANTHROPIC_MODEL,
        max_tokens=4000,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_prompt}],
    )
    return "".join(
        block.text for block in resp.content if getattr(block, "type", "") == "text"
    ).strip()


def tailor_resume(tex_source: str, jd_text: str, missing_skills: list,
                   company: str, role_title: str) -> dict:
    """Returns {"tex": new_tex, "diff": unified_diff_text, "changed": bool}.
    Raises RuntimeError if no provider is configured or the call fails —
    caller should catch this and fall back to the base resume."""
    if not is_available():
        raise RuntimeError(
            "No tailoring provider configured — set GEMINI_API_KEY (free, "
            "recommended: https://aistudio.google.com/apikey) or "
            "ANTHROPIC_API_KEY (paid)."
        )

    user_prompt = _build_user_prompt(tex_source, jd_text, missing_skills, company, role_title)

    if os.environ.get("GEMINI_API_KEY"):
        new_tex = _call_gemini(user_prompt)
    else:
        new_tex = _call_anthropic(user_prompt)

    if not new_tex.startswith(r"\documentclass"):
        raise RuntimeError("Tailoring output didn't look like a valid .tex file")

    diff = "\n".join(difflib.unified_diff(
        tex_source.splitlines(), new_tex.splitlines(),
        fromfile="original.tex", tofile="tailored.tex", lineterm=""
    ))

    return {"tex": new_tex, "diff": diff, "changed": new_tex.strip() != tex_source.strip()}


def save_diff(diff_text: str, company: str, role_slug: str) -> str:
    out_dir = os.path.join(os.path.dirname(__file__), "resumes", "diffs")
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, f"{date.today().isoformat()}_{company}_{role_slug}.diff")
    with open(path, "w") as f:
        f.write(diff_text or "(no changes made)")
    return path

"""
ats_score.py — heuristic keyword-overlap score between a job description
and a resume, in the same spirit as how most real ATS keyword-matching
modules work (they're not doing deep semantic understanding either).

score_jd_vs_resume() returns:
    score          0-100
    matched        skills found in BOTH the JD and the resume
    missing        skills found in the JD but NOT in the resume
                   (this list is what tailor.py tries to surface,
                   without inventing anything not already true)

This is deliberately dependency-free (no LLM call) so scoring always
works, even with no API key configured.
"""
import re
import yaml
import os

TAXONOMY_PATH = os.path.join(os.path.dirname(__file__), "skills_taxonomy.yaml")


def load_all_skills() -> list[str]:
    with open(TAXONOMY_PATH) as f:
        data = yaml.safe_load(f)
    skills = []
    for group in data.values():
        skills.extend(group)
    # Longer phrases first, so "power bi" matches before a hypothetical
    # bare "bi" entry would.
    return sorted(set(skills), key=len, reverse=True)


ALL_SKILLS = load_all_skills()


def _find_skills(text: str) -> set[str]:
    text = text.lower()
    found = set()
    for skill in ALL_SKILLS:
        pattern = r"(?<![a-z0-9])" + re.escape(skill) + r"(?![a-z0-9])"
        if re.search(pattern, text):
            found.add(skill)
    return found


def score_jd_vs_resume(jd_text: str, resume_text: str) -> dict:
    jd_skills = _find_skills(jd_text)
    resume_skills = _find_skills(resume_text)

    if not jd_skills:
        # JD didn't hit any taxonomy terms — not enough signal to score
        # meaningfully. Default to a neutral score rather than 0, and
        # flag it so the pipeline doesn't wrongly force a tailoring pass.
        return {"score": 70.0, "matched": [], "missing": [],
                "low_signal": True}

    matched = sorted(jd_skills & resume_skills)
    missing = sorted(jd_skills - resume_skills)
    score = round(100 * len(matched) / len(jd_skills), 1)

    return {"score": score, "matched": matched, "missing": missing,
            "low_signal": False}

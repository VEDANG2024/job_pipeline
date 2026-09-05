"""
prepare_application.py — for one scored/filtered job, this:
  1. Scores the JD against BOTH resumes (Analyst and SWE) via
     ats_score.py and uses whichever fits better. This is a fast,
     free, local keyword comparison — no API call, so it never depends
     on Gemini's availability or quota.
  2. Optionally (config.yaml: tailoring.enabled, off by default)
     rewrites the chosen resume's wording via Gemini if its fit score
     is below the threshold. If this is off, fails, or the daily
     budget is spent, the base resume from step 1 is used as-is — a
     tailoring outcome NEVER blocks applying.
  3. If the job is on Greenhouse or Lever (the only two ATSs this
     pipeline submits to) and apply.enabled is true: attempts the
     application via apply_bot.py, right here, using whatever resume
     step 1/2 landed on, unconditionally.
  4. Logs one row to application_log.csv via spreadsheet_log.py.

NOTE ON "status": for Greenhouse/Lever jobs with apply.enabled, status
becomes one of `submitted`, `auto_apply_dry_run_ready`, or
`auto_apply_blocked_incomplete` — see apply_result for specifics
(fields filled, what's missing, the screenshot path). Everything else
(LinkedIn/Naukri/Indeed/Glassdoor/Workday/company sites) is
`package_ready` — fully prepared, needs your click.
"""
import os
from datetime import date

import ats_score
import spreadsheet_log
from tex_to_text import flatten_file

BASE_DIR = os.path.dirname(__file__)
AUTO_SUBMIT_ATS = {"greenhouse", "lever"}


def _slug(text: str) -> str:
    return "".join(c if c.isalnum() else "_" for c in text)[:40].strip("_")


def _pick_best_resume(job: dict, cfg: dict) -> tuple:
    """Scores the JD against both resumes and returns
    (role, resume_pdf_path, ats_score_result) for whichever fits
    better. No tailoring, no API call — always succeeds.

    The raw ATS keyword score ties constantly (most often at the flat
    70.0 "low signal" score returned when a JD's text doesn't hit any
    taxonomy keyword at all — common with mangled/terse descriptions,
    and identical for both resumes since it doesn't even look at
    resume content in that case). A plain ">" comparison on a tie
    always fell through to "analyst" since it's checked first in the
    loop, which silently sent the Analyst resume to a large share of
    postings classify.py itself had already tagged "swe" from the
    title/keywords.

    Fix: trust classify.py's title/keyword classification (role_category)
    as the primary signal — it's already reliable — and only let the
    ATS content score override it when the OTHER resume clearly fits
    better by a real margin, not a tie. Postings classify.py couldn't
    categorize ("other") fall back to pure content-score comparison."""
    jd_text = job.get("description", "")
    scores = {}
    for role in ("analyst", "swe"):
        resume_cfg = cfg["resumes"][role]
        tex_path = os.path.join(BASE_DIR, resume_cfg["tex"])
        resume_text = flatten_file(tex_path)
        scores[role] = ats_score.score_jd_vs_resume(jd_text, resume_text)

    classified = job.get("role_category")
    margin = cfg["filters"].get("resume_override_margin", 15)

    if classified in ("analyst", "swe"):
        other = "swe" if classified == "analyst" else "analyst"
        best_role = other if scores[other]["score"] > scores[classified]["score"] + margin else classified
    else:
        best_role = max(scores, key=lambda r: scores[r]["score"])

    resume_cfg = cfg["resumes"][best_role]
    return best_role, os.path.join(BASE_DIR, resume_cfg["pdf"]), scores[best_role]


def _maybe_tailor(job: dict, cfg: dict, role: str, resume_file: str, result: dict) -> tuple:
    """Optional step, off by default (config.yaml: tailoring.enabled).
    Returns (resume_file, tailored_bool) — on any failure or if
    disabled, returns the inputs unchanged so the caller always has a
    usable resume regardless of what happens here."""
    tailoring_cfg = cfg.get("tailoring", {})
    if not tailoring_cfg.get("enabled"):
        return resume_file, False
    if result["score"] >= cfg["filters"]["ats_tailor_threshold"]:
        return resume_file, False

    try:
        import tailor
        import latex_compile
        tex_path = os.path.join(BASE_DIR, cfg["resumes"][role]["tex"])
        with open(tex_path, encoding="utf-8") as f:
            tex_source = f.read()
        tailoring = tailor.tailor_resume(
            tex_source, job.get("description", ""), result["missing"],
            company=job["company"], role_title=job["title"],
        )
        if not tailoring["changed"]:
            return resume_file, False
        out_pdf = os.path.join(
            BASE_DIR, "resumes", "tailored",
            f"{date.today().isoformat()}_{_slug(job['company'])}_{_slug(job['title'])}.pdf"
        )
        latex_compile.compile_tex(tailoring["tex"], out_pdf)
        tailor.save_diff(tailoring["diff"], _slug(job["company"]), _slug(job["title"]))
        return out_pdf, True
    except Exception as e:
        print(f"[prepare_application] tailoring skipped for "
              f"{job['company']} / {job['title']}: {e} — using the base resume instead")
        return resume_file, False


def _attempt_auto_apply(job: dict, resume_file: str, cfg: dict) -> tuple:
    """Returns (status, apply_result_text). Only called for Greenhouse/
    Lever jobs when apply.enabled is true. Never raises — a failure
    here falls back to package_ready with the error noted."""
    apply_cfg = cfg.get("apply", {})
    if job.get("ats") not in AUTO_SUBMIT_ATS or not apply_cfg.get("enabled") or not resume_file:
        return "package_ready", ""

    try:
        import apply_bot
        report = apply_bot.apply_to_job(
            job, resume_file, apply_cfg["applicant"],
            dry_run=apply_cfg.get("dry_run", True),
        )
    except Exception as e:
        return "package_ready", f"apply_bot error: {e}"

    if report["submitted"]:
        return "submitted", f"submitted — screenshot: {report['screenshot']}"
    if report["dry_run"]:
        missing = ", ".join(report["unfilled_required_fields"]) or "none"
        return ("auto_apply_dry_run_ready",
                f"dry-run filled ({', '.join(report['fields_filled']) or 'nothing'}); "
                f"unfilled required: {missing}; screenshot: {report['screenshot']}")
    missing = ", ".join(report["unfilled_required_fields"]) or "resume upload failed"
    return "auto_apply_blocked_incomplete", f"blocked — missing: {missing}"


def log_discovered_only(job: dict):
    """For jobs beyond pipeline.max_prepare_per_run: log the discovery
    with no ATS-detection network call and no resume scoring, so a
    broad search never balloons runtime no matter how many raw
    postings it finds."""
    spreadsheet_log.append_row({
        "date": date.today().isoformat(),
        "company": job["company"],
        "role_title": job["title"],
        "role_category": job.get("role_category", ""),
        "location": job.get("location", ""),
        "source": job.get("source", ""),
        "ats": "",
        "jd_brief": spreadsheet_log.brief(job.get("description", "")),
        "matched_skills": "", "missing_skills": "",
        "ats_score": "", "resume_variant": "", "tailored": "no",
        "resume_file": "", "job_url": job.get("url", ""),
        "status": "discovered_not_prepared", "apply_result": "",
    })


def prepare(job: dict, cfg: dict) -> dict:
    role, resume_file, result = _pick_best_resume(job, cfg)
    resume_file, tailored = _maybe_tailor(job, cfg, role, resume_file, result)

    status, apply_result = _attempt_auto_apply(job, resume_file, cfg)

    spreadsheet_log.append_row({
        "date": date.today().isoformat(),
        "company": job["company"],
        "role_title": job["title"],
        "role_category": job.get("role_category", ""),
        "location": job.get("location", ""),
        "source": job.get("source", ""),
        "ats": job.get("ats", ""),
        "jd_brief": spreadsheet_log.brief(job.get("description", "")),
        "matched_skills": ", ".join(result["matched"]),
        "missing_skills": ", ".join(result["missing"]),
        "ats_score": result["score"],
        "resume_variant": role,
        "tailored": "yes" if tailored else "no",
        "resume_file": resume_file,
        "job_url": job.get("url", ""),
        "status": status,
        "apply_result": apply_result,
    })

    job["ats_score"] = result["score"]
    job["resume_file"] = resume_file
    job["tailored"] = tailored
    job["status"] = status
    job["resume_to_use"] = role
    return job

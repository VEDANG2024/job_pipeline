"""
prepare_application.py — for one scored/filtered job, this:
  1. Picks the matching base resume (analyst / swe).
  2. Scores the JD against it (ats_score.py).
  3. If score < ats_tailor_threshold (default 85): tailors the .tex via
     tailor.py (LLM, truthful-content-only) and compiles a job-specific
     PDF. If tailoring is unavailable (no GEMINI_API_KEY) or fails,
     falls back to the base resume and flags the job for manual review
     rather than blocking the run.
  4. If the job is on Greenhouse or Lever (the only two ATSs this
     pipeline submits to) and apply.enabled is true: attempts the
     application via apply_bot.py, right here, so the outcome lands in
     the SAME row as everything else about this job.
  5. Logs one row to application_log.csv via spreadsheet_log.py.

NOTE ON "status": for Greenhouse/Lever jobs with apply.enabled, status
becomes one of `submitted`, `auto_apply_dry_run_ready`, or
`auto_apply_blocked_incomplete` — see apply_result for the specifics
(which fields filled, what's still missing, the screenshot path).
Everything else (LinkedIn/Naukri/Indeed/Glassdoor/Workday/company
sites) tops out at `package_ready` — fully prepared, needs your click.
"""
import os
from datetime import date

import ats_score
import tailor
import latex_compile
import spreadsheet_log
from tex_to_text import flatten_file

BASE_DIR = os.path.dirname(__file__)
AUTO_SUBMIT_ATS = {"greenhouse", "lever"}


def _slug(text: str) -> str:
    return "".join(c if c.isalnum() else "_" for c in text)[:40].strip("_")


def _attempt_auto_apply(job: dict, resume_file: str, cfg: dict) -> tuple:
    """Returns (status, apply_result_text). Only called for Greenhouse/
    Lever jobs when apply.enabled is true. Never raises — a failure
    here falls back to package_ready with the error noted, exactly
    like a tailoring failure does."""
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
    with no ATS-detection network call and no Gemini call, so a broad
    search never balloons runtime or API usage no matter how many raw
    postings it finds. Uses the base resume by default."""
    role = job.get("resume_to_use") or job.get("role_category")
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
        "ats_score": "", "resume_variant": role, "tailored": "no",
        "resume_file": "", "job_url": job.get("url", ""),
        "status": "discovered_not_prepared", "apply_result": "",
    })


def prepare(job: dict, cfg: dict) -> dict:
    role = job.get("resume_to_use") or job.get("role_category")
    resume_cfg = cfg["resumes"].get(role)

    if not resume_cfg:
        # "other" role category with no clear resume match (only reaches
        # here at all if it was an Ahmedabad mandatory-review posting).
        spreadsheet_log.append_row({
            "date": date.today().isoformat(),
            "company": job["company"],
            "role_title": job["title"],
            "role_category": job.get("role_category", "other"),
            "location": job.get("location", ""),
            "source": job.get("source", ""),
            "ats": job.get("ats", ""),
            "jd_brief": spreadsheet_log.brief(job.get("description", "")),
            "matched_skills": "", "missing_skills": "",
            "ats_score": "", "resume_variant": "", "tailored": "no",
            "resume_file": "", "job_url": job.get("url", ""),
            "status": "needs_resume_review", "apply_result": "",
        })
        return job

    tex_path = os.path.join(BASE_DIR, resume_cfg["tex"])
    base_pdf_path = os.path.join(BASE_DIR, resume_cfg["pdf"])
    resume_text = flatten_file(tex_path)

    result = ats_score.score_jd_vs_resume(job.get("description", ""), resume_text)
    threshold = cfg["filters"]["ats_tailor_threshold"]

    resume_file = base_pdf_path
    tailored = False
    status = "package_ready"

    if result["score"] < threshold:
        try:
            with open(tex_path, encoding="utf-8") as f:
                tex_source = f.read()
            tailoring = tailor.tailor_resume(
                tex_source, job.get("description", ""), result["missing"],
                company=job["company"], role_title=job["title"],
            )
            if tailoring["changed"]:
                out_pdf = os.path.join(
                    BASE_DIR, "resumes", "tailored",
                    f"{date.today().isoformat()}_{_slug(job['company'])}_{_slug(job['title'])}.pdf"
                )
                latex_compile.compile_tex(tailoring["tex"], out_pdf)
                tailor.save_diff(tailoring["diff"], _slug(job["company"]), _slug(job["title"]))
                resume_file = out_pdf
                tailored = True
            # else: model judged it couldn't improve without breaking a
            # truthfulness rule — base resume stands, no changes made.
        except (RuntimeError, latex_compile.CompileError) as e:
            print(f"[prepare_application] tailoring skipped for "
                  f"{job['company']} / {job['title']}: {e}")
            status = "needs_manual_tailor"

    apply_result = ""
    if status == "package_ready":  # only attempt auto-apply if tailoring didn't already fail
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
    return job

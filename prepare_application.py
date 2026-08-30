"""
prepare_application.py — for one scored/filtered job, this:
  1. Picks the matching base resume (analyst / swe).
  2. Scores the JD against it (ats_score.py).
  3. If score < ats_tailor_threshold (default 85): tailors the .tex via
     tailor.py (LLM, truthful-content-only) and compiles a job-specific
     PDF. If tailoring is unavailable (no GEMINI_API_KEY) or fails,
     falls back to the base resume and flags the job for manual review
     rather than blocking the run.
  4. Logs one row to application_log.csv via spreadsheet_log.py.

NOTE ON "status": this stage prepares the application package — it
does not click Apply anywhere yet. Status is written as
"package_ready" (or "needs_manual_tailor" / "needs_resume_review").
Once the next build phase (the actual submission layer — auto for
Greenhouse/Lever, human-gated review-and-click for LinkedIn/Naukri/
Indeed/Glassdoor/Workday) is wired in, that layer will flip the status
to "applied" after the real submission happens.
"""
import os
from datetime import date

import ats_score
import tailor
import latex_compile
import spreadsheet_log
from tex_to_text import flatten_file

BASE_DIR = os.path.dirname(__file__)


def _slug(text: str) -> str:
    return "".join(c if c.isalnum() else "_" for c in text)[:40].strip("_")


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
            "status": "needs_resume_review",
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
    })

    job["ats_score"] = result["score"]
    job["resume_file"] = resume_file
    job["tailored"] = tailored
    return job

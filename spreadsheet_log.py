"""
spreadsheet_log.py — appends one row per job to a CSV "spreadsheet".

Columns match what you asked for (role, JD brief, skills, company),
plus the ATS/tailoring bookkeeping so you can see at a glance what
happened to each application package.

Why CSV and not live Google Sheets: zero auth setup, works immediately,
and opens natively in Excel/Sheets/Numbers. If you want it synced to a
live Google Sheet instead (so it updates on your phone in real time),
that's a small follow-on build using the Sheets API + a service account
— say the word and I'll wire it in.
"""
import csv
import os

LOG_PATH = os.path.join(os.path.dirname(__file__), "application_log.csv")

FIELDS = [
    "date", "company", "role_title", "role_category", "location",
    "source", "jd_brief", "matched_skills", "missing_skills",
    "ats_score", "resume_variant", "tailored", "resume_file",
    "job_url", "status",
]


def _ensure_header():
    if not os.path.exists(LOG_PATH):
        with open(LOG_PATH, "w", newline="") as f:
            csv.DictWriter(f, fieldnames=FIELDS).writeheader()


def brief(description: str, max_len: int = 220) -> str:
    text = " ".join((description or "").split())
    return text[:max_len] + ("…" if len(text) > max_len else "")


def append_row(row: dict):
    _ensure_header()
    with open(LOG_PATH, "a", newline="") as f:
        csv.DictWriter(f, fieldnames=FIELDS, extrasaction="ignore").writerow(row)

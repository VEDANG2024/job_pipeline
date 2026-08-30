"""
Regression test for the pandas-NaN-is-truthy bug that crashed the
2026-08-30 production run (AttributeError: 'float' object has no
attribute 'lower').

python-jobspy returns rows from a pandas DataFrame, where a missing
field is `float('nan')` — not None, not "". `value or ""` does NOT
catch this because NaN is truthy in Python. This test feeds NaN
straight into every function that used to call `.lower()`/`.strip()`
on raw field values, to make sure safe.s() actually protects them.

Run with: python tests/test_nan_safety.py
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.chdir(os.path.join(os.path.dirname(__file__), ".."))

import yaml
from classify import score_and_filter
from db import job_id
from ats_score import score_jd_vs_resume
import spreadsheet_log

NAN = float("nan")

with open("config.yaml") as f:
    cfg = yaml.safe_load(f)
cfg["_big_company_set"] = set()

# A job dict with every single field NaN except the ones needed to
# reach the interesting code paths — this is the actual worst case
# JobSpy can hand back.
nan_job = {
    "source": "jobspy:linkedin",
    "company": NAN,
    "title": NAN,
    "location": NAN,
    "url": NAN,
    "description": NAN,
    "posted_date": NAN,
    "employment_type": NAN,
}

result = score_and_filter(dict(nan_job), cfg)
print("classify.score_and_filter survived all-NaN job:", result["role_category"],
      result["location_priority"], result["score"])

jid = job_id(nan_job["company"], nan_job["title"], nan_job["url"])
print("db.job_id survived all-NaN job:", jid)

ats_result = score_jd_vs_resume(NAN, "SQL Power BI Python")
print("ats_score.score_jd_vs_resume survived NaN JD text:", ats_result["score"])

brief = spreadsheet_log.brief(NAN)
print("spreadsheet_log.brief survived NaN description:", repr(brief))

print("\nAll NaN-safety checks passed — no AttributeError.")

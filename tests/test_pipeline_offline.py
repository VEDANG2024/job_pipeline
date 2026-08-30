"""
Offline sanity test for the whole pipeline using synthetic postings —
this sandbox's network is locked to package registries, so it can't
reach boards-api.greenhouse.io / api.lever.co / etc. This test stands
in for that by feeding fabricated-but-realistic job dicts straight
into score_and_filter() + prepare(), exercising:
  - role classification (analyst vs swe vs other)
  - the Ahmedabad-mandatory-inclusion rule
  - the internship stipend floor
  - ATS scoring against the real resumes
  - PDF compilation (tailoring itself is skipped — no API key here)
Run with: python tests/test_pipeline_offline.py
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.chdir(os.path.join(os.path.dirname(__file__), ".."))

import yaml
from classify import score_and_filter
from prepare_application import prepare

with open("config.yaml") as f:
    cfg = yaml.safe_load(f)
cfg["_big_company_set"] = {"stripe", "razorpay"}

SYNTHETIC_JOBS = [
    {  # Ahmedabad analyst role, decent match -> should score high, pass, low tailor need
        "source": "test", "company": "Stripe",
        "title": "Business Analyst",
        "location": "Ahmedabad, Gujarat, India",
        "url": "https://example.com/job/1",
        "description": ("0-2 years experience. SQL, Power BI, Advanced Excel, "
                         "stakeholder management, requirements gathering, "
                         "process mapping, UAT, Six Sigma required."),
    },
    {  # Ahmedabad posting requiring 5 years -> mandatory_review, not dropped
        "source": "test", "company": "Adani",
        "title": "Senior Data Analyst",
        "location": "Ahmedabad, Gujarat, India",
        "url": "https://example.com/job/2",
        "description": "Minimum of 5 years experience with SQL and Power BI.",
    },
    {  # Non-Ahmedabad internship below stipend floor -> dropped
        "source": "test", "company": "RandomStartup",
        "title": "Data Analyst Internship",
        "location": "Pune, India",
        "url": "https://example.com/job/3",
        "description": "Internship stipend Rs 12,000/month. SQL, Excel.",
    },
    {  # Remote SWE role, weak resume match -> should trigger tailoring path
        "source": "test", "company": "Razorpay",
        "title": "Software Engineer",
        "location": "Remote",
        "url": "https://example.com/job/4",
        "description": ("0-2 years. Python, REST API, AWS, Docker, Kubernetes, "
                         "CI/CD, system design, microservices required."),
    },
]

scored = [score_and_filter(dict(j), cfg) for j in SYNTHETIC_JOBS]

print("=== score_and_filter results ===")
for j in scored:
    print(f"{j['company']:15s} | passes={bool(j['passes_filters'])!s:5s} | "
          f"mandatory_review={bool(j['mandatory_review'])!s:5s} | "
          f"role={j['role_category']:8s} | loc={j['location_priority']:10s} | "
          f"score={j['score']}")

assert scored[0]["passes_filters"] == 1, "Ahmedabad analyst match should pass"
assert scored[1]["passes_filters"] == 1 and scored[1]["mandatory_review"] == 1, \
    "Ahmedabad posting outside experience band must still pass, flagged for review"
assert scored[2]["passes_filters"] == 0, "Sub-floor internship must be dropped"
assert scored[3]["passes_filters"] == 1, "Remote SWE match should pass"
print("\nAll classify.py assertions passed.\n")

print("=== prepare_application results (no ANTHROPIC_API_KEY -> no live tailoring) ===")
kept = [j for j in scored if j["passes_filters"]]
for j in kept:
    prepare(j, cfg)
    print(f"{j['company']:15s} | ats_score={j.get('ats_score')} | "
          f"tailored={j.get('tailored')} | resume_file={j.get('resume_file')}")

print("\nCheck application_log.csv for the logged rows:")
with open("application_log.csv") as f:
    print(f.read())

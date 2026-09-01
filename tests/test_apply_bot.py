"""
Regression test for apply_bot.py's core safety guarantees, run against
a real headless Chromium browser and local HTML fixtures that
approximate Greenhouse/Lever form structure. This does NOT verify
behavior against the real live sites (no network route to them from
where this was built) — it verifies the fill/submit-gating LOGIC is
sound, which is the part that matters most to get right before ever
pointing it at a real application.

Run with: python tests/test_apply_bot.py
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.chdir(os.path.join(os.path.dirname(__file__), ".."))

from playwright.sync_api import sync_playwright
import apply_bot

APPLICANT = {
    "first_name": "Vedang", "last_name": "Trivedi", "full_name": "Vedang Trivedi",
    "email": "vedangtrivediworks@gmail.com", "phone": "9999999999",
    "linkedin_url": "https://www.linkedin.com/in/vedang-trivedi-0389a91b9",
}

GH_FIXTURE = "file://" + os.path.abspath("tests/fixtures/greenhouse_like.html")
LEVER_FIXTURE = "file://" + os.path.abspath("tests/fixtures/lever_like.html")


def run(fixture_url, resume, dry_run):
    job = {"company": "TestCo", "title": "Role", "final_url": fixture_url}
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.goto(fixture_url)
        report = apply_bot.fill_application(page, job, resume, APPLICANT, dry_run=dry_run)
        browser.close()
    return report


# 1. Greenhouse-style: dry_run=True never submits, even though most fields fill fine
r = run(GH_FIXTURE, "resumes/VedangTrivedi_Analyst.pdf", dry_run=True)
assert set(r["fields_filled"]) >= {"first_name", "last_name", "email", "phone"}
assert r["resume_uploaded"] is True
assert r["submitted"] is False
print("1. Greenhouse-style dry_run=True: fields filled, never submitted — OK")

# 2. Greenhouse-style: has a required essay field we can't answer -> must
#    refuse to submit even with dry_run=False
r = run(GH_FIXTURE, "resumes/VedangTrivedi_Analyst.pdf", dry_run=False)
assert "why_interested" in r["unfilled_required_fields"]
assert r["ready_to_submit"] is False
assert r["submitted"] is False
print("2. Greenhouse-style dry_run=False, incomplete form: submission blocked — OK")

# 3. Lever-style: fully fillable, dry_run=True still never submits
r = run(LEVER_FIXTURE, "resumes/VedangTrivedi_SWE.pdf", dry_run=True)
assert r["unfilled_required_fields"] == []
assert r["submitted"] is False
print("3. Lever-style dry_run=True, complete form: still never submitted — OK")

# 4. Lever-style: fully fillable, dry_run=False -> submits
r = run(LEVER_FIXTURE, "resumes/VedangTrivedi_SWE.pdf", dry_run=False)
assert r["ready_to_submit"] is True
assert r["submitted"] is True
print("4. Lever-style dry_run=False, complete form: submitted — OK")

# 5. Missing resume file -> never submits even if every other field is fine
r = run(LEVER_FIXTURE, "resumes/does_not_exist.pdf", dry_run=False)
assert r["resume_uploaded"] is False
assert r["ready_to_submit"] is False
assert r["submitted"] is False
print("5. Missing resume file: submission blocked regardless of dry_run — OK")

print("\nAll apply_bot safety checks passed.")

"""
apply_bot.py — Playwright-based auto-fill for Greenhouse and Lever
application forms. These are the only two ATSs this pipeline
auto-submits to, and only after this file's checks pass — see README
for why LinkedIn/Naukri/Wellfound/Workday are handled differently.

Safety model, in order:
1. Dry-run by default (config.yaml: apply.dry_run). Fills what it can
   identify, screenshots the result, and stops — Submit is never
   clicked. Filling a form has zero effect on the employer's side;
   nothing is sent anywhere until Submit is clicked.
2. Even with dry_run turned off, a required field (detected live via
   the page's own `required` attribute, not guessed) that this bot
   couldn't fill blocks submission outright. An incomplete application
   is never submitted, regardless of the dry_run setting.
3. The resume file must have actually attached successfully, or
   submission is blocked.

IMPORTANT — read before trusting this: it's been verified against
local synthetic HTML fixtures that approximate Greenhouse/Lever's
typical form structure (tests/fixtures/), not against live
greenhouse.io / lever.co pages — this was built in a sandbox with no
network route to those domains. Review the first several real dry-run
screenshots against the actual job posting before ever setting
apply.dry_run to false.
"""
import os
import re
from datetime import date

SCREENSHOT_DIR = os.path.join(os.path.dirname(__file__), "applications", "screenshots")

# field_key -> label substrings to try, in order, via Playwright's
# label-based locator (robust to ID/class naming differences between
# companies using the same underlying ATS template).
FIELD_LABELS = {
    "first_name": ["first name"],
    "last_name": ["last name"],
    "full_name": ["full name", r"^name\*?$"],
    "email": ["email"],
    "phone": ["phone"],
    "linkedin": ["linkedin"],
}


def _slug(text: str) -> str:
    return "".join(c if c.isalnum() else "_" for c in text)[:50].strip("_")


def _try_fill_by_label(page, label_patterns, value) -> bool:
    for pattern in label_patterns:
        try:
            locator = page.get_by_label(re.compile(pattern, re.I))
            if locator.count() > 0 and locator.first.is_visible():
                locator.first.fill(value)
                return True
        except Exception:
            continue
    return False


def _find_file_input(page):
    try:
        inputs = page.locator("input[type='file']")
        if inputs.count() > 0:
            return inputs.first
    except Exception:
        pass
    return None


def _detect_unfilled_required(page) -> list:
    """Labels of any `required` input/textarea/select left empty —
    these must be completed by hand before this application can go
    out, dry_run or not. Detected from the live page, not guessed."""
    unfilled = []
    try:
        required_els = page.locator("[required]")
        for i in range(required_els.count()):
            el = required_els.nth(i)
            try:
                tag = el.evaluate("e => e.tagName")
                if tag == "SELECT":
                    value = el.evaluate("e => e.value")
                elif el.get_attribute("type") == "file":
                    value = "has-file" if el.evaluate(
                        "e => e.files && e.files.length > 0") else ""
                else:
                    value = el.input_value()
                if value:
                    continue
                label = (el.get_attribute("aria-label") or el.get_attribute("name")
                         or el.get_attribute("id") or f"unnamed_field_{i}")
                unfilled.append(label)
            except Exception:
                continue
    except Exception:
        pass
    return unfilled


def fill_application(page, job: dict, resume_path: str, applicant: dict,
                      dry_run: bool = True) -> dict:
    """Fills what it can identify on the current page (already
    navigated to the job's application URL). Returns a report dict.
    Never clicks Submit unless dry_run is False AND no required
    fields are left unfilled AND the resume attached successfully."""
    filled = {}

    def do_fill(key, value):
        if value and _try_fill_by_label(page, FIELD_LABELS[key], value):
            filled[key] = value

    do_fill("first_name", applicant.get("first_name"))
    do_fill("last_name", applicant.get("last_name"))
    if "first_name" not in filled and "last_name" not in filled:
        do_fill("full_name", applicant.get("full_name"))
    do_fill("email", applicant.get("email"))
    do_fill("phone", applicant.get("phone"))
    do_fill("linkedin", applicant.get("linkedin_url"))

    resume_uploaded = False
    file_input = _find_file_input(page)
    if file_input is not None and resume_path and os.path.exists(resume_path):
        try:
            file_input.set_input_files(resume_path)
            resume_uploaded = True
        except Exception:
            pass

    unfilled_required = _detect_unfilled_required(page)

    os.makedirs(SCREENSHOT_DIR, exist_ok=True)
    shot_name = (f"{date.today().isoformat()}_{_slug(job.get('company',''))}_"
                 f"{_slug(job.get('title',''))}.png")
    shot_path = os.path.join(SCREENSHOT_DIR, shot_name)
    try:
        page.screenshot(path=shot_path, full_page=True)
    except Exception:
        shot_path = None

    ready_to_submit = (not dry_run) and resume_uploaded and not unfilled_required
    submitted = False

    if ready_to_submit:
        try:
            submit_btn = page.get_by_role("button", name=re.compile("submit", re.I))
            if submit_btn.count() > 0:
                submit_btn.first.click()
                submitted = True
        except Exception:
            submitted = False

    return {
        "fields_filled": sorted(filled.keys()),
        "resume_uploaded": resume_uploaded,
        "unfilled_required_fields": unfilled_required,
        "screenshot": shot_path,
        "dry_run": dry_run,
        "ready_to_submit": ready_to_submit,
        "submitted": submitted,
    }


def apply_to_job(job: dict, resume_path: str, applicant: dict, dry_run: bool = True) -> dict:
    """Launches a headless browser, navigates to job['final_url'], and
    runs fill_application(). Only call this for jobs where
    ats_detect.can_auto_submit(job) is True."""
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        try:
            page.goto(job["final_url"], timeout=30000, wait_until="domcontentloaded")
            page.wait_for_timeout(1500)  # let any JS-rendered form fields settle
            report = fill_application(page, job, resume_path, applicant, dry_run=dry_run)
        finally:
            browser.close()
    return report

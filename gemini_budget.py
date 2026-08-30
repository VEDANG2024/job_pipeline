"""
gemini_budget.py — a hard, persisted daily budget on Gemini calls.

Why this exists: Google's free tier for gemini-3.6-flash turned out to
cap at 20 requests/DAY per project/model (not per-minute, as commonly
assumed for Flash models). When that quota was hit mid-run, the
pipeline kept firing a fresh request for the next job anyway, got
429'd repeatedly in a tight loop, and ignored the API's own
`retryDelay` hints entirely. That rapid-fire-against-an-exhausted-quota
pattern is exactly what got the Google Cloud project — and then the
whole Google Cloud account — suspended for "repeated Terms of Service
violations."

This module makes that failure mode structurally impossible: once the
daily budget is spent — or the very first real 429 comes back — NO
further Gemini call is attempted for the rest of the day, on this run
or any later run today. State is a small JSON file in data/, which the
GitHub Actions workflow already commits back to the repo alongside
everything else, so the budget persists across both daily runs.

Fail-safe, not fail-open: if the state file is missing, that's treated
as a legitimate first-ever run (fresh budget). If the file EXISTS but
is corrupted, has the wrong shape, or has been tampered with, that's
treated as exhausted — better to skip a day of tailoring than to
silently hand out a budget we can't actually verify.
"""
import json
import os
from datetime import date

STATE_PATH = os.path.join(os.path.dirname(__file__), "data", "gemini_usage.json")

# Google's free tier reported a hard limit of 20 requests/day per
# project/model in production (see the incident above). Staying well
# under that leaves headroom in case anything else shares the same
# project/key, or the limit changes again.
MAX_DAILY_CALLS = 15


def _fresh_state() -> dict:
    return {"date": date.today().isoformat(), "calls_used": 0, "exhausted": False}


def _fail_safe_state() -> dict:
    """The state file exists but looks wrong somehow — never hand out
    a fresh budget in that case. A missing file (first run ever) is
    the only situation that gets _fresh_state()."""
    return {"date": date.today().isoformat(), "calls_used": MAX_DAILY_CALLS, "exhausted": True}


def _load() -> dict:
    if not os.path.exists(STATE_PATH):
        return _fresh_state()  # legitimately the first run ever

    try:
        with open(STATE_PATH) as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError):
        return _fail_safe_state()

    if not isinstance(data, dict):
        return _fail_safe_state()

    stored_date = data.get("date")
    calls_used = data.get("calls_used")
    exhausted = data.get("exhausted")

    # Any shape anomaly (wrong types, negative count, missing field)
    # is treated as corruption, not as "assume zero and carry on."
    if (not isinstance(stored_date, str) or not isinstance(calls_used, int)
            or isinstance(calls_used, bool) or not isinstance(exhausted, bool)
            or calls_used < 0):
        return _fail_safe_state()

    if stored_date != date.today().isoformat():
        return _fresh_state()  # legitimate day rollover

    return {"date": stored_date, "calls_used": calls_used, "exhausted": exhausted}


def _save(data: dict):
    os.makedirs(os.path.dirname(STATE_PATH), exist_ok=True)
    with open(STATE_PATH, "w") as f:
        json.dump(data, f)


def can_call() -> bool:
    data = _load()
    return not data.get("exhausted") and data.get("calls_used", 0) < MAX_DAILY_CALLS


def record_call():
    data = _load()
    data["calls_used"] = data.get("calls_used", 0) + 1
    _save(data)


def record_quota_exhausted():
    """Call this the instant a real 429/RESOURCE_EXHAUSTED comes back.
    Marks the budget spent immediately regardless of our own count —
    this is the line that stops the hammering pattern that caused the
    suspension, since every subsequent job this run (and any run later
    today) will see can_call() == False and skip Gemini entirely."""
    data = _load()
    data["exhausted"] = True
    _save(data)


def status() -> dict:
    return _load()


def status_banner() -> str:
    """A one-line, impossible-to-miss summary for the top of the run
    log — the original incident was partly hard to diagnose because
    nothing surfaced the budget state clearly until things had already
    gone wrong."""
    s = _load()
    if s["exhausted"]:
        return f"Gemini budget: EXHAUSTED for {s['date']} — no tailoring calls will be attempted."
    remaining = MAX_DAILY_CALLS - s["calls_used"]
    return f"Gemini budget: {s['calls_used']}/{MAX_DAILY_CALLS} used today, {remaining} remaining."


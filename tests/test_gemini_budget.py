"""
Regression test for gemini_budget.py's fail-safe design: a missing
state file (first run ever) gets a fresh budget; an existing-but-
broken state file does NOT — it's treated as exhausted. This is the
guardrail against the state file being deleted, corrupted, or
otherwise tampered with and silently handing out a budget we can't
verify.

Run with: python tests/test_gemini_budget.py
"""
import os
import sys
import json
from datetime import date, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.chdir(os.path.join(os.path.dirname(__file__), ".."))

import gemini_budget as gb

STATE_PATH = gb.STATE_PATH


def reset():
    if os.path.exists(STATE_PATH):
        os.remove(STATE_PATH)


def write_raw(obj_or_text):
    os.makedirs(os.path.dirname(STATE_PATH), exist_ok=True)
    with open(STATE_PATH, "w") as f:
        if isinstance(obj_or_text, str):
            f.write(obj_or_text)
        else:
            json.dump(obj_or_text, f)


# 1. Missing file -> fresh budget (legitimate first-ever run)
reset()
assert gb.can_call() is True
s = gb.status()
assert s == {"date": date.today().isoformat(), "calls_used": 0, "exhausted": False}
print("1. Missing file -> fresh budget: OK")

# 2. Corrupted (unparseable) JSON -> fail-safe exhausted, NOT fresh
write_raw("{not valid json!!!")
assert gb.can_call() is False
assert gb.status()["exhausted"] is True
print("2. Corrupted JSON -> fail-safe exhausted: OK")

# 3. Valid JSON but wrong shape (calls_used is a string) -> fail-safe
write_raw({"date": date.today().isoformat(), "calls_used": "lots", "exhausted": False})
assert gb.can_call() is False
print("3. Wrong-typed field -> fail-safe exhausted: OK")

# 4. Valid JSON but negative calls_used -> fail-safe
write_raw({"date": date.today().isoformat(), "calls_used": -5, "exhausted": False})
assert gb.can_call() is False
print("4. Negative calls_used -> fail-safe exhausted: OK")

# 5. Valid JSON, not even a dict -> fail-safe
write_raw([1, 2, 3])
assert gb.can_call() is False
print("5. Non-dict JSON -> fail-safe exhausted: OK")

# 6. Legitimate day rollover -> fresh budget, not fail-safe
yesterday = (date.today() - timedelta(days=1)).isoformat()
write_raw({"date": yesterday, "calls_used": 15, "exhausted": True})
assert gb.can_call() is True  # new day, budget resets
print("6. Day rollover -> fresh budget: OK")

# 7. Normal increment behavior
reset()
for i in range(gb.MAX_DAILY_CALLS):
    assert gb.can_call() is True
    gb.record_call()
assert gb.can_call() is False  # budget spent normally
print(f"7. {gb.MAX_DAILY_CALLS} calls exhaust the budget normally: OK")

# 8. record_quota_exhausted() stops things immediately regardless of count
reset()
gb.record_call()  # just 1 call used
assert gb.can_call() is True
gb.record_quota_exhausted()  # but a real 429 came back
assert gb.can_call() is False  # stops immediately, not at the count-based limit
print("8. record_quota_exhausted() stops immediately: OK")

reset()
print("\nAll gemini_budget fail-safe checks passed.")

# 9. wait_before_call() actually paces consecutive calls (mocked time,
#    so this test doesn't really take 12+ seconds)
from unittest.mock import patch

sleep_calls = []
fake_now = [1000.0]

def fake_time():
    return fake_now[0]

def fake_sleep(seconds):
    sleep_calls.append(seconds)
    fake_now[0] += seconds

gb._last_call_time[0] = 0.0
with patch("time.time", side_effect=fake_time), patch("time.sleep", side_effect=fake_sleep):
    gb.wait_before_call()  # first call: plenty of time has "passed" -> no sleep
    assert sleep_calls == []
    fake_now[0] += 2  # only 2 real seconds before the next call
    gb.wait_before_call()  # elapsed=2 < 12 -> must sleep for the remaining 10
    assert sleep_calls == [10], sleep_calls

print("9. wait_before_call() paces consecutive calls: OK")
print("\nAll gemini_budget checks passed.")


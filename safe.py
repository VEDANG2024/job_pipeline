"""
safe.py — one tiny utility used everywhere a field from an external
source gets a string operation called on it.

Why this exists: python-jobspy returns rows from a pandas DataFrame.
When a field like `description` is missing, pandas fills it with
`float('nan')` — NOT None, NOT "". The classic `value or ""` pattern
does NOT catch this, because NaN is truthy in Python (only 0.0 is a
falsy float). That truthy-NaN then hits a `.lower()` call somewhere
downstream and crashes with `AttributeError: 'float' object has no
attribute 'lower'`. This module is the one place that fix lives.
"""


def s(x) -> str:
    """Coerce any value to a safe string. Handles None, NaN floats,
    and anything else by just str()-ing it."""
    if x is None:
        return ""
    if isinstance(x, float) and x != x:  # NaN is the only float where x != x
        return ""
    return str(x)

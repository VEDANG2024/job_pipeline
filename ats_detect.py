"""
ats_detect.py — figures out which application system a posting actually
lands on. Adzuna's `redirect_url` (and some JobSpy results) are tracking
links, not the employer's real apply page, so this follows the redirect
to find the true destination, then classifies it.

Why this exists: it's the honest answer to "can this be applied to
directly?" — Greenhouse and Lever postings CAN eventually be
auto-submitted (public, intentionally-scriptable, no personal login
involved). LinkedIn, Naukri, Indeed, and Glassdoor postings need either
your logged-in session (meaning your credentials, which carries real
account-ban risk — see README) or a human click, and generic company
career sites vary too much to generalize safely. This module doesn't
submit anything — it just labels each job so you and the pipeline both
know which bucket it's in.
"""
import re
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed

ATS_PATTERNS = [
    ("greenhouse", re.compile(r"greenhouse\.io", re.I)),
    ("lever", re.compile(r"lever\.co", re.I)),
    ("workday", re.compile(r"myworkdayjobs\.com", re.I)),
    ("linkedin", re.compile(r"linkedin\.com", re.I)),
    ("naukri", re.compile(r"naukri\.com", re.I)),
    ("indeed", re.compile(r"indeed\.com", re.I)),
    ("glassdoor", re.compile(r"glassdoor\.", re.I)),
    ("remoteok", re.compile(r"remoteok\.com", re.I)),
    ("weworkremotely", re.compile(r"weworkremotely\.com", re.I)),
]

# The only two ATSs that can be safely auto-submitted without either
# risking an account ban or needing your login credentials.
AUTO_SUBMIT_READY = {"greenhouse", "lever"}


def classify_url(url: str) -> str:
    for name, pattern in ATS_PATTERNS:
        if pattern.search(url or ""):
            return name
    return "company_site"


def resolve_final_url(url: str, timeout: int = 15) -> str:
    """Follows redirects (e.g. Adzuna's tracking link) to the real
    destination. Never raises — falls back to the original URL on any
    failure, since one slow/broken site must not block the whole run."""
    if not url:
        return url
    try:
        r = requests.head(url, allow_redirects=True, timeout=timeout)
        if r.status_code >= 400:
            r = requests.get(url, allow_redirects=True, timeout=timeout, stream=True)
        return r.url
    except requests.RequestException:
        return url


def detect_one(job: dict) -> dict:
    """Adds 'final_url' and 'ats' to a single job dict."""
    source = job.get("source", "")
    url = job.get("url", "")

    # Sources we already know the ATS for — skip the network round-trip.
    known = {"greenhouse": "greenhouse", "lever": "lever",
             "remoteok": "remoteok", "weworkremotely": "weworkremotely"}
    if source in known:
        job["final_url"] = url
        job["ats"] = known[source]
        return job

    final_url = resolve_final_url(url)
    job["final_url"] = final_url
    job["ats"] = classify_url(final_url)
    return job


def detect_all(jobs: list, max_workers: int = 15) -> list:
    """Runs detect_one concurrently across a batch of jobs. Order of
    the returned list is not guaranteed to match the input."""
    results = []
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = [pool.submit(detect_one, j) for j in jobs]
        for f in as_completed(futures):
            results.append(f.result())
    return results


def can_auto_submit(job: dict) -> bool:
    return job.get("ats") in AUTO_SUBMIT_READY


def summarize(jobs: list) -> dict:
    from collections import Counter
    return dict(Counter(j.get("ats", "unknown") for j in jobs))

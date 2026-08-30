"""Greenhouse public Job Board API.
https://boards-api.greenhouse.io/v1/boards/{token}/jobs?content=true
No auth, no login required — this is Greenhouse's intended public
read API, used by companies' own careers pages."""
import requests

BASE = "https://boards-api.greenhouse.io/v1/boards/{token}/jobs"


def fetch(token: str) -> list:
    url = BASE.format(token=token)
    r = requests.get(url, params={"content": "true"}, timeout=20)
    r.raise_for_status()
    data = r.json()
    jobs = []
    for j in data.get("jobs", []):
        jobs.append({
            "source": "greenhouse",
            "company": token,
            "title": j.get("title", ""),
            "location": (j.get("location") or {}).get("name", ""),
            "url": j.get("absolute_url", ""),
            "description": j.get("content", "") or "",
            "posted_date": j.get("updated_at", ""),
            "employment_type": "",
        })
    return jobs

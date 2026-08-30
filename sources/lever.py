"""Lever public postings API.
https://api.lever.co/v0/postings/{token}?mode=json
No auth, no login required."""
import requests

BASE = "https://api.lever.co/v0/postings/{token}"


def fetch(token: str) -> list:
    url = BASE.format(token=token)
    r = requests.get(url, params={"mode": "json"}, timeout=20)
    r.raise_for_status()
    jobs = []
    for j in r.json():
        cat = j.get("categories", {}) or {}
        jobs.append({
            "source": "lever",
            "company": token,
            "title": j.get("text", ""),
            "location": cat.get("location", ""),
            "url": j.get("hostedUrl", ""),
            "description": j.get("descriptionPlain", "") or j.get("description", ""),
            "posted_date": str(j.get("createdAt", "")),
            "employment_type": cat.get("commitment", ""),
        })
    return jobs

"""RemoteOK public JSON feed: https://remoteok.com/api
The first element of the response is metadata, not a job — skip it."""
import requests

URL = "https://remoteok.com/api"


def fetch() -> list:
    headers = {"User-Agent": "job-pipeline/1.0 (personal job search tool)"}
    r = requests.get(URL, headers=headers, timeout=20)
    r.raise_for_status()
    data = r.json()
    jobs = []
    for j in data:
        if "id" not in j:
            continue  # metadata row
        jobs.append({
            "source": "remoteok",
            "company": j.get("company", ""),
            "title": j.get("position", ""),
            "location": j.get("location", "Remote") or "Remote",
            "url": j.get("url", ""),
            "description": j.get("description", "") or "",
            "posted_date": j.get("date", ""),
            "employment_type": "",
        })
    return jobs

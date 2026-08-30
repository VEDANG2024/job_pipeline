"""
Adzuna public Jobs API — aggregates postings from 30+ sources including
Workday, Indeed, and Glassdoor, searched by keyword + location rather
than by company. This is what makes "no company list" discovery work:
Adzuna already crawls the companies — you just search by role.

Free signup (2 min, no cost): https://developer.adzuna.com/
Free tier is roughly 1,000 calls/month — the query list in config.yaml
is kept modest so a twice-daily run stays well inside that.

Docs: https://developer.adzuna.com/docs/search
"""
import os
import requests

BASE = "https://api.adzuna.com/v1/api/jobs/{country}/search/{page}"


def fetch(keywords: str, location: str, country: str = "in",
          results_per_page: int = 50, max_pages: int = 1) -> list:
    app_id = os.environ.get("ADZUNA_APP_ID")
    app_key = os.environ.get("ADZUNA_APP_KEY")
    if not app_id or not app_key:
        print("[adzuna] ADZUNA_APP_ID / ADZUNA_APP_KEY not set — skipping. "
              "Free signup: https://developer.adzuna.com/")
        return []

    jobs = []
    for page in range(1, max_pages + 1):
        url = BASE.format(country=country, page=page)
        params = {
            "app_id": app_id,
            "app_key": app_key,
            "what": keywords,
            "where": location,
            "results_per_page": results_per_page,
            "content-type": "application/json",
        }
        try:
            r = requests.get(url, params=params, timeout=20)
            r.raise_for_status()
        except requests.RequestException as e:
            print(f"[adzuna] request failed for '{keywords}' @ {location}: {e}")
            break

        data = r.json()
        results = data.get("results", [])
        if not results:
            break

        for j in results:
            company = (j.get("company") or {}).get("display_name", "")
            loc = (j.get("location") or {}).get("display_name", "")
            jobs.append({
                "source": "adzuna",
                "company": company,
                "title": j.get("title", ""),
                "location": loc,
                "url": j.get("redirect_url", ""),
                "description": j.get("description", "") or "",
                "posted_date": j.get("created", ""),
                "employment_type": j.get("contract_time", "") or "",
            })
    return jobs

"""
Best-effort discovery via LinkedIn / Indeed / Glassdoor / Naukri / Google,
using the `python-jobspy` library.

Read this before relying on it:
- These sites actively rate-limit and block scraping. Expect 429s,
  partial results, and periodic breakage when a site changes its markup.
  This is discovery-only (reading public search results) — it does not
  log into your accounts, so it doesn't carry the account-ban risk that
  automating actual applications on these sites would.
- Wrapped in try/except per query so one blocked site doesn't kill the run.
- Keep results_wanted modest and don't run this more than a few times a
  day — see README for details.
"""


def fetch(search_term: str, locations: list, sites: list,
          results_wanted: int, hours_old: int) -> list:
    try:
        from jobspy import scrape_jobs
    except ImportError:
        print("[jobspy] python-jobspy not installed — skipping this source. "
              "Run: pip install python-jobspy --break-system-packages")
        return []

    all_jobs = []
    for location in locations:
        try:
            df = scrape_jobs(
                site_name=sites,
                search_term=search_term,
                location=location,
                results_wanted=results_wanted,
                hours_old=hours_old,
                country_indeed="India",
            )
        except Exception as e:
            print(f"[jobspy] query failed for '{search_term}' @ {location}: {e}")
            continue
        if df is None or len(df) == 0:
            continue
        for _, row in df.iterrows():
            all_jobs.append({
                "source": f"jobspy:{row.get('site', 'unknown')}",
                "company": row.get("company", "") or "",
                "title": row.get("title", "") or "",
                "location": row.get("location", "") or "",
                "url": row.get("job_url", "") or "",
                "description": row.get("description", "") or "",
                "posted_date": str(row.get("date_posted", "")),
                "employment_type": row.get("job_type", "") or "",
            })
    return all_jobs

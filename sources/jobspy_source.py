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

    from safe import s

    all_jobs = []
    for location in locations:
        # "Remote" isn't a real place. jobspy's Glassdoor scraper looks up
        # whatever string you pass as `location` against its own location
        # database (jobspy/glassdoor/__init__.py:_get_location) and fails
        # with "location not parsed" for "Remote" — but that same function
        # skips the lookup entirely when is_remote=True, so passing it
        # properly (location=None, is_remote=True) fixes Glassdoor.
        #
        # Separately, the "Invalid country string: 'namibia'" crash seen
        # in logs is NOT caused by anything we pass in — it's LinkedIn's
        # own per-listing location parser (jobspy/linkedin/__init__.py:
        # _get_location) choking whenever a scraped posting's own location
        # text names a country outside jobspy's fixed ~70-country list
        # (Namibia isn't one of them). It can happen on any query, "Remote"
        # or not, whenever a matching posting happens to be based there,
        # and there's no config-side fix — it's an unpatched jobspy
        # limitation. Already handled as gracefully as it can be here: the
        # try/except below means that one location's results are skipped
        # for this run rather than crashing the whole pipeline.
        is_remote = location.strip().lower() == "remote"
        query_location = None if is_remote else location
        try:
            df = scrape_jobs(
                site_name=sites,
                search_term=search_term,
                location=query_location,
                is_remote=is_remote,
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
                "source": f"jobspy:{s(row.get('site')) or 'unknown'}",
                "company": s(row.get("company")),
                "title": s(row.get("title")),
                "location": s(row.get("location")),
                "url": s(row.get("job_url")),
                "description": s(row.get("description")),
                "posted_date": s(row.get("date_posted")),
                "employment_type": s(row.get("job_type")),
            })
    return all_jobs

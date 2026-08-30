"""
main.py — daily job-discovery + application-package-prep run.

1. Pulls postings from every configured source.
2. Normalizes + classifies + scores each one against your filters.
3. Diffs against data/jobs.db so only genuinely NEW postings surface.
4. For each new match: scores it against the right resume, tailors
   the resume if the match is weak, compiles a PDF, and logs a row to
   application_log.csv.
5. Writes data/new_matches_<date>.csv for a quick daily glance.

Usage:
    python main.py
Schedule it with cron to run daily (see README.md).
"""
import csv
import os
import sys
from datetime import date

import yaml

from db import get_conn, insert_new_jobs
from classify import score_and_filter
from prepare_application import prepare
from ats_detect import detect_all, can_auto_submit, summarize
from sources import greenhouse, lever, remoteok, wwr, jobspy_source, adzuna

CONFIG_PATH = os.path.join(os.path.dirname(__file__), "config.yaml")


def load_config():
    with open(CONFIG_PATH) as f:
        cfg = yaml.safe_load(f)
    cfg["_big_company_set"] = {
        c.lower() for c in
        cfg["companies"].get("greenhouse", []) + cfg["companies"].get("lever", [])
    }
    return cfg


def collect_raw_jobs(cfg) -> list:
    jobs = []

    # Primary source: Adzuna. Keyword+location based -> covers every
    # company automatically, no list to maintain.
    az_cfg = cfg.get("adzuna", {})
    if az_cfg.get("enabled"):
        for search in az_cfg["searches"]:
            try:
                jobs.extend(adzuna.fetch(
                    keywords=search["keywords"],
                    location=search["location"],
                    country=az_cfg.get("country", "in"),
                    results_per_page=az_cfg.get("results_per_page", 50),
                    max_pages=az_cfg.get("max_pages_per_query", 1),
                ))
            except Exception as e:
                print(f"[adzuna] search failed for {search}: {e}")

    # Optional/advanced: specific companies pinned in config.yaml.
    # Empty by default — Adzuna + JobSpy already cover everything.
    for token in cfg["companies"].get("greenhouse", []):
        try:
            jobs.extend(greenhouse.fetch(token))
        except Exception as e:
            print(f"[greenhouse] {token} failed: {e}")

    for token in cfg["companies"].get("lever", []):
        try:
            jobs.extend(lever.fetch(token))
        except Exception as e:
            print(f"[lever] {token} failed: {e}")

    if cfg["remote_boards"].get("remoteok"):
        try:
            jobs.extend(remoteok.fetch())
        except Exception as e:
            print(f"[remoteok] failed: {e}")

    for category in cfg["remote_boards"].get("weworkremotely", []):
        try:
            jobs.extend(wwr.fetch(category))
        except Exception as e:
            print(f"[wwr] {category} failed: {e}")

    js_cfg = cfg.get("jobspy", {})
    if js_cfg.get("enabled"):
        for term in js_cfg["search_terms"].values():
            jobs.extend(jobspy_source.fetch(
                search_term=term,
                locations=js_cfg["locations"],
                sites=js_cfg["sites"],
                results_wanted=js_cfg["results_wanted_per_query"],
                hours_old=js_cfg["hours_old"],
            ))

    return jobs


def main():
    cfg = load_config()
    print("Collecting postings from all sources...")
    raw_jobs = collect_raw_jobs(cfg)
    print(f"Fetched {len(raw_jobs)} raw postings.")

    scored = [score_and_filter(j, cfg) for j in raw_jobs]
    kept = [j for j in scored if j["passes_filters"]]
    print(f"{len(kept)} pass your filters (role / experience / stipend floor).")

    conn = get_conn()
    new_jobs = insert_new_jobs(conn, kept)

    if not new_jobs:
        print("No new matching postings since the last run.")
        conn.close()
        return

    print(f"{len(new_jobs)} NEW postings — detecting which ATS each one lands on...")
    new_jobs = detect_all(new_jobs)
    ats_breakdown = summarize(new_jobs)
    auto_ready = sum(1 for j in new_jobs if can_auto_submit(j))
    print(f"ATS breakdown: {ats_breakdown}")
    print(f"  -> {auto_ready} are Greenhouse/Lever (safe to auto-submit once that layer is built)")
    print(f"  -> {len(new_jobs) - auto_ready} need a human click or your login (LinkedIn/Naukri/"
          f"Indeed/Glassdoor/Workday/company sites) — see README for why")

    print("Preparing application packages...")
    for j in new_jobs:
        try:
            prepare(j, cfg)
        except Exception as e:
            print(f"[prepare] failed for {j['company']} / {j['title']}: {e}")

    new_jobs.sort(key=lambda j: (-j["mandatory_review"], -j["score"]))

    out_path = os.path.join(
        os.path.dirname(__file__), "data",
        f"new_matches_{date.today().isoformat()}.csv")
    fields = ["score", "mandatory_review", "role_category", "company", "title",
              "location", "location_priority", "years_min", "years_max",
              "is_internship", "resume_to_use", "ats_score", "tailored",
              "resume_file", "source", "ats", "final_url", "url"]
    with open(out_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(new_jobs)

    ahmedabad_count = sum(1 for j in new_jobs if j["location_priority"] == "ahmedabad")
    print(f"\n{len(new_jobs)} NEW matches written to {out_path}")
    print(f"  -> {ahmedabad_count} of those are in Ahmedabad")
    print(f"  -> {sum(1 for j in new_jobs if j['mandatory_review'])} flagged for manual review")
    print(f"  -> full application log: application_log.csv")

    conn.close()


if __name__ == "__main__":
    sys.exit(main())

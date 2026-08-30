"""
db.py — lightweight SQLite storage for discovered jobs.
Tracks what's already been seen so re-runs only surface NEW postings
(needed for "apply as soon as it's live" daily-diff behaviour).
"""
import sqlite3
import hashlib
import os
from datetime import datetime, timezone
from safe import s

DB_PATH = os.path.join(os.path.dirname(__file__), "data", "jobs.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    id TEXT PRIMARY KEY,
    source TEXT,
    company TEXT,
    title TEXT,
    location TEXT,
    url TEXT,
    description TEXT,
    posted_date TEXT,
    employment_type TEXT,
    salary_text TEXT,
    years_min INTEGER,
    years_max INTEGER,
    role_category TEXT,
    location_priority TEXT,
    is_internship INTEGER,
    passes_filters INTEGER,
    mandatory_review INTEGER,
    score REAL,
    resume_to_use TEXT,
    status TEXT DEFAULT 'new',
    discovered_at TEXT
);
"""


def job_id(company: str, title: str, url: str) -> str:
    """Stable dedupe key. Prefer URL; fall back to company+title if a
    source doesn't give a clean per-posting URL."""
    url, company, title = s(url), s(company), s(title)
    key = url or f"{company}|{title}"
    return hashlib.sha256(key.strip().lower().encode()).hexdigest()[:24]


def get_conn():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute(SCHEMA)
    return conn


def insert_new_jobs(conn, jobs: list) -> list:
    """Insert jobs that aren't already in the DB. Returns the list of
    genuinely NEW jobs from this run (for the daily CSV / next stage)."""
    new_jobs = []
    cur = conn.cursor()
    for j in jobs:
        jid = job_id(j["company"], j["title"], j["url"])
        cur.execute("SELECT 1 FROM jobs WHERE id = ?", (jid,))
        if cur.fetchone():
            continue  # already seen in a previous run
        j["id"] = jid
        j["discovered_at"] = datetime.now(timezone.utc).isoformat()
        cur.execute("""
            INSERT INTO jobs (id, source, company, title, location, url,
                description, posted_date, employment_type, salary_text,
                years_min, years_max, role_category, location_priority,
                is_internship, passes_filters, mandatory_review, score,
                resume_to_use, status, discovered_at)
            VALUES (:id, :source, :company, :title, :location, :url,
                :description, :posted_date, :employment_type, :salary_text,
                :years_min, :years_max, :role_category, :location_priority,
                :is_internship, :passes_filters, :mandatory_review, :score,
                :resume_to_use, 'new', :discovered_at)
        """, j)
        new_jobs.append(j)
    conn.commit()
    return new_jobs


def update_status(conn, job_id_: str, status: str):
    conn.execute("UPDATE jobs SET status = ? WHERE id = ?", (status, job_id_))
    conn.commit()

"""We Work Remotely RSS feeds — public, no auth required."""
import feedparser

BASE = "https://weworkremotely.com/categories/{category}.rss"


def fetch(category: str) -> list:
    feed = feedparser.parse(BASE.format(category=category))
    jobs = []
    for e in feed.entries:
        title = e.get("title", "")
        company = ""
        if ":" in title:
            company, title = title.split(":", 1)
        jobs.append({
            "source": "weworkremotely",
            "company": company.strip(),
            "title": title.strip(),
            "location": "Remote",
            "url": e.get("link", ""),
            "description": e.get("summary", "") or "",
            "posted_date": e.get("published", ""),
            "employment_type": "",
        })
    return jobs

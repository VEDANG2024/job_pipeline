"""
classify.py — turns a normalized job dict into a scored, filtered record
using the rules from config.yaml:
  - role: analyst vs swe (routes to the matching resume)
  - experience: keep 0-2 yrs
  - internships under the stipend floor are dropped
  - Ahmedabad postings are ALWAYS surfaced, even if they'd otherwise
    fail a soft filter — flagged mandatory_review instead of dropped
"""
import re
from safe import s

ANALYST_KEYWORDS = [
    "business analyst", "data analyst", "reporting analyst",
    "operations analyst", "process analyst", "mis executive",
    "power bi", "sql analyst", "requirements gathering",
]
SWE_KEYWORDS = [
    "software engineer", "sde", "backend", "frontend", "full stack",
    "full-stack", "developer", "programmer", "python developer",
    "java developer", "software developer", "engineer i", "engineer ii",
]

INTERNSHIP_KEYWORDS = ["intern", "internship", "trainee"]

# parse_experience() below defaults unspecified-years JDs to (0, 2) —
# entry-friendly — on the assumption a real years figure would be stated
# otherwise. Senior/manager/director postings routinely DON'T state a bare
# "X years" figure at all (seniority is signaled by title and scope
# instead), which let plenty of them slip through as if they were 0-2 yr
# roles. This list catches what the years-regex can't.
SENIOR_TITLE_KEYWORDS = [
    "senior", "sr.", "sr ", "staff", "principal", "director", "head of",
    "vice president", " vp ", "chief", "architect", "manager",
    "tech lead", "team lead", "president",
]

YEARS_PATTERNS = [
    re.compile(r"(\d+)\s*[-\u2013to]+\s*(\d+)\s*\+?\s*years?", re.I),
    re.compile(r"(\d+)\s*\+\s*years?", re.I),
    re.compile(r"minimum of (\d+)\s*years?", re.I),
]
FRESHER_KEYWORDS = ["fresher", "entry level", "entry-level", "0-1 year",
                     "no prior experience", "recent graduate", "new grad"]

STIPEND_PATTERN = re.compile(r"(?:\u20b9|rs\.?|inr)\s?([\d,]{4,7})", re.I)


def classify_role(title: str, description: str) -> str:
    text = f"{s(title)} {s(description)}".lower()
    if any(k in text for k in ANALYST_KEYWORDS):
        return "analyst"
    if any(k in text for k in SWE_KEYWORDS):
        return "swe"
    return "other"


def parse_experience(description: str):
    text = s(description).lower()
    if any(k in text for k in FRESHER_KEYWORDS):
        return (0, 1)
    for pat in YEARS_PATTERNS:
        m = pat.search(text)
        if m:
            groups = [int(g) for g in m.groups() if g]
            if len(groups) == 2:
                return (groups[0], groups[1])
            return (groups[0], groups[0] + 1)
    return (0, 2)  # unspecified -> assume entry-friendly, human confirms later


def parse_location_priority(location: str, priority_aliases: list) -> str:
    loc = s(location).lower()
    if any(a in loc for a in priority_aliases):
        return "ahmedabad"
    if "remote" in loc:
        return "remote"
    if "india" in loc or any(c in loc for c in [
            "gujarat", "mumbai", "bangalore", "bengaluru", "pune", "delhi",
            "hyderabad", "chennai", "gandhinagar", "surat", "vadodara"]):
        return "india_other"
    return "international"


def is_internship(title: str) -> bool:
    return any(k in s(title).lower() for k in INTERNSHIP_KEYWORDS)


def parse_stipend(description: str):
    m = STIPEND_PATTERN.search(s(description))
    if not m:
        return None
    return int(m.group(1).replace(",", ""))


def score_and_filter(job: dict, cfg: dict) -> dict:
    filters = cfg["filters"]
    role = classify_role(job["title"], job.get("description", ""))
    years_min, years_max = parse_experience(job.get("description", ""))
    loc_priority = parse_location_priority(
        job.get("location", ""), filters["priority_location_aliases"])
    intern = is_internship(job["title"])
    stipend = parse_stipend(job.get("description", "")) if intern else None

    passes = True
    mandatory_review = False

    # Hard filter: internship pay floor (only when a stipend is actually stated)
    if intern and stipend is not None and stipend < filters["internship_min_stipend_inr"]:
        passes = False

    # Soft filter: experience band. Ahmedabad postings bypass this —
    # flagged for manual review instead of being dropped.
    if years_min > filters["max_years_experience"]:
        if loc_priority == "ahmedabad":
            mandatory_review = True
        else:
            passes = False

    # Soft filter: senior/manager/director titles. Same bypass pattern —
    # catches the case above where years weren't stated at all, so the
    # (0, 2) fallback would otherwise have waved these through.
    title_text = f" {s(job['title']).lower()} "
    if any(k in title_text for k in SENIOR_TITLE_KEYWORDS):
        if loc_priority == "ahmedabad":
            mandatory_review = True
        else:
            passes = False

    if role == "other":
        if loc_priority == "ahmedabad":
            mandatory_review = True
        else:
            passes = False

    # Ahmedabad postings are never silently dropped, full stop.
    if loc_priority == "ahmedabad":
        passes = True

    score = 0.0
    if loc_priority == "ahmedabad":
        score += 50
    elif loc_priority == "remote":
        score += 20
    elif loc_priority == "india_other":
        score += 10

    if role in ("analyst", "swe"):
        score += 20
    if years_max <= filters["max_years_experience"]:
        score += 20
    if s(job.get("company")).lower() in cfg.get("_big_company_set", set()):
        score += 10

    job.update({
        "role_category": role,
        "years_min": years_min,
        "years_max": years_max,
        "location_priority": loc_priority,
        "is_internship": int(intern),
        "salary_text": str(stipend) if stipend else "",
        "passes_filters": int(passes),
        "mandatory_review": int(mandatory_review),
        "score": round(score, 1),
        "resume_to_use": role if role in ("analyst", "swe") else "",
    })
    return job

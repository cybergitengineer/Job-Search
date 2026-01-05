import json
import re
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
import requests
import os
from serpapi import GoogleSearch

@dataclass
class Job:
    id: str
    title: str
    location: str
    team: str
    company: str
    source: str
    url: str
    description: str

# NOW define the functions that use 'Job'
def fetch_serpapi_jobs(query: str, location: str = "United States") -> List[Job]:
    """
    Fetch from Google Jobs via SerpAPI (aggregates LinkedIn, Indeed, Glassdoor)
    Free tier: 100 searches/month
    Get key from: https://serpapi.com/
    """
    api_key = os.environ.get("SERPAPI_KEY")
    if not api_key:
        print("[WARN] SERPAPI_KEY not set, skipping job board search")
        return []
    
    params = {
        "engine": "google_jobs",
        "q": query,
        "location": location,
        "api_key": api_key,
        "chips": "date_posted:week"  # weekly posts
    }
    
    try:
        search = GoogleSearch(params)
        results = search.get_dict()
        jobs = []
        
        for j in results.get("jobs_results", []):
            jobs.append(Job(
                id=j.get("job_id", ""),
                title=j.get("title", ""),
                location=j.get("location", ""),
                team="",
                company=j.get("company_name", ""),
                source="Google Jobs",
                url=j.get("share_url", "") or j.get("apply_options", [{}])[0].get("link", ""),
                description=j.get("description", "")
            ))
        return jobs
    except Exception as e:
        print(f"[WARN] SerpAPI error: {e}")
        return []




def load_text_lines(path: str) -> List[str]:
    with open(path, "r", encoding="utf-8") as f:
        lines = [ln.strip() for ln in f.readlines()]
    return [ln for ln in lines if ln and not ln.startswith("#")]


def load_config(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def normalize(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip()).lower()


def contains_any(hay: str, needles: List[str]) -> bool:
    h = normalize(hay)
    return any(normalize(n) in h for n in needles)


def sponsorship_status(text: str) -> str:
    """
    Returns: "NO", "YES", or "UNKNOWN"
    We only hard-reject if we see explicit no-sponsorship language.
    """
    t = normalize(text)

    # Explicit "no sponsorship" patterns
    no_patterns = [
        "no sponsorship",
        "unable to sponsor",
        "cannot sponsor",
        "will not sponsor",
        "not sponsor",
        "without sponsorship",
        "no visa sponsorship",
        "do not sponsor",
        "not eligible for sponsorship",
        "us citizen only",
        "u.s. citizen only",
        "must be a u.s. citizen",
        "must be us citizen",
        "security clearance required"
    ]
    if any(p in t for p in no_patterns):
        return "NO"

    # Explicit "sponsorship available" patterns
    yes_patterns = [
        "visa sponsorship",
        "sponsorship available",
        "eligible for sponsorship",
        "will sponsor",
        "accept CPT",
        "accept OPT",
        "accept H1B",
        "can sponsor"
    ]
    if any(p in t for p in yes_patterns):
        return "YES"

    return "UNKNOWN"


def match_score(job: Job, keyword_phrases: List[str]) -> int:
    """
    Simple scoring: counts distinct keyword hits in title+description+team.
    Then maps to 0–100 with a soft cap.
    """
    text = f"{job.title}\n{job.team}\n{job.description}"
    t = normalize(text)

    hits = 0
    seen = set()
    for kw in keyword_phrases:
        k = normalize(kw)
        if k and k in t and k not in seen:
            hits += 1
            seen.add(k)

    # Map hits to 0–100 (tunable)
    # 0 hits -> 0
    # 10 hits -> ~80
    # 15 hits -> ~95
    score = int(min(100, (hits / 10) * 80))
    if hits >= 15:
        score = 95
    if hits >= 20:
        score = 100
    return score


def is_internship(job: Job, internship_keywords: List[str]) -> bool:
    # MUST have "intern" in the TITLE - not just description
    return contains_any(job.title, internship_keywords)


def location_ok(job: Job, locations: List[str]) -> bool:
    if not locations:
        return True
    loc = normalize(job.location)
    return any(normalize(x) in loc for x in locations) or ("remote" in loc and any("remote" in normalize(x) for x in locations))


def fetch_greenhouse_jobs(board: str) -> List[Job]:
    # Public endpoint:
    # https://boards-api.greenhouse.io/v1/boards/{board}/jobs
    url = f"https://boards-api.greenhouse.io/v1/boards/{board}/jobs?content=true"
    r = requests.get(url, timeout=30)
    r.raise_for_status()
    data = r.json()
    jobs = []
    for j in data.get("jobs", []):
        jobs.append(Job(
            id=str(j.get("id")),
            title=j.get("title", ""),
            location=(j.get("location") or {}).get("name", "") if isinstance(j.get("location"), dict) else (j.get("location") or ""),
            team=j.get("department", {}).get("name", "") if isinstance(j.get("department"), dict) else "",
            company=board,
            source="Greenhouse",
            url=j.get("absolute_url", ""),
            description=j.get("content", "") or ""
        ))
    return jobs


def fetch_lever_jobs(company: str) -> List[Job]:
    # Public endpoint:
    # https://api.lever.co/v0/postings/{company}?mode=json
    url = f"https://api.lever.co/v0/postings/{company}?mode=json"
    r = requests.get(url, timeout=30)
    r.raise_for_status()
    data = r.json()
    jobs = []
    for j in data:
        jobs.append(Job(
            id=str(j.get("id")),
            title=j.get("text", ""),
            location=(j.get("categories") or {}).get("location", "") if isinstance(j.get("categories"), dict) else "",
            team=(j.get("categories") or {}).get("team", "") if isinstance(j.get("categories"), dict) else "",
            company=company,
            source="Lever",
            url=j.get("hostedUrl", ""),
            description=j.get("descriptionPlain", "") or j.get("description", "") or ""
        ))
    return jobs


def build_digest_md(rows: List[Tuple[Job, int, str]]) -> str:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    md = []
    md.append(f"# Daily AI Internship Digest\n")
    md.append(f"Generated: **{now}**\n")
    md.append(f"Filters: score ≥ **{CONFIG['min_match_score']}**, max **{CONFIG['max_results']}**, locations: **Remote US + Texas**, sponsorship: **reject if explicit NO; silent = review**\n")
    md.append("---\n")
    md.append("| Score | Sponsorship | Title | Company | Source | Location | Link |\n")
    md.append("|---:|:---:|---|---|---|---|---|\n")
    for job, score, sponsor in rows:
        title = job.title.replace("|", " ")
        company = job.company.replace("|", " ")
        source = job.source.replace("|", " ")
        loc = (job.location or "").replace("|", " ")
        md.append(f"| {score} | {sponsor} | {title} | {company} | {source} | {loc} | [Apply]({job.url}) |\n")
    md.append("\n---\n")
    md.append("### Notes\n")
    md.append("- **Sponsorship** is inferred from posting text. If it says **NO sponsorship / US citizen only / clearance required**, it is rejected.\n")
    md.append("- If sponsorship is **silent**, it is marked **UNKNOWN** and kept for review.\n")
    return "".join(md)


def main() -> int:
    keyword_phrases = load_text_lines("keywords.txt")

    all_jobs: List[Job] = []
    for src in CONFIG.get("sources", []):
        if src.get("type") == "greenhouse":
            for board in src.get("boards", []):
                try:
                    all_jobs.extend(fetch_greenhouse_jobs(board))
                except Exception as e:
                    print(f"[WARN] Greenhouse {board}: {e}", file=sys.stderr)
        elif src.get("type") == "lever":
            for company in src.get("companies", []):
                try:
                    all_jobs.extend(fetch_lever_jobs(company))
                except Exception as e:
                    print(f"[WARN] Lever {company}: {e}", file=sys.stderr)

    # Filter to internships + role keywords
    internship_kw = CONFIG.get("internship_type_keywords", [])
    role_kw = CONFIG.get("role_keywords", [])
    locations = CONFIG.get("locations", [])

    candidates: List[Tuple[Job, int, str]] = []
    for job in all_jobs:
        text_for_role = f"{job.title}\n{job.description}\n{job.team}"
        if not is_internship(job, internship_kw):
            continue
        if not contains_any(text_for_role, role_kw):
            continue
        if not location_ok(job, locations):
            continue

        sponsor = sponsorship_status(text_for_role)
        if CONFIG.get("reject_if_no_sponsorship", True) and sponsor == "NO":
            continue

        score = match_score(job, keyword_phrases)
        if score < int(CONFIG.get("min_match_score", 0)):
            continue

        candidates.append((job, score, sponsor))

    # Sort best first, cap results
    candidates.sort(key=lambda x: (x[1], normalize(x[0].title)), reverse=True)
    candidates = candidates[: int(CONFIG.get("max_results", 15))]

    # After filtering and sorting candidates...
    if not candidates:
        md = f"# Daily AI Internship Digest\n\nNo new matches found for {datetime.now(timezone.utc).strftime('%Y-%m-%d')}. Check back tomorrow!"
    else:
        md = build_digest_md(candidates)

    # --- END OF YOUR LOGIC (where 'md' has been created) ---

    # 1. Define the path first (points one level up to the root)
    file_path = os.path.join(os.path.dirname(__file__), '..', 'digest.md')
    
    # 2. Now open the file using that defined path
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(md)

    print(f"Workflow finished. File saved to: {os.path.abspath(file_path)}")
    return 0


if __name__ == "__main__":
    CONFIG = load_config("config.json")
    raise SystemExit(main())

# After writing digest.md
import subprocess
subprocess.run(["python", "scripts/track_stats.py", str(len(candidates))])

# After the existing source loops, add:
try:
    # 1. THE BROAD SEARCH (Original)
    # This finds jobs across all boards like LinkedIn, Indeed, etc.
    all_jobs.extend(fetch_serpapi_jobs("AI intern OR ML intern OR Machine Learning intern OR Internship OR Accepts Sponsorship"))
    
    # 2. THE TARGETED SEARCH (New)
    # This specifically hunts within the career portals of top companies.
    # We use (site:A OR site:B) to group them into ONE search (saving credits).
    targeted_query = "(site:https://ibmglobal.avature.net/en_US/careers/ OR site:google.com OR site:nvidia.com) internship (AI OR ML)"
    all_jobs.extend(fetch_serpapi_jobs(targeted_query))
    
    print(f"Combined Search Complete. Total jobs collected: {len(all_jobs)}")
    
except Exception as e:
    print(f"[WARN] SerpAPI: {e}", file=sys.stderr)
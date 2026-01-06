import json
import re
import sys
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Tuple

import requests
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


def fetch_serpapi_jobs(query: str, location: str = "United States") -> List[Job]:
    """Fetch from Google Jobs via SerpAPI"""
    api_key = os.environ.get("SERPAPI_KEY")
    if not api_key:
        print("[WARN] SERPAPI_KEY not set, skipping job board search")
        return []
    
    params = {
        "engine": "google_jobs",
        "q": query,
        "location": location,
        "api_key": api_key,
        "chips": "date_posted:week"
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
                url=j.get("share_url", "") or (j.get("apply_options", [{}])[0].get("link", "") if j.get("apply_options") else ""),
                description=j.get("description", "")
            ))
        
        print(f"[INFO] SerpAPI returned {len(jobs)} jobs for query: {query[:50]}...")
        return jobs
    except Exception as e:
        print(f"[WARN] SerpAPI error: {e}")
        return []

import requests

def fetch_greenhouse_jobs(board_token):
    url = f"https://boards-api.greenhouse.io/v1/boards/{board_token}/jobs"
    response = requests.get(url)
    if response.status_code == 200:
        return response.json().get('jobs', [])
    return []

# Example Usage for companies like Airbnb or Figma
# jobs = fetch_greenhouse_jobs("airbnb")

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
    # Ensure hay is stringified and normalized
    h = str(hay).lower()
    return any(str(n).lower() in h for n in needles)


def sponsorship_status(text: str) -> str:
    t = normalize(text)
    no_patterns = [
        "no sponsorship", "unable to sponsor", "cannot sponsor",
        "will not sponsor", "not sponsor", "without sponsorship",
        "no visa sponsorship", "do not sponsor", "not eligible for sponsorship",
        "us citizen only", "u.s. citizen only", "must be a u.s. citizen",
        "must be us citizen", "security clearance required"
    ]
    if any(p in t for p in no_patterns):
        return "NO"
    
    yes_patterns = [
        "visa sponsorship", "sponsorship available", "eligible for sponsorship",
        "will sponsor", "accept CPT", "accept OPT", "accept H1B", "can sponsor"
    ]
    if any(p in t for p in yes_patterns):
        return "YES"
    
    return "UNKNOWN"


def match_score(job: Job, keyword_phrases: List[str]) -> int:
    text = f"{job.title}\n{job.team}\n{job.description}"
    t = normalize(text)
    
    hits = 0
    seen = set()
    for kw in keyword_phrases:
        k = normalize(kw)
        if k and k in t and k not in seen:
            hits += 1
            seen.add(k)
    
    score = int(min(100, (hits / 10) * 80))
    if hits >= 15:
        score = 95
    if hits >= 20:
        score = 100
    return score


def is_internship(job: Job, internship_keywords: List[str]) -> bool:
    # Broaden this: If "intern" isn't in title, check the description too
    in_title = contains_any(job.title, internship_keywords)
    # Optional: check description if title fails, but maybe only for "intern"
    return in_title or ("intern" in job.description.lower())


def location_ok(job: Job, locations: List[str]) -> bool:
    if not locations:
        return True
    loc = normalize(job.location)
    return any(normalize(x) in loc for x in locations) or \
           ("remote" in loc and any("remote" in normalize(x) for x in locations))


def fetch_greenhouse_jobs(board: str) -> List[Job]:
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
    
    # Fetch from Greenhouse
    for src in CONFIG.get("sources", []):
        if src.get("type") == "greenhouse":
            for board in src.get("boards", []):
                try:
                    jobs = fetch_greenhouse_jobs(board)
                    print(f"[INFO] Greenhouse {board}: {len(jobs)} jobs")
                    all_jobs.extend(jobs)
                except Exception as e:
                    print(f"[WARN] Greenhouse {board}: {e}", file=sys.stderr)
    
    # Fetch from SerpAPI (Google Jobs aggregator)
    try:
        print("[INFO] Fetching from SerpAPI (LinkedIn/Indeed/Glassdoor)...")
        serp_jobs = fetch_serpapi_jobs("AI intern OR ML intern OR Machine Learning intern sponsorship")
        all_jobs.extend(serp_jobs)
    except Exception as e:
        print(f"[WARN] SerpAPI: {e}", file=sys.stderr)
    
    print(f"[INFO] Total jobs fetched: {len(all_jobs)}")
    
    # Filter jobs
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
        if CONFIG.get("reject_if_no_sponsorship", False) and sponsor == "NO":
            continue
        
        score = match_score(job, keyword_phrases)
        if score < int(CONFIG.get("min_match_score", 0)):
            continue
        
        candidates.append((job, score, sponsor))
    
    # Sort and cap results
    candidates.sort(key=lambda x: (x[1], normalize(x[0].title)), reverse=True)
    candidates = candidates[: int(CONFIG.get("max_results", 15))]
    
    # Build digest
    if not candidates:
        md = f"# Daily AI Internship Digest\n\nNo new matches found for {datetime.now(timezone.utc).strftime('%Y-%m-%d')}. Check back tomorrow!"
    else:
        md = build_digest_md(candidates)
    
    # Save to scripts/digest.md (for GitHub Actions workflow)
    output_path = os.path.join("scripts", "digest.md")
    os.makedirs("scripts", exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(md)
    
    print(f"Wrote digest.md with {len(candidates)} matches to {output_path}")
    return 0


if __name__ == "__main__":
    CONFIG = load_config("config.json")
    raise SystemExit(main())
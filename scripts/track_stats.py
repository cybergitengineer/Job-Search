import json
import os
from datetime import datetime
from typing import Dict, Any

STATS_FILE = "data/stats.json"

def load_stats() -> Dict[str, Any]:
    if os.path.exists(STATS_FILE):
        with open(STATS_FILE, "r") as f:
            return json.load(f)
    return {
        "total_jobs_found": 0,
        "jobs_approved": 0,
        "applications_generated": 0,
        "by_company": {},
        "by_source": {},
        "daily_counts": []
    }

def update_stats(jobs_found: int, source: str = "daily_digest"):
    stats = load_stats()
    stats["total_jobs_found"] += jobs_found
    
    today = datetime.utcnow().date().isoformat()
    stats["daily_counts"].append({
        "date": today,
        "jobs_found": jobs_found,
        "source": source
    })
    
    # Keep last 90 days only
    stats["daily_counts"] = stats["daily_counts"][-90:]
    
    os.makedirs("data", exist_ok=True)
    with open(STATS_FILE, "w") as f:
        json.dump(stats, f, indent=2)

if __name__ == "__main__":
    # Called from fetch_jobs.py at end
    import sys
    count = int(sys.argv[1]) if len(sys.argv) > 1 else 0
    update_stats(count)
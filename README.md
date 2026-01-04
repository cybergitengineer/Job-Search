# Automated AI Internship Job Search

Fully automated system that finds, filters, and prepares application materials for AI/ML internship positions.

## How It Works

1. **Daily Job Digest** (6 AM UTC)
   - Fetches from 25+ company career pages via Greenhouse/Lever APIs
   - Filters for: internships, AI/ML roles, sponsorship-friendly, remote/Texas
   - Scores based on 100+ relevant keywords
   - Creates GitHub Issue with top 15 matches

2. **Review & Approve**
   - Review the daily digest issue
   - Add `approved` label to jobs you want to apply to

3. **Auto-Generate Materials**
   - System automatically creates:
     - Customized resume bullets (paste-ready)
     - Personalized cover letter
   - Posts as comment on issue

4. **Apply**
   - Copy/paste generated materials
   - Submit application
   - Track in issue comments

## Configuration

### `config.json`
- `min_match_score`: Minimum keyword match score (0-100)
- `max_results`: Max jobs per digest
- `locations`: Acceptable job locations
- `sources`: Job board companies to monitor

### `keywords.txt`
100+ AI/ML keywords for relevance scoring

## Stats

- **Total jobs monitored**: 25+ companies
- **Daily matches**: ~5-15 jobs
- **Time saved**: ~10 hours/week
- **Sponsorship filter**: Rejects explicit "no sponsorship"

## Files

job-search/
├── .github/workflows/
│   ├── daily-digest.yml          # Daily job scraper
│   ├── step3_comment_artifacts.yml  # Resume/cover letter generator
│   └── weekly_followup.yml       # Follow-up reminders
├── scripts/
│   ├── fetch_jobs.py            # Job fetcher with scoring
│   ├── step3_generate_artifacts.py  # Material generator
│   └── track_stats.py           # Analytics
├── templates/
│   └── master_resume.md         # Base resume template
├── data/
│   └── stats.json              # Application statistics
├── config.json                 # Configuration
├── keywords.txt               # Relevance keywords
└── requirements.txt           # Python dependencies

## Usage

### Manual Run
```bash
# Fetch jobs manually
python scripts/fetch_jobs.py

# Generate artifacts for issue #X
GITHUB_TOKEN=xxx REPO=owner/repo ISSUE_NUMBER=X python scripts/step3_generate_artifacts.py
```

### GitHub Actions
- Runs automatically daily at 6 AM UTC
- Trigger manually: Actions → Daily AI Internship Digest → Run workflow

## Metrics Tracked

- Total jobs found
- Jobs approved
- Applications generated
- Success rate by company
- Success rate by job board

## Future Enhancements

- [ ] LinkedIn API integration
- [ ] Auto-submit to Easy Apply jobs
- [ ] Email follow-up automation
- [ ] Response tracking
- [ ] Interview preparation materials
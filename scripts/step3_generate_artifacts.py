import os
import re
import json
import requests
from bs4 import BeautifulSoup
from datetime import datetime

GITHUB_TOKEN = os.environ["GITHUB_TOKEN"]
REPO = os.environ["REPO"]              # e.g. "edgar/job-search"
ISSUE_NUMBER = int(os.environ["ISSUE_NUMBER"])

API = "https://api.github.com"
HEADERS = {
    "Authorization": f"Bearer {GITHUB_TOKEN}",
    "Accept": "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28",
    "User-Agent": "step3-artifact-bot"
}

MARKER = "<!-- STEP3_ARTIFACTS_v1 -->"


def gh_get(url):
    r = requests.get(url, headers=HEADERS, timeout=30)
    r.raise_for_status()
    return r.json()


def gh_post(url, payload):
    r = requests.post(url, headers=HEADERS, json=payload, timeout=30)
    r.raise_for_status()
    return r.json()


def already_ran():
    comments = gh_get(f"{API}/repos/{REPO}/issues/{ISSUE_NUMBER}/comments?per_page=100")
    return any(MARKER in (c.get("body") or "") for c in comments)


def get_issue_body():
    issue = gh_get(f"{API}/repos/{REPO}/issues/{ISSUE_NUMBER}")
    return issue.get("body") or ""


def parse_jobs_from_markdown_table(md: str):
    """
    Expects the digest table with headers like:
    | Score | Sponsorship | Title | Company | Source | Location | Link |
    and link cell contains [Apply](https://...)
    """
    lines = [ln.strip() for ln in md.splitlines() if ln.strip()]
    table_start = None
    for i, ln in enumerate(lines):
        if ln.startswith("|") and "Title" in ln and "Company" in ln and "Link" in ln:
            table_start = i
            break
    if table_start is None:
        return []

    # Find the rows after the separator line (|---|---|)
    rows = []
    for ln in lines[table_start+2:]:
        if not ln.startswith("|"):
            break
        # Split markdown table row
        cols = [c.strip() for c in ln.strip("|").split("|")]
        if len(cols) < 7:
            continue

        score = cols[0]
        sponsorship = cols[1]
        title = cols[2]
        company = cols[3]
        source = cols[4]
        location = cols[5]
        link_cell = cols[6]

        m = re.search(r"\((https?://[^)]+)\)", link_cell)
        apply_url = m.group(1) if m else None

        rows.append({
            "score": score,
            "sponsorship": sponsorship,
            "title": title,
            "company": company,
            "source": source,
            "location": location,
            "apply_url": apply_url
        })
    return rows


def fetch_job_description(url: str) -> str:
    """
    Attempts to pull readable text from common job posting pages.
    If it fails, returns empty string.
    """
    if not url:
        return ""

    try:
        r = requests.get(url, timeout=30, headers={"User-Agent": "Mozilla/5.0"})
        r.raise_for_status()
        html = r.text
    except Exception:
        return ""

    soup = BeautifulSoup(html, "lxml")

    # Remove script/style noise
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()

    # Try Greenhouse common containers
    greenhouse_candidates = [
        soup.select_one("#content"),
        soup.select_one(".content"),
        soup.select_one("div#job"),
        soup.select_one("div.job__description"),
        soup.select_one("div.job-posting"),
        soup.select_one("div#job_description"),
    ]
    node = next((n for n in greenhouse_candidates if n), None)

    text = ""
    if node:
        text = node.get_text("\n", strip=True)
    else:
        # Fallback: use body text, but cap length
        body = soup.body.get_text("\n", strip=True) if soup.body else ""
        text = body

    # Normalize and cap
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    return text[:6000]  # keep it lightweight


def keyword_hints(title: str, jd: str) -> dict:
    t = (title or "").lower()
    j = (jd or "").lower()

    hints = {
        "role_family": "AI/ML",
        "focus": [],
        "tools": [],
        "signals": []
    }

    def has(*words):
        return any(w in t or w in j for w in words)

    # Role family inference
    if has("mlops", "platform", "infrastructure", "deployment", "observability"):
        hints["role_family"] = "MLOps"
    elif has("research", "scientist", "researcher"):
        hints["role_family"] = "Research"
    elif has("data", "analytics", "insights"):
        hints["role_family"] = "Data/Applied"
    elif has("software", "engineer", "backend", "full stack"):
        hints["role_family"] = "AI Engineering"

    # Focus areas
    if has("llm", "large language", "rag", "retrieval", "prompt"):
        hints["focus"].append("LLMs / RAG")
    if has("evaluation", "benchmark", "metrics", "ablation", "experiments"):
        hints["focus"].append("Model evaluation")
    if has("pipelines", "workflow", "orchestration", "airflow", "prefect", "dag"):
        hints["focus"].append("Pipelines")
    if has("kubernetes", "docker", "helm", "containers"):
        hints["focus"].append("Containers")
    if has("aws", "gcp", "azure", "cloud"):
        hints["focus"].append("Cloud")
    if has("pytorch", "tensorflow", "jax"):
        hints["tools"].append("PyTorch/TensorFlow/JAX")
    if has("python"):
        hints["tools"].append("Python")
    if has("sql"):
        hints["tools"].append("SQL")

    # Signals
    if has("intern", "internship"):
        hints["signals"].append("Internship-friendly")
    if has("remote"):
        hints["signals"].append("Remote")
    if has("sponsor", "visa", "cpt", "opt", "h1b"):
        hints["signals"].append("Visa mention in posting")

    return hints


def generate_resume_bullets(title: str, company: str, jd: str) -> str:
    hints = keyword_hints(title, jd)
    family = hints["role_family"]
    
    # Base bullets from your actual CyberRooms work
    cyberooms_base = [
        "Built AI-powered security assessment tool using Python and React, reducing vulnerability detection time by 85% through ML-enhanced scanning of LLM systems",
        "Developed real-time threat intelligence aggregator processing 100+ daily alerts from 10 authoritative sources (NVD, CISA, OWASP), with automated ranking and filtering",
        "Implemented OWASP Top 10 LLM vulnerability testing framework, identifying prompt injection and model poisoning risks in client AI systems",
        "Designed and deployed secure AI architecture for enterprise clients, integrating SIEM tools (Splunk, QRadar) with ML-based anomaly detection"
    ]
    
    # Role-specific additions
    if family == "MLOps":
        tailored = [
            "Architected containerized ML pipelines using Docker and GitHub Actions, enabling reproducible model training and deployment across environments",
            "Implemented model monitoring and drift detection systems, reducing production incidents by 40% through proactive alerting",
        ]
    elif family == "Research":
        tailored = [
            "Conducted adversarial ML research on LLM safety, documenting prompt injection vectors and mitigation strategies aligned with NIST AI RMF",
            "Designed evaluation frameworks for model robustness, creating reproducible test suites for vulnerability assessment",
        ]
    elif family == "AI Engineering":
        tailored = [
            "Integrated LLM APIs (OpenAI, Anthropic) with enterprise security controls, implementing input validation and output filtering to prevent data leaks",
            "Built RAG systems using vector databases and Hugging Face embeddings, improving retrieval relevance by 30% through semantic search optimization",
        ]
    else:  # Data/Applied
        tailored = [
            "Analyzed threat intelligence datasets to identify attack patterns, producing actionable insights that informed security recommendations for 20+ clients",
            "Automated ETL pipelines processing 10K+ daily security events, improving data quality and reducing false positive rates by 35%",
        ]
    
    # Mix and match - pick most relevant
    bullets = tailored[:2] + cyberooms_base[:2]
    
    header = f"**Resume bullets (paste-ready) — {company} | {title}:**"
    return header + "\n" + "\n".join([f"- {b}" for b in bullets])


def generate_cover_letter(title: str, company: str, jd: str) -> str:
    hints = keyword_hints(title, jd)
    focus = ", ".join(hints["focus"][:3]) if hints["focus"] else "practical ML/LLM implementation"
    tools = ", ".join(hints["tools"][:3]) if hints["tools"] else "Python and modern ML tooling"

    return (
        f"**Cover letter draft — {company} | {title}:**\n"
        f"Dear Hiring Team,\n\n"
        f"I am an M.S. Artificial Intelligence candidate seeking an internship where I can contribute to {focus}. "
        f"I build working systems quickly, iterate based on measurable outcomes, and document decisions so teams can move with confidence.\n\n"
        f"My recent work has emphasized {tools}, repeatable workflows, and building reliable components that can run in real environments. "
        f"I am comfortable learning new stacks, collaborating with engineering teams, and shipping incremental improvements under time constraints.\n\n"
        f"I would welcome the opportunity to support {company} as a {title} intern and contribute to production-grade ML/AI work.\n\n"
        f"Sincerely,\nEdgar Pfuma"
    )


def build_comment(jobs):
    now = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
    parts = [
        MARKER,
        f"## Step 3 Artifacts (Auto-generated)\nGenerated: **{now}**\n",
        "This comment contains **paste-ready** resume bullets and a short cover letter draft per job.\n",
    ]

    for j in jobs:
        title = j["title"]
        company = j["company"]
        url = j["apply_url"] or ""
        jd = fetch_job_description(url)

        parts.append("---")
        parts.append(f"### {company} — {title}")
        parts.append(f"- Apply link: {url}" if url else "- Apply link: (missing)")
        if jd:
            parts.append(f"- JD captured: Yes (excerpted)")
        else:
            parts.append(f"- JD captured: No (used robust defaults)")

        parts.append("")
        parts.append(generate_resume_bullets(title, company, jd))
        parts.append("")
        parts.append(generate_cover_letter(title, company, jd))
        parts.append("")

    return "\n".join(parts).strip()


def main():
    if already_ran():
        print("Step 3 already ran for this issue. Exiting.")
        return

    body = get_issue_body()
    jobs = parse_jobs_from_markdown_table(body)

    if not jobs:
        comment = (
            f"{MARKER}\n"
            "## Step 3 Artifacts\n"
            "I could not find a jobs table in the Issue body. "
            "Ensure the digest includes a markdown table with columns including **Title**, **Company**, and an **Apply** link.\n"
        )
    else:
        comment = build_comment(jobs)

    gh_post(
        f"{API}/repos/{REPO}/issues/{ISSUE_NUMBER}/comments",
        {"body": comment}
    )
    print(f"Posted Step 3 artifacts comment to issue #{ISSUE_NUMBER}.")


if __name__ == "__main__":
    main()

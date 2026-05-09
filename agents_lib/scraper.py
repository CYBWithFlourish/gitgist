import os
import re
import requests
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from langchain_classic.agents import AgentExecutor, create_tool_calling_agent
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from dotenv import load_dotenv

load_dotenv()

APIFY_TOKEN = os.environ.get("APIFY_API_TOKEN")
APIFY_BASE  = "https://api.apify.com/v2"


# Apify helpers
def _run_actor_sync(actor_id: str, input_body: dict) -> list:
    """Run an Apify actor synchronously and return dataset items."""
    if not APIFY_TOKEN:
        raise ValueError("APIFY_API_TOKEN is missing from environment")
    url = f"{APIFY_BASE}/acts/{actor_id}/run-sync-get-dataset-items"
    resp = requests.post(
        url,
        params={"token": APIFY_TOKEN},
        json=input_body,
        timeout=120,
    )
    resp.raise_for_status()
    return resp.json()


def _parse_repo_slug(github_url: str) -> tuple[str, str]:
    """Extract owner/repo from any github.com URL."""
    m = re.search(r"github\.com/([^/]+)/([^/?\s]+)", github_url)
    if not m:
        raise ValueError(f"Cannot parse GitHub URL: {github_url}")
    return m.group(1), m.group(2).rstrip("/")


# LangChain tools

@tool
def fetch_repo_metadata(github_url: str) -> str:
    """
    Fetch core metadata for a GitHub repository: stars, forks, language,
    topics, license, last updated, and description.
    Input: full GitHub repo URL.
    """
    owner, repo = _parse_repo_slug(github_url)

    api_url = f"https://api.github.com/repos/{owner}/{repo}"
    headers = {}
    if os.environ.get("GITHUB_TOKEN"):
        headers["Authorization"] = f"token {os.environ['GITHUB_TOKEN']}"

    r = requests.get(api_url, headers=headers, timeout=30)
    r.raise_for_status()
    data = r.json()

    return (
        f"Repo: {data.get('full_name')}\n"
        f"Description: {data.get('description')}\n"
        f"Stars: {data.get('stargazers_count')}\n"
        f"Forks: {data.get('forks_count')}\n"
        f"Language: {data.get('language')}\n"
        f"Topics: {', '.join(data.get('topics', []))}\n"
        f"License: {data.get('license', {}).get('name', 'None')}\n"
        f"Last pushed: {data.get('pushed_at')}\n"
        f"Open issues: {data.get('open_issues_count')}\n"
        f"Homepage: {data.get('homepage')}\n"
    )


@tool
def fetch_readme(github_url: str) -> str:
    """
    Fetch the README content of a GitHub repository.
    Input: full GitHub repo URL.
    Returns the raw README text (truncated to 4000 chars).
    """
    owner, repo = _parse_repo_slug(github_url)

    # Try Apify's GitHub scraper actor for README content
    if APIFY_TOKEN:
        try:
            items = _run_actor_sync(
                "automation-lab~github-scraper",
                {
                    "startUrls": [{"url": github_url}],
                    "maxItems": 1,
                },
            )
            if items and items[0].get("readme"):
                return items[0]["readme"][:1500]
        except Exception:
            pass

    # Fallback: GitHub API raw README
    api_url = f"https://api.github.com/repos/{owner}/{repo}/readme"
    headers = {"Accept": "application/vnd.github.raw+json"}
    if os.environ.get("GITHUB_TOKEN"):
        headers["Authorization"] = f"token {os.environ['GITHUB_TOKEN']}"
    r = requests.get(api_url, headers=headers, timeout=30)
    if r.status_code == 200:
        return r.text[:1500]
    return "README not found."


@tool
def fetch_recent_issues(github_url: str) -> str:
    """
    Fetch the 10 most recent open issues from a GitHub repository.
    Input: full GitHub repo URL.
    Returns titles and labels of recent issues.
    """
    owner, repo = _parse_repo_slug(github_url)

    api_url = f"https://api.github.com/repos/{owner}/{repo}/issues"
    headers = {"Accept": "application/vnd.github+json"}
    if os.environ.get("GITHUB_TOKEN"):
        headers["Authorization"] = f"token {os.environ['GITHUB_TOKEN']}"

    r = requests.get(
        api_url,
        headers=headers,
        params={"state": "open", "per_page": 10, "sort": "created"},
        timeout=30,
    )
    r.raise_for_status()
    issues = r.json()

    if not issues:
        return "No open issues found."

    lines = []
    for i in issues:
        labels = ", ".join(l["name"] for l in i.get("labels", []))
        lines.append(f"- [{i['number']}] {i['title']}  Labels: {labels or 'none'}")
    return "\n".join(lines)


@tool
def fetch_recent_commits(github_url: str) -> str:
    """
    Fetch the 5 most recent commits from a GitHub repository.
    Input: full GitHub repo URL.
    Returns commit messages and dates.
    """
    owner, repo = _parse_repo_slug(github_url)

    api_url = f"https://api.github.com/repos/{owner}/{repo}/commits"
    headers = {}
    if os.environ.get("GITHUB_TOKEN"):
        headers["Authorization"] = f"token {os.environ['GITHUB_TOKEN']}"

    r = requests.get(api_url, headers=headers, params={"per_page": 5}, timeout=30)
    r.raise_for_status()
    commits = r.json()

    lines = []
    for c in commits:
        msg = c["commit"]["message"].split("\n")[0]  # first line only
        date = c["commit"]["author"]["date"]
        lines.append(f"- {date[:10]}: {msg}")
    return "\n".join(lines)


@tool
def fetch_dependency_manifest(github_url: str) -> str:
    """
    Fetch the dependencies manifest file (requirements.txt, package.json, pyproject.toml) of a repository.
    Input: full GitHub repo URL.
    """
    owner, repo = _parse_repo_slug(github_url)
    headers = {}
    if os.environ.get("GITHUB_TOKEN"):
        headers["Authorization"] = f"token {os.environ['GITHUB_TOKEN']}"

    manifests = ["requirements.txt", "package.json", "pyproject.toml"]
    for file in manifests:
        url = f"https://api.github.com/repos/{owner}/{repo}/contents/{file}"
        r = requests.get(url, headers=headers, timeout=15)
        if r.status_code == 200:
            raw_headers = {**headers, "Accept": "application/vnd.github.raw+json"}
            r_raw = requests.get(url, headers=raw_headers, timeout=15)
            if r_raw.status_code == 200:
                return f"File: {file}\nContent:\n{r_raw.text[:500]}"
    return "No dependency manifest file found."


@tool
def fetch_directory_tree(github_url: str) -> str:
    """
    Fetch and generate the file directory structure / ASCII tree of a GitHub repository.
    Input: full GitHub repo URL.
    """
    owner, repo = _parse_repo_slug(github_url)
    headers = {}
    if os.environ.get("GITHUB_TOKEN"):
        headers["Authorization"] = f"token {os.environ['GITHUB_TOKEN']}"

    for branch in ["main", "master"]:
        url = f"https://api.github.com/repos/{owner}/{repo}/git/trees/{branch}?recursive=1"
        r = requests.get(url, headers=headers, timeout=20)
        if r.status_code == 200:
            tree = r.json().get("tree", [])
            paths = []
            for item in tree:
                path = item.get("path", "")
                if any(part in path.split("/") for part in [".git", "__pycache__", ".venv", "node_modules", ".idea", ".vscode", "dist", "build"]):
                    continue
                paths.append(path)

            if not paths:
                return "Empty repository."

            lines = []
            for path in sorted(paths):
                depth = path.count("/")
                name = path.split("/")[-1]
                lines.append("  " * depth + " " + name)
            return "\n".join(lines[:40])
    return "Could not retrieve repository tree."


@tool
def fetch_core_source_code(github_url: str) -> str:
    """
    Find and fetch snippets from the core source code files of a GitHub repository for quality evaluation.
    Input: full GitHub repo URL.
    """
    owner, repo = _parse_repo_slug(github_url)
    headers = {}
    if os.environ.get("GITHUB_TOKEN"):
        headers["Authorization"] = f"token {os.environ['GITHUB_TOKEN']}"

    url = f"https://api.github.com/repos/{owner}/{repo}/git/trees/main?recursive=1"
    r = requests.get(url, headers={**headers}, timeout=20)
    if r.status_code != 200:
        url = f"https://api.github.com/repos/{owner}/{repo}/git/trees/master?recursive=1"
        r = requests.get(url, headers={**headers}, timeout=20)

    if r.status_code == 200:
        tree = r.json().get("tree", [])
        candidates = []
        for item in tree:
            path = item.get("path", "")
            if item.get("type") == "blob" and any(path.endswith(ext) for ext in [".py", ".js", ".ts", ".jsx", ".tsx", ".go", ".java"]):
                if not any(part in path.split("/") for part in ["test", "tests", "node_modules", ".venv", "setup.py"]):
                    candidates.append(path)

        if candidates:
            snippets = []
            for file in candidates[:2]:
                file_url = f"https://api.github.com/repos/{owner}/{repo}/contents/{file}"
                raw_headers = {**headers, "Accept": "application/vnd.github.raw+json"}
                r_file = requests.get(file_url, headers=raw_headers, timeout=15)
                if r_file.status_code == 200:
                    snippets.append(f"File: {file}\nContent:\n{r_file.text[:500]}\n")
            return "\n===\n".join(snippets)
    return "No core source code files found."


@tool
def fetch_pr_and_contributor_data(github_url: str) -> str:
    """
    Fetch active contributors and open Pull Requests summaries from a repository.
    Input: full GitHub repo URL.
    """
    owner, repo = _parse_repo_slug(github_url)
    headers = {"Accept": "application/vnd.github+json"}
    if os.environ.get("GITHUB_TOKEN"):
        headers["Authorization"] = f"token {os.environ['GITHUB_TOKEN']}"

    pr_url = f"https://api.github.com/repos/{owner}/{repo}/pulls"
    r_pr = requests.get(pr_url, headers=headers, params={"state": "open", "per_page": 5}, timeout=15)
    prs_summary = "No open Pull Requests found."
    if r_pr.status_code == 200:
        prs = r_pr.json()
        if prs:
            lines = []
            for p in prs:
                lines.append(f"- PR #{p['number']}: {p['title']} by {p.get('user', {}).get('login', 'unknown')}")
            prs_summary = "\n".join(lines)

    cont_url = f"https://api.github.com/repos/{owner}/{repo}/contributors"
    r_cont = requests.get(cont_url, headers=headers, params={"per_page": 5}, timeout=15)
    cont_summary = "No contributor details found."
    if r_cont.status_code == 200:
        conts = r_cont.json()
        if conts:
            lines = []
            for c in conts:
                lines.append(f"- {c['login']} ({c['contributions']} contributions)")
            cont_summary = "\n".join(lines)

    return f"Open Pull Requests:\n{prs_summary}\n\nTop Contributors:\n{cont_summary}"


@tool
def enrich_contributor_socials(github_url: str) -> str:
    """
    Scrapes the Twitter/X profiles of GitHub contributors using Apify to retrieve portfolios and bios.
    Input: full GitHub repo URL.
    """
    owner, repo = _parse_repo_slug(github_url)
    apify_token = os.environ.get("APIFY_API_TOKEN") or os.environ.get("APIFY_TOKEN")
    if not apify_token:
        return "Social enrichment skipped (APIFY_API_TOKEN not configured)."

    try:
        headers = {"Accept": "application/vnd.github+json"}
        if os.environ.get("GITHUB_TOKEN"):
            headers["Authorization"] = f"token {os.environ['GITHUB_TOKEN']}"
        cont_url = f"https://api.github.com/repos/{owner}/{repo}/contributors"
        r = requests.get(cont_url, headers=headers, params={"per_page": 3}, timeout=15)
        if r.status_code != 200:
            return "No contributors found for social enrichment."
            
        conts = r.json()
        logins = [c['login'] for c in conts if 'login' in c]
        if not logins:
            return "No contributors found for social enrichment."

        print(f"[Apify Twitter Enrichment] Enriching contributors: {logins}...")
        url = "https://api.apify.com/v2/acts/apify~twitter-scraper/run-sync-get-dataset-items?token=" + apify_token
        payload = {
            "searchMode": "Users",
            "searchTerms": logins,
            "maxTweets": 1
        }
        r_apify = requests.post(url, json=payload, timeout=20)
        if r_apify.status_code in [200, 201]:
            items = r_apify.json()
            cards = []
            for item in items:
                name = item.get("name") or item.get("userName", "")
                twitter_url = item.get("twitterUrl") or f"https://x.com/{item.get('userName', '')}"
                bio = item.get("biography", "")
                cards.append(f"- **{name}** ({twitter_url})\n  _{bio}_")
            if cards:
                return "Maintainer Social Connections (via Apify Twitter Scraper):\n" + "\n".join(cards)
    except Exception as e:
        print(f"[Apify Twitter Enrichment Error] {e}")
        
    return "Social enrichment completed."


# Agent Setup

def get_scraper_executor() -> AgentExecutor:
    llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)
    tools = [
        fetch_repo_metadata,
        fetch_readme,
        fetch_recent_issues,
        fetch_recent_commits,
        fetch_dependency_manifest,
        fetch_directory_tree,
        fetch_core_source_code,
        fetch_pr_and_contributor_data
    ]

    prompt = ChatPromptTemplate.from_messages([
        (
            "system",
            """You are an advanced GitHub repository data collector.
Given a GitHub URL, you MUST call ALL of the following eight tools in order to gather complete repository context:
1. fetch_repo_metadata
2. fetch_readme
3. fetch_recent_issues
4. fetch_recent_commits
5. fetch_dependency_manifest
6. fetch_directory_tree
7. fetch_core_source_code
8. fetch_pr_and_contributor_data

Combine all results into a single structured text block.
Do not summarise or interpret — return raw collected data."""
        ),
        ("human", "{input}"),
        MessagesPlaceholder(variable_name="agent_scratchpad"),
    ])

    agent = create_tool_calling_agent(llm, tools, prompt)
    return AgentExecutor.from_agent_and_tools(
        agent=agent, tools=tools, verbose=True
    )


def run_scraper(github_url: str) -> str:
    """Run the in-memory scraper tools directly to bypass slow LLM loops and prevent timeouts."""
    print(f"[Direct Scraper] Gathering data for {github_url}...")
    try:
        metadata = fetch_repo_metadata.invoke(github_url)
        readme = fetch_readme.invoke(github_url)
        issues = fetch_recent_issues.invoke(github_url)
        commits = fetch_recent_commits.invoke(github_url)
        deps = fetch_dependency_manifest.invoke(github_url)
        tree = fetch_directory_tree.invoke(github_url)
        code = fetch_core_source_code.invoke(github_url)
        prs = fetch_pr_and_contributor_data.invoke(github_url)
        socials = enrich_contributor_socials.invoke(github_url)
        
        return f"""Repo Metadata:
{metadata}

README:
{readme}

Recent Issues:
{issues}

Recent Commits:
{commits}

Dependency Manifest:
{deps}

Directory Tree:
{tree}

Core Source Code:
{code}

PR and Contributor Data:
{prs}

Contributor Social Enrichment:
{socials}"""
    except Exception as e:
        print(f"[Scraper Fallback] Direct scrape failed, falling back to agent loop: {e}")
        executor = get_scraper_executor()
        res = executor.invoke({"input": github_url})
        return res.get("output", "")

import os
import re
import requests
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from langchain_classic.agents import AgentExecutor, create_tool_calling_agent
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_community.tools import DuckDuckGoSearchRun
from dotenv import load_dotenv

load_dotenv()


def _parse_repo_slug(github_url: str) -> tuple[str, str]:
    """Extract owner/repo from any github.com URL."""
    m = re.search(r"github\.com/([^/]+)/([^/?\s]+)", github_url)
    if not m:
        raise ValueError(f"Cannot parse GitHub URL: {github_url}")
    return m.group(1), m.group(2).rstrip("/")


# LangChain tools

@tool
def search_the_web(query: str) -> str:
    """
    Search the web for information using DuckDuckGo search.
    Use this to locate official documentation URLs, guides, or blog posts.
    Input: search query string.
    """
    try:
        print(f"[Instant Search] Querying DuckDuckGo for: '{query}'...")
        search = DuckDuckGoSearchRun()
        return search.run(query)
    except Exception as e:
        return f"Search failed: {e}"


@tool
def fetch_owner_ecosystem(github_url: str) -> str:
    """
    Fetch other popular repositories by the same owner/organization to understand their ecosystem.
    Input: full GitHub repo URL.
    """
    try:
        owner, _ = _parse_repo_slug(github_url)
        url = f"https://api.github.com/users/{owner}/repos"
        headers = {}
        if os.environ.get("GITHUB_TOKEN"):
            headers["Authorization"] = f"token {os.environ['GITHUB_TOKEN']}"
        r = requests.get(url, headers=headers, params={"sort": "stars", "per_page": 5}, timeout=15)
        if r.status_code == 200:
            repos = r.json()
            lines = []
            for r_item in repos:
                lines.append(f"- {r_item['name']}: {r_item.get('description', '')} (★ {r_item.get('stargazers_count')})")
            return f"Ecosystem Repositories by {owner}:\n" + "\n".join(lines)
    except Exception as e:
        return f"Failed to fetch ecosystem: {e}"
    return "No complementary repos found."


# Agent Setup

def get_deep_diver_executor() -> AgentExecutor:
    llm = ChatOpenAI(
        model="gpt-4o-mini",
        temperature=0.2,
        base_url=os.environ.get("OPENAI_API_BASE") or os.environ.get("OPENAI_BASE_URL") or None
    )
    tools = [search_the_web, fetch_owner_ecosystem]

    prompt = ChatPromptTemplate.from_messages([
        (
            "system",
            """You are a specialized documentation hunter and onboarding expert.
Given a GitHub URL and a project name, your goal is to research, locate, and compile a premium, step-by-step "Deep Dive Onboarding Guide" for the project.

You MUST use your tools to perform the following research:
1. Search the web for the official documentation homepage of the project (e.g. searching "[Project Name] official documentation" or "ReadTheDocs [Project Name]").
2. Search the web for a step-by-step tutorial or advanced guide.
3. Fetch the owner's complementary ecosystem repositories using fetch_owner_ecosystem.

Synthesize all your findings into a stunning, beautifully formatted Markdown report containing:
- 📖 **Official Documentation**: Clickable links to the official docs, API references, or wikis.
- 🎓 **Curated Tutorials & Guides**: Found blog posts, getting started tutorials, or setup guides with links.
- 🏗️ **Complementary Ecosystem**: Other notable libraries/projects by the same author to explore.
- 🗺️ **Step-by-Step Learning Path**: A logical recommended learning path for a developer trying to master this project.

Ensure all links are real markdown links (e.g. `[FastAPI Docs](https://fastapi.tiangolo.com)`). No placeholders."""
        ),
        ("human", "Analyze and Deep Dive into: {input}"),
        MessagesPlaceholder(variable_name="agent_scratchpad"),
    ])

    agent = create_tool_calling_agent(llm, tools, prompt)
    return AgentExecutor.from_agent_and_tools(
        agent=agent, tools=tools, verbose=True
    )


# Unified entry point

def run_deep_dive(github_url: str, project_name: str) -> str:
    """Run the in-memory deep dive research agent and return the compiled Markdown onboarding guide."""
    executor = get_deep_diver_executor()
    query = f"URL: {github_url}\nProject Name: {project_name}"
    res = executor.invoke({"input": query})
    return res.get("output", "")

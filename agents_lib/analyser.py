import os
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from langchain_classic.agents import AgentExecutor, create_tool_calling_agent
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from dotenv import load_dotenv

load_dotenv()


# LangChain tools

@tool
def analyse_repo_data(raw_data: str) -> str:
    """
    Analyse raw GitHub repository data and extract structured insights.
    Input: combined raw text from scraper agent (metadata + README + issues + commits + manifests + trees + code + PRs).
    Returns a JSON string with the analysis.
    """
    llm = ChatOpenAI(
        model="gpt-4o-mini",
        temperature=0.2,
        base_url=os.environ.get("OPENAI_API_BASE") or os.environ.get("OPENAI_BASE_URL") or None
    )

    prompt = f"""You are an expert software analyst. Analyse this GitHub repository data and return a JSON object.

RAW DATA:
{raw_data}

Return ONLY a valid JSON object with these exact keys:
{{
  "project_name": "name of the project",
  "one_line_summary": "what this project does in one sentence",
  "tech_stack": ["list", "of", "technologies"],
  "project_maturity": "alpha|beta|stable|mature",
  "activity_level": "inactive|low|moderate|high|very-high",
  "key_features": ["up to 5 key features"],
  "target_audience": "who this project is for",
  "getting_started": "how to install/run in 2-3 sentences",
  "open_problems": ["top 3 open issues or pain points"],
  "health_score": 0-100,
  "health_reasons": ["2-3 reasons for the score"],
  "dependencies": {{
    "security_score": 0-100,
    "issues": ["list of outdated, insecure, or heavy dependencies found, or 'None found'"]
  }},
  "directory_tree": "copy the generated ASCII directory tree structure exactly as-is from raw data, or return 'Not found'",
  "code_quality_review": {{
    "rating": "A|B|C|D|F",
    "readability": "evaluation of code cleanliness, comments, and structure of the fetched snippets",
    "bottlenecks": "mention any potential bugs, structural debt, or bottlenecks in the snippets",
    "suggestions": ["2-3 actionable improvement suggestions for the codebase"]
  }},
  "community_health": {{
    "open_prs": "number of open pull requests, or '0'",
    "activity_summary": "brief evaluation of contributor activity and pull request responsiveness"
  }}
}}

No markdown. No explanation. Pure JSON only."""

    response = llm.invoke(prompt)
    return response.content


@tool
def score_complexity(raw_data: str) -> str:
    """
    Score the complexity and learning curve of a repository.
    Input: raw repo data text.
    Returns complexity assessment as JSON.
    """
    llm = ChatOpenAI(
        model="gpt-4o-mini",
        temperature=0,
        base_url=os.environ.get("OPENAI_API_BASE") or os.environ.get("OPENAI_BASE_URL") or None
    )

    prompt = f"""Based on this repo data, assess complexity. Return ONLY JSON:

{raw_data[:2000]}

{{
  "complexity": "beginner|intermediate|advanced|expert",
  "setup_difficulty": "easy|moderate|hard|very-hard",
  "prerequisites": ["list of required knowledge/tools"],
  "estimated_setup_minutes": 5
}}"""

    response = llm.invoke(prompt)
    return response.content


# Agent Setup

def get_analyser_executor() -> AgentExecutor:
    llm = ChatOpenAI(
        model="gpt-4o-mini",
        temperature=0,
        base_url=os.environ.get("OPENAI_API_BASE") or os.environ.get("OPENAI_BASE_URL") or None
    )
    tools = [analyse_repo_data, score_complexity]

    prompt = ChatPromptTemplate.from_messages([
        (
            "system",
            """You are a repository intelligence analyst.
You receive raw GitHub repository data and must:
1. Call analyse_repo_data with the full input
2. Call score_complexity with the full input
3. Combine both JSON results into one merged JSON object and return it.

Always return a single valid JSON object. No prose."""
        ),
        ("human", "{input}"),
        MessagesPlaceholder(variable_name="agent_scratchpad"),
    ])

    agent = create_tool_calling_agent(llm, tools, prompt)
    return AgentExecutor.from_agent_and_tools(
        agent=agent, tools=tools, verbose=True
    )


def run_analyser(raw_data: str) -> str:
    """Run the in-memory analyser tools directly to bypass slow LLM loops and prevent timeouts."""
    print("[Direct Analyser] Analyzing repository data...")
    try:
        repo_json_str = analyse_repo_data.invoke(raw_data)
        complexity_json_str = score_complexity.invoke(raw_data)
        
        import json
        
        # Clean any markdown fences from LLM responses
        def clean_json(s):
            s = s.strip()
            if s.startswith("```"):
                s = s.split("```")[1]
                if s.startswith("json"):
                    s = s[4:]
            return s.strip()

        d1 = json.loads(clean_json(repo_json_str))
        d2 = json.loads(clean_json(complexity_json_str))
        d1.update(d2)
        return json.dumps(d1)
    except Exception as e:
        print(f"[Analyser Fallback] Direct analysis failed, falling back to agent loop: {e}")
        executor = get_analyser_executor()
        res = executor.invoke({"input": raw_data})
        return res.get("output", "{}")

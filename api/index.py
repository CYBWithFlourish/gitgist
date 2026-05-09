import os
import re
import uuid
import threading
import requests
from flask import Flask, request, jsonify
from flask_cors import CORS
from dotenv import load_dotenv

import sys
# Add project root to sys.path so agents_lib can be imported from api/
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Import the in-memory agents
from agents_lib import run_scraper, run_analyser, run_reporter, run_deep_dive

load_dotenv()

# Serve static files from '../static' directory at the root url path
app = Flask(__name__, static_folder="../static", static_url_path="")
CORS(app)

SUPERPLANE_URL = os.environ.get("SUPERPLANE_WEBHOOK_URL", "https://app.superplane.com")

# Zynd AI Integration
try:
    from zyndai_agent import ZyndAgent
    wallet_addr = os.environ.get("ZYND_WALLET_ADDRESS", "0xYourWeb3WalletAddressHere")
    zynd_agent = ZyndAgent(
        name="GitGist Repo Intelligence",
        description="Autonomous multi-agent system that scrapes, analyzes, and explains any GitHub repository.",
        version="1.0.0",
        wallet_address=wallet_addr
    )
    print(f"[Zynd AI] Agent initialized successfully with DID: {zynd_agent.did}")
    
    # Enable HTTP 402 Pay-Per-Call (0.05 USDC per call)
    zynd_agent.enable_payments(
        price_usdc=0.05,
        network="base"
    )
    print(f"[Zynd AI Web3] Pay-Per-Call activated on Base network for wallet: {wallet_addr}")
    
    # Register capabilities to the decentralized agent registry
    zynd_agent.register_capability(
        name="Scrape Repository",
        description="Fetches raw metadata, issues, trees, and dependencies of a GitHub URL."
    )
    zynd_agent.register_capability(
        name="Analyse Codebase",
        description="Performs code quality, health assessments, and maturity checks."
    )
    zynd_agent.register_capability(
        name="Deep Dive Documentation Hunter",
        description="Scours the web to find official docs and advanced tutorials."
    )
    print("[Zynd AI] Capabilities registered successfully on the decentralized agent registry.")
except Exception as e:
    zynd_agent = None
    print(f"[Zynd AI Info] SDK initialization skipped or not configured: {e}")

# In-memory job store
jobs: dict[str, dict] = {}


# Superplane Integration

def notify_superplane(event: str, payload: dict):
    """Send an event to the Superplane canvas webhook trigger."""
    try:
        requests.post(
            SUPERPLANE_URL,
            json={"event": event, **payload},
            timeout=5,
        )
    except Exception as e:
        print(f"[Superplane notify error] {e}")


# Pipeline Execution

def run_pipeline(job_id: str, github_url: str):
    """
    Full GitGist pipeline running in-memory:
      1. scraper_agent  → raw repo data
      2. analyser_agent → structured JSON analysis
      3. reporter_agent → final markdown report
    """
    jobs[job_id]["status"] = "running"
    notify_superplane("pipeline.started", {
        "job_id": job_id,
        "url": github_url,
        "github_url": github_url,
        "send_discord": jobs[job_id].get("send_discord", False),
        "send_telegram": jobs[job_id].get("send_telegram", False),
        "send_notion": jobs[job_id].get("send_notion", False)
    })

    try:
        # Step 1: Scraper
        jobs[job_id]["step"] = "scraping"
        notify_superplane("step.started", {"job_id": job_id, "step": "scraper"})

        print(f"[{job_id}] Running Scraper Agent...")
        raw_data = run_scraper(github_url)
        jobs[job_id]["raw_data"] = raw_data
        notify_superplane("step.completed", {"job_id": job_id, "step": "scraper"})

        # Step 2: Analyser
        jobs[job_id]["step"] = "analysing"
        notify_superplane("step.started", {"job_id": job_id, "step": "analyser"})

        print(f"[{job_id}] Running Analyser Agent...")
        analysis_json = run_analyser(raw_data)
        jobs[job_id]["analysis"] = analysis_json
        notify_superplane("step.completed", {"job_id": job_id, "step": "analyser"})

        # Step 3: Reporter
        jobs[job_id]["step"] = "formatting"
        notify_superplane("step.started", {"job_id": job_id, "step": "reporter"})

        print(f"[{job_id}] Running Reporter Agent...")
        report = run_reporter(analysis_json, github_url)

        jobs[job_id]["status"] = "done"
        jobs[job_id]["step"] = "complete"
        jobs[job_id]["report"] = report
        notify_superplane("pipeline.completed", {"job_id": job_id})
        print(f"[{job_id}] Pipeline completed successfully!")

    except Exception as e:
        jobs[job_id]["status"] = "error"
        jobs[job_id]["error"] = str(e)
        notify_superplane("pipeline.failed", {"job_id": job_id, "error": str(e)})
        print(f"[{job_id}] Pipeline error: {e}")


# Web Routes

@app.route("/")
def index():
    """Serve the index.html frontend page."""
    return app.send_static_file("index.html")


@app.post("/scraper")
def proxy_scraper():
    """In-memory Scraper endpoint called by Superplane Canvas."""
    body = request.get_json(silent=True) or {}
    github_url = (body.get("content") or "").strip() or (body.get("github_url") or "").strip()
    if not github_url:
        github_url = "https://github.com/fastapi/fastapi"
    print(f"[Superplane Action] Calling Scraper for: {github_url}")
    try:
        result = run_scraper(github_url)
        return jsonify({"output": result})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.post("/analyser")
def proxy_analyser():
    """In-memory Analyser endpoint called by Superplane Canvas."""
    body = request.get_json(silent=True) or {}
    raw_data = body.get("content", "")
    print(f"[Superplane Action] Calling Analyser")
    if not raw_data:
        raw_data = "No raw data provided."
    try:
        result = run_analyser(raw_data)
        return jsonify({"output": result})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.post("/reporter")
def proxy_reporter():
    """In-memory Reporter endpoint called by Superplane Canvas."""
    body = request.get_json(silent=True) or {}
    raw_input = body.get("content", "")
    print(f"[Superplane Action] Calling Reporter")
    if not raw_input:
        raw_input = "JSON: {}\nURL: https://github.com/fastapi/fastapi"

    # Extract JSON part
    analysis_json = "{}"
    m_json = re.search(r"JSON:\s*(.*?)\s*URL:", raw_input, re.DOTALL | re.IGNORECASE)
    if m_json:
        analysis_json = m_json.group(1).strip()
    else:
        if raw_input.strip().startswith("{"):
            analysis_json = raw_input.strip()

    # Extract URL part
    github_url = "https://github.com/fastapi/fastapi"
    m_url = re.search(r"URL:\s*(\S+)", raw_input, re.IGNORECASE)
    if m_url:
        github_url = m_url.group(1).strip()

    try:
        result = run_reporter(analysis_json, github_url)
        return jsonify({"output": result})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.post("/discord/notify")
def discord_notify():
    """Conditionally send a beautifully formatted Discord embed summary card."""
    body = request.get_json(silent=True) or {}
    send_discord = body.get("send_discord", False)
    if isinstance(send_discord, str):
        send_discord = send_discord.lower() == "true"
        
    if not send_discord:
        print("[Discord Notification] Skipped (user checkbox was not ticked).")
        return jsonify({"status": "skipped", "reason": "checkbox not ticked"})

    webhook_url = os.environ.get("DISCORD_WEBHOOK_URL")
    if not webhook_url:
        print("[Discord Notification] Skipped (DISCORD_WEBHOOK_URL not set in .env).")
        return jsonify({"status": "skipped", "reason": "webhook url not set"})

    url = body.get("url", "https://github.com/fastapi/fastapi")
    project_name = body.get("name", "the project")

    payload = {
        "embeds": [
            {
                "title": f"🚀 GitGist Repo Analysis Complete: {project_name}",
                "url": url,
                "color": 3447003,
                "description": f"Our autonomous multi-agent pipeline has successfully scraped, analysed, and generated a deep-dive onboarding guide for **{project_name}**!",
                "fields": [
                    {"name": "📁 Codebase URL", "value": url, "inline": False},
                    {"name": "🤖 Identity", "value": "Zynd AI DID Registered", "inline": True},
                    {"name": "⚡ Scrape Engine", "value": "Apify & GitHub APIs", "inline": True}
                ],
                "footer": {
                    "text": "Generated by GitGist · Powered by Zynd × Apify × Superplane"
                }
            }
        ]
    }
    try:
        r = requests.post(webhook_url, json=payload, timeout=10)
        if r.status_code in [200, 204]:
            print("[Discord Notification] Sent successfully!")
            return jsonify({"status": "success"})
        else:
            return jsonify({"status": "failed", "error": f"Discord returned {r.status_code}"}), r.status_code
    except Exception as e:
        return jsonify({"status": "failed", "error": str(e)}), 500


@app.post("/telegram/notify")
def telegram_notify():
    """Conditionally send a Markdown alert to Telegram via Bot API."""
    body = request.get_json(silent=True) or {}
    send_telegram = body.get("send_telegram", False)
    if isinstance(send_telegram, str):
        send_telegram = send_telegram.lower() == "true"

    if not send_telegram:
        print("[Telegram Notification] Skipped (user checkbox was not ticked).")
        return jsonify({"status": "skipped", "reason": "checkbox not ticked"})

    bot_token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    
    if not bot_token or not chat_id:
        print("[Telegram Notification] Skipped (TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID not set in .env).")
        return jsonify({"status": "skipped", "reason": "credentials not set"})

    url = body.get("url", "https://github.com/fastapi/fastapi")
    project_name = body.get("name", "the project")

    text = f"""🚀 *GitGist Repo Analysis Complete: {project_name}*

Our autonomous multi-agent pipeline has successfully analysed the codebase!
🔗 *Codebase URL:* {url}

_Generated by GitGist · Powered by Zynd × Apify × Superplane_"""

    try:
        t_url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        r = requests.post(t_url, json={
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "Markdown"
        }, timeout=10)
        if r.status_code == 200:
            print("[Telegram Notification] Sent successfully!")
            return jsonify({"status": "success"})
        else:
            return jsonify({"status": "failed", "error": f"Telegram returned {r.status_code}"}), r.status_code
    except Exception as e:
        return jsonify({"status": "failed", "error": str(e)}), 500


@app.post("/notion/create")
def notion_create():
    """Conditionally create a beautifully structured page in Notion via API."""
    body = request.get_json(silent=True) or {}
    send_notion = body.get("send_notion", False)
    if isinstance(send_notion, str):
        send_notion = send_notion.lower() == "true"

    if not send_notion:
        print("[Notion Wiki] Skipped (user checkbox was not ticked).")
        return jsonify({"status": "skipped", "reason": "checkbox not ticked"})

    token = os.environ.get("NOTION_INTEGRATION_TOKEN")
    parent_id = os.environ.get("NOTION_PARENT_PAGE_ID")

    if not token or not parent_id:
        print("[Notion Wiki] Skipped (NOTION_INTEGRATION_TOKEN or NOTION_PARENT_PAGE_ID not set in .env).")
        return jsonify({"status": "skipped", "reason": "credentials not set"})

    url = body.get("url", "https://github.com/fastapi/fastapi")
    project_name = body.get("name", "the project")

    n_url = "https://api.notion.com/v1/pages"
    headers = {
        "Authorization": f"Bearer {token}",
        "Notion-Version": "2022-06-28",
        "Content-Type": "application/json"
    }
    payload = {
        "parent": {"page_id": parent_id},
        "properties": {
            "title": {
                "title": [
                    {"text": {"content": f"🚀 Onboarding Guide: {project_name}"}}
                ]
            }
        },
        "children": [
            {
                "object": "block",
                "type": "heading_1",
                "heading_1": {
                    "rich_text": [{"text": {"content": f"🚀 GitGist Repository Manual: {project_name}"}}]
                }
            },
            {
                "object": "block",
                "type": "paragraph",
                "paragraph": {
                    "rich_text": [
                        {
                            "text": {
                                "content": f"This onboarding guide has been autonomously generated by GitGist for {url}. It is fully synchronized with your multi-agent architecture and decentralized Zynd AI identity!"
                            }
                        }
                    ]
                }
            }
        ]
    }
    try:
        r = requests.post(n_url, json=payload, headers=headers, timeout=12)
        if r.status_code in [200, 201]:
            print("[Notion Wiki] Page created successfully!")
            return jsonify({"status": "success"})
        else:
            return jsonify({"status": "failed", "error": f"Notion returned {r.status_code}: {r.text}"}), r.status_code
    except Exception as e:
        return jsonify({"status": "failed", "error": str(e)}), 500


@app.post("/superplane/result")
def superplane_result():
    """Callback for Superplane workflow finalization."""
    body = request.get_json(silent=True) or {}
    job_id = body.get("job_id", "canvas-run")
    report = body.get("report", "")
    print(f"[Superplane callback] Received final report for job {job_id}")
    if job_id not in jobs:
        jobs[job_id] = {}
    jobs[job_id]["status"] = "done"
    jobs[job_id]["report"] = report
    return jsonify({"status": "success"})


@app.post("/analyse")
def start_analysis():
    """Frontend entry point to initiate asynchronous pipeline."""
    body = request.get_json(force=True)
    github_url = (body.get("url") or "").strip()
    send_discord = body.get("send_discord", False)
    send_telegram = body.get("send_telegram", False)
    send_notion = body.get("send_notion", False)

    if not github_url or "github.com" not in github_url:
        return jsonify({"error": "Please provide a valid GitHub URL"}), 400

    job_id = str(uuid.uuid4())[:8]
    jobs[job_id] = {
        "id": job_id,
        "url": github_url,
        "status": "queued",
        "step": "queued",
        "report": None,
        "error": None,
        "send_discord": send_discord,
        "send_telegram": send_telegram,
        "send_notion": send_notion,
    }

    t = threading.Thread(target=run_pipeline, args=(job_id, github_url), daemon=True)
    t.start()

    return jsonify({"job_id": job_id})


@app.get("/status/<job_id>")
def get_status(job_id: str):
    """Poll endpoint for tracking job status."""
    job = jobs.get(job_id)
    if not job:
        return jsonify({"error": "Job not found"}), 404
    return jsonify(job)


@app.get("/health")
def health():
    return jsonify({"status": "ok", "jobs": len(jobs)})


@app.post("/superplane/trigger")
def superplane_trigger():
    """Triggered by external webhooks."""
    body = request.get_json(force=True)
    github_url = body.get("github_url", "")
    if not github_url:
        return jsonify({"error": "github_url required"}), 400

    job_id = str(uuid.uuid4())[:8]
    jobs[job_id] = {
        "id": job_id,
        "url": github_url,
        "status": "queued",
        "step": "queued",
        "report": None,
        "error": None,
    }
    t = threading.Thread(target=run_pipeline, args=(job_id, github_url), daemon=True)
    t.start()

    return jsonify({"job_id": job_id, "message": "Pipeline started"})


@app.post("/deep-dive")
def deep_dive():
    """Execute the Deep Diver Agent in-memory to find advanced docs and guides."""
    body = request.get_json(silent=True) or {}
    github_url = (body.get("url") or "").strip() or (body.get("github_url") or "").strip() or (body.get("content") or "").strip()
    project_name = (body.get("name") or "the project").strip()

    if not github_url:
        github_url = "https://github.com/fastapi/fastapi"

    print(f"[Deep Dive] Running documentation and tutorial search for {project_name} ({github_url})...")
    try:
        result = run_deep_dive(github_url, project_name)
        return jsonify({"output": result})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    print(f"Unified GitGist Server running on http://localhost:{port}")
    app.run(host="0.0.0.0", port=port, debug=False)

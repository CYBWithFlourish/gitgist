# GitGist - Autonomous Multi-Agent Repository Intelligence Suite

> Paste any public GitHub repository URL. An orchestrated, autonomous multi-agent pipeline scrapes, enriches, analyses, compiles documentation, and delivers beautifully formatted onboarding wikis and multi-channel notifications in under 30 seconds.

Built for **Bot-a-thon 2026** with **Python**, **Flask**, **LangChain**, and **OpenAI GPT-4o-mini**, orchestrated via **Superplane Canvas** and powered by **Zynd AI** and **Apify**.

-

## Flagship Features

GitGist integrates cutting-edge developer platforms to deliver an enterprise-grade repo onboarding pipeline:

- **Superplane Orchestrated Canvas**: A robust 9-node visual multi-agent workflow managing state transition from trigger to scraper, analyser, reporter, documentation hunter, and multi-channel dispatch.
- **Zynd AI Blockchain Payments**: Fully integrated pay-per-call USDC utility model on the **Base network** (`0.05 USDC` per run), registering your agent identity securely on the decentralized network.
- **Apify Social Enrichment**: Synchronously scrapes maintainer Twitter profiles during repository extraction to render complete social cards.
- **Notion Page Wiki Generation**: Creates a beautifully structured, dedicated onboarding page inside your team's Notion workspace dynamically via the Notion Pages API.
- **Telegram & Discord Alerts**: Sends stateless direct notifications (Markdown alerts to Telegram and high-fidelity embedded color cards to Discord) the instant your scan completes.
- **Deep Diver Documentation Hunter**: Autonomously crawls the web to gather official guides, wikis, tutorials, and complementary libraries for any repository.

-

## Pipeline Architecture

```
                                  [ Zynd AI (0.05 USDC / Base) ]
                                                ↓
User → Frontend (static/index.html) → POST /analyse → Flask Server (api/index.py)
                                                            ↓
                                               [ Superplane Webhook Trigger ]
                                                            ↓
       ┌───────────────────────────────┬────────────────────┴───────────────────┬───────────────────────────────┐
       ↓                               ↓                                        ↓                               ↓
[ Scraper Agent ]              [ Analyser Agent ]                       [ Reporter Agent ]              [ Deep Diver Agent ]
 (Apify Twitter Scraper)       (LangChain LLM Analysis)                 (Interactive Markdown Builder)   (Instant Documentation Hunt)
       │                               │                                        │                               │
       └───────────────────────────────┼────────────────────┬───────────────────┴───────────────────────────────┘
                                       ↓                    ↓
                                [ Discord Alert ]   [ Telegram Alert ]   [ Notion Wiki Creator ]
```

-

## Repository Structure

```
gitgist/
├── api/
│   └── index.py            # Unified Flask Server (Serves APIs & Static Site)
├── static/
│   └── index.html          # Premium Single-Page UI
├── agents_lib/             # Local autonomous AI agents package
│   ├── scraper.py          # GitHub API Crawler & Apify Social Scraper
│   ├── analyser.py         # LLM Repository Metrics Analyser
│   ├── reporter.py         # Markdown Report Compiler
│   └── deep_diver.py       # Instant Documentation & Guide Searcher
├── canvas.yaml             # Superplane 9-Node Visual Canvas Configuration
├── requirements.txt        # Python package dependencies
└── README.md               # Project Showcase & Documentation
```

-

## Setup & Local Deployment

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. Configure Environment

Copy `.env.example` to `.env` and fill in your custom API tokens:

```bash
cp .env.example .env
```

```env
OPENAI_API_KEY=your_openai_api_key
APIFY_API_TOKEN=your_apify_token
ZYND_WALLET_ADDRESS=your_base_usdc_wallet_address
SUPERPLANE_WEBHOOK_URL=your_superplane_webhook_url

# Integrations (Optional)
DISCORD_WEBHOOK_URL=your_discord_webhook_url
TELEGRAM_BOT_TOKEN=your_telegram_bot_token
TELEGRAM_CHAT_ID=your_telegram_chat_id
NOTION_INTEGRATION_TOKEN=your_notion_integration_token
NOTION_PARENT_PAGE_ID=your_notion_parent_page_id
```

### 3. Start the Server

```bash
PORT=8080 python api/index.py
```

Open `http://localhost:8080` in your browser and experience GitGist!

-
_Built for Bot-a-thon 2026. Powered by Zynd AI × Apify × Superplane._

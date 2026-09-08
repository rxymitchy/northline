# Find Clients Agent

Open-source personal outbound prospecting agent. It finds businesses (Kenya/Nairobi first) with **observable automation gaps**, researches public evidence, scores fit, drafts human emails, and waits for your approval. It does **not** auto-send email.

**Contributions are welcome.** If something is broken or clumsy, open an issue or a pull request. See [CONTRIBUTING.md](CONTRIBUTING.md). Licensed under [MIT](LICENSE).

The goal is not a generic lead scraper. The goal is: **companies showing evidence of operational pain you can actually automate.**

## Architecture

```
ICP text
  → ICP parser (OpenAI, heuristic fallback if the API is down/out of credits)
  → Discovery (pluggable search: DuckDuckGo / Tavily / Serper / Brave)
  → Deduplicate by domain/name
  → Drop news/listicles/review sites (keep official company sites)
  → Cheap filter
  → Deep research (public HTML)
  → Literal automation-gap detection (WhatsApp, call-to-book, agency overflow, …)
  → Contact finder (public email + phone only; never invented)
  → Score 0–100
  → Outreach draft for qualified prospects
  → Dashboard approve/reject + CSV
```

Python modules: `backend/app/modules/`. Search providers: `backend/app/providers/`. SQLite stores companies, contacts, opportunities, outreach, runs, logs, and API usage.

## Setup

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy ..\.env.example .env
# edit .env and set OPENAI_API_KEY (needs API billing credits, not ChatGPT Plus)
uvicorn app.main:app --reload --port 8000
```

Open **http://localhost:8000**.

Optional Next.js UI is in `frontend/` and talks to the same API.

On Windows, Avast/antivirus HTTPS scanning can block Python SSL. This project fetches via a stack that usually still works. If OpenAI has **no API credits**, ICP/outreach fall back to heuristics until you top up billing.

## Environment

| Variable | Required | Purpose |
|---|---|---|
| `OPENAI_API_KEY` | For AI drafts | ICP parse, research reasoning, outreach |
| `OPENAI_MODEL` | No | Default `gpt-4o-mini` |
| `SEARCH_PROVIDER` | No | `duckduckgo` (free), `tavily`, `serper`, or `brave` |
| `TAVILY_API_KEY` / `SERPER_API_KEY` / `BRAVE_API_KEY` | If you switch provider | Search APIs |
| `MAX_DISCOVER` / `MAX_DEEP_RESEARCH` / `MAX_OUTREACH` | No | Funnel caps |
| `EMAIL_SENDING_ENABLED` | Keep `false` | Sending is not implemented |

Never commit `.env`. Copy `.env.example` only.

## Database (SQLite)

`research_runs`, `companies`, `contacts`, `opportunities`, `outreach`, `event_logs`, `api_usage`.

## Known limitations

- Public HTML only. No login, CAPTCHA, paywall, or ToS bypass.
- Decision-maker emails/phones are often missing; marked **CONTACT NOT VERIFIED**. Never fabricated.
- DuckDuckGo is noisy; listicles are filtered but some still slip through.
- Heuristic scoring is rule-based; LLM scoring needs API credits.
- Follow-up sending is disabled on purpose.

## Cost (rough)

A small Nairobi run (discover ~25, research ~10–20, a handful of drafts) is typically well under **$0.10** on `gpt-4o-mini`, plus $0 if you use DuckDuckGo.

## Next improvements

1. Kenya directory adapters that extract official websites.
2. Optional send via a provider you control, still one-click approve.
3. Learn from good/bad feedback which gaps actually convert.

## Compliance

Respect robots.txt, site terms, API limits, privacy law, and email rules. This tool drafts research-backed outreach for a human to send.

# Northline

**Manual work is quietly ruining the company.**

Repo: [github.com/rxymitchy/northline](https://github.com/rxymitchy/northline)

Northline looks at how a business actually takes work in — website, social profile, spreadsheet, or a short description — and says what still depends on a person. It is not a generic lead scraper.

Public app: paste how you work, get a snapshot, download the full report, then optionally see **real companies** (not blogs or roundups) that are further along. Those companies are included when you download the report again.

A PIN-locked **admin** hunt still finds other businesses with public automation gaps and drafts outreach to **public** emails only. Never invented contacts.

**Contributions are welcome.** If something is broken or clumsy, open an issue or a pull request. See [CONTRIBUTING.md](CONTRIBUTING.md). Licensed under [MIT](LICENSE).

## What visitors get

1. Choose **Website**, **Social media**, **Data file / CSV**, or **Describe how you work**.
2. Add name and email, then **See the diagnosis**.
3. Northline reads the page you sent **and** a short public web search for the company (news, directories, other mentions), in parallel, with a hard time cap so this usually finishes in **10–20 seconds**.
4. On-page snapshot: overall manual dependency, which processes still wait on a person, what to automate first, and a suggested workflow.
5. **Download the full report**. Optional: **Schedule a 30-minute call** opens Calendly (`BOOKING_URL`, default `https://calendly.com/lucianamitchell19/northline-business-automation`) with name and email filled in.
6. **See companies in this industry** — operating businesses, not blogs or roundups. Download the report again so they are in the file.

Visitor diagnosis stays heuristic: no OpenAI, no invented emails, no login/CAPTCHA bypass. Search is bounded so a slow site or DuckDuckGo cannot hang the page for a minute.

## Admin hunt

Lock icon on the public page → admin dashboard. Pipeline: search → drop publishers/listicles → public HTML research → gap detection → public contacts only → score → optional SMTP cold send when enabled.

## Setup

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy ..\.env.example .env
# edit .env — SMTP if you want report emails; OPENAI_API_KEY only for admin LLM drafts
py -3.13 -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

Open **http://127.0.0.1:8000**.

Use **Python 3.13** (or any version with the packages in `requirements.txt` installed). On Windows, antivirus HTTPS scanning can block Python SSL; fetches go through a stack that usually still works.

An older Next.js dashboard lives in `frontend/` and talks to the same API. The product UI is the FastAPI pages in `backend/app/static/`.

## Environment

| Variable | Required | Purpose |
|---|---|---|
| `SMTP_HOST` / `SMTP_FROM_EMAIL` / `SMTP_PASSWORD` | To send mail | Visitor reports and (if enabled) outbound |
| `SMTP_PORT` / `SMTP_USE_TLS` | No | Default `587` + TLS |
| `EMAIL_SENDING_ENABLED` / `OUTBOUND_SEND_ENABLED` | Keep `false` until SMTP works | Cold emails to public contacts |
| `ADMIN_PIN` | For `/admin` | Unlock the hunt dashboard |
| `BOOKING_URL` | For the call CTA | Calendly event URL, e.g. `https://calendly.com/lucianamitchell19/northline-business-automation` |
| `CONTACT_EMAIL` | No | Fallback only if Calendly is not set |
| `OPENAI_API_KEY` | For AI drafts | Admin ICP/outreach; visitor search does not need it |
| `SEARCH_PROVIDER` | No | `duckduckgo` (free), `tavily`, `serper`, or `brave` |
| `TAVILY_API_KEY` / `SERPER_API_KEY` / `BRAVE_API_KEY` | If you switch provider | Search APIs |

Never commit `.env`. Copy `.env.example` only.

## Layout

Python modules: `backend/app/modules/`. Search providers: `backend/app/providers/`. SQLite (`backend/data/`, gitignored) stores runs, companies, contacts, opportunities, outreach, inquiries, and logs.

## Known limitations

- Public HTML only. No login, CAPTCHA, paywall, or ToS bypass.
- Similar companies are filtered to operating sites; thin or blocked pages may be skipped.
- Decision-maker emails are often missing on the admin hunt; marked **CONTACT NOT VERIFIED**. Never fabricated.
- If SMTP is empty, reports still show on the page and can be downloaded. The public UI leads with download rather than email.

## Compliance

Respect robots.txt, site terms, API limits, privacy law, and email rules. This tool drafts research from public pages for a human to send.

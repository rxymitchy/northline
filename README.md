# Northline

**See what's still manual.**

**Live app:** [https://northline-8j55.onrender.com](https://northline-8j55.onrender.com)  
Repo: [github.com/rxymitchy/northline](https://github.com/rxymitchy/northline)

Northline looks at how a business takes work in — website, social profile, spreadsheet, or a short description — and says what still depends on a person. It is not a generic lead scraper.

Paste how you work, get a snapshot, download the full report, optionally **schedule a 30-minute call** on Calendly, then optionally see **real companies** in the same industry (not blogs or roundups). Those companies are included when you download the report again.

A PIN-locked **admin** hunt still finds other businesses with public automation gaps and drafts outreach to **public** emails only. Never invented contacts.

**Contributions are welcome.** Open an issue or a pull request. See [CONTRIBUTING.md](CONTRIBUTING.md). Licensed under [MIT](LICENSE).

## Live site

Anyone can use **https://northline-8j55.onrender.com** without your computer being on. It is hosted on **Render** (free web service), not Vercel.

The first visit after idle can take about a minute (the free instance sleeps). The URL stays the same. SQLite on free Render can reset if the instance restarts, so saved leads are not a durable store.

## What visitors get

1. **Choose one:** website, social, a file, or a short note.
2. Add name and email, then **See the diagnosis**.
3. Northline reads what you sent **and** a short public web search for the company, in parallel, usually in **10–20 seconds**.
4. Snapshot: overall manual dependency, which processes still wait on a person, what to automate first, suggested workflow.
5. **Download the full report**. **Schedule a 30-minute call** opens [Calendly](https://calendly.com/lucianamitchell19/northline-business-automation) with name and email filled in.
6. **See companies in this industry** — operating businesses, not listicles. Download the report again so they are in the file.

Visitor diagnosis stays heuristic: no OpenAI, no invented emails, no login/CAPTCHA bypass.

## Admin hunt

Lock icon on the public page → admin dashboard. Pipeline: search → drop publishers/listicles → public HTML research → gap detection → public contacts only → score → optional SMTP cold send when enabled.

## Local setup

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy ..\.env.example .env
py -3.13 -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

Open **http://127.0.0.1:8000**. Use Python 3.12+ (Render uses 3.12). On Windows, antivirus HTTPS scanning can block Python SSL; fetches go through a stack that usually still works.

The product UI is `backend/app/static/`. An older Next.js dashboard in `frontend/` talks to the same API.

## Deploy

Hosted on Render from the `master` branch (`render.yaml`). **Do not deploy this app on Vercel** — diagnosis is a long-running Python process, not a short serverless function.

To redeploy: push to `master`, or use **Manual Deploy** on [the Render service](https://dashboard.render.com). The public URL is **https://northline-8j55.onrender.com**.

Set `ADMIN_PIN` and `BOOKING_URL` in the Render dashboard if you change them. Visitor diagnosis does not need OpenAI.

## Environment

| Variable | Required | Purpose |
|---|---|---|
| `SMTP_HOST` / `SMTP_FROM_EMAIL` / `SMTP_PASSWORD` | To send mail | Visitor reports and (if enabled) outbound |
| `SMTP_PORT` / `SMTP_USE_TLS` | No | Default `587` + TLS |
| `EMAIL_SENDING_ENABLED` / `OUTBOUND_SEND_ENABLED` | Keep `false` until SMTP works | Cold emails to public contacts |
| `ADMIN_PIN` | For `/admin` | Unlock the hunt dashboard |
| `BOOKING_URL` | For the call CTA | Calendly event, default Northline 30-minute call |
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
- If SMTP is empty, reports still show on the page and can be downloaded.
- Free Render sleeps when idle; first request after that is slow. Disk is ephemeral.

## Compliance

Respect robots.txt, site terms, API limits, privacy law, and email rules. This tool drafts research from public pages for a human to send.

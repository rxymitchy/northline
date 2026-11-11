# Northline

**See what's still manual.**

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
![Python 3.12+](https://img.shields.io/badge/python-3.12%2B-blue.svg)
![FastAPI](https://img.shields.io/badge/built%20with-FastAPI-009688.svg)

Northline looks at how work reaches you (a website, a social profile, a spreadsheet, or a short note) and points out the steps that still wait on a person. You get a short report that quotes your own words, gives one clear first step, and comes as a PDF you can keep.

**Try it:** [northline-manual.vercel.app](https://northline-manual.vercel.app)

## Contents

- [Features](#features)
- [How it works](#how-it-works)
- [Quick start](#quick-start)
- [Configuration](#configuration)
- [Running tests](#running-tests)
- [Deployment](#deployment)
- [Contributing](#contributing)
- [Security](#security)
- [License](#license)

## Features

- **Four ways in:** a website URL, a social profile, an uploaded file, or a plain description.
- **Grounded findings:** each finding is tied to a quote from what you gave it, so nothing is made up.
- **One next step:** a single, concrete thing to try first, written in plain words.
- **PDF export:** download the report and keep it.
- **Respectful by design:** it reads only what you provide and what is already public. It does not get past logins or CAPTCHAs, and it does not invent contact details.

## How it works

1. Pick a source: website, social, file, or description.
2. Add the link or note, plus your name and email.
3. Wait about 10 to 60 seconds while it reads and analyses.
4. Read the report and download the PDF.

The hosted version gives you a few free reports per email. After that, more reports are paid in Bitcoin over Lightning. If you host it yourself, you set the rules.

## Quick start

You need **Python 3.12+** and an **OpenAI API key**.

```bash
git clone https://github.com/rxymitchy/northline.git
cd northline/backend

python -m venv .venv
# Windows: .\.venv\Scripts\Activate.ps1
# macOS/Linux: source .venv/bin/activate

pip install -r requirements.txt
cp ../.env.example .env        # Windows: copy ..\.env.example .env
# open .env and set OPENAI_API_KEY

uvicorn app.main:app --reload
```

Then open [http://127.0.0.1:8000](http://127.0.0.1:8000).

With Docker instead:

```bash
docker build -t northline .
docker run --env-file backend/.env -p 8000:8000 northline
```

## Configuration

All settings come from environment variables (or `backend/.env`). [`.env.example`](.env.example) lists every option. The main ones:

| Variable | Required | What it does |
| --- | --- | --- |
| `OPENAI_API_KEY` | Yes | Key for the language model. |
| `OPENAI_MODEL` | No | Model name. Defaults to `gpt-4o-mini`. |
| `DATABASE_URL` | In production | SQLAlchemy URL. Defaults to a local SQLite file. Use Postgres anywhere the disk is not kept between restarts. |
| `ADMIN_PIN` | Yes | Secret for the operator pages. Always set your own, strong value. |
| `SEARCH_PROVIDER` | No | `duckduckgo` (free, no key), `tavily`, `serper`, or `brave`. |
| `SMTP_*` | No | Mail settings for sending reports by email. |
| `LIGHTNING_ADDRESS` | No | Enables paid reports and tips. Used only on the server. |

Never commit your `.env` file.

## Running tests

From `backend/`:

```bash
python -m unittest discover
```

## Deployment

Northline is a single FastAPI app, so it runs anywhere Python or Docker runs.

**Vercel:** import the repo, set **Root Directory** to `backend`, add a Postgres `DATABASE_URL`, and add your other environment variables. `backend/vercel.json` already sends every request to the app. Reports run inside the request while the page checks progress, because Vercel stops background work once a response is sent.

**Docker hosts (Railway, Fly.io, a VPS, and so on):** use the included `Dockerfile`. The health check lives at `/api/health`.

## Contributing

Contributions are welcome: bug reports, fixes, and small improvements. Please read [CONTRIBUTING.md](CONTRIBUTING.md) before you open a pull request.

We will not merge features that invent contacts, get around logins or CAPTCHAs, or send spam.

## Security

If you find a security issue, please **do not open a public issue**. Report it privately through GitHub's [security advisories](https://github.com/rxymitchy/northline/security/advisories/new) instead.

## License

Released under the [MIT License](LICENSE). © 2026 Northline.

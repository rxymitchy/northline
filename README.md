# Northline

**See what's still manual.**

**Use it:** [https://northline-8j55.onrender.com](https://northline-8j55.onrender.com)

Northline looks at how work comes in — a website, a social profile, a spreadsheet, or a short note — and shows what still waits on a person. You get a snapshot, then a PDF you can keep.

If it helped, you can tip us. We take Bitcoin over Lightning.

Northline is **open source** under the [MIT License](LICENSE). Issues and pull requests are welcome.

## How it works

1. Pick website, social, a file, or a short description.
2. Fill every field, including your name and email.
3. Wait about 10–20 seconds.
4. Download the PDF. Tip if you want to.

It only uses what you send and what is already public. It does not invent emails, skip logins, or need your computer to stay on. The live app is on Render; the first visit after idle can take about a minute. Names and emails from the form are stored in a database that survives restarts.

## Run locally

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy ..\.env.example .env
py -3.13 -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

Open [http://127.0.0.1:8000](http://127.0.0.1:8000). Python 3.12+.

## Deploy on Vercel

1. Import the repo in Vercel and set **Root Directory** to `backend`. `backend/vercel.json` sends every request to FastAPI and allows 300 seconds per request.
2. Add a Postgres database (Neon from the Vercel Marketplace works) and set `DATABASE_URL`. The app will not start on Vercel without it, because Vercel's disk does not keep files.
3. Add the other secrets from `.env.example` (`OPENAI_API_KEY`, `ADMIN_PIN`, SMTP settings, `LIGHTNING_ADDRESS`, and so on).
4. To bring over existing data, run this once from `backend` (the target must be empty):

   ```powershell
   py -3.13 scripts/copy_db.py "<old DATABASE_URL>" "<new DATABASE_URL>"
   ```

On Vercel each diagnosis runs inside a request (`POST /api/runs/{id}/start`) while the page polls for progress, because Vercel stops background work once a response is sent.

## License

[MIT](LICENSE) — copyright Northline, 2026. See [CONTRIBUTING.md](CONTRIBUTING.md) if you want to help.

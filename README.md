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

## License

[MIT](LICENSE) — copyright Northline, 2026. See [CONTRIBUTING.md](CONTRIBUTING.md) if you want to help.

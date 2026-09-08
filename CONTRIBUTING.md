# Contributing

This project is **open source**. Fixes, small improvements, and honest bug reports are welcome.

## How to help

1. Fork the repo and create a branch.
2. Keep changes focused (one problem per pull request).
3. Do not commit `.env`, API keys, or the SQLite database.
4. Open a pull request describing **what** you changed and **why**.

You do not need to ask permission to fix something that is clearly broken (fetch failures, scoring bugs, article-site false positives, missing public emails that were actually on the page, docs, tests).

## Ideas that are especially useful

- Better company-site vs article/listicle detection
- Stronger public decision-maker email/phone extraction (never generate addresses)
- Extra search providers behind the existing provider interface
- Tests for scoring, page-type filters, and CSV export
- UI accessibility and clearer “why this score” copy

## Rules we will not merge around

- Auto-sending email or WhatsApp spam
- Inventing emails, phone numbers, or operational problems
- Bypassing logins, CAPTCHAs, paywalls, or access controls
- Scraping private inboxes or logged-in social networks

Be kind in reviews. New contributors are welcome.

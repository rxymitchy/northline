"""Turn public signals into a visitor diagnosis.

Every finding is tied to something we actually saw (a quote from their page or their own
words), explained in plain language, and paired with a concrete fix.
"""

import re

from app.modules.research import SIGNAL_PATTERNS
from app.plain import plain_all

# One entry per kind of manual work we can spot.
PLAYBOOK = {
    "whatsapp": {
        "process": "Replying to new enquiries",
        "human_work": "New enquiries go to WhatsApp, and someone has to read and answer each one by hand.",
        "why": "Every new customer waits until a person picks up the phone. Slow replies are one of the most common ways small businesses lose sales.",
        "fix": "Switch to WhatsApp Business and set a greeting, quick replies, and a short menu so people get an answer straight away.",
        "title": "Answer WhatsApp enquiries straight away",
        "steps": [
            "Install WhatsApp Business and add a greeting and an away message.",
            "Save quick replies for the questions you get most, like prices, location, and opening hours.",
            "Log each new chat in one list so you can see who still needs an answer.",
        ],
    },
    "booking": {
        "process": "Booking",
        "human_work": "Customers have to call to book. There is no online calendar they can use themselves.",
        "why": "Calls that come in after hours or at busy times get missed, and many of those people book with someone else.",
        "fix": "Add an online booking link (Calendly or Google Calendar booking pages both work) and send reminders automatically.",
        "title": "Let customers book online",
        "steps": [
            "Set up a booking page with your real open slots.",
            "Put the link on your site, your social profiles, and your WhatsApp greeting.",
            "Turn on automatic reminders the day before to cut no shows.",
        ],
    },
    "form": {
        "process": "Sorting enquiries",
        "human_work": "Messages from the contact form most likely land in one inbox for someone to read and sort.",
        "why": "Leads get buried in email, and nobody can tell at a glance who has been answered and who has not.",
        "fix": "Send every form entry into one shared list with a status and an owner, and send an instant reply so people know you got it.",
        "title": "Put every enquiry in one list",
        "steps": [
            "Connect your form to a shared sheet or a simple CRM so each message becomes a row.",
            "Send an automatic reply that says when they will hear back.",
            "Give each enquiry an owner and a status: new, replied, won, or lost.",
        ],
    },
    "followup": {
        "process": "Following up",
        "human_work": "Your copy promises that the team will call or get back to people, so someone has to remember to do it.",
        "why": "Follow up that depends on memory is the first thing to slip when the week gets busy.",
        "human_work_own": "You follow up by hand, so it only happens if someone remembers.",
        "fix": "Set automatic reminders so every enquiry gets a reply within a set time, and a nudge if it is still open after two days.",
        "title": "Make follow up automatic",
        "steps": [
            "Decide how fast every enquiry should get a reply, for example within 2 hours.",
            "Set a reminder that flags any enquiry still waiting past that time.",
            "Send a friendly automatic check in if a customer goes quiet for two days.",
        ],
    },
    "quote": {
        "process": "Quotes",
        "human_work": "Quotes look like they are written by hand for each request.",
        "why": "Customers wait for a price, and some move on before it arrives.",
        "human_work_own": "You write each quote by hand.",
        "fix": "Make a quote template with your standard prices, or a short form that gives a starting price right away.",
        "title": "Send quotes faster",
        "steps": [
            "List your most common jobs and a starting price for each.",
            "Build a quote template you can fill in within a few minutes.",
            "Add a short form that asks the questions you always need answered before quoting.",
        ],
    },
    "sheet": {
        "process": "Keeping records",
        "human_work": "Work is tracked in a spreadsheet or file that someone updates by hand.",
        "why": "The sheet is only right if someone remembers to update it, and copying details in by hand leads to mistakes.",
        "fix": "Have new enquiries added to the sheet automatically, with columns for status, owner, and next step.",
        "title": "Stop typing enquiries into the spreadsheet",
        "steps": [
            "Connect your form or WhatsApp so new enquiries are added as rows on their own.",
            "Add columns for status, owner, and next step, and keep them up to date.",
            "Move to a simple CRM once the sheet has more than a few hundred rows.",
        ],
    },
    "social": {
        "process": "Replying to messages",
        "human_work": "Interest comes in through DMs and comments, which someone has to read and answer one by one.",
        "why": "Messages get buried as the feed moves on, and there is no list of who asked what.",
        "human_work_own": "Leads come in through DMs, and someone has to read and answer each one.",
        "fix": "Put a link in your bio to a short form or a WhatsApp chat so every enquiry is saved in one place.",
        "title": "Capture every DM in one place",
        "steps": [
            "Add a link in your bio to a short enquiry form or WhatsApp chat.",
            "Set saved replies for the questions you get most in DMs.",
            "Keep one list of everyone who asked, so nobody is forgotten.",
        ],
    },
    "application": {
        "process": "Applications",
        "human_work": "People apply or send documents, and someone checks each one by hand.",
        "why": "Missing documents mean back and forth emails, and applicants lose interest while they wait.",
        "fix": "Use one online form that collects every document at once and tells the applicant what is still missing.",
        "title": "Collect applications online",
        "steps": [
            "Build one form that asks for every document you need.",
            "Send an automatic message confirming what was received.",
            "Track each application with a clear status so nothing sits unchecked.",
        ],
    },
}

# Which research signal patterns prove each finding (used to quote their own words).
PROOF_KEYS = {
    "whatsapp": ["whatsapp_channel"],
    "booking": ["call_to_book"],
    "form": ["enquiry_form"],
    "followup": ["manual_followup_language"],
    "quote": ["quote_request"],
    "sheet": [],
    "social": ["dm_cta", "comments_cta", "link_in_bio"],
    "application": ["application_process"],
}
EXTRA_PROOF = {
    # Only phrases that are really about following up; "by hand" alone could be about anything.
    "followup": [r"follow[ -]?up", r"get back to you", r"we will call", r"call (them|people|customers) back"],
    "sheet": [r"spreadsheet", r"excel", r"google sheets?", r"\bcsv\b"],
    "whatsapp": [r"whatsapp"],
    "social": [r"\bdms?\b", r"instagram", r"facebook", r"tiktok"],
    "quote": [r"\bquot(e|es|ing)\b"],
}


def build_diagnosis(source: str, research: dict, gap: dict, channel: dict | None = None) -> dict:
    signals = research.get("signals") or {}
    raw = research.get("text") or ""
    text = raw.lower()
    processes = _processes(source, signals, text, raw)
    overall = _overall(processes, gap)
    primary = next((p for p in processes if p["priority"] == "HIGH"), None) or (processes[0] if processes else None)
    # Their own words are the strongest evidence; fall back to plain observations.
    facts = _uniq([p["proof"] for p in processes if p.get("proof")]) or _uniq(
        [str(f) for f in (gap.get("facts") or []) if f and "mention you" not in str(f)]
    )
    out = {
        "overall": overall,
        "overall_label": {"HIGH": "High", "MEDIUM": "Medium", "LOW": "Low"}[overall],
        "uncertainty": overall == "LOW" and not processes,
        "summary": _summary(source, overall, primary, processes, research),
        "processes": [{k: v for k, v in p.items() if k not in ("key", "title", "steps")} for p in processes],
        "automate_first": _automate_first(primary, facts),
        "workflow": _workflow(source, processes),
        "facts": facts,
        "caveat": (
            "We only used what you shared, your public pages, and mentions of you online. "
            "We cannot see your inbox, your tools, or how busy your team is, so treat this as a starting point."
        ),
    }
    return plain_all(out)


def _row(key: str, priority: str, proof: str = "", own_words: bool = False) -> dict:
    item = PLAYBOOK[key]
    return {
        "key": key,
        "process": item["process"],
        "human_work": (item.get("human_work_own") if own_words else None) or item["human_work"],
        "priority": priority,
        "why": item["why"],
        "fix": item["fix"],
        "proof": proof,
        "title": item["title"],
        "steps": item["steps"],
    }


def _processes(source: str, signals: dict, text: str, raw: str) -> list[dict]:
    own_words = source in ("describe", "csv")
    found: list[tuple[str, str]] = []
    has_whatsapp = signals.get("whatsapp_channel") or "whatsapp" in text
    if has_whatsapp and not signals.get("chatbot"):
        found.append(("whatsapp", "HIGH"))
    if signals.get("call_to_book") and not signals.get("online_booking"):
        found.append(("booking", "HIGH"))
    if source == "csv" or any(w in text for w in ("excel", "spreadsheet", "google sheet")):
        found.append(("sheet", "HIGH"))
    if (
        source == "social"
        or signals.get("dm_cta")
        or signals.get("comments_cta")
        or (own_words and re.search(r"\bdms?\b|instagram|facebook|tiktok", text))
    ):
        found.append(("social", "HIGH"))
    if signals.get("enquiry_form") and not signals.get("crm_mention") and not signals.get("chatbot"):
        found.append(("form", "HIGH" if source in ("website", "describe") else "MEDIUM"))
    if signals.get("manual_followup_language") or any(
        w in text for w in ("follow up", "follow-up", "get back to you", "we will call", "manually", "by hand")
    ):
        found.append(("followup", "MEDIUM"))
    wants_quote = signals.get("quote_request") or (own_words and re.search(r"\bquot(e|es|ing)\b", text))
    if wants_quote and not signals.get("ecommerce"):
        found.append(("quote", "MEDIUM"))
    if signals.get("application_process") and not signals.get("customer_portal"):
        found.append(("application", "MEDIUM"))

    rows = []
    seen = set()
    used: set[str] = set()
    for key, priority in found:
        if key in seen:
            continue
        seen.add(key)
        proof = _proof(key, raw, own_words, used)
        if proof:
            used.add(proof)
        rows.append(_row(key, priority, proof, own_words))
    # Findings with a real quote are stronger; show those first within each priority.
    rows.sort(key=lambda r: (r["priority"] != "HIGH", not r["proof"]))
    return rows[:5]


def _proof(key: str, raw: str, own_words: bool, used: set[str] | None = None) -> str:
    if not raw:
        return ""
    patterns: list[str] = []
    for sig in PROOF_KEYS.get(key, []):
        patterns += SIGNAL_PATTERNS.get(sig, [])
    patterns += EXTRA_PROOF.get(key, [])
    fallback = ""
    for pat in patterns:
        m = re.search(pat, raw, re.I)
        if not m:
            continue
        snippet = _sentence_around(raw, m.start(), m.end())
        if len(snippet) < 6:
            continue
        lead = "You wrote" if own_words else "Your page says"
        quote = f'{lead}: "{snippet}"'
        if used and quote in used:
            # Prefer a fresh sentence, but a correct repeat beats an unrelated quote.
            fallback = fallback or quote
            continue
        return quote
    return fallback


# A sentence ends at . ! ? followed by space or end (so "wa.me" or "3.5" do not split), or a newline.
_BREAK = re.compile(r"[.!?](?=\s|$)|\n")


def _sentence_around(raw: str, start: int, end: int, limit: int = 140) -> str:
    left = -1
    for m in _BREAK.finditer(raw, 0, start):
        left = m.start()
    nxt = _BREAK.search(raw, end)
    right = nxt.start() if nxt else len(raw)
    s = re.sub(r"\s+", " ", raw[left + 1 : right]).strip(" \"'")
    if len(s) > limit:
        mid = (start - left - 1)
        lo = max(0, mid - limit // 2)
        s = s[lo : lo + limit].strip()
        s = ("…" if lo > 0 else "") + s + "…"
    return s


def _overall(processes: list[dict], gap: dict) -> str:
    if any(p["priority"] == "HIGH" for p in processes):
        return "HIGH"
    if processes or gap.get("exists"):
        return "MEDIUM"
    return "LOW"


def _summary(source: str, overall: str, primary: dict | None, processes: list[dict], research: dict) -> str:
    pages = len(research.get("pages") or [])
    mentions = len(research.get("public_mentions") or [])
    read = ""
    if source in ("website", "social") and (pages or mentions):
        parts = []
        if pages:
            parts.append(f"{pages} page{'s' if pages != 1 else ''} of yours")
        if mentions:
            parts.append(f"{mentions} other place{'s that mention' if mentions != 1 else ' that mentions'} you")
        read = " We read " + " and ".join(parts) + "."
    if overall == "LOW" or not primary:
        return (
            "We did not find clear signs of work being done by hand in what we could see. "
            "That does not mean nothing can be improved, only that it was not visible from what you shared." + read
        )
    count = len(processes)
    if count > 1:
        lead = f"We found {count} places where work still depends on someone doing it by hand. The biggest one: "
    else:
        lead = "The main thing we found: "
    return f"{lead}{primary['human_work'][0].lower()}{primary['human_work'][1:]} {primary['why']}{read}"


def _automate_first(primary: dict | None, facts: list[str]) -> dict:
    if not primary:
        return {
            "title": "Start with how new enquiries reach you",
            "reason": (
                "We could not see one clear bottleneck from what you shared. "
                "A good first check is how fast you reply to a new enquiry and whether any get missed. "
                "That is usually where small businesses lose the most time and sales."
            ),
            "steps": [
                "Count how many enquiries came in last week and how long each took to get a reply.",
                "Write down every place enquiries arrive: phone, email, WhatsApp, social, walk ins.",
                "Pick the busiest one and set up an instant reply there first.",
            ],
            "evidence": facts[:3],
        }
    return {
        "title": primary["title"],
        "reason": f"{primary['why']} {primary['fix']}",
        "steps": primary["steps"],
        "evidence": facts[:4],
        "human_work": primary["human_work"],
    }


def _workflow(source: str, processes: list[dict]) -> list[str]:
    keys = {p["key"] for p in processes}
    steps = ["New enquiry", "Instant reply"]
    steps.append("Saved in one list")
    if "booking" in keys:
        steps.append("Customer books a slot online")
    if "quote" in keys:
        steps.append("Quote sent from a template")
    if "application" in keys:
        steps.append("Documents checked")
    steps.append("Reminder if nobody has replied")
    steps.append("A person steps in when needed")
    return steps


def _uniq(items: list[str]) -> list[str]:
    seen = set()
    out = []
    for item in items:
        k = item.strip().lower()
        if k and k not in seen:
            seen.add(k)
            out.append(item)
    return out

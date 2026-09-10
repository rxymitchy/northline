from urllib.parse import urlparse


SOCIAL_HOSTS = {
    "instagram.com": "Instagram",
    "facebook.com": "Facebook",
    "fb.com": "Facebook",
    "tiktok.com": "TikTok",
    "linkedin.com": "LinkedIn",
    "x.com": "X",
    "twitter.com": "X",
    "youtube.com": "YouTube",
    "wa.me": "WhatsApp",
    "whatsapp.com": "WhatsApp",
}


def channel_notes(source: str, url: str, research: dict, gap: dict) -> dict:
    text = (research.get("text") or "").lower()
    signals = research.get("signals") or {}
    host = urlparse(url or research.get("website") or "").netloc.lower().replace("www.", "")
    network = _network(host)
    gaps = gap.get("gaps") or []

    if source == "social":
        return _social(network, text, signals, gaps)
    if source == "website":
        return _website(text, signals, gaps)
    if source == "csv":
        return _csv(text, gaps)
    return _describe(text, gaps)


def _social(network: str | None, text: str, signals: dict, gaps: list) -> dict:
    label = network or "this profile"
    art = "an" if label[0].lower() in "aeiou" else "a"
    state = f"We reviewed {art} {label} presence. People can find you there, but the next step still looks like a person reading messages."
    if "login" in text or "log in" in text:
        state += " A lot of the real conversation is behind the login, so public pages only show part of the work."
    missing = [
        "A capture step in the bio (form, WhatsApp, or booking) so interest does not die in DMs.",
        "A page you own (even one landing page) so the algorithm is not the only storefront.",
    ]
    others = {
        "Instagram": ["WhatsApp Business", "TikTok", "Google Business Profile", "a simple website"],
        "Facebook": ["WhatsApp Business", "Instagram", "Google Business Profile", "a booking link"],
        "TikTok": ["Instagram", "WhatsApp Business", "YouTube Shorts", "a landing page in the bio"],
        "LinkedIn": ["a company website", "WhatsApp or email capture", "Google Business Profile"],
        "YouTube": ["a website with a clear CTA", "WhatsApp Business", "LinkedIn"],
        "WhatsApp": ["a website or Google Business Profile", "Instagram", "a shared inbox / CRM"],
        "X": ["LinkedIn", "a website", "WhatsApp Business"],
    }
    explore = [
        f"Also try {', '.join(others.get(network or '', ['WhatsApp Business', 'Instagram', 'Google Business Profile', 'a one-page site']))}."
    ]
    if network != "WhatsApp":
        explore.append("WhatsApp Business with a menu beats hoping someone opens the app.")
    if network != "LinkedIn":
        explore.append("LinkedIn if you sell to other businesses, not only consumers.")
    missing.extend(gaps[:2])
    return _pack(state, missing, explore)


def _website(text: str, signals: dict, gaps: list) -> dict:
    state = "We reviewed the website as the public front door."
    if signals.get("whatsapp_channel") and not signals.get("chatbot"):
        state = "The site sends people to WhatsApp. That works until volume grows and nobody replies in time."
    elif signals.get("call_to_book") and not signals.get("online_booking"):
        state = "The site still says call to book. That is extra work and easy to miss after hours."
    elif signals.get("enquiry_form") and not signals.get("crm_mention"):
        state = "There is a form, but nothing public says those leads are tracked. They likely land in one inbox."
    missing = []
    explore = []
    if not signals.get("online_booking") and not signals.get("ecommerce"):
        missing.append("Self-serve booking, quoting, or checkout so staff are not the only path.")
        explore.append("Calendly, a simple booking page, or checkout — depending on what you sell.")
    if not _has_social(text):
        missing.append("Links to where you actually talk to customers (Instagram, Facebook, TikTok, LinkedIn).")
        explore.append("Pick one social app for proof of work, then point it back to this site.")
    if not signals.get("whatsapp_channel"):
        explore.append("WhatsApp Business as a capture channel, with follow-up that is not typed by hand.")
    explore.append("Google Business Profile if people search you on Maps.")
    missing.extend(gaps[:2])
    return _pack(state, missing, explore)


def _csv(text: str, gaps: list) -> dict:
    cols = text.split("\n")[0] if text else ""
    state = "We read the file. Work is sitting in rows, which usually means a person is moving status by hand."
    if any(w in cols.lower() for w in ("lead", "customer", "name", "phone", "email")):
        state = "This looks like a lead or customer list. The file is the system — until someone forgets to update a row."
    missing = [
        "A live list with owner, status, and next action — not another export.",
        "A way new enquiries write themselves into that list (form, WhatsApp, or email).",
    ]
    explore = [
        "Google Sheets or Airtable if you are not ready for a CRM; HubSpot or a simple CRM when the file keeps breaking.",
        "A website or WhatsApp form that appends a row instead of copy-paste.",
        "Google Business Profile and one social channel so leads do not only arrive in that spreadsheet.",
    ]
    missing.extend(gaps[:2])
    return _pack(state, missing, explore)


def _describe(text: str, gaps: list) -> dict:
    state = "We read how you said work moves. It still depends on someone remembering to follow up."
    missing = []
    explore = []
    if "whatsapp" in text:
        state = "WhatsApp is the front door. Unread chats and no log of promises is the typical leak."
        missing.append("A log outside the phone: who asked, what they wanted, who owns the reply.")
        explore.append("WhatsApp Business menus, then a sheet or CRM the chat writes into.")
    if "excel" in text or "spreadsheet" in text or "google sheet" in text:
        missing.append("A step that does not start with copy-paste into a sheet.")
        explore.append("A form or WhatsApp capture that lands in the sheet automatically.")
    if "email" in text:
        explore.append("A shared inbox so enquiries are not stuck on one person's Gmail.")
    if "call" in text or "phone" in text:
        explore.append("A booking link so fewer people have to wait for a call back.")
    explore.append("A simple website or Google Business Profile if customers cannot find a written offer.")
    explore.append("Instagram, Facebook, or TikTok if the story of the work never leaves the inbox.")
    missing.extend(gaps[:2])
    if not missing:
        missing.append("One written path (form, booking, or WhatsApp menu) so the process is not only in someone's head.")
    return _pack(state, missing, explore)


def _network(host: str) -> str | None:
    for key, label in SOCIAL_HOSTS.items():
        if host == key or host.endswith("." + key):
            return label
    return None


def _has_social(text: str) -> bool:
    return any(n in text for n in ("instagram", "facebook", "tiktok", "linkedin", "youtube"))


def _uniq(items: list[str]) -> list[str]:
    seen = set()
    out = []
    for item in items:
        key = item.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(item)
    return out[:8]


def _pack(state: str, missing: list[str], explore: list[str]) -> dict:
    return {
        "state": state,
        "missing": _uniq(missing),
        "explore": _uniq(explore),
    }

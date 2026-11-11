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
    label = network or "social media"
    state = f"People can find you on {label}, but turning that interest into a customer still depends on someone reading and answering messages."
    if "login" in text or "log in" in text:
        state += " Much of the profile is behind a login, so we could only see part of it."
    missing = [
        "A link in your bio to a short form or WhatsApp chat, so interest does not get lost in DMs.",
        "A page you own, even a single landing page, so you are not relying only on the app to show your work.",
    ]
    others = {
        "Instagram": ["WhatsApp Business", "TikTok", "a Google Business Profile", "a simple website"],
        "Facebook": ["WhatsApp Business", "Instagram", "a Google Business Profile", "a booking link"],
        "TikTok": ["Instagram", "WhatsApp Business", "YouTube Shorts", "a landing page in your bio"],
        "LinkedIn": ["a company website", "an email signup", "a Google Business Profile"],
        "YouTube": ["a website with one clear next step", "WhatsApp Business", "LinkedIn"],
        "WhatsApp": ["a website or Google Business Profile", "Instagram", "a shared inbox"],
        "X": ["LinkedIn", "a website", "WhatsApp Business"],
    }
    picks = others.get(network or "", ["WhatsApp Business", "Instagram", "a Google Business Profile", "a simple website"])
    explore = [f"Worth adding: {', '.join(picks[:-1])} and {picks[-1]}."]
    if network != "WhatsApp":
        explore.append("WhatsApp Business with a short menu, so people get an answer without waiting for you.")
    if network != "LinkedIn":
        explore.append("LinkedIn, if you sell to other businesses.")
    return _pack(state, missing, explore)


def _website(text: str, signals: dict, gaps: list) -> dict:
    state = "Your website is the first place many customers will check, so we looked at what happens after someone decides to get in touch."
    if signals.get("whatsapp_channel") and not signals.get("chatbot"):
        state = "Your site sends people to WhatsApp. That works well until messages pile up and replies slow down."
    elif signals.get("call_to_book") and not signals.get("online_booking"):
        state = "Your site asks people to call to book. Calls after hours or at busy times are easy to miss."
    elif signals.get("enquiry_form") and not signals.get("crm_mention"):
        state = "Your site has a contact form, but nothing shows how those messages are tracked. They most likely land in one inbox."
    missing = []
    explore = []
    if not signals.get("online_booking") and not signals.get("ecommerce"):
        missing.append("A way for customers to book, get a price, or pay without waiting for a person.")
        explore.append("A simple booking page or online checkout, depending on what you sell.")
    if not _has_social(text):
        missing.append("Links to where you talk to customers, such as Instagram, Facebook, TikTok, or LinkedIn.")
        explore.append("Pick one social app to show your work, and link it back to your site.")
    if not signals.get("whatsapp_channel"):
        explore.append("WhatsApp Business with automatic replies, so new enquiries get an answer straight away.")
    explore.append("A Google Business Profile, if people look for you on Google Maps.")
    return _pack(state, missing, explore)


def _csv(text: str, gaps: list) -> dict:
    cols = text.split("\n")[0] if text else ""
    state = "We read your file. Work kept in rows usually means someone updates each one by hand."
    if any(w in cols.lower() for w in ("lead", "customer", "name", "phone", "email")):
        state = "This looks like a list of leads or customers. It is only accurate if someone remembers to update every row."
    missing = [
        "One live list with an owner, a status, and a next step for each row, instead of new exports.",
        "A way for new enquiries to add themselves to the list from your form, WhatsApp, or email.",
    ]
    explore = [
        "Google Sheets or Airtable for now, and a simple CRM such as HubSpot once the sheet gets hard to manage.",
        "A website or WhatsApp form that adds a new row on its own, so nobody has to copy details across.",
    ]
    return _pack(state, missing, explore)


def _describe(text: str, gaps: list) -> dict:
    state = "From what you told us, a lot still depends on someone remembering to reply and follow up."
    missing = []
    explore = []
    if "whatsapp" in text:
        state = "WhatsApp is how most customers reach you. Unread chats and promises nobody wrote down are where things slip."
        missing.append("A record outside your phone of who asked, what they wanted, and who is replying.")
        explore.append("WhatsApp Business quick replies, with each new chat saved to a sheet or CRM.")
    if "excel" in text or "spreadsheet" in text or "google sheet" in text:
        missing.append("A way to fill the sheet without copying and pasting.")
        explore.append("A form or WhatsApp chat that adds each enquiry to the sheet automatically.")
    if "email" in text:
        explore.append("A shared inbox, so enquiries are not stuck in one person's email.")
    if "call" in text or "phone" in text:
        explore.append("An online booking link, so fewer people have to wait for a call back.")
    if not missing:
        missing.append("One clear path for new enquiries, like a form, a booking link, or a WhatsApp menu, so the process is not only in someone's head.")
    explore.append("A simple website or Google Business Profile, if customers cannot easily find what you offer.")
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

"""Detect a literal automation gap from public page signals. No invented problems."""

from __future__ import annotations

AGENCY_SERVICE = (
    "digital marketing",
    "social media",
    "seo",
    "web design",
    "web development",
    "branding",
    "advertising",
    "content marketing",
    "ppc",
    "google ads",
)

ALREADY_AUTOMATED = (
    "whatsapp automation",
    "whatsapp chatbot",
    "ai chatbot",
    "crm integration",
    "odoo",
    "custom software",
    "ai agent",
    "workflow automation",
    "marketing automation platform",
)


def detect_automation_gap(research: dict, track: str | None) -> dict:
    signals = research.get("signals") or {}
    text = (research.get("text") or "").lower()
    gaps: list[str] = []
    facts: list[str] = []

    if signals.get("whatsapp_channel") or research.get("whatsapps"):
        facts.append("Customers are asked to contact you on WhatsApp.")
        if not signals.get("chatbot"):
            gaps.append("WhatsApp is used for customers with no automatic replies, so someone answers every chat by hand.")
    if signals.get("call_to_book") and not signals.get("online_booking"):
        facts.append("Customers are told to call to book.")
        gaps.append("There is no online booking, so every booking needs a person on the phone.")
    if signals.get("quote_request") and not signals.get("ecommerce"):
        facts.append("Customers can ask for a quote.")
        gaps.append("Quotes seem to be written by hand for each request.")
    if signals.get("manual_followup_language"):
        facts.append("Your copy says the team will call or get back to people.")
        gaps.append("Follow up depends on a person remembering to call back.")
    if signals.get("enquiry_form") and not signals.get("crm_mention") and not signals.get("chatbot"):
        facts.append("There is a contact form, and nothing shows where those messages go next.")
        gaps.append("New enquiries most likely land in one inbox for someone to sort.")
    if signals.get("dm_cta") or signals.get("comments_cta"):
        facts.append("People are asked to DM or comment instead of using a form.")
        gaps.append("Someone has to read and answer every DM by hand.")
    if signals.get("link_in_bio"):
        facts.append("There is a link in bio page.")
    mentions = research.get("public_mentions") or []
    if mentions:
        facts.append(f"Found {len(mentions)} other places online that mention you.")
    if signals.get("online_booking") and signals.get("chatbot"):
        facts.append("Online booking and automatic chat replies are already in place.")

    if (track or "") == "agency_partner" or _looks_like_agency(text):
        if any(s in text for s in AGENCY_SERVICE):
            facts.append("You sell marketing, web, or branding services to clients.")
            if not any(s in text for s in ALREADY_AUTOMATED):
                gaps.append(
                    "Your services stop at marketing and web, so technical client work like WhatsApp, CRM, or AI setups may be going elsewhere."
                )
            else:
                gaps.append(
                    "You mention some technical or AI work. Bigger client builds may still need extra help."
                )

    exists = len(gaps) > 0
    strength = min(100, 20 * len(gaps) + (15 if signals.get("whatsapp_channel") else 0))
    if signals.get("online_booking") and signals.get("chatbot") and not gaps:
        strength = 10
        exists = False

    return {
        "exists": exists,
        "strength": strength,
        "gaps": gaps,
        "facts": facts,
        "summary": " ".join(gaps[:2]) if gaps else "No clear public automation gap on the pages fetched.",
    }


def _looks_like_agency(text: str) -> bool:
    return any(s in text for s in ("marketing agency", "digital agency", "web design agency", "advertising agency"))

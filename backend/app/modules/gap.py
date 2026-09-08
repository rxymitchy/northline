"""Detect a literal automation gap from public page signals — no invented problems."""

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
        facts.append("Public WhatsApp enquiry/contact channel on the site.")
        if not signals.get("chatbot"):
            gaps.append("WhatsApp is used as a customer channel with no visible chatbot — follow-up is likely manual.")
    if signals.get("call_to_book") and not signals.get("online_booking"):
        facts.append("Site tells customers to call to book.")
        gaps.append("No visible online booking — appointment/lead capture looks staff-dependent.")
    if signals.get("quote_request") and not signals.get("ecommerce"):
        facts.append("Quote/request process is on the site.")
        gaps.append("Quote requests appear form/WhatsApp based rather than a self-serve workflow.")
    if signals.get("manual_followup_language"):
        facts.append("Copy says the team will call or get back to the customer.")
        gaps.append("Follow-up is described as a person calling back — a classic automation gap.")
    if signals.get("enquiry_form") and not signals.get("crm_mention") and not signals.get("chatbot"):
        facts.append("Enquiry/contact form present; no CRM or chatbot mentioned.")
        gaps.append("Inbound enquiries likely land in email/WhatsApp with manual qualification.")
    if signals.get("online_booking") and signals.get("chatbot"):
        facts.append("Online booking and a chatbot are both visible — less of an ops gap.")

    if (track or "") == "agency_partner" or _looks_like_agency(text):
        if any(s in text for s in AGENCY_SERVICE):
            facts.append("Site sells marketing/web/branding-type services to clients.")
            if not any(s in text for s in ALREADY_AUTOMATED):
                gaps.append(
                    "Agency services stop at marketing/web — no public WhatsApp/CRM/AI/custom-backend offer, so client technical work is a likely overflow gap."
                )
            else:
                gaps.append(
                    "They mention some technical/AI work; still a possible overflow gap when client jobs need extra engineering."
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

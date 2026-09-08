import json

from app.llm import chat_json


SYSTEM = """Score 0-100 for a Kenya software engineer selling automation.

Primary question: is there a LITERAL automation gap on the public site?
If heuristic_gap.exists is true, lead_score MUST be at least 58 (MEDIUM), usually 65-82.
Do not reject a company that has WhatsApp-as-channel, call-to-book, quote-by-staff, or an agency without a tech stack.

If there is no gap, score below 40.

Weights still sum to 100 but pain_evidence should track the gap, not 'company exists'.

Return JSON: lead_score, priority, breakdown, why, recommend_contact.
"""


def score_prospect(run_id: int, company: dict, research: dict, opportunity: dict, contact: dict | None) -> dict:
    heuristic = _heuristic_score(research, opportunity, contact, company)
    user = json.dumps(
        {
            "company": company.get("name"),
            "track": opportunity.get("track") or company.get("track"),
            "heuristic_gap": opportunity.get("heuristic_gap"),
            "automation_gap": opportunity.get("automation_gap"),
            "signals": research.get("signals"),
            "has_whatsapp": bool(research.get("whatsapps")),
            "has_phone": bool(contact and contact.get("phone")),
            "has_email": bool(contact and contact.get("email")),
            "opportunity": {
                "qualify": opportunity.get("qualify"),
                "confidence": opportunity.get("confidence"),
                "observed_problem": opportunity.get("observed_problem"),
                "facts": opportunity.get("facts"),
            },
            "heuristic_hint": heuristic,
        }
    )
    try:
        data = json.loads(chat_json(run_id, SYSTEM, user, temperature=0.1))
    except Exception:
        data = heuristic
    score = int(data.get("lead_score") or heuristic["lead_score"])
    gap = opportunity.get("heuristic_gap") or {}
    if opportunity.get("qualify") and gap.get("exists"):
        score = max(score, heuristic["lead_score"], 58)
    if not gap.get("exists") and not opportunity.get("qualify"):
        score = min(score, 39)
    score = max(0, min(100, score))
    data["lead_score"] = score
    data["priority"] = _label(score)
    data["recommend_contact"] = score >= 40 and bool(opportunity.get("qualify"))
    data.setdefault("breakdown", heuristic["breakdown"])
    why = data.get("why") or heuristic["why"]
    if gap.get("summary"):
        why = f"Automation gap: {gap.get('summary')} {why}"
    data["why"] = why
    return data


def _label(score: int) -> str:
    if score >= 80:
        return "HIGH PRIORITY"
    if score >= 60:
        return "MEDIUM"
    if score >= 40:
        return "LOW"
    return "REJECT"


def _heuristic_score(research: dict, opportunity: dict, contact: dict | None, company: dict | None = None) -> dict:
    company = company or {}
    gap = opportunity.get("heuristic_gap") or {}
    track = opportunity.get("track") or company.get("track") or "operational_pain"
    signals = research.get("signals") or {}

    pain = 6
    if gap.get("exists"):
        pain = min(30, 14 + int((gap.get("strength") or 0) / 8) + 4 * min(3, len(gap.get("gaps") or [])))
    else:
        if signals.get("whatsapp_channel"):
            pain += 10
        if signals.get("call_to_book") or signals.get("quote_request") or signals.get("manual_followup_language"):
            pain += 8
        if signals.get("online_booking") and signals.get("chatbot"):
            pain = max(4, pain - 10)
    pain = max(0, min(30, pain))

    fit = 16 if opportunity.get("qualify") or gap.get("exists") else 4
    if opportunity.get("confidence") == "High":
        fit = min(20, fit + 4)
    value = 12 if gap.get("exists") else 4
    company_fit = 12 if company.get("named_target") else 10
    access = 4
    if contact and contact.get("email"):
        access += 3
    if contact and contact.get("phone"):
        access += 3
    access = min(10, access)
    personalization = 8 if (opportunity.get("facts") or gap.get("facts")) else 3
    total = pain + fit + value + company_fit + access + personalization
    if gap.get("exists"):
        total = max(total, 62)
    return {
        "lead_score": min(100, total),
        "priority": _label(total),
        "breakdown": {
            "pain_evidence": pain,
            "automation_fit": fit,
            "business_value": value,
            "company_fit": company_fit,
            "decision_maker_access": access,
            "personalization": personalization,
        },
        "why": (
            f"Scored from literal automation gap ({'yes' if gap.get('exists') else 'no'}). "
            f"{gap.get('summary') or ''} Track={track}."
        ),
        "recommend_contact": total >= 40 and bool(opportunity.get("qualify") or gap.get("exists")),
    }

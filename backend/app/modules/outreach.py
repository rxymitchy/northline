import json

from app.llm import chat_json


SYSTEM = """Write a short, human outbound email for a software engineer in Kenya named Alex.

Rules:
- Reference ONLY provided facts. Do not invent internal processes, staffing gaps, or emails.
- Curious, concise, not salesy. No "leverage AI to streamline operations".
- 70-130 words.
- Do not ask for a job.

If track is agency_partner:
The email is a partnership/overflow ask, not a cold automation pitch.
Must include the substance of:
1) Do you ever have clients who need technical work beyond what your current team handles?
2) I'd like to work with you on a project/contract basis when you need extra engineering capacity.
Tie it to a specific service they publicly sell (web, ecommerce, marketing, CRM mention, etc.).

If track is software_contract:
Approach as a contract/freelance engineer who can help ship similar work (integrations, WhatsApp, dashboards, agents) when they need extra capacity. Reference what they actually build. Do not claim they are hiring or understaffed.

If track is operational_pain:
Reference the observed messy public process (WhatsApp enquiries, booking, quotes). Ask how they handle volume. Do not pretend you know their internals.

Return JSON: { "subject": "...", "body": "...", "pitch_rationale": "..." }
"""


def write_outreach(run_id: int, company: dict, opportunity: dict, contact: dict) -> dict:
    track = opportunity.get("track") or company.get("track") or "operational_pain"
    user = json.dumps(
        {
            "company_name": company.get("name"),
            "website": company.get("website"),
            "track": track,
            "facts": opportunity.get("facts"),
            "observed_problem": opportunity.get("observed_problem"),
            "automation_opportunity": opportunity.get("automation_opportunity"),
            "recommended_offer": opportunity.get("recommended_offer"),
            "contact_name": contact.get("name"),
            "contact_role": contact.get("role"),
            "confidence": opportunity.get("confidence"),
            "seller_name": "Alex",
        }
    )
    try:
        data = json.loads(chat_json(run_id, SYSTEM, user, temperature=0.4))
    except Exception:
        data = _fallback(company, opportunity, track)
    body = (data.get("body") or "").strip()
    if "leverage AI" in body.lower() or "streamline operations" in body.lower():
        data["body"] = body.replace("leverage AI", "help").replace("streamline operations", "handle extra technical work")
    data.setdefault("subject", f"Quick question for {company.get('name')}")
    data.setdefault("pitch_rationale", f"Track={track}, tied to observed website evidence.")
    return data


def _fallback(company: dict, opportunity: dict, track: str) -> dict:
    name = company.get("name")
    obs = opportunity.get("observed_problem") or "your public services"
    if track == "agency_partner":
        return {
            "subject": f"Overflow engineering for {name} clients",
            "body": (
                f"Hi,\n\nI was looking at {name}'s site — {obs}.\n\n"
                "Do you ever have clients who need technical work beyond what your current team handles "
                "(CRM, WhatsApp automation, payments, dashboards, APIs, custom backend)?\n\n"
                "I'd be interested in working with you on a project/contract basis when you need extra engineering capacity — not looking for a job.\n\nAlex"
            ),
            "pitch_rationale": "Agency overflow ask anchored to their public services.",
        }
    if track == "software_contract":
        return {
            "subject": f"Contract engineering capacity — {name}",
            "body": (
                f"Hi,\n\nI noticed {name} {obs}. I do contract work on automations, integrations, WhatsApp/CRM flows, dashboards and custom backends.\n\n"
                "If you ever need extra engineering capacity on a project basis, I'd like to be someone you can call.\n\nAlex"
            ),
            "pitch_rationale": "Contract engineer ask based on what they publicly build.",
        }
    return {
        "subject": f"Quick question about {name}",
        "body": (
            f"Hi,\n\nI was looking at {name}'s site and noticed {obs}. "
            "I was curious how your team currently handles that when volume picks up.\n\nAlex"
        ),
        "pitch_rationale": "Operational pain ask from public evidence.",
    }

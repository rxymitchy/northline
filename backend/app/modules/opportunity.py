import json

from app.llm import chat_json
from app.modules.gap import detect_automation_gap
from app.modules.icp import SERVICES


SYSTEM = """You are a careful B2B research analyst for a software engineer in Kenya who sells automation.

Judge the LITERAL automation gap on the public website. Do not invent internals.

A real gap looks like:
- WhatsApp/phone as the enquiry channel with no chatbot
- "Call to book" / "we will get back to you" / request-a-quote with no self-serve workflow
- Enquiry form with no CRM/booking/chat
- Marketing/web agency that does not offer WhatsApp/CRM/API/backend/AI delivery (their clients will need that)

Qualify=true when that gap is visible in the excerpt OR heuristic_gap.exists is true.
Qualify=false only when the site looks already automated (booking + chatbot + portal) or is not a real company.

Never invent emails or staffing problems. Label facts vs inferences.

Return JSON:
{
  "qualify": true/false,
  "track": "agency_partner|software_contract|operational_pain",
  "automation_gap": "one sentence naming the literal gap",
  "observed_problem": "facts from the site",
  "evidence": ["observations"],
  "facts": [{"observation": "...", "source_hint": "homepage|contact|about|other"}],
  "inferences": [{"claim": "...", "based_on": "...", "confidence": "High|Medium|Low"}],
  "automation_opportunity": "what to sell against that gap",
  "recommended_offer": "one offer",
  "confidence": "High|Medium|Low",
  "company_summary": "1-2 sentences",
  "industry_guess": "string or null",
  "location_guess": "string or null",
  "reject_reason": "if qualify is false"
}
"""


def detect_opportunity(run_id: int, company: dict, research: dict, parsed_icp: dict, use_llm: bool = True) -> dict:
    track = company.get("track") or "operational_pain"
    heuristic = detect_automation_gap(research, track)
    if not use_llm:
        data = _heuristic_opportunity(heuristic, track)
        data["heuristic_gap"] = heuristic
        return data
    user = json.dumps(
        {
            "icp": {
                "industry": parsed_icp.get("industry"),
                "location": parsed_icp.get("location"),
                "tracks": parsed_icp.get("tracks"),
            },
            "suggested_track": track,
            "named_target": company.get("named_target"),
            "company_name": company.get("name"),
            "website": research.get("website") or company.get("website"),
            "heuristic_signals": research.get("signals"),
            "heuristic_gap": heuristic,
            "extracted_whatsapp": research.get("whatsapps"),
            "extracted_phones": research.get("phones"),
            "pages_fetched": research.get("pages"),
            "seller_services": SERVICES,
            "website_text_excerpt": (research.get("text") or "")[:11000],
        },
        ensure_ascii=False,
    )
    try:
        data = json.loads(chat_json(run_id, SYSTEM, user, temperature=0.1))
    except Exception as exc:
        data = {
            "qualify": heuristic["exists"],
            "confidence": "Medium" if heuristic["exists"] else "Low",
            "facts": [{"observation": f} for f in heuristic["facts"]],
            "inferences": [],
            "evidence": heuristic["facts"],
            "observed_problem": heuristic["summary"],
            "automation_gap": heuristic["summary"],
            "automation_opportunity": heuristic["summary"],
            "recommended_offer": "Automation against the public process gap" if heuristic["exists"] else "None",
            "track": track,
            "reject_reason": None if heuristic["exists"] else f"Opportunity analysis failed: {exc}",
        }

    data.setdefault("facts", [])
    data.setdefault("inferences", [])
    data.setdefault("evidence", [])
    data.setdefault("track", track)
    data["heuristic_gap"] = heuristic

    if heuristic["exists"]:
        data["qualify"] = True
        if not data.get("automation_gap"):
            data["automation_gap"] = heuristic["summary"]
        if not data.get("observed_problem"):
            data["observed_problem"] = heuristic["summary"]
        if not data.get("automation_opportunity"):
            data["automation_opportunity"] = heuristic["summary"]
        if heuristic["facts"] and not data.get("evidence"):
            data["evidence"] = heuristic["facts"]
        if data.get("confidence") == "Low":
            data["confidence"] = "Medium"
    elif not data.get("observed_problem"):
        data["qualify"] = False
        data["reject_reason"] = data.get("reject_reason") or "No grounded automation gap on the public pages"
        data["automation_gap"] = data.get("automation_gap") or heuristic["summary"]

    return data


def _heuristic_opportunity(heuristic: dict, track: str) -> dict:
    return {
        "qualify": bool(heuristic.get("exists")),
        "confidence": "Medium" if heuristic.get("exists") else "Low",
        "facts": [{"observation": f} for f in (heuristic.get("facts") or [])],
        "inferences": [],
        "evidence": heuristic.get("facts") or [],
        "observed_problem": heuristic.get("summary"),
        "automation_gap": heuristic.get("summary"),
        "automation_opportunity": heuristic.get("summary"),
        "recommended_offer": "Automation against the public process gap" if heuristic.get("exists") else "None",
        "track": track,
        "reject_reason": None if heuristic.get("exists") else "No grounded automation gap on the public pages",
    }

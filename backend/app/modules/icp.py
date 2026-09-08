import json
import re

from app.llm import chat_json
from app.logging_util import log_event
from app.playbook import (
    AGENCY_QUERIES,
    DEFAULT_ICP,
    OPERATIONAL_QUERIES,
    SOFTWARE_QUERIES,
    TRACKS,
    named_for_tracks,
)


SERVICES = [
    "AI automation",
    "business process automation",
    "WhatsApp automation",
    "lead qualification and follow-up systems",
    "CRM integrations",
    "API integrations",
    "internal business tools",
    "dashboards",
    "custom web applications",
    "backend systems",
    "ecommerce workflows",
    "Odoo/ERP integrations",
    "reporting automation",
    "data processing",
    "AI customer-support workflows",
    "custom AI agents",
    "overflow / contract engineering for agencies",
]


def parse_icp(run_id: int, icp_text: str, target_count: int) -> dict:
    fallback = _heuristic_icp(icp_text, target_count)
    try:
        raw = chat_json(
            run_id,
            system=(
                "You parse prospecting ICPs into JSON. Never invent companies or websites. "
                "Seller is a Kenya-based software engineer offering automation, WhatsApp/CRM/API/ERP, "
                "dashboards, custom apps, and contract overflow work for agencies. "
                "Real estate is only ONE example of operational-pain businesses — not the default. "
                "Return JSON keys: country, city, location, industry, problem_hint, target_count, "
                "tracks (array subset of agency_partner, software_contract, operational_pain), "
                "named_targets (array of {name, track} the user mentioned), "
                "keywords (array), search_queries (6-12 official-website searches), "
                "directory_queries (array), must_signals (array)."
            ),
            user=(
                f"ICP request: {icp_text}\n"
                f"Default target count: {target_count}\n"
                f"Seller services: {json.dumps(SERVICES)}\n"
                "If the user is vague or wants clients in general, use ALL three tracks and Nairobi/Kenya. "
                "If they name specific companies, include them in named_targets. "
                "Search queries must find company websites, not job ads or listicles."
            ),
        )
        parsed = json.loads(raw)
        parsed["target_count"] = int(parsed.get("target_count") or target_count)
        parsed["country"] = parsed.get("country") or fallback["country"]
        parsed["city"] = parsed.get("city") or fallback["city"]
        parsed["industry"] = parsed.get("industry") or fallback["industry"]
        parsed["problem_hint"] = parsed.get("problem_hint") or fallback["problem_hint"]
        parsed["location"] = parsed.get("location") or fallback["location"]
        tracks = parsed.get("tracks") or fallback["tracks"]
        parsed["tracks"] = [t for t in tracks if t in TRACKS] or fallback["tracks"]
        parsed["keywords"] = parsed.get("keywords") or fallback["keywords"]
        parsed["search_queries"] = parsed.get("search_queries") or fallback["search_queries"]
        parsed["directory_queries"] = parsed.get("directory_queries") or fallback["directory_queries"]
        parsed["must_signals"] = parsed.get("must_signals") or fallback["must_signals"]
        parsed["named_targets"] = parsed.get("named_targets") or fallback["named_targets"]
        parsed["raw_icp"] = icp_text
        parsed["default_icp_note"] = DEFAULT_ICP[:80]
        return parsed
    except Exception as exc:
        log_event(run_id, "icp_fallback", f"LLM ICP parse failed, using heuristics: {exc}", level="warning")
        fallback["raw_icp"] = icp_text
        return fallback


def _heuristic_icp(icp_text: str, target_count: int) -> dict:
    text = icp_text.lower()
    count_match = re.search(r"(\d+)\s+(kenyan|nairobi|companies|business|prospects|agenc)", text)
    count = int(count_match.group(1)) if count_match else target_count
    city = "Nairobi" if "nairobi" in text or "kenya" in text or "kenyan" in text else "Nairobi"
    country = "Kenya"

    tracks: list[str] = []
    if any(k in text for k in ("agency", "agencies", "digital marketing", "web design", "overflow")):
        tracks.append("agency_partner")
    if any(k in text for k in ("software", "ai company", "freelance", "contract engineer")):
        tracks.append("software_contract")
    if any(
        k in text
        for k in (
            "real estate",
            "clinic",
            "school",
            "travel",
            "salon",
            "event",
            "ecommerce",
            "whatsapp",
            "manual",
            "operational",
        )
    ):
        tracks.append("operational_pain")
    if "priority" in text or "three" in text or not tracks:
        tracks = ["agency_partner", "software_contract", "operational_pain"]
    if "only real estate" in text or (text.count("real estate") and "agency" not in text and "software" not in text and "priority" not in text and "clinic" not in text):
        if "agency" not in text and "software" not in text and "priority" not in text:
            # Narrow request
            if "real estate" in text and "agency" not in text and len(tracks) == 3 and "digital" not in text:
                tracks = ["operational_pain"]

    # If user pasted the full playbook / default, keep all three
    if "priority 1" in text or "overflow" in text or "beyond what your current team" in text:
        tracks = ["agency_partner", "software_contract", "operational_pain"]

    industry = "mixed Kenya ICP"
    if tracks == ["operational_pain"] and "real estate" in text:
        industry = "real estate"
    elif tracks == ["agency_partner"]:
        industry = "digital / marketing agency"
    elif tracks == ["software_contract"]:
        industry = "software / AI"

    location = f"{city}, {country}"
    queries: list[str] = []
    if "agency_partner" in tracks:
        queries.extend(AGENCY_QUERIES)
    if "software_contract" in tracks:
        queries.extend(SOFTWARE_QUERIES)
    if "operational_pain" in tracks:
        queries.extend(OPERATIONAL_QUERIES)
    named = named_for_tracks(tracks)
    return {
        "country": country,
        "city": city,
        "location": location,
        "industry": industry,
        "problem_hint": "agency overflow + contract engineering + operational automation",
        "target_count": count,
        "tracks": tracks,
        "named_targets": named,
        "keywords": [city, country] + [k for t in tracks for k in TRACKS[t]["keywords"][:3]],
        "search_queries": queries[:12],
        "directory_queries": [
            "digital marketing agencies Nairobi Kenya website",
            "software companies Nairobi Kenya website",
        ],
        "must_signals": ["whatsapp", "enquire", "agency", "software", "automation", "contact"],
        "raw_icp": icp_text,
    }

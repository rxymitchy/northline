import re

from app.playbook import NAMED_TARGETS, TRACKS
from app.modules.page_type import is_editorial_name, should_skip_search_result

PAIN_HINTS = [
    "whatsapp",
    "wa.me",
    "enquire",
    "inquiry",
    "enquiry",
    "call us",
    "book a viewing",
    "request a quote",
    "get a quote",
    "chat with us",
    "appointment",
    "we will call you",
]

AGENCY_HINTS = [
    "digital marketing",
    "marketing agency",
    "web design",
    "web development",
    "seo",
    "social media",
    "branding",
    "advertising",
    "ecommerce website",
]

SOFTWARE_HINTS = [
    "software development",
    "ai automation",
    "custom software",
    "it solutions",
    "systems",
    "integrations",
    "saas",
]

SKIP_TITLE_HINTS = [
    "best 10",
    "top 10",
    "top 20",
    "list of",
    "wikipedia",
    "salary",
    "jobs in",
    "vacancy",
    "tender",
    "hiring",
]


def cheap_filter(company: dict, parsed_icp: dict) -> tuple[bool, int, str]:
    score = 20
    reasons: list[str] = []
    blob = " ".join(
        [
            company.get("name") or "",
            company.get("title") or "",
            company.get("snippet") or "",
            company.get("description") or "",
            company.get("website") or "",
            company.get("source_url") or "",
        ]
    ).lower()

    skip = should_skip_search_result(
        company.get("source_url") or company.get("website") or "",
        company.get("title") or company.get("name") or "",
        company.get("snippet") or "",
    )
    if skip:
        return False, 5, skip

    name = company.get("name") or ""
    if is_editorial_name(name) and not company.get("named_target"):
        return False, 4, f"Name looks like an article headline, not a company: {name}"

    if any(h in blob for h in SKIP_TITLE_HINTS) and not company.get("named_target"):
        return False, 8, "Looks like a listicle, job ad, or directory write-up"

    if company.get("named_target") or _matches_named(blob):
        score += 35
        reasons.append("named target from playbook")

    tracks = parsed_icp.get("tracks") or list(TRACKS.keys())
    track = company.get("track")
    if track in tracks:
        score += 12
        reasons.append(f"track={track}")

    if any(h in blob for h in AGENCY_HINTS) and "agency_partner" in tracks:
        score += 18
        reasons.append("agency/marketing signal")
    if any(h in blob for h in SOFTWARE_HINTS) and "software_contract" in tracks:
        score += 16
        reasons.append("software/AI signal")

    industry = (parsed_icp.get("industry") or "").lower()
    if industry and industry not in ("general", "mixed kenya icp") and "mixed" not in industry:
        tokens = [t for t in re.split(r"\W+", industry) if len(t) > 3]
        if any(t in blob for t in tokens):
            score += 12
            reasons.append("industry keyword in snippet")

    location_bits = [parsed_icp.get("city"), parsed_icp.get("country"), "nairobi", "kenya", "kenyan"]
    if any((b or "").lower() in blob for b in location_bits if b):
        score += 12
        reasons.append("location keyword present")

    hits = [h for h in PAIN_HINTS if h in blob]
    if hits and "operational_pain" in tracks:
        score += min(24, 6 * len(hits))
        reasons.append(f"ops pain hints: {', '.join(hits[:4])}")

    if company.get("website") and not company.get("is_directory"):
        score += 15
        reasons.append("has candidate website")
    elif company.get("is_directory"):
        score += 5
        reasons.append("directory listing — may resolve website later")
    else:
        score -= 15
        reasons.append("no website")

    score = max(0, min(100, score))
    passed = score >= 35 and (bool(company.get("website")) or bool(company.get("is_directory")) or bool(company.get("named_target")))
    reason = "; ".join(reasons) or "insufficient signal"
    return passed, score, reason


def _matches_named(blob: str) -> bool:
    for item in NAMED_TARGETS:
        n = item["name"].lower()
        if n in blob:
            return True
        token = n.split()[0]
        if len(token) >= 5 and token in blob:
            return True
    return False

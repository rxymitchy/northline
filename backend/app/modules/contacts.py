import re
from urllib.parse import urlparse

from app.logging_util import log_event
from app.modules.research import EMAIL_RE, KENYA_PHONE_RE
from app.providers.factory import get_search_provider

ROLE_BY_PROBLEM = [
    ("whatsapp", ["Founder", "CEO", "Managing Director", "Head of Sales", "Sales Manager", "Marketing Manager"]),
    ("lead", ["Head of Sales", "Sales Manager", "Marketing Manager", "Founder"]),
    ("support", ["Customer Experience Manager", "Operations Manager", "Founder"]),
    ("booking", ["Operations Manager", "Founder", "Managing Director"]),
    ("erp", ["IT Manager", "Operations Manager", "Founder"]),
    ("report", ["Operations Manager", "Founder"]),
]

GENERIC_LOCAL = {
    "info",
    "hello",
    "contact",
    "admin",
    "support",
    "sales",
    "enquiries",
    "enquiry",
    "office",
    "mail",
    "noreply",
    "no-reply",
    "webmaster",
    "privacy",
    "billing",
}

JUNK_EMAIL_DOMAINS = {
    "sentry.io",
    "wixpress.com",
    "cloudflare.com",
    "google.com",
    "gstatic.com",
    "schema.org",
    "example.com",
    "w3.org",
    "github.com",
}

DECISION_LOCAL = {"ceo", "founder", "director", "md", "managingdirector", "partnerships", "owner", "principal"}


def find_contact(company: dict, research: dict, opportunity: dict, run_id: int | None = None) -> dict:
    track = opportunity.get("track") or company.get("track")
    text = (opportunity.get("observed_problem") or "") + " " + (opportunity.get("automation_opportunity") or "")
    if track == "agency_partner":
        preferred_roles = ["Founder", "CEO", "Managing Director", "Partnerships", "Head of Operations"]
    elif track == "software_contract":
        preferred_roles = ["Founder", "CEO", "CTO", "Engineering Manager", "Managing Director"]
    else:
        preferred_roles = ["Founder", "CEO", "Managing Director"]
        low = text.lower()
        for key, roles in ROLE_BY_PROBLEM:
            if key in low:
                preferred_roles = roles
                break

    people = research.get("people") or []
    chosen_name = None
    chosen_role = None
    snippet = None
    for person in people:
        role = person.get("role_hint") or ""
        if any(r.lower() in role.lower() for r in preferred_roles):
            chosen_role = role
            snippet = person.get("snippet")
            chosen_name = _name_from_snippet(snippet or "", role)
            break
    if not chosen_role and people:
        chosen_role = people[0].get("role_hint")
        snippet = people[0].get("snippet")
        chosen_name = _name_from_snippet(snippet or "", chosen_role or "")

    domain = _domain(research.get("website") or company.get("website"))
    picked = _pick_email(
        research.get("email_records") or [],
        research.get("emails") or [],
        domain,
        chosen_name,
    )

    search_hits = []
    if not picked or picked.get("kind") == "company_inbox" or not (research.get("phones") or research.get("whatsapps")):
        search_hits = _search_public_emails(run_id, company.get("name") or "", domain, chosen_name)
        better = _best_search_email(search_hits, domain, chosen_name)
        if better and (not picked or picked.get("kind") != "decision_maker"):
            picked = better

    if not picked:
        public_email = None
        kind = "none"
        verified = False
        source = None
        note = "CONTACT NOT VERIFIED — no public email found on the website or in public search snippets. Email was not invented."
    else:
        public_email = picked["email"]
        kind = picked["kind"]
        verified = picked.get("verified", False)
        source = picked.get("source")
        if kind == "decision_maker":
            note = f"Public decision-maker email ({picked.get('why')}). Not generated."
        elif kind == "company_inbox":
            note = (
                "Only a generic company inbox was found (e.g. info@). "
                "That is a real public address, not a named decision-maker. Not generated."
            )
        else:
            note = "Email appeared in a public search snippet — verify before sending. Not generated."

    if not chosen_name and not chosen_role:
        chosen_role = preferred_roles[0]
        if not public_email:
            note = (
                "CONTACT NOT VERIFIED — no named decision-maker and no public email on fetched pages or search snippets. "
                f"Suggested role only: {preferred_roles[0]}."
            )

    phone = _best_phone(research.get("phones") or [], research.get("whatsapps") or [])
    if not phone:
        phone = _phone_from_search(search_hits)

    rationale = (
        f"Looked for {', '.join(preferred_roles[:3])} on contact/about/team pages, then public search. "
        f"Name: {chosen_name or 'not found on public pages'}. "
        f"Email: {public_email or 'not found'}. "
        f"Phone to call: {phone or 'not found'}. Kind: {kind}. "
        "Personal emails are never guessed from firstname.lastname@domain."
    )
    if phone and "Phone to call" not in note:
        note = f"{note} Call number found on a public page or WhatsApp link: {phone}."
    return {
        "name": chosen_name,
        "role": chosen_role,
        "email": public_email,
        "phone": phone,
        "linkedin": None,
        "verified": verified,
        "verification_note": note,
        "source_url": source or (research.get("pages") or [{}])[0].get("url") or company.get("website"),
        "rationale": rationale,
    }


def _pick_email(records: list[dict], emails: list[str], domain: str | None, person_name: str | None) -> dict | None:
    scored: list[dict] = []
    seen = set()
    for rec in records:
        email = (rec.get("email") or "").strip()
        if not _usable_email(email) or email.lower() in seen:
            continue
        seen.add(email.lower())
        scored.append(_score_email(email, rec.get("context") or rec.get("label") or "", domain, person_name, rec.get("source") or "page"))
    for email in emails:
        if not _usable_email(email) or email.lower() in seen:
            continue
        seen.add(email.lower())
        scored.append(_score_email(email, "", domain, person_name, "page_text"))
    if not scored:
        return None
    scored.sort(key=lambda x: x["score"], reverse=True)
    return scored[0]


def _score_email(email: str, context: str, domain: str | None, person_name: str | None, source: str) -> dict:
    local, host = email.split("@", 1)
    local_l = local.lower().replace(".", "").replace("-", "")
    host_l = host.lower()
    ctx = context.lower()
    score = 10
    kind = "company_inbox"
    why = "public address on website"
    if domain and host_l.replace("www.", "") == domain:
        score += 15
        why = "same domain as company website"
    if local.lower() in GENERIC_LOCAL:
        score += 2
        kind = "company_inbox"
        why = f"generic inbox {local.lower()}@ on a public page"
    elif local_l in DECISION_LOCAL or any(r in ctx for r in ("ceo", "founder", "managing director", "director")):
        score += 40
        kind = "decision_maker"
        why = "role mailbox or email next to a leadership title"
    elif "." in local or local.count("_") == 1:
        score += 25
        kind = "decision_maker"
        why = "person-style local part on a public page (not generated)"
    if person_name:
        parts = [p.lower() for p in person_name.split() if len(p) > 2]
        if parts and all(p in local.lower() or p in ctx for p in parts[:2]):
            score += 20
            kind = "decision_maker"
            why = f"email associated with named person {person_name}"
    verified = source in ("mailto", "page_text", "page")
    return {"email": email, "kind": kind, "score": score, "why": why, "verified": verified, "source": source}


def _search_public_emails(run_id: int | None, company_name: str, domain: str | None, person_name: str | None) -> list[dict]:
    if not company_name:
        return []
    queries = [
        f'"{company_name}" (CEO OR founder OR "managing director") email Kenya',
        f'"{company_name}" (director OR founder) "@" contact',
        f'"{company_name}" (CEO OR director OR founder) (phone OR tel OR "+254") Kenya',
    ]
    if domain:
        queries.append(f'site:{domain} (CEO OR founder OR director) email')
    if person_name:
        queries.append(f'"{person_name}" "{company_name}" email')
    hits: list[dict] = []
    try:
        provider = get_search_provider()
    except Exception as exc:
        log_event(run_id, "contact_search_error", str(exc), level="warning")
        return []
    for query in queries[:3]:
        try:
            rows = provider.search(query, max_results=5)
            log_event(run_id, "contact_search", query)
        except Exception as exc:
            log_event(run_id, "contact_search_error", f"{query}: {exc}", level="warning")
            continue
        for row in rows:
            blob = f"{row.title} {row.snippet} {row.url}"
            found_email = False
            for email in EMAIL_RE.findall(blob):
                if not _usable_email(email):
                    continue
                found_email = True
                hits.append(
                    {
                        "email": email,
                        "snippet": row.snippet,
                        "url": row.url,
                        "query": query,
                    }
                )
            if not found_email:
                hits.append({"email": None, "snippet": blob, "url": row.url, "query": query})
    return hits


def _best_search_email(hits: list[dict], domain: str | None, person_name: str | None) -> dict | None:
    scored = []
    seen = set()
    for hit in hits:
        email = hit.get("email")
        if not email or email.lower() in seen:
            continue
        seen.add(email.lower())
        item = _score_email(email, hit.get("snippet") or "", domain, person_name, hit.get("url") or "search")
        item["verified"] = False
        item["kind"] = "decision_maker" if item["kind"] == "decision_maker" else "unverified_search"
        item["why"] = f"Found in public search snippet ({item['why']}). Verify before sending."
        if domain and email.lower().endswith("@" + domain):
            item["score"] += 10
        scored.append(item)
    if not scored:
        return None
    scored.sort(key=lambda x: x["score"], reverse=True)
    return scored[0]


def _best_phone(phones: list[str], whatsapps: list[str]) -> str | None:
    for p in phones:
        if p and len(re.sub(r"\D", "", p)) >= 9:
            return p
    for wa in whatsapps:
        m = re.search(r"(\+?254\d{9}|0[17]\d{8})", wa)
        if m:
            return m.group(1)
    return None


def _phone_from_search(hits: list[dict]) -> str | None:
    for hit in hits:
        blob = hit.get("snippet") or ""
        found = KENYA_PHONE_RE.findall(blob)
        if found:
            return found[0]
    return None


def _usable_email(email: str) -> bool:
    if not email or "@" not in email:
        return False
    email = email.strip().strip(".")
    host = email.split("@", 1)[1].lower()
    if any(host.endswith(j) for j in JUNK_EMAIL_DOMAINS):
        return False
    if email.lower().endswith((".png", ".jpg", ".gif", ".webp", ".js", ".css")):
        return False
    return True


def _domain(url: str | None) -> str | None:
    if not url:
        return None
    host = urlparse(url).netloc.lower().replace("www.", "")
    return host or None


def _name_from_snippet(snippet: str, role: str) -> str | None:
    cleaned = snippet.replace(role, " ")
    match = re.search(r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,3})\b", cleaned)
    if match:
        name = match.group(1)
        if name.lower() in {"kenya", "nairobi", "managing director", "contact us", "about us"}:
            return None
        return name
    return None

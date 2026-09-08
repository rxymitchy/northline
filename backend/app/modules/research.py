import re
import time
from urllib.parse import urljoin, urlparse
from urllib.robotparser import RobotFileParser

from bs4 import BeautifulSoup

from app.config import settings
from app.http_compat import http_get, response_header, response_text
from app.logging_util import log_event
from app.modules.page_type import not_a_company_site_reason


EMAIL_RE = re.compile(r"[A-Z0-9._%+\-]+@[A-Z0-9.\-]+\.[A-Z]{2,}", re.I)
WHATSAPP_RE = re.compile(
    r"(?:https?://(?:wa\.me|api\.whatsapp\.com|web\.whatsapp\.com)/[^\s\"'<>]+|whatsapp)",
    re.I,
)
TEL_RE = re.compile(r"tel:([+\d][\d\s\-()]{6,})")
KENYA_PHONE_RE = re.compile(r"(?:\+254|0)[17]\d{8}|(?:\+254\s[17]\d{2}\s\d{3}\s\d{3})|(?:0[17]\d{2}\s\d{3}\s\d{3})")

SIGNAL_PATTERNS = {
    "whatsapp_channel": [r"whatsapp", r"wa\.me", r"chat on whatsapp"],
    "call_to_book": [r"call (us )?to (book|enquire|inquire)", r"phone to book"],
    "online_booking": [r"book online", r"online booking", r"calendly", r"schedule an appointment"],
    "enquiry_form": [r"enquiry form", r"inquiry form", r"contact form", r"send us a message"],
    "chatbot": [r"chatbot", r"tawk\.to", r"intercom", r"crisp\.chat", r"tidio"],
    "crm_mention": [r"\bcrm\b", r"hubspot", r"salesforce", r"zoho"],
    "ecommerce": [r"add to cart", r"shop now", r"woocommerce", r"shopify", r"checkout"],
    "quote_request": [r"request a quote", r"get a quote", r"quotation"],
    "application_process": [r"apply now", r"application form", r"submit documents"],
    "customer_portal": [r"client portal", r"customer portal", r"login to your account"],
    "manual_followup_language": [r"we will (call|contact|get back)", r"our team will"],
}


_robots_cache: dict[str, RobotFileParser | None] = {}


def research_company(run_id: int, company: dict) -> dict:
    start_url = company.get("website") or company.get("source_url")
    if not start_url:
        return {"ok": False, "reason": "No URL to research"}

    pages: list[dict] = []
    try:
        homepage = _fetch_page(start_url)
    except Exception as exc:
        log_event(run_id, "fetch_error", f"Failed to fetch {start_url}: {exc}", level="warning")
        return {"ok": False, "reason": str(exc)}

    if not homepage:
        return {"ok": False, "reason": f"Blocked or empty: {start_url}"}

    article_reason = not_a_company_site_reason(
        homepage.get("title") or "",
        homepage.get("text") or "",
        homepage.get("url") or start_url,
        homepage.get("html_sample") or "",
    )
    if article_reason:
        return {"ok": False, "reason": article_reason}

    pages.append(homepage)
    website = company.get("website") or _origin(homepage["url"])
    extra_urls = _candidate_paths(homepage, website)
    for url in extra_urls:
        time.sleep(settings.fetch_delay_seconds)
        try:
            page = _fetch_page(url)
            if page:
                pages.append(page)
        except Exception as exc:
            log_event(run_id, "fetch_error", f"Failed to fetch {url}: {exc}", level="warning")

    combined_text = "\n\n".join(p["text"] for p in pages)[:14000]
    combined_html = "\n".join(p.get("html_sample", "") for p in pages)
    signals = _extract_signals(combined_text + "\n" + combined_html)
    emails = _unique(sum((p["emails"] for p in pages), []))
    email_records = sum((p.get("email_records") or [] for p in pages), [])
    phones = _unique(sum((p["phones"] for p in pages), []))
    whatsapps = _unique(sum((p["whatsapps"] for p in pages), []))
    if whatsapps:
        signals["whatsapp_channel"] = True
        for wa in whatsapps:
            m = re.search(r"(?:wa\.me|whatsapp\.com/send\?phone=)/?(\d{10,15})", wa)
            if m:
                phones.append(_clean_phone("+" + m.group(1) if not m.group(1).startswith("0") else m.group(1)))
        phones = _unique(phones)
    people = sum((p["people"] for p in pages), [])
    resolved_website = _maybe_resolve_directory(homepage, company)

    return {
        "ok": True,
        "website": resolved_website or website,
        "pages": [{"url": p["url"], "title": p["title"]} for p in pages],
        "text": combined_text,
        "signals": signals,
        "emails": emails,
        "email_records": email_records,
        "phones": phones,
        "whatsapps": whatsapps,
        "people": people,
        "meta_description": pages[0].get("description"),
    }


def _fetch_page(url: str) -> dict | None:
    if not _allowed(url):
        return None
    try:
        response = http_get(url, timeout=settings.fetch_timeout_seconds)
    except Exception as exc:
        if "aswMonFltProxy" in str(exc) or getattr(exc, "errno", None) == 13:
            response = http_get(url, timeout=settings.fetch_timeout_seconds)
        else:
            raise
    status = getattr(response, "status_code", 0)
    if status in (401, 403, 407):
        return None
    if status >= 400:
        raise RuntimeError(f"HTTP {status}")
    content_type = response_header(response, "content-type")
    if content_type and "text/html" not in content_type and "application/xhtml" not in content_type and "text/" not in content_type:
        return None
    html = response_text(response)
    if _looks_like_captcha(html):
        return None
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript", "svg"]):
        tag.decompose()
    title = (soup.title.string or "").strip() if soup.title else ""
    desc = ""
    md = soup.find("meta", attrs={"name": "description"})
    if md and md.get("content"):
        desc = md["content"]
    text = re.sub(r"\n{3,}", "\n\n", soup.get_text("\n")).strip()[:12000]
    emails = _unique(EMAIL_RE.findall(html + "\n" + text))
    emails = [e for e in emails if not e.lower().endswith((".png", ".jpg", ".gif", ".webp"))]
    email_records = _email_records(soup, emails)
    phones = _unique(TEL_RE.findall(html) + KENYA_PHONE_RE.findall(html + "\n" + text))
    phones = [_clean_phone(p) for p in phones]
    whatsapps = _extract_whatsapps(html, soup)
    people = _extract_people(soup, text)
    return {
        "url": str(response.url),
        "title": title,
        "description": desc,
        "text": f"{title}\n{desc}\n{text}",
        "html_sample": html[:8000],
        "emails": emails,
        "email_records": email_records,
        "phones": phones,
        "whatsapps": whatsapps,
        "people": people,
        "links": [a.get("href") for a in soup.find_all("a", href=True)][:200],
    }


def _email_records(soup: BeautifulSoup, emails: list[str]) -> list[dict]:
    records: list[dict] = []
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if not href.lower().startswith("mailto:"):
            continue
        email = href.split(":", 1)[1].split("?")[0].strip()
        label = re.sub(r"\s+", " ", a.get_text(" ", strip=True))
        parent = re.sub(r"\s+", " ", a.parent.get_text(" ", strip=True)[:240] if a.parent else "")
        records.append({"email": email, "label": label, "context": parent, "source": "mailto"})
    for email in emails:
        if any(r["email"].lower() == email.lower() for r in records):
            continue
        records.append({"email": email, "label": "", "context": "", "source": "page_text"})
    return records


def _candidate_paths(homepage: dict, website: str) -> list[str]:
    wanted = (
        "contact",
        "about",
        "team",
        "leadership",
        "people",
        "staff",
        "founders",
        "enquire",
        "inquiry",
        "enquiry",
    )
    urls: list[str] = []
    for href in homepage.get("links") or []:
        if not href:
            continue
        low = href.lower()
        if any(w in low for w in wanted) and not low.startswith("mailto:"):
            abs_url = urljoin(homepage["url"], href)
            if urlparse(abs_url).netloc.replace("www.", "") == urlparse(website).netloc.replace("www.", ""):
                urls.append(abs_url.split("#")[0])
    # Common public paths if not linked
    for path in ("/contact", "/contact-us", "/about", "/about-us", "/team", "/our-team", "/leadership"):
        urls.append(urljoin(website.rstrip("/") + "/", path.lstrip("/")))
    deduped: list[str] = []
    seen = {homepage["url"]}
    for u in urls:
        if u not in seen:
            seen.add(u)
            deduped.append(u)
        if len(deduped) >= 5:
            break
    return deduped


def _extract_signals(blob: str) -> dict:
    low = blob.lower()
    out = {}
    for key, patterns in SIGNAL_PATTERNS.items():
        out[key] = any(re.search(p, low) for p in patterns)
    return out


def _extract_whatsapps(html: str, soup: BeautifulSoup) -> list[str]:
    found: list[str] = []
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if "wa.me" in href or "whatsapp" in href.lower():
            found.append(href)
    found.extend(WHATSAPP_RE.findall(html))
    return _unique(found)


def _extract_people(soup: BeautifulSoup, text: str) -> list[dict]:
    people: list[dict] = []
    role_re = re.compile(
        r"(?:CEO|Founder|Co-Founder|Managing Director|MD|Director|Operations Manager|"
        r"Sales Manager|Marketing Manager|Customer Experience|IT Manager|Head of Sales|"
        r"Head of Operations|Principal Agent)",
        re.I,
    )
    for match in role_re.finditer(text):
        start = max(0, match.start() - 80)
        end = min(len(text), match.end() + 80)
        window = re.sub(r"\s+", " ", text[start:end]).strip()
        people.append({"role_hint": match.group(0), "snippet": window})
        if len(people) >= 8:
            break
    return people


def _maybe_resolve_directory(homepage: dict, company: dict) -> str | None:
    if not company.get("is_directory"):
        return company.get("website")
    for href in homepage.get("links") or []:
        if not href or not href.startswith("http"):
            continue
        host = urlparse(href).netloc.lower().replace("www.", "")
        if any(h in host for h in ("facebook.", "linkedin.", "instagram.", "twitter.", "businesslist", "yellow.co")):
            continue
        if host and "." in host:
            return _origin(href)
    return company.get("website")


def _allowed(url: str) -> bool:
    parsed = urlparse(url)
    robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
    if robots_url not in _robots_cache:
        rp = RobotFileParser()
        try:
            resp = http_get(robots_url, timeout=8)
            if getattr(resp, "status_code", 0) >= 400:
                _robots_cache[robots_url] = None
            else:
                rp.parse(response_text(resp).splitlines())
                _robots_cache[robots_url] = rp
        except Exception:
            _robots_cache[robots_url] = None
    rp = _robots_cache[robots_url]
    if rp is None:
        return True
    try:
        return rp.can_fetch(settings.user_agent, url)
    except Exception:
        return True


def _looks_like_captcha(html: str) -> bool:
    """Skip challenge walls only — Cloudflare script URLs on real sites are fine."""
    low = html.lower()
    if len(html) < 25000 and "just a moment" in low and "cloudflare" in low:
        return True
    if len(html) < 25000 and "cf-challenge-running" in low:
        return True
    if len(html) < 12000 and ("are you a robot" in low or "verify you are human" in low):
        return True
    return False
    if "attention required" in low and "cloudflare" in low and len(html) < 20000:
        return True
    return False


def _origin(url: str) -> str:
    parsed = urlparse(url)
    return f"{parsed.scheme}://{parsed.netloc}"


def _clean_phone(raw: str) -> str:
    digits = re.sub(r"[^\d+]", "", raw or "")
    if digits.startswith("254") and len(digits) >= 12:
        return "+" + digits[:12]
    if digits.startswith("0") and len(digits) >= 10:
        return "+254" + digits[1:10]
    return raw.strip()


def _unique(items: list[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for item in items:
        key = item.strip()
        if key and key.lower() not in seen:
            seen.add(key.lower())
            out.append(key)
    return out

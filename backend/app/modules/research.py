import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
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
    "dm_cta": [r"\bdm (me|us)\b", r"send (us )?a dm", r"message us", r"inbox us", r"slide into"],
    "link_in_bio": [r"link in bio", r"linktr\.ee", r"beacons\.ai", r"stan\.store"],
    "comments_cta": [r"comment below", r"drop a comment", r"comment .{0,12}(for|to) (price|details|link)"],
}


_robots_cache: dict[str, RobotFileParser | None] = {}


def research_company(run_id: int, company: dict, quick: bool = False) -> dict:
    start_url = company.get("website") or company.get("source_url")
    if not start_url:
        return {"ok": False, "reason": "No URL to research"}

    timeout = 4 if quick else settings.fetch_timeout_seconds
    pages: list[dict] = []
    try:
        homepage = _fetch_page(start_url, timeout=timeout, skip_robots=quick)
    except Exception as exc:
        log_event(run_id, "fetch_error", f"Failed to fetch {start_url}: {exc}", level="warning")
        return {"ok": False, "reason": str(exc)}

    if not homepage:
        return {"ok": False, "reason": f"Blocked or empty: {start_url}"}

    if not quick:
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
    extra_urls = [] if quick else _candidate_paths(homepage, website)
    for url in extra_urls:
        if not quick:
            time.sleep(settings.fetch_delay_seconds)
        try:
            page = _fetch_page(url, timeout=timeout, skip_robots=quick)
            if page:
                pages.append(page)
        except Exception as exc:
            log_event(run_id, "fetch_error", f"Failed to fetch {url}: {exc}", level="warning")
            if quick:
                break

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
    if not quick:
        resolved_website = _maybe_resolve_directory(homepage, company)
    else:
        resolved_website = website

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


VISITOR_BUDGET_SECONDS = 18.0
_WALLED_SOCIAL = (
    "facebook.com",
    "fb.com",
    "instagram.com",
    "linkedin.com",
    "tiktok.com",
    "twitter.com",
    "x.com",
    "threads.net",
)


def visitor_research(run_id: int, name: str, url: str, description: str) -> dict:
    """Homepage + public web mentions in parallel, capped so diagnosis stays under ~15s."""
    deadline = time.monotonic() + VISITOR_BUDGET_SECONDS
    name = (name or "").strip()
    url = (url or "").strip()
    description = (description or "").strip()
    skip_home = not url
    walled = bool(url) and _is_walled_social(url)

    homepage = None
    mentions: list[dict] = []

    def _home() -> dict | None:
        if skip_home:
            return None
        page = _fetch_page_safe(url, 5)
        if page:
            return page
        if walled:
            return _fetch_jina(url, 6)
        return _fetch_jina(url, 5)

    def _search() -> list[dict]:
        return _public_mentions(name, url, description)

    pool = ThreadPoolExecutor(max_workers=2)
    try:
        home_f = pool.submit(_home)
        search_f = pool.submit(_search)
        try:
            homepage = home_f.result(timeout=min(7.0, max(0.2, deadline - time.monotonic())))
        except Exception as exc:
            log_event(run_id, "fetch_error", f"Homepage timed out or failed: {exc}", level="warning")
            homepage = None
        try:
            mentions = search_f.result(timeout=min(8.0, max(0.2, deadline - time.monotonic()))) or []
        except Exception as exc:
            log_event(run_id, "search_error", f"Public mentions search skipped: {exc}", level="warning")
            mentions = []
    finally:
        pool.shutdown(wait=False, cancel_futures=True)

    pages: list[dict] = []
    if homepage:
        pages.append(homepage)

    if homepage and time.monotonic() < deadline - 1.2:
        extra_urls = _candidate_paths(homepage, _origin(homepage.get("url") or url))[:3]
        remain = max(0.3, deadline - time.monotonic())
        extra_pool = ThreadPoolExecutor(max_workers=2)
        try:
            futures = [extra_pool.submit(_fetch_page_safe, extra, 3) for extra in extra_urls]
            try:
                for fut in as_completed(futures, timeout=remain):
                    page = fut.result()
                    if page:
                        pages.append(page)
            except Exception:
                pass
        finally:
            extra_pool.shutdown(wait=False, cancel_futures=True)

    if mentions and time.monotonic() < deadline - 1:
        from app.modules.page_type import host_of, is_publisher_host

        extras = []
        for row in mentions:
            href = (row.get("url") or "").strip()
            if not href or _is_walled_social(href):
                continue
            host = host_of(href)
            if is_publisher_host(host) and not _is_link_in_bio(host):
                continue
            if any(host == urlparse(p.get("url") or "").netloc.replace("www.", "").lower() for p in pages):
                continue
            extras.append(href)
            if len(extras) >= 2:
                break
        for href in extras:
            if time.monotonic() >= deadline - 0.4:
                break
            page = _fetch_page_safe(href, 3) or (_fetch_jina(href, 4) if _is_link_in_bio(urlparse(href).netloc) else None)
            if page:
                pages.append(page)

    mention_block = _format_mentions(mentions)
    own_host = ""
    if url:
        own_host = urlparse(url).netloc.replace("www.", "").lower()
    elif pages:
        own_host = urlparse(pages[0]["url"]).netloc.replace("www.", "").lower()

    if not pages and not description and not mention_block:
        return {"ok": False, "reason": "Could not read a public page or mentions for this company yet."}

    combined_text = "\n\n".join(p["text"] for p in pages)
    if description:
        combined_text = (description + "\n\n" + combined_text).strip()
    if mention_block:
        combined_text = (combined_text + "\n\n" + mention_block).strip()
    combined_text = combined_text[:14000]
    combined_html = "\n".join(p.get("html_sample", "") for p in pages)
    signals = _extract_signals(combined_text + "\n" + combined_html)

    own_pages = [p for p in pages if not own_host or urlparse(p["url"]).netloc.replace("www.", "").lower() == own_host]
    if not own_pages:
        own_pages = pages
    emails = _unique(sum((p["emails"] for p in own_pages), []))
    email_records = sum((p.get("email_records") or [] for p in own_pages), [])
    phones = _unique(sum((p["phones"] for p in own_pages), []))
    whatsapps = _unique(sum((p["whatsapps"] for p in own_pages), []))
    if whatsapps:
        signals["whatsapp_channel"] = True
        for wa in whatsapps:
            m = re.search(r"(?:wa\.me|whatsapp\.com/send\?phone=)/?(\d{10,15})", wa)
            if m:
                phones.append(_clean_phone("+" + m.group(1) if not m.group(1).startswith("0") else m.group(1)))
        phones = _unique(phones)
    people = sum((p["people"] for p in own_pages), [])
    website = None
    owned = next((p for p in pages if not _is_walled_social(p.get("url") or "")), None)
    if owned:
        website = _origin(owned["url"])
    elif pages:
        website = _origin(pages[0]["url"])
    elif url:
        website = url

    return {
        "ok": True,
        "website": website,
        "pages": [{"url": p["url"], "title": p.get("title") or ""} for p in pages],
        "text": combined_text,
        "signals": signals,
        "emails": emails,
        "email_records": email_records,
        "phones": phones,
        "whatsapps": whatsapps,
        "people": people,
        "meta_description": (pages[0].get("description") if pages else None),
        "public_mentions": mentions[:8],
    }


def _is_walled_social(url: str) -> bool:
    host = urlparse(url or "").netloc.lower().replace("www.", "")
    return any(host == h or host.endswith("." + h) for h in _WALLED_SOCIAL)


def _fetch_page_safe(url: str, timeout: int | float) -> dict | None:
    try:
        return _fetch_page(url, timeout=max(1, int(timeout)), skip_robots=True)
    except Exception:
        return None


def _is_link_in_bio(host: str) -> bool:
    host = (host or "").lower().replace("www.", "")
    return any(host == h or host.endswith("." + h) for h in ("linktr.ee", "beacons.ai", "stan.store", "bio.link", "carrd.co"))


def _social_handle(url: str) -> str:
    parsed = urlparse(url or "")
    parts = [p for p in (parsed.path or "").split("/") if p and p.lower() not in ("reel", "reels", "p", "share", "status", "watch", "posts")]
    if not parts:
        return ""
    handle = parts[0].lstrip("@")
    if handle.lower() in ("in", "company", "school", "pages", "groups"):
        handle = parts[1].lstrip("@") if len(parts) > 1 else ""
    return handle[:40]


def _mention_queries(name: str, url: str, description: str) -> list[str]:
    host = urlparse(url or "").netloc.replace("www.", "")
    handle = _social_handle(url) if url and _is_walled_social(url) else ""
    queries: list[str] = []
    if name and host:
        queries.append(f'"{name}" {host}')
        queries.append(f"{name} {host} contact WhatsApp")
    elif name:
        queries.append(name)
    if host and host not in (name or "").lower():
        queries.append(host)
    if handle:
        net = urlparse(url).netloc.replace("www.", "").split(".")[0]
        queries.append(f'"{handle}" {net}')
        queries.append(f"{handle} website")
        queries.append(f"{handle} WhatsApp OR linktree OR contact")
    if name and _is_walled_social(url or ""):
        queries.append(f'"{name}" Instagram OR Facebook OR TikTok OR LinkedIn')
    if description:
        bits = " ".join(description.split()[:8])
        if name and bits:
            queries.append(f"{name} {bits}")
    out: list[str] = []
    seen: set[str] = set()
    for q in queries:
        key = " ".join(q.split()).lower()
        if len(key) < 3 or key in seen:
            continue
        seen.add(key)
        out.append(" ".join(q.split()))
        if len(out) >= 4:
            break
    return out


def _public_mentions(name: str, url: str, description: str) -> list[dict]:
    from app.providers.factory import get_web_search_provider

    queries = _mention_queries(name, url, description)
    if not queries:
        return []
    try:
        provider = get_web_search_provider()
    except Exception:
        return []
    rows = []
    remain = 7.5
    started = time.monotonic()
    pool = ThreadPoolExecutor(max_workers=3)
    try:
        futs = {pool.submit(_safe_provider_search, provider, q): q for q in queries[:4]}
        try:
            for fut in as_completed(futs, timeout=max(0.4, remain)):
                try:
                    rows.extend(fut.result() or [])
                except Exception:
                    pass
                if time.monotonic() - started > remain:
                    break
        except Exception:
            pass
    finally:
        pool.shutdown(wait=False, cancel_futures=True)
    out: list[dict] = []
    seen: set[str] = set()
    for row in rows:
        href = (getattr(row, "url", None) or "").strip()
        if not href or href in seen:
            continue
        seen.add(href)
        out.append(
            {
                "title": (getattr(row, "title", None) or "")[:200],
                "url": href,
                "snippet": (getattr(row, "snippet", None) or "")[:400],
                "host": urlparse(href).netloc.replace("www.", ""),
            }
        )
        if len(out) >= 10:
            break
    return out


def _safe_provider_search(provider, query: str) -> list:
    try:
        return provider.search(query, max_results=8) or []
    except Exception:
        return []


def _fetch_jina(url: str, timeout: int | float) -> dict | None:
    if not url.startswith("http"):
        return None
    try:
        resp = http_get("https://r.jina.ai/" + url, timeout=max(3, int(timeout)))
    except Exception:
        return None
    status = getattr(resp, "status_code", 0)
    if status >= 400:
        return None
    text = (response_text(resp) or "").strip()
    if len(text) < 80:
        return None
    title = text.split("\n", 1)[0][:180]
    emails = _unique(EMAIL_RE.findall(text))
    phones = _unique(TEL_RE.findall(text) + KENYA_PHONE_RE.findall(text))
    whatsapps = _unique(WHATSAPP_RE.findall(text))
    return {
        "url": url,
        "title": title,
        "description": "",
        "text": text[:12000],
        "html_sample": text[:4000],
        "emails": emails,
        "email_records": [],
        "phones": [_clean_phone(p) for p in phones],
        "whatsapps": whatsapps,
        "people": [],
        "links": [],
    }


def _format_mentions(mentions: list[dict]) -> str:
    if not mentions:
        return ""
    lines = ["PUBLIC MENTIONS (web search, not only the submitted link):"]
    for row in mentions:
        title = (row.get("title") or "").strip()
        snippet = (row.get("snippet") or "").strip()
        href = (row.get("url") or "").strip()
        lines.append(f"- {title} — {snippet} ({href})")
    return "\n".join(lines)


def _fetch_page(url: str, timeout: int | None = None, skip_robots: bool = False) -> dict | None:
    if not skip_robots and not _allowed(url):
        return None
    wait = timeout if timeout is not None else settings.fetch_timeout_seconds
    try:
        response = http_get(url, timeout=wait)
    except Exception as exc:
        if "aswMonFltProxy" in str(exc) or getattr(exc, "errno", None) == 13:
            response = http_get(url, timeout=min(float(wait), 4.0))
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
    if not desc:
        og = soup.find("meta", attrs={"property": "og:description"})
        if og and og.get("content"):
            desc = og["content"]
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
        "book",
        "booking",
        "pricing",
        "shop",
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
    for path in ("/contact", "/contact-us", "/about", "/about-us", "/book", "/booking", "/pricing"):
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

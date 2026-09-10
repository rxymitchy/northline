from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urlparse

from app.logging_util import log_event
from app.modules.page_type import (
    homepage_from_article_path,
    is_publisher_host,
    looks_like_operating_company,
    should_skip_search_result,
)
from app.modules.research import _fetch_page
from app.providers.factory import get_search_provider


def find_peer_companies(run_id: int, name: str, website: str, research: dict, gap: dict) -> dict:
    host = (urlparse(website or "").netloc or "").replace("www.", "").lower()
    industry = _industry_guess(name, research)
    provider = get_search_provider()
    similar_q = f'{industry} Kenya (WhatsApp OR "call to book" OR "get a quote" OR "contact us")'
    right_q = f'{industry} Kenya ("book online" OR chatbot OR "online booking" OR "client portal")'
    similar = _collect(run_id, provider, similar_q, host, "similar")
    right = _collect(run_id, provider, right_q, host, "right")
    if not similar:
        similar = _collect(run_id, provider, f"{industry} Nairobi Kenya contact us", host, "similar")
    if not right:
        collected = _collect(run_id, provider, f'{industry} Nairobi "book online" OR "book now"', host, "right")
        seen = {c.get("website") for c in similar}
        right = [c for c in collected if c.get("website") not in seen]
    return {"industry": industry, "similar": similar[:6], "doing_it_right": right[:6]}


def find_better_companies(run_id: int, name: str, website: str, research: dict) -> list[dict]:
    host = (urlparse(website or "").netloc or "").replace("www.", "").lower()
    industry = _industry_guess(name, research)
    provider = get_search_provider()
    queries = [
        f'{industry} Kenya ("book online" OR chatbot OR "online booking" OR "client portal")',
        f'{industry} Nairobi "contact us" "about us"',
    ]
    right: list[dict] = []
    seen = {host}
    for query in queries:
        for row in _collect(run_id, provider, query, host, "right", limit=8):
            h = urlparse(row.get("website") or "").netloc.lower().replace("www.", "")
            if h in seen:
                continue
            seen.add(h)
            right.append(row)
            if len(right) >= 5:
                return right[:5]
    return right[:5]


def _collect(run_id: int, provider, query: str, own_host: str, kind: str, limit: int = 6) -> list[dict]:
    try:
        rows = provider.search(query, max_results=min(12, limit + 6))
        log_event(run_id, "search", f"{kind}: {query}")
    except Exception as exc:
        log_event(run_id, "search_error", str(exc), level="warning")
        return []
    candidates: list[dict] = []
    seen = {own_host}
    for row in rows:
        raw = (row.url or "").strip()
        url = homepage_from_article_path(raw)
        host = urlparse(url).netloc.lower().replace("www.", "")
        if not url.startswith("http") or not host or host in seen:
            continue
        title_for_filter = row.title if url == raw else host
        if is_publisher_host(host) or should_skip_search_result(url, title_for_filter, row.snippet):
            continue
        seen.add(host)
        title = (row.title or host).split("|")[0].split(" - ")[0].strip()[:80]
        snippet = (row.snippet or "").strip()[:220]
        candidates.append({"name": title or host, "website": url, "snippet": snippet, "kind": kind})
        if len(candidates) >= limit + 4:
            break
    verified = _verify_companies(run_id, candidates, limit)
    return verified


def _verify_companies(run_id: int, candidates: list[dict], limit: int) -> list[dict]:
    if not candidates:
        return []
    kept: list[dict] = []
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = {pool.submit(_confirm_company, cand): cand for cand in candidates}
        for fut in as_completed(futures):
            row = fut.result()
            if not row:
                continue
            kept.append(row)
            if len(kept) >= limit:
                break
    log_event(run_id, "peer_filter", f"kept {len(kept)} companies from {len(candidates)} search hits")
    return kept[:limit]


def _confirm_company(cand: dict) -> dict | None:
    url = cand.get("website") or ""
    try:
        page = _fetch_page(url, timeout=6, skip_robots=True)
    except Exception:
        return None
    if not page:
        return None
    title = page.get("title") or cand.get("name") or ""
    text = page.get("text") or ""
    html = page.get("html_sample") or ""
    if not looks_like_operating_company(title, text, url, html[:2500]):
        return None
    final = page.get("url") or url
    name = (title or cand.get("name") or final).split("|")[0].split(" - ")[0].strip()[:80]
    snippet = (page.get("description") or cand.get("snippet") or text[:180]).strip()[:220]
    return {
        "name": name or cand.get("name"),
        "website": final,
        "snippet": snippet,
        "kind": cand.get("kind"),
    }

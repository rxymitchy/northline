import re
from urllib.parse import urlparse

from app.config import settings
from app.logging_util import log_event
from app.modules.page_type import (
    homepage_from_article_path,
    is_editorial_name,
    is_publisher_host,
    should_skip_search_result,
)
from app.playbook import TRACKS, named_for_tracks
from app.providers.factory import get_search_provider
from app.providers.search_base import SearchResult


SKIP_DOMAINS = {
    "facebook.com",
    "m.facebook.com",
    "instagram.com",
    "twitter.com",
    "x.com",
    "youtube.com",
    "tiktok.com",
    "linkedin.com",
    "wikipedia.org",
    "reddit.com",
    "pinterest.com",
    "google.com",
    "maps.google.com",
    "bing.com",
    "glassdoor.com",
    "softonic.com",
    "originlab.com",
    "meta.com",
    "about.meta.com",
    "googleadservices.com",
    "doubleclick.net",
    "apple.com",
    "crunchbase.com",
}

DIRECTORY_HINTS = (
    "businesslist.co.ke",
    "yellow.co.ke",
    "kenyayp.com",
    "cylex.co.ke",
    "hotfrog.co.ke",
    "directory",
)


def discover_candidates(run_id: int, parsed_icp: dict) -> list[dict]:
    provider = get_search_provider()
    target = min(int(parsed_icp.get("target_count") or settings.max_discover), settings.max_discover)
    tracks = parsed_icp.get("tracks") or list(TRACKS.keys())
    named = parsed_icp.get("named_targets") or named_for_tracks(tracks)

    queries: list[str] = []
    for item in named[:18]:
        queries.append(f'"{item["name"]}" Kenya official website')
    queries.extend(list(parsed_icp.get("search_queries") or []))
    queries.extend(list(parsed_icp.get("directory_queries") or []))

    all_results: list[SearchResult] = []
    per_query = max(5, min(8, target // 2 + 3))

    for query in queries[:22]:
        try:
            rows = provider.search(query, max_results=per_query)
            log_event(run_id, "search", f"[{provider.name}] {query}", _payload({"count": len(rows), "query": query}))
            all_results.extend(rows)
        except Exception as exc:
            log_event(run_id, "search_error", f"Search failed for '{query}': {exc}", level="error")

    companies: list[dict] = []
    seen_domains: set[str] = set()
    seen_names: set[str] = set()

    for row in all_results:
        parsed = _result_to_company(row, parsed_icp, named)
        if not parsed:
            continue
        domain = parsed.get("domain") or ""
        name_key = _norm_name(parsed["name"])
        if domain and domain in seen_domains:
            continue
        if name_key in seen_names:
            continue
        if domain:
            seen_domains.add(domain)
        seen_names.add(name_key)
        companies.append(parsed)
        if len(companies) >= max(target + 10, settings.max_discover):
            break

    companies.sort(key=lambda c: (0 if c.get("named_target") else 1, 0 if c.get("track") == "agency_partner" else 2 if c.get("track") == "software_contract" else 3))
    log_event(run_id, "discover_done", f"Discovered {len(companies)} unique candidates from {len(all_results)} results")
    return companies


def _result_to_company(row: SearchResult, parsed_icp: dict, named: list[dict]) -> dict | None:
    url = (row.url or "").strip()
    if not url.startswith("http"):
        return None
    host = urlparse(url).netloc.lower().replace("www.", "")
    if not host or any(host.endswith(d) or host == d for d in SKIP_DOMAINS):
        return None
    skip = should_skip_search_result(url, row.title, row.snippet)
    named_hit_early = _match_named(f"{row.title} {row.snippet} {host}", named)
    if is_publisher_host(host):
        return None
    if skip:
        # A named company mentioned in an article still does not make the article their website.
        if not named_hit_early or not _host_looks_like_company(host, named_hit_early["name"]):
            return None
    is_directory = any(h in host or h in url.lower() for h in DIRECTORY_HINTS)
    name = _clean_name(row.title)
    if not name or len(name) < 3:
        return None
    if is_editorial_name(name) and not named_hit_early:
        return None
    blob = f"{name} {row.snippet} {row.title}".lower()
    named_hit = named_hit_early or _match_named(blob, named)
    if named_hit and not _host_looks_like_company(host, named_hit["name"]) and skip:
        return None
    track = (named_hit or {}).get("track") or _guess_track(blob, parsed_icp.get("tracks") or [])
    industry = TRACKS.get(track, {}).get("industry_label") or parsed_icp.get("industry")
    site = None if is_directory else homepage_from_article_path(url)
    return {
        "name": named_hit["name"] if named_hit else name,
        "website": site,
        "domain": None if is_directory else host,
        "industry": industry,
        "location": parsed_icp.get("location"),
        "description": row.snippet,
        "source": row.source,
        "source_url": url,
        "is_directory": is_directory,
        "snippet": row.snippet,
        "title": row.title,
        "track": track,
        "named_target": bool(named_hit),
    }


GENERIC_NAME_TOKENS = {
    "meta",
    "digital",
    "kenya",
    "nairobi",
    "origin",
    "iconic",
    "cloud",
    "africa",
    "capital",
    "tech",
    "agency",
    "marketing",
    "solutions",
    "limited",
    "omni",
}


def _match_named(blob: str, named: list[dict]) -> dict | None:
    blob_l = blob.lower()
    for item in named:
        full = item["name"].lower()
        if full in blob_l:
            return item
        parts = [p for p in re.split(r"\W+", full) if len(p) >= 4 and p not in GENERIC_NAME_TOKENS]
        if len(parts) >= 2 and all(p in blob_l for p in parts[:2]):
            return item
        if len(parts) == 1 and parts[0] in blob_l:
            return item
    return None


def _host_looks_like_company(host: str, company_name: str) -> bool:
    host_n = re.sub(r"[^a-z0-9]+", "", (host or "").lower().replace("www.", ""))
    parts = [p for p in re.split(r"\W+", company_name.lower()) if len(p) >= 4 and p not in GENERIC_NAME_TOKENS]
    if not parts:
        return False
    return any(p in host_n for p in parts)


def _guess_track(blob: str, allowed: list[str]) -> str:
    allowed = allowed or list(TRACKS.keys())
    scores = {t: 0 for t in allowed}
    for track in allowed:
        for kw in TRACKS[track]["keywords"]:
            if kw in blob:
                scores[track] += 1
    if not scores:
        return "operational_pain"
    best = max(scores, key=scores.get)
    return best if scores[best] else allowed[0]


def _origin(url: str) -> str:
    parsed = urlparse(url)
    return f"{parsed.scheme}://{parsed.netloc}"


def _clean_name(title: str) -> str:
    title = re.split(r"\s[\|\-–—:]\s", title)[0]
    title = re.sub(r"\s+", " ", title).strip()
    return title[:180]


def _norm_name(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", name.lower())


def _payload(data: dict) -> str:
    import json

    return json.dumps(data)

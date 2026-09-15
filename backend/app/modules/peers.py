import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urljoin, urlparse

from app.logging_util import log_event
from app.modules.page_type import (
    homepage_from_article_path,
    is_publisher_host,
    looks_like_article_page,
    looks_like_operating_company,
    should_skip_search_result,
)
from app.modules.research import _fetch_page


# Product categories first. Broad service words like "beauty" or "shop" come later
# so a perfume brand is not classified as a salon or generic store.
_PROFILES = [
    {
        "label": "fragrance and perfume brand",
        "keys": ("fragrance", "perfume", "cologne", "eau de parfum", "eau de toilette", "scented oil", "essential oil"),
        "must": ("fragrance", "perfume", "cologne", "parfum", "scent", "essential oil", "aroma"),
        "reject": ("dental", "clinic", "hospital", "law firm", "advocate", "garage", "real estate", "logistics", "safari"),
        "queries": (
            "perfume brand Kenya",
            "fragrance manufacturer Kenya",
            '"essential oils" Kenya company',
        ),
    },
    {
        "label": "cosmetics and skincare brand",
        "keys": ("skincare", "cosmetics", "makeup brand", "lotion", "serum", "shea butter"),
        "must": ("skincare", "cosmetic", "makeup", "lotion", "serum", "beauty product"),
        "reject": ("dental", "clinic", "hospital", "hair salon", "barber"),
        "queries": ("skincare brand Kenya", "cosmetics manufacturer Kenya", "natural beauty products Kenya"),
    },
    {
        "label": "real estate agency",
        "keys": ("real estate", "property letting", "apartment", "airbnb host"),
        "must": ("real estate", "property", "apartment", "letting", "rent"),
        "reject": ("perfume", "clinic", "software"),
        "queries": ("real estate agency Nairobi", "property management Kenya"),
    },
    {
        "label": "clinic",
        "keys": ("clinic", "hospital", "dental", "doctor", "pharmacy", "optometrist"),
        "must": ("clinic", "hospital", "dental", "doctor", "patient", "pharmacy"),
        "reject": ("perfume", "fragrance", "software agency"),
        "queries": ("clinic Nairobi Kenya", "dental clinic Kenya"),
    },
    {
        "label": "school",
        "keys": ("school", "college", "training academy", "tuition"),
        "must": ("school", "college", "academy", "student", "tuition"),
        "reject": ("perfume", "clinic"),
        "queries": ("school Nairobi Kenya", "training college Kenya"),
    },
    {
        "label": "travel agency",
        "keys": ("safari", "tour operator", "travel agency", "holiday package"),
        "must": ("safari", "tour", "travel", "holiday"),
        "reject": ("perfume", "clinic", "software"),
        "queries": ("tour operator Kenya", "safari company Kenya"),
    },
    {
        "label": "hair and beauty salon",
        "keys": ("hair salon", "nail salon", "barber", "beauty salon"),
        "must": ("salon", "barber", "hair", "nails"),
        "reject": ("perfume brand", "manufacturer", "clinic"),
        "queries": ("hair salon Nairobi", "barbershop Kenya"),
    },
    {
        "label": "restaurant",
        "keys": ("restaurant", "hotel", "cafe", "catering", "bakery"),
        "must": ("restaurant", "hotel", "cafe", "menu", "catering"),
        "reject": ("perfume", "software", "clinic"),
        "queries": ("restaurant Nairobi Kenya", "hotel Kenya official"),
    },
    {
        "label": "events company",
        "keys": ("event planner", "wedding planner", "conference", "photography studio"),
        "must": ("event", "wedding", "conference", "photography"),
        "reject": ("perfume", "clinic"),
        "queries": ("event planner Nairobi", "wedding company Kenya"),
    },
    {
        "label": "logistics company",
        "keys": ("logistics", "courier", "freight", "transport company"),
        "must": ("logistics", "courier", "freight", "delivery", "transport"),
        "reject": ("perfume", "clinic", "salon"),
        "queries": ("logistics company Kenya", "courier Nairobi"),
    },
    {
        "label": "construction company",
        "keys": ("construction", "contractor", "plumbing contractor"),
        "must": ("construction", "contractor", "building"),
        "reject": ("perfume", "clinic"),
        "queries": ("construction company Kenya", "contractor Nairobi"),
    },
    {
        "label": "law firm",
        "keys": ("law firm", "advocate", "attorney"),
        "must": ("law", "advocate", "attorney", "legal"),
        "reject": ("perfume", "clinic"),
        "queries": ("law firm Nairobi Kenya", "advocates Kenya"),
    },
    {
        "label": "accounting firm",
        "keys": ("accountant", "bookkeeping", "audit firm"),
        "must": ("account", "bookkeep", "audit", "tax"),
        "reject": ("perfume", "clinic"),
        "queries": ("accounting firm Nairobi", "auditors Kenya"),
    },
    {
        "label": "gym",
        "keys": ("gym", "fitness centre", "yoga studio"),
        "must": ("gym", "fitness", "yoga"),
        "reject": ("perfume", "clinic"),
        "queries": ("gym Nairobi Kenya", "fitness studio Kenya"),
    },
    {
        "label": "digital agency",
        "keys": ("digital marketing", "web design", "seo agency", "advertising agency"),
        "must": ("marketing", "seo", "web design", "branding", "agency"),
        "reject": ("perfume", "clinic", "hospital"),
        "queries": ("digital marketing agency Nairobi", "web design agency Kenya"),
    },
    {
        "label": "software company",
        "keys": ("software", "saas", "automation company", "developer"),
        "must": ("software", "saas", "app", "developer"),
        "reject": ("perfume", "clinic"),
        "queries": ("software company Kenya", "saas Kenya"),
    },
    {
        "label": "ecommerce shop",
        "keys": ("online shop", "ecommerce", "wholesale"),
        "must": ("shop", "store", "buy online", "wholesale"),
        "reject": ("clinic", "hospital"),
        "queries": ("online shop Kenya", "ecommerce Kenya"),
    },
]


def guess_industry(name: str, research: dict, extra: str = "") -> str:
    return industry_profile(name, research, extra)["label"]


def industry_profile(name: str, research: dict, extra: str = "") -> dict:
    text = f"{name} {extra} {(research.get('text') or '')[:8000]}".lower()
    for profile in _PROFILES:
        if any(k in text for k in profile["keys"]):
            return profile
    # Distinctive nouns from the site, so we do not fall back to generic services.
    hints = _product_hints(text)
    label = " ".join(hints[:3]) + " company" if hints else "Kenya product brand"
    must = tuple(hints[:6]) or ("kenya",)
    queries = tuple(f"{h} Kenya company" for h in hints[:3]) or ("Kenya manufacturer official website", "Kenya brand official website")
    return {
        "label": label.strip(),
        "keys": must,
        "must": must,
        "reject": ("dental", "clinic", "hospital", "law firm", "safari", "real estate"),
        "queries": queries,
    }


PEER_BUDGET_SECONDS = 28.0
_SKIP_HOSTS = (
    "facebook.com",
    "fb.com",
    "instagram.com",
    "linkedin.com",
    "tiktok.com",
    "twitter.com",
    "x.com",
    "youtube.com",
    "google.com",
    "maps.google.",
    "jumia.co.ke",
    "amazon.com",
    "ebay.com",
)


def find_better_companies(run_id: int, name: str, website: str, research: dict) -> list[dict]:
    host = (urlparse(website or "").netloc or "").replace("www.", "").lower()
    extra = " ".join([research.get("text") or "", website or ""])
    profile = industry_profile(name, research, extra)
    log_event(run_id, "peer_industry", f"Searching {profile['label']}")
    deadline = time.monotonic() + PEER_BUDGET_SECONDS
    queries = _peer_queries(profile, name)
    hits = _search_many(run_id, queries, deadline)
    right = _collect_from_hits(run_id, hits, {host} if host else set(), profile, strict=True, deadline=deadline)
    if len(right) < 3 and time.monotonic() < deadline - 2:
        extra_hits = _search_many(run_id, _broad_queries(profile), deadline)
        seen = {urlparse(r.get("website") or "").netloc.lower().replace("www.", "") for r in right}
        if host:
            seen.add(host)
        right.extend(_collect_from_hits(run_id, extra_hits, seen, profile, strict=False, deadline=deadline))
    return _rank(_dedupe(right))[:6]


def _peer_queries(profile: dict, name: str) -> list[str]:
    label = (profile.get("label") or "Kenya company").strip()
    must = [m for m in (profile.get("must") or ()) if m][:3]
    queries = list(profile.get("queries") or [])
    queries.extend(
        [
            f"{label} Kenya",
            f"{label} Nairobi",
            f"{label} Kenya official website",
        ]
    )
    for word in must:
        queries.append(f"{word} Kenya company")
        queries.append(f"{word} Nairobi")
    if (name or "").strip() and len(name.strip()) > 2:
        queries.append(f"{name.strip()} similar companies Kenya")
    out: list[str] = []
    seen: set[str] = set()
    for q in queries:
        key = " ".join((q or "").split()).lower()
        if key and key not in seen:
            seen.add(key)
            out.append(q)
        if len(out) >= 8:
            break
    return out


def _broad_queries(profile: dict) -> list[str]:
    label = (profile.get("label") or "").strip()
    must = (profile.get("must") or ("kenya",))[0]
    return [
        f"{must} Kenya official site",
        f"{label} company website",
        f"{must} Nairobi -list -top",
    ]


def _search_many(run_id: int, queries: list[str], deadline: float) -> list:
    from app.providers.factory import get_search_provider

    provider = get_search_provider()
    rows: list = []
    remain = max(0.4, deadline - time.monotonic())
    pool = ThreadPoolExecutor(max_workers=3)
    try:
        futs = {pool.submit(_safe_search, provider, q): q for q in queries[:6]}
        try:
            for fut in as_completed(futs, timeout=remain):
                q = futs[fut]
                try:
                    found = fut.result() or []
                except Exception:
                    found = []
                log_event(run_id, "search", f"peers: {q} → {len(found)} hits")
                rows.extend(found)
        except Exception:
            pass
    finally:
        pool.shutdown(wait=False, cancel_futures=True)
    return rows


def _safe_search(provider, query: str) -> list:
    try:
        return provider.search(query, max_results=12) or []
    except Exception:
        return []


def _collect_from_hits(
    run_id: int,
    hits: list,
    seen_hosts: set[str],
    profile: dict,
    strict: bool,
    deadline: float,
) -> list[dict]:
    candidates: list[dict] = []
    local_seen = set(seen_hosts)
    listings: list[str] = []
    for row in hits:
        if time.monotonic() >= deadline:
            break
        raw = (getattr(row, "url", None) or "").strip()
        url = homepage_from_article_path(raw)
        host = urlparse(url).netloc.lower().replace("www.", "")
        if not url.startswith("http") or not host or host in local_seen:
            continue
        if _skip_host(host):
            continue
        title_for_filter = getattr(row, "title", "") if url == raw else host
        snippet = (getattr(row, "snippet", None) or "").strip()[:220]
        blob = f"{title_for_filter} {snippet} {url}".lower()
        if is_publisher_host(host) or should_skip_search_result(url, title_for_filter, snippet):
            local_seen.add(host)
            listings.append(url)
            continue
        if strict and not _on_topic(blob, profile, strict=True):
            continue
        if not strict and not _on_topic(blob, profile, strict=False):
            # Still skip obvious off-topic rejects.
            if any(r in blob for r in (profile.get("reject") or ()) if r):
                continue
        local_seen.add(host)
        title = (getattr(row, "title", None) or host).split("|")[0].split(" - ")[0].strip()[:80]
        candidates.append(
            {
                "name": title or host,
                "website": url,
                "snippet": snippet,
                "kind": "industry",
                "industry": profile["label"],
                "profile": profile,
            }
        )
        if len(candidates) >= 14:
            break
    if len(candidates) < 8:
        for listing_url in listings[:2]:
            if time.monotonic() >= deadline:
                break
            harvested = _harvest_listing(run_id, listing_url, local_seen, profile, deadline)
            candidates.extend(harvested)
            for row_h in harvested:
                h = urlparse(row_h.get("website") or "").netloc.lower().replace("www.", "")
                if h:
                    local_seen.add(h)
            if len(candidates) >= 14:
                break
    return _verify_companies(run_id, candidates, 8, deadline)


def find_peer_companies(run_id: int, name: str, website: str, research: dict, gap: dict) -> dict:
    profile = industry_profile(name, research)
    right = find_better_companies(run_id, name, website, research)
    return {"industry": profile["label"], "similar": [], "doing_it_right": right}


def _verify_companies(run_id: int, candidates: list[dict], limit: int, deadline: float | None = None) -> list[dict]:
    if not candidates:
        return []
    kept: list[dict] = []
    remain = 12.0
    if deadline is not None:
        remain = max(0.5, deadline - time.monotonic())
    pool = ThreadPoolExecutor(max_workers=4)
    try:
        futures = {pool.submit(_confirm_company, cand): cand for cand in candidates}
        try:
            for fut in as_completed(futures, timeout=remain):
                try:
                    row = fut.result()
                except Exception:
                    row = None
                if not row:
                    continue
                kept.append(row)
                if len(kept) >= limit:
                    break
        except Exception:
            pass
    finally:
        pool.shutdown(wait=False, cancel_futures=True)
    log_event(run_id, "peer_filter", f"kept {len(kept)} related companies from {len(candidates)} hits")
    return kept[:limit]


def _confirm_company(cand: dict) -> dict | None:
    url = cand.get("website") or ""
    profile = cand.get("profile") or {}
    industry = cand.get("industry") or profile.get("label") or "this space"
    page = None
    try:
        page = _fetch_page(url, timeout=5, skip_robots=True)
    except Exception:
        page = None
    if page:
        title = page.get("title") or cand.get("name") or ""
        text = page.get("text") or ""
        html = page.get("html_sample") or ""
        blob = f"{title} {text[:4000]} {cand.get('snippet') or ''}".lower()
        final = page.get("url") or url
        if looks_like_article_page(title, text, url, html[:2500]):
            return None
        if "account suspended" in title.lower() or "cgi-sys/suspendedpage" in final.lower():
            return None
        if not _on_topic(blob, profile, strict=False):
            if any(r in blob for r in (profile.get("reject") or ()) if r):
                return None
        name = (title or cand.get("name") or final).split("|")[0].split(" - ")[0].strip()[:80]
        snippet = (page.get("description") or cand.get("snippet") or "").strip()[:220]
        why, evidence = _relevance(blob, industry, looks_like_operating_company(title, text, url, html[:2500]), profile)
        return {
            "name": name or cand.get("name"),
            "website": final,
            "snippet": snippet,
            "why": why,
            "evidence": evidence,
            "kind": cand.get("kind"),
        }
    snippet_blob = f"{cand.get('name')} {cand.get('snippet')}"
    if any(r in snippet_blob.lower() for r in (profile.get("reject") or ()) if r) and not _on_topic(snippet_blob, profile, strict=False):
        return None
    return {
        "name": cand.get("name"),
        "website": url,
        "snippet": cand.get("snippet") or "",
        "why": f"Search lists this as a {industry}. The homepage could not be fully read, so that is not confirmed.",
        "evidence": [],
        "kind": cand.get("kind"),
    }


def _on_topic(blob: str, profile: dict, strict: bool = True) -> bool:
    low = (blob or "").lower()
    must = [m for m in (profile.get("must") or ()) if m]
    keys = [k for k in (profile.get("keys") or ()) if k]
    reject = [r for r in (profile.get("reject") or ()) if r]
    must_hits = sum(1 for m in must if m in low)
    key_hits = sum(1 for k in keys if k in low)
    reject_hits = sum(1 for r in reject if r in low)
    if reject_hits and must_hits == 0 and key_hits == 0:
        return False
    if must and must_hits == 0:
        if strict:
            return False
        return key_hits > 0 or "kenya" in low or "nairobi" in low
    return True


def _skip_host(host: str) -> bool:
    host = (host or "").lower()
    return any(host == h or host.endswith("." + h) or h in host for h in _SKIP_HOSTS)


def _harvest_listing(run_id: int, url: str, seen_hosts: set[str], profile: dict, deadline: float) -> list[dict]:
    if time.monotonic() >= deadline - 1:
        return []
    try:
        page = _fetch_page(url, timeout=4, skip_robots=True)
    except Exception:
        page = None
    if not page:
        return []
    base = page.get("url") or url
    found: list[dict] = []
    local = set(seen_hosts)
    for href in page.get("links") or []:
        if time.monotonic() >= deadline:
            break
        raw = urljoin(base, (href or "").strip())
        if not raw.startswith("http"):
            continue
        home = homepage_from_article_path(raw)
        host = urlparse(home).netloc.lower().replace("www.", "")
        if not host or host in local or _skip_host(host) or is_publisher_host(host):
            continue
        if should_skip_search_result(home, host, ""):
            continue
        title = host.split(".")[0].replace("-", " ").title()
        blob = f"{title} {home}".lower()
        if not _on_topic(blob, profile, strict=False) and any(r in blob for r in (profile.get("reject") or ()) if r):
            continue
        local.add(host)
        found.append(
            {
                "name": title,
                "website": home,
                "snippet": "",
                "kind": "industry",
                "industry": profile["label"],
                "profile": profile,
            }
        )
        if len(found) >= 8:
            break
    log_event(run_id, "peer_harvest", f"{url} → {len(found)} company links")
    return found


def _dedupe(rows: list[dict]) -> list[dict]:
    out: list[dict] = []
    seen: set[str] = set()
    for row in rows:
        host = urlparse(row.get("website") or "").netloc.lower().replace("www.", "")
        if not host or host in seen:
            continue
        seen.add(host)
        out.append(row)
    return out


def _relevance(blob: str, industry: str, operating: bool, profile: dict) -> tuple[str, list[str]]:
    low = (blob or "").lower()
    matched = [m for m in (profile.get("must") or ()) if m in low][:4]
    evidence = matched[:]
    if matched:
        return (
            f"Same line of work ({industry}). Public pages mention {', '.join(matched)}.",
            evidence,
        )
    if operating:
        return (f"Looks like an operating {industry}. Northline did not confirm a deeper product overlap.", [])
    return (f"Appears related to {industry} from the listing. Overlap was not confirmed on the page.", [])


def _rank(rows: list[dict]) -> list[dict]:
    return sorted(rows, key=lambda r: (-len(r.get("evidence") or []), r.get("name") or ""))


def _product_hints(text: str) -> list[str]:
    stop = {
        "kenya",
        "nairobi",
        "contact",
        "about",
        "home",
        "whatsapp",
        "phone",
        "email",
        "follow",
        "company",
        "limited",
        "ltd",
        "the",
        "and",
        "for",
        "your",
        "with",
        "from",
        "this",
        "that",
        "have",
        "will",
        "our",
        "you",
    }
    words = []
    for raw in text.replace("/", " ").split():
        word = "".join(ch for ch in raw.lower() if ch.isalpha())
        if len(word) < 5 or word in stop:
            continue
        if word not in words:
            words.append(word)
        if len(words) >= 8:
            break
    return words

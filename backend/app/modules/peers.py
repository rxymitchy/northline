from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urlparse

from app.logging_util import log_event
from app.modules.page_type import (
    homepage_from_article_path,
    is_publisher_host,
    looks_like_article_page,
    looks_like_operating_company,
    should_skip_search_result,
)
from app.modules.research import _fetch_page
from app.providers.factory import get_search_provider


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
    queries = tuple(f'"{h}" Kenya company' for h in hints[:3]) or ("Kenya manufacturer official website",)
    return {
        "label": label.strip(),
        "keys": must,
        "must": must,
        "reject": ("dental", "clinic", "hospital", "law firm", "safari", "real estate"),
        "queries": queries,
    }


def find_peer_companies(run_id: int, name: str, website: str, research: dict, gap: dict) -> dict:
    profile = industry_profile(name, research)
    right = find_better_companies(run_id, name, website, research)
    return {"industry": profile["label"], "similar": [], "doing_it_right": right}


def find_better_companies(run_id: int, name: str, website: str, research: dict) -> list[dict]:
    host = (urlparse(website or "").netloc or "").replace("www.", "").lower()
    extra = " ".join([research.get("text") or "", website or ""])
    profile = industry_profile(name, research, extra)
    log_event(run_id, "peer_industry", f"Searching {profile['label']}")
    provider = get_search_provider()
    queries = list(profile.get("queries") or [])
    queries.append(f"{profile['label']} Kenya")
    right: list[dict] = []
    seen = {host} if host else set()
    for query in queries:
        for row in _collect(run_id, provider, query, seen, profile, limit=10):
            h = urlparse(row.get("website") or "").netloc.lower().replace("www.", "")
            if not h or h in seen:
                continue
            seen.add(h)
            right.append(row)
            if len(right) >= 6:
                return _rank(right)[:6]
    return _rank(right)[:6]


def _collect(run_id: int, provider, query: str, seen_hosts: set[str], profile: dict, limit: int) -> list[dict]:
    try:
        rows = provider.search(query, max_results=12)
        log_event(run_id, "search", f"peers: {query} → {len(rows)} hits")
    except Exception as exc:
        log_event(run_id, "search_error", str(exc), level="warning")
        return []
    candidates: list[dict] = []
    local_seen = set(seen_hosts)
    for row in rows:
        raw = (row.url or "").strip()
        url = homepage_from_article_path(raw)
        host = urlparse(url).netloc.lower().replace("www.", "")
        if not url.startswith("http") or not host or host in local_seen:
            continue
        title_for_filter = row.title if url == raw else host
        snippet = (row.snippet or "").strip()[:220]
        blob = f"{title_for_filter} {snippet} {url}".lower()
        if is_publisher_host(host) or should_skip_search_result(url, title_for_filter, snippet):
            continue
        if not _on_topic(blob, profile):
            continue
        local_seen.add(host)
        title = (row.title or host).split("|")[0].split(" - ")[0].strip()[:80]
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
        if len(candidates) >= limit + 4:
            break
    return _verify_companies(run_id, candidates, limit)


def _verify_companies(run_id: int, candidates: list[dict], limit: int) -> list[dict]:
    if not candidates:
        return []
    kept: list[dict] = []
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = {pool.submit(_confirm_company, cand): cand for cand in candidates}
        for fut in as_completed(futures):
            try:
                row = fut.result()
            except Exception:
                row = None
            if not row:
                continue
            kept.append(row)
            if len(kept) >= limit:
                break
    log_event(run_id, "peer_filter", f"kept {len(kept)} related companies from {len(candidates)} hits")
    return kept[:limit]


def _confirm_company(cand: dict) -> dict | None:
    url = cand.get("website") or ""
    profile = cand.get("profile") or {}
    industry = cand.get("industry") or profile.get("label") or "this space"
    page = None
    try:
        page = _fetch_page(url, timeout=6, skip_robots=True)
    except Exception:
        page = None
    if page:
        title = page.get("title") or cand.get("name") or ""
        text = page.get("text") or ""
        html = page.get("html_sample") or ""
        blob = f"{title} {text[:4000]} {cand.get('snippet') or ''}".lower()
        if looks_like_article_page(title, text, url, html[:2500]):
            return None
        if not _on_topic(blob, profile):
            return None
        final = page.get("url") or url
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
    # No homepage loaded: keep only if the search snippet already looks on-topic.
    if not _on_topic(f"{cand.get('name')} {cand.get('snippet')}", profile):
        return None
    return {
        "name": cand.get("name"),
        "website": url,
        "snippet": cand.get("snippet") or "",
        "why": f"Search lists this as a {industry}. The homepage could not be fully read, so that is not confirmed.",
        "evidence": [],
        "kind": cand.get("kind"),
    }


def _on_topic(blob: str, profile: dict) -> bool:
    low = (blob or "").lower()
    must = [m for m in (profile.get("must") or ()) if m]
    reject = [r for r in (profile.get("reject") or ()) if r]
    must_hits = sum(1 for m in must if m in low)
    reject_hits = sum(1 for r in reject if r in low)
    if reject_hits and must_hits == 0:
        return False
    if must and must_hits == 0:
        return False
    return True


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

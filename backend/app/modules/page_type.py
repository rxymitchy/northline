import re
from urllib.parse import urlparse

PUBLISHER_DOMAINS = {
    "medium.com",
    "substack.com",
    "wikipedia.org",
    "businessdailyafrica.com",
    "standardmedia.co.ke",
    "nation.africa",
    "nation.co.ke",
    "the-star.co.ke",
    "capitalfm.co.ke",
    "kenyans.co.ke",
    "tuko.co.ke",
    "citizen.digital",
    "theeastafrican.co.ke",
    "african.business",
    "techcrunch.com",
    "forbes.com",
    "bloomberg.com",
    "bbc.com",
    "cnn.com",
    "nytimes.com",
    "theguardian.com",
    "clutch.co",
    "goodfirms.co",
    "designrush.com",
    "sortlist.com",
    "g2.com",
    "capterra.com",
    "pickanagency.com",
    "agencyfinder.com",
    "expertise.com",
    "upcity.com",
    "themanifest.com",
    "manifest.com",
    "extract.co.ke",
    "kenyanwallstreet.com",
    "techweez.com",
    "cio.co.ke",
    "meta.com",
    "about.meta.com",
    "yelp.com",
    "tripadvisor.com",
    "quora.com",
    "slideshare.net",
    "scribd.com",
    "issuu.com",
    "youtube.com",
    "tiktok.com",
    "facebook.com",
    "linkedin.com",
    "instagram.com",
    "x.com",
    "twitter.com",
    "reddit.com",
    "pinterest.com",
    "bing.com",
    "google.com",
    "glassdoor.com",
    "softonic.com",
    "originlab.com",
    "crunchbase.com",
    "zoominfo.com",
}

# Hosts whose job is ranking/writing about other companies
LISTING_HOST_BITS = (
    "pickanagency",
    "clutch",
    "goodfirms",
    "designrush",
    "sortlist",
    "agencyfinder",
    "directory",
    "yellowpages",
    "businesslist",
    "hotfrog",
    "cylex",
)

ARTICLE_PATH_BITS = (
    "/blog/",
    "/blogs/",
    "/news/",
    "/article/",
    "/articles/",
    "/press/",
    "/story/",
    "/stories/",
    "/opinion/",
    "/insights/",
    "/resources/",
    "/magazine/",
    "/best-",
    "/top-",
    "/agencies/",
    "/directory/",
    "/reviews/",
    "/roundup/",
    "/list/",
)

LISTICLE_TITLE = re.compile(
    r"("
    r"top\s+\d+|"
    r"best\s+\d+|"
    r"list of|"
    r"how to (?:choose|find|hire)|"
    r"guide to|"
    r"\d+\s+best|"
    r"\d+\s+companies|"
    r"best (?:advertising|digital|marketing|web|seo) agencies|"
    r"top (?:digital )?marketing agenc|"
    r"agencies in kenya|"
    r"companies in kenya|"
    r"best companies to|"
    r"who (?:are|is) the best"
    r")",
    re.I,
)

ABOUT_OTHER_COMPANIES = (
    "best agencies in",
    "top agencies in",
    "agencies in kenya",
    "best advertising agencies",
    "best digital agencies",
    "top digital marketing agencies",
    "we compared",
    "our list of",
    "this list of",
    "ranked the following",
    "visit website",
    "view profile",
    "agency profile",
    "written by",
    "min read",
    "share this article",
    "related articles",
    "last updated",
    "updated on",
    "roundup",
)

FIRST_PERSON_COMPANY = (
    "our services",
    "our team",
    "we help",
    "we build",
    "we design",
    "contact us",
    "get a quote",
    "book a call",
    "work with us",
    "about us",
)


def host_of(url: str) -> str:
    return urlparse(url or "").netloc.lower().replace("www.", "")


def is_publisher_host(host: str) -> bool:
    host = (host or "").lower().replace("www.", "")
    if any(host == d or host.endswith("." + d) for d in PUBLISHER_DOMAINS):
        return True
    return any(bit in host for bit in LISTING_HOST_BITS)


def is_listing_path(url: str) -> bool:
    path = (urlparse(url).path or "").lower()
    norm = path.rstrip("/") + "/"
    return any(bit in norm for bit in ARTICLE_PATH_BITS)


def is_editorial_name(name: str) -> bool:
    text = (name or "").strip()
    if not text:
        return False
    if LISTICLE_TITLE.search(text):
        return True
    if re.match(r"^(top|best|leading)\b.+\b(kenya|nairobi|2024|2025|2026)\b", text, re.I):
        return True
    return False


def should_skip_search_result(url: str, title: str, snippet: str = "") -> str | None:
    """Skip pages that are about companies, not the company itself."""
    host = host_of(url)
    blob = f"{title} {snippet}".lower()
    if is_publisher_host(host):
        return f"Third-party article/listing site ({host}), not the company's own website"
    if is_listing_path(url) and LISTICLE_TITLE.search(title or blob):
        return "URL is a ranking/list article about companies, not a company homepage"
    if is_editorial_name(title or ""):
        return f"Search title is editorial ('{title[:80]}'), not a company name"
    about_hits = sum(1 for p in ABOUT_OTHER_COMPANIES if p in blob)
    if about_hits >= 2:
        return "Snippet describes a roundup/article about agencies, not one company"
    if "best advertising agencies" in blob or "top digital marketing agencies" in blob:
        return "List article about agencies, not a company site"
    return None


def not_a_company_site_reason(title: str, text: str, url: str, html_sample: str = "") -> str | None:
    """After fetch: reject media/review/list pages that write about other businesses."""
    if is_publisher_host(host_of(url)):
        return f"Host {host_of(url)} publishes content about companies, it is not a company site"
    if is_editorial_name(title or ""):
        return f"Page title is a listicle/article headline, not a company: {title[:100]}"
    low = f"{title}\n{text[:4000]}\n{html_sample[:2000]}".lower()
    about = sum(1 for p in ABOUT_OTHER_COMPANIES if p in low)
    first_person = sum(1 for p in FIRST_PERSON_COMPANY if p in low)
    if about >= 3 and first_person < 2:
        return "Page reads as an article or directory listing other companies, not this company's own site"
    if "og:type" in (html_sample or "").lower() and 'content="article"' in (html_sample or "").lower() and first_person < 2:
        return "Page is marked as an article (og:type=article), not a company homepage"
    return None


def looks_like_article_page(title: str, text: str, url: str, html_sample: str = "") -> bool:
    return not_a_company_site_reason(title, text, url, html_sample) is not None


def homepage_from_article_path(url: str) -> str:
    parsed = urlparse(url)
    path = (parsed.path or "/").lower().rstrip("/") + "/"
    # Own-site blog posts → use origin. Listing paths on third-party hosts are skipped elsewhere.
    own_blog = ("/blog/", "/blogs/", "/news/", "/article/", "/articles/", "/press/", "/insights/")
    if any(bit in path for bit in own_blog) and not is_publisher_host(parsed.netloc):
        return f"{parsed.scheme}://{parsed.netloc}"
    return url

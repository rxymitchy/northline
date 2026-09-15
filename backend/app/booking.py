"""Public scheduling CTA. Visitors book on Calendly instead of waiting for a follow-up email."""

from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from app.config import settings

DEFAULT_CALENDLY = "https://calendly.com/lucianamitchell19/northline-business-automation"


def configured_booking_url() -> str:
    return normalize_booking_url((settings.booking_url or "").strip() or DEFAULT_CALENDLY)


def calendly_href(base: str, name: str = "", email: str = "") -> str:
    parsed = urlparse(normalize_booking_url(base))
    if not parsed.netloc:
        return ""
    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    if (name or "").strip():
        query["name"] = name.strip()
    if (email or "").strip():
        query["email"] = email.strip()
    return urlunparse(parsed._replace(query=urlencode(query)))


def is_calendly(url: str) -> bool:
    host = urlparse(url or "").netloc.lower().replace("www.", "")
    return host == "calendly.com" or host.endswith(".calendly.com")


def normalize_booking_url(raw: str) -> str:
    url = (raw or "").strip().strip("\"'")
    if not url:
        return ""
    if url.startswith("//"):
        url = "https:" + url
    parsed = urlparse(url)
    if not parsed.scheme:
        url = "https://" + url.lstrip("/")
        parsed = urlparse(url)
    if parsed.scheme == "http":
        url = "https://" + url[len("http://") :]
        parsed = urlparse(url)
    if parsed.scheme != "https" or not parsed.netloc:
        return ""
    return url

"""Public scheduling CTA. Visitors book on Calendly instead of waiting for a follow-up email."""

from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from app.config import settings


def configured_booking_url() -> str:
    return _https_url((settings.booking_url or "").strip())


def calendly_href(base: str, name: str = "", email: str = "") -> str:
    parsed = urlparse(_https_url(base))
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


def _https_url(raw: str) -> str:
    url = (raw or "").strip()
    parsed = urlparse(url)
    if parsed.scheme != "https" or not parsed.netloc:
        return ""
    return url

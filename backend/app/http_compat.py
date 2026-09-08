"""HTTP helpers that avoid Avast's Python SSL hook (aswMonFltProxy)."""

from __future__ import annotations

import json

import primp

from app.config import settings


def _client(timeout: float | None = None):
    return primp.Client(
        verify=False,
        timeout=timeout or 30,
        follow_redirects=True,
    )


def http_get(url: str, timeout: float | None = None, headers: dict | None = None):
    client = _client(timeout or settings.fetch_timeout_seconds)
    hdrs = {"User-Agent": settings.user_agent, "Accept": "text/html,application/xhtml+xml", **(headers or {})}
    return client.get(url, headers=hdrs)


def http_post_json(url: str, payload: dict, headers: dict | None = None, timeout: float = 60):
    client = _client(timeout)
    hdrs = {"Content-Type": "application/json", **(headers or {})}
    return client.post(url, headers=hdrs, json=payload)


def response_text(resp) -> str:
    text = getattr(resp, "text", None)
    if isinstance(text, str):
        return text
    content = getattr(resp, "content", b"") or b""
    if isinstance(content, bytes):
        return content.decode("utf-8", errors="replace")
    return str(content)


def response_header(resp, name: str, default: str = "") -> str:
    headers = resp.headers or {}
    for key, value in headers.items():
        if key.lower() == name.lower():
            return str(value)
    return default

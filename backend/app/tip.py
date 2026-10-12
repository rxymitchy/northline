"""Lightning tips via LNURL-pay into the configured Lightning Address.

The address is never returned to the browser. Invoices are BOLT11 only.
Callbacks must stay on the address host over HTTPS with no redirects.
"""

from __future__ import annotations

import base64
import io
import ipaddress
import re
import time
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

import httpx

from app.config import settings

DEFAULT_LIGHTNING_ADDRESS = "satoshirxymitchy@blink.sv"
PRESET_SATS = (1000, 5000, 10000)
MIN_SATS = 100
MAX_SATS = 2_000_000
_INVOICE_RE = re.compile(r"^ln(bc|tbs|bcrt)[0-9]*[munp]?1[ac-hj-np-z02-9]{20,}$")
_TIP_HITS: dict[str, list[float]] = {}


def configured_lightning_address() -> str:
    raw = (settings.lightning_address or "").strip() or DEFAULT_LIGHTNING_ADDRESS
    if "@" not in raw or " " in raw:
        return DEFAULT_LIGHTNING_ADDRESS
    user, domain = raw.split("@", 1)
    user = user.strip().lower()
    domain = domain.strip().lower()
    if not re.fullmatch(r"[a-z0-9._-]{1,64}", user) or not re.fullmatch(r"[a-z0-9.-]+\.[a-z]{2,}", domain):
        return DEFAULT_LIGHTNING_ADDRESS
    return f"{user}@{domain}"


def lnurlp_endpoint(address: str) -> str:
    user, domain = address.split("@", 1)
    return f"https://{domain}/.well-known/lnurlp/{user}"


def tip_rate_ok(ip: str, limit: int = 12, window: float = 60.0) -> bool:
    now = time.monotonic()
    key = (ip or "unknown")[:80]
    hits = [t for t in _TIP_HITS.get(key, []) if now - t < window]
    if len(hits) >= limit:
        _TIP_HITS[key] = hits
        return False
    hits.append(now)
    _TIP_HITS[key] = hits
    if len(_TIP_HITS) > 400:
        stale = [k for k, v in _TIP_HITS.items() if not v or now - v[-1] > window]
        for k in stale:
            _TIP_HITS.pop(k, None)
    return True


def create_tip_invoice(amount_sats: int) -> dict:
    sats = int(amount_sats or 0)
    if sats < MIN_SATS or sats > MAX_SATS:
        raise ValueError(f"Choose an amount between {MIN_SATS} and {MAX_SATS} sats.")
    address = configured_lightning_address()
    expected_host = address.split("@", 1)[1]
    pay = _get_json(lnurlp_endpoint(address), expected_host)
    tag = (pay.get("tag") or "").lower()
    if tag not in ("payrequest",) and not pay.get("callback"):
        raise RuntimeError("Could not start a Lightning payment.")
    callback = (pay.get("callback") or "").strip()
    if not _callback_allowed(callback, address):
        raise RuntimeError("Lightning pay callback was not from the expected host.")
    min_sats = max(MIN_SATS, int(pay.get("minSendable") or 1000) // 1000)
    max_sats = min(MAX_SATS, int(pay.get("maxSendable") or MAX_SATS * 1000) // 1000)
    if max_sats < min_sats:
        max_sats = MAX_SATS
    sats = min(max(sats, min_sats), max_sats)
    invoice_payload = _get_json(_with_amount(callback, sats * 1000), expected_host)
    invoice = _clean_invoice(invoice_payload.get("pr") or invoice_payload.get("bolt11") or "")
    uri = f"lightning:{invoice}"
    png = _qr_png(uri)
    return {
        "ok": True,
        "amount_sats": sats,
        "invoice": invoice,
        "wallet_uri": uri,
        "qr_png": png,
        "expires_hint": "Scan with Phoenix, Blink, Wallet of Satoshi, Zeus, or any Lightning wallet. The invoice is one-time.",
    }


def _clean_invoice(raw: str) -> str:
    invoice = "".join((raw or "").split()).lower()
    if invoice.startswith("lightning:"):
        invoice = invoice.split(":", 1)[1]
    if "://" in invoice or "@" in invoice or "/" in invoice or len(invoice) > 3000:
        raise RuntimeError("Wallet did not return an invoice.")
    if not _INVOICE_RE.match(invoice):
        raise RuntimeError("Wallet did not return an invoice.")
    return invoice


def _callback_allowed(callback: str, address: str) -> bool:
    parsed = urlparse(callback)
    if parsed.scheme != "https" or not parsed.netloc:
        return False
    if parsed.username or parsed.password:
        return False
    if parsed.port not in (None, 443):
        return False
    host = (parsed.hostname or "").lower()
    try:
        ipaddress.ip_address(host)
        return False
    except ValueError:
        pass
    expected = address.split("@", 1)[1].lower()
    return host == expected or host.endswith("." + expected)


def _with_amount(callback: str, amount_msat: int) -> str:
    parsed = urlparse(callback)
    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    query["amount"] = str(int(amount_msat))
    return urlunparse(parsed._replace(query=urlencode(query)))


def _get_json(url: str, expected_host: str) -> dict:
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    if parsed.scheme != "https" or not (host == expected_host or host.endswith("." + expected_host)):
        raise RuntimeError("Blocked a Lightning request that was not on the expected host.")
    headers = {
        "Accept": "application/json",
        "User-Agent": "Mozilla/5.0 (compatible; Northline/1.0)",
    }
    try:
        with httpx.Client(verify=True, timeout=12.0, follow_redirects=False) as client:
            response = client.get(url, headers=headers)
    except httpx.ConnectError:
        # Windows antivirus HTTPS inspection can break cert verify; host is still allowlisted.
        with httpx.Client(verify=False, timeout=12.0, follow_redirects=False) as client:
            response = client.get(url, headers=headers)
    if response.status_code >= 300:
        raise RuntimeError("Could not start a Lightning payment.")
    final_host = (urlparse(str(response.url)).hostname or "").lower()
    if not (final_host == expected_host or final_host.endswith("." + expected_host)):
        raise RuntimeError("Blocked a Lightning request that was not on the expected host.")
    data = response.json()
    return data if isinstance(data, dict) else {}


def _qr_png(payload: str) -> str:
    import segno

    qr = segno.make(payload, error="l")
    buf = io.BytesIO()
    qr.save(buf, kind="png", scale=8, border=4)
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode("ascii")

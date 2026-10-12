"""Lightning tips via LNURL-pay.

Breez Spark would create a separate wallet. This path requests a BOLT11 invoice
from the configured Lightning Address (Blink) so sats land in that account.
The address is never returned to the browser — visitors scan a QR or open a wallet URI.
"""

from __future__ import annotations

import io
import json
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

import httpx

from app.config import settings

DEFAULT_LIGHTNING_ADDRESS = "satoshirxymitchy@blink.sv"
PRESET_SATS = (1000, 5000, 21000)
MIN_SATS = 100
MAX_SATS = 2_000_000


def configured_lightning_address() -> str:
    raw = (settings.lightning_address or "").strip() or DEFAULT_LIGHTNING_ADDRESS
    if "@" not in raw or " " in raw:
        return DEFAULT_LIGHTNING_ADDRESS
    user, domain = raw.split("@", 1)
    if not user or "." not in domain:
        return DEFAULT_LIGHTNING_ADDRESS
    return f"{user}@{domain.lower()}"


def lnurlp_endpoint(address: str) -> str:
    user, domain = address.split("@", 1)
    return f"https://{domain}/.well-known/lnurlp/{user}"


def create_tip_invoice(amount_sats: int) -> dict:
    sats = int(amount_sats or 0)
    if sats < MIN_SATS or sats > MAX_SATS:
        raise ValueError(f"Choose an amount between {MIN_SATS} and {MAX_SATS} sats.")
    address = configured_lightning_address()
    pay = _get_json(lnurlp_endpoint(address))
    if (pay.get("tag") or "").lower() != "payrequest" and pay.get("tag") != "payRequest":
        if pay.get("status") == "ERROR":
            raise RuntimeError(pay.get("reason") or "Could not start a Lightning payment.")
        if not pay.get("callback"):
            raise RuntimeError("Could not start a Lightning payment.")
    callback = (pay.get("callback") or "").strip()
    if not _callback_allowed(callback, address):
        raise RuntimeError("Lightning pay callback was not from the expected host.")
    min_sats = max(MIN_SATS, int(pay.get("minSendable") or 1000) // 1000)
    max_sats = min(MAX_SATS, int(pay.get("maxSendable") or MAX_SATS * 1000) // 1000)
    if max_sats < min_sats:
        max_sats = MAX_SATS
    if sats < min_sats:
        sats = min_sats
    if sats > max_sats:
        sats = max_sats
    invoice_payload = _get_json(_with_amount(callback, sats * 1000))
    invoice = (invoice_payload.get("pr") or invoice_payload.get("bolt11") or "").strip()
    if not invoice.lower().startswith("ln"):
        reason = invoice_payload.get("reason") or "Wallet did not return an invoice."
        raise RuntimeError(reason)
    uri = f"lightning:{invoice}"
    return {
        "ok": True,
        "amount_sats": sats,
        "invoice": invoice,
        "wallet_uri": uri,
        "qr_svg": _qr_svg(uri),
        "expires_hint": "Scan with Phoenix, Blink, Wallet of Satoshi, Zeus, or any Lightning wallet. The invoice is one-time.",
    }


def _callback_allowed(callback: str, address: str) -> bool:
    parsed = urlparse(callback)
    if parsed.scheme != "https" or not parsed.netloc:
        return False
    host = parsed.hostname or ""
    expected = address.split("@", 1)[1].lower()
    host = host.lower()
    return host == expected or host.endswith("." + expected)


def _with_amount(callback: str, amount_msat: int) -> str:
    parsed = urlparse(callback)
    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    query["amount"] = str(int(amount_msat))
    return urlunparse(parsed._replace(query=urlencode(query)))


def _get_json(url: str) -> dict:
    headers = {
        "Accept": "application/json",
        "User-Agent": "Mozilla/5.0 (compatible; Northline/1.0)",
    }
    try:
        with httpx.Client(timeout=18, follow_redirects=True) as client:
            response = client.get(url, headers=headers)
            response.raise_for_status()
            data = response.json()
            return data if isinstance(data, dict) else {}
    except Exception:
        from app.http_compat import http_get, response_text

        resp = http_get(url, timeout=18, headers=headers)
        raw = response_text(resp)
        data = json.loads(raw)
        return data if isinstance(data, dict) else {}


def _qr_svg(payload: str) -> str:
    try:
        import segno

        qr = segno.make(payload, error="m")
        buf = io.BytesIO()
        qr.save(buf, kind="svg", xmldecl=False, scale=5, border=2)
        return buf.getvalue().decode("utf-8")
    except Exception:
        return ""

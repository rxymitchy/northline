import re
import smtplib
from email.message import EmailMessage

from app.config import settings


EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}$")


def valid_email(value: str | None) -> bool:
    text = (value or "").strip()
    return bool(text) and len(text) <= 200 and EMAIL_RE.match(text) is not None


def smtp_ready() -> bool:
    host = (settings.smtp_host or "").strip()
    password = (settings.smtp_password or "").strip()
    sender = (settings.smtp_from_email or settings.smtp_username or "").strip()
    return bool(host and sender and password)


def sending_outbound_allowed() -> bool:
    return bool(settings.email_sending_enabled or settings.outbound_send_enabled) and smtp_ready()


def send_email(
    to_email: str,
    subject: str,
    body: str,
    html: str | None = None,
    attachment_html: str | None = None,
    attachment_name: str = "northline-report.html",
) -> dict:
    if not valid_email(to_email):
        return {"sent": False, "reason": "That email address does not look valid.", "code": "invalid_email"}
    if not smtp_ready():
        return {
            "sent": False,
            "code": "smtp_unconfigured",
            "reason": "Email delivery is not connected on this server. Download the full report instead.",
        }
    sender = (settings.smtp_from_email or settings.smtp_username).strip()
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = f"{settings.smtp_from_name} <{sender}>"
    msg["To"] = to_email.strip()
    msg.set_content(body or "Your Northline report is attached.")
    if html:
        msg.add_alternative(html, subtype="html")
    attached = attachment_html if attachment_html is not None else html
    if attached:
        msg.add_attachment(
            attached.encode("utf-8"),
            maintype="text",
            subtype="html",
            filename=attachment_name,
        )
    user = (settings.smtp_username or sender).strip()
    try:
        if settings.smtp_port == 465:
            with smtplib.SMTP_SSL(settings.smtp_host, settings.smtp_port, timeout=30) as server:
                server.login(user, settings.smtp_password)
                server.send_message(msg)
        else:
            with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=30) as server:
                server.ehlo()
                if settings.smtp_use_tls:
                    server.starttls()
                    server.ehlo()
                if user:
                    server.login(user, settings.smtp_password)
                server.send_message(msg)
        return {"sent": True, "code": "sent", "reason": "Sent"}
    except Exception as exc:
        return {
            "sent": False,
            "code": "smtp_error",
            "reason": _public_smtp_error(exc),
        }


def redact_secrets(text: str | None) -> str:
    raw = str(text or "")
    secrets = [
        settings.smtp_password,
        settings.openai_api_key,
        settings.tavily_api_key,
        settings.serper_api_key,
        settings.brave_api_key,
        settings.admin_pin,
    ]
    for secret in secrets:
        if secret and len(secret) > 2:
            raw = raw.replace(secret, "[redacted]")
    return raw[:500]


def _public_smtp_error(exc: Exception) -> str:
    safe = redact_secrets(str(exc)).lower()
    if "authentication" in safe or "535" in safe or "534" in safe:
        return "The mail server rejected the login. Check SMTP settings, then download the report in the meantime."
    if "timed out" in safe or "timeout" in safe:
        return "The mail server did not respond in time. Download the report instead, and try email later."
    if "connection" in safe or "refused" in safe or "name or service not known" in safe:
        return "Could not reach the mail server. Download the report instead."
    return "The report could not be emailed. Download it from this page instead."

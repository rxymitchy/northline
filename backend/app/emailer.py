import smtplib
from email.message import EmailMessage

from app.config import settings


def smtp_ready() -> bool:
    host = (settings.smtp_host or "").strip()
    password = (settings.smtp_password or "").strip()
    sender = (settings.smtp_from_email or settings.smtp_username or "").strip()
    return bool(host and sender and password)


def sending_outbound_allowed() -> bool:
    return bool(settings.email_sending_enabled or settings.outbound_send_enabled) and smtp_ready()


def send_email(to_email: str, subject: str, body: str, html: str | None = None) -> dict:
    if not to_email or "@" not in to_email:
        return {"sent": False, "reason": "No valid recipient email."}
    if not smtp_ready():
        return {
            "sent": False,
            "reason": "Email is not connected yet. Download the full report below.",
        }
    sender = (settings.smtp_from_email or settings.smtp_username).strip()
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = f"{settings.smtp_from_name} <{sender}>"
    msg["To"] = to_email.strip()
    msg.set_content(body)
    if html:
        msg.add_alternative(html, subtype="html")
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
        return {"sent": True, "reason": f"Sent to {to_email}"}
    except Exception as exc:
        return {"sent": False, "reason": str(exc)}

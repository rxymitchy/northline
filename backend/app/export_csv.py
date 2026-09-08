import csv
import io
import json
from datetime import datetime

from sqlalchemy.orm import Session

from app.models import Company, Contact, Outreach


CSV_COLUMNS = [
    "Company",
    "Website",
    "Industry",
    "Location",
    "Contact Name",
    "Contact Role",
    "Contact Email",
    "WhatsApp",
    "Observed Problem",
    "Evidence",
    "Automation Opportunity",
    "Confidence",
    "Lead Score",
    "Recommended Offer",
    "Email Subject",
    "Email Body",
    "Status",
    "Date Discovered",
    "Date Contacted",
    "Follow-up Date",
]


def export_run_csv(db: Session, run_id: int) -> str:
    companies = db.query(Company).filter(Company.run_id == run_id).order_by(Company.lead_score.desc().nullslast()).all()
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=CSV_COLUMNS)
    writer.writeheader()
    for company in companies:
        contact = (
            db.query(Contact).filter(Contact.company_id == company.id).order_by(Contact.id.desc()).first()
        )
        outreach = (
            db.query(Outreach).filter(Outreach.company_id == company.id).order_by(Outreach.id.desc()).first()
        )
        evidence = company.evidence or ""
        try:
            parsed = json.loads(evidence)
            if isinstance(parsed, list):
                evidence = " | ".join(
                    p if isinstance(p, str) else json.dumps(p) for p in parsed
                )
        except Exception:
            pass
        writer.writerow(
            {
                "Company": company.name,
                "Website": company.website or "",
                "Industry": company.industry or "",
                "Location": company.location or "",
                "Contact Name": (contact.name if contact else "") or "",
                "Contact Role": (contact.role if contact else "") or "",
                "Contact Email": (contact.email if contact else "") or "",
                "WhatsApp": company.whatsapp or "",
                "Observed Problem": company.observed_problem or "",
                "Evidence": evidence,
                "Automation Opportunity": company.automation_opportunity or "",
                "Confidence": company.confidence or "",
                "Lead Score": company.lead_score if company.lead_score is not None else "",
                "Recommended Offer": company.recommended_offer or "",
                "Email Subject": (outreach.subject if outreach else "") or "",
                "Email Body": (outreach.body if outreach else "") or "",
                "Status": company.status,
                "Date Discovered": _fmt(company.discovered_at),
                "Date Contacted": _fmt(company.date_contacted or (outreach.date_contacted if outreach else None)),
                "Follow-up Date": _fmt(company.follow_up_date or (outreach.follow_up_date if outreach else None)),
            }
        )
    return buf.getvalue()


def _fmt(value: datetime | None) -> str:
    if not value:
        return ""
    return value.strftime("%Y-%m-%d")

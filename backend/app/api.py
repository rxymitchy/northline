import hmac
import json
import re
from datetime import datetime, timezone
from threading import Thread
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, Request, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.config import settings
from app.emailer import email_reject_reason, smtp_ready
from app.db import get_db
from app.export_csv import export_run_csv
from app.models import Company, Contact, EventLog, Inquiry, Opportunity, Outreach, ResearchRun
from app.pipeline import run_pipeline
from app.playbook import DEFAULT_ICP
from app.report_pdf import build_brief_pdf
from app.self_analysis import compose_brief, email_report, run_search
from app.tip import create_tip_invoice, tip_menu, tip_rate_ok


router = APIRouter()


def _has_public_link(url: str) -> bool:
    raw = (url or "").strip()
    if not raw or any(ch.isspace() for ch in raw):
        return False
    candidate = raw if re.match(r"^https?://", raw, re.I) else "https://" + raw
    parsed = urlparse(candidate)
    host = (parsed.hostname or "").lower()
    if parsed.scheme not in ("http", "https"):
        return False
    if not host or "." not in host:
        return False
    if host in ("localhost", "127.0.0.1") or host.endswith(".local"):
        return False
    return True


def _admin_ok(pin: str | None) -> bool:
    expected = (settings.admin_pin or "").encode("utf-8")
    got = (pin or "").encode("utf-8")
    if not expected or len(expected) != len(got):
        return False
    return hmac.compare_digest(got, expected)


class RunRequest(BaseModel):
    icp: str
    target_count: int | None = None


class PinRequest(BaseModel):
    pin: str


class FeedbackRequest(BaseModel):
    target: str = "prospect"
    value: str


class StatusRequest(BaseModel):
    action: str


class TipRequest(BaseModel):
    amount_sats: int = 1000


@router.post("/admin/unlock")
def admin_unlock(payload: PinRequest):
    if not _admin_ok(payload.pin):
        raise HTTPException(403, "Wrong pin")
    return {"ok": True}


@router.post("/search")
async def create_search(
    db: Session = Depends(get_db),
    name: str = Form(...),
    email: str = Form(...),
    source: str = Form(...),
    url: str = Form(""),
    description: str = Form(""),
    file: UploadFile | None = File(None),
):
    name = (name or "").strip()
    email = (email or "").strip().lower()
    source = (source or "").strip().lower()
    url = (url or "").strip()
    description = (description or "").strip()
    if len(name) < 2:
        raise HTTPException(400, "Add your name")
    blocked = email_reject_reason(email)
    if blocked:
        raise HTTPException(400, blocked)
    if source not in ("website", "social", "csv", "describe"):
        raise HTTPException(400, "Choose how you work")
    csv_text = ""
    if source in ("website", "social"):
        if not _has_public_link(url):
            raise HTTPException(400, "Add the full website or profile link")
    if source == "csv":
        if len(description) < 20:
            raise HTTPException(400, "Add a short note about follow-up")
        if not file:
            raise HTTPException(400, "Attach a CSV or spreadsheet export")
        raw = await file.read()
        if len(raw) > 1_500_000:
            raise HTTPException(400, "File is too large")
        csv_text = raw.decode("utf-8", errors="replace")[:20000]
        description = (description + "\n" + csv_text).strip()
    if source == "describe" and len(description) < 20:
        raise HTTPException(400, "Tell us a little more about how work moves today")
    payload = {
        "name": name,
        "email": email,
        "source": source,
        "url": url,
        "description": description,
        "filename": file.filename if file else "",
    }
    inquiry = db.query(Inquiry).filter(Inquiry.email == email).first()
    if inquiry and inquiry.run_id:
        live = db.get(ResearchRun, inquiry.run_id)
        if live and live.kind == "search" and live.status in ("queued", "running"):
            return {"id": live.id, "status": live.status, "lead_saved": True, "reused": True}
    run = ResearchRun(icp_text=json.dumps(payload), status="queued", kind="search")
    db.add(run)
    db.commit()
    db.refresh(run)
    now = datetime.now(timezone.utc)
    detail = (url or description or csv_text)[:4000]
    if inquiry:
        inquiry.name = name
        inquiry.run_id = run.id
        inquiry.source_kind = source
        inquiry.source_value = detail
        inquiry.search_count = int(inquiry.search_count or 1) + 1
        inquiry.updated_at = now
    else:
        db.add(
            Inquiry(
                run_id=run.id,
                name=name,
                email=email,
                source_kind=source,
                source_value=detail,
                search_count=1,
                updated_at=now,
            )
        )
    db.commit()
    Thread(target=run_search, args=(run.id,), daemon=True).start()
    return {"id": run.id, "status": run.status, "lead_saved": True}


@router.post("/runs/{run_id}/help")
def request_help(run_id: int, db: Session = Depends(get_db)):
    run = db.get(ResearchRun, run_id)
    if not run or (getattr(run, "kind", None) or "") != "search":
        raise HTTPException(404, "Not found")
    inquiry = db.query(Inquiry).filter(Inquiry.run_id == run_id).order_by(Inquiry.id.desc()).first()
    if not inquiry:
        try:
            sub = json.loads(run.icp_text or "{}")
        except Exception:
            sub = {}
        email = str((sub or {}).get("email") or "").strip().lower()
        if email:
            inquiry = db.query(Inquiry).filter(Inquiry.email == email).first()
    if not inquiry:
        raise HTTPException(400, "No lead was saved for this diagnosis.")
    inquiry.wants_help = True
    db.commit()
    return {
        "ok": True,
        "saved": True,
        "message": "Thanks. Use Tip us if you want to send sats — no booking link.",
    }


@router.get("/tip")
def tip_options():
    return tip_menu()


@router.post("/tip")
def create_tip(payload: TipRequest, request: Request):
    ip = (request.client.host if request.client else "") or "unknown"
    if not tip_rate_ok(ip):
        raise HTTPException(429, "Too many tip requests. Wait a minute and try again.")
    try:
        return create_tip_invoice(payload.amount_sats)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except Exception:
        raise HTTPException(502, "Could not create a Lightning invoice. Try another amount in a moment.") from None


@router.get("/leads")
def list_leads(db: Session = Depends(get_db), x_admin_pin: str | None = Header(default=None)):
    if not _admin_ok(x_admin_pin):
        raise HTTPException(403, "Admin only")
    rows = db.query(Inquiry).order_by(Inquiry.id.desc()).limit(200).all()
    return [
        {
            "id": row.id,
            "run_id": row.run_id,
            "name": row.name,
            "email": row.email,
            "source": row.source_kind,
            "detail": (row.source_value or "")[:240],
            "wants_help": bool(getattr(row, "wants_help", False)),
            "search_count": int(getattr(row, "search_count", 1) or 1),
            "created_at": row.created_at.isoformat() if row.created_at else None,
        }
        for row in rows
    ]


@router.post("/runs/{run_id}/email")
def send_report(run_id: int, db: Session = Depends(get_db)):
    run = db.get(ResearchRun, run_id)
    if not run:
        raise HTTPException(404, "Not found")
    if run.status not in ("completed", "failed"):
        raise HTTPException(400, "The snapshot is still running. Try email in a moment.")
    result = email_report(run_id)
    if result.get("code") == "invalid_email":
        raise HTTPException(400, result.get("reason"))
    if result.get("code") == "smtp_unconfigured":
        return {
            "ok": False,
            "sent": False,
            "smtp_configured": False,
            "reason": result.get("reason"),
        }
    if not result.get("sent"):
        return {
            "ok": False,
            "sent": False,
            "smtp_configured": smtp_ready(),
            "reason": result.get("reason") or "Could not send the email. Download the full report instead.",
        }
    return {"ok": True, "sent": True, "smtp_configured": True}


@router.get("/runs/{run_id}/report")
def download_report(run_id: int, db: Session = Depends(get_db)):
    run = db.get(ResearchRun, run_id)
    if not run:
        raise HTTPException(
            404,
            "This snapshot is no longer on the server. Run See the diagnosis again, then download.",
        )
    company = (
        db.query(Company)
        .filter(Company.run_id == run_id)
        .order_by(Company.id.asc())
        .first()
    )
    if not company:
        raise HTTPException(400, "The report is not ready yet.")
    fi = _json(company.fact_inference) if company.fact_inference else {}
    if not isinstance(fi, dict):
        fi = {}
    brief = compose_brief(company, fi)
    fi["brief"] = brief
    company.fact_inference = json.dumps(fi)
    db.add(company)
    db.commit()
    try:
        pdf = build_brief_pdf(brief, company.name or "Report", company.website or "")
    except Exception:
        raise HTTPException(400, "The report could not be built. Try the analysis again.")
    if not pdf or not pdf.startswith(b"%PDF"):
        raise HTTPException(400, "The report could not be built. Try the analysis again.")
    safe = "".join(c if c.isalnum() else "-" for c in (company.name or "northline"))[:40]
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{safe}-northline-report.pdf"'},
    )


@router.post("/runs")
def create_run(
    payload: RunRequest,
    db: Session = Depends(get_db),
    x_admin_pin: str | None = Header(default=None),
):
    if not _admin_ok(x_admin_pin):
        raise HTTPException(403, "Admin only")
    icp = payload.icp.strip() or DEFAULT_ICP
    run = ResearchRun(icp_text=icp, status="queued", kind="outbound")
    db.add(run)
    db.commit()
    db.refresh(run)
    Thread(target=run_pipeline, args=(run.id,), daemon=True).start()
    return {"id": run.id, "status": run.status, "kind": run.kind}


@router.get("/runs")
def list_runs(db: Session = Depends(get_db), x_admin_pin: str | None = Header(default=None)):
    if not _admin_ok(x_admin_pin):
        raise HTTPException(403, "Admin only")
    runs = db.query(ResearchRun).order_by(ResearchRun.id.desc()).limit(30).all()
    return [_run_summary(r) for r in runs]


@router.get("/runs/{run_id}")
def get_run(run_id: int, db: Session = Depends(get_db), x_admin_pin: str | None = Header(default=None)):
    run = db.get(ResearchRun, run_id)
    if not run:
        raise HTTPException(404, "Run not found")
    kind = getattr(run, "kind", None) or "outbound"
    if kind != "search" and not _admin_ok(x_admin_pin):
        raise HTTPException(403, "Admin only")
    companies = (
        db.query(Company)
        .filter(Company.run_id == run_id)
        .order_by(Company.lead_score.desc().nullslast(), Company.id.asc())
        .all()
    )
    parsed = _json(run.parsed_icp)
    fi = {}
    if companies:
        fi = _json(companies[0].fact_inference) if companies[0].fact_inference else {}
        if not isinstance(fi, dict):
            fi = {}
    result = None
    if companies:
        c = companies[0]
        diagnosis = fi.get("diagnosis") if isinstance(fi.get("diagnosis"), dict) else {}
        result = {
            "name": c.name,
            "observed": c.observed_problem,
            "facts": _plain_list(fi.get("facts") if isinstance(fi, dict) else []),
            "gaps": _plain_list((fi.get("heuristic_gap") or {}).get("gaps") if isinstance(fi, dict) else []),
            "offer": c.automation_opportunity,
            "emailed": bool(fi.get("emailed")) if isinstance(fi, dict) else False,
            "confidence": c.confidence,
            "source": fi.get("source") if isinstance(fi, dict) else None,
            "channel": fi.get("channel") if isinstance(fi, dict) else None,
            "diagnosis": diagnosis,
            "industry": (fi.get("industry") if isinstance(fi, dict) else None) or c.industry,
        }
    if kind == "search":
        return {
            "id": run.id,
            "kind": kind,
            "status": run.status,
            "error": run.error,
            "progress": parsed.get("stage") if isinstance(parsed, dict) else None,
            "result": result,
            "smtp_configured": smtp_ready(),
            "contact_email": (settings.contact_email or "").strip(),
        }
    return {
        **_run_summary(run),
        "progress": parsed.get("stage") if isinstance(parsed, dict) else None,
        "result": result,
        "parsed_icp": parsed,
        "companies": [_company_row(c) for c in companies],
        "email_sending_enabled": settings.email_sending_enabled,
        "smtp_configured": smtp_ready(),
    }


@router.get("/runs/{run_id}/logs")
def get_logs(run_id: int, db: Session = Depends(get_db), x_admin_pin: str | None = Header(default=None)):
    if not _admin_ok(x_admin_pin):
        raise HTTPException(403, "Admin only")
    logs = (
        db.query(EventLog)
        .filter(EventLog.run_id == run_id)
        .order_by(EventLog.id.asc())
        .all()
    )
    return [
        {
            "id": log.id,
            "level": log.level,
            "event_type": log.event_type,
            "message": log.message,
            "created_at": log.created_at.isoformat() if log.created_at else None,
        }
        for log in logs
    ]


@router.get("/runs/{run_id}/export.csv")
def export_csv(run_id: int, db: Session = Depends(get_db), x_admin_pin: str | None = Header(default=None)):
    if not _admin_ok(x_admin_pin):
        raise HTTPException(403, "Admin only")
    run = db.get(ResearchRun, run_id)
    if not run:
        raise HTTPException(404, "Run not found")
    content = export_run_csv(db, run_id)
    return Response(
        content=content,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="prospects-run-{run_id}.csv"'},
    )


@router.get("/prospects/{company_id}")
def get_prospect(company_id: int, db: Session = Depends(get_db), x_admin_pin: str | None = Header(default=None)):
    if not _admin_ok(x_admin_pin):
        raise HTTPException(403, "Admin only")
    company = db.get(Company, company_id)
    if not company:
        raise HTTPException(404, "Prospect not found")
    contacts = db.query(Contact).filter(Contact.company_id == company.id).all()
    opportunities = db.query(Opportunity).filter(Opportunity.company_id == company.id).all()
    outreach = db.query(Outreach).filter(Outreach.company_id == company.id).all()
    return {
        **_company_detail(company),
        "contacts": [_contact(c) for c in contacts],
        "opportunities": [_opportunity(o) for o in opportunities],
        "outreach": [_outreach(o) for o in outreach],
        "email_sending_enabled": settings.email_sending_enabled,
    }


@router.post("/prospects/{company_id}/decision")
def decide(company_id: int, payload: StatusRequest, db: Session = Depends(get_db), x_admin_pin: str | None = Header(default=None)):
    if not _admin_ok(x_admin_pin):
        raise HTTPException(403, "Admin only")
    company = db.get(Company, company_id)
    if not company:
        raise HTTPException(404, "Prospect not found")
    outreach = db.query(Outreach).filter(Outreach.company_id == company.id).order_by(Outreach.id.desc()).first()
    if payload.action == "approve":
        company.status = "ready_to_send"
        if outreach:
            outreach.status = "approved"
        db.commit()
        return {
            "status": company.status,
            "note": "Marked ready to send. Outbound send happens automatically only when SMTP is configured and EMAIL_SENDING_ENABLED=true.",
        }
    if payload.action == "reject":
        company.status = "rejected"
        if outreach:
            outreach.status = "rejected"
        db.commit()
        return {"status": company.status}
    raise HTTPException(400, "action must be approve or reject")


@router.post("/prospects/{company_id}/feedback")
def feedback(company_id: int, payload: FeedbackRequest, db: Session = Depends(get_db), x_admin_pin: str | None = Header(default=None)):
    if not _admin_ok(x_admin_pin):
        raise HTTPException(403, "Admin only")
    company = db.get(Company, company_id)
    if not company:
        raise HTTPException(404, "Prospect not found")
    if payload.value not in ("good", "bad"):
        raise HTTPException(400, "value must be good or bad")
    if payload.target == "opportunity":
        company.opportunity_feedback = payload.value
        opp = db.query(Opportunity).filter(Opportunity.company_id == company.id).order_by(Opportunity.id.desc()).first()
        if opp:
            opp.feedback = payload.value
    else:
        company.feedback = payload.value
    db.commit()
    return {"ok": True}


def _run_summary(run: ResearchRun) -> dict:
    return {
        "id": run.id,
        "kind": getattr(run, "kind", None) or "outbound",
        "icp_text": run.icp_text,
        "status": run.status,
        "error": run.error,
        "discovered_count": run.discovered_count,
        "researched_count": run.researched_count,
        "qualified_count": run.qualified_count,
        "rejected_count": run.rejected_count,
        "estimated_cost_usd": run.estimated_cost_usd,
        "created_at": run.created_at.isoformat() if run.created_at else None,
        "finished_at": run.finished_at.isoformat() if run.finished_at else None,
    }


def _nz(value, fallback="Not found on public pages"):
    if value is None:
        return fallback
    if isinstance(value, str) and not value.strip():
        return fallback
    return value


def _decision_summary(c: Company) -> str:
    notes = _json(c.research_notes) if (c.research_notes or "").startswith("{") else {}
    if isinstance(notes, dict) and notes.get("decision"):
        return notes["decision"]
    if c.status == "filtered_out":
        return _nz(c.cheap_filter_reason, "Dropped by cheap filter.")
    if c.status == "research_failed":
        return _nz(notes.get("fail_reason") if isinstance(notes, dict) else None, c.observed_problem or "Fetch failed.")
    if c.status in ("rejected_score", "no_pain_evidence"):
        why = (_json(c.score_breakdown) or {}).get("why") if isinstance(_json(c.score_breakdown), dict) else None
        return _nz(why, c.observed_problem or "Not qualified.")
    if c.status in ("outreach_drafted", "ready_to_send", "qualified", "emailed"):
        why = (_json(c.score_breakdown) or {}).get("why") if isinstance(_json(c.score_breakdown), dict) else None
        return _nz(why, "Qualified from public evidence.")
    if c.status in ("self_report_ready", "self_report_emailed"):
        return _nz(c.observed_problem, "Self-analysis report is ready on this page.")
    if c.status == "rejected":
        return "You rejected this prospect in the dashboard."
    if c.status == "skipped_cost_cap":
        return "Not deep-researched because the run hit the cost/research cap."
    return _nz(c.observed_problem, f"Status is {c.status}.")


def _company_row(c: Company) -> dict:
    notes = _json(c.research_notes) if (c.research_notes or "").startswith("{") else {}
    track = notes.get("track") if isinstance(notes, dict) else None
    return {
        "id": c.id,
        "run_id": c.run_id,
        "name": c.name,
        "website": _nz(c.website, "No company website resolved"),
        "industry": _nz(c.industry, "Unknown"),
        "track": track or "unclassified",
        "named_target": bool(notes.get("named_target")) if isinstance(notes, dict) else False,
        "location": _nz(c.location, "Location not confirmed"),
        "status": c.status,
        "lead_score": c.lead_score,
        "confidence": _nz(c.confidence, "n/a"),
        "observed_problem": _nz(c.observed_problem, "Not analysed yet."),
        "automation_opportunity": _nz(c.automation_opportunity, "None yet."),
        "whatsapp": _nz(c.whatsapp, "No WhatsApp link found"),
        "phone": _nz(c.phone, "No public phone found"),
        "general_email": _nz(c.general_email, "No public company email found"),
        "feedback": _nz(c.feedback, "No feedback yet"),
        "decision_summary": _decision_summary(c),
        "cheap_filter_reason": _nz(c.cheap_filter_reason, "n/a"),
    }


def _company_detail(c: Company) -> dict:
    breakdown = _json(c.score_breakdown)
    return {
        **_company_row(c),
        "description": _nz(c.description, "No public description captured."),
        "phone": _nz(c.phone, "No public phone found"),
        "general_email": _nz(c.general_email, "No public company email found"),
        "source": _nz(c.source, "Unknown source"),
        "source_url": _nz(c.source_url, "No source URL"),
        "score_breakdown": breakdown if breakdown else {"why": _decision_summary(c), "breakdown": {}},
        "cheap_filter_score": c.cheap_filter_score if c.cheap_filter_score is not None else "n/a",
        "page_signals": _json(c.page_signals) if c.page_signals and c.page_signals != "{}" else {"note": "No page signals stored"},
        "evidence": _json(c.evidence) if (c.evidence or "").startswith("[") or (c.evidence or "").startswith("{") else _nz(c.evidence, "No evidence quotes stored"),
        "recommended_offer": _nz(c.recommended_offer, "None"),
        "fact_inference": _json(c.fact_inference) if c.fact_inference and c.fact_inference != "{}" else {"facts": [], "inferences": []},
        "opportunity_feedback": _nz(c.opportunity_feedback, "No feedback yet"),
        "discovered_at": c.discovered_at.isoformat() if c.discovered_at else "Unknown",
        "researched_at": c.researched_at.isoformat() if c.researched_at else "Not researched",
        "date_contacted": c.date_contacted.isoformat() if c.date_contacted else "Not contacted (sending disabled)",
        "follow_up_date": c.follow_up_date.isoformat() if c.follow_up_date else "Not set",
    }


def _contact(c: Contact) -> dict:
    return {
        "id": c.id,
        "name": _nz(c.name, "Name not found on public pages"),
        "role": _nz(c.role, "Role inferred only — not confirmed on a public page"),
        "email": _nz(c.email, "CONTACT NOT VERIFIED — no public email found"),
        "phone": _nz(c.phone, "No public phone found"),
        "linkedin": _nz(c.linkedin, "No public LinkedIn URL found"),
        "verified": c.verified,
        "verification_note": _nz(c.verification_note, "CONTACT NOT VERIFIED"),
        "source_url": _nz(c.source_url, "No source URL"),
        "rationale": _nz(c.rationale, "No contact-hunting notes stored."),
    }


def _opportunity(o: Opportunity) -> dict:
    return {
        "id": o.id,
        "observed_problem": o.observed_problem,
        "evidence": _json(o.evidence),
        "automation_opportunity": o.automation_opportunity,
        "recommended_offer": o.recommended_offer,
        "confidence": o.confidence,
        "facts": _json(o.facts_json),
        "inferences": _json(o.inferences_json),
        "feedback": o.feedback,
    }


def _outreach(o: Outreach) -> dict:
    return {
        "id": o.id,
        "subject": _nz(o.subject, "No subject generated"),
        "body": _nz(o.body, "No outreach draft — prospect was not qualified or generation failed."),
        "pitch_rationale": _nz(o.pitch_rationale, "No pitch rationale stored."),
        "status": o.status,
        "date_contacted": o.date_contacted.isoformat() if o.date_contacted else None,
        "follow_up_date": o.follow_up_date.isoformat() if o.follow_up_date else None,
        "follow_up_count": o.follow_up_count,
        "response_status": o.response_status,
        "meetings": o.meetings,
        "proposals": o.proposals,
        "outcome": o.outcome,
    }


def _json(raw: str | None):
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except Exception:
        return raw


def _plain_list(items) -> list:
    out = []
    for item in items or []:
        if isinstance(item, str) and item.strip():
            out.append(item)
        elif isinstance(item, dict):
            text = item.get("observation") or item.get("claim") or item.get("summary")
            if text:
                out.append(str(text))
    return out

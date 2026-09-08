import json
from threading import Thread

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_db
from app.export_csv import export_run_csv
from app.models import Company, Contact, EventLog, Opportunity, Outreach, ResearchRun
from app.pipeline import run_pipeline


router = APIRouter()


class RunRequest(BaseModel):
    icp: str
    target_count: int | None = None


class FeedbackRequest(BaseModel):
    target: str = "prospect"  # prospect | opportunity
    value: str  # good | bad


class StatusRequest(BaseModel):
    action: str  # approve | reject


@router.post("/runs")
def create_run(payload: RunRequest, db: Session = Depends(get_db)):
    if not payload.icp.strip():
        raise HTTPException(400, "ICP text is required")
    if not settings.openai_api_key:
        raise HTTPException(
            400,
            "OPENAI_API_KEY is not set. Copy .env.example to backend/.env and add your key.",
        )
    run = ResearchRun(icp_text=payload.icp.strip(), status="queued")
    db.add(run)
    db.commit()
    db.refresh(run)
    Thread(target=run_pipeline, args=(run.id,), daemon=True).start()
    return {"id": run.id, "status": run.status}


@router.get("/runs")
def list_runs(db: Session = Depends(get_db)):
    runs = db.query(ResearchRun).order_by(ResearchRun.id.desc()).limit(30).all()
    return [_run_summary(r) for r in runs]


@router.get("/runs/{run_id}")
def get_run(run_id: int, db: Session = Depends(get_db)):
    run = db.get(ResearchRun, run_id)
    if not run:
        raise HTTPException(404, "Run not found")
    companies = (
        db.query(Company)
        .filter(Company.run_id == run_id)
        .order_by(Company.lead_score.desc().nullslast(), Company.id.asc())
        .all()
    )
    return {
        **_run_summary(run),
        "parsed_icp": _json(run.parsed_icp),
        "companies": [_company_row(c) for c in companies],
        "email_sending_enabled": settings.email_sending_enabled,
    }


@router.get("/runs/{run_id}/logs")
def get_logs(run_id: int, db: Session = Depends(get_db)):
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
def export_csv(run_id: int, db: Session = Depends(get_db)):
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
def get_prospect(company_id: int, db: Session = Depends(get_db)):
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
def decide(company_id: int, payload: StatusRequest, db: Session = Depends(get_db)):
    company = db.get(Company, company_id)
    if not company:
        raise HTTPException(404, "Prospect not found")
    outreach = db.query(Outreach).filter(Outreach.company_id == company.id).order_by(Outreach.id.desc()).first()
    if payload.action == "approve":
        company.status = "ready_to_send"
        if outreach:
            outreach.status = "approved"
        db.commit()
        return {"status": company.status, "note": "Marked ready to send. Automatic sending is disabled in MVP."}
    if payload.action == "reject":
        company.status = "rejected"
        if outreach:
            outreach.status = "rejected"
        db.commit()
        return {"status": company.status}
    raise HTTPException(400, "action must be approve or reject")


@router.post("/prospects/{company_id}/feedback")
def feedback(company_id: int, payload: FeedbackRequest, db: Session = Depends(get_db)):
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
    if c.status in ("outreach_drafted", "ready_to_send", "qualified"):
        why = (_json(c.score_breakdown) or {}).get("why") if isinstance(_json(c.score_breakdown), dict) else None
        return _nz(why, "Qualified from public evidence; draft ready. Email is not sent automatically.")
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

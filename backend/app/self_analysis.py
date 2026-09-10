import json
import re
from datetime import datetime, timezone
from urllib.parse import urlparse

from app.brief import BRAND, build_brief
from app.db import SessionLocal
from app.emailer import send_email
from app.logging_util import log_event
from app.models import Company, Contact, Opportunity, Outreach, ResearchRun
from app.modules.channel_notes import channel_notes
from app.modules.gap import detect_automation_gap
from app.modules.opportunity import detect_opportunity
from app.modules.peers import find_better_companies
from app.modules.research import research_company
from app.modules.scoring import score_prospect


def normalize_website(raw: str) -> str:
    url = (raw or "").strip()
    if not url:
        return ""
    if not re.match(r"^https?://", url, re.I):
        url = "https://" + url
    return url


def run_self_analysis(run_id: int, website: str, recipient_email: str, company_name: str | None) -> None:
    run_search(run_id)


def run_search(run_id: int) -> None:
    db = SessionLocal()
    try:
        run = db.get(ResearchRun, run_id)
        if not run:
            return
        sub = _submission(run)
        name = sub.get("name") or "Your company"
        email = sub.get("email") or ""
        source = sub.get("source") or "website"
        run.status = "running"
        _progress(db, run, "Looking at how you work. This usually takes under a minute…")
        log_event(run_id, "search_start", f"{name} · {source}")

        site, host, research = _gather_research(run_id, sub)
        company = Company(
            run_id=run_id,
            name=name,
            website=site or None,
            domain=host or None,
            location="Submitted",
            source=source,
            source_url=site or None,
            description=(sub.get("description") or "")[:2000],
            status="researching",
            research_notes=json.dumps(
                {"track": "operational_pain", "named_target": False, "self": True, "submission": sub}
            ),
        )
        db.add(company)
        db.commit()
        db.refresh(company)

        if not research.get("ok"):
            company.status = "research_failed"
            company.observed_problem = research.get("reason") or "Could not read what you sent."
            run.status = "failed"
            run.error = company.observed_problem
            run.finished_at = datetime.now(timezone.utc)
            _progress(db, run, "Could not finish")
            db.commit()
            return

        company.website = research.get("website") or site or company.website
        company.whatsapp = (research.get("whatsapps") or [None])[0]
        company.general_email = (research.get("emails") or [None])[0]
        company.phone = (research.get("phones") or [None])[0]
        company.page_signals = json.dumps(research.get("signals") or {})
        company.researched_at = datetime.now(timezone.utc)
        run.researched_count = 1
        run.discovered_count = 1
        _progress(db, run, "Finding repetitive work")

        cand = {"name": name, "website": company.website, "source_url": company.source_url, "track": "operational_pain"}
        parsed = {"industry": "self-analysis", "location": "", "tracks": ["operational_pain"]}
        opportunity = detect_opportunity(run_id, cand, research, parsed, use_llm=False)
        gap = opportunity.get("heuristic_gap") or detect_automation_gap(research, "operational_pain")
        company.observed_problem = opportunity.get("observed_problem") or gap.get("summary")
        company.evidence = json.dumps(opportunity.get("evidence") or gap.get("facts") or [])
        company.automation_opportunity = opportunity.get("automation_opportunity") or gap.get("summary")
        company.recommended_offer = opportunity.get("recommended_offer") or "Automate the repetitive hand-offs we can see."
        company.confidence = opportunity.get("confidence") or ("Medium" if gap.get("exists") else "Low")

        notes = channel_notes(source, company.website or sub.get("url") or "", research, gap)
        company.fact_inference = json.dumps(
            {
                "facts": opportunity.get("facts") or gap.get("facts") or [],
                "inferences": opportunity.get("inferences") or [],
                "automation_gap": opportunity.get("automation_gap") or gap.get("summary"),
                "heuristic_gap": gap,
                "doing_it_right": [],
                "emailed": False,
                "research_text": (research.get("text") or "")[:8000],
                "channel": notes,
                "source": source,
            }
        )
        db.add(
            Opportunity(
                company_id=company.id,
                observed_problem=company.observed_problem or "",
                evidence=company.evidence or "[]",
                automation_opportunity=company.automation_opportunity or "",
                recommended_offer=company.recommended_offer,
                confidence=company.confidence or "Low",
                facts_json=json.dumps(opportunity.get("facts") or []),
                inferences_json=json.dumps(opportunity.get("inferences") or []),
            )
        )
        if source in ("describe", "csv"):
            contact_data = {
                "name": name,
                "role": None,
                "email": email,
                "phone": None,
                "linkedin": None,
                "verified": True,
                "verification_note": "Saved when they searched.",
                "source_url": None,
                "rationale": "Details they submitted.",
            }
        else:
            contact_data = {
                "name": name,
                "role": None,
                "email": email,
                "phone": (research.get("phones") or [None])[0],
                "linkedin": None,
                "verified": True,
                "verification_note": "Saved when they searched.",
                "source_url": company.website,
                "rationale": "Visitor email; no public contact hunt.",
            }
        contact = Contact(company_id=company.id, **contact_data)
        db.add(contact)
        db.flush()

        scoring = score_prospect(run_id, cand, research, opportunity, contact_data, use_llm=False)
        company.lead_score = scoring.get("lead_score")
        company.score_breakdown = json.dumps(scoring)
        company.status = "self_report_ready"
        run.qualified_count = 1 if gap.get("exists") or opportunity.get("qualify") else 0

        fi = json.loads(company.fact_inference)
        brief = compose_brief(company, fi)
        fi["brief"] = brief
        company.fact_inference = json.dumps(fi)
        db.add(
            Outreach(
                company_id=company.id,
                contact_id=contact.id,
                subject=f"Your {BRAND} report — {name}",
                body=brief["text"],
                pitch_rationale="Requested search.",
                status="draft",
            )
        )
        run.status = "completed"
        run.finished_at = datetime.now(timezone.utc)
        _progress(db, run, "Ready")
        log_event(run_id, "search_done", name)
    except Exception as exc:
        db.rollback()
        run = db.get(ResearchRun, run_id)
        if run:
            run.status = "failed"
            run.error = str(exc)
            run.finished_at = datetime.now(timezone.utc)
            _progress(db, run, "Something went wrong")
        log_event(run_id, "search_error", str(exc), level="error")
    finally:
        db.close()


def compose_brief(company: Company, fi: dict) -> dict:
    old = fi.get("brief") if isinstance(fi.get("brief"), dict) else {}
    gap = fi.get("heuristic_gap") if isinstance(fi.get("heuristic_gap"), dict) else {}
    opportunity = {
        "facts": fi.get("facts") or [],
        "observed_problem": company.observed_problem,
        "automation_opportunity": company.automation_opportunity,
    }
    peers = {
        "industry": old.get("industry") or "your space",
        "similar": old.get("similar") or [],
        "doing_it_right": fi.get("doing_it_right") or old.get("doing_it_right") or [],
    }
    return build_brief(
        company.name or "Report",
        company.website or "",
        gap,
        opportunity,
        peers,
        emailed=bool(fi.get("emailed")),
        channel=fi.get("channel") if isinstance(fi.get("channel"), dict) else {},
    )


def email_report(run_id: int) -> dict:
    db = SessionLocal()
    try:
        run = db.get(ResearchRun, run_id)
        if not run:
            return {"sent": False, "reason": "Not found"}
        sub = _submission(run)
        email = (sub.get("email") or "").strip()
        company = db.query(Company).filter(Company.run_id == run_id).order_by(Company.id.asc()).first()
        if not company:
            return {"sent": False, "reason": "Search is not ready yet"}
        fi = _fi(company)
        brief = compose_brief(company, fi)
        fi["brief"] = brief
        company.fact_inference = json.dumps(fi)
        db.commit()
        subject = f"Your {BRAND} report — {company.name}"
        body = brief.get("text") or company.observed_problem or "Your report is ready."
        html = brief.get("html")
        mail = send_email(email, subject, body, html=html)
        outreach = db.query(Outreach).filter(Outreach.company_id == company.id).order_by(Outreach.id.desc()).first()
        if mail.get("sent"):
            company.status = "self_report_emailed"
            company.date_contacted = datetime.now(timezone.utc)
            if outreach:
                outreach.status = "sent"
                outreach.date_contacted = company.date_contacted
            fi["emailed"] = True
            if isinstance(brief, dict):
                brief["emailed"] = True
                fi["brief"] = brief
            company.fact_inference = json.dumps(fi)
            db.commit()
            log_event(run_id, "email_sent", mail.get("reason") or "")
        else:
            log_event(run_id, "email_not_sent", mail.get("reason") or "", level="warning")
        return mail
    finally:
        db.close()


def find_better(run_id: int) -> dict:
    db = SessionLocal()
    try:
        run = db.get(ResearchRun, run_id)
        if not run:
            return {"ok": False, "peers": []}
        company = db.query(Company).filter(Company.run_id == run_id).order_by(Company.id.asc()).first()
        if not company:
            return {"ok": False, "peers": []}
        _progress(db, run, "Finding companies doing better")
        run.status = "running"
        db.commit()
        fi = _fi(company)
        research = {"text": fi.get("research_text") or company.description or ""}
        peers = find_better_companies(run_id, company.name, company.website or "", research)
        fi["doing_it_right"] = peers
        brief = compose_brief(company, fi)
        fi["brief"] = brief
        company.fact_inference = json.dumps(fi)
        run.status = "completed"
        _progress(db, run, "Ready")
        log_event(run_id, "better_done", f"{len(peers)} companies")
        return {"ok": True, "peers": peers}
    except Exception as exc:
        db.rollback()
        run = db.get(ResearchRun, run_id)
        if run:
            run.status = "completed"
            db.commit()
        log_event(run_id, "better_error", str(exc), level="error")
        return {"ok": False, "peers": [], "reason": str(exc)}
    finally:
        db.close()


def _gather_research(run_id: int, sub: dict) -> tuple[str, str, dict]:
    source = sub.get("source") or "website"
    url = normalize_website(sub.get("url") or "")
    blob = (sub.get("description") or "").strip()
    if source in ("website", "social") and url:
        cand = {"name": sub.get("name"), "website": url, "source_url": url, "track": "operational_pain"}
        research = research_company(run_id, cand, quick=True)
        if research.get("ok"):
            host = urlparse(research.get("website") or url).netloc.replace("www.", "")
            return research.get("website") or url, host, research
        if blob:
            return url, urlparse(url).netloc.replace("www.", ""), _text_research(blob + "\n" + url)
        return url, urlparse(url).netloc.replace("www.", ""), research
    if not blob:
        blob = url or "The company described repetitive manual work."
    host = urlparse(url).netloc.replace("www.", "") if url else ""
    return url, host, _text_research(blob)


def _text_research(text: str) -> dict:
    low = text.lower()
    signals = {
        "whatsapp_channel": "whatsapp" in low,
        "call_to_book": "call" in low and ("book" in low or "enquire" in low),
        "online_booking": "book online" in low or "calendly" in low,
        "enquiry_form": "form" in low or "spreadsheet" in low or "excel" in low or "csv" in low,
        "chatbot": "chatbot" in low,
        "crm_mention": "crm" in low,
        "quote_request": "quote" in low,
        "manual_followup_language": any(w in low for w in ("follow up", "follow-up", "manually", "by hand", "copy paste", "excel")),
    }
    return {
        "ok": True,
        "text": text[:14000],
        "signals": signals,
        "emails": [],
        "whatsapps": [],
        "phones": [],
        "pages": [{"url": "", "text": text[:4000]}],
        "website": None,
    }


def _submission(run: ResearchRun) -> dict:
    try:
        data = json.loads(run.icp_text or "{}")
        if isinstance(data, dict) and data.get("email"):
            return data
    except Exception:
        pass
    return {"name": "", "email": "", "source": "website", "url": "", "description": run.icp_text or ""}


def _fi(company: Company) -> dict:
    try:
        data = json.loads(company.fact_inference or "{}")
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _progress(db, run: ResearchRun, label: str) -> None:
    run.parsed_icp = json.dumps({"stage": label})
    db.commit()
    log_event(run.id, "progress", label)

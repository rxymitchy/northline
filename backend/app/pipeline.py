import json
import time
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.config import settings
from app.db import SessionLocal
from app.emailer import send_email, sending_outbound_allowed
from app.logging_util import log_event
from app.models import ApiUsage, Company, Contact, Opportunity, Outreach, ResearchRun
from app.modules.cheap_filter import cheap_filter
from app.modules.contacts import find_contact
from app.modules.discovery import discover_candidates
from app.modules.icp import parse_icp
from app.modules.opportunity import detect_opportunity
from app.modules.outreach import write_outreach
from app.modules.research import research_company
from app.modules.scoring import score_prospect


def run_pipeline(run_id: int) -> None:
    db = SessionLocal()
    try:
        run = db.get(ResearchRun, run_id)
        if not run:
            return
        run.status = "running"
        db.commit()
        log_event(run_id, "pipeline_start", "Prospecting run started")

        parsed = parse_icp(run_id, run.icp_text, settings.max_discover)
        run.parsed_icp = json.dumps(parsed)
        db.commit()
        log_event(run_id, "icp_parsed", "ICP parsed", json.dumps(parsed))

        candidates = discover_candidates(run_id, parsed)
        run.discovered_count = len(candidates)
        db.commit()

        saved: list[Company] = []
        for cand in candidates:
            company = Company(
                run_id=run_id,
                name=cand["name"],
                website=cand.get("website"),
                domain=cand.get("domain"),
                industry=cand.get("industry"),
                location=cand.get("location"),
                description=cand.get("description"),
                source=cand.get("source"),
                source_url=cand.get("source_url"),
                status="discovered",
                research_notes=json.dumps(
                    {
                        "is_directory": cand.get("is_directory"),
                        "snippet": cand.get("snippet"),
                        "track": cand.get("track"),
                        "named_target": cand.get("named_target"),
                    }
                ),
            )
            db.add(company)
            saved.append(company)
        db.commit()

        passed: list[Company] = []
        for company in saved:
            meta = json.loads(company.research_notes or "{}")
            blob = {
                "name": company.name,
                "website": company.website,
                "source_url": company.source_url,
                "snippet": meta.get("snippet"),
                "is_directory": meta.get("is_directory"),
                "title": company.name,
                "description": company.description,
                "track": meta.get("track"),
                "named_target": meta.get("named_target"),
            }
            ok, score, reason = cheap_filter(blob, parsed)
            company.cheap_filter_score = score
            company.cheap_filter_reason = reason
            if ok:
                company.status = "filter_passed"
                passed.append(company)
            else:
                company.status = "filtered_out"
                company.observed_problem = f"Skipped before deep research: {reason}"
                company.automation_opportunity = "Not researched — cheap filter rejected this result."
                company.recommended_offer = "None"
                company.confidence = "n/a"
                company.description = company.description or (meta.get("snippet") or "No snippet")
                run.rejected_count += 1
                log_event(run_id, "filtered_out", f"{company.name}: {reason}")
        db.commit()

        passed.sort(key=lambda c: c.cheap_filter_score or 0, reverse=True)
        to_research = passed[: settings.max_deep_research]
        log_event(
            run_id,
            "funnel",
            f"Cheap filter passed {len(passed)}; deep-researching {len(to_research)}",
        )

        outreach_made = 0
        for company in to_research:
            time.sleep(settings.fetch_delay_seconds)
            try:
                _research_one(db, run, company, parsed)
            except Exception as exc:
                company.status = "research_failed"
                company.observed_problem = f"Research failed: {exc}"
                company.automation_opportunity = "Could not finish website research."
                company.recommended_offer = "None"
                company.confidence = "n/a"
                notes = {}
                try:
                    notes = json.loads(company.research_notes or "{}")
                    if not isinstance(notes, dict):
                        notes = {}
                except Exception:
                    notes = {}
                notes["fail_reason"] = str(exc)
                company.research_notes = json.dumps(notes)
                db.commit()
                log_event(run.id, "research_failed", f"{company.name}: {exc}", level="error")
            if company.status in ("outreach_drafted", "qualified"):
                outreach_made += 1
            if outreach_made >= settings.max_outreach:
                for leftover in to_research:
                    if leftover.status == "filter_passed":
                        leftover.status = "skipped_cost_cap"
                    leftover.observed_problem = leftover.observed_problem or (
                        "Passed cheap filter but was not deep-researched because MAX_OUTREACH/MAX_DEEP_RESEARCH was reached."
                    )
                break

        run.researched_count = sum(1 for c in saved if c.researched_at)
        run.qualified_count = sum(1 for c in saved if (c.lead_score or 0) >= 40 and c.status != "filtered_out")
        run.rejected_count = sum(
            1
            for c in saved
            if c.status in ("filtered_out", "rejected_score", "no_pain_evidence", "research_failed")
        )
        usage_rows = db.query(ApiUsage.estimated_cost_usd).filter(ApiUsage.run_id == run_id).all()
        run.estimated_cost_usd = float(sum((row[0] or 0) for row in usage_rows))
        run.status = "completed"
        run.finished_at = datetime.now(timezone.utc)
        db.commit()
        log_event(run_id, "pipeline_done", "Prospecting run completed")
    except Exception as exc:
        db.rollback()
        run = db.get(ResearchRun, run_id)
        if run:
            run.status = "failed"
            run.error = str(exc)
            run.finished_at = datetime.now(timezone.utc)
            db.commit()
        log_event(run_id, "pipeline_error", str(exc), level="error")
        raise
    finally:
        db.close()


def _research_one(db: Session, run: ResearchRun, company: Company, parsed: dict) -> None:
    company.status = "researching"
    db.commit()
    notes = {}
    try:
        notes = json.loads(company.research_notes or "{}")
        if not isinstance(notes, dict):
            notes = {}
    except Exception:
        notes = {}
    cand = {
        "name": company.name,
        "website": company.website,
        "source_url": company.source_url,
        "is_directory": notes.get("is_directory"),
        "track": notes.get("track"),
        "named_target": notes.get("named_target"),
        "industry": company.industry,
    }
    research = research_company(run.id, cand)
    if not research.get("ok"):
        company.status = "research_failed"
        notes["fail_reason"] = research.get("reason")
        company.research_notes = json.dumps(notes)
        company.observed_problem = research.get("reason") or "Website fetch failed."
        company.automation_opportunity = "Not analysed — the public site could not be used (blocked, article, or empty)."
        company.recommended_offer = "None"
        company.confidence = "n/a"
        db.commit()
        log_event(run.id, "research_failed", f"{company.name}: {research.get('reason')}", level="warning")
        return

    if research.get("website"):
        company.website = research["website"]
    company.whatsapp = (research.get("whatsapps") or [None])[0]
    company.general_email = (research.get("emails") or [None])[0]
    company.phone = (research.get("phones") or [None])[0]
    company.page_signals = json.dumps(research.get("signals") or {})
    company.researched_at = datetime.now(timezone.utc)
    run.researched_count = (run.researched_count or 0) + 1
    db.commit()

    opportunity = detect_opportunity(run.id, cand, research, parsed)
    company.observed_problem = _filled(
        opportunity.get("observed_problem"),
        opportunity.get("reject_reason") or "No grounded observation on the public website.",
    )
    company.evidence = json.dumps(opportunity.get("evidence") or opportunity.get("facts") or [])
    if company.evidence in ("[]", "null", ""):
        company.evidence = json.dumps(
            ["No extractable evidence quotes — see reject/qualify notes and page signals."]
        )
    company.automation_opportunity = _filled(
        opportunity.get("automation_opportunity"),
        "No automation offer because the page did not support a grounded recommendation.",
    )
    company.recommended_offer = _filled(
        opportunity.get("recommended_offer"),
        "None — not qualified from public evidence.",
    )
    company.confidence = opportunity.get("confidence") or "Low"
    company.fact_inference = json.dumps(
        {
            "facts": opportunity.get("facts"),
            "inferences": opportunity.get("inferences"),
            "automation_gap": opportunity.get("automation_gap"),
            "heuristic_gap": opportunity.get("heuristic_gap"),
        }
    )
    if opportunity.get("track"):
        notes["track"] = opportunity["track"]
        company.research_notes = json.dumps(notes)
    if opportunity.get("industry_guess"):
        company.industry = opportunity["industry_guess"]
    if opportunity.get("location_guess"):
        company.location = opportunity["location_guess"]
    if opportunity.get("company_summary"):
        company.description = opportunity["company_summary"]

    db.add(
        Opportunity(
            company_id=company.id,
            observed_problem=opportunity.get("observed_problem") or "",
            evidence=company.evidence or "[]",
            automation_opportunity=opportunity.get("automation_opportunity") or "",
            recommended_offer=opportunity.get("recommended_offer"),
            confidence=opportunity.get("confidence") or "Low",
            facts_json=json.dumps(opportunity.get("facts") or []),
            inferences_json=json.dumps(opportunity.get("inferences") or []),
        )
    )

    contact_data = find_contact(cand, research, opportunity, run.id)
    if contact_data.get("phone"):
        company.phone = contact_data["phone"]
    contact = Contact(company_id=company.id, **contact_data)
    db.add(contact)
    db.flush()

    scoring = score_prospect(run.id, cand, research, opportunity, contact_data)
    scoring.setdefault("why", "Score produced without a model explanation.")
    if not opportunity.get("qualify"):
        scoring["why"] = (
            f"Not recommended. Qualify=false. "
            f"{opportunity.get('reject_reason') or 'Public pages did not show a fit for agency overflow, contract work, or operational pain.'} "
            f"Model score {scoring.get('lead_score')}."
        )
    elif scoring["lead_score"] < 40:
        scoring["why"] = (
            f"Rejected: lead score {scoring['lead_score']} is below 40. "
            f"{scoring.get('why')}"
        )
    company.lead_score = scoring["lead_score"]
    company.score_breakdown = json.dumps(scoring)

    if not opportunity.get("qualify") or scoring["lead_score"] < 40:
        company.status = "rejected_score" if scoring["lead_score"] < 40 else "no_pain_evidence"
        notes["decision"] = scoring["why"]
        company.research_notes = json.dumps(notes)
        db.commit()
        log_event(
            run.id,
            "rejected",
            f"{company.name} score={scoring['lead_score']} qualify={opportunity.get('qualify')}",
        )
        return

    company.status = "qualified"
    if scoring["lead_score"] >= 40:
        draft = write_outreach(run.id, cand, opportunity, contact_data)
        outreach_row = Outreach(
                company_id=company.id,
                contact_id=contact.id,
                subject=draft.get("subject") or "",
                body=draft.get("body") or "",
                pitch_rationale=draft.get("pitch_rationale") or "",
                status="draft",
            )
        db.add(outreach_row)
        company.status = "outreach_drafted"
        notes["decision"] = (
            f"Qualified from a public automation gap. Score {scoring['lead_score']}. "
            f"{scoring.get('why')} Track={opportunity.get('track') or cand.get('track')}."
        )
        company.research_notes = json.dumps(notes)
        db.commit()
        _maybe_send_outbound(db, run, company, contact, outreach_row)
    db.commit()
    log_event(run.id, "qualified", f"{company.name} scored {scoring['lead_score']}")


def _maybe_send_outbound(db, run: ResearchRun, company: Company, contact: Contact, outreach_row: Outreach) -> None:
    email = (contact.email or "").strip()
    note = (contact.verification_note or "").lower()
    if not sending_outbound_allowed():
        log_event(run.id, "email_skipped", "Outbound sending is off or SMTP is not configured.")
        return
    if "@" not in email or "not found" in email.lower() or "not verified" in note:
        log_event(run.id, "email_skipped", f"{company.name}: no verified public email (never invented)")
        return
    time.sleep(settings.outbound_send_delay_seconds)
    result = send_email(email, outreach_row.subject, outreach_row.body)
    if result.get("sent"):
        outreach_row.status = "sent"
        outreach_row.date_contacted = datetime.now(timezone.utc)
        company.status = "emailed"
        company.date_contacted = outreach_row.date_contacted
        notes = {}
        try:
            notes = json.loads(company.research_notes or "{}")
            if not isinstance(notes, dict):
                notes = {}
        except Exception:
            notes = {}
        notes["decision"] = f"Emailed public contact {email}. {result.get('reason')}"
        company.research_notes = json.dumps(notes)
        db.commit()
        log_event(run.id, "email_sent", f"{company.name} → {email}")
    else:
        log_event(run.id, "email_failed", f"{company.name}: {result.get('reason')}", level="warning")


def _filled(value: str | None, fallback: str) -> str:
    text = (value or "").strip()
    return text if text else fallback

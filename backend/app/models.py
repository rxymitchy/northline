from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class ResearchRun(Base):
    __tablename__ = "research_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    icp_text: Mapped[str] = mapped_column(Text)
    parsed_icp: Mapped[str] = mapped_column(Text, default="{}")
    status: Mapped[str] = mapped_column(String(40), default="queued")
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    discovered_count: Mapped[int] = mapped_column(Integer, default=0)
    researched_count: Mapped[int] = mapped_column(Integer, default=0)
    qualified_count: Mapped[int] = mapped_column(Integer, default=0)
    rejected_count: Mapped[int] = mapped_column(Integer, default=0)
    estimated_cost_usd: Mapped[float] = mapped_column(Float, default=0.0)
    kind: Mapped[str] = mapped_column(String(40), default="outbound")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    companies: Mapped[list["Company"]] = relationship(back_populates="run")
    logs: Mapped[list["EventLog"]] = relationship(back_populates="run")


class Inquiry(Base):
    __tablename__ = "inquiries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_id: Mapped[int | None] = mapped_column(ForeignKey("research_runs.id"), nullable=True)
    name: Mapped[str] = mapped_column(String(200))
    email: Mapped[str] = mapped_column(String(200))
    source_kind: Mapped[str] = mapped_column(String(40))
    source_value: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Company(Base):
    __tablename__ = "companies"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("research_runs.id"))
    name: Mapped[str] = mapped_column(String(300))
    website: Mapped[str | None] = mapped_column(String(500), nullable=True)
    domain: Mapped[str | None] = mapped_column(String(250), nullable=True)
    industry: Mapped[str | None] = mapped_column(String(200), nullable=True)
    location: Mapped[str | None] = mapped_column(String(300), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    phone: Mapped[str | None] = mapped_column(String(80), nullable=True)
    general_email: Mapped[str | None] = mapped_column(String(200), nullable=True)
    whatsapp: Mapped[str | None] = mapped_column(String(200), nullable=True)
    source: Mapped[str | None] = mapped_column(String(200), nullable=True)
    source_url: Mapped[str | None] = mapped_column(String(800), nullable=True)
    status: Mapped[str] = mapped_column(String(40), default="discovered")
    lead_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    score_breakdown: Mapped[str] = mapped_column(Text, default="{}")
    cheap_filter_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cheap_filter_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    research_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    page_signals: Mapped[str] = mapped_column(Text, default="{}")
    observed_problem: Mapped[str | None] = mapped_column(Text, nullable=True)
    evidence: Mapped[str | None] = mapped_column(Text, nullable=True)
    automation_opportunity: Mapped[str | None] = mapped_column(Text, nullable=True)
    recommended_offer: Mapped[str | None] = mapped_column(Text, nullable=True)
    confidence: Mapped[str | None] = mapped_column(String(20), nullable=True)
    fact_inference: Mapped[str] = mapped_column(Text, default="{}")
    feedback: Mapped[str | None] = mapped_column(String(20), nullable=True)
    opportunity_feedback: Mapped[str | None] = mapped_column(String(20), nullable=True)
    discovered_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    researched_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    date_contacted: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    follow_up_date: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    run: Mapped["ResearchRun"] = relationship(back_populates="companies")
    contacts: Mapped[list["Contact"]] = relationship(back_populates="company")
    opportunities: Mapped[list["Opportunity"]] = relationship(back_populates="company")
    outreach: Mapped[list["Outreach"]] = relationship(back_populates="company")


class Contact(Base):
    __tablename__ = "contacts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"))
    name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    role: Mapped[str | None] = mapped_column(String(200), nullable=True)
    email: Mapped[str | None] = mapped_column(String(200), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(80), nullable=True)
    linkedin: Mapped[str | None] = mapped_column(String(400), nullable=True)
    verified: Mapped[bool] = mapped_column(Boolean, default=False)
    verification_note: Mapped[str] = mapped_column(Text, default="CONTACT NOT VERIFIED")
    source_url: Mapped[str | None] = mapped_column(String(800), nullable=True)
    rationale: Mapped[str | None] = mapped_column(Text, nullable=True)

    company: Mapped["Company"] = relationship(back_populates="contacts")


class Opportunity(Base):
    __tablename__ = "opportunities"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"))
    observed_problem: Mapped[str] = mapped_column(Text)
    evidence: Mapped[str] = mapped_column(Text)
    automation_opportunity: Mapped[str] = mapped_column(Text)
    recommended_offer: Mapped[str | None] = mapped_column(Text, nullable=True)
    confidence: Mapped[str] = mapped_column(String(20))
    facts_json: Mapped[str] = mapped_column(Text, default="[]")
    inferences_json: Mapped[str] = mapped_column(Text, default="[]")
    feedback: Mapped[str | None] = mapped_column(String(20), nullable=True)

    company: Mapped["Company"] = relationship(back_populates="opportunities")


class Outreach(Base):
    __tablename__ = "outreach"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"))
    contact_id: Mapped[int | None] = mapped_column(ForeignKey("contacts.id"), nullable=True)
    subject: Mapped[str] = mapped_column(String(300))
    body: Mapped[str] = mapped_column(Text)
    pitch_rationale: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(40), default="draft")
    date_contacted: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    follow_up_date: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    follow_up_count: Mapped[int] = mapped_column(Integer, default=0)
    response_status: Mapped[str | None] = mapped_column(String(40), nullable=True)
    meetings: Mapped[int] = mapped_column(Integer, default=0)
    proposals: Mapped[int] = mapped_column(Integer, default=0)
    outcome: Mapped[str | None] = mapped_column(String(40), nullable=True)
    follow_up_draft: Mapped[str | None] = mapped_column(Text, nullable=True)

    company: Mapped["Company"] = relationship(back_populates="outreach")


class EventLog(Base):
    __tablename__ = "event_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_id: Mapped[int | None] = mapped_column(ForeignKey("research_runs.id"), nullable=True)
    level: Mapped[str] = mapped_column(String(20), default="info")
    event_type: Mapped[str] = mapped_column(String(80))
    message: Mapped[str] = mapped_column(Text)
    payload: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    run: Mapped["ResearchRun | None"] = relationship(back_populates="logs")


class ApiUsage(Base):
    __tablename__ = "api_usage"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_id: Mapped[int | None] = mapped_column(ForeignKey("research_runs.id"), nullable=True)
    provider: Mapped[str] = mapped_column(String(80))
    model: Mapped[str | None] = mapped_column(String(80), nullable=True)
    tokens_in: Mapped[int] = mapped_column(Integer, default=0)
    tokens_out: Mapped[int] = mapped_column(Integer, default=0)
    estimated_cost_usd: Mapped[float] = mapped_column(Float, default=0.0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

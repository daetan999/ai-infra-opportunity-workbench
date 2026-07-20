from __future__ import annotations

from datetime import UTC, date, datetime
from enum import StrEnum

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    String,
    Text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def utc_now() -> datetime:
    """Return a SQLite-safe UTC timestamp."""

    return datetime.now(UTC).replace(tzinfo=None)


class Base(DeclarativeBase):
    pass


class EvidenceType(StrEnum):
    VERIFIED_FACT = "verified_fact"
    USER_PROVIDED = "user_provided"
    HYPOTHESIS = "hypothesis"
    GENERATED_SUGGESTION = "generated_suggestion"


EVIDENCE_TYPE = Enum(
    EvidenceType,
    values_callable=lambda enum_type: [item.value for item in enum_type],
    native_enum=False,
    validate_strings=True,
    length=32,
)


class Account(Base):
    __tablename__ = "accounts"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    industry: Mapped[str | None] = mapped_column(String(120))
    geography: Mapped[str | None] = mapped_column(String(120))
    segment: Mapped[str | None] = mapped_column(String(120))
    fictional: Mapped[bool] = mapped_column(Boolean(), default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(), default=utc_now, nullable=False
    )


class Opportunity(Base):
    __tablename__ = "opportunities"

    id: Mapped[int] = mapped_column(primary_key=True)
    account_id: Mapped[int] = mapped_column(
        ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text())
    stage: Mapped[str] = mapped_column(String(60), default="discovery", nullable=False)
    recommendation: Mapped[str | None] = mapped_column(String(40))
    owner: Mapped[str | None] = mapped_column(String(160))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(), default=utc_now, nullable=False
    )


class Signal(Base):
    __tablename__ = "signals"
    __table_args__ = (
        CheckConstraint(
            "confidence >= 0.0 AND confidence <= 1.0",
            name="ck_signals_confidence_range",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    account_id: Mapped[int] = mapped_column(
        ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    opportunity_id: Mapped[int | None] = mapped_column(
        ForeignKey("opportunities.id", ondelete="CASCADE"), index=True
    )
    title: Mapped[str] = mapped_column(String(240), nullable=False)
    description: Mapped[str | None] = mapped_column(Text())
    source: Mapped[str | None] = mapped_column(String(1000))
    source_url: Mapped[str | None] = mapped_column(String(2000))
    source_date: Mapped[date | None] = mapped_column(Date())
    evidence_type: Mapped[EvidenceType] = mapped_column(
        EVIDENCE_TYPE, default=EvidenceType.HYPOTHESIS, nullable=False
    )
    confidence: Mapped[float] = mapped_column(Float(), default=0.5, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text())
    created_at: Mapped[datetime] = mapped_column(
        DateTime(), default=utc_now, nullable=False
    )


class WorkloadHypothesis(Base):
    __tablename__ = "workload_hypotheses"
    __table_args__ = (
        CheckConstraint(
            "confidence >= 0.0 AND confidence <= 1.0",
            name="ck_workload_hypotheses_confidence_range",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    account_id: Mapped[int] = mapped_column(
        ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    opportunity_id: Mapped[int | None] = mapped_column(
        ForeignKey("opportunities.id", ondelete="CASCADE"), index=True
    )
    title: Mapped[str] = mapped_column(String(240), nullable=False)
    workload_type: Mapped[str | None] = mapped_column(String(80))
    deployment_pattern: Mapped[str | None] = mapped_column(String(120))
    description: Mapped[str | None] = mapped_column(Text())
    business_metric: Mapped[str | None] = mapped_column(String(240))
    success_metrics: Mapped[str | None] = mapped_column(Text())
    technical_requirements: Mapped[str | None] = mapped_column(Text())
    confidence: Mapped[float] = mapped_column(Float(), default=0.5, nullable=False)
    status: Mapped[str] = mapped_column(String(40), default="hypothesis", nullable=False)
    notes: Mapped[str | None] = mapped_column(Text())
    created_at: Mapped[datetime] = mapped_column(
        DateTime(), default=utc_now, nullable=False
    )


class Stakeholder(Base):
    __tablename__ = "stakeholders"

    id: Mapped[int] = mapped_column(primary_key=True)
    account_id: Mapped[int] = mapped_column(
        ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    opportunity_id: Mapped[int | None] = mapped_column(
        ForeignKey("opportunities.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    title: Mapped[str | None] = mapped_column(String(200))
    role: Mapped[str | None] = mapped_column(String(80))
    influence: Mapped[str | None] = mapped_column(String(40))
    relationship_status: Mapped[str | None] = mapped_column(String(60))
    is_champion: Mapped[bool] = mapped_column(Boolean(), default=False, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text())
    created_at: Mapped[datetime] = mapped_column(
        DateTime(), default=utc_now, nullable=False
    )


class DiscoveryRecord(Base):
    __tablename__ = "discovery_records"
    __table_args__ = (
        CheckConstraint(
            "confidence >= 0.0 AND confidence <= 1.0",
            name="ck_discovery_records_confidence_range",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    account_id: Mapped[int] = mapped_column(
        ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    opportunity_id: Mapped[int | None] = mapped_column(
        ForeignKey("opportunities.id", ondelete="CASCADE"), index=True
    )
    category: Mapped[str] = mapped_column(String(80), default="general", nullable=False)
    question: Mapped[str] = mapped_column(Text(), nullable=False)
    answer: Mapped[str | None] = mapped_column(Text())
    source: Mapped[str | None] = mapped_column(String(1000))
    source_url: Mapped[str | None] = mapped_column(String(2000))
    source_date: Mapped[date | None] = mapped_column(Date())
    evidence_type: Mapped[EvidenceType] = mapped_column(
        EVIDENCE_TYPE, default=EvidenceType.HYPOTHESIS, nullable=False
    )
    confidence: Mapped[float] = mapped_column(Float(), default=0.5, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text())
    created_at: Mapped[datetime] = mapped_column(
        DateTime(), default=utc_now, nullable=False
    )


class QualificationScore(Base):
    __tablename__ = "qualification_scores"
    __table_args__ = (
        CheckConstraint(
            "total_score >= 0.0 AND total_score <= 100.0",
            name="ck_qualification_scores_total_range",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    account_id: Mapped[int] = mapped_column(
        ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    opportunity_id: Mapped[int | None] = mapped_column(
        ForeignKey("opportunities.id", ondelete="CASCADE"), index=True
    )
    total_score: Mapped[float] = mapped_column(Float(), nullable=False)
    component_scores: Mapped[dict[str, float]] = mapped_column(JSON(), default=dict)
    missing_evidence: Mapped[list[str]] = mapped_column(JSON(), default=list)
    rationale: Mapped[str | None] = mapped_column(Text())
    recommendation: Mapped[str | None] = mapped_column(String(40))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(), default=utc_now, nullable=False
    )


class Risk(Base):
    __tablename__ = "risks"

    id: Mapped[int] = mapped_column(primary_key=True)
    account_id: Mapped[int] = mapped_column(
        ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    opportunity_id: Mapped[int | None] = mapped_column(
        ForeignKey("opportunities.id", ondelete="CASCADE"), index=True
    )
    title: Mapped[str] = mapped_column(String(240), nullable=False)
    category: Mapped[str | None] = mapped_column(String(80))
    severity: Mapped[str | None] = mapped_column(String(40))
    likelihood: Mapped[str | None] = mapped_column(String(40))
    impact: Mapped[str | None] = mapped_column(Text())
    mitigation: Mapped[str | None] = mapped_column(Text())
    status: Mapped[str] = mapped_column(String(40), default="open", nullable=False)
    notes: Mapped[str | None] = mapped_column(Text())
    created_at: Mapped[datetime] = mapped_column(
        DateTime(), default=utc_now, nullable=False
    )


class NextAction(Base):
    __tablename__ = "next_actions"

    id: Mapped[int] = mapped_column(primary_key=True)
    account_id: Mapped[int] = mapped_column(
        ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    opportunity_id: Mapped[int | None] = mapped_column(
        ForeignKey("opportunities.id", ondelete="CASCADE"), index=True
    )
    title: Mapped[str] = mapped_column(String(240), nullable=False)
    owner: Mapped[str | None] = mapped_column(String(160))
    due_date: Mapped[date | None] = mapped_column(Date())
    status: Mapped[str] = mapped_column(String(40), default="open", nullable=False)
    rationale: Mapped[str | None] = mapped_column(Text())
    notes: Mapped[str | None] = mapped_column(Text())
    created_at: Mapped[datetime] = mapped_column(
        DateTime(), default=utc_now, nullable=False
    )


class PoCPlan(Base):
    __tablename__ = "poc_plans"
    __table_args__ = (
        CheckConstraint(
            "readiness_score IS NULL OR "
            "(readiness_score >= 0.0 AND readiness_score <= 100.0)",
            name="ck_poc_plans_readiness_range",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    account_id: Mapped[int] = mapped_column(
        ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    opportunity_id: Mapped[int | None] = mapped_column(
        ForeignKey("opportunities.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(240), nullable=False)
    objective: Mapped[str | None] = mapped_column(Text())
    workload: Mapped[str | None] = mapped_column(Text())
    scope: Mapped[str | None] = mapped_column(Text())
    success_criteria: Mapped[list[str]] = mapped_column(JSON(), default=list)
    readiness_score: Mapped[float | None] = mapped_column(Float())
    status: Mapped[str] = mapped_column(String(40), default="draft", nullable=False)
    start_date: Mapped[date | None] = mapped_column(Date())
    end_date: Mapped[date | None] = mapped_column(Date())
    notes: Mapped[str | None] = mapped_column(Text())
    created_at: Mapped[datetime] = mapped_column(
        DateTime(), default=utc_now, nullable=False
    )

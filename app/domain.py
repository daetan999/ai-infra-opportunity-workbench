"""Immutable domain contracts for deterministic opportunity qualification."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class QualificationArea(str, Enum):
    MEASURABLE_PAIN = "measurable_pain"
    BUSINESS_IMPACT = "business_impact"
    TECHNICAL_FIT = "technical_fit"
    URGENCY = "urgency"
    EXECUTIVE_SPONSORSHIP = "executive_sponsorship"
    CHAMPION_STRENGTH = "champion_strength"
    BUYING_PROCESS_CLARITY = "buying_process_clarity"
    PROCUREMENT_FRICTION = "procurement_friction"
    COMPETITIVE_POSITION = "competitive_position"
    ACCESS_TO_TECHNICAL_EVIDENCE = "access_to_technical_evidence"


ALL_QUALIFICATION_AREAS: tuple[QualificationArea, ...] = tuple(QualificationArea)


class StakeholderRole(str, Enum):
    CHAMPION = "champion"
    EXECUTIVE_SPONSOR = "executive_sponsor"
    ECONOMIC_BUYER = "economic_buyer"
    TECHNICAL_EVALUATOR = "technical_evaluator"
    PROCUREMENT = "procurement"
    SECURITY = "security"
    OPERATIONS = "operations"


class RiskLevel(str, Enum):
    LOW = "Low"
    MEDIUM = "Medium"
    HIGH = "High"


class Recommendation(str, Enum):
    ADVANCE = "Advance"
    RESHAPE = "Reshape"
    NURTURE = "Nurture"
    DISQUALIFY = "Disqualify"


class PoCReadiness(str, Enum):
    READY = "Ready"
    CONDITIONAL = "Conditional"
    NOT_READY = "Not ready"


def _validate_int_range(name: str, value: object, minimum: int, maximum: int) -> None:
    if type(value) is not int:
        raise TypeError(f"{name} must be an integer")
    if not minimum <= value <= maximum:
        raise ValueError(f"{name} must be between {minimum} and {maximum}")


@dataclass(frozen=True, slots=True)
class QualificationSignal:
    """Evidence-backed score input for one qualification area.

    ``evidence_score`` represents qualification strength from 0 to 10.  The
    scoring engine gates it on actual evidence; an unsupported score contributes
    zero regardless of ``activity_count``.
    """

    area: QualificationArea
    evidence_score: int
    evidence: tuple[str, ...] = ()
    previous_score: int | None = None
    activity_count: int = 0

    def __post_init__(self) -> None:
        if not isinstance(self.area, QualificationArea):
            raise TypeError("area must be a QualificationArea")
        _validate_int_range("evidence_score", self.evidence_score, 0, 10)
        if self.previous_score is not None:
            _validate_int_range("previous_score", self.previous_score, 0, 10)
        _validate_int_range("activity_count", self.activity_count, 0, 1_000_000_000)
        if not isinstance(self.evidence, tuple):
            raise TypeError("evidence must be an immutable tuple")
        if any(not isinstance(item, str) for item in self.evidence):
            raise TypeError("each evidence item must be a string")
        if any(not item.strip() for item in self.evidence):
            raise ValueError("evidence items cannot be blank")


@dataclass(frozen=True, slots=True)
class StakeholderEngagement:
    role: StakeholderRole
    relationship_strength: int

    def __post_init__(self) -> None:
        if not isinstance(self.role, StakeholderRole):
            raise TypeError("role must be a StakeholderRole")
        _validate_int_range("relationship_strength", self.relationship_strength, 0, 3)


@dataclass(frozen=True, slots=True)
class OpportunityAssessment:
    signals: tuple[QualificationSignal, ...]
    stakeholders: tuple[StakeholderEngagement, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.signals, tuple):
            raise TypeError("signals must be an immutable tuple")
        if not all(isinstance(signal, QualificationSignal) for signal in self.signals):
            raise TypeError("signals must contain QualificationSignal values")
        areas = tuple(signal.area for signal in self.signals)
        if len(areas) != len(ALL_QUALIFICATION_AREAS) or set(areas) != set(
            ALL_QUALIFICATION_AREAS
        ):
            raise ValueError("signals must contain exactly one signal per qualification area")

        if not isinstance(self.stakeholders, tuple):
            raise TypeError("stakeholders must be an immutable tuple")
        if not all(
            isinstance(stakeholder, StakeholderEngagement)
            for stakeholder in self.stakeholders
        ):
            raise TypeError("stakeholders must contain StakeholderEngagement values")
        roles = tuple(stakeholder.role for stakeholder in self.stakeholders)
        if len(roles) != len(set(roles)):
            raise ValueError("each stakeholder role may appear only once")


@dataclass(frozen=True, slots=True)
class ComponentScore:
    area: QualificationArea
    score: int
    max_score: int
    previous_score: int | None
    change: int | None
    reason: str


@dataclass(frozen=True, slots=True)
class DiscoveryQuestion:
    role: StakeholderRole
    area: QualificationArea
    question: str


@dataclass(frozen=True, slots=True)
class OpportunityScore:
    components: tuple[ComponentScore, ...]
    total: int
    previous_total: int | None
    total_change: int | None
    missing_evidence: tuple[QualificationArea, ...]
    single_threading_risk: RiskLevel
    recommendation: Recommendation
    poc_readiness: PoCReadiness
    discovery_questions: tuple[DiscoveryQuestion, ...]

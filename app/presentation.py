from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import asdict

from app.domain import (
    ALL_QUALIFICATION_AREAS,
    OpportunityAssessment,
    OpportunityScore,
    PoCReadiness,
    QualificationArea,
    QualificationSignal,
    StakeholderEngagement,
    StakeholderRole,
)
from app.repository import OpportunityRepository
from app.scoring import score_opportunity

_DISCOVERY_CATEGORY: dict[QualificationArea, str] = {
    QualificationArea.MEASURABLE_PAIN: "measurable_pain",
    QualificationArea.BUSINESS_IMPACT: "business_impact",
    QualificationArea.URGENCY: "urgency",
    QualificationArea.BUYING_PROCESS_CLARITY: "buying_process",
    QualificationArea.PROCUREMENT_FRICTION: "procurement_friction",
    QualificationArea.COMPETITIVE_POSITION: "competitive_position",
}

_STAKEHOLDER_ROLE: dict[str, StakeholderRole] = {
    "champion": StakeholderRole.CHAMPION,
    "economic_buyer": StakeholderRole.ECONOMIC_BUYER,
    "executive_sponsor": StakeholderRole.EXECUTIVE_SPONSOR,
    "technical_buyer": StakeholderRole.TECHNICAL_EVALUATOR,
    "procurement": StakeholderRole.PROCUREMENT,
    "security": StakeholderRole.SECURITY,
    "operations": StakeholderRole.OPERATIONS,
}

_RELATIONSHIP_STRENGTH = {
    "unknown": 0,
    "identified": 1,
    "engaged": 3,
    "confirmed": 3,
}

_EVIDENCE_CAP = {
    "verified_fact": 10,
    "user_provided": 10,
    "hypothesis": 5,
    "generated_suggestion": 3,
}


def _evidence_score(record: Mapping[str, object]) -> int:
    confidence = float(record.get("confidence") or 0)
    evidence_type = str(record.get("evidence_type") or "hypothesis")
    return min(round(confidence * 10), _EVIDENCE_CAP.get(evidence_type, 0))


def _records_for_category(
    discoveries: Sequence[Mapping[str, object]], category: str
) -> tuple[Mapping[str, object], ...]:
    return tuple(record for record in discoveries if record.get("category") == category)


def _record_signal(
    area: QualificationArea,
    records: Sequence[Mapping[str, object]],
    previous_score: int | None,
    activity_count: int,
) -> QualificationSignal:
    evidence = tuple(
        str(record.get("answer") or record.get("description") or record.get("title"))
        for record in records
        if record.get("answer") or record.get("description") or record.get("title")
    )
    score = max((_evidence_score(record) for record in records), default=0)
    return QualificationSignal(
        area=area,
        evidence_score=score,
        evidence=evidence,
        previous_score=previous_score,
        activity_count=activity_count,
    )


def _stakeholder_signal(
    area: QualificationArea,
    stakeholders: Sequence[Mapping[str, object]],
    accepted_roles: set[str],
    previous_score: int | None,
    activity_count: int,
) -> QualificationSignal:
    matching = tuple(
        record for record in stakeholders if record.get("role") in accepted_roles
    )
    evidence = tuple(
        f"{record.get('title') or record.get('name')} is "
        f"{record.get('relationship_status') or 'unknown'}"
        for record in matching
    )
    strength = max(
        (
            _RELATIONSHIP_STRENGTH.get(str(record.get("relationship_status") or "unknown"), 0)
            for record in matching
        ),
        default=0,
    )
    score = {0: 0, 1: 5, 2: 7, 3: 9}[strength]
    return QualificationSignal(
        area=area,
        evidence_score=score,
        evidence=evidence,
        previous_score=previous_score,
        activity_count=activity_count,
    )


def build_assessment(repository: OpportunityRepository, account_id: int) -> OpportunityAssessment:
    signals = repository.list_related(account_id, "signal")
    workloads = repository.list_related(account_id, "workload_hypothesis")
    stakeholders = repository.list_related(account_id, "stakeholder")
    discoveries = repository.list_related(account_id, "discovery_record")
    previous = repository.list_related(account_id, "qualification_score")
    previous_components = previous[-1].get("component_scores", {}) if previous else {}
    activity_count = len(signals) + len(discoveries)

    qualification_signals: list[QualificationSignal] = []
    for area in ALL_QUALIFICATION_AREAS:
        previous_score = None
        if isinstance(previous_components, Mapping) and area.value in previous_components:
            previous_score = int(previous_components[area.value])

        if area in _DISCOVERY_CATEGORY:
            qualification_signals.append(
                _record_signal(
                    area,
                    _records_for_category(discoveries, _DISCOVERY_CATEGORY[area]),
                    previous_score,
                    activity_count,
                )
            )
        elif area is QualificationArea.TECHNICAL_FIT:
            qualification_signals.append(
                _record_signal(area, workloads, previous_score, activity_count)
            )
        elif area is QualificationArea.EXECUTIVE_SPONSORSHIP:
            qualification_signals.append(
                _stakeholder_signal(
                    area,
                    stakeholders,
                    {"executive_sponsor", "economic_buyer"},
                    previous_score,
                    activity_count,
                )
            )
        elif area is QualificationArea.CHAMPION_STRENGTH:
            qualification_signals.append(
                _stakeholder_signal(
                    area,
                    stakeholders,
                    {"champion"},
                    previous_score,
                    activity_count,
                )
            )
        else:
            technical_records = tuple(
                signal
                for signal in signals
                if signal.get("evidence_type") in {"verified_fact", "user_provided"}
            )
            qualification_signals.append(
                _record_signal(area, technical_records, previous_score, activity_count)
            )

    engagements_by_role: dict[StakeholderRole, int] = {}
    for stakeholder in stakeholders:
        role = _STAKEHOLDER_ROLE.get(str(stakeholder.get("role") or ""))
        if role is None:
            continue
        strength = _RELATIONSHIP_STRENGTH.get(
            str(stakeholder.get("relationship_status") or "unknown"), 0
        )
        engagements_by_role[role] = max(engagements_by_role.get(role, 0), strength)

    engagements = tuple(
        StakeholderEngagement(role=role, relationship_strength=strength)
        for role, strength in engagements_by_role.items()
    )
    return OpportunityAssessment(signals=tuple(qualification_signals), stakeholders=engagements)


def score_account(repository: OpportunityRepository, account_id: int) -> OpportunityScore:
    return score_opportunity(build_assessment(repository, account_id))


def score_payload(result: OpportunityScore) -> dict[str, object]:
    components = {
        component.area.value: {
            "score": component.score,
            "max_score": component.max_score,
            "previous_score": component.previous_score,
            "change": component.change,
            "reason": component.reason,
        }
        for component in result.components
    }
    missing = [area.value for area in result.missing_evidence]
    risks: list[dict[str, str]] = []
    if result.single_threading_risk.value != "Low":
        risks.append(
            {
                "level": result.single_threading_risk.value,
                "title": "Single-threading risk",
                "mitigation": "Engage distinct economic, technical, and champion roles.",
            }
        )
    if missing:
        risks.append(
            {
                "level": "High" if len(missing) >= 4 else "Medium",
                "title": "Missing qualification evidence",
                "mitigation": "Resolve the lowest-scoring evidence gaps before progression.",
            }
        )
    return {
        "total": result.total,
        "overall": result.total,
        "previous_total": result.previous_total,
        "total_change": result.total_change,
        "components": components,
        "dimensions": [
            {
                "name": component.area.value.replace("_", " ").title(),
                "value": component.score,
                "max": component.max_score,
                "evidence": component.reason,
            }
            for component in result.components
        ],
        "missing_evidence": missing,
        "single_threading_risk": result.single_threading_risk.value,
        "recommendation": result.recommendation.value,
        "label": result.recommendation.value,
        "status": "Qualified" if result.recommendation.value == "Advance" else "Needs evidence",
        "summary": "Evidence-based qualification; activity volume is excluded from scoring.",
        "risks": risks,
        "questions": [asdict(question) for question in result.discovery_questions],
    }


def poc_payload(result: OpportunityScore) -> dict[str, object]:
    numeric_score = {
        PoCReadiness.READY: 90,
        PoCReadiness.CONDITIONAL: 60,
        PoCReadiness.NOT_READY: 20,
    }[result.poc_readiness]
    component_scores = {component.area: component.score for component in result.components}
    criteria = (
        (
            "Representative workload",
            component_scores[QualificationArea.TECHNICAL_FIT] >= 6,
            "Workload constraints and acceptance criteria are documented.",
        ),
        (
            "Baseline evidence",
            component_scores[QualificationArea.ACCESS_TO_TECHNICAL_EVIDENCE] >= 6,
            "A measurable current-state baseline is available.",
        ),
        (
            "Decision path",
            component_scores[QualificationArea.BUYING_PROCESS_CLARITY] >= 6,
            "Decision criteria, reviewers, and timing are known.",
        ),
        (
            "Technical partner",
            result.single_threading_risk.value != "High",
            "A technical stakeholder can support the evaluation.",
        ),
    )
    return {
        "status": result.poc_readiness.value,
        "score": numeric_score,
        "ready": result.poc_readiness is PoCReadiness.READY,
        "label": result.poc_readiness.value,
        "summary": (
            "Readiness is derived from technical evidence, stakeholder coverage, "
            "and decision clarity."
        ),
        "criteria": [
            {"label": label, "complete": complete, "detail": detail}
            for label, complete, detail in criteria
        ],
    }


def recommended_next_action(result: OpportunityScore) -> str:
    return {
        "Advance": "Schedule a bounded technical validation with named success criteria.",
        "Reshape": "Close the highest-impact evidence gap before committing solution resources.",
        "Nurture": "Maintain a dated learning plan and confirm whether urgency or impact changes.",
        "Disqualify": "Document the technical or business-fit failure and close the active motion.",
    }[result.recommendation.value]

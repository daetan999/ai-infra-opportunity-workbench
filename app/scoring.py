"""Pure, deterministic opportunity scoring with no model or network calls."""

from __future__ import annotations

from app.domain import (
    ALL_QUALIFICATION_AREAS,
    ComponentScore,
    DiscoveryQuestion,
    OpportunityAssessment,
    OpportunityScore,
    PoCReadiness,
    QualificationArea,
    QualificationSignal,
    Recommendation,
    RiskLevel,
    StakeholderRole,
)

MAX_COMPONENT_SCORE = 10

_DISCOVERY_PROMPTS: dict[
    QualificationArea, tuple[StakeholderRole, str]
] = {
    QualificationArea.MEASURABLE_PAIN: (
        StakeholderRole.CHAMPION,
        "Which operational pain can we baseline with a current metric and owner?",
    ),
    QualificationArea.BUSINESS_IMPACT: (
        StakeholderRole.ECONOMIC_BUYER,
        "What financial or strategic outcome would justify acting on this opportunity?",
    ),
    QualificationArea.TECHNICAL_FIT: (
        StakeholderRole.TECHNICAL_EVALUATOR,
        "Which workload constraints and acceptance criteria must the solution satisfy?",
    ),
    QualificationArea.URGENCY: (
        StakeholderRole.EXECUTIVE_SPONSOR,
        "Which dated business event makes this outcome important now?",
    ),
    QualificationArea.EXECUTIVE_SPONSORSHIP: (
        StakeholderRole.EXECUTIVE_SPONSOR,
        "Who will sponsor decisions and remove cross-functional blockers?",
    ),
    QualificationArea.CHAMPION_STRENGTH: (
        StakeholderRole.CHAMPION,
        "How will you mobilize internal stakeholders and share decision context?",
    ),
    QualificationArea.BUYING_PROCESS_CLARITY: (
        StakeholderRole.ECONOMIC_BUYER,
        "Which approvals, decision criteria, and decision date govern the purchase?",
    ),
    QualificationArea.PROCUREMENT_FRICTION: (
        StakeholderRole.PROCUREMENT,
        "Which commercial, legal, security, or vendor steps could delay approval?",
    ),
    QualificationArea.COMPETITIVE_POSITION: (
        StakeholderRole.CHAMPION,
        "Which alternatives, including no action, are being compared and on what criteria?",
    ),
    QualificationArea.ACCESS_TO_TECHNICAL_EVIDENCE: (
        StakeholderRole.TECHNICAL_EVALUATOR,
        "Which representative data, telemetry, and workload access can support validation?",
    ),
}


def score_opportunity(assessment: OpportunityAssessment) -> OpportunityScore:
    """Score a validated assessment using explicit, stable business rules."""

    if not isinstance(assessment, OpportunityAssessment):
        raise TypeError("assessment must be an OpportunityAssessment")

    signals = {signal.area: signal for signal in assessment.signals}
    components = tuple(
        _score_component(signals[area]) for area in ALL_QUALIFICATION_AREAS
    )
    scores = {component.area: component.score for component in components}
    total = sum(scores.values())
    missing_evidence = tuple(
        component.area for component in components if not signals[component.area].evidence
    )
    risk = _single_threading_risk(assessment)
    recommendation = _recommend(total, scores, risk)
    readiness = _poc_readiness(total, scores, assessment)

    previous_scores = tuple(component.previous_score for component in components)
    has_complete_history = all(score is not None for score in previous_scores)
    previous_total = (
        sum(score for score in previous_scores if score is not None)
        if has_complete_history
        else None
    )

    return OpportunityScore(
        components=components,
        total=total,
        previous_total=previous_total,
        total_change=total - previous_total if previous_total is not None else None,
        missing_evidence=missing_evidence,
        single_threading_risk=risk,
        recommendation=recommendation,
        poc_readiness=readiness,
        discovery_questions=_discovery_questions(scores),
    )


def _score_component(signal: QualificationSignal) -> ComponentScore:
    score = signal.evidence_score if signal.evidence else 0
    previous_score = signal.previous_score
    change = score - previous_score if previous_score is not None else None
    label = signal.area.value.replace("_", " ").capitalize()

    if signal.evidence:
        count = len(signal.evidence)
        noun = "item" if count == 1 else "items"
        reason = (
            f"{label} scored {score}/10 from {count} qualifying evidence {noun}; "
            "activity volume was excluded."
        )
    else:
        reason = (
            f"No qualifying evidence supplied for {signal.area.value.replace('_', ' ')}; "
            f"{signal.activity_count} recorded activities did not increase the score."
        )

    return ComponentScore(
        area=signal.area,
        score=score,
        max_score=MAX_COMPONENT_SCORE,
        previous_score=previous_score,
        change=change,
        reason=reason,
    )


def _single_threading_risk(assessment: OpportunityAssessment) -> RiskLevel:
    engaged_roles = {
        stakeholder.role
        for stakeholder in assessment.stakeholders
        if stakeholder.relationship_strength >= 2
    }
    if len(engaged_roles) <= 1:
        return RiskLevel.HIGH
    if (
        len(engaged_roles) >= 3
        and StakeholderRole.EXECUTIVE_SPONSOR in engaged_roles
        and StakeholderRole.TECHNICAL_EVALUATOR in engaged_roles
    ):
        return RiskLevel.LOW
    return RiskLevel.MEDIUM


def _recommend(
    total: int,
    scores: dict[QualificationArea, int],
    risk: RiskLevel,
) -> Recommendation:
    pain = scores[QualificationArea.MEASURABLE_PAIN]
    impact = scores[QualificationArea.BUSINESS_IMPACT]
    technical_fit = scores[QualificationArea.TECHNICAL_FIT]

    if technical_fit <= 2 or (pain <= 2 and impact <= 2):
        return Recommendation.DISQUALIFY

    advance_gates = (
        pain >= 6,
        impact >= 6,
        technical_fit >= 6,
        scores[QualificationArea.EXECUTIVE_SPONSORSHIP] >= 6,
        scores[QualificationArea.CHAMPION_STRENGTH] >= 6,
        scores[QualificationArea.BUYING_PROCESS_CLARITY] >= 6,
        scores[QualificationArea.ACCESS_TO_TECHNICAL_EVIDENCE] >= 6,
        risk is not RiskLevel.HIGH,
    )
    if total >= 75 and all(advance_gates):
        return Recommendation.ADVANCE
    if total >= 50 or pain >= 8 or impact >= 8:
        return Recommendation.RESHAPE
    return Recommendation.NURTURE


def _poc_readiness(
    total: int,
    scores: dict[QualificationArea, int],
    assessment: OpportunityAssessment,
) -> PoCReadiness:
    technical_fit = scores[QualificationArea.TECHNICAL_FIT]
    technical_evidence = scores[QualificationArea.ACCESS_TO_TECHNICAL_EVIDENCE]
    has_technical_partner = any(
        stakeholder.role is StakeholderRole.TECHNICAL_EVALUATOR
        and stakeholder.relationship_strength >= 2
        for stakeholder in assessment.stakeholders
    )

    if (
        total >= 75
        and technical_fit >= 8
        and technical_evidence >= 8
        and scores[QualificationArea.URGENCY] >= 6
        and scores[QualificationArea.BUYING_PROCESS_CLARITY] >= 6
        and has_technical_partner
    ):
        return PoCReadiness.READY
    if total >= 50 and technical_fit >= 6 and technical_evidence >= 4:
        return PoCReadiness.CONDITIONAL
    return PoCReadiness.NOT_READY


def _discovery_questions(
    scores: dict[QualificationArea, int],
) -> tuple[DiscoveryQuestion, ...]:
    order = {area: index for index, area in enumerate(ALL_QUALIFICATION_AREAS)}
    prioritized = sorted(
        ALL_QUALIFICATION_AREAS,
        key=lambda area: (scores[area], order[area]),
    )
    return tuple(
        DiscoveryQuestion(
            role=_DISCOVERY_PROMPTS[area][0],
            area=area,
            question=_DISCOVERY_PROMPTS[area][1],
        )
        for area in prioritized
    )

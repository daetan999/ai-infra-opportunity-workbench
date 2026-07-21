from dataclasses import FrozenInstanceError

import pytest

from app.domain import (
    ALL_QUALIFICATION_AREAS,
    DiscoveryQuestion,
    OpportunityAssessment,
    PoCReadiness,
    QualificationArea,
    QualificationSignal,
    Recommendation,
    RiskLevel,
    StakeholderEngagement,
    StakeholderRole,
)
from app.scoring import score_opportunity


def signal(
    area: QualificationArea,
    score: int,
    *,
    has_evidence: bool = True,
    previous_score: int | None = None,
    activity_count: int = 0,
) -> QualificationSignal:
    evidence = (f"Verified evidence for {area.value}.",) if has_evidence else ()
    return QualificationSignal(
        area=area,
        evidence_score=score,
        evidence=evidence,
        previous_score=previous_score,
        activity_count=activity_count,
    )


def assessment(
    scores: dict[QualificationArea, int],
    *,
    no_evidence: frozenset[QualificationArea] = frozenset(),
    previous_scores: dict[QualificationArea, int] | None = None,
    stakeholders: tuple[StakeholderEngagement, ...] = (),
    activity_count: int = 0,
) -> OpportunityAssessment:
    previous_scores = previous_scores or {}
    return OpportunityAssessment(
        signals=tuple(
            signal(
                area,
                scores[area],
                has_evidence=area not in no_evidence,
                previous_score=previous_scores.get(area),
                activity_count=activity_count,
            )
            for area in ALL_QUALIFICATION_AREAS
        ),
        stakeholders=stakeholders,
    )


def uniform_scores(value: int) -> dict[QualificationArea, int]:
    return {area: value for area in ALL_QUALIFICATION_AREAS}


HEALTHY_STAKEHOLDERS = (
    StakeholderEngagement(StakeholderRole.CHAMPION, 3),
    StakeholderEngagement(StakeholderRole.EXECUTIVE_SPONSOR, 2),
    StakeholderEngagement(StakeholderRole.TECHNICAL_EVALUATOR, 3),
)


def component(result, area: QualificationArea):
    return next(item for item in result.components if item.area is area)


def test_high_evidence_opportunity_advances_and_is_poc_ready():
    result = score_opportunity(
        assessment(uniform_scores(9), stakeholders=HEALTHY_STAKEHOLDERS)
    )

    assert len(result.components) == 10
    assert result.total == 90
    assert result.recommendation is Recommendation.ADVANCE
    assert result.poc_readiness is PoCReadiness.READY
    assert result.single_threading_risk is RiskLevel.LOW
    assert result.missing_evidence == ()
    assert all(item.max_score == 10 for item in result.components)


def test_medium_opportunity_is_reshaped_and_conditionally_poc_ready():
    result = score_opportunity(
        assessment(
            uniform_scores(6),
            stakeholders=(
                StakeholderEngagement(StakeholderRole.CHAMPION, 2),
                StakeholderEngagement(StakeholderRole.TECHNICAL_EVALUATOR, 2),
            ),
        )
    )

    assert result.total == 60
    assert result.recommendation is Recommendation.RESHAPE
    assert result.poc_readiness is PoCReadiness.CONDITIONAL
    assert result.single_threading_risk is RiskLevel.MEDIUM


def test_low_technical_fit_disqualifies_an_opportunity():
    scores = uniform_scores(3)
    scores[QualificationArea.TECHNICAL_FIT] = 2

    result = score_opportunity(assessment(scores))

    assert result.recommendation is Recommendation.DISQUALIFY
    assert result.poc_readiness is PoCReadiness.NOT_READY
    assert result.single_threading_risk is RiskLevel.HIGH


def test_low_but_viable_opportunity_is_nurtured():
    result = score_opportunity(assessment(uniform_scores(4)))

    assert result.total == 40
    assert result.recommendation is Recommendation.NURTURE


def test_advance_threshold_is_inclusive_and_explainable():
    values = (8, 8, 8, 8, 8, 8, 7, 6, 7, 7)
    scores = dict(zip(ALL_QUALIFICATION_AREAS, values, strict=True))

    result = score_opportunity(assessment(scores, stakeholders=HEALTHY_STAKEHOLDERS))

    assert result.total == 75
    assert result.recommendation is Recommendation.ADVANCE
    assert all(item.reason for item in result.components)


def test_single_threading_prevents_advance_even_with_high_scores():
    result = score_opportunity(
        assessment(
            uniform_scores(9),
            stakeholders=(StakeholderEngagement(StakeholderRole.CHAMPION, 3),),
        )
    )

    assert result.single_threading_risk is RiskLevel.HIGH
    assert result.recommendation is Recommendation.RESHAPE


def test_activity_volume_never_substitutes_for_evidence():
    missing_area = QualificationArea.MEASURABLE_PAIN
    result = score_opportunity(
        assessment(
            uniform_scores(9),
            no_evidence=frozenset({missing_area}),
            stakeholders=HEALTHY_STAKEHOLDERS,
            activity_count=10_000,
        )
    )

    pain = component(result, missing_area)
    assert pain.score == 0
    assert missing_area in result.missing_evidence
    assert "did not increase" in pain.reason
    assert result.recommendation is Recommendation.RESHAPE


def test_activity_count_does_not_change_a_supported_component_score():
    quiet = score_opportunity(assessment(uniform_scores(7), activity_count=0))
    busy = score_opportunity(assessment(uniform_scores(7), activity_count=500))

    assert quiet.total == busy.total
    assert tuple(item.score for item in quiet.components) == tuple(
        item.score for item in busy.components
    )


def test_previous_scores_produce_component_and_total_changes():
    result = score_opportunity(
        assessment(
            uniform_scores(7),
            previous_scores=uniform_scores(5),
            stakeholders=HEALTHY_STAKEHOLDERS,
        )
    )

    assert result.previous_total == 50
    assert result.total_change == 20
    assert all(item.previous_score == 5 for item in result.components)
    assert all(item.change == 2 for item in result.components)


def test_partial_previous_scores_have_component_deltas_but_no_total_delta():
    previous = {QualificationArea.URGENCY: 8}
    result = score_opportunity(assessment(uniform_scores(7), previous_scores=previous))

    urgency = component(result, QualificationArea.URGENCY)
    assert urgency.change == -1
    assert result.previous_total is None
    assert result.total_change is None


def test_questions_are_typed_stakeholder_specific_and_prioritize_gaps():
    missing = QualificationArea.BUYING_PROCESS_CLARITY
    result = score_opportunity(
        assessment(uniform_scores(8), no_evidence=frozenset({missing}))
    )

    assert len(result.discovery_questions) == 10
    assert all(isinstance(item, DiscoveryQuestion) for item in result.discovery_questions)
    assert result.discovery_questions[0].area is missing
    assert result.discovery_questions[0].role is StakeholderRole.ECONOMIC_BUYER
    assert result.discovery_questions[0].question.endswith("?")


@pytest.mark.parametrize("invalid", [-1, 11, True, 3.5])
def test_signal_rejects_invalid_score_ranges_and_types(invalid):
    with pytest.raises((TypeError, ValueError)):
        QualificationSignal(
            area=QualificationArea.URGENCY,
            evidence_score=invalid,
            evidence=("A dated business event is documented.",),
        )


@pytest.mark.parametrize("invalid", [-1, 11, True, 2.5])
def test_signal_rejects_invalid_previous_scores(invalid):
    with pytest.raises((TypeError, ValueError)):
        QualificationSignal(
            area=QualificationArea.URGENCY,
            evidence_score=5,
            evidence=("A dated business event is documented.",),
            previous_score=invalid,
        )


@pytest.mark.parametrize("invalid", [-1, True, 1.5])
def test_signal_rejects_invalid_activity_counts(invalid):
    with pytest.raises((TypeError, ValueError)):
        QualificationSignal(
            area=QualificationArea.URGENCY,
            evidence_score=5,
            evidence=("A dated business event is documented.",),
            activity_count=invalid,
        )


def test_signal_rejects_unknown_qualification_area_and_mutable_evidence():
    with pytest.raises(TypeError):
        QualificationSignal(
            area="urgency",
            evidence_score=5,
            evidence=("A dated business event is documented.",),
        )

    with pytest.raises(TypeError):
        QualificationSignal(
            area=QualificationArea.URGENCY,
            evidence_score=5,
            evidence=["A dated business event is documented."],
        )


def test_signal_rejects_blank_evidence_items():
    with pytest.raises(ValueError, match="blank"):
        QualificationSignal(
            area=QualificationArea.URGENCY,
            evidence_score=5,
            evidence=("  ",),
        )


@pytest.mark.parametrize("invalid", [-1, 4, True, 1.5])
def test_stakeholder_rejects_invalid_relationship_strength(invalid):
    with pytest.raises((TypeError, ValueError)):
        StakeholderEngagement(StakeholderRole.CHAMPION, invalid)


def test_stakeholder_rejects_unknown_role():
    with pytest.raises(TypeError):
        StakeholderEngagement("coach", 2)


def test_assessment_requires_exactly_one_signal_per_area():
    valid = tuple(signal(area, 5) for area in ALL_QUALIFICATION_AREAS)

    with pytest.raises(ValueError, match="exactly one"):
        OpportunityAssessment(signals=valid[:-1])

    with pytest.raises(ValueError, match="exactly one"):
        OpportunityAssessment(signals=(*valid, valid[0]))


def test_assessment_rejects_duplicate_stakeholder_roles_and_mutable_inputs():
    valid = tuple(signal(area, 5) for area in ALL_QUALIFICATION_AREAS)

    with pytest.raises(ValueError, match="stakeholder role"):
        OpportunityAssessment(
            signals=valid,
            stakeholders=(
                StakeholderEngagement(StakeholderRole.CHAMPION, 2),
                StakeholderEngagement(StakeholderRole.CHAMPION, 3),
            ),
        )

    with pytest.raises(TypeError):
        OpportunityAssessment(signals=list(valid))


def test_domain_inputs_and_results_are_immutable():
    source = assessment(uniform_scores(7))
    result = score_opportunity(source)

    with pytest.raises(FrozenInstanceError):
        source.signals[0].evidence_score = 10

    with pytest.raises(FrozenInstanceError):
        result.total = 100

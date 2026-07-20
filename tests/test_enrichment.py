from __future__ import annotations

from app.enrichment import enrich_executive_summary


class FakeNarrativeClient:
    def __init__(self, response: str = "Concise generated suggestion.") -> None:
        self.response = response
        self.prompts: list[str] = []

    def rewrite(self, prompt: str) -> str:
        self.prompts.append(prompt)
        return self.response


class FailingNarrativeClient:
    def rewrite(self, prompt: str) -> str:
        raise RuntimeError("provider unavailable")


def test_offline_mode_returns_deterministic_summary() -> None:
    result = enrich_executive_summary(
        deterministic_summary="Validated pain; procurement path remains unknown.",
        evidence=["User supplied a latency baseline."],
        client=None,
    )

    assert result.text == "Validated pain; procurement path remains unknown."
    assert result.mode == "deterministic"
    assert result.evidence_type == "user_provided"


def test_optional_model_output_is_labelled_and_constrained_to_supplied_evidence() -> None:
    client = FakeNarrativeClient()

    result = enrich_executive_summary(
        deterministic_summary="Validated pain; procurement path remains unknown.",
        evidence=["User supplied a latency baseline."],
        client=client,
    )

    assert result.text == "Concise generated suggestion."
    assert result.mode == "optional_model"
    assert result.evidence_type == "generated_suggestion"
    assert len(client.prompts) == 1
    assert "Do not invent" in client.prompts[0]
    assert "User supplied a latency baseline." in client.prompts[0]
    assert "qualification score" not in client.prompts[0].lower()


def test_provider_failure_or_blank_output_falls_back_without_losing_summary() -> None:
    baseline = "Deterministic executive summary."

    failed = enrich_executive_summary(baseline, [], FailingNarrativeClient())
    blank = enrich_executive_summary(baseline, [], FakeNarrativeClient("   "))

    assert failed.text == baseline
    assert blank.text == baseline
    assert failed.mode == blank.mode == "deterministic"

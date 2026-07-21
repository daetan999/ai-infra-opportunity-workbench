from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol


class NarrativeClient(Protocol):
    def rewrite(self, prompt: str) -> str: ...


@dataclass(frozen=True, slots=True)
class EnrichmentResult:
    text: str
    mode: str
    evidence_type: str


def enrich_executive_summary(
    deterministic_summary: str,
    evidence: Sequence[str],
    client: NarrativeClient | None,
) -> EnrichmentResult:
    """Optionally rewrite a deterministic brief without changing facts or scores."""
    baseline = deterministic_summary.strip()
    fallback = EnrichmentResult(
        text=baseline,
        mode="deterministic",
        evidence_type="user_provided",
    )
    if client is None:
        return fallback

    evidence_block = "\n".join(f"- {item.strip()}" for item in evidence if item.strip())
    prompt = (
        "Rewrite the supplied deterministic executive brief for clarity. "
        "Do not invent companies, people, budgets, deployments, contracts, dates, or results. "
        "Use only the evidence listed below. Preserve uncertainty and missing-information labels. "
        "Return prose only; do not calculate or alter any score.\n\n"
        "Deterministic brief:\n"
        f"{baseline}\n\nEvidence:\n{evidence_block or '- No additional evidence'}"
    )
    try:
        suggestion = client.rewrite(prompt).strip()
    except Exception:  # Provider failure must never break the offline workflow.
        return fallback
    if not suggestion:
        return fallback
    return EnrichmentResult(
        text=suggestion,
        mode="optional_model",
        evidence_type="generated_suggestion",
    )

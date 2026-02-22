"""
Canonical ConfidenceV3 schema (v3.2).
All confidence outputs should migrate to this single object.
"""

from __future__ import annotations
from pydantic import BaseModel, Field
from typing import Dict, List, Literal, Optional, Any


FactorKey = Literal[
    "valuation_dcf",
    "macro",
    "industry",
    "company",
    "volatility",
    "earnings",
    "liquidity",
    "alpha",
    "technical",
    "options_pricing",
    "skew",
    "positioning",
    "qualitative_proxy",  # NEW: deterministic qualitative proxy composite
]


class ConfidenceFactor(BaseModel):
    score_01: float = Field(ge=0.0, le=1.0)
    weight_01: float = Field(ge=0.0, le=1.0)
    contribution_01: float = Field(ge=0.0, le=1.0)
    status: Literal["ok", "missing", "neutral", "derived"] = "neutral"
    notes: List[str] = Field(default_factory=list)
    inputs: Dict[str, Any] = Field(default_factory=dict)


class ConfidenceV3(BaseModel):
    """
    Canonical single confidence object v3.2.

    Governance rules:
      - total_0_100 is the ONLY score that drives risk controls / sizing / blocked.
      - All weight_01 across active factors must sum to 1.0.
      - contribution_01 == score_01 * weight_01 for every factor.
      - Missing factors are re-normalised out of weights (not silently zero-weighted).
      - AI may NEVER modify this object.
    """
    version: str = "3.2"
    mode: Literal["stock", "options"]

    # Primary score
    total_0_100: int = Field(ge=0, le=100)
    raw_01: float = Field(ge=0.0, le=1.0)
    grade: Literal["A", "B", "C", "D", "F"] = "C"

    # Factors
    factors: Dict[str, ConfidenceFactor] = Field(default_factory=dict)

    # Data provenance
    signals_used: List[str] = Field(default_factory=list)
    missing_modules: List[str] = Field(default_factory=list)

    # Penalties and caps
    missing_penalty_points: int = Field(default=0, ge=0, le=30)
    overlay_delta_points: int = Field(default=0, ge=-10, le=10)
    caps_applied: List[str] = Field(default_factory=list)

    # Execution gating
    blocked: bool = False
    blocked_reason: Optional[str] = None

    debug: Dict[str, Any] = Field(default_factory=dict)

    @staticmethod
    def grade_from_score(total: int) -> Literal["A", "B", "C", "D", "F"]:
        if total >= 80:
            return "A"
        if total >= 65:
            return "B"
        if total >= 50:
            return "C"
        if total >= 35:
            return "D"
        return "F"

    def validate_weights(self) -> None:
        """Assert all active factor weights sum to 1.0."""
        wsum = sum(f.weight_01 for f in self.factors.values())
        if abs(wsum - 1.0) > 1e-6:
            raise ValueError(
                f"ConfidenceV3 weights must sum to 1.0, got {wsum:.6f}"
            )
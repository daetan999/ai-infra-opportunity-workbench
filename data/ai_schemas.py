"""
Structured output schemas for Gemini AI responses.
Used with response_mime_type="application/json" and response_json_schema=...
"""

from __future__ import annotations
from pydantic import BaseModel, Field
from typing import List, Optional, Literal, Dict, Any


# ---------------------------------------------------------------------------
# Price / target sub-schemas
# ---------------------------------------------------------------------------

class AIPriceGuidance(BaseModel):
    entry_normal_low: float
    entry_normal_high: float
    entry_conservative_low: float
    entry_conservative_high: float


class AITargets(BaseModel):
    base: float
    bull: float
    bear: float


# ---------------------------------------------------------------------------
# Primary AI analysis response (schema-bound structured output)
# ---------------------------------------------------------------------------

class AIAnalysisResponse(BaseModel):
    """
    Schema-bound Gemini output.
    All fields are required so the model cannot omit them.
    Sent via response_json_schema config — do NOT duplicate in prompt.
    """
    # Core analysis
    narrative: str = Field(
        description=(
            "Full analysis: executive summary, bull case, bear case, "
            "positioning (2-4 paragraphs)."
        )
    )
    time_horizon: str = Field(
        description="One of: 'Trade (days-weeks)', 'Swing (weeks-months)', 'Investment (months-years)'."
    )
    key_drivers: List[str] = Field(
        description="3-5 specific, measurable drivers to monitor."
    )
    risks: List[str] = Field(
        description="3-5 specific risks with potential impact."
    )
    targets: AITargets = Field(
        description=(
            "Price targets. base must be <= spot*(1+2*implied_move_pct). "
            "If reasonableness<3, cap at spot*(1+implied_move_pct)."
        )
    )
    price_guidance: AIPriceGuidance = Field(
        description="Entry zones. For bullish stance: entries should be below or at spot."
    )

    # AI Conviction fields (NEW)
    conviction_0_100: int = Field(
        ge=0, le=100,
        description=(
            "AI thesis-strength conviction 0-100. High (>75) only if valuation + "
            "technical + alpha all aligned. This is a SECONDARY narrative score — "
            "it does NOT override the Official Confidence from the deterministic model."
        )
    )
    conviction_label: Literal["High", "Medium", "Low"] = Field(
        description="Human-readable label derived from conviction_0_100."
    )
    conviction_drivers: List[str] = Field(
        default_factory=list,
        description="Up to 3-5 short bullets explaining why conviction is High/Medium/Low."
    )
    conviction_risks: List[str] = Field(
        default_factory=list,
        description="Up to 3-5 short bullets on key thesis risks."
    )

    # Overlay traceability
    overlay_note: Optional[str] = Field(
        default=None,
        description=(
            "If overlay JSON was provided: briefly note how it influenced the narrative. "
            "Overlay must NOT override risk controls or Official Confidence."
        )
    )
    overlay_used: bool = Field(
        default=False,
        description="True if overlay context materially shaped the narrative."
    )

    # Legacy compatibility
    confidence_score: Optional[int] = Field(
        default=None, ge=0, le=100,
        description="Deprecated alias for conviction_0_100. Use conviction_0_100."
    )
    notes_on_overlay: Optional[str] = Field(
        default=None,
        description="Deprecated alias for overlay_note."
    )


# ---------------------------------------------------------------------------
# AIConviction — secondary display object (never drives risk controls)
# ---------------------------------------------------------------------------

class AIConviction(BaseModel):
    """
    Secondary AI narrative/thesis strength score.

    GOVERNANCE: This object may NEVER override Official Confidence,
    blocked status, or position sizing multipliers.
    """
    version: str = "1.0"
    available: bool = False

    score_0_100: Optional[int] = Field(default=None, ge=0, le=100)
    label: Optional[Literal["High", "Medium", "Low"]] = None

    # UI-friendly explanations
    drivers: List[str] = Field(default_factory=list)   # up to 3-5
    risks: List[str] = Field(default_factory=list)      # up to 3-5
    overlay_note: Optional[str] = None

    # Disagreement diagnostics
    disagreement_abs: Optional[int] = None
    disagreement_flag: Optional[Literal["aligned", "moderate", "high"]] = None

    # Traceability
    model: Optional[str] = None
    trace_id: Optional[str] = None
    disclaimer: str = (
        "AI Conviction reflects narrative/thesis strength and does not "
        "override the risk model."
    )
    debug: Dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------

def ai_conviction_label(score: int) -> Literal["High", "Medium", "Low"]:
    """Map conviction score to label."""
    if score >= 75:
        return "High"
    if score >= 55:
        return "Medium"
    return "Low"


def compute_disagreement(
    ai_score: int, official: int
) -> tuple[int, Literal["aligned", "moderate", "high"]]:
    """Return (abs_delta, flag) comparing AI conviction vs Official Confidence."""
    d = abs(int(ai_score) - int(official))
    if d < 10:
        return d, "aligned"
    if d < 25:
        return d, "moderate"
    return d, "high"


def build_ai_conviction(
    analysis: AIAnalysisResponse,
    official_confidence: int,
    model_name: str = "gemini-2.5-flash",
    trace_id: Optional[str] = None,
    debug_payload: Optional[Dict[str, Any]] = None,
) -> AIConviction:
    """
    Build an AIConviction object from a validated AIAnalysisResponse.
    Computes disagreement against the official deterministic confidence.
    """
    score = analysis.conviction_0_100
    label = analysis.conviction_label
    d_abs, d_flag = compute_disagreement(score, official_confidence)

    return AIConviction(
        available=True,
        score_0_100=score,
        label=label,
        drivers=analysis.conviction_drivers[:5],
        risks=analysis.conviction_risks[:5],
        overlay_note=analysis.overlay_note or analysis.notes_on_overlay,
        disagreement_abs=d_abs,
        disagreement_flag=d_flag,
        model=model_name,
        trace_id=trace_id,
        debug=debug_payload or {},
    )


def fallback_ai_conviction() -> AIConviction:
    """Return an unavailable AIConviction for error / fallback paths."""
    return AIConviction(available=False)
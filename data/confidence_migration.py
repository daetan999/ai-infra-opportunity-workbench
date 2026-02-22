"""
Confidence migration helpers.

Convert between legacy Option A / institutional dicts and
the canonical ConfidenceV3 object, and back to the template-safe dict.
"""

from __future__ import annotations
from typing import Dict, Any, Optional
from data.confidence_schema import ConfidenceV3, ConfidenceFactor


# Map from Option A / confidence_regime keys → ConfidenceV3 FactorKey strings
_OPTION_A_MAP: Dict[str, str] = {
    "dcf":                "valuation_dcf",
    "macro":              "macro",
    "industry":           "industry",
    "company":            "company",
    "vol":                "volatility",
    "earnings":           "earnings",
    "liquidity":          "liquidity",
    "alpha":              "alpha",
    "qualitative_proxy":  "qualitative_proxy",
}

_INV_MAP: Dict[str, str] = {v: k for k, v in _OPTION_A_MAP.items()}


def option_a_to_v3(conf: Dict[str, Any], mode: str) -> ConfidenceV3:
    """Convert an Option A confidence dict → ConfidenceV3."""
    total = int(conf.get("total", 50))
    raw = float(conf.get("raw", total / 100.0))

    factors: Dict[str, ConfidenceFactor] = {}
    breakdown = conf.get("breakdown", {}) or {}
    weights = conf.get("weights", {}) or {}
    contrib = conf.get("contrib", {}) or {}

    for k_old, k_new in _OPTION_A_MAP.items():
        if k_old in breakdown and k_old in weights:
            score = float(breakdown[k_old])
            w = float(weights[k_old])
            c = float(contrib.get(k_old, score * w))
            factors[k_new] = ConfidenceFactor(
                score_01=max(0.0, min(1.0, score)),
                weight_01=max(0.0, min(1.0, w)),
                contribution_01=max(0.0, min(1.0, c)),
                status="ok",
            )

    v3 = ConfidenceV3(
        mode=mode,
        total_0_100=total,
        raw_01=max(0.0, min(1.0, raw)),
        grade=ConfidenceV3.grade_from_score(total),
        factors=factors,
        signals_used=list(conf.get("debug", {}).get("signals_used", [])),
        missing_modules=list(conf.get("debug", {}).get("missing_modules", [])),
        debug={"legacy": {"option_a": conf}},
    )
    return v3


def v3_to_template_confidence(conf: ConfidenceV3) -> Dict[str, Any]:
    """
    Convert ConfidenceV3 → template-safe dict.
    Keeps report.html working without changes.
    """
    breakdown: Dict[str, float] = {}
    weights: Dict[str, float] = {}
    contrib: Dict[str, float] = {}

    for k_new, f in conf.factors.items():
        k_old = _INV_MAP.get(k_new, k_new)
        breakdown[k_old] = f.score_01
        weights[k_old] = f.weight_01
        contrib[k_old] = f.contribution_01

    return {
        "total": conf.total_0_100,
        "raw": conf.raw_01,
        "breakdown": breakdown,
        "weights": weights,
        "contrib": contrib,
        "missing_penalty_points": conf.missing_penalty_points,
        "overlay_delta_points": conf.overlay_delta_points,
        "blocked": conf.blocked,
        "blocked_reason": conf.blocked_reason,
        "debug": conf.debug,
    }

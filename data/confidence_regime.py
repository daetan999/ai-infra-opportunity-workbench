# data/confidence_regime.py
from __future__ import annotations

from typing import Any, Dict, List, Optional


# ========================================
# HELPER: Clamp to [0, 1]
# ========================================

def _clamp01(x: float) -> float:
    """Clamp value to [0.0, 1.0]."""
    return max(0.0, min(1.0, float(x)))


def _safe_float(x: Any, default: float = 0.5) -> float:
    """Convert to float with safe default."""
    try:
        if x is None:
            return default
        return float(x)
    except Exception:
        return default


# ========================================
# NORMALIZATION FUNCTIONS (Option A)
# ========================================

def _normalize_dcf(
    spot: float,
    intrinsic_value: Optional[float],
) -> tuple[float, dict]:
    """
    S_dcf: Valuation strength from DCF gap.
    
    Formula:
        DCF_gap = (intrinsic_value - spot) / spot
        if DCF_gap <= -0.30: S_dcf = 0
        elif DCF_gap >= 0.30: S_dcf = 1
        else: S_dcf = (DCF_gap + 0.30) / 0.60
        clamp to [0, 1]
    
    Returns:
        (S_dcf, reasoning_dict)
    """
    if intrinsic_value is None or spot is None or spot <= 0:
        return 0.5, {"missing": True, "DCF_gap": None}
    
    dcf_gap = (intrinsic_value - spot) / spot
    
    if dcf_gap <= -0.30:
        score = 0.0
    elif dcf_gap >= 0.30:
        score = 1.0
    else:
        score = (dcf_gap + 0.30) / 0.60
    
    score = _clamp01(score)
    
    return score, {
        "DCF_gap": round(dcf_gap, 4),
        "intrinsic_value": intrinsic_value,
        "spot": spot,
    }


def _normalize_macro(regime_label: Optional[str]) -> tuple[float, dict]:
    """
    S_macro: Macro regime strength.
    
    Mapping:
        Risk Off -> 0.30
        Neutral -> 0.50
        Risk On -> 0.70
    
    Returns:
        (S_macro, reasoning_dict)
    """
    regime = (regime_label or "").strip()
    
    mapping = {
        "Risk Off": 0.30,
        "RISK_OFF": 0.30,
        "Neutral": 0.50,
        "NEUTRAL": 0.50,
        "Risk On": 0.70,
        "RISK_ON": 0.70,
    }
    
    score = mapping.get(regime, 0.5)  # default neutral
    
    return score, {"regime_label": regime}


def _normalize_industry(
    cycle_stage: Optional[str],
    pricing_power: Optional[float],
    supply_discipline: Optional[float],
) -> tuple[float, dict]:
    """
    S_industry: Industry posture strength.
    
    Formula:
        cycle_score:
            Expansion -> 0.70
            Mid -> 0.50
            Contraction -> 0.30
        
        S_industry = 0.5*cycle_score + 0.3*pricing_power + 0.2*supply_discipline
        clamp to [0, 1]
    
    Returns:
        (S_industry, reasoning_dict)
    """
    # Cycle stage mapping
    cycle_map = {
        "Expansion": 0.70,
        "EXPANSION": 0.70,
        "Mid": 0.50,
        "MID": 0.50,
        "Contraction": 0.30,
        "CONTRACTION": 0.30,
    }
    
    cycle = (cycle_stage or "").strip()
    cycle_score = cycle_map.get(cycle, 0.5)  # default Mid
    
    # Normalize inputs (spec says not yet normalized)
    pp = _clamp01(_safe_float(pricing_power, 0.5))
    sd = _clamp01(_safe_float(supply_discipline, 0.5))
    
    score = 0.5 * cycle_score + 0.3 * pp + 0.2 * sd
    score = _clamp01(score)
    
    return score, {
        "cycle_stage": cycle,
        "cycle_score": cycle_score,
        "pricing_power": pp,
        "supply_discipline": sd,
    }


def _normalize_company(
    overall_quality: Optional[float],
    overall_risk: Optional[float],
) -> tuple[float, dict]:
    """
    S_company: Company structural strength.
    
    Formula:
        S_company = 0.7*overall_quality + 0.3*(1 - overall_risk)
        clamp to [0, 1]
    
    Returns:
        (S_company, reasoning_dict)
    """
    quality = _clamp01(_safe_float(overall_quality, 0.5))
    risk = _clamp01(_safe_float(overall_risk, 0.5))
    
    score = 0.7 * quality + 0.3 * (1.0 - risk)
    score = _clamp01(score)
    
    return score, {
        "overall_quality": quality,
        "overall_risk": risk,
    }


def _normalize_vol(
    hv20: Optional[float],
    hv60: Optional[float],
    iv_rank: Optional[float],
) -> tuple[float, dict]:
    """
    S_vol: Volatility regime favorability.
    
    Formula:
        vol_spread = abs(HV20 - HV60)
        base_vol_score = 0.4 if vol_spread > 0.20 else 0.6
        iv_component = 1 - IV_rank
        S_vol = 0.6*base_vol_score + 0.4*iv_component
        clamp to [0, 1]
    
    Returns:
        (S_vol, reasoning_dict)
    """
    h20 = _safe_float(hv20, None)
    h60 = _safe_float(hv60, None)
    ivr = _safe_float(iv_rank, 0.5)
    
    # Compute vol_spread
    if h20 is not None and h60 is not None:
        vol_spread = abs(h20 - h60)
    else:
        vol_spread = 0.0  # default if missing
    
    # Base score
    base_vol_score = 0.4 if vol_spread > 0.20 else 0.6
    
    # IV component (inverted: low IV rank = better)
    iv_component = 1.0 - _clamp01(ivr)
    
    score = 0.6 * base_vol_score + 0.4 * iv_component
    score = _clamp01(score)
    
    return score, {
        "HV20": h20,
        "HV60": h60,
        "vol_spread": round(vol_spread, 4) if vol_spread else None,
        "IV_rank": ivr,
        "base_vol_score": base_vol_score,
        "iv_component": iv_component,
    }


def _normalize_earnings(days_to_earnings: Optional[int]) -> tuple[float, dict]:
    """
    S_earnings: Event risk (earnings proximity).
    
    Formula:
        if days is None: S_earnings = 0.55 (neutral default)
        elif days <= 5: S_earnings = 0.30
        elif days <= 10: S_earnings = 0.40
        elif days <= 20: S_earnings = 0.50
        else: S_earnings = 0.70
    
    Returns:
        (S_earnings, reasoning_dict)
    """
    if days_to_earnings is None:
        return 0.55, {"days_to_earnings": None, "note": "No earnings date available"}
    
    days = int(days_to_earnings)
    
    if days <= 5:
        score = 0.30
    elif days <= 10:
        score = 0.40
    elif days <= 20:
        score = 0.50
    else:
        score = 0.70
    
    return score, {"days_to_earnings": days}


def _normalize_liquidity(
    pct_two_sided: Optional[float],
    pct_any_activity: Optional[float],
    median_spread_pct: Optional[float],
) -> tuple[float, dict]:
    """
    S_liquidity: Execution reliability.
    
    Formula:
        normalized_spread = median_spread_pct (already in [0, 1] range typically)
        S_liquidity = 0.4*pct_two_sided + 0.4*pct_any_activity + 0.2*(1 - normalized_spread)
        clamp to [0, 1]
    
    Returns:
        (S_liquidity, reasoning_dict)
    """
    pts = _clamp01(_safe_float(pct_two_sided, 0.5))
    paa = _clamp01(_safe_float(pct_any_activity, 0.5))
    
    # Normalize spread: assume it's in pct (e.g., 0.005 = 0.5%)
    # We want: lower spread = better, so invert it
    # Clamp to reasonable range first
    spread = _safe_float(median_spread_pct, 0.01)  # default 1% spread
    
    # Normalize spread to [0, 1] where 1 = very wide (bad)
    # Assume spread > 2% is "very wide"
    normalized_spread = min(spread / 0.02, 1.0)
    
    score = 0.4 * pts + 0.4 * paa + 0.2 * (1.0 - normalized_spread)
    score = _clamp01(score)
    
    return score, {
        "pct_two_sided": pts,
        "pct_any_activity": paa,
        "median_spread_pct": spread,
        "normalized_spread": normalized_spread,
    }


def _normalize_alpha(alpha_60d_cum_pct: Optional[float]) -> tuple[float, dict]:
    """
    S_alpha: Alpha/regression strength.
    
    Formula (heuristic fallback since we don't have historical z-score distribution):
        Treat alpha_60d_cum_pct as proxy for z-score
        Assume ±8% cumulative alpha over 60d ~ ±2 sigma
        
        alpha_z = alpha_60d_cum_pct / 4.0  (normalize to approx ±2 range)
        
        if alpha_z <= -2: S_alpha = 0
        elif alpha_z >= 2: S_alpha = 1
        else: S_alpha = (alpha_z + 2) / 4
        clamp to [0, 1]
    
    Returns:
        (S_alpha, reasoning_dict)
    """
    if alpha_60d_cum_pct is None:
        return 0.5, {"alpha_60d_cum_pct": None, "alpha_z": None, "note": "No alpha data"}
    
    alpha_pct = float(alpha_60d_cum_pct)
    
    # Heuristic: assume ±8% cum alpha ~ ±2 sigma
    # So divide by 4 to get pseudo z-score
    alpha_z = alpha_pct / 4.0
    
    if alpha_z <= -2.0:
        score = 0.0
    elif alpha_z >= 2.0:
        score = 1.0
    else:
        score = (alpha_z + 2.0) / 4.0
    
    score = _clamp01(score)
    
    return score, {
        "alpha_60d_cum_pct": alpha_pct,
        "alpha_z": round(alpha_z, 3),
    }


# ========================================
# MAIN: Option A Weighted Confidence
# ========================================

def compute_confidence_option_a(
    spot: float,
    dcf_result: Optional[dict],
    macro_snapshot: Optional[dict],
    company_snapshot: Optional[dict],  # has quant_profile.derived + industry_snapshot
    hv20: Optional[float],
    hv60: Optional[float],
    iv_rank: Optional[float],
    earnings_info: Optional[dict],
    liquidity_metrics: Optional[dict],  # for options mode
    alpha_snapshot: Optional[dict],
    mode: str = "stock",  # "stock" or "options"
    # Adaptive DCF parameters
    adaptive_dcf_weight=None,
    adaptive_dcf_score=None,
    # Qualitative proxy composite (NEW)
    qualitative_proxy: Optional[dict] = None,
    # Reverse DCF reasonableness [0-10] — blended into S_dcf
    # 0 = market implies absurd assumptions, 10 = fully reasonable
    # None = not available (uses S_dcf as-is)
    reverse_dcf_reasonableness: Optional[float] = None,
) -> dict:
    """
    Phase D: Option A Weighted Confidence Composite.
    
    Inputs:
        - spot: current price
        - dcf_result: {intrinsic_value, conservative_value, ...}
        - macro_snapshot: {regime_label, ...}
        - company_snapshot: {quant_profile: {derived: {overall_risk, overall_quality}}, industry_snapshot: {...}}
        - hv20, hv60: historical volatility
        - iv_rank: IV rank [0, 1]
        - earnings_info: {days_to_earnings, ...}
        - liquidity_metrics: {pct_two_sided, pct_any_activity, median_spread_pct}
        - alpha_snapshot: {vs_peers: {alpha_60d_cum_pct}, vs_sox: {...}}
        - mode: "stock" or "options"
    
    Returns:
        {
            "total": int (0..100),
            "raw": float (0..1),
            "breakdown": {factor: score, ...},
            "weights": {factor: weight, ...},
            "contrib": {factor: weight*score, ...},
            "reasoning": {...},
            "debug": {...}
        }
    """
    
    # ========================================
    # Extract inputs
    # ========================================
    
    # Try both "intrinsic_value" (schema key) and "intrinsic" (build_dcf key)
    intrinsic_value = (
        (dcf_result or {}).get("intrinsic_value")
        or (dcf_result or {}).get("intrinsic")
    )
    regime_label = (macro_snapshot or {}).get("regime_label")
    
    # Company
    qp = (company_snapshot or {}).get("quant_profile", {})
    derived = qp.get("derived", {})
    overall_quality = derived.get("overall_quality")
    overall_risk = derived.get("overall_risk")
    
    # Industry
    industry = (company_snapshot or {}).get("industry_snapshot", {})
    cycle_stage = industry.get("cycle_stage")
    pricing_power = industry.get("pricing_power")
    supply_discipline = industry.get("supply_discipline")
    
    # Earnings
    days_to_earnings = (earnings_info or {}).get("days_to_earnings")
    
    # Liquidity (options mode only)
    liq = liquidity_metrics or {}
    pct_two_sided = liq.get("pct_two_sided")
    pct_any_activity = liq.get("pct_any_activity")
    median_spread_pct = liq.get("median_spread_pct")
    
    # Alpha
    alpha_snap = alpha_snapshot or {}
    vs_peers = alpha_snap.get("vs_peers", {})
    vs_sox = alpha_snap.get("vs_sox", {})
    alpha_60d_cum_pct = vs_peers.get("alpha_60d_cum_pct") or vs_sox.get("alpha_60d_cum_pct")
    
    # ========================================
    # Normalize all factors
    # ========================================
    
    # Use adaptive DCF score if provided, otherwise use standard normalization
    if adaptive_dcf_score is not None:
        S_dcf = adaptive_dcf_score
        reason_dcf = "Adaptive DCF score"
    else:
        S_dcf, reason_dcf = _normalize_dcf(spot, intrinsic_value)

    # Blend Reverse DCF reasonableness into S_dcf.
    # reverse_dcf_reasonableness is on [0, 10]; normalise to [0, 1].
    #
    # Blending rule:
    #   S_dcf = 0.55 * S_dcf_gap + 0.45 * reverse_reasonableness_01
    #
    # Giving the reverse DCF 45% weight means it materially affects the score.
    # Example: S_dcf_gap=0.50 (neutral gap), reasonableness=0.5/10 → 0.05
    #   S_dcf = 0.55*0.50 + 0.45*0.05 = 0.275 + 0.022 = 0.30  ← properly bearish
    # Example: S_dcf_gap=0.50, reasonableness=8/10 → 0.80
    #   S_dcf = 0.55*0.50 + 0.45*0.80 = 0.275 + 0.36 = 0.635  ← properly bullish
    if reverse_dcf_reasonableness is not None:
        _rev_01 = _clamp01(float(reverse_dcf_reasonableness) / 10.0)
        _S_dcf_pre = S_dcf
        S_dcf = _clamp01(0.55 * S_dcf + 0.45 * _rev_01)
        _reason_base = reason_dcf if isinstance(reason_dcf, dict) else {"note": str(reason_dcf)}
        reason_dcf = {
            **_reason_base,
            "base_S_dcf": round(_S_dcf_pre, 4),
            "reverse_reasonableness_raw": round(float(reverse_dcf_reasonableness), 2),
            "reverse_reasonableness_01": round(_rev_01, 4),
            "blended_S_dcf": round(S_dcf, 4),
            "blend_formula": "0.55 * DCF_gap_score + 0.45 * reverse_reasonableness_01",
        }
    S_macro, reason_macro = _normalize_macro(regime_label)
    S_industry, reason_industry = _normalize_industry(cycle_stage, pricing_power, supply_discipline)
    S_company, reason_company = _normalize_company(overall_quality, overall_risk)
    S_vol, reason_vol = _normalize_vol(hv20, hv60, iv_rank)
    S_earnings, reason_earnings = _normalize_earnings(days_to_earnings)
    S_liquidity, reason_liquidity = _normalize_liquidity(pct_two_sided, pct_any_activity, median_spread_pct)
    S_alpha, reason_alpha = _normalize_alpha(alpha_60d_cum_pct)

    # Qualitative proxy
    S_qual = None
    if qualitative_proxy and qualitative_proxy.get("available"):
        S_qual = _clamp01(_safe_float(qualitative_proxy.get("score_01"), 0.5))

    # ========================================
    # Define weights (mode-dependent)
    # ========================================
    # Qualitative proxy weight: 0.10 stock, 0.07 options
    qual_weight_base = 0.10 if mode == "stock" else 0.07
    has_qual = S_qual is not None

    # DCF weight: clamp adaptive input so it can't fall below 0.25.
    # Adaptive logic may rate DCF as "unreliable" (e.g. 0.10) when DCF gap is large,
    # but DCF remains structurally important — we respect the floor.
    DCF_WEIGHT_FLOOR = 0.25
    _dcf_raw = adaptive_dcf_weight if adaptive_dcf_weight is not None else 0.30
    dcf_weight = max(DCF_WEIGHT_FLOOR, float(_dcf_raw))

    if mode == "options":
        # Options mode: all factors active.  Non-DCF weights are relative anchors;
        # total will be renormalized to 1.0 in the final step below.
        if has_qual:
            weights = {
                "dcf":       dcf_weight,
                "macro":     0.10,
                "industry":  0.08,
                "company":   0.10,
                "vol":       0.09,
                "earnings":  0.09,
                "liquidity": 0.05,
                "alpha":     0.09,
                "qual":      qual_weight_base,
            }
        else:
            weights = {
                "dcf":       dcf_weight,
                "macro":     0.10,
                "industry":  0.10,
                "company":   0.13,
                "vol":       0.10,
                "earnings":  0.10,
                "liquidity": 0.05,
                "alpha":     0.12,
            }
    else:
        # Stock mode: liquidity is excluded (weight = 0).
        # We build a proportional table where other factors keep their relative anchors
        # but DCF is guaranteed >= DCF_WEIGHT_FLOOR after normalization.
        if has_qual:
            base_weights = {
                "dcf":       dcf_weight,
                "macro":     0.10,
                "industry":  0.08,
                "company":   0.10,
                "vol":       0.09,
                "earnings":  0.09,
                "liquidity": 0.00,
                "alpha":     0.09,
                "qual":      qual_weight_base,
            }
        else:
            base_weights = {
                "dcf":       dcf_weight,
                "macro":     0.10,
                "industry":  0.10,
                "company":   0.13,
                "vol":       0.10,
                "earnings":  0.10,
                "liquidity": 0.00,
                "alpha":     0.12,
            }

        # Redistribute: exclude liquidity, scale active factors to sum to 1.0
        total_non_liq = sum(w for k, w in base_weights.items() if k != "liquidity")
        weights = {k: (w / total_non_liq if k != "liquidity" else 0.0) for k, w in base_weights.items()}

        # Enforce DCF floor AFTER redistribution.
        # If DCF was diluted below the floor, top it up and shrink other non-DCF
        # non-liquidity factors proportionally to compensate.
        if weights.get("dcf", 0) < DCF_WEIGHT_FLOOR:
            deficit = DCF_WEIGHT_FLOOR - weights["dcf"]
            _non_dcf_keys = [k for k in weights if k not in ("dcf", "liquidity") and weights[k] > 0]
            _non_dcf_sum = sum(weights[k] for k in _non_dcf_keys)
            if _non_dcf_sum > deficit:
                # Shrink non-DCF factors proportionally to cover the deficit
                for k in _non_dcf_keys:
                    weights[k] -= deficit * (weights[k] / _non_dcf_sum)
                weights["dcf"] = DCF_WEIGHT_FLOOR

    # Final renormalization: guarantee exact sum = 1.0 (handles floating-point drift)
    total_weight = sum(weights.values())
    if total_weight > 0 and abs(total_weight - 1.0) > 1e-9:
        weights = {k: v / total_weight for k, v in weights.items()}
    
    # ========================================
    # Compute contributions
    # ========================================
    
    breakdown = {
        "dcf":      S_dcf,
        "macro":    S_macro,
        "industry": S_industry,
        "company":  S_company,
        "vol":      S_vol,
        "earnings": S_earnings,
        "liquidity": S_liquidity,
        "alpha":    S_alpha,
    }
    if has_qual:
        breakdown["qual"] = S_qual
    
    contrib = {k: weights[k] * breakdown[k] for k in weights}
    
    confidence_raw = sum(contrib.values())
    confidence_raw = _clamp01(confidence_raw)

    # Missing-data penalty: identify factors where the raw INPUT was None/unavailable.
    # A factor is "missing" when its normalizer returned the neutral default (0.5 or 0.55)
    # because its source data was absent.  We track this via the reasoning dicts that
    # the normalizers return — each sets reasoning["missing"] = True when falling back.
    #
    # Factors with weight == 0 (e.g. liquidity in stock mode) are EXCLUDED, not missing.
    missing_inputs = []
    # DCF is only truly "missing" (defaulted to neutral 0.5) when:
    #   - no intrinsic value from DCF model
    #   - no adaptive_dcf_score computed by the adaptive engine
    #   - no reverse DCF reasonableness to blend
    # If ANY of these is present, DCF score is real (not defaulted).
    _dcf_has_signal = (
        (intrinsic_value is not None and spot is not None and spot > 0)
        or (adaptive_dcf_score is not None)
        or (reverse_dcf_reasonableness is not None)
    )
    if not _dcf_has_signal:
        missing_inputs.append("dcf")
    # macro: mapping returns 0.5 for unknown label, treat as missing only if label is blank
    if not (regime_label or "").strip():
        missing_inputs.append("macro")
    # company: both quality AND risk absent
    if overall_quality is None and overall_risk is None:
        missing_inputs.append("company")
    # industry: cycle_stage absent
    if not (cycle_stage or "").strip():
        missing_inputs.append("industry")
    # vol: both HV20 and HV60 absent
    if hv20 is None and hv60 is None:
        missing_inputs.append("vol")
    # alpha: absent
    if alpha_60d_cum_pct is None:
        missing_inputs.append("alpha")
    # liquidity (options only): key metrics absent
    if mode == "options" and pct_two_sided is None and pct_any_activity is None:
        missing_inputs.append("liquidity")

    # Only penalise factors that have nonzero weight (not excluded) and are truly absent
    missing_factors = [k for k in missing_inputs if weights.get(k, 0) > 1e-9]
    # Track "defaulted" factors (missing but present in breakdown as 0.5) for UI display
    defaulted_factors = missing_factors[:]

    # Weight-proportional penalty: passing weights enables proper scaling
    missing_penalty = _compute_missing_penalty(mode, missing_factors, weights=weights)

    # ── Dispersion amplification ─────────────────────────────────────────────
    # Factors that ARE computed (not defaulted) have their scores pushed away from
    # the neutral 0.5 mid-point.  Default/missing factors stay at 0.5 unchanged.
    # Formula: S_amplified = 0.5 + (S - 0.5) * AMP
    # AMP = 1.20 → a strong 0.75 becomes 0.80, a weak 0.25 becomes 0.20.
    # This gives the model more dispersion without changing the factor logic.
    AMP = 1.20
    for k in list(breakdown.keys()):
        if k not in defaulted_factors and weights.get(k, 0) > 1e-9:
            breakdown[k] = _clamp01(0.5 + (breakdown[k] - 0.5) * AMP)

    # Recompute contrib and raw with amplified scores
    contrib = {k: weights[k] * breakdown[k] for k in weights}
    confidence_raw = _clamp01(sum(contrib.values()))
    # ────────────────────────────────────────────────────────────────────────

    confidence_total = max(0, min(100, round(100 * confidence_raw) - missing_penalty))
    
    # ========================================
    # Reasoning / debug
    # ========================================
    
    reasoning = {
        "dcf":      reason_dcf,
        "macro":    reason_macro,
        "industry": reason_industry,
        "company":  reason_company,
        "vol":      reason_vol,
        "earnings": reason_earnings,
        "liquidity": reason_liquidity,
        "alpha":    reason_alpha,
    }
    if has_qual:
        reasoning["qual"] = f"Qualitative proxy score: {S_qual:.3f}" 
    
    debug = {
        "mode": mode,
        "spot": spot,
        "intrinsic_value": intrinsic_value,
        "regime_label": regime_label,
        "overall_quality": overall_quality,
        "overall_risk": overall_risk,
        "cycle_stage": cycle_stage,
        "pricing_power": pricing_power,
        "supply_discipline": supply_discipline,
        "HV20": hv20,
        "HV60": hv60,
        "IV_rank": iv_rank,
        "days_to_earnings": days_to_earnings,
        "alpha_60d_cum_pct": alpha_60d_cum_pct,
        "liquidity_metrics": liquidity_metrics,
    }
    
    # ========================================
    # Return structured output
    # ========================================
    
    # ========================================
    # Build factor_meta: per-factor status for UI and signals list
    # status: "ok"       → computed from real inputs
    #         "defaulted"→ present in breakdown at 0.5 because source data was absent
    #         "excluded" → weight = 0 (not relevant to this mode)
    #         "missing"  → was in missing_inputs but has nonzero weight (same as defaulted here)
    # ========================================
    _PRETTY = {
        "dcf":      "DCF vs price",
        "macro":    "Macro regime",
        "industry": "Industry cycle",
        "company":  "Company quality",
        "vol":      "Vol context",
        "earnings": "Earnings quality",
        "alpha":    "Relative alpha",
        "liquidity":"Options liquidity",
        "qual":     "Qualitative proxies",
    }
    # Reason text for defaulted factors
    _DEFAULT_REASON = {
        "dcf":      "intrinsic value unavailable",
        "macro":    "regime not detected",
        "industry": "cycle stage unavailable",
        "company":  "quality/risk data absent",
        "vol":      "HV20 and HV60 absent",
        "alpha":    "alpha data absent",
        "liquidity":"liquidity metrics absent",
    }
    factor_meta = {}
    _all_factors = ["dcf", "macro", "industry", "company", "vol", "earnings", "alpha", "liquidity", "qual"]
    for _fk in _all_factors:
        _w = weights.get(_fk, 0.0)
        if _w <= 1e-9:
            factor_meta[_fk] = {
                "status": "excluded",
                "weight": 0.0,
                "pretty": _PRETTY.get(_fk, _fk),
                "reason": "not scored in this mode",
            }
        elif _fk in defaulted_factors:
            factor_meta[_fk] = {
                "status": "defaulted",
                "weight": round(_w, 4),
                "pretty": _PRETTY.get(_fk, _fk),
                "reason": _DEFAULT_REASON.get(_fk, "data unavailable"),
            }
        elif _fk in breakdown:
            factor_meta[_fk] = {
                "status": "ok",
                "weight": round(_w, 4),
                "pretty": _PRETTY.get(_fk, _fk),
                "reason": None,
            }
        # qual is only present when has_qual
        # earnings never defaults — always has a score (days_to_earnings can be None → 0.55 but not in missing_inputs)
    # earnings special case: defaulted if no date but we don't treat as missing
    if "earnings" not in factor_meta:
        factor_meta["earnings"] = {
            "status": "ok" if days_to_earnings is not None else "defaulted",
            "weight": round(weights.get("earnings", 0.0), 4),
            "pretty": "Earnings quality",
            "reason": "no earnings date" if days_to_earnings is None else None,
        }

    return {
        "total": confidence_total,
        "raw": round(confidence_raw, 4),
        "missing_penalty": missing_penalty,
        "missing_factors": missing_factors,
        "defaulted_factors": defaulted_factors,
        "factor_meta": factor_meta,
        "breakdown": {k: round(v, 4) for k, v in breakdown.items()},
        "weights": {k: round(v, 4) for k, v in weights.items()},
        "contrib": {k: round(v, 4) for k, v in contrib.items()},
        "reasoning": reasoning,
        "debug": debug,
    }

# ========================================
# MISSING PENALTY HELPER
# ========================================

def _compute_missing_penalty(mode: str, missing_factors: list, weights: dict = None) -> int:
    """
    Compute missing-data penalty points, proportional to each missing factor's weight.

    A missing factor defaults to S=0.5 (neutral), contributing weight*0.5 when the
    "true" signal is unknown.  The penalty represents the *expected information loss*:
        penalty_per_factor = weight * 50 (points that could have been informative)
    Capped at 15 points total to avoid over-penalizing data-sparse environments.

    Falls back to legacy flat penalty (2 pts per critical) if weights unavailable.
    """
    if weights:
        critical = {"dcf", "macro", "industry", "company"}
        if mode == "options":
            critical |= {"liquidity", "vol"}
        total_penalty = 0.0
        for f in missing_factors:
            if f in critical:
                w = weights.get(f, 0.0)
                # 50 = the maximum points a factor could contribute (weight * 100 at score=1.0)
                # We penalise half that (weight * 50) for each missing critical factor
                total_penalty += w * 50.0
        return min(15, round(total_penalty))
    else:
        # Legacy fallback
        critical = {"dcf", "macro", "industry", "company"}
        if mode == "options":
            critical |= {"liquidity", "vol"}
        missing_critical = len([f for f in missing_factors if f in critical])
        return min(15, 3 * missing_critical)
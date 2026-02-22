"""
Qualitative Proxy Metrics
=========================
Deterministic, cross-ticker, scalable proxy factors.
Each metric returns score_01 ∈ [0,1] with status and traceability inputs.

All metrics are computable from existing system data sources:
  - hist_df: yfinance 1y daily price history
  - alpha_snapshot: alpha vs peers/sox
  - earnings_info: beat rate, guidance tone, days to event
  - dcf_result: intrinsic value / DCF gap
  - headlines: news.py tagged headlines
  - yf_info: yfinance .info dict
  - sector_bucket: from semis_universe.py

Usage:
    result = compute_qualitative_proxies(
        ticker="MU", mode="stock", hold_days=90,
        hist_df=hist_df, sector_bucket="Memory",
        alpha_snapshot=alpha_snapshot, earnings_info=earnings_info,
        dcf_result=dcf_result, headlines=headlines, yf_info=yf_info,
    )
    # result["available"] -> bool
    # result["score_01"]  -> float 0-1
    # result["metrics"]   -> {key: {score_01, status, inputs, notes}}
"""

from __future__ import annotations

import math
from typing import Any, Dict, List, Optional


# ---------------------------------------------------------------------------
# Math helpers
# ---------------------------------------------------------------------------

def _clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, float(x)))


def _clamp01(x: float) -> float:
    return _clamp(float(x), 0.0, 1.0)


def _tanh_scale(x: float, s: float) -> float:
    """tanh(x/s) with zero-division guard."""
    return math.tanh(x / s) if s else 0.0


def _safe_float(v: Any, default: float = 0.0) -> float:
    try:
        if v is None:
            return default
        return float(v)
    except (TypeError, ValueError):
        return default


def _missing(key: str, note: str) -> Dict[str, Any]:
    return {"score_01": 0.5, "status": "missing", "inputs": {}, "notes": [note]}


def _ok(score: float, inputs: Dict[str, Any], notes: Optional[List[str]] = None) -> Dict[str, Any]:
    return {
        "score_01": _clamp01(score),
        "status": "ok",
        "inputs": inputs,
        "notes": notes or [],
    }


# ---------------------------------------------------------------------------
# Individual proxy metrics
# ---------------------------------------------------------------------------

PROXY_WEIGHTS: Dict[str, float] = {
    "mom_regime_01":         0.15,
    "rel_strength_01":       0.10,
    "earnings_quality_01":   0.10,
    "guidance_tone_01":      0.10,
    "bs_resilience_01":      0.10,
    "capex_discipline_01":   0.10,
    "news_shock_01":         0.10,
    "segment_exposure_01":   0.15,
    "valuation_discomfort_01": 0.10,
}


def _mom_regime(hist_df) -> Dict[str, Any]:
    """Price momentum regime: SMA50/SMA200 + momentum score."""
    try:
        if hist_df is None or len(hist_df) < 200:
            return _missing("mom_regime_01", "Insufficient price history (<200 bars)")

        close = hist_df["Close"] if "Close" in hist_df.columns else hist_df.iloc[:, 0]
        close = close.dropna()
        if len(close) < 200:
            return _missing("mom_regime_01", "Insufficient price history after dropna")

        sma50 = float(close.tail(50).mean())
        sma200 = float(close.tail(200).mean())
        current = float(close.iloc[-1])

        if sma200 == 0:
            return _missing("mom_regime_01", "SMA200 is zero")

        mom = _clamp((current / sma200) - 1, -0.25, 0.25)
        trend = 1.0 if sma50 > sma200 else -1.0
        score = _clamp01(0.5 + 0.35 * _tanh_scale(mom, 0.10) + 0.15 * trend)

        return _ok(score, {
            "current": round(current, 2),
            "sma50": round(sma50, 2),
            "sma200": round(sma200, 2),
            "mom": round(mom, 4),
            "trend": trend,
        })
    except Exception as e:
        return _missing("mom_regime_01", f"Error: {e}")


def _rel_strength(alpha_snapshot: Optional[dict]) -> Dict[str, Any]:
    """Relative strength vs cluster proxy using alpha_snapshot."""
    try:
        if not alpha_snapshot:
            return _missing("rel_strength_01", "alpha_snapshot not available")

        # Try vs_peers first, then vs_sox
        vs_peers = alpha_snapshot.get("vs_peers", {})
        vs_sox = alpha_snapshot.get("vs_sox", {})
        alpha_pct = (
            vs_peers.get("alpha_60d_cum_pct")
            or vs_sox.get("alpha_60d_cum_pct")
        )
        if alpha_pct is None:
            return _missing("rel_strength_01", "alpha_60d_cum_pct not found")

        a = _clamp(float(alpha_pct), -20.0, 20.0)
        score = _clamp01(0.5 + 0.5 * _tanh_scale(a, 8.0))

        return _ok(score, {"alpha_60d_cum_pct": alpha_pct, "clamped": a})
    except Exception as e:
        return _missing("rel_strength_01", f"Error: {e}")


def _earnings_quality(earnings_info: Optional[dict]) -> Dict[str, Any]:
    """Earnings execution quality: beat rate."""
    try:
        if not earnings_info:
            return _missing("earnings_quality_01", "earnings_info not available")

        # Support both dict formats: {beat_rate: X} or {quarters: [...]}
        beat_rate = earnings_info.get("beat_rate")
        if beat_rate is None:
            quarters = earnings_info.get("quarters", [])
            if not quarters:
                return _missing("earnings_quality_01", "No quarters data")
            beats = sum(
                1 for q in quarters
                if (q.get("results", {}).get("eps", {}).get("verdict") == "beat"
                    or q.get("beat", False))
            )
            beat_rate = beats / len(quarters)

        beat_rate = float(beat_rate)
        score = _clamp01(0.5 + 0.5 * (beat_rate - 0.5) * 2)

        return _ok(score, {"beat_rate": round(beat_rate, 3)})
    except Exception as e:
        return _missing("earnings_quality_01", f"Error: {e}")


def _guidance_tone(earnings_info: Optional[dict]) -> Dict[str, Any]:
    """Guidance tone proxy."""
    TONE_MAP = {
        "raised": 1.0,
        "positive": 0.8,
        "inline": 0.6,
        "in-line": 0.6,
        "mixed": 0.5,
        "unknown": 0.5,
        "lowered": 0.2,
        "negative": 0.2,
        "withdrawn": 0.3,
    }
    try:
        if not earnings_info:
            return _missing("guidance_tone_01", "earnings_info not available")

        tone = (earnings_info.get("guidance_tone") or "unknown").lower().strip()
        score = TONE_MAP.get(tone, 0.5)

        # If tone is "unknown" treat as missing but still return 0.5
        status = "ok" if tone != "unknown" else "missing"
        return {"score_01": score, "status": status, "inputs": {"tone": tone}, "notes": []}
    except Exception as e:
        return _missing("guidance_tone_01", f"Error: {e}")


def _bs_resilience(yf_info: Optional[dict]) -> Dict[str, Any]:
    """Balance sheet resilience: net cash / market cap."""
    try:
        if not yf_info:
            return _missing("bs_resilience_01", "yf_info not available")

        total_cash = yf_info.get("totalCash")
        total_debt = yf_info.get("totalDebt")
        market_cap = yf_info.get("marketCap")

        if any(v is None for v in [total_cash, total_debt, market_cap]) or market_cap == 0:
            return _missing("bs_resilience_01", "Missing totalCash/totalDebt/marketCap")

        net_cash = float(total_cash) - float(total_debt)
        ratio = _clamp(net_cash / float(market_cap), -0.30, 0.30)
        score = _clamp01(0.5 + 0.5 * _tanh_scale(ratio, 0.10))

        return _ok(score, {
            "totalCash": total_cash,
            "totalDebt": total_debt,
            "marketCap": market_cap,
            "net_cash": round(net_cash, 0),
            "ratio": round(ratio, 4),
        })
    except Exception as e:
        return _missing("bs_resilience_01", f"Error: {e}")


def _capex_discipline(yf_info: Optional[dict]) -> Dict[str, Any]:
    """
    Capex discipline proxy: revenue growth outpacing capex growth.
    Uses yf_info financials if available.
    """
    try:
        if not yf_info:
            return _missing("capex_discipline_01", "yf_info not available")

        # Try to get from yf_info financial summary fields
        # yfinance puts some cashflow items in .info under various keys
        rev_ttm = _safe_float(yf_info.get("totalRevenue"), 0)
        capex_ttm = _safe_float(yf_info.get("capitalExpenditures"), 0)

        # Also look for trailing vs previous (revenueGrowth is 1-yr)
        rev_growth = _safe_float(yf_info.get("revenueGrowth"), 0)  # e.g., 0.12 = 12%

        if rev_ttm == 0 or capex_ttm == 0:
            return _missing("capex_discipline_01", "Revenue or CapEx data unavailable")

        # Estimate capex intensity trend from available data
        capex_intensity = abs(capex_ttm) / rev_ttm if rev_ttm > 0 else 0

        # Use revenue growth as proxy for discipline measure
        # Positive revenue growth + low capex intensity = disciplined
        # Simple proxy: discipline = revenue_growth - capex_intensity_delta
        # When we can't compute prior year, use rev_growth as primary signal
        discipline = rev_growth - max(0, capex_intensity - 0.10)  # penalise >10% intensity
        score = _clamp01(0.5 + 0.5 * _tanh_scale(discipline, 0.25))

        return _ok(score, {
            "rev_ttm": rev_ttm,
            "capex_ttm": capex_ttm,
            "capex_intensity": round(capex_intensity, 4),
            "rev_growth": rev_growth,
            "discipline_proxy": round(discipline, 4),
        })
    except Exception as e:
        return _missing("capex_discipline_01", f"Error: {e}")


def _news_shock(headlines: Optional[List[dict]]) -> Dict[str, Any]:
    """Deterministic news shock: severity-weighted headline risk (inverted)."""
    SEVERITY_WEIGHTS = {"HIGH": 1.0, "MED": 0.5, "MEDIUM": 0.5, "LOW": 0.2}

    try:
        if not headlines:
            return _missing("news_shock_01", "No headlines available")

        weights_sum = 0.0
        n = len(headlines)
        for h in headlines:
            sev = (h.get("severity") or h.get("tag") or "LOW").upper()
            weights_sum += SEVERITY_WEIGHTS.get(sev, 0.2)

        risk = _clamp01(weights_sum / max(1, n))
        score = 1.0 - risk

        return _ok(score, {
            "headline_count": n,
            "total_severity_weight": round(weights_sum, 2),
            "risk": round(risk, 4),
        })
    except Exception as e:
        return _missing("news_shock_01", f"Error: {e}")


# Bucket scores by horizon category (used for 90d default)
_BUCKET_SCORES: Dict[str, float] = {
    "GPU/AI":       0.75,
    "AI":           0.75,
    "Networking":   0.70,
    "Memory":       0.60,
    "EDA":          0.65,
    "WFE":          0.50,
    "Analog":       0.55,
    "Auto":         0.55,
    "Analog/Auto":  0.55,
    "Logic":        0.62,
    "Foundry":      0.58,
    "RF/Wireless":  0.58,
    "Power":        0.55,
    "MEMS":         0.53,
    "Mixed":        0.55,
}


def _segment_exposure(sector_bucket: Optional[str], hold_days: int = 90) -> Dict[str, Any]:
    """Segment exposure proxy based on sector bucket."""
    try:
        if not sector_bucket:
            return _missing("segment_exposure_01", "sector_bucket not available")

        # Look up base score; fallback 0.5 for unknown
        score = _BUCKET_SCORES.get(sector_bucket)
        if score is None:
            return {
                "score_01": 0.5,
                "status": "missing",
                "inputs": {"sector_bucket": sector_bucket},
                "notes": ["Unknown bucket — defaulting to 0.5"],
            }

        # Modest time-horizon adjustment: short holds reduce score slightly
        if hold_days <= 30:
            score = _clamp01(score - 0.05)

        return _ok(score, {
            "sector_bucket": sector_bucket,
            "hold_days": hold_days,
        })
    except Exception as e:
        return _missing("segment_exposure_01", f"Error: {e}")


def _valuation_discomfort(dcf_result: Optional[dict], spot: float) -> Dict[str, Any]:
    """Valuation discomfort proxy: DCF gap → overvalued = lower score."""
    try:
        if not dcf_result or not spot or spot <= 0:
            return _missing("valuation_discomfort_01", "DCF result or spot not available")

        dcf = dcf_result.get("intrinsic_value") or dcf_result.get("intrinsic")
        if dcf is None:
            return _missing("valuation_discomfort_01", "intrinsic_value missing from dcf_result")

        dcf = float(dcf)
        # gap > 0: DCF above spot (undervalued) → good for bulls → high score
        # gap < 0: DCF below spot (overvalued) → discomfort → low score
        gap = _clamp((dcf / spot) - 1, -0.60, 0.60)
        score = _clamp01(0.5 + 0.5 * _tanh_scale(gap, 0.25))

        return _ok(score, {
            "dcf": round(dcf, 2),
            "spot": round(spot, 2),
            "gap": round(gap, 4),
        })
    except Exception as e:
        return _missing("valuation_discomfort_01", f"Error: {e}")


# ---------------------------------------------------------------------------
# Main compute function
# ---------------------------------------------------------------------------

def compute_qualitative_proxies(
    *,
    ticker: str,
    mode: str,
    hold_days: int,
    hist_df=None,
    sector_bucket: Optional[str] = None,
    alpha_snapshot: Optional[dict] = None,
    earnings_info: Optional[dict] = None,
    dcf_result: Optional[dict] = None,
    headlines: Optional[List[dict]] = None,
    yf_info: Optional[dict] = None,
    spot: float = 0.0,
) -> Dict[str, Any]:
    """
    Compute all qualitative proxy metrics and return aggregate.

    Returns:
        {
            "available": bool,
            "score_01": float,
            "metrics": {key: {score_01, status, inputs, notes}},
            "missing": [key, ...],
            "signals_used": [key, ...],
            "weights_used": {key: float},
        }
    """
    metrics: Dict[str, Dict[str, Any]] = {}
    missing_keys: List[str] = []
    signals_used: List[str] = []

    # Compute each metric
    metrics["mom_regime_01"]          = _mom_regime(hist_df)
    metrics["rel_strength_01"]        = _rel_strength(alpha_snapshot)
    metrics["earnings_quality_01"]    = _earnings_quality(earnings_info)
    metrics["guidance_tone_01"]       = _guidance_tone(earnings_info)
    metrics["bs_resilience_01"]       = _bs_resilience(yf_info)
    metrics["capex_discipline_01"]    = _capex_discipline(yf_info)
    metrics["news_shock_01"]          = _news_shock(headlines)
    metrics["segment_exposure_01"]    = _segment_exposure(sector_bucket, hold_days)
    metrics["valuation_discomfort_01"] = _valuation_discomfort(dcf_result, spot)

    # Separate ok vs missing
    ok_keys = [k for k, v in metrics.items() if v["status"] == "ok"]
    missing_keys = [k for k, v in metrics.items() if v["status"] == "missing"]
    signals_used = ok_keys[:]

    # Need at least 3 ok metrics to compute aggregate
    if len(ok_keys) < 3:
        return {
            "available": False,
            "score_01": 0.5,
            "metrics": metrics,
            "missing": missing_keys,
            "signals_used": signals_used,
            "weights_used": {},
        }

    # Renormalise weights among available metrics only
    raw_weights = {k: PROXY_WEIGHTS.get(k, 0.10) for k in ok_keys}
    total_w = sum(raw_weights.values())
    norm_weights = {k: w / total_w for k, w in raw_weights.items()}

    # Weighted mean
    score_01 = sum(
        norm_weights[k] * metrics[k]["score_01"]
        for k in ok_keys
    )
    score_01 = _clamp01(score_01)

    return {
        "available": True,
        "score_01": round(score_01, 4),
        "metrics": metrics,
        "missing": missing_keys,
        "signals_used": signals_used,
        "weights_used": {k: round(norm_weights[k], 4) for k in ok_keys},
    }
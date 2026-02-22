from __future__ import annotations

import math 
from datetime import datetime, timezone
from typing import Any
from math import sqrt
from data.conclusion import build_conclusion
from zoneinfo import ZoneInfo
from data.iv_history import append_atm_iv_snapshot, compute_iv_rank_from_snapshots
from data.quant_entry import atr, anchored_vwap, execution_bands
from data.news import get_company_snapshot, get_latest_headlines
from data.cache import CHAIN_CACHE, EARNINGS_CACHE, PEER_CACHE, COMPANY_CACHE, NEWS_CACHE, ALPHA_CACHE
from data.alpha_regression import compute_alpha_snapshot, classify_alpha_regime
from data.confidence_regime import compute_confidence_option_a
from data.confidence_migration import option_a_to_v3, v3_to_template_confidence
from data.qualitative_proxies import compute_qualitative_proxies
try:
    from data.ai_schemas import AIConviction, build_ai_conviction, fallback_ai_conviction, ai_conviction_label, compute_disagreement
    AI_SCHEMAS_AVAILABLE = True
except ImportError:
    AI_SCHEMAS_AVAILABLE = False
try:
    from data.cache import GEMINI_TRACE_CACHE
except (ImportError, AttributeError):
    GEMINI_TRACE_CACHE = None
from data.company_brief import build_company_chain 
from data.semis_universe import sector_bucket_for
# DCF and price guidance helpers
from data.dcf_engine import build_dcf
from data.price_guidance import widen_factor_from_confidence
from data.adaptive_confidence import calculate_adaptive_dcf_weight, format_dcf_display_context
from data.earnings_history import build_earnings_track_record
from data.gemini_analyst_v2 import ask_ai_question
from data.price_guidance import recommend_options_contracts
from data.confidence_engine import ConfidenceEngine
from data.contract_recommender import ContractRecommender
from data.trade_dashboard import TradeDashboard
from data.reverse_dcf import ReverseDCF
from data.industry_metrics import IndustryMetrics
from data.strategy_optimizer import StrategyOptimizer
from data.greeks_risk_analyzer import GreeksRiskAnalyzer
from data.volatility_surface_analyzer import VolatilitySurfaceAnalyzer

from data.price_guidance import (
    entry_zone_from_peers,
    scenario_bands,
    build_price_guidance,
)

import numpy as np
import pandas as pd
import yfinance as yf
import json
from fastapi import FastAPI, Request, Form, Query, HTTPException
from pydantic import BaseModel
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates

from data.macro import get_macro_report, macro_report_to_dict
from data.macro_engine import get_macro_snapshot
from data.semis_universe import load_semis_universe, search_semis_universe
from data.glossary import GLOSSARY
from data.annotate import annotate_keys


# ---------------------------------------------------------------------------
# Helper: safely build AIConviction from ai result dict
# ---------------------------------------------------------------------------

def _build_ai_conviction_safe(ai_result, official_confidence: int):
    """
    Build AIConviction from the ai result dict returned by compute_confidence_with_ai.
    Returns fallback_ai_conviction() if AI wasn't available.
    Never raises — safe to call in any code path.

    GOVERNANCE: disagreement is ALWAYS recomputed here against official_confidence
    (the deterministic Option A score), so we never use the AI-vs-AI disagreement
    that gemini_confidence.py baked in when it built the pre-built ac object.
    """
    if not AI_SCHEMAS_AVAILABLE:
        return fallback_ai_conviction()
    try:
        if ai_result and isinstance(ai_result, dict):
            ac = ai_result.get("ai_conviction")

            if ac is not None and isinstance(ac, AIConviction) and ac.available and ac.score_0_100 is not None:
                # Re-compute disagreement against Official Confidence (Option A deterministic),
                # NOT against the AI's own confidence score that was baked in at build time.
                score = ac.score_0_100
                d_abs, d_flag = compute_disagreement(score, official_confidence)
                # Return a fresh object with corrected disagreement fields
                return AIConviction(
                    available=True,
                    score_0_100=score,
                    label=ac.label or ai_conviction_label(score),
                    drivers=ac.drivers[:5],
                    risks=ac.risks[:5],
                    overlay_note=ac.overlay_note,
                    disagreement_abs=d_abs,
                    disagreement_flag=d_flag,
                    model=ac.model,
                    trace_id=ac.trace_id,
                    debug=ac.debug,
                )

            # Legacy path: no pre-built ac — ai result has a raw confidence score only.
            # Treat as unavailable conviction (not a conviction score, just AI confidence).
            if ai_result.get("available") and ai_result.get("confidence") is not None:
                score = int(ai_result["confidence"])
                d_abs, d_flag = compute_disagreement(score, official_confidence)
                return AIConviction(
                    available=True,
                    score_0_100=score,
                    label=ai_conviction_label(score),
                    drivers=ai_result.get("key_drivers", [])[:5],
                    risks=ai_result.get("risks", [])[:5],
                    disagreement_abs=d_abs,
                    disagreement_flag=d_flag,
                    model="gemini-legacy",
                )
    except Exception as _e:
        print(f"_build_ai_conviction_safe error: {_e}")
    return fallback_ai_conviction()


def _build_options_confidence_v3(
    option_a_dict: dict,
    final_confidence: int,
    overlay: dict,
    overlay_delta: int,
) -> dict:
    """
    Canonical ConfidenceV3 pipeline for options mode.
    Converts the raw Option A dict → ConfidenceV3 → template-safe dict.
    Always safe: falls back to a minimal valid dict if anything fails.
    """
    try:
        from data.confidence_schema import ConfidenceV3 as _CV3
        _v3 = option_a_to_v3(option_a_dict, mode="options")
        _v3.total_0_100 = max(0, min(100, final_confidence))
        _v3.overlay_delta_points = overlay_delta
        _v3.missing_penalty_points = option_a_dict.get("missing_penalty", 0)
        _v3.grade = _CV3.grade_from_score(_v3.total_0_100)
        result = v3_to_template_confidence(_v3)
        result["base"]       = option_a_dict.get("total", final_confidence)
        result["overlay"]    = overlay
        result["reasoning"]  = option_a_dict.get("reasoning", {})
        # Preserve factor_meta — v3 conversion does not carry it.
        result["factor_meta"] = option_a_dict.get("factor_meta", {})
        result["weights"]     = option_a_dict.get("weights", result.get("weights", {}))
        result["breakdown"]   = option_a_dict.get("breakdown", result.get("breakdown", {}))
        result["contrib"]     = option_a_dict.get("contrib", result.get("contrib", {}))
        return result
    except Exception as _e:
        print(f"_build_options_confidence_v3 error: {_e}")
        return {
            "total": final_confidence,
            "raw": final_confidence / 100.0,
            "base": final_confidence,
            "overlay_delta": overlay_delta,
            "overlay": overlay,
            "contrib": {},
            "breakdown": {},
            "weights": {},
            "reasoning": {},
            "debug": {},
        }


app = FastAPI()
templates = Jinja2Templates(directory="templates")


def recommend_contracts_simple(ticker, spot, view, budget, max_loss, chain_data, confidence, expiry=None):
    recs = []
    if not chain_data or not isinstance(chain_data, dict): return recs
    opt_type = 'call' if view.lower() == 'bullish' else 'put'
    for exp_str, exp_data in chain_data.items():
        if expiry and exp_str != expiry: continue
        opts = exp_data.get('calls' if opt_type == 'call' else 'puts', [])
        for o in opts:
            strike, mid, iv = o.get('strike'), o.get('lastPrice', o.get('mid', 0)), o.get('impliedVolatility')
            bid, ask = o.get('bid', 0), o.get('ask', mid * 2 if mid else 0)
            if not strike or not mid or mid <= 0: continue
            spread_pct = ((ask - bid) / mid * 100) if (mid > 0 and bid > 0) else 999
            if spread_pct > 10: continue
            premium = mid * 100
            contracts = min(int(budget / premium) if premium > 0 else 0, int(max_loss / premium) if premium > 0 else 0)
            if contracts <= 0: continue
            money = (strike - spot) / spot if opt_type == 'call' else (spot - strike) / spot
            quality = (1.0 - min(abs(money) / 0.15, 1.0)) * 0.5 + (0.5 if not iv else (1.0 - min(abs(iv - 0.35) / 0.35, 1.0))) * 0.2 + max(0, 1.0 - spread_pct / 5.0) * 0.3
            recs.append({'type': opt_type.upper(), 'expiry': exp_str, 'strike': strike, 'mid': mid, 'spread_pct': spread_pct, 'iv': iv, 'contracts': contracts, 'total_cost': contracts * premium, 'max_loss': contracts * premium, 'quality_score': quality, 'moneyness': money})
    recs.sort(key=lambda x: x['quality_score'], reverse=True)
    return recs[:5]


# =========================
# Black–Scholes helpers
# =========================

def norm_cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))

def norm_pdf(x: float) -> float:
    return (1.0 / math.sqrt(2.0 * math.pi)) * math.exp(-0.5 * x * x)

def bs_price(S: float, K: float, T: float, r: float, sigma: float, opt_type: str) -> float:
    if T <= 0 or sigma <= 0 or S <= 0 or K <= 0:
        return float("nan")
    d1 = (math.log(S / K) + (r + 0.5 * sigma**2) * T) / (sigma * math.sqrt(T))
    d2 = d1 - sigma * math.sqrt(T)
    if opt_type == "call":
        return S * norm_cdf(d1) - K * math.exp(-r * T) * norm_cdf(d2)
    else:
        return K * math.exp(-r * T) * norm_cdf(-d2) - S * norm_cdf(-d1)

def bs_greeks(S: float, K: float, T: float, r: float, sigma: float, opt_type: str):
    d1 = (math.log(S / K) + (r + 0.5 * sigma**2) * T) / (sigma * math.sqrt(T))
    pdf = norm_pdf(d1)
    gamma = pdf / (S * sigma * math.sqrt(T))
    vega = S * pdf * math.sqrt(T)  # per 1.0 vol
    if opt_type == "call":
        delta = norm_cdf(d1)
    else:
        delta = norm_cdf(d1) - 1
    return float(delta), float(gamma), float(vega)

def realized_vol(close: pd.Series, window: int = 20) -> float:
    r = np.log(close / close.shift(1)).dropna()
    rv = r.rolling(window).std() * np.sqrt(252)
    return float(rv.iloc[-1])

def implied_vol_from_price(mid: float, S: float, K: float, T: float, r: float, opt_type: str) -> float:
    """
    Solve for sigma such that BS price(sigma) ~= mid.
    Returns NaN if no solution / invalid.
    """
    if mid is None or mid <= 0 or S <= 0 or K <= 0 or T <= 0:
        return float("nan")

    sigma = 0.5  # start guess 50%
    for _ in range(50):
        price = bs_price(S, K, T, r, sigma, opt_type)
        if math.isnan(price):
            return float("nan")
        diff = price - mid

        _, _, vega = bs_greeks(S, K, T, r, sigma, opt_type)
        if vega <= 1e-8:
            break

        sigma_new = sigma - diff / vega
        sigma = max(1e-4, min(5.0, sigma_new))

        if abs(diff) < 1e-4:
            break

    return float(sigma)


# =========================
# Semis cluster mapping (v1)
# =========================

CLUSTERS = {
    # ---- Compute / CPUs / GPUs / AI silicon ----
    "compute_ai": ["NVDA", "AMD", "INTC", "ARM"],

    # ---- Connectivity / RF / Networking ----
    "connectivity_rf": ["AVGO", "QCOM", "SWKS", "QRVO", "NXPI", "MRVL", "ANET"],

    # ---- Analog / Power / PMIC / mixed-signal ----
    "analog_power": ["TXN", "ADI", "MPWR", "MCHP", "ON", "STM"],

    # ---- Memory / Storage ----
    "memory_storage": ["MU", "WDC", "STX"],

    # ---- Foundry / Manufacturing ----
    "foundry": ["TSM", "UMC", "GFS"],

    # ---- Semi equipment / Process / Inspection / Test ----
    "equipment": [
        "ASML", "AMAT", "LRCX", "KLAC", "TER", "ACLS", "ONTO",
        "MKSI", "ENTG", "COHU", "AEHR", "CAMT", "FORM",
    ],

    # ---- Photonics / Laser (often used in semi/AI infra chain) ----
    "photonics": ["IPGP"],

    # ---- Power / SiC ----
    "power_sic": ["WOLF"],

    # ---- EDA ----
    "eda": ["CDNS", "SNPS"],

    # ---- OSAT / Packaging / Test ----
    "osat": ["ASX"],

    # ---- Programmable logic ----
    "programmable": ["LSCC"],

    # ---- AI servers / infra (not a “semiconductor” company, but trading-relevant) ----
    "ai_infra": ["SMCI"],
}

def _num(x):
    try:
        if x is None:
            return None
        v = float(x)
        if math.isnan(v) or math.isinf(v):
            return None
        return v
    except Exception:
        return None

def _quantiles(vals: list[float]):
    if not vals:
        return {"p25": None, "median": None, "p75": None}
    s = sorted(vals)
    n = len(s)
    def q(p: float):
        if n == 1:
            return s[0]
        idx = p * (n - 1)
        lo = int(math.floor(idx))
        hi = int(math.ceil(idx))
        if lo == hi:
            return s[lo]
        w = idx - lo
        return s[lo] * (1 - w) + s[hi] * w
    return {"p25": q(0.25), "median": q(0.50), "p75": q(0.75)}

def _pct_rank(x: float, vals: list[float]):
    if x is None or not vals:
        return None
    s = sorted(vals)
    n = len(s)
    if n == 1:
        return 1.0
    le = sum(1 for v in s if v <= x)
    return le / n

def build_peer_snapshot(ticker: str, peers: list[str], cluster: str | None = None):
    ticker = (ticker or "").strip().upper()
    peers = [p.strip().upper() for p in (peers or []) if p]

    # ensure self included
    if ticker and ticker not in peers:
        peers = [ticker] + peers

    rows = []
    for sym in peers[:30]:
        info = {}
        try:
            info = (yf.Ticker(sym).info or {})
        except Exception:
            info = {}

        name = info.get("longName") or info.get("shortName") or sym
        last = _num(info.get("regularMarketPrice") or info.get("currentPrice"))
        mcap = _num(info.get("marketCap"))
        tpe = _num(info.get("trailingPE"))
        fpe = _num(info.get("forwardPE"))
        peg = _num(info.get("pegRatio"))

        rows.append({
            "ticker": sym,
            "name": name,
            "last": last,
            "market_cap": mcap,
            "trailing_pe": tpe,
            "forward_pe": fpe,
            "peg": peg,
        })

    # build PE bands from available peer values
    trailing_vals = [r["trailing_pe"] for r in rows if r["trailing_pe"] is not None]
    forward_vals  = [r["forward_pe"]  for r in rows if r["forward_pe"]  is not None]

    trailing_bands = _quantiles(trailing_vals)
    forward_bands  = _quantiles(forward_vals)

    # focal ticker row
    focal = next((r for r in rows if r["ticker"] == ticker), None) or {}

    # simple interpretation flags (deterministic)
    flags = []
    if focal.get("forward_pe") is not None and forward_bands["p25"] is not None and forward_bands["p75"] is not None:
        if focal["forward_pe"] <= forward_bands["p25"]:
            flags.append("Cheap vs peers (forward P/E in bottom quartile)")
        elif focal["forward_pe"] >= forward_bands["p75"]:
            flags.append("Expensive vs peers (forward P/E in top quartile)")
    elif focal.get("trailing_pe") is not None and trailing_bands["p25"] is not None and trailing_bands["p75"] is not None:
        if focal["trailing_pe"] <= trailing_bands["p25"]:
            flags.append("Cheap vs peers (trailing P/E in bottom quartile)")
        elif focal["trailing_pe"] >= trailing_bands["p75"]:
            flags.append("Expensive vs peers (trailing P/E in top quartile)")
    else:
        flags.append("Valuation bands missing (insufficient peer P/E data)")

    # sort display by market cap desc (None last)
    def _mcap_key(r):
        v = r.get("market_cap")
        return (-v) if isinstance(v, (int, float)) else float("inf")

    rows_sorted = sorted(rows, key=_mcap_key)

    return {
        "ticker": ticker,
        "cluster": cluster,
        "peer_count": len(rows_sorted),
        "bands": {
            "trailing_pe": trailing_bands,
            "forward_pe": forward_bands,
        },
        "focal": {
            **focal,
            "trailing_pe_pct_rank": _pct_rank(focal.get("trailing_pe"), trailing_vals) if focal else None,
            "forward_pe_pct_rank": _pct_rank(focal.get("forward_pe"), forward_vals) if focal else None,
            "flags": flags,
        },
        "rows": rows_sorted,
        "asof_utc": datetime.now(timezone.utc).isoformat(),
    }



# =========================
# Shared helpers
# =========================

HORIZONS = {
    "short": (7, 30),
    "swing": (14, 60),
    "long": (60, 180),
}

def build_liquidity_gate(auto_info: dict | None, max_spread_pct: float) -> dict:
    """
    P0-1 FIX: IB-standard liquidity gate - single source of truth.
    All liquidity metrics come from auto_expiry ONLY.
    No fallbacks that create contradictions.
    
    Returns unified liquidity_gate object used everywhere:
    - Banner display
    - Auto-expiry diagnostics
    - Verdict gating
    - AI chat blocking
    """
    if not auto_info or not auto_info.get("metrics"):
        return {
            "status": "BLOCK",
            "reason": "Chain unavailable — cannot compute liquidity metrics",
            "pct_two_sided": None,
            "median_spread": None,
            "liquidity_grade": "F",
            "score": 0.0,
            "source": "unavailable",
            "auto_expiry_score": 0.0
        }
    
    # Extract from auto_expiry metrics (ONLY source - no fallbacks!)
    metrics = auto_info.get("metrics", {})
    liq_grade = auto_info.get("liq_grade") or "C"
    liq_score = auto_info.get("score", 0.0)
    
    pct_two_sided = metrics.get("pct_two_sided")
    median_spread = metrics.get("median_spread")
    
    # Gate logic using auto-expiry values ONLY
    reasons = []
    
    # Grade gate
    if liq_grade in ["C", "D", "F"]:
        reasons.append(f"Liquidity grade {liq_grade}")
    
    # Two-sided quote gate
    if pct_two_sided is not None:
        try:
            if float(pct_two_sided) <= 0.05:
                reasons.append(f"pct_two_sided too low ({pct_two_sided:.3f})")
        except:
            pass
    
    # Spread gate (using median_spread from auto_expiry)
    if median_spread is not None:
        try:
            if float(median_spread) > float(max_spread_pct):
                reasons.append(f"Spread too wide ({median_spread:.2%} > {max_spread_pct:.2%})")
        except:
            pass
    
    # Determine status
    if len(reasons) > 0:
        if liq_grade in ["D", "F"]:
            status = "BLOCK"
        else:
            status = "WARN"
    else:
        status = "PASS"
    
    return {
        "status": status,  # PASS | WARN | BLOCK
        "reason": " / ".join(reasons) if reasons else "Liquidity passes institutional filter",
        "pct_two_sided": pct_two_sided,
        "median_spread": median_spread,
        "liquidity_grade": liq_grade,
        "score": liq_score,
        "source": "auto_expiry",
        "auto_expiry_score": liq_score
    }


# DEPRECATED - kept for backward compatibility, redirects to build_liquidity_gate
def compute_liquidity_gate(auto_expiry_result: dict | None,
                           selected_option: dict | None,
                           max_spread_pct: float) -> tuple[bool, str]:
    """
    DEPRECATED: Use build_liquidity_gate instead.
    This function kept for backward compatibility only.
    """
    # Redirect to new unified function
    gate = build_liquidity_gate(auto_expiry_result, max_spread_pct)
    blocked = (gate["status"] == "BLOCK")
    reason = gate["reason"]
    return blocked, reason


def horizon_matches(hold_days: int, overlay_horizon: str) -> bool:
    """Check if overlay horizon matches trade horizon."""
    if hold_days <= 30:
        return overlay_horizon in ["days-weeks", "1-3 months"]
    elif hold_days <= 90:
        return overlay_horizon in ["1-3 months", "6-12 months"]
    else:
        return True  # Long-term trades match all horizons


def overlay_to_risk_adjustments(overlay: dict, base_metrics: dict) -> dict:
    """
    ADVANCED OVERLAY: Transform user overlay into institutional risk plan adjustments.
    
    Overlay primarily affects RISK CONTROLS (sizing, entry, stops, hedges), not confidence.
    Small confidence nudge (±0 to ±5 max) only if horizon matches.
    
    This is how real PMs operate: conviction changes risk management, not whether math is true.
    """
    # Default (no overlay)
    if not overlay.get('present'):
        return {
            'size_multiplier': 1.0,
            'entry_aggressiveness': 'base',
            'stop_tightness': 'normal',
            'require_hedge': False,
            'hedge_style': None,
            'take_profit_style': 'scale',
            'confidence_delta': 0,
            'notes': [],
            'overlay_used': False
        }
    
    # Extract overlay components
    bull_text = overlay.get('bull', '').strip()
    bear_text = overlay.get('bear', '').strip()
    strength = overlay.get('strength', 0)  # 0-100
    horizon = overlay.get('horizon', '')
    overlay_type = overlay.get('type', 'other')
    actionability = overlay.get('actionability', False)
    
    # Extract base metrics
    hold_days = base_metrics.get('hold_days', 14)
    base_confidence = base_metrics.get('base_confidence', 50)
    liq_status = base_metrics.get('liquidity_gate_status', 'PASS')
    dcf_reasonableness = base_metrics.get('reverse_dcf_reasonableness', 5.0)
    earnings_window = base_metrics.get('earnings_within_window', False)
    
    # Normalize strength (0 to 1)
    s = max(0.0, min(1.0, strength / 100.0))
    
    # Horizon gating (CRITICAL)
    horizon_match = horizon_matches(hold_days, horizon)
    if not horizon_match and not actionability:
        return {
            'size_multiplier': 1.0,
            'entry_aggressiveness': 'base',
            'stop_tightness': 'normal',
            'require_hedge': False,
            'hedge_style': None,
            'take_profit_style': 'scale',
            'confidence_delta': 0,
            'notes': [f"Overlay horizon ({horizon}) doesn't match trade horizon ({hold_days}d) - not applied"],
            'overlay_used': False
        }
    
    # Determine bias
    has_bull = len(bull_text) > 0
    has_bear = len(bear_text) > 0
    
    if has_bear and not has_bull:
        bias = 'bearish'
    elif has_bull and not has_bear:
        bias = 'bullish'
    else:
        bias = 'mixed'
    
    # Initialize risk adjustments
    risk_adj = {
        'size_multiplier': 1.0,
        'entry_aggressiveness': 'base',
        'stop_tightness': 'normal',
        'require_hedge': False,
        'hedge_style': None,
        'take_profit_style': 'scale',
        'confidence_delta': 0,
        'notes': [],
        'overlay_used': True
    }
    
    # ==================================================================
    # BEARISH OVERLAY → Reduce size, tighten discipline
    # ==================================================================
    if bias == 'bearish':
        # Size reduction (max down to 0.6x)
        risk_adj['size_multiplier'] = 1.0 - (0.4 * s)
        risk_adj['notes'].append(f"Size reduced to {risk_adj['size_multiplier']:.2f}x due to bearish overlay (strength {strength}/100)")
        
        # Tighten stops
        if s >= 0.6:
            risk_adj['stop_tightness'] = 'tight'
            risk_adj['notes'].append("Stops tightened due to bearish risk awareness")
        
        # Conservative entry
        risk_adj['entry_aggressiveness'] = 'conservative'
        risk_adj['notes'].append("Entry: conservative (wait for better support/vol)")
        
        # Hedge requirement for macro/earnings risk
        if overlay_type in ['macro/policy', 'earnings'] and s >= 0.7:
            risk_adj['require_hedge'] = True
            risk_adj['hedge_style'] = 'protective_put'  # or collar
            risk_adj['notes'].append(f"Hedge required due to {overlay_type} risk (strength {strength}/100)")
        
        # NOTE: confidence_delta is intentionally 0 here; overlay_confidence_delta() is the
        # sole driver of confidence adjustments to prevent double-counting.
    
    # ==================================================================
    # BULLISH OVERLAY → Increase size slightly, loosen entry
    # ==================================================================
    elif bias == 'bullish':
        # Check if we can be aggressive
        can_be_aggressive = (
            liq_status == 'PASS' and
            dcf_reasonableness >= 3.0 and
            (not earnings_window or overlay_type == 'earnings')
        )
        
        # Size increase (max up to 1.2x)
        if can_be_aggressive:
            risk_adj['size_multiplier'] = 1.0 + (0.2 * s)
            risk_adj['notes'].append(f"Size increased to {risk_adj['size_multiplier']:.2f}x due to bullish overlay (strength {strength}/100)")
        else:
            risk_adj['size_multiplier'] = 1.0 + (0.1 * s)
            risk_adj['notes'].append(f"Size modestly increased to {risk_adj['size_multiplier']:.2f}x (constraints prevent full aggressiveness)")
        
        # Entry aggressiveness
        if can_be_aggressive and s >= 0.7:
            risk_adj['entry_aggressiveness'] = 'aggressive'
            risk_adj['notes'].append("Entry: aggressive (can enter near current price)")
        else:
            risk_adj['entry_aggressiveness'] = 'base'
        
        # Stops stay normal
        risk_adj['stop_tightness'] = 'normal'
        
        # NOTE: confidence_delta is intentionally 0 here; overlay_confidence_delta() is the
        # sole driver of confidence adjustments to prevent double-counting.
    
    # ==================================================================
    # MIXED OVERLAY → Conservative adjustments
    # ==================================================================
    else:  # mixed
        if len(bear_text) > len(bull_text):
            risk_adj['size_multiplier'] = 0.8
            risk_adj['notes'].append("Size: 0.8x (mixed overlay, bearish lean)")
        else:
            risk_adj['size_multiplier'] = 1.1
            risk_adj['notes'].append("Size: 1.1x (mixed overlay, bullish lean)")
        
        risk_adj['confidence_delta'] = 0
        risk_adj['notes'].append("Confidence: no adjustment (mixed signals)")
    
    # ==================================================================
    # HARD CAPS - Overlay can NEVER override
    # ==================================================================
    if liq_status == 'BLOCK':
        risk_adj['size_multiplier'] = 0.0
        risk_adj['require_hedge'] = False
        risk_adj['notes'].append("⚠️ HARD CAP: Liquidity BLOCKED - no trade possible")
        risk_adj['entry_aggressiveness'] = 'none'
    
    if dcf_reasonableness < 2.0 and risk_adj['entry_aggressiveness'] == 'aggressive':
        risk_adj['entry_aggressiveness'] = 'base'
        risk_adj['notes'].append("⚠️ HARD CAP: DCF stretch prevents aggressive entry")
    
    if earnings_window and overlay_type == 'macro/policy' and bias == 'bearish':
        risk_adj['require_hedge'] = True
        risk_adj['hedge_style'] = 'collar'
        risk_adj['notes'].append("⚠️ Hedge required: earnings + macro risk combination")
    
    return risk_adj


def overlay_confidence_delta(overlay: dict, hold_days: int, cap: int = 5) -> int:
    """
    Deterministic confidence adjustment from overlay.
    cap=5 keeps it an 'insider nudge' not an override.
    Negative overlay should reduce confidence too.
    """
    if not overlay or not overlay.get("present"):
        return 0

    strength = int(overlay.get("strength") or 0)
    bull = bool((overlay.get("bull") or "").strip())
    bear = bool((overlay.get("bear") or "").strip())

    # Horizon gating: only apply if overlay horizon matches trade horizon bucket
    h = (overlay.get("horizon") or "").lower()
    if hold_days <= 30 and ("days" not in h and "1-3" not in h):
        return 0
    if 30 < hold_days <= 90 and ("1-3" not in h and "6-12" not in h):
        return 0

    # Convert strength (0-100) to 0..cap
    mag = round((strength / 100.0) * cap)

    if bull and not bear:
        return +mag
    if bear and not bull:
        return -mag

    # If both provided, net to small effect (default 0)
    return 0


def cap_target_price(
    spot: float,
    ai_base: float | None,
    implied_move_pct: float | None,
    model_target_price: float | None,
    reverse_dcf_score: float | None,
) -> tuple[float, dict]:
    """
    Clamp AI targets using the market-implied expected move and valuation stretch.
    implied_move_pct is decimal (e.g., 0.35 for 35%).
    """
    caps = {"applied": False, "reason": ""}
    # Fallback expected move if missing
    em = float(implied_move_pct) if implied_move_pct and implied_move_pct > 0 else 0.20
    # Determine sigma multiplier based on stretch (lower score => tighter caps)
    s = reverse_dcf_score if reverse_dcf_score is not None else 5.0
    if s < 2.0:
        k = 1.0
        caps["reason"] = "reverse-DCF stretch → cap at ~1σ expected move"
    elif s < 4.0:
        k = 1.5
        caps["reason"] = "elevated stretch → cap at ~1.5σ expected move"
    else:
        k = 2.0
        caps["reason"] = "normal → cap at ~2σ expected move"
    cap_by_vol = spot * (1.0 + k * em)
    raw = ai_base if ai_base and ai_base > 0 else None
    if raw is None:
        raw = model_target_price if model_target_price and model_target_price > 0 else spot * 1.10
        caps["applied"] = True
        caps["reason"] = "missing AI target → fallback to model/spot baseline"
    final = min(raw, cap_by_vol)
    # Optional: if model target is lower than vol cap, prefer model target as an upper bound
    if model_target_price and model_target_price > 0:
        final = min(final, float(model_target_price) * 1.05)  # small tolerance
        caps["applied"] = True
    if final != raw:
        caps["applied"] = True
        caps["reason"] = caps["reason"] or "vol-based cap applied"
    return float(final), caps


def _days_to_exp(date_str: str) -> int:
    dt = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    return max((dt - datetime.now(timezone.utc)).days, 0)

def _json_safe_float(x):
    if x is None:
        return None
    if isinstance(x, float):
        if math.isnan(x) or math.isinf(x):
            return None
    return x

def sanitize(obj: Any):
    if isinstance(obj, dict):
        return {k: sanitize(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [sanitize(v) for v in obj]
    return _json_safe_float(obj)

from zoneinfo import ZoneInfo

def cached_option_chain(ticker: str, expiry: str):
    """
    Cache yfinance option_chain calls for (ticker, expiry).
    Returns the yfinance OptionChain object (calls/puts DataFrames).
    """
    key = f"chain:{ticker}:{expiry}"
    return CHAIN_CACHE.get_or_set(
        key,
        lambda: yf.Ticker(ticker).option_chain(expiry),
        ttl_sec=45,
    )


def get_earnings_info(t: yf.Ticker, ticker: str | None = None) -> dict:
    """
    Robust earnings date resolver + US session labeling (ET).
    Tries, in order:
      1) yfinance.get_earnings_dates (index OR column)
      2) yfinance.calendar (dict OR DataFrame; handles list/tuple/series)
      3) t.info timestamp keys (earningsTimestamp / Start / End)
    Returns keys used by report.html:
      - earnings_date_utc, days_to_earnings, source
      - earnings_date_us, earnings_time_us, session_us, days_to_earnings_us
    """
    now_utc = datetime.now(timezone.utc)
    ET = ZoneInfo("America/New_York")

    def _to_ts(x):
        """Parse x -> pd.Timestamp (may be tz-naive)."""
        dt = pd.to_datetime(x, errors="coerce")
        if pd.isna(dt):
            return None
        return dt

    def _as_utc(ts: pd.Timestamp | None):
        if ts is None:
            return None
        # If tz-naive, assume UTC (date-only sources)
        if getattr(ts, "tzinfo", None) is None and getattr(ts, "tz", None) is None:
            return ts.tz_localize(timezone.utc)
        return ts.tz_convert(timezone.utc)

    def _pick_next(dts_utc: list[pd.Timestamp]):
        dts_utc = [d for d in dts_utc if d is not None]
        if not dts_utc:
            return None
        # allow "today" to show
        cutoff = now_utc - pd.Timedelta(days=1)
        future = [d for d in dts_utc if d.to_pydatetime() >= cutoff.to_pydatetime()]
        if not future:
            return None
        return min(future)

    def _session_label(dt_et: datetime | None):
        """
        Determine session in ET (best-effort):
          Pre:   before 09:30
          Regular: 09:30–16:00
          Post:  after 16:00
        If we only have date (00:00) we return None.
        """
        if dt_et is None:
            return None
        # if time looks like midnight and source is date-only, don't pretend
        if dt_et.hour == 0 and dt_et.minute == 0 and dt_et.second == 0:
            return None

        mins = dt_et.hour * 60 + dt_et.minute
        pre_open = 9 * 60 + 30
        reg_close = 16 * 60

        if mins < pre_open:
            return "Pre-market"
        if mins >= reg_close:
            return "Post-market"
        return "Regular"

    def _build_payload(best_utc: pd.Timestamp, source: str):
        dt_utc = best_utc.to_pydatetime()
        dt_et = dt_utc.astimezone(ET)

        days_utc = int((dt_utc - now_utc).days)

        payload = {
            "earnings_date_utc": best_utc.date().isoformat(),
            "days_to_earnings": days_utc,
            "source": source,
            # US-facing fields (ET)
            "earnings_date_us": dt_et.date().isoformat(),
            "earnings_time_us": None,
            "session_us": None,
            "days_to_earnings_us": int((dt_et.date() - now_utc.astimezone(ET).date()).days),
        }

        # Only show time/session if we have a real time (not date-only midnight)
        sess = _session_label(dt_et)
        if sess is not None:
            payload["earnings_time_us"] = dt_et.strftime("%H:%M")
            payload["session_us"] = sess
        
        # -------- Phase 7A: deterministic reliability score --------
        # Source strength (deterministic)
        base = 0.55
        if source == "yfinance.get_earnings_dates":
            base = 0.90
        elif source == "yfinance.calendar":
            base = 0.75
        elif source.startswith("yfinance.info."):
            base = 0.65
        elif source.startswith("yfinance.retry.info."):
            base = 0.60
        elif source == "yfinance.retry.get_earnings_dates":
            base = 0.70

        # Data quality: penalize if we only have date-only (no time/session)
        if payload.get("earnings_time_us") is None or payload.get("session_us") is None:
            base = max(0.0, base - 0.10)

        if base >= 0.80:
            rel_label = "HIGH"
        elif base >= 0.65:
            rel_label = "MED"
        else:
            rel_label = "LOW"

        payload["reliability"] = round(float(base), 2)
        payload["reliability_label"] = rel_label


        return payload

    # 1) get_earnings_dates (index/columns)
    try:
        df = t.get_earnings_dates(limit=40)
        if df is not None and not df.empty:
            dts_utc = []

            # earnings datetime in index (common)
            if df.index is not None and len(df.index) > 0:
                for x in list(df.index):
                    ts = _as_utc(_to_ts(x))
                    if ts is not None:
                        dts_utc.append(ts)

            # sometimes a column
            for col in ["Earnings Date", "EarningsDate", "Earnings", "earningsDate"]:
                if col in df.columns:
                    for x in df[col].tolist():
                        ts = _as_utc(_to_ts(x))
                        if ts is not None:
                            dts_utc.append(ts)

            best = _pick_next(dts_utc)
            if best is not None:
                payload = _build_payload(best, "yfinance.get_earnings_dates")
                payload["all_earnings_dates_utc"] = [d.isoformat() for d in sorted(set(dts_utc))[:40]]
                payload["all_earnings_dates_us"] = [
                    d.to_pydatetime().astimezone(ET).date().isoformat()
                    for d in sorted(set(dts_utc))[:40]
                ]
                return payload

    except Exception:
        pass

    # 2) calendar fallback (dict or DataFrame)
    try:
        cal = t.calendar
        val = None

        # a) dict-style calendar (your probe shows this case)
        if isinstance(cal, dict):
            # keys can vary; try a few
            for k in ["Earnings Date", "EarningsDate", "earningsDate"]:
                if k in cal:
                    val = cal.get(k)
                    break

        # b) DataFrame-style calendar
        elif cal is not None and not getattr(cal, "empty", False):
            if "Earnings Date" in getattr(cal, "index", []):
                try:
                    val = cal.loc["Earnings Date"][0]
                except Exception:
                    val = None
            if val is None:
                for col in getattr(cal, "columns", []):
                    if str(col).lower().strip() in ["earnings date", "earningsdate"]:
                        try:
                            val = cal[col].iloc[0]
                        except Exception:
                            val = None
                        break

        dts_utc = []
        if isinstance(val, (list, tuple)):
            for x in val:
                ts = _as_utc(_to_ts(x))
                if ts is not None:
                    dts_utc.append(ts)
        else:
            ts = _as_utc(_to_ts(val))
            if ts is not None:
                dts_utc.append(ts)

        best = _pick_next(dts_utc)
        if best is not None:
            return _build_payload(best, "yfinance.calendar")
    except Exception:
        pass

    # 3) t.info timestamp keys (NVDA works here in your probe)
    try:
        info = getattr(t, "info", {}) or {}
        for key in ["earningsTimestamp", "earningsTimestampStart", "earningsTimestampEnd"]:
            ts_val = info.get(key)
            if ts_val:
                # Yahoo is seconds since epoch
                dt_utc = datetime.fromtimestamp(int(ts_val), tz=timezone.utc)
                best = pd.Timestamp(dt_utc)
                return _build_payload(best, f"yfinance.info.{key}")
    except Exception:
        pass


    # 4) FINAL RETRY: fresh Ticker object (yfinance can return empty/blocked data on first object)
    # Only do one retry to avoid making the request path heavy.
    if ticker:
        try:
            t2 = yf.Ticker(ticker)

            # Try info timestamp keys first (fast, often available even when other endpoints fail)
            info2 = getattr(t2, "info", {}) or {}
            for key in ["earningsTimestamp", "earningsTimestampStart", "earningsTimestampEnd"]:
                ts_val = info2.get(key)
                if ts_val:
                    dt_utc = datetime.fromtimestamp(int(ts_val), tz=timezone.utc)
                    best = pd.Timestamp(dt_utc)
                    return _build_payload(best, f"yfinance.retry.info.{key}")

            # Then try get_earnings_dates with a small limit
            df2 = t2.get_earnings_dates(limit=16)
            if df2 is not None and not df2.empty:
                dts_utc = []
                if df2.index is not None and len(df2.index) > 0:
                    for x in list(df2.index):
                        ts = _as_utc(_to_ts(x))
                        if ts is not None:
                            dts_utc.append(ts)

                for col in ["Earnings Date", "EarningsDate", "Earnings", "earningsDate"]:
                    if col in df2.columns:
                        for x in df2[col].tolist():
                            ts = _as_utc(_to_ts(x))
                            if ts is not None:
                                dts_utc.append(ts)

                best = _pick_next(dts_utc)
                if best is not None:
                    payload = _build_payload(best, "yfinance.retry.get_earnings_dates")
                    payload["all_earnings_dates_utc"] = [d.isoformat() for d in sorted(set(dts_utc))[:40]]
                    payload["all_earnings_dates_us"] = [
                        d.to_pydatetime().astimezone(ET).date().isoformat()
                        for d in sorted(set(dts_utc))[:40]
                    ]
                    return payload

        except Exception:
            pass

    return {
        "earnings_date_utc": None,
        "days_to_earnings": None,
        "source": None,
        "earnings_date_us": None,
        "earnings_time_us": None,
        "session_us": None,
        "days_to_earnings_us": None,
    }


def earnings_realized_move_stats(hist: pd.DataFrame, earnings_info: dict, lookback: int = 6) -> dict | None:
    """
    Deterministic realized earnings move proxy:
    abs(close_after / close_before - 1) around the earnings DATE (no session modeling).
    Uses the last close BEFORE the earnings date and first close AFTER the earnings date.
    """
    try:
        if hist is None or hist.empty or "Close" not in hist:
            return None

        close = hist["Close"].dropna()
        if close.empty:
            return None

        dates_us = (earnings_info or {}).get("all_earnings_dates_us") or []
        if not dates_us:
            return None

        last_day = close.index[-1].date()

        # keep only past earnings dates (strictly before last history date)
        past = []
        for d in dates_us:
            try:
                dd = pd.to_datetime(d).date()
                if dd < last_day:
                    past.append(dd)
            except Exception:
                continue

        past = sorted(past)[-lookback:]
        if not past:
            return None

        idx_dates = [ts.date() for ts in close.index]
        moves = []

        for ed in past:
            prev_candidates = [i for i, dt in enumerate(idx_dates) if dt < ed]
            next_candidates = [i for i, dt in enumerate(idx_dates) if dt > ed]
            if not prev_candidates or not next_candidates:
                continue

            i_prev = prev_candidates[-1]
            i_next = next_candidates[0]

            c_prev = float(close.iloc[i_prev])
            c_next = float(close.iloc[i_next])
            if c_prev > 0:
                moves.append(abs(c_next / c_prev - 1.0))

        if not moves:
            return None

        moves_sorted = sorted(moves)
        n = len(moves_sorted)
        median = moves_sorted[n // 2] if (n % 2 == 1) else 0.5 * (moves_sorted[n // 2 - 1] + moves_sorted[n // 2])

        return {
            "n": n,
            "avg_abs_pct": round((sum(moves_sorted) / n) * 100.0, 2),
            "median_abs_pct": round(median * 100.0, 2),
            "min_abs_pct": round(moves_sorted[0] * 100.0, 2),
            "max_abs_pct": round(moves_sorted[-1] * 100.0, 2),
        }
    except Exception:
        return None



def build_iv_term_and_skew_from_chain(
        ticker: str, 
        t: yf.Ticker, 
        spot: float, 
        r: float, 
        selected_expiry: str, 
        max_strikes_each_side: int = 12
) -> tuple[list[dict], list[dict], float | None]:
    """
    Returns:
      term: [{expiry, dte, atm_iv}]
      skew: [{strike, iv}] for selected_expiry
      atm_iv_selected
    Uses mid=(bid+ask)/2 when possible, else lastPrice if >0.
    IV is solved via implied_vol_from_price (your existing function).
    """
    expiries = list(t.options or [])
    if not expiries:
        return [], [], None

    term = []
    atm_iv_selected = None

    def _calc_iv_for_expiry(exp: str) -> tuple[float | None, float | None, pd.DataFrame | None, pd.DataFrame | None]:
        try:
            ch = cached_option_chain(ticker, exp)
            calls = ch.calls.copy()
            puts = ch.puts.copy()
        except Exception:
            return None, None, None, None

        if calls is None or calls.empty:
            return None, None, None, None

        # compute DTE/T
        dte = _days_to_exp(exp)
        T = max(dte / 365.0, 1e-6)

        # find ATM strike
        calls["abs_m"] = (calls["strike"] - spot).abs()
        atm_strike = float(calls.sort_values("abs_m").iloc[0]["strike"])

        def _pick_mid(row):
            bid = _to_float(row.get("bid"), 0.0)
            ask = _to_float(row.get("ask"), 0.0)
            lastp = _to_float(row.get("lastPrice"), 0.0)

            if bid > 0 and ask > 0:
                return (bid + ask) / 2.0
            # NEW: one-sided fallback
            if bid > 0 and ask <= 0:
                return bid
            if ask > 0 and bid <= 0:
                return ask

            if lastp > 0:
                return lastp
            return None

        # ATM IV from call + put if available
        ivs = []
        call_row = calls.loc[calls["strike"].astype(float) == float(atm_strike)]
        if not call_row.empty:
            mid = _pick_mid(call_row.iloc[0])
            if mid is not None and mid > 0:
                iv = implied_vol_from_price(mid, spot, atm_strike, T, r, "call")
                if iv and (not math.isnan(iv)) and (not math.isinf(iv)) and iv > 0:
                    ivs.append(float(iv))

        if puts is not None and (not puts.empty):
            put_row = puts.loc[puts["strike"].astype(float) == float(atm_strike)]
            if not put_row.empty:
                mid = _pick_mid(put_row.iloc[0])
                if mid is not None and mid > 0:
                    iv = implied_vol_from_price(mid, spot, atm_strike, T, r, "put")
                    if iv and (not math.isnan(iv)) and (not math.isinf(iv)) and iv > 0:
                        ivs.append(float(iv))

        atm_iv = (sum(ivs) / len(ivs)) if ivs else None
        return atm_iv, atm_strike, calls, puts

    # ---- term structure across expiries ----
    for exp in expiries:
        atm_iv, atm_strike, _, _ = _calc_iv_for_expiry(exp)
        if atm_iv is None:
            continue
        term.append({"expiry": exp, "dte": _days_to_exp(exp), "atm_iv": float(atm_iv)})
        if exp == selected_expiry:
            atm_iv_selected = float(atm_iv)

    term.sort(key=lambda x: x["dte"])

    # ---- skew for selected expiry ----
    skew = []
    atm_iv, atm_strike, calls, puts = _calc_iv_for_expiry(selected_expiry)
    if calls is None or calls.empty:
        return term, skew, atm_iv_selected

    # build strike set near ATM
    strikes = sorted(set(calls["strike"].astype(float).tolist()) | set((puts["strike"].astype(float).tolist() if puts is not None and not puts.empty else [])))
    idx = min(range(len(strikes)), key=lambda i: abs(strikes[i] - float(atm_strike)))
    lo = max(0, idx - max_strikes_each_side)
    hi = min(len(strikes), idx + max_strikes_each_side + 1)
    keep = set(strikes[lo:hi])

    dte = _days_to_exp(selected_expiry)
    T = max(dte / 365.0, 1e-6)

    def _add_rows(df: pd.DataFrame, opt_type: str):
        if df is None or df.empty:
            return
        df2 = df[df["strike"].astype(float).isin(keep)].copy()
        for _, row in df2.iterrows():
            K = float(row["strike"])
            bid = _to_float(row.get("bid"), 0.0)
            ask = _to_float(row.get("ask"), 0.0)
            lastp = _to_float(row.get("lastPrice"), 0.0)
            if bid > 0 and ask > 0:
                mid = (bid + ask) / 2.0
            elif bid > 0 and ask <= 0:
                mid = bid
            elif ask > 0 and bid <= 0:
                mid = ask
            elif lastp > 0:
                mid = lastp
            else:
                continue

            iv = implied_vol_from_price(mid, spot, K, T, r, opt_type)
            if iv and (not math.isnan(iv)) and (not math.isinf(iv)) and iv > 0:
                skew.append({"strike": K, "iv": float(iv)})

    _add_rows(calls, "call")
    if puts is not None and (not puts.empty):
        _add_rows(puts, "put")

    # average duplicates (call+put at same strike) into one point
    if skew:
        by_k = {}
        for pt in skew:
            by_k.setdefault(pt["strike"], []).append(pt["iv"])
        skew = [{"strike": k, "iv": sum(vs) / len(vs)} for k, vs in by_k.items()]
        skew.sort(key=lambda x: x["strike"])

    return term, skew, atm_iv_selected


def get_atm_straddle_from_chain(ticker: str, expiry: str, spot: float) -> dict:
    """
    Returns ATM call/put mids and straddle mid for a given expiry.
    Uses the nearest strike to spot, prefers mid, falls back to bid/ask/last.
    """
    try:
        chain = cached_option_chain(ticker, expiry)
    except Exception:
        return {"atm_strike": None, "call_mid": None, "put_mid": None, "straddle_mid": None}

    calls = chain.calls.copy()
    puts = chain.puts.copy()
    if calls is None or calls.empty or puts is None or puts.empty:
        return {"atm_strike": None, "call_mid": None, "put_mid": None, "straddle_mid": None}

    calls["abs_moneyness"] = (calls["strike"] - spot).abs()
    atm_strike = float(calls.sort_values("abs_moneyness").iloc[0]["strike"])

    def _pick_mid(df: pd.DataFrame) -> float | None:
        row = df.loc[df["strike"] == atm_strike]
        if row is None or row.empty:
            return None
        row = row.iloc[0]
        bid = _to_float(row.get("bid"), 0.0)
        ask = _to_float(row.get("ask"), 0.0)
        lastp = _to_float(row.get("lastPrice"), 0.0)

        if bid > 0 and ask > 0:
            return (bid + ask) / 2.0
        if bid > 0 and ask <= 0:
            return bid
        if ask > 0 and bid <= 0:
            return ask
        if lastp > 0:
            return lastp
        return None

    call_mid = _pick_mid(calls)
    put_mid = _pick_mid(puts)

    straddle_mid = None
    if call_mid is not None and put_mid is not None:
        straddle_mid = float(call_mid + put_mid)

    return {
        "atm_strike": atm_strike,
        "call_mid": call_mid,
        "put_mid": put_mid,
        "straddle_mid": straddle_mid,
    }



def _to_float(v, default=0.0):
    return default if pd.isna(v) else float(v)

def _to_int(v, default=0):
    return default if pd.isna(v) else int(v)

def build_oi_vol_profile(
    ticker: str,
    expiry: str,
    strike_limit: int = 2000,
) -> dict:
    """
    Returns:
      {
        "by_strike": [{"strike", "call_oi","put_oi","call_vol","put_vol"}...],
        "totals": {"call_oi","put_oi","call_vol","put_vol","pcr_oi","pcr_vol"}
      }
    """
    ch = cached_option_chain(ticker, expiry)
    calls = ch.calls.copy()
    puts = ch.puts.copy()
    if calls is None or calls.empty or puts is None or puts.empty:
        return {"by_strike": [], "totals": {}}

    # keep sane max strikes (avoid huge payloads)
    strikes = sorted(set(calls["strike"].astype(float).tolist()) | set(puts["strike"].astype(float).tolist()))
    if len(strikes) > strike_limit:
        # keep centered band around median strike
        mid_idx = len(strikes) // 2
        half = strike_limit // 2
        lo = max(0, mid_idx - half)
        hi = min(len(strikes), mid_idx + half + 1)
        keep = set(strikes[lo:hi])
        calls = calls[calls["strike"].astype(float).isin(keep)]
        puts  = puts[puts["strike"].astype(float).isin(keep)]

    # map by strike
    c_map = {}
    for _, r in calls.iterrows():
        k = float(r["strike"])
        c_map[k] = {
            "call_oi": _to_int(r.get("openInterest"), 0),
            "call_vol": _to_int(r.get("volume"), 0),
        }

    p_map = {}
    for _, r in puts.iterrows():
        k = float(r["strike"])
        p_map[k] = {
            "put_oi": _to_int(r.get("openInterest"), 0),
            "put_vol": _to_int(r.get("volume"), 0),
        }

    all_strikes = sorted(set(c_map.keys()) | set(p_map.keys()))
    by_strike = []
    for k in all_strikes:
        c = c_map.get(k, {})
        p = p_map.get(k, {})
        by_strike.append({
            "strike": k,
            "call_oi": int(c.get("call_oi", 0)),
            "put_oi": int(p.get("put_oi", 0)),
            "call_vol": int(c.get("call_vol", 0)),
            "put_vol": int(p.get("put_vol", 0)),
        })

    call_oi = sum(x["call_oi"] for x in by_strike)
    put_oi  = sum(x["put_oi"] for x in by_strike)
    call_vol = sum(x["call_vol"] for x in by_strike)
    put_vol  = sum(x["put_vol"] for x in by_strike)

    # If OI is basically missing, treat PCR(OI) as unavailable
    oi_missing = (call_oi + put_oi) == 0

    pcr_oi = None
    if not oi_missing and call_oi > 0:
        pcr_oi = (put_oi / call_oi)

    pcr_vol = (put_vol / call_vol) if call_vol > 0 else None

    totals = {
        "call_oi": int(call_oi),
        "put_oi": int(put_oi),
        "call_vol": int(call_vol),
        "put_vol": int(put_vol),
        "pcr_oi": None if pcr_oi is None else float(pcr_oi),
        "pcr_vol": None if pcr_vol is None else float(pcr_vol),
        "oi_missing": int(oi_missing),
    }

    return {"by_strike": by_strike, "totals": totals}


def score_expiry(
    ticker: str,
    t: yf.Ticker,
    spot: float,
    exp_str: str,
    width: int,
) -> dict:
    """
    Score a single expiry based on:
    pct_two_sided, pct_any_activity, median_spread, oi_strength
    Returns:
      {"expiry","days","score","metrics","reason"}
    """
    try:
        ch = cached_option_chain(ticker, exp_str)
        c = ch.calls
        p = ch.puts
        if c is None or c.empty or p is None or p.empty:
            return {"expiry": exp_str, "days": _days_to_exp(exp_str), "score": -1.0, "reason": ["no chain data"], "metrics": {}}
    except Exception:
        return {"expiry": exp_str, "days": _days_to_exp(exp_str), "score": -1.0, "reason": ["chain fetch failed"], "metrics": {}}

    c2 = c.copy()
    c2["abs_m"] = (c2["strike"] - spot).abs()
    atm = float(c2.sort_values("abs_m").iloc[0]["strike"])

    strikes = sorted(set(c["strike"].tolist()) | set(p["strike"].tolist()))
    idx = min(range(len(strikes)), key=lambda i: abs(strikes[i] - atm))
    lo = max(0, idx - min(width, 10))
    hi = min(len(strikes), idx + min(width, 10) + 1)
    keep = set(strikes[lo:hi])

    c_w = c[c["strike"].isin(keep)]
    p_w = p[p["strike"].isin(keep)]

    rows = []
    for df in [c_w, p_w]:
        for _, row in df.iterrows():
            bid2 = 0.0 if pd.isna(row.get("bid")) else float(row.get("bid"))
            ask2 = 0.0 if pd.isna(row.get("ask")) else float(row.get("ask"))
            lastp2 = 0.0 if pd.isna(row.get("lastPrice")) else float(row.get("lastPrice"))
            oi = 0 if pd.isna(row.get("openInterest")) else int(row.get("openInterest"))
            vol = 0 if pd.isna(row.get("volume")) else int(row.get("volume"))

            has_two = (bid2 > 0 and ask2 > 0)
            has_any = has_two or (lastp2 > 0) or (oi > 0) or (vol > 0)

            spread_pct = None
            if has_two:
                mid2 = (bid2 + ask2) / 2.0
                if mid2 > 0:
                    spread_pct = (ask2 - bid2) / mid2

            rows.append({"has_any": has_any, "has_two": has_two, "spread_pct": spread_pct, "oi": oi, "vol": vol})

    total = len(rows) if rows else 1
    pct_any = sum(1 for x in rows if x["has_any"]) / total
    pct_two = sum(1 for x in rows if x["has_two"]) / total

    spreads = [x["spread_pct"] for x in rows if x["spread_pct"] is not None]
    med_spread = float(np.median(spreads)) if spreads else None

    oi_total = float(sum(x["oi"] for x in rows)) if rows else 0.0
    vol_total = float(sum(x["vol"] for x in rows)) if rows else 0.0

    metrics = {
        "pct_two_sided": float(pct_two),
        "pct_any_activity": float(pct_any),
        "median_spread": None if med_spread is None else float(med_spread),
        "oi_total": float(oi_total),
        "vol_total": float(vol_total),
    }

    reason = [
        f"pct_two_sided={pct_two:.2f}",
        f"pct_any_activity={pct_any:.2f}",
        f"median_spread={med_spread}",
        f"oi_total={oi_total}",
        f"vol_total={vol_total}",
    ]

    # IMPORTANT: we do NOT finalize score here anymore (needs cross-expiry normalization)
    return {
        "expiry": exp_str,
        "days": _days_to_exp(exp_str),
        "score": None,          # filled later
        "metrics": metrics,
        "reason": reason,
    }



def auto_pick_expiry(
    ticker: str,
    t: yf.Ticker,
    spot: float,
    horizon: str,
    width: int,
    hold_days: int = None,
) -> dict:
    """
    Auto-select best expiry based on liquidity score.
    
    If hold_days is provided, filters expiries to be >= hold_days.
    Otherwise uses horizon ranges (backward compatibility).
    """
    
    expiries = list(t.options or [])
    
    # Build candidates with days to expiration
    cand = [(e, _days_to_exp(e)) for e in expiries]
    
    # Initialize min_d and max_d (CRITICAL: needed for return statement)
    min_d = None
    max_d = None
    
    # Filter based on hold_days OR horizon
    if hold_days is not None and hold_days > 0:
        # NEW LOGIC: Use hold_days directly
        # Select expiries that are >= hold_days
        print(f"🎯 Auto-selecting expiry: hold_days = {hold_days}")
        cand = [(e, d) for (e, d) in cand if d >= hold_days]
        
        if not cand:
            # If no expiries >= hold_days, take the longest available
            print(f"⚠️ No expiries >= {hold_days} days, using longest available")
            cand = [(e, _days_to_exp(e)) for e in expiries]
            if cand:
                cand = [max(cand, key=lambda x: x[1])]  # Pick longest
        
        # Set min_d and max_d for return statement
        min_d = hold_days
        max_d = max([d for (e, d) in cand], default=hold_days) if cand else hold_days
    else:
        # OLD LOGIC: Use horizon ranges (backward compatibility)
        if horizon not in HORIZONS:
            raise HTTPException(status_code=400, detail="horizon must be one of: short, swing, long")
        
        min_d, max_d = HORIZONS[horizon]
        print(f"🎯 Auto-selecting expiry: horizon = {horizon} ({min_d}-{max_d} days)")
        cand = [(e, d) for (e, d) in cand if min_d <= d <= max_d]
    
    if not cand:
        raise HTTPException(status_code=404, detail=f"No suitable expiries found")
    
    print(f"✅ Found {len(cand)} candidate expiries")
    
    # Score all candidates
    scored = [score_expiry(ticker, t, spot, e, width) for (e, _) in cand]

    # Remove failures
    scored = [x for x in scored if isinstance(x.get("metrics"), dict)]
    if not scored:
        raise HTTPException(status_code=404, detail="Could not score any expiries (Yahoo data missing)")

    # ---- normalization denominators (per ticker, per run) ----
    max_oi = max((x["metrics"].get("oi_total", 0.0) for x in scored), default=0.0)
    max_vol = max((x["metrics"].get("vol_total", 0.0) for x in scored), default=0.0)

    # avoid division by zero
    max_oi = max(max_oi, 1.0)
    max_vol = max(max_vol, 1.0)

    # ---- compute final score with:
    # (C) replace oi_strength -> oi_norm + vol_norm
    # (A) hard gate cap if pct_two_sided < 0.10
    # (B) multiply by quote quality multiplier
    for x in scored:
        m = x["metrics"]

        pct_two = float(m.get("pct_two_sided", 0.0) or 0.0)
        pct_any = float(m.get("pct_any_activity", 0.0) or 0.0)
        med_spread = m.get("median_spread")
        med_spread = float(med_spread) if med_spread is not None else 0.5  # fallback

        oi_norm = float(m.get("oi_total", 0.0) or 0.0) / max_oi
        vol_norm = float(m.get("vol_total", 0.0) or 0.0) / max_vol

        # Base score (0..1-ish)
        base = (
            0.45 * pct_two +
            0.20 * pct_any +
            0.15 * oi_norm +
            0.10 * vol_norm +
            0.10 * (1.0 - med_spread)
        )

        # (A) Hard gate: if quote-poor, cap the score
        gate_capped = 0
        if pct_two < 0.10:
            base = min(base, 0.25)
            gate_capped = 1

        # (B) Quote-quality multiplier (smooth, not brutal)
        # range: 0.50 .. 1.00
        quote_mult = 0.5 + 0.5 * pct_two

        final = base * quote_mult

        # store extras for display
        m["oi_norm"] = float(oi_norm)
        m["vol_norm"] = float(vol_norm)
        m["quote_quality_mult"] = float(quote_mult)
        m["quote_gate_capped"] = int(gate_capped)

        x["score"] = float(final)

    def _liq_label(s: float) -> tuple[str, str]:
        # (grade, label)
        if s >= 0.70:
            return ("A", "Excellent liquidity")
        if s >= 0.45:
            return ("B", "Tradable")
        return ("C", "Quote-poor / caution")

    scored.sort(key=lambda x: x["score"], reverse=True)

    # build top3 from the sorted list (guarantees consistency)
    def _decorate_row(x: dict) -> dict:
        s = float(x.get("score") or 0.0)
        g, lbl = _liq_label(s)
        m = x.get("metrics") or {}
        return {
            "expiry": x.get("expiry"),
            "days": x.get("days"),
            "score": s,
            "liq_grade": g,
            "liq_label": lbl,
            "metrics": m,
        }

    top3_pretty = [_decorate_row(x) for x in scored[:3]]

    best = scored[0]
    best_score = float(best.get("score") or 0.0)
    best_grade, best_label = _liq_label(best_score)

    return {
        "suggested_expiry": best["expiry"],
        "days": best["days"],
        "score": best_score,
        "liq_grade": best_grade,
        "liq_label": best_label,
        "metrics": best.get("metrics"),
        "top3": top3_pretty,
        "min_days": min_d,  # Now always defined!
        "max_days": max_d,  # Now always defined!
    }




# =========================
# Debug routes
# =========================

@app.get("/ping")
def ping():
    return {"ok": True}

@app.get("/cache_stats")
def cache_stats():
    return {
        "chain": {"hits": CHAIN_CACHE.hits, "misses": CHAIN_CACHE.misses, "size": len(CHAIN_CACHE._store)},
        "earn": {"hits": EARNINGS_CACHE.hits, "misses": EARNINGS_CACHE.misses, "size": len(EARNINGS_CACHE._store)},
    }

@app.get("/hello", response_class=HTMLResponse)
def hello():
    return HTMLResponse("<h1>Hello</h1><p>Server is running.</p>")

@app.get("/routes", response_class=HTMLResponse)
def routes_list():
    paths = [r.path for r in app.routes]
    html = "<h1>Routes</h1><ul>" + "".join([f"<li>{p}</li>" for p in paths]) + "</ul>"
    return HTMLResponse(html)


# =========================
# Web pages
# =========================

@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request, "clusters": CLUSTERS})

@app.get("/macro", response_class=HTMLResponse)
def macro_page(request: Request):
    report = get_macro_report(ttl_seconds=300)
    ctx = macro_report_to_dict(report)
    ctx["request"] = request
    return templates.TemplateResponse("macro.html", ctx)

@app.get("/semis", response_class=HTMLResponse)
def semis_page(request: Request, refresh: int = 0):
    universe = load_semis_universe(force_refresh=bool(refresh))
    return templates.TemplateResponse("semis.html", {"request": request, "universe": universe})


# =========================
# HTML report (POST)
# =========================


@app.post("/report", response_class=HTMLResponse)
def report(
    request: Request,
    ticker: str = Form(...),
    cluster: str = Form(""),
    budget: float = Form(...),
    max_loss: float = Form(...),
    view: str = Form(...),
    hold_days: int = Form(...),
    planned_hold_days: int = Form(0),
    analysis_mode: str = Form("options"),
    opt_type: str = Form("call"),
    expiry: str = Form(""),
    strike: float = Form(0.0),
    bid: float = Form(0.0),
    ask: float = Form(0.0),
    r: float = Form(0.04),
    sigma_choice: str = Form("HV20"),
    max_spread_pct: float = Form(0.10),
    auto_expiry: int = Form(0),
    width: int = Form(10),
    horizon: str = Form("swing"),  # short/swing/long
    overlay_bull: str = Form("", description="User overlay bull info"),
    overlay_bear: str = Form("", description="User overlay bear info"),
    overlay_strength: int = Form(60, description="Overlay strength 0-100"),
    overlay_horizon: str = Form("1-3 months", description="Overlay horizon bucket"),
    raw: int = Query(0, description="1 = raw keys; 0 = annotated keys"),
    debug_ai: int = Query(0, description="Set to 1 to enable AI debug panel (localhost only)"),
):
    price_guidance_engine = None
    show_price_guidance = False
     # --- always-defined option outputs (avoid UnboundLocalError) ---
    top3_contracts = []
    chain_data = {}
    ticker = ticker.strip().upper()
    cluster = (cluster or "").strip()
    peers = CLUSTERS.get(cluster, [])
    opt_type = opt_type.strip().lower()
    view = view.strip().lower()
    analysis_mode = (analysis_mode or "options").strip().lower()
    if analysis_mode not in ("stock", "options"):
        analysis_mode = "options"

    # ==============================
    # Insider overlay normalization
    # ==============================
    overlay = {
        "present": bool((overlay_bull or "").strip() or (overlay_bear or "").strip()),
        "bull": (overlay_bull or "").strip(),
        "bear": (overlay_bear or "").strip(),
        "strength": max(0, min(int(overlay_strength or 0), 100)),
        "horizon": (overlay_horizon or "1-3 months").strip(),
    }

    # Resolve cluster/peers if user didn't pass cluster (safety)
    if not peers or not cluster:
        for cname, members in CLUSTERS.items():
            if ticker in members:
                if not cluster:
                    cluster = cname
                if not peers:
                    peers = members
                break

    # Phase 8: peers snapshot (cached)
    peer_snapshot = PEER_CACHE.get_or_set(
        f"peer_snapshot:{ticker}",
        lambda: build_peer_snapshot(ticker, peers, cluster=cluster),
        ttl_sec=30 * 60,
    )

    # Phase 13A: alpha vs peers + SOX proxy (cached)
    alpha_snapshot = ALPHA_CACHE.get_or_set(
        f"alpha:{ticker}:{cluster}",
        lambda: compute_alpha_snapshot(ticker, peers, sox_proxy="SOXX", window=60, period="6mo"),
        ttl_sec=30 * 60,
    )

    alpha_regime = classify_alpha_regime(alpha_snapshot)


    t = yf.Ticker(ticker)
    hist = t.history(period="1y")

    auto_info = None  # must exist for early returns

    # guardrail: no history
    if hist is None or hist.empty or hist["Close"].dropna().empty:
        return templates.TemplateResponse(
            "report.html",
            {
                "request": request,
                "error": f"No data found for ticker {ticker}.",
                "ticker": ticker,
                "cluster": cluster,
                "peers": peers,
                "horizon": horizon,
                "width": width,
                "auto_expiry": bool(auto_expiry),
                "auto_info": auto_info,
                "iv_term_json": None,
                "iv_skew_json": None,
                "atm_iv_selected": None,
                "implied_move_pct": None,
                "implied_move_abs": None,
                "implied_low": None,
                "implied_high": None,
                "vol_context": None,
                "earnings_info": None,
                "auto_curve_json": "[]",
            },
        )

    S = float(hist["Close"].dropna().iloc[-1])
    # Phase 13: ATR execution inputs
    atr14 = atr(hist, 14)
    atr20 = atr(hist, 20)

    analytics = {}

    # =========================
    # Phase 13: alpha snapshot + regime (cached)
    # =========================
    alpha_snapshot = ALPHA_CACHE.get_or_set(
        f"alpha:{ticker}",
        lambda: compute_alpha_snapshot(ticker, peers),
        ttl_sec=30 * 60,
    )
    alpha_regime = classify_alpha_regime(alpha_snapshot) if alpha_snapshot else None

    # =========================
    # Phase 8: Peer snapshot
    # =========================

    if not peers or not cluster:
        for cname, members in CLUSTERS.items():
            if ticker in members:
                if not cluster:
                    cluster = cname
                if not peers:
                    peers = members
                break

    peer_snapshot = PEER_CACHE.get_or_set(
        f"peer_snapshot:{ticker}",
        lambda: build_peer_snapshot(ticker, peers, cluster=cluster),
        ttl_sec=30 * 60,
    )

    # =========================
    # Deterministic "Model Target" from peer multiple bands
    # (works for BOTH stock + options mode)
    # =========================
    try:
        model_target = None
        model_target_band = None

        focal = (peer_snapshot or {}).get("focal", {}) or {}
        bands = (peer_snapshot or {}).get("bands", {}) or {}

        # Prefer forward PE if available, else trailing PE
        focal_pe = focal.get("forward_pe") or focal.get("trailing_pe")
        peer_p50 = (bands.get("forward_pe") or {}).get("median") or (bands.get("trailing_pe") or {}).get("median")
        peer_p25 = (bands.get("forward_pe") or {}).get("p25") or (bands.get("trailing_pe") or {}).get("p25")
        peer_p75 = (bands.get("forward_pe") or {}).get("p75") or (bands.get("trailing_pe") or {}).get("p75")

        if focal_pe and peer_p50 and float(focal_pe) > 0:
            # “What price would make the focal trade at peer median multiple?”
            model_target = float(S) * (float(peer_p50) / float(focal_pe))

            # Provide a deterministic band too (p25..p75)
            if peer_p25 and peer_p75:
                model_target_band = {
                    "low": float(S) * (float(peer_p25) / float(focal_pe)),
                    "base": float(model_target),
                    "high": float(S) * (float(peer_p75) / float(focal_pe)),
                }

        peer_snapshot["model_target"] = {
            "value": float(model_target) if model_target is not None else None,
            "band": model_target_band,
            "basis": "forward_pe" if focal.get("forward_pe") else "trailing_pe",
            "peer_p50": float(peer_p50) if peer_p50 else None,
            "focal_pe": float(focal_pe) if focal_pe else None,
        }
    except Exception as e:
        print(f"model_target compute failed: {e}")
        try:
            peer_snapshot["model_target"] = {"value": None, "band": None}
        except Exception:
            pass

    # =========================
    # Earnings Track Record (SHARED BY BOTH MODES)
    # =========================

    earnings_track = None
    try:
        earnings_track = build_earnings_track_record(
            ticker=ticker,
            peers=peers,
            hist=hist,
            lookback_quarters=4
        )
        print(f"✅ Earnings track built: {earnings_track['summary']['total_quarters']} quarters")
    except Exception as e:
        print(f"❌ Earnings track failed: {e}")
        earnings_track = {
            "quarters": [],
            "summary": {
                "total_quarters": 0,
                "beat_rate": 0,
                "avg_reaction": 0,
            },
            "error": str(e)
        }

    # Phase 13A: alpha vs peers + SOX proxy (cached)
    alpha_snapshot = ALPHA_CACHE.get_or_set(
        f"alpha:{ticker}:{cluster}",
        lambda: compute_alpha_snapshot(ticker, peers, sox_proxy="SOXX", window=60, period="6mo"),
        ttl_sec=30 * 60,
    )
    alpha_regime = classify_alpha_regime(alpha_snapshot)

    # =========================
    # Phase A: DCF (shared across modes)
    # =========================
    dcf_result = None
    try:
        dcf_result = build_dcf(ticker, spot=S, rf=0.04, sector_bucket=None, view=view)
        print(f"✅ DCF executed: intrinsic = ${dcf_result.get('intrinsic', 'N/A')}")
    except Exception as e:
        print(f"❌ DCF FAILED: {str(e)}")
        import traceback
        traceback.print_exc()
        dcf_result = None

    # =========================
    # Phase 6: STOCK mode (no options chain)
    # =========================
    # =========================
    # Earnings Info (SHARED BY BOTH MODES)
    # =========================
    # CRITICAL FIX: Initialize earnings_info BEFORE mode branching
    print(f"🔍 Fetching earnings info for {ticker}...")
    
    earnings_info = None
    try:
        earnings_info = EARNINGS_CACHE.get_or_set(
            f"earn:{ticker}",
            lambda: get_earnings_info(t, ticker),
            ttl_sec=6 * 3600,
        )
        print(f"✅ Earnings info loaded")
    except Exception as e:
        print(f"❌ Earnings info fetch failed: {e}")
        earnings_info = None
    
    # Earnings fallback
    try:
        if not earnings_info or not any(earnings_info.values()):
            try:
                cal = t.calendar if hasattr(t, "calendar") else {}
                edates = None
                try:
                    edates = t.get_earnings_dates()
                except Exception:
                    edates = None
                
                fallback = {}
                if isinstance(cal, dict) and cal:
                    fallback["calendar"] = str(cal)
                if edates:
                    fallback["earnings_dates_raw"] = str(edates)
                if fallback:
                    earnings_info = earnings_info or {}
                    earnings_info.update({"__note__": "fallback used", "fallback": fallback})
                    print(f"📊 Earnings fallback used for {ticker}")
            except Exception as e:
                print(f"⚠️ Earnings fallback error: {e}")
    except Exception:
        pass
    
    # Ensure always a dict
    if earnings_info is None:
        earnings_info = {"__note__": "earnings unavailable"}
    
    # Refresh if empty
    try:
        if not (earnings_info.get('earnings_date_us') or earnings_info.get('earnings_date_utc')):
            fresh = get_earnings_info(t, ticker)
            if fresh and (fresh.get('earnings_date_us') or fresh.get('earnings_date_utc')):
                earnings_info = fresh
                EARNINGS_CACHE.set(f"earn:{ticker}", earnings_info, ttl_sec=2 * 3600)
                print(f"🔄 Earnings cache refreshed")
    except Exception as e:
        print(f"⚠️ Earnings refresh skipped: {e}")
    
    # P0-4 FIX: Determine if earnings is past or future
    if earnings_info and earnings_info.get('earnings_date_us'):
        try:
            from datetime import datetime
            earnings_dt = earnings_info.get('earnings_date_us')
            
            # Convert to datetime if needed
            if isinstance(earnings_dt, str):
                # Try parsing common formats
                try:
                    earnings_dt = datetime.fromisoformat(earnings_dt.replace('Z', '+00:00'))
                except:
                    try:
                        earnings_dt = datetime.strptime(earnings_dt, '%Y-%m-%d %H:%M:%S')
                    except:
                        earnings_dt = datetime.strptime(earnings_dt, '%Y-%m-%d')
            
            # Calculate days to earnings
            days_to_earnings = (earnings_dt - datetime.now()).days
            earnings_info['days_to_event'] = days_to_earnings
            earnings_info['is_past'] = days_to_earnings < 0
            
            # Determine if should display as future event
            if days_to_earnings < 0:
                print(f"  Earnings is in the past ({abs(days_to_earnings)} days ago), marking as historical")
                earnings_info['display_as_future'] = False
            else:
                print(f"  Earnings in {days_to_earnings} days, displaying as future event")
                earnings_info['display_as_future'] = True
        except Exception as e:
            print(f"  Warning: Could not process earnings date: {e}")
            earnings_info['display_as_future'] = True  # Show by default if can't determine
            earnings_info['is_past'] = False
    elif earnings_info:
        earnings_info['display_as_future'] = False  # No date, don't show as future
        earnings_info['is_past'] = True
    
    macro_snapshot = None  # set in both stock + options modes
    if analysis_mode == "stock":
        # planned hold horizon (separate from expiry DTE)
        ph = int(planned_hold_days) if planned_hold_days and planned_hold_days > 0 else int(hold_days)
        planned_days = max(1, ph)

        # realized vol (still useful in stock mode)
        hv20 = realized_vol(hist["Close"], 20)
        hv60 = realized_vol(hist["Close"], 60)

        if sigma_choice == "HV20":
            sigma_forecast = hv20
        elif sigma_choice == "HV60":
            sigma_forecast = hv60
        else:
            sigma_forecast = hv20

        # macro snapshot (still included)
        macro_snapshot = get_macro_snapshot()

        # earnings_info now initialized before mode branching



        # Phase 13: Anchored VWAP from earnings date (best-effort)
        avwap = None
        anchor = (earnings_info or {}).get("earnings_date_us") or (earnings_info or {}).get("earnings_date_utc")
        if anchor:
            avwap = anchored_vwap(hist, anchor)

        earnings_move_stats = earnings_realized_move_stats(hist, earnings_info, lookback=6)

        # News | Company Snapshots
        company = COMPANY_CACHE.get_or_set(
            f"company:{ticker}",
            lambda: get_company_snapshot(t),
            ttl_sec=12 * 3600,
        )

        # ---- deterministic company brief (no AI) ----
        summary = (company.get("summary") or "").strip()

        brief = ""
        if summary:
            # Prefer first 2 sentences, fallback to 260 chars
            parts = [p.strip() for p in summary.replace("\n", " ").split(".") if p.strip()]
            if len(parts) >= 2:
                brief = parts[0] + ". " + parts[1] + "."
            elif len(parts) == 1:
                brief = parts[0] + "."
            else:
                brief = summary[:260].rstrip() + ("…" if len(summary) > 260 else "")
        else:
            brief = ""

        key_points = []
        if company.get("sector"):
            key_points.append(f"Sector: {company.get('sector')}")
        if company.get("industry"):
            key_points.append(f"Industry: {company.get('industry')}")
        if company.get("country"):
            key_points.append(f"Country: {company.get('country')}")
        if company.get("website"):
            key_points.append(f"Website: {company.get('website')}")

        company["brief"] = brief
        company["key_points"] = key_points

        # ---- Phase B: Company chain (business model / suppliers / customers) ----
        try:
            sector_bucket = sector_bucket_for(ticker)

            company_chain = build_company_chain(
                ticker,
                company,
                cluster=cluster,
                sector_bucket=sector_bucket,
            )
        except Exception as e:
            company_chain = {"source_note": f"company_chain error: {e}"}

        company["company_chain"] = company_chain

        # Optional: also alias it so report.html's cb fallback works consistently
        company["company_brief"] = company_chain


        headlines = NEWS_CACHE.get_or_set(
            f"news:{ticker}",
            lambda: get_latest_headlines(t, max_items=8),
            ttl_sec=30 * 60,
        )

        # ============================================================
        # P0-4 FIX: STOCK OPTIONS DIAGNOSTICS
        # Compute options-derived metrics even in stock mode if chain available
        # This prevents "missing modules" penalty in confidence engine
        # ============================================================
        stock_options_diagnostics = None
        
        try:
            from datetime import datetime, timedelta
            print("📊 Computing options-derived diagnostics for stock mode...")
            
            # P0-4 FIX: Pick a REAL listed expiry closest to planned_days (avoid chain miss)
            target_dte = planned_days if 'planned_days' in locals() and planned_days else 30
            expiry_list_stock = []
            try:
                expiry_list_stock = list(getattr(t, "options", []) or [])
            except Exception:
                expiry_list_stock = []

            def _dte_stock(exp_str: str):
                try:
                    ed = datetime.strptime(exp_str, "%Y-%m-%d").date()
                    return max(0, (ed - datetime.now().date()).days)
                except Exception:
                    return None

            listed_stock = [(e, _dte_stock(e)) for e in expiry_list_stock]
            listed_stock = [(e, d) for (e, d) in listed_stock if d is not None]
            if listed_stock:
                best_expiry_stock, _ = min(listed_stock, key=lambda x: abs(x[1] - target_dte))
            else:
                best_expiry_stock = (datetime.now() + timedelta(days=30)).strftime("%Y-%m-%d")  # last resort
            
            # Attempt to load chain with the real listed expiry
            chain_available = False
            ch_stock = None
            try:
                ch_stock = cached_option_chain(ticker, best_expiry_stock)
                if ch_stock and hasattr(ch_stock, 'calls') and not ch_stock.calls.empty:
                    chain_available = True
                    print(f"  ✅ Options chain available for {best_expiry_stock}")
            except Exception as e:
                print(f"  ⚠️ Could not load chain: {e}")
                chain_available = False
            
            if chain_available and ch_stock:
                # Run auto_pick_expiry for liquidity scoring
                auto_info_stock = None
                try:
                    auto_info_stock = auto_pick_expiry(
                        ticker, t, S, 
                        horizon=30,  # default 30d for stock
                        width=0.15
                    )
                    print(f"  ✅ Auto-expiry diagnostics: Grade {auto_info_stock.get('liq_grade', 'N/A')}")
                except Exception as e:
                    print(f"  ⚠️ Auto-expiry failed: {e}")
                
                # Compute IV rank
                iv_rank_stock = None
                try:
                    iv_rank_result = compute_iv_rank(ticker, t)
                    if iv_rank_result:
                        iv_rank_stock = iv_rank_result.get('iv_rank', 0.5)
                        print(f"  ✅ IV Rank: {iv_rank_stock:.2%}")
                except Exception as e:
                    print(f"  ⚠️ IV rank failed: {e}")
                
                # Compute put/call metrics (inline - no separate module needed)
                put_call_metrics = None
                try:
                    # Simple put/call ratio computed directly from option chain
                    if hasattr(ch_stock, 'puts') and hasattr(ch_stock, 'calls'):
                        # Get total open interest for puts and calls
                        total_put_oi = 0
                        total_call_oi = 0
                        total_put_vol = 0
                        total_call_vol = 0
                        
                        if 'openInterest' in ch_stock.puts.columns:
                            total_put_oi = ch_stock.puts['openInterest'].sum()
                        if 'openInterest' in ch_stock.calls.columns:
                            total_call_oi = ch_stock.calls['openInterest'].sum()
                        if 'volume' in ch_stock.puts.columns:
                            total_put_vol = ch_stock.puts['volume'].sum()
                        if 'volume' in ch_stock.calls.columns:
                            total_call_vol = ch_stock.calls['volume'].sum()
                        
                        # Compute ratios
                        pcr_oi = total_put_oi / total_call_oi if total_call_oi > 0 else None
                        pcr_vol = total_put_vol / total_call_vol if total_call_vol > 0 else None
                        
                        put_call_metrics = {
                            'pcr_oi': pcr_oi,
                            'pcr_vol': pcr_vol,
                            'total_put_oi': total_put_oi,
                            'total_call_oi': total_call_oi,
                        }
                        
                        if pcr_oi is not None:
                            print(f"  ✅ Put/Call ratio (OI): {pcr_oi:.2f}")
                        else:
                            print(f"  ⚠️ Put/Call ratio: Unable to compute (no open interest data)")
                    else:
                        print(f"  ⚠️ Put/call metrics: Chain missing puts or calls")
                        
                except Exception as e:
                    print(f"  ⚠️ Put/call metrics failed: {e}")
                    put_call_metrics = None
                
                # Compute ATM IV and implied move vs forecast
                atm_iv_stock = None
                implied_vs_forecast = None
                try:
                    # Get ATM IV
                    atm_calls = ch_stock.calls[(ch_stock.calls['strike'] >= S * 0.95) & 
                                                 (ch_stock.calls['strike'] <= S * 1.05)]
                    if not atm_calls.empty and 'impliedVolatility' in atm_calls.columns:
                        atm_iv_stock = atm_calls['impliedVolatility'].median()
                        
                        # Compute implied vs forecast
                        if atm_iv_stock and hv20:
                            implied_vs_forecast = atm_iv_stock / hv20
                            print(f"  ✅ ATM IV: {atm_iv_stock:.2%}, IV/HV: {implied_vs_forecast:.2f}")
                except Exception as e:
                    print(f"  ⚠️ ATM IV failed: {e}")
                
                stock_options_diagnostics = {
                    "available": True,
                    "auto_expiry": auto_info_stock,
                    "iv_rank": iv_rank_stock,
                    "put_call": put_call_metrics,
                    "atm_iv": atm_iv_stock,
                    "hv20": hv20,
                    "implied_vs_forecast": implied_vs_forecast,
                    "chain_loaded": True,
                }
                
                print("  ✅ Options-derived diagnostics complete")
            else:
                stock_options_diagnostics = {
                    "available": False,
                    "reason": "Options chain not available",
                    "chain_loaded": False,
                }
                print("  ⚠️ Options chain not available for diagnostics")
                
        except Exception as e:
            print(f"  ❌ Stock options diagnostics failed: {e}")
            import traceback
            traceback.print_exc()
            stock_options_diagnostics = {
                "available": False,
                "reason": f"Error: {e}",
                "chain_loaded": False,
            }

        # minimal conclusion context (stock mode - fill from diagnostics if available)
        # P0-4 FIX: Plumb stock_options_diagnostics into conclusion_ctx
        auto_info_stock_ctx = None
        pcr_stock_ctx = {}
        atm_iv_stock_ctx = None
        iv_rank_stock_ctx = None
        implied_vs_forecast_ctx = None
        if stock_options_diagnostics and stock_options_diagnostics.get("available"):
            auto_info_stock_ctx = stock_options_diagnostics.get("auto_expiry")
            pcr_stock_ctx = stock_options_diagnostics.get("put_call") or {}
            atm_iv_stock_ctx = stock_options_diagnostics.get("atm_iv")
            iv_rank_stock_ctx = stock_options_diagnostics.get("iv_rank")
            implied_vs_forecast_ctx = stock_options_diagnostics.get("implied_vs_forecast")

        conclusion_ctx = {
            "view": view,

            # In stock mode, do NOT force liquidity gating to kill the verdict
            "liq_ok": True,
            "spread_pct": None,
            "gap_pct": None,
            "label": "N/A",

            "hv20": hv20,
            "hv60": hv60,

            "planned_days": planned_days,
            "days_to_exp": None,

            "implied_move_pct": None,
            "implied_move_pct_expiry": None,

            # P0-4 FIX: use diagnostics values, not None
            "auto_info": auto_info_stock_ctx,
            "macro_snapshot": macro_snapshot,
            "pcr": pcr_stock_ctx,
            "atm_iv_selected": atm_iv_stock_ctx,
            "iv_rank": {"iv_rank": iv_rank_stock_ctx} if iv_rank_stock_ctx is not None else None,

            "earnings_info": earnings_info,
            "earnings_move_stats": earnings_move_stats,
        }

        # Surface implied_vs_forecast label if available
        if isinstance(implied_vs_forecast_ctx, dict):
            conclusion_ctx["gap_pct"] = implied_vs_forecast_ctx.get("gap_pct")
            conclusion_ctx["label"] = implied_vs_forecast_ctx.get("label", "N/A")
        elif isinstance(implied_vs_forecast_ctx, (int, float)):
            conclusion_ctx["label"] = f"IV/HV ratio: {implied_vs_forecast_ctx:.2f}"

        conclusion = build_conclusion(conclusion_ctx)
        
        # =========================
        # Phase D: Option A Weighted Confidence (stock mode)
        # =========================
        # =========================
        # Adaptive DCF Weighting
        # =========================
        adaptive_dcf = calculate_adaptive_dcf_weight(
            dcf_intrinsic=dcf_result.get('intrinsic') if dcf_result else None,
            spot=S,
            view=view,
        )

        # Format DCF display context
        dcf_display = format_dcf_display_context(
            dcf_result=dcf_result,
            spot=S,
            view=view,
            adaptive_dcf=adaptive_dcf,
            company_snapshot=company_chain,
        )

        # Phase D: Option A Weighted Confidence (stock mode)
        # Try Gemini AI for analyst commentary / price guidance (does NOT set the official confidence score)
        ai = None
        try:
            from data.gemini_confidence import compute_confidence_with_ai

            ai = compute_confidence_with_ai(
                ticker=ticker,
                user_stance=view if view else "neutral",
                spot_price=S,
                intrinsic_value=dcf_result.get('intrinsic') if dcf_result else S,
                macro_regime=macro_snapshot.get('regime_label', 'Neutral') if macro_snapshot else 'Neutral',
                earnings_data=earnings_track if earnings_track else {'quarters': []},
                valuation_data={
                    'pe_ratio': company.get('trailing_pe'),
                    'ps_ratio': company.get('price_to_sales'),
                    'profit_margin': company.get('profit_margin'),
                    'revenue_growth': company.get('revenue_growth'),
                    'eps_growth': company.get('eps_growth'),
                },
                company_info={
                    'name': company.get('name', ticker),
                    'sector': company.get('sector', 'Unknown'),
                    'industry': company.get('industry', 'Unknown'),
                    'description': company.get('summary', '')
                },
                macro_context=None,
                technical_data={
                    'atr14': atr14,
                    'atr20': atr20,
                    'anchored_vwap': avwap,
                    'exec_bands': exec_bands if 'exec_bands' in locals() else None,
                    'primary_entry': entry_zone_final if 'entry_zone_final' in locals() else None,
                    'spot_price': S,
                },
                alpha_data={
                    'alpha_snapshot': alpha_snapshot,
                    'alpha_regime': alpha_regime,
                },
                iv_data=None,  # Stock mode doesn't have IV
                peer_data={
                    'peers': peers,
                    'peer_snapshot': peer_snapshot,
                    'cluster': cluster,
                },
                extra_info=json.dumps(overlay),
            )
        except Exception as e:
            print(f"Gemini AI failed (stock mode): {e}")
            ai = {"available": False, "error": str(e)}

        # --- Qualitative Proxies (computed once before confidence) ---
        try:
            yf_info_for_proxy = getattr(yf.Ticker(ticker), 'info', None) or {}
        except Exception:
            yf_info_for_proxy = {}
        try:
            qualitative_proxy_result = compute_qualitative_proxies(
                ticker=ticker,
                mode="stock",
                hold_days=planned_days if 'planned_days' in locals() and planned_days > 0 else hold_days,
                hist_df=hist if 'hist' in locals() else None,
                sector_bucket=sector_bucket_for(ticker) if 'sector_bucket_for' in dir() else None,
                alpha_snapshot=alpha_snapshot,
                earnings_info=earnings_info,
                dcf_result=dcf_result,
                headlines=headlines if 'headlines' in locals() else None,
                yf_info=yf_info_for_proxy,
                spot=S,
            )
        except Exception as _qpe:
            print(f"Qualitative proxy error (stock): {_qpe}")
            qualitative_proxy_result = {"available": False, "score_01": 0.5}

        # ── Early Reverse DCF (stock mode) ────────────────────────────────────
        # Compute reverse DCF BEFORE confidence so its reasonableness score is
        # blended into S_dcf.  Mirrors the options-mode early reverse DCF block.
        stock_reverse_dcf_analysis = None
        _stock_reverse_reasonableness = None
        try:
            if dcf_result and isinstance(dcf_result, dict) and company:
                from data.reverse_dcf import ReverseDCF as _RDCF_STOCK
                _rdcf_stock = _RDCF_STOCK()
                _rev_growth_s = company.get("revenue_growth")
                try:
                    _rev_cagr_s = float(_rev_growth_s) if _rev_growth_s is not None else 0.08
                    _rev_cagr_s = max(-0.20, min(0.40, _rev_cagr_s))
                except Exception:
                    _rev_cagr_s = 0.08
                _fcf_s = company.get("free_cash_flow")
                _rev_s = company.get("revenue")
                try:
                    _fcf_margin_s = float(_fcf_s) / float(_rev_s) if (_fcf_s and _rev_s) else 0.10
                    _fcf_margin_s = max(-0.10, min(0.35, _fcf_margin_s))
                except Exception:
                    _fcf_margin_s = 0.10
                stock_reverse_dcf_analysis = _rdcf_stock.analyze(
                    current_price=S,
                    current_revenue=company.get("revenue", 30e9),
                    current_margin=company.get("profit_margin", 0.10),
                    current_fcf_margin=_fcf_margin_s,
                    shares_outstanding=company.get("shares_outstanding", 1.1e9),
                    dcf_intrinsic=dcf_result.get("intrinsic", S),
                    dcf_assumptions={
                        "revenue_cagr": _rev_cagr_s,
                        "terminal_growth": 0.025 if (company.get("sector") or "").lower().find("technology") >= 0 else 0.02,
                        "fcf_margin": _fcf_margin_s,
                    },
                    current_hbm_mix=0.15 if ticker == "MU" else None,
                    hbm_tam_growth=0.85 if ticker == "MU" else None,
                    beta=1.5,
                )
                _stock_reverse_reasonableness = stock_reverse_dcf_analysis.get("reasonableness_score")
                print(f"✅ [Stock] Reverse DCF: reasonableness={_stock_reverse_reasonableness}/10")
        except Exception as _sre:
            print(f"⚠️ [Stock] Reverse DCF failed: {_sre}")
            stock_reverse_dcf_analysis = None
            _stock_reverse_reasonableness = None
        # ─────────────────────────────────────────────────────────────────────

        # Official confidence score: deterministic / auditable (Option A)
        confidence = compute_confidence_option_a(
            spot=S,
            dcf_result=dcf_result,
            macro_snapshot=macro_snapshot,
            company_snapshot=company_chain,
            hv20=hv20,
            hv60=hv60,
            iv_rank=None,
            earnings_info=earnings_info,
            liquidity_metrics=None,
            alpha_snapshot=alpha_snapshot,
            mode="stock",
            # Adaptive DCF parameters
            adaptive_dcf_weight=adaptive_dcf.get('weight'),
            adaptive_dcf_score=adaptive_dcf.get('score'),
            # Qualitative proxy
            qualitative_proxy=qualitative_proxy_result,
            # Reverse DCF reasonableness: blended into S_dcf (55/45 formula)
            reverse_dcf_reasonableness=_stock_reverse_reasonableness,
        )

        # ==================================================================
        # STOCK MODE: Confidence Harmonization (blend with institutional engine)
        # ==================================================================
        from data.confidence_engine import ConfidenceEngine
        ce = ConfidenceEngine()

        inst = ce.compute_confidence(
            mode="stock",
            stock_options_diagnostics=stock_options_diagnostics if 'stock_options_diagnostics' in locals() else None,
            spread_pct=None,
            liquidity_grade=None,
            oi_total=None,
            vol_total=None,
            iv_rank=None,
            iv_hv_ratio=None,
            atm_iv=None,
            hv20=hv20,
            dcf_intrinsic=(dcf_result or {}).get("intrinsic"),
            spot_price=S,
            dcf_gap_pct=None,
            macro_regime=(macro_snapshot or {}).get("regime_label"),
            industry_cycle=None,
            atr_bands={"primary": (S-atr14, S+atr14)} if (atr14 and S) else None,
            vwap_anchor=avwap,
            support_levels=None,
        )

        # Save Option A dict BEFORE blend overwrites confidence variable
        option_a_dict = confidence if isinstance(confidence, dict) else {}

        # Handle confidence - it can be a dict or a number
        if isinstance(confidence, dict):
            base_total = int(confidence.get("total", confidence.get("total_confidence", 50)))
        else:
            base_total = int(confidence)
            
        inst_total = int(inst.get("total_confidence", 50))
        confidence = round(0.65 * base_total + 0.35 * inst_total)

        print(f"Stock Mode Confidence Blend: base={base_total}, inst={inst_total}, final={confidence}")

        # ==================================================================
        # ADVANCED OVERLAY → RISK PLAN ADJUSTMENTS (Stock Mode)
        # ==================================================================
        base_confidence = confidence
        risk_adj = {'overlay_used': False}
        
        if overlay.get('present'):
            base_metrics = {
                'base_confidence': base_confidence,
                'liquidity_gate_status': 'PASS',  # Stock mode typically no liquidity gate
                'reverse_dcf_reasonableness': 5.0,  # Usually not calculated in stock mode
                'iv_rank': 50.0,
                'hold_days': planned_days if planned_days > 0 else hold_days,
                'earnings_within_window': False,
            }
            risk_adj = overlay_to_risk_adjustments(overlay, base_metrics)
            adjusted_confidence = base_confidence + risk_adj['confidence_delta']
            
            if risk_adj['overlay_used']:
                print(f"📊 Risk Plan (Stock Mode):")
                print(f"   Size: {risk_adj['size_multiplier']:.2f}x")
                print(f"   Entry: {risk_adj['entry_aggressiveness']}")
                if risk_adj['require_hedge']:
                    print(f"   Hedge: {risk_adj['hedge_style']}")
                print(f"   Confidence: {base_confidence}% {risk_adj['confidence_delta']:+d} = {adjusted_confidence}%")
        else:
            adjusted_confidence = base_confidence
            risk_adj = {
                'size_multiplier': 1.0,
                'entry_aggressiveness': 'base',
                'stop_tightness': 'normal',
                'require_hedge': False,
                'hedge_style': None,
                'confidence_delta': 0,
                'notes': [],
                'overlay_used': False
            }
        
        # Hard caps (macro regime for stock mode)
        max_confidence_cap = 100
        cap_reasons = []
        
        if macro_snapshot and isinstance(macro_snapshot, dict):
            regime = macro_snapshot.get('regime_label', '').upper()
            if 'RISK_OFF' in regime or 'CRASH' in regime:
                max_confidence_cap = min(max_confidence_cap, 60)
                cap_reasons.append(f"Macro regime ({regime})")
        
        if adjusted_confidence > max_confidence_cap:
            print(f"⚠️ Hard cap: {adjusted_confidence}% → {max_confidence_cap}%")
            adjusted_confidence = max_confidence_cap
        
        # Apply overlay confidence delta (expert's simpler approach)
        hold_days_for_overlay = planned_days if planned_days > 0 else hold_days
        overlay_delta = overlay_confidence_delta(overlay, hold_days_for_overlay, cap=5)
        
        if overlay_delta != 0:
            print(f"📊 Overlay confidence delta: {overlay_delta:+d} points (stock mode)")
        
        # ── ConfidenceV3 canonical pipeline (stock mode) ──────────────────────
        # 1. Convert raw Option A dict → ConfidenceV3 object
        _v3_stock = option_a_to_v3(option_a_dict, mode="stock")
        # 2. Set overlay / penalty fields on the canonical object
        _v3_stock.overlay_delta_points = overlay_delta
        _v3_stock.missing_penalty_points = option_a_dict.get("missing_penalty", 0)
        # 3. Apply overlay cap to total
        _v3_stock.total_0_100 = max(0, min(100, option_a_dict.get("total", 50) + overlay_delta))
        # 4. Re-derive grade after overlay
        from data.confidence_schema import ConfidenceV3 as _CV3
        _v3_stock.grade = _CV3.grade_from_score(_v3_stock.total_0_100)
        # 5. Flatten back to template-safe dict (keeps report.html working unchanged)
        stock_confidence_dict = v3_to_template_confidence(_v3_stock)
        # 6. Preserve extra keys the template still uses
        stock_confidence_dict["base"] = option_a_dict.get("total", 50)
        stock_confidence_dict["overlay"] = overlay
        stock_confidence_dict["reasoning"] = option_a_dict.get("reasoning", {})
        # Preserve factor_meta — v3_to_template_confidence does not carry it through.
        # This is the authoritative per-factor status dict used by signals_used
        # and the Data Gaps section in report.html.
        stock_confidence_dict["factor_meta"] = option_a_dict.get("factor_meta", {})
        stock_confidence_dict["weights"]     = option_a_dict.get("weights", stock_confidence_dict.get("weights", {}))
        stock_confidence_dict["breakdown"]   = option_a_dict.get("breakdown", stock_confidence_dict.get("breakdown", {}))
        stock_confidence_dict["contrib"]     = option_a_dict.get("contrib", stock_confidence_dict.get("contrib", {}))
        # ────────────────────────────────────────────────────────────────────

        final_confidence = stock_confidence_dict["total"]

        # DCF weight display: read from the ACTUAL weights dict used in scoring
        _dcf_w = stock_confidence_dict.get("weights", {}).get("dcf", 0.0)
        dcf_weight_display_pct = round(float(_dcf_w) * 100, 1)

        # P0-4 FIX: Ensure headline conclusion reflects final capped confidence
        try:
            if isinstance(conclusion, dict):
                conclusion["confidence"] = final_confidence
        except Exception:
            pass

        ai_entry = ai_cons_entry = ai_overall_avg = ai_target_price = options_recos = None
        if isinstance(ai, dict):
            # Merge AI confidence data into stock_confidence_dict
            # NOTE: Do NOT overwrite breakdown/weights/contrib from AI - those are dummy zeros.
            # Option A values are already set in stock_confidence_dict.
            # Only extract price guidance and debug info from AI.
            if 'reasoning' in ai and not stock_confidence_dict.get('reasoning'):
                stock_confidence_dict['reasoning'] = ai['reasoning']
            if 'debug' in ai:
                stock_confidence_dict['debug'] = ai.get('debug', {})
            
            # Debug logging
            print(f"DEBUG STOCK MODE: ai keys = {list(ai.keys())}")
            print(f"DEBUG: entry_price_low = {ai.get('entry_price_low')}, entry_price_high = {ai.get('entry_price_high')}")
            
            el, eh = ai.get('entry_price_low'), ai.get('entry_price_high')
            if el is not None and eh is not None: 
                ai_entry = {'low': float(el), 'high': float(eh), 'avg': (float(el) + float(eh)) / 2}
                print(f"DEBUG: ai_entry created = {ai_entry}")
            
            cl, ch = ai.get('conservative_entry_low'), ai.get('conservative_entry_high')
            if cl is not None and ch is not None: 
                ai_cons_entry = {'low': float(cl), 'high': float(ch), 'avg': (float(cl) + float(ch)) / 2}
                print(f"DEBUG: ai_cons_entry created = {ai_cons_entry}")
            
            if ai_entry and ai_cons_entry: 
                ai_overall_avg = (ai_entry['avg'] + ai_cons_entry['avg']) / 2
            elif ai_entry: 
                ai_overall_avg = ai_entry['avg']
            
            print(f"DEBUG: ai_overall_avg = {ai_overall_avg}")
            
            if ai.get('target_price_base'): 
                ai_target_price = float(ai.get('target_price_base'))
                print(f"✅ Using AI base case target: ${ai_target_price:.2f}")
            elif ai.get('target_price_bull'):
                ai_target_price = float(ai.get('target_price_bull'))
                print(f"✅ Using AI bull case target: ${ai_target_price:.2f}")
            elif ai_entry and ai_entry.get('high'): 
                # Smarter fallback based on view and DCF
                if view and 'bull' in view.lower():
                    dcf_value = dcf_result.get('intrinsic') if dcf_result else None
                    if dcf_value and dcf_value > S:
                        ai_target_price = dcf_value * 1.10  # DCF + 10%
                        print(f"⚠️ FALLBACK: DCF-based ${ai_target_price:.2f}")
                    else:
                        ai_target_price = S * 1.20  # 20% upside
                        print(f"⚠️ FALLBACK: 20% upside ${ai_target_price:.2f}")
                else:
                    ai_target_price = ai_entry['high'] * 1.15
                    print(f"⚠️ FALLBACK: Entry-based ${ai_target_price:.2f}")
            
            print(f"DEBUG: ai_target_price = {ai_target_price}")

        # -----------------------------
        # Options Mode: build chain_data + Top-3 contract recommendations (budget/max_loss)
        # -----------------------------
        top3_contracts = []
        chain_data = {}
        try:
            if expiry:
                ch0 = cached_option_chain(ticker, expiry)
                calls_df = getattr(ch0, 'calls', None)
                puts_df  = getattr(ch0, 'puts', None)
                calls_df = calls_df if isinstance(calls_df, pd.DataFrame) else pd.DataFrame()
                puts_df  = puts_df  if isinstance(puts_df,  pd.DataFrame) else pd.DataFrame()

                def _df_to_rows(df: pd.DataFrame):
                    rows = []
                    if df is None or df.empty:
                        return rows
                    for _, r0 in df.iterrows():
                        strike0 = float(r0.get('strike')) if r0.get('strike') is not None else None
                        bid0 = r0.get('bid')
                        ask0 = r0.get('ask')
                        iv0  = r0.get('impliedVolatility')
                        try: bid0 = float(bid0) if bid0 is not None else None
                        except: bid0 = None
                        try: ask0 = float(ask0) if ask0 is not None else None
                        except: ask0 = None
                        try: iv0  = float(iv0) if iv0 is not None else None
                        except: iv0 = None

                        mid0 = None
                        if bid0 is not None and ask0 is not None and bid0 > 0 and ask0 > 0:
                            mid0 = 0.5 * (bid0 + ask0)
                        elif bid0 is not None and bid0 > 0:
                            mid0 = bid0
                        elif ask0 is not None and ask0 > 0:
                            mid0 = ask0

                        if strike0 is None or mid0 is None or mid0 <= 0:
                            continue

                        rows.append({
                            'strike': strike0,
                            'bid': bid0,
                            'ask': ask0,
                            'mid': mid0,
                            'iv': iv0,
                        })
                    return rows

                chain_data = {
                    expiry: {
                        'calls': _df_to_rows(calls_df),
                        'puts':  _df_to_rows(puts_df),
                    }
                }
            
        except Exception as e:
            print(f"chain_data build failed: {e}")
            chain_data = {}

        # -----------------------------
        # NEW: DCF & Price Guidance bridge
        # Inserted: just BEFORE Phase 10 comment
        # -----------------------------
        # Ensure DCF module is available: import guard at top of file must include:
        #   from data.dcf_engine import build_dcf
        # and price_guidance helpers are imported:
        #   from data.price_guidance import widen_factor_from_confidence
        #
        # (If those imports are not present at the top, add them. I show that later.)

        # =========================
        # Phase C: Price guidance engine (DCF-anchored)
        # =========================
        price_guidance_engine = None
        price_guidance_normal = None
        price_guidance_conservative = None
        price_guidance_reasons = []

        try:
            # Prefer derived quant scores (overall_risk / overall_quality) if available
            company_pg = None
            if isinstance(company_chain, dict):
                qp = company_chain.get("quant_profile") or {}
                if isinstance(qp, dict):
                    derived = qp.get("derived") or {}
                    if isinstance(derived, dict) and derived:
                        company_pg = derived
                if company_pg is None:
                    company_pg = company_chain

            days_to_earn = None
            try:
                days_to_earn = (earnings_info or {}).get("days_to_earnings")
            except Exception:
                days_to_earn = None

            price_guidance_engine = build_price_guidance(
                spot=S,
                dcf_result=dcf_result,
                macro_snapshot=macro_snapshot,
                company_snapshot=company_pg,
                iv_rank=None,          # will wire later after we move the call lower
                hv20=hv20,
                hv60=hv60,
                earnings_days=days_to_earn,
            )

            if isinstance(price_guidance_engine, dict):
                price_guidance_reasons.append("Phase C engine: DCF-anchored guidance with macro/company/vol/earnings overlays.")

                # Backward-compatible shapes (optional, but keeps your ctx keys consistent)
                b = float(price_guidance_engine.get("bear_extension"))
                base = float(price_guidance_engine.get("base_case"))
                bull = float(price_guidance_engine.get("bull_extension"))
                cons = float(price_guidance_engine.get("conservative_case"))

                price_guidance_normal = {
                    "bear": round(b, 2),
                    "base": round(base, 2),
                    "bull": round(bull, 2),
                    "avg": round((b + base + bull) / 3.0, 2),
                }

                price_guidance_conservative = {
                    "bear": round(min(b, cons), 2),
                    "base": round(cons, 2),
                    "bull": round(max(bull, cons), 2),
                    "avg": round((min(b, cons) + cons + max(bull, cons)) / 3.0, 2),
                    "widen_factor": (price_guidance_engine.get("reasoning") or {}).get("total_width"),
                }

        except Exception as e:
            price_guidance_engine = None
            price_guidance_normal = None
            price_guidance_conservative = None
            price_guidance_reasons = [f"Phase C engine failed: {e}"]
            price_guidance_reasons.append("Error while building price guidance from DCF.")


        # =========================
        # =========================
        # Phase 10: Price guidance (fair-value / range)
        # =========================

        # conclusion.confidence is 0..100 (deterministic)
        conf_pct = None
        try:
            conf_pct = float(conclusion.get("confidence"))
        except Exception:
            conf_pct = None

        fv_low, fv_high, fv_reasons = entry_zone_from_peers(
            S,
            peer_snapshot,
            hv20,
            hv60,
            conf_pct,
            view=view,
        )

        fair_value_zone = {
            "low": fv_low,
            "high": fv_high,
            "avg": round((float(fv_low) + float(fv_high)) / 2.0, 2) if (fv_low is not None and fv_high is not None) else None,
            "reasons": fv_reasons,
        }

        scenarios = scenario_bands(S, planned_days, hv20, hv60)

        # =========================
        # Phase 13: execution bands (ATR/VWAP aware)
        # =========================

        # execution_bands signature varies across phases; call defensively.
        exec_bands = None
        try:
            exec_bands = execution_bands(
                S,
                atr14,
                atr20,
                conf_pct,
                view=view,
                alpha_regime=alpha_regime,
                liquidity_metrics=None,  # stock mode has no option-chain liquidity metrics
            )
        except TypeError:
            # older/newer signature fallbacks
            try:
                exec_bands = execution_bands(S, atr14, atr20, conf_pct, view=view, alpha_regime=alpha_regime)
            except Exception:
                exec_bands = None
        except Exception:
            exec_bands = None

        # -----------------------------
        # Final displayed "ENTRY" zone
        # -----------------------------
        # Rule: ENTRY = realistic pullback zone. We construct it from:
        #   (a) fair-value/range band (Phase 10)
        #   (b) primary execution band (Phase 13)
        #   (c) VWAP band cap (Phase 13C) to avoid "buy above spot" in bull/neutral.
        entry_zone_final = None
        entry_reasons = []
        try:
            if exec_bands and isinstance(exec_bands.get("primary"), dict):
                p_lo = exec_bands["primary"].get("low")
                p_hi = exec_bands["primary"].get("high")
            else:
                p_lo, p_hi = None, None

            # Intersection base (Phase10 × Phase13)
            lo_candidates = [x for x in [fv_low, p_lo] if x is not None]
            hi_candidates = [x for x in [fv_high, p_hi] if x is not None]
            base_lo = max(lo_candidates) if lo_candidates else None
            base_hi = min(hi_candidates) if hi_candidates else None

            # VWAP/spot pullback cap for bullish/neutral
            cap_hi = None
            if view in ("bullish", "neutral"):
                cap_hi = float(S)

                try:
                    vwap = avwap.get("vwap")
                    if vwap is not None and float(vwap) < cap_hi:
                        cap_hi = float(vwap)
                        entry_reasons.append("Pullback cap: anchored VWAP.")
                except Exception:
                    pass

                try:
                    band_hi = avwap.get("band_high")
                    if band_hi is not None and float(band_hi) < cap_hi:
                        cap_hi = float(band_hi)
                        entry_reasons.append("Pullback cap: VWAP +1σ band.")
                except Exception:
                    pass

                entry_reasons.append("Pullback rule: bullish/neutral entries must be at or below pullback cap.")
            else:
                cap_hi = None

            # Apply cap
            if base_lo is not None and base_hi is not None:
                hi2 = float(base_hi)
                if cap_hi is not None:
                    hi2 = min(hi2, float(cap_hi))
                lo2 = float(base_lo)

                if lo2 <= hi2:
                    entry_zone_final = {"low": round(lo2, 2), "high": round(hi2, 2)}
                    entry_zone_final["avg"] = round((lo2 + hi2) / 2.0, 2)
                    entry_zone_final["reasons"] = (["Entry = Phase10 × Phase13 intersection."] + entry_reasons + (fv_reasons or []))
                else:
                    entry_zone_final = None

            # Fallback: if intersection fails, fall back to primary band (still capped for bull/neutral)
            if entry_zone_final is None and p_lo is not None and p_hi is not None:
                lo2 = float(p_lo)
                hi2 = float(p_hi)
                if cap_hi is not None:
                    hi2 = min(hi2, float(cap_hi))
                if lo2 <= hi2:
                    entry_zone_final = {"low": round(lo2, 2), "high": round(hi2, 2)}
                    entry_zone_final["avg"] = round((lo2 + hi2) / 2.0, 2)
                    entry_zone_final["reasons"] = (["Entry fallback: Phase13 primary band."] + entry_reasons)
        except Exception:
            entry_zone_final = None
        # -----------------------------
        # Entry band sanity: ensure the FINAL entry band has a meaningful width.
        # If the pullback cap collapses the band (hi ~= lo), widen DOWNWARD using ATR (analysis-based),
        # so the entry remains a realistic "zone" and conservative band can exist.
        # -----------------------------
        try:
            if entry_zone_final and entry_zone_final.get("low") is not None and entry_zone_final.get("high") is not None:
                lo0 = float(entry_zone_final["low"])
                hi0 = float(entry_zone_final["high"])
                w0 = hi0 - lo0

                # Width floor: prefer ATR14, else ATR20, else 0.75% of spot
                w_floor = None
                try:
                    if atr14 is not None and float(atr14) > 0:
                        w_floor = 0.35 * float(atr14)
                except Exception:
                    w_floor = None
                if w_floor is None:
                    try:
                        if atr20 is not None and float(atr20) > 0:
                            w_floor = 0.30 * float(atr20)
                    except Exception:
                        w_floor = None
                if w_floor is None:
                    w_floor = 0.0075 * float(S)

                if w0 < float(w_floor):
                    # widen downwards (keep hi anchored at cap)
                    lo1 = max(0.0, hi0 - float(w_floor))
                    entry_zone_final["low"] = round(lo1, 2)
                    entry_zone_final["high"] = round(hi0, 2)
                    entry_zone_final["avg"] = round((lo1 + hi0) / 2.0, 2)
                    try:
                        entry_zone_final.setdefault("reasons", [])
                        entry_zone_final["reasons"].insert(0, "Band floor: widened entry zone downward using ATR/spot width floor.")
                    except Exception:
                        pass
        except Exception:
            pass

        # Conservative entry (wait-for-better-price):
        # Deterministic + analysis-based: push the zone LOWER using ATR, then clamp within the final entry band.
        entry_zone_conservative = None
        try:
            if entry_zone_final and entry_zone_final.get("low") is not None and entry_zone_final.get("high") is not None:
                lo = float(entry_zone_final["low"])
                hi = float(entry_zone_final["high"])
                if hi > lo:
                    a = None
                    try:
                        if atr14 is not None and float(atr14) > 0:
                            a = float(atr14)
                    except Exception:
                        a = None
                    if a is None:
                        try:
                            if atr20 is not None and float(atr20) > 0:
                                a = float(atr20)
                        except Exception:
                            a = None

                    if a is not None:
                        # target a lower, tighter band: [lo - 0.50*ATR, lo + 0.15*ATR]
                        c_lo = max(0.0, lo - 0.50 * a)
                        c_hi = lo + 0.15 * a
                    else:
                        # fallback: bottom 25% slice of the band
                        width = hi - lo
                        c_lo = lo
                        c_hi = lo + 0.25 * width

                    # ensure conservative band stays within [0, hi] and is not above the normal band high
                    c_hi = min(c_hi, hi)
                    if c_lo > c_hi:
                        c_lo = c_hi

                    entry_zone_conservative = {"low": round(c_lo, 2), "high": round(c_hi, 2)}
                    entry_zone_conservative["avg"] = round((c_lo + c_hi) / 2.0, 2)
        except Exception:
            entry_zone_conservative = None

        # ── Signals used + factor_meta (stock mode) ─────────────────────────
        # Derive from the official Option A confidence dict (stock_confidence_dict).
        # Only factors with status="ok" and weight>0 appear.
        _fm_stock = stock_confidence_dict.get("factor_meta", {})
        signals_used_stock = []
        signals_used_display_stock = []
        for _fk, _fmv in _fm_stock.items():
            if _fmv.get("status") == "ok" and _fmv.get("weight", 0) > 1e-9:
                signals_used_stock.append(_fk)
                signals_used_display_stock.append(_fmv.get("pretty", _fk))
        print(f"📊 [Stock] Signals used: {', '.join(signals_used_display_stock) or 'none'}")
        # ────────────────────────────────────────────────────────────────────

        # ── AI–Model Divergence Risk Multiplier ─────────────────────────────
        # If AI conviction disagrees strongly with Option A official confidence,
        # reduce position sizing by 15% as a deterministic risk control.
        _ac_div = _build_ai_conviction_safe(ai if isinstance(ai, dict) else None, final_confidence)
        _div_score = _ac_div.score_0_100 if (_ac_div and _ac_div.available and _ac_div.score_0_100 is not None) else None
        divergence_flag = "aligned"
        divergence_size_multiplier = 1.0
        divergence_abs = 0
        if _div_score is not None:
            divergence_abs = abs(_div_score - final_confidence)
            if divergence_abs >= 25:
                divergence_flag = "high"
                divergence_size_multiplier = 0.85
            elif divergence_abs >= 15:
                divergence_flag = "moderate"
            else:
                divergence_flag = "aligned"
        _overlay_size_mult = risk_adj.get("size_multiplier", 1.0)
        final_size_multiplier = round(_overlay_size_mult * divergence_size_multiplier, 4)
        if divergence_flag == "high":
            print(f"⚠️ AI–Model divergence HIGH (Δ{divergence_abs}) → size {_overlay_size_mult:.2f}x × 0.85 = {final_size_multiplier:.2f}x")
        risk_adj["size_multiplier"] = final_size_multiplier
        risk_adj["divergence_flag"] = divergence_flag
        risk_adj["divergence_abs"] = divergence_abs
        risk_adj["divergence_size_multiplier"] = divergence_size_multiplier
        # ────────────────────────────────────────────────────────────────────

        ctx = {
            "request": request,
            "error": None,
            "analysis_mode": analysis_mode,

            "ticker": ticker,
            "spot": S,

            "earnings_track": earnings_track,

            "atr14": atr14,
            "atr20": atr20,
            "anchored_vwap": avwap,

            "exec_bands": exec_bands,

            "primary_entry": entry_zone_final,

            "hv20": hv20,
            "hv60": hv60,
            "sigma_choice": sigma_choice,
            "sigma_forecast": sigma_forecast,

            "company": company,
            "headlines": headlines,

            # UI inputs
            "budget": budget,
            "max_loss": max_loss,
            "view": view,
            "hold_days": hold_days,
            "planned_days": planned_days,
            "planned_hold_days": planned_hold_days,
            
            # P1-1 FIX: Explicit horizon separation
            "trade_horizon_days": planned_days,  # Actual trade plan (days to exit)
            "fundamental_horizon_months": 12,  # Long-term thesis horizon

            "cluster": cluster,
            "peers": peers,
            "peer_snapshot": peer_snapshot,

            "alpha_snapshot": alpha_snapshot,
            "alpha_regime": alpha_regime,

            "width": width,
            "horizon": horizon,
            "auto_expiry": False,

            "conclusion": conclusion,
    
            # NEW: Add adaptive DCF fields
            "adaptive_dcf": adaptive_dcf,
            "dcf_display": dcf_display,
            "dcf_weight_display_pct": dcf_weight_display_pct if 'dcf_weight_display_pct' in locals() else None,

            # Price guidance outputs
            "fair_value_zone": fair_value_zone,
            "exit_scenarios": scenarios,
            "entry_zone": entry_zone_final,
            "entry_zone_conservative": entry_zone_conservative,

            "dcf": dcf_result,
            "price_guidance_normal": price_guidance_normal,
            "price_guidance_conservative": price_guidance_conservative,
            "price_guidance_reasons": price_guidance_reasons,
            # Phase C engine output (structured)
            "price_guidance_engine": price_guidance_engine,

            # flip UI when engine exists
            "show_price_guidance": True if price_guidance_engine else False,

            # Missing previously: macro + events wiring (for report.html)
            "macro_snapshot": macro_snapshot,
            "earnings_info": earnings_info,
            "earnings_move_stats": earnings_move_stats,
            
            # Phase D: Option A confidence
            "confidence": stock_confidence_dict,  # Use dict structure (has .total for template)
            
            # ADVANCED OVERLAY: Risk plan adjustments
            "overlay": overlay,
            "risk_adj": risk_adj,
            "base_confidence": base_confidence,
            "final_confidence": final_confidence,
            "signals_used": signals_used_display_stock,
            "factor_meta": stock_confidence_dict.get("factor_meta", {}),
            "qualitative_proxy": qualitative_proxy_result if 'qualitative_proxy_result' in locals() else None,
            
            # AI Conviction (secondary - never drives risk controls)
            "ai_conviction": _build_ai_conviction_safe(ai, final_confidence),
            "divergence_flag": risk_adj.get("divergence_flag", "aligned"),
            "divergence_abs": risk_adj.get("divergence_abs", 0),
            "divergence_size_multiplier": risk_adj.get("divergence_size_multiplier", 1.0),
            "final_size_multiplier": risk_adj.get("size_multiplier", 1.0),

            "ai": ai,
            "ai_entry": ai_entry,
            "ai_cons_entry": ai_cons_entry,
            "ai_overall_avg": ai_overall_avg,
            "ai_target_price": ai_target_price,
            "options_recos": options_recos,
            "debug_ai": debug_ai,
            
            # P0-4 FIX: Target guardrail context (stock mode - no guardrail applied, pass through)
            "target_price_final": ai_target_price,
            "target_caps": None,
            "target_price_ai_raw": ai_target_price,
            
            # P0-4 FIX: Stock options diagnostics (if available)
            "stock_options_diagnostics": stock_options_diagnostics if 'stock_options_diagnostics' in locals() else None,

            # Reverse DCF analysis for stock mode (same template section as options)
            "reverse_dcf_analysis": stock_reverse_dcf_analysis if 'stock_reverse_dcf_analysis' in locals() else None,
            
        }

        from data.api_key_manager import print_usage_status
        print_usage_status()


        # Return raw JSON if requested
        if raw == 1:
            from fastapi.responses import JSONResponse
            # Remove non-serializable objects
            json_ctx = {k: v for k, v in ctx.items() if k != "request"}
            return JSONResponse(content=json_ctx)

        return templates.TemplateResponse(
            "report.html",
            context=ctx,
            headers={"Cache-Control": "no-cache"}
        )
    
    

    # auto-expiry (always compute for display, but only auto-select if enabled)
    auto_info = None
    try:
        auto_info = auto_pick_expiry(
            ticker, t, S, 
            horizon=horizon, 
            width=width,
            hold_days=int(hold_days) if hold_days else None  # ← PASS hold_days
        )
        if auto_expiry:
            expiry = auto_info["suggested_expiry"]
    except Exception as e:
        print(f"auto_pick_expiry failed: {e}")
        auto_info = None

    # P0-2 FIX: Compute suggested expiry DTE (days to expiry)
    suggested_dte = None
    if auto_info and auto_info.get("best_expiry"):
        try:
            from datetime import datetime
            best_exp_str = auto_info.get("best_expiry")
            if best_exp_str:
                # Handle both string and datetime objects
                if isinstance(best_exp_str, str):
                    best_exp_date = datetime.strptime(best_exp_str, "%Y-%m-%d")
                else:
                    best_exp_date = best_exp_str
                
                suggested_dte = (best_exp_date - datetime.now()).days
                if suggested_dte < 0:
                    suggested_dte = 0
                
                print(f"  Suggested DTE: {suggested_dte} days")
        except Exception as e:
            print(f"  Warning: Could not compute suggested_dte: {e}")
            suggested_dte = None

    # annotate display-only metrics (safe)
    if raw != 1 and auto_info:
            auto_info = dict(auto_info)

            # annotate the best expiry metrics
            if isinstance(auto_info.get("metrics"), dict):
                auto_info["metrics"] = annotate_keys(auto_info["metrics"], GLOSSARY)

            # annotate top-3 metrics too
            if isinstance(auto_info.get("top3"), list):
                top3_new = []
                for row in auto_info["top3"]:
                    row2 = dict(row)
                    if isinstance(row2.get("metrics"), dict):
                        row2["metrics"] = annotate_keys(row2["metrics"], GLOSSARY)
                    top3_new.append(row2)
                auto_info["top3"] = top3_new

    # =========================
    # NEW: IV term structure + skew (uses your IV solver)
    # =========================
    days_to_exp = _days_to_exp(expiry)
    # =========================
    # NEW: planned hold horizon (separate from expiry DTE)
    # =========================
    ph = int(planned_hold_days) if planned_hold_days and planned_hold_days > 0 else int(hold_days)
    planned_days = max(1, min(ph, int(days_to_exp))) if (days_to_exp and days_to_exp > 0) else max(1, ph)

    iv_term, iv_skew, atm_iv_selected = build_iv_term_and_skew_from_chain(
        ticker = ticker,
        t=t,
        spot=S,
        r=r,
        selected_expiry=expiry,
        max_strikes_each_side=12,
    )
    # store ATM IV snapshot for future IV Rank (deterministic history)
    append_atm_iv_snapshot(ticker=ticker, expiry=expiry, atm_iv=atm_iv_selected)



    iv_term_json = json.dumps(iv_term) if iv_term else None
    iv_skew_json = json.dumps(iv_skew) if iv_skew else None

    # ----------------------------
    # IV Rank (from stored ATM IV snapshots)
    # ----------------------------
    iv_rank_res = compute_iv_rank_from_snapshots(
        ticker=ticker,
        current_atm_iv=atm_iv_selected,
        lookback_days=252,
    )

    analytics["iv_rank"] = {
        "current_iv": iv_rank_res.current_iv,
        "iv_rank": iv_rank_res.iv_rank,
        "iv_percentile": iv_rank_res.iv_percentile,
        "lookback_days": iv_rank_res.lookback_days,
        "n_points": iv_rank_res.n_points,
        "note": iv_rank_res.note,
    }




    analytics["iv_term_json"] = iv_term_json
    analytics["iv_skew_json"] = iv_skew_json
    analytics["atm_iv_selected"] = atm_iv_selected


    implied_move_pct = None            # expiry horizon
    implied_move_pct_planned = None    # planned horizon

    if atm_iv_selected is not None and days_to_exp and days_to_exp > 0:
        implied_move_pct = float(atm_iv_selected) * sqrt(days_to_exp / 365.0)

    if atm_iv_selected is not None and planned_days and planned_days > 0:
        implied_move_pct_planned = float(atm_iv_selected) * sqrt(planned_days / 365.0)

    

    analytics["days_to_exp"] = days_to_exp

    # vol forecast
    hv20 = realized_vol(hist["Close"], 20)
    hv60 = realized_vol(hist["Close"], 60)

    if sigma_choice == "HV20":
        sigma_forecast = hv20
    elif sigma_choice == "HV60":
        sigma_forecast = hv60
    else:
        sigma_forecast = hv20

    # macro snapshot (options mode; keep stock mode unchanged)
    try:
        macro_snapshot = get_macro_snapshot()
    except Exception as e:
        print(f"macro snapshot failed: {e}")
        macro_snapshot = None


    # =========================
    # NEW: expected move + vol context + earnings
    # =========================
    implied_move_abs = None
    implied_low = None
    implied_high = None
    if implied_move_pct is not None:
        implied_move_abs = float(S) * float(implied_move_pct)
        implied_low = float(S) - implied_move_abs
        implied_high = float(S) + implied_move_abs


    implied_move_abs_planned = None
    implied_low_planned = None
    implied_high_planned = None
    if implied_move_pct_planned is not None:
        implied_move_abs_planned = float(S) * float(implied_move_pct_planned)
        implied_low_planned = float(S) - implied_move_abs_planned
        implied_high_planned = float(S) + implied_move_abs_planned

    
    analytics["implied_move_pct"] = implied_move_pct
    analytics["implied_move_abs"] = implied_move_abs
    analytics["implied_low"] = implied_low
    analytics["implied_high"] = implied_high

    analytics["planned_days"] = planned_days
    analytics["implied_move_pct_planned"] = implied_move_pct_planned
    analytics["implied_move_abs_planned"] = implied_move_abs_planned
    analytics["implied_low_planned"] = implied_low_planned
    analytics["implied_high_planned"] = implied_high_planned

    vol_context = {
        "atm_iv_selected": atm_iv_selected,
        "iv_minus_hv20": (atm_iv_selected - hv20) if (atm_iv_selected is not None) else None,
        "iv_minus_hv60": (atm_iv_selected - hv60) if (atm_iv_selected is not None) else None,
        "iv_over_hv20": (atm_iv_selected / hv20) if (atm_iv_selected is not None and hv20 and hv20 > 0) else None,
        "iv_over_hv60": (atm_iv_selected / hv60) if (atm_iv_selected is not None and hv60 and hv60 > 0) else None,
    }

    analytics["vol_context"] = vol_context

    company = COMPANY_CACHE.get_or_set(
        f"company:{ticker}",
        lambda: get_company_snapshot(t),
        ttl_sec=12 * 3600,
    )

    # ---- Phase B: Company chain (business model / suppliers / customers) ----
    try:
        sector_bucket = sector_bucket_for(ticker)

        company_chain = build_company_chain(
            ticker,
            company,
            cluster=cluster,
            sector_bucket=sector_bucket,
        )
    except Exception as e:
        company_chain = {"source_note": f"company_chain error: {e}"}

    company["company_chain"] = company_chain

    # Optional: also alias it so report.html's cb fallback works consistently
    company["company_brief"] = company_chain

    headlines = NEWS_CACHE.get_or_set(
        f"news:{ticker}",
        lambda: get_latest_headlines(t, max_items=8),
        ttl_sec=30 * 60,
    )
    analytics["company"] = company
    analytics["headlines"] = headlines


    # earnings_info already initialized before mode branching


    # Phase 13: Anchored VWAP from earnings date (best-effort)
    avwap = None
    anchor = (earnings_info or {}).get("earnings_date_us") or (earnings_info or {}).get("earnings_date_utc")
    if anchor:
        try:
            avwap = anchored_vwap(hist, anchor)
        except Exception:
            avwap = None

    oi_vol_profile = build_oi_vol_profile(ticker, expiry, strike_limit=2000)
    oi_vol_json = json.dumps(oi_vol_profile.get("by_strike", [])) if oi_vol_profile else "[]"
    pcr = oi_vol_profile.get("totals", {}) if oi_vol_profile else {}

    analytics["earnings_info"] = earnings_info
    analytics["earnings_move_stats"] = earnings_realized_move_stats(hist, earnings_info, lookback=6)
    analytics["oi_vol_json"] = oi_vol_json
    analytics["pcr"] = pcr

    mid = (bid + ask) / 2.0

    T = max(days_to_exp / 365.0, 1e-6)

    theo = bs_price(S, strike, T, r, sigma_forecast, opt_type)
    delta, gamma, vega = bs_greeks(S, strike, T, r, sigma_forecast, opt_type)

    gap_pct = None
    label = "N/A"
    if theo and (not math.isnan(theo)) and theo > 0 and mid > 0:
        gap_pct = (mid - theo) / theo
        if gap_pct > 0.10:
            label = "RICH (expensive vs forecast vol)"
        elif gap_pct < -0.10:
            label = "CHEAP (cheap vs forecast vol)"
        else:
            label = "FAIR-ish"

    spread_pct = None
    liq_ok = False
    if mid > 0:
        spread_pct = (ask - bid) / mid
        liq_ok = (spread_pct is not None) and (spread_pct <= max_spread_pct)
    
    # ============================================================
    # ============================================================
    # P0-1 FIX: UNIFIED LIQUIDITY GATE - SINGLE SOURCE OF TRUTH
    # ============================================================
    liquidity_gate = None
    liquidity_blocked = False
    liquidity_block_reason = ""

    try:
        if analysis_mode == "options":
            # Build unified liquidity gate object from auto_expiry ONLY
            liquidity_gate = build_liquidity_gate(auto_info, max_spread_pct)
            
            # Extract boolean flags for legacy compatibility
            liquidity_blocked = (liquidity_gate["status"] == "BLOCK")
            liquidity_block_reason = liquidity_gate["reason"]
            
            print(f"🔒 Liquidity Gate Status: {liquidity_gate['status']}")
            print(f"   Grade: {liquidity_gate['liquidity_grade']} | Score: {liquidity_gate['score']:.3f}")
            if liquidity_gate['pct_two_sided'] is not None:
                print(f"   Pct Two-Sided: {liquidity_gate['pct_two_sided']:.3f}")
            if liquidity_gate['median_spread'] is not None:
                print(f"   Median Spread: {liquidity_gate['median_spread']:.2%}")
            if liquidity_blocked:
                print(f"   Reason: {liquidity_block_reason}")

            # gate used by /api/ai/chat (options follow-up Q&A)
            AI_CHAT_GATES[ticker] = {
                "blocked": liquidity_blocked, 
                "reason": liquidity_block_reason,
                "gate": liquidity_gate  # Full object for detailed responses
            }

            # also store in analytics for report rendering/debug
            analytics["liquidity_gate"] = liquidity_gate  # Full unified object
    except Exception as e:
        print(f"liquidity gate compute failed: {e}")
        liquidity_blocked = False
        liquidity_block_reason = ""
        liquidity_gate = {
            "status": "PASS",
            "reason": "Gate computation failed, allowing trade",
            "pct_two_sided": None,
            "median_spread": None,
            "liquidity_grade": "C",
            "score": 0.5,
            "source": "error_fallback"
        }

    conf = 0.2 + 0.35 + 0.25 + (0.20 if liq_ok else 0.0)
    conf = max(0.0, min(1.0, conf))

    contract_cost = mid * 100
    max_contracts_budget = int(budget // contract_cost) if contract_cost > 0 else 0

    # Macro fallback: if snapshot is falsy, use macro_report -> dict conversion
    try:
        if not macro_snapshot:
            try:
                mr = get_macro_report()
                if mr:
                    macro_snapshot = macro_report_to_dict(mr)
                    print("macro fallback: used get_macro_report() for macro_snapshot")
                else:
                    macro_snapshot = {}
            except Exception as e:
                print("macro fallback failed:", e)
                macro_snapshot = {}
    except Exception:
        macro_snapshot = {}

    # =========================
    # NEW: Straddle vs HV (defaults first so TemplateResponse never crashes)
    # =========================
    straddle = {"atm_strike": None, "call_mid": None, "put_mid": None, "straddle_mid": None}
    straddle_implied_move_pct = None
    straddle_implied_move_abs = None
    hv20_move_pct_planned = None
    hv60_move_pct_planned = None
    straddle_vs_hv20 = None

    # Compute straddle
    straddle = get_atm_straddle_from_chain(ticker, expiry, S)

    if straddle.get("straddle_mid") is not None and S > 0:
        straddle_implied_move_pct = float(straddle["straddle_mid"] / S)
        straddle_implied_move_abs = float(straddle["straddle_mid"])

    # Planned-horizon HV expected move (annualized HV -> horizon move)
    if planned_days and planned_days > 0:
        T_planned = planned_days / 365.0
        if hv20 is not None:
            hv20_move_pct_planned = float(hv20) * math.sqrt(T_planned)
        if hv60 is not None:
            hv60_move_pct_planned = float(hv60) * math.sqrt(T_planned)

    if (
        straddle_implied_move_pct is not None
        and hv20_move_pct_planned is not None
        and hv20_move_pct_planned > 0
    ):
        straddle_vs_hv20 = float(straddle_implied_move_pct / hv20_move_pct_planned)

    analytics["straddle"] = straddle
    analytics["straddle_implied_move_pct"] = straddle_implied_move_pct
    analytics["straddle_implied_move_abs"] = straddle_implied_move_abs
    analytics["hv20_move_pct_planned"] = hv20_move_pct_planned
    analytics["hv60_move_pct_planned"] = hv60_move_pct_planned
    analytics["straddle_vs_hv20"] = straddle_vs_hv20


    # =========================
    # Phase 13E: prep liquidity metrics for confidence overlay
    # - prefer auto-expiry metrics if present
    # - fallback to current strike spread/liquidity gate
    # =========================
    liq_metrics_for_confidence = None
    try:
        if isinstance(auto_info, dict) and isinstance(auto_info.get("metrics"), dict):
            liq_metrics_for_confidence = auto_info.get("metrics")
        else:
            liq_metrics_for_confidence = {"spread_pct": spread_pct, "liq_ok": liq_ok}
    except Exception:
        liq_metrics_for_confidence = {"spread_pct": spread_pct, "liq_ok": liq_ok}


    conclusion_ctx = {
        "view": view,
        "liq_ok": liq_ok,
        "spread_pct": spread_pct,
        "gap_pct": gap_pct,
        "label": label,
        "hv20": hv20,
        "hv60": hv60,


        # required for earnings window logic
        "planned_days": planned_days,
        "days_to_exp": days_to_exp,

        # planned horizon drives conclusion
        "implied_move_pct": implied_move_pct_planned,
        "implied_move_pct_expiry": implied_move_pct,

        "auto_info": auto_info,
        "macro_snapshot": macro_snapshot,
        "pcr": pcr,
        "earnings_info": earnings_info,
    }

    # add analytics fields so signals can use them later without re-plumbing
    conclusion_ctx.update(analytics)

    conclusion = build_conclusion(conclusion_ctx)

    # Phase D: Option A Weighted Confidence (options mode)
    # Try Gemini AI for analyst commentary / price guidance (does NOT set the official confidence score)
    ai = None
    try:
        from data.gemini_confidence import compute_confidence_with_ai

        # Get company info for Gemini
        company = COMPANY_CACHE.get_or_set(
            f"company:{ticker}",
            lambda: get_company_snapshot(yf.Ticker(ticker)),
            ttl_sec=12 * 3600,
        )

        ai = compute_confidence_with_ai(
            ticker=ticker,
            user_stance=view if view else "neutral",
            spot_price=S,
            intrinsic_value=dcf_result.get('intrinsic') if dcf_result else S,
            macro_regime=macro_snapshot.get('regime_label', 'Neutral') if macro_snapshot else 'Neutral',
            earnings_data=earnings_track if earnings_track else {'quarters': []},
            valuation_data={
                'pe_ratio': company.get('trailing_pe'),
                'ps_ratio': company.get('price_to_sales'),
                'profit_margin': company.get('profit_margin'),
                'revenue_growth': company.get('revenue_growth'),
                'eps_growth': company.get('eps_growth'),
            },
            company_info={
                'name': company.get('name', ticker),
                'sector': company.get('sector', 'Unknown'),
                'industry': company.get('industry', 'Unknown'),
                'description': company.get('summary', '')
            },
            macro_context=None,
            # FULL QUANT STACK - Professional Grade
            technical_data={
                'atr14': atr14,
                'atr20': atr20,
                'anchored_vwap': avwap if 'avwap' in locals() else None,
                'exec_bands': exec_bands if 'exec_bands' in locals() else None,
                'primary_entry': primary_entry if 'primary_entry' in locals() else None,
                'spot_price': S,
            },
            alpha_data={
                'alpha_snapshot': alpha_snapshot,
                'alpha_regime': alpha_regime,
            },
            iv_data={
                'iv_rank': (analytics.get("iv_rank") or {}).get("iv_rank"),
                'current_iv': (analytics.get("iv_rank") or {}).get("current_iv"),
                'iv_percentile': (analytics.get("iv_rank") or {}).get("iv_percentile"),
            },
            peer_data={
                'peers': peers,
                'peer_snapshot': peer_snapshot if 'peer_snapshot' in locals() else None,
                'cluster': cluster,
            },
            extra_info=json.dumps(overlay),
        )

    except Exception as e:
        print(f"Gemini AI failed (options mode): {e}")
        ai = {"available": False, "error": str(e)}

    # --- Qualitative Proxies (options mode) ---
    try:
        yf_info_opts = getattr(yf.Ticker(ticker), 'info', None) or {}
    except Exception:
        yf_info_opts = {}
    try:
        qualitative_proxy_result = compute_qualitative_proxies(
            ticker=ticker,
            mode="options",
            hold_days=hold_days,
            hist_df=hist if 'hist' in locals() else None,
            sector_bucket=sector_bucket_for(ticker) if 'sector_bucket_for' in dir() else None,
            alpha_snapshot=alpha_snapshot,
            earnings_info=earnings_info,
            dcf_result=dcf_result if isinstance(dcf_result, dict) else None,
            headlines=headlines if 'headlines' in locals() else None,
            yf_info=yf_info_opts,
            spot=S,
        )
    except Exception as _qpe:
        print(f"Qualitative proxy error (options): {_qpe}")
        qualitative_proxy_result = {"available": False, "score_01": 0.5}

    # ── Early Reverse DCF ─────────────────────────────────────────────────────
    # Run reverse DCF BEFORE computing confidence so its reasonableness score
    # can be blended into S_dcf.  The full institutional block later reuses the
    # same object (reverse_dcf_analysis) for display and cap logic.
    if not ('reverse_dcf_analysis' in locals() and reverse_dcf_analysis):
        reverse_dcf_analysis = None
        try:
            if dcf_result and isinstance(dcf_result, dict) and company:
                from data.reverse_dcf import ReverseDCF as _RDCF
                _rdcf_runner = _RDCF()
                _rev_growth = company.get("revenue_growth")
                try:
                    _rev_cagr = float(_rev_growth) if _rev_growth is not None else 0.08
                    _rev_cagr = max(-0.20, min(0.40, _rev_cagr))
                except Exception:
                    _rev_cagr = 0.08
                _fcf = company.get("free_cash_flow")
                _rev = company.get("revenue")
                try:
                    _fcf_margin = float(_fcf) / float(_rev) if (_fcf and _rev) else 0.10
                    _fcf_margin = max(-0.10, min(0.35, _fcf_margin))
                except Exception:
                    _fcf_margin = 0.10
                reverse_dcf_analysis = _rdcf_runner.analyze(
                    current_price=S,
                    current_revenue=company.get("revenue", 30e9),
                    current_margin=company.get("profit_margin", 0.10),
                    current_fcf_margin=_fcf_margin,
                    shares_outstanding=company.get("shares_outstanding", 1.1e9),
                    dcf_intrinsic=dcf_result.get("intrinsic", S),
                    dcf_assumptions={
                        "revenue_cagr": _rev_cagr,
                        "terminal_growth": 0.025 if (company.get("sector") or "").lower().find("technology") >= 0 else 0.02,
                        "fcf_margin": _fcf_margin,
                    },
                    current_hbm_mix=0.15 if ticker == "MU" else None,
                    hbm_tam_growth=0.85 if ticker == "MU" else None,
                    beta=1.5,
                )
                print(f"✅ Early Reverse DCF: reasonableness={reverse_dcf_analysis.get('reasonableness_score', 'N/A')}/10")
        except Exception as _re:
            print(f"⚠️ Early Reverse DCF failed: {_re}")
            reverse_dcf_analysis = None
    # ────────────────────────────────────────────────────────────────────────

    # Official confidence score: deterministic / auditable (Option A)
    confidence = compute_confidence_option_a(
        spot=S,
        dcf_result=dcf_result if isinstance(dcf_result, dict) else None,
        macro_snapshot=macro_snapshot if isinstance(macro_snapshot, dict) else None,
        company_snapshot=company_chain,  # has quant_profile.derived + industry_snapshot
        hv20=hv20,
        hv60=hv60,
        iv_rank=(analytics.get("iv_rank") or {}).get("iv_rank"),
        earnings_info=earnings_info,
        liquidity_metrics=liq_metrics_for_confidence,
        alpha_snapshot=alpha_snapshot,
        mode="options",
        qualitative_proxy=qualitative_proxy_result,
        # Blend reverse DCF reasonableness into S_dcf
        reverse_dcf_reasonableness=reverse_dcf_analysis.get("reasonableness_score") if reverse_dcf_analysis else None,
    )

    # Save Option A dict BEFORE overlay/cap logic overwrites confidence variable
    options_option_a_dict = confidence if isinstance(confidence, dict) else {}

    # ==================================================================
    # ADVANCED OVERLAY → RISK PLAN ADJUSTMENTS (Options Mode)
    # ==================================================================
    # Extract numeric confidence value (handle dict or number)
    if isinstance(confidence, dict):
        base_confidence_value = int(confidence.get("total", confidence.get("total_confidence", 50)))
    else:
        base_confidence_value = int(confidence)
    
    # IMPORTANT: base_confidence must be numeric for Jinja filters like |round
    base_confidence = base_confidence_value
    risk_adj = {'overlay_used': False}
    
    if overlay.get('present'):
        base_metrics = {
            'base_confidence': base_confidence_value,  # Use numeric value
            'liquidity_gate_status': liquidity_gate.get('status') if liquidity_gate else 'PASS',
            'reverse_dcf_reasonableness': reverse_dcf_analysis.get('reasonableness_score', 5.0) if 'reverse_dcf_analysis' in locals() and reverse_dcf_analysis else 5.0,
            'iv_rank': (analytics.get("iv_rank") or {}).get("iv_rank", 50.0),
            'hold_days': planned_days if planned_days > 0 else hold_days,
            'earnings_within_window': earnings_in_window if 'earnings_in_window' in locals() else False,
        }
        risk_adj = overlay_to_risk_adjustments(overlay, base_metrics)
        adjusted_confidence = base_confidence_value + risk_adj['confidence_delta']
        
        if risk_adj['overlay_used']:
            print(f"📊 Risk Plan (Options Mode):")
            print(f"   Size: {risk_adj['size_multiplier']:.2f}x")
            print(f"   Entry: {risk_adj['entry_aggressiveness']}")
            print(f"   Stops: {risk_adj['stop_tightness']}")
            if risk_adj['require_hedge']:
                print(f"   Hedge: {risk_adj['hedge_style']}")
            print(f"   Confidence: {base_confidence_value}% {risk_adj['confidence_delta']:+d} = {adjusted_confidence}%")
    else:
        adjusted_confidence = base_confidence_value
        risk_adj = {
            'size_multiplier': 1.0,
            'entry_aggressiveness': 'base',
            'stop_tightness': 'normal',
            'require_hedge': False,
            'hedge_style': None,
            'confidence_delta': 0,
            'notes': [],
            'overlay_used': False
        }
    
    # Hard caps (DCF, liquidity, macro)
    max_confidence_cap = 100
    cap_reasons = []
    
    # Cap 1: Reverse DCF stretch
    if 'reverse_dcf_analysis' in locals() and reverse_dcf_analysis:
        reverse_dcf_reasonableness = reverse_dcf_analysis.get('reasonableness_score', 5.0)
        if reverse_dcf_reasonableness < 2.0:
            max_confidence_cap = min(max_confidence_cap, 65)
            cap_reasons.append(f"DCF stretch (reasonableness: {reverse_dcf_reasonableness:.1f}/10)")
    
    # Cap 2: Liquidity gate
    if liquidity_gate:
        gate_status = liquidity_gate.get('status')
        if gate_status == 'BLOCK':
            max_confidence_cap = 0
            cap_reasons.append("Liquidity BLOCKED")
        elif gate_status == 'WARN':
            max_confidence_cap = min(max_confidence_cap, 70)
            cap_reasons.append("Liquidity WARNING")
    
    # Cap 3: Macro crash regime
    if macro_snapshot and isinstance(macro_snapshot, dict):
        regime = macro_snapshot.get('regime_label', '').upper()
        if 'RISK_OFF' in regime or 'CRASH' in regime:
            max_confidence_cap = min(max_confidence_cap, 60)
            cap_reasons.append(f"Macro regime ({regime})")
    
    if adjusted_confidence > max_confidence_cap:
        print(f"⚠️ Hard cap: {adjusted_confidence}% → {max_confidence_cap}% (reason: {', '.join(cap_reasons)})")
        adjusted_confidence = max_confidence_cap
    
    final_confidence = adjusted_confidence

    # DCF weight display: read from the ACTUAL weights dict used in scoring
    _dcf_w_opts = options_option_a_dict.get("weights", {}).get("dcf", 0.0) if 'options_option_a_dict' in locals() else 0.0
    dcf_weight_display_pct = round(float(_dcf_w_opts) * 100, 1)

    # P0-4 FIX: Ensure headline conclusion reflects final capped confidence
    try:
        if isinstance(conclusion, dict):
            conclusion["confidence"] = final_confidence
    except Exception:
        pass

    # ============================================================
    # FIX 2: ENSURE AI SECTION APPEARS IN REPORT
    # ============================================================
    if ai and isinstance(ai, dict):
        # Force enable AI section if we have content
        has_content = ai.get('ai_report') or ai.get('report')
        
        if has_content:
            # Ensure 'available' key is True
            ai['available'] = True
            
            # Map 'report' to 'ai_report' if needed
            if 'report' in ai and 'ai_report' not in ai:
                ai['ai_report'] = ai['report']
            
            # Ensure all required keys exist with defaults
            ai.setdefault('available', True)
            ai.setdefault('confidence', ai.get('total', 50))
            ai.setdefault('total', ai.get('confidence', 50))
            ai.setdefault('key_drivers', [])
            ai.setdefault('risks', [])
            ai.setdefault('time_horizon', '')
            
            print(f"✅ AI SECTION ENABLED: confidence={ai.get('confidence')}, report_length={len(str(ai.get('ai_report', '')))}")
        else:
            print(f"⚠️ AI section disabled: no content available")
            ai['available'] = False
    elif ai:
        print(f"⚠️ AI is not a dict: type={type(ai)}")
    else:
        print(f"⚠️ AI is None")

    ai_entry = ai_cons_entry = ai_overall_avg = ai_target_price = options_recos = None
    if isinstance(ai, dict):
        # Debug logging
        print(f"DEBUG OPTIONS MODE: ai keys = {list(ai.keys())}")
        print(f"DEBUG: entry_price_low = {ai.get('entry_price_low')}, entry_price_high = {ai.get('entry_price_high')}")
        
        el, eh = ai.get('entry_price_low'), ai.get('entry_price_high')
        if el is not None and eh is not None: 
            ai_entry = {'low': float(el), 'high': float(eh), 'avg': (float(el) + float(eh)) / 2}
            print(f"DEBUG: ai_entry created = {ai_entry}")
        
        cl, ch = ai.get('conservative_entry_low'), ai.get('conservative_entry_high')
        if cl is not None and ch is not None: 
            ai_cons_entry = {'low': float(cl), 'high': float(ch), 'avg': (float(cl) + float(ch)) / 2}
            print(f"DEBUG: ai_cons_entry created = {ai_cons_entry}")
        
        if ai_entry and ai_cons_entry: 
            ai_overall_avg = (ai_entry['avg'] + ai_cons_entry['avg']) / 2
        elif ai_entry: 
            ai_overall_avg = ai_entry['avg']
        
        print(f"DEBUG: ai_overall_avg = {ai_overall_avg}")
        
        if ai.get('target_price_base'): 
            ai_target_price = float(ai.get('target_price_base'))
            print(f"✅ Using AI base case target: ${ai_target_price:.2f}")
        elif ai.get('target_price_bull'):
            ai_target_price = float(ai.get('target_price_bull'))
            print(f"✅ Using AI bull case target: ${ai_target_price:.2f}")
        elif ai_entry and ai_entry.get('high'): 
            # Smarter fallback based on view and DCF
            if view and 'bull' in view.lower():
                dcf_value = dcf_result.get('intrinsic') if dcf_result else None
                if dcf_value and dcf_value > S:
                    ai_target_price = dcf_value * 1.10  # DCF + 10%
                    print(f"⚠️ FALLBACK: DCF-based ${ai_target_price:.2f}")
                else:
                    ai_target_price = S * 1.20  # 20% upside
                    print(f"⚠️ FALLBACK: 20% upside ${ai_target_price:.2f}")
            else:
                ai_target_price = ai_entry['high'] * 1.15
                print(f"⚠️ FALLBACK: Entry-based ${ai_target_price:.2f}")
        
        print(f"DEBUG: ai_target_price = {ai_target_price}")

        # Canonical target for options mode: use AI target if available, else deterministic peer-band model target, else a mild upside fallback
        try:
            if (ai_target_price is None or float(ai_target_price) <= 0) and model_target_price:
                ai_target_price = float(model_target_price)
                print(f"⚠️ CANONICAL TARGET: using model_target_price ${ai_target_price:.2f}")
        except Exception:
            pass

        if ai_target_price is None:
            ai_target_price = float(S) * 1.10
            print(f"⚠️ CANONICAL TARGET: fallback 10% upside ${ai_target_price:.2f}")

        # ============================================================
        # P0-4 FIX: APPLY TARGET GUARDRAILS (cap_target_price)
        # Prevents unconstrained AI targets from driving dashboard/optimiser
        # ============================================================
        target_price_ai_raw = ai_target_price
        try:
            _rdcf_score = reverse_dcf_analysis.get("reasonableness_score") if ('reverse_dcf_analysis' in locals() and reverse_dcf_analysis) else None
            target_price_final, target_caps = cap_target_price(
                spot=float(S),
                ai_base=float(ai_target_price) if ai_target_price else None,
                implied_move_pct=implied_move_pct_planned,
                model_target_price=float(model_target_price) if model_target_price else None,
                reverse_dcf_score=_rdcf_score,
            )
            # Use capped target for all deterministic tooling
            ai_target_price = target_price_final
            if target_caps.get("applied"):
                print(f"🛡️ Target capped: raw=${target_price_ai_raw:.2f} → final=${target_price_final:.2f} ({target_caps['reason']})")
        except Exception as e:
            print(f"⚠️ cap_target_price failed: {e}")
            target_price_final = ai_target_price
            target_caps = {"applied": False, "reason": ""}
            target_price_ai_raw = ai_target_price

        # -----------------------------
        # Options Mode: build chain_data + Top-3 contract recommendations (budget/max_loss)
        # -----------------------------
        try:
            chain_data = {}
            top3_contracts = []

            if expiry:
                ch0 = cached_option_chain(ticker, expiry)
                calls_df = getattr(ch0, "calls", None)
                puts_df  = getattr(ch0, "puts", None)
                calls_df = calls_df if isinstance(calls_df, pd.DataFrame) else pd.DataFrame()
                puts_df  = puts_df  if isinstance(puts_df,  pd.DataFrame) else pd.DataFrame()

                def _df_to_rows(df: pd.DataFrame):
                    rows = []
                    if df is None or df.empty:
                        return rows
                    for _, r0 in df.iterrows():
                        strike0 = r0.get("strike")
                        if strike0 is None:
                            continue
                        try:
                            strike0 = float(strike0)
                        except Exception:
                            continue

                        bid0 = r0.get("bid")
                        ask0 = r0.get("ask")
                        iv0  = r0.get("impliedVolatility")

                        try: bid0 = float(bid0) if bid0 is not None else None
                        except Exception: bid0 = None
                        try: ask0 = float(ask0) if ask0 is not None else None
                        except Exception: ask0 = None
                        try: iv0  = float(iv0)  if iv0  is not None else None
                        except Exception: iv0 = None

                        mid0 = None
                        if bid0 is not None and ask0 is not None and bid0 > 0 and ask0 > 0:
                            mid0 = 0.5 * (bid0 + ask0)
                        elif bid0 is not None and bid0 > 0:
                            mid0 = bid0
                        elif ask0 is not None and ask0 > 0:
                            mid0 = ask0

                        # RELAXED: Allow mid=0 if we have bid or ask
                        if mid0 is None:
                            # Last resort: use bid or ask even if 0
                            if bid0 is not None and bid0 >= 0:
                                mid0 = bid0
                            elif ask0 is not None and ask0 >= 0:
                                mid0 = ask0
                        
                        # Only skip if we truly have no price data
                        if mid0 is None:
                            continue

                        rows.append({"strike": strike0, "bid": bid0, "ask": ask0, "mid": mid0, "iv": iv0})
                    return rows

                chain_data = {
                    expiry: {
                        "calls": _df_to_rows(calls_df),
                        "puts":  _df_to_rows(puts_df),
                    }
                }

                # Build option_chain list for ContractRecommender
                option_chain = []
                for row in chain_data[expiry]["calls"]:
                    option_chain.append({"expiry": expiry, "type": "call", "strike": row["strike"], "mid": row["mid"], "iv": row.get("iv")})
                for row in chain_data[expiry]["puts"]:
                    option_chain.append({"expiry": expiry, "type": "put", "strike": row["strike"], "mid": row["mid"], "iv": row.get("iv")})
                
                # ============================================================
                # FIX 3: DEBUG WHY OPTION_CHAIN IS EMPTY
                # ============================================================
                print(f"📊 OPTION CHAIN DEBUG:")
                print(f"   Expiry: {expiry}")
                print(f"   option_chain length: {len(option_chain)}")
                
                if len(option_chain) == 0:
                    print(f"   ⚠️ EMPTY! Investigating...")
                    
                    # Check if ch0 has data
                    if 'ch0' in locals() and ch0:
                        if hasattr(ch0, 'calls') and hasattr(ch0.calls, 'shape'):
                            print(f"   ch0.calls.shape: {ch0.calls.shape}")
                            print(f"   ch0.calls.empty: {ch0.calls.empty}")
                        else:
                            print(f"   ch0.calls: {type(ch0.calls)}")
                    else:
                        print(f"   ch0 not available")
                    
                    # Check chain_data
                    if expiry in chain_data:
                        calls_count = len(chain_data[expiry]['calls'])
                        puts_count = len(chain_data[expiry]['puts'])
                        print(f"   chain_data[{expiry}]: calls={calls_count}, puts={puts_count}")
                        
                        if calls_count == 0 and puts_count == 0:
                            print(f"   ❌ _df_to_rows() returned empty! Check if mid prices are all <= 0")
                    else:
                        print(f"   ❌ Expiry '{expiry}' not in chain_data keys: {list(chain_data.keys())}")
                else:
                    print(f"   ✅ {len(option_chain)} options available")
                    # Show first option as sample
                    if option_chain:
                        sample = option_chain[0]
                        print(f"   Sample: {sample['type']} ${sample['strike']} @ ${sample['mid']:.2f}")

                # IV Rank fallback
                iv_rank_val = None
                try:
                    iv_rank_val = float((analytics.get("iv_rank") or {}).get("iv_rank"))
                except Exception:
                    iv_rank_val = None
                if iv_rank_val is None:
                    try:
                        iv_rank_val = float(ai.get("iv_rank")) if isinstance(ai, dict) else None
                    except Exception:
                        iv_rank_val = None
                if iv_rank_val is None:
                    iv_rank_val = 0.5

                # IV/HV ratio fallback
                iv_hv_ratio = None
                try:
                    if atm_iv_selected is not None and hv20 is not None and hv20 > 0:
                        iv_hv_ratio = float(atm_iv_selected) / float(hv20)
                except Exception:
                    iv_hv_ratio = None
                if iv_hv_ratio is None:
                    iv_hv_ratio = 1.0

                # ============================================================
                # P1-2 FIX: CANONICAL IV RANK - SINGLE SOURCE OF TRUTH
                # ============================================================
                canonical_iv_rank = None
                canonical_iv_percentile = None

                # Priority 1: From analytics (most reliable)
                if analytics and analytics.get("iv_rank"):
                    canonical_iv_rank = analytics["iv_rank"].get("iv_rank")
                    canonical_iv_percentile = analytics["iv_rank"].get("iv_percentile")

                # Priority 2: From iv_rank_val (computed earlier)
                if canonical_iv_rank is None and 'iv_rank_val' in locals() and iv_rank_val is not None:
                    canonical_iv_rank = iv_rank_val

                # Priority 3: From AI (if available)
                if canonical_iv_rank is None and ai and isinstance(ai, dict):
                    canonical_iv_rank = ai.get("iv_rank")

                # Priority 4: From confidence
                if canonical_iv_rank is None and confidence and isinstance(confidence, dict):
                    canonical_iv_rank = confidence.get("iv_rank")

                # Fallback
                if canonical_iv_rank is None:
                    canonical_iv_rank = 0.5

                # Ensure in 0-1 range (convert from percent if needed)
                if canonical_iv_rank > 1:
                    canonical_iv_rank = canonical_iv_rank / 100

                print(f"📊 Canonical IV Rank: {canonical_iv_rank:.2%} (Percentile: {canonical_iv_percentile if canonical_iv_percentile else 'N/A'})")

                # Use this everywhere instead of iv_rank_val
                iv_rank_val = canonical_iv_rank


                # ============================================================
                # BUILD ENTRY ZONES FOR CONTRACT RECOMMENDER
                # ============================================================
                entry_zones = {
                    'normal': {
                        'low': ai_entry['low'] if ai_entry else S * 0.95,
                        'high': ai_entry['high'] if ai_entry else S * 1.05,
                    },
                    'conservative': {
                        'low': ai_cons_entry['low'] if ai_cons_entry else S * 0.90,
                        'high': ai_cons_entry['high'] if ai_cons_entry else S * 1.00,
                    }
                }

                # ============================================================
                # INSTITUTIONAL ANALYSIS MODULES - FIXED
                # ============================================================
                
                # CRITICAL FIX 1: Define variables BEFORE try block to avoid NameError
                auto_expiry_result = _auto_gate if '_auto_gate' in locals() else {}
                liquidity_grade = 'C'  # Default fallback
                spread_pct = 0.10  # Default fallback
                
                # Initialize all analyzers
                print("🔧 Initializing institutional analysis modules...")
                
                from data.confidence_engine import ConfidenceEngine
                from data.greeks_risk_analyzer import GreeksRiskAnalyzer
                from data.industry_metrics import IndustryMetrics
                from data.reverse_dcf import ReverseDCF
                from data.strategy_optimizer import StrategyOptimizer
                from data.trade_dashboard import TradeDashboard
                from data.volatility_surface_analyzer import VolatilitySurfaceAnalyzer
                
                confidence_engine = ConfidenceEngine()
                greeks_analyzer = GreeksRiskAnalyzer()
                industry_metrics = IndustryMetrics()
                reverse_dcf = ReverseDCF()
                strategy_optimizer = StrategyOptimizer()
                trade_dashboard = TradeDashboard()
                vol_surface_analyzer = VolatilitySurfaceAnalyzer()

                # 1. INSTITUTIONAL CONFIDENCE ENGINE
                institutional_confidence = None
                try:
                    print("🎯 Running institutional confidence engine...")
                    
                    # Prepare liquidity data - FIXED REFERENCES
                    spread_pct = (analytics.get('selected_option') or {}).get('spread_pct', 0.10)
                    liquidity_grade = (auto_info or {}).get('liq_grade') or (auto_info or {}).get('liquidity_grade') or 'C'
                    
                    # CRITICAL FIX 2: Use ch0 instead of undefined 'chain'
                    # Get OI and volume from chain
                    oi_total = 0
                    vol_total = 0
                    if 'ch0' in locals() and ch0 and hasattr(ch0, 'calls'):
                        try:
                            oi_total = ch0.calls['openInterest'].sum() if 'openInterest' in ch0.calls.columns else 0
                            vol_total = ch0.calls['volume'].sum() if 'volume' in ch0.calls.columns else 0
                        except Exception as e:
                            print(f"  Warning: Could not get OI/volume from chain: {e}")
                            oi_total = 0
                            vol_total = 0
                    
                    # ATR bands
                    atr_bands_dict = None
                    if atr14 and S:
                        atr_bands_dict = {
                            'primary': (S - atr14, S + atr14),
                            'secondary': (S - 2*atr14, S + 2*atr14),
                        }
                    
                    # Run institutional confidence engine
                    institutional_confidence = confidence_engine.compute_confidence(
                        # Liquidity
                        spread_pct=spread_pct,
                        liquidity_grade=liquidity_grade,
                        oi_total=float(oi_total) if oi_total else None,
                        vol_total=float(vol_total) if vol_total else None,
                        
                        # Volatility
                        iv_rank=float(iv_rank_val) if iv_rank_val else None,
                        iv_hv_ratio=iv_hv_ratio,
                        atm_iv=atm_iv_selected,
                        hv20=hv20,
                        
                        # Skew (calculate from chain if available)
                        put_skew=None,
                        call_skew=None,
                        
                        # DCF
                        dcf_intrinsic=dcf_result.get('intrinsic') if dcf_result else None,
                        spot_price=S,
                        dcf_gap_pct=None,
                        
                        # Macro
                        macro_regime=macro_snapshot.get('regime_label') if macro_snapshot else None,
                        
                        # Industry
                        industry_cycle='Early Recovery',  # Will get from industry metrics
                        
                        # Technical
                        atr_bands=atr_bands_dict,
                        vwap_anchor=avwap if isinstance(avwap, (int, float)) else None,
                        support_levels=None,
                    )
                    
                    print(f"✅ Institutional Confidence: {institutional_confidence['total_confidence']}/100 (Grade: {institutional_confidence['grade']})")
                    
                    # Apply overlay confidence delta
                    hold_days_for_overlay = planned_days if planned_days > 0 else hold_days
                    delta = overlay_confidence_delta(overlay, hold_days_for_overlay, cap=5)
                    
                    institutional_confidence["total_confidence"] = max(0, min(100, 
                        int(institutional_confidence.get("total_confidence", 50)) + delta))
                    institutional_confidence["overlay_delta"] = delta
                    institutional_confidence["overlay"] = overlay
                    
                    if delta != 0:
                        print(f"📊 Overlay confidence delta: {delta:+d} points")
                    
                    # signals_used: derived from factor_meta in the official confidence dict.
                    # Only factors with status="ok" AND weight>0 appear.
                    # "defaulted" factors are excluded — they contributed neutral noise, not signal.
                    signals_used = []
                    signals_used_display = []
                    _fm = confidence.get("factor_meta", {}) if isinstance(confidence, dict) else {}
                    for _fk, _fm_v in _fm.items():
                        if _fm_v.get("status") == "ok" and _fm_v.get("weight", 0) > 1e-9:
                            signals_used.append(_fk)
                            signals_used_display.append(_fm_v.get("pretty", _fk))
                    print(f"📊 Signals used (from factor_meta): {', '.join(signals_used_display) if signals_used_display else 'none'}")
                    
                except Exception as e:
                    print(f"❌ Institutional confidence engine failed: {e}")
                    import traceback
                    traceback.print_exc()
                    institutional_confidence = None

                # 2. INDUSTRY METRICS (Memory sector)
                industry_analysis = None
                try:
                    if ticker in ['MU', 'WDC', 'STX']:
                        print("🏢 Running industry metrics analysis...")
                        industry_analysis = industry_metrics.get_memory_context(
                            ticker=ticker,
                            current_price=S,
                            company_info=company,
                        )
                        print(f"✅ Industry Analysis: {industry_analysis['overall_signal']}")
                except Exception as e:
                    print(f"❌ Industry metrics failed: {e}")
                    industry_analysis = None

                # 3. REVERSE DCF (What market is pricing)
                reverse_dcf_analysis = None
                try:
                    if dcf_result and company:
                        print("💵 Running reverse DCF analysis...")
                        
                        # ===== Compute minimally-realistic inputs =====
                        rev_growth = company.get("revenue_growth")
                        try:
                            rev_cagr = float(rev_growth) if rev_growth is not None else 0.08
                            rev_cagr = max(-0.20, min(0.40, rev_cagr))
                        except Exception:
                            rev_cagr = 0.08
                        
                        fcf = company.get("free_cash_flow")
                        rev = company.get("revenue")
                        try:
                            fcf_margin = float(fcf) / float(rev) if (fcf and rev) else 0.10
                            fcf_margin = max(-0.10, min(0.35, fcf_margin))
                        except Exception:
                            fcf_margin = 0.10
                        
                        terminal_growth = 0.02
                        if (company.get("sector") or "").lower().find("technology") >= 0:
                            terminal_growth = 0.025
                        
                        dcf_assumptions = {
                            "revenue_cagr": rev_cagr,
                            "terminal_growth": terminal_growth,
                            "fcf_margin": fcf_margin,
                        }
                        
                        reverse_dcf_analysis = reverse_dcf.analyze(
                            current_price=S,
                            current_revenue=company.get('revenue', 30e9),  # Fallback
                            current_margin=company.get('profit_margin', 0.10),
                            current_fcf_margin=fcf_margin,
                            shares_outstanding=company.get('shares_outstanding', 1.1e9),
                            dcf_intrinsic=dcf_result.get('intrinsic', S),
                            dcf_assumptions=dcf_assumptions,
                            current_hbm_mix=0.15 if ticker == 'MU' else None,
                            hbm_tam_growth=0.85 if ticker == 'MU' else None,
                            beta=1.5,
                        )
                        print(f"✅ Reverse DCF: Market pricing {reverse_dcf_analysis['implied_revenue_cagr']}% CAGR")
                        
                        # P1-5 FIX: Format all reverse DCF values to clean precision
                        if reverse_dcf_analysis:
                            # Format prices to 2 decimals
                            if 'current_price' in reverse_dcf_analysis:
                                reverse_dcf_analysis['current_price'] = round(float(reverse_dcf_analysis['current_price']), 2)
                            
                            # Format percentages to 1 decimal
                            for key in ['implied_revenue_cagr', 'implied_margin', 'implied_hbm_mix']:
                                if key in reverse_dcf_analysis and reverse_dcf_analysis[key] is not None:
                                    reverse_dcf_analysis[key] = round(float(reverse_dcf_analysis[key]), 1)
                            
                            # Format other floats to appropriate precision
                            for key, value in reverse_dcf_analysis.items():
                                if isinstance(value, float) and key not in ['current_price', 'implied_revenue_cagr', 'implied_margin', 'implied_hbm_mix']:
                                    # Default to 2 decimals for other values
                                    reverse_dcf_analysis[key] = round(value, 2)
                        
                except Exception as e:
                    print(f"❌ Reverse DCF failed: {e}")
                    reverse_dcf_analysis = None

                # 4. STRATEGY OPTIMIZER (Call spread vs naked call)
                strategy_recommendation = None
                try:
                    # CRITICAL FIX 3: Get ATM option data safely
                    atm_call_price = None
                    otm_call_price = None
                    
                    if 'ch0' in locals() and ch0 and hasattr(ch0, 'calls'):
                        atm_strike = round(S / 5) * 5
                        calls_df = ch0.calls
                        
                        # Find ATM
                        atm_calls = calls_df[calls_df['strike'] == atm_strike]
                        if not atm_calls.empty:
                            bid = atm_calls.iloc[0].get('bid', 0)
                            ask = atm_calls.iloc[0].get('ask', 0)
                            if bid > 0 and ask > 0:
                                atm_call_price = (bid + ask) / 2
                        
                        # Find OTM (15% above)
                        otm_strike = round(S * 1.15 / 5) * 5
                        otm_calls = calls_df[calls_df['strike'] == otm_strike]
                        if not otm_calls.empty:
                            bid = otm_calls.iloc[0].get('bid', 0)
                            ask = otm_calls.iloc[0].get('ask', 0)
                            if bid > 0 and ask > 0:
                                otm_call_price = (bid + ask) / 2
                    
                    if atm_call_price and ai_target_price:
                        print("🎲 Running strategy optimizer...")
                        strategy_recommendation = strategy_optimizer.recommend_strategy(
                            user_stance=view if view else 'bullish',
                            spot=S,
                            target=ai_target_price,
                            entry_zone_avg=(ai_entry['low'] + ai_entry['high']) / 2 if ai_entry else S,
                            iv_rank=float(iv_rank_val) if iv_rank_val else 50,
                            iv_hv_ratio=iv_hv_ratio,
                            iv_percentile=(analytics.get('iv_rank') or {}).get('iv_percentile', 50),
                            atm_call_price=atm_call_price,
                            atm_put_price=None,
                            otm_call_price=otm_call_price,
                            max_budget=float(budget) if budget else None,
                            max_loss=float(max_loss) if max_loss else None,
                            dte=int(days_to_exp) if days_to_exp else 30,
                        )
                        print(f"✅ Strategy Recommendation: {strategy_recommendation['structure']}")
                    else:
                        print(f"  Skipping strategy optimizer: atm_price={atm_call_price}, target={ai_target_price}")
                except Exception as e:
                    print(f"❌ Strategy optimizer failed: {e}")
                    import traceback
                    traceback.print_exc()
                    strategy_recommendation = None

                # 5. TRADE DASHBOARD
                dashboard_data = None
                try:
                    if ai_target_price and ai_entry:
                        print("📊 Generating trade dashboard...")
                        
                        # CRITICAL FIX 4: Use variables that are guaranteed to exist
                        expiry_quality = 0.5
                        if 'auto_info' in locals() and auto_info:
                            expiry_quality = (auto_info.get('score') or 0.5)
                        
                        # P1-1 FIX: Ensure implied move is in percent units (not decimal)
                        implied_move_30d_pct = (hv20 * math.sqrt(30/365) * 100) if hv20 else 10.0
                        hv20_expected_pct = (hv20 * math.sqrt(days_to_exp/365) * 100) if (hv20 and days_to_exp) else 10.0
                        
                        dashboard_data = trade_dashboard.generate_dashboard(
                            spot=S,
                            target_price=ai_target_price,
                            entry_normal_avg=ai_entry['avg'] if ai_entry else S,
                            entry_conservative_avg=ai_cons_entry['avg'] if ai_cons_entry else S * 0.92,
                            iv_rank=float(iv_rank_val) if iv_rank_val else 50,
                            iv_percentile=(analytics.get('iv_rank') or {}).get('iv_percentile', 50),
                            implied_move_30d=implied_move_30d_pct,  # Already in percent
                            hv20_expected=hv20_expected_pct,  # Already in percent
                            iv_hv_ratio=iv_hv_ratio,
                            liquidity_grade=liquidity_grade,
                            expiry_quality_score=expiry_quality,
                            spread_pct=spread_pct,
                            confidence=institutional_confidence['total_confidence'] if institutional_confidence else 50,
                        )
                        print(f"✅ Trade Dashboard: R/R = {dashboard_data['entry_rr']}")
                    else:
                        print(f"  Skipping trade dashboard: target={ai_target_price}, ai_entry={bool(ai_entry)}")
                except Exception as e:
                    print(f"❌ Trade dashboard failed: {e}")
                    import traceback
                    traceback.print_exc()
                    dashboard_data = None

                # 6. VOLATILITY SURFACE ANALYZER
                vol_surface_analysis = None
                try:
                    if atm_iv_selected:
                        print("📈 Analyzing volatility surface...")
                        vol_surface_analysis = vol_surface_analyzer.analyze_skew(
                            atm_iv=atm_iv_selected,
                            user_stance=view if view else 'bullish',
                        )
                        if vol_surface_analysis.get('available'):
                            print(f"✅ Vol Surface: {vol_surface_analysis['skew_shape']}")
                except Exception as e:
                    print(f"❌ Vol surface analyzer failed: {e}")
                    vol_surface_analysis = None

                print(f"✅ All institutional modules executed")

                # ============================================================
                # TOP 3 CONTRACT RECOMMENDATIONS (FIXED!)
                # ============================================================
                top3_contracts = []
                # Deterministic target for contract selection (NO AI dependency)
                det_target_price = None
                try:
                    det_target_price = ((peer_snapshot or {}).get("model_target") or {}).get("value", None)
                except Exception:
                    det_target_price = None

                # fallback: DCF intrinsic if available
                if det_target_price is None and isinstance(dcf_result, dict):
                    try:
                        det_target_price = dcf_result.get("intrinsic", None)
                    except Exception:
                        det_target_price = None

                # last resort: small directional nudge from spot
                if det_target_price is None:
                    if (view or "").lower() in ("bearish", "bear"):
                        det_target_price = float(S) * 0.90
                    else:
                        det_target_price = float(S) * 1.10

                try:
                    # PHASE 3 UPGRADE: Generate Top 3 regardless of liquidity (show with warnings)
                    if option_chain and budget and max_loss and (det_target_price is not None):
                        print("🎯 Generating Top 3 contract recommendations...")
                        print(f"   Inputs: spot=${S}, target=${det_target_price}, budget=${budget}, max_loss=${max_loss}")
                        
                        if liquidity_blocked:
                            print(f"   ⚠️ WARNING: Liquidity gate triggered ({liquidity_block_reason})")
                            print(f"   Continuing with recommendations for educational purposes...")


                        # Initialize ContractRecommender (NO ARGUMENTS!)
                        rec = ContractRecommender()
                        
                        # Call with CORRECT parameters
                        top3_contracts = rec.recommend_top3(
                            spot=float(S),
                            target_price=float(det_target_price),
                            entry_zones=entry_zones,  # ✅ FIXED: Pass dict
                            option_chain=option_chain,  # ✅ FIXED: Add option_chain
                            user_stance=view if view else 'bullish',  # ✅ FIXED: Add stance
                            expiry=expiry if expiry else '2026-03-27',  # ✅ FIXED: Add expiry
                            dte=int(days_to_exp) if days_to_exp else 30,  # ✅ FIXED: Renamed from days_to_exp
                            iv_rank=float(iv_rank_val) if iv_rank_val else 0.5,
                            iv_hv_ratio=float(iv_hv_ratio),
                            max_budget=float(budget),  # ✅ FIXED: Renamed from budget
                            max_loss=float(max_loss),
                        )
                        
                        print(f"✅ Generated {len(top3_contracts)} contract recommendations")
                        
                        # Add Greeks risk analysis to each contract
                        for contract in top3_contracts:
                            try:
                                greeks_risk = greeks_analyzer.analyze_greeks_risk(
                                    strike=contract['strike'],
                                    spot=S,
                                    option_price=contract['price'],
                                    option_type=contract['type'],
                                    delta=contract['delta'],
                                    gamma=contract['gamma'],
                                    theta=contract['theta'],
                                    vega=contract['vega'],
                                    iv=contract.get('iv', 0.50),
                                    iv_rank=float(iv_rank_val) if iv_rank_val else 50,
                                    contracts=1,
                                )
                                contract['greeks_risk'] = greeks_risk
                                print(f"   ✅ Greeks risk for ${contract['strike']} {contract['type']}: {greeks_risk['overall_risk']}")
                            except Exception as e:
                                print(f"   ❌ Greeks risk analysis failed for contract: {e}")
                                contract['greeks_risk'] = None
                        
                    else:
                        skip_reasons = []
                        if not option_chain: skip_reasons.append("option_chain empty")
                        if not budget: skip_reasons.append("budget missing")
                        if not max_loss: skip_reasons.append("max_loss missing")
                        if det_target_price is None: skip_reasons.append("target_price missing")
                        print(f"⚠️ Skipping ContractRecommender: {', '.join(skip_reasons)}")
                        print(f"   option_chain={len(option_chain) if option_chain else 0} options, budget=${budget}, max_loss=${max_loss}, target=${det_target_price}")
                        
                except Exception as e:
                    print(f"❌ ContractRecommender failed: {e}")
                    import traceback
                    traceback.print_exc()
                    top3_contracts = []

        except Exception as e:
            print(f"⚠️ top3_contracts/chain_data build failed: {e}")
            import traceback
            traceback.print_exc()
            top3_contracts = []
            chain_data = {}
            # Reset all institutional analysis on error
            institutional_confidence = None
            industry_analysis = None
            reverse_dcf_analysis = None
            strategy_recommendation = None
            dashboard_data = None
            vol_surface_analysis = None


        # Options recos (uses chain_data)
        try:
            if budget and max_loss:
                options_recos = recommend_contracts_simple(
                    ticker, S, view,
                    float(budget), float(max_loss),
                    chain_data,
                    confidence,
                    None,
                )
        except Exception as e:
            print(f"⚠️ options_recos failed: {e}")
            options_recos = []

    # Build price guidance from AI confidence
    price_guidance_engine = None
    price_guidance_normal = None
    price_guidance_conservative = None
    price_guidance_reasons = []
    
    if isinstance(confidence, dict) and confidence.get('entry_price_low'):
        try:
            el = float(confidence['entry_price_low'])
            eh = float(confidence['entry_price_high'])
            cl = float(confidence['conservative_entry_low'])
            ch = float(confidence['conservative_entry_high'])
            
            price_guidance_engine = {
                "base_case": round((el + eh) / 2, 2),
                "bull_extension": round(eh, 2),
                "bear_extension": round(el, 2),
                "conservative_case": round((cl + ch) / 2, 2),
                "reasoning": {
                    "macro_regime": (macro_snapshot or {}).get('regime_label', 'Neutral'),
                    "total_width": round(eh - el, 2),
                    "source": "AI Gemini" if confidence.get('gemini_used') else "Formula",
                    "earnings_adj": 0,
                    "vol_spread": round(eh - el, 2),
                }
            }
            
            price_guidance_normal = {
                "bear": round(el, 2),
                "base": round((el + eh) / 2, 2),
                "bull": round(eh, 2),
                "avg": round((el + eh) / 2, 2),
            }
            
            price_guidance_conservative = {
                "bear": round(cl, 2),
                "base": round((cl + ch) / 2, 2),
                "bull": round(ch, 2),
                "avg": round((cl + ch) / 2, 2),
            }
            
            price_guidance_reasons = [
                f"AI-derived from {confidence.get('confidence', 50)}% confidence",
                f"Normal range: ${el:.2f} - ${eh:.2f}",
                f"Conservative range: ${cl:.2f} - ${ch:.2f}",
            ]
        except Exception as e:
            print(f"Price guidance engine build failed: {e}")

    # =========================
    # Phase 10: Price guidance (options mode)
    # =========================
    conf_01 = None
    try:
        conf_01 = conclusion.get("confidence")
    except Exception:
        conf_01 = None


    entry_low, entry_high, entry_reasons = entry_zone_from_peers(
        S,
        peer_snapshot,
        hv20,
        hv60,
        conf_01,
        view=view,
    )

    scenarios = scenario_bands(
        S,
        planned_days,
        hv20,
        hv60,
    )

    # =========================
    # Phase 13: Execution bands (options mode)
    # =========================
    # =========================
    # Phase 13C: liquidity-aware factor for execution bands (options mode)
    # Prefer best-expiry liquidity metrics from auto_info if available.
    # Fallback to current-strike spread/liquidity gate.
    # =========================
    liq_metrics_for_bands = None
    try:
        if isinstance(auto_info, dict) and isinstance(auto_info.get("metrics"), dict):
            liq_metrics_for_bands = auto_info.get("metrics")
        else:
            liq_metrics_for_bands = {"spread_pct": spread_pct, "liq_ok": liq_ok}
    except Exception:
        liq_metrics_for_bands = {"spread_pct": spread_pct, "liq_ok": liq_ok}

    exec_bands = execution_bands(
        S,
        atr14,
        atr20,
        conf_01,
        view=view,
        alpha_regime=alpha_regime,
        liquidity_metrics=liq_metrics_for_bands,
        confidence_regime=confidence,  # Pass new confidence dict (kept param name for backward compat)
    )

    primary_entry = None
    if exec_bands and entry_low is not None and entry_high is not None:
        lo = max(entry_low, exec_bands["primary"]["low"])
        hi = min(entry_high, exec_bands["primary"]["high"])
        if lo <= hi:
            primary_entry = {"low": round(lo, 2), "high": round(hi, 2)}


    # =========================
    # Adaptive DCF (for options mode too)
    # =========================
    adaptive_dcf = calculate_adaptive_dcf_weight(
        dcf_intrinsic=dcf_result.get('intrinsic') if dcf_result else None,
        spot=S,
        view=view,
    )

    # Format DCF display context
    dcf_display = format_dcf_display_context(
        dcf_result=dcf_result,
        spot=S,
        view=view,
        adaptive_dcf=adaptive_dcf,
        company_snapshot=company_chain,
    )

    # =========================
    # AI guidance helpers for template
    # =========================
#     ai_entry = None
#     ai_cons_entry = None
#     ai_overall_avg = None
#     ai_target_price = None
#     try:
#         if isinstance(confidence, dict):
#             ai_entry = confidence.get('entry_range')
#             ai_cons_entry = confidence.get('conservative_entry')
#             ai_overall_avg = confidence.get('overall_avg')
#             ai_target_price = confidence.get('target_price')
#     except Exception:
#         pass
    # If AI didn't provide target price, fall back to deterministic base scenario exit if available.
    if ai_target_price is None:
        try:
            ai_target_price = float(scenarios.get('base')) if isinstance(scenarios, dict) and scenarios.get('base') is not None else None
        except Exception:
            ai_target_price = None

    # Options contract recommendations (uses budget/max_loss) — only for options mode.
    options_recos = []
    if analysis_mode == 'options':
        try:
            if (not liquidity_blocked) and budget and max_loss and expiry and expiry != 'N/A':
                from data.price_guidance import recommend_options_contracts  # adjust path if needed

                options_recos = recommend_options_contracts(
                    t=t,
                    expiry=expiry,
                    view=view,
                    S=S,
                    r=r,
                    sigma_forecast=sigma_forecast,
                    budget=budget,
                    max_loss=max_loss,
                    top_n=5
                )
        except Exception:
            options_recos = []

    # Hide deterministic price guidance card when AI guidance is available (AI section replaces it).
    show_price_guidance = bool(price_guidance_engine) and not (isinstance(ai, dict) and ai.get("available"))

    # =========================
    # Deterministic model target for template (peer-band derived)
    # =========================
    model_target_price = None
    try:
        model_target_price = ((peer_snapshot or {}).get("model_target") or {}).get("value", None)
    except Exception:
        model_target_price = None

    # ============================================================
    # Phase 3: Deterministic Institutional Execution Plan
    # ============================================================

    execution_plan = None

    if analysis_mode == "options" and not liquidity_blocked and expiry and budget and max_loss and top3_contracts:

        # Build candidate sizing rows from Top 3 (canonical deterministic surface)
        candidates = []
        for c in top3_contracts:
            try:
                rank = int(c.get("rank", 999))
                opt_type = (c.get("type") or "").lower()  # "call" / "put"
                strike = float(c.get("strike"))
                premium = float(c.get("price"))  # per-share option price

                if premium <= 0:
                    continue

                cost_per_contract = premium * 100.0
                contracts_budget = int(float(budget) // cost_per_contract) if cost_per_contract > 0 else 0
                contracts_risk = int(float(max_loss) // cost_per_contract) if cost_per_contract > 0 else 0
                contracts = max(0, min(contracts_budget, contracts_risk))

                breakeven = (strike + premium) if opt_type == "call" else (strike - premium)

                delta = float(c.get("delta", 0.0) or 0.0)
                delta_exposure = delta * contracts * 100.0

                candidates.append({
                    "rank": rank,
                    "type": opt_type,
                    "structure": "Long Call" if opt_type == "call" else "Long Put",
                    "expiry": expiry,
                    "strike": strike,
                    "premium": premium,
                    "cost_per_contract": cost_per_contract,
                    "contracts": contracts,
                    "contracts_budget": contracts_budget,
                    "contracts_risk": contracts_risk,
                    "total_cost": contracts * cost_per_contract,
                    "max_loss": contracts * cost_per_contract,
                    "breakeven": breakeven,
                    "delta_exposure": delta_exposure,
                    "max_loss_pct_budget": (contracts * cost_per_contract / float(budget) * 100.0) if float(budget) > 0 else None,
                })

            except Exception:
                continue

        # Sort by rank (1 best)
        candidates = sorted(candidates, key=lambda x: x.get("rank", 999))

        # Select first candidate that can afford >= 1 contract
        selected = None
        for row in candidates:
            if row.get("contracts", 0) >= 1:
                selected = row
                break

        if selected:
            execution_plan = {
                "trade_allowed": True,
                "selected": selected,
                "candidates": candidates,
            }
        else:
            execution_plan = {
                "trade_allowed": False,
                "reason": "Insufficient budget or max_loss for 1 contract (across top candidates)",
                "candidates": candidates,
            }


    # ── AI–Model Divergence Risk Multiplier ─────────────────────────────
    _ac_div = _build_ai_conviction_safe(ai if 'ai' in locals() and isinstance(ai, dict) else None, final_confidence)
    _div_score = _ac_div.score_0_100 if (_ac_div and _ac_div.available and _ac_div.score_0_100 is not None) else None
    divergence_flag = "aligned"
    divergence_size_multiplier = 1.0
    divergence_abs = 0
    if _div_score is not None:
        divergence_abs = abs(_div_score - final_confidence)
        if divergence_abs >= 25:
            divergence_flag = "high"
            divergence_size_multiplier = 0.85
        elif divergence_abs >= 15:
            divergence_flag = "moderate"
        else:
            divergence_flag = "aligned"
    _overlay_size_mult = risk_adj.get("size_multiplier", 1.0)
    final_size_multiplier = round(_overlay_size_mult * divergence_size_multiplier, 4)
    if divergence_flag == "high":
        print(f"⚠️ AI–Model divergence HIGH (Δ{divergence_abs}) → size {_overlay_size_mult:.2f}x × 0.85 = {final_size_multiplier:.2f}x")
    risk_adj["size_multiplier"] = final_size_multiplier
    risk_adj["divergence_flag"] = divergence_flag
    risk_adj["divergence_abs"] = divergence_abs
    risk_adj["divergence_size_multiplier"] = divergence_size_multiplier
    # ────────────────────────────────────────────────────────────────────

    ctx = {
        "request": request,
        "error": None,
        "analysis_mode": analysis_mode,
        
        "ticker": ticker,
        "spot": S,
        
        "earnings_track": earnings_track,
        
        "atr14": atr14,
        "atr20": atr20,
        "anchored_vwap": avwap,
        "exec_bands": exec_bands,
        "primary_entry": primary_entry,
        
        "hv20": hv20,
        "hv60": hv60,
        "sigma_choice": sigma_choice,
        "sigma_forecast": sigma_forecast,
        
        "company": company,
        "headlines": headlines,
        
        # UI inputs
        "budget": budget,
        "max_loss": max_loss,
        "view": view,
        "hold_days": hold_days,
        "planned_days": planned_days,
        "planned_hold_days": planned_hold_days,
        
        # P1-1 FIX: Explicit horizon separation
        "trade_horizon_days": planned_days if planned_days else int(hold_days),  # Actual trade plan
        "fundamental_horizon_months": 12,  # Long-term thesis (always 12-24m)
        
        "cluster": cluster,
        "peers": peers,
        "peer_snapshot": peer_snapshot,
        
        "alpha_snapshot": alpha_snapshot,
        "alpha_regime": alpha_regime,
        
        "width": width,
        "horizon": horizon,
        
        # Options-specific fields
        "opt_type": opt_type,
        "expiry": expiry,
        "strike": strike,
        "bid": bid,
        "ask": ask,
        "mid": mid,
        "r": r,
        "theo": theo,
        "delta": delta,
        "gamma": gamma,
        "vega": vega,
        "gap_pct": gap_pct,
        "label": label,
        "spread_pct": spread_pct,
        "liq_ok": liq_ok,
        "contract_cost": contract_cost,
        "max_contracts_budget": max_contracts_budget,
        
        "auto_expiry": bool(auto_expiry),
        "auto_info": auto_info,
        "suggested_dte": suggested_dte if 'suggested_dte' in locals() else None,  # P0-2 FIX
        "auto_curve_json": json.dumps(auto_info.get("curve", [])) if auto_info else "[]",

        "liquidity_blocked": liquidity_blocked,
        "debug_ai": debug_ai,
        "liquidity_block_reason": liquidity_block_reason,
        "liquidity_gate": liquidity_gate if 'liquidity_gate' in locals() else None,  # P0-1 FIX: Full unified object
        
        "conclusion": conclusion,
        # ── ConfidenceV3 canonical pipeline (options mode) ──────────────────
        # Build the canonical V3 object once, flatten for template use.
        "confidence": _build_options_confidence_v3(
            options_option_a_dict if 'options_option_a_dict' in locals() else {},
            final_confidence,
            overlay,
            (institutional_confidence or {}).get("overlay_delta", 0) if 'institutional_confidence' in locals() else 0,
        ),
        "legacy_confidence": confidence,  # Keep for debugging
        
        # ADVANCED OVERLAY: Risk plan adjustments
        "overlay": overlay,
        "risk_adj": risk_adj,
        "base_confidence": base_confidence,
        "final_confidence": final_confidence,
        
        "qualitative_proxy": qualitative_proxy_result if 'qualitative_proxy_result' in locals() else None,
        "model_target_price": model_target_price,
        
        # DCF / Valuation
        "dcf": dcf_result,
        "adaptive_dcf": adaptive_dcf,
        "dcf_display": dcf_display,
        "dcf_weight_display_pct": dcf_weight_display_pct if 'dcf_weight_display_pct' in locals() else None,
        
        # Price guidance outputs
        "fair_value_zone": fair_value_zone if 'fair_value_zone' in locals() else {},
        "exit_scenarios": scenarios,
        "entry_zone": {
            "low": entry_low,
            "high": entry_high,
            "reasons": entry_reasons,
        },
        "entry_zone_conservative": entry_zone_conservative if 'entry_zone_conservative' in locals() else None,
        "price_guidance_normal": price_guidance_normal if 'price_guidance_normal' in locals() else None,
        "price_guidance_conservative": price_guidance_conservative if 'price_guidance_conservative' in locals() else None,
        "price_guidance_reasons": price_guidance_reasons if 'price_guidance_reasons' in locals() else [],
        "price_guidance_engine": price_guidance_engine if 'price_guidance_engine' in locals() else None,
        "show_price_guidance": True if ('price_guidance_engine' in locals() and price_guidance_engine) else False,
        
        # Macro + events
        "macro_snapshot": macro_snapshot,
        "earnings_info": earnings_info,
        "earnings_move_stats": earnings_move_stats if 'earnings_move_stats' in locals() else {},
        
        "max_spread_pct": max_spread_pct,
        "ai_entry": ai_entry, 
        "ai_cons_entry": ai_cons_entry, 
        "ai_overall_avg": ai_overall_avg, 
        "ai_target_price": ai_target_price, 
        "options_recos": options_recos,
        "top3_contracts": top3_contracts,
        "execution_plan": execution_plan,

        # CRITICAL FIX: Add ai variable so template can see it
        # AI Conviction (secondary - never drives risk controls)
        "ai_conviction": _build_ai_conviction_safe(ai if 'ai' in locals() else None, final_confidence),
        "divergence_flag": risk_adj.get("divergence_flag", "aligned"),
        "divergence_abs": risk_adj.get("divergence_abs", 0),
        "divergence_size_multiplier": risk_adj.get("divergence_size_multiplier", 1.0),
        "final_size_multiplier": risk_adj.get("size_multiplier", 1.0),

        "ai": ai if 'ai' in locals() else None,
        
        # P0-4 FIX: Target guardrail context variables
        "target_price_final": target_price_final if 'target_price_final' in locals() else ai_target_price,
        "target_caps": target_caps if 'target_caps' in locals() else None,
        "target_price_ai_raw": target_price_ai_raw if 'target_price_ai_raw' in locals() else None,
        
        "institutional_confidence": institutional_confidence if 'institutional_confidence' in locals() else None,
        "signals_used": signals_used_display if 'signals_used_display' in locals() else (signals_used if 'signals_used' in locals() else []),
        # factor_meta must come from options_option_a_dict — the raw Option A dict
        # that still has factor_meta before v3 conversion strips it.
        # "confidence" in this ctx is the v3 result (no factor_meta).
        "factor_meta": options_option_a_dict.get("factor_meta", {}) if 'options_option_a_dict' in locals() else {},
        "industry_analysis": industry_analysis if 'industry_analysis' in locals() else None,
        "reverse_dcf_analysis": reverse_dcf_analysis if 'reverse_dcf_analysis' in locals() else None,
        "strategy_recommendation": strategy_recommendation if 'strategy_recommendation' in locals() else None,
        "dashboard_data": dashboard_data if 'dashboard_data' in locals() else None,
        "vol_surface_analysis": vol_surface_analysis if 'vol_surface_analysis' in locals() else None,
    }

    analytics["alpha_snapshot"] = alpha_snapshot
    analytics["alpha_regime"] = alpha_regime

    # merge all charts/analytics in one shot
    ctx.update(analytics)

    # Return raw JSON if requested
    if raw == 1:
        from fastapi.responses import JSONResponse
        # Remove non-serializable objects
        json_ctx = {k: v for k, v in ctx.items() if k != "request"}
        return JSONResponse(content=json_ctx)

    # DEBUG: Check what template receives
    print(f"\n{'='*60}")
    print(f"🔍 TEMPLATE RECEIVES:")
    print(f"   ai exists: {'ai' in ctx}")
    if 'ai' in ctx and ctx['ai']:
        print(f"   ai['available']: {ctx['ai'].get('available')}")
    print(f"   institutional_confidence exists: {'institutional_confidence' in ctx}")
    print(f"{'='*60}\n")

    return templates.TemplateResponse("report.html", ctx)


# =========================
# APIs (JSON)
# =========================

@app.get("/api/semis/universe")
def semis_universe_api(
    q: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=500),
    refresh: int = Query(default=0),
):
    results = search_semis_universe(
        q=(q or ""),
        limit=int(limit),
        force_refresh=bool(refresh),
    )
    return {"count": len(results), "results": results}


@app.get("/api/semis/profile/{ticker}")
def semis_profile(ticker: str):
    ticker = ticker.strip().upper()
    t = yf.Ticker(ticker)
    hist = t.history(period="1y")

    if hist is None or hist.empty:
        raise HTTPException(status_code=404, detail=f"No price history for {ticker}")

    close = hist["Close"].dropna()
    if close.empty:
        raise HTTPException(status_code=404, detail=f"No close prices for {ticker}")

    last = float(close.iloc[-1])
    hi_1y = float(close.max())
    lo_1y = float(close.min())

    hv20 = realized_vol(close, 20)
    hv60 = realized_vol(close, 60)

    info = {}
    try:
        info = t.info or {}
    except Exception:
        info = {}

    name = info.get("longName") or info.get("shortName") or ticker
    market_cap = info.get("marketCap")
    pe = info.get("trailingPE")

    return {
        "ticker": ticker,
        "name": name,
        "last": last,
        "high_1y": hi_1y,
        "low_1y": lo_1y,
        "hv20": hv20,
        "hv60": hv60,
        "market_cap": market_cap,
        "trailing_pe": pe,
        "asof_utc": datetime.now(timezone.utc).isoformat(),
    }


@app.get("/api/semis/peers/{ticker}")
def semis_peers(ticker: str):
    ticker = ticker.strip().upper()
    cluster_name = None
    peers = []
    for cname, members in CLUSTERS.items():
        if ticker in members:
            cluster_name = cname
            peers = members
            break
    return {"ticker": ticker, "cluster": cluster_name, "peers": peers}

@app.get("/api/semis/peer_snapshot/{ticker}")
def semis_peer_snapshot(ticker: str, refresh: int = Query(0, ge=0, le=1)):
    ticker = ticker.strip().upper()

    # resolve cluster/peers
    cluster_name = None
    peers = []
    for cname, members in CLUSTERS.items():
        if ticker in members:
            cluster_name = cname
            peers = members
            break

    key = f"peer_snapshot:{ticker}"
    if refresh:
        snap = build_peer_snapshot(ticker, peers, cluster=cluster_name)
        PEER_CACHE.set(key, snap, ttl_sec=30 * 60)
        return snap

    return PEER_CACHE.get_or_set(
        key,
        lambda: build_peer_snapshot(ticker, peers, cluster=cluster_name),
        ttl_sec=30 * 60,
    )


@app.get("/api/semis/expiries/{ticker}")
def semis_expiries(
    ticker: str,
    horizon: str | None = Query(default=None, description="short/swing/long"),
):
    ticker = ticker.strip().upper()
    t = yf.Ticker(ticker)

    expiries = list(t.options or [])
    out = [{"expiry": e, "dte": _days_to_exp(e)} for e in expiries]
    out.sort(key=lambda x: x["dte"])

    if horizon and horizon in HORIZONS:
        mn, mx = HORIZONS[horizon]
        out = [x for x in out if mn <= x["dte"] <= mx]

    return {"ticker": ticker, "count": len(out), "results": out}

@app.get("/api/semis/options/{ticker}")
def semis_options(
    ticker: str,
    expiry: str = Query(..., description="YYYY-MM-DD"),
    width: int = Query(10, ge=2, le=500),
    full_chain: int = Query(0, ge=0, le=1),
    r: float = Query(0.03, ge=-0.05, le=0.2),
    liquid_only: int = Query(0, ge=0, le=1),
    max_spread_pct: float = Query(0.20, ge=0.0, le=2.0),
    auto_expiry: int = Query(0, ge=0, le=1),
    horizon: str = Query("short"),
    strike_limit: int = Query(800, ge=50, le=5000),
):
    ticker = ticker.strip().upper()

    t = yf.Ticker(ticker)
    hist = t.history(period="5d")
    if hist is None or hist.empty or hist["Close"].dropna().empty:
        raise HTTPException(status_code=404, detail=f"No price data for {ticker}")
    S = float(hist["Close"].dropna().iloc[-1])

    auto_info = None
    if auto_expiry:
        auto_info = auto_pick_expiry(ticker, t, S, horizon=horizon, width=width)
        if auto_expiry:
            expiry = auto_info["suggested_expiry"]

    try:
        chain = cached_option_chain(ticker, expiry)
    except Exception:
        raise HTTPException(status_code=404, detail=f"Options expiry not found: {expiry}")

    calls = chain.calls.copy()
    puts = chain.puts.copy()
    if calls is None or calls.empty:
        raise HTTPException(status_code=404, detail=f"No calls found for {ticker} {expiry}")
    if puts is None or puts.empty:
        raise HTTPException(status_code=404, detail=f"No puts found for {ticker} {expiry}")

    exp_dt = datetime.strptime(expiry, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    now = datetime.now(timezone.utc)
    days_to_exp = max((exp_dt - now).days, 0)
    T = max(days_to_exp / 365.0, 1e-6)

    # ATM strike (from calls)
    calls["abs_moneyness"] = (calls["strike"] - S).abs()
    atm_strike = float(calls.sort_values("abs_moneyness").iloc[0]["strike"])

    # --- strikes selection: windowed (default) or "show all" centered around ATM ---
    strikes = sorted(set(calls["strike"].tolist()) | set(puts["strike"].tolist()))
    idx = min(range(len(strikes)), key=lambda i: abs(strikes[i] - atm_strike))

    if not full_chain:
        lo = max(0, idx - width)
        hi = min(len(strikes), idx + width + 1)
        keep_strikes = set(strikes[lo:hi])
    else:
        if len(strikes) <= strike_limit:
            keep_strikes = set(strikes)
        else:
            half = strike_limit // 2
            lo = max(0, idx - half)
            hi = min(len(strikes), idx + half + 1)

            while (hi - lo) < strike_limit and lo > 0:
                lo -= 1
            while (hi - lo) < strike_limit and hi < len(strikes):
                hi += 1

            keep_strikes = set(strikes[lo:hi])

    calls = calls[calls["strike"].isin(keep_strikes)].copy()
    puts = puts[puts["strike"].isin(keep_strikes)].copy()

    def enrich(df: pd.DataFrame, opt_type: str):
        out = []
        for _, row in df.iterrows():
            K = float(row["strike"])
            bid = _to_float(row.get("bid"), 0.0)
            ask = _to_float(row.get("ask"), 0.0)
            lastp = _to_float(row.get("lastPrice"), 0.0)
            open_interest = _to_int(row.get("openInterest"), 0)
            volume = _to_int(row.get("volume"), 0)

            has_two_sided = (bid > 0 and ask > 0)

            # IMPORTANT: count one-sided bid/ask as "has_quotes" too
            has_quotes = (bid > 0) or (ask > 0) or (lastp > 0) or (open_interest > 0) or (volume > 0)

            # mid selection with one-sided fallback
            if bid > 0 and ask > 0:
                mid = (bid + ask) / 2.0
                price_source = "mid"
            elif bid > 0 and ask <= 0:
                mid = bid
                price_source = "bid"
            elif ask > 0 and bid <= 0:
                mid = ask
                price_source = "ask"
            elif lastp > 0:
                mid = lastp
                price_source = "last"
            else:
                mid = None
                price_source = None

            iv = delta = gamma = vega = spread_pct = None

            if mid is not None and mid > 0:
                iv_calc = implied_vol_from_price(mid, S, K, T, r, opt_type)
                if (iv_calc is not None) and (not math.isnan(iv_calc)) and (not math.isinf(iv_calc)) and iv_calc > 0:
                    iv = float(iv_calc)
                    d, g, v = bs_greeks(S, K, T, r, iv, opt_type)
                    delta = float(d) if not (math.isnan(d) or math.isinf(d)) else None
                    gamma = float(g) if not (math.isnan(g) or math.isinf(g)) else None
                    vega = float(v) if not (math.isnan(v) or math.isinf(v)) else None

            if has_two_sided and mid is not None and mid > 0:
                sp = (ask - bid) / mid
                spread_pct = float(sp) if not (math.isnan(sp) or math.isinf(sp)) else None

            liq_ok = (spread_pct is not None and spread_pct <= max_spread_pct)

            out.append({
                "strike": K,
                "bid": bid if bid > 0 else None,
                "ask": ask if ask > 0 else None,
                "last": lastp if lastp > 0 else None,
                "mid": mid,
                "open_interest": open_interest,
                "volume": volume,
                "iv": iv,
                "delta": delta,
                "gamma": gamma,
                "vega": vega,
                "spread_pct": spread_pct,
                "has_quotes": has_quotes,
                "has_two_sided": has_two_sided,
                "price_source": price_source,
                "liq_ok": liq_ok,
            })
        return out

    all_calls = enrich(calls, "call")
    all_puts = enrich(puts, "put")
    all_opts = all_calls + all_puts

    # Apply optional "liquid_only" filter
    if liquid_only:
        calls_out = [x for x in all_calls if x.get("has_two_sided") and (x.get("spread_pct") is not None) and x["spread_pct"] <= max_spread_pct]
        puts_out  = [x for x in all_puts  if x.get("has_two_sided") and (x.get("spread_pct") is not None) and x["spread_pct"] <= max_spread_pct]
        if not calls_out:
            calls_out = [x for x in all_calls if x.get("has_quotes")]
        if not puts_out:
            puts_out = [x for x in all_puts if x.get("has_quotes")]
    else:
        calls_out = all_calls
        puts_out = all_puts

    def _nearest_atm(options_list):
        candidates = [x for x in options_list if x.get("iv") is not None]
        if not candidates:
            return None
        return min(candidates, key=lambda x: abs(x["strike"] - S))

    atm_call = _nearest_atm(all_calls)
    atm_put = _nearest_atm(all_puts)

    atm_call_iv = atm_call["iv"] if atm_call else None
    atm_put_iv = atm_put["iv"] if atm_put else None
    skew_atm = (atm_put_iv - atm_call_iv) if (atm_put_iv is not None and atm_call_iv is not None) else None

    quoted = [x for x in all_opts if x.get("has_quotes")]
    liq_ok_list = [x for x in quoted if x.get("liq_ok")]
    spreads = [x["spread_pct"] for x in quoted if x.get("spread_pct") is not None]

    pct_quoted = (len(quoted) / len(all_opts)) if all_opts else None
    pct_liq_ok = (len(liq_ok_list) / len(all_opts)) if all_opts else None
    median_spread = float(np.median(spreads)) if spreads else None

    payload = {
        "ticker": ticker,
        "spot": S,
        "expiry": expiry,
        "days_to_exp": days_to_exp,
        "r": r,
        "atm_strike": atm_strike,
        "liquid_only": bool(liquid_only),
        "auto_info": auto_info,
        "summary": {
            "atm_call_strike": atm_call["strike"] if atm_call else None,
            "atm_put_strike": atm_put["strike"] if atm_put else None,
            "atm_call_iv": atm_call_iv,
            "atm_put_iv": atm_put_iv,
            "atm_skew_put_minus_call": skew_atm,
            "pct_with_quotes": pct_quoted,
            "pct_liq_ok": pct_liq_ok,
            "median_spread_pct": median_spread,
        },
        "calls": calls_out,
        "puts": puts_out,

        # DEBUG COUNTS (super helpful)
        "debug": {
            "calls_rows": len(all_calls),
            "puts_rows": len(all_puts),
            "total_rows": len(all_opts),
            "quoted_rows": len(quoted),
            "liq_ok_rows": len(liq_ok_list),
            "full_chain": int(full_chain),
            "strike_limit": int(strike_limit),
            "width": int(width),
        },
    }

    return sanitize(payload)


# =========================
# AI Chat Guardrails Cache
# =========================
AI_CHAT_GATES = {}  # { "TICKER": {"blocked": bool, "reason": str} }

# =========================
# AI Chat API (Gemini)
# =========================
class AIChatPayload(BaseModel):
    ticker: str
    question: str

@app.post("/api/ai/chat")
def api_ai_chat(payload: AIChatPayload):
    """Follow-up Q&A about the generated report."""
    try:
        tkr = (payload.ticker or "").strip().upper()
        q = (payload.question or "").strip()
        if not tkr or not q:
            return JSONResponse({"error": "Missing ticker or question."}, status_code=400)
        
        gate = AI_CHAT_GATES.get(tkr, None)
        if gate and gate.get("blocked"):
            reason = gate.get("reason") or "Liquidity failed institutional filter."
            return {
                "answer": (
                    "🚫 Trade recommendation blocked by liquidity guardrail.\n"
                    f"Reason: {reason}\n\n"
                    "Institutional process: switch to a tighter-spread expiry/strike "
                    "or wait for better quote quality before selecting a contract."
                )
            }

        answer = ask_ai_question(tkr, q)

        # ask_ai_question returns a plain string on success or a fallback string on failure.
        if not answer:
            return JSONResponse({"error": "No answer returned."}, status_code=502)

        return {"answer": answer}
    except Exception as e:
        return JSONResponse({"error": f"AI error: {e}"}, status_code=500)

# ---------------------------------------------------------------------------
# Debug: Gemini trace endpoint (localhost-only when ENABLE_DEBUG_UI=1)
# ---------------------------------------------------------------------------

import os as _os
import re as _re

def _redact_trace(obj, max_len: int = 300):
    """Redact secrets and truncate long strings from trace payload."""
    if isinstance(obj, dict):
        redacted = {}
        for k, v in obj.items():
            if _re.search(r'(api_key|token|authorization|secret)', str(k), _re.I):
                redacted[k] = "***REDACTED***"
            else:
                redacted[k] = _redact_trace(v, max_len)
        return redacted
    elif isinstance(obj, list):
        return [_redact_trace(i, max_len) for i in obj]
    elif isinstance(obj, str) and len(obj) > 800:
        return obj[:max_len] + "…"
    return obj


@app.get("/api/debug/gemini/{trace_id}")
async def debug_gemini_trace(request: Request, trace_id: str):
    """
    Return redacted Gemini debug trace.
    Enabled only when ENABLE_DEBUG_UI=1 and caller is localhost.
    """
    if not _os.getenv("ENABLE_DEBUG_UI"):
        raise HTTPException(status_code=403, detail="Debug UI not enabled")

    host = request.client.host if request.client else ""
    if host not in {"127.0.0.1", "::1", "localhost"}:
        raise HTTPException(status_code=403, detail="Debug only available on localhost")

    if GEMINI_TRACE_CACHE is None:
        raise HTTPException(status_code=404, detail="Trace cache not available")

    trace = GEMINI_TRACE_CACHE.get(trace_id)
    if trace is None:
        raise HTTPException(status_code=404, detail=f"Trace {trace_id!r} not found or expired")

    return JSONResponse(_redact_trace(trace))
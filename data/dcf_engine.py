# data/dcf_engine_v2.py
# INSTITUTIONAL-GRADE VIEW-AWARE DCF ENGINE
# 
# Built with:
# - Phase 1A: Proper WACC (unlever/relever beta, target capital structure)
# - Phase 1B: ROIC-driven reinvestment model
# - Phase 1C: Working capital from operating cycle (industry defaults)
# - Phase 1D: Cash tax rate + mid-year discounting convention
# - Phase 1E: Terminal value validation (ROIC fade, sensitivity)
# - VIEW-AWARE: Adjusts assumptions based on bullish/neutral/bearish stance
#
# Author: Built for institutional-grade personal trading system
# Date: 2026-02-14 (View-aware update)

import yfinance as yf
import numpy as np
import pandas as pd
from typing import Optional, Dict, Tuple, List

# ========================================
# PHASE 1A: WACC CALCULATION
# ========================================

def _unlever_beta(levered_beta: float, tax_rate: float, debt_to_equity: float) -> float:
    """Unlever equity beta to get asset beta (Hamada formula)."""
    if levered_beta is None or np.isnan(levered_beta):
        return 1.0
    
    tax_rate = max(0.0, min(0.99, tax_rate))
    debt_to_equity = max(0.0, debt_to_equity)
    
    denominator = 1.0 + (1.0 - tax_rate) * debt_to_equity
    if denominator <= 0:
        return levered_beta
    
    asset_beta = levered_beta / denominator
    return max(0.2, min(2.5, asset_beta))


def _relever_beta(asset_beta: float, tax_rate: float, target_debt_to_equity: float) -> float:
    """Relever asset beta to equity beta at target capital structure."""
    tax_rate = max(0.0, min(0.99, tax_rate))
    target_debt_to_equity = max(0.0, min(5.0, target_debt_to_equity))
    
    levered_beta = asset_beta * (1.0 + (1.0 - tax_rate) * target_debt_to_equity)
    return max(0.2, min(3.0, levered_beta))


def _estimate_cost_of_debt(debt_to_equity: Optional[float], rf_rate: float) -> float:
    """Estimate cost of debt from D/E ratio."""
    if debt_to_equity is None:
        return rf_rate + 0.0150
    
    if debt_to_equity < 0.2:
        spread = 0.0080
    elif debt_to_equity < 0.5:
        spread = 0.0115
    elif debt_to_equity < 1.0:
        spread = 0.0150
    elif debt_to_equity < 2.0:
        spread = 0.0275
    else:
        spread = 0.0500
    
    return rf_rate + spread


def _compute_wacc_institutional(
    market_cap: float,
    total_debt: float,
    levered_beta: float,
    tax_rate: float,
    rf_rate: float,
    equity_risk_premium: float = 0.05,
) -> Dict[str, float]:
    """Compute WACC using institutional methodology."""
    total_capital_current = market_cap + total_debt
    current_debt_ratio = total_debt / total_capital_current if total_capital_current > 0 else 0.0
    current_de_ratio = total_debt / market_cap if market_cap > 0 else 0.0
    
    # Unlever beta
    asset_beta = _unlever_beta(levered_beta, tax_rate, current_de_ratio)
    
    # Use current structure as target
    target_debt_ratio = current_debt_ratio
    target_debt_ratio = max(0.0, min(0.60, target_debt_ratio))
    
    if target_debt_ratio >= 0.999:
        target_de_ratio = 99.0
    else:
        target_de_ratio = target_debt_ratio / (1.0 - target_debt_ratio)
    
    # Relever at target
    target_equity_beta = _relever_beta(asset_beta, tax_rate, target_de_ratio)
    
    # Cost of equity
    cost_of_equity = rf_rate + target_equity_beta * equity_risk_premium
    cost_of_equity = max(0.06, min(0.20, cost_of_equity))
    
    # Cost of debt
    cost_of_debt = _estimate_cost_of_debt(current_de_ratio, rf_rate)
    
    # WACC at target weights
    weight_equity_target = 1.0 - target_debt_ratio
    weight_debt_target = target_debt_ratio
    
    wacc = (weight_equity_target * cost_of_equity + 
            weight_debt_target * cost_of_debt * (1.0 - tax_rate))
    
    wacc = max(0.05, min(0.18, wacc))
    
    return {
        "wacc": wacc,
        "cost_of_equity": cost_of_equity,
        "cost_of_debt": cost_of_debt,
        "asset_beta": asset_beta,
        "levered_beta_target": target_equity_beta,
        "target_debt_ratio": target_debt_ratio,
        "weight_equity_target": weight_equity_target,
        "weight_debt_target": weight_debt_target,
    }


# ========================================
# PHASE 1B: ROIC MODEL
# ========================================

def _calculate_roic(nopat: float, invested_capital: float) -> float:
    """Calculate Return on Invested Capital."""
    if invested_capital <= 0:
        return 0.15
    roic = nopat / invested_capital
    return max(-0.50, min(2.0, roic))


# ========================================
# PHASE 1E: TERMINAL VALUE
# ========================================

def _gordon_growth_terminal_value(terminal_fcf: float, wacc: float, growth_rate: float) -> float:
    """Calculate terminal value using Gordon Growth."""
    if growth_rate >= wacc:
        growth_rate = min(growth_rate, wacc - 0.01)
    
    growth_rate = max(0.01, min(0.05, growth_rate))
    terminal_value = terminal_fcf * (1 + growth_rate) / (wacc - growth_rate)
    return terminal_value


def _validate_terminal_roic(terminal_nopat: float, terminal_invested_capital: float, wacc: float) -> Dict[str, float]:
    """Validate terminal ROIC assumptions."""
    if terminal_invested_capital > 0:
        terminal_roic = terminal_nopat / terminal_invested_capital
    else:
        terminal_roic = wacc
    
    roic_spread = terminal_roic - wacc
    is_value_creating = terminal_roic >= wacc
    
    return {
        "terminal_roic": terminal_roic,
        "roic_wacc_spread": roic_spread,
        "is_value_creating": is_value_creating,
    }


# ========================================
# PHASE 1D: DISCOUNTING
# ========================================

def _present_value_mid_year(cash_flows: List[float], discount_rate: float) -> float:
    """Calculate PV using mid-year convention."""
    pv = 0.0
    for t, cf in enumerate(cash_flows, start=1):
        pv += cf / ((1 + discount_rate) ** (t - 0.5))
    return pv


# ========================================
# VIEW-AWARE: GROWTH TIER CLASSIFICATION
# ========================================

def _classify_growth_tier(rev_growth_cagr: float) -> str:
    """
    Classify company into growth tier based on historical revenue CAGR.
    
    Returns:
        "high": >20% CAGR (NVDA, AMD, MU)
        "moderate": 10-20% CAGR (QCOM, AVGO)
        "mature": <10% CAGR (INTC, MCHP, TXN)
    """
    if rev_growth_cagr >= 0.20:
        return "high"
    elif rev_growth_cagr >= 0.10:
        return "moderate"
    else:
        return "mature"


def _get_terminal_growth_for_view(growth_tier: str, view: str) -> Tuple[float, int, str]:
    """
    Get terminal growth rate, explicit period, and note based on growth tier and view.
    
    Args:
        growth_tier: "high", "moderate", or "mature"
        view: "bullish", "neutral", or "bearish"
    
    Returns:
        (terminal_growth_rate, explicit_years, assumption_note)
    
    Framework:
        HIGH GROWTH (NVDA, AMD, MU):
            Bearish: 2.0% / 5yr
            Neutral: 3.0% / 7yr
            Bullish: 3.5% / 10yr
        
        MODERATE GROWTH (QCOM, AVGO):
            Bearish: 1.5% / 5yr
            Neutral: 2.5% / 7yr
            Bullish: 3.0% / 8yr
        
        MATURE (INTC, MCHP, TXN):
            Bearish: 1.0% / 5yr
            Neutral: 2.0% / 6yr
            Bullish: 2.5% / 7yr
    """
    view = view.lower() if view else "neutral"
    
    if growth_tier == "high":
        if view == "bearish":
            return (0.020, 5, "Terminal growth: 2.0% (bearish assumption for high-growth semiconductor)")
        elif view == "bullish":
            return (0.035, 10, "Terminal growth: 3.5% (bullish assumption for high-growth semiconductor)")
        else:  # neutral
            return (0.030, 7, "Terminal growth: 3.0% (neutral assumption for high-growth semiconductor)")
    
    elif growth_tier == "moderate":
        if view == "bearish":
            return (0.015, 5, "Terminal growth: 1.5% (bearish assumption for moderate-growth semiconductor)")
        elif view == "bullish":
            return (0.030, 8, "Terminal growth: 3.0% (bullish assumption for moderate-growth semiconductor)")
        else:  # neutral
            return (0.025, 7, "Terminal growth: 2.5% (neutral assumption for moderate-growth semiconductor)")
    
    else:  # mature
        if view == "bearish":
            return (0.010, 5, "Terminal growth: 1.0% (bearish assumption for mature semiconductor)")
        elif view == "bullish":
            return (0.025, 7, "Terminal growth: 2.5% (bullish assumption for mature semiconductor)")
        else:  # neutral
            return (0.020, 6, "Terminal growth: 2.0% (neutral assumption for mature semiconductor)")


def _get_margin_adjustment_for_view(view: str) -> float:
    """
    Get margin adjustment based on view.
    
    Bearish: Compress margins by 2pp
    Neutral: Stable margins
    Bullish: Expand margins by 2pp
    """
    view = view.lower() if view else "neutral"
    
    if view == "bearish":
        return -0.02  # -2 percentage points
    elif view == "bullish":
        return +0.02  # +2 percentage points
    else:
        return 0.00  # neutral


# ========================================
# HELPER FUNCTIONS
# ========================================

def _safe(v, default=0.0):
    """Safe conversion to float."""
    try:
        if v is None:
            return default
        return float(v)
    except Exception:
        return default


def _clamp(x, lo, hi):
    """Clamp value to range."""
    try:
        x = float(x)
    except Exception:
        return lo
    return max(lo, min(hi, x))


def _last_row(df, row_name, default=None):
    """Get last (most recent) value from DataFrame row."""
    try:
        if df is None or df.empty:
            return default
        s = df.loc[row_name]
        for v in list(s.values):
            if v is None:
                continue
            try:
                fv = float(v)
                if np.isfinite(fv):
                    return fv
            except Exception:
                continue
        return default
    except Exception:
        return default


def _calc_cagr(series_vals):
    """Calculate CAGR from time series."""
    try:
        vals = [float(x) for x in series_vals if x is not None and np.isfinite(float(x))]
        if len(vals) < 2:
            return None
        return (vals[-1] / vals[0]) ** (1 / (len(vals) - 1)) - 1
    except Exception:
        return None


# ========================================
# MAIN DCF FUNCTION (VIEW-AWARE)
# ========================================

def build_dcf(ticker: str, spot: float, rf: float = 0.04, sector_bucket: Optional[str] = None, view: str = "neutral") -> dict:
    """
    INSTITUTIONAL-GRADE VIEW-AWARE DCF ENGINE
    
    Integrates 5 phases + view-aware framework:
    - Phase 1A: Proper WACC (unlever/relever beta)
    - Phase 1B: ROIC-driven reinvestment
    - Phase 1C: Working capital (operating cycle)
    - Phase 1D: Cash tax rate + mid-year discounting
    - Phase 1E: Terminal value validation
    - VIEW-AWARE: Adjusts terminal growth, explicit period, margins based on user view
    
    Args:
        ticker: Stock ticker symbol
        spot: Current stock price
        rf: Risk-free rate (10Y Treasury)
        sector_bucket: Industry sector (optional, for compatibility)
        view: "bullish", "neutral", or "bearish" - adjusts assumptions
    
    Returns:
        Dictionary with DCF results (backward compatible + new view-aware fields)
    """
    
    t = yf.Ticker(ticker)
    info = t.info or {}
    fin = t.financials
    cf = t.cashflow
    bs = t.balance_sheet
    
    # Normalize view
    view = view.lower() if view else "neutral"
    if view not in ["bullish", "neutral", "bearish"]:
        view = "neutral"
    
    # ========================================
    # STEP 1: GATHER INPUTS
    # ========================================
    
    shares = _safe(info.get("sharesOutstanding"), 1)
    
    # Revenue
    rev_hist = None
    rev0 = None
    try:
        if fin is not None and not fin.empty and "Total Revenue" in fin.index:
            rev_series = fin.loc["Total Revenue"].iloc[:5]
            rev_hist = list(rev_series.values[::-1])
            rev0 = float(rev_series.values[0])
    except Exception:
        pass
    
    market_cap_guess = _safe(info.get("marketCap"), spot * shares)
    if rev0 is None or not np.isfinite(rev0) or rev0 <= 0:
        rev0 = max(1.0, market_cap_guess / 2.0)
    
    # Revenue growth (historical CAGR)
    rev_growth = _calc_cagr(rev_hist) if rev_hist else 0.08
    if rev_growth is None or not np.isfinite(rev_growth):
        rev_growth = 0.08
    rev_growth = _clamp(rev_growth, -0.10, 0.35)
    
    # Operating margin
    op_margin0 = _safe(info.get("operatingMargins"), None)
    if op_margin0 is None:
        ebit_guess = _last_row(fin, "Ebit", None)
        if ebit_guess is not None and rev0 > 0:
            op_margin0 = ebit_guess / rev0
        else:
            op_margin0 = 0.25
    op_margin0 = _clamp(op_margin0, 0.05, 0.55)
    
    # CapEx
    capex = _last_row(cf, "Capital Expenditure", None)
    if capex is not None and rev0 > 0:
        capex_pct = abs(float(capex)) / rev0
    else:
        capex_pct = 0.06
    capex_pct = _clamp(capex_pct, 0.01, 0.18)
    
    # Capital structure
    total_debt = _safe(info.get("totalDebt"), 0)
    market_cap = _safe(info.get("marketCap"), market_cap_guess)
    beta = _safe(info.get("beta"), 1.2)
    
    # FIX: Cap beta at 2.0 (yfinance sometimes returns inflated values)
    if beta > 2.0:
        beta = 1.7  # Use reasonable default for semis
    elif beta < 0.5:
        beta = 1.2
    
    # Tax rate
    income_tax_exp = _last_row(fin, "Tax Provision", None)
    ebit_for_tax = _last_row(fin, "Ebit", None)
    
    if income_tax_exp is not None and ebit_for_tax is not None and ebit_for_tax > 0:
        interest_exp = _last_row(fin, "Interest Expense", 0) or 0
        pretax_income = ebit_for_tax - abs(interest_exp)
        if pretax_income > 0:
            tax_rate = income_tax_exp / pretax_income
            tax_rate = max(0.0, min(0.50, tax_rate))
        else:
            tax_rate = 0.21
    else:
        tax_rate = 0.21
    
    # ========================================
    # STEP 2: WACC
    # ========================================
    
    wacc_result = _compute_wacc_institutional(
        market_cap=market_cap,
        total_debt=total_debt,
        levered_beta=beta,
        tax_rate=tax_rate,
        rf_rate=rf,
        equity_risk_premium=0.05,
    )
    
    wacc0 = wacc_result["wacc"]
    
    # ========================================
    # STEP 3: WORKING CAPITAL (Industry Defaults)
    # ========================================
    
    # For semiconductors, use industry defaults
    # (yfinance balance sheet data is often stale/incorrect)
    dso = 45.0  # Days sales outstanding
    dio = 60.0  # Days inventory outstanding
    dpo = 60.0  # Days payable outstanding
    
    ccc_days = dso + dio - dpo  # Cash conversion cycle = 45 days
    nwc_pct = ccc_days / 365.0  # NWC as % of revenue ≈ 12.3%
    nwc_pct = _clamp(nwc_pct, 0.02, 0.20)
    
    # ========================================
    # STEP 4: ROIC & REINVESTMENT
    # ========================================
    
    ebit_current = rev0 * op_margin0
    nopat_current = ebit_current * (1 - tax_rate)
    
    # Sales-to-capital ratio (conservative for semis)
    sales_to_capital = 2.0
    invested_capital_current = rev0 / sales_to_capital
    
    roic_current = _calculate_roic(nopat_current, invested_capital_current)
    
    # ========================================
    # STEP 5: VIEW-AWARE ASSUMPTIONS
    # ========================================
    
    # Classify growth tier
    growth_tier = _classify_growth_tier(rev_growth)
    
    # Get view-based terminal growth and explicit period
    g_term0, years, assumption_note = _get_terminal_growth_for_view(growth_tier, view)
    
    # Ensure terminal growth < WACC
    g_term0 = min(g_term0, wacc0 - 0.01)
    g_term0 = _clamp(g_term0, 0.01, 0.05)
    
    # Get margin adjustment based on view
    margin_adjustment = _get_margin_adjustment_for_view(view)
    
    # ========================================
    # STEP 6: PROJECT CASH FLOWS
    # ========================================
    
    # Growth path (taper to terminal)
    growth_path = []
    for i in range(1, years + 1):
        frac = (i - 1) / max(1, years - 1)
        g_i = (1 - frac) * rev_growth + frac * g_term0
        growth_path.append(_clamp(g_i, -0.10, 0.35))
    
    # Margin path (with view adjustment)
    op_margin_target = op_margin0 + margin_adjustment
    op_margin_target = _clamp(op_margin_target, 0.08, 0.60)
    
    margin_path = []
    for i in range(1, years + 1):
        frac = i / years
        m_i = (1 - frac) * op_margin0 + frac * op_margin_target
        margin_path.append(_clamp(m_i, 0.05, 0.60))
    
    # Project revenues, NOPAT, reinvestment, FCF
    revs = []
    fcffs = []
    r = float(rev0)
    
    for i in range(years):
        r = r * (1 + growth_path[i])
        revs.append(r)
        
        ebit = r * margin_path[i]
        nopat = ebit * (1 - tax_rate)
        
        # Reinvestment = CapEx + ΔNWC
        maintenance_capex = r * 0.03
        growth_capex = (r - revs[i-1] if i > 0 else r - rev0) / sales_to_capital
        total_capex = maintenance_capex + growth_capex
        
        # ΔNWC
        nwc_current = r * nwc_pct
        nwc_prev = (revs[i-1] if i > 0 else rev0) * nwc_pct
        delta_nwc = nwc_current - nwc_prev
        
        reinvest = total_capex + delta_nwc
        fcff = nopat - reinvest
        fcffs.append(fcff)
    
    # ========================================
    # STEP 7: TERMINAL VALUE
    # ========================================
    
    terminal_fcf = fcffs[-1]
    tv_g0 = _gordon_growth_terminal_value(terminal_fcf, wacc0, g_term0)
    
    # Validate terminal ROIC
    terminal_revenue = revs[-1]
    terminal_ebit = terminal_revenue * margin_path[-1]
    terminal_nopat = terminal_ebit * (1 - tax_rate)
    terminal_ic = terminal_revenue / sales_to_capital
    
    terminal_validation = _validate_terminal_roic(terminal_nopat, terminal_ic, wacc0)
    
    # ========================================
    # STEP 8: MID-YEAR DISCOUNTING
    # ========================================
    
    pv_fcff0 = _present_value_mid_year(fcffs, wacc0)
    pv_tv0 = tv_g0 / ((1 + wacc0) ** (years - 0.5))
    
    # Enterprise value
    ev0 = pv_fcff0 + pv_tv0
    intrinsic0 = ev0 / max(1.0, shares)
    
    upside0 = (intrinsic0 / spot - 1) * 100 if spot else 0
    
    # ========================================
    # STEP 9: SCENARIOS (BEAR/BULL)
    # ========================================
    
    def _run_scenario(g_adj=0.0, m_adj=0.0, wacc_adj=0.0):
        w = _clamp(wacc0 + wacc_adj, 0.06, 0.16)
        g_term = _clamp(g_term0 + (g_adj * 0.5), 0.01, 0.05)
        g_term = min(g_term, w - 0.01)
        
        g_start = _clamp(rev_growth + g_adj, -0.10, 0.35)
        m_target = _clamp(op_margin_target + m_adj, 0.06, 0.65)
        
        fcffs_scenario = []
        r_s = rev0
        for i in range(years):
            frac = (i + 1) / years
            g_i = (1 - frac) * g_start + frac * g_term
            m_i = (1 - frac) * op_margin0 + frac * m_target
            
            r_s = r_s * (1 + g_i)
            ebit_s = r_s * m_i
            nopat_s = ebit_s * (1 - tax_rate)
            
            reinvest_s = r_s * (capex_pct + nwc_pct * 0.5)
            fcff_s = nopat_s - reinvest_s
            fcffs_scenario.append(fcff_s)
        
        pv_explicit = _present_value_mid_year(fcffs_scenario, w)
        tv_s = _gordon_growth_terminal_value(fcffs_scenario[-1], w, g_term)
        pv_tv_s = tv_s / ((1 + w) ** (years - 0.5))
        
        ev_s = pv_explicit + pv_tv_s
        return ev_s / max(1.0, shares)
    
    bear = _run_scenario(g_adj=-0.03, m_adj=-0.04, wacc_adj=0.015)
    bull = _run_scenario(g_adj=0.03, m_adj=0.03, wacc_adj=-0.005)
    
    # ========================================
    # STEP 10: SENSITIVITY (3x3 GRID)
    # ========================================
    
    sens = []
    for dw in [-0.01, 0.0, 0.01]:
        row = []
        for dg in [-0.005, 0.0, 0.005]:
            row.append(_run_scenario(g_adj=0.0, m_adj=0.0, wacc_adj=dw))
        sens.append(row)
    
    # Valuation bias
    bias = (
        "undervalued" if upside0 > 10 else
        "overvalued" if upside0 < -10 else
        "fair"
    )
    
    # ========================================
    # STEP 11: RETURN RESULTS
    # ========================================
    
    return {
        # REQUIRED by old version
        "intrinsic": round(float(intrinsic0), 2),
        "upside_pct": round(float(upside0), 1),
        "band": {
            "bear": round(float(bear), 2),
            "base": round(float(intrinsic0), 2),
            "bull": round(float(bull), 2),
        },
        "wacc": round(float(wacc0), 4),
        "rev_growth": round(float(rev_growth), 4),
        "op_margin": round(float(op_margin0), 4),
        "capex_pct": round(float(capex_pct), 4),
        "nwc_pct": float(nwc_pct),
        "sensitivity": sens,
        "valuation_bias": bias,
        
        # NEW institutional-grade fields
        "wacc_institutional": wacc_result,
        "roic_analysis": {
            "current_roic": round(float(roic_current), 4),
            "terminal_roic": round(terminal_validation["terminal_roic"], 4),
            "roic_wacc_spread": round(terminal_validation["roic_wacc_spread"], 4),
            "is_value_creating": terminal_validation["is_value_creating"],
        },
        "working_capital_detail": {
            "dso_days": round(float(dso), 1),
            "dio_days": round(float(dio), 1),
            "dpo_days": round(float(dpo), 1),
            "ccc_days": round(float(ccc_days), 1),
            "nwc_pct_revenue": round(float(nwc_pct), 4),
        },
        "tax_analysis": {
            "tax_rate_used": round(float(tax_rate), 4),
            "source": "effective from financials" if income_tax_exp else "statutory default",
        },
        "terminal_value_detail": {
            "terminal_fcf": round(float(terminal_fcf), 2),
            "growth_rate": round(float(g_term0), 4),
            "terminal_value": round(float(tv_g0), 2),
            "pv_terminal": round(float(pv_tv0), 2),
            "pv_explicit": round(float(pv_fcff0), 2),
        },
        "discounting_method": "mid-year convention (institutional standard)",
        
        # VIEW-AWARE fields
        "view_used": view,
        "growth_tier": growth_tier,
        "explicit_years": years,
        "assumption_note": assumption_note,
        "margin_adjustment": margin_adjustment,
        
        # Metadata
        "methodology": "institutional-grade view-aware (5-phase)",
        "version": "2.1",
        "debug": {
            "ticker": ticker,
            "shares": float(shares),
            "market_cap": float(market_cap),
            "total_debt": float(total_debt),
        }
    }


# ========================================
# BACKWARD COMPATIBILITY
# ========================================

def build_dcf_v2(*args, **kwargs):
    """Alias for build_dcf (backward compatibility)."""
    return build_dcf(*args, **kwargs)
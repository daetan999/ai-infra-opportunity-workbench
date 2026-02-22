import math
from datetime import datetime, timezone

def widen_factor_from_confidence(conf_pct: float | None):
    if conf_pct is None:
        return 1.25
    if conf_pct >= 0.75:
        return 0.8
    if conf_pct >= 0.60:
        return 1.0
    if conf_pct >= 0.45:
        return 1.2
    return 1.4



def entry_zone_from_peers(
    spot: float,
    peer_snapshot: dict | None,
    hv20: float | None,
    hv60: float | None,
    confidence_pct: float | None,
    view: str | None = None,
):
    """
    Returns (low, high, reasons[])
    """

    reasons = []

    base_width = 0.03  # ±3% baseline (tighter, actionable)
    bias = 0.0
    v = (view or "").lower()
    if v == "bull":
        bias = -0.4 * base_width   # shift band down
    elif v == "bear":
        bias = 0.4 * base_width    # shift band up

    vol = None
    if hv20:
        vol = hv20
        reasons.append("Using HV20 for volatility regime")
    elif hv60:
        vol = hv60
        reasons.append("Using HV60 for volatility regime")

    if vol:
        if vol > 0.6:
            base_width += 0.02
            reasons.append("High volatility → slightly wider entry band")
        elif vol > 0.4:
            base_width += 0.01


    # peer valuation anchor
    if peer_snapshot:
        bands = peer_snapshot.get("bands", {})
        fwd = bands.get("forward_pe") or {}
        med = fwd.get("median")
        focal = peer_snapshot.get("focal") or {}
        focal_fpe = focal.get("forward_pe")

        if med and focal_fpe:
            if focal_fpe > med:
                base_width += 0.02
                reasons.append("Trading above peer median valuation")
            else:
                reasons.append("Below peer median valuation")

    widen = widen_factor_from_confidence(confidence_pct)
    width = base_width * widen
    # hard cap so entry zones stay usable
    width = min(width, 0.08)  # max ±8%
    width = max(width, 0.02)  # min ±2%

    lo = spot * (1 + bias - width)
    hi = spot * (1 + bias + width)

    return round(lo, 2), round(hi, 2), reasons


def scenario_bands(
    spot: float,
    horizon_days: int,
    hv20: float | None,
    hv60: float | None,
):
    """
    Simple vol-based scenario bands.
    """

    vol = hv20 or hv60 or 0.4

    t = horizon_days / 252

    sigma_move = vol * math.sqrt(t)

    bear = spot * (1 - 1.2 * sigma_move)
    base = spot * (1 + 0.0 * sigma_move)
    bull = spot * (1 + 1.2 * sigma_move)

    return {
        "bear": round(bear, 2),
        "base": round(base, 2),
        "bull": round(bull, 2),
        "vol_used": vol,
        "asof_utc": datetime.now(timezone.utc).isoformat(),
    }


def build_price_guidance(
    spot,
    dcf_result,
    macro_snapshot,
    company_snapshot,
    iv_rank,
    hv20,
    hv60,
    earnings_days
):
    """
    Phase C institutional price guidance engine.
    Deterministic. DCF-anchored.
    """

    if not dcf_result or "intrinsic_value" not in dcf_result:
        return None

    intrinsic = float(dcf_result.get("intrinsic_value", spot))
    conservative = float(dcf_result.get("conservative_value", intrinsic))

    # --- 1️⃣ Base anchored to intrinsic ---
    base = intrinsic

    # --- 2️⃣ Company risk widening ---
    risk = (company_snapshot or {}).get("overall_risk", 0.5)
    quality = (company_snapshot or {}).get("overall_quality", 0.5)

    risk_multiplier = 1 + (risk - 0.5) * 0.4
    quality_tightener = 1 - (quality - 0.5) * 0.2

    width_factor = risk_multiplier * quality_tightener

    # --- 3️⃣ Macro overlay ---
    regime = (macro_snapshot or {}).get("regime_label", "Neutral")

    if regime == "Risk Off":
        macro_adj = 0.9
    elif regime == "Risk On":
        macro_adj = 1.05
    else:
        macro_adj = 1.0

    # --- 3.5️⃣ Industry posture overlay ---
    industry = (company_snapshot or {}).get("industry_snapshot", {})

    cycle_stage = industry.get("cycle_stage", "Mid")
    pricing_power = industry.get("pricing_power", 0.5)
    supply_discipline = industry.get("supply_discipline", 0.5)

    # Cycle stage multiplier
    if cycle_stage == "Expansion":
        cycle_adj = 1.05
    elif cycle_stage == "Contraction":
        cycle_adj = 0.9
    else:
        cycle_adj = 1.0

    # Pricing power tightens downside if strong
    pricing_adj = 1 - (pricing_power - 0.5) * 0.2

    # Weak supply discipline widens volatility
    supply_adj = 1 + (0.5 - supply_discipline) * 0.3

    industry_width_adj = cycle_adj * pricing_adj * supply_adj


    # --- 4️⃣ Vol regime overlay ---
    vol_spread = abs((hv20 or 0) - (hv60 or 0))

    if vol_spread > 0.15:
        vol_adj = 1.1
    else:
        vol_adj = 1.0

    # --- 5️⃣ Earnings proximity ---
    if earnings_days is not None and earnings_days <= 10:
        earnings_adj = 1.15
    else:
        earnings_adj = 1.0

    total_width = width_factor * vol_adj * earnings_adj * industry_width_adj

    conservative_case = conservative * macro_adj
    bull_extension = base * (1 + 0.15 * total_width)
    bear_extension = conservative_case * (1 - 0.10 * total_width)

    entry_low = min(base, conservative_case)
    entry_high = base

    return {
        "base_case": round(base, 2),
        "conservative_case": round(conservative_case, 2),
        "bull_extension": round(bull_extension, 2),
        "bear_extension": round(bear_extension, 2),
        "entry_zone_low": round(entry_low, 2),
        "entry_zone_high": round(entry_high, 2),
        "reasoning": {
            "risk_multiplier": round(risk_multiplier, 3),
            "macro_regime": regime,
            "cycle_stage": cycle_stage,
            "pricing_power": pricing_power,
            "supply_discipline": supply_discipline,
            "industry_width_adj": round(industry_width_adj, 3),
            "vol_spread": round(vol_spread, 3),
            "earnings_adj": earnings_adj,
            "total_width": round(total_width, 3),
        }
    }


def recommend_options_contracts(
    t,
    expiry: str,
    view: str,
    S: float,
    r: float | None,
    sigma_forecast: float | None,
    budget: float,
    max_loss: float,
    top_n: int = 5,
):
    """Rank and size option contracts given budget and max loss (long premium).

    Returns a list of dict rows suitable for rendering in report.html.

    Notes:
    - Uses Yahoo chain (yfinance) and mid price (or best available).
    - Assumes max loss = premium paid.
    - Focuses around ATM for practicality.
    """
    if t is None or not expiry or expiry == "N/A":
        return []

    try:
        chain = t.option_chain(expiry)
    except Exception:
        return []

    v = (view or "").lower()
    side = "call" if v.startswith("bull") else "put"
    df = getattr(chain, "calls", None) if side == "call" else getattr(chain, "puts", None)
    if df is None or len(df) == 0:
        return []

    try:
        spot = float(S)
    except Exception:
        return []

    # Subset near ATM first (keeps output sane)
    try:
        df = df.copy()
        df["abs_moneyness"] = (df["strike"].astype(float) - spot).abs()
        df = df.sort_values("abs_moneyness").head(60)
    except Exception:
        df = df.head(60)

    # spend cap is limited by BOTH budget and max_loss (max loss = premium)
    spend_cap = None
    try:
        spend_cap = float(min(budget, max_loss))
    except Exception:
        return []

    rows = []
    for _, row in df.iterrows():
        try:
            strike = float(row.get("strike"))
            bid = float(row.get("bid") or 0.0)
            ask = float(row.get("ask") or 0.0)
            oi = float(row.get("openInterest") or 0.0)
            vol = float(row.get("volume") or 0.0)
            if bid <= 0 and ask <= 0:
                continue
            mid = (bid + ask) / 2.0 if (bid > 0 and ask > 0) else (ask if ask > 0 else bid)
            if mid <= 0:
                continue

            cost = mid * 100.0
            if cost <= 0:
                continue

            # contracts sized by spend_cap (hard cap)
            n = int(spend_cap // cost) if spend_cap > 0 else 0
            if n <= 0:
                continue

            spread_pct = None
            if bid > 0 and ask > 0 and mid > 0:
                spread_pct = (ask - bid) / mid

            abs_m = abs(strike - spot)
            abs_m_pct = abs_m / spot if spot > 0 else abs_m

            rows.append(
                {
                    "type": side,
                    "expiry": expiry,
                    "strike": round(strike, 2),
                    "bid": round(bid, 3),
                    "ask": round(ask, 3),
                    "mid": round(mid, 3),
                    "spread_pct": round(spread_pct * 100, 2) if spread_pct is not None else None,
                    "open_interest": int(oi),
                    "volume": int(vol),
                    "abs_moneyness_pct": round(abs_m_pct * 100, 2),
                    "contract_cost": round(cost, 2),
                    "contracts": int(n),
                    "total_cost": round(n * cost, 2),
                    "max_loss": round(n * cost, 2),
                }
            )
        except Exception:
            continue

    if not rows:
        return []

    # Normalize and score: prefer tighter spreads, higher OI/vol, closer to ATM.
    max_oi = max((r.get("open_interest") or 0) for r in rows) or 1
    max_vol = max((r.get("volume") or 0) for r in rows) or 1

    for rrow in rows:
        oi_n = (rrow.get("open_interest") or 0) / max_oi
        vol_n = (rrow.get("volume") or 0) / max_vol
        spread = (rrow.get("spread_pct") or 9999.0) / 100.0  # convert back to 0..1
        m = (rrow.get("abs_moneyness_pct") or 9999.0) / 100.0

        # score: liquidity heavy, penalize wide spread and far OTM
        score = (0.45 * oi_n) + (0.25 * vol_n) - (0.20 * spread) - (0.10 * m)
        rrow["score"] = round(score, 4)

    rows.sort(key=lambda x: x.get("score", -999), reverse=True)
    return rows[: max(1, int(top_n))]

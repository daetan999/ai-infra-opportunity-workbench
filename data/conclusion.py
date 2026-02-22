from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Tuple

@dataclass
class SignalResult:
    name: str
    available: bool
    weight: float
    score_0_1: float         # signal quality score (0..1)
    bullets: List[str]
    cautions: List[str]

def _clamp01(x: float) -> float:
    return max(0.0, min(1.0, float(x)))

def _fmt_pct(x: Optional[float]) -> str:
    if x is None:
        return "—"
    return f"{x*100:.1f}%"

# ---- Signals ----

def sig_liquidity(ctx: Dict[str, Any]) -> SignalResult:
    spread_pct = ctx.get("spread_pct")
    liq_ok = bool(ctx.get("liq_ok"))
    bullets, cautions = [], []

    if liq_ok:
        bullets.append("Liquidity passes your filter (spread OK).")
        score = 0.85
    else:
        cautions.append("Liquidity fails your filter (spread too wide or missing two-sided quotes).")
        score = 0.25

    if spread_pct is not None:
        bullets.append(f"Spread ≈ {_fmt_pct(spread_pct)}.")

    return SignalResult("liquidity", True, 0.30, score, bullets, cautions)

def sig_pricing_vs_forecast(ctx: Dict[str, Any]) -> SignalResult:
    gap_pct = ctx.get("gap_pct")
    label = ctx.get("label") or ""
    bullets, cautions = [], []

    if gap_pct is None:
        return SignalResult("pricing_vs_forecast", False, 0.20, 0.5, [], ["No mispricing signal (missing theo or mid)."])

    # score here is NOT “good trade”, it’s “signal clarity”
    # extreme cheap/rich gives a stronger signal (clarity), neutral = weaker.
    g = float(gap_pct)
    if abs(g) >= 0.20:
        score = 0.80
    elif abs(g) >= 0.10:
        score = 0.65
    else:
        score = 0.50

    bullets.append(f"Forecast pricing label: {label}.")
    bullets.append(f"Mid vs Theo gap: {_fmt_pct(gap_pct)}.")

    return SignalResult("pricing_vs_forecast", True, 0.20, score, bullets, cautions)

def sig_vol_context(ctx: Dict[str, Any]) -> SignalResult:
    atm_iv = ctx.get("atm_iv_selected")
    hv20 = ctx.get("hv20")
    hv60 = ctx.get("hv60")
    implied_move = ctx.get("implied_move_pct")
    bullets, cautions = [], []

    if atm_iv is None or hv20 is None or hv60 is None:
        return SignalResult("vol_context", False, 0.20, 0.5, [], ["Vol context unavailable (missing IV/HV)."])

    # Clarity score: if IV is meaningfully different from HV, the signal is clearer
    iv_over_hv20 = (atm_iv / hv20) if hv20 and hv20 > 0 else None
    if iv_over_hv20 is None:
        return SignalResult("vol_context", False, 0.20, 0.5, [], ["Vol context unavailable (HV20 invalid)."])

    bullets.append(f"ATM IV: {_fmt_pct(atm_iv)} | HV20: {_fmt_pct(hv20)} | HV60: {_fmt_pct(hv60)}.")
    bullets.append(f"IV/HV20: {iv_over_hv20:.2f}.")

    if implied_move is not None:
        bullets.append(f"Implied move to expiry ≈ ±{implied_move*100:.1f}%.")

    # score: more divergence = more informative
    if iv_over_hv20 >= 1.3 or iv_over_hv20 <= 0.9:
        score = 0.75
    else:
        score = 0.55

    return SignalResult("vol_context", True, 0.20, score, bullets, cautions)

def sig_auto_expiry(ctx: Dict[str, Any]) -> SignalResult:
    auto = ctx.get("auto_info")
    if not auto or not isinstance(auto, dict):
        return SignalResult("auto_expiry", False, 0.15, 0.5, [], [])

    grade = auto.get("liq_grade")
    label = auto.get("liq_label")
    score = float(auto.get("score") or 0.0)

    bullets = [f"Auto-expiry liquidity grade: {grade} ({label}).", f"Auto liquidity score: {score:.3f}."]
    cautions = []
    # signal clarity tied to score
    return SignalResult("auto_expiry", True, 0.15, _clamp01(score), bullets, cautions)

def sig_put_call(ctx: Dict[str, Any]) -> SignalResult:
    pcr = ctx.get("pcr") or {}
    pcr_oi = pcr.get("pcr_oi")
    pcr_vol = pcr.get("pcr_vol")
    if pcr_oi is None and pcr_vol is None:
        return SignalResult("put_call", False, 0.15, 0.5, [], [])

    bullets = []
    if pcr_oi is not None:
        bullets.append(f"Put/Call (OI): {pcr_oi:.2f}.")
    if pcr_vol is not None:
        bullets.append(f"Put/Call (Vol): {pcr_vol:.2f}.")

    # clarity: more extreme ratios = more informative (not “bullish/bearish”)
    extreme = 0.0
    for v in [pcr_oi, pcr_vol]:
        if v is None:
            continue
        extreme = max(extreme, abs(float(v) - 1.0))
    score = 0.55 + min(0.25, extreme / 2.0)

    return SignalResult("put_call", True, 0.15, _clamp01(score), bullets, [])

def signal_pcr_positioning(ctx: Dict[str, Any]) -> SignalResult:
    """
    Put/Call positioning + flow sanity check using OI/volume totals.
    Penalizes extreme crowding.
    """
    p = ctx.get("pcr") or {}

    call_oi = p.get("call_oi") or p.get("calls_oi") or p.get("oi_calls")
    put_oi = p.get("put_oi") or p.get("puts_oi") or p.get("oi_puts")

    call_vol = p.get("call_vol") or p.get("calls_vol") or p.get("vol_calls")
    put_vol = p.get("put_vol") or p.get("puts_vol") or p.get("vol_puts")

    # Need OI at minimum (0 is valid; only None means missing)
    if call_oi is None or put_oi is None:
        return SignalResult(
            name="PCR positioning",
            available=False,
            weight=0.10,
            score_0_1=0.5,
            bullets=[],
            cautions=[],
        )

    try:
        call_oi = float(call_oi)
        put_oi = float(put_oi)
        pcr_oi = put_oi / call_oi if call_oi > 0 else None
    except Exception:
        pcr_oi = None

    pcr_vol = None
    try:
        if call_vol and put_vol:
            call_vol = float(call_vol)
            put_vol = float(put_vol)
            pcr_vol = put_vol / call_vol if call_vol > 0 else None
    except Exception:
        pcr_vol = None

    bullets = []
    cautions = []

    if pcr_oi is None:
        return SignalResult(
            name="PCR positioning",
            available=False,
            weight=0.10,
            score_0_1=0.5,
            bullets=[],
            cautions=[],
        )

    bullets.append(
        f"Put/Call OI ratio: {pcr_oi:.2f}"
        + (f" • Put/Call vol: {pcr_vol:.2f}" if pcr_vol is not None else "")
    )

    # Extremes imply crowding risk
    if pcr_oi < 0.6:
        score = 0.45
        cautions.append("Calls dominate OI → crowding risk; IV crush more likely on good news.")
    elif pcr_oi > 1.8:
        score = 0.45
        cautions.append("Puts dominate OI → squeeze risk if news surprises.")
    elif 0.7 <= pcr_oi <= 1.4:
        score = 0.70
        bullets.append("OI positioning not extreme (lower crowding risk).")
    else:
        score = 0.60
        bullets.append("OI positioning mildly skewed.")

    if pcr_vol is not None:
        if (pcr_oi > 1.6 and pcr_vol < 0.9) or (pcr_oi < 0.7 and pcr_vol > 1.3):
            cautions.append("OI vs volume PCR diverge → flow/position mismatch.")
            score = max(0.40, score - 0.08)

    return SignalResult(
        name="PCR positioning",
        available=True,
        weight=0.10,
        score_0_1=float(score),
        bullets=bullets,
        cautions=cautions,
    )

def sig_straddle_vs_hv(ctx: Dict[str, Any]) -> SignalResult:
    ratio = ctx.get("straddle_vs_hv20")
    imp = ctx.get("straddle_implied_move_pct")
    hv = ctx.get("hv20_move_pct_planned")

    if ratio is None or imp is None or hv is None:
        return SignalResult(
            name="Straddle vs HV20",
            available=False,
            weight=0.12,
            score_0_1=0.5,
            bullets=[],
            cautions=[],
        )

    bullets = [f"ATM straddle implies ±{imp*100:.1f}% vs HV20-scaled ±{hv*100:.1f}% (Implied/HV20: {ratio:.2f}×)."]
    cautions = []

    # scoring heuristic
    if ratio >= 1.6:
        score = 0.45
        cautions.append("Options look rich vs recent realized vol → IV crush risk higher (prefer defined-risk or sell premium).")
    elif ratio <= 0.9:
        score = 0.70
        bullets.append("Options look cheap vs realized vol → premium may be underpriced (event risk still matters).")
    else:
        score = 0.62
        bullets.append("Straddle pricing roughly aligns with realized vol.")

    return SignalResult(
        name="Straddle vs HV20",
        available=True,
        weight=0.12,
        score_0_1=float(score),
        bullets=bullets,
        cautions=cautions,
    )

def sig_macro_regime(ctx: Dict[str, Any]) -> SignalResult:
    macro = ctx.get("macro_snapshot") or {}
    regime = macro.get("risk_regime")
    view = (ctx.get("view") or "").lower()  # bullish / bearish / neutral

    if not regime:
        return SignalResult("macro_regime", False, 0.10, 0.5, [], [])

    bullets: List[str] = [f"Macro backdrop: {regime.replace('_',' ').title()}."]
    cautions: List[str] = []

    # Score = “setup friendliness” given directional intent (deterministic heuristic)
    if regime == "RISK_OFF":
        if view == "bullish":
            score = 0.45
            cautions.append("Risk-off regime → bullish exposure has higher gap/derisking risk.")
        elif view == "bearish":
            score = 0.70
            bullets.append("Risk-off regime aligns with bearish bias.")
        else:
            score = 0.60
            bullets.append("Risk-off regime → neutral/defined-risk structures tend to behave better.")
    elif regime == "RISK_ON":
        if view == "bullish":
            score = 0.70
            bullets.append("Risk-on regime aligns with bullish bias.")
        elif view == "bearish":
            score = 0.50
            cautions.append("Risk-on regime → bearish convexity needs cleaner timing.")
        else:
            score = 0.60
            bullets.append("Risk-on regime → directionals work; still manage vol/entry.")
    else:
        score = 0.58
        bullets.append("Macro regime is mixed/neutral — keep sizing honest.")

    return SignalResult("macro_regime", True, 0.10, float(score), bullets, cautions)


SIGNALS: List[Callable[[Dict[str, Any]], SignalResult]] = [
    sig_liquidity,
    sig_macro_regime,
    sig_pricing_vs_forecast,
    sig_vol_context,
    sig_straddle_vs_hv,
    sig_auto_expiry,
    sig_put_call,
    signal_pcr_positioning,
]

def build_conclusion(ctx: Dict[str, Any]) -> Dict[str, Any]:
    results = [fn(ctx) for fn in SIGNALS]

    used = [r for r in results if r.available and r.weight > 0]
    total_w = sum(r.weight for r in used) or 1.0
    weighted = sum(r.weight * r.score_0_1 for r in used) / total_w

    macro = ctx.get("macro_snapshot") or {}
    regime = macro.get("risk_regime")

    # Penalize if too many missing modules (keeps confidence honest)
    missing = len([r for r in results if not r.available])
    missing_penalty = min(0.20, 0.05 * missing)
    confidence = _clamp01(weighted - missing_penalty)

    # =========================
    # Earnings vs planned exit window overlay
    # =========================
    planned_days = int(ctx.get("planned_days") or 0)
    earnings_info = ctx.get("earnings_info") or {}

    d_us = earnings_info.get("days_to_earnings_us")
    d_utc = earnings_info.get("days_to_earnings")

    days_to_earnings = None
    try:
        if d_us is not None:
            days_to_earnings = int(d_us)
        elif d_utc is not None:
            days_to_earnings = int(d_utc)
    except Exception:
        days_to_earnings = None

    earnings_in_window = False
    if planned_days > 0 and days_to_earnings is not None:
        earnings_in_window = (0 <= days_to_earnings <= planned_days)

    earnings_label = None
    date_us = earnings_info.get("earnings_date_us")
    time_us = earnings_info.get("earnings_time_us")
    sess = earnings_info.get("session_us")

    if date_us:
        if time_us and sess:
            earnings_label = f"{date_us} {time_us} ET ({sess})"
        else:
            earnings_label = f"{date_us} ET"

    if earnings_in_window:
        confidence = _clamp01(confidence - 0.08)

    # =========================
    # Collect bullets / cautions from signals
    # =========================
    bullets = []
    cautions = []
    for r in results:
        bullets.extend(r.bullets)
        cautions.extend(r.cautions)

    # =========================
    # Horizon / earnings / macro bullets
    # =========================
    if planned_days > 0:
        bullets.insert(0, f"Horizon used: planned {planned_days}d (exit plan).")

    if earnings_in_window:
        if earnings_label:
            bullets.insert(1, f"Event-driven: earnings within planned hold window ({earnings_label}).")
        else:
            bullets.insert(1, "Event-driven: earnings within planned hold window.")
        cautions.append(
            "Earnings inside planned hold window → gap risk and IV crush risk elevated. "
            "Position sizing and exits matter more than usual."
        )
    else:
        bullets.insert(1, "No earnings detected within planned hold window (best-effort).")

    if regime:
        bullets.insert(2, f"Macro backdrop: {regime.replace('_', ' ').title()}.")

        if regime == "RISK_OFF":
            cautions.append("Macro regime is Risk-off → higher gap/derisking risk across equities.")

    view = (ctx.get("view") or "neutral").lower()

    if earnings_in_window:
        # Defined-risk preference
        if view == "bullish":
            bullets.insert(2, "Earnings-aware structure: consider call spreads, call calendars/diagonals, or broken-wing butterflies (defined risk).")
        elif view == "bearish":
            bullets.insert(2, "Earnings-aware structure: consider put spreads, put calendars/diagonals, or broken-wing butterflies (defined risk).")
        else:
            bullets.insert(2, "Earnings-aware structure: consider iron condors/iron butterflies (defined risk) if you’re playing vol, not direction.")

        cautions.append("Avoid naked long premium into earnings unless you explicitly want binary gap exposure.")
    else:
        # Optional: if earnings just passed (best-effort heuristic)
        if days_to_earnings is not None and days_to_earnings < 0 and abs(days_to_earnings) <= 3:
            bullets.insert(2, "Post-earnings window: if IV remains elevated, premium-selling / spreads may benefit from vol normalization (watch liquidity).")

    # =========================
    # P0-3 FIX: Verdict based on confidence + liquidity gate status
    # =========================
    liq_ok = bool(ctx.get("liq_ok"))
    
    # Get liquidity gate from context (unified source of truth)
    liquidity_gate = ctx.get("liquidity_gate")
    gate_status = liquidity_gate.get("status") if liquidity_gate else None
    
    # CRITICAL: Verdict MUST respect liquidity gate
    if gate_status == "BLOCK":
        verdict = "Not tradable under institutional constraints (liquidity blocked)"
    elif gate_status == "WARN":
        # Can trade but with conservative restrictions
        if confidence >= 0.75:
            verdict = "Tradable with caution (liquidity warning) — conservative sizing / defined risk only"
        elif confidence >= 0.55:
            verdict = "Marginal setup (liquidity warning) — very conservative sizing / defined risk mandatory"
        else:
            verdict = "Low confidence + liquidity warning — wait for better setup"
    else:
        # Normal verdict logic when liquidity passes
        if confidence >= 0.75 and liq_ok:
            verdict = "Supports action (high confidence) — focus on structure + sizing."
        elif confidence >= 0.55:
            verdict = "Mixed signals — tradable, but keep sizing conservative / prefer defined risk."
        else:
            verdict = "Low confidence — change expiry/strike or wait for better setup."

    return {
        "verdict": verdict,
        "confidence": float(confidence),
        "inputs_used": [r.name for r in used],
        "bullets": bullets,
        "cautions": cautions,
        "missing_modules": [r.name for r in results if not r.available],

        # debug / UI helpers
        "earnings_in_planned_window": earnings_in_window,
        "earnings_label": earnings_label,
    }

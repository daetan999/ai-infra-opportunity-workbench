import math
import pandas as pd


def atr(df: pd.DataFrame, n: int = 14) -> float | None:
    """
    Average True Range using High/Low/Close.
    Returns latest ATR value (float) or None.
    """
    if df is None or df.empty:
        return None
    for c in ["High", "Low", "Close"]:
        if c not in df.columns:
            return None

    high = df["High"].astype(float)
    low = df["Low"].astype(float)
    close = df["Close"].astype(float)

    prev_close = close.shift(1)
    tr = pd.concat(
        [
            (high - low).abs(),
            (high - prev_close).abs(),
            (low - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)

    atr_series = tr.rolling(n).mean()
    v = atr_series.dropna()
    if v.empty:
        return None
    return float(v.iloc[-1])


def anchored_vwap(df: pd.DataFrame, anchor_date: str) -> dict:
    """
    Anchored VWAP from a YYYY-MM-DD anchor_date.
    Returns dict with vwap, stdev, band_low, band_high, used_rows.
    """
    out = {
        "anchor_date": anchor_date,
        "vwap": None,
        "stdev": None,
        "band_low": None,
        "band_high": None,
        "used_rows": 0,
    }

    if df is None or df.empty:
        return out
    for c in ["High", "Low", "Close", "Volume"]:
        if c not in df.columns:
            return out

    # filter from anchor
    d2 = df.copy()
    d2 = d2.dropna(subset=["High", "Low", "Close", "Volume"])
    if d2.empty:
        return out

    # handle index type
    try:
        d2.index = pd.to_datetime(d2.index)
    except Exception:
        return out

    anchor_ts = pd.to_datetime(anchor_date, errors="coerce")
    if pd.isna(anchor_ts):
        return out

    # Make anchor_ts timezone-compatible with d2.index
    try:
        if d2.index.tz is not None:
            # If anchor has no tz, localize it to the same tz as the price index
            if anchor_ts.tzinfo is None:
                anchor_ts = anchor_ts.tz_localize(d2.index.tz)
            else:
                anchor_ts = anchor_ts.tz_convert(d2.index.tz)
    except Exception:
        # If anything weird happens, skip anchored VWAP gracefully
        return out

    d2 = d2[d2.index >= anchor_ts]
    if d2.empty:
        return out

    tp = (d2["High"].astype(float) + d2["Low"].astype(float) + d2["Close"].astype(float)) / 3.0
    vol = d2["Volume"].astype(float).clip(lower=0.0)

    pv = (tp * vol).cumsum()
    vv = vol.cumsum().replace(0, math.nan)
    vwap_series = pv / vv

    vwap = vwap_series.dropna()
    if vwap.empty:
        return out

    vwap_last = float(vwap.iloc[-1])

    # deviation band based on closing deviations from VWAP
    close = d2["Close"].astype(float)
    dev = (close - vwap_series).dropna()
    if dev.empty:
        return out

    st = float(dev.std())

    out["vwap"] = round(vwap_last, 2)
    out["stdev"] = round(st, 2)
    out["band_low"] = round(vwap_last - 1.0 * st, 2)
    out["band_high"] = round(vwap_last + 1.0 * st, 2)
    out["used_rows"] = int(len(d2))
    return out

def execution_bands(
    spot: float,
    atr14: float | None,
    atr20: float | None,
    conf_pct: float | None,
    view: str | None,
    alpha_regime: dict | None = None,   
    liquidity_metrics: dict | None = None,  # <-- NEW (Phase 13C)
    confidence_regime: dict | None = None,  # <-- NEW (Phase 13E)
):
    """
    Quant-ish execution bands:
      Primary band = spot ± k*ATR(14)
      Aggressive band = spot ± k2*ATR(20)
      Invalidation = further band edge (risk line)

    - k shrinks when confidence is high.
    - k is additionally scaled by alpha regime (Phase 13D):
        STRONG_POS / POS  -> tighter (smaller k)
        NEUTRAL           -> unchanged
        NEG / STRONG_NEG  -> wider (bigger k)
    """
    if spot is None:
        return None

    # choose ATR
    a1 = atr14 or atr20
    a2 = atr20 or atr14
    if a1 is None or a2 is None:
        return None

    # confidence scaling
    if conf_pct is None:
        k = 1.0
    elif conf_pct >= 0.75:
        k = 0.7
    elif conf_pct >= 0.60:
        k = 0.85
    elif conf_pct >= 0.45:
        k = 1.0
    else:
        k = 1.15

    # -----------------------------
    # Phase 13D: alpha-regime factor
    # -----------------------------
    regime = None
    try:
        regime = (alpha_regime or {}).get("regime")
    except Exception:
        regime = None

    alpha_factor_map = {
        "STRONG_POS": 0.85,
        "POS": 0.92,
        "NEUTRAL": 1.00,
        "NEG": 1.08,
        "STRONG_NEG": 1.15,
    }
    alpha_factor = alpha_factor_map.get(regime, 1.00)

    # apply alpha scaling to k (tighten/widen)
    k = float(k) * float(alpha_factor)
    

    # -----------------------------
    # Phase 13C: liquidity-aware factor
    # - tighter bands when liquidity is strong
    # - wider bands when liquidity is weak
    # Accepts either:
    #   - auto_expiry metrics dict (pct_two_sided, median_spread_pct, pct_any_activity)
    #   - fallback dict (spread_pct, liq_ok)
    # -----------------------------
    liq_factor = 1.00
    try:
        m = liquidity_metrics or {}

        # prefer auto-expiry style keys if present
        pts = m.get("pct_two_sided", None)
        ms = m.get("median_spread_pct", None)

        # fallback to current-strike spread/liquidity gate
        if ms is None:
            ms = m.get("spread_pct", None)

        # normalize numeric parsing
        def _to_float(x):
            try:
                return float(x)
            except Exception:
                return None

        pts_f = _to_float(pts)
        ms_f = _to_float(ms)

        # if we only have liq_ok, use a coarse factor
        liq_ok = m.get("liq_ok", None)

        if pts_f is not None:
            # pct_two_sided is typically 0..1
            if pts_f >= 0.75:
                liq_factor *= 0.92
            elif pts_f >= 0.55:
                liq_factor *= 0.98
            elif pts_f >= 0.35:
                liq_factor *= 1.04
            else:
                liq_factor *= 1.10

        if ms_f is not None:
            # spread in % terms; lower is better
            if ms_f <= 0.25:
                liq_factor *= 0.92
            elif ms_f <= 0.50:
                liq_factor *= 0.97
            elif ms_f <= 0.90:
                liq_factor *= 1.03
            else:
                liq_factor *= 1.10
        elif liq_ok is not None:
            # last resort
            liq_factor *= 1.00 if bool(liq_ok) else 1.08

    except Exception:
        liq_factor = 1.00

    # apply liquidity scaling to k
    k = float(k) * float(liq_factor)

    # -----------------------------
    # Phase 13E: confidence-regime band multiplier
    # - widen/tighten bands deterministically
    # -----------------------------
    band_mult = 1.00
    try:
        band_mult = float((confidence_regime or {}).get("band_mult") or 1.00)
    except Exception:
        band_mult = 1.00
    band_mult = max(0.85, min(1.25, float(band_mult)))

    k = float(k) * float(band_mult)



    k2 = max(0.8, k)  # aggressive band uses similar k baseline

    v = (view or "").lower()
    # stance bias: bull wants lower entries; bear wants higher entries
    bias = 0.0
    if v in ["bull", "bullish"]:
        bias = -0.25
    elif v in ["bear", "bearish"]:
        bias = 0.25

    primary_low = spot + (bias - k) * a1
    primary_high = spot + (bias + k) * a1

    aggressive_low = spot + (bias - k2) * a2
    aggressive_high = spot + (bias + k2) * a2

    # invalidation = beyond primary by +0.75 ATR
    inv_low = primary_low - 0.75 * a1
    inv_high = primary_high + 0.75 * a1

    return {
        "atr14": round(float(atr14), 2) if atr14 is not None else None,
        "atr20": round(float(atr20), 2) if atr20 is not None else None,
        "k": round(float(k), 2),
        "alpha_regime": regime,                 # <-- NEW (for debugging / UI if you want later)
        "alpha_factor": round(alpha_factor, 2), # <-- NEW
        "liq_factor": round(float(liq_factor), 2),
        "band_mult": round(float(band_mult), 2),
        "primary": {"low": round(primary_low, 2), "high": round(primary_high, 2)},
        "aggressive": {"low": round(aggressive_low, 2), "high": round(aggressive_high, 2)},
        "invalidation": {"low": round(inv_low, 2), "high": round(inv_high, 2)},
    }

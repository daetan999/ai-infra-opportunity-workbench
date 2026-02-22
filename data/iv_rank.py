import math
from dataclasses import dataclass
from typing import Optional, List, Dict, Any

import yfinance as yf


@dataclass
class IVRankResult:
    current_iv: Optional[float]
    iv_rank: Optional[float]        # 0..1
    iv_percentile: Optional[float]  # 0..1
    lookback_days: int
    n_points: int
    note: str


def _pct_rank(values: List[float], x: float) -> float:
    # percentile: fraction <= x
    if not values:
        return 0.0
    count = sum(1 for v in values if v <= x)
    return count / len(values)


def compute_iv_rank(
    ticker: str,
    current_atm_iv: Optional[float],
    lookback_days: int = 252,
) -> IVRankResult:
    """
    Uses Yahoo daily 'impliedVolatility' series if available.
    If not available, returns note explaining why.
    """
    if current_atm_iv is None or not (current_atm_iv > 0):
        return IVRankResult(
            current_iv=current_atm_iv,
            iv_rank=None,
            iv_percentile=None,
            lookback_days=lookback_days,
            n_points=0,
            note="Current ATM IV missing; cannot compute IV rank.",
        )

    try:
        t = yf.Ticker(ticker)
        hist = t.history(period="2y", interval="1d", auto_adjust=False)
        if hist is None or hist.empty:
            return IVRankResult(current_atm_iv, None, None, lookback_days, 0, "No price history returned.")

        # Yahoo sometimes exposes impliedVolatility as a column; sometimes it doesn't.
        col = None
        for c in hist.columns:
            if str(c).lower() == "impliedvolatility":
                col = c
                break

        if col is None:
            return IVRankResult(
                current_atm_iv,
                None,
                None,
                lookback_days,
                0,
                "Yahoo history has no impliedVolatility column for this ticker.",
            )

        series = hist[col].dropna().astype(float).tolist()
        if not series:
            return IVRankResult(current_atm_iv, None, None, lookback_days, 0, "Implied volatility series empty.")

        # take most recent lookback_days points
        series = series[-lookback_days:]

        lo = min(series)
        hi = max(series)
        if hi <= lo or not math.isfinite(lo) or not math.isfinite(hi):
            return IVRankResult(current_atm_iv, None, None, lookback_days, len(series), "IV series not usable.")

        iv_rank = (current_atm_iv - lo) / (hi - lo)
        iv_rank = max(0.0, min(1.0, iv_rank))

        iv_pct = _pct_rank(series, current_atm_iv)
        iv_pct = max(0.0, min(1.0, iv_pct))

        return IVRankResult(
            current_iv=current_atm_iv,
            iv_rank=iv_rank,
            iv_percentile=iv_pct,
            lookback_days=lookback_days,
            n_points=len(series),
            note="ok",
        )

    except Exception as e:
        return IVRankResult(current_atm_iv, None, None, lookback_days, 0, f"IV rank error: {e}")

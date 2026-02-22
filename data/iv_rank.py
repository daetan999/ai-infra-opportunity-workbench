import math
import time as _time
from dataclasses import dataclass
from typing import Optional, List, Dict, Any

import yfinance as yf

try:
    from data.cache import COMPANY_CACHE as _IV_CACHE
except ImportError:
    _IV_CACHE = None

def _yf_call_iv(fn, retries: int = 3, base_delay: float = 2.0):
    """429-backoff wrapper for iv_rank yfinance calls."""
    for attempt in range(retries):
        try:
            return fn()
        except Exception as exc:
            msg = str(exc).lower()
            is_rl = any(k in msg for k in ("too many requests", "rate limit", "429", "rateerror"))
            if is_rl and attempt < retries - 1:
                _time.sleep(base_delay * (2 ** attempt))
            else:
                return None
    return None


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
        _iv_key = f"hist:{ticker}:2y:1d"
        if _IV_CACHE is not None:
            hist = _IV_CACHE.get_or_set(
                _iv_key,
                lambda: _yf_call_iv(lambda: t.history(period="2y", interval="1d", auto_adjust=False)),
                ttl_sec=12 * 3600,  # 12h — IV history doesn't need frequent refresh
            )
        else:
            hist = _yf_call_iv(lambda: t.history(period="2y", interval="1d", auto_adjust=False))
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
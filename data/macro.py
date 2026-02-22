from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import time
import yfinance as yf

try:
    from data.cache import COMPANY_CACHE as _MACRO_CACHE
except ImportError:
    _MACRO_CACHE = None

def _yf_call_macro(fn, retries: int = 3, base_delay: float = 2.0):
    """429-backoff wrapper for macro.py yfinance calls."""
    for attempt in range(retries):
        try:
            return fn()
        except Exception as exc:
            msg = str(exc).lower()
            is_rl = any(k in msg for k in ("too many requests", "rate limit", "429", "rateerror"))
            if is_rl and attempt < retries - 1:
                time.sleep(base_delay * (2 ** attempt))
            else:
                return None
    return None


@dataclass
class MacroReport:
    asof_utc: str
    items: list[dict]


_CACHE: dict = {"ts": 0.0, "report": None}


def _safe_last_and_change(symbol: str):
    t = yf.Ticker(symbol)
    _mk = f"hist:{symbol}:5d:1d"
    if _MACRO_CACHE is not None:
        hist = _MACRO_CACHE.get_or_set(
            _mk,
            lambda _s=symbol: _yf_call_macro(lambda: yf.Ticker(_s).history(period="5d", interval="1d")),
            ttl_sec=1800,  # 30 min — macro prices refresh fast enough
        )
    else:
        hist = _yf_call_macro(lambda: t.history(period="5d", interval="1d"))
    if hist is None or hist.empty:
        return None, None
    closes = hist["Close"].dropna()
    if len(closes) == 0:
        return None, None
    last = float(closes.iloc[-1])
    if len(closes) >= 2:
        prev = float(closes.iloc[-2])
        chg_pct = (last / prev - 1.0) if prev != 0 else None
    else:
        chg_pct = None
    return last, chg_pct


def get_macro_report(ttl_seconds: int = 300) -> MacroReport:
    now = time.time()
    if _CACHE["report"] is not None and (now - _CACHE["ts"] < ttl_seconds):
        return _CACHE["report"]

    watch = [
        {"name": "VIX", "symbol": "^VIX", "note": "risk appetite / fear gauge"},
        {"name": "US Dollar Index", "symbol": "DX-Y.NYB", "note": "USD strength proxy"},
        {"name": "WTI Oil", "symbol": "CL=F", "note": "energy / inflation impulse proxy"},
        {"name": "S&P 500", "symbol": "SPY", "note": "broad risk"},
        {"name": "Nasdaq 100", "symbol": "QQQ", "note": "tech risk"},
        {"name": "Semis ETF", "symbol": "SOXX", "note": "semis sector risk"},
        {"name": "Semis ETF (alt)", "symbol": "SMH", "note": "semis sector risk (alt)"},
        {"name": "US 10Y Yield", "symbol": "^TNX", "note": "rates proxy (TNX is ~yield*10)"},
    ]

    items = []
    for w in watch:
        last, chg = _safe_last_and_change(w["symbol"])
        items.append(
            {"name": w["name"], "symbol": w["symbol"], "last": last, "chg_pct": chg, "note": w["note"]}
        )

    asof = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    report = MacroReport(asof_utc=asof, items=items)
    _CACHE["ts"] = now
    _CACHE["report"] = report
    return report


def macro_report_to_dict(report: MacroReport) -> dict:
    return {"asof_utc": report.asof_utc, "items": report.items}
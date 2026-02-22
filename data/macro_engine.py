# data/macro_engine.py

from __future__ import annotations

import time
from pathlib import Path
import json
from typing import Dict, Any
from datetime import datetime, timezone

import numpy as np
import yfinance as yf
import pandas as pd


CACHE_PATH = Path(__file__).resolve().parent / "macro_cache.json"
CACHE_TTL = 60 * 10   # 10 minutes


PROXIES = {
    "rates": "^TNX",
    "dollar": "UUP",
    "vol": "^VIX",
    "equity": "SPY",
    "credit": "HYG",
    "oil": "USO",
    "semis": "SMH",
}


# ============================
# Small helpers
# ============================

def _trend(series, lookback=20):
    if series is None or len(series) < lookback:
        return None

    recent = series[-lookback:]
    slope = np.polyfit(range(len(recent)), recent, 1)[0]

    if slope > 0:
        return "up"
    if slope < 0:
        return "down"
    return "flat"


def _safe_last(series):
    if series is None or len(series) == 0:
        return None
    return float(series[-1])

def _pct_change(series, n):
    if series is None or len(series) <= n:
        return None
    return float(series[-1] / series[-(n + 1)] - 1.0)


def _zscore(series):
    if series is None or len(series) < 30:
        return None
    mean = float(series.mean())
    std = float(series.std())
    if std == 0:
        return None
    return float((series.iloc[-1] - mean) / std)


# ============================
# Build macro snapshot
# ============================

def _build_macro_snapshot() -> Dict[str, Any]:

    tickers = list(PROXIES.values())

    # Bulk download (MUCH faster + consistent)
    df = yf.download(
        tickers,
        period="3mo",
        interval="1d",
        group_by="ticker",
        progress=False,
        threads=True,
    )

    print("MACRO DF EMPTY?", df.empty)
    print("MACRO DF COLS:", df.columns)

    snapshot: Dict[str, Any] = {}

    for name, sym in PROXIES.items():

        try:
            # MultiIndex: df[(sym, "Close")]
            close = df[(sym, "Close")].dropna()

            if close.empty:
                raise ValueError("No close prices")

            level = float(close.iloc[-1])

            chg5 = (
                (close.iloc[-1] / close.iloc[-6] - 1)
                if len(close) >= 6 else None
            )

            chg20 = (
                (close.iloc[-1] / close.iloc[-21] - 1)
                if len(close) >= 21 else None
            )

            zscore = None
            if len(close) >= 60:
                zscore = float(
                    (close.iloc[-1] - close.iloc[-60:].mean())
                    / close.iloc[-60:].std()
                )

            # Simple trend label
            trend = None
            if chg20 is not None:
                if chg20 > 0.02:
                    trend = "up"
                elif chg20 < -0.02:
                    trend = "down"
                else:
                    trend = "flat"

            snapshot[name] = {
                "ticker": sym,
                "level": level,
                "trend": trend,
                "chg5": chg5,
                "chg20": chg20,
                "zscore_3m": zscore,
            }

        except Exception as e:

            print("MACRO FAIL:", sym, e)

            snapshot[name] = {
                "ticker": sym,
                "level": None,
                "trend": None,
                "chg5": None,
                "chg20": None,
                "zscore_3m": None,
            }

    # -------------------------
    # Risk regime heuristic
    # -------------------------

    risk_score = 0

    if snapshot.get("vol", {}).get("trend") == "up":
        risk_score -= 1

    if snapshot.get("rates", {}).get("trend") == "up":
        risk_score -= 1

    if snapshot.get("credit", {}).get("trend") == "down":
        risk_score -= 1

    if snapshot.get("equity", {}).get("trend") == "up":
        risk_score += 1

    if snapshot.get("semis", {}).get("trend") == "up":
        risk_score += 1

    if risk_score >= 2:
        regime = "RISK_ON"
    elif risk_score <= -2:
        regime = "RISK_OFF"
    else:
        regime = "NEUTRAL"

    warnings = []
    if snapshot.get("vol", {}).get("trend") == "up":
        warnings.append("VIX rising")
    if snapshot.get("rates", {}).get("trend") == "up":
        warnings.append("Rates rising")
    if snapshot.get("credit", {}).get("trend") == "down":
        warnings.append("Credit weakening")

    snapshot["risk_regime"] = regime
    snapshot["warnings"] = warnings

    return snapshot



# ============================
# Cache wrapper
# ============================

def get_macro_snapshot(force=False) -> Dict[str, Any]:

    if not force and CACHE_PATH.exists():
        try:
            obj = json.loads(CACHE_PATH.read_text())
            if time.time() - obj.get("generated_at", 0) < CACHE_TTL:
                return obj["data"]
        except Exception:
            pass

    data = _build_macro_snapshot()

    try:
        CACHE_PATH.write_text(json.dumps({
            "generated_at": time.time(),
            "data": data,
        }, indent=2))
    except Exception:
        pass

    return data

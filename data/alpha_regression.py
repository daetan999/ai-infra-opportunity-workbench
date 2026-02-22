# data/alpha_regression.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Any
import numpy as np
import pandas as pd
import yfinance as yf


def _safe_close(df: pd.DataFrame) -> Optional[pd.Series]:
    """
    Accepts yf.download output. Returns Close series if possible.
    """
    if df is None or df.empty:
        return None
    if isinstance(df.columns, pd.MultiIndex):
        # yf.download with multiple tickers -> columns like ('Close','NVDA')
        if ("Close" in df.columns.get_level_values(0)):
            close = df["Close"]
            if isinstance(close, pd.DataFrame):
                # still per-ticker columns
                return close
    else:
        if "Close" in df.columns:
            return df["Close"]
    return None


def _ols_beta_alpha(x: pd.Series, y: pd.Series) -> Dict[str, Any]:
    """
    Deterministic OLS on returns: y = a + b*x.
    Returns beta, alpha (daily), r2.
    """
    xy = pd.concat([x, y], axis=1).dropna()
    if xy.shape[0] < 15:
        return {"beta": None, "alpha_daily": None, "r2": None}

    x = xy.iloc[:, 0].astype(float)
    y = xy.iloc[:, 1].astype(float)

    vx = float(np.var(x, ddof=0))
    if vx <= 1e-12:
        return {"beta": None, "alpha_daily": None, "r2": None}

    cov = float(np.mean((x - x.mean()) * (y - y.mean())))
    beta = cov / vx
    alpha = float(y.mean() - beta * x.mean())

    corr = float(np.corrcoef(x, y)[0, 1]) if xy.shape[0] >= 2 else 0.0
    r2 = corr * corr

    return {"beta": float(beta), "alpha_daily": float(alpha), "r2": float(r2)}


def compute_alpha_snapshot(
    ticker: str,
    peers: List[str],
    sox_proxy: str = "SOXX",
    window: int = 60,
    period: str = "6mo",
) -> Dict[str, Any]:
    """
    Deterministic alpha/beta snapshot:
    - Ticker vs peer basket (equal-weight)
    - Ticker vs SOX proxy (default SOXX)
    Uses daily log returns and rolling window. Returns last values.
    """
    tkr = (ticker or "").strip().upper()
    ps = [p.strip().upper() for p in (peers or []) if p]
    ps = [p for p in ps if p != tkr]

    symbols = [tkr] + ps + [sox_proxy]

    try:
        df = yf.download(symbols, period=period, interval="1d", group_by="column", auto_adjust=False, progress=False)
    except Exception:
        return {
            "ok": False,
            "error": "yfinance download failed",
            "sox_proxy": sox_proxy,
        }

    close = _safe_close(df)
    if close is None or close.empty:
        return {
            "ok": False,
            "error": "no close data",
            "sox_proxy": sox_proxy,
        }

    # close can be DataFrame (multi-ticker) or Series (single)
    if isinstance(close, pd.Series):
        # should not happen because we request multiple symbols, but handle anyway
        return {"ok": False, "error": "unexpected close shape", "sox_proxy": sox_proxy}

    # Ensure required columns exist
    if tkr not in close.columns:
        return {"ok": False, "error": f"missing ticker {tkr}", "sox_proxy": sox_proxy}

    # Build benchmark series
    bench_peer = None
    if ps:
        have = [p for p in ps if p in close.columns]
        if have:
            bench_peer = close[have].mean(axis=1)

    bench_sox = close[sox_proxy] if sox_proxy in close.columns else None

    # log returns
    ret_t = np.log(close[tkr] / close[tkr].shift(1))

    out: Dict[str, Any] = {
        "ok": True,
        "ticker": tkr,
        "sox_proxy": sox_proxy,
        "window": int(window),
        "period": period,
    }

    def last_rolling_stats(bench: pd.Series, label: str):
        r_b = np.log(bench / bench.shift(1))
        df2 = pd.concat([r_b, ret_t], axis=1).dropna()
        if df2.shape[0] < window + 5:
            out[label] = {"beta": None, "alpha_daily": None, "r2": None, "alpha_60d_cum_pct": None}
            return

        x = df2.iloc[:, 0]
        y = df2.iloc[:, 1]

        # rolling beta/alpha
        betas = []
        alphas = []
        r2s = []
        idxs = []

        for i in range(window, len(df2) + 1):
            xs = x.iloc[i - window:i]
            ys = y.iloc[i - window:i]
            stats = _ols_beta_alpha(xs, ys)
            betas.append(stats["beta"])
            alphas.append(stats["alpha_daily"])
            r2s.append(stats["r2"])
            idxs.append(df2.index[i - 1])

        beta_last = betas[-1]
        alpha_last = alphas[-1]
        r2_last = r2s[-1]

        # alpha cumulative over window (approx): sum(residuals) in pct terms
        xs = x.iloc[-window:]
        ys = y.iloc[-window:]
        if beta_last is None:
            alpha_cum = None
        else:
            resid = ys - (alpha_last + beta_last * xs)
            alpha_cum = float(np.expm1(resid.sum())) * 100.0  # % cumulative

        out[label] = {
            "beta": None if beta_last is None else round(float(beta_last), 3),
            "alpha_daily": None if alpha_last is None else round(float(alpha_last), 6),
            "r2": None if r2_last is None else round(float(r2_last), 3),
            "alpha_60d_cum_pct": None if alpha_cum is None else round(float(alpha_cum), 2),
        }

    # vs peers
    if bench_peer is not None:
        last_rolling_stats(bench_peer, "vs_peers")
    else:
        out["vs_peers"] = {"beta": None, "alpha_daily": None, "r2": None, "alpha_60d_cum_pct": None}

    # vs sox proxy
    if bench_sox is not None and not bench_sox.dropna().empty:
        last_rolling_stats(bench_sox, "vs_sox")
    else:
        out["vs_sox"] = {"beta": None, "alpha_daily": None, "r2": None, "alpha_60d_cum_pct": None}

    return out

def classify_alpha_regime(alpha_snapshot: dict) -> dict:
    """
    Deterministic classification from alpha_snapshot.
    Prefers vs_peers; falls back to vs_sox.
    """
    if not alpha_snapshot or not alpha_snapshot.get("ok"):
        return {"regime": None}

    snap = alpha_snapshot.get("vs_peers") or alpha_snapshot.get("vs_sox") or {}
    val = snap.get("alpha_60d_cum_pct")

    if val is None:
        return {"regime": None}

    if val > 3:
        r = "STRONG_POS"
    elif val > 1:
        r = "POS"
    elif val < -3:
        r = "STRONG_NEG"
    elif val < -1:
        r = "NEG"
    else:
        r = "NEUTRAL"

    return {
        "regime": r,
        "alpha_60d_cum_pct": val,
        "beta": snap.get("beta"),
        "anchor": "vs_peers" if alpha_snapshot.get("vs_peers") else "vs_sox",
    }

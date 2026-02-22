# data/iv_history.py
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any


@dataclass
class IVRankResult:
    current_iv: Optional[float]
    iv_rank: Optional[float]         # 0..1
    iv_percentile: Optional[float]   # 0..1
    lookback_days: int
    n_points: int
    note: str


def _path_for(ticker: str) -> str:
    # stores one file per ticker
    folder = os.path.join("data", "iv_store")
    os.makedirs(folder, exist_ok=True)
    return os.path.join(folder, f"{ticker.upper()}_atm_iv.json")


def append_atm_iv_snapshot(
    ticker: str,
    expiry: str,
    atm_iv: Optional[float],
) -> None:
    """
    Append one snapshot {ts_utc, expiry, atm_iv}.
    Safe: does nothing if atm_iv is None.
    """
    if atm_iv is None:
        return

    path = _path_for(ticker)
    now = datetime.now(timezone.utc).isoformat()

    row = {"ts_utc": now, "expiry": expiry, "atm_iv": float(atm_iv)}

    data: List[Dict[str, Any]] = []
    if os.path.exists(path):
        try:
            with open(path, "r") as f:
                data = json.load(f) or []
        except Exception:
            data = []

    data.append(row)

    # keep file from growing forever (keep last ~2000 points)
    if len(data) > 2000:
        data = data[-2000:]

    with open(path, "w") as f:
        json.dump(data, f)


def compute_iv_rank_from_snapshots(
    ticker: str,
    current_atm_iv: Optional[float],
    lookback_days: int = 252,
) -> IVRankResult:
    """
    Compute IV Rank / Percentile using stored ATM IV snapshots.
    Rank = (current - min) / (max - min)
    Percentile = pct of samples <= current
    """
    if current_atm_iv is None:
        return IVRankResult(
            current_iv=None,
            iv_rank=None,
            iv_percentile=None,
            lookback_days=lookback_days,
            n_points=0,
            note="No current ATM IV (cannot compute rank).",
        )

    path = _path_for(ticker)
    if not os.path.exists(path):
        return IVRankResult(
            current_iv=float(current_atm_iv),
            iv_rank=None,
            iv_percentile=None,
            lookback_days=lookback_days,
            n_points=0,
            note="No stored IV history yet. Run reports over time to build it.",
        )

    try:
        with open(path, "r") as f:
            data = json.load(f) or []
    except Exception as e:
        return IVRankResult(
            current_iv=float(current_atm_iv),
            iv_rank=None,
            iv_percentile=None,
            lookback_days=lookback_days,
            n_points=0,
            note=f"Could not read IV history file: {e}",
        )

    # pull atm_iv values only
    vals = []
    for row in data:
        v = row.get("atm_iv")
        if isinstance(v, (int, float)) and v > 0:
            vals.append(float(v))

    if len(vals) < 10:
        return IVRankResult(
            current_iv=float(current_atm_iv),
            iv_rank=None,
            iv_percentile=None,
            lookback_days=lookback_days,
            n_points=len(vals),
            note="Not enough stored IV points yet (need ~10+).",
        )

    vmin = min(vals)
    vmax = max(vals)
    if vmax <= vmin:
        return IVRankResult(
            current_iv=float(current_atm_iv),
            iv_rank=None,
            iv_percentile=None,
            lookback_days=lookback_days,
            n_points=len(vals),
            note="IV history is flat (cannot compute rank).",
        )

    cur = float(current_atm_iv)
    iv_rank = (cur - vmin) / (vmax - vmin)
    iv_rank = max(0.0, min(1.0, iv_rank))

    # percentile: fraction <= current
    le = sum(1 for x in vals if x <= cur)
    iv_pct = le / len(vals)
    iv_pct = max(0.0, min(1.0, iv_pct))

    return IVRankResult(
        current_iv=cur,
        iv_rank=float(iv_rank),
        iv_percentile=float(iv_pct),
        lookback_days=lookback_days,
        n_points=len(vals),
        note="IV rank computed from stored ATM IV snapshots (deterministic).",
    )

"""
Unit conversion layer.
Rules:
  - Internally store IV Rank as iv_rank_01   (0-1 fraction)
  - Internally store spreads as spread_01    (0-1 fraction)
  - Convert to "% strings" only at render boundaries (template layer)
"""

def pct01_to_pct100(x01: float) -> float:
    if x01 is None:
        return None
    return float(x01) * 100.0


def pct100_to_pct01(x100: float) -> float:
    if x100 is None:
        return None
    return float(x100) / 100.0


def spread_mid_fraction(bid: float, ask: float) -> float:
    if bid is None or ask is None:
        return float("inf")
    mid = 0.5 * (bid + ask)
    return (ask - bid) / mid if mid > 0 else float("inf")


def ensure_pct100(value: float, threshold: float = 1.5) -> float:
    """
    Ensure iv_rank is on the 0-100 scale.
    If value <= threshold (likely 0-1 fraction), multiply by 100.
    """
    if value is None:
        return None
    v = float(value)
    if 0.0 <= v <= threshold:
        return v * 100.0
    return v


def ensure_pct01(value: float, threshold: float = 1.5) -> float:
    """
    Ensure iv_rank is on the 0-1 scale.
    If value > threshold (likely 0-100), divide by 100.
    """
    if value is None:
        return None
    v = float(value)
    if v > threshold:
        return v / 100.0
    return v

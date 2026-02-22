# data/glossary.py

GLOSSARY: dict[str, str] = {
    # Liquidity / quoting coverage
    "median_spread_pct": "median bid–ask spread; lower=better",
    "pct_two_sided": "% strikes with both bid & ask; higher=better",
    "pct_with_quotes": "% strikes with any quote; higher=better",
    "pct_any_activity": "% strikes w volume or OI; higher=better",
    "open_interest": "total contracts open; higher often=more liquid",
    "oi_total": "total open interest in ATM window; higher=more liquidity",
    "vol_total": "total volume in ATM window; higher=more activity",
    "oi_norm": "oi_total normalized vs best expiry (0-1)",
    "vol_norm": "vol_total normalized vs best expiry (0-1)",
    "quote_quality_mult": "score multiplier from pct_two_sided",
    "quote_gate_capped": "1 if capped due to low pct_two_sided",
    "liq_grade": "A/B/C liquidity grade from score",
    "liq_label": "plain-English liquidity verdict",


    # Common option fields (optional)
    "volume": "contracts traded today",
    "bid": "best bid price",
    "ask": "best ask price",
    "mid": "(bid+ask)/2",
    "iv": "implied volatility",
}

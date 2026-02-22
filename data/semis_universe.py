# data/semis_universe.py

from __future__ import annotations

from typing import List, Dict, Any
from pathlib import Path
import json
import time

import yfinance as yf


# -----------------------------
# 1) Universe tickers (you expand this)
# -----------------------------
RAW_TICKERS = [
    # Compute / AI / CPUs / GPUs
    "NVDA","AMD","INTC","ARM","AVGO","QCOM","MRVL","ANET","SMCI","DELL","HPE",

    # Analog / Power / Mixed-signal
    "TXN","ADI","ON","MCHP","MPWR","NXPI","STM","IFNNY",
    "SLAB","CRUS","MTSI","DIOD","VSH","ALGM",
    "POWI","AEIS",

    # RF / Connectivity
    "SWKS","QRVO",

    # Memory / Storage
    "MU","WDC","STX","SIMO",

    # Foundry / manufacturing (US-traded ADRs)
    "TSM","UMC","GFS",

    # Equipment / WFE / Metrology / Inspection / Test
    "ASML","AMAT","LRCX","KLAC","TER","ACLS","ONTO","MKSI","ENTG",
    "COHU","AEHR","CAMT","FORM","IPGP","UCTT","VECO","ASMIY",

    # EDA / IP
    "CDNS","SNPS","RMBS",

    # Programmable / specialty logic
    "LSCC",

    # Silicon carbide / power
    "WOLF",

    # Packaging / OSAT (US-traded)
    "ASX","AMKR",
]

# -----------------------------
# 1b) Sector buckets (manual tagging)
# -----------------------------
SECTOR_BUCKET_BY_SYMBOL = {
    # GPU / AI / Compute
    "NVDA": "GPU / AI",
    "AMD": "CPU / GPU",
    "INTC": "CPU / Foundry",
    "ARM": "CPU / IP",
    "AVGO": "Networking / ASIC",
    "MRVL": "Networking / ASIC",
    "ANET": "Networking",
    "SMCI": "Servers / Systems",
    "DELL": "Servers / Systems",
    "HPE": "Servers / Systems",

    # Analog / Power / Mixed-signal
    "TXN": "Analog",
    "ADI": "Analog",
    "ON": "Power / Auto",
    "MCHP": "MCU / Embedded",
    "MPWR": "Power",
    "NXPI": "Auto / MCU",
    "STM": "Mixed-signal / Auto",
    "IFNNY": "Power / Auto",
    "SLAB": "Mixed-signal",
    "CRUS": "Mixed-signal",
    "DIOD": "Discrete / Power",
    "VSH": "Discrete / Power",
    "ALGM": "Auto / Sensors",
    "POWI": "Power",
    "AEIS": "Power / Industrial",

    # RF / Connectivity
    "QCOM": "Mobile / Connectivity",
    "SWKS": "RF",
    "QRVO": "RF",

    # Memory / Storage
    "MU": "Memory",
    "WDC": "Storage",
    "STX": "Storage",
    "SIMO": "Storage / Controllers",

    # Foundry / Manufacturing (US-traded)
    "TSM": "Foundry ADR",
    "UMC": "Foundry ADR",
    "GFS": "Foundry (US)",

    # Equipment / WFE / Metrology / Test
    "ASML": "WFE",
    "AMAT": "WFE",
    "LRCX": "WFE",
    "KLAC": "Metrology / Inspection",
    "TER": "Test / ATE",
    "ACLS": "WFE",
    "ONTO": "Metrology / Inspection",
    "MKSI": "WFE",
    "ENTG": "Materials / Suppliers",
    "COHU": "Test / ATE",
    "AEHR": "Test / Burn-in",
    "CAMT": "Metrology / Inspection",
    "FORM": "WFE",
    "IPGP": "Photonics / Lasers",
    "UCTT": "Materials / Suppliers",
    "VECO": "WFE",
    "ASMIY": "WFE",

    # EDA / IP
    "CDNS": "EDA",
    "SNPS": "EDA",
    "RMBS": "IP / Memory",

    # FPGA / Specialty logic
    "LSCC": "FPGA",

    # SiC / Power
    "WOLF": "SiC / Power",

    # OSAT / Packaging (US-traded)
    "ASX": "OSAT / Packaging",
    "AMKR": "OSAT / Packaging",
}



# -----------------------------
# 2) Caching config
# -----------------------------
CACHE_PATH = Path(__file__).resolve().parent / "semis_universe_cache.json"
CACHE_TTL_SECONDS = 60 * 60 * 24 * 7  # 7 days (change if you want)
CACHE_VERSION = 2

# Yahoo/yfinance exchange codes -> display exchange
EXCHANGE_MAP = {
    "NMS": "NASDAQ",
    "NGM": "NASDAQ",
    "NGS": "NASDAQ",
    "NAS": "NASDAQ",
    "NYQ": "NYSE",
    "ASE": "AMEX",        # NYSE American (we'll call it AMEX)
    "PCX": "AMEX",
    "BATS": "BATS",
    "OTC": "OTC",
    "PNK": "OTC",
}

US_EXCHANGE_ALLOW = {"NASDAQ", "NYSE", "AMEX", "BATS"}
US_EXCHANGE_BLOCK = {"OTC", "PNK"}

def normalize_exchange(raw: str | None) -> str:
    if not raw:
        return "US"
    code = str(raw).upper()
    return EXCHANGE_MAP.get(code, code)

def is_us_listed(exchange_display: str) -> bool:
    ex = (exchange_display or "").upper().strip()
    if ex in US_EXCHANGE_BLOCK:
        return False
    # If yfinance gives weird codes, we still allow if it maps to known US venues
    return ex in US_EXCHANGE_ALLOW or ex == "US"


def _build_fresh_universe() -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []

    for sym in RAW_TICKERS:
        sym = sym.strip().upper()
        try:
            t = yf.Ticker(sym)
            info = t.info or {}

            name = info.get("longName") or info.get("shortName") or sym
            exch = normalize_exchange(info.get("exchange"))

            # US-only filter
            if not is_us_listed(exch):
                continue

            sector_bucket = SECTOR_BUCKET_BY_SYMBOL.get(sym, "Other")

            out.append({
                "symbol": sym,
                "exchange": exch,
                "name": name,
                "display": f"{name} ({exch}:{sym})",
                "sector_bucket": sector_bucket,
            })


        except Exception:
            out.append({
                "symbol": sym,
                "exchange": "US",
                "name": sym,
                "display": f"{sym} (US:{sym})",
            })

    # Deduplicate by symbol (in case you accidentally add twice)
    dedup = {}
    for row in out:
        dedup[row["symbol"]] = row

    # Sort by name for UI
    return sorted(dedup.values(), key=lambda x: x["name"])

def _cache_is_fresh(cache_obj: Dict[str, Any]) -> bool:
    ts = cache_obj.get("generated_at")
    if not isinstance(ts, (int, float)):
        return False
    return (time.time() - ts) <= CACHE_TTL_SECONDS

def load_semis_universe(force_refresh: bool = False) -> List[Dict[str, Any]]:
    """
    Instant response path:
    - Use cache if fresh
    - Otherwise rebuild and write cache
    """
    if not force_refresh and CACHE_PATH.exists():
        try:
            cache_obj = json.loads(CACHE_PATH.read_text(encoding="utf-8"))

            # If schema changed, force rebuild
            if cache_obj.get("version") != CACHE_VERSION:
                raise ValueError("Universe cache version mismatch")

            if _cache_is_fresh(cache_obj) and isinstance(cache_obj.get("data"), list):
                return cache_obj["data"]

        except Exception:
            # If cache corrupt, fall through to rebuild
            pass

    data = _build_fresh_universe()
    cache_obj = {
        "version": CACHE_VERSION,
        "generated_at": time.time(),
        "ttl_seconds": CACHE_TTL_SECONDS,
        "data": data,
    }

    try:
        CACHE_PATH.write_text(json.dumps(cache_obj, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        # If writing fails, still return data (don’t crash the endpoint)
        pass

    return data

def search_semis_universe(q: str = "", limit: int = 50, force_refresh: bool = False) -> List[Dict[str, Any]]:
    """
    Returns a list of rows from the semis universe, filtered by query.
    Each row already has:
      - symbol
      - name
      - exchange
      - display  (e.g. "NVIDIA (NASDAQ:NVDA)")
    """
    data = load_semis_universe(force_refresh=force_refresh)

    q = (q or "").strip().lower()
    if not q:
        return data[:limit]

    hits = []
    for x in data:
        sym = (x.get("symbol") or "").lower()
        name = (x.get("name") or "").lower()
        exch = (x.get("exchange") or "").lower()
        disp = (x.get("display") or "").lower()

        if q in sym or q in name or q in exch or q in disp:
            hits.append(x)

    # rank: symbol prefix > name prefix > contains
    def score(row):
        sym = (row.get("symbol") or "").lower()
        name = (row.get("name") or "").lower()
        return (
            0 if sym.startswith(q) else 1,
            0 if name.startswith(q) else 1,
            len(name),
        )

    hits.sort(key=score)
    return hits[:limit]


_SECTOR_BUCKET_CACHE: dict[str, str] | None = None

def sector_bucket_for(symbol: str) -> str | None:
    global _SECTOR_BUCKET_CACHE
    s = (symbol or "").upper().strip()
    try:
        if _SECTOR_BUCKET_CACHE is None:
            _SECTOR_BUCKET_CACHE = {}
            for row in load_semis_universe(force_refresh=False):
                sym = (row.get("symbol") or "").upper().strip()
                if sym:
                    _SECTOR_BUCKET_CACHE[sym] = row.get("sector_bucket") or "Other"
        return _SECTOR_BUCKET_CACHE.get(s)
    except Exception:
        return None


def sector_bucket_for(symbol: str) -> str | None:
    """
    Deterministic lookup of sector_bucket from the cached semis universe.
    """
    s = (symbol or "").upper().strip()
    try:
        data = load_semis_universe(force_refresh=False)
        for row in data:
            if (row.get("symbol") or "").upper().strip() == s:
                return row.get("sector_bucket")
    except Exception:
        return None
    return None

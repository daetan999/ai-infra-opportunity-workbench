# news.py
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

# deterministic keyword tagging (no AI, no sentiment)
KEYWORDS = {
    "earnings": ["earnings", "eps", "revenue", "results", "quarter", "q1", "q2", "q3", "q4"],
    "guidance": ["guidance", "outlook", "forecast", "raises", "cuts", "expects", "sees"],
    "analyst": ["upgrade", "downgrade", "price target", "pt", "initiates", "coverage"],
    "mna": ["acquire", "acquisition", "merge", "merger", "buyout", "takeover", "deal"],
    "regulation": ["antitrust", "probe", "ban", "sanction", "export", "restriction", "license", "entity list"],
    "china": ["china", "beijing", "taiwan", "huawei", "smic"],
    "capacity": ["fab", "capacity", "wafer", "expansion", "plant", "capex"],
    "product": ["launch", "chip", "gpu", "cpu", "ai", "accelerator", "node", "process"],
    "supply_chain": ["shortage", "inventory", "supply", "demand", "shipment", "backlog"],
}

# simple severity rules (deterministic; no AI)
SEVERITY_KEYWORDS = {
    "HIGH": ["sec", "doj", "lawsuit", "fraud", "investigation", "ban", "sanction", "export restriction", "recall"],
    "MED": ["guidance", "outlook", "forecast", "downgrade", "upgrade", "price target", "probe", "delay"],
}

SEVERITY_HIGH = ["ban", "sanction", "export restriction", "probe", "antitrust", "cuts guidance", "warning"]
SEVERITY_MED = ["guidance", "earnings", "downgrade", "upgrade", "capex", "capacity"]

def _safe_str(x: Any) -> str | None:
    if x is None:
        return None
    s = str(x).strip()
    return s if s else None

def _utc_iso_from_epoch(sec: Any) -> str | None:
    try:
        if sec is None:
            return None
        ts = int(sec)
        return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()
    except Exception:
        return None

def _age_hours(published_utc: str | None) -> float | None:
    try:
        if not published_utc:
            return None
        dt = datetime.fromisoformat(published_utc.replace("Z", "+00:00"))
        now = datetime.now(timezone.utc)
        return round((now - dt).total_seconds() / 3600.0, 2)
    except Exception:
        return None

def _severity(title: str, tags: list[str]) -> str:
    t = (title or "").lower()

    # explicit keyword hits first
    for kw in SEVERITY_KEYWORDS["HIGH"]:
        if kw in t:
            return "HIGH"
    for kw in SEVERITY_KEYWORDS["MED"]:
        if kw in t:
            return "MED"

    # tag-based fallback (still deterministic)
    if "regulation" in tags or "mna" in tags:
        return "MED"

    return "LOW"


def _tag_and_severity(title: str) -> tuple[list[str], str]:
    t = (title or "").lower()
    tags: list[str] = []
    for tag, kws in KEYWORDS.items():
        if any(kw in t for kw in kws):
            tags.append(tag)

    sev = "LOW"
    if any(x in t for x in SEVERITY_HIGH):
        sev = "HIGH"
    elif any(x in t for x in SEVERITY_MED):
        sev = "MED"
    return tags, sev


def _tag_headline(title: str) -> list[str]:
    t = title.lower()
    tags: list[str] = []
    for tag, kws in KEYWORDS.items():
        for kw in kws:
            if kw in t:
                tags.append(tag)
                break
    return tags

def get_company_snapshot(ticker_obj) -> dict:
    """
    Deterministic company snapshot from yfinance .info only.
    """
    info = {}
    try:
        info = ticker_obj.info or {}
    except Exception:
        info = {}

    summary = _safe_str(info.get("longBusinessSummary"))
    if summary and len(summary) > 700:
        summary = summary[:700].rstrip() + "…"

    return {
        "name": _safe_str(info.get("longName") or info.get("shortName")),
        "sector": _safe_str(info.get("sector")),
        "industry": _safe_str(info.get("industry")),
        "website": _safe_str(info.get("website")),
        "summary": summary,
        "country": _safe_str(info.get("country")),
    }

def get_latest_headlines(ticker_obj, max_items: int = 8) -> list[dict]:
    """
    Deterministic latest headlines from yfinance Ticker.news.
    """
    items = []
    try:
        items = ticker_obj.news or []
    except Exception:
        items = []

    out: list[dict] = []
    for it in items[:max_items]:
        title = _safe_str(it.get("title")) or ""
        # HARD FILTER: skip blank headlines (prevents "LOW —" rows)
        if not title.strip():
            continue

        pub = _safe_str(it.get("publisher"))
        link = _safe_str(it.get("link"))
        published_utc = _utc_iso_from_epoch(it.get("providerPublishTime"))
        age = _age_hours(published_utc)
        tags = _tag_headline(title) if title else []
        sev = _severity(title, tags) if title else "LOW"

        out.append({
            "title": title,
            "publisher": pub,
            "link": link,
            "published_utc": published_utc,
            "age_hours": age,
            "tags": tags,
            "severity": sev,
        })
        
    out = [r for r in out if r.get("title")]

    return out

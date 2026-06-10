"""
services/data/fetchers/mf_herding.py
======================================
AMFI mutual fund sector herding signal via mfapi.in (no API key needed).

Tracks 30-day NAV momentum across sector ETFs to surface institutional
accumulation or distribution before it shows up in price moves.

Architecture
------------
Weekly cache (ISO week key) — NAV changes daily but the trend signal is
stable across 7 days. ContextBuilder.build() calls get_sector_mf_herding()
once per sector; no per-agent re-fetch.

Signal value
------------
Sector ETFs grow when investors are buying (net inflows) and shrink when
redeeming. A -0.4% NAV momentum across 3 auto ETFs while Nifty is flat
signals net redemption pressure on the sector — bearish context the
sentiment agent cannot see from Serper news.

Limitations
-----------
mfapi.in is a community wrapper around AMFI. Data is end-of-day NAV, not
real-time. If mfapi.in is unreachable the module returns a neutral signal
and logs a warning — all agents fall back to Serper-only context.

Sector ETF scheme codes are hard-coded from known AMFI scheme registrations.
Run `list_sector_etfs(sector)` to search for alternatives if codes change.
"""

from __future__ import annotations

import logging
from datetime import date

import requests

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Sector ETF scheme codes (from mfapi.in / AMFI registration)
# ---------------------------------------------------------------------------

_SECTOR_ETF_CODES: dict[str, list[tuple[int, str]]] = {
    "automobile": [
        (148620, "Mirae Asset Nifty Auto ETF"),
        (149075, "ICICI Prudential Nifty Auto ETF"),
        (148553, "Nippon India Nifty Auto ETF"),
    ],
    "banking_bfsi": [
        (102885, "Nippon India ETF Nifty Bank BeES"),
        (120716, "ICICI Prudential Nifty Bank ETF"),
        (120717, "SBI Nifty Bank ETF"),
    ],
    "it_sector": [
        (120706, "ICICI Prudential Nifty IT ETF"),
        (101485, "Nippon India ETF Nifty IT BeES"),
        (143534, "Mirae Asset Nifty IT ETF"),
    ],
    "renewable_energy": [
        (149365, "Mirae Asset Nifty India New Energy ETF"),
        (150716, "Nippon India Nifty India New Energy ETF"),
    ],
}

_MFAPI_BASE = "https://api.mfapi.in/mf"
_TIMEOUT    = 10

# ---------------------------------------------------------------------------
# In-process weekly cache (ISO week key)
# ---------------------------------------------------------------------------

_CACHE: dict[str, dict] = {}   # { "YYYY-WNN": herding_dict }


def _week_key() -> str:
    today = date.today()
    return f"{today.year}-W{today.isocalendar()[1]:02d}"


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _fetch_nav_history(scheme_code: int, days: int = 40) -> list[dict]:
    """Fetch NAV history for one scheme code. Returns sorted list [{date, nav}]."""
    from datetime import timedelta
    try:
        resp = requests.get(f"{_MFAPI_BASE}/{scheme_code}", timeout=_TIMEOUT)
        resp.raise_for_status()
        raw   = resp.json().get("data", [])
        cutoff = date.today() - timedelta(days=days)
        result = []
        for entry in raw:
            try:
                d, m, y = entry["date"].split("-")
                entry_date = date(int(y), int(m), int(d))
                if entry_date >= cutoff:
                    result.append({"date": entry_date.isoformat(), "nav": float(entry["nav"])})
            except (ValueError, KeyError):
                continue
        return sorted(result, key=lambda x: x["date"])
    except Exception as exc:
        logger.debug("[mf_herding] NAV fetch failed for scheme %d: %s", scheme_code, exc)
        return []


def _nav_momentum_pct(history: list[dict]) -> float | None:
    """% change from first to last entry. None if insufficient data."""
    if len(history) < 2:
        return None
    start = history[0]["nav"]
    end   = history[-1]["nav"]
    if start == 0:
        return None
    return round((end - start) / start * 100, 3)


# ---------------------------------------------------------------------------
# Public API — cached weekly
# ---------------------------------------------------------------------------

def get_sector_mf_herding(sector: str, force_refresh: bool = False) -> dict:
    """
    Return 30-day NAV momentum signal for the sector's ETFs.

    Parameters
    ----------
    sector : str — one of: automobile | banking_bfsi | it_sector | renewable_energy
                   Falls back to automobile for unknown sectors.

    Returns dict with keys:
        sector             : str
        avg_momentum_pct   : float | None   — mean 30-day NAV % across ETFs
        institutional_flow : "INFLOW" | "OUTFLOW" | "NEUTRAL" | "UNKNOWN"
        fund_count         : int
        individual         : list[{scheme_code, name, momentum_pct}]
        fetched_at         : str (ISO week key)
        error              : str | None
    """
    key = f"{_week_key()}:{sector}"
    if not force_refresh and key in _CACHE:
        return _CACHE[key]

    result: dict = {
        "sector":             sector,
        "avg_momentum_pct":   None,
        "institutional_flow": "UNKNOWN",
        "fund_count":         0,
        "individual":         [],
        "fetched_at":         _week_key(),
        "error":              None,
    }

    etf_codes = _SECTOR_ETF_CODES.get(sector, _SECTOR_ETF_CODES.get("automobile", []))
    if not etf_codes:
        result["error"] = "no_etf_codes_for_sector"
        return result

    momenta: list[float] = []
    individual: list[dict] = []

    for code, name in etf_codes:
        history = _fetch_nav_history(code, days=35)
        mom = _nav_momentum_pct(history)
        individual.append({
            "scheme_code":   code,
            "name":          name,
            "momentum_pct":  mom,
            "data_points":   len(history),
        })
        if mom is not None:
            momenta.append(mom)

    result["individual"]   = individual
    result["fund_count"]   = len([x for x in individual if x["momentum_pct"] is not None])

    if momenta:
        avg = round(sum(momenta) / len(momenta), 3)
        result["avg_momentum_pct"] = avg

        if avg >= 0.5:
            result["institutional_flow"] = "INFLOW"
        elif avg <= -0.3:
            result["institutional_flow"] = "OUTFLOW"
        else:
            result["institutional_flow"] = "NEUTRAL"
    else:
        result["error"] = "no_nav_data_available"

    logger.info(
        "[mf_herding] sector=%s avg_momentum=%.3f%% flow=%s (%d funds)",
        sector,
        result["avg_momentum_pct"] or 0,
        result["institutional_flow"],
        result["fund_count"],
    )
    _CACHE[key] = result
    return result


def format_mf_herding_context(data: dict) -> str:
    """
    Format MF herding signal for agent prompt injection.

    Returns "" when data has an error or no momentum data (agents fall back to
    Serper-only context silently).
    """
    if not data or data.get("error") == "nsepython_not_installed":
        return ""

    avg  = data.get("avg_momentum_pct")
    flow = data.get("institutional_flow", "UNKNOWN")
    cnt  = data.get("fund_count", 0)
    sec  = data.get("sector", "")

    if avg is None or flow == "UNKNOWN" or cnt == 0:
        return ""

    direction = "net inflow — institutional accumulation" if flow == "INFLOW" else (
        "net outflow — institutional distribution / redemption pressure" if flow == "OUTFLOW"
        else "neutral — no directional flow signal"
    )

    lines = [
        f"[MF HERDING SIGNAL — {sec} sector, {data.get('fetched_at', '')}]",
        f"  Sector ETF 30-day NAV momentum: {avg:+.3f}% ({cnt} funds) → {direction}",
    ]

    # Individual fund breakdown (brief)
    for item in data.get("individual", []):
        m = item.get("momentum_pct")
        if m is not None:
            lines.append(f"    {item['name'][:45]}: {m:+.3f}%")

    return "\n".join(lines)


def list_sector_etfs(query: str) -> list[dict]:
    """
    Helper: search mfapi.in for ETF schemes matching a query string.
    Use when scheme codes change or for adding a new sector.
    """
    try:
        resp = requests.get(_MFAPI_BASE, timeout=_TIMEOUT)
        resp.raise_for_status()
        q   = query.lower()
        return [
            {"code": s["schemeCode"], "name": s["schemeName"]}
            for s in resp.json()
            if q in s.get("schemeName", "").lower()
        ]
    except Exception as exc:
        logger.warning("[mf_herding] list_sector_etfs failed: %s", exc)
        return []

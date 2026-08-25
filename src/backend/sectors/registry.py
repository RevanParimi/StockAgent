"""
src/backend/sectors/registry.py
================================
Unified sector registry — Phase 0 (toggle layer) + Phase 1 (ticker map).

Public API (backward-compatible shims for detect_sector / get_orchestrator):
    SectorRegistry.resolve(ticker)      → sector key (str)
    SectorRegistry.get_handler(sector)  → orchestrator class
    SectorRegistry.is_enabled(sector)   → bool
    SectorRegistry.all_sectors()        → list[dict]

Toggle state is read from config/sector_toggles.json at import time.

This module is the SINGLE resolution point for the whole system (PI task
A1). `core.intelligence.rl.workflows.sector_router` delegates here rather
than keeping its own map — before A1 the two disagreed on every disabled
sector, which is what minted the duplicate prediction stores (spec §2.1).

Unknown tickers and disabled sectors resolve to "generic", never to
"automobile": the generic graph is sector-agnostic by construction, while
the automobile graph injects nine automobile-specific dimensions into a
pharma or realestate name. `sectors.generic_fallback_enabled: false`
sends the UNPLACEABLE cases (unknown ticker, unrecognised sector key)
back to automobile; a known sector without a native graph stays on the
generic graph either way.
"""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Toggle config — loaded once at import
# ---------------------------------------------------------------------------

# CWD-relative (AUD-040): `Path(__file__).parents[3]` resolved to the
# filesystem ROOT inside the Docker image (src/backend/ ships as /app/backend/,
# one level shallower than in the repo) — the file never loaded in prod.
# Both layouts run with CWD at the app/repo root, where config/ lives.
_TOGGLES_PATH = Path(os.getenv("SECTOR_TOGGLES_PATH", "config/sector_toggles.json"))

def _load_toggles() -> dict[str, dict]:
    try:
        with open(_TOGGLES_PATH, encoding="utf-8") as f:
            raw = json.load(f)
        return {k: v for k, v in raw.items() if not k.startswith("_")}
    except Exception as exc:
        logger.info("[SectorRegistry] sector_toggles.json not loaded (%s) — using defaults", exc)
        return {
            "automobile":       {"enabled": True,  "tier": "backend"},
            "banking_bfsi":     {"enabled": True,  "tier": "backend"},
            "it_sector":        {"enabled": True,  "tier": "backend"},
            "renewable_energy": {"enabled": True,  "tier": "backend"},
        }

_TOGGLES: dict[str, dict] = _load_toggles()

# ---------------------------------------------------------------------------
# Phase 1 — comprehensive ticker → sector map
# Disabled sectors are mapped here too: resolve() returns the REAL sector
# (PredictionStore uses it for the directory layout) and only the GRAPH
# degrades to generic. See get_graph_sector.
# ---------------------------------------------------------------------------

TICKER_SECTOR: dict[str, str] = {
    # ── automobile (enabled, tier=backend) ──────────────────────────────────
    "MARUTI":       "automobile",   "TATAMOTORS":   "automobile",
    "M&M":          "automobile",   "HEROMOTOCO":   "automobile",
    "BAJAJ-AUTO":   "automobile",   "EICHERMOT":    "automobile",
    "TVSMOTORS":    "automobile",   "ASHOKLEY":     "automobile",
    "ESCORTS":      "automobile",   "APOLLOTYRE":   "automobile",
    "MRF":          "automobile",   "BALKRISIND":   "automobile",
    "MOTHERSON":    "automobile",   "BOSCHLTD":     "automobile",
    "SUNDRMFAST":   "automobile",   "ENDURANCE":    "automobile",

    # ── banking_bfsi (enabled, tier=backend) ────────────────────────────────
    "HDFCBANK":     "banking_bfsi", "ICICIBANK":    "banking_bfsi",
    "SBIN":         "banking_bfsi", "KOTAKBANK":    "banking_bfsi",
    "AXISBANK":     "banking_bfsi", "INDUSINDBK":   "banking_bfsi",
    "BANKBARODA":   "banking_bfsi", "PNB":          "banking_bfsi",
    "CANARABANK":   "banking_bfsi", "FEDERALBNK":   "banking_bfsi",
    "IDFCFIRSTB":   "banking_bfsi", "BANDHANBNK":   "banking_bfsi",
    "RBLBANK":      "banking_bfsi", "YESBANK":      "banking_bfsi",
    "HDFCAMC":      "banking_bfsi", "BAJAJFINSV":   "banking_bfsi",
    "BAJFINANCE":   "banking_bfsi", "MUTHOOTFIN":   "banking_bfsi",
    "CHOLAFIN":     "banking_bfsi", "MANAPPURAM":   "banking_bfsi",

    # ── it_sector (enabled, tier=backend) ───────────────────────────────────
    "TCS":          "it_sector",    "INFY":         "it_sector",
    "WIPRO":        "it_sector",    "HCLTECH":      "it_sector",
    "TECHM":        "it_sector",    "LTIM":         "it_sector",
    "COFORGE":      "it_sector",    "MPHASIS":      "it_sector",
    "PERSISTENT":   "it_sector",    "LTTS":         "it_sector",
    "KPITTECH":     "it_sector",    "TATAELXSI":    "it_sector",
    "NIIT":         "it_sector",    "MASTEK":       "it_sector",
    "HEXAWARE":     "it_sector",    "HAPPSTMNDS":   "it_sector",

    # ── renewable_energy (enabled, tier=backend) ─────────────────────────────
    "ADANIGREEN":   "renewable_energy", "TATAPOWER":    "renewable_energy",
    "TORNTPOWER":   "renewable_energy", "CESC":         "renewable_energy",
    "SJVN":         "renewable_energy", "NHPC":         "renewable_energy",
    "NTPC":         "renewable_energy", "POWERGRID":    "renewable_energy",
    "ADANIPOWER":   "renewable_energy", "JSWENERGY":    "renewable_energy",
    "INOXGREEN":    "renewable_energy", "INOXWIND":     "renewable_energy",
    "WAAREEENER":   "renewable_energy", "SUZLON":       "renewable_energy",
    "PREMIERENE":   "renewable_energy", "RPOWER":       "renewable_energy",

    # ── pharma (disabled) ────────────────────────────────────────────────────
    "SUNPHARMA":    "pharma",       "DRREDDY":      "pharma",
    "CIPLA":        "pharma",       "DIVISLAB":     "pharma",
    "AUROPHARMA":   "pharma",       "LUPIN":        "pharma",
    "MANKIND":      "pharma",       "ABBOTINDIA":   "pharma",
    "PFIZER":       "pharma",       "ALKEM":        "pharma",
    "TORNTPHARM":   "pharma",       "BIOCON":       "pharma",
    "ZYDUSLIFE":    "pharma",       "IPCALAB":      "pharma",

    # ── fmcg (disabled) ──────────────────────────────────────────────────────
    "HINDUNILVR":   "fmcg",         "ITC":          "fmcg",
    "NESTLEIND":    "fmcg",         "BRITANNIA":    "fmcg",
    "DABUR":        "fmcg",         "MARICO":       "fmcg",
    "GODREJCP":     "fmcg",         "TATACONSUM":   "fmcg",
    "EMAMILTD":     "fmcg",         "COLPAL":       "fmcg",
    "MCDOWELL-N":   "fmcg",         "RADICO":       "fmcg",

    # ── metals (disabled) ────────────────────────────────────────────────────
    "TATASTEEL":    "metals",       "JSWSTEEL":     "metals",
    "HINDALCO":     "metals",       "SAIL":         "metals",
    "VEDL":         "metals",       "NATIONALUM":   "metals",
    "NMDC":         "metals",       "COALINDIA":    "metals",
    "HINDCOPPER":   "metals",       "WELCORP":      "metals",
    "RATNAMANI":    "metals",       "APL":          "metals",

    # ── oilgas (disabled) ────────────────────────────────────────────────────
    "RELIANCE":     "oilgas",       "ONGC":         "oilgas",
    "BPCL":         "oilgas",       "IOC":          "oilgas",
    "GAIL":         "oilgas",       "OIL":          "oilgas",
    "HINDPETRO":    "oilgas",       "MGL":          "oilgas",
    "IGL":          "oilgas",       "PETRONET":     "oilgas",
    "CASTROLIND":   "oilgas",

    # ── capgoods (disabled) ──────────────────────────────────────────────────
    "LT":           "capgoods",     "ABB":          "capgoods",
    "SIEMENS":      "capgoods",     "BEL":          "capgoods",
    "HAL":          "capgoods",     "BHEL":         "capgoods",
    "THERMAX":      "capgoods",     "CUMMINSIND":   "capgoods",
    "SCHAEFFLER":   "capgoods",     "ELGIEQUIP":    "capgoods",
    "AIAENG":       "capgoods",     "GRINDWELL":    "capgoods",

    # ── power / utilities ────────────────────────────────────────────────────
    # Utility names live in the renewable_energy block above; TORNTPOWER was
    # repeated here (harmlessly, same value) and is now listed once.

    # ── chemicals (disabled) ─────────────────────────────────────────────────
    "PIDILITIND":   "chemicals",    "DEEPAKNITRI":  "chemicals",
    "FINEORG":      "chemicals",    "AAVAS":        "chemicals",
    "CLEAN":        "chemicals",    "ATUL":         "chemicals",
    "NAVINFLUOR":   "chemicals",    "ALKYLAMINE":   "chemicals",

    # ── defence (disabled) ───────────────────────────────────────────────────
    "COCHINSHIP":   "defence",      "GRSE":         "defence",
    "MAZDA":        "defence",      "PARAS":        "defence",
    "MTAR":         "defence",      "IDEAFORGE":    "defence",

    # ── infra (disabled) ─────────────────────────────────────────────────────
    "ULTRACEMCO":   "infra",        "SHREECEM":     "infra",
    "AMBUJACEM":    "infra",        "ACCCEMENT":    "infra",
    "LODHA":        "infra",        "KNRCON":       "infra",
    "HGINFRA":      "infra",
    # DLF was listed here AND under realestate. Python keeps the last
    # literal, so realestate has always won — the infra entry was dead
    # text that read like a live mapping. Removed, not re-pointed.

    # ── insurance (disabled) ─────────────────────────────────────────────────
    "SBILIFE":      "insurance",    "HDFCLIFE":     "insurance",
    "ICICIGI":      "insurance",    "ICICIPRULI":   "insurance",
    "STARHEALTH":   "insurance",    "NIACL":        "insurance",

    # ── logistics (disabled) ─────────────────────────────────────────────────
    "DELHIVERY":    "logistics",    "BLUEDART":     "logistics",
    "MAHLOG":       "logistics",    "TCI":          "logistics",
    "GATI":         "logistics",    "CONCOR":       "logistics",

    # ── media (disabled) ─────────────────────────────────────────────────────
    "ZEEL":         "media",        "SUNTV":        "media",
    "PVR":          "media",        "INOXLEISUR":   "media",
    "NAZARA":       "media",        "SAREGAMA":     "media",

    # ── realestate (disabled) ────────────────────────────────────────────────
    "DLF":          "realestate",   "GODREJPROP":   "realestate",
    "PRESTIGE":     "realestate",   "OBEROIRLTY":   "realestate",
    "BRIGADE":      "realestate",   "SOBHA":        "realestate",

    # ── retail (disabled) ────────────────────────────────────────────────────
    "DMART":        "retail",       "TRENT":        "retail",
    "ABFRL":        "retail",       "VMART":        "retail",
    "NYKAA":        "retail",       "ZOMATO":       "retail",

    # ── agrochem (disabled) ──────────────────────────────────────────────────
    "UPL":          "agrochem",     "PIIND":        "agrochem",
    "BAYER":        "agrochem",     "RALLIS":       "agrochem",
    "DHANUKA":      "agrochem",     "COROMANDEL":   "agrochem",

    # ── hospitality (disabled) ───────────────────────────────────────────────
    "INDHOTEL":     "hospitality",  "EIHOTEL":      "hospitality",
    "CHALET":       "hospitality",  "LEMONTREE":    "hospitality",
    "MAHINDHOTEL":  "hospitality",

    # ── tech hardware (disabled) ─────────────────────────────────────────────
    "DIXON":        "tech",         "AMBER":        "tech",
    "KAYNES":       "tech",         "SYRMA":        "tech",
    "PGEL":         "tech",

    # ── telecom (disabled) ───────────────────────────────────────────────────
    "BHARTIARTL":   "telecom",      "IDEA":         "telecom",
    "INDUSTOWER":   "telecom",      "TATACOMM":     "telecom",
    "RAILTEL":      "telecom",
}

# name-fragment fallback for free-text inputs
_NAME_FRAGMENTS: list[tuple[str, str]] = [
    ("hdfc bank", "banking_bfsi"),   ("icici bank", "banking_bfsi"),
    ("state bank", "banking_bfsi"),  ("kotak", "banking_bfsi"),
    ("axis bank", "banking_bfsi"),   ("bajaj finance", "banking_bfsi"),
    ("tata consultancy", "it_sector"), ("infosys", "it_sector"),
    ("wipro", "it_sector"),          ("hcl tech", "it_sector"),
    ("tech mahindra", "it_sector"),  ("ltimindtree", "it_sector"),
    ("adani green", "renewable_energy"), ("tata power", "renewable_energy"),
    ("ntpc", "renewable_energy"),    ("suzlon", "renewable_energy"),
    ("sun pharma", "pharma"),        ("dr. reddy", "pharma"),
    ("cipla", "pharma"),             ("reliance industries", "oilgas"),
    ("ongc", "oilgas"),              ("hindustan unilever", "fmcg"),
    ("itc limited", "fmcg"),
]


# ---------------------------------------------------------------------------
# Backend handler lazy-import map
# ---------------------------------------------------------------------------

def _get_automobile():
    from backend.sectors.automobile.pipeline.orchestrator import AutomobileAgentOrchestrator
    return AutomobileAgentOrchestrator

def _get_banking():
    from backend.sectors.banking_bfsi.pipeline.orchestrator import BankingAgentOrchestrator
    return BankingAgentOrchestrator

def _get_it():
    from backend.sectors.it_sector.pipeline.orchestrator import ITAgentOrchestrator
    return ITAgentOrchestrator

def _get_renewable():
    from backend.sectors.renewable_energy.pipeline.orchestrator import RenewableAgentOrchestrator
    return RenewableAgentOrchestrator

def _get_generic():
    from backend.sectors.generic.pipeline.orchestrator import GenericSectorOrchestrator
    return GenericSectorOrchestrator

GENERIC_SECTOR = "generic"

# Sectors with a hand-built native graph. `generic` is deliberately NOT one of
# them — it is a routing target, not a sector, and it has no toggle entry.
NATIVE_SECTORS: frozenset[str] = frozenset(
    {"automobile", "banking_bfsi", "it_sector", "renewable_energy"}
)

_BACKEND_LOADERS: dict[str, Any] = {
    "automobile":       _get_automobile,
    "banking_bfsi":     _get_banking,
    "it_sector":        _get_it,
    "renewable_energy": _get_renewable,
    GENERIC_SECTOR:     _get_generic,
}


def _generic_fallback_enabled() -> bool:
    """A1: an input we cannot place at all resolves to `generic`.

    Scope is deliberately narrow — an unknown TICKER and an unrecognised
    SECTOR KEY. A known sector without a native graph goes to `generic`
    regardless (see get_graph_sector).

    Rollback line: `sectors.generic_fallback_enabled: false` in config.yaml
    sends those unplaceable inputs back to automobile, which is where they
    went before A1.
    """
    from backend.shared.config.settings.loader import cfg
    return bool(cfg("sectors.generic_fallback_enabled", fallback=True))


# ---------------------------------------------------------------------------
# SectorRegistry
# ---------------------------------------------------------------------------

class _SectorRegistry:
    """
    Singleton registry for sector routing with toggle support.
    The one resolution point: both the API path and the RL path route here.
    Unknown tickers and sectors without a native graph degrade to
    `generic` (A1), never to automobile.
    """

    def _fallback_sector(self) -> str:
        return GENERIC_SECTOR if _generic_fallback_enabled() else "automobile"

    def resolve(self, ticker: str) -> str:
        """
        ticker → sector key.
        Returns the canonical sector string even for disabled sectors
        (caller should check is_enabled before dispatching).
        """
        t = ticker.strip().upper()
        if t in TICKER_SECTOR:
            return TICKER_SECTOR[t]
        tl = t.lower()
        for fragment, sector in _NAME_FRAGMENTS:
            if fragment in tl:
                return sector
        fallback = self._fallback_sector()
        logger.info(
            "[SectorRegistry] '%s' is not in the ticker map — resolving to '%s'",
            t, fallback,
        )
        return fallback

    def get_graph_sector(self, sector: str) -> str:
        """
        sector key → the sector whose GRAPH actually runs.

        Native + enabled + tier=backend  → itself.
        KNOWN sector without a native graph → `generic`, unconditionally.
        Unrecognised sector key           → `generic`, or `automobile` when
                                            the fallback flag is off.

        This is the function A1 unified: `sector_router` calls it too, so the
        two entry points cannot disagree about which graph a ticker gets.

        The flag deliberately does NOT reach a known-but-disabled sector.
        There is no single "pre-A1 state" to roll back to — pharma got the
        automobile graph on the API path and the generic graph on the RL path,
        which is the bug itself — so the flag picks which CONSISTENT state to
        degrade to. Sending a mapped sector to the automobile graph is never
        that state: it injects nine automobile dimensions into a pharma name.
        Compass Phase B settled those sectors on generic and this keeps them
        there whatever the flag says. The flag governs only the case where
        `automobile` was ever a defensible default — an input we cannot place
        at all.
        """
        s = (sector or "").strip().lower()
        if s == GENERIC_SECTOR:
            return GENERIC_SECTOR

        toggle = _TOGGLES.get(s)
        if toggle is not None:
            enabled = toggle.get("enabled", False)
            tier    = toggle.get("tier", "backend")
            if enabled and tier == "backend" and s in _BACKEND_LOADERS:
                return s
            logger.info(
                "[SectorRegistry] sector '%s' has no native graph (%s) — using the generic graph",
                s,
                "disabled" if not enabled else f"tier={tier!r}",
            )
            return GENERIC_SECTOR

        fallback = self._fallback_sector()
        if s != fallback:
            logger.warning(
                "[SectorRegistry] sector '%s' is not a known sector key — routing to '%s'",
                s, fallback,
            )
        return fallback

    def get_handler(self, sector: str):
        """Returns the orchestrator CLASS for a sector (lazy-imported)."""
        return _BACKEND_LOADERS[self.get_graph_sector(sector)]()

    def is_enabled(self, sector: str) -> bool:
        return bool(_TOGGLES.get(sector, {}).get("enabled", False))

    def all_sectors(self) -> list[dict]:
        return [
            {"sector": k, **v}
            for k, v in _TOGGLES.items()
        ]

    def enabled_sectors(self) -> list[str]:
        return [k for k, v in _TOGGLES.items() if v.get("enabled")]


# Module-level singleton
SectorRegistry = _SectorRegistry()

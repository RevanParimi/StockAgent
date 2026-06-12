"""
services/data/context/bundle_builder.py
========================================
Unified Sector Analyst (2026-06-12 redesign) — one shared data-fetch pass
that feeds a single reasoning-model call instead of 9 parallel per-agent
LLM calls, each with its own data fetch.

Public API
----------
SectorDataBundle           — dataclass: sections, has_real_data, api_calls_made
build_sector_bundle(query, sector) -> SectorDataBundle

Design notes
------------
- Every `_fetch_<section>` is a module-level function so tests (and future
  callers) can patch them individually.
- `build_sector_bundle` NEVER raises. Each fetcher is wrapped in its own
  try/except; on failure the section becomes the literal string
  "unavailable" and a warning is logged.
- Each section is capped at `settings.UNIFIED_SECTION_MAX_CHARS`.
- `SectorDataBundle.to_prompt_text()` renders labelled `## SECTION_NAME`
  blocks in a fixed order, with the overall result capped at
  `settings.UNIFIED_BUNDLE_MAX_CHARS`.
- NSE data is NEVER refetched here — it comes from `query.nse_data`,
  populated once by the orchestrator's existing prefetch step.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date

from core.config import settings
from core.schemas.pipeline import StockQuery

logger = logging.getLogger(__name__)

# Fixed section order — also the order rendered by to_prompt_text().
SECTION_ORDER: list[str] = [
    "company_news",
    "sector_policy_news",
    "macro_context",
    "policy_deep_dive",
    "fundamentals",
    "technicals",
    "commodities",
    "flows_sentiment",
    "peers_valuation",
    "dossier",
]

UNAVAILABLE = "unavailable"


# ---------------------------------------------------------------------------
# SectorDataBundle
# ---------------------------------------------------------------------------

@dataclass
class SectorDataBundle:
    """One shared data bundle for the Unified Sector Analyst."""

    sections: dict[str, str] = field(default_factory=dict)
    has_real_data: bool = False
    api_calls_made: dict[str, int] = field(default_factory=dict)

    def to_prompt_text(self) -> str:
        """
        Render all sections as labelled `## SECTION_NAME` blocks in
        SECTION_ORDER, capped overall at settings.UNIFIED_BUNDLE_MAX_CHARS.
        """
        parts: list[str] = []
        for name in SECTION_ORDER:
            text = self.sections.get(name, UNAVAILABLE)
            parts.append(f"## {name.upper()}\n{text}")
        full_text = "\n\n".join(parts)

        max_chars = settings.UNIFIED_BUNDLE_MAX_CHARS
        if len(full_text) > max_chars:
            full_text = full_text[:max_chars]
        return full_text


# ---------------------------------------------------------------------------
# Per-section fetchers — each is module-level so tests can patch it directly.
# Each function returns a plain str and may raise; build_sector_bundle()
# wraps every call in try/except.
# ---------------------------------------------------------------------------

def _cap(text: str) -> str:
    """Cap a section's text at settings.UNIFIED_SECTION_MAX_CHARS."""
    max_chars = settings.UNIFIED_SECTION_MAX_CHARS
    if text is None:
        return ""
    if len(text) > max_chars:
        return text[:max_chars]
    return text


def _fetch_company_news(query: StockQuery, serper_key: str) -> str:
    """Serper search #1 — company news, results, guidance, management commentary."""
    from services.data.fetchers.news import fetch_news_context

    today = date.today()
    queries = [
        f"{query.company_name} {query.ticker} latest news results guidance "
        f"{today.strftime('%B')} {today.year}"
    ]
    return fetch_news_context(queries, max_queries=1, api_key=serper_key)


def _fetch_sector_policy_news(query: StockQuery, sector: str, serper_key: str) -> str:
    """Serper search #2 — sector demand, policy/regulatory, and competitive moves."""
    from services.data.fetchers.news import fetch_news_context

    today = date.today()
    queries = [
        f"India {sector} sector demand policy regulation competitors news "
        f"{today.strftime('%B')} {today.year}"
    ]
    return fetch_news_context(queries, max_queries=1, api_key=serper_key)


def _fetch_macro_context(sector: str, serper_key: str) -> str:
    """
    yfinance INR/USD + crude + factor regime, plus Serper search #3
    (skipped on macro_cache hit — same cached news the legacy risk_macro
    builder uses).
    """
    from services.data.fetchers.macro import get_macro_context
    from services.data.cache.macro_cache import get_macro_cache

    macro = get_macro_context()

    cached_news = get_macro_cache(sector)
    if cached_news:
        logger.debug("[bundle_builder] macro_context: cache HIT — skipping Serper call")
        return f"{macro}\n\n[Macro news — from micro search cache]\n{cached_news}"

    from services.data.fetchers.news import fetch_news_context

    today = date.today()
    queries = [
        f"India {sector} sector macro economy INR USD crude oil RBI "
        f"{today.strftime('%B')} {today.year}"
    ]
    news = fetch_news_context(queries, max_queries=1, api_key=serper_key)
    return f"{macro}\n\n{news}"


def _fetch_policy_deep_dive(query: StockQuery) -> str:
    """1 Tavily page (down from 2) — existing month cache."""
    from services.clients.tavily_fetcher import fetch_tavily_context

    today = date.today()
    queries = [
        f"India {query.company_name} sector policy regulation circular FAME PLI "
        f"{today.year}"
    ]
    return fetch_tavily_context(queries, max_queries=1, max_results_per_query=1)


def _fetch_fundamentals(query: StockQuery) -> str:
    """yfinance fundamentals + NSE board/results dates (from prefetch, no refetch)."""
    from services.data.fetchers.fundamentals import get_fundamentals_context
    from services.data.fetchers.nse_announcements import format_nse_context

    fin_context = get_fundamentals_context(query.ticker)
    nse_ctx = format_nse_context(query.nse_data, agent_type="fundamentals")
    if nse_ctx:
        return f"{fin_context}\n\n{nse_ctx}"
    return fin_context


def _fetch_technicals(query: StockQuery) -> str:
    """Local RSI/MACD/BB + 10-yr history (yfinance, cached) — same as pattern_analysis builder."""
    from core.intelligence.algorithms.indicators.fetcher import get_technical_context

    return get_technical_context(query.ticker)


def _fetch_commodities() -> str:
    """yfinance 6 commodity tickers (existing daily cache) — same as raw_materials builder."""
    from services.data.fetchers.macro import get_raw_materials_context

    return get_raw_materials_context()


def _fetch_flows_sentiment(query: StockQuery, sector: str) -> str:
    """NSE bulk deals + FII/DII + MF herding — NO Serper here."""
    parts: list[str] = []

    try:
        from services.data.fetchers.nse_market import get_nse_market_data, format_nse_market_context
        bulk_ctx = format_nse_market_context(
            get_nse_market_data(), focus="bulk_deals", ticker=query.ticker
        )
        if bulk_ctx:
            parts.append(bulk_ctx)
    except Exception as exc:
        logger.debug("[bundle_builder] flows_sentiment: NSE bulk deals unavailable: %s", exc)

    try:
        from services.data.fetchers.nse_market import get_nse_market_data, format_nse_market_context
        fii_dii_ctx = format_nse_market_context(get_nse_market_data(), focus="fii_dii")
        if fii_dii_ctx:
            parts.append(fii_dii_ctx)
    except Exception as exc:
        logger.debug("[bundle_builder] flows_sentiment: NSE FII/DII unavailable: %s", exc)

    try:
        from services.data.fetchers.mf_herding import get_sector_mf_herding, format_mf_herding_context
        mf_ctx = format_mf_herding_context(get_sector_mf_herding(sector or "automobile"))
        if mf_ctx:
            parts.append(mf_ctx)
    except Exception as exc:
        logger.debug("[bundle_builder] flows_sentiment: MF herding unavailable: %s", exc)

    return "\n\n".join(parts) if parts else ""


def _fetch_peers_valuation(query: StockQuery) -> str:
    """Peer P/E (existing peer list) + NSE dividend/bonus/corporate actions."""
    from core.intelligence.algorithms.indicators.fetcher import get_valuation_context
    from services.data.fetchers.nse_announcements import format_nse_context

    peers = getattr(
        settings, "PEER_TICKERS", ["MARUTI", "TATAMOTORS", "M&M", "HEROMOTOCO", "BAJAJ-AUTO"]
    )[:5]
    valuation_ctx = get_valuation_context(query.ticker, peer_tickers=peers)
    nse_ctx = format_nse_context(query.nse_data, agent_type="valuation_catalyst")
    if nse_ctx:
        return f"{valuation_ctx}\n\n{nse_ctx}"
    return valuation_ctx


def _fetch_dossier(query: StockQuery, sector: str) -> str:
    """Ticker dossier digest — injected ONCE (replaces 9x repetition)."""
    if not getattr(settings, "RL_DOSSIER_ENABLED", True):
        return ""

    from core.intelligence.rl.stores.prediction_store import PredictionStore

    ps = PredictionStore(ticker=query.ticker, sector=sector or "automobile")
    dossier = ps.load_dossier()
    if dossier is None:
        return ""
    return dossier.to_digest(settings.DOSSIER_AGENT_DIGEST_CHARS)


# ---------------------------------------------------------------------------
# build_sector_bundle
# ---------------------------------------------------------------------------

def build_sector_bundle(query: StockQuery, sector: str) -> SectorDataBundle:
    """
    Build the one-pass SectorDataBundle for `sector`.

    NEVER raises. Every fetcher failure degrades only that section to
    "unavailable"; the run continues.

    api_calls_made is an upper-bound estimate used for logging/tests:
      - serper: company_news (1) + sector_policy_news (1) + macro_context (<=1, skipped on cache hit)
      - tavily: policy_deep_dive (<=1)
    """
    serper_key = settings.get_serper_key(sector)

    sections: dict[str, str] = {}

    # --- company_news -----------------------------------------------------
    try:
        sections["company_news"] = _cap(_fetch_company_news(query, serper_key))
    except Exception as exc:
        logger.warning("[bundle_builder] company_news fetch failed: %s", exc)
        sections["company_news"] = UNAVAILABLE

    # --- sector_policy_news -------------------------------------------------
    try:
        sections["sector_policy_news"] = _cap(_fetch_sector_policy_news(query, sector, serper_key))
    except Exception as exc:
        logger.warning("[bundle_builder] sector_policy_news fetch failed: %s", exc)
        sections["sector_policy_news"] = UNAVAILABLE

    # --- macro_context -------------------------------------------------------
    try:
        sections["macro_context"] = _cap(_fetch_macro_context(sector, serper_key))
    except Exception as exc:
        logger.warning("[bundle_builder] macro_context fetch failed: %s", exc)
        sections["macro_context"] = UNAVAILABLE

    # --- policy_deep_dive ------------------------------------------------------
    try:
        sections["policy_deep_dive"] = _cap(_fetch_policy_deep_dive(query))
    except Exception as exc:
        logger.warning("[bundle_builder] policy_deep_dive fetch failed: %s", exc)
        sections["policy_deep_dive"] = UNAVAILABLE

    # --- fundamentals -----------------------------------------------------------
    try:
        sections["fundamentals"] = _cap(_fetch_fundamentals(query))
    except Exception as exc:
        logger.warning("[bundle_builder] fundamentals fetch failed: %s", exc)
        sections["fundamentals"] = UNAVAILABLE

    # --- technicals -------------------------------------------------------------
    try:
        sections["technicals"] = _cap(_fetch_technicals(query))
    except Exception as exc:
        logger.warning("[bundle_builder] technicals fetch failed: %s", exc)
        sections["technicals"] = UNAVAILABLE

    # --- commodities --------------------------------------------------------------
    try:
        sections["commodities"] = _cap(_fetch_commodities())
    except Exception as exc:
        logger.warning("[bundle_builder] commodities fetch failed: %s", exc)
        sections["commodities"] = UNAVAILABLE

    # --- flows_sentiment ---------------------------------------------------------
    try:
        sections["flows_sentiment"] = _cap(_fetch_flows_sentiment(query, sector))
    except Exception as exc:
        logger.warning("[bundle_builder] flows_sentiment fetch failed: %s", exc)
        sections["flows_sentiment"] = UNAVAILABLE

    # --- peers_valuation -----------------------------------------------------------
    try:
        sections["peers_valuation"] = _cap(_fetch_peers_valuation(query))
    except Exception as exc:
        logger.warning("[bundle_builder] peers_valuation fetch failed: %s", exc)
        sections["peers_valuation"] = UNAVAILABLE

    # --- dossier --------------------------------------------------------------------
    try:
        sections["dossier"] = _cap(_fetch_dossier(query, sector))
    except Exception as exc:
        logger.warning("[bundle_builder] dossier fetch failed: %s", exc)
        sections["dossier"] = UNAVAILABLE

    live_count = sum(
        1 for name in SECTION_ORDER
        if sections.get(name, UNAVAILABLE) not in (UNAVAILABLE, "")
    )
    has_real_data = live_count >= 3

    api_calls_made = {
        "serper": 3,   # company_news + sector_policy_news + macro_context (upper bound)
        "tavily": 1,   # policy_deep_dive (upper bound)
    }

    return SectorDataBundle(
        sections=sections,
        has_real_data=has_real_data,
        api_calls_made=api_calls_made,
    )

"""
services/data/context/bundle_builder.py
========================================
Unified Sector Analyst (2026-06-12 redesign) — one shared data-fetch pass
that feeds a single reasoning-model call instead of 9 parallel per-agent
LLM calls, each with its own data fetch.

Public API
----------
SectorDataBundle           — dataclass: sections, has_real_data, api_calls_made,
                             section_status, section_provenance
build_sector_bundle(query, sector) -> SectorDataBundle

Design notes
------------
- Every `_fetch_<section>` is a module-level function so tests (and future
  callers) can patch them individually.
- SA-002: every `_fetch_<section>` returns a `FetchResult` (fetch_result.py):
  the prompt text plus a status, source, as-of date and reason decided by the
  producer from its structured data. `section_status` takes the status and
  `section_provenance` the rest. A producer that returns plain text is
  recorded `unverified` — a returned string is not proof of usable data.
- `build_sector_bundle` NEVER raises. Each fetcher is wrapped by `_safe`;
  on failure the section becomes the literal string "unavailable", a warning
  is logged, and `section_status[name]` records `failed:<ExceptionType>`.
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
from services.data.context.fetch_result import (  # noqa: F401 — re-exported
    LIVE_STATUSES,
    STATUS_CACHE_HIT,
    STATUS_EMPTY,
    STATUS_FAILED_PREFIX,
    STATUS_FALLBACK,
    STATUS_NOT_APPLICABLE,
    STATUS_OK,
    STATUS_STALE,
    STATUS_UNVERIFIED,
    FetchResult,
    failed_status,
    join_reasons,
)

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
NOT_APPLICABLE = "not_applicable"

# ---------------------------------------------------------------------------
# Per-section fetch outcomes (B2, spec 2026-08-24 §6.2; SA-002)
# ---------------------------------------------------------------------------
# `sections` records WHAT a fetcher returned; `section_status` records HOW it
# went. B2 derived the status from the text, so a producer that wrapped its
# failure in a sentence ("Technical data unavailable for ...", "[No results
# for: ...]") read `ok`. Since SA-002 the producer states the status in its
# FetchResult. The STATUS_* names are defined in fetch_result.py and
# re-exported here, where B2's readers import them.


# ---------------------------------------------------------------------------
# Per-sector bundle configuration
# ---------------------------------------------------------------------------
#
# Drives sector-aware query wording (company_news, sector_policy_news,
# policy_deep_dive), whether the commodities section is fetched at all, the
# peer list for peers_valuation, and the macro_context cache-key alias.
#
# - company_news_terms: appended to the company-name/ticker query.
# - sector_policy_news_query: full Serper query template
#   (`.format(today=..., year=...)`).
# - policy_deep_dive_query: Tavily query template
#   (`.format(company_name=..., ticker=..., year=...)`).
# - has_commodities: automobile only — other sectors' commodity/module-price
#   signals are covered by the news queries instead.
# - peer_tickers_module / peer_tickers_attr: lazy import target for the
#   sector's peer universe (settings.TICKERS for the 3 new sectors;
#   automobile keeps its existing PEER_TICKERS list).
# - macro_cache_key: alias passed to get_macro_cache()/get_serper_key()
#   (bfsi/it aliases match services/data/context/builder.py; automobile and
#   renewable_energy use their own sector name).
# ---------------------------------------------------------------------------

_SECTOR_BUNDLE_CFG: dict[str, dict] = {
    "automobile": {
        "company_news_terms": "results guidance",
        "sector_policy_news_query": (
            "India automobile sector demand policy regulation competitors news "
            "{month} {year}"
        ),
        "policy_deep_dive_query": (
            "India {company_name} sector policy regulation circular FAME PLI {year}"
        ),
        "has_commodities": True,
        "peer_tickers_module": None,
        "peer_tickers_attr": "PEER_TICKERS",
        "macro_cache_key": "automobile",
    },
    "banking_bfsi": {
        "company_news_terms": "quarterly results NPA NIM deposits",
        "sector_policy_news_query": (
            "India banking sector RBI policy credit growth banking regulation news "
            "{month} {year}"
        ),
        "policy_deep_dive_query": (
            "{company_name} RBI policy regulation impact banking {year}"
        ),
        "has_commodities": False,
        "peer_tickers_module": "backend.sectors.banking_bfsi.config.settings",
        "peer_tickers_attr": "TICKERS",
        "macro_cache_key": "bfsi",
    },
    "it_sector": {
        "company_news_terms": "results deal wins attrition guidance",
        "sector_policy_news_query": (
            "US tech spending H1B visa AI services disruption India IT sector news "
            "{month} {year}"
        ),
        "policy_deep_dive_query": (
            "{company_name} earnings call transcript guidance commentary {year}"
        ),
        "has_commodities": False,
        "peer_tickers_module": "backend.sectors.it_sector.config.settings",
        "peer_tickers_attr": "TICKERS",
        "macro_cache_key": "it",
    },
    "renewable_energy": {
        "company_news_terms": "results PPA commissioning capacity",
        "sector_policy_news_query": (
            "India MNRE solar wind auctions module prices DISCOM renewable energy news "
            "{month} {year}"
        ),
        "policy_deep_dive_query": (
            "India MNRE renewable auction policy {company_name} {year}"
        ),
        "has_commodities": False,
        "peer_tickers_module": "backend.sectors.renewable_energy.config.settings",
        "peer_tickers_attr": "TICKERS",
        "macro_cache_key": "renewable_energy",
    },
    "generic": {
        # Compass Phase B: sector-agnostic wording — the ticker's industry is
        # inferred by the analyst from the bundle itself.
        "company_news_terms": "results guidance outlook",
        "sector_policy_news_query": (
            "India stock market {month} {year} sector news policy demand"
        ),
        "policy_deep_dive_query": (
            "{company_name} NSE {ticker} results outlook policy regulation {year}"
        ),
        "has_commodities": False,
        "peer_tickers_module": None,
        "peer_tickers_attr": "TICKERS",
        "macro_cache_key": "generic",
    },
}

# Fallback config for an unregistered sector — mirrors automobile's shape so
# build_sector_bundle never raises on an unknown sector string.
_DEFAULT_BUNDLE_CFG = _SECTOR_BUNDLE_CFG["automobile"]


def _bundle_cfg(sector: str) -> dict:
    return _SECTOR_BUNDLE_CFG.get(sector, _DEFAULT_BUNDLE_CFG)


# ---------------------------------------------------------------------------
# SectorDataBundle
# ---------------------------------------------------------------------------

@dataclass
class SectorDataBundle:
    """One shared data bundle for the Unified Sector Analyst."""

    sections: dict[str, str] = field(default_factory=dict)
    has_real_data: bool = False
    api_calls_made: dict[str, int] = field(default_factory=dict)
    # B2: one outcome per section name — STATUS_* above, or failed:<Type>.
    section_status: dict[str, str] = field(default_factory=dict)
    # SA-002: per section {source, as_of, reason}, from the producer's FetchResult.
    section_provenance: dict[str, dict] = field(default_factory=dict)

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


def _classify_section(text: str) -> str:
    """Map UNTYPED text (a producer that returned a plain str) to an outcome.

    B2's blank and exact-marker rules are kept: `n/a` is a deliberate skip,
    and "", whitespace or the literal UNAVAILABLE is `empty`. Any other text
    is `unverified`, not `ok` (SA-002): without a FetchResult nothing says
    whether it is data or a producer's apology for having none.
    """
    if text == NOT_APPLICABLE:
        return STATUS_NOT_APPLICABLE
    if text == UNAVAILABLE or not (text or "").strip():
        return STATUS_EMPTY
    return STATUS_UNVERIFIED


def _safe(
    sections: dict[str, str],
    status: dict[str, str],
    name: str,
    fetcher,
    *args,
    provenance: dict[str, dict] | None = None,
) -> None:
    """Run one section fetcher, recording its text, outcome and provenance.

    Never raises: a failing fetcher degrades that section to UNAVAILABLE and
    records `failed:<ExceptionType>`. A FetchResult's status is taken as the
    producer states it; plain text is classified by `_classify_section`.
    """
    if provenance is None:
        provenance = {}
    try:
        result = fetcher(*args)
    except Exception as exc:
        logger.warning("[bundle_builder] %s fetch failed: %s", name, exc,
                       exc_info=True)
        sections[name] = UNAVAILABLE
        status[name] = failed_status(exc)
        provenance[name] = {"source": None, "as_of": None,
                            "reason": f"raised {type(exc).__name__}: {exc}"[:300]}
        return
    if isinstance(result, FetchResult):
        sections[name] = _cap(result.text)
        status[name] = result.status
        provenance[name] = result.provenance()
        return
    text = _cap(result)
    sections[name] = text
    status[name] = _classify_section(text)
    provenance[name] = {"source": "untyped", "as_of": None,
                        "reason": "producer returned plain text; not verified"}


def _fetch_company_news(query: StockQuery, sector: str, serper_key: str) -> FetchResult:
    """Serper search #1 — company news, results, guidance, management commentary."""
    from services.data.fetchers.news import fetch_news_result

    today = date.today()
    terms = _bundle_cfg(sector)["company_news_terms"]
    queries = [
        f"{query.company_name} {query.ticker} latest news {terms} "
        f"{today.strftime('%B')} {today.year}"
    ]
    return fetch_news_result(queries, max_queries=1, api_key=serper_key)


def _fetch_sector_policy_news(query: StockQuery, sector: str, serper_key: str) -> FetchResult:
    """Serper search #2 — sector demand, policy/regulatory, and competitive moves."""
    from services.data.fetchers.news import fetch_news_result

    today = date.today()
    template = _bundle_cfg(sector)["sector_policy_news_query"]
    queries = [template.format(month=today.strftime("%B"), year=today.year)]
    return fetch_news_result(queries, max_queries=1, api_key=serper_key)


def _fetch_macro_context(sector: str, serper_key: str) -> FetchResult:
    """
    yfinance INR/USD + crude + factor regime, plus Serper search #3
    (skipped on macro_cache hit — same cached news the legacy risk_macro
    builder uses).

    Status: the macro indicators decide it. With a core indicator missing the
    section is `unavailable` and no news is fetched, exactly as when
    `get_macro_context` raised here before SA-002. A macro_cache hit is
    `cache_hit` — the one outcome the text cannot show, recorded by the branch
    that knows (B2). News that found nothing is named in `reason`.
    """
    from services.data.fetchers.macro import get_macro_result
    from services.data.cache.macro_cache import get_macro_cache

    macro = get_macro_result()
    if macro.status not in LIVE_STATUSES:
        return FetchResult(UNAVAILABLE, macro.status, macro.source, reason=macro.reason)

    cache_key = _bundle_cfg(sector)["macro_cache_key"]
    cached_news = get_macro_cache(cache_key)
    if cached_news:
        logger.debug("[bundle_builder] macro_context: cache HIT — skipping Serper call")
        return FetchResult(
            f"{macro.text}\n\n[Macro news — from micro search cache]\n{cached_news}",
            STATUS_CACHE_HIT, "yfinance+macro_cache", reason=macro.reason,
        )

    from services.data.fetchers.news import fetch_news_result

    today = date.today()
    queries = [
        f"India {sector} sector macro economy INR USD crude oil RBI "
        f"{today.strftime('%B')} {today.year}"
    ]
    news = fetch_news_result(queries, max_queries=1, api_key=serper_key)
    return FetchResult(
        f"{macro.text}\n\n{news.text}", STATUS_OK, "yfinance+serper", as_of=news.as_of,
        reason=join_reasons([
            macro.reason,
            "macro news: no results" if news.status not in LIVE_STATUSES else None,
        ]),
    )


def _fetch_policy_deep_dive(query: StockQuery, sector: str) -> FetchResult:
    """1 Tavily page (down from 2) — existing month cache. Sector-specific query."""
    from services.clients.tavily_fetcher import fetch_tavily_result

    today = date.today()
    template = _bundle_cfg(sector)["policy_deep_dive_query"]
    queries = [template.format(company_name=query.company_name, ticker=query.ticker, year=today.year)]
    return fetch_tavily_result(queries, max_queries=1, max_results_per_query=1)


def _fetch_fundamentals(query: StockQuery) -> FetchResult:
    """yfinance fundamentals + NSE board/results dates (from prefetch, no refetch).

    Status is the yfinance statement's: the NSE dates are context from the
    orchestrator's prefetch, and do not make a missing statement usable.
    """
    from services.data.fetchers.fundamentals import get_fundamentals_result
    from services.data.fetchers.nse_announcements import format_nse_context

    fin = get_fundamentals_result(query.ticker)
    nse_ctx = format_nse_context(query.nse_data, agent_type="fundamentals")
    if nse_ctx:
        return FetchResult(f"{fin.text}\n\n{nse_ctx}", fin.status, fin.source,
                           as_of=fin.as_of, reason=fin.reason)
    return fin


def _fetch_technicals(query: StockQuery, sector: str) -> FetchResult:
    """Local RSI/MACD/BB + 10-yr history (yfinance, cached) — same as pattern_analysis builder.

    SA-010: correlation and beta are measured against `sector`'s benchmark
    index (`fetcher.sector_benchmark`), not the automobile index for all.
    """
    from core.intelligence.algorithms.indicators.fetcher import get_technical_result

    return get_technical_result(query.ticker, sector=sector)


def _fetch_commodities(sector: str) -> FetchResult:
    """
    yfinance 6 commodity tickers (existing daily cache) — same as raw_materials
    builder. Automobile only; other sectors' commodity/module-price signals
    are covered by the sector_policy_news query instead, so this returns
    NOT_APPLICABLE WITHOUT calling the fetcher.
    """
    if not _bundle_cfg(sector)["has_commodities"]:
        return FetchResult(NOT_APPLICABLE, STATUS_NOT_APPLICABLE, "config",
                           reason=f"no commodities section for sector {sector}")

    from services.data.fetchers.macro import get_raw_materials_result

    return get_raw_materials_result()


def _fetch_flows_sentiment(query: StockQuery, sector: str) -> FetchResult:
    """NSE bulk deals + FII/DII + MF herding — NO Serper here.

    `empty` when none of the three came back (the "" case B2 was built to
    catch); `ok` otherwise, naming any part that did not come back.
    """
    parts: list[str] = []
    missing: list[str] = []

    try:
        from services.data.fetchers.nse_market import get_nse_market_data, format_nse_market_context
        bulk_ctx = format_nse_market_context(
            get_nse_market_data(), focus="bulk_deals", ticker=query.ticker
        )
        if bulk_ctx:
            parts.append(bulk_ctx)
        else:
            missing.append("bulk deals: no data")
    except Exception as exc:
        logger.debug("[bundle_builder] flows_sentiment: NSE bulk deals unavailable: %s", exc)
        missing.append(f"bulk deals: {type(exc).__name__}")

    try:
        from services.data.fetchers.nse_market import get_nse_market_data, format_nse_market_context
        fii_dii_ctx = format_nse_market_context(get_nse_market_data(), focus="fii_dii")
        if fii_dii_ctx:
            parts.append(fii_dii_ctx)
        else:
            missing.append("FII/DII: no data")
    except Exception as exc:
        logger.debug("[bundle_builder] flows_sentiment: NSE FII/DII unavailable: %s", exc)
        missing.append(f"FII/DII: {type(exc).__name__}")

    try:
        from services.data.fetchers.mf_herding import get_sector_mf_herding, format_mf_herding_context
        mf_ctx = format_mf_herding_context(get_sector_mf_herding(sector or "automobile"))
        if mf_ctx:
            parts.append(mf_ctx)
        else:
            missing.append("MF herding: no data")
    except Exception as exc:
        logger.debug("[bundle_builder] flows_sentiment: MF herding unavailable: %s", exc)
        missing.append(f"MF herding: {type(exc).__name__}")

    if not parts:
        return FetchResult("", STATUS_EMPTY, "nse", reason=join_reasons(missing))
    return FetchResult("\n\n".join(parts), STATUS_OK, "nse", reason=join_reasons(missing))


_MAX_PEERS = 5


def _sector_peer_tickers(sector: str, ticker: str) -> list[str]:
    """
    Resolve the peer list for `sector`, excluding `ticker` itself and capped
    at `_MAX_PEERS`.

    automobile: settings.PEER_TICKERS (existing behaviour, unchanged).
    banking_bfsi / it_sector / renewable_energy: that sector's
    config.settings.TICKERS (lazy import).
    """
    cfg = _bundle_cfg(sector)
    module_path = cfg["peer_tickers_module"]
    attr = cfg["peer_tickers_attr"]

    if module_path is None:
        universe = getattr(
            settings, attr, ["MARUTI", "TATAMOTORS", "M&M", "HEROMOTOCO", "BAJAJ-AUTO"]
        )
    else:
        import importlib

        sector_settings = importlib.import_module(module_path)
        universe = getattr(sector_settings, attr, [])

    ticker_upper = (ticker or "").upper()
    peers = [t for t in universe if t.upper() != ticker_upper]
    return peers[:_MAX_PEERS]


def _fetch_peers_valuation(query: StockQuery, sector: str) -> FetchResult:
    """Peer P/E (sector peer list, queried ticker excluded) + NSE dividend/bonus/corporate actions.

    Status is `get_valuation_result`'s; the NSE corporate actions are prefetch
    context and do not change it.
    """
    from core.intelligence.algorithms.indicators.fetcher import get_valuation_result
    from services.data.fetchers.nse_announcements import format_nse_context

    peers = _sector_peer_tickers(sector, query.ticker)
    valuation = get_valuation_result(query.ticker, peer_tickers=peers)
    nse_ctx = format_nse_context(query.nse_data, agent_type="valuation_catalyst")
    if nse_ctx:
        return FetchResult(f"{valuation.text}\n\n{nse_ctx}", valuation.status, valuation.source,
                           as_of=valuation.as_of, reason=valuation.reason)
    return valuation


def _fetch_dossier(query: StockQuery, sector: str) -> FetchResult:
    """Ticker dossier digest — injected ONCE (replaces 9x repetition).

    Disabled, or no dossier stored for the ticker yet, is `n/a`: nothing was
    lost, there is nothing to fetch. The text stays "" in both cases, as before.
    """
    if not getattr(settings, "RL_DOSSIER_ENABLED", True):
        return FetchResult("", STATUS_NOT_APPLICABLE, "dossier",
                           reason="RL_DOSSIER_ENABLED is off")

    from core.intelligence.rl.stores.prediction_store import PredictionStore

    ps = PredictionStore(ticker=query.ticker, sector=sector or "automobile")
    dossier = ps.load_dossier()
    if dossier is None:
        return FetchResult("", STATUS_NOT_APPLICABLE, "dossier",
                           reason="no dossier stored for this ticker yet")
    digest = dossier.to_digest(settings.DOSSIER_AGENT_DIGEST_CHARS)
    as_of = getattr(dossier, "last_updated", None) or None
    if not (digest or "").strip():
        return FetchResult(digest, STATUS_EMPTY, "dossier", as_of=as_of,
                           reason="dossier digest is empty")
    return FetchResult(digest, STATUS_OK, "dossier", as_of=as_of)


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
    status: dict[str, str] = {}
    prov: dict[str, dict] = {}

    _safe(sections, status, "company_news", _fetch_company_news, query, sector, serper_key, provenance=prov)
    _safe(sections, status, "sector_policy_news", _fetch_sector_policy_news, query, sector, serper_key, provenance=prov)
    _safe(sections, status, "macro_context", _fetch_macro_context, sector, serper_key, provenance=prov)
    _safe(sections, status, "policy_deep_dive", _fetch_policy_deep_dive, query, sector, provenance=prov)
    _safe(sections, status, "fundamentals", _fetch_fundamentals, query, provenance=prov)
    _safe(sections, status, "technicals", _fetch_technicals, query, sector, provenance=prov)
    _safe(sections, status, "commodities", _fetch_commodities, sector, provenance=prov)
    _safe(sections, status, "flows_sentiment", _fetch_flows_sentiment, query, sector, provenance=prov)
    _safe(sections, status, "peers_valuation", _fetch_peers_valuation, query, sector, provenance=prov)
    _safe(sections, status, "dossier", _fetch_dossier, query, sector, provenance=prov)

    # UNCHANGED BY B2 — deliberately not re-expressed in terms of
    # `section_status`, because the two do not agree. This rule counts a
    # `n/a` section (commodities outside automobile) as live; the health
    # record does not. B2 is additive, so the flag keeps its old meaning and
    # its one consumer (a log line at base_orchestrator.py:509); B5 gates on
    # the health record instead. See spec §2.3.
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
        section_status=status,
        section_provenance=prov,
    )

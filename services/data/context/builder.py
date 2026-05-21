"""
tools/context_builder.py
========================
Assembles the per-agent context string from live data fetchers.
Each agent gets only the data relevant to its dimensions.

Called by BaseAgent._gather_context() when RAG is disabled.

Public API
----------
ContextBuilder().build(agent_name, query) → str
"""

from __future__ import annotations

import logging
from datetime import date

from core.config import settings as _settings
from core.schemas.pipeline import StockQuery

logger = logging.getLogger(__name__)


class ContextBuilder:
    """
    Routes each agent to the appropriate data fetchers and
    returns a single formatted context string for prompt injection.
    """

    def build(self, agent_name: str, query: StockQuery, sector: str = "") -> tuple[str, bool]:
        """
        Build context for the given agent and stock query.

        Parameters
        ----------
        agent_name : str   e.g. "fundamentals"
        query      : StockQuery
        sector     : str   e.g. "bfsi", "it", "re", "" (automobile/default)

        Returns
        -------
        (context_str, has_real_data)
            has_real_data=True  — a specialised fetcher ran and returned live data
            has_real_data=False — no fetcher exists or fetcher raised; generic stub returned

        Routing order:
          1. _build_{sector}_{agent_name}  — sector-specific override
          2. _build_{agent_name}           — generic / automobile fallback
          3. _build_generic               — no fetcher; stub only
        """
        # Resolve the Serper key for this sector before calling any builder.
        # Stored on the instance so builder methods can reference self._serper_key
        # without needing a parameter change. Build() is always called sequentially
        # per agent, so this is safe.
        self._serper_key: str = _settings.get_serper_key(sector)

        builder_fn = None
        if sector:
            builder_fn = getattr(self, f"_build_{sector}_{agent_name}", None)
        if builder_fn is None:
            builder_fn = getattr(self, f"_build_{agent_name}", None)

        if builder_fn is None:
            logger.warning("[ContextBuilder] No fetcher for sector=%s agent=%s — returning stub",
                           sector, agent_name)
            return self._build_generic(query), False

        try:
            return builder_fn(query), True
        except Exception as exc:
            logger.error("[ContextBuilder] Failed for sector=%s agent=%s ticker=%s: %s",
                         sector, agent_name, query.ticker, exc)
            return self._build_generic(query), False

    # ------------------------------------------------------------------
    # Per-agent context builders
    # ------------------------------------------------------------------

    def _build_sales_demand(self, query: StockQuery) -> str:
        from services.data.fetchers.news import fetch_news_context
        from core.config.prompts.automobile.sales_demand import CONTEXT_SEARCH_QUERIES

        today = date.today()
        queries = [
            q.format(
                ticker=query.ticker,
                company_name=query.company_name,
                month=today.strftime("%B"),
                year=today.year,
            )
            for q in CONTEXT_SEARCH_QUERIES
        ]
        news = fetch_news_context(queries, api_key=self._serper_key)
        return (
            f"Stock: {query.ticker} | Company: {query.company_name} | "
            f"Date: {query.analysis_date}\n\n"
            f"{news}"
        )

    def _build_fundamentals(self, query: StockQuery) -> str:
        from services.data.fetchers.fundamentals import get_fundamentals_context
        from services.data.fetchers.news import fetch_news_context
        from services.data.fetchers.nse_announcements import format_nse_context
        from core.config.prompts.automobile.fundamentals import CONTEXT_SEARCH_QUERIES

        today = date.today()
        queries = [
            q.format(
                ticker=query.ticker,
                company_name=query.company_name,
                quarter=f"Q{((today.month - 1) // 3) + 1} FY{today.year % 100}",
                year=today.year,
            )
            for q in CONTEXT_SEARCH_QUERIES
        ]
        fin_context = get_fundamentals_context(query.ticker)
        news = fetch_news_context(queries, api_key=self._serper_key)
        # NseIndiaApi: board meeting dates + results filings (official NSE events)
        nse_ctx = format_nse_context(query.nse_data, agent_type="fundamentals")
        parts = [fin_context, news]
        if nse_ctx:
            parts.append(nse_ctx)
        return "\n\n".join(parts)

    def _build_pattern_analysis(self, query: StockQuery) -> str:
        from core.intelligence.algorithms.indicators.fetcher import get_technical_context

        tech = get_technical_context(query.ticker)
        return (
            f"Stock: {query.ticker} | Company: {query.company_name} | "
            f"Date: {query.analysis_date}\n\n"
            f"{tech}"
        )

    def _build_sentiment(self, query: StockQuery) -> str:
        from services.data.fetchers.news import fetch_news_context
        from core.config.prompts.automobile.sentiment import CONTEXT_SEARCH_QUERIES

        today = date.today()
        queries = [
            q.format(
                ticker=query.ticker,
                company_name=query.company_name,
                month=today.strftime("%B"),
                year=today.year,
                quarter=f"Q{((today.month - 1) // 3) + 1} FY{today.year % 100}",
            )
            for q in CONTEXT_SEARCH_QUERIES
        ]
        news = fetch_news_context(queries, api_key=self._serper_key)
        return (
            f"Stock: {query.ticker} | Company: {query.company_name} | "
            f"Date: {query.analysis_date}\n\n"
            f"{news}"
        )

    def _build_risk_macro(self, query: StockQuery) -> str:
        from services.data.fetchers.macro import get_macro_context
        from services.data.fetchers.news import fetch_news_context
        from services.data.cache.macro_cache import get_macro_cache
        from core.config.prompts.automobile.risk_macro import CONTEXT_SEARCH_QUERIES

        # yfinance macro data — always free, fetch fresh every time
        macro = get_macro_context()

        # Check cache first — populated by micro_search_loop() in main.py.
        # risk_macro queries (INR/USD, commodities, RBI repo) are sector-level:
        # same answer for MARUTI as for TATAMOTORS on the same day.
        cached_news = get_macro_cache("automobile")
        if cached_news:
            logger.debug(
                "[ContextBuilder] risk_macro: cache HIT — skipping 3 Serper calls"
            )
            return f"{macro}\n\n[Macro news — from micro search cache]\n{cached_news}"

        # Cache miss: fetch fresh (up to SERPER_MAX_QUERIES calls)
        today = date.today()
        queries = [
            q.format(
                ticker=query.ticker,
                company_name=query.company_name,
                month=today.strftime("%B"),
                year=today.year,
                date=today.isoformat(),
            )
            for q in CONTEXT_SEARCH_QUERIES
        ]
        news = fetch_news_context(queries, api_key=self._serper_key)
        return f"{macro}\n\n{news}"

    def _build_raw_materials(self, query: StockQuery) -> str:
        from services.data.fetchers.macro import get_raw_materials_context
        from services.data.fetchers.news import fetch_news_context
        from core.config.prompts.automobile.raw_materials import CONTEXT_SEARCH_QUERIES

        today = date.today()
        queries = [
            q.format(
                ticker=query.ticker,
                company_name=query.company_name,
                year=today.year,
            )
            for q in CONTEXT_SEARCH_QUERIES
        ]
        raw_prices = get_raw_materials_context()
        news = fetch_news_context(queries, max_queries=1, api_key=self._serper_key)
        return (
            f"Stock: {query.ticker} | Company: {query.company_name} | "
            f"Date: {query.analysis_date}\n\n"
            f"{raw_prices}\n\n"
            f"{news}"
        )

    def _build_policy_regulatory(self, query: StockQuery) -> str:
        from services.clients.tavily_fetcher import fetch_tavily_context
        from services.data.fetchers.news import fetch_news_context
        from core.config.prompts.automobile.policy_regulatory import TAVILY_SEARCH_QUERIES, CONTEXT_SEARCH_QUERIES

        today = date.today()
        tavily_queries = [
            q.format(
                ticker=query.ticker,
                company_name=query.company_name,
                year=today.year,
            )
            for q in TAVILY_SEARCH_QUERIES
        ]
        serper_queries = [
            q.format(
                ticker=query.ticker,
                company_name=query.company_name,
                year=today.year,
            )
            for q in CONTEXT_SEARCH_QUERIES
        ]
        tavily_text = fetch_tavily_context(tavily_queries, max_queries=2)
        news = fetch_news_context(serper_queries, api_key=self._serper_key)
        return (
            f"Stock: {query.ticker} | Company: {query.company_name} | "
            f"Date: {query.analysis_date}\n\n"
            f"[Policy Documents — full text via Tavily]\n{tavily_text}\n\n"
            f"[Policy News — snippets via Serper]\n{news}"
        )

    def _build_competitive_intel(self, query: StockQuery) -> str:
        from services.data.fetchers.news import fetch_news_context
        from core.config.prompts.automobile.competitive_intel import CONTEXT_SEARCH_QUERIES

        today = date.today()
        queries = [
            q.format(
                ticker=query.ticker,
                company_name=query.company_name,
                month=today.strftime("%B"),
                year=today.year,
            )
            for q in CONTEXT_SEARCH_QUERIES
        ]
        news = fetch_news_context(queries, api_key=self._serper_key)
        return (
            f"Stock: {query.ticker} | Company: {query.company_name} | "
            f"Date: {query.analysis_date}\n\n"
            f"{news}"
        )

    def _build_valuation_catalyst(self, query: StockQuery) -> str:
        from core.intelligence.algorithms.indicators.fetcher import get_valuation_context
        from services.data.fetchers.nse_announcements import format_nse_context
        from core.config import settings

        peers = getattr(settings, "PEER_TICKERS", ["MARUTI", "TATAMOTORS", "M&M", "HEROMOTOCO", "BAJAJ-AUTO"])[:5]
        valuation_ctx = get_valuation_context(query.ticker, peer_tickers=peers)
        # NseIndiaApi: dividend ex-dates, bonus ratio, stock split details
        nse_ctx = format_nse_context(query.nse_data, agent_type="valuation_catalyst")
        if nse_ctx:
            return f"{valuation_ctx}\n\n{nse_ctx}"
        return valuation_ctx

    # ------------------------------------------------------------------
    # Banking & BFSI sector builders
    # ------------------------------------------------------------------

    def _build_bfsi_fundamentals(self, query: StockQuery) -> str:
        from services.data.fetchers.fundamentals import get_fundamentals_context
        from services.data.fetchers.news import fetch_news_context

        today = date.today()
        queries = [
            f"{query.ticker} NPA gross net provision coverage ratio {today.year}",
            f"{query.company_name} NIM CASA ratio quarterly results {today.year}",
            f"{query.ticker} CRAR CET1 capital adequacy RBI {today.year}",
            f"{query.company_name} RoA RoE credit cost loan growth {today.year}",
            f"{query.ticker} retail corporate loan mix MSME {today.year}",
        ]
        fin = get_fundamentals_context(query.ticker)
        news = fetch_news_context(queries, api_key=self._serper_key)
        return f"{fin}\n\n{news}"

    def _build_bfsi_risk(self, query: StockQuery) -> str:
        from services.data.fetchers.news import fetch_news_context

        today = date.today()
        queries = [
            f"{query.company_name} NPA slippage SMA-1 SMA-2 restructured book {today.year}",
            f"{query.ticker} top borrower sector concentration geography exposure {today.year}",
            f"{query.company_name} CASA wholesale deposit LCR liquidity {today.year}",
            f"{query.ticker} RBI penalty enforcement order SEBI PCA {today.year}",
            f"{query.company_name} cyber fraud incident CERT-In RBI report {today.year}",
        ]
        news = fetch_news_context(queries, api_key=self._serper_key)
        return (
            f"Stock: {query.ticker} | Company: {query.company_name} | "
            f"Date: {query.analysis_date}\n\n{news}"
        )

    def _build_bfsi_pattern_analysis(self, query: StockQuery) -> str:
        from services.data.fetchers.fundamentals import get_fundamentals_context
        from services.data.fetchers.news import fetch_news_context

        today = date.today()
        queries = [
            f"{query.ticker} technical analysis RSI MACD 52-week high low {today.year}",
            f"{query.ticker} Nifty Bank relative performance outperform {today.year}",
            f"RBI rate cut cycle PSU bank private bank rally {today.year}",
            f"{query.ticker} support resistance breakout price chart {today.year}",
        ]
        fin = get_fundamentals_context(query.ticker)
        news = fetch_news_context(queries, api_key=self._serper_key)
        return f"{fin}\n\n{news}"

    def _build_bfsi_institutional(self, query: StockQuery) -> str:
        from services.data.fetchers.fundamentals import get_fundamentals_context
        from services.data.fetchers.news import fetch_news_context

        today = date.today()
        queries = [
            f"{query.ticker} FII DII shareholding change quarterly {today.year}",
            f"{query.company_name} promoter pledge SAST filing {today.year}",
            f"AMFI {query.ticker} mutual fund monthly portfolio {today.strftime('%B')} {today.year}",
            f"{query.ticker} BSE bulk deal block trade {today.strftime('%B')} {today.year}",
            f"{query.ticker} insider trading SEBI director KMP disclosure {today.year}",
        ]
        fin = get_fundamentals_context(query.ticker)
        news = fetch_news_context(queries, api_key=self._serper_key)
        return f"{fin}\n\n{news}"

    def _build_bfsi_universe_setup(self, query: StockQuery) -> str:
        from services.data.fetchers.news import fetch_news_context

        today = date.today()
        queries = [
            f"{query.ticker} Nifty Bank PSU Bank index weight constituent {today.year}",
            f"{query.company_name} peer group PSU private NBFC market cap rank {today.year}",
            f"AMFI monthly portfolio {query.ticker} mutual fund {today.strftime('%B')} {today.year}",
            f"{query.company_name} corporate actions dividend rights merger buyback {today.year}",
            f"NSE Nifty Bank rebalancing reconstitution semi-annual {today.year}",
        ]
        news = fetch_news_context(queries, api_key=self._serper_key)
        return (
            f"Stock: {query.ticker} | Company: {query.company_name} | "
            f"Date: {query.analysis_date}\n\n{news}"
        )

    def _build_macro_policy(self, query: StockQuery) -> str:
        from services.data.fetchers.macro import get_macro_context
        from services.data.fetchers.news import fetch_news_context
        from services.data.cache.macro_cache import get_macro_cache

        macro = get_macro_context()
        cached = get_macro_cache("bfsi")
        if cached:
            return f"{macro}\n\n[BFSI macro news — cached]\n{cached}"

        today = date.today()
        queries = [
            f"RBI MPC repo rate decision {today.strftime('%B')} {today.year}",
            f"India system credit growth deposit growth CD ratio {today.year}",
            f"RBI LAF liquidity VRR VRRR CRR SLR {today.year}",
            f"RBI circular SEBI IRDAI regulatory action banking {today.year}",
            f"India government borrowing PSU bank recapitalisation IBC {today.year}",
        ]
        news = fetch_news_context(queries, api_key=self._serper_key)
        return f"{macro}\n\n{news}"

    def _build_institutional(self, query: StockQuery) -> str:
        from services.data.fetchers.fundamentals import get_fundamentals_context
        from services.data.fetchers.news import fetch_news_context

        today = date.today()
        queries = [
            f"{query.ticker} FII DII net buying selling {today.strftime('%B')} {today.year}",
            f"{query.company_name} promoter shareholding pledge change {today.year}",
            f"{query.ticker} insider trade ESOP exercise open market {today.year}",
            f"{query.company_name} analyst rating upgrade downgrade target price {today.year}",
            f"{query.ticker} mutual fund holding institutional ownership {today.year}",
        ]
        fin = get_fundamentals_context(query.ticker)
        news = fetch_news_context(queries, api_key=self._serper_key)
        return f"{fin}\n\n{news}"

    def _build_universe_setup(self, query: StockQuery) -> str:
        from services.data.fetchers.news import fetch_news_context

        today = date.today()
        queries = [
            f"{query.ticker} Nifty Bank PSU Bank index weight composition {today.year}",
            f"{query.company_name} peer comparison PSU private NBFC SFB {today.year}",
            f"{query.ticker} market cap free float classification {today.year}",
            f"{query.company_name} corporate action split bonus rights merger {today.year}",
        ]
        news = fetch_news_context(queries, api_key=self._serper_key)
        return (
            f"Stock: {query.ticker} | Company: {query.company_name} | "
            f"Date: {query.analysis_date}\n\n{news}"
        )

    # ------------------------------------------------------------------
    # IT sector builders
    # ------------------------------------------------------------------

    def _build_it_fundamentals(self, query: StockQuery) -> str:
        from services.data.fetchers.fundamentals import get_fundamentals_context
        from services.data.fetchers.news import fetch_news_context

        today = date.today()
        quarter = f"Q{((today.month - 1) // 3) + 1} FY{today.year % 100}"
        queries = [
            f"{query.ticker} revenue growth constant currency {quarter} {today.year}",
            f"{query.company_name} EBIT margin guidance quarterly results {today.year}",
            f"{query.company_name} TCV deal wins large deal pipeline {today.year}",
            f"{query.company_name} attrition fresher hiring headcount {today.year}",
            f"{query.ticker} PE EV revenue valuation peers {today.year}",
        ]
        fin = get_fundamentals_context(query.ticker)
        news = fetch_news_context(queries, api_key=self._serper_key)
        return f"{fin}\n\n{news}"

    def _build_global_macro(self, query: StockQuery) -> str:
        from services.data.fetchers.macro import get_macro_context
        from services.data.fetchers.news import fetch_news_context

        macro = get_macro_context()
        today = date.today()
        queries = [
            f"US IT spending enterprise software cloud capex {today.year}",
            f"Federal Reserve rate decision US tech capex impact {today.year}",
            f"USD INR exchange rate impact Indian IT revenue {today.strftime('%B')} {today.year}",
            f"US China tech war CHIPS Act offshoring Indian IT {today.year}",
            f"global IT M&A deal multiples software consolidation {today.year}",
        ]
        news = fetch_news_context(queries, api_key=self._serper_key)
        return f"{macro}\n\n{news}"

    def _build_it_risk_macro(self, query: StockQuery) -> str:
        from services.data.fetchers.macro import get_macro_context
        from services.data.fetchers.news import fetch_news_context
        from services.data.cache.macro_cache import get_macro_cache

        macro = get_macro_context()
        cached = get_macro_cache("it")
        if cached:
            return f"{macro}\n\n[IT macro news — cached]\n{cached}"

        today = date.today()
        queries = [
            f"H1B L1 visa approval denial rate US immigration {today.year}",
            f"GenAI automation disruption Indian IT revenue risk {today.year}",
            f"{query.company_name} top client concentration churn vertical {today.year}",
            f"{query.ticker} INR USD hedge FX derivative revenue mix {today.year}",
            f"Indian IT talent supply campus hiring moonlighting {today.year}",
        ]
        news = fetch_news_context(queries, api_key=self._serper_key)
        return f"{macro}\n\n{news}"

    def _build_peer_benchmark(self, query: StockQuery) -> str:
        from services.data.fetchers.fundamentals import get_fundamentals_context
        from services.data.fetchers.news import fetch_news_context

        today = date.today()
        quarter = f"Q{((today.month - 1) // 3) + 1} FY{today.year % 100}"
        queries = [
            f"{query.ticker} vs TCS Infosys HCL Wipro revenue growth {quarter}",
            f"{query.company_name} EBIT margin peer comparison IT sector {today.year}",
            f"{query.company_name} deal wins TCV vs peers Infosys TCS {today.year}",
            f"{query.company_name} attrition headcount vs IT peers comparison {today.year}",
            f"{query.ticker} PE premium discount to IT peer median {today.year}",
        ]
        fin = get_fundamentals_context(query.ticker)
        news = fetch_news_context(queries, api_key=self._serper_key)
        return f"{fin}\n\n{news}"

    def _build_it_pattern_analysis(self, query: StockQuery) -> str:
        from services.data.fetchers.fundamentals import get_fundamentals_context
        from services.data.fetchers.news import fetch_news_context

        today = date.today()
        queries = [
            f"{query.ticker} technical analysis RSI MACD 52-week high low Nifty IT {today.year}",
            f"{query.ticker} Nifty IT relative performance alpha beta {today.year}",
            f"{query.ticker} support resistance breakout price chart {today.strftime('%B')} {today.year}",
            f"Indian IT sector Nifty IT trend momentum {today.strftime('%B')} {today.year}",
        ]
        fin = get_fundamentals_context(query.ticker)
        news = fetch_news_context(queries, api_key=self._serper_key)
        return f"{fin}\n\n{news}"

    def _build_it_sentiment(self, query: StockQuery) -> str:
        from services.data.fetchers.news import fetch_news_context

        today = date.today()
        quarter = f"Q{((today.month - 1) // 3) + 1} FY{today.year % 100}"
        queries = [
            f"{query.company_name} AI GenAI deal announcement narrative {today.year}",
            f"{query.company_name} layoff bench utilisation headcount {today.year}",
            f"{query.ticker} CEO CFO management interview outlook {today.strftime('%B')} {today.year}",
            f"Indian IT sector Nifty IT analyst rating outlook {today.strftime('%B')} {today.year}",
            f"{query.ticker} news media coverage {today.strftime('%B')} {today.year}",
        ]
        news = fetch_news_context(queries, api_key=self._serper_key)
        return (
            f"Stock: {query.ticker} | Company: {query.company_name} | "
            f"Date: {query.analysis_date}\n\n{news}"
        )

    def _build_transcript_nlp(self, query: StockQuery) -> str:
        from services.clients.tavily_fetcher import fetch_tavily_context
        from services.data.fetchers.news import fetch_news_context

        today = date.today()
        quarter = f"Q{((today.month - 1) // 3) + 1} FY{today.year % 100}"
        tavily_queries = [
            f"{query.company_name} earnings call transcript {quarter} {today.year}",
            f"{query.ticker} CEO CFO analyst Q&A conference call {today.year}",
        ]
        news_queries = [
            f"{query.company_name} management commentary guidance {quarter}",
            f"{query.ticker} earnings call GenAI AI demand commentary {today.year}",
        ]
        transcript = fetch_tavily_context(tavily_queries, max_queries=2)
        news = fetch_news_context(news_queries, max_queries=2, api_key=self._serper_key)
        return (
            f"Stock: {query.ticker} | Company: {query.company_name} | "
            f"Date: {query.analysis_date}\n\n"
            f"[Transcript context — Tavily]\n{transcript}\n\n"
            f"[Earnings news]\n{news}"
        )

    def _build_insider_smart_money(self, query: StockQuery) -> str:
        from services.data.fetchers.fundamentals import get_fundamentals_context
        from services.data.fetchers.news import fetch_news_context

        today = date.today()
        queries = [
            f"{query.ticker} SAST filing SEBI acquisition promoter pledge {today.year}",
            f"{query.company_name} director insider trade KMP ESOP exercise {today.year}",
            f"AMFI {query.ticker} mutual fund monthly portfolio {today.strftime('%B')} {today.year}",
            f"{query.ticker} FII futures derivative net position {today.year}",
            f"{query.ticker} BSE bulk deal block trade {today.strftime('%B')} {today.year}",
        ]
        fin = get_fundamentals_context(query.ticker)
        news = fetch_news_context(queries, api_key=self._serper_key)
        return f"{fin}\n\n{news}"

    # ------------------------------------------------------------------
    # Renewable Energy sector builders
    # ------------------------------------------------------------------

    def _build_re_fundamentals(self, query: StockQuery) -> str:
        from services.data.fetchers.fundamentals import get_fundamentals_context
        from services.data.fetchers.news import fetch_news_context
        from services.data.fetchers.nse_announcements import format_nse_context

        today = date.today()
        queries = [
            f"{query.company_name} CUF capacity utilisation solar wind generation {today.year}",
            f"{query.ticker} EBITDA per MW operating leverage O&M cost {today.year}",
            f"{query.company_name} DSCR debt service coverage refinancing {today.year}",
            f"{query.ticker} DISCOM receivables payment delay aging {today.year}",
            f"{query.company_name} debt equity leverage project holdco {today.year}",
        ]
        fin = get_fundamentals_context(query.ticker)
        news = fetch_news_context(queries, api_key=self._serper_key)
        # NseIndiaApi: commissioning milestones (COD events) + board meeting results dates.
        # RE companies must file "Commencement of commercial production/operations" to NSE
        # within 24h of COD — official, timestamped, MW detail in attchmntText.
        nse_ctx = format_nse_context(query.nse_data, agent_type="re_fundamentals")
        parts = [fin, news]
        if nse_ctx:
            parts.append(nse_ctx)
        return "\n\n".join(parts)

    def _build_business(self, query: StockQuery) -> str:
        from services.data.fetchers.news import fetch_news_context
        from services.data.fetchers.nse_announcements import format_nse_context

        today = date.today()
        queries = [
            f"{query.company_name} solar wind hybrid capacity mix MW commissioned {today.year}",
            f"{query.ticker} PPA tariff tenor counterparty DISCOM C&I {today.year}",
            f"{query.company_name} under construction pipeline commissioning {today.year}",
            f"{query.ticker} state wise MW distribution geography irradiance {today.year}",
        ]
        news = fetch_news_context(queries, api_key=self._serper_key)
        # NseIndiaApi: commissioning COD filings + PPA/project update announcements.
        # "Commencement of commercial production/operations" filings give exact COD dates,
        # location, and MW capacity — directly feeds pipeline_cred and subsector_mix scores.
        nse_ctx = format_nse_context(query.nse_data, agent_type="re_business")
        base = (
            f"Stock: {query.ticker} | Company: {query.company_name} | "
            f"Date: {query.analysis_date}\n\n{news}"
        )
        return f"{base}\n\n{nse_ctx}" if nse_ctx else base

    def _build_valuation(self, query: StockQuery) -> str:
        from services.data.fetchers.fundamentals import get_fundamentals_context
        from services.data.fetchers.news import fetch_news_context
        from services.data.fetchers.nse_announcements import format_nse_context

        today = date.today()
        queries = [
            f"{query.ticker} EV per MW enterprise value renewable peer {today.year}",
            f"{query.company_name} EV EBITDA multiple valuation solar wind {today.year}",
            f"MNRE auction tariff L1 rate solar wind {today.strftime('%B')} {today.year}",
            f"{query.company_name} equity IRR WACC implied returns {today.year}",
        ]
        fin = get_fundamentals_context(query.ticker)
        news = fetch_news_context(queries, api_key=self._serper_key)
        # NseIndiaApi: dividend/bonus/rights from actions() (capital return policy).
        # Fund raising board meetings (QIP, rights issue) signal equity dilution — critical
        # for EV/MW denominator and pipeline DCF accretion/dilution calculation.
        nse_ctx = format_nse_context(query.nse_data, agent_type="re_valuation")
        parts = [fin, news]
        if nse_ctx:
            parts.append(nse_ctx)
        return "\n\n".join(parts)

    def _build_sentiment_policy(self, query: StockQuery) -> str:
        from services.clients.tavily_fetcher import fetch_tavily_context
        from services.data.fetchers.news import fetch_news_context

        today = date.today()
        tavily_queries = [
            f"MNRE renewable energy auction {today.year} GW awarded tariff solar wind",
            f"India Union Budget renewable energy PLI RPO ISTS waiver {today.year}",
        ]
        news_queries = [
            f"{query.company_name} MNRE project win auction {today.year}",
            f"RBI repo rate WACC impact renewable energy {today.year}",
            f"solar module price BloombergNEF Mercom {today.strftime('%B')} {today.year}",
        ]
        policy = fetch_tavily_context(tavily_queries, max_queries=2)
        news = fetch_news_context(news_queries, api_key=self._serper_key)
        return (
            f"Stock: {query.ticker} | Company: {query.company_name} | "
            f"Date: {query.analysis_date}\n\n"
            f"[Policy & MNRE — Tavily]\n{policy}\n\n"
            f"[Sector news]\n{news}"
        )

    def _build_technical(self, query: StockQuery) -> str:
        from core.intelligence.algorithms.indicators.fetcher import get_technical_context

        tech = get_technical_context(query.ticker)
        return (
            f"Stock: {query.ticker} | Company: {query.company_name} | "
            f"Date: {query.analysis_date}\n\n{tech}"
        )

    def _build_re_risk(self, query: StockQuery) -> str:
        from services.data.fetchers.news import fetch_news_context
        from services.data.fetchers.nse_announcements import format_nse_context

        today = date.today()
        queries = [
            f"{query.ticker} DISCOM payment delay PFC RDSS report {today.year}",
            f"{query.ticker} curtailment risk CERC MNRE state grid {today.year}",
            f"{query.company_name} PPA tariff protection force majeure renegotiation {today.year}",
            f"{query.company_name} commissioning delay execution risk MNRE extension {today.year}",
            f"{query.ticker} promoter pledge BSE NSE refinancing {today.year}",
        ]
        news = fetch_news_context(queries, api_key=self._serper_key)
        # NseIndiaApi: promoter pledge disclosures and operational risk filings.
        # Pledge changes are mandatory NSE disclosures — official, timestamped, authoritative.
        # Replaces the "{ticker} promoter pledge BSE NSE" Serper query for primary source.
        nse_ctx = format_nse_context(query.nse_data, agent_type="re_risk")
        base = (
            f"Stock: {query.ticker} | Company: {query.company_name} | "
            f"Date: {query.analysis_date}\n\n{news}"
        )
        return f"{base}\n\n{nse_ctx}" if nse_ctx else base

    def _build_generic(self, query: StockQuery) -> str:
        return (
            f"Stock: {query.ticker} | Company: {query.company_name} | "
            f"Exchange: {query.exchange} | Date: {query.analysis_date}\n"
            "No specialised data fetcher for this agent."
        )

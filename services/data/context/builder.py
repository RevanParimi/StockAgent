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

from models.schemas import StockQuery

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
        from tools.news_fetcher import fetch_news_context
        from prompts.sales_demand import CONTEXT_SEARCH_QUERIES

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
        news = fetch_news_context(queries)
        return (
            f"Stock: {query.ticker} | Company: {query.company_name} | "
            f"Date: {query.analysis_date}\n\n"
            f"{news}"
        )

    def _build_fundamentals(self, query: StockQuery) -> str:
        from tools.fundamentals_fetcher import get_fundamentals_context
        from tools.news_fetcher import fetch_news_context
        from prompts.fundamentals import CONTEXT_SEARCH_QUERIES

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
        news = fetch_news_context(queries)
        return f"{fin_context}\n\n{news}"

    def _build_pattern_analysis(self, query: StockQuery) -> str:
        from tools.yfinance_fetcher import get_technical_context

        tech = get_technical_context(query.ticker)
        return (
            f"Stock: {query.ticker} | Company: {query.company_name} | "
            f"Date: {query.analysis_date}\n\n"
            f"{tech}"
        )

    def _build_sentiment(self, query: StockQuery) -> str:
        from tools.news_fetcher import fetch_news_context
        from prompts.sentiment import CONTEXT_SEARCH_QUERIES

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
        news = fetch_news_context(queries)
        return (
            f"Stock: {query.ticker} | Company: {query.company_name} | "
            f"Date: {query.analysis_date}\n\n"
            f"{news}"
        )

    def _build_risk_macro(self, query: StockQuery) -> str:
        from tools.macro_fetcher import get_macro_context
        from tools.news_fetcher import fetch_news_context
        from tools.macro_cache import get_macro_cache
        from prompts.risk_macro import CONTEXT_SEARCH_QUERIES

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
        news = fetch_news_context(queries)
        return f"{macro}\n\n{news}"

    def _build_raw_materials(self, query: StockQuery) -> str:
        from tools.macro_fetcher import get_raw_materials_context
        from tools.news_fetcher import fetch_news_context
        from prompts.raw_materials import CONTEXT_SEARCH_QUERIES

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
        news = fetch_news_context(queries, max_queries=1)
        return (
            f"Stock: {query.ticker} | Company: {query.company_name} | "
            f"Date: {query.analysis_date}\n\n"
            f"{raw_prices}\n\n"
            f"{news}"
        )

    def _build_policy_regulatory(self, query: StockQuery) -> str:
        from tools.tavily_fetcher import fetch_tavily_context
        from tools.news_fetcher import fetch_news_context
        from prompts.policy_regulatory import TAVILY_SEARCH_QUERIES, CONTEXT_SEARCH_QUERIES

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
        news = fetch_news_context(serper_queries)
        return (
            f"Stock: {query.ticker} | Company: {query.company_name} | "
            f"Date: {query.analysis_date}\n\n"
            f"[Policy Documents — full text via Tavily]\n{tavily_text}\n\n"
            f"[Policy News — snippets via Serper]\n{news}"
        )

    def _build_competitive_intel(self, query: StockQuery) -> str:
        from tools.news_fetcher import fetch_news_context
        from prompts.competitive_intel import CONTEXT_SEARCH_QUERIES

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
        news = fetch_news_context(queries)
        return (
            f"Stock: {query.ticker} | Company: {query.company_name} | "
            f"Date: {query.analysis_date}\n\n"
            f"{news}"
        )

    def _build_valuation_catalyst(self, query: StockQuery) -> str:
        from tools.yfinance_fetcher import get_valuation_context
        from config import settings

        peers = getattr(settings, "PEER_TICKERS", ["MARUTI", "TATAMOTORS", "M&M", "HEROMOTOCO", "BAJAJ-AUTO"])[:5]
        return get_valuation_context(query.ticker, peer_tickers=peers)

    # ------------------------------------------------------------------
    # Banking & BFSI sector builders
    # ------------------------------------------------------------------

    def _build_bfsi_fundamentals(self, query: StockQuery) -> str:
        from tools.fundamentals_fetcher import get_fundamentals_context
        from tools.news_fetcher import fetch_news_context

        today = date.today()
        queries = [
            f"{query.ticker} NPA gross net provision coverage ratio {today.year}",
            f"{query.company_name} NIM CASA ratio quarterly results {today.year}",
            f"{query.ticker} CRAR CET1 capital adequacy RBI {today.year}",
            f"{query.company_name} RoA RoE credit cost loan growth {today.year}",
            f"{query.ticker} retail corporate loan mix MSME {today.year}",
        ]
        fin = get_fundamentals_context(query.ticker)
        news = fetch_news_context(queries)
        return f"{fin}\n\n{news}"

    def _build_bfsi_risk(self, query: StockQuery) -> str:
        from tools.news_fetcher import fetch_news_context

        today = date.today()
        queries = [
            f"{query.company_name} NPA slippage SMA restructured book {today.year}",
            f"{query.ticker} top borrower concentration sectoral exposure {today.year}",
            f"{query.company_name} CASA wholesale deposit runoff risk {today.year}",
            f"{query.ticker} RBI penalty SEBI action regulatory risk {today.year}",
            f"{query.company_name} NIM compression rate sensitivity FX exposure {today.year}",
        ]
        news = fetch_news_context(queries)
        return (
            f"Stock: {query.ticker} | Company: {query.company_name} | "
            f"Date: {query.analysis_date}\n\n{news}"
        )

    def _build_macro_policy(self, query: StockQuery) -> str:
        from tools.macro_fetcher import get_macro_context
        from tools.news_fetcher import fetch_news_context
        from tools.macro_cache import get_macro_cache

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
        news = fetch_news_context(queries)
        return f"{macro}\n\n{news}"

    def _build_institutional(self, query: StockQuery) -> str:
        from tools.fundamentals_fetcher import get_fundamentals_context
        from tools.news_fetcher import fetch_news_context

        today = date.today()
        queries = [
            f"{query.ticker} FII DII net buying selling {today.strftime('%B')} {today.year}",
            f"{query.company_name} promoter shareholding pledge change {today.year}",
            f"{query.ticker} insider trade ESOP exercise open market {today.year}",
            f"{query.company_name} analyst rating upgrade downgrade target price {today.year}",
            f"{query.ticker} mutual fund holding institutional ownership {today.year}",
        ]
        fin = get_fundamentals_context(query.ticker)
        news = fetch_news_context(queries)
        return f"{fin}\n\n{news}"

    def _build_universe_setup(self, query: StockQuery) -> str:
        from tools.news_fetcher import fetch_news_context

        today = date.today()
        queries = [
            f"{query.ticker} Nifty Bank PSU Bank index weight composition {today.year}",
            f"{query.company_name} peer comparison PSU private NBFC SFB {today.year}",
            f"{query.ticker} market cap free float classification {today.year}",
            f"{query.company_name} corporate action split bonus rights merger {today.year}",
        ]
        news = fetch_news_context(queries)
        return (
            f"Stock: {query.ticker} | Company: {query.company_name} | "
            f"Date: {query.analysis_date}\n\n{news}"
        )

    # ------------------------------------------------------------------
    # IT sector builders
    # ------------------------------------------------------------------

    def _build_it_fundamentals(self, query: StockQuery) -> str:
        from tools.fundamentals_fetcher import get_fundamentals_context
        from tools.news_fetcher import fetch_news_context

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
        news = fetch_news_context(queries)
        return f"{fin}\n\n{news}"

    def _build_global_macro(self, query: StockQuery) -> str:
        from tools.macro_fetcher import get_macro_context
        from tools.news_fetcher import fetch_news_context

        macro = get_macro_context()
        today = date.today()
        queries = [
            f"US IT spending enterprise software cloud capex {today.year}",
            f"Federal Reserve rate decision US tech capex impact {today.year}",
            f"USD INR exchange rate impact Indian IT revenue {today.strftime('%B')} {today.year}",
            f"US China tech war CHIPS Act offshoring Indian IT {today.year}",
            f"global IT M&A deal multiples software consolidation {today.year}",
        ]
        news = fetch_news_context(queries)
        return f"{macro}\n\n{news}"

    def _build_it_risk_macro(self, query: StockQuery) -> str:
        from tools.macro_fetcher import get_macro_context
        from tools.news_fetcher import fetch_news_context
        from tools.macro_cache import get_macro_cache

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
        news = fetch_news_context(queries)
        return f"{macro}\n\n{news}"

    def _build_peer_benchmark(self, query: StockQuery) -> str:
        from tools.fundamentals_fetcher import get_fundamentals_context
        from tools.news_fetcher import fetch_news_context

        today = date.today()
        quarter = f"Q{((today.month - 1) // 3) + 1} FY{today.year % 100}"
        queries = [
            f"{query.ticker} vs TCS Infosys HCL Wipro revenue growth {quarter}",
            f"{query.company_name} EBIT margin peer comparison IT sector {today.year}",
            f"{query.company_name} deal wins TCV vs peers Infosys TCS {today.year}",
            f"{query.ticker} RoCE dividend buyback vs IT peers {today.year}",
            f"{query.ticker} PE premium discount to IT peer median {today.year}",
        ]
        fin = get_fundamentals_context(query.ticker)
        news = fetch_news_context(queries)
        return f"{fin}\n\n{news}"

    def _build_it_sentiment(self, query: StockQuery) -> str:
        from tools.news_fetcher import fetch_news_context

        today = date.today()
        quarter = f"Q{((today.month - 1) // 3) + 1} FY{today.year % 100}"
        queries = [
            f"{query.company_name} news sentiment analyst view {today.strftime('%B')} {today.year}",
            f"{query.ticker} earnings call management tone guidance {quarter}",
            f"{query.company_name} GenAI AI deal announcement strategy {today.year}",
            f"{query.company_name} layoff workforce reduction bench utilisation {today.year}",
            f"{query.ticker} investor sentiment Twitter Reddit IT stock {today.year}",
        ]
        news = fetch_news_context(queries)
        return (
            f"Stock: {query.ticker} | Company: {query.company_name} | "
            f"Date: {query.analysis_date}\n\n{news}"
        )

    def _build_transcript_nlp(self, query: StockQuery) -> str:
        from tools.tavily_fetcher import fetch_tavily_context
        from tools.news_fetcher import fetch_news_context

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
        news = fetch_news_context(news_queries, max_queries=2)
        return (
            f"Stock: {query.ticker} | Company: {query.company_name} | "
            f"Date: {query.analysis_date}\n\n"
            f"[Transcript context — Tavily]\n{transcript}\n\n"
            f"[Earnings news]\n{news}"
        )

    def _build_insider_smart_money(self, query: StockQuery) -> str:
        from tools.fundamentals_fetcher import get_fundamentals_context
        from tools.news_fetcher import fetch_news_context

        today = date.today()
        queries = [
            f"{query.ticker} promoter open market buy sell ESOP {today.year}",
            f"{query.company_name} director insider trade pre post results {today.year}",
            f"{query.ticker} SBI HDFC Mirae mutual fund allocation change {today.year}",
            f"{query.ticker} put call ratio short interest F&O {today.year}",
            f"{query.ticker} block deal bulk deal counterparty {today.year}",
        ]
        fin = get_fundamentals_context(query.ticker)
        news = fetch_news_context(queries)
        return f"{fin}\n\n{news}"

    # ------------------------------------------------------------------
    # Renewable Energy sector builders
    # ------------------------------------------------------------------

    def _build_re_fundamentals(self, query: StockQuery) -> str:
        from tools.fundamentals_fetcher import get_fundamentals_context
        from tools.news_fetcher import fetch_news_context

        today = date.today()
        queries = [
            f"{query.company_name} CUF capacity utilisation solar wind generation {today.year}",
            f"{query.ticker} EBITDA per MW operating leverage O&M cost {today.year}",
            f"{query.company_name} DSCR debt service coverage refinancing {today.year}",
            f"{query.ticker} DISCOM receivables payment delay aging {today.year}",
            f"{query.company_name} debt equity leverage project holdco {today.year}",
        ]
        fin = get_fundamentals_context(query.ticker)
        news = fetch_news_context(queries)
        return f"{fin}\n\n{news}"

    def _build_business(self, query: StockQuery) -> str:
        from tools.news_fetcher import fetch_news_context

        today = date.today()
        queries = [
            f"{query.company_name} solar wind hybrid capacity mix MW commissioned {today.year}",
            f"{query.ticker} PPA tariff tenor counterparty DISCOM C&I {today.year}",
            f"{query.company_name} under construction pipeline commissioning {today.year}",
            f"{query.ticker} state wise MW distribution geography irradiance {today.year}",
        ]
        news = fetch_news_context(queries)
        return (
            f"Stock: {query.ticker} | Company: {query.company_name} | "
            f"Date: {query.analysis_date}\n\n{news}"
        )

    def _build_valuation(self, query: StockQuery) -> str:
        from tools.fundamentals_fetcher import get_fundamentals_context
        from tools.news_fetcher import fetch_news_context

        today = date.today()
        queries = [
            f"{query.ticker} EV per MW enterprise value renewable peer {today.year}",
            f"{query.company_name} EV EBITDA multiple valuation solar wind {today.year}",
            f"MNRE auction tariff L1 rate solar wind {today.strftime('%B')} {today.year}",
            f"{query.company_name} equity IRR WACC implied returns {today.year}",
        ]
        fin = get_fundamentals_context(query.ticker)
        news = fetch_news_context(queries)
        return f"{fin}\n\n{news}"

    def _build_sentiment_policy(self, query: StockQuery) -> str:
        from tools.tavily_fetcher import fetch_tavily_context
        from tools.news_fetcher import fetch_news_context

        today = date.today()
        tavily_queries = [
            f"MNRE renewable energy auction {today.year} GW awarded tariff",
            f"India green hydrogen mission ISTS waiver RPO target {today.year}",
        ]
        news_queries = [
            f"{query.company_name} MNRE project win auction order {today.year}",
            f"India Union Budget renewable energy capex solar wind {today.year}",
            f"{query.ticker} green hydrogen investment announcement {today.year}",
        ]
        policy = fetch_tavily_context(tavily_queries, max_queries=2)
        news = fetch_news_context(news_queries)
        return (
            f"Stock: {query.ticker} | Company: {query.company_name} | "
            f"Date: {query.analysis_date}\n\n"
            f"[Policy & MNRE — Tavily]\n{policy}\n\n"
            f"[Sector news]\n{news}"
        )

    def _build_technical(self, query: StockQuery) -> str:
        from tools.yfinance_fetcher import get_technical_context

        tech = get_technical_context(query.ticker)
        return (
            f"Stock: {query.ticker} | Company: {query.company_name} | "
            f"Date: {query.analysis_date}\n\n{tech}"
        )

    def _build_re_risk(self, query: StockQuery) -> str:
        from tools.news_fetcher import fetch_news_context

        today = date.today()
        queries = [
            f"{query.company_name} DISCOM payment delay default UDAY RDSS {today.year}",
            f"{query.ticker} tariff renegotiation curtailment order regulatory {today.year}",
            f"monsoon variability hydro solar wind generation impact India {today.year}",
            f"{query.company_name} transmission bottleneck grid evacuation {today.year}",
            f"solar module steel copper capex cost India {today.year}",
        ]
        news = fetch_news_context(queries)
        return (
            f"Stock: {query.ticker} | Company: {query.company_name} | "
            f"Date: {query.analysis_date}\n\n{news}"
        )

    def _build_generic(self, query: StockQuery) -> str:
        return (
            f"Stock: {query.ticker} | Company: {query.company_name} | "
            f"Exchange: {query.exchange} | Date: {query.analysis_date}\n"
            "No specialised data fetcher for this agent."
        )

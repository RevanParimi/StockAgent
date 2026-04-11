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

    def build(self, agent_name: str, query: StockQuery) -> str:
        """
        Build context for the given agent and stock query.

        Parameters
        ----------
        agent_name : str   e.g. "sales_demand"
        query      : StockQuery

        Returns
        -------
        str — multi-line context block ready for {context} placeholder
        """
        builder_fn = getattr(self, f"_build_{agent_name}", self._build_generic)
        try:
            return builder_fn(query)
        except Exception as exc:
            logger.error("[ContextBuilder] Failed for agent=%s ticker=%s: %s",
                         agent_name, query.ticker, exc)
            return self._build_generic(query)

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

    def _build_generic(self, query: StockQuery) -> str:
        return (
            f"Stock: {query.ticker} | Company: {query.company_name} | "
            f"Exchange: {query.exchange} | Date: {query.analysis_date}\n"
            "No specialised data fetcher for this agent."
        )

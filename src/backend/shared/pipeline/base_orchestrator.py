"""
src/backend/shared/pipeline/base_orchestrator.py
=================================================
Abstract base class for all sector orchestrators.

Every sector (automobile, banking_bfsi, it_sector, renewable_energy) creates one
concrete subclass that:
  1. Defines its SECTOR_NAME class attribute
  2. Instantiates its own _SUB_AGENTS dict
  3. Calls super().__init__() to wire everything up

All the heavy lifting — ticker resolution, LangGraph dispatch, RL weight loading,
signal aggregation, logging — lives here so it never has to be duplicated.

Usage (automobile sector):
    from backend.shared.pipeline.base_orchestrator import BaseSectorOrchestrator
    class AutomobileAgentOrchestrator(BaseSectorOrchestrator):
        SECTOR_NAME = "automobile"
        def __init__(self):
            from backend.sectors.automobile.agents.sales_demand import SalesDemandAgent
            ...
            self._sub_agents = {"sales_demand": SalesDemandAgent(), ...}
            super().__init__()
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import time
import uuid
from abc import ABC, abstractmethod
from collections.abc import Callable
from datetime import date, datetime, timezone

from langgraph.graph import END, START, StateGraph
try:
    from langgraph.types import RetryPolicy
except ImportError:
    from langgraph.pregel import RetryPolicy  # type: ignore[no-redef]

from backend.shared.config import settings
from backend.shared.schemas.pipeline import AgentOutput, FinalReport, PipelineRun, StockQuery
from backend.shared.prompts import orchestrator as P
from backend.shared.clients.llm_client import get_llm_client
from backend.shared.data.fetchers.symbol_resolver import learn_company_name, resolve_company_name
from backend.shared.data.stores.run_logger import log_llm_call, log_run_summary
from backend.shared.data.stores.analysis_logger import log_analysis
from backend.shared.data.stores.api_usage import log_run_api_usage, snapshot_usage
from backend.shared.pipeline.graphs.nodes import make_dispatch_fn, make_run_agent_node
from backend.shared.pipeline.graphs.state import GraphState
from backend.shared.pipeline.signal_aggregator import SignalAggregator

logger = logging.getLogger(__name__)


def _build_worker_pool_graph(agents: dict, sector: str):
    """Compile a minimal LangGraph worker pool for a given sector's agent dict."""
    agents_snapshot = dict(agents.items())
    _run_agent_node = make_run_agent_node(agents_snapshot, sector)
    _dispatch_fn = make_dispatch_fn(list(agents_snapshot.keys()))

    wf = StateGraph(GraphState)
    wf.add_node("run_agent", _run_agent_node, retry_policy=RetryPolicy(max_attempts=2))
    wf.add_conditional_edges(START, _dispatch_fn)
    wf.add_edge("run_agent", END)
    return wf.compile()


class BaseSectorOrchestrator(ABC):
    """
    Sector-agnostic orchestrator base.

    Concrete subclasses must:
      - Set SECTOR_NAME (str)
      - Populate self._sub_agents (dict[str, BaseAgent]) before calling super().__init__()
    """

    SECTOR_NAME: str = "unknown"

    def __init__(self) -> None:
        if not hasattr(self, "_sub_agents") or not self._sub_agents:
            raise RuntimeError(
                f"{self.__class__.__name__} must populate self._sub_agents before calling super().__init__()"
            )
        self._llm = get_llm_client()
        self._aggregator = SignalAggregator()
        # Set by generate_forecast.py / daily_review.py; else auto-loaded from RL WeightMemory.
        self._aggregator_weights: dict[str, float] | None = None
        # Ticker that _aggregator_weights was resolved/injected for — drives per-ticker
        # weight scoping so a long-lived orchestrator instance reloads weights when
        # the ticker changes between analyse()/analyse_async() calls.
        self._aggregator_weights_ticker: str | None = None
        self._worker_pool_graph = _build_worker_pool_graph(self._sub_agents, self.SECTOR_NAME)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def analyse_async(
        self,
        user_input: str,
        progress_callback: Callable[[str, float], None] | None = None,
    ) -> FinalReport:
        """Async end-to-end analysis. Preferred entry point for FastAPI / WebSocket."""
        run_id = str(uuid.uuid4())[:8]
        start = time.time()
        started_at = datetime.now(timezone.utc)
        api_snapshot = snapshot_usage()
        logger.info("[%s] Async run %s started for '%s'", self.SECTOR_NAME, run_id, user_input)

        query = await asyncio.to_thread(self._resolve_ticker, user_input, run_id)
        logger.info("[%s] Resolved: %s -> %s", self.SECTOR_NAME, user_input, query)

        if self._aggregator_weights is None or self._aggregator_weights_ticker != query.ticker:
            learned = await asyncio.to_thread(self._load_learned_weights, query.ticker)
            self._aggregator_weights = learned or self._get_default_weights()
            self._aggregator_weights_ticker = query.ticker

        # Pre-fetch NseIndiaApi data before fan-out — NSE() is sync, run in thread.
        # All 8 parallel agents share query.nse_data as read-only (set here, never written by agents).
        await asyncio.to_thread(self._prefetch_nse_data, query)

        pipeline_run = PipelineRun(run_id=run_id, query=query, status="running")
        if self._unified_enabled():
            agent_outputs = await asyncio.to_thread(
                self._run_agents, query, run_id, progress_callback
            )
        else:
            agent_outputs = await self._run_via_graph_async(
                query, run_id=run_id, progress_callback=progress_callback
            )

        report = self._aggregator.run(
            ticker=query.ticker,
            company_name=query.company_name,
            agent_outputs=agent_outputs,
            learned_weights=self._aggregator_weights,
            run_id=run_id,
        )

        pipeline_run.report = report
        pipeline_run.status = "completed"
        pipeline_run.duration_seconds = round(time.time() - start, 2)

        errors = [f"{n}: {o.error}" for n, o in agent_outputs.items() if o.error]
        log_run_summary(
            run_id=run_id, ticker=query.ticker, company_name=query.company_name,
            started_at=started_at, duration_seconds=pipeline_run.duration_seconds,
            final_score=report.final_score, verdict=report.verdict,
            total_prompt_tokens=0, total_completion_tokens=0, total_cost_usd=0.0,
            agent_scores={n: o.overall_score for n, o in agent_outputs.items()},
            errors=errors,
        )
        log_run_api_usage(run_id, query.ticker, api_snapshot)
        log_analysis(
            report=report, run_id=run_id,
            duration_seconds=pipeline_run.duration_seconds,
            model=settings.LLM_MODEL, agent_outputs=agent_outputs,
        )
        logger.info(
            "[%s] Async run %s done in %.1fs — verdict=%s score=%.3f",
            self.SECTOR_NAME, run_id, pipeline_run.duration_seconds,
            report.verdict, report.final_score,
        )
        return report

    def analyse(
        self,
        user_input: str,
        progress_callback: Callable[[str, float], None] | None = None,
    ) -> FinalReport:
        """Sync end-to-end analysis. Used by CLI and scheduler."""
        run_id = str(uuid.uuid4())[:8]
        start = time.time()
        started_at = datetime.now(timezone.utc)
        api_snapshot = snapshot_usage()
        logger.info("[%s] Run %s started for '%s'", self.SECTOR_NAME, run_id, user_input)

        query = self._resolve_ticker(user_input, run_id=run_id)
        logger.info("[%s] Resolved: %s -> %s", self.SECTOR_NAME, user_input, query)

        self._resolve_weights_for(query.ticker)

        # Pre-fetch NseIndiaApi data before fan-out — one session, three calls, 0.5s sleep each.
        # All 8 parallel agents share query.nse_data as read-only.
        self._prefetch_nse_data(query)

        pipeline_run = PipelineRun(run_id=run_id, query=query, status="running")
        agent_outputs = self._run_agents(
            query, run_id=run_id, progress_callback=progress_callback
        )

        report = self._aggregator.run(
            ticker=query.ticker,
            company_name=query.company_name,
            agent_outputs=agent_outputs,
            learned_weights=self._aggregator_weights,
            run_id=run_id,
        )

        pipeline_run.report = report
        pipeline_run.status = "completed"
        pipeline_run.duration_seconds = round(time.time() - start, 2)

        errors = [f"{n}: {o.error}" for n, o in agent_outputs.items() if o.error]
        log_run_summary(
            run_id=run_id, ticker=query.ticker, company_name=query.company_name,
            started_at=started_at, duration_seconds=pipeline_run.duration_seconds,
            final_score=report.final_score, verdict=report.verdict,
            total_prompt_tokens=0, total_completion_tokens=0, total_cost_usd=0.0,
            agent_scores={n: o.overall_score for n, o in agent_outputs.items()},
            errors=errors,
        )
        log_run_api_usage(run_id, query.ticker, api_snapshot)
        log_analysis(
            report=report, run_id=run_id,
            duration_seconds=pipeline_run.duration_seconds,
            model=settings.LLM_MODEL, agent_outputs=agent_outputs,
        )
        logger.info(
            "[%s] Run %s done in %.1fs — verdict=%s score=%.3f",
            self.SECTOR_NAME, run_id, pipeline_run.duration_seconds,
            report.verdict, report.final_score,
        )
        return report

    # ------------------------------------------------------------------
    # RL learned weights
    # ------------------------------------------------------------------

    def _load_learned_weights(self, ticker: str) -> dict[str, float] | None:
        """Load RL-learned agent weights from WeightMemory. Falls back to None (→ settings defaults)."""
        try:
            from core.intelligence.rl.stores.prediction_store import PredictionStore
            ps = PredictionStore(ticker=ticker, sector=self.SECTOR_NAME)
            memory = ps.load_weight_memory()
            if memory and memory.current_weights and memory.weight_version > 0:
                weights = memory.effective_weights()
                logger.info(
                    "[%s] Using RL weights v%d for %s (%d adjustments)",
                    self.SECTOR_NAME, memory.weight_version, ticker, len(memory.weight_history),
                )
                return weights
        except Exception as exc:
            logger.debug("[%s] No RL weights for %s: %s", self.SECTOR_NAME, ticker, exc)
        return None

    def _get_default_weights(self) -> dict[str, float]:
        """Sector-specific default weights when no RL data exists. Override in sector subclasses."""
        return settings.AGENT_WEIGHTS

    # ------------------------------------------------------------------
    # Per-ticker aggregator weight scoping (RL knowledge layer)
    # ------------------------------------------------------------------

    def set_aggregator_weights(self, weights: dict[str, float], ticker: str) -> None:
        """Explicit injection (generate_forecast / daily_review). Pins weights to ticker."""
        self._aggregator_weights = weights
        self._aggregator_weights_ticker = ticker

    def _resolve_weights_for(self, ticker: str) -> None:
        """(Re)load learned weights when unset or when the ticker changed."""
        if self._aggregator_weights is None or self._aggregator_weights_ticker != ticker:
            learned = self._load_learned_weights(ticker)
            self._aggregator_weights = learned or self._get_default_weights()
            self._aggregator_weights_ticker = ticker

    # ------------------------------------------------------------------
    # NseIndiaApi pre-fetch (called before LangGraph fan-out)
    # ------------------------------------------------------------------

    def _prefetch_nse_data(self, query: StockQuery) -> None:
        """
        Fetch NseIndiaApi data and store in query.nse_data before fan-out.

        All 8 parallel agents read query.nse_data in their ContextBuilder calls.
        This method sets it once — agents never write to it (read-only sharing).
        Non-fatal: on any failure, query.nse_data stays empty and agents use Serper-only.
        """
        try:
            from services.data.fetchers.nse_announcements import prefetch_nse_data
            from services.data.stores.api_usage import record_call
            nse_result = prefetch_nse_data(query.ticker)
            query.nse_data.update(nse_result)
            if not nse_result.get("error"):
                record_call("nse_india")
        except Exception as exc:
            logger.warning(
                "[%s] NseIndiaApi prefetch failed for %s (non-fatal): %s",
                self.SECTOR_NAME, query.ticker, exc,
            )

    # ------------------------------------------------------------------
    # Ticker resolution
    # ------------------------------------------------------------------

    def _managed_tickers(self) -> set[str]:
        """
        Return this sector's managed ticker symbols (uppercased), cached on
        the instance. Lazy-imports `backend.sectors.{SECTOR_NAME}.config.settings`
        and reads its TICKERS list. Any failure (missing module, missing
        attribute, bad shape) yields an empty set — never raises.
        """
        cached = getattr(self, "_managed_tickers_cache", None)
        if cached is not None:
            return cached

        tickers: set[str] = set()
        try:
            import importlib
            mod = importlib.import_module(f"backend.sectors.{self.SECTOR_NAME}.config.settings")
            raw = getattr(mod, "TICKERS", None) or getattr(mod, "STOCKS", None) or []
            tickers = {str(t).strip().upper() for t in raw if str(t).strip()}
        except Exception as exc:
            logger.debug("[%s] _managed_tickers lookup failed: %s", self.SECTOR_NAME, exc)
            tickers = set()

        self._managed_tickers_cache = tickers
        return tickers

    def _yf_info(self, ticker: str) -> dict:
        """
        Fetch yfinance `.info` for a ticker, applying the same symbol-override
        and exchange-suffix logic used everywhere else. Any failure -> {}.
        """
        import yfinance as yf
        suffix = settings.YFINANCE_SUFFIX
        yf_ticker = settings.YF_SYMBOL_OVERRIDES.get(ticker.upper()) or (
            ticker if ticker.endswith(suffix) else f"{ticker}{suffix}"
        )
        return yf.Ticker(yf_ticker).info or {}

    def _company_name_for(self, ticker: str) -> str:
        """
        Best-effort company name lookup for an already-known managed ticker.

        Curated override / learned cache hit -> return immediately (no
        network). On a cache miss, fetch yfinance `.info` once and learn the
        result for next time. Falls back to the ticker itself on any failure.
        """
        cached = resolve_company_name(ticker)
        if cached:
            return cached
        try:
            info = self._yf_info(ticker)
            name = info.get("longName") or info.get("shortName")
            if name:
                learn_company_name(ticker, name)
                return name
            return ticker
        except Exception as exc:
            logger.debug("[%s] _company_name_for failed for %s: %s", self.SECTOR_NAME, ticker, exc)
            return ticker

    def _resolve_ticker(self, user_input: str, run_id: str = "") -> StockQuery:
        t0 = time.time()

        candidate = user_input.strip().upper()
        if candidate in self._managed_tickers():
            return StockQuery(
                ticker=candidate,
                company_name=self._company_name_for(candidate),
                exchange=settings.DEFAULT_EXCHANGE,
                analysis_date=date.today(),
            )

        def _llm_call(prompt: str) -> dict:
            response = self._llm.chat.completions.create(
                model=settings.LLM_MODEL,
                temperature=0.0,
                max_tokens=256,
                messages=[
                    {"role": "system", "content": P.SYSTEM_PROMPT},
                    {"role": "user",   "content": prompt},
                ],
                response_format={"type": "json_object"},
            )
            if response.usage:
                pt = response.usage.prompt_tokens
                ct = response.usage.completion_tokens
                cost = (pt * settings.LLM_INPUT_COST_PER_M + ct * settings.LLM_OUTPUT_COST_PER_M) / 1_000_000
                log_llm_call(
                    run_id=run_id, ticker=user_input.upper(), phase="ticker_resolution",
                    agent_name=None, model=settings.LLM_MODEL,
                    prompt_tokens=pt, completion_tokens=ct,
                    duration_ms=(time.time() - t0) * 1000, cost_usd=cost,
                )
            raw = response.choices[0].message.content or "{}"
            # Strip markdown code fences added by some models despite json_object format
            if raw.strip().startswith("```"):
                raw = re.sub(r"^```(?:json)?\s*", "", raw.strip())
                raw = re.sub(r"\s*```\s*$", "", raw).strip()
            return json.loads(raw)

        try:
            data = _llm_call(P.TICKER_RESOLUTION_PROMPT.format(user_input=user_input))
            ticker_candidate = data.get("ticker") or ""
            needs_fallback = not all([ticker_candidate, data.get("company_name"), data.get("exchange")])
            if not needs_fallback and ticker_candidate:
                needs_fallback = not self._verify_ticker(ticker_candidate)

            if needs_fallback:
                logger.info("[%s] Serper fallback for '%s'", self.SECTOR_NAME, user_input)
                from services.data.fetchers.news import search_serper
                results = search_serper(
                    f"{user_input} NSE BSE India stock ticker symbol listed company", n=3
                )
                if results:
                    snippets = "\n".join(f"- {r['title']}: {r['snippet']}" for r in results)
                    enriched = (
                        P.TICKER_RESOLUTION_PROMPT.format(user_input=user_input)
                        + f"\n\nWeb search results:\n{snippets}\n\n"
                        "Extract the exact NSE ticker from the results. Do NOT guess."
                    )
                    data = _llm_call(enriched)

            return StockQuery(
                ticker=data.get("ticker") or user_input.upper(),
                company_name=data.get("company_name") or user_input,
                exchange=data.get("exchange") or settings.DEFAULT_EXCHANGE,
                analysis_date=date.today(),
            )
        except Exception as exc:
            logger.warning("[%s] Ticker resolution failed: %s", self.SECTOR_NAME, exc)
            return StockQuery(
                ticker=user_input.upper(),
                company_name=user_input,
                exchange=settings.DEFAULT_EXCHANGE,
            )

    def _verify_ticker(self, ticker: str) -> bool:
        try:
            info = self._yf_info(ticker)
            return bool(
                info.get("regularMarketPrice") or info.get("currentPrice") or info.get("previousClose")
            )
        except Exception:
            return False

    # ------------------------------------------------------------------
    # Unified Sector Analyst (2026-06-12 redesign) — one bundle + one call
    # ------------------------------------------------------------------

    def _unified_enabled(self) -> bool:
        """
        True when this sector is on the unified-analyst path.

        Reads settings.UNIFIED_ANALYST_SECTORS freshly (via the settings
        module object held by this module) so tests can monkeypatch
        `base_orchestrator.settings.UNIFIED_ANALYST_SECTORS` directly.
        """
        sectors = {s.strip() for s in settings.UNIFIED_ANALYST_SECTORS.split(",") if s.strip()}
        return self.SECTOR_NAME in sectors

    def _run_unified(
        self,
        query: StockQuery,
        run_id: str = "",
        progress_callback: Callable[[str, float], None] | None = None,
    ) -> dict[str, AgentOutput]:
        """
        Unified path: one shared data bundle + one reasoning-model call
        produces all of this sector's dimension AgentOutputs.

        Returns {} (never raises) to signal the caller should fall back to
        the legacy worker pool when UNIFIED_ANALYST_FALLBACK_LEGACY is set.
        """
        from services.data.context.bundle_builder import build_sector_bundle
        from backend.shared.pipeline.unified_analyst import UnifiedAnalyst

        bundle = build_sector_bundle(query, self.SECTOR_NAME)
        logger.info(
            "[%s] unified bundle: api_calls=%s real_data=%s",
            self.SECTOR_NAME, bundle.api_calls_made, bundle.has_real_data,
        )
        outputs = UnifiedAnalyst().run(query, bundle, self.SECTOR_NAME)
        if outputs and progress_callback:
            for name, out in outputs.items():
                try:
                    progress_callback(name, out.overall_score)
                except Exception:
                    pass
        return outputs

    def _run_agents(
        self,
        query: StockQuery,
        run_id: str = "",
        progress_callback: Callable[[str, float], None] | None = None,
    ) -> dict[str, AgentOutput]:
        """
        Dispatch: unified path when enabled for this sector, legacy worker
        pool otherwise (or as a fallback on unified-analyst total failure).
        """
        if self._unified_enabled():
            outputs = self._run_unified(query, run_id, progress_callback)
            if outputs:
                return outputs
            if not settings.UNIFIED_ANALYST_FALLBACK_LEGACY:
                return outputs
            logger.warning("[%s] unified analyst failed -> legacy fallback", self.SECTOR_NAME)
        return self._run_via_graph(query, run_id=run_id, progress_callback=progress_callback)

    # ------------------------------------------------------------------
    # Parallel sub-agent execution — LangGraph worker pool
    # ------------------------------------------------------------------

    def _run_via_graph(
        self,
        query: StockQuery,
        run_id: str = "",
        progress_callback: Callable[[str, float], None] | None = None,
    ) -> dict[str, AgentOutput]:
        initial: GraphState = {
            "query": query, "run_id": run_id,
            "current_agent": "", "agent_outputs": {}, "rail_errors": [],
        }
        result = self._worker_pool_graph.invoke(initial)
        agent_outputs: dict[str, AgentOutput] = result.get("agent_outputs", {})
        for name, out in agent_outputs.items():
            logger.info("[%s] %s done — score=%.3f", self.SECTOR_NAME, name, out.overall_score)
            if progress_callback:
                try:
                    progress_callback(name, out.overall_score)
                except Exception:
                    pass
        return agent_outputs

    async def _run_via_graph_async(
        self,
        query: StockQuery,
        run_id: str = "",
        progress_callback: Callable[[str, float], None] | None = None,
    ) -> dict[str, AgentOutput]:
        initial: GraphState = {
            "query": query, "run_id": run_id,
            "current_agent": "", "agent_outputs": {}, "rail_errors": [],
        }
        collected: dict[str, AgentOutput] = {}
        async for event in self._worker_pool_graph.astream_events(initial, version="v2"):
            if event["event"] == "on_chain_end" and event["name"] == "run_agent":
                partial: dict = event["data"]["output"].get("agent_outputs", {})
                for name, out in partial.items():
                    collected[name] = out
                    logger.info(
                        "[%s] %s done (async) — score=%.3f",
                        self.SECTOR_NAME, name, out.overall_score,
                    )
                    if progress_callback:
                        try:
                            progress_callback(name, out.overall_score)
                        except Exception:
                            pass
        return collected

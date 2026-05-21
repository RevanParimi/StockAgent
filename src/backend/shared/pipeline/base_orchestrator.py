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

        if self._aggregator_weights is None:
            self._aggregator_weights = await asyncio.to_thread(
                self._load_learned_weights, query.ticker
            )

        pipeline_run = PipelineRun(run_id=run_id, query=query, status="running")
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

        if self._aggregator_weights is None:
            self._aggregator_weights = self._load_learned_weights(query.ticker)

        pipeline_run = PipelineRun(run_id=run_id, query=query, status="running")
        agent_outputs = self._run_via_graph(
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

    # ------------------------------------------------------------------
    # Ticker resolution
    # ------------------------------------------------------------------

    def _resolve_ticker(self, user_input: str, run_id: str = "") -> StockQuery:
        t0 = time.time()

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
            import yfinance as yf
            suffix = settings.YFINANCE_SUFFIX
            yf_ticker = ticker if ticker.endswith(suffix) else f"{ticker}{suffix}"
            info = yf.Ticker(yf_ticker).info or {}
            return bool(
                info.get("regularMarketPrice") or info.get("currentPrice") or info.get("previousClose")
            )
        except Exception:
            return False

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

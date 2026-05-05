"""
agents/orchestrator.py
=======================
Top-level Automobile Agent orchestrator.

Execution flow:
  1. Resolve ticker → company name via LLM
  2. Dispatch all 9 sub-agents IN PARALLEL via LangGraph worker pool (Send fan-out)
  3. Collect structured outputs (fan-in via state reducers)
  4. Pass to SignalAggregator
  5. Return FinalReport

The orchestrator is the only public-facing class in the pipeline.
Usage:
    from core.pipeline.orchestrator import AutomobileAgentOrchestrator
    report = AutomobileAgentOrchestrator().analyse("MARUTI")
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from collections.abc import Callable
from datetime import date, datetime, timezone

from langgraph.graph import END, START, StateGraph
try:
    from langgraph.types import RetryPolicy
except ImportError:
    from langgraph.pregel import RetryPolicy  # type: ignore[no-redef]

from core.graphs.nodes import make_dispatch_fn, make_run_agent_node
from core.graphs.state import GraphState

from core.config import settings
from core.schemas.pipeline import AgentOutput, FinalReport, PipelineRun, StockQuery
from core.config.prompts.shared import orchestrator as P
from services.clients.llm_client import get_llm_client
from services.data.stores.run_logger import log_llm_call, log_run_summary
from services.data.stores.analysis_logger import log_analysis
from services.data.stores.api_usage import log_run_api_usage, snapshot_usage

from core.sectors.automobile.sales_demand import SalesDemandAgent
from core.sectors.automobile.raw_materials import RawMaterialsAgent
from core.sectors.automobile.fundamentals import FundamentalsAgent
from core.sectors.automobile.pattern_analysis import PatternAnalysisAgent
from core.sectors.automobile.sentiment import SentimentAgent
from core.sectors.automobile.policy_regulatory import PolicyRegulatoryAgent
from core.sectors.automobile.competitive_intel import CompetitiveIntelAgent
from core.sectors.automobile.risk_macro import RiskMacroAgent
from core.sectors.automobile.valuation_catalyst import ValuationCatalystAgent
from core.pipeline.signal_aggregator import SignalAggregator

logger = logging.getLogger(__name__)


def _build_worker_pool_graph(agents: dict):
    """
    Compile a minimal LangGraph worker pool:
        START → [Send × N] → run_agent (parallel) → END

    No ticker resolution, input rail, or aggregation — the orchestrator
    handles those steps directly.  Built from the shared node factories so
    the same swarm-fallback and RetryPolicy logic applies as in sector graphs.

    agents_snapshot resolves the dict via .items() at build time so test mocks
    that configure .items() (not .keys() or __getitem__) are captured correctly.
    """
    agents_snapshot = dict(agents.items())
    _run_agent_node = make_run_agent_node(agents_snapshot, "automobile")
    _dispatch_fn = make_dispatch_fn(list(agents_snapshot.keys()))

    wf = StateGraph(GraphState)
    wf.add_node("run_agent", _run_agent_node, retry_policy=RetryPolicy(max_attempts=2))
    wf.add_conditional_edges(START, _dispatch_fn)
    wf.add_edge("run_agent", END)
    return wf.compile()


# All sub-agents instantiated once (they are stateless per .run() call)
_SUB_AGENTS = {
    "sales_demand":        SalesDemandAgent(),
    "raw_materials":       RawMaterialsAgent(),
    "fundamentals":        FundamentalsAgent(),
    "pattern_analysis":    PatternAnalysisAgent(),
    "sentiment":           SentimentAgent(),
    "policy_regulatory":   PolicyRegulatoryAgent(),
    "competitive_intel":   CompetitiveIntelAgent(),
    "risk_macro":          RiskMacroAgent(),
    "valuation_catalyst":  ValuationCatalystAgent(),
}


class AutomobileAgentOrchestrator:
    """
    Main entry point for the Automobile Agent system.

    Example
    -------
    >>> from core.pipeline.orchestrator import AutomobileAgentOrchestrator
    >>> report = AutomobileAgentOrchestrator().analyse("MARUTI")
    >>> print(report.verdict, report.final_score)
    """

    def __init__(self) -> None:
        self._llm = get_llm_client()
        self._aggregator = SignalAggregator()
        # Explicitly injected by generate_forecast.py / daily_review.py.
        # When None, analyse() auto-loads from RL WeightMemory for the resolved ticker.
        self._aggregator_weights: dict[str, float] | None = None
        # Worker pool graph — built here so test patches on _SUB_AGENTS take effect.
        self._worker_pool_graph = _build_worker_pool_graph(_SUB_AGENTS)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def analyse_async(
        self,
        user_input: str,
        progress_callback: Callable[[str, float], None] | None = None,
    ) -> FinalReport:
        """
        Async version of analyse().  Uses AsyncOpenAI for all agent LLM calls
        via asyncio.gather — no threads for LLM I/O, no GIL contention.

        Preferred entry point for FastAPI routes and WebSocket streaming.
        """
        run_id = str(uuid.uuid4())[:8]
        start = time.time()
        started_at = datetime.now(timezone.utc)
        api_snapshot = snapshot_usage()
        logger.info("[Orchestrator] Async run %s started for '%s'", run_id, user_input)

        # Ticker resolution is a single sync LLM call — offload to a thread
        # so the event loop isn't blocked.
        query = await asyncio.to_thread(self._resolve_ticker, user_input, run_id)
        logger.info("[Orchestrator] Resolved: %s → %s", user_input, query)

        # Auto-load RL learned weights unless a caller (generate_forecast / daily_review)
        # has already injected them via self._aggregator_weights.
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
            report=report,
            run_id=run_id,
            duration_seconds=pipeline_run.duration_seconds,
            model=settings.LLM_MODEL,
            agent_outputs=agent_outputs,
        )
        logger.info(
            "[Orchestrator] Async run %s complete in %.1fs – verdict=%s score=%.3f",
            run_id,
            pipeline_run.duration_seconds,
            report.verdict,
            report.final_score,
        )
        return report

    def analyse(
        self,
        user_input: str,
        progress_callback: Callable[[str, float], None] | None = None,
    ) -> FinalReport:
        """
        Analyse an Indian automobile stock end-to-end.

        Parameters
        ----------
        user_input : str
            Ticker symbol or company name, e.g. "MARUTI" or "Maruti Suzuki"
        progress_callback : callable, optional
            Called after each agent completes as ``callback(agent_name, score)``.
            Used by the FastAPI WebSocket route to stream live progress to clients.

        Returns
        -------
        FinalReport
        """
        run_id = str(uuid.uuid4())[:8]
        start = time.time()
        started_at = datetime.now(timezone.utc)
        api_snapshot = snapshot_usage()

        logger.info("[Orchestrator] Run %s started for '%s'", run_id, user_input)

        # Step 1: Resolve ticker
        query = self._resolve_ticker(user_input, run_id=run_id)
        logger.info("[Orchestrator] Resolved: %s → %s", user_input, query)

        # Auto-load RL learned weights unless already injected by caller.
        if self._aggregator_weights is None:
            self._aggregator_weights = self._load_learned_weights(query.ticker)

        pipeline_run = PipelineRun(run_id=run_id, query=query, status="running")

        # Step 2: Run all sub-agents in parallel via LangGraph worker pool
        agent_outputs = self._run_via_graph(
            query, run_id=run_id, progress_callback=progress_callback
        )

        # Step 3: Aggregate (pass learned weights if set by caller)
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
            report=report,
            run_id=run_id,
            duration_seconds=pipeline_run.duration_seconds,
            model=settings.LLM_MODEL,
            agent_outputs=agent_outputs,
        )
        logger.info(
            "[Orchestrator] Run %s complete in %.1fs – verdict=%s score=%.3f",
            run_id,
            pipeline_run.duration_seconds,
            report.verdict,
            report.final_score,
        )
        return report

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
            return json.loads(response.choices[0].message.content or "{}")

        try:
            # Attempt 1: LLM only
            data = _llm_call(P.TICKER_RESOLUTION_PROMPT.format(user_input=user_input))

            # Fire Serper fallback if:
            # (a) any core field is None — LLM had no idea, or
            # (b) resolved ticker fails yfinance verification — likely wrong symbol
            ticker_candidate = data.get("ticker") or ""
            needs_fallback = not all([ticker_candidate, data.get("company_name"), data.get("exchange")])
            if not needs_fallback and ticker_candidate:
                needs_fallback = not self._verify_ticker(ticker_candidate)

            if needs_fallback:
                logger.info(
                    "[Orchestrator] LLM couldn't resolve '%s' — trying Serper fallback",
                    user_input,
                )
                from services.data.fetchers.news import search_serper
                results = search_serper(
                    f"{user_input} NSE BSE India stock ticker symbol listed company",
                    n=3,
                )
                if results:
                    snippets = "\n".join(
                        f"- {r['title']}: {r['snippet']}" for r in results
                    )
                    enriched_prompt = (
                        P.TICKER_RESOLUTION_PROMPT.format(user_input=user_input)
                        + f"\n\nWeb search results for '{user_input} NSE ticker':\n{snippets}\n\n"
                        "IMPORTANT: Extract the exact NSE ticker symbol from the web results above "
                        "(e.g. if you see 'OLAELEC.NS' or 'OLAELEC' in any result, use OLAELEC). "
                        "Do NOT guess — use only what is explicitly visible in the web results."
                    )
                    # Attempt 2: LLM + Serper context
                    data = _llm_call(enriched_prompt)
                    logger.info("[Orchestrator] Serper-assisted resolution result: %s", data)

            return StockQuery(
                ticker=data.get("ticker") or user_input.upper(),
                company_name=data.get("company_name") or user_input,
                exchange=data.get("exchange") or settings.DEFAULT_EXCHANGE,
                analysis_date=date.today(),
            )

        except Exception as exc:
            logger.warning("[Orchestrator] Ticker resolution failed: %s", exc)
            return StockQuery(
                ticker=user_input.upper(),
                company_name=user_input,
                exchange=settings.DEFAULT_EXCHANGE,
            )

    def _load_learned_weights(self, ticker: str) -> dict[str, float] | None:
        """
        Load ticker-specific RL-learned agent weights from WeightMemory.

        Called automatically by analyse() / analyse_async() when no weights have
        been explicitly injected by generate_forecast.py or daily_review.py.
        Returns None (→ settings.AGENT_WEIGHTS fallback) if no WeightMemory
        exists yet or if loading fails for any reason.
        """
        try:
            from core.intelligence.rl.stores.prediction_store import PredictionStore
            ps = PredictionStore(ticker=ticker, sector="automobile")
            memory = ps.load_weight_memory()
            if memory and memory.current_weights and memory.weight_version > 0:
                weights = memory.effective_weights()
                logger.info(
                    "[Orchestrator] Using RL weights v%d for %s (learned over %d adj.)",
                    memory.weight_version, ticker, len(memory.weight_history),
                )
                return weights
        except Exception as exc:
            logger.debug("[Orchestrator] No RL weights for %s: %s", ticker, exc)
        return None

    def _verify_ticker(self, ticker: str) -> bool:
        """
        Quick yfinance check — returns True if the ticker is a valid listed symbol.
        Uses only .info (no price download) to stay fast and cheap.
        """
        try:
            import yfinance as yf
            suffix = settings.YFINANCE_SUFFIX  # ".NS"
            yf_ticker = ticker if ticker.endswith(suffix) else f"{ticker}{suffix}"
            info = yf.Ticker(yf_ticker).info or {}
            return bool(info.get("regularMarketPrice") or info.get("currentPrice") or info.get("previousClose"))
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
        """
        Run all agents in parallel using the LangGraph worker pool graph.
        Each agent is dispatched via Send fan-out; results are merged by the
        _merge_dicts reducer.  RetryPolicy(max_attempts=2) handles transient
        failures; swarm-style neutral fallback fires on persistent errors.

        progress_callback fires after all agents complete (sync path is used
        only by CLI/scheduler, not by the WebSocket route).
        """
        initial: GraphState = {
            "query":         query,
            "run_id":        run_id,
            "current_agent": "",
            "agent_outputs": {},
            "rail_errors":   [],
        }
        result = self._worker_pool_graph.invoke(initial)
        agent_outputs: dict[str, AgentOutput] = result.get("agent_outputs", {})
        for name, out in agent_outputs.items():
            logger.info("[Orchestrator] %s done – score=%.3f", name, out.overall_score)
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
        """
        Async version: streams events from the worker pool graph via
        astream_events so progress_callback fires as each agent completes —
        identical real-time behaviour to the previous asyncio.gather approach.

        Called from within the FastAPI event loop; put_nowait in the WebSocket
        progress_callback remains safe (no call_soon_threadsafe needed).
        """
        initial: GraphState = {
            "query":         query,
            "run_id":        run_id,
            "current_agent": "",
            "agent_outputs": {},
            "rail_errors":   [],
        }
        collected: dict[str, AgentOutput] = {}

        async for event in self._worker_pool_graph.astream_events(
            initial,
            version="v2",
        ):
            if event["event"] == "on_chain_end" and event["name"] == "run_agent":
                partial: dict = event["data"]["output"].get("agent_outputs", {})
                for name, out in partial.items():
                    collected[name] = out
                    logger.info(
                        "[Orchestrator] %s done (graph) – score=%.3f",
                        name, out.overall_score,
                    )
                    if progress_callback:
                        try:
                            progress_callback(name, out.overall_score)
                        except Exception:
                            pass

        return collected

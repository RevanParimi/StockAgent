"""
agents/orchestrator.py
=======================
Top-level Automobile Agent orchestrator.

Execution flow:
  1. Resolve ticker → company name via LLM
  2. Dispatch all 5 sub-agents IN PARALLEL using asyncio + ThreadPoolExecutor
  3. Collect structured outputs
  4. Pass to SignalAggregator
  5. Return FinalReport

The orchestrator is the only public-facing class in the pipeline.
Usage:
    from agents.orchestrator import AutomobileAgentOrchestrator
    report = AutomobileAgentOrchestrator().analyse("MARUTI")
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date

from openai import OpenAI

from config import settings
from models.schemas import AgentOutput, FinalReport, PipelineRun, StockQuery
from prompts import orchestrator as P

from agents.sales_demand import SalesDemandAgent
from agents.raw_materials import RawMaterialsAgent
from agents.fundamentals import FundamentalsAgent
from agents.pattern_analysis import PatternAnalysisAgent
from agents.sentiment import SentimentAgent
from agents.policy_regulatory import PolicyRegulatoryAgent
from agents.competitive_intel import CompetitiveIntelAgent
from agents.risk_macro import RiskMacroAgent
from agents.signal_aggregator import SignalAggregator

logger = logging.getLogger(__name__)

# All sub-agents instantiated once (they are stateless per .run() call)
_SUB_AGENTS = {
    "sales_demand":      SalesDemandAgent(),
    "raw_materials":     RawMaterialsAgent(),
    "fundamentals":      FundamentalsAgent(),
    "pattern_analysis":  PatternAnalysisAgent(),
    "sentiment":         SentimentAgent(),
    "policy_regulatory": PolicyRegulatoryAgent(),
    "competitive_intel": CompetitiveIntelAgent(),
    "risk_macro":        RiskMacroAgent(),
}


class AutomobileAgentOrchestrator:
    """
    Main entry point for the Automobile Agent system.

    Example
    -------
    >>> from agents.orchestrator import AutomobileAgentOrchestrator
    >>> report = AutomobileAgentOrchestrator().analyse("MARUTI")
    >>> print(report.verdict, report.final_score)
    """

    def __init__(self) -> None:
        self._llm = OpenAI(
            api_key=settings.OPENROUTER_API_KEY,
            base_url=settings.OPENROUTER_BASE_URL,
            timeout=settings.LLM_TIMEOUT_SECONDS,
        )
        self._aggregator = SignalAggregator()
        # Optional: set by generate_forecast.py / daily_review.py to inject
        # ticker-specific learned weights without mutating global settings.
        self._aggregator_weights: dict[str, float] | None = None

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
        logger.info("[Orchestrator] Async run %s started for '%s'", run_id, user_input)

        # Ticker resolution is a single sync LLM call — offload to a thread
        # so the event loop isn't blocked.
        query = await asyncio.to_thread(self._resolve_ticker, user_input)
        logger.info("[Orchestrator] Resolved: %s → %s", user_input, query)

        pipeline_run = PipelineRun(run_id=run_id, query=query, status="running")

        agent_outputs = await self._run_agents_parallel_async(
            query, progress_callback=progress_callback
        )

        report = self._aggregator.run(
            ticker=query.ticker,
            company_name=query.company_name,
            agent_outputs=agent_outputs,
            learned_weights=self._aggregator_weights,
        )

        pipeline_run.report = report
        pipeline_run.status = "completed"
        pipeline_run.duration_seconds = round(time.time() - start, 2)

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

        logger.info("[Orchestrator] Run %s started for '%s'", run_id, user_input)

        # Step 1: Resolve ticker
        query = self._resolve_ticker(user_input)
        logger.info("[Orchestrator] Resolved: %s → %s", user_input, query)

        pipeline_run = PipelineRun(run_id=run_id, query=query, status="running")

        # Step 2: Run all sub-agents in parallel
        agent_outputs = self._run_agents_parallel(query, progress_callback=progress_callback)

        # Step 3: Aggregate (pass learned weights if set by caller)
        report = self._aggregator.run(
            ticker=query.ticker,
            company_name=query.company_name,
            agent_outputs=agent_outputs,
            learned_weights=self._aggregator_weights,
        )

        pipeline_run.report = report
        pipeline_run.status = "completed"
        pipeline_run.duration_seconds = round(time.time() - start, 2)

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

    def _resolve_ticker(self, user_input: str) -> StockQuery:
        prompt = P.TICKER_RESOLUTION_PROMPT.format(user_input=user_input)
        try:
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
            data = json.loads(response.choices[0].message.content or "{}")
            return StockQuery(
                ticker=data.get("ticker", user_input.upper()),
                company_name=data.get("company_name", user_input),
                exchange=data.get("exchange", settings.DEFAULT_EXCHANGE),
                analysis_date=date.today(),
            )
        except Exception as exc:
            logger.warning("[Orchestrator] Ticker resolution failed: %s", exc)
            # Fallback: treat the input as a ticker directly
            return StockQuery(
                ticker=user_input.upper(),
                company_name=user_input,
                exchange=settings.DEFAULT_EXCHANGE,
            )

    # ------------------------------------------------------------------
    # Parallel sub-agent execution
    # ------------------------------------------------------------------

    def _run_agents_parallel(
        self,
        query: StockQuery,
        progress_callback: Callable[[str, float], None] | None = None,
    ) -> dict[str, AgentOutput]:
        results: dict[str, AgentOutput] = {}

        with ThreadPoolExecutor(max_workers=max(1, len(_SUB_AGENTS))) as pool:
            future_to_name = {
                pool.submit(agent.run, query): name
                for name, agent in _SUB_AGENTS.items()
            }
            for future in as_completed(
                future_to_name,
                timeout=settings.AGENT_TIMEOUT_SECONDS,
            ):
                name = future_to_name[future]
                try:
                    results[name] = future.result()
                    logger.info(
                        "[Orchestrator] %s done – score=%.3f",
                        name,
                        results[name].overall_score,
                    )
                except Exception as exc:
                    logger.error("[Orchestrator] %s failed: %s", name, exc)
                    # Inject a neutral placeholder so aggregation can still proceed
                    results[name] = AgentOutput(
                        agent=name,
                        ticker=query.ticker,
                        overall_score=0.5,
                        error=str(exc),
                        summary=f"Agent failed: {exc}",
                    )
                finally:
                    if progress_callback and name in results:
                        try:
                            progress_callback(name, results[name].overall_score)
                        except Exception:
                            pass  # never let a callback crash the pipeline

        return results

    async def _run_agents_parallel_async(
        self,
        query: StockQuery,
        progress_callback: Callable[[str, float], None] | None = None,
    ) -> dict[str, AgentOutput]:
        """
        Run all 8 agents concurrently with asyncio.gather + AsyncOpenAI.
        No threads for LLM calls — each await yields the event loop while
        waiting for the OpenRouter network response.
        """

        async def _run_one(name: str, agent) -> tuple[str, AgentOutput]:
            output = AgentOutput(
                agent=name, ticker=query.ticker, overall_score=0.5,
                error="did not complete", summary="Agent did not complete",
            )
            try:
                output = await asyncio.wait_for(
                    agent.run_async(query),
                    timeout=settings.AGENT_TIMEOUT_SECONDS,
                )
                logger.info(
                    "[Orchestrator] %s done (async) – score=%.3f",
                    name, output.overall_score,
                )
            except asyncio.TimeoutError:
                logger.error("[Orchestrator] %s timed out after %ss", name, settings.AGENT_TIMEOUT_SECONDS)
                output = AgentOutput(
                    agent=name, ticker=query.ticker, overall_score=0.5,
                    error="timeout", summary=f"Agent timed out after {settings.AGENT_TIMEOUT_SECONDS}s",
                )
            except Exception as exc:
                logger.error("[Orchestrator] %s failed: %s", name, exc)
                output = AgentOutput(
                    agent=name, ticker=query.ticker, overall_score=0.5,
                    error=str(exc), summary=f"Agent failed: {exc}",
                )
            if progress_callback:
                try:
                    progress_callback(name, output.overall_score)
                except Exception:
                    pass
            return name, output

        pairs = await asyncio.gather(
            *[_run_one(name, agent) for name, agent in _SUB_AGENTS.items()]
        )
        return dict(pairs)

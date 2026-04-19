"""
agents/orchestrator.py
=======================
Top-level Automobile Agent orchestrator.

Execution flow:
  1. Resolve ticker → company name via LLM
  2. Dispatch all 8 sub-agents IN PARALLEL using asyncio + ThreadPoolExecutor
  3. Collect structured outputs
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
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timezone

from config import settings
from core.schemas.pipeline import AgentOutput, FinalReport, PipelineRun, StockQuery
from config.prompts.shared import orchestrator as P
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
        started_at = datetime.now(timezone.utc)
        api_snapshot = snapshot_usage()
        logger.info("[Orchestrator] Async run %s started for '%s'", run_id, user_input)

        # Ticker resolution is a single sync LLM call — offload to a thread
        # so the event loop isn't blocked.
        query = await asyncio.to_thread(self._resolve_ticker, user_input, run_id)
        logger.info("[Orchestrator] Resolved: %s → %s", user_input, query)

        pipeline_run = PipelineRun(run_id=run_id, query=query, status="running")

        agent_outputs = await self._run_agents_parallel_async(
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

        pipeline_run = PipelineRun(run_id=run_id, query=query, status="running")

        # Step 2: Run all sub-agents in parallel
        agent_outputs = self._run_agents_parallel(
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
    # Parallel sub-agent execution
    # ------------------------------------------------------------------

    def _run_agents_parallel(
        self,
        query: StockQuery,
        run_id: str = "",
        progress_callback: Callable[[str, float], None] | None = None,
    ) -> dict[str, AgentOutput]:
        results: dict[str, AgentOutput] = {}

        with ThreadPoolExecutor(max_workers=max(1, len(_SUB_AGENTS))) as pool:
            future_to_name = {
                pool.submit(agent.run, query, run_id): name
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
        run_id: str = "",
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
                    agent.run_async(query, run_id),
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

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
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date

from groq import Groq

from config import settings
from models.schemas import AgentOutput, FinalReport, PipelineRun, StockQuery
from prompts import orchestrator as P

from agents.sales_demand import SalesDemandAgent
from agents.fundamentals import FundamentalsAgent
from agents.pattern_analysis import PatternAnalysisAgent
from agents.sentiment import SentimentAgent
from agents.risk_macro import RiskMacroAgent
from agents.signal_aggregator import SignalAggregator

logger = logging.getLogger(__name__)

# All five sub-agents instantiated once (they are stateless per .run() call)
_SUB_AGENTS = {
    "sales_demand":     SalesDemandAgent(),
    "fundamentals":     FundamentalsAgent(),
    "pattern_analysis": PatternAnalysisAgent(),
    "sentiment":        SentimentAgent(),
    "risk_macro":       RiskMacroAgent(),
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
        self._llm = Groq(
            api_key=settings.GROQ_API_KEY,
            timeout=settings.LLM_TIMEOUT_SECONDS,
        )
        self._aggregator = SignalAggregator()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def analyse(self, user_input: str) -> FinalReport:
        """
        Analyse an Indian automobile stock end-to-end.

        Parameters
        ----------
        user_input : str
            Ticker symbol or company name, e.g. "MARUTI" or "Maruti Suzuki"

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
        agent_outputs = self._run_agents_parallel(query)

        # Step 3: Aggregate
        report = self._aggregator.run(
            ticker=query.ticker,
            company_name=query.company_name,
            agent_outputs=agent_outputs,
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
        self, query: StockQuery
    ) -> dict[str, AgentOutput]:
        results: dict[str, AgentOutput] = {}

        with ThreadPoolExecutor(max_workers=len(_SUB_AGENTS)) as pool:
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

        return results

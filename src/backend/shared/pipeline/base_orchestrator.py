"""
src/backend/shared/pipeline/base_orchestrator.py
=================================================
Base class for the five analysis paths (automobile, banking_bfsi, it_sector,
renewable_energy, generic).

A path is a subclass that sets SECTOR_NAME (and, where it has its own, the
default weights). Everything else lives here: ticker resolution, the data
bundle and the one analysis call (unified_analyst.py), RL weight loading,
signal aggregation, the decision gate and logging.

When the analysis call scores no dimension there is no analysis: the run
raises AnalysisUnavailable (no_analysis.py) and writes no verdict. There is no
second method behind it (CLEAN-005 removed the per-analyst worker pool).

Usage (automobile path):
    from backend.shared.pipeline.base_orchestrator import BaseSectorOrchestrator
    class AutomobileAgentOrchestrator(BaseSectorOrchestrator):
        SECTOR_NAME = "automobile"
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import sqlite3
import time
import uuid
from abc import ABC, abstractmethod
from collections.abc import Callable
from datetime import date, datetime, timezone

from backend.shared.config import settings
from backend.shared.schemas.pipeline import AgentOutput, FinalReport, PipelineRun, StockQuery
from backend.shared.prompts import orchestrator as P
from backend.shared.clients.llm_client import get_llm_client
from services.clients.llm_client import JSON_MODE_EXTRA_BODY
from backend.shared.data.fetchers.symbol_resolver import learn_company_name, resolve_company_name
from backend.shared.data.stores.run_logger import log_llm_call, log_run_summary
from services.data.stores.log_store import run_context, set_run_ticker
from backend.shared.data.stores.analysis_logger import log_analysis
from backend.shared.data.stores.api_usage import log_run_api_usage, snapshot_usage
from backend.shared.pipeline.no_analysis import AnalysisUnavailable, scored_nothing, why_nothing
from backend.shared.pipeline.signal_aggregator import SignalAggregator

logger = logging.getLogger(__name__)


def sum_run_usage(
    agent_outputs: dict[str, AgentOutput],
    resolve_usage: tuple[int, int],
    aggregator: object,
) -> tuple[int, int, float]:
    """Run totals for log_run_summary (AUD-087): agents + ticker-resolve + aggregator."""
    pt = sum(o.prompt_tokens for o in agent_outputs.values())
    ct = sum(o.completion_tokens for o in agent_outputs.values())
    cost = sum(o.cost_usd for o in agent_outputs.values())
    resolve_pt, resolve_ct = resolve_usage
    agg_pt = getattr(aggregator, "_last_prompt_tokens", 0)
    agg_ct = getattr(aggregator, "_last_completion_tokens", 0)
    # AUD-105: resolve runs on BULK, the aggregator on REASONING — cost each at its rate.
    cost += settings.llm_cost_usd(settings.LLM_MODEL_BULK, resolve_pt, resolve_ct)
    cost += settings.llm_cost_usd(settings.LLM_MODEL_REASONING, agg_pt, agg_ct)
    return pt + resolve_pt + agg_pt, ct + resolve_ct + agg_ct, round(cost, 6)


class BaseSectorOrchestrator(ABC):
    """
    Sector-agnostic orchestrator base. A subclass sets SECTOR_NAME (str), the
    key of its spec in unified_analyst.SECTOR_SPECS. A name without a spec
    gets no analysis (the analyst returns nothing), never another method.
    """

    SECTOR_NAME: str = "unknown"

    def __init__(self) -> None:
        self._llm = get_llm_client()
        self._aggregator = SignalAggregator()
        # Set by generate_forecast.py / daily_review.py; else auto-loaded from RL WeightMemory.
        self._aggregator_weights: dict[str, float] | None = None
        # Ticker that _aggregator_weights was resolved/injected for — drives per-ticker
        # weight scoping so a long-lived orchestrator instance reloads weights when
        # the ticker changes between analyse()/analyse_async() calls.
        self._aggregator_weights_ticker: str | None = None
        # B2: the health record for the run in flight, attached to the report
        # once the aggregator has one. Reset per run — an orchestrator instance
        # is long-lived, and a stale record on the next report would be a lie.
        self._last_data_health: dict | None = None
        # SA-003: what the decision gate is computed from — the unified run's
        # section statuses and dimension counts. None means no bundle was
        # described, which the gate treats as unverified.
        self._last_gate_inputs: dict | None = None
        # FIX-026: the deep dive's sector question for the run in flight, and
        # the analysis's answer to it (unvalidated). Reset per run.
        self._sector_question: str | None = None
        self._last_sector_answer = None
        # CLEAN-005: why the unified analyst returned nothing, for the run in
        # flight. Reset per run.
        self._last_analyst_failure: str | None = None

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
        # E1: everything this run logs at WARNING+ is stamped with the run id,
        # so a degradation can be traced back to the verdict it damaged. The
        # ticker is named below, once resolution has actually produced one.
        with run_context(run_id):
            start = time.time()
            started_at = datetime.now(timezone.utc)
            api_snapshot = snapshot_usage()
            self._last_data_health = None
            self._last_gate_inputs = None
            self._sector_question = None
            self._last_sector_answer = None
            self._last_analyst_failure = None
            logger.info("[%s] Async run %s started for '%s'", self.SECTOR_NAME, run_id, user_input)

            query = await asyncio.to_thread(self._resolve_ticker, user_input, run_id)
            set_run_ticker(query.ticker)
            logger.info("[%s] Resolved: %s -> %s", self.SECTOR_NAME, user_input, query)

            if self._aggregator_weights is None or self._aggregator_weights_ticker != query.ticker:
                learned = await asyncio.to_thread(self._load_learned_weights, query.ticker)
                self._aggregator_weights = learned or self._get_default_weights()
                self._aggregator_weights_ticker = query.ticker

            # Pre-fetch NseIndiaApi data before the bundle — NSE() is sync, run in thread.
            await asyncio.to_thread(self._prefetch_nse_data, query)

            pipeline_run = PipelineRun(run_id=run_id, query=query, status="running")
            agent_outputs = await asyncio.to_thread(
                self._run_agents, query, run_id, progress_callback
            )
            # CLEAN-005: a run that scored nothing is no analysis.
            if scored_nothing(agent_outputs):
                self._no_analysis(query, run_id, agent_outputs, api_snapshot)

            report = self._aggregator.run(
                ticker=query.ticker,
                company_name=query.company_name,
                agent_outputs=agent_outputs,
                learned_weights=self._aggregator_weights,
                run_id=run_id,
                sector=self.SECTOR_NAME,
            )

            # B2: the run's health record travels with its verdict.
            report.data_health = self._last_data_health
            # SA-003: the decision gate, before anything logs or returns the verdict.
            self._apply_decision_gate(report, query.ticker, run_id)

            pipeline_run.report = report
            pipeline_run.status = "completed"
            pipeline_run.duration_seconds = round(time.time() - start, 2)

            errors = [f"{n}: {o.error}" for n, o in agent_outputs.items() if o.error]
            total_pt, total_ct, total_cost = sum_run_usage(
                agent_outputs, getattr(self, "_last_resolve_usage", (0, 0)), self._aggregator
            )
            log_run_summary(
                run_id=run_id, ticker=query.ticker, company_name=query.company_name,
                started_at=started_at, duration_seconds=pipeline_run.duration_seconds,
                final_score=report.final_score, verdict=report.verdict,
                total_prompt_tokens=total_pt, total_completion_tokens=total_ct,
                total_cost_usd=total_cost,
                agent_scores={n: o.overall_score for n, o in agent_outputs.items()},
                errors=errors,
            )
            self._record_score_history(report)
            log_run_api_usage(run_id, query.ticker, api_snapshot)
            log_analysis(
                report=report, run_id=run_id,
                duration_seconds=pipeline_run.duration_seconds,
                model=settings.LLM_MODEL_BULK, agent_outputs=agent_outputs,
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
        *,
        sector_question: str | None = None,
    ) -> FinalReport:
        """Sync end-to-end analysis. Used by CLI and scheduler.

        `sector_question` (the discovery deep dive's, FIX-026) rides in the
        unified analyst's one call, no extra call; the answer comes back as
        `report.sector_answer`, unvalidated."""
        run_id = str(uuid.uuid4())[:8]
        # E1: everything this run logs at WARNING+ is stamped with the run id,
        # so a degradation can be traced back to the verdict it damaged. The
        # ticker is named below, once resolution has actually produced one.
        with run_context(run_id):
            start = time.time()
            started_at = datetime.now(timezone.utc)
            api_snapshot = snapshot_usage()
            self._last_data_health = None
            self._last_gate_inputs = None
            self._sector_question = sector_question
            self._last_sector_answer = None
            self._last_analyst_failure = None
            logger.info("[%s] Run %s started for '%s'", self.SECTOR_NAME, run_id, user_input)

            query = self._resolve_ticker(user_input, run_id=run_id)
            set_run_ticker(query.ticker)
            logger.info("[%s] Resolved: %s -> %s", self.SECTOR_NAME, user_input, query)

            self._resolve_weights_for(query.ticker)

            # Pre-fetch NseIndiaApi data before the bundle — one session, three calls, 0.5s sleep each.
            self._prefetch_nse_data(query)

            pipeline_run = PipelineRun(run_id=run_id, query=query, status="running")
            agent_outputs = self._run_agents(
                query, run_id=run_id, progress_callback=progress_callback
            )
            # CLEAN-005: a run that scored nothing is no analysis.
            if scored_nothing(agent_outputs):
                self._no_analysis(query, run_id, agent_outputs, api_snapshot)

            report = self._aggregator.run(
                ticker=query.ticker,
                company_name=query.company_name,
                agent_outputs=agent_outputs,
                learned_weights=self._aggregator_weights,
                run_id=run_id,
                sector=self.SECTOR_NAME,
            )

            # B2: the run's health record travels with its verdict.
            report.data_health = self._last_data_health
            # FIX-026: the sector answer, None unless a question was asked and
            # the unified call answered it.
            report.sector_answer = self._last_sector_answer
            # SA-003: the decision gate, before anything logs or returns the verdict.
            self._apply_decision_gate(report, query.ticker, run_id)

            pipeline_run.report = report
            pipeline_run.status = "completed"
            pipeline_run.duration_seconds = round(time.time() - start, 2)

            errors = [f"{n}: {o.error}" for n, o in agent_outputs.items() if o.error]
            total_pt, total_ct, total_cost = sum_run_usage(
                agent_outputs, getattr(self, "_last_resolve_usage", (0, 0)), self._aggregator
            )
            log_run_summary(
                run_id=run_id, ticker=query.ticker, company_name=query.company_name,
                started_at=started_at, duration_seconds=pipeline_run.duration_seconds,
                final_score=report.final_score, verdict=report.verdict,
                total_prompt_tokens=total_pt, total_completion_tokens=total_ct,
                total_cost_usd=total_cost,
                agent_scores={n: o.overall_score for n, o in agent_outputs.items()},
                errors=errors,
            )
            self._record_score_history(report)
            log_run_api_usage(run_id, query.ticker, api_snapshot)
            log_analysis(
                report=report, run_id=run_id,
                duration_seconds=pipeline_run.duration_seconds,
                model=settings.LLM_MODEL_BULK, agent_outputs=agent_outputs,
            )
            logger.info(
                "[%s] Run %s done in %.1fs — verdict=%s score=%.3f",
                self.SECTOR_NAME, run_id, pipeline_run.duration_seconds,
                report.verdict, report.final_score,
            )
            return report

    def _no_analysis(
        self,
        query: StockQuery,
        run_id: str,
        agent_outputs: dict[str, AgentOutput],
        api_snapshot,
    ) -> None:
        """
        CLEAN-005: the run scored no dimension, so there is no analysis.

        Records the failure (the day's count on GET /scheduler/status), logs
        it once and raises AnalysisUnavailable. Nothing a verdict feeds is
        written: no aggregator call, no score-history row, no analysis log,
        no run summary. The run's data-health row (written by
        _record_data_health) and its API spend stay on record.
        """
        reason = why_nothing(agent_outputs, self._last_analyst_failure)
        try:
            from services.data.stores.analysis_failures import record_analysis_failure
            record_analysis_failure(self.SECTOR_NAME, query.ticker, reason, run_id=run_id)
        except Exception as exc:
            logger.warning("[%s] analysis failure not recorded (non-fatal): %s",
                           self.SECTOR_NAME, exc, exc_info=True)
        try:
            log_run_api_usage(run_id, query.ticker, api_snapshot)
        except Exception as exc:
            logger.warning("[%s] API usage not logged for failed run %s (non-fatal): %s",
                           self.SECTOR_NAME, run_id, exc, exc_info=True)
        logger.warning(
            "[%s] No analysis for %s today (run %s): %s. No verdict or score; "
            "the stock is skipped by this run's caller.",
            self.SECTOR_NAME, query.ticker, run_id, reason,
        )
        raise AnalysisUnavailable(query.ticker, self.SECTOR_NAME, reason, run_id=run_id)

    def _record_score_history(self, report: FinalReport) -> None:
        """One score-history row per completed analysis, with the verdict the
        run returns (after the decision gate).

        Member screens read it: dated scores on Home and the watchlist, the
        verdict changes on Portfolio, and the chat's current verdicts. Every
        entry point (the 16:30 review, the monthly forecast, discovery deep
        dives, /analyse, the stream and the chat) ends here, so this is the one
        writer. A failed write is a warning; it never fails the analysis."""
        from services.data.stores.score_store import ScoreStore
        try:
            ScoreStore().save(report)
        # The store's own failures, and a report that will not serialize
        # (pydantic's serialization error is a ValueError).
        except (sqlite3.Error, OSError, ValueError, TypeError) as exc:
            logger.warning("[%s] score history not written for %s: %s",
                           self.SECTOR_NAME, report.ticker, exc, exc_info=True)

    # ------------------------------------------------------------------
    # RL learned weights
    # ------------------------------------------------------------------

    def _load_learned_weights(self, ticker: str) -> dict[str, float] | None:
        """Load RL-learned agent weights from WeightMemory. Falls back to None (→ settings defaults).

        SA-039: in observe mode nothing learned is used — None, so callers
        aggregate with this sector's _get_default_weights().
        """
        try:
            from core.intelligence.rl.learning_mode import learning_mode, OBSERVE
            if learning_mode() == OBSERVE:
                logger.info(
                    "[%s] learning_mode=observe — %s aggregates with sector default weights",
                    self.SECTOR_NAME, ticker,
                )
                return None
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
    # NseIndiaApi pre-fetch (called before the data bundle is built)
    # ------------------------------------------------------------------

    def _prefetch_nse_data(self, query: StockQuery) -> None:
        """
        Fetch NseIndiaApi data and store in query.nse_data before the bundle.

        The data bundle reads query.nse_data; this method sets it once and
        nothing writes to it afterwards.
        Non-fatal: on any failure, query.nse_data stays empty and the bundle uses Serper only.
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
                self.SECTOR_NAME, query.ticker, exc, exc_info=True,
            )

    # ------------------------------------------------------------------
    # Ticker resolution
    # ------------------------------------------------------------------

    def _managed_tickers(self) -> set[str]:
        """
        Return this sector's static TICKERS setting (uppercased), cached on
        the instance. Lazy-imports `backend.sectors.{SECTOR_NAME}.config.settings`
        and reads its TICKERS list. Any failure (missing module, missing
        attribute, bad shape) yields an empty set — never raises.

        Most production-managed tickers are not in it; _tracked_tickers holds
        those (FIX-002).
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

    def _tracked_tickers(self) -> set[str]:
        """
        FIX-002: every ticker the app already tracks under its own code, in
        any sector — each managed-list entry (data/managed_tickers.json,
        enabled or not) and each instrument-registry record. Read on every
        call, so a ticker the owner adds is known at once; both reads are
        read-only and never raise.

        Before this, a managed ticker missing from its sector's TICKERS went
        to the LLM: on 1 Oct the monthly forecast for TATAELXSI analysed
        TATAMOTORS. A retired or unresolved ticker resolves to itself too;
        SA-008's identity gate decides whether it may act.
        """
        from backend.shared.data.instruments import recorded_tickers
        from services.api.log_buffer import managed_symbols
        return managed_symbols() | recorded_tickers()

    def _yf_info(self, ticker: str) -> dict:
        """
        Fetch yfinance `.info` for a ticker, applying the same symbol-override
        and exchange-suffix logic used everywhere else. Any failure -> {}.

        Only the instrument registry's symbol or the naive listing: never the
        learned symbol cache (a fuzzy match must not name the company).
        """
        import yfinance as yf
        from backend.shared.data.instruments import registry_identity
        suffix = settings.YFINANCE_SUFFIX
        registered = registry_identity(ticker, date.today())
        yf_ticker = registered.symbol if registered is not None else (
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
        self._last_resolve_usage = (0, 0)  # AUD-087: reset per run

        candidate = user_input.strip().upper()
        if candidate in self._managed_tickers() or candidate in self._tracked_tickers():
            return StockQuery(
                ticker=candidate,
                company_name=self._company_name_for(candidate),
                exchange=settings.DEFAULT_EXCHANGE,
                analysis_date=date.today(),
            )

        def _llm_call(prompt: str) -> dict:
            response = self._llm.chat.completions.create(
                model=settings.LLM_MODEL_BULK,
                temperature=0.0,
                max_tokens=256,
                messages=[
                    {"role": "system", "content": P.SYSTEM_PROMPT},
                    {"role": "user",   "content": prompt},
                ],
                response_format={"type": "json_object"},
                extra_body=JSON_MODE_EXTRA_BODY,
            )
            if response.usage:
                pt = response.usage.prompt_tokens
                ct = response.usage.completion_tokens
                self._last_resolve_usage = (pt, ct)  # AUD-087
                cost = settings.llm_cost_usd(settings.LLM_MODEL_BULK, pt, ct)
                log_llm_call(
                    run_id=run_id, ticker=user_input.upper(), phase="ticker_resolution",
                    agent_name=None, model=settings.LLM_MODEL_BULK,
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
            logger.warning("[%s] Ticker resolution failed: %s",
                           self.SECTOR_NAME, exc, exc_info=True)
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

    def _run_unified(
        self,
        query: StockQuery,
        run_id: str = "",
        progress_callback: Callable[[str, float], None] | None = None,
    ) -> dict[str, AgentOutput]:
        """
        One shared data bundle + one reasoning-model call produces all of
        this sector's dimension AgentOutputs.

        Returns {} (never raises) when the call produced nothing; the analyst
        says why in `_last_failure`, kept for the "no analysis" record.
        """
        from services.data.context.bundle_builder import build_sector_bundle
        from backend.shared.pipeline.unified_analyst import UnifiedAnalyst

        bundle = build_sector_bundle(query, self.SECTOR_NAME)
        logger.info(
            "[%s] unified bundle: api_calls=%s real_data=%s",
            self.SECTOR_NAME, bundle.api_calls_made, bundle.has_real_data,
        )
        analyst = UnifiedAnalyst()
        question = getattr(self, "_sector_question", None)
        if question:
            outputs = analyst.run(query, bundle, self.SECTOR_NAME, run_id=run_id,
                                  sector_question=question)
            self._last_sector_answer = analyst._last_sector_answer
        else:
            outputs = analyst.run(query, bundle, self.SECTOR_NAME, run_id=run_id)
        if not outputs:
            self._last_analyst_failure = getattr(analyst, "_last_failure", None)
        self._record_data_health(query, bundle, outputs, run_id)
        self._shadow_company_search(query, bundle, outputs, run_id)
        if outputs:
            # AUD-087: one LLM call produced all outputs — stamp totals on one
            # output so sum_run_usage() over the dict counts them exactly once.
            first = next(iter(outputs.values()))
            first.prompt_tokens = analyst._last_prompt_tokens
            first.completion_tokens = analyst._last_completion_tokens
            first.cost_usd = settings.llm_cost_usd(
                settings.LLM_MODEL_REASONING,
                analyst._last_prompt_tokens, analyst._last_completion_tokens,
            )
        if outputs and progress_callback:
            for name, out in outputs.items():
                try:
                    progress_callback(name, out.overall_score)
                except Exception:
                    pass
        return outputs

    def _shadow_company_search(
        self,
        query: StockQuery,
        bundle,
        outputs: dict[str, AgentOutput],
        run_id: str,
    ) -> None:
        """
        PR-043: queue the search shadow (the engines in search_shadow.engines
        beside Serper) for this run's company search. Called after the analyst
        has returned, and only when it scored a dimension: a failed analysis
        is no decision. The work runs on a daemon thread and the analysis reads
        nothing from it.

        Never raises, and never changes the run's outcome.
        """
        if scored_nothing(outputs):     # CLEAN-005: no analysis is no decision
            return
        try:
            from services.data.fetchers.search_shadow import submit_shadow

            submit_shadow(
                run_id=run_id,
                ticker=query.ticker,
                sector=self.SECTOR_NAME,
                company_search=getattr(bundle, "company_search", None),
                section_status=(getattr(bundle, "section_status", None) or {}).get("company_news"),
            )
        except Exception as exc:
            logger.warning("[%s] search shadow not queued (non-fatal): %s",
                           self.SECTOR_NAME, exc, exc_info=True)

    def _record_data_health(
        self,
        query: StockQuery,
        bundle,
        outputs: dict[str, AgentOutput],
        run_id: str,
    ) -> None:
        """
        B2: write one row saying what this run actually received.

        Called after the analyst returns and BEFORE the `if outputs:` branch,
        so the total-failure case (`outputs == {}`) — the one most worth a
        record — produces a row like any other run. A dimension counts as
        missing when its output carries an `error`, which is the same test
        `SignalAggregator` uses to exclude it from the composite; the two
        numbers are meant to agree.

        Never raises, and never changes the run's outcome.

        SA-003: the same section statuses and dimension counts are kept as the
        decision gate's inputs before the row is written, so the gate does not
        depend on the row being recorded (the observability flag is only the
        row's rollback line).
        """
        self._last_data_health = None
        try:
            from services.data.stores.data_health import record_data_health
            from backend.shared.pipeline.unified_analyst import DIMENSIONS

            expected = list(DIMENSIONS.get(self.SECTOR_NAME) or outputs.keys())
            if outputs:
                missing = [n for n, o in outputs.items() if o.error]
            else:
                # The analyst returned nothing: every dimension is missing.
                missing = list(expected)
            self._last_gate_inputs = {
                "section_status": dict(getattr(bundle, "section_status", None) or {}),
                "section_provenance": getattr(bundle, "section_provenance", None),
                "dimensions_expected": expected,
                "dimensions_missing": missing,
            }
            self._last_data_health = record_data_health(
                run_id=run_id,
                ticker=query.ticker,
                sector=self.SECTOR_NAME,
                section_status=getattr(bundle, "section_status", None),
                api_calls=getattr(bundle, "api_calls_made", None),
                dimensions_expected=expected,
                dimensions_missing=missing,
                section_provenance=getattr(bundle, "section_provenance", None),
            )
        except Exception as exc:
            logger.warning("[%s] data_health record failed (non-fatal): %s",
                           self.SECTOR_NAME, exc, exc_info=True)

    def _apply_decision_gate(self, report: FinalReport, ticker: str, run_id: str) -> None:
        """
        SA-003: attach the decision gate to the report. In enforce mode an
        abstaining gate withholds the verdict (INSUFFICIENT DATA). Every
        abstention is recorded with its reasons and this run id, in both modes.

        Never raises. If the gate itself cannot be computed, the run abstains:
        an analysis nobody could check is not evidence.

        SA-008: the ticker's identity for today joins the gate. An unresolved
        identity, or price history fetched for another symbol, abstains.
        """
        from backend.shared.pipeline import decision_gate as dg
        from backend.shared.data.fetchers.symbol_resolver import resolve_identity
        try:
            inputs = self._last_gate_inputs
            if inputs is None:
                gate = dg.no_provenance_gate(
                    run_id, "no structured provenance: this run's data bundle was "
                            "not described, so its inputs cannot be checked")
            else:
                gate = dg.assess_analysis(run_id=run_id, **inputs)
            provenance = (inputs or {}).get("section_provenance") or {}
            price_symbol = (provenance.get("technicals") or {}).get("symbol")
            dg.apply_identity(gate, resolve_identity(ticker, date.today()), price_symbol)
        except Exception as exc:
            logger.error("[%s] decision gate failed for %s — abstaining: %s",
                         self.SECTOR_NAME, ticker, exc, exc_info=True)
            gate = dg.no_provenance_gate(
                run_id, f"decision gate evaluation failed: {type(exc).__name__}")
        try:
            dg.apply_gate(report, gate)
            if gate.status == dg.ABSTAIN:
                dg.record_gate_decision(
                    consumer="analysis", ticker=ticker,
                    skipped=f"actionable verdict {gate.withheld_verdict or report.verdict}",
                    status=gate.status, reasons=gate.reasons, run_id=run_id,
                    enforced=gate.enforced, on_date=date.today().isoformat(),
                    extra={"sector": self.SECTOR_NAME},
                )
        except Exception as exc:
            logger.error("[%s] decision gate could not be applied for %s: %s",
                         self.SECTOR_NAME, ticker, exc, exc_info=True)

    def _run_agents(
        self,
        query: StockQuery,
        run_id: str = "",
        progress_callback: Callable[[str, float], None] | None = None,
    ) -> dict[str, AgentOutput]:
        """The one analysis method: one bundle and one call (CLEAN-005: no
        per-sector switch and no backup). An empty or wholly errored result
        is "no analysis" (analyse / analyse_async raise AnalysisUnavailable)."""
        return self._run_unified(query, run_id, progress_callback)

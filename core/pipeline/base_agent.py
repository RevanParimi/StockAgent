"""
agents/base_agent.py
====================
Base class shared by all five sub-agents.

Responsibilities:
  - OpenRouter LLM client initialisation (openai-compatible SDK)
  - Retry logic with exponential back-off
  - JSON response parsing and validation
  - Structured logging
  - Context assembly from search results (stub for RAG)
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from abc import ABC, abstractmethod
from typing import Any

from openai import APIError, APITimeoutError, RateLimitError

from core.config import settings
from core.schemas.pipeline import AgentOutput, StockQuery
from services.clients.llm_client import get_llm_client, get_async_llm_client
from services.data.stores.run_logger import log_llm_call

logger = logging.getLogger(__name__)

# Appended to every system prompt when real data is available.
# Prevents the LLM from filling gaps with training-knowledge hallucinations.
_DATA_ONLY_INSTRUCTION = (
    "\n\nCRITICAL: Score ONLY from the context data provided. "
    "Do NOT use your training knowledge to fill any gaps. "
    "If a sub-score dimension has no data in the context, return 0.5 for that dimension "
    "and add 'no real-time data for this dimension' to key_risks. "
    "Fabricating facts from training knowledge is strictly prohibited."
)


def _date_instruction() -> str:
    """
    Returns a date-awareness block injected into every agent system prompt.
    Converts a runtime today's date so the LLM knows exactly what is fresh.
    """
    from datetime import date
    today = date.today().isoformat()
    return (
        f"\n\nDATA FRESHNESS RULES (today is {today}):\n"
        "Every news/search result in the context has a [Date: YYYY-MM-DD] tag.\n"
        "RULE 1: When two results contradict each other, trust the one with the more recent date.\n"
        "RULE 2: Any result with a date older than 14 days — use as background context only, "
        "not as primary evidence for scoring.\n"
        "RULE 3: Set data_freshness in your output to the date of the most recent result you used."
    )


class BaseAgent(ABC):
    """
    Abstract base for all Automobile Agent sub-agents.

    Subclasses must implement:
        - `agent_name`  property (str)
        - `_build_prompt(query, context)` -> (system_prompt, user_prompt)
        - `_parse_output(raw_json, ticker)` -> AgentOutput subclass
    """

    def __init__(self) -> None:
        self._client = get_llm_client()
        # Async client created lazily — avoids instantiation in sync-only test paths.
        self._async_client = None
        # Populated by LLM call methods; read by run()/run_async() for logging.
        self._last_usage: dict[str, int] = {"prompt_tokens": 0, "completion_tokens": 0}

    def _get_async_client(self):
        if self._async_client is None:
            self._async_client = get_async_llm_client()
        return self._async_client

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def run(self, query: StockQuery, run_id: str = "") -> AgentOutput:
        """
        Synchronous entry point.  Used by CLI, scheduler, and sync tests.
        """
        logger.info("[%s] Starting analysis for %s", self.agent_name, query.ticker)
        context, has_real_data = self._gather_context(query)
        if not has_real_data:
            logger.warning(
                "[%s] No real-time data for %s — skipping LLM, returning neutral 0.5",
                self.agent_name, query.ticker,
            )
            return self._no_data_output(query.ticker)
        system_prompt, user_prompt = self._build_prompt(query, context)
        system_prompt += _DATA_ONLY_INSTRUCTION + _date_instruction()
        t0 = time.time()
        raw = self._call_llm_with_retry(system_prompt, user_prompt)
        duration_ms = (time.time() - t0) * 1000
        output = self._safe_parse(raw, query.ticker)

        pt = self._last_usage["prompt_tokens"]
        ct = self._last_usage["completion_tokens"]
        cost = (pt * settings.LLM_INPUT_COST_PER_M + ct * settings.LLM_OUTPUT_COST_PER_M) / 1_000_000
        log_llm_call(
            run_id=run_id, ticker=query.ticker, phase="agent",
            agent_name=self.agent_name, model=settings.LLM_MODEL,
            prompt_tokens=pt, completion_tokens=ct,
            duration_ms=duration_ms, cost_usd=cost,
            score=output.overall_score, error=output.error,
        )
        logger.info(
            "[%s] Done – score=%.3f tokens=%d cost=$%.5f",
            self.agent_name, output.overall_score, pt + ct, cost,
        )
        return output

    async def run_async(self, query: StockQuery, run_id: str = "") -> AgentOutput:
        """
        Async entry point.  Uses AsyncOpenAI — no threads for LLM I/O.
        Context gathering (yfinance / news APIs) is offloaded via asyncio.to_thread
        since those libraries are synchronous.
        """
        logger.info("[%s] Starting async analysis for %s", self.agent_name, query.ticker)
        context, has_real_data = await asyncio.to_thread(self._gather_context, query)
        if not has_real_data:
            logger.warning(
                "[%s] No real-time data for %s — skipping LLM, returning neutral 0.5",
                self.agent_name, query.ticker,
            )
            return self._no_data_output(query.ticker)
        system_prompt, user_prompt = self._build_prompt(query, context)
        system_prompt += _DATA_ONLY_INSTRUCTION + _date_instruction()
        t0 = time.time()
        raw = await self._call_llm_async(system_prompt, user_prompt)
        duration_ms = (time.time() - t0) * 1000
        output = self._safe_parse(raw, query.ticker)

        pt = self._last_usage["prompt_tokens"]
        ct = self._last_usage["completion_tokens"]
        cost = (pt * settings.LLM_INPUT_COST_PER_M + ct * settings.LLM_OUTPUT_COST_PER_M) / 1_000_000
        log_llm_call(
            run_id=run_id, ticker=query.ticker, phase="agent",
            agent_name=self.agent_name, model=settings.LLM_MODEL,
            prompt_tokens=pt, completion_tokens=ct,
            duration_ms=duration_ms, cost_usd=cost,
            score=output.overall_score, error=output.error,
        )
        logger.info(
            "[%s] Done (async) – score=%.3f tokens=%d cost=$%.5f",
            self.agent_name, output.overall_score, pt + ct, cost,
        )
        return output

    # ------------------------------------------------------------------
    # Abstract interface
    # ------------------------------------------------------------------

    @property
    @abstractmethod
    def agent_name(self) -> str:
        """Unique snake_case name, e.g. 'sales_demand'."""

    @property
    def sector(self) -> str:
        """Sector identifier passed to ContextBuilder for routing. Override in sector agents."""
        return ""

    @abstractmethod
    def _build_prompt(
        self, query: StockQuery, context: str
    ) -> tuple[str, str]:
        """Return (system_prompt, user_prompt) strings."""

    @abstractmethod
    def _parse_output(self, data: dict[str, Any], ticker: str) -> AgentOutput:
        """Convert parsed JSON dict into the correct AgentOutput subclass."""

    # ------------------------------------------------------------------
    # LLM calling
    # ------------------------------------------------------------------

    def _call_llm_with_retry(
        self,
        system_prompt: str,
        user_prompt: str,
        retries: int = settings.MAX_RETRIES,
    ) -> str:
        delay = settings.RETRY_DELAY_SECONDS
        last_error: Exception | None = None

        for attempt in range(1, retries + 1):
            try:
                response = self._client.chat.completions.create(
                    model=settings.LLM_MODEL,
                    temperature=settings.LLM_TEMPERATURE,
                    max_tokens=settings.LLM_MAX_TOKENS,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user",   "content": user_prompt},
                    ],
                    response_format={"type": "json_object"},
                )
                content = response.choices[0].message.content or ""
                logger.debug("[%s] Raw LLM response: %s", self.agent_name, content[:200])
                if response.usage:
                    self._last_usage = {
                        "prompt_tokens": response.usage.prompt_tokens,
                        "completion_tokens": response.usage.completion_tokens,
                    }
                return content

            except RateLimitError as e:
                logger.warning(
                    "[%s] Rate limit hit (attempt %d/%d), sleeping %.1fs",
                    self.agent_name, attempt, retries, delay,
                )
                last_error = e
                time.sleep(delay)
                delay *= 2

            except APITimeoutError as e:
                logger.warning(
                    "[%s] Timeout (attempt %d/%d)", self.agent_name, attempt, retries
                )
                last_error = e
                time.sleep(delay)

            except APIError as e:
                logger.error("[%s] API error: %s", self.agent_name, e)
                last_error = e
                break

        raise RuntimeError(
            f"[{self.agent_name}] LLM call failed after {retries} attempts: {last_error}"
        )

    async def _call_llm_async(
        self,
        system_prompt: str,
        user_prompt: str,
        retries: int = settings.MAX_RETRIES,
    ) -> str:
        """Async LLM call with exponential back-off. Uses AsyncOpenAI — no threads."""
        client = self._get_async_client()
        delay = settings.RETRY_DELAY_SECONDS
        last_error: Exception | None = None

        for attempt in range(1, retries + 1):
            try:
                response = await client.chat.completions.create(
                    model=settings.LLM_MODEL,
                    temperature=settings.LLM_TEMPERATURE,
                    max_tokens=settings.LLM_MAX_TOKENS,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user",   "content": user_prompt},
                    ],
                    response_format={"type": "json_object"},
                )
                content = response.choices[0].message.content or ""
                logger.debug("[%s] Raw async LLM response: %s", self.agent_name, content[:200])
                if response.usage:
                    self._last_usage = {
                        "prompt_tokens": response.usage.prompt_tokens,
                        "completion_tokens": response.usage.completion_tokens,
                    }
                return content

            except RateLimitError as e:
                logger.warning(
                    "[%s] Rate limit (async, attempt %d/%d), sleeping %.1fs",
                    self.agent_name, attempt, retries, delay,
                )
                last_error = e
                await asyncio.sleep(delay)
                delay *= 2

            except APITimeoutError as e:
                logger.warning(
                    "[%s] Timeout (async, attempt %d/%d)", self.agent_name, attempt, retries
                )
                last_error = e
                await asyncio.sleep(delay)

            except APIError as e:
                logger.error("[%s] API error (async): %s", self.agent_name, e)
                last_error = e
                break

        raise RuntimeError(
            f"[{self.agent_name}] Async LLM call failed after {retries} attempts: {last_error}"
        )

    # ------------------------------------------------------------------
    # JSON parsing
    # ------------------------------------------------------------------

    def _safe_parse(self, raw: str, ticker: str) -> AgentOutput:
        """Parse LLM JSON, falling back to an error output on failure."""
        try:
            data = json.loads(raw)
            # Thinking models (e.g. qwen3-235b) can return bare strings/numbers
            # instead of a JSON object even when json_object format is requested.
            # Extract the first {...} block from the raw string as a fallback.
            if not isinstance(data, dict):
                match = re.search(r'\{.*\}', raw, re.DOTALL)
                if match:
                    data = json.loads(match.group())
                else:
                    raise ValueError(f"LLM returned {type(data).__name__}, expected dict")
            output = self._parse_output(data, ticker)
            output.raw_llm_response = raw
            return output
        except Exception as exc:
            logger.error(
                "[%s] Failed to parse LLM output: %s\nRaw: %s",
                self.agent_name, exc, raw[:500],
            )
            return self._error_output(ticker, str(exc), raw)

    def _error_output(
        self, ticker: str, error_msg: str, raw: str = ""
    ) -> AgentOutput:
        return AgentOutput(
            agent=self.agent_name,
            ticker=ticker,
            overall_score=0.5,   # neutral fallback
            key_positives=[],
            key_risks=[f"Parse error: {error_msg}"],
            summary="Agent encountered an error and returned a neutral fallback score.",
            error=error_msg,
            raw_llm_response=raw,
        )

    # ------------------------------------------------------------------
    # Context gathering — Phase 2 live data + Phase 3 RAG
    # ------------------------------------------------------------------

    def _gather_context(self, query: StockQuery) -> tuple[str, bool]:
        """
        Assemble context string for the prompt.

        Returns (context_str, has_real_data).
        has_real_data=False means no live data was fetched — caller must NOT
        invoke the LLM to prevent training-knowledge hallucinations.

        Priority order:
          1. RAG (if RAG_ENABLED=true) — retrieves from vector store
          2. Live data — yfinance + news APIs via ContextBuilder
          3. Stub — no real data; signals caller to skip LLM
        """
        from core.intelligence.rag import config as rag_config

        if rag_config.RAG_ENABLED:
            try:
                return self._rag_retrieve(query), True
            except Exception as exc:
                logger.warning(
                    "[%s] RAG retrieval failed, falling back to live data: %s",
                    self.agent_name, exc,
                )

        # Live data via ContextBuilder
        try:
            from services.data.context.builder import ContextBuilder
            context, has_real_data = ContextBuilder().build(
                self.agent_name, query, sector=self.sector
            )
            if has_real_data and context:
                return context, True
        except Exception as exc:
            logger.warning("[%s] ContextBuilder failed: %s", self.agent_name, exc)

        # No real data — return stub so caller skips LLM
        stub = (
            f"Stock: {query.ticker} | Company: {query.company_name} | "
            f"Exchange: {query.exchange} | Analysis date: {query.analysis_date}"
        )
        return stub, False

    def _rag_retrieve(self, query: StockQuery) -> str:
        """
        Retrieve relevant document chunks from ChromaDB for this agent + query.
        Active only when RAG_ENABLED=true in config/rag_config.py.
        """
        from core.intelligence.rag.core.retriever import RAGRetriever
        from core.config.prompts.automobile import sales_demand, fundamentals, pattern_analysis, sentiment, risk_macro, orchestrator

        # Map agent name → its search queries template list
        prompt_modules = {
            "sales_demand":     sales_demand,
            "fundamentals":     fundamentals,
            "pattern_analysis": pattern_analysis,
            "sentiment":        sentiment,
            "risk_macro":       risk_macro,
        }
        mod = prompt_modules.get(self.agent_name)
        if mod and hasattr(mod, "CONTEXT_SEARCH_QUERIES"):
            from datetime import date as _date
            today = _date.today()
            raw_queries = [
                q.format(
                    ticker=query.ticker,
                    company_name=query.company_name,
                    month=today.strftime("%B"),
                    year=today.year,
                    quarter=f"Q{((today.month - 1) // 3) + 1} FY{today.year % 100}",
                    date=today.isoformat(),
                )
                for q in mod.CONTEXT_SEARCH_QUERIES[:3]
            ]
            search_query = " ".join(raw_queries[:2])
        else:
            search_query = f"{query.ticker} {query.company_name} automobile India"

        retriever = RAGRetriever()
        chunks = retriever.retrieve(search_query)
        if not chunks:
            return f"No RAG documents found for {query.ticker}."
        return "\n\n---\n".join(chunks)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _no_data_output(self, ticker: str) -> AgentOutput:
        """Neutral output returned when no real-time data is available. No LLM call made."""
        return AgentOutput(
            agent=self.agent_name,
            ticker=ticker,
            overall_score=0.5,
            key_positives=[],
            key_risks=["No real-time data available — score is neutral and excluded from confidence weighting"],
            summary=(
                f"[DATA UNAVAILABLE] {self.agent_name} could not fetch real-time data for {ticker}. "
                "Score held at neutral 0.5 to avoid distorting weighted analysis with stale LLM knowledge."
            ),
            error="no_real_time_data",
            data_freshness="unavailable",
        )

    @staticmethod
    def _clamp(value: float, lo: float = 0.0, hi: float = 1.0) -> float:
        return max(lo, min(hi, value))

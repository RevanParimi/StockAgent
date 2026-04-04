"""
agents/base_agent.py
====================
Base class shared by all five sub-agents.

Responsibilities:
  - Groq LLM client initialisation (using openai-compatible SDK)
  - Retry logic with exponential back-off
  - JSON response parsing and validation
  - Structured logging
  - Context assembly from search results (stub for RAG)
"""

from __future__ import annotations

import json
import logging
import time
from abc import ABC, abstractmethod
from typing import Any

from groq import Groq, APIError, APITimeoutError, RateLimitError

from config import settings
from models.schemas import AgentOutput, StockQuery

logger = logging.getLogger(__name__)


class BaseAgent(ABC):
    """
    Abstract base for all Automobile Agent sub-agents.

    Subclasses must implement:
        - `agent_name`  property (str)
        - `_build_prompt(query, context)` -> (system_prompt, user_prompt)
        - `_parse_output(raw_json, ticker)` -> AgentOutput subclass
    """

    def __init__(self) -> None:
        self._client = Groq(
            api_key=settings.GROQ_API_KEY,
            timeout=settings.LLM_TIMEOUT_SECONDS,
        )

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def run(self, query: StockQuery) -> AgentOutput:
        """
        Main entry point.  Gathers context, calls LLM, returns typed output.
        """
        logger.info("[%s] Starting analysis for %s", self.agent_name, query.ticker)
        context = self._gather_context(query)
        system_prompt, user_prompt = self._build_prompt(query, context)
        raw = self._call_llm_with_retry(system_prompt, user_prompt)
        output = self._safe_parse(raw, query.ticker)
        logger.info(
            "[%s] Done – score=%.3f for %s",
            self.agent_name,
            output.overall_score,
            query.ticker,
        )
        return output

    # ------------------------------------------------------------------
    # Abstract interface
    # ------------------------------------------------------------------

    @property
    @abstractmethod
    def agent_name(self) -> str:
        """Unique snake_case name, e.g. 'sales_demand'."""

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

    # ------------------------------------------------------------------
    # JSON parsing
    # ------------------------------------------------------------------

    def _safe_parse(self, raw: str, ticker: str) -> AgentOutput:
        """Parse LLM JSON, falling back to an error output on failure."""
        try:
            data = json.loads(raw)
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

    def _gather_context(self, query: StockQuery) -> str:
        """
        Assemble context string for the prompt.

        Priority order:
          1. RAG (if RAG_ENABLED=true) — retrieves from vector store
          2. Live data (Phase 2) — yfinance + news APIs via ContextBuilder
          3. Minimal stub fallback if both fail
        """
        from config import rag_config

        if rag_config.RAG_ENABLED:
            try:
                return self._rag_retrieve(query)
            except Exception as exc:
                logger.warning(
                    "[%s] RAG retrieval failed, falling back to live data: %s",
                    self.agent_name, exc,
                )

        # Phase 2: live data via ContextBuilder
        try:
            from tools.context_builder import ContextBuilder
            context = ContextBuilder().build(self.agent_name, query)
            if context:
                return context
        except Exception as exc:
            logger.warning(
                "[%s] ContextBuilder failed, using minimal stub: %s",
                self.agent_name, exc,
            )

        # Fallback stub
        return (
            f"Stock: {query.ticker} | Company: {query.company_name} | "
            f"Exchange: {query.exchange} | Analysis date: {query.analysis_date}\n"
            "Note: Live data unavailable. LLM will use training knowledge."
        )

    def _rag_retrieve(self, query: StockQuery) -> str:
        """
        Retrieve relevant document chunks from ChromaDB for this agent + query.
        Active only when RAG_ENABLED=true in config/rag_config.py.
        """
        from tools.rag.retriever import RAGRetriever
        from prompts import sales_demand, fundamentals, pattern_analysis, sentiment, risk_macro, orchestrator

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

    @staticmethod
    def _clamp(value: float, lo: float = 0.0, hi: float = 1.0) -> float:
        return max(lo, min(hi, value))

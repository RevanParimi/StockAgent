"""
src/backend/shared/agents/universal/agent.py
=============================================
UniversalAgent — one class replaces all sector-specific LLM agents.

Behaviour is driven entirely by the prompts_module passed at construction.
Each sector keeps its own prompts/{agent}.py with SYSTEM_PROMPT, ANALYSIS_PROMPT,
and CONTEXT_SEARCH_QUERIES. UniversalAgent reads from them; zero logic duplication.

Sector-specific agents that have custom data-fetching or non-standard output
parsing (SalesDemandAgent, RawMaterialsAgent, ITTranscriptNLPAgent, etc.)
are NOT replaced — they keep their own classes.

Usage in a sector registry.py:
    from backend.shared.agents.universal import UniversalAgent
    from backend.sectors.automobile.prompts import fundamentals as fund_p

    AGENTS = {
        "fundamentals": UniversalAgent("fundamentals", fund_p, sector="automobile"),
        ...
    }
"""
from __future__ import annotations

from types import ModuleType
from typing import Any

from backend.shared.pipeline.base_agent import BaseAgent
from backend.shared.schemas.pipeline import AgentOutput, StockQuery


class UniversalAgent(BaseAgent):
    """
    Generic LLM agent: prompt-in, scored-JSON-out.

    Args:
        name:           agent_name string (used as dict key in registry + in output)
        prompts_module: any module exposing SYSTEM_PROMPT and ANALYSIS_PROMPT strings
        sector:         sector key string forwarded to base class (default "")
    """

    def __init__(self, name: str, prompts_module: ModuleType, sector: str = "") -> None:
        super().__init__()
        self._name          = name
        self._P             = prompts_module
        self._sector_key    = sector
        # Expose CONTEXT_SEARCH_QUERIES to BaseAgent's RAG gather step if present
        self._extra_queries = list(getattr(prompts_module, "CONTEXT_SEARCH_QUERIES", []))

    # ------------------------------------------------------------------
    # BaseAgent abstract interface
    # ------------------------------------------------------------------

    @property
    def agent_name(self) -> str:
        return self._name

    @property
    def sector(self) -> str:
        return self._sector_key

    def _build_prompt(self, query: StockQuery, context: str) -> tuple[str, str]:
        user = self._P.ANALYSIS_PROMPT.format(
            ticker=query.ticker,
            company_name=query.company_name or query.ticker,
            context=context,
        )
        return self._P.SYSTEM_PROMPT, user

    def _parse_output(self, data: dict[str, Any], ticker: str) -> AgentOutput:
        return AgentOutput(
            agent=self._name,
            ticker=ticker,
            overall_score=self._clamp(float(data.get("overall_score", 0.5))),
            key_positives=data.get("key_positives", []),
            key_risks=data.get("key_risks", []),
            summary=data.get("summary", ""),
            data_freshness=data.get("data_freshness", ""),
        )

"""Auto-generated agent file. Edit prompt strings to customise LLM behaviour."""
from __future__ import annotations
from typing import Any
from backend.shared.pipeline.base_agent import BaseAgent
from backend.shared.schemas.pipeline import AgentOutput, StockQuery


class BFSIUniverseAgent(BaseAgent):
    @property
    def sector(self) -> str: return "bfsi"
    @property
    def agent_name(self) -> str: return "universe_setup"

    def _build_prompt(self, query: StockQuery, context: str) -> tuple[str, str]:
        system = """BFSI equity research analyst establishing peer group and index context. Return ONLY valid JSON."""
        user = """Universe setup and peer context for {ticker} ({company_name}) as of {analysis_date}.

Context:
{context}

Evaluate:
1. index_weight — Weight in Nifty Bank / PSU Bank
2. peer_positioning — Rank among PSU/Private/SFB/NBFC peers
3. market_cap_tier — Large/mid/small cap, free-float
4. corporate_actions — Splits, bonuses, rights, mergers
5. rebalancing_risk — Index inclusion/exclusion probability

Return ONLY valid JSON."""
        return system, user.format(
            ticker=query.ticker,
            company_name=query.company_name,
            analysis_date=query.analysis_date,
            context=context,
        )

    def _parse_output(self, data: dict, ticker: str) -> AgentOutput:
        return AgentOutput(
            agent=self.agent_name, ticker=ticker,
            overall_score=self._clamp(float(data.get("overall_score", 0.5))),
            key_positives=data.get("key_positives", []),
            key_risks=data.get("key_risks", []),
            summary=data.get("summary", ""),
            data_freshness=data.get("data_freshness", ""),
        )

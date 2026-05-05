from __future__ import annotations
from typing import Any
from pipeline.base_agent import BaseAgent
from core.schemas.pipeline import AgentOutput, StockQuery


class BFSIUniverseAgent(BaseAgent):
    @property
    def sector(self) -> str:
        return "bfsi"

    @property
    def agent_name(self) -> str:
        return "universe_setup"

    def _build_prompt(self, query: StockQuery, context: str) -> tuple[str, str]:
        system = (
            "You are a BFSI equity research analyst establishing the peer group "
            "and index context for a banking stock. Return ONLY valid JSON."
        )
        user = f"""
Universe setup and peer context for {query.ticker} ({query.company_name}) as of {query.analysis_date}.

Context:
{context}

Evaluate:
1. index_weight       — Weight in Nifty Bank / PSU Bank / Nifty 50 if applicable
2. peer_positioning   — Relative rank among PSU/Private/SFB/NBFC peers on key metrics
3. market_cap_tier    — Large/mid/small cap classification, free-float
4. corporate_actions  — Recent splits, bonuses, rights issues, merger events
5. rebalancing_risk   — Upcoming index rebalancing, inclusion/exclusion probability

Return:
{{
  "overall_score": <0.0–1.0>,
  "sub_scores": {{
    "index_weight": <float>,
    "peer_positioning": <float>,
    "market_cap_tier": <float>,
    "corporate_actions": <float>,
    "rebalancing_risk": <float>
  }},
  "key_positives": ["<point>", ...],
  "key_risks": ["<risk>", ...],
  "summary": "<2-3 sentence summary>",
  "data_freshness": "<date>"
}}
"""
        return system, user

    def _parse_output(self, data: dict[str, Any], ticker: str) -> AgentOutput:
        return AgentOutput(
            agent=self.agent_name, ticker=ticker,
            overall_score=self._clamp(float(data.get("overall_score", 0.5))),
            key_positives=data.get("key_positives", []),
            key_risks=data.get("key_risks", []),
            summary=data.get("summary", ""),
            data_freshness=data.get("data_freshness", ""),
        )

from __future__ import annotations
from typing import Any
from pipeline.base_agent import BaseAgent
from core.schemas.pipeline import AgentOutput, StockQuery


class BFSIInstitutionalAgent(BaseAgent):
    @property
    def sector(self) -> str:
        return "bfsi"

    @property
    def agent_name(self) -> str:
        return "institutional"

    def _build_prompt(self, query: StockQuery, context: str) -> tuple[str, str]:
        system = (
            "You are an equity market analyst tracking smart money flow for "
            "Indian banking stocks. Return ONLY valid JSON."
        )
        user = f"""
Institutional and insider flow analysis for {query.ticker} ({query.company_name}) as of {query.analysis_date}.

Context:
{context}

Evaluate:
1. fii_dii_flow       — Net FII/DII buying over 1M and 3M windows
2. promoter_holding   — Promoter stake change, pledge %
3. insider_trades     — ESOP exercises, open-market purchases/sales by insiders
4. analyst_changes    — Rating upgrades/downgrades, target price revisions
5. institutional_conc — Mutual fund holding %, top-10 institutional ownership

Return:
{{
  "overall_score": <0.0–1.0>,
  "sub_scores": {{
    "fii_dii_flow": <float>,
    "promoter_holding": <float>,
    "insider_trades": <float>,
    "analyst_changes": <float>,
    "institutional_conc": <float>
  }},
  "key_positives": ["<point>", ...],
  "key_risks": ["<risk>", ...],
  "summary": "<2-3 sentence summary>",
  "data_freshness": "<quarter>"
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

from __future__ import annotations
from typing import Any
from pipeline.base_agent import BaseAgent
from core.schemas.pipeline import AgentOutput, StockQuery


class BFSIMacroPolicyAgent(BaseAgent):
    @property
    def sector(self) -> str:
        return "bfsi"

    @property
    def agent_name(self) -> str:
        return "macro_policy"

    def _build_prompt(self, query: StockQuery, context: str) -> tuple[str, str]:
        system = (
            "You are a macro analyst covering the Indian banking system. "
            "Focus on RBI policy, systemic credit trends, and regulatory environment. "
            "Return ONLY valid JSON."
        )
        user = f"""
Macro & policy environment for {query.ticker} ({query.company_name}) as of {query.analysis_date}.

Context:
{context}

Evaluate:
1. rbi_rate_cycle       — Current repo rate, rate trajectory, MPC stance
2. system_credit        — System credit growth YoY, deposit growth, CD ratio
3. liquidity_conditions — LAF corridor, CRR/SLR impact, VRR/VRRR operations
4. regulatory_actions   — Recent RBI circulars, SEBI actions, IRDAI (if insurance)
5. fiscal_policy        — Government borrowing programme, PSU bank recap, IBC resolution pace

Return:
{{
  "overall_score": <0.0–1.0>,
  "sub_scores": {{
    "rbi_rate_cycle": <float>,
    "system_credit": <float>,
    "liquidity_conditions": <float>,
    "regulatory_actions": <float>,
    "fiscal_policy": <float>
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

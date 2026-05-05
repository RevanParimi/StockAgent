from __future__ import annotations
from typing import Any
from pipeline.base_agent import BaseAgent
from core.schemas.pipeline import AgentOutput, StockQuery


class REFundamentalsAgent(BaseAgent):
    @property
    def sector(self) -> str:
        return "re"

    @property
    def agent_name(self) -> str:
        return "fundamentals"

    def _build_prompt(self, query: StockQuery, context: str) -> tuple[str, str]:
        system = (
            "You are a project-finance analyst specialising in Indian renewable energy. "
            "Assess operational performance, cash generation, and leverage metrics. "
            "Return ONLY valid JSON."
        )
        user = f"""
Fundamental analysis of {query.ticker} ({query.company_name}) as of {query.analysis_date}.

Context:
{context}

Evaluate (score 0.0–1.0 each):
1. capacity_utilisation — CUF (%) vs technology benchmark: Solar 19-22%, Wind 28-35%
2. ebitda_quality       — EBITDA/MW trend, operating leverage, O&M cost control
3. debt_serviceability  — DSCR (target ≥1.2x), refinancing risk, debt maturity profile
4. receivables          — Receivables aging (<180 days ideal), DISCOM payment delays
5. leverage             — Project-level D/E, holdco leverage, off-balance-sheet exposure

Return:
{{
  "overall_score": <0.0–1.0>,
  "sub_scores": {{
    "capacity_utilisation": <float>,
    "ebitda_quality": <float>,
    "debt_serviceability": <float>,
    "receivables": <float>,
    "leverage": <float>
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

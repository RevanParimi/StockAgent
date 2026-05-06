"""Auto-generated agent file. Edit prompt strings to customise LLM behaviour."""
from __future__ import annotations
from typing import Any
from backend.shared.pipeline.base_agent import BaseAgent
from backend.shared.schemas.pipeline import AgentOutput, StockQuery


class RERiskAgent(BaseAgent):
    @property
    def sector(self) -> str: return "re"
    @property
    def agent_name(self) -> str: return "risk"

    def _build_prompt(self, query: StockQuery, context: str) -> tuple[str, str]:
        system = """Risk specialist for Indian renewable energy projects. Return ONLY valid JSON."""
        user = """Risk assessment for {ticker} ({company_name}) as of {analysis_date}.

Context:
{context}

Evaluate (1.0=low risk, 0.0=high risk — inverse scoring):
1. discom_credit — DISCOM payment delays, UDAY/RDSS compliance
2. regulatory_change — Retroactive tariff renegotiation, curtailment
3. weather_resource — Monsoon variability, generation impact
4. grid_integration — Transmission bottlenecks, curtailment %
5. commodity_input — Steel/copper capex impact, module prices

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

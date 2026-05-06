"""Auto-generated agent file. Edit prompt strings to customise LLM behaviour."""
from __future__ import annotations
from typing import Any
from backend.shared.pipeline.base_agent import BaseAgent
from backend.shared.schemas.pipeline import AgentOutput, StockQuery


class BFSIFundamentalsAgent(BaseAgent):
    @property
    def sector(self) -> str: return "bfsi"
    @property
    def agent_name(self) -> str: return "fundamentals"

    def _build_prompt(self, query: StockQuery, context: str) -> tuple[str, str]:
        system = """Senior banking analyst specialising in Indian BFSI. Analyse credit quality, capital adequacy, and profitability. Return ONLY valid JSON."""
        user = """Analyse the fundamentals of {ticker} ({company_name}) as of {analysis_date}.

Context:
{context}

Evaluate (score 0.0-1.0):
1. asset_quality — Gross NPA, Net NPA, PCR
2. net_interest — NIM trend, CASA ratio
3. capital_adequacy — CRAR/CET1 vs RBI minimum
4. profitability — RoA, RoE, credit cost, cost-to-income
5. loan_mix — Retail vs corporate, secured vs unsecured

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

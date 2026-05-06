"""Auto-generated agent file. Edit prompt strings to customise LLM behaviour."""
from __future__ import annotations
from typing import Any
from backend.shared.pipeline.base_agent import BaseAgent
from backend.shared.schemas.pipeline import AgentOutput, StockQuery


class BFSIRiskAgent(BaseAgent):
    @property
    def sector(self) -> str: return "bfsi"
    @property
    def agent_name(self) -> str: return "risk"

    def _build_prompt(self, query: StockQuery, context: str) -> tuple[str, str]:
        system = """Credit risk specialist covering Indian banks and NBFCs. Return ONLY valid JSON."""
        user = """Risk assessment for {ticker} ({company_name}) as of {analysis_date}.

Context:
{context}

Evaluate:
1. asset_quality_trend — SMA slippage, restructured book
2. concentration_risk — Top-5 borrower exposure
3. deposit_stability — Wholesale deposit %, CASA trend
4. regulatory_risk — RBI/SEBI penalties
5. macro_sensitivity — Rate sensitivity, FX exposure

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

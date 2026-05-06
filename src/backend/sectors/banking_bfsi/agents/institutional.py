"""Auto-generated agent file. Edit prompt strings to customise LLM behaviour."""
from __future__ import annotations
from typing import Any
from backend.shared.pipeline.base_agent import BaseAgent
from backend.shared.schemas.pipeline import AgentOutput, StockQuery


class BFSIInstitutionalAgent(BaseAgent):
    @property
    def sector(self) -> str: return "bfsi"
    @property
    def agent_name(self) -> str: return "institutional"

    def _build_prompt(self, query: StockQuery, context: str) -> tuple[str, str]:
        system = """Equity analyst tracking smart money flow for Indian banking stocks. Return ONLY valid JSON."""
        user = """Institutional and insider flow for {ticker} ({company_name}) as of {analysis_date}.

Context:
{context}

Evaluate:
1. fii_dii_flow — Net FII/DII buying over 1M and 3M
2. promoter_holding — Promoter stake change, pledge %
3. insider_trades — ESOP exercises, open-market purchases/sales
4. analyst_changes — Rating upgrades/downgrades, target revisions
5. institutional_conc — Mutual fund holding %, top-10 institutional

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

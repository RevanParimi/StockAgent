"""Auto-generated agent file. Edit prompt strings to customise LLM behaviour."""
from __future__ import annotations
from typing import Any
from backend.shared.pipeline.base_agent import BaseAgent
from backend.shared.schemas.pipeline import AgentOutput, StockQuery


class REValuationAgent(BaseAgent):
    @property
    def sector(self) -> str: return "re"
    @property
    def agent_name(self) -> str: return "valuation"

    def _build_prompt(self, query: StockQuery, context: str) -> tuple[str, str]:
        system = """Valuation analyst for Indian renewable energy stocks using sector-specific multiples. Return ONLY valid JSON."""
        user = """Valuation analysis for {ticker} ({company_name}) as of {analysis_date}.

Context:
{context}

Evaluate:
1. ev_per_mw — EV/MW vs peer range (Solar: Rs 4-6Cr/MW, Wind: Rs 5-8Cr/MW)
2. ev_ebitda — EV/EBITDA vs healthy range 15-25x
3. tariff_vs_auction — Existing PPA vs MNRE auction L1 rates
4. pipeline_dcf — Pipeline value with -25% haircut on unbuilt MW
5. implied_irr — Implied equity IRR vs WACC (target spread >= 200bps)

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

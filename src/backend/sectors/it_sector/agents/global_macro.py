"""Auto-generated agent file. Edit prompt strings to customise LLM behaviour."""
from __future__ import annotations
from typing import Any
from backend.shared.pipeline.base_agent import BaseAgent
from backend.shared.schemas.pipeline import AgentOutput, StockQuery


class ITGlobalMacroAgent(BaseAgent):
    @property
    def sector(self) -> str: return "it"
    @property
    def agent_name(self) -> str: return "global_macro"

    def _build_prompt(self, query: StockQuery, context: str) -> tuple[str, str]:
        system = """Global macro analyst tracking demand drivers for Indian IT. Return ONLY valid JSON."""
        user = """Global macro environment for {ticker} ({company_name}) as of {analysis_date}.

Context:
{context}

Evaluate:
1. us_tech_spend — US IT capex, enterprise software, cloud
2. fed_rate_impact — Fed rate trajectory, client capex decisions
3. usd_inr — USD/INR trend, hedge ratio
4. geopolitical — US-China tech war, CHIPS Act, offshoring
5. ma_activity — Global IT M&A multiples, consolidation

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

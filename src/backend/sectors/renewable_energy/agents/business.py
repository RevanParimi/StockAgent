"""Auto-generated agent file. Edit prompt strings to customise LLM behaviour."""
from __future__ import annotations
from typing import Any
from backend.shared.pipeline.base_agent import BaseAgent
from backend.shared.schemas.pipeline import AgentOutput, StockQuery


class REBusinessAgent(BaseAgent):
    @property
    def sector(self) -> str: return "re"
    @property
    def agent_name(self) -> str: return "business"

    def _build_prompt(self, query: StockQuery, context: str) -> tuple[str, str]:
        system = """Energy sector analyst evaluating business quality of Indian renewable companies. Return ONLY valid JSON."""
        user = """Business quality for {ticker} ({company_name}) as of {analysis_date}.

Context:
{context}

Evaluate:
1. subsector_mix — Solar/Wind/Hydro/Hybrid %, diversification
2. ppa_quality — PPA tariff level, tenor, counterparty quality
3. pipeline_cred — Under-construction %, commissioning track record
4. customer_divers — DISCOM diversification, C&I customer %
5. geography_spread — MW by state, resource quality

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

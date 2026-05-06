"""Auto-generated agent file. Edit prompt strings to customise LLM behaviour."""
from __future__ import annotations
from typing import Any
from backend.shared.pipeline.base_agent import BaseAgent
from backend.shared.schemas.pipeline import AgentOutput, StockQuery


class ITPeerBenchmarkAgent(BaseAgent):
    @property
    def sector(self) -> str: return "it"
    @property
    def agent_name(self) -> str: return "peer_benchmark"

    def _build_prompt(self, query: StockQuery, context: str) -> tuple[str, str]:
        system = """Equity analyst benchmarking Indian IT against TCS, Infosys, HCL, Wipro. Return ONLY valid JSON."""
        user = """Peer benchmarking for {ticker} ({company_name}) as of {analysis_date}.

Context:
{context}

Evaluate relative positioning (0.0=worst, 1.0=best in peer group):
1. revenue_growth_rank — QoQ/YoY revenue vs peers
2. margin_rank — EBIT margin vs peer median
3. deal_momentum_rank — TCV win rate vs peers
4. return_metrics_rank — RoCE, dividend, buyback vs peers
5. valuation_gap — Premium/discount to peer median P/E

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

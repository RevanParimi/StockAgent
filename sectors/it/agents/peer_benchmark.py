from __future__ import annotations
from typing import Any
from pipeline.base_agent import BaseAgent
from core.schemas.pipeline import AgentOutput, StockQuery


class ITPeerBenchmarkAgent(BaseAgent):
    @property
    def sector(self) -> str:
        return "it"

    @property
    def agent_name(self) -> str:
        return "peer_benchmark"

    def _build_prompt(self, query: StockQuery, context: str) -> tuple[str, str]:
        system = (
            "You are an equity analyst benchmarking Indian IT companies against peers. "
            "Compare TCS, Infosys, HCL Tech, and Wipro on key metrics. "
            "Return ONLY valid JSON."
        )
        user = f"""
Peer benchmarking for {query.ticker} ({query.company_name}) vs TCS, Infosys, HCL, Wipro as of {query.analysis_date}.

Context:
{context}

Evaluate relative positioning (score 0.0=worst in peer group, 1.0=best):
1. revenue_growth_rank — QoQ/YoY revenue growth vs peers
2. margin_rank         — EBIT margin vs peer median
3. deal_momentum_rank  — TCV win rate, large deal momentum vs peers
4. return_metrics_rank — RoCE, dividend yield, buyback yield vs peers
5. valuation_gap       — Premium/discount to peer median P/E justified?

Return:
{{
  "overall_score": <0.0–1.0>,
  "sub_scores": {{
    "revenue_growth_rank": <float>,
    "margin_rank": <float>,
    "deal_momentum_rank": <float>,
    "return_metrics_rank": <float>,
    "valuation_gap": <float>
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

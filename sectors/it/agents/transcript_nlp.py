from __future__ import annotations
from typing import Any
from pipeline.base_agent import BaseAgent
from core.schemas.pipeline import AgentOutput, StockQuery


class ITTranscriptNLPAgent(BaseAgent):
    @property
    def sector(self) -> str:
        return "it"

    @property
    def agent_name(self) -> str:
        return "transcript_nlp"

    def _build_prompt(self, query: StockQuery, context: str) -> tuple[str, str]:
        system = (
            "You are an NLP specialist extracting signals from earnings call transcripts "
            "of Indian IT companies. Return ONLY valid JSON."
        )
        user = f"""
Earnings call transcript NLP for {query.ticker} ({query.company_name}) as of {query.analysis_date}.

Context (may include recent transcript excerpts):
{context}

Evaluate:
1. guidance_tone     — Forward guidance language: cautious/neutral/optimistic
2. demand_signals    — Client spending commentary, vertical-specific demand signals
3. margin_commentary — Management explanation of margin levers/pressures
4. ai_deal_mentions  — Frequency and conviction of GenAI deal references
5. analyst_qa_tone   — Quality of responses to analyst questions, evasion signals

Return:
{{
  "overall_score": <0.0–1.0>,
  "sub_scores": {{
    "guidance_tone": <float>,
    "demand_signals": <float>,
    "margin_commentary": <float>,
    "ai_deal_mentions": <float>,
    "analyst_qa_tone": <float>
  }},
  "key_positives": ["<point>", ...],
  "key_risks": ["<risk>", ...],
  "summary": "<2-3 sentence summary>",
  "data_freshness": "<quarter earnings date>"
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

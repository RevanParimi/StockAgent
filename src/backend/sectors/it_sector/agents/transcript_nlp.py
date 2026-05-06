"""Auto-generated agent file. Edit prompt strings to customise LLM behaviour."""
from __future__ import annotations
from typing import Any
from backend.shared.pipeline.base_agent import BaseAgent
from backend.shared.schemas.pipeline import AgentOutput, StockQuery


class ITTranscriptNLPAgent(BaseAgent):
    @property
    def sector(self) -> str: return "it"
    @property
    def agent_name(self) -> str: return "transcript_nlp"

    def _build_prompt(self, query: StockQuery, context: str) -> tuple[str, str]:
        system = """NLP specialist extracting signals from earnings call transcripts. Return ONLY valid JSON."""
        user = """Transcript NLP for {ticker} ({company_name}) as of {analysis_date}.

Context:
{context}

Evaluate:
1. guidance_tone — Forward guidance: cautious/neutral/optimistic
2. demand_signals — Client spending commentary, vertical demand
3. margin_commentary — Management explanation of margin levers
4. ai_deal_mentions — Frequency and conviction of GenAI references
5. analyst_qa_tone — Quality of responses to analyst questions

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

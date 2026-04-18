"""
graphs/it_sector/agents.py
===========================
Eight specialist sub-agents for Indian IT sector.
Spec source: IT_Sector_Agent_Registry.docx

Agent                  Weight   Focus
─────────────────────  ──────   ─────────────────────────────────────────────
fundamentals            0.25    Revenue, EBIT margin, TCV/deal wins, attrition
global_macro            0.20    US tech spend, Fed rates, USD/INR, US-China risk
risk_macro              0.15    H1B/L1 visa, AI disruption, client concentration
peer_benchmark          0.15    TCS/Infosys/HCL/Wipro comparative metrics
pattern_analysis        0.10    10yr cycles, RSI/MACD/BB, Nifty IT correlation
sentiment               0.08    AI narrative, layoff signals, management tone
transcript_nlp          0.04    Earnings call sentiment extraction
insider_smart_money     0.03    Insider trades, smart money patterns
"""

from __future__ import annotations

from typing import Any

from agents.base_agent import BaseAgent
from models.schemas import AgentOutput, StockQuery


# ──────────────────────────────────────────────────────────────────────────
# 1. Fundamentals
# ──────────────────────────────────────────────────────────────────────────

class ITFundamentalsAgent(BaseAgent):
    @property
    def agent_name(self) -> str:
        return "fundamentals"

    def _build_prompt(self, query: StockQuery, context: str) -> tuple[str, str]:
        system = (
            "You are a senior IT equity analyst covering Indian technology companies. "
            "Assess financial performance, deal pipeline, and talent metrics. "
            "Return ONLY valid JSON."
        )
        user = f"""
Fundamental analysis of {query.ticker} ({query.company_name}) as of {query.analysis_date}.

Context:
{context}

Evaluate (score 0.0–1.0 each):
1. revenue_growth   — QoQ and YoY revenue growth, constant-currency growth
2. ebit_margins     — EBIT margin trend over 8 quarters, guidance vs actual
3. deal_wins        — TCV of large deals, deal pipeline health, win rates
4. attrition        — Trailing 12M attrition %, trend, fresher intake ratio
5. valuation        — P/E, EV/Revenue, PEG vs 5yr historical and peers

Return:
{{
  "overall_score": <0.0–1.0>,
  "sub_scores": {{
    "revenue_growth": <float>,
    "ebit_margins": <float>,
    "deal_wins": <float>,
    "attrition": <float>,
    "valuation": <float>
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


# ──────────────────────────────────────────────────────────────────────────
# 2. Global Macro
# ──────────────────────────────────────────────────────────────────────────

class ITGlobalMacroAgent(BaseAgent):
    @property
    def agent_name(self) -> str:
        return "global_macro"

    def _build_prompt(self, query: StockQuery, context: str) -> tuple[str, str]:
        system = (
            "You are a global macro analyst tracking demand drivers for Indian IT. "
            "Focus on US tech spending, Fed policy, and geopolitical risk. "
            "Return ONLY valid JSON."
        )
        user = f"""
Global macro environment for {query.ticker} ({query.company_name}) as of {query.analysis_date}.

Context:
{context}

Evaluate:
1. us_tech_spend     — US IT capex trends, enterprise software budgets, cloud spend
2. fed_rate_impact   — Fed funds rate trajectory, impact on US client capex decisions
3. usd_inr           — USD/INR trend, hedge ratio, revenue translation impact
4. geopolitical      — US-China tech war impact, CHIPS Act, offshoring sentiment
5. ma_activity       — Global IT M&A wave, deal multiples, consolidation risk

Return:
{{
  "overall_score": <0.0–1.0>,
  "sub_scores": {{
    "us_tech_spend": <float>,
    "fed_rate_impact": <float>,
    "usd_inr": <float>,
    "geopolitical": <float>,
    "ma_activity": <float>
  }},
  "key_positives": ["<point>", ...],
  "key_risks": ["<risk>", ...],
  "summary": "<2-3 sentence summary>",
  "data_freshness": "<date>"
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


# ──────────────────────────────────────────────────────────────────────────
# 3. Risk & Macro
# ──────────────────────────────────────────────────────────────────────────

class ITRiskMacroAgent(BaseAgent):
    @property
    def agent_name(self) -> str:
        return "risk_macro"

    def _build_prompt(self, query: StockQuery, context: str) -> tuple[str, str]:
        system = (
            "You are a risk analyst covering Indian IT companies. "
            "Assess visa, AI disruption, and concentration risks. "
            "Return ONLY valid JSON."
        )
        user = f"""
Risk assessment for {query.ticker} ({query.company_name}) as of {query.analysis_date}.

Context:
{context}

Evaluate:
1. visa_risk          — H1B/L1 approval rates, denial trends, visa reform legislation
2. ai_disruption      — % of revenue at risk from GenAI/automation, AI deal wins
3. client_concentration — Top-5 client revenue %, churn risk, vertical concentration
4. fx_hedge           — INR/USD hedge coverage, derivative positions, revenue mix
5. talent_risk        — Supply of skilled talent, campus hiring, moonlighting trends

Return:
{{
  "overall_score": <0.0–1.0>,
  "sub_scores": {{
    "visa_risk": <float>,
    "ai_disruption": <float>,
    "client_concentration": <float>,
    "fx_hedge": <float>,
    "talent_risk": <float>
  }},
  "key_positives": ["<point>", ...],
  "key_risks": ["<risk>", ...],
  "summary": "<2-3 sentence summary>",
  "data_freshness": "<date>"
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


# ──────────────────────────────────────────────────────────────────────────
# 4. Peer Benchmark
# ──────────────────────────────────────────────────────────────────────────

class ITPeerBenchmarkAgent(BaseAgent):
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


# ──────────────────────────────────────────────────────────────────────────
# 5. Pattern Analysis
# ──────────────────────────────────────────────────────────────────────────

class ITPatternAgent(BaseAgent):
    @property
    def agent_name(self) -> str:
        return "pattern_analysis"

    def _build_prompt(self, query: StockQuery, context: str) -> tuple[str, str]:
        system = (
            "You are a technical analyst covering Indian IT stocks. "
            "Identify price patterns, momentum signals, and seasonality. "
            "Return ONLY valid JSON."
        )
        user = f"""
Technical analysis for {query.ticker} ({query.company_name}) as of {query.analysis_date}.

Context:
{context}

Evaluate:
1. price_cycle       — 10yr cycle position, quarter-end rebalancing seasonality
2. momentum          — RSI (14d), MACD line/signal crossover, BB width
3. breakout_levels   — Key support/resistance levels, recent breakouts/breakdowns
4. nifty_it_beta     — Rolling 12M beta vs Nifty IT, alpha generation
5. volume_quality    — Volume trend, accumulation/distribution, put-call ratio

Return:
{{
  "overall_score": <0.0–1.0>,
  "sub_scores": {{
    "price_cycle": <float>,
    "momentum": <float>,
    "breakout_levels": <float>,
    "nifty_it_beta": <float>,
    "volume_quality": <float>
  }},
  "key_positives": ["<point>", ...],
  "key_risks": ["<risk>", ...],
  "summary": "<2-3 sentence summary>",
  "data_freshness": "<date>"
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


# ──────────────────────────────────────────────────────────────────────────
# 6. Sentiment
# ──────────────────────────────────────────────────────────────────────────

class ITSentimentAgent(BaseAgent):
    @property
    def agent_name(self) -> str:
        return "sentiment"

    def _build_prompt(self, query: StockQuery, context: str) -> tuple[str, str]:
        system = (
            "You are a sentiment analyst tracking news and social signals for "
            "Indian IT companies. Return ONLY valid JSON."
        )
        user = f"""
Sentiment analysis for {query.ticker} ({query.company_name}) as of {query.analysis_date}.

Context:
{context}

Evaluate:
1. ai_narrative      — GenAI deal announcements, AI transformation storyline strength
2. layoff_signals    — Workforce reduction news, bench utilisation concerns
3. management_tone   — CFO/CEO interview sentiment, guidance language analysis
4. media_coverage    — Volume and tone of recent news coverage
5. social_buzz       — LinkedIn/Twitter/Reddit IT community sentiment

Return:
{{
  "overall_score": <0.0–1.0>,
  "sub_scores": {{
    "ai_narrative": <float>,
    "layoff_signals": <float>,
    "management_tone": <float>,
    "media_coverage": <float>,
    "social_buzz": <float>
  }},
  "key_positives": ["<point>", ...],
  "key_risks": ["<risk>", ...],
  "summary": "<2-3 sentence summary>",
  "data_freshness": "<date>"
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


# ──────────────────────────────────────────────────────────────────────────
# 7. Transcript NLP
# ──────────────────────────────────────────────────────────────────────────

class ITTranscriptNLPAgent(BaseAgent):
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


# ──────────────────────────────────────────────────────────────────────────
# 8. Insider & Smart Money
# ──────────────────────────────────────────────────────────────────────────

class ITInsiderAgent(BaseAgent):
    @property
    def agent_name(self) -> str:
        return "insider_smart_money"

    def _build_prompt(self, query: StockQuery, context: str) -> tuple[str, str]:
        system = (
            "You are an analyst tracking insider and institutional smart-money flows "
            "for Indian IT stocks. Return ONLY valid JSON."
        )
        user = f"""
Insider and smart-money analysis for {query.ticker} ({query.company_name}) as of {query.analysis_date}.

Context:
{context}

Evaluate:
1. promoter_activity   — Promoter open-market buys/sells, ESOP exercise patterns
2. director_trades     — Non-executive director trades pre/post results
3. smart_money_flow    — Tier-1 mutual fund allocation changes (SBI/HDFC/Mirae)
4. short_interest      — F&O put-call ratio, short-selling trend
5. block_deals         — Recent block/bulk deal activity and counterparties

Return:
{{
  "overall_score": <0.0–1.0>,
  "sub_scores": {{
    "promoter_activity": <float>,
    "director_trades": <float>,
    "smart_money_flow": <float>,
    "short_interest": <float>,
    "block_deals": <float>
  }},
  "key_positives": ["<point>", ...],
  "key_risks": ["<risk>", ...],
  "summary": "<2-3 sentence summary>",
  "data_freshness": "<date>"
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


# ── Registry ───────────────────────────────────────────────────────────────

AGENTS: dict = {
    "fundamentals":        ITFundamentalsAgent(),
    "global_macro":        ITGlobalMacroAgent(),
    "risk_macro":          ITRiskMacroAgent(),
    "peer_benchmark":      ITPeerBenchmarkAgent(),
    "pattern_analysis":    ITPatternAgent(),
    "sentiment":           ITSentimentAgent(),
    "transcript_nlp":      ITTranscriptNLPAgent(),
    "insider_smart_money": ITInsiderAgent(),
}

WEIGHTS: dict[str, float] = {
    "fundamentals":        0.25,
    "global_macro":        0.20,
    "risk_macro":          0.15,
    "peer_benchmark":      0.15,
    "pattern_analysis":    0.10,
    "sentiment":           0.08,
    "transcript_nlp":      0.04,
    "insider_smart_money": 0.03,
}

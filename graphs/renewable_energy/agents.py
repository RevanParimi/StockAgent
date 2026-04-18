"""
graphs/renewable_energy/agents.py
===================================
Six specialist sub-agents for Indian Renewable Energy sector.
Spec source: RenewableEnergy_Agent_Registry.docx

Agent                Weight   Focus
───────────────────  ──────   ──────────────────────────────────────────────
fundamentals          0.30    CUF, EBITDA/MW, DSCR, receivables, D/E
business              0.25    Sub-sector mix, PPA quality, pipeline credibility
valuation             0.20    EV/MW, EV/EBITDA, PPA tariff vs auction rates
sentiment_policy      0.15    MNRE auctions, Budget RE capex, green hydrogen
technical             0.10    50/200 DMA, RSI, MACD, volume surge
risk                  0.00*   DISCOM credit, weather, grid, regulation (* flagged
                               separately — does not dilute score but raises alerts)
"""

from __future__ import annotations

from typing import Any

from agents.base_agent import BaseAgent
from models.schemas import AgentOutput, StockQuery


# ──────────────────────────────────────────────────────────────────────────
# 1. Fundamentals
# ──────────────────────────────────────────────────────────────────────────

class REFundamentalsAgent(BaseAgent):
    @property
    def sector(self) -> str:
        return "re"

    @property
    def agent_name(self) -> str:
        return "fundamentals"

    def _build_prompt(self, query: StockQuery, context: str) -> tuple[str, str]:
        system = (
            "You are a project-finance analyst specialising in Indian renewable energy. "
            "Assess operational performance, cash generation, and leverage metrics. "
            "Return ONLY valid JSON."
        )
        user = f"""
Fundamental analysis of {query.ticker} ({query.company_name}) as of {query.analysis_date}.

Context:
{context}

Evaluate (score 0.0–1.0 each):
1. capacity_utilisation — CUF (%) vs technology benchmark: Solar 19-22%, Wind 28-35%
2. ebitda_quality       — EBITDA/MW trend, operating leverage, O&M cost control
3. debt_serviceability  — DSCR (target ≥1.2x), refinancing risk, debt maturity profile
4. receivables          — Receivables aging (<180 days ideal), DISCOM payment delays
5. leverage             — Project-level D/E, holdco leverage, off-balance-sheet exposure

Return:
{{
  "overall_score": <0.0–1.0>,
  "sub_scores": {{
    "capacity_utilisation": <float>,
    "ebitda_quality": <float>,
    "debt_serviceability": <float>,
    "receivables": <float>,
    "leverage": <float>
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
# 2. Business Quality
# ──────────────────────────────────────────────────────────────────────────

class REBusinessAgent(BaseAgent):
    @property
    def sector(self) -> str:
        return "re"

    @property
    def agent_name(self) -> str:
        return "business"

    def _build_prompt(self, query: StockQuery, context: str) -> tuple[str, str]:
        system = (
            "You are an energy sector analyst evaluating the business quality of "
            "Indian renewable energy companies. Return ONLY valid JSON."
        )
        user = f"""
Business quality assessment for {query.ticker} ({query.company_name}) as of {query.analysis_date}.

Context:
{context}

Evaluate:
1. subsector_mix     — Solar/Wind/Hydro/Hybrid %, technology diversification score
2. ppa_quality       — PPA tariff level, tenor remaining, counterparty (central/state/C&I)
3. pipeline_cred     — Under-construction % of total target, commissioning track record
4. customer_divers   — DISCOM diversification (state mix), C&I customer %
5. geography_spread  — MW by state, wind resource quality, irradiance levels

Return:
{{
  "overall_score": <0.0–1.0>,
  "sub_scores": {{
    "subsector_mix": <float>,
    "ppa_quality": <float>,
    "pipeline_cred": <float>,
    "customer_divers": <float>,
    "geography_spread": <float>
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
# 3. Valuation
# ──────────────────────────────────────────────────────────────────────────

class REValuationAgent(BaseAgent):
    @property
    def sector(self) -> str:
        return "re"

    @property
    def agent_name(self) -> str:
        return "valuation"

    def _build_prompt(self, query: StockQuery, context: str) -> tuple[str, str]:
        system = (
            "You are a valuation analyst for Indian renewable energy stocks. "
            "Use sector-specific multiples and DCF methodology. "
            "Return ONLY valid JSON."
        )
        user = f"""
Valuation analysis for {query.ticker} ({query.company_name}) as of {query.analysis_date}.

Context:
{context}

Evaluate:
1. ev_per_mw         — EV/MW vs peer range (Solar: ₹4-6Cr/MW, Wind: ₹5-8Cr/MW)
2. ev_ebitda         — EV/EBITDA vs healthy range 15-25x for quality RE assets
3. tariff_vs_auction — Existing PPA tariffs vs current MNRE auction L1 rates
4. pipeline_dcf      — Pipeline value with −25% haircut on unbuilt MW
5. implied_irr       — Implied equity IRR vs WACC (target spread ≥200-300bps)

Return:
{{
  "overall_score": <0.0–1.0>,
  "sub_scores": {{
    "ev_per_mw": <float>,
    "ev_ebitda": <float>,
    "tariff_vs_auction": <float>,
    "pipeline_dcf": <float>,
    "implied_irr": <float>
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
# 4. Sentiment & Policy
# ──────────────────────────────────────────────────────────────────────────

class RESentimentPolicyAgent(BaseAgent):
    @property
    def sector(self) -> str:
        return "re"

    @property
    def agent_name(self) -> str:
        return "sentiment_policy"

    def _build_prompt(self, query: StockQuery, context: str) -> tuple[str, str]:
        system = (
            "You are a policy analyst and sentiment tracker for Indian renewable energy. "
            "Track MNRE auctions, Budget allocations, and sector news flow. "
            "Return ONLY valid JSON."
        )
        user = f"""
Sentiment and policy analysis for {query.ticker} ({query.company_name}) as of {query.analysis_date}.

Context:
{context}

Evaluate:
1. mnre_auction_health — Recent auction GW awarded, tariff trajectory, bid pipeline
2. budget_allocation   — Union Budget RE capex, green hydrogen mission funding
3. policy_tailwinds    — RPO targets, must-run status, ISTS waiver continuation
4. green_hydrogen      — Company exposure to green H2 opportunity/investment
5. news_sentiment      — Recent news tone: project wins, delays, govt support

Return:
{{
  "overall_score": <0.0–1.0>,
  "sub_scores": {{
    "mnre_auction_health": <float>,
    "budget_allocation": <float>,
    "policy_tailwinds": <float>,
    "green_hydrogen": <float>,
    "news_sentiment": <float>
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
# 5. Technical (timing signal)
# ──────────────────────────────────────────────────────────────────────────

class RETechnicalAgent(BaseAgent):
    @property
    def sector(self) -> str:
        return "re"

    @property
    def agent_name(self) -> str:
        return "technical"

    def _build_prompt(self, query: StockQuery, context: str) -> tuple[str, str]:
        system = (
            "You are a technical analyst providing entry/exit timing signals for "
            "Indian renewable energy stocks. Return ONLY valid JSON."
        )
        user = f"""
Technical timing signal for {query.ticker} ({query.company_name}) as of {query.analysis_date}.

Context:
{context}

Evaluate:
1. moving_averages   — 50-DMA vs 200-DMA (golden cross / death cross)
2. rsi_signal        — Weekly RSI: oversold <35 = bullish, overbought >70 = bearish
3. macd_weekly       — Weekly MACD crossover direction and histogram trend
4. volume_catalyst   — Volume surge on policy/MNRE news, accumulation zones
5. accumulation_zone — Current price vs 52-week range, Fibonacci retracement levels

Return:
{{
  "overall_score": <0.0–1.0>,
  "sub_scores": {{
    "moving_averages": <float>,
    "rsi_signal": <float>,
    "macd_weekly": <float>,
    "volume_catalyst": <float>,
    "accumulation_zone": <float>
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
# 6. Risk (monitoring-only — weight=0 but alerts fire on high risk scores)
# ──────────────────────────────────────────────────────────────────────────

class RERiskAgent(BaseAgent):
    @property
    def sector(self) -> str:
        return "re"

    @property
    def agent_name(self) -> str:
        return "risk"

    def _build_prompt(self, query: StockQuery, context: str) -> tuple[str, str]:
        system = (
            "You are a risk specialist for Indian renewable energy projects. "
            "Identify structural risks that could impair cash flows. "
            "Return ONLY valid JSON."
        )
        user = f"""
Risk assessment for {query.ticker} ({query.company_name}) as of {query.analysis_date}.

Context:
{context}

Evaluate (1.0 = low risk, 0.0 = high risk — inverse scoring):
1. discom_credit     — DISCOM payment delays, state UDAY/RDSS compliance
2. regulatory_change — Retroactive tariff re-negotiation, curtailment orders
3. weather_resource  — Monsoon variability impact on hydro/solar generation
4. grid_integration  — Transmission bottlenecks, curtailment %, grid evacuation
5. commodity_input   — Steel/copper price impact on capex, module price volatility

Return:
{{
  "overall_score": <0.0–1.0>,
  "sub_scores": {{
    "discom_credit": <float>,
    "regulatory_change": <float>,
    "weather_resource": <float>,
    "grid_integration": <float>,
    "commodity_input": <float>
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
    "fundamentals":     REFundamentalsAgent(),
    "business":         REBusinessAgent(),
    "valuation":        REValuationAgent(),
    "sentiment_policy": RESentimentPolicyAgent(),
    "technical":        RETechnicalAgent(),
    "risk":             RERiskAgent(),
}

# Risk runs as a monitoring agent (weight=0 → score doesn't alter verdict
# but conflicts and key_risks surface in FinalReport.top_risks)
WEIGHTS: dict[str, float] = {
    "fundamentals":     0.30,
    "business":         0.25,
    "valuation":        0.20,
    "sentiment_policy": 0.15,
    "technical":        0.10,
    "risk":             0.00,
}

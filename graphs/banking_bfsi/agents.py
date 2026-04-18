"""
graphs/banking_bfsi/agents.py
==============================
Six specialist sub-agents for Indian Banking & BFSI sector.
Spec source: Banking_BFSI_Agent_Registry.docx

Agent               Weight   Focus
──────────────────  ──────   ────────────────────────────────────────────────
fundamentals         0.25    NPA, NIM, CASA, CRAR, RoA/RoE, loan mix
risk                 0.20    Asset quality, concentration, deposit runoff
macro_policy         0.20    RBI MPC repo, system credit growth, SEBI circulars
institutional        0.15    FII/DII flows, promoter holding, insider trades
pattern_analysis     0.15    10yr cycle, rate-cut seasonality, RSI/MACD/BB
universe_setup       0.05    Index composition, peer grouping, corporate actions
"""

from __future__ import annotations

from typing import Any

from agents.base_agent import BaseAgent
from models.schemas import AgentOutput, StockQuery


# ──────────────────────────────────────────────────────────────────────────
# 1. Fundamentals
# ──────────────────────────────────────────────────────────────────────────

class BFSIFundamentalsAgent(BaseAgent):
    @property
    def agent_name(self) -> str:
        return "fundamentals"

    def _build_prompt(self, query: StockQuery, context: str) -> tuple[str, str]:
        system = (
            "You are a senior banking analyst specialising in Indian BFSI stocks. "
            "Analyse credit quality, capital adequacy, and profitability metrics. "
            "Return ONLY valid JSON."
        )
        user = f"""
Analyse the fundamentals of {query.ticker} ({query.company_name}) as of {query.analysis_date}.

Context:
{context}

Evaluate these dimensions (score each 0.0–1.0):
1. asset_quality     — Gross NPA %, Net NPA %, Provision Coverage Ratio (PCR)
2. net_interest      — NIM trend (8-quarter), CASA ratio quality
3. capital_adequacy  — CRAR/CET1 vs RBI minimum, tier-1 buffer
4. profitability     — RoA, RoE, credit cost trend, cost-to-income
5. loan_mix          — Retail vs corporate split, secured vs unsecured, MSME %

Return:
{{
  "overall_score": <0.0–1.0>,
  "sub_scores": {{
    "asset_quality": <float>,
    "net_interest": <float>,
    "capital_adequacy": <float>,
    "profitability": <float>,
    "loan_mix": <float>
  }},
  "key_positives": ["<point>", ...],
  "key_risks": ["<risk>", ...],
  "summary": "<2-3 sentence summary>",
  "data_freshness": "<quarter/date of data used>"
}}
"""
        return system, user

    def _parse_output(self, data: dict[str, Any], ticker: str) -> AgentOutput:
        return AgentOutput(
            agent=self.agent_name,
            ticker=ticker,
            overall_score=self._clamp(float(data.get("overall_score", 0.5))),
            key_positives=data.get("key_positives", []),
            key_risks=data.get("key_risks", []),
            summary=data.get("summary", ""),
            data_freshness=data.get("data_freshness", ""),
        )


# ──────────────────────────────────────────────────────────────────────────
# 2. Risk
# ──────────────────────────────────────────────────────────────────────────

class BFSIRiskAgent(BaseAgent):
    @property
    def agent_name(self) -> str:
        return "risk"

    def _build_prompt(self, query: StockQuery, context: str) -> tuple[str, str]:
        system = (
            "You are a credit risk specialist covering Indian banks and NBFCs. "
            "Identify structural risks that could impair capital or liquidity. "
            "Return ONLY valid JSON."
        )
        user = f"""
Risk assessment for {query.ticker} ({query.company_name}) as of {query.analysis_date}.

Context:
{context}

Evaluate:
1. asset_quality_trend — SMA/SMA-2 slippage, restructured book, watchlist
2. concentration_risk  — Top-5 borrower exposure, sectoral concentration
3. deposit_stability   — Wholesale deposit %, CASA trend, deposit run-off risk
4. regulatory_risk     — RBI/SEBI penalties pending, prompt corrective action risk
5. macro_sensitivity   — Rate sensitivity (NIM compression), FX exposure

Return:
{{
  "overall_score": <0.0–1.0>,
  "sub_scores": {{
    "asset_quality_trend": <float>,
    "concentration_risk": <float>,
    "deposit_stability": <float>,
    "regulatory_risk": <float>,
    "macro_sensitivity": <float>
  }},
  "key_positives": ["<point>", ...],
  "key_risks": ["<risk>", ...],
  "summary": "<2-3 sentence summary>",
  "data_freshness": "<quarter/date>"
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
# 3. Macro & Policy
# ──────────────────────────────────────────────────────────────────────────

class BFSIMacroPolicyAgent(BaseAgent):
    @property
    def agent_name(self) -> str:
        return "macro_policy"

    def _build_prompt(self, query: StockQuery, context: str) -> tuple[str, str]:
        system = (
            "You are a macro analyst covering the Indian banking system. "
            "Focus on RBI policy, systemic credit trends, and regulatory environment. "
            "Return ONLY valid JSON."
        )
        user = f"""
Macro & policy environment for {query.ticker} ({query.company_name}) as of {query.analysis_date}.

Context:
{context}

Evaluate:
1. rbi_rate_cycle      — Current repo rate, rate trajectory, MPC stance
2. system_credit       — System credit growth YoY, deposit growth, CD ratio
3. liquidity_conditions — LAF corridor, CRR/SLR impact, VRR/VRRR operations
4. regulatory_actions  — Recent RBI circulars, SEBI actions, IRDAI (if insurance)
5. fiscal_policy       — Government borrowing programme, PSU bank recap, IBC resolution pace

Return:
{{
  "overall_score": <0.0–1.0>,
  "sub_scores": {{
    "rbi_rate_cycle": <float>,
    "system_credit": <float>,
    "liquidity_conditions": <float>,
    "regulatory_actions": <float>,
    "fiscal_policy": <float>
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
# 4. Institutional & Insider Flows
# ──────────────────────────────────────────────────────────────────────────

class BFSIInstitutionalAgent(BaseAgent):
    @property
    def agent_name(self) -> str:
        return "institutional"

    def _build_prompt(self, query: StockQuery, context: str) -> tuple[str, str]:
        system = (
            "You are an equity market analyst tracking smart money flow for "
            "Indian banking stocks. Return ONLY valid JSON."
        )
        user = f"""
Institutional and insider flow analysis for {query.ticker} ({query.company_name}) as of {query.analysis_date}.

Context:
{context}

Evaluate:
1. fii_dii_flow       — Net FII/DII buying over 1M and 3M windows
2. promoter_holding   — Promoter stake change, pledge %
3. insider_trades     — ESOP exercises, open-market purchases/sales by insiders
4. analyst_changes    — Rating upgrades/downgrades, target price revisions
5. institutional_conc — Mutual fund holding %, top-10 institutional ownership

Return:
{{
  "overall_score": <0.0–1.0>,
  "sub_scores": {{
    "fii_dii_flow": <float>,
    "promoter_holding": <float>,
    "insider_trades": <float>,
    "analyst_changes": <float>,
    "institutional_conc": <float>
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

class BFSIPatternAgent(BaseAgent):
    @property
    def agent_name(self) -> str:
        return "pattern_analysis"

    def _build_prompt(self, query: StockQuery, context: str) -> tuple[str, str]:
        system = (
            "You are a technical analyst specialising in Indian banking stocks. "
            "Identify price cycles, seasonality, and momentum signals. "
            "Return ONLY valid JSON."
        )
        user = f"""
Technical and pattern analysis for {query.ticker} ({query.company_name}) as of {query.analysis_date}.

Context:
{context}

Evaluate:
1. price_cycle        — 10-year cycle position, rate-cut rally seasonality
2. momentum           — RSI (14d), MACD, Bollinger Band position
3. breakout_zones     — Key support/resistance, breakout or breakdown levels
4. relative_strength  — Performance vs Nifty Bank, Nifty PSU Bank indices
5. volume_pattern     — OBV trend, institutional accumulation/distribution

Return:
{{
  "overall_score": <0.0–1.0>,
  "sub_scores": {{
    "price_cycle": <float>,
    "momentum": <float>,
    "breakout_zones": <float>,
    "relative_strength": <float>,
    "volume_pattern": <float>
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
# 6. Universe Setup (index composition + peer context)
# ──────────────────────────────────────────────────────────────────────────

class BFSIUniverseAgent(BaseAgent):
    @property
    def agent_name(self) -> str:
        return "universe_setup"

    def _build_prompt(self, query: StockQuery, context: str) -> tuple[str, str]:
        system = (
            "You are a BFSI equity research analyst establishing the peer group "
            "and index context for a banking stock. Return ONLY valid JSON."
        )
        user = f"""
Universe setup and peer context for {query.ticker} ({query.company_name}) as of {query.analysis_date}.

Context:
{context}

Evaluate:
1. index_weight       — Weight in Nifty Bank / PSU Bank / Nifty 50 if applicable
2. peer_positioning   — Relative rank among PSU/Private/SFB/NBFC peers on key metrics
3. market_cap_tier    — Large/mid/small cap classification, free-float
4. corporate_actions  — Recent splits, bonuses, rights issues, merger events
5. rebalancing_risk   — Upcoming index rebalancing, inclusion/exclusion probability

Return:
{{
  "overall_score": <0.0–1.0>,
  "sub_scores": {{
    "index_weight": <float>,
    "peer_positioning": <float>,
    "market_cap_tier": <float>,
    "corporate_actions": <float>,
    "rebalancing_risk": <float>
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
    "fundamentals":      BFSIFundamentalsAgent(),
    "risk":              BFSIRiskAgent(),
    "macro_policy":      BFSIMacroPolicyAgent(),
    "institutional":     BFSIInstitutionalAgent(),
    "pattern_analysis":  BFSIPatternAgent(),
    "universe_setup":    BFSIUniverseAgent(),
}

WEIGHTS: dict[str, float] = {
    "fundamentals":     0.25,
    "risk":             0.20,
    "macro_policy":     0.20,
    "institutional":    0.15,
    "pattern_analysis": 0.15,
    "universe_setup":   0.05,
}

"""
core/intelligence/prompt_enhancer/enhancer.py
=============================================
P4 — PromptEnhancer: miss_counter → Search Queries

Reads the miss_counter from a ticker's LearningLedger and produces
additional context search queries for each agent, targeting the top-N
factors the system has historically missed.

Called once per month-start (generate_forecast.py). Output is cached in
a per-ticker JSON file for the cycle and loaded lazily by each agent at
run() time via PredictionStore.

Self-regulating behaviour
--------------------------
Enhancements are regenerated each month-start from the CURRENT miss_counter.
If a previously-missed factor stops appearing (queries found the data), its
count stays flat → it falls out of top_n → deprioritised automatically.

Query resolution order
-----------------------
1. Sector-specific template (SECTOR_MISS_FACTOR_TEMPLATES[sector][factor])
2. Generic cross-sector template (MISS_FACTOR_TO_QUERY_TEMPLATE[factor])
3. LLM-generated query (any factor with NO template in either map above)

LLM generation is only triggered for factors with no template entry — a
narrow, low-frequency path that fires at most once per unknown factor per
cycle.  The LLM generates 2 date-qualified, agent-specific queries and the
results are cached alongside template-generated ones in the enhancements JSON.
"""

from __future__ import annotations

import json
import logging
import time
from datetime import date
from pathlib import Path
from typing import TYPE_CHECKING

from core.config import settings
from services.clients.llm_client import JSON_MODE_EXTRA_BODY

if TYPE_CHECKING:
    from core.schemas.feedback import LearningLedger

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Generic cross-sector template map (automobile-focused, used as fallback)
# Placeholders: {ticker}, {date}, {month}, {year}
# ---------------------------------------------------------------------------

MISS_FACTOR_TO_QUERY_TEMPLATE: dict[str, dict[str, str]] = {
    "FII_outflow_spike": {
        "risk_macro": "{ticker} FII DII net flows provisional {date}",
        "sentiment":  "FII selling India equity {month} {year}",
    },
    "crude_oil_spot_price": {
        "raw_materials": "Brent crude spot price today {date}",
        "risk_macro":    "crude oil impact Indian automobile sector {month}",
    },
    "RBI_policy_surprise": {
        "risk_macro":   "RBI MPC meeting upcoming schedule {year}",
        "fundamentals": "RBI repo rate decision impact auto loan rates",
    },
    "INR_depreciation": {
        "risk_macro":    "USD INR exchange rate {date}",
        "raw_materials": "INR depreciation impact import cost automobile {year}",
    },
    "month_end_inventory_flush": {
        "sales_demand": "{ticker} dealer inventory days channel check {month}",
    },
}


# ---------------------------------------------------------------------------
# Sector-specific templates — each key is a sector name matching sector param.
# These take priority over MISS_FACTOR_TO_QUERY_TEMPLATE for the given sector.
# ---------------------------------------------------------------------------

SECTOR_MISS_FACTOR_TEMPLATES: dict[str, dict[str, dict[str, str]]] = {

    "automobile": {
        "FADA_dispatch_miss": {
            "sales_demand":   "FADA retail dispatch {ticker} {month} {year}",
            "fundamentals":   "{ticker} wholesale vs retail channel inventory days {month} {year}",
        },
        "EV_penetration_spike": {
            "competitive_intel": "EV electric vehicle sales share India {month} {year}",
            "risk_macro":        "{ticker} ICE cannibalisation EV market share impact {year}",
        },
        "steel_aluminium_cost": {
            "raw_materials":  "India HRC hot-rolled coil steel price {month} {year}",
            "risk_macro":     "aluminium LME price India import cost automobile {month}",
        },
        "dealer_inventory_flush": {
            "sales_demand":   "{ticker} dealer inventory channel check days on ground {month} {year}",
            "competitive_intel": "India two-wheeler four-wheeler inventory FADA channel {month} {year}",
        },
        "crude_rubber_cost": {
            "raw_materials":  "natural rubber price India TOCOM {month} {year}",
            "risk_macro":     "Brent crude impact India automobile input cost {month}",
        },
        "CAFE_regulatory_compliance": {
            "policy_regulatory": "India CAFE 2.0 norms compliance cost OEM {year}",
            "risk_macro":        "{ticker} fleet average fuel efficiency regulatory penalty {year}",
        },
        "semiconductor_supply": {
            "risk_macro":     "automotive semiconductor chip shortage India {month} {year}",
            "fundamentals":   "{ticker} production volume constraint semiconductor {year}",
        },
        "OEM_market_share_shift": {
            "competitive_intel": "India passenger vehicle market share OEM {month} {year} SIAM",
            "sales_demand":      "{ticker} vs competitors retail market share gain loss {month}",
        },
        "export_decline": {
            "sales_demand":   "{ticker} export sales volume {month} {year} SIAM data",
            "risk_macro":     "India automobile export demand Middle East Africa {year}",
        },
        "FII_outflow_spike": {
            "risk_macro":     "{ticker} FII DII net flows provisional {date}",
            "sentiment":      "FII selling India automobile sector {month} {year}",
        },
    },

    "banking_bfsi": {
        "GNPA_slippage": {
            "fundamentals": "{ticker} GNPA NPA slippage Q quarterly results {month} {year}",
            "risk":         "India banking sector NPA slippage trend {month} {year}",
        },
        "NIM_compression": {
            "fundamentals": "{ticker} net interest margin NIM Q results {month} {year}",
            "macro_policy": "India bank NIM trend repo rate impact {year}",
        },
        "credit_cost_spike": {
            "fundamentals": "{ticker} credit cost provisioning quarterly {month} {year}",
            "risk":         "{ticker} loan book stress credit cost guidance {year}",
        },
        "CASA_outflow": {
            "fundamentals": "{ticker} CASA ratio savings deposit growth {month} {year}",
            "macro_policy": "India bank deposit growth CASA competitive pressure {year}",
        },
        "RBI_regulatory_action": {
            "macro_policy": "RBI banking regulatory circular action {month} {year}",
            "risk":         "{ticker} RBI inspection observation compliance {year}",
        },
        "system_credit_slowdown": {
            "macro_policy": "India bank credit growth RBI data {month} {year}",
            "fundamentals": "{ticker} loan book growth quarterly guidance {year}",
        },
        "IBC_resolution_delay": {
            "risk":         "{ticker} IBC NCLT resolution stressed asset update {year}",
            "fundamentals": "India banking sector NPA recovery IBC timeline {year}",
        },
        "FII_outflow_spike": {
            "institutional": "{ticker} FII DII shareholding change quarterly {month} {year}",
            "macro_policy":  "FII selling India banking sector {month} {year}",
        },
        "RBI_policy_surprise": {
            "macro_policy": "RBI MPC repo rate decision banking impact {month} {year}",
            "fundamentals": "RBI rate change net interest margin bank profitability {year}",
        },
        "INR_depreciation": {
            "macro_policy": "USD INR exchange rate impact bank forex book {date}",
            "risk":         "{ticker} forex hedging exposure USD liabilities {year}",
        },
    },

    "it_sector": {
        "attrition_spike": {
            "fundamentals": "{ticker} attrition rate quarterly employee headcount {month} {year}",
            "risk_macro":   "India IT sector attrition wage cost pressure {year}",
        },
        "deal_win_slowdown": {
            "fundamentals": "{ticker} TCV deal wins quarterly results {month} {year}",
            "peer_benchmark": "{ticker} deal pipeline bookings update {month} {year}",
        },
        "US_tech_spend_cut": {
            "global_macro":   "US enterprise IT spending Gartner IDC outlook {year}",
            "fundamentals":   "{ticker} US revenue demand commentary {month} {year}",
        },
        "H1B_visa_restriction": {
            "risk_macro":     "H1B visa denial rate US immigration IT services {year}",
            "global_macro":   "India IT H1B visa impact onsite cost {year}",
        },
        "BFSI_vertical_weakness": {
            "fundamentals":   "{ticker} BFSI vertical revenue mix quarterly {month} {year}",
            "transcript_nlp": "{ticker} earnings call BFSI client commentary {month} {year}",
        },
        "guidance_cut": {
            "transcript_nlp": "{ticker} earnings guidance revenue outlook {month} {year}",
            "peer_benchmark": "India IT sector revenue guidance {month} {year}",
        },
        "AI_disruption_risk": {
            "risk_macro":     "AI automation impact IT services revenue {year}",
            "fundamentals":   "{ticker} AI GenAI deal pipeline revenue contribution {year}",
        },
        "USD_INR_headwind": {
            "global_macro":   "USD INR exchange rate impact IT revenue {date}",
            "fundamentals":   "{ticker} FX hedge coverage USD receivables {year}",
        },
        "FII_outflow_spike": {
            "insider_smart_money": "{ticker} FII DII shareholding change {month} {year}",
            "global_macro":        "FII selling India IT sector {month} {year}",
        },
        "RBI_policy_surprise": {
            "global_macro": "RBI rate decision IT sector rupee impact {month} {year}",
            "risk_macro":   "India macro rate policy IT services demand outlook {year}",
        },
    },

    "renewable_energy": {
        "DISCOM_payment_delay": {
            "risk":              "{ticker} DISCOM receivables payment delay days {month} {year}",
            "fundamentals":      "India state DISCOM payment overdue renewable energy {year}",
        },
        "MNRE_auction_cancellation": {
            "sentiment_policy":  "MNRE renewable energy auction cancellation tender {month} {year}",
            "business":          "India solar wind auction awarded capacity {month} {year}",
        },
        "curtailment_risk": {
            "risk":              "{ticker} grid curtailment solar wind generation loss {year}",
            "fundamentals":      "India renewable energy grid curtailment state {year}",
        },
        "module_price_spike": {
            "sentiment_policy":  "China solar module price per watt {month} {year}",
            "valuation":         "solar panel cost LCOE impact India project {year}",
        },
        "PPA_counterparty_risk": {
            "risk":              "{ticker} PPA counterparty DISCOM credit rating {year}",
            "business":          "{ticker} power purchase agreement offtaker profile {year}",
        },
        "RBI_rate_impact": {
            "sentiment_policy":  "RBI rate decision project finance renewable energy cost {month} {year}",
            "valuation":         "India RE project IRR WACC interest rate sensitivity {year}",
        },
        "tariff_revision": {
            "sentiment_policy":  "MNRE CERC tariff revision renewable energy {month} {year}",
            "valuation":         "{ticker} tariff locked blended average PPA {year}",
        },
        "execution_delay": {
            "risk":              "{ticker} capacity commissioning delay project update {month} {year}",
            "business":          "{ticker} under construction pipeline progress {year}",
        },
        "FII_outflow_spike": {
            "technical":         "{ticker} FII DII institutional shareholding {month} {year}",
            "sentiment_policy":  "FII selling India renewable energy sector {month} {year}",
        },
        "crude_oil_spot_price": {
            "sentiment_policy":  "crude oil price impact renewable energy demand {month}",
            "valuation":         "India energy transition fossil fuel vs renewable cost {year}",
        },
    },
}


# ---------------------------------------------------------------------------
# LLM system prompt for dynamic query generation
# ---------------------------------------------------------------------------

_LLM_QUERY_GEN_SYSTEM = """\
You are a financial data analyst generating targeted web search queries for an AI stock analysis system.

Given a ticker, sector, agent role, and a missed factor (something the system consistently failed to \
find data for), generate exactly 2 precise search queries.

Rules:
- Each query must be specific enough to return actual financial data, not general articles.
- Always include the current month and year in at least one query.
- Use terminology specific to the sector (e.g. "GNPA slippage" for banking, "TCV deal wins" for IT).
- Target sources that publish this data: NSE, BSE, company investor relations, SEBI, RBI, MNRE, SIAM, FADA.
- Do NOT generate generic queries. "MARUTI stock news" is useless. "MARUTI FADA retail dispatch April 2026" is good.
- Return ONLY valid JSON: {"queries": ["<query1>", "<query2>"]}
"""


class PromptEnhancer:
    """
    Builds extra search queries from the ticker's miss history.

    Query resolution order per (factor, agent) pair:
      1. Sector-specific template
      2. Generic cross-sector template
      3. LLM generation (only for factors with no template in either map)
    """

    MISS_FACTOR_TO_QUERY_TEMPLATE = MISS_FACTOR_TO_QUERY_TEMPLATE
    SECTOR_MISS_FACTOR_TEMPLATES  = SECTOR_MISS_FACTOR_TEMPLATES

    def enhance(
        self,
        ticker: str,
        learning_ledger: "LearningLedger",
        sector: str = "automobile",
        top_n: int = 3,
    ) -> dict[str, list[str]]:
        """
        Build extra search queries from the top-N missed factors.

        Returns {agent_name: [extra_query_1, extra_query_2, ...]}
        Returns {} when miss_counter is empty (first cycle — no history yet).
        """
        miss_counter = learning_ledger.miss_counter
        if not miss_counter:
            return {}

        # RL Intelligence Phase, Component 3 — recency-weighted miss ranking.
        # When enabled, rank factors by recency_weighted_miss_scores() so recent
        # misses outrank old, frequent ones (and external_shock-type misses are
        # discounted). Falls back to raw miss_counter ranking when the flag is
        # off, or when miss_events is empty (legacy ledgers — scores reduce to
        # the raw counts anyway, but we keep the explicit fallback for clarity
        # and byte-identical ordering on ties).
        if getattr(settings, "RL_FORGETTING_ENABLED", True) and learning_ledger.miss_events:
            scores = learning_ledger.recency_weighted_miss_scores()
            sorted_factors = sorted(
                miss_counter.items(), key=lambda kv: scores.get(kv[0], 0.0), reverse=True
            )
        else:
            sorted_factors = sorted(miss_counter.items(), key=lambda kv: kv[1], reverse=True)
        top_factors = [factor for factor, _ in sorted_factors[:top_n]]

        today = date.today()
        fmt = {
            "ticker": ticker,
            "date":   today.isoformat(),
            "month":  today.strftime("%B"),
            "year":   str(today.year),
        }

        sector_templates = self.SECTOR_MISS_FACTOR_TEMPLATES.get(sector, {})
        agent_queries: dict[str, list[str]] = {}
        llm_needed: list[tuple[str, str]] = []  # (factor, primary_agent) pairs needing LLM

        for factor in top_factors:
            # Resolution order: sector-specific → generic → LLM
            agent_templates = (
                sector_templates.get(factor)
                or self.MISS_FACTOR_TO_QUERY_TEMPLATE.get(factor)
            )

            if agent_templates:
                for agent_name, template in agent_templates.items():
                    try:
                        query = template.format(**fmt)
                    except KeyError as exc:
                        logger.warning(
                            "[PromptEnhancer] Template placeholder error '%s': %s", factor, exc
                        )
                        query = template
                    agent_queries.setdefault(agent_name, []).append(query)
            else:
                # No template for this factor in any map — queue for LLM generation
                primary_agent = self._guess_primary_agent(factor, sector)
                llm_needed.append((factor, primary_agent))
                logger.debug(
                    "[PromptEnhancer] No template for '%s' in sector '%s' — queuing LLM",
                    factor, sector,
                )

        # Batch LLM calls for unknown factors (one call per factor, not per agent).
        # Wrapped in try/except so a failing LLM call never blocks enhance().
        for factor, agent_name in llm_needed:
            try:
                llm_queries = self._generate_queries_llm(
                    factor=factor,
                    ticker=ticker,
                    sector=sector,
                    agent_name=agent_name,
                    fmt=fmt,
                )
                if llm_queries:
                    agent_queries.setdefault(agent_name, []).extend(llm_queries)
            except Exception as exc:
                logger.warning(
                    "[PromptEnhancer] LLM query generation failed for factor '%s' (non-fatal): %s",
                    factor, exc,
                )

        logger.info(
            "[PromptEnhancer] %s/%s | top-%d factors %s → %d agents enhanced "
            "(%d via LLM, %d via template)",
            ticker, sector, top_n, top_factors,
            len(agent_queries), len(llm_needed),
            len(top_factors) - len(llm_needed),
        )
        return agent_queries

    # ------------------------------------------------------------------
    # LLM query generation for unknown factors
    # ------------------------------------------------------------------

    def _generate_queries_llm(
        self,
        factor: str,
        ticker: str,
        sector: str,
        agent_name: str,
        fmt: dict[str, str],
    ) -> list[str]:
        """
        Ask LLM to generate 2 targeted, date-qualified search queries for a
        factor that has no template in either template map.

        Returns list of query strings (empty on any failure — non-fatal).
        """
        user_prompt = (
            f"Ticker: {ticker} (sector: {sector})\n"
            f"Agent role: {agent_name}\n"
            f"Missed factor: {factor}\n"
            f"Today: {fmt['date']} ({fmt['month']} {fmt['year']})\n\n"
            f"This system has repeatedly failed to find data for '{factor}' "
            f"when analysing {ticker} ({sector} sector).\n"
            f"Generate 2 precise search queries for the '{agent_name}' analyst "
            f"to find current {factor} data. Include the current month and year."
        )
        try:
            from openai import OpenAI
            client = OpenAI(
                api_key=settings.OPENROUTER_API_KEY,
                base_url=settings.OPENROUTER_BASE_URL,
                timeout=settings.LLM_TIMEOUT_SECONDS,
            )
            resp = client.chat.completions.create(
                model=settings.LLM_MODEL,
                temperature=0.1,
                max_tokens=120,
                messages=[
                    {"role": "system", "content": _LLM_QUERY_GEN_SYSTEM},
                    {"role": "user",   "content": user_prompt},
                ],
                response_format={"type": "json_object"},
                extra_body=JSON_MODE_EXTRA_BODY,
            )
            raw = resp.choices[0].message.content or "{}"
            data = json.loads(raw)
            queries = [str(q) for q in data.get("queries", [])[:2]]
            logger.info(
                "[PromptEnhancer] LLM generated %d queries for factor '%s' (agent=%s)",
                len(queries), factor, agent_name,
            )
            return queries
        except Exception as exc:
            logger.warning(
                "[PromptEnhancer] LLM query generation failed for factor '%s': %s",
                factor, exc,
            )
            return []

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _guess_primary_agent(factor: str, sector: str) -> str:
        """
        Heuristic: pick the most likely agent to benefit from data on this factor.
        Used only when there is no template to derive an agent name from.
        """
        factor_lower = factor.lower()

        # Sector-specific policy signals — checked BEFORE the generic "policy" keyword
        # so "MNRE_policy_reversal" routes to sentiment_policy, not risk_macro.
        # RE-sector policy signals (auction, subsidy, tariff) → sentiment_policy
        if sector == "renewable_energy" and any(
            k in factor_lower for k in ("mnre", "fame", "pli", "subsidy", "tariff", "rpo", "ists")
        ):
            return "sentiment_policy"
        if any(k in factor_lower for k in ("gnpa", "nim", "npa", "casa", "crar", "ibc",
                                            "slippage", "pcr", "credit_cost")):
            return "fundamentals"
        # Cross-sector signal words
        if any(k in factor_lower for k in ("fii", "dii", "institutional", "shareholding")):
            return "institutional" if sector == "banking_bfsi" else "risk_macro"
        if any(k in factor_lower for k in ("rbi", "rate", "repo", "mpc")):
            return "macro_policy" if sector == "banking_bfsi" else "risk_macro"
        if any(k in factor_lower for k in ("macro", "global", "fed", "usd", "inr", "crude")):
            return "global_macro" if sector == "it_sector" else "risk_macro"
        if any(k in factor_lower for k in ("revenue", "margin", "earnings",
                                            "attrition", "deal", "tcv", "capacity", "ebitda")):
            return "fundamentals"
        if any(k in factor_lower for k in ("sentiment", "news", "management", "tone")):
            return "sentiment" if sector != "banking_bfsi" else "institutional"
        if any(k in factor_lower for k in ("technical", "rsi", "macd", "breakout", "support")):
            return "pattern_analysis"
        if any(k in factor_lower for k in ("risk", "execution", "pledge", "concentration",
                                            "discom", "curtailment", "ppa_counter")):
            return "risk"
        if any(k in factor_lower for k in ("valuation", "pe", "ev", "dcf", "irr", "target")):
            return "valuation"
        if any(k in factor_lower for k in ("policy", "regulation")):
            return "sentiment_policy" if sector == "renewable_energy" else "policy_regulatory"

        # Sector-level default agent
        sector_defaults = {
            "banking_bfsi":    "fundamentals",
            "it_sector":       "fundamentals",
            "renewable_energy":"fundamentals",
            "automobile":      "risk_macro",
        }
        return sector_defaults.get(sector, "risk_macro")

    def save_enhancements(
        self,
        ticker: str,
        sector: str,
        enhancements: dict[str, list[str]],
        cycle_id: str,
        learning_ledger: "LearningLedger | None" = None,
    ) -> None:
        """
        Persist enhancements to:
          data/predictions/{sector}/{ticker}/{cycle_id}_prompt_enhancements.json

        The payload records which queries came from a template vs LLM so the
        miss-reduction loop can be audited: if LLM-generated queries successfully
        find the data, miss_count for that factor stops growing → it falls out of
        top_n next cycle → LLM call no longer fires.
        """
        base_dir = Path(settings.PREDICTION_DATA_DIR)
        target_dir = base_dir / sector / ticker.upper()
        target_dir.mkdir(parents=True, exist_ok=True)

        path = target_dir / f"{cycle_id}_prompt_enhancements.json"
        tmp  = path.with_suffix(".tmp")

        miss_snapshot: dict[str, int] = {}
        if learning_ledger is not None:
            miss_snapshot = dict(learning_ledger.miss_counter)

        payload = {
            "ticker":                ticker.upper(),
            "sector":                sector,
            "cycle_id":              cycle_id,
            "generated_at":          date.today().isoformat(),
            "based_on_miss_counter": miss_snapshot,
            "agent_enhancements":    enhancements,
        }
        tmp.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        tmp.replace(path)
        logger.info(
            "[PromptEnhancer] Saved enhancements for %s/%s cycle %s (%d agents enhanced)",
            ticker, sector, cycle_id, len(enhancements),
        )

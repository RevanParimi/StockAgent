"""
prompts/risk_macro.py
=====================
All prompt templates for the Risk & Macro agent.
"""

SYSTEM_PROMPT = """You are a macro-economic and sector risk analyst covering Indian automobile OEMs.
You specialise in:
- Currency risk: INR/USD exchange rate impact on revenue (exports) and costs (imports)
- Commodity prices: Steel, Aluminium, Rubber – the three largest raw material cost drivers
- Monetary policy: RBI repo rate trajectory and its effect on auto loan EMIs / demand
- Regulatory risk: Emission norms (BS6, CAFE), EV mandate timelines, safety regulations
- Global geopolitical risk: oil supply shocks, FII outflows, INR depreciation pressure,
  supply chain disruption (China semiconductors, rare earth, EV components)

You provide a risk-adjusted score, where high risk = low score.
"""

ANALYSIS_PROMPT = """Analyse the Risk & Macro outlook for Indian automobile company: **{ticker}** ({company_name}).

{business_model_context}

Score each dimension from 0.0 (high risk / bearish) to 1.0 (low risk / bullish):

1. **INR/USD & Crude Oil Revenue Exposure** – Net forex position; crude impact on input costs
2. **Steel / Aluminium / Rubber Prices** – Commodity cycle position and hedging status
3. **RBI Repo Rate & EMI Impact** – Rate environment effect on retail financing demand
4. **Emission Norms & Policy Risk** – Compliance readiness; regulatory tailwinds/headwinds
5. **Global Geopolitical Risk** – Four transmission channels (internal weights):
   - Oil price shock (40%): energy cost spike → input costs + consumer squeeze
   - FII outflow / risk-off (30%): capital flight from EMs → Nifty selloff → auto de-rating
   - INR depreciation during crisis (20%): import-heavy OEMs hurt via higher component costs
   - Supply chain disruption — sanctions/blockades (10%): semiconductor / component shortage

Context / recent data:
{context}

Return ONLY valid JSON. IMPORTANT: Be ticker-specific. Cite actual macro data values.
For key_positives/key_risks: quote specific levels (e.g. "Crude at $78/bbl; every $10 rise compresses margin ~80bps for MARUTI").
For ticker_vs_peers: cite relative macro exposure vs named peers (e.g. "MARUTI 15% export revenue vs BAJAJ-AUTO 45%; lower USD exposure").
For bull_case_if: name the specific macro tailwind + threshold (e.g. "If crude falls to $65/bbl, margin expands 120-150bps").
For bear_case_if: name the specific macro risk + quantified impact (e.g. "If crude >$90/bbl sustained, EBITDA margin compresses 100-150bps").
For what_changed: cite what shifted in macro environment this cycle vs last (e.g. "RBI cut 25bps; INR strengthened 2% vs USD").

{{
  "agent": "risk_macro",
  "ticker": "{ticker}",
  "overall_score": <float 0.0-1.0>,
  "sub_scores": {{
    "inr_usd_crude_exposure": <float>,
    "commodity_prices": <float>,
    "rbi_repo_emi_impact": <float>,
    "emission_policy_risk": <float>,
    "global_geopolitical_risk": <float>
  }},
  "key_positives": [<string>, ...],
  "key_risks": [<string>, ...],
  "summary": "<2-3 sentence narrative>",
  "data_freshness": "<date of most recent data point used>",
  "ticker_vs_peers": "<relative macro exposure vs named peers with specific % or bps figures>",
  "bull_case_if": "<specific macro tailwind + threshold that would add ~0.15 to score>",
  "bear_case_if": "<specific macro risk + quantified margin/earnings impact that would cut ~0.15 from score>",
  "what_changed": "<what shifted in macro environment this cycle vs last, with specific numbers>",
  "data_confidence": <float 0.3-1.0>
}}
"""

CONTEXT_SEARCH_QUERIES = [
    "INR USD exchange rate {date} India automobile exports",
    "steel aluminium rubber prices India {month} {year}",
    "RBI repo rate {year} auto loan EMI demand impact",
    "India emission norms BS6 CAFE {company_name} compliance {year}",
    "global geopolitical risk oil FII outflow India auto sector {year}",
    "China semiconductor supply chain India EV components disruption {year}",
    "US Iran tensions oil price India stock market {year}",
    "FII outflow India {month} {year} global risk-off",
    "INR depreciation {year} India automobile import cost",
    "global geopolitical risk India emerging market {year}",
]

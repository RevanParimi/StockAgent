"""
prompts/renewable/macro.py
============================
Prompt templates for the Renewable Energy Macro & Policy agent.

Framework source: sector_analysis_v4_final.html — Renewable Energy > Macro pillar
Key macro drivers: MNRE auctions, RBI rate cycles, solar module prices, DISCOM health
"""

SYSTEM_PROMPT = """You are a macro and policy analyst specialising in Indian renewable energy.
You track:

1. **MNRE Auction Pipelines** — Ministry of New & Renewable Energy tenders and awards.
   GW awarded per quarter, tariff discovery trend (L1 rates), bid pipeline depth.
   High auction volume = strong future revenue visibility for IPPs.

2. **RBI Rate Cycles** — RE projects are funded by long-term debt. Rate sensitivity:
   1% fall in interest rates → ~1.5-2% improvement in project equity IRR.
   Rate cut cycles are among the most reliable re-rating triggers for RE stocks.

3. **Solar Module Prices** — Module prices (primarily set by Chinese manufacturers)
   affect project capex. Falling prices → cheaper projects → better economics.
   Rising prices (polysilicon shortage, anti-dumping duties) → margin squeeze.

4. **State DISCOM Financial Health** — Most RE power is purchased by state electricity
   distribution companies. Financially stressed DISCOMs → payment delays of 6-18 months.
   UDAY 2.0 / RDSS compliance, state-level subsidy support are key indicators.

Key data sources: MNRE website, RBI monetary policy statements, BloombergNEF module
price index, MoPNG DISCOM health reports, Union Budget RE capex line items.
"""

ANALYSIS_PROMPT = """Analyse the Macro & Policy environment for Indian renewable energy company: **{ticker}** ({company_name}).

Score each dimension from 0.0 (very bearish) to 1.0 (very bullish):

1. **MNRE Auction Health** — Recent auction GW awarded, current tender pipeline, L1 tariff
   trend (falling tariffs = competitive pressure; stable/rising = rational market).
   Is the government meeting its annual auction targets (40-50 GW/year goal)?

2. **RBI Rate Cycle** — Current repo rate trajectory. Rate cut cycle = positive re-rating
   catalyst. Rate hike cycle = negative for high-leverage RE companies.
   Every 50bps cut can add 100-150bps to project IRR.

3. **Solar Module Price Trend** — Current module prices vs 12-month ago.
   Falling prices = lower project capex = better pipeline economics.
   Rising prices = cost inflation risk on under-construction capacity.

4. **DISCOM Financial Health** — State DISCOM payment record, RDSS compliance status,
   payment guarantee mechanisms (LCs, escrow from state revenues), federal support.
   Poor DISCOM health = cash flow risk for IPPs.

5. **Green Hydrogen & Policy Tailwinds** — RPO (Renewable Purchase Obligation) targets,
   must-run status continuation, ISTS waiver extension, green hydrogen mission funding.
   Strong policy support = structural demand floor for RE capacity.

Context / recent data snippets:
{context}

Return ONLY valid JSON:
{{
  "agent": "macro",
  "ticker": "{ticker}",
  "overall_score": <float 0.0-1.0>,
  "sub_scores": {{
    "mnre_auction_health": <float>,
    "rbi_rate_cycle": <float>,
    "module_price_trend": <float>,
    "discom_financial_health": <float>,
    "policy_tailwinds": <float>
  }},
  "key_positives": [<string>, ...],
  "key_risks": [<string>, ...],
  "summary": "<2-3 sentence narrative>",
  "data_freshness": "<date of most recent data point used>"
}}
"""

CONTEXT_SEARCH_QUERIES = [
    "MNRE renewable energy auction GW awarded tender {year}",
    "RBI repo rate cut monetary policy renewable energy impact {year}",
    "solar module panel price BloombergNEF India {year}",
    "{company_name} DISCOM payment delay receivables {year}",
    "India RPO renewable purchase obligation ISTS waiver green hydrogen {year}",
]

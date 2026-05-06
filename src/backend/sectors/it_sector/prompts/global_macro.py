"""
prompts/global_macro.py — IT Sector
======================================
Covers US tech spend, Fed rate impact on client capex, USD/INR, geopolitical risk,
RBI repo rate sensitivity, regulatory changes (SEBI/MCA IT rules), and M&A activity.
Sources: yfinance (INR=X for USD/INR), Serper (6 queries ~275 tokens each).
"""

SYSTEM_PROMPT = """You are a global macro analyst tracking demand drivers and risk factors for Indian IT companies.
You have deep expertise in:
- US enterprise IT spending cycle: cloud, software, BPO/ITO budget trends
- Federal Reserve rate decisions and their impact on client capex discretionary spend
- USD/INR exchange rate impact on revenue and margin hedging for Indian IT exporters
- Geopolitical risks: US-China tech decoupling, CHIPS Act, nearshore vs offshore shift
- SEBI/MCA regulatory changes affecting IT sector listing and governance
- Global IT M&A multiples as valuation benchmarks

Score 1.0 = US IT spend accelerating, Fed cutting rates, INR depreciating (revenue tailwind), benign geopolitics.
Score 0.0 = US tech spend freeze, Fed hiking, INR appreciating (revenue headwind), adverse regulation.
"""

ANALYSIS_PROMPT = """Analyse the Global Macro & News environment for Indian IT company: **{ticker}** ({company_name}).

Score each dimension from 0.0 (very bearish) to 1.0 (very bullish):

1. **us_tech_spend** — US enterprise IT spending cycle (Gartner/IDC estimates);
   cloud capex from hyperscalers (AWS, Azure, GCP) as a proxy for enterprise demand;
   Fortune-500 CIO survey signals; US software and BPO outsourcing budget trends.

2. **fed_rate_impact** — Fed funds rate trajectory and impact on client capex decisions;
   rate cuts = client confidence returning, rate hikes = discretionary spend freeze;
   US recession probability index (Fed model, yield curve inversion signal).

3. **usd_inr** — USD/INR spot rate trend (INR weakening = revenue/margin tailwind for exporters);
   hedge ratio (% of forward book covered); natural hedge from US cost base;
   INR appreciation risk if RBI intervenes.

4. **geopolitical** — US-China tech war: Indian IT as beneficiary of China+1 strategy;
   CHIPS Act: semiconductor onshoring requiring more IT services;
   H1B reform risk (separate from visa_risk in Risk agent);
   SEBI/MCA IT-sector regulatory changes.

5. **ma_activity** — Global IT M&A deal multiples (EV/Revenue for SaaS/services);
   recent Indian IT M&A (Infosys buying US firm = growth signal);
   consolidation trend: larger deals reducing competitive fragmentation;
   private equity IT buyout activity as valuation floor signal.

Context / recent data snippets:
{context}

Return ONLY valid JSON:
{{
  "agent": "global_macro",
  "ticker": "{ticker}",
  "overall_score": <float 0.0-1.0>,
  "sub_scores": {{
    "us_tech_spend": <float>,
    "fed_rate_impact": <float>,
    "usd_inr": <float>,
    "geopolitical": <float>,
    "ma_activity": <float>
  }},
  "key_positives": ["<string>", "..."],
  "key_risks": ["<string>", "..."],
  "summary": "<2-3 sentence narrative on US IT demand cycle, Fed impact, and key macro risks>",
  "data_freshness": "<date of most recent macro data used>"
}}
"""

CONTEXT_SEARCH_QUERIES = [
    "US IT spending enterprise software cloud capex {year}",
    "Federal Reserve rate decision impact US tech capex {year}",
    "USD INR exchange rate impact Indian IT revenue {month} {year}",
    "US China tech war CHIPS Act offshoring nearshore Indian IT {year}",
    "global IT M&A deal multiples software consolidation {year}",
]

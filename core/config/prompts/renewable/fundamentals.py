"""
prompts/renewable/fundamentals.py
===================================
Prompt templates for the Renewable Energy Fundamentals agent.

Framework source: sector_analysis_v4_final.html — Renewable Energy > Fundamentals pillar
Primary metrics: DSCR, CUF, EBITDA/MW, LCOE, Net Debt/EBITDA
"""

SYSTEM_PROMPT = """You are a project-finance analyst specialising in Indian renewable energy.
You have deep expertise in:
- DSCR (Debt Service Coverage Ratio): the single most critical solvency metric for RE IPPs
- CUF (Capacity Utilisation Factor): actual generation vs theoretical maximum
- EBITDA/MW: normalised profitability comparison across companies of different sizes
- LCOE (Levelised Cost of Energy): total lifetime cost per unit of electricity generated
- Net Debt/EBITDA: leverage assessment — 5-8x is typical, >10x is concerning

Key benchmarks:
- DSCR: >1.3x = comfortable, <1.1x = dangerous
- CUF: Solar 20-25%, Wind 25-35% (site-dependent), Hydro 35-45%
- Net Debt/EBITDA: 5-8x typical for Indian RE IPPs; declining trend signals health
- EBITDA/MW: compare within peers — higher margins signal better tariff rates or lower O&M

Return structured, quantitative output grounded in BSE/NSE filings, project reports,
and CERC/SERC tariff orders.
"""

ANALYSIS_PROMPT = """Analyse the Fundamental outlook for Indian renewable energy company: **{ticker}** ({company_name}).

Score each dimension from 0.0 (very bearish) to 1.0 (very bullish):

1. **DSCR (Debt Service Coverage Ratio)** — Operating Cash Flow ÷ Total Debt Service.
   >1.3x = score 0.8-1.0. 1.1-1.3x = 0.5-0.7. <1.1x = 0.0-0.4.
   Check project-level DSCR, not just consolidated — a healthy blended DSCR can mask
   cash-flow-negative individual projects.

2. **CUF (Capacity Utilisation Factor)** — Actual generation vs theoretical maximum.
   Solar benchmark 20-25%, Wind 25-35%. Below benchmark = site quality or equipment issues.
   Above benchmark = premium asset quality.

3. **EBITDA/MW** — EBITDA per megawatt of operational capacity. Compare vs peers.
   Higher EBITDA/MW = better tariff rates, lower O&M costs, or superior technology mix.

4. **LCOE** — Levelised Cost of Energy. Companies with lower LCOE can bid lower tariffs
   at MNRE auctions while remaining profitable. Track trend — declining LCOE = improving
   competitiveness.

5. **Net Debt/EBITDA** — Leverage ratio. 5-8x is typical for asset-heavy RE. Track
   direction: declining ratio = financial health improving. >10x = distress territory.

Context / recent data snippets:
{context}

Return ONLY valid JSON:
{{
  "agent": "fundamentals",
  "ticker": "{ticker}",
  "overall_score": <float 0.0-1.0>,
  "sub_scores": {{
    "dscr": <float>,
    "cuf": <float>,
    "ebitda_per_mw": <float>,
    "lcoe": <float>,
    "net_debt_ebitda": <float>
  }},
  "key_positives": [<string>, ...],
  "key_risks": [<string>, ...],
  "summary": "<2-3 sentence narrative>",
  "data_freshness": "<date of most recent data point used>"
}}
"""

CONTEXT_SEARCH_QUERIES = [
    "{ticker} DSCR debt service coverage ratio project {year}",
    "{ticker} CUF capacity utilisation factor generation MU {year}",
    "{company_name} EBITDA per MW operational metrics {year}",
    "{ticker} net debt EBITDA leverage ratio {quarter} {year}",
    "{company_name} LCOE levelised cost energy tariff auction {year}",
]

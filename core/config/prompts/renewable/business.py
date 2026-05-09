"""
prompts/renewable/business.py
==============================
Prompt templates for the Renewable Energy Business Quality agent.

Framework source: sector_analysis_v4_final.html — Renewable Energy > Business pillar
Key question: Is this an IPP (bond-like recurring PPA revenue) or a manufacturer
(cyclical, commodity-price exposed)?
"""

SYSTEM_PROMPT = """You are an energy sector analyst evaluating the business quality of
Indian renewable energy companies. You specialise in:
- Distinguishing IPPs (Independent Power Producers) from equipment manufacturers
- Assessing Power Purchase Agreement (PPA) quality: tariff, tenor, counterparty
- Evaluating capacity pipeline credibility and execution track record
- Analysing land bank readiness and grid evacuation connectivity
- Benchmarking subsector mix (Solar / Wind / Hydro / Hybrid) for technology risk

Key benchmarks:
- PPA coverage: 90%+ of capacity under PPA = low revenue risk
- Pipeline: 3-5x current operational capacity = healthy growth visibility
- Central govt counterparty (SECI, NTPC) > state DISCOM in credit quality
- Land readiness: construction-ready land is the only activated pipeline

Return structured, quantitative output grounded in BSE/NSE filings,
MNRE project data, and company investor presentations.
"""

ANALYSIS_PROMPT = """Analyse the Business Quality of Indian renewable energy company: **{ticker}** ({company_name}).

Score each dimension from 0.0 (very bearish) to 1.0 (very bullish):

1. **Business Model Clarity (IPP vs Manufacturer)** — Is the company an IPP earning
   stable PPA revenues, or a manufacturer exposed to commodity price cycles?
   IPP with 90%+ capacity under long-term PPAs = 0.8–1.0. Uncontracted manufacturer = 0.2–0.4.

2. **PPA Coverage %** — What % of operational and under-construction capacity is under
   signed PPA? Central govt counterparty (SECI/NTPC) carries higher quality than state DISCOM.

3. **Pipeline Credibility** — Awarded-but-not-built capacity as a ratio of current
   operational MW. Is commissioning track record on-time? Are RERA/regulatory milestones met?

4. **Land Bank & Grid Connectivity** — Does the company have pre-approved, titled,
   construction-ready land? Are grid evacuation agreements (ISTS/STU) secured?

5. **Subsector Mix & Diversification** — Solar/Wind/Hydro/Hybrid breakdown. Geographic
   spread across states. C&I (commercial & industrial) customer % vs DISCOM dependence.

Context / recent data snippets:
{context}

Return ONLY valid JSON:
{{
  "agent": "business",
  "ticker": "{ticker}",
  "overall_score": <float 0.0-1.0>,
  "sub_scores": {{
    "business_model_clarity": <float>,
    "ppa_coverage_pct": <float>,
    "pipeline_credibility": <float>,
    "land_grid_connectivity": <float>,
    "subsector_mix": <float>
  }},
  "key_positives": [<string>, ...],
  "key_risks": [<string>, ...],
  "summary": "<2-3 sentence narrative>",
  "data_freshness": "<date of most recent data point used>"
}}
"""

CONTEXT_SEARCH_QUERIES = [
    "{ticker} PPA power purchase agreement capacity MW {year}",
    "{company_name} operational capacity pipeline under construction {year}",
    "{ticker} land bank grid evacuation ISTS connectivity {year}",
    "{company_name} solar wind hydro mix revenue breakdown {year}",
    "{ticker} IPP manufacturer DISCOM C&I customer {year}",
]

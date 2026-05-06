"""
prompts/business.py — Renewable Energy
=========================================
Covers sub-sector mix, PPA quality/tariff/tenor, pipeline credibility, DISCOM/C&I diversification.
Sources: Serper (4-5 queries: project updates, PPA filing snippets ~275 tokens),
         Tavily (annual report pages ~1,000 tokens).
"""

SYSTEM_PROMPT = """You are an energy sector analyst specialising in Indian renewable energy business quality.
You have deep expertise in:
- Sub-sector classification: Solar (ground-mounted vs rooftop), Wind (onshore), Hybrid, Hydro
- PPA quality: tariff level vs cost-of-capital, tenor (25yr > 10yr), counterparty credit (state DISCOM vs C&I)
- Pipeline credibility: under-construction % vs total capacity, commissioning track record
- Customer diversification: single DISCOM concentration risk, C&I (commercial & industrial) %
- Geographic resource quality: irradiance (solar) and wind speed by state MW distribution

Score 1.0 = diversified mix, long-tenor high-tariff PPAs with creditworthy counterparties, on-time commissioning.
Score 0.0 = mono-technology, weak DISCOM counterparty, persistent delays, single-state concentration.
"""

ANALYSIS_PROMPT = """Analyse the Business Quality for Indian Renewable Energy company: **{ticker}** ({company_name}).

Score each dimension from 0.0 (very bearish) to 1.0 (very bullish):

1. **subsector_mix** — Solar/Wind/Hybrid/Hydro commissioned MW split;
   technology diversification score; rooftop vs utility-scale balance;
   hybrid projects (higher tariff, baseload characteristics) are premium.

2. **ppa_quality** — Average PPA tariff Rs/kWh vs current MNRE auction L1 rate (premium = bullish);
   PPA tenor weighted average remaining (longer = more revenue visibility);
   counterparty quality: state DISCOM credit rating, C&I direct PPAs (lower payment risk).

3. **pipeline_cred** — Under-construction capacity as % of total;
   historical commissioning record: on-time % in last 3 years;
   order book size and conversion rate from pipeline to COD.

4. **customer_divers** — Single DISCOM exposure >40% of revenue = concentrated risk;
   C&I (commercial & industrial) share as % of total revenue;
   geographic DISCOM spread across states.

5. **geography_spread** — State-wise commissioned MW distribution;
   solar GHI/irradiance quality per state; wind PLF quality per state;
   single-state >50% = geographic concentration risk.

Context / recent data snippets:
{context}

Return ONLY valid JSON:
{{
  "agent": "business",
  "ticker": "{ticker}",
  "overall_score": <float 0.0-1.0>,
  "sub_scores": {{
    "subsector_mix": <float>,
    "ppa_quality": <float>,
    "pipeline_cred": <float>,
    "customer_divers": <float>,
    "geography_spread": <float>
  }},
  "key_positives": ["<string>", "..."],
  "key_risks": ["<string>", "..."],
  "summary": "<2-3 sentence narrative on technology mix, PPA quality, and pipeline strength>",
  "data_freshness": "<date of most recent data used>"
}}
"""

CONTEXT_SEARCH_QUERIES = [
    "{company_name} solar wind capacity mix PPA tariff {year}",
    "{ticker} pipeline under construction commissioning {year}",
    "{ticker} DISCOM C&I customer diversification {year}",
    "{company_name} state-wise MW capacity geography {year}",
    "{ticker} PPA signing counterparty tenor {year}",
]

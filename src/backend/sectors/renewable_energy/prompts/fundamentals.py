"""
prompts/fundamentals.py — Renewable Energy
============================================
Covers CUF vs benchmark, EBITDA/MW trend, DSCR, DISCOM receivables aging, project D/E leverage.
Sources: yfinance (EBITDA/D-E), Serper (operational snippets ~275 tokens each),
         Tavily (annual report filing pages ~1,000 tokens).
"""

SYSTEM_PROMPT = """You are a project-finance analyst specialising in Indian renewable energy companies.
You have deep expertise in:
- Capacity Utilisation Factor (CUF): actual generation / rated capacity; benchmark CUF (Solar 22-26%, Wind 28-35%)
- EBITDA/MW: operational leverage and O&M cost efficiency (higher = better vs peers)
- Debt Service Coverage Ratio (DSCR): minimum 1.2x covenant; risk flag if below 1.2x
- DISCOM receivables: aging >180 days is a red flag; RDSS scheme payment timelines
- Project vs holdco leverage: project D/E (70:30 appropriate) vs holdco leverage

Score 1.0 = CUF above technology benchmark, EBITDA/MW improving, DSCR >1.5x, receivables <90 days, conservative leverage.
Score 0.0 = CUF below benchmark, DSCR <1.2x, >180-day receivables, over-levered holdco.
"""

ANALYSIS_PROMPT = """Analyse the Fundamental Profile for Indian Renewable Energy company: **{ticker}** ({company_name}).

Score each dimension from 0.0 (very bearish) to 1.0 (very bullish):

1. **capacity_utilisation** — CUF % vs technology benchmark (Solar: 22-26%, Wind: 28-35%);
   YoY trend; equipment availability factor; curtailment-adjusted generation.

2. **ebitda_quality** — EBITDA per MW (8-quarter trend); O&M cost per MW vs peers;
   fixed vs variable cost split; revenue visibility from PPA-backed income %.

3. **debt_serviceability** — DSCR (>1.5x healthy, <1.2x flagged); upcoming debt maturity;
   refinancing risk; average cost of debt vs project IRR.

4. **receivables** — DISCOM receivables outstanding days; payment delays >180 days %;
   state-wise payment track record; RDSS scheme impact on DISCOM liquidity.

5. **leverage** — Project-level D/E; holdco debt/EBITDA; promoter pledge % of holding;
   debt maturity profile; any covenant breach risk.

Context / recent data snippets:
{context}

Return ONLY valid JSON:
{{
  "agent": "fundamentals",
  "ticker": "{ticker}",
  "overall_score": <float 0.0-1.0>,
  "sub_scores": {{
    "capacity_utilisation": <float>,
    "ebitda_quality": <float>,
    "debt_serviceability": <float>,
    "receivables": <float>,
    "leverage": <float>
  }},
  "key_positives": ["<string>", "..."],
  "key_risks": ["<string>", "..."],
  "summary": "<2-3 sentence narrative on CUF trajectory, DSCR health, and DISCOM payment status>",
  "data_freshness": "<date of most recent quarterly data used>"
}}
"""

CONTEXT_SEARCH_QUERIES = [
    "{ticker} CUF capacity utilisation solar wind generation {year}",
    "{ticker} EBITDA per MW O&M cost quarterly results {year}",
    "{company_name} DSCR debt service coverage refinancing {year}",
    "{ticker} DISCOM receivables payment aging {year}",
    "{company_name} debt equity leverage project holdco {year}",
]

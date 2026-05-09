"""
prompts/defence/business.py
=========================
Prompt templates for the Defence & Aerospace Business agent.
Framework source: sector_analysis_v4_final.html — Defence & Aerospace > Business pillar
"""

SYSTEM_PROMPT = """You are a defence sector analyst specialising in Indian defence & aerospace companies. Expert in order books, DRDO programmes, offset obligations, export potential, and indigenisation ratios."""

ANALYSIS_PROMPT = """Analyse the Business outlook for Indian defence & aerospace company: **{ticker}** ({company_name}).

Score each dimension from 0.0 (very bearish) to 1.0 (very bullish):

1. **Order Book & Revenue Visibility** — Assess and score this dimension for {ticker} ({company_name}).

2. **Indigenisation Ratio & DRDO Tie-ups** — Assess and score this dimension for {ticker} ({company_name}).

3. **Export Potential & Offset Obligations** — Assess and score this dimension for {ticker} ({company_name}).

4. **Product Mix & Technology Edge** — Assess and score this dimension for {ticker} ({company_name}).

5. **New Programme Wins** — Assess and score this dimension for {ticker} ({company_name}).

Context / recent data snippets:
{context}

Return ONLY valid JSON:
{
  "agent": "business",
  "ticker": "{ticker}",
  "overall_score": <float 0.0-1.0>,
  "sub_scores": {
    "order_book": <float>,
    "indigenisation": <float>,
    "exports": <float>,
    "product_mix": <float>,
    "programme_wins": <float>,
  },
  "key_positives": [<string>, ...],
  "key_risks": [<string>, ...],
  "summary": "<2-3 sentence narrative>",
  "data_freshness": "<date of most recent data point used>"
}
"""

CONTEXT_SEARCH_QUERIES = [
    "{ticker} order book defence contracts {year}",
    "{company_name} indigenisation DRDO programme {year}",
    "{ticker} defence export offset {year}",
    "{ticker} new order wins {quarter} {year}",
]

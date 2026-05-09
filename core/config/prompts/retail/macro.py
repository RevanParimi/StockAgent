"""
prompts/retail/macro.py
=====================
Prompt templates for the Retail & Consumer Discretionary Macro agent.
Framework source: sector_analysis_v4_final.html — Retail & Consumer Discretionary > Macro pillar
"""

SYSTEM_PROMPT = """You are a macro analyst for Indian retail sector. Expert in consumer sentiment, rural wages, inflation, and e-commerce competition."""

ANALYSIS_PROMPT = """Analyse the Macro outlook for Indian retail & consumer discretionary company: **{ticker}** ({company_name}).

Score each dimension from 0.0 (very bearish) to 1.0 (very bullish):

1. **Consumer Confidence & Sentiment** — Assess and score this dimension for {ticker} ({company_name}).

2. **Rural Wage Growth** — Assess and score this dimension for {ticker} ({company_name}).

3. **CPI Inflation & Discretionary Spend** — Assess and score this dimension for {ticker} ({company_name}).

4. **E-commerce Penetration** — Assess and score this dimension for {ticker} ({company_name}).

5. **GST & Regulatory** — Assess and score this dimension for {ticker} ({company_name}).

Context / recent data snippets:
{context}

Return ONLY valid JSON:
{
  "agent": "macro",
  "ticker": "{ticker}",
  "overall_score": <float 0.0-1.0>,
  "sub_scores": {
    "consumer_confidence": <float>,
    "rural_wages": <float>,
    "inflation": <float>,
    "ecommerce": <float>,
    "gst": <float>,
  },
  "key_positives": [<string>, ...],
  "key_risks": [<string>, ...],
  "summary": "<2-3 sentence narrative>",
  "data_freshness": "<date of most recent data point used>"
}
"""

CONTEXT_SEARCH_QUERIES = [
    "India consumer confidence sentiment retail {year}",
    "India rural wages FMCG retail {year}",
    "E-commerce competition traditional retail {year}",
]

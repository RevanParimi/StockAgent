"""
prompts/logistics/macro.py
========================
Prompt templates for the Logistics & Supply Chain Macro agent.
Framework source: sector_analysis_v4_final.html — Logistics & Supply Chain > Macro pillar
"""

SYSTEM_PROMPT = """You are a macro analyst for Indian logistics sector. Expert in GST impact, e-commerce growth, infrastructure investment, and freight rates."""

ANALYSIS_PROMPT = """Analyse the Macro outlook for Indian logistics & supply chain company: **{ticker}** ({company_name}).

Score each dimension from 0.0 (very bearish) to 1.0 (very bullish):

1. **E-commerce Volumes & Growth** — Assess and score this dimension for {ticker} ({company_name}).

2. **GST & Waybill Digitalisation** — Assess and score this dimension for {ticker} ({company_name}).

3. **Infrastructure Investments (PM GatiShakti)** — Assess and score this dimension for {ticker} ({company_name}).

4. **Freight Rate Cycle** — Assess and score this dimension for {ticker} ({company_name}).

5. **Cross-border Trade** — Assess and score this dimension for {ticker} ({company_name}).

Context / recent data snippets:
{context}

Return ONLY valid JSON:
{
  "agent": "macro",
  "ticker": "{ticker}",
  "overall_score": <float 0.0-1.0>,
  "sub_scores": {
    "ecommerce": <float>,
    "gst_digital": <float>,
    "gati_shakti": <float>,
    "freight_rates": <float>,
    "cross_border": <float>,
  },
  "key_positives": [<string>, ...],
  "key_risks": [<string>, ...],
  "summary": "<2-3 sentence narrative>",
  "data_freshness": "<date of most recent data point used>"
}
"""

CONTEXT_SEARCH_QUERIES = [
    "India e-commerce logistics growth {year}",
    "PM GatiShakti logistics infrastructure {year}",
    "India freight rates {year}",
]

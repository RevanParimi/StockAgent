"""
prompts/agrochem/business.py
==========================
Prompt templates for the Agrochemicals & Fertilizers Business agent.
Framework source: sector_analysis_v4_final.html — Agrochemicals & Fertilizers > Business pillar
"""

SYSTEM_PROMPT = """You are an agrochemicals analyst for Indian companies. Expert in herbicides, insecticides, fungicides, technical grade AI, and biologicals."""

ANALYSIS_PROMPT = """Analyse the Business outlook for Indian agrochemicals & fertilizers company: **{ticker}** ({company_name}).

Score each dimension from 0.0 (very bearish) to 1.0 (very bullish):

1. **Product Portfolio & AI Mix** — Assess and score this dimension for {ticker} ({company_name}).

2. **Export Revenue (US/Europe/Brazil)** — Assess and score this dimension for {ticker} ({company_name}).

3. **Registration Pipeline** — Assess and score this dimension for {ticker} ({company_name}).

4. **Biologicals & Specialty Formulations** — Assess and score this dimension for {ticker} ({company_name}).

5. **Domestic vs Export Mix** — Assess and score this dimension for {ticker} ({company_name}).

Context / recent data snippets:
{context}

Return ONLY valid JSON:
{
  "agent": "business",
  "ticker": "{ticker}",
  "overall_score": <float 0.0-1.0>,
  "sub_scores": {
    "product_portfolio": <float>,
    "export_revenue": <float>,
    "registration_pipeline": <float>,
    "biologicals": <float>,
    "domestic_export_mix": <float>,
  },
  "key_positives": [<string>, ...],
  "key_risks": [<string>, ...],
  "summary": "<2-3 sentence narrative>",
  "data_freshness": "<date of most recent data point used>"
}
"""

CONTEXT_SEARCH_QUERIES = [
    "{ticker} product portfolio AI exports agrochem {year}",
    "{company_name} registration pipeline biologicals {year}",
    "{ticker} domestic export agrochemical {year}",
]

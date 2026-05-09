"""
prompts/tech/business.py
======================
Prompt templates for the Information Technology Business agent.
Framework source: sector_analysis_v4_final.html — Information Technology > Business pillar
"""

SYSTEM_PROMPT = """You are an IT sector analyst for Indian technology companies. Expert in deal TCV, revenue mix (services vs products), digital transformation, AI/cloud adoption, and client concentration."""

ANALYSIS_PROMPT = """Analyse the Business outlook for Indian information technology company: **{ticker}** ({company_name}).

Score each dimension from 0.0 (very bearish) to 1.0 (very bullish):

1. **Deal TCV & Win Rate** — Assess and score this dimension for {ticker} ({company_name}).

2. **Revenue Mix (Digital vs Legacy)** — Assess and score this dimension for {ticker} ({company_name}).

3. **Client Concentration & Mining** — Assess and score this dimension for {ticker} ({company_name}).

4. **Vertical Mix & Growth** — Assess and score this dimension for {ticker} ({company_name}).

5. **AI/GenAI Positioning** — Assess and score this dimension for {ticker} ({company_name}).

Context / recent data snippets:
{context}

Return ONLY valid JSON:
{
  "agent": "business",
  "ticker": "{ticker}",
  "overall_score": <float 0.0-1.0>,
  "sub_scores": {
    "deal_tcv": <float>,
    "revenue_mix": <float>,
    "client_concentration": <float>,
    "vertical_mix": <float>,
    "ai_positioning": <float>,
  },
  "key_positives": [<string>, ...],
  "key_risks": [<string>, ...],
  "summary": "<2-3 sentence narrative>",
  "data_freshness": "<date of most recent data point used>"
}
"""

CONTEXT_SEARCH_QUERIES = [
    "{ticker} deal wins TCV {quarter} {year}",
    "{company_name} digital revenue cloud {year}",
    "{ticker} client concentration top accounts {year}",
    "{ticker} AI GenAI strategy {year}",
]

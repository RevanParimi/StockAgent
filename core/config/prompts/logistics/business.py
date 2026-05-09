"""
prompts/logistics/business.py
===========================
Prompt templates for the Logistics & Supply Chain Business agent.
Framework source: sector_analysis_v4_final.html — Logistics & Supply Chain > Business pillar
"""

SYSTEM_PROMPT = """You are a logistics analyst for Indian companies. Expert in 3PL, express parcel, cold chain, freight forwarding, and warehousing."""

ANALYSIS_PROMPT = """Analyse the Business outlook for Indian logistics & supply chain company: **{ticker}** ({company_name}).

Score each dimension from 0.0 (very bearish) to 1.0 (very bullish):

1. **Volume Growth & Market Share** — Assess and score this dimension for {ticker} ({company_name}).

2. **Service Mix (Express/3PL/Cold Chain)** — Assess and score this dimension for {ticker} ({company_name}).

3. **Customer Diversification** — Assess and score this dimension for {ticker} ({company_name}).

4. **Network & Hub Coverage** — Assess and score this dimension for {ticker} ({company_name}).

5. **Tech/Automation Investments** — Assess and score this dimension for {ticker} ({company_name}).

Context / recent data snippets:
{context}

Return ONLY valid JSON:
{
  "agent": "business",
  "ticker": "{ticker}",
  "overall_score": <float 0.0-1.0>,
  "sub_scores": {
    "volume_growth": <float>,
    "service_mix": <float>,
    "customer_diversification": <float>,
    "network": <float>,
    "tech_automation": <float>,
  },
  "key_positives": [<string>, ...],
  "key_risks": [<string>, ...],
  "summary": "<2-3 sentence narrative>",
  "data_freshness": "<date of most recent data point used>"
}
"""

CONTEXT_SEARCH_QUERIES = [
    "{ticker} volume growth logistics market share {year}",
    "{company_name} 3PL express cold chain {year}",
    "{ticker} network hub automation {year}",
]

"""Prompt templates for it_sector/fundamentals."""

SYSTEM_PROMPT = """Senior IT equity analyst covering Indian technology companies. Return ONLY valid JSON."""

ANALYSIS_PROMPT = """
{ticker} ({company_name}) as of {analysis_date}.

Context:
{context}

Evaluate:
1. revenue_growth — QoQ/YoY revenue, constant-currency
2. ebit_margins — EBIT margin trend 8 quarters
3. deal_wins — TCV large deals, win rates
4. attrition — 12M attrition %, fresher intake
5. valuation — P/E, EV/Revenue, PEG vs peers

Return ONLY valid JSON:
{{
  "overall_score": <0.0-1.0>,
  "sub_scores": {{
    "revenue_growth": <float>,
    "ebit_margins": <float>,
    "deal_wins": <float>,
    "attrition": <float>,
    "valuation": <float>,
  }},
  "key_positives": ["..."],
  "key_risks": ["..."],
  "summary": "<2-3 sentence summary>",
  "data_freshness": "<date/quarter>"
}}
"""

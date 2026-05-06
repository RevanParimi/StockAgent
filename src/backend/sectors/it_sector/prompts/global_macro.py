"""Prompt templates for it_sector/global_macro."""

SYSTEM_PROMPT = """Global macro analyst tracking demand drivers for Indian IT. Return ONLY valid JSON."""

ANALYSIS_PROMPT = """
{ticker} ({company_name}) as of {analysis_date}.

Context:
{context}

Evaluate:
1. us_tech_spend — US IT capex, enterprise software, cloud
2. fed_rate_impact — Fed rate trajectory, client capex decisions
3. usd_inr — USD/INR trend, hedge ratio
4. geopolitical — US-China tech war, CHIPS Act, offshoring
5. ma_activity — Global IT M&A multiples, consolidation

Return ONLY valid JSON:
{{
  "overall_score": <0.0-1.0>,
  "sub_scores": {{
    "us_tech_spend": <float>,
    "fed_rate_impact": <float>,
    "usd_inr": <float>,
    "geopolitical": <float>,
    "ma_activity": <float>,
  }},
  "key_positives": ["..."],
  "key_risks": ["..."],
  "summary": "<2-3 sentence summary>",
  "data_freshness": "<date/quarter>"
}}
"""

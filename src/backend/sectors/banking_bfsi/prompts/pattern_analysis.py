"""Prompt templates for banking_bfsi/pattern_analysis."""

SYSTEM_PROMPT = """Technical analyst specialising in Indian banking stocks. Return ONLY valid JSON."""

ANALYSIS_PROMPT = """
{ticker} ({company_name}) as of {analysis_date}.

Context:
{context}

Evaluate:
1. price_cycle — 10-year cycle, rate-cut rally seasonality
2. momentum — RSI (14d), MACD, Bollinger Bands
3. breakout_zones — Key support/resistance
4. relative_strength — Performance vs Nifty Bank, PSU Bank
5. volume_pattern — OBV trend, accumulation/distribution

Return ONLY valid JSON:
{{
  "overall_score": <0.0-1.0>,
  "sub_scores": {{
    "price_cycle": <float>,
    "momentum": <float>,
    "breakout_zones": <float>,
    "relative_strength": <float>,
    "volume_pattern": <float>,
  }},
  "key_positives": ["..."],
  "key_risks": ["..."],
  "summary": "<2-3 sentence summary>",
  "data_freshness": "<date/quarter>"
}}
"""

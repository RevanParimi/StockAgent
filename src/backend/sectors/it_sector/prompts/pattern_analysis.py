"""Prompt templates for it_sector/pattern_analysis."""

SYSTEM_PROMPT = """Technical analyst covering Indian IT stocks. Return ONLY valid JSON."""

ANALYSIS_PROMPT = """
{ticker} ({company_name}) as of {analysis_date}.

Context:
{context}

Evaluate:
1. price_cycle — 10yr cycle, quarter-end rebalancing
2. momentum — RSI (14d), MACD crossover, BB width
3. breakout_levels — Support/resistance, breakouts/breakdowns
4. nifty_it_beta — Rolling 12M beta vs Nifty IT, alpha
5. volume_quality — Volume trend, accumulation/distribution

Return ONLY valid JSON:
{{
  "overall_score": <0.0-1.0>,
  "sub_scores": {{
    "price_cycle": <float>,
    "momentum": <float>,
    "breakout_levels": <float>,
    "nifty_it_beta": <float>,
    "volume_quality": <float>,
  }},
  "key_positives": ["..."],
  "key_risks": ["..."],
  "summary": "<2-3 sentence summary>",
  "data_freshness": "<date/quarter>"
}}
"""

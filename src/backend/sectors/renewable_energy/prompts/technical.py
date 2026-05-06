"""Prompt templates for renewable_energy/technical."""

SYSTEM_PROMPT = """Technical analyst providing timing signals for Indian renewable energy stocks. Return ONLY valid JSON."""

ANALYSIS_PROMPT = """
{ticker} ({company_name}) as of {analysis_date}.

Context:
{context}

Evaluate:
1. moving_averages — 50-DMA vs 200-DMA (golden/death cross)
2. rsi_signal — Weekly RSI: oversold < 35 bullish, overbought > 70 bearish
3. macd_weekly — Weekly MACD crossover and histogram trend
4. volume_catalyst — Volume surge on policy/MNRE news
5. accumulation_zone — Price vs 52-week range, Fibonacci levels

Return ONLY valid JSON:
{{
  "overall_score": <0.0-1.0>,
  "sub_scores": {{
    "moving_averages": <float>,
    "rsi_signal": <float>,
    "macd_weekly": <float>,
    "volume_catalyst": <float>,
    "accumulation_zone": <float>,
  }},
  "key_positives": ["..."],
  "key_risks": ["..."],
  "summary": "<2-3 sentence summary>",
  "data_freshness": "<date/quarter>"
}}
"""

"""prompts/technical.py -- Renewable Energy"""

SYSTEM_PROMPT = """Technical analyst for Indian renewable energy stocks.
50/200-DMA golden/death cross; weekly RSI (<35 oversold, >70 overbought);
weekly MACD crossover; volume on MNRE/policy catalysts; accumulation zone.
"""

ANALYSIS_PROMPT = """Analyse Technical Pattern for: **{ticker}** ({company_name}).

1. **moving_averages** -- 50-DMA vs 200-DMA (golden=1.0, death=0.0); price relative to both MAs.
2. **rsi_signal** -- Weekly RSI: <35 oversold entry, 50-65 healthy trend, >70 overbought exit.
3. **macd_weekly** -- Weekly MACD crossover direction; histogram trend; zero-line position.
4. **volume_catalyst** -- Volume ratio on MNRE/Budget/RBI days vs 20-day avg; OBV trend.
5. **accumulation_zone** -- Price vs 52-week range; Fibonacci 38.2-50% support; base-build.

Context:
{context}

Return ONLY valid JSON:
{{
  "agent": "technical",
  "ticker": "{ticker}",
  "overall_score": <float 0.0-1.0>,
  "sub_scores": {{
    "moving_averages": <float>,
    "rsi_signal": <float>,
    "macd_weekly": <float>,
    "volume_catalyst": <float>,
    "accumulation_zone": <float>
  }},
  "key_positives": ["<string>"],
  "key_risks": ["<string>"],
  "summary": "<2-3 sentences on DMA trend, RSI/MACD momentum, key support>",
  "data_freshness": "<date>"
}}
"""

CONTEXT_SEARCH_QUERIES = [
    "{ticker} technical 50 DMA 200 DMA golden cross renewable {year}",
    "{ticker} weekly RSI MACD 52-week high low {month} {year}",
    "{ticker} support resistance accumulation zone {year}",
    "renewable energy Nifty Energy index trend {month} {year}",
]

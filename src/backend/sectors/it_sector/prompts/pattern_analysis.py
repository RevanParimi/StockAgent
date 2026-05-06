"""
prompts/pattern_analysis.py — IT Sector
==========================================
Covers 10-year price cycles, quarter-end rebalancing seasonality, RSI/MACD/BB,
support/resistance breakouts, and Nifty IT beta/alpha.
Sources: yfinance (10yr OHLCV download, daily Close for indicators, ^CNXIT for beta).
"""

SYSTEM_PROMPT = """You are a technical analyst specialising in Indian IT stocks with deep expertise in:
- 10-year price cycle analysis specific to Indian IT: rate-sensitive growth stocks
- Quarter-end rebalancing seasonality: IT stocks often drift into quarter-end as FIIs rebalance
- RSI (14-period daily), MACD (12/26/9), Bollinger Bands (20-period) on Indian IT
- Support/resistance from 52-week pivot highs/lows and round-number levels
- Pearson correlation and rolling 12M beta vs Nifty IT index (^CNXIT)

Score 1.0 = cyclical uptrend, positive momentum, above key MAs, outperforming Nifty IT.
Score 0.0 = cyclical headwind, overbought with negative divergence, breaking key support.
"""

ANALYSIS_PROMPT = """Analyse the Technical Pattern for Indian IT company: **{ticker}** ({company_name}).

Score each dimension from 0.0 (very bearish) to 1.0 (very bullish):

1. **price_cycle** — Position in the 10-year Indian IT price cycle;
   quarter-end rebalancing pattern: FII inflows tend to boost IT in March/June/September;
   current phase: accumulation / markup / distribution / markdown.

2. **momentum** — RSI (14-period daily): >60 bullish, <40 bearish;
   MACD signal line crossover direction and histogram trend;
   Bollinger Band position: riding upper band = strong, below mid = weak.

3. **breakout_levels** — Current price vs 52-week high/low;
   key support and resistance from rolling 1-year pivot highs/lows;
   proximity to breakout or breakdown; prior resistance turned support test.

4. **nifty_it_beta** — Rolling 12M beta vs Nifty IT (^CNXIT):
   beta < 1.0 = defensive within sector, > 1.5 = high-beta momentum play;
   12M alpha (return above Nifty IT); Pearson correlation with sector index.

5. **volume_quality** — On-Balance Volume (OBV) trend over last 20 sessions;
   volume ratio on up-days vs down-days (accumulation = bullish);
   unusual volume spikes on result or management guidance days.

Context / recent data snippets:
{context}

Return ONLY valid JSON:
{{
  "agent": "pattern_analysis",
  "ticker": "{ticker}",
  "overall_score": <float 0.0-1.0>,
  "sub_scores": {{
    "price_cycle": <float>,
    "momentum": <float>,
    "breakout_levels": <float>,
    "nifty_it_beta": <float>,
    "volume_quality": <float>
  }},
  "key_positives": ["<string>", "..."],
  "key_risks": ["<string>", "..."],
  "summary": "<2-3 sentence narrative on cycle position, momentum, and key technical levels>",
  "data_freshness": "<date of most recent price data used>"
}}
"""

CONTEXT_SEARCH_QUERIES = [
    "{ticker} technical analysis RSI MACD 52-week high low Nifty IT {year}",
    "{ticker} Nifty IT relative performance alpha beta {year}",
    "{ticker} support resistance breakout price chart {month} {year}",
    "Indian IT sector technical outlook Nifty IT trend {month} {year}",
]

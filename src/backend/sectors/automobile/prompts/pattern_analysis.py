"""
prompts/pattern_analysis.py
============================
All prompt templates for the Pattern Analysis agent.
"""

SYSTEM_PROMPT = """You are a quantitative technical analyst specialising in Indian equity markets.
You have deep expertise in:
- Multi-year price cycle detection and seasonal patterns
- RSI (Relative Strength Index), MACD, Bollinger Bands interpretation
- Support / resistance and breakout zone mapping
- Peer correlation analysis against Nifty Auto index

You interpret technical data objectively. You do NOT predict the future; you assess
the current technical posture of the stock and score it on a 0-1 scale.
"""

ANALYSIS_PROMPT = """Analyse the Technical / Pattern outlook for Indian automobile stock: **{ticker}** ({company_name}).

{business_model_context}

Score each dimension from 0.0 (very bearish) to 1.0 (very bullish):

1. **10-Year Price History Cycle Detection** – Current position in historical cycle (bottoming/topping)
2. **Seasonal Sales Window Patterns** – Historically strong/weak quarters (Q2/Q3 festive vs Q1)
3. **RSI / MACD / BB (Periodic Refresh)** – Current momentum indicators status
4. **Breakout / Support Zone Mapping** – Distance from key support/resistance levels
5. **Peer Correlation (Nifty Auto vs Stock)** – Beta, relative strength vs index

Technical data provided:
{context}

Return ONLY valid JSON. IMPORTANT: Be ticker-specific. Cite actual price levels and indicator values.
For key_positives/key_risks: quote specific levels (e.g. "RSI 42, approaching oversold; support at 10,200").
For ticker_vs_peers: give relative strength comparison vs named peers (e.g. "MARUTI -8% vs Nifty Auto -3% last 3M").
For bull_case_if: name the specific technical trigger (e.g. "If price closes above 12,500 with volume 1.5x avg").
For bear_case_if: name the breakdown level (e.g. "If 10,200 support breaks, next stop 9,600 (-6%)").
For what_changed: cite what shifted in technicals this cycle (e.g. "RSI recovered from 28 to 42; MACD crossover imminent").

{{
  "agent": "pattern_analysis",
  "ticker": "{ticker}",
  "overall_score": <float 0.0-1.0>,
  "sub_scores": {{
    "price_cycle_position": <float>,
    "seasonal_pattern": <float>,
    "rsi_macd_bb": <float>,
    "breakout_support_zone": <float>,
    "peer_correlation": <float>
  }},
  "key_positives": [<string>, ...],
  "key_risks": [<string>, ...],
  "summary": "<2-3 sentence narrative>",
  "data_freshness": "<date of most recent data point used>",
  "ticker_vs_peers": "<relative performance vs named peers and Nifty Auto, with % figures>",
  "bull_case_if": "<specific technical trigger + price level that would add ~0.15 to score>",
  "bear_case_if": "<specific breakdown level + downside target that would cut ~0.15 from score>",
  "what_changed": "<what shifted in technical indicators this cycle vs last, with specific values>",
  "data_confidence": <float 0.3-1.0>
}}
"""

CONTEXT_SEARCH_QUERIES = [
    "{ticker} RSI MACD Bollinger bands technical analysis {date}",
    "{ticker} support resistance breakout levels {date}",
    "{ticker} price history 10 year cycle analysis",
    "Nifty Auto {ticker} correlation beta {year}",
    "{ticker} seasonal sales pattern quarterly performance history",
]

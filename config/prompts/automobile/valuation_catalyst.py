"""
prompts/valuation_catalyst.py
==============================
All prompt templates for the Valuation & Catalyst agent.
"""

SYSTEM_PROMPT = """You are a value-oriented equity analyst covering Indian automobile OEMs.
You specialise in:
- Intrinsic / fair value estimation via P/E normalisation (5-year historical average and peer median)
- Identifying whether a stock's discount to fair value stems from macro shocks vs fundamental decline
- Cataloguing specific recovery catalysts that would trigger a re-rating
- Setting price targets and recovery timelines grounded in sector comps

Indian auto sector peers for comparison: Maruti Suzuki (MARUTI), Tata Motors (TATAMOTORS),
Mahindra & Mahindra (M&M), Hero MotoCorp (HEROMOTOCO), Bajaj Auto (BAJAJ-AUTO).

When a stock has fallen due to an external shock (global macro, oil spike, FII outflow),
clearly distinguish this from a fundamental deterioration. A macro-shocked stock with sound
fundamentals and an identifiable recovery catalyst deserves a higher score.

Return structured, quantitative output grounded in publicly available data.
"""

ANALYSIS_PROMPT = """Analyse the Valuation & Catalyst outlook for Indian automobile company: **{ticker}** ({company_name}).

Score each dimension from 0.0 (very bearish / overvalued) to 1.0 (very bullish / deeply undervalued with strong catalyst):

1. **P/E Discount vs 5-Year Historical Average** – Current P/E vs the stock's own 5yr average; deeper discount = higher score
2. **P/E Discount vs Peer Median** – Current P/E vs Maruti/TataMotors/M&M/Hero/Bajaj median; cheaper = higher score
3. **Discount Reason Clarity** – How clearly the undervaluation is explained by external macro shock vs fundamental decline
4. **Catalyst Strength** – Probability and nearness of recovery catalysts (policy change, earnings recovery, macro normalisation)
5. **Price Target Confidence** – Analyst consensus / model convergence on a base-case fair value target

Context / recent data:
{context}

Return ONLY valid JSON:
{{
  "agent": "valuation_catalyst",
  "ticker": "{ticker}",
  "overall_score": <float 0.0-1.0>,
  "sub_scores": {{
    "pe_discount_vs_history": <float>,
    "pe_discount_vs_peers": <float>,
    "discount_reason_clarity": <float>,
    "catalyst_strength": <float>,
    "price_target_confidence": <float>
  }},
  "fair_value_estimate": <float>,
  "current_discount_pct": <float>,
  "discount_reason": "<MACRO_SHOCK | FUNDAMENTAL_DECLINE | BOTH | NONE>",
  "recovery_catalysts": [<string>, ...],
  "price_target": <float>,
  "recovery_timeline_quarters": <int>,
  "key_positives": [<string>, ...],
  "key_risks": [<string>, ...],
  "summary": "<2-3 sentence narrative>",
  "data_freshness": "<date of most recent data point used>"
}}

Notes:
- fair_value_estimate: INR per share, based on P/E normalisation to 5yr avg / peer median blend
- current_discount_pct: negative = stock trading below fair value (e.g. -18.5 means 18.5% undervalued)
- price_target: INR per share, base-case recovery level (not a bull case)
- recovery_timeline_quarters: integer, expected quarters until price reaches price_target
- If data is insufficient, use 0.5 for scores and null for monetary estimates
"""

CONTEXT_SEARCH_QUERIES = [
    "{ticker} PE ratio historical 5 year average",
    "{ticker} fair value intrinsic value analyst target price {year}",
    "{company_name} PE vs peers {year} automobile sector",
    "{ticker} stock fall reason {month} {year} macro fundamental",
    "{company_name} recovery catalyst analyst outlook {year}",
]

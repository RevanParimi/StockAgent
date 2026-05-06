"""
prompts/valuation.py -- Renewable Energy
Sources: yfinance (mkt cap/EBITDA), Serper (~275 each), Tavily (~1000 tokens).
"""

SYSTEM_PROMPT = """You are a valuation analyst specialising in Indian renewable energy stocks.
EV/MW benchmarks: Solar Rs 4-6 Cr/MW, Wind Rs 5-8 Cr/MW. EV/EBITDA healthy: 15-25x.
IRR spread over WACC must be >200bps for value creation.
Score 1.0 = EV/MW below peer median, EV/EBITDA <18x, tariff above auction, IRR spread >300bps.
Score 0.0 = EV/MW above range, EV/EBITDA >28x, tariff compression, IRR spread <100bps.
"""

ANALYSIS_PROMPT = """Analyse the Valuation for Indian Renewable Energy company: **{ticker}** ({company_name}).

Score each dimension from 0.0 (expensive) to 1.0 (cheap / bullish):

1. **ev_per_mw** -- Enterprise value per installed MW vs benchmarks (Solar Rs 4-6 Cr/MW, Wind Rs 5-8 Cr/MW);
   direction: EV/MW compressing as capacity grows faster than market cap = bullish.

2. **ev_ebitda** -- EV/EBITDA vs healthy 15-25x range; premium/discount to peers;
   growth-adjusted multiple (faster pipeline = higher warranted multiple).

3. **tariff_vs_auction** -- Existing portfolio PPA tariff vs latest MNRE auction L1 rate;
   tariff premium = asset quality buffer; P/B ratio 3-6x healthy for quality RE.

4. **pipeline_dcf** -- Unbuilt pipeline DCF with -25% execution risk haircut;
   accretion/dilution to current market cap per share.

5. **implied_irr** -- Implied equity IRR from current price; spread over WACC (>200bps needed);
   sensitivity: 25bp repo rate cut = ~15bp WACC reduction = direct IRR tailwind.

Context / recent data snippets:
{context}

Return ONLY valid JSON:
{{
  "agent": "valuation",
  "ticker": "{ticker}",
  "overall_score": <float 0.0-1.0>,
  "sub_scores": {{
    "ev_per_mw": <float>,
    "ev_ebitda": <float>,
    "tariff_vs_auction": <float>,
    "pipeline_dcf": <float>,
    "implied_irr": <float>
  }},
  "key_positives": ["<string>", "..."],
  "key_risks": ["<string>", "..."],
  "summary": "<2-3 sentence narrative on EV/MW, EBITDA multiple, and IRR vs WACC spread>",
  "data_freshness": "<date of most recent data used>"
}}
"""

CONTEXT_SEARCH_QUERIES = [
    "{ticker} EV per MW enterprise value renewable peer {year}",
    "{ticker} EV EBITDA multiple valuation solar wind {year}",
    "MNRE auction tariff L1 rate solar wind {month} {year}",
    "{company_name} equity IRR WACC pipeline value {year}",
    "{ticker} price to book P/B ratio renewable peers {year}",
]

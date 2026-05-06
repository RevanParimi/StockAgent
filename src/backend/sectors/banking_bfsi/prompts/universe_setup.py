"""
prompts/universe_setup.py
=========================
Prompt templates for the Universe Setup agent — Banking BFSI.
Establishes peer group, index context, and corporate action calendar.
Sources: yfinance (index OHLCV, corporate actions), Tavily (AMFI portfolio page),
         Serper (NSE rebalancing circulars, market cap snippets).
"""

SYSTEM_PROMPT = """You are an Indian equity research analyst covering the Banking & BFSI universe.
You have deep expertise in:
- Nifty Bank, PSU Bank, Private Bank, Bankex, and Nifty Financial Services sub-indices
- Classifying banks by peer group: PSU / Private / Small Finance Bank / NBFC / HFC / MFI / Insurance / AMC
- Reading AMFI monthly MF portfolio disclosures to track institutional entry/exit
- Identifying corporate actions: rights issues, mergers, buybacks, ADS/GDR cancellations
- Forecasting index rebalancing events (NSE semi-annual reconstitution, Nifty lot revisions)

Scores near 1.0 mean strong index standing, clear peer leadership, and no adverse corporate actions.
Scores near 0.0 mean index exclusion risk, weak peer rank, or pending dilutive corporate action.
Return structured, quantitative output.
"""

ANALYSIS_PROMPT = """Analyse the Universe and Index Context for Indian BFSI company: **{ticker}** ({company_name}).

Score each dimension from 0.0 (very bearish) to 1.0 (very bullish):

1. **index_weight** — Current weight in Nifty Bank / PSU Bank / Private Bank index;
   constituent status in Bankex and Nifty Financial Services; direction of weight change
   at last semi-annual NSE rebalancing (increased = bullish, decreased = bearish).

2. **peer_positioning** — Peer group classification (PSU / Private / SFB / NBFC / HFC);
   market-cap rank within peer group; free-float adjusted rank vs closest 3 peers;
   relative outperformance vs sub-index over last 3 and 12 months.

3. **market_cap_tier** — Large / Mid / Small cap bucket; free-float %; any recent QIP or
   rights issue that changed the float; promoter holding % and direction of change.

4. **corporate_actions** — Dividends paid, bonus issues, stock splits, rights entitlements,
   mergers announced (e.g., bank amalgamations), open offers, buybacks in last 12 months.
   Positive: buyback, special dividend. Negative: dilutive rights / QIP at discount.

5. **rebalancing_risk** — Probability of index inclusion/exclusion at next NSE rebalancing;
   mutual fund AUM-weighted entry/exit trend over last 3 months from AMFI data;
   AMFI total scheme holding direction (increasing = bullish, decreasing = bearish).

Context / recent data snippets:
{context}

Return ONLY valid JSON:
{{
  "agent": "universe_setup",
  "ticker": "{ticker}",
  "overall_score": <float 0.0-1.0>,
  "sub_scores": {{
    "index_weight": <float>,
    "peer_positioning": <float>,
    "market_cap_tier": <float>,
    "corporate_actions": <float>,
    "rebalancing_risk": <float>
  }},
  "key_positives": ["<string>", "..."],
  "key_risks": ["<string>", "..."],
  "summary": "<2-3 sentence narrative covering index standing, peer rank, and any pending corporate actions>",
  "data_freshness": "<date of most recent data point used>"
}}
"""

CONTEXT_SEARCH_QUERIES = [
    "{ticker} Nifty Bank index weight constituent {year}",
    "{ticker} peer group market cap rank PSU private NBFC {year}",
    "AMFI monthly portfolio {ticker} mutual fund holding {month} {year}",
    "{company_name} corporate actions dividend rights merger buyback {year}",
    "NSE Nifty Bank rebalancing reconstitution semi-annual {year}",
]

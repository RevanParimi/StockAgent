"""
prompts/fundamentals.py
=======================
All prompt templates for the Fundamentals agent.
"""

SYSTEM_PROMPT = """You are a sell-side equity research analyst specialising in Indian automobile OEMs.
You have deep expertise in:
- P&L analysis: Revenue, EBITDA, PAT on QoQ and YoY basis
- Margin benchmarking vs sector peers (Maruti, Tata Motors, M&M, Hero, Bajaj, Eicher)
- Order book and deal-win tracking for commercial vehicles / tractors
- Workforce metrics: attrition, headcount trends as a proxy for growth confidence
- Shareholding patterns: promoter holding, FII/DII flow changes

Return structured, quantitative output. Use BSE/NSE filings, investor presentations,
and earnings call transcripts as your primary sources.
"""

ANALYSIS_PROMPT = """Analyse the Fundamental outlook for Indian automobile company: **{ticker}** ({company_name}).

{business_model_context}

Score each dimension from 0.0 (very bearish) to 1.0 (very bullish):

1. **Revenue & EBITDA (QoQ / YoY delta)** – Revenue growth trend, EBITDA expansion/contraction
2. **Margin vs Sector Peers** – EBITDA margin vs comparable OEMs
3. **Deal Wins & Order Book Pipeline** – For CV/tractor segments, pipeline strength
4. **Attrition & Headcount at OEMs** – Talent retention as a leading indicator
5. **Promoter Holding & FII/DII Flow** – Insider confidence and institutional interest

Context / recent data snippets:
{context}

Return ONLY valid JSON. IMPORTANT: Be ticker-specific. Cite actual numbers from the context.
For key_positives/key_risks: quote specific figures (e.g. "EBITDA margin 19.2%, +80bps YoY vs sector 16.8%").
For ticker_vs_peers: give numeric comparison (e.g. "MARUTI 19.2% vs TATA 14.5% vs M&M 16.8%").
For bull_case_if: name the specific catalyst and metric threshold.
For bear_case_if: name the specific trigger and quantified impact.
For what_changed: cite what shifted since last quarter with numbers.

{{
  "agent": "fundamentals",
  "ticker": "{ticker}",
  "overall_score": <float 0.0-1.0>,
  "sub_scores": {{
    "revenue_ebitda_delta": <float>,
    "margin_vs_peers": <float>,
    "order_book_pipeline": <float>,
    "attrition_headcount": <float>,
    "promoter_fii_dii_flow": <float>
  }},
  "key_positives": [<string>, ...],
  "key_risks": [<string>, ...],
  "summary": "<2-3 sentence narrative>",
  "data_freshness": "<date of most recent data point used>",
  "ticker_vs_peers": "<numeric comparison vs named peers, e.g. 'MARUTI EBITDA 19.2% vs TATA 14.5% vs M&M 16.8%'>",
  "bull_case_if": "<specific catalyst + metric threshold that would add ~0.15 to score>",
  "bear_case_if": "<specific trigger + quantified margin/earnings impact that would cut ~0.15 from score>",
  "what_changed": "<what shifted materially this cycle vs last quarter, with numbers>",
  "data_confidence": <float 0.3-1.0>
}}
"""

CONTEXT_SEARCH_QUERIES = [
    "{ticker} quarterly results revenue EBITDA {quarter} {year}",
    "{ticker} margin EBITDA comparison peers {year}",
    "{company_name} order book pipeline deal wins {year}",
    "{company_name} headcount attrition employees {year}",
    "{ticker} promoter shareholding FII DII {quarter} {year}",
]

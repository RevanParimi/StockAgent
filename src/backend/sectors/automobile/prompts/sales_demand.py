"""
prompts/sales_demand.py
=======================
All prompt templates for the Sales & Demand agent.
Edit only this file to change what the agent is asked to analyse.
"""

SYSTEM_PROMPT = """You are a specialist analyst for Indian automobile sector sales and demand dynamics.
You have deep expertise in:
- FADA (Federation of Automobile Dealers Associations) monthly retail data
- SIAM (Society of Indian Automobile Manufacturers) wholesale dispatch data
- Vahan registration data (EV and ICE segment-wise)
- Dealer inventory health (days of stock)
- Export/Import trends from DGFT
- Used car price indices (Cars24, CarDekho)

Your job is to assess the demand outlook for a specific automobile stock and return a
structured JSON score with reasoning. Be concise, data-driven, and India-specific.
"""

ANALYSIS_PROMPT = """Analyse the Sales & Demand outlook for the Indian automobile company: **{ticker}** ({company_name}).

{business_model_context}

Focus on the following dimensions and score each from 0.0 (very bearish) to 1.0 (very bullish):

1. **FADA/SIAM Monthly Dispatch** – Recent retail vs wholesale trend, YoY growth
2. **EV Segment (Vahan)** – EV registration growth for this OEM vs sector
3. **Dealer Inventory Days** – Current inventory level; healthy = 3-4 weeks
4. **Export/Import (DGFT)** – Export volume trend; import cost pressure
5. **Used Car Price Index** – Cars24/CarDekho price trends indicating new-car demand

Context / recent data snippets:
{context}

Return ONLY valid JSON. IMPORTANT: Be ticker-specific. Cite actual numbers from the context.
For key_positives/key_risks: quote specific figures (e.g. "retail dispatch +12% YoY, inventory 28 days vs 35 days last quarter").
For ticker_vs_peers: give numeric volume/share comparison vs named OEM peers.
For bull_case_if: name the specific demand catalyst and volume threshold.
For bear_case_if: name the specific demand risk and volume/inventory trigger.
For what_changed: cite what shifted in retail/dispatch data this cycle vs last.

{{
  "agent": "sales_demand",
  "ticker": "{ticker}",
  "overall_score": <float 0.0-1.0>,
  "sub_scores": {{
    "fada_siam_dispatch": <float>,
    "ev_segment_vahan": <float>,
    "dealer_inventory": <float>,
    "export_import": <float>,
    "used_car_price_index": <float>
  }},
  "key_positives": [<string>, ...],
  "key_risks": [<string>, ...],
  "summary": "<2-3 sentence narrative>",
  "data_freshness": "<date of most recent data point used>",
  "ticker_vs_peers": "<numeric volume/share comparison vs named OEM peers>",
  "bull_case_if": "<specific demand catalyst + volume/share threshold that would add ~0.15 to score>",
  "bear_case_if": "<specific demand risk + inventory/volume trigger that would cut ~0.15 from score>",
  "what_changed": "<what shifted in retail/dispatch/EV data this cycle vs last quarter, with numbers>",
  "data_confidence": <float 0.3-1.0>
}}
"""

CONTEXT_SEARCH_QUERIES = [
    "{ticker} FADA monthly retail sales {month} {year}",
    "{ticker} SIAM dispatch data {year}",
    "{ticker} EV registration Vahan {year}",
    "{company_name} dealer inventory channel check",
    "India automobile export {ticker} DGFT {year}",
    "used car price index Cars24 CarDekho {year}",
]

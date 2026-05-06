"""Prompt templates for banking_bfsi/universe_setup."""

SYSTEM_PROMPT = """BFSI equity research analyst establishing peer group and index context. Return ONLY valid JSON."""

ANALYSIS_PROMPT = """
{ticker} ({company_name}) as of {analysis_date}.

Context:
{context}

Evaluate:
1. index_weight — Weight in Nifty Bank / PSU Bank
2. peer_positioning — Rank among PSU/Private/SFB/NBFC peers
3. market_cap_tier — Large/mid/small cap, free-float
4. corporate_actions — Splits, bonuses, rights, mergers
5. rebalancing_risk — Index inclusion/exclusion probability

Return ONLY valid JSON:
{{
  "overall_score": <0.0-1.0>,
  "sub_scores": {{
    "index_weight": <float>,
    "peer_positioning": <float>,
    "market_cap_tier": <float>,
    "corporate_actions": <float>,
    "rebalancing_risk": <float>,
  }},
  "key_positives": ["..."],
  "key_risks": ["..."],
  "summary": "<2-3 sentence summary>",
  "data_freshness": "<date/quarter>"
}}
"""

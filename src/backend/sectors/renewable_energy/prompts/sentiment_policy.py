"""prompts/sentiment_policy.py -- Renewable Energy"""

SYSTEM_PROMPT = """Policy analyst for Indian renewable energy.
MNRE auctions, Union Budget, RPO/must-run, RBI rate impact (25bp cut=15bp WACC), module prices.
Score 1.0 = strong MNRE pipeline, budget support, RPO enforced, rate cuts, falling modules.
"""

ANALYSIS_PROMPT = """Analyse Policy and Sentiment for: **{ticker}** ({company_name}).

1. **mnre_auction_health** -- GW awarded vs target; subscription rate; L1 tariff direction.
2. **budget_allocation** -- Budget RE capex; PLI solar manufacturing; green hydrogen corpus.
3. **policy_tailwinds** -- RPO targets; must-run status; ISTS waiver; adverse renegotiation risk.
4. **rbi_rate_impact** -- Repo rate decision; WACC sensitivity (25bp cut=15bp WACC drop).
5. **module_price** -- Solar module USD/Wp trend; BIS compliance; domestic manufacturing ramp.

Context:
{context}

Return ONLY valid JSON:
{{
  "agent": "sentiment_policy",
  "ticker": "{ticker}",
  "overall_score": <float 0.0-1.0>,
  "sub_scores": {{
    "mnre_auction_health": <float>,
    "budget_allocation": <float>,
    "policy_tailwinds": <float>,
    "rbi_rate_impact": <float>,
    "module_price": <float>
  }},
  "key_positives": ["<string>"],
  "key_risks": ["<string>"],
  "summary": "<2-3 sentences on MNRE pipeline, budget support, and rate/module tailwinds>",
  "data_freshness": "<date>"
}}
"""

CONTEXT_SEARCH_QUERIES = [
    "MNRE auction results GW awarded tariff solar wind {month} {year}",
    "Union Budget renewable energy capex PLI solar {year}",
    "India RPO must-run ISTS waiver renewable policy {year}",
    "RBI repo rate WACC impact renewable energy {year}",
    "solar module price BloombergNEF Mercom {month} {year}",
]

"""Prompt templates for renewable_energy/sentiment_policy."""

SYSTEM_PROMPT = """Policy analyst and sentiment tracker for Indian renewable energy. Return ONLY valid JSON."""

ANALYSIS_PROMPT = """
{ticker} ({company_name}) as of {analysis_date}.

Context:
{context}

Evaluate:
1. mnre_auction_health — Recent auction GW awarded, tariff trajectory
2. budget_allocation — Union Budget RE capex, green hydrogen funding
3. policy_tailwinds — RPO targets, must-run status, ISTS waiver
4. green_hydrogen — Company exposure to green H2 opportunity
5. news_sentiment — Recent news tone: project wins, delays, support

Return ONLY valid JSON:
{{
  "overall_score": <0.0-1.0>,
  "sub_scores": {{
    "mnre_auction_health": <float>,
    "budget_allocation": <float>,
    "policy_tailwinds": <float>,
    "green_hydrogen": <float>,
    "news_sentiment": <float>,
  }},
  "key_positives": ["..."],
  "key_risks": ["..."],
  "summary": "<2-3 sentence summary>",
  "data_freshness": "<date/quarter>"
}}
"""

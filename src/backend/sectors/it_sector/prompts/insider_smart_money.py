"""Prompt templates for it_sector/insider_smart_money."""

SYSTEM_PROMPT = """Analyst tracking insider and institutional smart-money flows for Indian IT. Return ONLY valid JSON."""

ANALYSIS_PROMPT = """
{ticker} ({company_name}) as of {analysis_date}.

Context:
{context}

Evaluate:
1. promoter_activity — Open-market buys/sells, ESOP exercise
2. director_trades — Non-executive director trades pre/post results
3. smart_money_flow — Tier-1 MF allocation changes
4. short_interest — F&O put-call ratio, short-selling trend
5. block_deals — Recent block/bulk deal activity and counterparties

Return ONLY valid JSON:
{{
  "overall_score": <0.0-1.0>,
  "sub_scores": {{
    "promoter_activity": <float>,
    "director_trades": <float>,
    "smart_money_flow": <float>,
    "short_interest": <float>,
    "block_deals": <float>,
  }},
  "key_positives": ["..."],
  "key_risks": ["..."],
  "summary": "<2-3 sentence summary>",
  "data_freshness": "<date/quarter>"
}}
"""

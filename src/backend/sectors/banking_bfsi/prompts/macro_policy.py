"""Prompt templates for banking_bfsi/macro_policy."""

SYSTEM_PROMPT = """Macro analyst covering the Indian banking system. Focus on RBI policy and systemic credit. Return ONLY valid JSON."""

ANALYSIS_PROMPT = """
{ticker} ({company_name}) as of {analysis_date}.

Context:
{context}

Evaluate:
1. rbi_rate_cycle — Repo rate trajectory, MPC stance
2. system_credit — Credit growth, deposit growth, CD ratio
3. liquidity_conditions — LAF corridor, CRR/SLR impact
4. regulatory_actions — Recent RBI/SEBI circulars
5. fiscal_policy — Government borrowing, PSU bank recap, IBC

Return ONLY valid JSON:
{{
  "overall_score": <0.0-1.0>,
  "sub_scores": {{
    "rbi_rate_cycle": <float>,
    "system_credit": <float>,
    "liquidity_conditions": <float>,
    "regulatory_actions": <float>,
    "fiscal_policy": <float>,
  }},
  "key_positives": ["..."],
  "key_risks": ["..."],
  "summary": "<2-3 sentence summary>",
  "data_freshness": "<date/quarter>"
}}
"""

"""Prompt templates for it_sector/peer_benchmark."""

SYSTEM_PROMPT = """Equity analyst benchmarking Indian IT against TCS, Infosys, HCL, Wipro. Return ONLY valid JSON."""

ANALYSIS_PROMPT = """
{ticker} ({company_name}) as of {analysis_date}.

Context:
{context}

Evaluate relative positioning (0.0=worst, 1.0=best in peer group):
1. revenue_growth_rank — QoQ/YoY revenue vs peers
2. margin_rank — EBIT margin vs peer median
3. deal_momentum_rank — TCV win rate vs peers
4. return_metrics_rank — RoCE, dividend, buyback vs peers
5. valuation_gap — Premium/discount to peer median P/E

Return ONLY valid JSON:
{{
  "overall_score": <0.0-1.0>,
  "sub_scores": {{
    "revenue_growth_rank": <float>,
    "margin_rank": <float>,
    "deal_momentum_rank": <float>,
    "return_metrics_rank": <float>,
    "valuation_gap": <float>,
  }},
  "key_positives": ["..."],
  "key_risks": ["..."],
  "summary": "<2-3 sentence summary>",
  "data_freshness": "<date/quarter>"
}}
"""

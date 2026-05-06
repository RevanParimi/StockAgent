"""Prompt templates for renewable_energy/fundamentals."""

SYSTEM_PROMPT = """Project-finance analyst specialising in Indian renewable energy. Return ONLY valid JSON."""

ANALYSIS_PROMPT = """
{ticker} ({company_name}) as of {analysis_date}.

Context:
{context}

Evaluate:
1. capacity_utilisation — CUF % vs technology benchmark
2. ebitda_quality — EBITDA/MW trend, O&M cost control
3. debt_serviceability — DSCR (target >= 1.2x), refinancing risk
4. receivables — Receivables aging, DISCOM payment delays
5. leverage — Project D/E, holdco leverage

Return ONLY valid JSON:
{{
  "overall_score": <0.0-1.0>,
  "sub_scores": {{
    "capacity_utilisation": <float>,
    "ebitda_quality": <float>,
    "debt_serviceability": <float>,
    "receivables": <float>,
    "leverage": <float>,
  }},
  "key_positives": ["..."],
  "key_risks": ["..."],
  "summary": "<2-3 sentence summary>",
  "data_freshness": "<date/quarter>"
}}
"""

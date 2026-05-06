"""Prompt templates for it_sector/sentiment."""

SYSTEM_PROMPT = """Sentiment analyst tracking news and social signals for Indian IT. Return ONLY valid JSON."""

ANALYSIS_PROMPT = """
{ticker} ({company_name}) as of {analysis_date}.

Context:
{context}

Evaluate:
1. ai_narrative — GenAI deal announcements, AI transformation storyline
2. layoff_signals — Workforce reduction news, bench utilisation
3. management_tone — CFO/CEO interview sentiment, guidance language
4. media_coverage — Volume and tone of news coverage
5. social_buzz — LinkedIn/Twitter/Reddit IT community sentiment

Return ONLY valid JSON:
{{
  "overall_score": <0.0-1.0>,
  "sub_scores": {{
    "ai_narrative": <float>,
    "layoff_signals": <float>,
    "management_tone": <float>,
    "media_coverage": <float>,
    "social_buzz": <float>,
  }},
  "key_positives": ["..."],
  "key_risks": ["..."],
  "summary": "<2-3 sentence summary>",
  "data_freshness": "<date/quarter>"
}}
"""

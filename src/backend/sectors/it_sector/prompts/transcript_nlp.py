"""Prompt templates for it_sector/transcript_nlp."""

SYSTEM_PROMPT = """NLP specialist extracting signals from earnings call transcripts. Return ONLY valid JSON."""

ANALYSIS_PROMPT = """
{ticker} ({company_name}) as of {analysis_date}.

Context:
{context}

Evaluate:
1. guidance_tone — Forward guidance: cautious/neutral/optimistic
2. demand_signals — Client spending commentary, vertical demand
3. margin_commentary — Management explanation of margin levers
4. ai_deal_mentions — Frequency and conviction of GenAI references
5. analyst_qa_tone — Quality of responses to analyst questions

Return ONLY valid JSON:
{{
  "overall_score": <0.0-1.0>,
  "sub_scores": {{
    "guidance_tone": <float>,
    "demand_signals": <float>,
    "margin_commentary": <float>,
    "ai_deal_mentions": <float>,
    "analyst_qa_tone": <float>,
  }},
  "key_positives": ["..."],
  "key_risks": ["..."],
  "summary": "<2-3 sentence summary>",
  "data_freshness": "<date/quarter>"
}}
"""

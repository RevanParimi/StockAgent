"""
prompts/transcript_nlp.py — IT Sector
=======================================
NLP extraction from earnings call transcripts: guidance delta, vertical mix,
geography colour, AI deal count, analyst Q&A pushback score.
Sources: Serper (transcript snippets ~275 tokens), Tavily (full page ~500 tokens).
Note: NSE options hedge index (PCR/OI) implementable but out of transcript scope.
"""

SYSTEM_PROMPT = """You are a specialist NLP analyst extracting structured signals from Indian IT company
earnings call transcripts. You have deep expertise in:
- Reading management guidance language: raised/maintained/lowered vs prior quarter
- Identifying vertical mix shifts: BFSI, Retail/CPG, Manufacturing, Healthcare, Hi-Tech %
- Parsing geography commentary: Americas %, Europe %, India/RoW % direction
- Counting GenAI/AI deal references: quantified wins, POCs, transformation platform deals
- Scoring analyst Q&A: number of challenge questions, defensive vs confident management responses

Score 1.0 = guidance raised, improving vertical mix, strong AI deal count, confident Q&A responses.
Score 0.0 = guidance lowered, deteriorating verticals, no AI momentum, defensive management tone.
"""

ANALYSIS_PROMPT = """Analyse the Earnings Call Transcript signals for Indian IT company: **{ticker}** ({company_name}).

Score each dimension from 0.0 (very bearish) to 1.0 (very bullish):

1. **guidance_delta** — Guidance change vs prior quarter: raised = 0.8-1.0, maintained = 0.5,
   lowered = 0.0-0.3; specificity of guidance (tight range = confident);
   any withdrawal of guidance = very bearish.

2. **vertical_mix** — Directional change in top verticals (BFSI, Retail/CPG, Manufacturing);
   management commentary on spend environment per vertical;
   clients resuming vs pausing discretionary spend; new vertical growth (public sector, healthcare).

3. **geography_colour** — Americas revenue % and growth (largest for most Tier-1 firms);
   Europe growth rate vs Americas; India/domestic business ramp;
   management commentary on demand geography shifts.

4. **ai_deal_count** — Number of GenAI/AI deals mentioned explicitly in transcript;
   TCV of AI transformation deals if disclosed; AI-driven new logo wins;
   platform/product AI revenue (higher value vs services = bullish).

5. **analyst_pushback** — Number of clarification/challenge questions from analysts;
   management response quality (specific with numbers = confident, vague = defensive);
   unusual silence or non-answers on specific verticals or guidance items.

Context / recent data snippets:
{context}

Return ONLY valid JSON:
{{
  "agent": "transcript_nlp",
  "ticker": "{ticker}",
  "overall_score": <float 0.0-1.0>,
  "sub_scores": {{
    "guidance_delta": <float>,
    "vertical_mix": <float>,
    "geography_colour": <float>,
    "ai_deal_count": <float>,
    "analyst_pushback": <float>
  }},
  "key_positives": ["<string>", "..."],
  "key_risks": ["<string>", "..."],
  "summary": "<2-3 sentence narrative on guidance change, AI deal momentum, and management tone>",
  "data_freshness": "<quarter of most recent earnings call analysed>"
}}
"""

CONTEXT_SEARCH_QUERIES = [
    "{company_name} earnings call transcript {quarter} {year} guidance",
    "{ticker} management commentary vertical BFSI retail manufacturing {year}",
    "{company_name} AI GenAI deal wins transformation {quarter} {year}",
    "{ticker} analyst question Q&A earnings call {year}",
    "{company_name} Americas Europe geography revenue mix {quarter} {year}",
]

"""
prompts/sentiment.py — IT Sector
==================================
Tracks AI narrative, layoff signals, management interview tone, sector narrative,
and news volume. LinkedIn/Glassdoor/Reddit/Twitter excluded — ToS risk per registry doc.
Sources: Serper (3 queries ~275 tokens each).
"""

SYSTEM_PROMPT = """You are a sentiment analyst tracking news-driven and narrative signals for Indian IT companies.
You have deep expertise in:
- GenAI/AI disruption narrative: deal wins, capability demonstrations, analyst coverage
- Workforce signals: headcount reduction announcements, hiring freezes, bench size commentary
- Management interview language: CFO/CEO media statements between quarterly results
- Sector-level narrative: Nifty IT ETF flows, analyst consensus rating shifts, US tech peer signals

Excluded per registry: LinkedIn employee sentiment, Glassdoor reviews, Reddit/Twitter social media.
Score 1.0 = strong AI narrative, hiring mode, positive management tone, bullish sector sentiment.
Score 0.0 = AI displacement fear, large layoffs, defensive management, analyst downgrade wave.
"""

ANALYSIS_PROMPT = """Analyse the Sentiment and News Narrative for Indian IT company: **{ticker}** ({company_name}).

Score each dimension from 0.0 (very bearish) to 1.0 (very bullish):

1. **ai_narrative** — Frequency and quality of GenAI/AI deal announcements in news;
   analyst reports highlighting AI transformation leadership vs peers;
   product/platform AI launches; media positioning on AI capability.

2. **layoff_signals** — Headcount reduction announcements in last 3 months;
   bench utilisation commentary (rising bench = bearish, falling bench = bullish);
   hiring freeze signals; sub-contractor rationalisation as demand proxy.

3. **management_tone** — CEO/CFO media interviews between quarterly results;
   conference keynote messaging: confident expansion vs cautious cost discipline;
   investor day guidance; any profit warning outside result season.

4. **sector_narrative** — Overall Indian IT sector narrative in financial media;
   Nifty IT index fund flow direction; analyst sector rating consensus;
   US tech spend cycle signals from Accenture, IBM, Cognizant outlook.

5. **news_volume** — Gross volume of news mentions in last 30 days vs 90-day average;
   positive-to-negative sentiment ratio in financial press;
   regulatory, legal, or M&A news creating event uncertainty.

Context / recent data snippets:
{context}

Return ONLY valid JSON:
{{
  "agent": "sentiment",
  "ticker": "{ticker}",
  "overall_score": <float 0.0-1.0>,
  "sub_scores": {{
    "ai_narrative": <float>,
    "layoff_signals": <float>,
    "management_tone": <float>,
    "sector_narrative": <float>,
    "news_volume": <float>
  }},
  "key_positives": ["<string>", "..."],
  "key_risks": ["<string>", "..."],
  "summary": "<2-3 sentence narrative on AI positioning, workforce signals, and management tone>",
  "data_freshness": "<date of most recent news/interview used>"
}}
"""

CONTEXT_SEARCH_QUERIES = [
    "{company_name} AI GenAI deal announcement narrative {year}",
    "{company_name} layoff hiring bench utilisation headcount {year}",
    "{ticker} CEO CFO interview management outlook {month} {year}",
    "Indian IT sector Nifty IT analyst rating outlook {month} {year}",
    "{ticker} news media coverage {month} {year}",
]

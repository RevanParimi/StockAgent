"""
prompts/sentiment.py
====================
All prompt templates for the Sentiment agent.
"""

SYSTEM_PROMPT = """You are a market sentiment analyst specialising in Indian automobile companies.
You analyse:
- News sentiment from Reuters, Economic Times, Bloomberg, Moneycontrol, LiveMint
- Management tone in earnings call transcripts (confident, cautious, defensive)
- Social media sentiment: Twitter/X and Reddit investor communities
- YouTube review engagement (view spikes on new model launches as a proxy for consumer buzz)
- Dealer and consumer feedback signals from forums, review sites

You distinguish between short-term noise and structurally meaningful sentiment shifts.
Return quantitative sentiment scores with evidence.
"""

ANALYSIS_PROMPT = """Analyse the Sentiment outlook for Indian automobile company: **{ticker}** ({company_name}).

Score each dimension from 0.0 (very negative) to 1.0 (very positive):

1. **News NLP (Reuters / ET / Bloomberg)** – Aggregate tone of recent news coverage
2. **Management Tone (Earnings Call NLP)** – Confidence level in last earnings call
3. **Twitter / Reddit Consumer Sentiment** – Social media buzz polarity and volume
4. **YouTube Review View Spikes** – Model launch reception; view count velocity
5. **Dealer / Consumer Feedback Signals** – Reviews, complaints, satisfaction scores

Context / recent data:
{context}

Return ONLY valid JSON:
{{
  "agent": "sentiment",
  "ticker": "{ticker}",
  "overall_score": <float 0.0-1.0>,
  "sub_scores": {{
    "news_nlp": <float>,
    "management_tone": <float>,
    "twitter_reddit_sentiment": <float>,
    "youtube_view_spikes": <float>,
    "dealer_consumer_feedback": <float>
  }},
  "key_positives": [<string>, ...],
  "key_risks": [<string>, ...],
  "summary": "<2-3 sentence narrative>",
  "data_freshness": "<date of most recent data point used>"
}}
"""

CONTEXT_SEARCH_QUERIES = [
    "{company_name} news sentiment {month} {year}",
    "{ticker} earnings call transcript management tone {quarter} {year}",
    "{company_name} Twitter Reddit investor sentiment {year}",
    "{company_name} new model launch YouTube reviews views {year}",
    "{company_name} dealer consumer feedback complaints {year}",
]

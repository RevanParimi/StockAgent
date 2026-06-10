"""
data/fetchers/transcript.py — IT Sector
==========================================
Fetches earnings call transcript text for NLP extraction by the Transcript NLP agent.

Sources (free tier):
  - Tavily → full earnings call transcript page (~500 tokens per fetch)
  - Serper → transcript snippet if Tavily fails (~275 tokens)

Status: stub — implement in Phase 7.
        ContextBuilder uses Tavily + Serper fallback for transcript context.
"""
from __future__ import annotations


def get_transcript_text(ticker: str, company_name: str, quarter: str) -> str:
    """
    Fetch earnings call transcript text for NLP analysis.

    Returns raw transcript text (truncated to ~3,000 tokens) covering:
    - Management prepared remarks
    - Guidance language (exact quotes)
    - Analyst Q&A section

    Implementation plan (Phase 7):
    1. Tavily search: "{company_name} earnings call transcript {quarter} {year}"
       → fetch the transcript page (Seeking Alpha, Motley Fool, company IR site)
       → returns up to 1,000 tokens of readable text
    2. Do 2-3 Tavily calls to cover prepared remarks + Q&A separately.
    3. Cache result for 90 days (transcripts don't change after publication).

    Fallback: Serper → fetches title + snippet of transcript summary articles.
    """
    raise NotImplementedError(
        "transcript.get_transcript_text not implemented — Phase 7. "
        "ContextBuilder uses Tavily + Serper news fallback."
    )


def get_guidance_extract(ticker: str, company_name: str, quarter: str) -> dict:
    """
    Extract structured guidance from transcript text.

    Returns dict with keys:
    - revenue_guidance_range (tuple[float, float] | None)  — in % CC growth
    - margin_guidance (str | None)  — e.g. "expanding 50-100bps"
    - guidance_direction (str)  — "raised" | "maintained" | "lowered" | "withdrawn"
    - vertical_commentary (dict)  — {vertical: "positive"|"cautious"|"neutral"}

    Implementation plan (Phase 7):
    1. Call get_transcript_text() to get raw text.
    2. Use regex + keyword patterns to extract guidance numbers.
    3. LLM mini-call (single GPT-4o-mini call, ~200 tokens) to classify direction.
    """
    raise NotImplementedError(
        "transcript.get_guidance_extract not implemented — Phase 7."
    )

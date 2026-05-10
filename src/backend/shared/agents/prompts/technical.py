"""
src/backend/shared/agents/prompts/technical.py
===============================================
Single source of truth for technical / pattern-analysis prompts.

Replaces 4 duplicate prompt files:
  - automobile/prompts/pattern_analysis.py
  - banking_bfsi/prompts/pattern_analysis.py
  - it_sector/prompts/pattern_analysis.py
  - renewable_energy/prompts/technical.py

Standardised sub_scores across all sectors:
  price_cycle          — position in multi-year price cycle
  momentum             — RSI / MACD / Bollinger signal
  breakout_zones       — support / resistance proximity + quality
  peer_relative_strength — alpha vs sector index
  volume_confirmation  — price-volume relationship quality

Usage in registry.py:
  from backend.shared.agents.prompts.technical import AUTO_TECHNICAL
  UniversalAgent("pattern_analysis", AUTO_TECHNICAL, sector="automobile")
"""
from __future__ import annotations

from types import SimpleNamespace

# ---------------------------------------------------------------------------
# Base templates — use {{ticker}} / {{context}} so they survive the first
# .format() call that injects sector-specific values.
# ---------------------------------------------------------------------------

_SYSTEM_BASE = """\
You are a quantitative technical analyst specialising in Indian equity markets
({sector_name} sector).

Your expertise:
- Multi-year price cycle detection and position mapping
- RSI (14-period), MACD (12/26/9), Bollinger Bands — momentum signals
- Support / resistance and breakout zone identification
- Relative strength vs {sector_index} (sector benchmark index)
- Volume confirmation of price moves (accumulation vs distribution)

Reference index: {sector_index} · Peer context: {peer_context}

You score objectively. You do NOT predict the future; you describe the current
technical posture of the stock on a 0–1 scale where:
  1.0 = strong bullish setup (accumulation zone, rising momentum, outperforming peers)
  0.5 = neutral / mixed signals
  0.0 = weak / bearish setup (distribution, declining momentum, underperforming)
"""

_ANALYSIS_BASE = """\
Analyse the Technical outlook for {sector_name} stock: **{{ticker}}** ({{company_name}}).

Score each dimension from 0.0 (bearish) to 1.0 (bullish):

1. **price_cycle** — Where in the multi-year price cycle is this stock?
   Bottoming / early accumulation = 1.0 · Mid-cycle trending = 0.7 ·
   Late-cycle / distribution = 0.3 · Clear downtrend = 0.0
   {seasonal_note}

2. **momentum** — RSI (14), MACD (12/26/9), Bollinger Band position.
   RSI 50–68 + MACD crossover above signal + price above mid-BB = 1.0
   RSI < 40 + MACD below signal + price below lower BB = 0.0

3. **breakout_zones** — Quality and proximity of support/resistance levels.
   Strong multi-tested support immediately below + low downside risk = 1.0
   Sitting at resistance with no support nearby = 0.0

4. **peer_relative_strength** — Alpha vs {sector_index} over last 90 days.
   Outperforming sector index by >5% = 1.0 · In-line = 0.5 ·
   Underperforming by >5% = 0.0

5. **volume_confirmation** — Volume quality relative to price action.
   Rising price + rising volume = accumulation = 1.0
   Rising price + falling volume = weak rally, unconfirmed = 0.3
   Distribution on high volume = 0.0

Technical data provided:
{{context}}

Return ONLY valid JSON:
{{{{
  "agent": "technical",
  "ticker": "{{ticker}}",
  "overall_score": <float 0.0-1.0>,
  "sub_scores": {{{{
    "price_cycle": <float>,
    "momentum": <float>,
    "breakout_zones": <float>,
    "peer_relative_strength": <float>,
    "volume_confirmation": <float>
  }}}},
  "key_positives": ["<string>", "..."],
  "key_risks": ["<string>", "..."],
  "summary": "<2-3 sentence narrative on current technical posture>",
  "data_freshness": "<date of most recent data used>"
}}}}
"""

_QUERIES_BASE = [
    "{{ticker}} RSI MACD Bollinger technical analysis {sector_name} {{year}}",
    "{{ticker}} {sector_index} relative performance alpha beta {{year}}",
    "{{ticker}} support resistance breakout levels price chart {{month}} {{year}}",
    "{sector_name} sector index {sector_index} technical trend {{month}} {{year}}",
    "{{ticker}} 52-week high low price cycle position {{year}}",
]


def _make(
    sector_name: str,
    sector_index: str,
    peer_context: str,
    seasonal_note: str = "",
) -> SimpleNamespace:
    """
    Build a prompts namespace for a specific sector. The returned object
    exposes SYSTEM_PROMPT, ANALYSIS_PROMPT, CONTEXT_SEARCH_QUERIES —
    the same interface that UniversalAgent expects from any prompts module.
    """
    system = _SYSTEM_BASE.format(
        sector_name=sector_name,
        sector_index=sector_index,
        peer_context=peer_context,
    )
    # First .format() fills sector vars; {{...}} becomes {...} for UniversalAgent
    analysis = _ANALYSIS_BASE.format(
        sector_name=sector_name,
        sector_index=sector_index,
        seasonal_note=seasonal_note,
    )
    queries = [
        q.format(sector_name=sector_name, sector_index=sector_index)
        for q in _QUERIES_BASE
    ]
    return SimpleNamespace(
        SYSTEM_PROMPT=system,
        ANALYSIS_PROMPT=analysis,
        CONTEXT_SEARCH_QUERIES=queries,
    )


# ---------------------------------------------------------------------------
# Module-level sector instances — import directly in registry.py
# ---------------------------------------------------------------------------

AUTO_TECHNICAL = _make(
    sector_name    = "Automobile",
    sector_index   = "^CNXAUTO",
    peer_context   = "Maruti, Tata Motors, M&M, Bajaj Auto, Hero MotoCorp, Eicher",
    seasonal_note  = "Note: auto sector has strong Q2/Q3 festive-season tailwinds "
                     "— weight seasonal position in price_cycle scoring.",
)

BANKING_TECHNICAL = _make(
    sector_name    = "Banking & BFSI",
    sector_index   = "^NSEBANK",
    peer_context   = "HDFC Bank, ICICI Bank, SBI, Kotak, Axis, IndusInd",
    seasonal_note  = "Note: banking stocks are rate-cycle sensitive — price_cycle "
                     "should reflect position relative to RBI rate-cut/hike regime.",
)

IT_TECHNICAL = _make(
    sector_name    = "IT & Technology",
    sector_index   = "^CNXIT",
    peer_context   = "TCS, Infosys, HCL Tech, Wipro, Tech Mahindra, LTIMindtree",
    seasonal_note  = "Note: IT stocks are USD/rate sensitive growth stocks — "
                     "price_cycle should reflect Fed rate and US macro cycle position.",
)

RE_TECHNICAL = _make(
    sector_name    = "Renewable Energy",
    sector_index   = "^CNXENERGY",
    peer_context   = "Adani Green, Tata Power, NTPC, JSW Energy, Suzlon",
    seasonal_note  = "Note: RE stocks often move on policy announcements (MNRE, Budget) "
                     "— price_cycle should reflect policy cycle as well as price cycle.",
)

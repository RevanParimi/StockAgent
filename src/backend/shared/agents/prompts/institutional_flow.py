"""
src/backend/shared/agents/prompts/institutional_flow.py
=========================================================
Single source of truth for institutional / smart-money flow prompts.

Replaces 2 near-duplicate prompt files:
  - banking_bfsi/prompts/institutional.py
  - it_sector/prompts/insider_smart_money.py

Shared tracking objective (both agents):
  - FII/DII shareholding changes (quarterly)
  - Promoter stake movements (SAST filings)
  - Mutual fund holding deltas (AMFI monthly)
  - Bulk / block deals on exchange
  - Insider / director trades (SEBI disclosures)

Standardised sub_scores:
  fii_dii_flow       — FII + DII net directional signal
  promoter_activity  — promoter stake + pledge changes
  mf_holding_change  — AMFI monthly MF delta
  bulk_block_deals   — large exchange trades
  insider_activity   — director / KMP SEBI disclosures

Sector-level difference parametrized:
  Banking → fii_dii_flow focuses on Nifty Bank FII cash positioning
  IT      → fii_dii_flow focuses on FII F&O net futures position (forward signal)

Usage:
  from backend.shared.agents.prompts.institutional_flow import BANKING_INSTITUTIONAL
  UniversalAgent("institutional", BANKING_INSTITUTIONAL, sector="banking_bfsi")
"""
from __future__ import annotations

from types import SimpleNamespace

_SYSTEM_BASE = """\
You are an equity analyst tracking institutional and smart-money flows for
Indian {sector_name} stocks. You have deep expertise in:

- Quarterly FII/DII shareholding pattern changes (BSE/NSE bulk + quarterly data)
- Promoter SAST filing analysis: >2% acquisitions, creeping vs open-offer signals
- AMFI monthly MF portfolio changes: large fund buying/trimming signals
- BSE/NSE bulk deal and block trade identification: institutional accumulation
- SEBI insider trading disclosures: director / KMP trades as conviction signal

{fii_note}

Smart-money consensus scoring:
  1.0 = clear accumulation (FII buying + promoter adding + MF increasing + large block buys)
  0.5 = mixed / neutral flows
  0.0 = distribution (FII selling + promoter pledge increase + MF reducing + insider selling)
"""

_ANALYSIS_BASE = """\
Analyse the Institutional Flow picture for {sector_name} stock: **{{ticker}}** ({{company_name}}).

Score each dimension from 0.0 (bearish flows / distribution) to 1.0 (bullish / accumulation):

1. **fii_dii_flow** — {fii_dimension_label}
   FII increasing stake / net buying = 1.0 · Neutral = 0.5 · FII reducing / net selling = 0.0

2. **promoter_activity** — Promoter stake change + pledge trend (SAST filings).
   Stake increasing + pledge reducing = 1.0 · Stake stable, no pledge = 0.5 ·
   Stake falling or pledge increasing = 0.0

3. **mf_holding_change** — AMFI monthly MF portfolio delta (last 3 months).
   Multiple large funds increasing = 1.0 · Mixed = 0.5 · Across-the-board reducing = 0.0

4. **bulk_block_deals** — Quality and direction of large exchange trades (last 60 days).
   Institutional buy-side dominance at higher prices = 1.0 ·
   Large sell blocks at lower prices = 0.0

5. **insider_activity** — Director / KMP trades (SEBI UPSI disclosures).
   Board members buying in open market = 1.0 · No activity = 0.5 ·
   Insiders selling = 0.0

Data context:
{{context}}

Return ONLY valid JSON:
{{{{
  "agent": "institutional_flow",
  "ticker": "{{ticker}}",
  "overall_score": <float 0.0-1.0>,
  "sub_scores": {{{{
    "fii_dii_flow": <float>,
    "promoter_activity": <float>,
    "mf_holding_change": <float>,
    "bulk_block_deals": <float>,
    "insider_activity": <float>
  }}}},
  "key_positives": ["<string>", "..."],
  "key_risks": ["<string>", "..."],
  "summary": "<2-3 sentence narrative on net institutional positioning>",
  "data_freshness": "<date of most recent shareholding / AMFI data used>"
}}}}
"""

_QUERIES_BASE = [
    "{ticker} FII DII shareholding quarterly change {quarter} {year}",
    "{ticker} promoter stake SAST filing pledge BSE {year}",
    "AMFI {ticker} mutual fund monthly portfolio {month} {year}",
    "{ticker} BSE bulk deal block trade {month} {year}",
    "{ticker} insider trading SEBI disclosure director KMP {year}",
]


def _make(
    sector_name: str,
    fii_note: str,
    fii_dimension_label: str,
) -> SimpleNamespace:
    system = _SYSTEM_BASE.format(
        sector_name=sector_name,
        fii_note=fii_note,
    )
    analysis = _ANALYSIS_BASE.format(
        sector_name=sector_name,
        fii_dimension_label=fii_dimension_label,
    )
    return SimpleNamespace(
        SYSTEM_PROMPT=system,
        ANALYSIS_PROMPT=analysis,
        CONTEXT_SEARCH_QUERIES=list(_QUERIES_BASE),
    )


# ---------------------------------------------------------------------------
# Sector instances
# ---------------------------------------------------------------------------

BANKING_INSTITUTIONAL = _make(
    sector_name = "Banking & BFSI",
    fii_note    = (
        "For banking stocks, FII cash-market flows are the primary signal. "
        "Nifty Bank FII shareholding change matters more than F&O positioning "
        "since private banks are held as core portfolio allocations."
    ),
    fii_dimension_label = (
        "FII quarterly shareholding change + DII (MF+Insurance) net direction "
        "in cash market. Key: private bank FII stake above 40% = positive."
    ),
)

IT_INSTITUTIONAL = _make(
    sector_name = "IT & Technology",
    fii_note    = (
        "For IT stocks, FII F&O net futures position is a leading signal alongside "
        "cash-market shareholding. Short covering in Nifty IT futures often "
        "precedes sector re-rating. Watch SEBI SAST >2% triggers carefully — "
        "Indian IT promoter acquisitions are rare and highly significant."
    ),
    fii_dimension_label = (
        "FII cash-market shareholding change + net futures position (F&O) combined. "
        "Heavy FII F&O long buildup = forward accumulation signal."
    ),
)

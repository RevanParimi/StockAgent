"""
prompts/dimensions.py — generic sector (Compass Phase B).

Per-dimension prompt objects for the LEGACY worker-pool fallback path
(BaseSectorOrchestrator requires a non-empty _sub_agents dict; the pool only
runs when the unified analyst totally fails and
UNIFIED_ANALYST_FALLBACK_LEGACY is true). UniversalAgent duck-types its
prompts_module, so SimpleNamespace objects are sufficient — no need for
8 separate files.
"""
from __future__ import annotations

from types import SimpleNamespace

DIMENSIONS: list[str] = [
    "business", "fundamentals", "valuation", "technical",
    "macro", "risk", "management", "earnings",
]

_FOCUS: dict[str, str] = {
    "business": ("revenue mix, market position, demand trajectory, competitive moat, "
                 "customer/geography concentration, growth pipeline"),
    "fundamentals": ("revenue and profit growth, margin trend vs industry norm, RoE/RoCE, "
                     "leverage and interest cover, cash-flow conversion"),
    "valuation": ("P/E and EV/EBITDA vs peers and own history, growth-adjusted multiple, "
                  "price/book, asset backing — scores only, no price targets"),
    "technical": ("trend vs 50/200-DMA, RSI/momentum, volume confirmation, "
                  "distance to 52-week high/low, support/resistance"),
    "macro": ("interest-rate and currency sensitivity, commodity inputs, sector policy "
              "direction, domestic vs export demand cycle"),
    "risk": ("balance-sheet stress, regulatory/litigation overhangs, concentration risks, "
             "execution risk, surveillance-list red flags"),
    "management": ("promoter track record and pledge, capital allocation, related-party "
                   "complexity, guidance credibility, audit hygiene"),
    "earnings": ("quarterly trajectory vs run-rate, one-offs/exceptionals, "
                 "revenue-recognition red flags, beat/miss vs guidance"),
}

_QUERIES: dict[str, list[str]] = {
    "business": ["{ticker} business growth market share {year}",
                 "{company_name} demand orders outlook {year}"],
    "fundamentals": ["{ticker} quarterly results revenue margin {year}",
                     "{company_name} debt RoCE cash flow {year}"],
    "valuation": ["{ticker} valuation P/E EV/EBITDA peers {year}"],
    "technical": ["{ticker} stock price technical analysis {year}"],
    "macro": ["India {company_name} sector policy demand outlook {year}"],
    "risk": ["{ticker} risk litigation regulatory {year}"],
    "management": ["{ticker} promoter pledge governance {year}"],
    "earnings": ["{ticker} earnings results {quarter} {year}"],
}


def _make_prompt(dim: str) -> SimpleNamespace:
    system = (
        "You are a senior Indian-equity research analyst applying a sector-agnostic "
        f"framework. Assess ONLY the '{dim}' dimension of the stock: {_FOCUS[dim]}. "
        "Score strictly from the provided context — if data is missing, score 0.5 "
        "(neutral) and say so in key_risks. Return ONLY valid JSON with keys: "
        "overall_score (0.0-1.0), key_positives (list), key_risks (list), "
        "summary (<=2 sentences), data_freshness."
    )
    user = (
        "Analyse {ticker} ({company_name}) on the '" + dim + "' dimension using ONLY "
        "this context:\n\n{context}\n\n"
        "Return the JSON object now."
    )
    return SimpleNamespace(
        SYSTEM_PROMPT=system,
        ANALYSIS_PROMPT=user,
        CONTEXT_SEARCH_QUERIES=list(_QUERIES[dim]),
    )


PROMPTS: dict[str, SimpleNamespace] = {dim: _make_prompt(dim) for dim in DIMENSIONS}

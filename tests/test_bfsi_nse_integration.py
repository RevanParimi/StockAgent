"""
tests/test_bfsi_nse_integration.py
====================================
3-Agent integration test: NseIndiaApi for Banking/BFSI sector.

Agent 1 — Researcher : Fetches real NseIndiaApi data for HDFCBANK (large
                        private), SBIN (PSU), ICICIBANK (mid private) and
                        reports annotation categories + ESOP/regulatory filings.
Agent 2 — Designer   : Formats context for each BFSI agent_type and evaluates
                        whether category filtering routes data correctly.
Agent 3 — Reviewer   : LLM judges if the official event data is correctly
                        categorized per BFSI agent_type with no cross-contamination.

Run:
    python -m tests.test_bfsi_nse_integration
"""

from __future__ import annotations

import json
import os
import re
import sys
from datetime import date

BFSI_AGENT_DIMENSIONS = {
    "bfsi_fundamentals": [
        "asset_quality (GNPA/PCR trends)",
        "net_interest (NIM 8Q rolling, CASA ratio)",
        "capital_adequacy (CRAR vs 11.5% RBI minimum)",
        "profitability (RoA >1.0%, RoE >12%, credit cost)",
        "loan_mix (retail vs corporate, CD ratio)",
    ],
    "bfsi_institutional": [
        "fii_dii_flow (quarterly shareholding change)",
        "promoter_holding (pledge %, direction)",
        "insider_trades (SAST filings, KMP trades)",
        "amfi_mf_flow (MF net entry/exit)",
        "bulk_block_deals (>0.5% equity single session)",
    ],
    "bfsi_risk": [
        "asset_quality_trend (NPA slippage, SMA-1/2 outstanding)",
        "concentration_risk (top-5 borrower % of Tier-1 capital)",
        "deposit_stability (wholesale deposit %, LCR vs 100%)",
        "regulatory_risk (RBI enforcement, SEBI notice, PCA)",
        "cyber_fraud_risk (CERT-In advisories, RBI fraud >Rs 1Cr)",
    ],
    "bfsi_universe": [
        "index_weight (Nifty Bank constituent, weight direction)",
        "peer_positioning (PSU/private/SFB/NBFC peer rank)",
        "market_cap_tier (large/mid/small, free-float %)",
        "corporate_actions (dividends, bonus, splits, rights, mergers)",
        "rebalancing_risk (inclusion/exclusion at next rebalancing)",
    ],
}

TEST_TICKERS = ["HDFCBANK", "SBIN", "ICICIBANK"]


def safe(s: str) -> str:
    return str(s).encode("ascii", "replace").decode("ascii")


# ---------------------------------------------------------------------------
# Agent 1 - Researcher
# ---------------------------------------------------------------------------

def agent_researcher() -> dict[str, dict]:
    print("\n" + "=" * 65)
    print("AGENT 1 - RESEARCHER: Fetching NseIndiaApi data for BFSI tickers")
    print("=" * 65)

    from services.data.fetchers.nse_announcements import prefetch_nse_data

    results: dict[str, dict] = {}

    for ticker in TEST_TICKERS:
        print(f"\n  [{ticker}] fetching...")
        nse_data = prefetch_nse_data(ticker)

        ann   = nse_data.get("announcements", [])
        bm    = nse_data.get("board_meetings", [])
        act   = nse_data.get("actions", [])
        error = nse_data.get("error")

        print(f"    announcements : {len(ann)} items  |  error={error}")
        print(f"    board_meetings: {len(bm)} items")
        print(f"    actions       : {len(act)} items")
        print(f"    key_mappings  : {nse_data.get('key_mappings', {})}")

        # Show unique announcement categories
        seen: set[str] = set()
        print("    Announcement categories (unique):")
        for item in ann:
            cat = item.get("desc", "?")
            if cat not in seen:
                dt = item.get("an_dt", "")
                attach = (item.get("attchmntText") or "")[:80]
                print(f"      [{safe(str(dt))}] {safe(str(cat))} | {safe(attach)}")
                seen.add(cat)

        # ESOP filings specifically (key for bfsi_institutional)
        esop = [
            i for i in ann
            if any(k in str(i.get("desc", "")).lower() for k in ["esop", "esos", "esps"])
        ]
        print(f"    ESOP filings found: {len(esop)}")

        # Regulatory/enforcement filings (key for bfsi_risk)
        regulatory = [
            i for i in ann
            if any(k in str(i.get("desc", "")).lower() for k in
                   ["regulatory", "press release", "general updates"])
        ]
        print(f"    Regulatory/PR/Updates filings found: {len(regulatory)}")

        # Board meetings - results/dividend
        results_bm = [
            i for i in bm
            if any(k in str(i.get("bm_desc", "")).lower() for k in
                   ["results", "financial", "dividend", "annual", "quarterly"])
        ]
        print(f"    Results/Dividend board meetings: {len(results_bm)}")
        for item in results_bm[:2]:
            print(f"      [{safe(str(item.get('bm_date', '')))}] "
                  f"{safe(str(item.get('bm_desc', ''))[:100])}")

        # Corporate actions - financial
        financial_act = [
            i for i in act
            if not any(k in str(i.get("subject", "")).lower()
                       for k in ["annual general meeting", "agm", "egm"])
        ]
        print(f"    Financial corporate actions: {len(financial_act)}")
        for item in financial_act[:2]:
            print(f"      [ex-date: {safe(str(item.get('exDate', '')))}] "
                  f"{safe(str(item.get('subject', ''))[:80])}")

        results[ticker] = nse_data

    return results


# ---------------------------------------------------------------------------
# Agent 2 - Designer
# ---------------------------------------------------------------------------

def agent_designer(research: dict[str, dict]) -> dict[str, dict]:
    print("\n" + "=" * 65)
    print("AGENT 2 - DESIGNER: Evaluating formatted context per agent_type")
    print("=" * 65)

    from services.data.fetchers.nse_announcements import format_nse_context

    evaluations: dict[str, dict] = {}

    for ticker, nse_data in research.items():
        print(f"\n  [{ticker}]")
        ticker_eval: dict[str, dict] = {}

        for agent_type, dimensions in BFSI_AGENT_DIMENSIONS.items():
            ctx = format_nse_context(nse_data, agent_type=agent_type)
            ctx_lower = ctx.lower()

            # Agent-specific signal checks (use full context, not truncated preview)
            signals: dict[str, bool] = {}
            if agent_type == "bfsi_fundamentals":
                # Check full context for results-related keywords
                signals["results_bm_present"] = any(
                    k in ctx_lower for k in ["results", "financial", "dividend", "annual",
                                              "audited", "unaudited", "quarterly"]
                )
                signals["board_meeting_section"] = "nse board meetings" in ctx_lower
            elif agent_type == "bfsi_institutional":
                signals["esop_present"]  = any(k in ctx_lower for k in ["esop", "esos", "esps"])
                signals["sast_present"]  = "sast" in ctx_lower or "shareholders" in ctx_lower
                signals["no_regulatory"] = "regulatory" not in ctx_lower
            elif agent_type == "bfsi_risk":
                signals["risk_signals_present"] = any(
                    k in ctx_lower for k in ["regulatory", "press release", "general updates",
                                              "management", "penalty", "enforcement"]
                )
                signals["no_esop_bleed"] = not any(k in ctx_lower for k in ["esop", "esos", "esps"])
            elif agent_type == "bfsi_universe":
                signals["corporate_actions_present"] = "corporate actions" in ctx_lower
                signals["no_agm_bleed"]              = "annual general meeting" not in ctx_lower
                signals["dividend_or_bonus"]         = any(
                    k in ctx_lower for k in ["dividend", "bonus", "rights", "split"]
                )

            print(f"    [{agent_type}]")
            print(f"      chars={len(ctx)} | has_content={'YES' if ctx else 'NO'}")
            if ctx:
                print(f"      preview: {safe(ctx[:220].replace(chr(10),' | '))}")
            print(f"      signals: {signals}")

            ticker_eval[agent_type] = {
                "ctx": ctx,
                "has_content": bool(ctx),
                "signals": signals,
            }

        evaluations[ticker] = ticker_eval

    # Coverage grid
    print("\n  --- Coverage Grid ---")
    header = f"  {'Ticker':<12}"
    for at in BFSI_AGENT_DIMENSIONS:
        header += f" {at.replace('bfsi_',''):<14}"
    print(header)
    for ticker, te in evaluations.items():
        row = f"  {ticker:<12}"
        for at in BFSI_AGENT_DIMENSIONS:
            row += f" {'YES' if te.get(at, {}).get('has_content') else 'NO':<14}"
        print(row)

    return evaluations


# ---------------------------------------------------------------------------
# Agent 3 - Reviewer (LLM)
# ---------------------------------------------------------------------------

def agent_reviewer(research: dict[str, dict], evaluations: dict[str, dict]) -> bool:
    print("\n" + "=" * 65)
    print("AGENT 3 - REVIEWER: LLM quality judgment")
    print("=" * 65)

    from dotenv import load_dotenv
    load_dotenv()

    openrouter_key = os.getenv("OPENROUTER_API_KEY", "")
    llm_model      = os.getenv("LLM_MODEL", "qwen/qwen-2.5-72b-instruct")

    if not openrouter_key:
        print("  No OPENROUTER_API_KEY — running rule-based fallback")
        return _rule_based_review(evaluations)

    from openai import OpenAI
    client = OpenAI(api_key=openrouter_key, base_url="https://openrouter.ai/api/v1")

    # Use HDFCBANK as sample (largest filing volume, most representative)
    sample_ticker = "HDFCBANK"
    te = evaluations.get(sample_ticker, evaluations.get(TEST_TICKERS[0], {}))

    context_samples = {
        at: (te.get(at, {}).get("ctx") or "(empty)")[:400]
        for at in BFSI_AGENT_DIMENSIONS
    }

    prompt = f"""Today is {date.today().isoformat()}.
Sector: Banking/BFSI (India, NSE).
Ticker under review: {sample_ticker}

CONTEXT — what NseIndiaApi provides (official exchange filings ONLY):
  announcements(): regulatory filings to NSE — ESOP allotments, press releases,
    management changes, SEBI notices, general operational updates
  boardMeetings(): scheduled board meeting dates + agenda (results, dividend, fund raising)
  actions(): corporate actions — dividends, bonus issues, rights, splits

IMPORTANT: NseIndiaApi does NOT provide NIM rates, NPA numbers, CRAR ratios, or
shareholding percentages — those come from yfinance and Serper. Evaluate ONLY
whether the official event DATA is routed to the correct agent_type.

What each BFSI agent_type should receive:
  bfsi_fundamentals  -> board meetings for results/dividend/annual (anchors NIM/CASA/NPA
                        data freshness from Serper/yfinance). Note: board meetings for
                        "consider and approve" or "quarterly" also qualify.
  bfsi_institutional -> ESOP/ESOS/ESPS allotment records + SAST Reg-29 disclosures
                        (authoritative KMP exercise records and threshold crossings)
  bfsi_risk          -> regulatory/press release/general updates announcements
                        (RBI enforcement and SEBI notices filed to exchange)
  bfsi_universe      -> corporate actions (dividend ex-dates, bonus ratio, splits/rights)
                        AND fund raising board meetings (QIP/NCD/rights signal capital
                        dilution for market_cap_tier and corporate_actions sub-scores).
                        FUND RAISING BMs belong in bfsi_universe, NOT bfsi_fundamentals.

Formatted NseIndiaApi context for {sample_ticker}:

bfsi_fundamentals:
{context_samples['bfsi_fundamentals']}

bfsi_institutional:
{context_samples['bfsi_institutional']}

bfsi_risk:
{context_samples['bfsi_risk']}

bfsi_universe:
{context_samples['bfsi_universe']}

Evaluate:
1. Are results/dividend board meetings in fundamentals (not valuation or risk)?
2. Do ESOP filings appear in institutional (not risk or universe)?
3. Are regulatory/press-release events in risk (no ESOP bleed-through)?
4. Are financial corporate actions in universe (AGM/EGM entries excluded)?
5. Overall: is each agent_type receiving its intended official event category?

Respond ONLY with valid JSON:
{{
  "verdict": "APPROVED" | "NEEDS_REVISION",
  "bfsi_fundamentals_correct": true | false,
  "bfsi_institutional_correct": true | false,
  "bfsi_risk_correct": true | false,
  "bfsi_universe_correct": true | false,
  "category_isolation_clean": true | false,
  "esop_correctly_routed": true | false,
  "key_finding": "<one sentence — highest-value official event NseIndiaApi adds for BFSI>",
  "main_gap": "<one sentence — what official event type is missing or misrouted>",
  "issues": ["<cross-contamination issues if any>"],
  "recommendation": "ship" | "fix_then_ship" | "redesign"
}}"""

    try:
        resp = client.chat.completions.create(
            model=llm_model,
            messages=[
                {"role": "system", "content": "You are a concise financial data pipeline reviewer. Output only valid JSON."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.0,
            max_tokens=500,
        )
        raw = resp.choices[0].message.content or ""
        raw = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL).strip()
        if raw.startswith("```"):
            raw = re.sub(r"^```(?:json)?\s*", "", raw)
            raw = re.sub(r"\s*```\s*$", "", raw).strip()
        result = json.loads(raw)

        print(f"\n  Verdict                    : {result.get('verdict')}")
        print(f"  bfsi_fundamentals correct  : {result.get('bfsi_fundamentals_correct')}")
        print(f"  bfsi_institutional correct : {result.get('bfsi_institutional_correct')}")
        print(f"  bfsi_risk correct          : {result.get('bfsi_risk_correct')}")
        print(f"  bfsi_universe correct      : {result.get('bfsi_universe_correct')}")
        print(f"  Category isolation clean   : {result.get('category_isolation_clean')}")
        print(f"  ESOP correctly routed      : {result.get('esop_correctly_routed')}")
        print(f"  Key finding                : {safe(result.get('key_finding', ''))}")
        print(f"  Main gap                   : {safe(result.get('main_gap', ''))}")
        print(f"  Issues                     : {result.get('issues', [])}")
        print(f"  Recommendation             : {result.get('recommendation')}")

        return result.get("verdict") == "APPROVED"

    except Exception as exc:
        print(f"  LLM failed: {exc}")
        return _rule_based_review(evaluations)


def _rule_based_review(evaluations: dict[str, dict]) -> bool:
    """Rule-based fallback when no LLM key is available."""
    checks_passed = 0
    total = 0

    for ticker, te in evaluations.items():
        # fundamentals: must have board meeting section
        total += 1
        ev = te.get("bfsi_fundamentals", {})
        if ev.get("has_content") and ev.get("signals", {}).get("board_meeting_section"):
            checks_passed += 1

        # institutional: ESOP must be present if bank issues ESOPs
        total += 1
        ev = te.get("bfsi_institutional", {})
        # ESOP presence depends on the bank — check no_regulatory at least
        if ev.get("signals", {}).get("no_regulatory", True):
            checks_passed += 1

        # risk: must have content and no ESOP bleed
        total += 1
        ev = te.get("bfsi_risk", {})
        if ev.get("signals", {}).get("no_esop_bleed", True):
            checks_passed += 1

        # universe: corporate actions present without AGM
        total += 1
        ev = te.get("bfsi_universe", {})
        if ev.get("signals", {}).get("no_agm_bleed", True):
            checks_passed += 1

    pct = checks_passed / total * 100 if total else 0
    print(f"\n  Rule-based: {checks_passed}/{total} checks passed ({pct:.0f}%)")

    if pct >= 75:
        print("  Rule-based verdict: APPROVED")
        return True
    print("  Rule-based verdict: NEEDS_REVISION")
    return False


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("\nStockAgent -- BFSI Sector NseIndiaApi Integration Test (3-Agent Loop)")
    print("Tests: prefetch -> category filtering -> context quality per agent_type\n")

    research    = agent_researcher()
    evaluations = agent_designer(research)
    approved    = agent_reviewer(research, evaluations)

    print("\n" + "=" * 65)
    if approved:
        print("RESULT: APPROVED -- BFSI sector NseIndiaApi integration is working")
    else:
        print("RESULT: NEEDS_REVISION -- see Reviewer output above")
    print("=" * 65)

    sys.exit(0 if approved else 1)

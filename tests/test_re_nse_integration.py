"""
tests/test_re_nse_integration.py
=================================
3-Agent integration test: NseIndiaApi for Renewable Energy sector.

Agent 1 — Researcher : Fetches real NseIndiaApi data for NTPC, TATAPOWER,
                        ADANIGREEN and reports raw counts + sample fields.
Agent 2 — Designer   : Formats context for each RE agent_type and evaluates
                        whether the data covers each scoring dimension.
Agent 3 — Reviewer   : LLM judges if the context output would genuinely help
                        an LLM agent score the 5 RE sub-dimensions correctly,
                        and confirms no regression in category filtering.

Run:
    python -m tests.test_re_nse_integration

No external API key needed beyond OPENROUTER_API_KEY for the Reviewer agent.
"""

from __future__ import annotations

import json
import os
import re
import sys
from datetime import date

# ── score dimensions per RE agent ────────────────────────────────────────────
RE_AGENT_DIMENSIONS = {
    "re_fundamentals": [
        "capacity_utilisation (CUF % vs benchmark)",
        "ebitda_quality (EBITDA/MW 8Q trend)",
        "debt_serviceability (DSCR)",
        "receivables (DISCOM aging)",
        "leverage (D/E, holdco debt)",
    ],
    "re_business": [
        "subsector_mix (solar/wind/hybrid MW split)",
        "ppa_quality (tariff Rs/kWh vs MNRE L1)",
        "pipeline_cred (commissioning record, on-time %)",
        "customer_divers (DISCOM vs C&I %)",
        "geography_spread (state-wise MW)",
    ],
    "re_valuation": [
        "ev_per_mw (EV/MW vs Rs 4-6 Cr/MW benchmark)",
        "ev_ebitda (vs 15-25x healthy range)",
        "tariff_vs_auction (PPA tariff premium over L1)",
        "pipeline_dcf (unbuilt pipeline DCF, -25% haircut)",
        "implied_irr (equity IRR vs WACC spread >200bp)",
    ],
    "re_risk": [
        "discom_credit (PFC score, >180d receivables)",
        "curtailment_risk (state CERC data)",
        "ppa_protection (force majeure, renegotiation)",
        "execution_risk (commissioning delay, LDs)",
        "promoter_pledge (pledge %, direction)",
    ],
}

TEST_TICKERS = ["NTPC", "TATAPOWER", "ADANIGREEN"]


def safe(s: str) -> str:
    return str(s).encode("ascii", "replace").decode("ascii")


# ─────────────────────────────────────────────────────────────────────────────
# Agent 1 — Researcher
# ─────────────────────────────────────────────────────────────────────────────

def agent_researcher() -> dict[str, dict]:
    print("\n" + "=" * 65)
    print("AGENT 1 - RESEARCHER: Fetching NseIndiaApi data for RE tickers")
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

        # Show sample announcements with their categories
        if ann:
            print(f"    Sample announcement categories:")
            seen_cats: set[str] = set()
            for item in ann[:10]:
                cat = item.get("desc", item.get("subject", "?"))
                if cat not in seen_cats:
                    dt = item.get("an_dt", item.get("date", ""))
                    attach = (item.get("attchmntText") or "")[:80]
                    print(f"      [{safe(str(dt))}] {safe(str(cat))} | {safe(attach)}")
                    seen_cats.add(cat)

        # Check for commissioning announcements specifically
        commissioning = [
            item for item in ann
            if "commencement of commercial production" in str(item.get("desc", "")).lower()
        ]
        print(f"    COMMISSIONING filings found: {len(commissioning)}")
        for item in commissioning[:3]:
            dt = item.get("an_dt", "")
            attach = (item.get("attchmntText") or item.get("desc", ""))[:120]
            print(f"      [{safe(str(dt))}] {safe(attach)}")

        results[ticker] = nse_data

    return results


# ─────────────────────────────────────────────────────────────────────────────
# Agent 2 — Designer
# ─────────────────────────────────────────────────────────────────────────────

def agent_designer(research: dict[str, dict]) -> dict[str, dict]:
    print("\n" + "=" * 65)
    print("AGENT 2 - DESIGNER: Evaluating formatted context per agent_type")
    print("=" * 65)

    from services.data.fetchers.nse_announcements import format_nse_context

    evaluations: dict[str, dict] = {}

    for ticker, nse_data in research.items():
        print(f"\n  [{ticker}]")
        ticker_eval: dict[str, dict] = {}

        for agent_type, dimensions in RE_AGENT_DIMENSIONS.items():
            ctx = format_nse_context(nse_data, agent_type=agent_type)
            ctx_len = len(ctx)
            ctx_lines = ctx.count("\n") + 1 if ctx else 0

            # Check which dimensions might be covered
            ctx_lower = ctx.lower()
            covered: list[str] = []
            partial: list[str] = []

            for dim in dimensions:
                dim_name = dim.split("(")[0].strip().lower()
                keywords = {
                    "capacity_utilisation":  ["commencement", "production", "mw"],
                    "ebitda_quality":        ["financial results", "board meeting"],
                    "debt_serviceability":   ["fund raising"],
                    "receivables":           ["general updates"],
                    "leverage":              ["general updates", "press release"],
                    "subsector_mix":         ["commencement", "production"],
                    "ppa_quality":           ["updates", "press release"],
                    "pipeline_cred":         ["commencement", "production"],
                    "customer_divers":       [],
                    "geography_spread":      [],
                    "ev_per_mw":             ["financial results", "board meeting"],
                    "ev_ebitda":             ["financial results"],
                    "tariff_vs_auction":     [],
                    "pipeline_dcf":          ["commencement"],
                    "implied_irr":           ["fund raising"],
                    "discom_credit":         ["general updates"],
                    "curtailment_risk":      [],
                    "ppa_protection":        [],
                    "execution_risk":        ["commencement", "updates"],
                    "promoter_pledge":       ["general updates", "press release"],
                }.get(dim_name, [])

                if any(kw in ctx_lower for kw in keywords):
                    covered.append(dim_name)
                elif ctx:
                    partial.append(dim_name)

            print(f"    [{agent_type}]")
            print(f"      context length : {ctx_len} chars / {ctx_lines} lines")
            print(f"      has content    : {'YES' if ctx else 'NO (Serper fallback)'}")
            if ctx:
                print(f"      preview        : {safe(ctx[:200].replace(chr(10), ' | '))}")
            print(f"      dims covered   : {covered or 'none directly'}")

            ticker_eval[agent_type] = {
                "ctx": ctx,
                "ctx_len": ctx_len,
                "has_content": bool(ctx),
                "covered_dims": covered,
                "partial_dims": partial,
            }

        evaluations[ticker] = ticker_eval

    # Summary table
    print("\n  --- Coverage Summary ---")
    print(f"  {'Ticker':<15} {'re_fundamentals':<6} {'re_business':<6} {'re_valuation':<6} {'re_risk':<6}")
    for ticker, te in evaluations.items():
        row = ticker
        for at in ["re_fundamentals", "re_business", "re_valuation", "re_risk"]:
            ev = te.get(at, {})
            row += f"  {'YES' if ev.get('has_content') else 'NO '}"
        print(f"  {row}")

    return evaluations


# ─────────────────────────────────────────────────────────────────────────────
# Agent 3 — Reviewer (LLM)
# ─────────────────────────────────────────────────────────────────────────────

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

    # Build a compact review prompt from one representative ticker
    sample_ticker = "NTPC"
    te = evaluations.get(sample_ticker, {})

    context_samples = {}
    for at in ["re_fundamentals", "re_business", "re_valuation", "re_risk"]:
        ctx = te.get(at, {}).get("ctx", "(empty)")
        context_samples[at] = ctx[:400] if ctx else "(empty — Serper fallback)"

    dimensions_str = ""
    for at, dims in RE_AGENT_DIMENSIONS.items():
        dimensions_str += f"\n{at}:\n" + "\n".join(f"  - {d}" for d in dims)

    prompt = f"""Today is {date.today().isoformat()}.
Sector: Renewable Energy (India, NSE).
Ticker under review: {sample_ticker}

CONTEXT:
NseIndiaApi provides OFFICIAL EVENT DATA (what companies filed with NSE Exchange):
  - announcements(): company regulatory filings — commissioning milestones, management
    changes, corporate disclosures, SEBI filings, operational updates
  - boardMeetings(): scheduled board meeting dates + agenda
  - actions(): corporate actions — dividends, bonus, splits, rights

IMPORTANT: NseIndiaApi does NOT provide financial ratios (EV/MW, EBITDA/MW, DSCR,
CUF%) — those come from yfinance and Serper news. NseIndiaApi adds OFFICIAL EVENT
ANCHORS that supplement the financial data. Evaluate ONLY whether the event data
shown per agent_type is:
  (a) the correct type of event for that agent's scoring purpose
  (b) not cross-contaminated with events belonging to a different agent

RE agents and what NseIndiaApi events they need:
  re_fundamentals → commissioning milestones (capacity went live), results board meeting dates
  re_business     → commissioning COD events, project updates, capacity-addition news
  re_valuation    → fund raising board meetings (equity dilution risk), dividend/rights actions
  re_risk         → management change filings, regulatory disclosures, SEBI takeover filings

Formatted NseIndiaApi context produced for {sample_ticker}:

re_fundamentals:
{context_samples['re_fundamentals']}

re_business:
{context_samples['re_business']}

re_valuation:
{context_samples['re_valuation']}

re_risk:
{context_samples['re_risk']}

Evaluate:
1. Does each section contain the right TYPE of official event for that agent?
2. Is there obvious wrong-category data appearing in the wrong section?
3. Is the commissioning/trial operation signal present where expected (business, fundamentals)?
4. Are AGM/non-financial entries excluded from corporate actions?
5. Does the risk section show governance/regulatory signals?

Respond ONLY with valid JSON:
{{
  "verdict": "APPROVED" | "NEEDS_REVISION",
  "re_fundamentals_useful": true | false,
  "re_business_useful": true | false,
  "re_valuation_useful": true | false,
  "re_risk_useful": true | false,
  "category_filtering_correct": true | false,
  "commissioning_signal_present": true | false,
  "key_finding": "<one sentence — most valuable official event NseIndiaApi adds for RE>",
  "main_gap": "<one sentence — what OFFICIAL EVENT type is missing, not financial ratios>",
  "issues": ["<issue if any — only flag wrong-category cross-contamination>"],
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
        # Strip markdown code fences
        if raw.startswith("```"):
            raw = re.sub(r"^```(?:json)?\s*", "", raw)
            raw = re.sub(r"\s*```\s*$", "", raw).strip()
        result = json.loads(raw)

        print(f"\n  Verdict                    : {result.get('verdict')}")
        print(f"  re_fundamentals useful     : {result.get('re_fundamentals_useful')}")
        print(f"  re_business useful         : {result.get('re_business_useful')}")
        print(f"  re_valuation useful        : {result.get('re_valuation_useful')}")
        print(f"  re_risk useful             : {result.get('re_risk_useful')}")
        print(f"  Category filtering correct : {result.get('category_filtering_correct')}")
        print(f"  Commissioning signal       : {result.get('commissioning_signal_present')}")
        print(f"  Key finding                : {safe(result.get('key_finding', ''))}")
        print(f"  Main gap                   : {safe(result.get('main_gap', ''))}")
        print(f"  Issues                     : {result.get('issues', [])}")
        print(f"  Recommendation             : {result.get('recommendation')}")

        approved = result.get("verdict") == "APPROVED"
        return approved

    except Exception as exc:
        print(f"  LLM failed: {exc}")
        return _rule_based_review(evaluations)


def _rule_based_review(evaluations: dict[str, dict]) -> bool:
    """Rule-based fallback when no LLM key is available."""
    total_has_content = 0
    total_checks = 0

    for ticker, te in evaluations.items():
        for agent_type, ev in te.items():
            total_checks += 1
            if ev.get("has_content"):
                total_has_content += 1

    pct = total_has_content / total_checks * 100 if total_checks else 0
    print(f"\n  Rule-based: {total_has_content}/{total_checks} agent_types have content ({pct:.0f}%)")

    # fundamentals and business should always have content for active RE companies
    fundamentals_ok = all(
        evaluations.get(t, {}).get("re_fundamentals", {}).get("has_content", False)
        for t in ["NTPC", "TATAPOWER"]
    )
    business_ok = all(
        evaluations.get(t, {}).get("re_business", {}).get("has_content", False)
        for t in ["NTPC", "TATAPOWER"]
    )

    if fundamentals_ok and business_ok and pct >= 50:
        print("  Rule-based verdict: APPROVED")
        return True
    else:
        print("  Rule-based verdict: NEEDS_REVISION")
        return False


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("\nStockAgent — RE Sector NseIndiaApi Integration Test (3-Agent Loop)")
    print("Tests: prefetch -> category filtering -> context quality per agent_type\n")

    research    = agent_researcher()
    evaluations = agent_designer(research)
    approved    = agent_reviewer(research, evaluations)

    print("\n" + "=" * 65)
    if approved:
        print("RESULT: APPROVED — RE sector NseIndiaApi integration is working")
    else:
        print("RESULT: NEEDS_REVISION — see Reviewer output above")
    print("=" * 65)

    sys.exit(0 if approved else 1)

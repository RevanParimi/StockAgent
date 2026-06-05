"""
tests/test_nse_india_api.py
===========================
3-Agent test: NseIndiaApi for per-ticker company data.

Agent 1 — Researcher : calls announcements(), boardMeetings(), actions(),
                       quote() for TATAMOTORS, HDFCBANK, TCS
Agent 2 — Designer   : evaluates what each endpoint returns and whether
                       it's usable for RL FeedbackAgent market_context
Agent 3 — Reviewer   : LLM judges if NseIndiaApi output is sufficient
                       to augment/replace Serper for per-ticker context

Run:
    python -m tests.test_nse_india_api

No API key needed — uses NSE India website directly.
"""

from __future__ import annotations

import json
import os
import re
import sys
import time
from datetime import date

TEST_TICKERS = ["TATAMOTORS", "HDFCBANK", "TCS"]

# Rate limit: NSE throttles to 3 req/sec — add small delay between calls
DELAY = 0.5  # seconds between requests


def safe(s: str) -> str:
    """ASCII-safe print on Windows CP1252 console."""
    return str(s).encode("ascii", "replace").decode("ascii")


# ---------------------------------------------------------------------------
# Agent 1 — Researcher
# ---------------------------------------------------------------------------

def agent_researcher() -> dict[str, dict]:
    print("\n" + "=" * 65)
    print("AGENT 1 - RESEARCHER: Calling NseIndiaApi per ticker")
    print("=" * 65)

    try:
        from nse import NSE
    except ImportError:
        print("ERROR: nse package not installed. Run: pip install nse")
        sys.exit(1)

    import tempfile, pathlib
    dl_folder = pathlib.Path(tempfile.mkdtemp())
    nse = NSE(download_folder=dl_folder)
    results = {}

    for ticker in TEST_TICKERS:
        print(f"\n  [{ticker}]")
        data = {
            "ticker":        ticker,
            "announcements": [],
            "board_meetings": [],
            "actions":       [],
            "quote":         {},
            "errors":        [],
        }

        # --- announcements() ---
        try:
            time.sleep(DELAY)
            raw = nse.announcements(symbol=ticker)
            # Can return list or dict with 'data' key
            if isinstance(raw, list):
                items = raw
            elif isinstance(raw, dict):
                items = raw.get("data", raw.get("announcements", []))
                if not isinstance(items, list):
                    items = [raw]
            else:
                items = []

            data["announcements"] = items[:5]  # cap at 5 for display
            print(f"    announcements()  : {len(items)} items")
            for item in items[:3]:
                desc = item.get("desc", item.get("subject", item.get("description", "")))
                dt   = item.get("an_dt", item.get("date", item.get("bm_date", "")))
                print(f"      [{safe(str(dt))}] {safe(str(desc))[:80]}")
        except Exception as exc:
            data["errors"].append(f"announcements: {exc}")
            print(f"    announcements()  : ERROR - {safe(str(exc))[:80]}")

        # --- boardMeetings() ---
        try:
            time.sleep(DELAY)
            raw = nse.boardMeetings(symbol=ticker)
            if isinstance(raw, list):
                items = raw
            elif isinstance(raw, dict):
                items = raw.get("data", [])
            else:
                items = []

            data["board_meetings"] = items[:3]
            print(f"    boardMeetings()  : {len(items)} items")
            for item in items[:2]:
                purpose = item.get("purpose", item.get("desc", ""))
                dt      = item.get("bm_date", item.get("meetingDate", ""))
                print(f"      [{safe(str(dt))}] {safe(str(purpose))[:80]}")
        except Exception as exc:
            data["errors"].append(f"boardMeetings: {exc}")
            print(f"    boardMeetings()  : ERROR - {safe(str(exc))[:80]}")

        # --- actions() (corporate actions: dividends, splits, bonuses) ---
        try:
            time.sleep(DELAY)
            raw = nse.actions(symbol=ticker)
            if isinstance(raw, list):
                items = raw
            elif isinstance(raw, dict):
                items = raw.get("data", [])
            else:
                items = []

            data["actions"] = items[:3]
            print(f"    actions()        : {len(items)} items")
            for item in items[:2]:
                subject = item.get("subject", item.get("desc", ""))
                ex_date = item.get("exDate", item.get("ex_date", ""))
                print(f"      [exDate: {safe(str(ex_date))}] {safe(str(subject))[:80]}")
        except Exception as exc:
            data["errors"].append(f"actions: {exc}")
            print(f"    actions()        : ERROR - {safe(str(exc))[:80]}")

        # --- equityQuote() for current price context ---
        try:
            time.sleep(DELAY)
            raw = nse.quote(symbol=ticker)
            if isinstance(raw, dict):
                price_info = raw.get("priceInfo", raw.get("data", {}))
                data["quote"] = {
                    "last_price":    price_info.get("lastPrice", raw.get("lastPrice", "?")),
                    "change_pct":    price_info.get("pChange", raw.get("pChange", "?")),
                    "52w_high":      price_info.get("weekHighLow", {}).get("max", "?"),
                    "52w_low":       price_info.get("weekHighLow", {}).get("min", "?"),
                }
                print(f"    quote()          : last={data['quote']['last_price']} "
                      f"chg={data['quote']['change_pct']}%")
            else:
                print(f"    quote()          : unexpected format - {type(raw)}")
        except Exception as exc:
            data["errors"].append(f"quote: {exc}")
            print(f"    quote()          : ERROR - {safe(str(exc))[:80]}")

        results[ticker] = data

    nse.exit()
    return results


# ---------------------------------------------------------------------------
# Agent 2 — Designer
# ---------------------------------------------------------------------------

def agent_designer(research: dict[str, dict]) -> dict[str, dict]:
    print("\n" + "=" * 65)
    print("AGENT 2 - DESIGNER: Evaluating Usefulness per Agent Type")
    print("=" * 65)

    evaluations = {}

    for ticker, data in research.items():
        ann_count  = len(data["announcements"])
        bm_count   = len(data["board_meetings"])
        act_count  = len(data["actions"])
        has_quote  = bool(data["quote"])
        errors     = data["errors"]

        # What agent types benefit from each endpoint
        print(f"\n  [{ticker}]")
        print(f"    Announcements : {ann_count} items -> fundamentals + risk_macro agent")
        print(f"    Board meetings: {bm_count} items -> fundamentals agent (earnings dates)")
        print(f"    Corp actions  : {act_count} items -> fundamentals agent (dividends)")
        print(f"    Quote         : {'yes' if has_quote else 'no'} -> all agents (price context)")
        if errors:
            print(f"    Errors        : {errors}")

        # Date freshness check on announcements
        fresh_ann = 0
        for item in data["announcements"]:
            dt_str = str(item.get("an_dt", item.get("date", "")))
            if dt_str and (date.today().isoformat()[:7] in dt_str or  # current month
                           str(date.today().year) in dt_str):         # current year
                fresh_ann += 1

        # Is the data useful for RL daily review?
        rl_useful = ann_count > 0 or bm_count > 0
        agents_covered = []
        if ann_count > 0:
            agents_covered += ["fundamentals", "risk_macro"]
        if bm_count > 0 and "fundamentals" not in agents_covered:
            agents_covered.append("fundamentals")
        if act_count > 0 and "fundamentals" not in agents_covered:
            agents_covered.append("fundamentals")

        print(f"    Fresh (this year): {fresh_ann} announcements")
        print(f"    RL daily review useful: {rl_useful}")
        print(f"    Agents that benefit: {agents_covered or ['none - all returned empty']}")

        evaluations[ticker] = {
            "ann_count":      ann_count,
            "bm_count":       bm_count,
            "act_count":      act_count,
            "has_quote":      has_quote,
            "fresh_ann":      fresh_ann,
            "rl_useful":      rl_useful,
            "agents_covered": agents_covered,
            "errors":         errors,
        }

    return evaluations


# ---------------------------------------------------------------------------
# Agent 3 — Reviewer (LLM)
# ---------------------------------------------------------------------------

def agent_reviewer(research: dict[str, dict], evaluations: dict[str, dict]) -> None:
    print("\n" + "=" * 65)
    print("AGENT 3 - REVIEWER: LLM Quality Judgment")
    print("=" * 65)

    from dotenv import load_dotenv
    load_dotenv()

    openrouter_key = os.getenv("OPENROUTER_API_KEY", "")
    llm_model      = os.getenv("LLM_MODEL", "qwen/qwen-2.5-72b-instruct")

    if not openrouter_key:
        print("  No OPENROUTER_API_KEY - running rule-based fallback")
        _rule_based_review(evaluations)
        return

    from openai import OpenAI
    client = OpenAI(api_key=openrouter_key, base_url="https://openrouter.ai/api/v1")

    for ticker, data in research.items():
        ev = evaluations[ticker]

        # Format announcements sample for LLM
        ann_sample = ""
        for item in data["announcements"][:5]:
            desc = item.get("desc", item.get("subject", item.get("description", "")))
            dt   = item.get("an_dt", item.get("date", ""))
            ann_sample += f"  [{dt}] {str(desc)[:100]}\n"

        bm_sample = ""
        for item in data["board_meetings"][:3]:
            purpose = item.get("purpose", item.get("desc", ""))
            dt      = item.get("bm_date", item.get("meetingDate", ""))
            bm_sample += f"  [{dt}] {str(purpose)[:100]}\n"

        act_sample = ""
        for item in data["actions"][:3]:
            subject = item.get("subject", item.get("desc", ""))
            ex_date = item.get("exDate", item.get("ex_date", ""))
            act_sample += f"  [exDate: {ex_date}] {str(subject)[:100]}\n"

        prompt = f"""Today is {date.today().isoformat()}.
Ticker: {ticker} (NSE India)

NseIndiaApi returned:

ANNOUNCEMENTS ({ev['ann_count']} total, sample):
{ann_sample or '  (none)'}

BOARD MEETINGS ({ev['bm_count']} total, sample):
{bm_sample or '  (none)'}

CORPORATE ACTIONS ({ev['act_count']} total, sample):
{act_sample or '  (none)'}

Our RL daily review (daily_review.py) needs market_context_today for FeedbackAgent.
It currently gets "Market context unavailable." because no news API works for NSE.

Our analysis agents need company-specific context:
- fundamentals agent: earnings dates, revenue results, board decisions
- risk_macro agent: regulatory filings, management changes, debt actions
- sentiment agent: management tone signals, corporate actions

Evaluate if NseIndiaApi data is useful and respond ONLY with this JSON:
{{
  "ticker": "{ticker}",
  "verdict": "USEFUL" or "PARTIAL" or "NOT_USEFUL",
  "covers_fundamentals": true/false,
  "covers_risk_macro": true/false,
  "covers_sentiment": true/false,
  "suitable_for_rl_daily_review": true/false,
  "data_quality": "high" or "medium" or "low",
  "key_finding": "<one sentence — what this data actually provides>",
  "limitation": "<one sentence — what it cannot provide>",
  "recommendation": "use_alongside_serper" or "replace_serper" or "skip"
}}"""

        try:
            resp = client.chat.completions.create(
                model=llm_model,
                messages=[
                    {"role": "system", "content": "You are a concise financial data quality reviewer. Output only valid JSON."},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.0,
                max_tokens=400,
            )
            raw = resp.choices[0].message.content or ""
            raw = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL).strip()
            result = json.loads(raw)

            print(f"\n  [{ticker}]")
            print(f"    Verdict                     : {result.get('verdict')}")
            print(f"    Covers fundamentals         : {result.get('covers_fundamentals')}")
            print(f"    Covers risk_macro           : {result.get('covers_risk_macro')}")
            print(f"    Covers sentiment            : {result.get('covers_sentiment')}")
            print(f"    RL daily review suitable    : {result.get('suitable_for_rl_daily_review')}")
            print(f"    Data quality                : {result.get('data_quality')}")
            print(f"    Key finding                 : {safe(result.get('key_finding', ''))}")
            print(f"    Limitation                  : {safe(result.get('limitation', ''))}")
            print(f"    Recommendation              : {result.get('recommendation')}")

        except Exception as exc:
            print(f"  [{ticker}] LLM failed: {exc}")
            _rule_based_review_ticker(ticker, ev)


def _rule_based_review(evaluations: dict[str, dict]) -> None:
    for ticker, ev in evaluations.items():
        _rule_based_review_ticker(ticker, ev)


def _rule_based_review_ticker(ticker: str, ev: dict) -> None:
    total = ev["ann_count"] + ev["bm_count"] + ev["act_count"]
    verdict = "USEFUL" if total > 0 else "NOT_USEFUL"
    print(f"\n  [{ticker}] Rule-based verdict: {verdict}")
    print(f"    Total data points : {total}")
    print(f"    Errors encountered: {ev['errors']}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("\nStockAgent - NseIndiaApi Test (3-Agent Loop)")
    print("Tests announcements, boardMeetings, actions, quote per NSE ticker\n")

    research    = agent_researcher()
    evaluations = agent_designer(research)
    agent_reviewer(research, evaluations)

    print("\n" + "=" * 65)
    print("Test complete.")
    print("=" * 65)

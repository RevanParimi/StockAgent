"""
scripts/aud098_thesis_tier_bench.py — AUD-098 ThesisReviewer tier A/B.

Question: can the ThesisReviewer run on the BULK tier (deepseek-v4-flash,
$0.098/$0.196 per M) instead of the REASONING tier (glm-5.2, $1.218/$3.828)
without losing quality?  ThesisReviewer is a single structured-JSON call that
judges which of a forecast's key assumptions a miss invalidated and applies a
0.3-1.0 confidence haircut — a mechanical rubric task, a plausible down-tier
candidate.

This harness sends the EXACT production prompt (thesis_reviewer._SYSTEM_PROMPT
+ _format_prompt) for three representative scenarios and scores each response
deterministically — no LLM judge:

  json_ok        response parses as a JSON object
  schema_ok      all five required keys present
  types_ok       thesis_intact is bool, arrays are lists, multiplier castable
  mult_range_ok  horizon_confidence_multiplier in [0.3, 1.0]
  restraint_ok   revised_narrative carries no broker target / EPS / rating
                 (the system prompt forbids them)
  scenario_ok    scenario-appropriate behaviour (haircut a clear break, do
                 NOT over-haircut a benign magnitude miss)

Run:  PYTHONPATH="src;." python scripts/aud098_thesis_tier_bench.py
      (optional argv: model ids to compare; default = reasoning vs bulk)
Output: outputs/aud098_thesis_bench_<date>.json + printed scorecard.
"""
from __future__ import annotations

import json
import re
import sys
import time
from datetime import date
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
for _p in (_ROOT, _ROOT / "src"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

try:
    from dotenv import load_dotenv
    load_dotenv(_ROOT / ".env")
except Exception:
    pass

from core.config import settings
from services.clients.llm_client import JSON_MODE_EXTRA_BODY, get_llm_client
from core.intelligence.rl.agents.thesis_reviewer import _SYSTEM_PROMPT, _format_prompt
from core.schemas.feedback import FeedbackAgentOutput

TRIALS = 3
MODELS = [m for m in sys.argv[1:]] or [
    settings.LLM_MODEL_REASONING,   # baseline: z-ai/glm-5.2
    settings.LLM_MODEL_BULK,        # candidate: deepseek/deepseek-v4-flash
]

_FORBIDDEN_RE = re.compile(
    r"\b(price target|target price|broker|analyst rating|\brating\b|\bEPS\b|buy rating|sell rating)\b",
    re.IGNORECASE,
)

REQUIRED_KEYS = {
    "assumptions_invalidated", "assumptions_still_valid",
    "thesis_intact", "revised_narrative", "horizon_confidence_multiplier",
}


# ---------------------------------------------------------------------------
# Scenarios — (name, key_assumptions, FeedbackAgentOutput, market_context,
#              price_error_pct, expectation)
# expectation is checked deterministically in score().
# ---------------------------------------------------------------------------

SCENARIOS = [
    {
        "name": "clear_break",  # external shock invalidates a core assumption
        "ticker": "MARUTI", "sector": "automobile",
        "key_assumptions": [
            "Crude oil stays range-bound below $80/bbl, protecting input-cost margins",
            "Festive-season demand momentum continues into Q3",
            "No adverse change to EV or emission policy in the near term",
        ],
        "fb": FeedbackAgentOutput(
            primary_miss_agent="risk_macro", miss_type="external_shock",
            missed_factors=["crude_oil_spike", "hawkish_rbi_commentary"],
            over_weighted_factors=["festive_demand_momentum"],
        ),
        "market_context": (
            "Crude oil spiked +9% to $88/bbl overnight on a Middle-East supply "
            "disruption; INR weakened to 84.2/USD; the NSE auto index fell 3.1%. "
            "RBI held rates but guidance turned hawkish. No MARUTI-specific news."
        ),
        "price_error_pct": -3.4,
        # A genuine external shock invalidating the crude assumption must produce
        # SOME haircut and flag at least one invalidated assumption.
        "expect": lambda m, inval, intact: (m < 1.0 and len(inval) >= 1),
    },
    {
        "name": "benign_miss",  # small magnitude miss, no thesis damage
        "ticker": "TCS", "sector": "it_sector",
        "key_assumptions": [
            "Strong deal pipeline supports revenue visibility for the year",
            "Margins stable on benign wage and currency conditions",
        ],
        "fb": FeedbackAgentOutput(
            primary_miss_agent="pattern_analysis", miss_type="magnitude",
            missed_factors=["intraday_profit_booking"],
            over_weighted_factors=[],
        ),
        "market_context": (
            "Broad market flat; the stock drifted -1.2% on light profit-booking "
            "with no company news. Commodity and currency backdrop unchanged."
        ),
        "price_error_pct": -1.2,
        # A benign, newsless magnitude miss must NOT be over-haircut.
        "expect": lambda m, inval, intact: (m >= 0.7),
    },
    {
        "name": "direction_flip",  # structural: guidance cut breaks the thesis
        "ticker": "TATAMOTORS", "sector": "automobile",
        "key_assumptions": [
            "Confirmed technical breakout above resistance signals continuation",
            "Positive management tone underpins the near-term move",
        ],
        "fb": FeedbackAgentOutput(
            primary_miss_agent="sentiment", miss_type="direction_flip",
            missed_factors=["negative_management_guidance"],
            over_weighted_factors=["technical_breakout"],
        ),
        "market_context": (
            "The stock fell 4.1% after management cut FY guidance on the earnings "
            "call; sector peers were little changed. The technical breakout failed."
        ),
        "price_error_pct": -4.1,
        # A direction flip driven by a guidance cut breaks a core assumption →
        # a meaningful haircut and at least one invalidated assumption.
        "expect": lambda m, inval, intact: (m < 0.9 and len(inval) >= 1),
    },
]


def score(parsed: dict, scenario: dict) -> dict:
    schema_ok = REQUIRED_KEYS <= set(parsed)
    intact = parsed.get("thesis_intact")
    inval = parsed.get("assumptions_invalidated")
    still = parsed.get("assumptions_still_valid")
    narrative = parsed.get("revised_narrative", "")
    types_ok = (
        isinstance(intact, bool)
        and isinstance(inval, list) and isinstance(still, list)
        and isinstance(narrative, str)
    )
    try:
        mult = float(parsed.get("horizon_confidence_multiplier", 99))
        mult_ok = 0.3 <= mult <= 1.0
    except (TypeError, ValueError):
        mult, mult_ok = 99.0, False
    restraint_ok = not _FORBIDDEN_RE.search(str(narrative))
    try:
        scenario_ok = bool(scenario["expect"](
            mult, inval if isinstance(inval, list) else [], intact))
    except Exception:
        scenario_ok = False
    return {
        "schema_ok": schema_ok, "types_ok": types_ok, "mult_range_ok": mult_ok,
        "restraint_ok": restraint_ok, "scenario_ok": scenario_ok,
        "_mult": mult, "_intact": intact,
    }


def run_one(client, model: str, scenario: dict) -> dict:
    user_prompt = _format_prompt(
        scenario["ticker"], scenario["sector"], scenario["key_assumptions"],
        scenario["fb"], scenario["market_context"],
    )
    t0 = time.time()
    resp = client.chat.completions.create(
        model=model,
        temperature=0.1,
        max_tokens=300,
        messages=[
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        response_format={"type": "json_object"},
        extra_body=JSON_MODE_EXTRA_BODY,
    )
    latency = time.time() - t0
    raw = resp.choices[0].message.content or ""
    u = getattr(resp, "usage", None)
    tin = (getattr(u, "prompt_tokens", 0) or 0) if u else 0
    tout = (getattr(u, "completion_tokens", 0) or 0) if u else 0
    stripped = raw.strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```(?:json)?\s*", "", stripped)
        stripped = re.sub(r"\s*```\s*$", "", stripped).strip()
    try:
        parsed = json.loads(stripped)
        json_ok = isinstance(parsed, dict)
    except (json.JSONDecodeError, ValueError):
        parsed, json_ok = {}, False
    return {
        "raw": raw, "parsed": parsed, "json_ok": json_ok,
        "latency": round(latency, 1), "tin": tin, "tout": tout,
        "cost": settings.llm_cost_usd(model, tin, tout),
    }


def main() -> None:
    client = get_llm_client()
    rows = []
    for model in MODELS:
        for scenario in SCENARIOS:
            for trial in range(TRIALS):
                tag = f"{model.split('/')[-1]:24} {scenario['name']:14} #{trial + 1}"
                try:
                    r = run_one(client, model, scenario)
                    checks = score(r["parsed"], scenario) if r["json_ok"] else {}
                    all_ok = r["json_ok"] and all(
                        v for k, v in checks.items() if not k.startswith("_"))
                    rows.append({"model": model, "scenario": scenario["name"],
                                 "trial": trial, **r, "checks": checks,
                                 "all_ok": all_ok})
                    fails = [k for k, v in checks.items()
                             if not k.startswith("_") and not v]
                    print(f"[{'ok ' if all_ok else 'BAD'}] {tag} "
                          f"lat={r['latency']:5.1f}s cost=${r['cost']:.6f} "
                          f"json={r['json_ok']} mult={checks.get('_mult','-')} "
                          f"intact={checks.get('_intact','-')} fails={fails or '-'}")
                except Exception as exc:
                    rows.append({"model": model, "scenario": scenario["name"],
                                 "trial": trial, "error": str(exc)[:200]})
                    print(f"[ERR] {tag} {str(exc)[:120]}")

    print("\n" + "=" * 96)
    print(f"{'MODEL':28} {'runs':>4} {'errs':>4} {'json%':>6} {'pass%':>6} "
          f"{'scen%':>6} {'restr%':>7} {'avg_lat':>8} {'cost_all':>10}")
    print("-" * 96)
    for model in MODELS:
        rs = [r for r in rows if r["model"] == model]
        errs = [r for r in rs if "error" in r]
        ok = [r for r in rs if "error" not in r]
        n = len(ok)
        if not n:
            print(f"{model:28} {len(rs):4} {len(errs):4}   all errored")
            continue
        jp = 100 * sum(r["json_ok"] for r in ok) / n
        pp = 100 * sum(r["all_ok"] for r in ok) / n
        sc = [r for r in ok if "scenario_ok" in r.get("checks", {})]
        sp = 100 * sum(r["checks"]["scenario_ok"] for r in sc) / len(sc) if sc else 0
        rc = [r for r in ok if "restraint_ok" in r.get("checks", {})]
        rp = 100 * sum(r["checks"]["restraint_ok"] for r in rc) / len(rc) if rc else 0
        lat = sum(r["latency"] for r in ok) / n
        cost = sum(r["cost"] for r in ok)
        print(f"{model:28} {len(rs):4} {len(errs):4} {jp:5.0f}% {pp:5.0f}% "
              f"{sp:5.0f}% {rp:6.0f}% {lat:7.1f}s ${cost:.6f}")

    out = Path("outputs") / f"aud098_thesis_bench_{date.today().isoformat()}.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(rows, indent=2, default=str), encoding="utf-8")
    print(f"\nFull transcripts: {out}")


if __name__ == "__main__":
    main()

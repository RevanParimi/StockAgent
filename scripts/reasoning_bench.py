"""
scripts/reasoning_bench.py — REASONING-tier model comparison harness.

The REASONING tier (SignalAggregator verdict, FeedbackAgent, ThesisReviewer,
Unified Analyst) needs: strict json_object output with reasoning DISABLED
(JSON_MODE_EXTRA_BODY — the 2026-07 thinking-snapshot incident), schema and
constraint compliance, and correct quantitative reasoning. This battery scores
all of that deterministically — no LLM judge:

  json_ok      — response parses as JSON (no salvage needed)
  schema_ok    — every required key present, enums respected
  slug_ok      — missed_factors match feedback_agent.VALID_MISS_FACTOR_RE
  math_ok      — weighted composite correct to ±0.001 (weights × scores given)
  verdict_ok   — verdict matches the deterministic threshold rule given
  restraint_ok — fields for ABSENT data returned as null (no hallucination)
  latency_s / cost_usd — wall-clock + live-priced token cost

Run:  PYTHONPATH="src;." .stockai/Scripts/python.exe scripts/reasoning_bench.py
Output: outputs/reasoning_bench_<date>.json + printed scorecard.
"""
from __future__ import annotations

import asyncio
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

from services.clients.llm_client import JSON_MODE_EXTRA_BODY, get_async_llm_client
from core.intelligence.rl.agents.feedback_agent import VALID_MISS_FACTOR_RE

# OpenRouter ids + live price ($/1M in, out) — verified 2026-07-03 via /api/v1/models
PRICES: dict[str, tuple[float, float]] = {
    "qwen/qwen3.7-max":          (1.25, 3.75),    # current REASONING tier (baseline)
    "qwen/qwen3.7-plus":         (0.32, 1.28),
    "deepseek/deepseek-v4-pro":  (0.435, 0.87),
    "minimax/minimax-m3":        (0.30, 1.20),
    "z-ai/glm-4.7":              (0.40, 1.75),
    "minimax/minimax-m2.7":      (0.18, 0.72),
    "deepseek/deepseek-v4-flash": (0.089, 0.18),  # BULK tier — floor reference
}
MODELS = list(PRICES)
TRIALS = 3   # per task per model

AGENT_SCORES = {
    "sales_demand": 0.62, "raw_materials": 0.55, "fundamentals": 0.71,
    "pattern_analysis": 0.38, "sentiment": 0.44, "policy_regulatory": 0.58,
    "competitive_intel": 0.52, "risk_macro": 0.31, "valuation_catalyst": 0.66,
}
WEIGHTS = {
    "sales_demand": 0.18, "raw_materials": 0.08, "fundamentals": 0.16,
    "pattern_analysis": 0.12, "sentiment": 0.08, "policy_regulatory": 0.08,
    "competitive_intel": 0.08, "risk_macro": 0.12, "valuation_catalyst": 0.10,
}
_wsum = sum(WEIGHTS.values())
EXPECTED_COMPOSITE = round(
    sum(AGENT_SCORES[k] * WEIGHTS[k] for k in AGENT_SCORES) / _wsum, 4)
# Threshold rule given verbatim to the model:
# composite >= 0.60 BUY; <= 0.45 SELL; else NEUTRAL
EXPECTED_VERDICT = ("BUY" if EXPECTED_COMPOSITE >= 0.60
                    else "SELL" if EXPECTED_COMPOSITE <= 0.45 else "NEUTRAL")

FEEDBACK_PROMPT = f"""You are the RL feedback analyst for an Indian equities forecasting system.

Yesterday's data for MARUTI (NSE):
- predicted_close: 14395.00, actual_close: 14102.30 (miss of -2.03%)
- predicted_verdict was NEUTRAL; the stock fell 2.03% (actual direction DOWN)
- Market context: NSE-wide selloff after a surprise RBI rate hold with hawkish
  commentary; FII outflow proxy -1.9% over 5 days; VIX rose 14.1 -> 16.8.
  MARUTI-specific: none — no company news, results, or filings yesterday.
- Frozen agent scores at forecast time: {json.dumps(AGENT_SCORES)}
- Current agent weights: {json.dumps(WEIGHTS)}

Respond with ONLY a JSON object, keys exactly:
  "miss_type": one of "external_shock" | "direction_flip" | "magnitude_miss" | "model_bias"
  "primary_miss_agent": one of {json.dumps(sorted(AGENT_SCORES))}
  "missed_factors": array of 1-3 snake_case slugs, each 3-40 chars of ONLY
      lowercase a-z, 0-9, underscore, ampersand (e.g. "hawkish_rbi_commentary")
  "weighted_composite": the weighted average of the frozen agent scores using
      the weights above (sum of score*weight divided by sum of weights),
      rounded to exactly 4 decimal places
  "horizon_confidence_adjustment": a float in [-0.15, 0.15]
  "company_specific_catalyst": the company-specific news that drove the move,
      or null if the move was market-wide with no company-specific driver
"""

VERDICT_PROMPT = f"""You are the signal aggregator for an equities forecasting system.

Agent scores: {json.dumps(AGENT_SCORES)}
Agent weights: {json.dumps(WEIGHTS)}

Rules (apply EXACTLY):
1. composite = sum(score*weight) / sum(weights), rounded to 4 decimal places
2. verdict: composite >= 0.60 -> "BUY"; composite <= 0.45 -> "SELL"; else "NEUTRAL"
3. top_drivers: the 3 agents with the LARGEST score*weight contribution,
   sorted descending by contribution

Respond with ONLY a JSON object, keys exactly:
  "composite": float (4 dp)
  "verdict": "BUY" | "SELL" | "NEUTRAL"
  "top_drivers": array of exactly 3 agent-name strings
  "conviction": float in [0.0, 1.0]
"""

EXPECTED_DRIVERS = [k for k, _ in sorted(
    ((k, AGENT_SCORES[k] * WEIGHTS[k]) for k in AGENT_SCORES),
    key=lambda kv: kv[1], reverse=True)[:3]]


def score_feedback(parsed: dict) -> dict:
    keys = {"miss_type", "primary_miss_agent", "missed_factors",
            "weighted_composite", "horizon_confidence_adjustment",
            "company_specific_catalyst"}
    schema_ok = keys <= set(parsed)
    slugs = parsed.get("missed_factors") or []
    slug_ok = (isinstance(slugs, list) and 1 <= len(slugs) <= 3 and
               all(isinstance(s, str) and VALID_MISS_FACTOR_RE.fullmatch(s) for s in slugs))
    try:
        math_ok = abs(float(parsed.get("weighted_composite", 99)) - EXPECTED_COMPOSITE) <= 0.001
    except (TypeError, ValueError):
        math_ok = False
    try:
        adj_ok = -0.15 <= float(parsed.get("horizon_confidence_adjustment", 99)) <= 0.15
    except (TypeError, ValueError):
        adj_ok = False
    # Market-wide selloff, explicitly "no company news" → catalyst must be null
    restraint_ok = parsed.get("company_specific_catalyst", "MISSING") is None
    miss_ok = parsed.get("miss_type") in {"external_shock", "direction_flip"}
    return {"schema_ok": schema_ok, "slug_ok": slug_ok, "math_ok": math_ok,
            "range_ok": adj_ok, "restraint_ok": restraint_ok, "sane_ok": miss_ok}


def score_verdict(parsed: dict) -> dict:
    keys = {"composite", "verdict", "top_drivers", "conviction"}
    schema_ok = keys <= set(parsed)
    try:
        math_ok = abs(float(parsed.get("composite", 99)) - EXPECTED_COMPOSITE) <= 0.001
    except (TypeError, ValueError):
        math_ok = False
    verdict_ok = parsed.get("verdict") == EXPECTED_VERDICT
    drivers_ok = parsed.get("top_drivers") == EXPECTED_DRIVERS
    try:
        conv_ok = 0.0 <= float(parsed.get("conviction", 99)) <= 1.0
    except (TypeError, ValueError):
        conv_ok = False
    return {"schema_ok": schema_ok, "math_ok": math_ok, "verdict_ok": verdict_ok,
            "drivers_ok": drivers_ok, "range_ok": conv_ok}


TASKS = [("feedback", FEEDBACK_PROMPT, score_feedback),
         ("verdict", VERDICT_PROMPT, score_verdict)]


async def run_one(client, model: str, prompt: str) -> dict:
    t0 = time.time()
    resp = await client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.1,
        max_tokens=1200,
        response_format={"type": "json_object"},
        extra_body=JSON_MODE_EXTRA_BODY,
    )
    latency = time.time() - t0
    raw = resp.choices[0].message.content or ""
    u = getattr(resp, "usage", None)
    tin = (getattr(u, "prompt_tokens", 0) or 0) if u else 0
    tout = (getattr(u, "completion_tokens", 0) or 0) if u else 0
    pin, pout = PRICES[model]
    try:
        parsed = json.loads(raw)
        json_ok = isinstance(parsed, dict)
    except (json.JSONDecodeError, ValueError):
        parsed, json_ok = {}, False
    return {"raw": raw, "parsed": parsed, "json_ok": json_ok,
            "latency": round(latency, 1), "tin": tin, "tout": tout,
            "cost": tin / 1e6 * pin + tout / 1e6 * pout}


async def main() -> None:
    client = get_async_llm_client()
    rows = []
    for model in MODELS:
        for task, prompt, scorer in TASKS:
            for trial in range(TRIALS):
                tag = f"{model.split('/')[-1]:22} {task:8} #{trial + 1}"
                try:
                    r = await asyncio.wait_for(run_one(client, model, prompt), timeout=120)
                    checks = scorer(r["parsed"]) if r["json_ok"] else {}
                    all_ok = r["json_ok"] and all(checks.values())
                    rows.append({"model": model, "task": task, "trial": trial,
                                 **r, "checks": checks, "all_ok": all_ok})
                    fails = [k for k, v in checks.items() if not v]
                    print(f"[{'ok ' if all_ok else 'BAD'}] {tag} lat={r['latency']:5.1f}s "
                          f"cost=${r['cost']:.5f} json={r['json_ok']} fails={fails or '-'}")
                except Exception as exc:
                    rows.append({"model": model, "task": task, "trial": trial,
                                 "error": str(exc)[:200]})
                    print(f"[ERR] {tag} {str(exc)[:110]}")

    print("\n" + "=" * 100)
    print(f"{'MODEL':26} {'runs':>4} {'errs':>4} {'json%':>6} {'pass%':>6} "
          f"{'math%':>6} {'restraint%':>10} {'avg_lat':>8} {'cost_all':>9}")
    print("-" * 100)
    for model in MODELS:
        rs = [r for r in rows if r["model"] == model]
        errs = [r for r in rs if "error" in r]
        ok = [r for r in rs if "error" not in r]
        n = len(ok)
        if not n:
            print(f"{model:26} {len(rs):4} {len(errs):4}   all errored")
            continue
        jp = 100 * sum(r["json_ok"] for r in ok) / n
        pp = 100 * sum(r["all_ok"] for r in ok) / n
        mm = [r for r in ok if "math_ok" in r.get("checks", {})]
        mp = 100 * sum(r["checks"]["math_ok"] for r in mm) / len(mm) if mm else 0
        rr = [r for r in ok if "restraint_ok" in r.get("checks", {})]
        rp = 100 * sum(r["checks"]["restraint_ok"] for r in rr) / len(rr) if rr else 0
        lat = sum(r["latency"] for r in ok) / n
        cost = sum(r["cost"] for r in ok)
        print(f"{model:26} {len(rs):4} {len(errs):4} {jp:5.0f}% {pp:5.0f}% "
              f"{mp:5.0f}% {rp:9.0f}% {lat:7.1f}s ${cost:.5f}")

    out = Path("outputs") / f"reasoning_bench_{date.today().isoformat()}.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(rows, indent=2, default=str), encoding="utf-8")
    print(f"\nFull transcripts: {out}")


if __name__ == "__main__":
    asyncio.run(main())

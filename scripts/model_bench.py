"""
scripts/model_bench.py — Chat-tier model comparison harness.

Runs a fixed battery of hard queries through the REAL chat pipeline (deterministic
pre-router + tools + grounding + sanitizer) for each candidate model, and auto-scores
the things that actually matter for production:

  fabrication   — a source cited in the answer that is NOT in the fetched tool results
  bracket_tell  — "[Invented Headline ...]" pattern (a fabrication tell)
  skipped_tool  — a self-routed query where the model called NO tools (should have)
  format_viol   — banned "Critical/Important Note" disclaimer labels (pre-sanitize)
  latency_s     — wall-clock per turn
  cost_usd      — prompt+completion tokens × OpenRouter price

Run:  PYTHONPATH=src .stockai/Scripts/python.exe scripts/model_bench.py
Output: outputs/model_bench_<date>.json + a printed scorecard.
"""
from __future__ import annotations

import asyncio
import json
import re
import sys
import time
from datetime import date
from pathlib import Path

# Make runnable from anywhere: put project root (for `services`) and src (for `backend`) on path.
_ROOT = Path(__file__).resolve().parent.parent
for _p in (_ROOT, _ROOT / "src"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

try:
    from dotenv import load_dotenv
    load_dotenv(_ROOT / ".env")
except Exception:
    pass

from services.clients.llm_client import get_async_llm_client
from services.api.routes import ui_data as U

# OpenRouter ids + price ($ per 1M tokens: in, out) — from openrouter.ai/api/v1/models
PRICES: dict[str, tuple[float, float]] = {
    "qwen/qwen3-235b-a22b":        (0.065, 0.26),   # current baseline (from settings)
    "qwen/qwen3.7-max":            (1.25, 3.75),
    "qwen/qwen3.6-flash":          (0.1875, 1.125),
    "google/gemini-3.5-flash":     (1.50, 9.00),
    "deepseek/deepseek-v4-flash":  (0.0983, 0.1966),
    "stepfun/step-3.7-flash":      (0.20, 1.15),
    "moonshotai/kimi-k2.6":        (0.684, 3.42),
    "z-ai/glm-5.1":                (0.98, 3.08),
}
MODELS = list(PRICES)

# (label, query, expects_self_routed_tools)
BATTERY = [
    ("itbuy",      "Which IT stocks should I buy now for the next few months?", False),
    ("autoprofit", "Which auto stocks should I book profit on right now?",      False),
    ("whyfall",    "Why is the Nifty falling today?",                           True),
    ("silver",     "What is the outlook for silver prices over the next month?", True),
]


def _acc(usage: dict, resp) -> None:
    u = getattr(resp, "usage", None)
    if u:
        usage["in"] += getattr(u, "prompt_tokens", 0) or 0
        usage["out"] += getattr(u, "completion_tokens", 0) or 0


async def run_turn(client, model: str, message: str) -> dict:
    usage = {"in": 0, "out": 0}
    llm_calls = 0
    tool_results: list[tuple[str, str]] = []
    tool_calls_made = 0
    t0 = time.time()

    context = U._build_chat_context(message)
    messages = [
        {"role": "system", "content": U._CHAT_SYSTEM_PROMPT.format(context=context)},
        {"role": "user", "content": message},
    ]

    # Deterministic pre-route (same as the endpoint).
    intent = U._detect_invest_intent(message)
    if intent:
        sec_label = {"automobile": "auto", "it_sector": "IT", "banking_bfsi": "banking",
                     "renewable_energy": "renewable energy"}.get(intent["sector"], intent["sector"])
        action_phrase = {"buy": "stocks to buy oversold value", "sell": "stocks profit booking overvalued",
                         "momentum": "stocks momentum leaders"}[intent["action"]]
        news_q = f"India {sec_label} {action_phrase} {date.today().isoformat()}"
        screen, news = await asyncio.gather(
            U._chat_tool_screen_stocks(intent["sector"], intent["mode"]),
            U._chat_tool_search_news(news_q),
            return_exceptions=True,
        )
        if isinstance(screen, str) and "screen —" in screen:
            tool_results.append(("screen_stocks", screen))
            messages.append({"role": "system", "content": f"PRE-FETCHED SCREEN:\n{screen}\nBase picks on this; each needs a number + reason."})
        if isinstance(news, str) and "NEWS RESULTS" in news:
            tool_results.append(("search_market_news", news))
            messages.append({"role": "system", "content": f"PRE-FETCHED NEWS:\n{news}\nCite ONLY headlines above; never invent one."})

    final_text = ""
    for _ in range(U._CHAT_MAX_TOOL_ROUNDS):
        resp = await U._chat_completion(client, models=[model], messages=messages,
                                        temperature=0.4, max_tokens=700,
                                        tools=U._CHAT_TOOLS, tool_choice="auto")
        llm_calls += 1
        _acc(usage, resp)
        msg = resp.choices[0].message
        tcs = getattr(msg, "tool_calls", None) or []
        if not tcs:
            final_text = U._strip_think(msg.content or "")
            break
        tool_calls_made += len(tcs)
        messages.append({"role": "assistant", "content": msg.content or "",
                         "tool_calls": [{"id": tc.id, "type": "function",
                                         "function": {"name": tc.function.name, "arguments": tc.function.arguments}}
                                        for tc in tcs]})
        parsed = []
        for tc in tcs:
            try:
                parsed.append(json.loads(tc.function.arguments or "{}"))
            except Exception:
                parsed.append({})
        results = await asyncio.gather(*[U._execute_chat_tool(tc.function.name, a) for tc, a in zip(tcs, parsed)])
        for tc, r in zip(tcs, results):
            messages.append({"role": "tool", "tool_call_id": tc.id, "content": r})
            tool_results.append((tc.function.name, r))
    else:
        resp = await U._chat_completion(client, models=[model], messages=messages, temperature=0.4, max_tokens=700)
        llm_calls += 1
        _acc(usage, resp)
        final_text = U._strip_think(resp.choices[0].message.content or "")

    raw = final_text
    final_text = U._sanitize_answer(final_text) if final_text else final_text
    return {"model": model, "message": message, "pre_routed": intent is not None,
            "final": final_text, "raw": raw, "grounding": " ".join(c for _, c in tool_results),
            "tool_calls_made": tool_calls_made, "llm_calls": llm_calls, "usage": usage,
            "latency": round(time.time() - t0, 1)}


def score(turn: dict, expects_tools: bool) -> dict:
    g = (turn["grounding"] or "").lower()
    final = turn["final"] or ""
    fabs = 0
    m = re.search(r"sources?:\s*(.+)", final, re.I)
    if m:
        for c in re.split(r"[·,|]", m.group(1)):
            tok = c.strip(" *_.").split(" ")[0].lower()
            if tok and len(tok) > 2 and tok not in g:
                fabs += 1
    # Bracketed pseudo-headline NOT followed by a (url) — a fabrication tell.
    # (Real markdown links "[text](url)" are excluded by the negative lookahead.)
    bracket = len(re.findall(r"\[[A-Z][^\]]{14,}\](?!\()", final))
    fmt = len(re.findall(r"(?im)\b(critical note|important note|final note|disclaimer)\b", turn["raw"] or ""))
    skipped = 1 if (expects_tools and turn["tool_calls_made"] == 0) else 0
    # broken = empty or truncated answer (a model that returns nothing scores fab=0
    # but is useless — this metric was missing in v1 and added after a transcript review).
    broken = 1 if len((turn.get("final") or "").strip()) < 120 else 0
    pin, pout = PRICES.get(turn["model"], (0, 0))
    cost = turn["usage"]["in"] / 1e6 * pin + turn["usage"]["out"] / 1e6 * pout
    return {"fabs": fabs, "bracket": bracket, "fmt": fmt, "skipped": skipped, "broken": broken, "cost": cost}


async def main():
    client = get_async_llm_client()
    rows = []
    for model in MODELS:
        for label, q, expects in BATTERY:
            tag = f"{model.split('/')[-1]:24} {label:11}"
            try:
                turn = await asyncio.wait_for(run_turn(client, model, q), timeout=120)
                s = score(turn, expects)
                turn["scores"] = s
                rows.append(turn)
                print(f"[ok]  {tag} lat={turn['latency']:5.1f}s tools={turn['tool_calls_made']} "
                      f"broken={s['broken']} fab={s['fabs']} brk={s['bracket']} fmt={s['fmt']} skip={s['skipped']} "
                      f"cost=${s['cost']:.5f}")
            except Exception as exc:
                rows.append({"model": model, "message": q, "error": str(exc)[:160]})
                print(f"[ERR] {tag} {str(exc)[:120]}")

    # Aggregate per model
    print("\n" + "=" * 96)
    print(f"{'MODEL':26} {'turns':5} {'errs':4} {'broken':6} {'fab':4} {'brk':4} {'fmt':4} {'skip':5} {'avg_lat':8} {'cost_4q':9}")
    print("-" * 104)
    agg = {}
    for r in rows:
        a = agg.setdefault(r["model"], {"turns": 0, "errs": 0, "broken": 0, "fab": 0, "brk": 0, "fmt": 0, "skip": 0, "lat": 0.0, "cost": 0.0})
        if "error" in r:
            a["errs"] += 1
            continue
        a["turns"] += 1
        a["lat"] += r["latency"]
        s = r["scores"]
        a["broken"] += s["broken"]
        a["fab"] += s["fabs"]; a["brk"] += s["bracket"]; a["fmt"] += s["fmt"]
        a["skip"] += s["skipped"]; a["cost"] += s["cost"]
    for model in MODELS:
        a = agg.get(model)
        if not a:
            continue
        avg_lat = a["lat"] / a["turns"] if a["turns"] else 0
        print(f"{model:26} {a['turns']:5} {a['errs']:4} {a['broken']:6} {a['fab']:4} {a['brk']:4} {a['fmt']:4} "
              f"{a['skip']:5} {avg_lat:7.1f}s ${a['cost']:.5f}")

    out = Path("outputs") / f"model_bench_{date.today().isoformat()}.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(rows, indent=2, default=str), encoding="utf-8")
    print(f"\nFull transcripts: {out}")


if __name__ == "__main__":
    asyncio.run(main())

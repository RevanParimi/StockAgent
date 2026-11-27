"""
scripts/lenses/bench.py — PR-032's bench: today's general-path wording against the
industry lenses, on the same stocks the same day, before `lenses.enabled` is on.

It SPENDS MONEY and is run in production only at the owner's word: about 3 Serper
searches and 1 Tavily page per stock and arm with searches (A and C), and 4 calls
of the analysis's model per stock. Without --yes it prints the plan and the
stocks, and calls nothing. It writes no store: no data-health row, no score
history, no verdict-shadow row, no shelf or dive record (it never runs the
orchestrator). The model calls are logged in the LLM call log like any spend,
and the Tavily month cache and the peers' profile cache fill as they do for any
analysis.

    railway ssh "cd /app && python -B scripts/lenses/bench.py"          # the plan
    railway ssh "cd /app && python -B scripts/lenses/bench.py --yes"    # the run

**Arms, per stock** (written 27 Nov 2026, before any data):

- **A**: today's wording (lenses off).
- **A2**: A's bundle again, a second model call: run-to-run noise, reported as
  context; the rule does not read it.
- **B**: the lens searches without the industry block: C's bundle with the block
  removed, so B and C read the same evidence.
- **C**: the lens searches and the industry block (lenses on).

**Counted by script** (A against B; C shares B's searches):

- *usable results*: a result with a title or a snippet. Per search (company,
  sector, macro), the mean over the stocks; the page extract counts 1 when
  Tavily returned a page.
- *on-industry share*: of the three searches' results, the share whose title
  or snippet holds a lens word (`lens_words`): the words of the lens's KPIs and
  news terms (for the default lens, of the Yahoo label), four letters or more,
  less `COMMON_WORDS`, which any business story uses. A stock with no label has
  no lens words and is left out (n says how many).
- *repeats*: results found by both the sector and the macro search (the same
  link, else the same title).
- *conviction*: the composite of the dimension scores at the stock's weights,
  computed as the aggregator computes it; the verdict is its band
  (`verdict_from_composite`, the band the product's verdict is bound to). The
  aggregator's own second model call is not made: it would write a
  verdict-shadow row and double the cost.

**The rule** (the card's, fixed here before the run):

- **B is ready to switch on** when the on-industry share rises by 20 points or
  more (B against A, pooled over the stocks' results) and, for each of the
  three searches and the page extract, B's mean usable results are not below
  A's.
- **C goes with B** unless the block alone moves conviction by more than 0.05 on
  average: the mean of |composite C − composite B| over the stocks (B and C
  read the same evidence). Above it, the block waits for PR-017's grades.
- "No benefit" is a valid result: the card then closes with the setting off.

**Also reported, not acted on:** what the page extract would hold at 2,000
characters instead of 600 (the C arm's page, when Tavily fetched it live):
its length and how many lens words fall in the first 600 against the first
2,000 characters.
"""
from __future__ import annotations

import sys

sys.dont_write_bytecode = True

import argparse  # noqa: E402
import json  # noqa: E402
import re  # noqa: E402
import statistics  # noqa: E402
import time  # noqa: E402
from contextlib import ExitStack, contextmanager  # noqa: E402
from dataclasses import replace  # noqa: E402
from datetime import date  # noqa: E402
from pathlib import Path  # noqa: E402
from unittest.mock import patch  # noqa: E402

_REPO = Path(__file__).resolve().parents[2]
for _p in (str(_REPO), str(_REPO / "src")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

SEARCHES = ("company_news", "sector_policy_news", "macro_context")
SHARE_RISE = 0.20          # 20 points
BLOCK_LIMIT = 0.05         # mean |composite C - composite B|
STOCKS = 20
MIN_INDUSTRIES = 8
EXTRACT_NOW, EXTRACT_ASKED = 600, 2000

# Words any business story uses; a match on these says nothing about the
# industry. Fixed before the run.
COMMON_WORDS = frozenset("""
india indian news results result growth price prices demand sales revenue revenues
quarter quarterly profit profits margin margins cost costs volume volumes share
shares stock stocks market markets company companies business year years month
months government policy rate rates data report reports high higher lower record
order orders new from with that this their they will over into such than more
expansion capacity commentary guidance outlook latest update""".split())


# ---------------------------------------------------------------------------
# What is counted (pure; tested)
# ---------------------------------------------------------------------------

def _tokens(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z][a-z0-9]+", (text or "").lower()) if len(w) >= 4}


def lens_words(choice) -> frozenset[str]:
    """The words a result must hold to count as on-industry for this stock."""
    if choice is None or choice.kind == "none":
        return frozenset()
    if choice.lens is not None:
        text = " ".join(choice.lens.kpis) + " " + choice.lens.news_terms
    else:
        text = choice.industry
    return frozenset(_tokens(text) - COMMON_WORDS)


def usable(results: list[dict]) -> int:
    return sum(1 for r in results or ()
               if str(r.get("title") or "").strip() or str(r.get("snippet") or "").strip())


def on_industry(results: list[dict], words: frozenset[str]) -> int:
    """How many results' title or snippet holds a lens word."""
    if not words:
        return 0
    return sum(1 for r in results or ()
               if _tokens(f"{r.get('title') or ''} {r.get('snippet') or ''}") & words)


def _key(r: dict) -> str:
    return str(r.get("link") or "").strip() or str(r.get("title") or "").strip().lower()


def repeats(sector: list[dict], macro: list[dict]) -> int:
    seen = {_key(r) for r in sector or () if _key(r)}
    return sum(1 for r in macro or () if _key(r) and _key(r) in seen)


def composite(outputs: dict, weights: dict) -> float | None:
    """The aggregator's composite (SignalAggregator.run): errored outputs left
    out, weights renormalised; None when nothing scored."""
    total, weight = 0.0, 0.0
    for name, out in (outputs or {}).items():
        if getattr(out, "error", None):
            continue
        w = float(weights.get(name, 0.0))
        total += round(float(out.overall_score) * w, 4)
        weight += w
    if not weight:
        return None
    return max(0.0, min(1.0, total / weight))


def choose_stocks(dives: list[dict], n: int = STOCKS) -> list[dict]:
    """`n` general-path dives with a Yahoo label, one stock each, taken in
    turn from each industry (most dives first), the latest dive first."""
    by_industry: dict[str, list[dict]] = {}
    for d in sorted(dives, key=lambda r: r["dive_date"], reverse=True):
        if d.get("graph") != "generic" or not d.get("industry"):
            continue
        by_industry.setdefault(d["industry"], []).append(d)
    order = sorted(by_industry, key=lambda k: (-len(by_industry[k]), k))
    chosen: list[dict] = []
    seen: set[str] = set()
    while len(chosen) < n and any(by_industry[k] for k in order):
        for k in order:
            while by_industry[k]:
                d = by_industry[k].pop(0)
                if d["symbol"] not in seen:
                    seen.add(d["symbol"])
                    chosen.append(d)
                    break
            if len(chosen) >= n:
                break
    return chosen


def summarise(rows: list[dict]) -> dict:
    """The bench's figures, each with its n, and the rule's outcome."""
    done = [r for r in rows if r.get("arms")]
    out: dict = {"stocks": len(done)}
    if not done:
        out["outcome"] = "no stock completed: nothing to judge"
        return out
    for search in SEARCHES + ("policy_deep_dive",):
        for arm in ("A", "B"):
            vals = [r["arms"][arm]["usable"].get(search) for r in done]
            vals = [v for v in vals if v is not None]
            out[f"usable_{search}_{arm}"] = (round(statistics.mean(vals), 2) if vals else None,
                                             len(vals))
    labelled = [r for r in done if r.get("words")]
    for arm in ("A", "B"):
        hits = sum(r["arms"][arm]["on_industry"] for r in labelled)
        total = sum(r["arms"][arm]["results"] for r in labelled)
        out[f"on_industry_{arm}"] = (round(hits / total, 3) if total else None, total)
        out[f"repeats_{arm}"] = (sum(r["arms"][arm]["repeats"] for r in done), len(done))
    out["on_industry_stocks"] = len(labelled)

    def deltas(x: str, y: str) -> list[float]:
        return [abs(r["arms"][x]["composite"] - r["arms"][y]["composite"]) for r in done
                if r["arms"][x].get("composite") is not None
                and r["arms"][y].get("composite") is not None]

    for x, y in (("B", "A"), ("C", "A"), ("C", "B"), ("A2", "A")):
        d = deltas(x, y)
        out[f"mean_abs_{x}_{y}"] = (round(statistics.mean(d), 3) if d else None, len(d))
        out[f"verdict_changes_{x}_{y}"] = (
            sum(1 for r in done if r["arms"][x].get("verdict") and r["arms"][y].get("verdict")
                and r["arms"][x]["verdict"] != r["arms"][y]["verdict"]), len(d))

    share_a, share_b = out["on_industry_A"][0], out["on_industry_B"][0]
    # Rounded before comparing: 0.3 - 0.1 is 0.19999999999999998 in floats,
    # and a rise of exactly 20 points meets the rule.
    rise = (round(share_b - share_a, 6)
            if share_a is not None and share_b is not None else None)
    fewer = [s for s in SEARCHES + ("policy_deep_dive",)
             if out[f"usable_{s}_A"][0] is not None and out[f"usable_{s}_B"][0] is not None
             and out[f"usable_{s}_B"][0] < out[f"usable_{s}_A"][0]]
    b_ready = rise is not None and rise >= SHARE_RISE and not fewer
    block = out["mean_abs_C_B"][0]          # rounded to 3 places: 0.05 meets the limit
    c_goes = b_ready and block is not None and block <= BLOCK_LIMIT
    out["share_rise"] = round(rise, 3) if rise is not None else None
    out["fewer_usable"] = fewer
    out["b_ready"] = b_ready
    out["c_goes"] = c_goes
    if not b_ready:
        out["outcome"] = ("no benefit shown: the setting stays off"
                          + (f" (share rise {rise:+.1%}" if rise is not None else " (no share")
                          + (f"; fewer usable results in {', '.join(fewer)})" if fewer else ")"))
    elif c_goes:
        out["outcome"] = "B and C ready: the lens searches and the industry block"
    else:
        out["outcome"] = ("B ready; the block waits for PR-017's grades (it moved the "
                          f"composite by {block} on average with the same evidence)")
    out["too_few"] = len(done) < 30
    return out


def render(summary: dict, rows: list[dict]) -> str:
    s = summary
    lines = [f"PR-032 bench: {s.get('stocks', 0)} stocks"
             + (" (under 30: too few to judge beyond this predeclared rule)"
                if s.get("too_few") else "")]
    if not s.get("stocks"):
        return "\n".join(lines + [s.get("outcome", "")])
    lines.append("search | usable A (n) | usable B (n)")
    for search in SEARCHES + ("policy_deep_dive",):
        a, b = s[f"usable_{search}_A"], s[f"usable_{search}_B"]
        lines.append(f"{search} | {a[0]} ({a[1]}) | {b[0]} ({b[1]})")
    a, b = s["on_industry_A"], s["on_industry_B"]
    lines.append(f"on-industry share: A {a[0]} of {a[1]} results, B {b[0]} of {b[1]} "
                 f"(stocks with lens words: {s['on_industry_stocks']}); rise "
                 f"{s['share_rise']}")
    lines.append(f"sector/macro repeats: A {s['repeats_A'][0]}, B {s['repeats_B'][0]} "
                 f"(n {s['repeats_A'][1]} stocks)")
    for x, y in (("B", "A"), ("C", "A"), ("C", "B"), ("A2", "A")):
        m, v = s[f"mean_abs_{x}_{y}"], s[f"verdict_changes_{x}_{y}"]
        lines.append(f"composite {x} vs {y}: mean |change| {m[0]} (n {m[1]}); verdict "
                     f"changed {v[0]} of {v[1]}")
    lines.append(f"RULE: {s['outcome']}")
    extracts = [r["extract"] for r in rows if r.get("extract")]
    if extracts:
        lines.append(f"page extract, {len(extracts)} live pages: median length "
                     f"{statistics.median(e['chars'] for e in extracts):.0f} chars; lens words "
                     f"in the first {EXTRACT_NOW}: {sum(e['words_600'] for e in extracts)}, in "
                     f"the first {EXTRACT_ASKED}: {sum(e['words_2000'] for e in extracts)}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# The run (I/O)
# ---------------------------------------------------------------------------

@contextmanager
def _capture(store: dict):
    """Record each search's raw results by section, and each live Tavily page."""
    from services.clients import tavily_fetcher
    from services.data.context import bundle_builder as bb
    from services.data.fetchers import news

    current: dict = {"name": None}
    real_news, real_tavily = news.fetch_news_result, tavily_fetcher.search_tavily

    def news_wrapper(queries, max_queries=None, api_key=None, tbs=None, searches=None):
        mine: list = []
        kwargs = {"api_key": api_key, "tbs": tbs, "searches": mine}
        if max_queries is not None:
            kwargs["max_queries"] = max_queries
        result = real_news(queries, **kwargs)
        if searches is not None:
            searches.extend(mine)
        if current["name"]:
            store.setdefault("searches", {})[current["name"]] = mine[0] if mine else None
        return result

    def tavily_wrapper(query, *args, **kwargs):
        results = real_tavily(query, *args, **kwargs)
        store.setdefault("pages", []).append({"query": query, "results": results})
        return results

    def tagged(name, fn):
        def run(*args, **kwargs):
            current["name"] = name
            try:
                return fn(*args, **kwargs)
            finally:
                current["name"] = None
        return run

    with ExitStack() as stack:
        stack.enter_context(patch.object(news, "fetch_news_result", news_wrapper))
        stack.enter_context(patch.object(tavily_fetcher, "search_tavily", tavily_wrapper))
        for name, attr in (("company_news", "_fetch_company_news"),
                           ("sector_policy_news", "_fetch_sector_policy_news"),
                           ("macro_context", "_fetch_macro_context")):
            stack.enter_context(patch.object(bb, attr, tagged(name, getattr(bb, attr))))
        yield


def _build(query, enabled: bool):
    from services.data.context import bundle_builder as bb
    from services.data.context import lenses

    store: dict = {}
    with patch.object(lenses, "lenses_enabled", lambda: enabled), _capture(store):
        bundle = bb.build_sector_bundle(query, "generic")
    return bundle, store


def _arm_searches(bundle, store: dict, words: frozenset[str]) -> dict:
    searches = store.get("searches") or {}
    results = {name: list((searches.get(name) or {}).get("results") or []) for name in SEARCHES}
    pooled = [r for name in SEARCHES for r in results[name]]
    status = (bundle.section_status or {}).get("policy_deep_dive", "")
    return {
        "queries": {name: (searches.get(name) or {}).get("query") for name in SEARCHES},
        "usable": {**{name: usable(results[name]) for name in SEARCHES if searches.get(name)},
                   "policy_deep_dive": 1 if status in ("ok", "cache_hit") else 0},
        "results": len(pooled),
        "on_industry": on_industry(pooled, words),
        "repeats": repeats(results["sector_policy_news"], results["macro_context"]),
        "titles": {name: [r.get("title") for r in results[name]] for name in SEARCHES},
    }


def _analyse(analyst_cls, query, bundle, weights: dict, arm: str) -> dict:
    from backend.shared.pipeline.verdict_shadow import verdict_from_composite

    outputs = analyst_cls().run(query, bundle, "generic", run_id=f"pr032-bench-{arm}")
    score = composite(outputs, weights)
    return {"composite": round(score, 4) if score is not None else None,
            "verdict": verdict_from_composite(score) if score is not None else "",
            "dimensions": {k: round(float(v.overall_score), 3) for k, v in outputs.items()
                           if not getattr(v, "error", None)}}


def bench_stock(symbol: str, *, orchestrator, analyst_cls, lens_set) -> dict:
    query = orchestrator._resolve_ticker(symbol, exact=True)
    orchestrator._resolve_weights_for(query.ticker)
    weights = dict(orchestrator._aggregator_weights or {})

    bundle_a, store_a = _build(query, enabled=False)
    bundle_c, store_c = _build(query, enabled=True)
    bundle_b = replace(bundle_c, industry_block="")
    choice = lens_set.lens_for(_industry_of(bundle_c, query))
    words = lens_words(choice)

    row = {"symbol": query.ticker, "company": query.company_name,
           "lens": bundle_c.lens or choice.record, "industry": choice.industry,
           "words": sorted(words), "block": bundle_c.industry_block, "arms": {}}
    search_a = _arm_searches(bundle_a, store_a, words)
    search_c = _arm_searches(bundle_c, store_c, words)
    row["arms"]["A"] = {**search_a, **_analyse(analyst_cls, query, bundle_a, weights, "A")}
    row["arms"]["A2"] = _analyse(analyst_cls, query, bundle_a, weights, "A2")
    row["arms"]["B"] = {**search_c, **_analyse(analyst_cls, query, bundle_b, weights, "B")}
    row["arms"]["C"] = {**search_c, **_analyse(analyst_cls, query, bundle_c, weights, "C")}
    row["extract"] = _extract_report(store_c, search_c, words)
    return row


def _industry_of(bundle, query) -> str:
    """The Yahoo label the C bundle read: its peers note names it."""
    note = str((bundle.section_provenance or {}).get("peers_valuation", {}).get("peers") or "")
    m = re.search(r'Yahoo industry "([^"]+)"', note)
    if m:
        return m.group(1)
    from services.data.context.peers import choose_peers
    return choose_peers(query.ticker, sector="generic").industry


def _extract_report(store: dict, search: dict, words: frozenset[str]) -> dict | None:
    pages = store.get("pages") or []
    if not pages or not pages[-1]["results"]:
        return None
    content = str(pages[-1]["results"][0].get("content") or "")
    return {"query": pages[-1]["query"], "chars": len(content),
            "words_600": len(_tokens(content[:EXTRACT_NOW]) & words),
            "words_2000": len(_tokens(content[:EXTRACT_ASKED]) & words)}


def main(argv: list[str] | None = None) -> int:
    from scripts.lenses import coverage_report as cov
    from core.config import settings
    from services.data.context.lenses import load_lenses
    from services.data.context.peers import PROFILE_PATH

    ap = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    ap.add_argument("--yes", action="store_true", help="spend: run the searches and the model")
    ap.add_argument("--symbols", help="comma-separated NSE symbols instead of the chosen ones")
    ap.add_argument("--n", type=int, default=STOCKS)
    ap.add_argument("--weeks", type=int, default=8)
    ap.add_argument("--out", default="/tmp/pr032_bench.json", help="raw rows, JSON")
    args = ap.parse_args(argv)

    lens_set = load_lenses()
    today = date.today()
    if args.symbols:
        chosen = [{"symbol": s.strip().upper(), "industry": "?", "dive_date": ""}
                  for s in args.symbols.split(",") if s.strip()]
    else:
        dives = cov.gather(Path(settings.DISCOVERY_DATA_DIR), today, args.weeks,
                           profiles_path=PROFILE_PATH)
        chosen = choose_stocks(dives, args.n)
    industries = {d["industry"] for d in chosen}
    print(f"PR-032 bench plan, {today}: {len(chosen)} stocks from {len(industries)} industries"
          + ("" if len(industries) >= MIN_INDUSTRIES or args.symbols
             else f" (the card asks for at least {MIN_INDUSTRIES})"))
    for d in chosen:
        print(f"  {d['symbol']} | {d['industry']} | lens {lens_set.lens_for(d['industry']).record}")
    print(f"cost: about {len(chosen) * 6} Serper searches, {len(chosen) * 2} Tavily pages "
          f"at most, {len(chosen) * 4} calls of {settings.LLM_MODEL_REASONING}")
    if not args.yes:
        print("plan only: nothing was called. Add --yes to run it.")
        return 0

    from backend.shared.pipeline.unified_analyst import UnifiedAnalyst
    from core.intelligence.rl.workflows.sector_router import get_orchestrator

    orchestrator = get_orchestrator("generic")
    rows: list[dict] = []
    for d in chosen:
        t0 = time.time()
        try:
            row = bench_stock(d["symbol"], orchestrator=orchestrator,
                              analyst_cls=UnifiedAnalyst, lens_set=lens_set)
        except Exception as exc:          # one stock's failure costs only that stock
            row = {"symbol": d["symbol"], "error": f"{type(exc).__name__}: {exc}"[:300]}
        row["seconds"] = round(time.time() - t0, 1)
        rows.append(row)
        print(f"  done {d['symbol']} in {row['seconds']}s"
              + (f" ({row['error']})" if row.get("error") else ""), flush=True)
    summary = summarise(rows)
    Path(args.out).write_text(json.dumps({"date": today.isoformat(), "summary": summary,
                                          "rows": rows}, indent=1, default=str),
                              encoding="utf-8")
    print(render(summary, rows))
    print(f"raw rows: {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

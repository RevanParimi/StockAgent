# Morning Brief Enhancements — Design Spec

**Date:** 2026-07-28
**Author:** Claude (Opus 4.8) with Revan
**Status:** Approved (design), pending implementation
**Builds on:** [2026-07-27 brief redesign](2026-07-27-morning-brief-redesign-design.md)
**Touches:** `core/delivery/brief.py`, `config.yaml`, `src/backend/shared/config/settings/base.py`, `tests/unit/test_delivery_brief.py`

---

## 1. Goal

Three additive enhancements on top of the now-live sectioned brief, all staying
strictly **research-framed (never personal advice)**:

- **A. Earnings "why"** — each earnings line is a *holding*; explain why it matters and,
  where the dossier has it, what to watch.
- **B. IPO lean** — the tool's own **demand-based** research view per IPO (Attractive /
  Moderate / Soft / data-pending), consistent with how it already shows a BUY view on
  discovery stocks. **Demand-only** — the IPO feed has no valuation/earnings data, so we do
  NOT claim P/E or fundamental analysis. No grey-market-premium / listing-gain number
  (no reliable source).
- **C. Overnight "why it matters"** — a one-line relevance note per overnight item.

## 2. Non-goals
- No personalized buy/avoid advice; no GMP scrape; no listing-gain prediction.
- No new IPO valuation data source.
- **No new LLM calls** — A and B are deterministic; C reuses the single existing SUMMARY
  narration call.

## 3. Component design (`core/delivery/brief.py`)

### 3.1 A — Earnings "why" (deterministic)
Enrich each `earnings_soon` entry (built from held symbols) at build time with a best-effort
`watch` string:

```
_earnings_watch(symbol: str) -> str
    sector = SectorRegistry().resolve(symbol)         # cheap registry lookup
    d = PredictionStore(symbol, sector=sector).load_dossier()
    open_g = [g for g in d.guidance if g.status == "open"]   # GuidanceItem.guidance
    return _trim_words(open_g[-1].guidance, cfg maxlen) if open_g else ""
    # any failure (no sector / no dossier / no guidance) -> "" (non-fatal)
```

`build_morning_brief` attaches `watch` to each earnings entry. **Render** (EARNINGS section):
```
  • SUZLON  — Tue 28 Jul
      You hold this — results & guidance are the next catalyst.
  • ACMESOLAR  — Wed 29 Jul
      You hold this — watch: FY27 capex guidance (₹42,000 cr).
```
Rule: line 2 = `You hold this — ` + (`watch: {watch}` if watch else `results & guidance are the next catalyst.`).

### 3.2 B — IPO lean (deterministic, demand-based, config thresholds)
```
_ipo_lean(row: dict) -> tuple[str, str]   # (label, reason)
    total, qib = row.get("total_x"), row.get("qib_x")
    if total is None and qib is None and row.get("retail_x") is None:
        return ("data pending", "subscription not yet reported")
    strong = (total or 0) >= STRONG_DEMAND_X or (qib or 0) >= STRONG_QIB_X
    soft   = (total or 0) <  SOFT_DEMAND_X and (qib or 0) < SOFT_DEMAND_X
    if strong: return ("STRONG DEMAND", "heavy demand — historically tends to list well, though never guaranteed.")
    if soft:   return ("SOFT DEMAND",   "light subscription so far — muted interest.")
    return ("MODERATE DEMAND", "steady subscription interest.")
```
Section header becomes `IPOs OPEN NOW   (the tool's research view — not advice)`. **Render** per IPO:
```
  • XTRANET  Xtranet Technologies
      Lean: STRONG DEMAND · 24× overall (QIB 41×)
      Heavy demand — historically tends to list well, though never guaranteed.
```
`data pending` rows render on one line (`· Lean: data pending — subscription not yet reported`).
The demand figure reuses the existing `_ipo_demand(row)`.

### 3.3 C — Overnight "why it matters" (reuse the ONE existing call)
`_narrate_brief` currently returns the headline string. Change it to return
`(headline: str, overnight_notes: list[str])`:
- Extend `_PROMPT` to ask for JSON `{"headline": "...", "overnight_notes": ["<=1 line each, aligned to the overnight items in order, [] if none>"]}`.
- Parse both; `overnight_notes` defaults to `[]` on any failure (deterministic fallback unchanged for headline).
- `build_morning_brief` attaches note-by-index onto each `brief["overnight"]` item (`item["note"]`); extra/short lists tolerated.

**Render** (OVERNIGHT): under each headline, if `note`:
```
  • <headline>
      Why it matters: <note>
```

## 4. Config additions (`delivery.*`; config-over-hardcode)
| Key | Default | Meaning |
|-----|---------|---------|
| `delivery.brief_ipo_strong_demand_x` | `10.0` | total-x (or qib-x via next key) at/above ⇒ STRONG |
| `delivery.brief_ipo_strong_qib_x` | `15.0` | qib-x at/above ⇒ STRONG |
| `delivery.brief_ipo_soft_demand_x` | `2.0` | below ⇒ SOFT |
| `delivery.brief_earnings_watch_maxlen` | `120` | cap for the earnings watch line |

## 5. Testing (`tests/unit/test_delivery_brief.py`)
1. `_ipo_lean`: strong (total 24 / qib 41), soft (total 1.5), moderate (total 5), data-pending ({}).
2. Earnings render: holding with no watch → generic catalyst line; with a monkeypatched `_earnings_watch` → `watch: …` line.
3. `_earnings_watch`: monkeypatched SectorRegistry + PredictionStore returning a dossier with one open guidance → returns its text; no dossier → "".
4. Overnight notes: `_narrate_brief` monkeypatched to return `("h", ["note1"])` → render shows `Why it matters: note1`; empty notes → no note line.
5. Golden render: full brief with earnings watch + IPO lean + overnight note present.
6. Existing brief tests still green (render signature of `_narrate_brief` changed — update its call sites/tests).

Full-suite fail-set must stay byte-identical to the known-red baseline (A/B).

## 6. Rollout / risk
- Pure additive render + one deterministic dossier read per held-earnings ticker (1–3/day); zero new LLM calls.
- Every enrichment degrades to the plain line on any failure; `render_brief_text` never raises.
- Deploy watch: first 08:50 IST brief after deploy shows earnings notes + IPO leans (when demand data exists) + overnight notes.

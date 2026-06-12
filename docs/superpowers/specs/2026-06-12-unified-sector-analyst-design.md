# Unified Sector Analyst — Automobile Pipeline Redesign

**Date:** 2026-06-12
**Status:** APPROVED — ready for implementation
**Scope:** Automobile sector first. BFSI / IT / renewable onboard later via config + one prompt file each.

---

## 1. Problem

The automobile sector run costs **11 LLM calls + 8–9 paid API calls (~$0.11/ticker)** for what is
fundamentally one analysis. The 9 "agents" are not agents — they are 9 prompts over mostly the
same data, each making its own LLM call and its own Serper search:

- 6–7 Serper calls per run where 3 suffice (sentiment, policy, competitive, fundamentals,
  sales_demand, raw_materials each search independently; queries overlap in intent).
- The actual analysis runs on the **bulk model** (qwen-2.5-72b) while the reasoning model is
  spent only on aggregation — backwards.
- Sentiment agent: full LLM call + Serper call for **0.04 weight**.
- Valuation output extracted twice (aggregator weighting AND hardcoded field pull,
  `signal_aggregator.py:226–235`).
- Dossier digest, date rules, data-only rules repeated in all 9 prompts (~45KB context/run).
- Dead weight: `config/registry.py` UniversalAgent map is built but never used by the
  orchestrator (`pipeline/orchestrator.py` imports the 9 classes directly).

Contrast: the RL daily-review loop runs on 2–3 LLM calls, the agentic chat on 1–5. This pipeline
is the outlier.

## 2. Goal & core insight

**Keep the 9 dimensions, kill the 9 LLM calls.** Dimensions are an output format, not an
architecture. One shared data-fetch pass feeds ONE reasoning-model call that scores all 9
dimensions; aggregation becomes deterministic math + the existing synthesis call.

Result: **3 LLM calls** (resolve + analyst + synthesis), **~4 paid API calls**
(3 Serper + 1 Tavily), ~$0.04–0.05/ticker, ~15–20s wall clock. All downstream contracts
byte-compatible — zero RL migration.

## 3. Component 1 — `SectorDataBundle` (one fetch pass)

New `services/data/context/bundle_builder.py`:

```python
@dataclass
class SectorDataBundle:
    sections: dict[str, str]   # labeled, individually char-capped
    has_real_data: bool
    api_calls_made: dict[str, int]  # {"serper": 3, "tavily": 1, ...} for logging/tests

def build_sector_bundle(query: StockQuery, sector: str) -> SectorDataBundle
```

Reuses EXISTING fetchers (no new clients). Sections, fetched once per run:

| Section | Source | Replaces |
|---|---|---|
| `company_news` | Serper search #1: company news / results / guidance / management commentary | sales_demand + fundamentals + sentiment searches |
| `sector_policy_news` | Serper search #2: sector demand + policy/regulatory (FAME, PLI, BS6) + competitive moves | policy_regulatory + competitive_intel searches |
| `macro_context` | Serper search #3 (SKIPPED on macro_cache hit) + yfinance INR/USD + crude + factor regime | risk_macro search |
| `policy_deep_dive` | 1 Tavily page (down from 2), existing cache | policy_regulatory's 2 Tavily calls |
| `fundamentals` | yfinance fundamentals + NSE board/results dates (from prefetch, no refetch) | fundamentals builder |
| `technicals` | local RSI/MACD/BB + 10-yr history (yfinance, cached) | pattern_analysis builder |
| `commodities` | yfinance 6 commodity tickers (existing daily `_COMMODITY_CACHE`) | raw_materials builder |
| `flows_sentiment` | NSE bulk deals + FII/DII + MF herding | sentiment + risk_macro builders |
| `peers_valuation` | yfinance peer P/E (existing peer list) + NSE dividend/bonus | valuation_catalyst builder |
| `dossier` | dossier digest — injected ONCE | 9× repetition |

Rules: every section individually capped (`UNIFIED_SECTION_MAX_CHARS`, default 2500); total bundle
capped (`UNIFIED_BUNDLE_MAX_CHARS`, default 18000); every fetcher failure non-fatal (section
becomes `"unavailable"`); `has_real_data` true if ≥3 sections populated. NSE data comes from the
orchestrator's existing single prefetch — the bundle builder must NOT refetch it.

## 4. Component 2 — `UnifiedAnalyst` (one reasoning call)

New `src/backend/shared/pipeline/unified_analyst.py`, sector-generic:

```python
class UnifiedAnalyst:
    def run(self, query: StockQuery, bundle: SectorDataBundle, sector: str) -> dict[str, AgentOutput]
        """One LLM call -> 9 dimension outputs. NEVER raises; returns {} on total failure."""
```

- Model: `settings.LLM_MODEL_REASONING` (the good model finally does the analysis),
  temp 0.2, json_object, `UNIFIED_ANALYST_MAX_TOKENS` (default 3500), retry ×2.
- Prompt: new `src/backend/sectors/automobile/prompts/unified.py` — system prompt with the
  date/data-only/grounding rules ONCE, then per-dimension definitions distilled from the 9
  existing prompt files (each dimension: what to assess, its 5 sub_score names, scoring anchors).
  Sector-parameterized: other sectors later add one prompts module, nothing else.
- Output contract per dimension (same 9 keys: `sales_demand` … `valuation_catalyst`):
  `score` (0–1), `confidence`, `summary`, `key_evidence` (≤3 bullets), `sub_scores`
  (the dimension's 5 named sub-scores; any missing sub_score defaults to the dimension score),
  plus for `valuation_catalyst` only: `price_target`, `recovery_quarters`, `discount_reason`,
  `recovery_catalysts`.
- Parse → instantiate the SAME existing `AgentOutput` subclasses (SalesDemandOutput, …) so
  `FinalReport.agent_outputs` is schema-identical. Malformed/missing dimension → that dimension's
  `_no_data_output()` equivalent (neutral 0.5 + error flag), same as today's degraded behavior.

## 5. Component 3 — Aggregation (unchanged math, one extraction point)

- Weighted composite: existing `SignalAggregator` weighting path, fed the 9 outputs exactly as
  the parallel agents feed it today — `AGENT_WEIGHTS` × RL per-ticker learned weights
  (`set_aggregator_weights`) × lesson emphasis all keep working with **zero changes**.
- Synthesis LLM call: existing SignalAggregator call stays as-is (verdict, conviction_drivers,
  top_risks, investment_thesis).
- Cleanup: valuation fields (`price_target`, `discount_reason`, …) extracted in ONE helper used
  by both legacy and unified paths (removes the dual-path smell at `signal_aggregator.py:226–235`
  without changing values).

## 6. Component 4 — Orchestrator branch + surfaces

`BaseSectorOrchestrator.analyse` / `analyse_async`:

```
resolve ticker (unchanged) → load RL weights (unchanged) → prefetch NSE (unchanged)
→ if SECTOR_NAME in UNIFIED_ANALYST_SECTORS:
      bundle = build_sector_bundle(query, sector)        # one fetch pass
      outputs = UnifiedAnalyst().run(query, bundle, sector)
      if not outputs and UNIFIED_ANALYST_FALLBACK_LEGACY: run legacy worker pool
      else: progress_callback(name, score) per dimension  # UI stays alive
  else: legacy 9-agent worker pool (byte-identical)
→ SignalAggregator (unchanged)
```

- WebSocket `/ws/stream`, REST `/analyse`, chat `run_agent_analysis` tool, scheduler,
  `daily_review._run_todays_agent_scores` — all unchanged consumers; FinalReport identical shape.
- Per-dimension `progress_callback` fires after the analyst returns (scores arrive as one batch
  instead of trickling — acceptable; UI contract is per-agent events, which it still gets).

## 7. New settings (`src/backend/shared/config/settings/base.py`)

| Setting | Default | Controls |
|---|---|---|
| `UNIFIED_ANALYST_SECTORS` | `"automobile"` | CSV of sectors on the unified path; `""` = fully off |
| `UNIFIED_ANALYST_FALLBACK_LEGACY` | `True` | Total analyst failure → legacy multi-agent run |
| `UNIFIED_ANALYST_MAX_TOKENS` | `3500` | Analyst output budget |
| `UNIFIED_SECTION_MAX_CHARS` | `2500` | Per-section bundle cap |
| `UNIFIED_BUNDLE_MAX_CHARS` | `18000` | Total bundle cap |

## 8. Safety

- `UNIFIED_ANALYST_SECTORS=""` → legacy path byte-identical (branch checked before any new code
  runs). Legacy agents/prompts stay in the repo untouched until all 4 sectors migrate.
- `UnifiedAnalyst.run` never raises; per-dimension parse failures degrade that dimension only;
  total failure falls back to legacy run (flag-gated) — production never gets a blank report.
- RL compatibility is a hard invariant: `weighted_agent_scores` keys, `agent_outputs` keys and
  schemas, verdict enum — all unchanged. Calibration, lesson `prioritise_agents`/`discount_agents`,
  weight adaptation, drift detection need zero migration.
- Cost ceiling per ticker run: 3 LLM calls, ≤3 Serper, ≤1 Tavily.

## 9. Validation

- TDD: bundle builder (section caps, total cap, fetcher-failure → "unavailable", api_calls_made
  counts, no NSE refetch); analyst (never-raises, malformed JSON → degraded dims, sub_scores
  defaulting, valuation extras); orchestrator branch (flag off → legacy path invoked, flag on →
  exactly 1 analyst call, fallback path); aggregator parity (same FinalReport fields from
  unified outputs); single valuation extraction (legacy + unified produce same fields).
- Live (reviewer must RUN): `UNIFIED_ANALYST_SECTORS=automobile` real MARUTI run — show
  FinalReport verdict + all 9 `weighted_agent_scores` populated + `api_calls_made` proving
  ≤3 Serper/≤1 Tavily; then flag-off run proving legacy path still works; then
  `daily_review._run_todays_agent_scores` consuming the unified report.

## 10. Not in scope

- BFSI / IT / renewable migration (later: one prompts module + add to `UNIFIED_ANALYST_SECTORS`).
- Deleting legacy agent classes/prompts or the unused `config/registry.py` (cleanup after all
  4 sectors migrate).
- Early-exit / conditional analysis days.
- Changing FinalReport schema or any consumer.

## 11. File map

| File | Change |
|---|---|
| `services/data/context/bundle_builder.py` | NEW — SectorDataBundle, build_sector_bundle |
| `src/backend/shared/pipeline/unified_analyst.py` | NEW — UnifiedAnalyst (sector-generic) |
| `src/backend/sectors/automobile/prompts/unified.py` | NEW — sectioned analyst prompt, 9 dimension definitions |
| `src/backend/shared/pipeline/base_orchestrator.py` | Unified-path branch in analyse/analyse_async |
| `src/backend/shared/pipeline/signal_aggregator.py` | Single valuation-extraction helper (both paths) |
| `src/backend/shared/config/settings/base.py` | 5 settings |
| tests | `test_bundle_builder.py`, `test_unified_analyst.py`, orchestrator-branch + parity tests |

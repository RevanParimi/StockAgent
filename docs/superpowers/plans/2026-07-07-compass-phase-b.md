# Compass Phase B — Discovery Funnel + Generic Sector Graph Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A weekly quant discovery funnel (~2000 NSE mainboard stocks → ~40 quant candidates → ~10 LLM deep-dives → 5-10 shelf ideas with paper envelopes in an ISOLATED paper lane), plus a **generic sector graph** on the Unified Analyst that lifts Phase A's 4-sector promotion restriction.

**Architecture:** Three new surfaces. (1) **Generic sector graph**: a new `src/backend/sectors/generic/` package (unified prompt + UniversalAgent fallback pool + neutral weights) registered in `UnifiedAnalyst.SECTOR_SPECS`, `bundle_builder._SECTOR_BUNDLE_CFG` and `sector_router` — any sector string not among the 4 native ones routes to it instead of silently degrading to automobile. (2) **Discovery data + funnel**: `services/data/fetchers/bhavcopy.py` + `services/data/stores/eod_store.py` (daily delivery-bhavcopy → per-day parquet under `data/market_cache/bhavcopy/`), bulk/block + surveillance fetchers, and a pure-pandas `core/discovery/` package (universe → signals → composite rank → guards → screen → deep-dive → shelf). (3) **Paper lane**: `paper=True` threading through `generate_forecast` / `run_daily_review` that redirects the `PredictionStore` root to `data/rl/paper/predictions` and HARD-disables WeightAdapter writes, shared-ledger propagation, sticky-regime writes, re-forecasts and the control lane.

**Tech Stack:** Python 3.11, Pydantic v2, pandas + pyarrow (new dep), FastAPI, APScheduler, `nse` package v2.1.3 (`deliveryBhavcopy`, `bulkdeals`, `equityMetaInfo`), yfinance, OpenRouter via `services/clients/llm_client.py`.

**Spec:** `docs/superpowers/specs/2026-07-06-portfolio-intelligence-discovery-design.md` (§4.3 reality check, §6 M3, §8 data plan, §9 rails, §10 Phase B row).

## Verified-against-code findings (read before implementing)

- `UnifiedAnalyst` (`src/backend/shared/pipeline/unified_analyst.py`) returns `{}` for any sector without a `SECTOR_SPECS` entry. `_make_output_cls(prefix, dim, None)` already supports dimensions **without** a sub-scores model — the generic sector needs no sub-score schemas.
- `BaseSectorOrchestrator.__init__` **requires** non-empty `self._sub_agents` (worker-pool fallback). `UniversalAgent(name, prompts_module, sector=...)` (`src/backend/shared/agents/universal/agent.py`) accepts any object with `SYSTEM_PROMPT`/`ANALYSIS_PROMPT` (format vars `{ticker}`, `{company_name}`, `{context}`) and optional `CONTEXT_SEARCH_QUERIES` — a single module of `SimpleNamespace` prompt objects suffices for the fallback pool.
- `PredictionStore` already accepts `base_dir=` (used by tests) — the paper lane needs **no store changes**, only call-site threading.
- `run_daily_review` global-state leak points that `paper=True` must gate: `update_sticky_regime()` (writes `data/predictions/_regime_state.json`), `WeightAdapter().update` + `store.save_weight_memory` (daily_review.py ~line 960), `propagate_lessons` + `save_sector_ledger`/`save_market_ledger` (~line 1011), the Living-Envelope re-forecast block (~line 1114), and Step 10 control lane (~line 1317).
- `nse` v2.1.3: `deliveryBhavcopy(date, folder)` downloads the `sec_bhavdata_full` CSV which contains **OHLC + turnover + delivery %** in one file — one download per day covers momentum/delivery/volume/52-wk signals. `bulkdeals("bulk_deals"|"block_deals", fromdate, todate)` returns dicts. `equityMetaInfo(symbol)` returns surveillance/suspension status.
- The ~20 `core/sectors/*` skeleton dirs (commit e30042f "Multi Sector Support") are the **chat-path** `CoreSectorAdapter` tier — all toggled off in `config/sector_toggles.json`, 8 LLM calls per analysis (legacy pattern), never wired to the RL path. **Phase B does NOT enable them.** The generic graph is built on the Unified Analyst (1 call/ticker) as the spec directs; the skeletons stay untouched.
- Scheduler jobs `_ledger_cleanup_job`, `_event_ingest_job`, `_research_loop_job` hardcode `_KNOWN_SECTORS` = the 4 native sectors and path-sniff `data/predictions/{sector}/{ticker}` — a generic-graph ticker (e.g. SUNPHARMA under `data/predictions/pharma/`) would be misrouted to automobile. Task 4 fixes this.
- Signals scoped v1: **5 live** (vol-adjusted 6m+12m momentum, delivery surge, volume anomaly + breakout, bulk/block accumulation, 52-wk-high proximity + RS) and **2 dark** (insider net buying, MF holding increases — both need data sources that are their own sub-projects; config weights reserved, screen renormalizes over live signals and reports them in `dark_signals` per the spec §8 degraded-mode design). Promoter-pledge guard likewise ships dark (`degraded_checks`). IPO tracker (spec §6.2) is **Phase C** — not in this plan.

## Global Constraints

- **PAPER-LANE ISOLATION is a design invariant (spec §6.3):** paper reviews use store root `data/rl/paper/predictions`, and `paper=True` hard-disables WeightAdapter writes, shared-ledger propagation, sticky-regime state writes, re-forecasts, and the control lane. A unit test asserting "paper review never touches sector/market ledger, weight memory, or regime state" ships with the feature (Task 12) — the phase does not merge without it green.
- Discovery guards (spec §6.1/§9): liquidity floor median daily traded value ≥ ₹5 cr; free-float mcap ≥ ₹500 cr; no ASM/GSM; no BE/BZ (T2T) series; price > ₹20; no upper-circuit streaks; SME excluded (`discovery.include_sme: false`).
- Cost rails: discovery LLM spend = deep-dives only (≤ `discovery.deep_dive_count`, default 10/week, unified one-call path); paper reviews weekly (not daily), never through the daily-review cron; shelf ideas are NOT in `managed_tickers.json`.
- Every `response_format={"type": "json_object"}` LLM call passes `extra_body=JSON_MODE_EXTRA_BODY` (from `services/clients/llm_client.py`). (No new direct LLM calls in this phase — deep-dives reuse the orchestrator/UnifiedAnalyst path which already complies.)
- Pipeline errors are telemetry, never training signal: every fetcher/job stage is non-fatal (log warning, degrade, continue) — mirror `services/data/fetchers/corporate_events.py`.
- All tunables in `config.yaml` + `src/backend/shared/config/settings/base.py` via `cfg("section.key", env=..., fallback=...)`. Secrets never in config.yaml.
- All persistent state under `data/` (Railway volume). Atomic writes (temp file + rename). New stores: `data/market_cache/bhavcopy/*.parquet`, `data/market_cache/bulk_block.json`, `data/market_cache/symbol_meta.json`, `data/discovery/screens/*.json`, `data/discovery/shelf.json`, `data/discovery/shelf_events.jsonl`, `data/rl/paper/predictions/…`.
- Output copy is research/analysis, never "advice"; every shelf idea carries an `invalidation_level` ("thesis dead below X", spec §9.4); no auto-trading.
- Schemas live in `src/backend/shared/schemas/`; no files in retired dirs. New logic packages: `core/discovery/` (registered in CODEBASE.md in Task 15).
- Auth on new routes mirrors `portfolio_api._check_auth` (optional `X-Scheduler-Key`; lockdown deferred — user decision 2026-07-06).
- Existing full unit suite is green (~1693 passed / 7 skipped after Phase A merge). Every task's final step runs its test file AND must not break neighbours; Task 15 runs the whole suite.
- Run tests from repo root: `python -m pytest tests/unit/<file> -v` (pythonpath `[".", "src"]` from pyproject.toml).

---

### Task 1: Config + settings for `discovery.*` and `generic_graph.*` (+ pyarrow dep)

**Files:**
- Modify: `config.yaml` (append at end; also edit the `unified_analyst.sectors` line)
- Modify: `src/backend/shared/config/settings/base.py` (append at end; also edit the `UNIFIED_ANALYST_SECTORS` fallback)
- Modify: `requirements.txt`
- Test: `tests/unit/test_discovery_settings.py`

**Interfaces:**
- Produces (read by every later task): `settings.DISCOVERY_ENABLED: bool`, `DISCOVERY_HISTORY_DAYS: int`, `DISCOVERY_BHAVCOPY_DIR: str`, `DISCOVERY_DATA_DIR: str`, `PAPER_PREDICTION_DATA_DIR: str`, `DISCOVERY_LIQUIDITY_FLOOR_CR: float`, `DISCOVERY_FLOAT_MCAP_FLOOR_CR: float`, `DISCOVERY_MIN_PRICE: float`, `DISCOVERY_MAX_PLEDGE_PCT: float`, `DISCOVERY_CIRCUIT_STREAK_MAX: int`, `DISCOVERY_SHORTLIST_SIZE: int`, `DISCOVERY_MAX_CANDIDATES: int`, `DISCOVERY_DEEP_DIVE_COUNT: int`, `DISCOVERY_SHELF_SIZE: int`, `DISCOVERY_STALE_DAYS: int`, `DISCOVERY_MIN_CONVICTION: float`, `DISCOVERY_INCLUDE_SME: bool`, `DISCOVERY_SIGNAL_WEIGHTS: dict[str, float]`, `GENERIC_AGENT_WEIGHTS: dict[str, float]`; `settings.UNIFIED_ANALYST_SECTORS` now contains `"generic"`.

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_discovery_settings.py
"""Compass Phase B — discovery + generic-graph tunables exposed via settings."""
from core.config import settings


def test_discovery_settings_present():
    assert settings.DISCOVERY_ENABLED is True          # yaml true; base.py fallback False
    assert settings.DISCOVERY_HISTORY_DAYS == 550
    assert settings.DISCOVERY_BHAVCOPY_DIR == "data/market_cache/bhavcopy"
    assert settings.DISCOVERY_DATA_DIR == "data/discovery"
    assert settings.PAPER_PREDICTION_DATA_DIR == "data/rl/paper/predictions"
    assert settings.DISCOVERY_LIQUIDITY_FLOOR_CR == 5.0
    assert settings.DISCOVERY_FLOAT_MCAP_FLOOR_CR == 500.0
    assert settings.DISCOVERY_MIN_PRICE == 20.0
    assert settings.DISCOVERY_MAX_PLEDGE_PCT == 25.0
    assert settings.DISCOVERY_CIRCUIT_STREAK_MAX == 3
    assert settings.DISCOVERY_SHORTLIST_SIZE == 80
    assert settings.DISCOVERY_MAX_CANDIDATES == 40
    assert settings.DISCOVERY_DEEP_DIVE_COUNT == 10
    assert settings.DISCOVERY_SHELF_SIZE == 10
    assert settings.DISCOVERY_STALE_DAYS == 60
    assert settings.DISCOVERY_MIN_CONVICTION == 0.55
    assert settings.DISCOVERY_INCLUDE_SME is False


def test_discovery_signal_weights_sum_to_one():
    w = settings.DISCOVERY_SIGNAL_WEIGHTS
    assert set(w) == {"momentum", "delivery_surge", "volume_breakout",
                      "bulk_block", "high_52wk_rs", "insider_buying", "mf_holding"}
    assert abs(sum(w.values()) - 1.0) < 1e-9
    assert w["momentum"] == 0.30


def test_generic_agent_weights_sum_to_one():
    w = settings.GENERIC_AGENT_WEIGHTS
    assert set(w) == {"business", "fundamentals", "valuation", "technical",
                      "macro", "risk", "management", "earnings"}
    assert abs(sum(w.values()) - 1.0) < 1e-9


def test_generic_on_unified_path_and_regime_role_mapped():
    sectors = {s.strip() for s in settings.UNIFIED_ANALYST_SECTORS.split(",")}
    assert "generic" in sectors
    role_map = settings.SECTOR_AGENT_REGIME_ROLE["generic"]
    assert role_map["technical"] == "pattern_analysis"
    assert role_map["macro"] == "risk_macro"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/unit/test_discovery_settings.py -v`
Expected: FAIL with `AttributeError: module ... has no attribute 'DISCOVERY_ENABLED'`

- [ ] **Step 3: Edit config.yaml**

3a. Change the `unified_analyst:` sectors line:

```yaml
  # CSV of sectors on the unified one-call path; "" disables everywhere.
  sectors: "automobile,banking_bfsi,it_sector,renewable_energy,generic"
```

3b. Inside the existing `sector_agent_regime_role:` mapping, append (same indent as `automobile:`):

```yaml
  generic:                           # Compass Phase B — generic sector graph
    business: sales_demand
    fundamentals: fundamentals
    valuation: valuation_catalyst
    technical: pattern_analysis
    macro: risk_macro
    risk: risk_macro
    management: competitive_intel
    earnings: fundamentals
```

3c. Append at end of file:

```yaml
# =============================================================================
# Compass Phase B — Discovery funnel + generic sector graph (spec 2026-07-06 §6/§8)
# =============================================================================
discovery:
  enabled: true
  history_days: 550              # rolling EOD window (~2.2yr; 12m momentum needs 252 tds)
  bhavcopy_dir: "data/market_cache/bhavcopy"
  data_dir: "data/discovery"     # screens/, shelf.json, shelf_events.jsonl
  paper_data_dir: "data/rl/paper/predictions"   # ISOLATED paper-lane store root (spec §6.3)
  liquidity_floor_cr: 5.0        # median daily traded value ≥ ₹5 cr
  float_mcap_floor_cr: 500.0     # free-float mcap ≥ ₹500 cr (thin float = operator bait)
  min_price: 20.0                # no penny stocks
  max_promoter_pledge_pct: 25.0  # guard ships dark in v1 (no free data source yet)
  circuit_streak_max: 3          # > N trailing upper-circuit days = operator pattern
  shortlist_size: 80             # bhavcopy-ranked names that get per-symbol guard checks
  max_candidates: 40             # ScreenResult size after guards
  deep_dive_count: 10            # weekly unified-analyst calls (LLM cost cap)
  shelf_size: 10                 # max active shelf ideas
  stale_days: 60                 # idea age without trigger -> rotate out
  min_conviction: 0.55           # deep-dive final_score floor to reach the shelf (= BUY threshold)
  include_sme: false             # SME platform excluded by default (spec §6.2)
  signal_weights:                # composite rank blend; renormalized over LIVE signals
    momentum: 0.30               # 6m+12m vol-adjusted (NSE Momentum-50 style)
    delivery_surge: 0.15         # 5d delivery% vs prior 20d
    volume_breakout: 0.15        # 5d/60d volume ratio, gated on 60d-high proximity
    bulk_block: 0.15             # same-side bulk/block net accumulation over 4wks
    high_52wk_rs: 0.10           # 52wk-high proximity + 3m relative strength
    insider_buying: 0.10         # DARK in v1 — fetcher returns None until a source ships
    mf_holding: 0.05             # DARK in v1 — AMC portfolio parsing is its own sub-project

generic_graph:
  # Neutral 8-dimension weights for sectors without a native graph (must sum to 1.0).
  agent_weights:
    business: 0.14
    fundamentals: 0.18
    valuation: 0.14
    technical: 0.12
    macro: 0.12
    risk: 0.12
    management: 0.09
    earnings: 0.09
```

- [ ] **Step 4: Append to `src/backend/shared/config/settings/base.py`**

4a. Edit the existing `UNIFIED_ANALYST_SECTORS` line so the hardcoded fallback also includes generic:

```python
UNIFIED_ANALYST_SECTORS: str = cfg(
    "unified_analyst.sectors", env="UNIFIED_ANALYST_SECTORS",
    fallback="automobile,banking_bfsi,it_sector,renewable_energy,generic",
)
```

(Keep the exact `cfg(...)` call shape already present — only the fallback string changes.)

4b. Append at end of file:

```python
# ---------------------------------------------------------------------------
# Compass Phase B — Discovery funnel + generic sector graph (spec 2026-07-06)
# ---------------------------------------------------------------------------
DISCOVERY_ENABLED: bool = bool(cfg("discovery.enabled", env="DISCOVERY_ENABLED", fallback=False))
DISCOVERY_HISTORY_DAYS: int = int(cfg("discovery.history_days", fallback=550))
DISCOVERY_BHAVCOPY_DIR: str = cfg("discovery.bhavcopy_dir", fallback="data/market_cache/bhavcopy")
DISCOVERY_DATA_DIR: str = cfg("discovery.data_dir", fallback="data/discovery")
PAPER_PREDICTION_DATA_DIR: str = cfg(
    "discovery.paper_data_dir", env="PAPER_PREDICTION_DATA_DIR",
    fallback="data/rl/paper/predictions",
)
DISCOVERY_LIQUIDITY_FLOOR_CR: float = float(cfg("discovery.liquidity_floor_cr", fallback=5.0))
DISCOVERY_FLOAT_MCAP_FLOOR_CR: float = float(cfg("discovery.float_mcap_floor_cr", fallback=500.0))
DISCOVERY_MIN_PRICE: float = float(cfg("discovery.min_price", fallback=20.0))
DISCOVERY_MAX_PLEDGE_PCT: float = float(cfg("discovery.max_promoter_pledge_pct", fallback=25.0))
DISCOVERY_CIRCUIT_STREAK_MAX: int = int(cfg("discovery.circuit_streak_max", fallback=3))
DISCOVERY_SHORTLIST_SIZE: int = int(cfg("discovery.shortlist_size", fallback=80))
DISCOVERY_MAX_CANDIDATES: int = int(cfg("discovery.max_candidates", fallback=40))
DISCOVERY_DEEP_DIVE_COUNT: int = int(cfg("discovery.deep_dive_count", fallback=10))
DISCOVERY_SHELF_SIZE: int = int(cfg("discovery.shelf_size", fallback=10))
DISCOVERY_STALE_DAYS: int = int(cfg("discovery.stale_days", fallback=60))
DISCOVERY_MIN_CONVICTION: float = float(cfg("discovery.min_conviction", fallback=0.55))
DISCOVERY_INCLUDE_SME: bool = bool(cfg("discovery.include_sme", fallback=False))

_DISCOVERY_SIGNAL_WEIGHTS_FALLBACK: dict[str, float] = {
    "momentum": 0.30, "delivery_surge": 0.15, "volume_breakout": 0.15,
    "bulk_block": 0.15, "high_52wk_rs": 0.10, "insider_buying": 0.10,
    "mf_holding": 0.05,
}
DISCOVERY_SIGNAL_WEIGHTS: dict[str, float] = {
    str(k): float(v)
    for k, v in cfg("discovery.signal_weights", fallback=_DISCOVERY_SIGNAL_WEIGHTS_FALLBACK).items()
}

_GENERIC_AGENT_WEIGHTS_FALLBACK: dict[str, float] = {
    "business": 0.14, "fundamentals": 0.18, "valuation": 0.14, "technical": 0.12,
    "macro": 0.12, "risk": 0.12, "management": 0.09, "earnings": 0.09,
}
GENERIC_AGENT_WEIGHTS: dict[str, float] = {
    str(k): float(v)
    for k, v in cfg("generic_graph.agent_weights", fallback=_GENERIC_AGENT_WEIGHTS_FALLBACK).items()
}
```

4c. Find the `SECTOR_AGENT_REGIME_ROLE` fallback dict in base.py (`grep -n "SECTOR_AGENT_REGIME_ROLE" src/backend/shared/config/settings/base.py`) and add the same `"generic"` mapping from Step 3b to its hardcoded fallback dict (resilience if config.yaml is absent):

```python
    "generic": {
        "business": "sales_demand", "fundamentals": "fundamentals",
        "valuation": "valuation_catalyst", "technical": "pattern_analysis",
        "macro": "risk_macro", "risk": "risk_macro",
        "management": "competitive_intel", "earnings": "fundamentals",
    },
```

- [ ] **Step 5: Add pyarrow to requirements.txt**

Append under the `# Data fetching` block:

```
pyarrow>=16.0.0           # Parquet EOD market cache (Compass Phase B discovery)
```

Then install locally: `pip install "pyarrow>=16.0.0"`

- [ ] **Step 6: Run test to verify it passes**

Run: `python -m pytest tests/unit/test_discovery_settings.py tests/unit/test_unified_analyst_settings.py -v`
Expected: PASS (including the pre-existing unified-analyst settings tests — if one of them pins the sectors CSV to the old 4-sector string, update that assertion to the new 5-sector string in the same commit and note it).

- [ ] **Step 7: Commit**

```bash
git add config.yaml src/backend/shared/config/settings/base.py requirements.txt tests/unit/test_discovery_settings.py tests/unit/test_unified_analyst_settings.py
git commit -m "feat(compass-b): discovery + generic-graph config/settings, pyarrow dep (Task 1)"
```

---

### Task 2: Generic sector package (`src/backend/sectors/generic/`)

**Files:**
- Create: `src/backend/sectors/generic/__init__.py` (empty)
- Create: `src/backend/sectors/generic/config/__init__.py` (empty)
- Create: `src/backend/sectors/generic/config/settings.py`
- Create: `src/backend/sectors/generic/prompts/__init__.py` (empty)
- Create: `src/backend/sectors/generic/prompts/unified.py`
- Create: `src/backend/sectors/generic/prompts/dimensions.py`
- Create: `src/backend/sectors/generic/pipeline/__init__.py` (empty)
- Create: `src/backend/sectors/generic/pipeline/orchestrator.py`
- Test: `tests/unit/sectors/test_generic_sector.py`

**Interfaces:**
- Consumes: `settings.GENERIC_AGENT_WEIGHTS` (Task 1), `UniversalAgent(name, prompts_module, sector)` (existing), `BaseSectorOrchestrator` (existing).
- Produces: `GenericSectorOrchestrator` (class, `SECTOR_NAME="generic"`, constructor takes no args, `analyse(ticker) -> FinalReport`); `backend.sectors.generic.prompts.unified` exposing `SYSTEM_PROMPT`/`ANALYSIS_PROMPT` (format vars `ticker`, `company_name`, `report_date`, `bundle`); `backend.sectors.generic.prompts.dimensions` exposing `DIMENSIONS: list[str]` (order: business, fundamentals, valuation, technical, macro, risk, management, earnings) and `PROMPTS: dict[str, SimpleNamespace]`; `backend.sectors.generic.config.settings` exposing `AGENT_WEIGHTS: dict[str, float]` and `TICKERS: list[str]` (empty).

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/sectors/test_generic_sector.py
"""Compass Phase B — generic sector graph package (spec §4.3 reality check)."""
from core.config import settings


def test_generic_dimensions_order():
    from backend.sectors.generic.prompts.dimensions import DIMENSIONS, PROMPTS
    assert DIMENSIONS == ["business", "fundamentals", "valuation", "technical",
                          "macro", "risk", "management", "earnings"]
    for dim in DIMENSIONS:
        p = PROMPTS[dim]
        assert isinstance(p.SYSTEM_PROMPT, str) and len(p.SYSTEM_PROMPT) > 50
        rendered = p.ANALYSIS_PROMPT.format(ticker="SUNPHARMA",
                                            company_name="Sun Pharma", context="ctx")
        assert "SUNPHARMA" in rendered
        assert isinstance(p.CONTEXT_SEARCH_QUERIES, list)


def test_generic_config_settings_module():
    from backend.sectors.generic.config.settings import AGENT_WEIGHTS, TICKERS
    assert AGENT_WEIGHTS == settings.GENERIC_AGENT_WEIGHTS
    assert TICKERS == []


def test_generic_orchestrator_constructs_with_8_agents():
    from backend.sectors.generic.pipeline.orchestrator import GenericSectorOrchestrator
    orch = GenericSectorOrchestrator()
    assert orch.SECTOR_NAME == "generic"
    assert set(orch._sub_agents) == {"business", "fundamentals", "valuation",
                                     "technical", "macro", "risk",
                                     "management", "earnings"}
    assert abs(sum(orch._get_default_weights().values()) - 1.0) < 1e-9


def test_generic_unified_prompt_module_contract():
    import backend.sectors.generic.prompts.unified as U
    assert "JSON" in U.SYSTEM_PROMPT
    rendered = U.ANALYSIS_PROMPT.format(ticker="SUNPHARMA", company_name="Sun Pharma",
                                        report_date="2026-07-07", bundle="BUNDLE")
    assert "SUNPHARMA" in rendered and "BUNDLE" in rendered
    for dim in ["business", "fundamentals", "valuation", "technical",
                "macro", "risk", "management", "earnings"]:
        assert dim in rendered
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/unit/sectors/test_generic_sector.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'backend.sectors.generic'`

- [ ] **Step 3: Create the package**

`src/backend/sectors/generic/config/settings.py`:

```python
"""
Generic sector graph — Compass Phase B (spec §4.3 reality check).

Neutral config for tickers whose sector has no native orchestrator.
AGENT_WEIGHTS re-exports the config.yaml-tunable generic weights so
sector_router.get_sector_weights() and WeightMemory initialisation read
one source of truth. TICKERS is empty by design: generic-graph names are
auto-promoted portfolio/discovery symbols, never a hardcoded universe
(BaseSectorOrchestrator._managed_tickers tolerates the empty list).
"""
from __future__ import annotations

from backend.shared.config import settings as _settings

AGENT_WEIGHTS: dict[str, float] = dict(_settings.GENERIC_AGENT_WEIGHTS)

TICKERS: list[str] = []
```

`src/backend/sectors/generic/prompts/unified.py` — full content:

```python
"""
prompts/unified.py — generic sector (Compass Phase B).

Sector-agnostic Unified Analyst prompt: ONE reasoning-model call scores all
8 dimensions for a stock whose sector has no native graph (pharma, fmcg,
metals, …). Mirrors the grounding/output-size rules of the four native
unified prompts.

NOTE: ANALYSIS_PROMPT is rendered with `.format(ticker=..., company_name=...,
report_date=..., bundle=...)`. Every literal JSON brace below is doubled
(`{{` / `}}`) so `.format()` does not choke on it.
"""

from __future__ import annotations


SYSTEM_PROMPT = """You are a senior Indian-equity research analyst. The stock below belongs to a sector
without a specialised coverage graph, so you apply a rigorous SECTOR-AGNOSTIC framework.

In a single pass you assess EIGHT dimensions of one stock — business quality, fundamentals,
valuation, technical pattern, macro environment, risk, management & governance, and earnings
quality — and return ONE JSON object covering all eight.

CRITICAL GROUNDING RULES (apply to every dimension):
- Score ONLY from the data bundle provided below. Do NOT use training knowledge to fill gaps.
- If a dimension has no supporting data in the bundle, score it 0.5 (neutral) and add
  "no real-time data for this dimension" to that dimension's key_risks.
- Fabricating facts, figures, or events not present in the bundle is strictly prohibited.
- Every section in the bundle carries a [Date: YYYY-MM-DD] tag (today is the report date given
  below). When two facts conflict, trust the more recent one. Treat anything older than 14 days
  as background context only, not primary evidence. Set each dimension's data_freshness to
  "unified_analyst".
- First infer the company's industry from the bundle (fundamentals / company_news sections) and
  judge every dimension against norms for THAT industry — e.g. margin quality for a pharma firm
  is not judged like a metals firm's.
- Be ticker-specific: cite real numbers, dates, and named peers from the bundle wherever possible.
- Output ONLY valid JSON — no markdown fences, no commentary outside the JSON object.

OUTPUT-SIZE RULES (the whole response must fit a fixed token budget — be terse):
- "summary": at most 2 short sentences.
- "key_positives" / "key_risks": at most 3 items each, each item at most 10 words.
- "ticker_vs_peers", "bull_case_if", "bear_case_if", "what_changed": each at most 1 short
  sentence.
- Compact JSON only: no extra whitespace, no markdown, no keys beyond the schema below.
"""


ANALYSIS_PROMPT = """Analyse the Indian company **{ticker}** ({company_name}) as of {report_date}
across all eight dimensions below, using ONLY the data bundle provided.

=== DATA BUNDLE ===
{bundle}
=== END DATA BUNDLE ===

For each dimension, score 0.0-1.0 per its own anchor (below), give a confidence (0.3 sparse
data/inference, 0.7 multiple data points, 1.0 direct verified data), and fill ticker_vs_peers
(numeric comparison vs named peers), bull_case_if (specific catalyst that would add ~0.15),
bear_case_if (specific risk that would cut ~0.15), and what_changed (what shifted this cycle vs
last, with numbers).

BE TERSE — the full response must fit a fixed token budget (same limits as the system prompt).

1. business (0.0 very bearish -> 1.0 very bullish): revenue mix and market position in its
   industry, demand trajectory and order/volume visibility, competitive moat and pricing power,
   customer/geography concentration, growth pipeline credibility.

2. fundamentals (0.0 very bearish -> 1.0 very bullish): revenue and profit growth trend,
   margin trend vs industry norm, return ratios (RoE/RoCE), leverage and interest cover,
   cash-flow conversion and working-capital discipline.

3. valuation (0.0 expensive -> 1.0 cheap/bullish; scores+summary only, no price targets):
   P/E and EV/EBITDA vs named peers and own history, growth-adjusted multiple (PEG-style
   judgement), price/book where relevant, any sum-of-parts or asset-backing angle.

4. technical (0.0 very bearish -> 1.0 very bullish): trend vs 50/200-DMA, RSI/momentum state,
   volume confirmation of the move, distance to 52-week high/low, support/resistance posture
   (use the technicals section of the bundle).

5. macro (0.0 hostile backdrop -> 1.0 supportive backdrop): interest-rate and currency
   sensitivity, commodity input exposure, sector policy/regulatory direction, domestic vs
   export demand cycle relevant to this industry.

6. risk (0.0 severe risk -> 1.0 low risk): balance-sheet stress, regulatory/litigation
   overhangs, customer or product concentration, execution risk on announced plans,
   liquidity/float and any surveillance-list red flags in the bundle.

7. management (0.0 poor governance -> 1.0 excellent): promoter track record and pledge levels,
   capital-allocation discipline, related-party/subsidiary complexity, guidance credibility,
   board and audit hygiene signals.

8. earnings (0.0 deteriorating quality -> 1.0 improving quality): latest quarterly trajectory
   vs run-rate, one-off/exceptional items, revenue-recognition or margin red flags,
   beat/miss vs street or guidance where the bundle shows it.

Return EXACTLY this JSON shape (one block per dimension, in this order):
{{
  "business":     {{"score": 0.0, "confidence": 0.5, "key_positives": [], "key_risks": [],
                   "summary": "", "ticker_vs_peers": "", "bull_case_if": "",
                   "bear_case_if": "", "what_changed": ""}},
  "fundamentals": {{ ... same keys ... }},
  "valuation":    {{ ... same keys ... }},
  "technical":    {{ ... same keys ... }},
  "macro":        {{ ... same keys ... }},
  "risk":         {{ ... same keys ... }},
  "management":   {{ ... same keys ... }},
  "earnings":     {{ ... same keys ... }}
}}
"""
```

`src/backend/sectors/generic/prompts/dimensions.py` — full content:

```python
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
```

`src/backend/sectors/generic/pipeline/orchestrator.py` — full content:

```python
"""
pipeline/orchestrator.py — GenericSectorOrchestrator (Compass Phase B).

Sector-agnostic orchestrator for tickers whose sector has no native graph.
Primary path: the Unified Analyst ("generic" is in UNIFIED_ANALYST_SECTORS,
so BaseSectorOrchestrator._run_agents dispatches to _run_unified — one
reasoning-model call for all 8 dimensions). Fallback path: 8 UniversalAgents
built from prompts/dimensions.py (only on unified total failure with
UNIFIED_ANALYST_FALLBACK_LEGACY=true).
"""
from __future__ import annotations

from backend.shared.config import settings
from backend.shared.pipeline.base_orchestrator import BaseSectorOrchestrator
from backend.shared.agents.universal import UniversalAgent
from backend.sectors.generic.prompts import dimensions as D


class GenericSectorOrchestrator(BaseSectorOrchestrator):
    SECTOR_NAME = "generic"

    def __init__(self) -> None:
        self._sub_agents = {
            dim: UniversalAgent(dim, D.PROMPTS[dim], sector="generic")
            for dim in D.DIMENSIONS
        }
        super().__init__()

    def _get_default_weights(self) -> dict[str, float]:
        return dict(settings.GENERIC_AGENT_WEIGHTS)
```

Create the four empty `__init__.py` files (`src/backend/sectors/generic/__init__.py`, `.../config/__init__.py`, `.../prompts/__init__.py`, `.../pipeline/__init__.py`).

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/unit/sectors/test_generic_sector.py -v`
Expected: PASS (4 tests). Note: `GenericSectorOrchestrator()` construction compiles a LangGraph worker pool — no network calls happen at init.

- [ ] **Step 5: Commit**

```bash
git add src/backend/sectors/generic tests/unit/sectors/test_generic_sector.py
git commit -m "feat(compass-b): generic sector package — unified prompt, fallback pool, orchestrator (Task 2)"
```

---

### Task 3: Register "generic" in UnifiedAnalyst + bundle_builder

**Files:**
- Modify: `src/backend/shared/pipeline/unified_analyst.py` (add generic classes + SECTOR_SPECS entry, after the renewable_energy block ~line 203)
- Modify: `services/data/context/bundle_builder.py` (add generic entry to `_SECTOR_BUNDLE_CFG`, line ~137)
- Test: `tests/unit/test_unified_analyst_generic.py`

**Interfaces:**
- Consumes: `_build_sector_classes(prefix, sub_scores_models)` and `SectorSpec` (existing in unified_analyst.py); `backend.sectors.generic.prompts.unified` (Task 2).
- Produces: `SECTOR_SPECS["generic"]` (8 dimensions, no sub-scores, no valuation extras); `DIMENSIONS["generic"]` == the 8-dim list; `_SECTOR_BUNDLE_CFG["generic"]`.

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_unified_analyst_generic.py
"""Compass Phase B — 'generic' sector on the Unified Analyst one-call path."""
import json

from backend.shared.pipeline.unified_analyst import (
    DIMENSIONS, SECTOR_SPECS, UnifiedAnalyst,
)
from backend.shared.schemas.pipeline import StockQuery


GENERIC_DIMS = ["business", "fundamentals", "valuation", "technical",
                "macro", "risk", "management", "earnings"]


def test_generic_sector_spec_registered():
    assert "generic" in SECTOR_SPECS
    assert DIMENSIONS["generic"] == GENERIC_DIMS
    spec = SECTOR_SPECS["generic"]
    assert spec.prompts_module == "backend.sectors.generic.prompts.unified"
    assert spec.has_valuation_extras is False


def _fake_response() -> str:
    block = {"score": 0.7, "confidence": 0.7, "key_positives": ["strong growth"],
             "key_risks": ["fx risk"], "summary": "Fine.", "ticker_vs_peers": "cheaper",
             "bull_case_if": "order win", "bear_case_if": "margin miss",
             "what_changed": "nothing"}
    return json.dumps({dim: dict(block) for dim in GENERIC_DIMS})


def test_generic_run_parses_all_8_dimensions(monkeypatch):
    ua = UnifiedAnalyst.__new__(UnifiedAnalyst)   # skip __init__ (no LLM client)
    ua._last_prompt_tokens = 0
    ua._last_completion_tokens = 0
    monkeypatch.setattr(UnifiedAnalyst, "_call_llm",
                        lambda self, s, u: _fake_response())

    class _Bundle:
        api_calls_made: dict = {}
        has_real_data = True
        def to_prompt_text(self) -> str: return "BUNDLE"

    query = StockQuery(ticker="SUNPHARMA", company_name="Sun Pharma")
    outputs = ua.run(query, _Bundle(), "generic")
    assert set(outputs) == set(GENERIC_DIMS)
    assert outputs["fundamentals"].overall_score == 0.7
    assert outputs["risk"].agent == "risk"
    assert outputs["technical"].sub_scores is None   # generic dims have no sub-score models


def test_generic_bundle_cfg_registered():
    from services.data.context.bundle_builder import _SECTOR_BUNDLE_CFG
    cfg = _SECTOR_BUNDLE_CFG["generic"]
    assert cfg["has_commodities"] is False
    assert cfg["macro_cache_key"] == "generic"
    assert cfg["peer_tickers_module"] is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/unit/test_unified_analyst_generic.py -v`
Expected: FAIL — `test_generic_sector_spec_registered` with `AssertionError: assert 'generic' in SECTOR_SPECS`

- [ ] **Step 3: Add the generic spec to unified_analyst.py**

Insert after the `_RENEWABLE_ENERGY_CLASSES` block (before the `SectorSpec` dataclass):

```python
# --- generic (Compass Phase B — sector-agnostic graph) -----------------------
GENERIC_DIMENSIONS: list[str] = [
    "business", "fundamentals", "valuation", "technical",
    "macro", "risk", "management", "earnings",
]

# No sub-score models by design: the generic graph is sector-agnostic, and
# _make_output_cls / _parse_dimension already handle sub_scores_model=None.
_GENERIC_CLASSES: dict[str, type[AgentOutput]] = _build_sector_classes(
    "Generic", {dim: None for dim in GENERIC_DIMENSIONS},
)
```

Add to the `SECTOR_SPECS` literal (after the `"renewable_energy"` entry):

```python
    "generic": SectorSpec(
        classes=_GENERIC_CLASSES,
        prompts_module="backend.sectors.generic.prompts.unified",
        has_valuation_extras=False,
    ),
```

- [ ] **Step 4: Add the generic bundle config to bundle_builder.py**

Add to `_SECTOR_BUNDLE_CFG` (after the `"renewable_energy"` entry):

```python
    "generic": {
        # Compass Phase B: sector-agnostic wording — the ticker's industry is
        # inferred by the analyst from the bundle itself.
        "company_news_terms": "results guidance outlook",
        "sector_policy_news_query": (
            "India stock market {month} {year} sector news policy demand"
        ),
        "policy_deep_dive_query": (
            "{company_name} NSE {ticker} results outlook policy regulation {year}"
        ),
        "has_commodities": False,
        "peer_tickers_module": None,
        "peer_tickers_attr": "TICKERS",
        "macro_cache_key": "generic",
    },
```

(`get_serper_key()`/`get_macro_cache()` accept arbitrary keys — verified: single Serper key serves all sectors; macro cache is a plain dict keyed by the alias and is populated on miss.)

- [ ] **Step 5: Run tests to verify they pass (plus unified-analyst neighbours)**

Run: `python -m pytest tests/unit/test_unified_analyst_generic.py tests/unit/test_unified_analyst_sectors.py tests/unit/test_unified_analyst_settings.py -v`
Expected: PASS. If `test_unified_analyst_sectors.py` asserts the exact `SECTOR_SPECS` key set, extend that assertion with `"generic"` in the same commit.

- [ ] **Step 6: Commit**

```bash
git add src/backend/shared/pipeline/unified_analyst.py services/data/context/bundle_builder.py tests/unit/test_unified_analyst_generic.py tests/unit/test_unified_analyst_sectors.py
git commit -m "feat(compass-b): 'generic' SectorSpec on unified analyst + generic bundle config (Task 3)"
```

---

### Task 4: Route unknown sectors to the generic graph (sector_router + scheduler + CLI)

**Files:**
- Modify: `core/intelligence/rl/workflows/sector_router.py` (whole-file rewrite below)
- Modify: `services/scheduler/python/scheduler.py` (`_ledger_cleanup_job`, `_event_ingest_job`, `_research_loop_job` — replace `_KNOWN_SECTORS` path-sniffing)
- Modify: `core/intelligence/rl/workflows/daily_review.py` (`main()` — drop the 4-sector `choices=` restriction)
- Test: `tests/unit/intelligence/rl/test_sector_router_generic.py`

**Interfaces:**
- Consumes: `GenericSectorOrchestrator` (Task 2), `settings.GENERIC_AGENT_WEIGHTS` (Task 1), `get_active_tickers_with_sector()` (existing, `services/api/log_buffer.py`).
- Produces: `get_orchestrator(sector)` returns `GenericSectorOrchestrator` for any sector not in the native map (no more silent automobile fallback); `get_sector_weights(sector)` returns generic weights for unknown sectors; `NATIVE_SECTORS: frozenset[str]` exported from sector_router; scheduler module-level helper `_sector_lookup() -> dict[str, str]`.

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/intelligence/rl/test_sector_router_generic.py
"""Compass Phase B — unknown sectors route to the generic graph, not automobile."""
from core.config import settings
from core.intelligence.rl.workflows import sector_router as sr


def test_native_sectors_unchanged():
    assert sr.NATIVE_SECTORS == frozenset(
        {"automobile", "banking_bfsi", "it_sector", "renewable_energy"}
    )
    assert sr._ORCHESTRATORS["automobile"].endswith("AutomobileAgentOrchestrator")


def test_unknown_sector_gets_generic_orchestrator():
    orch = sr.get_orchestrator("pharma")
    assert type(orch).__name__ == "GenericSectorOrchestrator"
    assert orch.SECTOR_NAME == "generic"


def test_unknown_sector_gets_generic_weights():
    w = sr.get_sector_weights("pharma")
    assert w == settings.GENERIC_AGENT_WEIGHTS


def test_native_sector_still_gets_native_weights():
    w = sr.get_sector_weights("automobile")
    assert "sales_demand" in w        # automobile agent name — not a generic dim


def test_scheduler_sector_lookup_uses_managed_tickers(monkeypatch):
    import services.scheduler.python.scheduler as sched
    monkeypatch.setattr(
        sched, "get_active_tickers_with_sector",
        lambda: [{"sym": "SUNPHARMA", "sector": "pharma"},
                 {"sym": "MARUTI", "sector": "automobile"}],
        raising=False,
    )
    lookup = sched._sector_lookup()
    assert lookup["SUNPHARMA"] == "pharma"
    assert lookup["MARUTI"] == "automobile"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/unit/intelligence/rl/test_sector_router_generic.py -v`
Expected: FAIL with `AttributeError: module ... has no attribute 'NATIVE_SECTORS'`

- [ ] **Step 3: Rewrite sector_router.py**

Replace the full contents of `core/intelligence/rl/workflows/sector_router.py` with:

```python
"""
core/intelligence/rl/workflows/sector_router.py
================================================
Maps sector strings to the correct orchestrator and weight config.

Used by generate_forecast and daily_review so both use the same routing
logic — a single place to add new sectors.

Compass Phase B: sectors WITHOUT a native graph (pharma, fmcg, metals, …)
route to the GENERIC sector graph (sector-agnostic unified analyst +
neutral weights) instead of silently degrading to the automobile graph.
The PredictionStore keeps using the REAL sector name for its directory
layout (data/predictions/pharma/SUNPHARMA/…) — only the analysis graph
is generic.
"""
from __future__ import annotations

import importlib
import logging

logger = logging.getLogger(__name__)

# Sectors with a hand-built native graph.
NATIVE_SECTORS: frozenset[str] = frozenset(
    {"automobile", "banking_bfsi", "it_sector", "renewable_energy"}
)

# sector → dotted path to orchestrator class
_ORCHESTRATORS: dict[str, str] = {
    "automobile":       "core.pipeline.orchestrator.AutomobileAgentOrchestrator",
    "renewable_energy": "backend.sectors.renewable_energy.pipeline.orchestrator.RenewableAgentOrchestrator",
    "banking_bfsi":     "backend.sectors.banking_bfsi.pipeline.orchestrator.BankingAgentOrchestrator",
    "it_sector":        "backend.sectors.it_sector.pipeline.orchestrator.ITAgentOrchestrator",
}

_GENERIC_ORCHESTRATOR = (
    "backend.sectors.generic.pipeline.orchestrator.GenericSectorOrchestrator"
)

# sector → dotted module path that contains AGENT_WEIGHTS
_WEIGHT_MODULES: dict[str, str] = {
    "automobile":       "core.config.settings",
    "renewable_energy": "backend.sectors.renewable_energy.config.settings",
    "banking_bfsi":     "backend.sectors.banking_bfsi.config.settings",
    "it_sector":        "backend.sectors.it_sector.config.settings",
}


def get_orchestrator(sector: str):
    """Return a freshly instantiated orchestrator for the given sector."""
    dotted = _ORCHESTRATORS.get(sector)
    if dotted is None:
        logger.info(
            "[sector_router] Sector '%s' has no native graph — using generic sector graph",
            sector,
        )
        dotted = _GENERIC_ORCHESTRATOR

    module_path, cls_name = dotted.rsplit(".", 1)
    mod = importlib.import_module(module_path)
    cls = getattr(mod, cls_name)
    logger.debug("[sector_router] Resolved '%s' → %s", sector, cls_name)
    return cls()


def get_sector_weights(sector: str) -> dict[str, float]:
    """
    Return the sector-specific AGENT_WEIGHTS dict.
    Used to initialise WeightMemory with the right baseline. Sectors without
    a native graph get the neutral generic weights (config generic_graph.*).
    """
    mod_path = _WEIGHT_MODULES.get(sector)
    if mod_path is None:
        from core.config import settings
        logger.info(
            "[sector_router] Sector '%s' has no native weight module — using generic weights",
            sector,
        )
        return dict(settings.GENERIC_AGENT_WEIGHTS)

    try:
        mod = importlib.import_module(mod_path)
        return dict(mod.AGENT_WEIGHTS)
    except Exception as exc:
        logger.warning(
            "[sector_router] Could not load AGENT_WEIGHTS from '%s': %s — using automobile fallback",
            mod_path, exc,
        )
        from core.config import settings
        return dict(settings.AGENT_WEIGHTS)
```

- [ ] **Step 4: Fix the scheduler's sector lookup**

In `services/scheduler/python/scheduler.py`:

4a. Add a module-level import + helper directly under `_active_tickers()`:

```python
from services.api.log_buffer import get_active_tickers_with_sector


def _sector_lookup() -> dict[str, str]:
    """sym -> sector from managed_tickers.json — works for ANY sector,
    including generic-graph ones (Compass Phase B). Empty dict on failure."""
    try:
        return {
            e["sym"]: e.get("sector", "automobile")
            for e in get_active_tickers_with_sector()
        }
    except Exception as exc:
        logger.warning("[scheduler] _sector_lookup failed: %s", exc)
        return {}
```

(Note: `_daily_review_job` and `_monthly_forecast_job` already import `get_active_tickers_with_sector` locally — the new module-level import replaces those local imports; remove the two local `from services.api.log_buffer import get_active_tickers_with_sector` lines.)

4b. In each of `_ledger_cleanup_job`, `_event_ingest_job`, `_research_loop_job`, delete the `_KNOWN_SECTORS = [...]`, `base_dir = "data/predictions"` and nested `def _sector_for(...)` blocks, and replace with:

```python
        sectors = _sector_lookup()
```

then replace every `sector = _sector_for(ticker)` with:

```python
                sector = sectors.get(ticker, "automobile")
```

(Also delete the now-unused `from pathlib import Path` local import in `_event_ingest_job` / `_research_loop_job` if nothing else in the function uses `Path`; `_ledger_cleanup_job` keeps its other imports.)

4c. In `core/intelligence/rl/workflows/daily_review.py` `main()`, replace the `--sector` argument definition with:

```python
    parser.add_argument(
        "--sector",
        default="automobile",
        help="Sector graph to use (native: automobile | banking_bfsi | it_sector | "
             "renewable_energy; any other sector key routes via the generic graph)",
    )
```

(i.e. drop the `choices=[...]` kwarg.)

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/unit/intelligence/rl/test_sector_router_generic.py tests/unit/intelligence/rl/ -v`
Expected: new file PASS; the existing `tests/unit/intelligence/rl/` suite stays green (scheduler-hook tests monkeypatch `get_active_tickers_with_sector`, which still exists).

- [ ] **Step 6: Commit**

```bash
git add core/intelligence/rl/workflows/sector_router.py services/scheduler/python/scheduler.py core/intelligence/rl/workflows/daily_review.py tests/unit/intelligence/rl/test_sector_router_generic.py
git commit -m "feat(compass-b): route unknown sectors to generic graph; scheduler sector lookup from managed tickers (Task 4)"
```

---

### Task 5: Lift the 4-sector promotion restriction

**Files:**
- Modify: `core/portfolio/promotion.py`
- Modify: `services/api/routes/portfolio_api.py` (two `SUPPORTED_SECTORS` gates: `add_holding` line ~107, `add_watchlist` line ~166)
- Modify: `tests/unit/test_portfolio_promotion.py` (replace `test_promote_unsupported_sector_rejected`)
- Modify: `tests/unit/test_portfolio_api.py` (replace `test_add_holding_unsupported_sector_422`)

**Interfaces:**
- Consumes: `NATIVE_SECTORS` semantics (promotion keeps its own frozenset, mirroring sector_router).
- Produces: `promote_symbol(symbol, sector, origin) -> dict` now accepts ANY sector key matching `^[a-z][a-z0-9_]{1,31}$` and returns an extra `"graph": "native"|"generic"` field; new export `is_valid_sector(sector: str) -> bool`; invalid keys return `{"status": "invalid_sector", ...}`. `SUPPORTED_SECTORS` name is kept as an alias of `NATIVE_SECTORS` (other importers unaffected).

- [ ] **Step 1: Update the tests first (they define the new contract)**

In `tests/unit/test_portfolio_promotion.py`, replace `test_promote_unsupported_sector_rejected` with:

```python
def test_promote_generic_sector_accepted(managed):
    """Phase B: generic sector graph lifts the 4-sector restriction."""
    result = promo.promote_symbol("SUNPHARMA", "pharma", origin="held")
    assert result["status"] == "promoted"
    assert result["graph"] == "generic"
    entry = next(t for t in managed["tickers"] if t["sym"] == "SUNPHARMA")
    assert entry["sector"] == "pharma" and entry["cadence"] == "daily"


def test_promote_native_sector_flagged_native(managed):
    result = promo.promote_symbol("TCS2", "it_sector", origin="held")
    assert result["status"] == "promoted"
    assert result["graph"] == "native"


def test_promote_invalid_sector_key_rejected(managed):
    result = promo.promote_symbol("XYZ", "Pharma & Health!!", origin="held")
    assert result["status"] == "invalid_sector"
    assert all(t["sym"] != "XYZ" for t in managed["tickers"])


def test_is_valid_sector():
    assert promo.is_valid_sector("pharma")
    assert promo.is_valid_sector("banking_bfsi")
    assert not promo.is_valid_sector("Pharma!!")
    assert not promo.is_valid_sector("")
    assert not promo.is_valid_sector("x" * 40)
```

In `tests/unit/test_portfolio_api.py`, replace `test_add_holding_unsupported_sector_422` with (keep the file's existing `client` fixture and monkeypatch style):

```python
def test_add_holding_invalid_sector_422(client):
    resp = client.post("/portfolio/holdings", json={
        "symbol": "XYZ", "sector": "Not A Sector!!", "qty": 1,
        "buy_date": "2026-07-01", "price": 100.0,
    })
    assert resp.status_code == 422
    assert "sector" in resp.json()["detail"].lower()


def test_add_holding_generic_sector_accepted(client, monkeypatch):
    import services.api.routes.portfolio_api as papi
    monkeypatch.setattr(
        papi, "promote_symbol",
        lambda symbol, sector, origin: {"status": "promoted", "symbol": symbol,
                                        "graph": "generic", "cadence": "daily"},
    )
    resp = client.post("/portfolio/holdings", json={
        "symbol": "SUNPHARMA", "sector": "pharma", "qty": 5,
        "buy_date": "2026-07-01", "price": 1650.0,
    })
    assert resp.status_code == 200
    assert resp.json()["promotion"]["graph"] == "generic"
```

(If the old test monkeypatched `promote_symbol` to return `unsupported_sector`, delete that variant entirely — the status no longer exists.)

- [ ] **Step 2: Run tests to verify the new ones fail**

Run: `python -m pytest tests/unit/test_portfolio_promotion.py tests/unit/test_portfolio_api.py -v`
Expected: new tests FAIL (`unsupported_sector` returned / `AttributeError: is_valid_sector`); old passing tests still pass.

- [ ] **Step 3: Rewrite the gate in promotion.py**

In `core/portfolio/promotion.py`:

3a. Add `import re` to the imports; replace the `SUPPORTED_SECTORS` block with:

```python
# Sectors with a hand-built native graph — mirrors sector_router.NATIVE_SECTORS.
NATIVE_SECTORS: frozenset[str] = frozenset(
    {"automobile", "banking_bfsi", "it_sector", "renewable_energy"}
)
# Back-compat alias (Phase A name; portfolio_api and older tests import it).
SUPPORTED_SECTORS = NATIVE_SECTORS

# Any other well-formed sector key routes via the GENERIC sector graph
# (Compass Phase B). Format guard only — a typo'd key would silently fragment
# PredictionStore directories, so reject anything that isn't a clean
# lowercase token.
_SECTOR_RE = re.compile(r"^[a-z][a-z0-9_]{1,31}$")


def is_valid_sector(sector: str) -> bool:
    """True when `sector` is a well-formed sector key (native or generic)."""
    return bool(_SECTOR_RE.match(sector.strip().lower()))
```

3b. In `promote_symbol`, replace the `if sector not in SUPPORTED_SECTORS:` rejection block with:

```python
    if not _SECTOR_RE.match(sector):
        detail = (
            f"'{sector}' is not a valid sector key — use a lowercase token "
            f"(letters/digits/underscore, 2-32 chars), e.g. 'pharma'."
        )
        logger.info("[promotion] %s rejected: %s", symbol, detail)
        return {"status": "invalid_sector", "symbol": symbol, "detail": detail}
    graph = "native" if sector in NATIVE_SECTORS else "generic"
```

3c. Add `"graph": graph` to BOTH success returns:

```python
        return {"status": "already_managed", "symbol": symbol, "graph": graph}
```

and

```python
    return {"status": "promoted", "symbol": symbol,
            "cadence": _ORIGIN_CADENCE[origin], "graph": graph}
```

3d. Update the module docstring paragraph that says promotion "REJECTS unsupported sectors until the generic sector graph ships (Phase B)" to:

```
Phase B: the generic sector graph shipped — any well-formed sector key is
accepted; sectors outside NATIVE_SECTORS are analysed via the generic graph
(sector_router routes them). Malformed keys are rejected (invalid_sector).
```

- [ ] **Step 4: Update the two API gates**

In `services/api/routes/portfolio_api.py`:

4a. Change the promotion import line to:

```python
from core.portfolio.promotion import demote_symbol, is_valid_sector, promote_symbol
```

4b. In `add_holding`, replace the `if body.sector.strip().lower() not in SUPPORTED_SECTORS:` block with:

```python
    if not is_valid_sector(body.sector):
        raise HTTPException(
            status_code=422,
            detail=(
                f"Invalid sector key '{body.sector}' — use a lowercase token like "
                f"'pharma' or 'banking_bfsi' (letters/digits/underscore)."
            ),
        )
```

4c. In `add_watchlist`, replace the identical `SUPPORTED_SECTORS` block with the same `is_valid_sector` gate.

4d. Normalise the sector before storing in both routes: where `Holding(...)`/`WatchlistItem(...)` are constructed with `sector=body.sector`, change to `sector=body.sector.strip().lower()`, and pass the same normalised value to `promote_symbol`.

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/unit/test_portfolio_promotion.py tests/unit/test_portfolio_api.py -v`
Expected: PASS (all — including untouched Phase A tests).

- [ ] **Step 6: Commit**

```bash
git add core/portfolio/promotion.py services/api/routes/portfolio_api.py tests/unit/test_portfolio_promotion.py tests/unit/test_portfolio_api.py
git commit -m "feat(compass-b): lift 4-sector promotion restriction — generic graph accepts any sector key (Task 5)"
```

---

### Task 6: EOD market cache — parquet store + bhavcopy fetcher + daily sync job

**Files:**
- Create: `services/data/stores/eod_store.py`
- Create: `services/data/fetchers/bhavcopy.py`
- Modify: `services/scheduler/python/scheduler.py` (new Job 11: weekday 19:00 IST bhavcopy sync)
- Test: `tests/unit/test_eod_store.py`, `tests/unit/test_bhavcopy_fetcher.py`

**Interfaces:**
- Consumes: `settings.DISCOVERY_BHAVCOPY_DIR`, `DISCOVERY_HISTORY_DAYS`, `DISCOVERY_ENABLED` (Task 1); `core.intelligence.rl.nse_calendar.is_trading_day` (existing); `nse.NSE.deliveryBhavcopy` (installed package).
- Produces:
  - `EodStore(base_dir: str | None = None)` with `save_day(day: date, df: pd.DataFrame) -> Path`, `has_day(day: date) -> bool`, `latest_day() -> date | None`, `load_window(end: date, sessions: int) -> pd.DataFrame` (concatenated frame, sorted by date), `prune(keep_sessions: int) -> int`.
  - Canonical EOD columns (every consumer relies on these exact names): `symbol: str`, `series: str`, `date: str` (ISO), `prev_close/open/high/low/close: float`, `volume: float`, `traded_value_cr: float`, `delivery_qty: float`, `delivery_pct: float`.
  - `bhavcopy.fetch_day(day: date) -> pd.DataFrame | None` (canonical columns; None on failure — never raises); `bhavcopy.sync_recent(end: date | None = None, days_back: int | None = None) -> dict` (`{"synced": int, "skipped": int, "failed": [iso...]}`).
  - Scheduler method `_bhavcopy_sync_job(self) -> None`.

- [ ] **Step 1: Write the failing store test**

```python
# tests/unit/test_eod_store.py
"""Compass Phase B — per-day parquet EOD store."""
from datetime import date

import pandas as pd
import pytest

from services.data.stores.eod_store import EodStore


def _day_frame(iso: str, symbols=("AAA", "BBB")) -> pd.DataFrame:
    rows = []
    for i, s in enumerate(symbols):
        rows.append({"symbol": s, "series": "EQ", "date": iso,
                     "prev_close": 99.0 + i, "open": 100.0 + i, "high": 102.0 + i,
                     "low": 99.0 + i, "close": 101.0 + i, "volume": 1000.0 * (i + 1),
                     "traded_value_cr": 6.0 + i, "delivery_qty": 400.0,
                     "delivery_pct": 40.0 + i})
    return pd.DataFrame(rows)


@pytest.fixture
def store(tmp_path):
    return EodStore(base_dir=str(tmp_path))


def test_save_and_has_day(store):
    d = date(2026, 7, 3)
    path = store.save_day(d, _day_frame("2026-07-03"))
    assert path.name == "2026-07-03.parquet"
    assert store.has_day(d) is True
    assert store.has_day(date(2026, 7, 4)) is False
    assert store.latest_day() == d


def test_load_window_concats_and_sorts(store):
    store.save_day(date(2026, 7, 1), _day_frame("2026-07-01"))
    store.save_day(date(2026, 7, 2), _day_frame("2026-07-02"))
    store.save_day(date(2026, 7, 3), _day_frame("2026-07-03"))
    win = store.load_window(end=date(2026, 7, 3), sessions=2)
    assert sorted(win["date"].unique()) == ["2026-07-02", "2026-07-03"]
    assert set(win.columns) >= {"symbol", "series", "date", "close",
                                "volume", "traded_value_cr", "delivery_pct"}


def test_load_window_empty_store(store):
    win = store.load_window(end=date(2026, 7, 3), sessions=10)
    assert win.empty


def test_prune_keeps_newest(store):
    for d in (date(2026, 7, 1), date(2026, 7, 2), date(2026, 7, 3)):
        store.save_day(d, _day_frame(d.isoformat()))
    removed = store.prune(keep_sessions=2)
    assert removed == 1
    assert store.has_day(date(2026, 7, 1)) is False
    assert store.latest_day() == date(2026, 7, 3)
```

- [ ] **Step 2: Run store test to verify it fails**

Run: `python -m pytest tests/unit/test_eod_store.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'services.data.stores.eod_store'`

- [ ] **Step 3: Implement `services/data/stores/eod_store.py`**

```python
"""
Compass Phase B — per-day parquet EOD store (spec §8 data plan).

One parquet file per trading day under data/market_cache/bhavcopy/
(YYYY-MM-DD.parquet). Per-day files make the initial ~550-session backfill
resumable (a crashed sync just skips days already on disk) and pruning
trivial. ~2yr of NSE mainboard EOD ≈ 200MB — fits the Railway volume.

Canonical columns (all consumers depend on these exact names):
  symbol, series, date (ISO str), prev_close, open, high, low, close,
  volume, traded_value_cr, delivery_qty, delivery_pct
"""
from __future__ import annotations

import logging
import re
from datetime import date
from pathlib import Path

import pandas as pd

from core.config import settings

logger = logging.getLogger(__name__)

_DAY_FILE_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})\.parquet$")

COLUMNS: list[str] = [
    "symbol", "series", "date", "prev_close", "open", "high", "low",
    "close", "volume", "traded_value_cr", "delivery_qty", "delivery_pct",
]


class EodStore:
    def __init__(self, base_dir: str | None = None) -> None:
        self._dir = Path(base_dir or settings.DISCOVERY_BHAVCOPY_DIR)
        self._dir.mkdir(parents=True, exist_ok=True)

    def _path(self, day: date) -> Path:
        return self._dir / f"{day.isoformat()}.parquet"

    def _day_files(self) -> list[Path]:
        return sorted(
            p for p in self._dir.glob("*.parquet") if _DAY_FILE_RE.match(p.name)
        )

    def save_day(self, day: date, df: pd.DataFrame) -> Path:
        missing = [c for c in COLUMNS if c not in df.columns]
        if missing:
            raise ValueError(f"EodStore.save_day: missing columns {missing}")
        path = self._path(day)
        tmp = path.with_suffix(".tmp")
        df[COLUMNS].to_parquet(tmp, index=False)
        tmp.replace(path)
        return path

    def has_day(self, day: date) -> bool:
        return self._path(day).exists()

    def latest_day(self) -> date | None:
        files = self._day_files()
        if not files:
            return None
        return date.fromisoformat(files[-1].stem)

    def load_window(self, end: date, sessions: int) -> pd.DataFrame:
        """Concatenate the newest `sessions` day-files with date <= end."""
        files = [
            p for p in self._day_files() if date.fromisoformat(p.stem) <= end
        ][-sessions:]
        if not files:
            return pd.DataFrame(columns=COLUMNS)
        frames = []
        for p in files:
            try:
                frames.append(pd.read_parquet(p))
            except Exception as exc:                      # corrupt file: skip, log
                logger.warning("[eod_store] unreadable %s: %s", p.name, exc)
        if not frames:
            return pd.DataFrame(columns=COLUMNS)
        return pd.concat(frames, ignore_index=True).sort_values(
            ["date", "symbol"], ignore_index=True
        )

    def prune(self, keep_sessions: int) -> int:
        files = self._day_files()
        stale = files[:-keep_sessions] if keep_sessions > 0 else files
        for p in stale:
            try:
                p.unlink()
            except OSError as exc:
                logger.warning("[eod_store] prune failed for %s: %s", p.name, exc)
        return len(stale)
```

- [ ] **Step 4: Run store test to verify it passes**

Run: `python -m pytest tests/unit/test_eod_store.py -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Write the failing fetcher test**

```python
# tests/unit/test_bhavcopy_fetcher.py
"""Compass Phase B — delivery-bhavcopy fetcher -> canonical EOD frame."""
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

import services.data.fetchers.bhavcopy as bc
from services.data.stores.eod_store import EodStore

# sec_bhavdata_full CSV as NSE ships it: padded values, ' -' for missing.
_CSV = (
    "SYMBOL, SERIES, DATE1, PREV_CLOSE, OPEN_PRICE, HIGH_PRICE, LOW_PRICE,"
    " LAST_PRICE, CLOSE_PRICE, AVG_PRICE, TTL_TRD_QNTY, TURNOVER_LACS,"
    " NO_OF_TRADES, DELIV_QTY, DELIV_PER\n"
    "AAA, EQ, 03-Jul-2026, 99.0, 100.0, 102.0, 99.0, 101.0, 101.0, 100.5,"
    " 10000, 600.00, 500, 4000, 40.00\n"
    "BBB, BE, 03-Jul-2026, 50.0, 50.0, 52.0, 49.0, 51.0, 51.0, 50.5,"
    " 2000, 101.00, 80, -, -\n"
)


@pytest.fixture
def fake_nse(tmp_path, monkeypatch):
    csv_path = tmp_path / "sec_bhavdata_full_03072026.csv"
    csv_path.write_text(_CSV, encoding="utf-8")

    class _FakeNSE:
        def deliveryBhavcopy(self, dt, folder=None):
            return csv_path
        def exit(self):
            pass

    monkeypatch.setattr(bc, "_make_nse_client", lambda: _FakeNSE())
    return csv_path


def test_fetch_day_normalises_columns(fake_nse):
    df = bc.fetch_day(date(2026, 7, 3))
    assert df is not None
    aaa = df[df["symbol"] == "AAA"].iloc[0]
    assert aaa["series"] == "EQ"
    assert aaa["date"] == "2026-07-03"
    assert aaa["close"] == 101.0
    assert aaa["traded_value_cr"] == pytest.approx(6.0)    # TURNOVER_LACS 600.00 lakh = ₹6.0 cr
    assert aaa["delivery_pct"] == 40.0
    # ' -' missing markers parse to NaN, not crash
    bbb = df[df["symbol"] == "BBB"].iloc[0]
    assert pd.isna(bbb["delivery_pct"])


def test_fetch_day_failure_returns_none(monkeypatch):
    class _Boom:
        def deliveryBhavcopy(self, dt, folder=None):
            raise RuntimeError("403")
        def exit(self):
            pass
    monkeypatch.setattr(bc, "_make_nse_client", lambda: _Boom())
    assert bc.fetch_day(date(2026, 7, 3)) is None


def test_sync_recent_skips_existing_and_records_failures(tmp_path, monkeypatch, fake_nse):
    store = EodStore(base_dir=str(tmp_path / "eod"))
    monkeypatch.setattr(bc, "EodStore", lambda: store)
    monkeypatch.setattr(bc, "is_trading_day", lambda d: d.weekday() < 5)
    monkeypatch.setattr(bc.time, "sleep", lambda s: None)

    result = bc.sync_recent(end=date(2026, 7, 3), days_back=3)  # Wed 1st..Fri 3rd
    assert result["synced"] == 3 and result["skipped"] == 0

    result2 = bc.sync_recent(end=date(2026, 7, 3), days_back=3)
    assert result2["synced"] == 0 and result2["skipped"] == 3
```

- [ ] **Step 6: Run fetcher test to verify it fails**

Run: `python -m pytest tests/unit/test_bhavcopy_fetcher.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'services.data.fetchers.bhavcopy'`

- [ ] **Step 7: Implement `services/data/fetchers/bhavcopy.py`**

```python
"""
Compass Phase B — NSE delivery-bhavcopy fetcher (spec §8: bhavcopy ARCHIVES
are the reliable backbone; delivery % is included in sec_bhavdata_full).

fetch_day(day)    -> canonical EOD DataFrame (EodStore.COLUMNS) | None
sync_recent(...)  -> top-up the EodStore for recent trading days; resumable
                     (skips days already stored) and non-fatal per day.

House pattern mirrors corporate_events.py: isolated _make_nse_client factory
(tests monkeypatch it), never raises, degraded days are reported not thrown.
"""
from __future__ import annotations

import logging
import pathlib
import tempfile
import time
from datetime import date, datetime, timedelta

import pandas as pd

from core.config import settings
from core.intelligence.rl.nse_calendar import is_trading_day
from services.data.stores.eod_store import COLUMNS, EodStore

logger = logging.getLogger(__name__)

_SLEEP_BETWEEN_CALLS = 0.5   # same safe margin as nse_announcements.py

# sec_bhavdata_full CSV column -> canonical column
_COLMAP = {
    "SYMBOL": "symbol",
    "SERIES": "series",
    "DATE1": "date",
    "PREV_CLOSE": "prev_close",
    "OPEN_PRICE": "open",
    "HIGH_PRICE": "high",
    "LOW_PRICE": "low",
    "CLOSE_PRICE": "close",
    "TTL_TRD_QNTY": "volume",
    "TURNOVER_LACS": "traded_value_cr",   # ÷100 below (lakh -> crore)
    "DELIV_QTY": "delivery_qty",
    "DELIV_PER": "delivery_pct",
}
_NUMERIC = ["prev_close", "open", "high", "low", "close", "volume",
            "traded_value_cr", "delivery_qty", "delivery_pct"]


def _make_nse_client():
    """Isolated factory so tests can monkeypatch it."""
    from nse import NSE
    return NSE(download_folder=pathlib.Path(tempfile.mkdtemp()))


def fetch_day(day: date) -> pd.DataFrame | None:
    """Download + normalise one day's delivery bhavcopy. None on any failure."""
    try:
        nse = _make_nse_client()
    except Exception as exc:
        logger.warning("[bhavcopy] NSE client unavailable: %s", exc)
        return None
    try:
        path = nse.deliveryBhavcopy(
            datetime(day.year, day.month, day.day),
            folder=pathlib.Path(tempfile.mkdtemp()),
        )
        raw = pd.read_csv(path, skipinitialspace=True)
        raw.columns = [c.strip() for c in raw.columns]
        df = raw[list(_COLMAP)].rename(columns=_COLMAP)
        df["symbol"] = df["symbol"].astype(str).str.strip().str.upper()
        df["series"] = df["series"].astype(str).str.strip().str.upper()
        for col in _NUMERIC:
            df[col] = pd.to_numeric(
                df[col].astype(str).str.strip().str.replace(",", ""),
                errors="coerce",
            )
        df["traded_value_cr"] = df["traded_value_cr"] / 100.0   # lakh -> crore
        df["date"] = day.isoformat()
        return df[COLUMNS]
    except Exception as exc:
        logger.warning("[bhavcopy] fetch failed for %s: %s", day, exc)
        return None
    finally:
        try:
            nse.exit()
        except Exception:
            pass


def sync_recent(end: date | None = None, days_back: int | None = None) -> dict:
    """Fetch any missing trading days in (end - days_back, end] into the store.

    Resumable: days already stored are skipped. Failed days are recorded and
    retried on the next sync (the daily job passes days_back=7 so transient
    NSE outages self-heal). Prunes beyond DISCOVERY_HISTORY_DAYS at the end.
    """
    end = end or date.today()
    days_back = days_back or settings.DISCOVERY_HISTORY_DAYS
    store = EodStore()

    synced = skipped = 0
    failed: list[str] = []
    day = end
    scanned = 0
    while scanned < days_back:
        if is_trading_day(day):
            if store.has_day(day):
                skipped += 1
            else:
                df = fetch_day(day)
                if df is not None and not df.empty:
                    store.save_day(day, df)
                    synced += 1
                else:
                    failed.append(day.isoformat())
                time.sleep(_SLEEP_BETWEEN_CALLS)
        day -= timedelta(days=1)
        scanned += 1

    pruned = store.prune(keep_sessions=settings.DISCOVERY_HISTORY_DAYS)
    result = {"synced": synced, "skipped": skipped, "failed": failed, "pruned": pruned}
    logger.info("[bhavcopy] sync_recent end=%s days_back=%d -> %s", end, days_back, result)
    return result
```

**Note for the implementer:** `sync_recent`'s `scanned` counts calendar days (matching the test: `days_back=3` ending Fri covers Wed/Thu/Fri). The initial history backfill therefore runs with `days_back≈800` calendar days to land ~550 sessions — that is a one-time manual/ops step (`python -c "from services.data.fetchers.bhavcopy import sync_recent; print(sync_recent(days_back=800))"`), NOT part of any scheduled job. Until backfill depth reaches 252 sessions the momentum signal reports dark (Task 9 handles that gracefully).

- [ ] **Step 8: Run fetcher test to verify it passes**

Run: `python -m pytest tests/unit/test_bhavcopy_fetcher.py -v`
Expected: PASS (3 tests)

- [ ] **Step 9: Add scheduler Job 11 (daily bhavcopy sync)**

In `services/scheduler/python/scheduler.py` `_build_scheduler()`, after the Job 10 block:

```python
        # ── Job 11: Daily bhavcopy sync (19:00 IST weekdays — EOD data settles ~18:30) ──
        if getattr(settings, "DISCOVERY_ENABLED", False):
            scheduler.add_job(
                func=self._bhavcopy_sync_job,
                trigger=CronTrigger(
                    day_of_week="mon-fri", hour=19, minute=0, timezone="Asia/Kolkata",
                ),
                id="bhavcopy_daily_sync",
                name="Daily bhavcopy EOD cache sync",
                misfire_grace_time=3600,
                coalesce=True,
                replace_existing=True,
            )
            logger.info("[Scheduler] Bhavcopy sync job: weekdays at 7:00 pm IST")
        else:
            logger.info("[Scheduler] Bhavcopy sync job disabled (DISCOVERY_ENABLED=false)")
```

And the job implementation (alongside the other `_*_job` methods):

```python
    def _bhavcopy_sync_job(self) -> None:
        """Top up the EOD market cache with the last week's trading days.
        days_back=7 self-heals transient NSE outages. Non-fatal by construction."""
        from services.data.fetchers.bhavcopy import sync_recent

        _job_banner("Daily Bhavcopy Sync")
        try:
            result = sync_recent(days_back=7)
            logger.info(
                "[Scheduler] Bhavcopy sync — synced=%d skipped=%d failed=%s pruned=%d",
                result["synced"], result["skipped"], result["failed"], result["pruned"],
            )
        except Exception as exc:
            logger.error("[Scheduler] Bhavcopy sync FAILED: %s", exc, exc_info=True)
        _job_banner("Daily Bhavcopy Sync", done=True)
```

- [ ] **Step 10: Run the touched suites + commit**

Run: `python -m pytest tests/unit/test_eod_store.py tests/unit/test_bhavcopy_fetcher.py tests/unit/intelligence/rl/test_sector_router_generic.py -v`
Expected: PASS

```bash
git add services/data/stores/eod_store.py services/data/fetchers/bhavcopy.py services/scheduler/python/scheduler.py tests/unit/test_eod_store.py tests/unit/test_bhavcopy_fetcher.py
git commit -m "feat(compass-b): EOD parquet market cache + delivery-bhavcopy fetcher + daily sync job (Task 6)"
```

---

### Task 7: Bulk/block deals + surveillance/meta fetchers (guard data)

**Files:**
- Create: `services/data/fetchers/bulk_block.py`
- Create: `services/data/fetchers/surveillance.py`
- Test: `tests/unit/test_discovery_fetchers.py`

**Interfaces:**
- Consumes: `nse.NSE.bulkdeals(option_type, fromdate, todate)`, `nse.NSE.equityMetaInfo(symbol)`; `_yf_info`-style yfinance lookup for float mcap (self-contained copy — do NOT import from base_orchestrator).
- Produces:
  - `bulk_block.refresh_bulk_block(weeks: int = 4, cache_path: str | None = None) -> dict` — cache shape `{"fetched_at": iso, "degraded": bool, "deals": [ {symbol, side ("BUY"|"SELL"), qty: float, kind ("bulk"|"block"), date: iso}, ... ]}` written atomically to `data/market_cache/bulk_block.json`.
  - `bulk_block.load_bulk_block(cache_path: str | None = None) -> dict` (same shape; empty skeleton when absent/unreadable).
  - `bulk_block.net_accumulation(cache: dict) -> dict[str, float]` — per-symbol net BUY qty (buys − sells; negative values floored at 0.0).
  - `surveillance.get_symbol_meta(symbol: str) -> dict` — `{"surveillance": str | None, "suspended": bool, "industry": str | None, "degraded": bool}`, backed by a per-day JSON cache `data/market_cache/symbol_meta.json` (key `{symbol}|{YYYY-MM-DD}`).
  - `surveillance.float_mcap_cr(symbol: str) -> float | None` — `floatShares × currentPrice / 1e7` (₹ crore); None when unknown.

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_discovery_fetchers.py
"""Compass Phase B — bulk/block + surveillance guard-data fetchers."""
from datetime import date

import pytest

import services.data.fetchers.bulk_block as bb
import services.data.fetchers.surveillance as surv


class _FakeNSE:
    def __init__(self, bulk=None, block=None, meta=None, boom=False):
        self._bulk, self._block = bulk or [], block or []
        self._meta, self._boom = meta or {}, boom
    def bulkdeals(self, option_type, fromdate, todate):
        if self._boom:
            raise RuntimeError("403")
        return self._bulk if option_type == "bulk_deals" else self._block
    def equityMetaInfo(self, symbol):
        if self._boom:
            raise RuntimeError("403")
        return self._meta
    def exit(self):
        pass


def test_refresh_and_net_accumulation(tmp_path, monkeypatch):
    deals = [
        {"BD_SYMBOL": "AAA", "BD_BUY_SELL": "BUY",  "BD_QTY_TRD": "10000",
         "BD_DT_DATE": "01-Jul-2026"},
        {"BD_SYMBOL": "AAA", "BD_BUY_SELL": "SELL", "BD_QTY_TRD": "2000",
         "BD_DT_DATE": "02-Jul-2026"},
        {"BD_SYMBOL": "BBB", "BD_BUY_SELL": "SELL", "BD_QTY_TRD": "5000",
         "BD_DT_DATE": "02-Jul-2026"},
    ]
    monkeypatch.setattr(bb, "_make_nse_client", lambda: _FakeNSE(bulk=deals))
    cache = bb.refresh_bulk_block(weeks=4, cache_path=str(tmp_path / "bb.json"))
    assert cache["degraded"] is False
    assert len(cache["deals"]) == 3

    net = bb.net_accumulation(cache)
    assert net["AAA"] == 8000.0
    assert net["BBB"] == 0.0            # net seller floored at 0


def test_refresh_degrades_and_keeps_stale(tmp_path, monkeypatch):
    path = str(tmp_path / "bb.json")
    monkeypatch.setattr(bb, "_make_nse_client", lambda: _FakeNSE(
        bulk=[{"BD_SYMBOL": "AAA", "BD_BUY_SELL": "BUY", "BD_QTY_TRD": "100",
               "BD_DT_DATE": "01-Jul-2026"}]))
    bb.refresh_bulk_block(weeks=4, cache_path=path)

    monkeypatch.setattr(bb, "_make_nse_client", lambda: _FakeNSE(boom=True))
    cache = bb.refresh_bulk_block(weeks=4, cache_path=path)
    assert cache["degraded"] is True
    assert len(cache["deals"]) == 1     # stale deals kept


def test_symbol_meta_surveillance(tmp_path, monkeypatch):
    meta = {"info": {"industry": "Pharmaceuticals"},
            "metadata": {"status": "Listed"},
            "surveillance": {"surv": "ASM", "desc": "Additional Surveillance Measure"}}
    monkeypatch.setattr(surv, "_make_nse_client", lambda: _FakeNSE(meta=meta))
    monkeypatch.setattr(surv, "_CACHE_PATH_DEFAULT", str(tmp_path / "meta.json"))
    m = surv.get_symbol_meta("SUNPHARMA")
    assert m["surveillance"] == "ASM"
    assert m["suspended"] is False
    assert m["industry"] == "Pharmaceuticals"
    assert m["degraded"] is False


def test_symbol_meta_degraded(tmp_path, monkeypatch):
    monkeypatch.setattr(surv, "_make_nse_client", lambda: _FakeNSE(boom=True))
    monkeypatch.setattr(surv, "_CACHE_PATH_DEFAULT", str(tmp_path / "meta.json"))
    m = surv.get_symbol_meta("XXX")
    assert m["degraded"] is True
    assert m["surveillance"] is None


def test_float_mcap_cr(monkeypatch):
    monkeypatch.setattr(surv, "_yf_info",
                        lambda t: {"floatShares": 100_000_000, "currentPrice": 250.0})
    assert surv.float_mcap_cr("AAA") == pytest.approx(2500.0)
    monkeypatch.setattr(surv, "_yf_info", lambda t: {})
    assert surv.float_mcap_cr("AAA") is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/unit/test_discovery_fetchers.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'services.data.fetchers.bulk_block'`

- [ ] **Step 3: Implement `services/data/fetchers/bulk_block.py`**

```python
"""
Compass Phase B — NSE bulk/block deals over a trailing window (spec §6.1:
"repeated same-side bulk/block deals" = institutional accumulation).

Degraded mode (spec §8): on fetch failure the previous cache is kept and
flagged degraded — the screen treats the signal as live-but-stale, and the
weekly job logs it.
"""
from __future__ import annotations

import json
import logging
import pathlib
import tempfile
from datetime import date, datetime, timedelta, timezone

logger = logging.getLogger(__name__)

_DEFAULT_CACHE = "data/market_cache/bulk_block.json"

# NSE bulk/block rows use several key spellings across report vintages.
_SYMBOL_KEYS = ("BD_SYMBOL", "symbol", "SYMBOL")
_SIDE_KEYS = ("BD_BUY_SELL", "buySell", "BUY_SELL")
_QTY_KEYS = ("BD_QTY_TRD", "qty", "QTY_TRADED", "noOfShareTraded")
_DATE_KEYS = ("BD_DT_DATE", "date", "DEAL_DATE", "mDate")

_NSE_DATE_FMTS = ("%d-%b-%Y", "%d-%m-%Y", "%Y-%m-%d")


def _make_nse_client():
    from nse import NSE
    return NSE(download_folder=pathlib.Path(tempfile.mkdtemp()))


def _first(item: dict, keys: tuple[str, ...]) -> str:
    for k in keys:
        v = item.get(k)
        if v is not None and str(v).strip():
            return str(v).strip()
    return ""


def _parse_date(raw: str) -> str:
    for fmt in _NSE_DATE_FMTS:
        try:
            return datetime.strptime(raw, fmt).date().isoformat()
        except ValueError:
            continue
    return ""


def _normalise(rows: list[dict], kind: str) -> list[dict]:
    out: list[dict] = []
    for item in rows or []:
        if not isinstance(item, dict):
            continue
        symbol = _first(item, _SYMBOL_KEYS).upper()
        side = _first(item, _SIDE_KEYS).upper()
        qty_raw = _first(item, _QTY_KEYS).replace(",", "")
        deal_date = _parse_date(_first(item, _DATE_KEYS))
        try:
            qty = float(qty_raw)
        except ValueError:
            continue
        if not symbol or side not in ("BUY", "SELL"):
            continue
        out.append({"symbol": symbol, "side": side, "qty": qty,
                    "kind": kind, "date": deal_date})
    return out


def load_bulk_block(cache_path: str | None = None) -> dict:
    path = pathlib.Path(cache_path or _DEFAULT_CACHE)
    if not path.exists():
        return {"fetched_at": "", "degraded": True, "deals": []}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.error("[bulk_block] cache unreadable %s: %s", path, exc)
        return {"fetched_at": "", "degraded": True, "deals": []}


def refresh_bulk_block(weeks: int = 4, cache_path: str | None = None) -> dict:
    """Fetch trailing `weeks` of bulk + block deals. Never raises."""
    path = pathlib.Path(cache_path or _DEFAULT_CACHE)
    previous = load_bulk_block(cache_path=str(path))

    todate = datetime.now()
    fromdate = todate - timedelta(weeks=weeks)
    deals: list[dict] = []
    degraded = False
    try:
        nse = _make_nse_client()
        try:
            deals += _normalise(nse.bulkdeals("bulk_deals", fromdate, todate), "bulk")
            deals += _normalise(nse.bulkdeals("block_deals", fromdate, todate), "block")
        finally:
            try:
                nse.exit()
            except Exception:
                pass
    except Exception as exc:
        logger.warning("[bulk_block] fetch failed — keeping stale cache: %s", exc)
        degraded = True
        deals = list(previous.get("deals", []))

    result = {
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "degraded": degraded,
        "deals": deals,
    }
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(result, indent=2), encoding="utf-8")
        tmp.replace(path)
    except OSError as exc:
        logger.error("[bulk_block] cache write failed %s: %s", path, exc)
    return result


def net_accumulation(cache: dict) -> dict[str, float]:
    """Per-symbol net BUY quantity over the cached window, floored at 0.
    (Spec §6.1 wants same-side ACCUMULATION — net sellers are simply 0.)"""
    net: dict[str, float] = {}
    for d in cache.get("deals", []):
        sign = 1.0 if d.get("side") == "BUY" else -1.0
        net[d["symbol"]] = net.get(d["symbol"], 0.0) + sign * float(d.get("qty", 0.0))
    return {s: max(0.0, q) for s, q in net.items()}
```

- [ ] **Step 4: Implement `services/data/fetchers/surveillance.py`**

```python
"""
Compass Phase B — per-symbol surveillance/meta + float-mcap guard data
(spec §6.1 threshold gates: ASM/GSM, suspension, free-float mcap floor).

Called only for the post-rank SHORTLIST (~80 symbols), never the full
universe — per-symbol NSE calls at 0.5s spacing stay under a minute.
Per-day JSON cache so a re-run within the day is free.
"""
from __future__ import annotations

import json
import logging
import pathlib
import tempfile
import time
from datetime import date

logger = logging.getLogger(__name__)

_CACHE_PATH_DEFAULT = "data/market_cache/symbol_meta.json"
_SLEEP_BETWEEN_CALLS = 0.5


def _make_nse_client():
    from nse import NSE
    return NSE(download_folder=pathlib.Path(tempfile.mkdtemp()))


def _yf_info(ticker: str) -> dict:
    """yfinance .info with the repo's NSE suffix convention. {} on failure."""
    try:
        import yfinance as yf
        from core.config import settings
        suffix = settings.YFINANCE_SUFFIX
        yf_ticker = settings.YF_SYMBOL_OVERRIDES.get(ticker.upper()) or (
            ticker if ticker.endswith(suffix) else f"{ticker}{suffix}"
        )
        return yf.Ticker(yf_ticker).info or {}
    except Exception as exc:
        logger.debug("[surveillance] yfinance info failed for %s: %s", ticker, exc)
        return {}


def _load_cache(path: pathlib.Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_cache(path: pathlib.Path, cache: dict) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(cache, indent=2), encoding="utf-8")
        tmp.replace(path)
    except OSError as exc:
        logger.error("[surveillance] cache write failed %s: %s", path, exc)


def get_symbol_meta(symbol: str) -> dict:
    """NSE meta for one symbol: surveillance flag, suspension, industry.
    Cached per (symbol, day). Never raises — degraded=True on failure."""
    symbol = symbol.strip().upper()
    path = pathlib.Path(_CACHE_PATH_DEFAULT)
    cache = _load_cache(path)
    key = f"{symbol}|{date.today().isoformat()}"
    if key in cache:
        return cache[key]

    result = {"surveillance": None, "suspended": False, "industry": None,
              "degraded": False}
    try:
        nse = _make_nse_client()
        try:
            meta = nse.equityMetaInfo(symbol) or {}
        finally:
            try:
                nse.exit()
            except Exception:
                pass
        surv_block = meta.get("surveillance") or {}
        surv = surv_block.get("surv") if isinstance(surv_block, dict) else None
        result["surveillance"] = (str(surv).strip() or None) if surv else None
        status = str((meta.get("metadata") or {}).get("status", "")).lower()
        result["suspended"] = "suspend" in status or "delist" in status
        info = meta.get("info") or {}
        industry = info.get("industry") or meta.get("industry")
        result["industry"] = str(industry).strip() if industry else None
    except Exception as exc:
        logger.warning("[surveillance] meta fetch failed for %s: %s", symbol, exc)
        result["degraded"] = True

    cache[key] = result
    _save_cache(path, cache)
    time.sleep(_SLEEP_BETWEEN_CALLS)
    return result


def float_mcap_cr(symbol: str) -> float | None:
    """Free-float market cap in ₹ crore via yfinance; None when unknown."""
    info = _yf_info(symbol)
    shares = info.get("floatShares")
    price = info.get("currentPrice") or info.get("regularMarketPrice") \
        or info.get("previousClose")
    if not shares or not price:
        return None
    return float(shares) * float(price) / 1e7
```

- [ ] **Step 5: Run test to verify it passes**

Run: `python -m pytest tests/unit/test_discovery_fetchers.py -v`
Expected: PASS (5 tests)

- [ ] **Step 6: Commit**

```bash
git add services/data/fetchers/bulk_block.py services/data/fetchers/surveillance.py tests/unit/test_discovery_fetchers.py
git commit -m "feat(compass-b): bulk/block deals + surveillance/float-mcap guard fetchers (Task 7)"
```

---

### Task 8: Discovery schemas + universe + guards

**Files:**
- Create: `src/backend/shared/schemas/discovery.py`
- Create: `core/discovery/__init__.py` (empty)
- Create: `core/discovery/universe.py`
- Create: `core/discovery/guards.py`
- Test: `tests/unit/test_discovery_universe_guards.py`

**Interfaces:**
- Consumes: EOD canonical columns (Task 6); `surveillance.get_symbol_meta` / `float_mcap_cr` (Task 7); `settings.DISCOVERY_*` (Task 1).
- Produces:
  - Schemas: `DiscoveryCandidate(symbol, close, composite, signal_ranks: dict[str, float], flags: list[str])`; `ScreenResult(screen_date, universe_size, shortlist_size, candidates: list[DiscoveryCandidate], rejected: dict[str, list[str]], dark_signals: list[str], degraded_checks: list[str])`; `DeepDiveResult(symbol, sector, graph, conviction, verdict, thesis, entry_low, entry_high, invalidation_level, close, composite, dive_date)`; `ShelfIdea(symbol, sector, graph, added, conviction, verdict, thesis, entry_low, entry_high, invalidation_level, close_at_add, status, paper_cycle_id, last_paper_review, source_screen_date)`; `Shelf(ideas: list[ShelfIdea], updated_at: str)`.
  - `universe.build_universe(window: pd.DataFrame) -> list[str]` — symbols whose LATEST session is series EQ with close ≥ `DISCOVERY_MIN_PRICE`.
  - `guards.apply_guards(shortlist: list[str], window: pd.DataFrame) -> tuple[list[str], dict[str, list[str]], list[str]]` — `(passed_in_input_order, rejected {symbol: [gate names]}, degraded_checks)`.
  - Gate names (exact strings): `"t2t_series"`, `"low_liquidity"`, `"below_min_price"`, `"upper_circuit_streak"`, `"surveillance_asm_gsm"`, `"suspended"`, `"low_float_mcap"`. Flags: `"float_unverified"` recorded via degraded, `"promoter_pledge"` always in `degraded_checks` (dark guard v1).

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_discovery_universe_guards.py
"""Compass Phase B — universe construction + threshold gates (spec §6.1/§9)."""
from datetime import date, timedelta

import pandas as pd
import pytest

from core.discovery.guards import apply_guards
from core.discovery.universe import build_universe


def _window(rows: list[dict]) -> pd.DataFrame:
    return pd.DataFrame(rows)


def _sessions(symbol, n, *, close=100.0, series="EQ", tv=6.0, uc_tail=0,
              start=date(2026, 4, 1)):
    """n sessions; the last uc_tail sessions are upper-circuit days
    (close == high, +10% daily)."""
    rows, px, d = [], close, start
    for i in range(n):
        is_uc = i >= n - uc_tail
        prev = px
        px = px * 1.10 if is_uc else px
        rows.append({"symbol": symbol, "series": series, "date": d.isoformat(),
                     "prev_close": prev, "open": prev, "high": px if is_uc else px * 1.01,
                     "low": prev * 0.99, "close": px, "volume": 10000.0,
                     "traded_value_cr": tv, "delivery_qty": 4000.0,
                     "delivery_pct": 40.0})
        d += timedelta(days=1)
    return rows


def test_build_universe_filters_series_and_price():
    win = _window(
        _sessions("GOODCO", 3)
        + _sessions("T2TCO", 3, series="BE")
        + _sessions("PENNY", 3, close=8.0)
    )
    assert build_universe(win) == ["GOODCO"]


def test_guards_liquidity_and_circuit(monkeypatch):
    import core.discovery.guards as g
    monkeypatch.setattr(g, "get_symbol_meta",
                        lambda s: {"surveillance": None, "suspended": False,
                                   "industry": "X", "degraded": False})
    monkeypatch.setattr(g, "float_mcap_cr", lambda s: 2000.0)

    win = _window(
        _sessions("LIQCO", 70)
        + _sessions("THINCO", 70, tv=0.5)          # ₹0.5 cr median < ₹5 cr floor
        + _sessions("PUMPCO", 70, uc_tail=5)       # 5 straight UC days > max 3
    )
    passed, rejected, degraded = apply_guards(["LIQCO", "THINCO", "PUMPCO"], win)
    assert passed == ["LIQCO"]
    assert "low_liquidity" in rejected["THINCO"]
    assert "upper_circuit_streak" in rejected["PUMPCO"]
    assert "promoter_pledge" in degraded            # dark guard always reported


def test_guards_surveillance_and_float(monkeypatch):
    import core.discovery.guards as g
    metas = {
        "ASMCO":  {"surveillance": "ASM ST1", "suspended": False, "industry": None, "degraded": False},
        "SUSPCO": {"surveillance": None, "suspended": True, "industry": None, "degraded": False},
        "TINYCO": {"surveillance": None, "suspended": False, "industry": None, "degraded": False},
        "DARKCO": {"surveillance": None, "suspended": False, "industry": None, "degraded": True},
    }
    monkeypatch.setattr(g, "get_symbol_meta", lambda s: metas[s])
    monkeypatch.setattr(g, "float_mcap_cr",
                        lambda s: {"ASMCO": 900.0, "SUSPCO": 900.0,
                                   "TINYCO": 100.0, "DARKCO": None}[s])

    win = _window(sum((_sessions(s, 70) for s in metas), []))
    passed, rejected, degraded = apply_guards(list(metas), win)
    assert "surveillance_asm_gsm" in rejected["ASMCO"]
    assert "suspended" in rejected["SUSPCO"]
    assert "low_float_mcap" in rejected["TINYCO"]
    assert "DARKCO" in passed                       # unverifiable float -> keep, degrade
    assert "float_mcap:DARKCO" in degraded
    assert "surveillance:DARKCO" in degraded
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/unit/test_discovery_universe_guards.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'core.discovery'`

- [ ] **Step 3: Implement the schemas**

`src/backend/shared/schemas/discovery.py`:

```python
"""
Compass Phase B — Discovery Engine schemas (spec §6).

Everything the funnel persists: weekly ScreenResult (quant stage), DeepDiveResult
(LLM stage) and the Discovery Shelf. All output copy is research/analysis,
never "advice"; every idea carries an invalidation_level (spec §9.4).
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class DiscoveryCandidate(BaseModel):
    """One guard-passed symbol from the weekly quant screen."""
    symbol: str
    close: float
    composite: float                       # weighted percentile-rank blend, 0-1
    signal_ranks: dict[str, float] = Field(default_factory=dict)
    flags: list[str] = Field(default_factory=list)


class ScreenResult(BaseModel):
    """Stage-1 output: ~2000 universe -> ranked, guarded candidates."""
    screen_date: str                       # ISO
    universe_size: int
    shortlist_size: int
    candidates: list[DiscoveryCandidate] = Field(default_factory=list)
    rejected: dict[str, list[str]] = Field(default_factory=dict)   # symbol -> gates
    dark_signals: list[str] = Field(default_factory=list)
    degraded_checks: list[str] = Field(default_factory=list)


class DeepDiveResult(BaseModel):
    """Stage-3 output: unified-analyst one-call conviction on a candidate."""
    symbol: str
    sector: str
    graph: Literal["native", "generic"]
    conviction: float                      # FinalReport.final_score, 0-1
    verdict: str
    thesis: str
    entry_low: float
    entry_high: float
    invalidation_level: float              # "thesis dead below X" (spec §9.4)
    close: float
    composite: float
    dive_date: str                         # ISO


class ShelfIdea(BaseModel):
    symbol: str
    sector: str
    graph: Literal["native", "generic"] = "generic"
    added: str                             # ISO date
    conviction: float
    verdict: str = ""
    thesis: str = ""
    entry_low: float = 0.0
    entry_high: float = 0.0
    invalidation_level: float = 0.0
    close_at_add: float = 0.0
    status: Literal["active", "promoted", "dropped"] = "active"
    paper_cycle_id: str = ""
    last_paper_review: str = ""            # ISO date of last paper review
    source_screen_date: str = ""


class Shelf(BaseModel):
    ideas: list[ShelfIdea] = Field(default_factory=list)
    updated_at: str = ""
```

- [ ] **Step 4: Implement `core/discovery/universe.py`**

```python
"""
Compass Phase B — universe construction (spec §6.1 gates that are free
straight from the bhavcopy: mainboard EQ series only, no penny stocks).
"""
from __future__ import annotations

import logging

import pandas as pd

from core.config import settings

logger = logging.getLogger(__name__)


def build_universe(window: pd.DataFrame) -> list[str]:
    """Symbols whose LATEST session is series EQ with close >= min_price.

    BE/BZ (T2T) and SME series never enter; price floor kills the penny tail.
    Returns a sorted list. Empty input -> empty list (screen degrades upstream).
    """
    if window.empty:
        return []
    latest_date = window["date"].max()
    latest = window[window["date"] == latest_date]
    ok = latest[
        (latest["series"] == "EQ")
        & (latest["close"] >= settings.DISCOVERY_MIN_PRICE)
    ]
    symbols = sorted(ok["symbol"].unique().tolist())
    logger.info("[discovery.universe] %s: %d symbols (of %d listed rows)",
                latest_date, len(symbols), len(latest))
    return symbols
```

- [ ] **Step 5: Implement `core/discovery/guards.py`**

```python
"""
Compass Phase B — threshold gates on the post-rank shortlist (spec §6.1/§9.1).

Bhavcopy-derived gates (liquidity, series, price, circuit streaks) run from
the EOD window — free for any number of symbols. Per-symbol gates
(surveillance/suspension via NSE meta, float mcap via yfinance) run only on
the shortlist. A gate whose data source is unavailable DEGRADES (symbol kept,
check recorded in degraded_checks) rather than silently passing or failing —
spec §8: "the brief says which signals are dark".

Promoter-pledge (< DISCOVERY_MAX_PLEDGE_PCT) has no free data source yet and
ships DARK: always reported in degraded_checks, never evaluated (v1).
"""
from __future__ import annotations

import logging

import pandas as pd

from core.config import settings
from services.data.fetchers.surveillance import float_mcap_cr, get_symbol_meta

logger = logging.getLogger(__name__)


def _upper_circuit_streak(sym_win: pd.DataFrame) -> int:
    """Trailing consecutive sessions that look like upper-circuit days:
    close == high AND daily gain >= 9.5% (10%/5% bands land under this
    with float noise; a 3+ streak is the operator pattern we exclude)."""
    streak = 0
    for _, row in sym_win.sort_values("date").iloc[::-1].iterrows():
        prev = row["prev_close"]
        if prev and prev > 0:
            gain = (row["close"] - prev) / prev * 100.0
        else:
            gain = 0.0
        if row["close"] >= row["high"] * 0.999 and gain >= 9.5:
            streak += 1
        else:
            break
    return streak


def apply_guards(
    shortlist: list[str], window: pd.DataFrame
) -> tuple[list[str], dict[str, list[str]], list[str]]:
    """Returns (passed_in_input_order, rejected {sym: [gates]}, degraded_checks)."""
    passed: list[str] = []
    rejected: dict[str, list[str]] = {}
    degraded: list[str] = ["promoter_pledge"]     # dark guard, v1 (spec §6.1)

    by_symbol = {s: g for s, g in window.groupby("symbol")} if not window.empty else {}

    for sym in shortlist:
        gates: list[str] = []
        sym_win = by_symbol.get(sym)
        if sym_win is None or sym_win.empty:
            rejected[sym] = ["no_eod_history"]
            continue
        sym_win = sym_win.sort_values("date")
        latest = sym_win.iloc[-1]

        if latest["series"] in ("BE", "BZ"):
            gates.append("t2t_series")
        if latest["close"] < settings.DISCOVERY_MIN_PRICE:
            gates.append("below_min_price")

        median_tv = sym_win.tail(60)["traded_value_cr"].median()
        if pd.isna(median_tv) or median_tv < settings.DISCOVERY_LIQUIDITY_FLOOR_CR:
            gates.append("low_liquidity")

        if _upper_circuit_streak(sym_win.tail(20)) > settings.DISCOVERY_CIRCUIT_STREAK_MAX:
            gates.append("upper_circuit_streak")

        meta = get_symbol_meta(sym)
        if meta["degraded"]:
            degraded.append(f"surveillance:{sym}")
        else:
            surv = (meta["surveillance"] or "").upper()
            if "ASM" in surv or "GSM" in surv:
                gates.append("surveillance_asm_gsm")
            if meta["suspended"]:
                gates.append("suspended")

        fmcap = float_mcap_cr(sym)
        if fmcap is None:
            degraded.append(f"float_mcap:{sym}")
        elif fmcap < settings.DISCOVERY_FLOAT_MCAP_FLOOR_CR:
            gates.append("low_float_mcap")

        if gates:
            rejected[sym] = gates
        else:
            passed.append(sym)

    logger.info("[discovery.guards] %d passed / %d rejected / %d degraded checks",
                len(passed), len(rejected), len(degraded))
    return passed, rejected, degraded
```

- [ ] **Step 6: Run test to verify it passes**

Run: `python -m pytest tests/unit/test_discovery_universe_guards.py -v`
Expected: PASS (3 tests)

- [ ] **Step 7: Commit**

```bash
git add src/backend/shared/schemas/discovery.py core/discovery tests/unit/test_discovery_universe_guards.py
git commit -m "feat(compass-b): discovery schemas, universe builder, threshold guards (Task 8)"
```

---

### Task 9: Quant signals + composite screen

**Files:**
- Create: `core/discovery/signals.py`
- Create: `core/discovery/screen.py`
- Test: `tests/unit/test_discovery_signals.py`, `tests/unit/test_discovery_screen.py`

**Interfaces:**
- Consumes: EOD window frame (Task 6), `bulk_block.load_bulk_block`/`net_accumulation` (Task 7), `build_universe`/`apply_guards` (Task 8), `settings.DISCOVERY_SIGNAL_WEIGHTS`.
- Produces:
  - `signals.compute_signals(window: pd.DataFrame, universe: list[str], bulk_cache: dict | None) -> dict[str, pd.Series | None]` with EXACT keys `momentum`, `delivery_surge`, `volume_breakout`, `bulk_block`, `high_52wk_rs`, `insider_buying`, `mf_holding`. A `None` value = signal dark. Series are indexed by symbol, higher = better, raw (unranked).
  - `screen.run_screen(on: date | None = None) -> ScreenResult` and `screen.load_latest_screen() -> ScreenResult | None`; results persisted to `{DISCOVERY_DATA_DIR}/screens/{date}_screen.json`.

- [ ] **Step 1: Write the failing signals test**

```python
# tests/unit/test_discovery_signals.py
"""Compass Phase B — quant screen signals (spec §6.1), pure pandas."""
from datetime import date, timedelta

import numpy as np
import pandas as pd
import pytest

from core.discovery import signals as sig


def _make_window(specs: dict[str, dict], sessions: int = 280) -> pd.DataFrame:
    """specs: symbol -> {drift: daily pct, vol_mult, deliv_recent, deliv_base,
    vol_recent_mult}. Deterministic geometric price paths."""
    rows = []
    start = date(2026, 1, 1)
    rng = np.random.default_rng(42)
    for sym, s in specs.items():
        px = 100.0
        for i in range(sessions):
            d = start + timedelta(days=i)
            drift = s.get("drift", 0.0)
            noise = rng.normal(0, 0.005 * s.get("vol_mult", 1.0))
            prev = px
            px = px * (1 + drift + noise)
            recent = i >= sessions - 5
            vol = 10000.0 * (s.get("vol_recent_mult", 1.0) if recent else 1.0)
            deliv = s.get("deliv_recent", 40.0) if recent else s.get("deliv_base", 40.0)
            rows.append({"symbol": sym, "series": "EQ", "date": d.isoformat(),
                         "prev_close": prev, "open": prev, "high": max(prev, px),
                         "low": min(prev, px), "close": px, "volume": vol,
                         "traded_value_cr": 6.0, "delivery_qty": vol * deliv / 100,
                         "delivery_pct": deliv})
    return pd.DataFrame(rows)


@pytest.fixture(scope="module")
def window():
    return _make_window({
        "UPTREND":  {"drift": 0.002},
        "FLATCO":   {"drift": 0.0},
        "DELIVCO":  {"drift": 0.0, "deliv_base": 30.0, "deliv_recent": 70.0},
        "VOLSPIKE": {"drift": 0.001, "vol_recent_mult": 5.0},
    })


def test_momentum_ranks_uptrend_first(window):
    s = sig.sig_momentum(window)
    assert s is not None
    assert s.idxmax() == "UPTREND"
    assert s["UPTREND"] > s["FLATCO"]


def test_momentum_dark_without_history():
    short = _make_window({"AAA": {}}, sessions=100)
    assert sig.sig_momentum(short) is None


def test_delivery_surge(window):
    s = sig.sig_delivery_surge(window)
    assert s.idxmax() == "DELIVCO"


def test_volume_breakout_rewards_spike_near_high(window):
    s = sig.sig_volume_breakout(window)
    assert s["VOLSPIKE"] > s["FLATCO"]


def test_bulk_block_uses_cache(window):
    cache = {"deals": [
        {"symbol": "FLATCO", "side": "BUY", "qty": 50000.0, "kind": "bulk", "date": "2026-07-01"},
    ]}
    s = sig.sig_bulk_block(window, cache)
    assert s["FLATCO"] > 0
    assert s.get("UPTREND", 0.0) == 0.0


def test_bulk_block_dark_without_cache(window):
    assert sig.sig_bulk_block(window, None) is None


def test_high_52wk_rs(window):
    s = sig.sig_high_52wk_rs(window)
    assert s["UPTREND"] > s["FLATCO"]


def test_compute_signals_keys_and_dark(window):
    out = sig.compute_signals(window, ["UPTREND", "FLATCO", "DELIVCO", "VOLSPIKE"], None)
    assert set(out) == {"momentum", "delivery_surge", "volume_breakout",
                        "bulk_block", "high_52wk_rs", "insider_buying", "mf_holding"}
    assert out["insider_buying"] is None and out["mf_holding"] is None   # dark v1
    assert out["bulk_block"] is None                                     # no cache passed
```

- [ ] **Step 2: Run signals test to verify it fails**

Run: `python -m pytest tests/unit/test_discovery_signals.py -v`
Expected: FAIL with `ImportError: cannot import name 'signals'`

- [ ] **Step 3: Implement `core/discovery/signals.py`**

```python
"""
Compass Phase B — quant screen signals (spec §6.1). Pure pandas, zero LLM.

Each sig_* returns a pd.Series indexed by symbol (higher = better, raw
values — screen.py converts to percentile ranks) or None when the signal is
DARK (insufficient history / feed unavailable). Dark signals are reported in
ScreenResult.dark_signals and the composite renormalizes over live ones
(spec §8 degraded mode).

v1 live signals: momentum (6m+12m vol-adjusted, NSE Momentum-50 style),
delivery_surge, volume_breakout, bulk_block, high_52wk_rs.
v1 dark signals: insider_buying, mf_holding — their data sources (NSE
insider-trading disclosures, AMC portfolio parsing) are sub-projects of
their own; config weights are reserved so they plug in without re-tuning.
"""
from __future__ import annotations

import logging

import pandas as pd

logger = logging.getLogger(__name__)

_MOMENTUM_MIN_SESSIONS = 252


def _pivot(window: pd.DataFrame, value: str) -> pd.DataFrame:
    return window.pivot_table(
        index="date", columns="symbol", values=value, aggfunc="last"
    ).sort_index()


def sig_momentum(window: pd.DataFrame) -> pd.Series | None:
    """6m+12m volatility-adjusted momentum: mean over L in (126, 252) of
    (close_t/close_{t-L} - 1) / std(daily returns over L)."""
    px = _pivot(window, "close")
    if len(px) < _MOMENTUM_MIN_SESSIONS:
        return None
    daily = px.pct_change()
    parts = []
    for lookback in (126, 252):
        ret = px.iloc[-1] / px.iloc[-lookback] - 1.0
        vol = daily.tail(lookback).std()
        parts.append(ret / vol.replace(0, pd.NA))
    out = (parts[0] + parts[1]) / 2.0
    return out.dropna()


def sig_delivery_surge(window: pd.DataFrame) -> pd.Series | None:
    """Mean delivery% of last 5 sessions vs the prior 20 sessions."""
    piv = _pivot(window, "delivery_pct")
    if len(piv) < 25:
        return None
    recent = piv.tail(5).mean()
    base = piv.iloc[-25:-5].mean()
    return (recent / base.replace(0, pd.NA)).dropna()


def sig_volume_breakout(window: pd.DataFrame) -> pd.Series | None:
    """5d/60d volume ratio, gated on proximity to the 60d high (accumulation
    signature = volume anomaly WITH the price pressing its range top;
    a volume spike far from highs scores only 30% of its ratio)."""
    vol = _pivot(window, "volume")
    px = _pivot(window, "close")
    if len(vol) < 60:
        return None
    ratio = vol.tail(5).mean() / vol.tail(60).mean().replace(0, pd.NA)
    near_high = px.iloc[-1] >= 0.97 * px.tail(60).max()
    return ratio.where(near_high, ratio * 0.3).dropna()


def sig_bulk_block(window: pd.DataFrame, bulk_cache: dict | None) -> pd.Series | None:
    """Net same-side bulk/block BUY qty over the cached ~4wk window,
    normalised by the symbol's 20d average volume. Symbols without deals = 0."""
    if bulk_cache is None:
        return None
    from services.data.fetchers.bulk_block import net_accumulation
    net = net_accumulation(bulk_cache)
    vol = _pivot(window, "volume")
    if len(vol) < 20:
        return None
    avg20 = vol.tail(20).mean()
    ser = pd.Series(net, dtype=float).reindex(avg20.index).fillna(0.0)
    return (ser / avg20.replace(0, pd.NA)).fillna(0.0)


def sig_high_52wk_rs(window: pd.DataFrame) -> pd.Series | None:
    """52-wk-high proximity + 3m relative strength vs the universe median
    (median 3m return as the market proxy — no external index fetch)."""
    px = _pivot(window, "close")
    if len(px) < _MOMENTUM_MIN_SESSIONS:
        return None
    proximity = px.iloc[-1] / px.tail(252).max()
    r3 = px.iloc[-1] / px.iloc[-63] - 1.0
    rs = r3 - r3.median()
    return (proximity + rs).dropna()


def sig_insider_buying(window: pd.DataFrame) -> pd.Series | None:
    """DARK in v1 — NSE insider-trading (corporates-pit) fetcher not built yet."""
    return None


def sig_mf_holding(window: pd.DataFrame) -> pd.Series | None:
    """DARK in v1 — AMC monthly portfolio parsing is its own sub-project."""
    return None


def compute_signals(
    window: pd.DataFrame, universe: list[str], bulk_cache: dict | None
) -> dict[str, pd.Series | None]:
    """All 7 signal slots, restricted to `universe` symbols. None = dark."""
    win = window[window["symbol"].isin(universe)]
    out: dict[str, pd.Series | None] = {
        "momentum": sig_momentum(win),
        "delivery_surge": sig_delivery_surge(win),
        "volume_breakout": sig_volume_breakout(win),
        "bulk_block": sig_bulk_block(win, bulk_cache),
        "high_52wk_rs": sig_high_52wk_rs(win),
        "insider_buying": sig_insider_buying(win),
        "mf_holding": sig_mf_holding(win),
    }
    dark = [k for k, v in out.items() if v is None]
    if dark:
        logger.info("[discovery.signals] dark signals: %s", dark)
    return out
```

- [ ] **Step 4: Run signals test to verify it passes**

Run: `python -m pytest tests/unit/test_discovery_signals.py -v`
Expected: PASS (8 tests)

- [ ] **Step 5: Write the failing screen test**

```python
# tests/unit/test_discovery_screen.py
"""Compass Phase B — composite screen orchestration + persistence."""
from datetime import date

import pandas as pd
import pytest

import core.discovery.screen as scr
from backend.shared.schemas.discovery import ScreenResult


@pytest.fixture
def patched(tmp_path, monkeypatch):
    """Screen with every collaborator faked: 3-symbol universe, 2 live signals,
    one guard rejection."""
    monkeypatch.setattr(scr.settings, "DISCOVERY_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(scr.settings, "DISCOVERY_SHORTLIST_SIZE", 3)
    monkeypatch.setattr(scr.settings, "DISCOVERY_MAX_CANDIDATES", 2)

    win = pd.DataFrame([{"symbol": s, "series": "EQ", "date": "2026-07-03",
                         "prev_close": 99.0, "open": 99.0, "high": 101.0, "low": 98.0,
                         "close": 100.0, "volume": 1.0, "traded_value_cr": 6.0,
                         "delivery_qty": 1.0, "delivery_pct": 40.0}
                        for s in ("AAA", "BBB", "CCC")])

    class _FakeStore:
        def load_window(self, end, sessions):
            return win
        def latest_day(self):
            return date(2026, 7, 3)
    monkeypatch.setattr(scr, "EodStore", lambda: _FakeStore())
    monkeypatch.setattr(scr, "build_universe", lambda w: ["AAA", "BBB", "CCC"])
    monkeypatch.setattr(
        scr, "compute_signals",
        lambda w, u, c: {
            "momentum": pd.Series({"AAA": 3.0, "BBB": 2.0, "CCC": 1.0}),
            "delivery_surge": pd.Series({"AAA": 1.0, "BBB": 3.0, "CCC": 2.0}),
            "volume_breakout": None, "bulk_block": None,
            "high_52wk_rs": None, "insider_buying": None, "mf_holding": None,
        })
    monkeypatch.setattr(
        scr, "apply_guards",
        lambda shortlist, w: (
            [s for s in shortlist if s != "CCC"],
            {"CCC": ["low_liquidity"]},
            ["promoter_pledge"],
        ))
    monkeypatch.setattr(scr, "load_bulk_block", lambda: {"degraded": True, "deals": []})
    return tmp_path


def test_run_screen_ranks_guards_and_persists(patched):
    result = scr.run_screen(on=date(2026, 7, 4))
    assert isinstance(result, ScreenResult)
    assert result.universe_size == 3
    assert len(result.candidates) == 2
    # momentum weight 0.30 dominates delivery 0.15 -> AAA first
    assert result.candidates[0].symbol == "AAA"
    assert result.rejected == {"CCC": ["low_liquidity"]}
    assert set(result.dark_signals) == {"volume_breakout", "bulk_block",
                                        "high_52wk_rs", "insider_buying", "mf_holding"}
    assert "promoter_pledge" in result.degraded_checks
    assert (patched / "screens" / "2026-07-03_screen.json").exists()

    latest = scr.load_latest_screen()
    assert latest is not None and latest.screen_date == "2026-07-03"


def test_run_screen_empty_store(patched, monkeypatch):
    class _Empty:
        def load_window(self, end, sessions):
            return pd.DataFrame()
        def latest_day(self):
            return None
    monkeypatch.setattr(scr, "EodStore", lambda: _Empty())
    result = scr.run_screen(on=date(2026, 7, 4))
    assert result.universe_size == 0 and result.candidates == []
```

- [ ] **Step 6: Run screen test to verify it fails**

Run: `python -m pytest tests/unit/test_discovery_screen.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'core.discovery.screen'`

- [ ] **Step 7: Implement `core/discovery/screen.py`**

```python
"""
Compass Phase B — Stage-1 weekly quant screen (spec §6.1).

Funnel: EOD window -> universe (EQ, price floor) -> 7 signal slots ->
weighted percentile-rank composite (renormalized over LIVE signals) ->
top shortlist_size -> per-symbol guards -> top max_candidates.

Persistence: {DISCOVERY_DATA_DIR}/screens/{screen_date}_screen.json
(screen_date = the EOD store's latest session, not the wall-clock date).
"""
from __future__ import annotations

import json
import logging
from datetime import date
from pathlib import Path

import pandas as pd

from core.config import settings
from backend.shared.schemas.discovery import DiscoveryCandidate, ScreenResult
from core.discovery.guards import apply_guards
from core.discovery.signals import compute_signals
from core.discovery.universe import build_universe
from services.data.fetchers.bulk_block import load_bulk_block
from services.data.stores.eod_store import EodStore

logger = logging.getLogger(__name__)


def _screens_dir() -> Path:
    d = Path(settings.DISCOVERY_DATA_DIR) / "screens"
    d.mkdir(parents=True, exist_ok=True)
    return d


def run_screen(on: date | None = None) -> ScreenResult:
    """Run the full quant screen as of `on` (default today). Never raises."""
    on = on or date.today()
    store = EodStore()
    window = store.load_window(end=on, sessions=settings.DISCOVERY_HISTORY_DAYS)
    screen_date = (store.latest_day() or on).isoformat()

    if window.empty:
        logger.warning("[discovery.screen] EOD store empty — screen skipped")
        result = ScreenResult(screen_date=screen_date, universe_size=0,
                              shortlist_size=0)
        _persist(result)
        return result

    universe = build_universe(window)

    bulk_cache = load_bulk_block()
    if bulk_cache.get("degraded") and not bulk_cache.get("deals"):
        bulk_cache = None            # fully dark, not just stale
    raw_signals = compute_signals(window, universe, bulk_cache)

    live = {k: v.rank(pct=True) for k, v in raw_signals.items() if v is not None}
    dark = [k for k, v in raw_signals.items() if v is None]

    if not live:
        logger.warning("[discovery.screen] ALL signals dark — screen degraded to empty")
        result = ScreenResult(screen_date=screen_date, universe_size=len(universe),
                              shortlist_size=0, dark_signals=dark)
        _persist(result)
        return result

    weights = {k: settings.DISCOVERY_SIGNAL_WEIGHTS.get(k, 0.0) for k in live}
    total_w = sum(weights.values()) or 1.0
    weights = {k: w / total_w for k, w in weights.items()}

    composite = pd.Series(0.0, index=pd.Index(universe, name="symbol"))
    for name, ranks in live.items():
        composite = composite + ranks.reindex(universe).fillna(0.5) * weights[name]

    shortlist = composite.sort_values(ascending=False).head(
        settings.DISCOVERY_SHORTLIST_SIZE).index.tolist()

    passed, rejected, degraded = apply_guards(shortlist, window)
    ranked_passed = sorted(passed, key=lambda s: composite[s], reverse=True)[
        : settings.DISCOVERY_MAX_CANDIDATES]

    latest_close = (
        window[window["date"] == window["date"].max()]
        .set_index("symbol")["close"].to_dict()
    )
    candidates = [
        DiscoveryCandidate(
            symbol=s,
            close=float(latest_close.get(s, 0.0)),
            composite=round(float(composite[s]), 4),
            signal_ranks={n: round(float(r.reindex([s]).fillna(0.5).iloc[0]), 4)
                          for n, r in live.items()},
        )
        for s in ranked_passed
    ]

    result = ScreenResult(
        screen_date=screen_date,
        universe_size=len(universe),
        shortlist_size=len(shortlist),
        candidates=candidates,
        rejected=rejected,
        dark_signals=dark,
        degraded_checks=degraded,
    )
    _persist(result)
    logger.info(
        "[discovery.screen] %s: universe=%d shortlist=%d candidates=%d dark=%s",
        screen_date, len(universe), len(shortlist), len(candidates), dark,
    )
    return result


def _persist(result: ScreenResult) -> None:
    try:
        path = _screens_dir() / f"{result.screen_date}_screen.json"
        tmp = path.with_suffix(".tmp")
        tmp.write_text(result.model_dump_json(indent=2), encoding="utf-8")
        tmp.replace(path)
    except OSError as exc:
        logger.error("[discovery.screen] persist failed: %s", exc)


def load_latest_screen() -> ScreenResult | None:
    files = sorted(_screens_dir().glob("*_screen.json"))
    if not files:
        return None
    try:
        return ScreenResult(**json.loads(files[-1].read_text(encoding="utf-8")))
    except Exception as exc:
        logger.error("[discovery.screen] latest screen unreadable: %s", exc)
        return None
```

- [ ] **Step 8: Run both test files to verify they pass**

Run: `python -m pytest tests/unit/test_discovery_signals.py tests/unit/test_discovery_screen.py -v`
Expected: PASS (10 tests)

- [ ] **Step 9: Commit**

```bash
git add core/discovery/signals.py core/discovery/screen.py tests/unit/test_discovery_signals.py tests/unit/test_discovery_screen.py
git commit -m "feat(compass-b): quant signals + composite weekly screen with dark-signal degradation (Task 9)"
```

---

### Task 10: Stage-3 LLM deep-dive + sector inference

**Files:**
- Create: `core/discovery/deep_dive.py`
- Test: `tests/unit/test_discovery_deep_dive.py`

**Interfaces:**
- Consumes: `get_orchestrator(sector)` (Task 4 — routes generic), `NATIVE_SECTORS` (from `core.intelligence.rl.workflows.sector_router`), `get_symbol_meta` (Task 7), `TICKER_SECTOR` (existing, `src/backend/sectors/registry.py`), `EodStore` (Task 6), `load_managed_tickers` (existing, `services/api/log_buffer.py`), `DiscoveryCandidate`/`DeepDiveResult` (Task 8), `settings.ADVISOR_STOP_ATR_MULT` (Phase A).
- Produces: `infer_sector(symbol: str) -> str`; `run_deep_dives(candidates: list[DiscoveryCandidate], on: date, max_n: int | None = None) -> list[DeepDiveResult]`.

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_discovery_deep_dive.py
"""Compass Phase B — Stage-3 deep dive: sector inference + one-call conviction."""
from datetime import date

import pandas as pd
import pytest

import core.discovery.deep_dive as dd
from backend.shared.schemas.discovery import DiscoveryCandidate


def test_infer_sector_exact_registry_hit():
    assert dd.infer_sector("SUNPHARMA") == "pharma"       # TICKER_SECTOR map
    assert dd.infer_sector("MARUTI") == "automobile"


def test_infer_sector_industry_keyword(monkeypatch):
    monkeypatch.setattr(dd, "get_symbol_meta",
                        lambda s: {"surveillance": None, "suspended": False,
                                   "industry": "Pharmaceuticals & Biotech",
                                   "degraded": False})
    assert dd.infer_sector("NEWPHARMACO") == "pharma"


def test_infer_sector_falls_back_generic(monkeypatch):
    monkeypatch.setattr(dd, "get_symbol_meta",
                        lambda s: {"surveillance": None, "suspended": False,
                                   "industry": None, "degraded": True})
    assert dd.infer_sector("MYSTERYCO") == "generic"


class _FakeReport:
    final_score = 0.72
    verdict = "BUY"
    investment_thesis = "Strong momentum with improving delivery."


def _window(symbol="NEWCO", n=30):
    rows = []
    for i in range(n):
        rows.append({"symbol": symbol, "series": "EQ", "date": f"2026-06-{i+1:02d}",
                     "prev_close": 100.0, "open": 100.0, "high": 104.0, "low": 98.0,
                     "close": 100.0, "volume": 1.0, "traded_value_cr": 6.0,
                     "delivery_qty": 1.0, "delivery_pct": 40.0})
    return pd.DataFrame(rows)


def test_run_deep_dives_skips_managed_and_builds_result(monkeypatch):
    monkeypatch.setattr(dd, "load_managed_tickers",
                        lambda: [{"sym": "MANAGED", "enabled": True}])

    class _FakeShelfStore:
        def load(self):
            from backend.shared.schemas.discovery import Shelf, ShelfIdea
            return Shelf(ideas=[ShelfIdea(symbol="SHELVED", sector="generic",
                                          added="2026-07-01", conviction=0.6)])
    monkeypatch.setattr(dd, "ShelfStore", _FakeShelfStore)

    class _FakeStore:
        def load_window(self, end, sessions):
            return _window()
    monkeypatch.setattr(dd, "EodStore", lambda: _FakeStore())

    monkeypatch.setattr(dd, "infer_sector", lambda s: "pharma")
    monkeypatch.setattr(dd, "get_orchestrator",
                        lambda sector: type("O", (), {"analyse": lambda self, t: _FakeReport()})())

    cands = [DiscoveryCandidate(symbol=s, close=100.0, composite=0.9 - i * 0.1)
             for i, s in enumerate(["MANAGED", "SHELVED", "NEWCO", "EXTRA"])]
    results = dd.run_deep_dives(cands, on=date(2026, 7, 4), max_n=1)

    assert len(results) == 1
    r = results[0]
    assert r.symbol == "NEWCO"                    # managed + shelved skipped
    assert r.sector == "pharma" and r.graph == "generic"
    assert r.conviction == 0.72 and r.verdict == "BUY"
    assert r.entry_low == pytest.approx(97.0) and r.entry_high == pytest.approx(102.0)
    assert r.invalidation_level < r.close         # ATR-scaled stop below close
    assert r.dive_date == "2026-07-04"


def test_run_deep_dives_orchestrator_failure_is_nonfatal(monkeypatch):
    monkeypatch.setattr(dd, "load_managed_tickers", lambda: [])

    class _EmptyShelf:
        def load(self):
            from backend.shared.schemas.discovery import Shelf
            return Shelf()
    monkeypatch.setattr(dd, "ShelfStore", _EmptyShelf)

    class _FakeStore:
        def load_window(self, end, sessions):
            return _window()
    monkeypatch.setattr(dd, "EodStore", lambda: _FakeStore())
    monkeypatch.setattr(dd, "infer_sector", lambda s: "generic")

    class _Boom:
        def analyse(self, t):
            raise RuntimeError("LLM down")
    monkeypatch.setattr(dd, "get_orchestrator", lambda sector: _Boom())

    cands = [DiscoveryCandidate(symbol="NEWCO", close=100.0, composite=0.9)]
    assert dd.run_deep_dives(cands, on=date(2026, 7, 4)) == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/unit/test_discovery_deep_dive.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'core.discovery.deep_dive'`

- [ ] **Step 3: Implement `core/discovery/deep_dive.py`**

```python
"""
Compass Phase B — Stage-3 LLM deep-dive (spec §6.3).

Top weekly candidates run the existing orchestrator path (unified analyst,
ONE reasoning call per name — generic graph for sectors without a native
one). Deterministic entry zone and ATR-scaled invalidation level are
computed here, NOT by the LLM (spec §9.4: every idea carries "thesis dead
below X").

LLM cost cap: at most DISCOVERY_DEEP_DIVE_COUNT dives per weekly run;
symbols already managed or already on the shelf are skipped BEFORE any
LLM call.
"""
from __future__ import annotations

import logging
from datetime import date

import pandas as pd

from core.config import settings
from backend.shared.schemas.discovery import DeepDiveResult, DiscoveryCandidate
from core.discovery.shelf import ShelfStore
from core.intelligence.rl.workflows.sector_router import NATIVE_SECTORS, get_orchestrator
from services.api.log_buffer import load_managed_tickers
from services.data.fetchers.surveillance import get_symbol_meta
from services.data.stores.eod_store import EodStore

logger = logging.getLogger(__name__)

# NSE meta "industry" keyword -> our sector key (lowercase substring match,
# first hit wins). Keys must satisfy promotion._SECTOR_RE.
_INDUSTRY_SECTOR_KEYWORDS: list[tuple[str, str]] = [
    ("pharma", "pharma"), ("healthcare", "pharma"), ("hospital", "pharma"),
    ("bank", "banking_bfsi"), ("financ", "banking_bfsi"), ("nbfc", "banking_bfsi"),
    ("software", "it_sector"), ("information technology", "it_sector"), ("it services", "it_sector"),
    ("power", "renewable_energy"), ("renewable", "renewable_energy"), ("electric utilit", "renewable_energy"),
    ("auto", "automobile"), ("tyre", "automobile"),
    ("fmcg", "fmcg"), ("consumer", "fmcg"), ("food", "fmcg"), ("beverage", "fmcg"),
    ("steel", "metals"), ("metal", "metals"), ("mining", "metals"), ("aluminium", "metals"),
    ("oil", "oilgas"), ("gas", "oilgas"), ("petro", "oilgas"), ("refin", "oilgas"),
    ("cement", "infra"), ("construction", "infra"), ("infrastructure", "infra"),
    ("chemical", "chemicals"), ("fertil", "agrochem"), ("agro", "agrochem"),
    ("defence", "defence"), ("aerospace", "defence"),
    ("insurance", "insurance"), ("logistic", "logistics"), ("transport", "logistics"),
    ("media", "media"), ("entertainment", "media"),
    ("realty", "realestate"), ("real estate", "realestate"),
    ("retail", "retail"), ("e-commerce", "retail"),
    ("hotel", "hospitality"), ("tourism", "hospitality"),
    ("telecom", "telecom"),
    ("capital goods", "capgoods"), ("electrical equipment", "capgoods"), ("engineering", "capgoods"),
]


def infer_sector(symbol: str) -> str:
    """Best-effort sector key: registry exact hit -> NSE meta industry
    keyword -> 'generic'. Never raises."""
    symbol = symbol.strip().upper()
    try:
        from backend.sectors.registry import TICKER_SECTOR
        if symbol in TICKER_SECTOR:
            return TICKER_SECTOR[symbol]
    except Exception as exc:
        logger.debug("[deep_dive] registry lookup failed for %s: %s", symbol, exc)

    try:
        meta = get_symbol_meta(symbol)
        industry = (meta.get("industry") or "").lower()
        for keyword, sector in _INDUSTRY_SECTOR_KEYWORDS:
            if keyword in industry:
                return sector
    except Exception as exc:
        logger.debug("[deep_dive] meta industry lookup failed for %s: %s", symbol, exc)

    return "generic"


def _atr_pct(sym_win: pd.DataFrame, period: int = 20) -> float:
    """period-day mean True Range as % of latest close. 15.0 fallback."""
    try:
        w = sym_win.sort_values("date").tail(period + 1)
        prev_close = w["close"].shift(1)
        tr = pd.concat([
            w["high"] - w["low"],
            (w["high"] - prev_close).abs(),
            (w["low"] - prev_close).abs(),
        ], axis=1).max(axis=1).dropna()
        close = float(w["close"].iloc[-1])
        if tr.empty or close <= 0:
            return 15.0
        return float(tr.mean() / close * 100.0)
    except Exception:
        return 15.0


def run_deep_dives(
    candidates: list[DiscoveryCandidate], on: date, max_n: int | None = None
) -> list[DeepDiveResult]:
    """Run at most max_n (default DISCOVERY_DEEP_DIVE_COUNT) one-call dives
    over the ranked candidates, skipping managed/shelved names. Per-candidate
    failures are non-fatal."""
    limit = max_n or settings.DISCOVERY_DEEP_DIVE_COUNT
    try:
        managed = {t["sym"] for t in load_managed_tickers() if t.get("enabled", True)}
    except Exception:
        managed = set()
    try:
        shelved = {i.symbol for i in ShelfStore().load().ideas if i.status == "active"}
    except Exception:
        shelved = set()

    window = EodStore().load_window(end=on, sessions=90)
    results: list[DeepDiveResult] = []

    for cand in candidates:
        if len(results) >= limit:
            break
        if cand.symbol in managed or cand.symbol in shelved:
            logger.debug("[deep_dive] %s skipped (managed/shelved)", cand.symbol)
            continue
        try:
            sector = infer_sector(cand.symbol)
            report = get_orchestrator(sector).analyse(cand.symbol)
            sym_win = window[window["symbol"] == cand.symbol]
            atr = _atr_pct(sym_win)
            stop_pct = max(8.0, min(22.0, settings.ADVISOR_STOP_ATR_MULT * atr))
            results.append(DeepDiveResult(
                symbol=cand.symbol,
                sector=sector,
                graph="native" if sector in NATIVE_SECTORS else "generic",
                conviction=float(report.final_score),
                verdict=str(report.verdict),
                thesis=str(report.investment_thesis)[:800],
                entry_low=round(cand.close * 0.97, 2),
                entry_high=round(cand.close * 1.02, 2),
                invalidation_level=round(cand.close * (1 - stop_pct / 100.0), 2),
                close=cand.close,
                composite=cand.composite,
                dive_date=on.isoformat(),
            ))
            logger.info("[deep_dive] %s sector=%s conviction=%.2f verdict=%s",
                        cand.symbol, sector, report.final_score, report.verdict)
        except Exception as exc:
            logger.warning("[deep_dive] %s failed (non-fatal): %s", cand.symbol, exc)
    return results
```

**Note:** `core.discovery.shelf` doesn't exist yet — Task 11 creates it. To keep THIS task independently testable, create the minimal `core/discovery/shelf.py` stub now (Task 11 replaces it with the full implementation):

```python
"""Compass Phase B — Discovery Shelf store. Full implementation in Task 11."""
from __future__ import annotations

from backend.shared.schemas.discovery import Shelf


class ShelfStore:
    def load(self) -> Shelf:
        return Shelf()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/unit/test_discovery_deep_dive.py -v`
Expected: PASS (5 tests)

- [ ] **Step 5: Commit**

```bash
git add core/discovery/deep_dive.py core/discovery/shelf.py tests/unit/test_discovery_deep_dive.py
git commit -m "feat(compass-b): stage-3 deep dive — sector inference + one-call conviction + ATR invalidation (Task 10)"
```

---

### Task 11: Discovery Shelf — store, rotation, promote-to-watchlist

**Files:**
- Modify: `core/discovery/shelf.py` (replace the Task-10 stub with the full implementation)
- Test: `tests/unit/test_discovery_shelf.py`

**Interfaces:**
- Consumes: `Shelf`/`ShelfIdea`/`DeepDiveResult` (Task 8), `settings.DISCOVERY_SHELF_SIZE / DISCOVERY_STALE_DAYS / DISCOVERY_MIN_CONVICTION / DISCOVERY_DATA_DIR`, `PortfolioStore` + `WatchlistItem` + `promote_symbol` (Phase A).
- Produces: `ShelfStore(path: str | None = None)` with `load() -> Shelf`, `save(shelf) -> None`, `apply_deep_dives(dives: list[DeepDiveResult], on: date) -> dict` (`{"added": [...], "displaced": [...], "skipped": [...]}`), `rotate_stale(on: date) -> list[str]`, `promote(symbol: str, user_id: str | None = None) -> dict`, `drop(symbol: str, reason: str) -> bool`. Every mutation appends one JSONL event to `{DISCOVERY_DATA_DIR}/shelf_events.jsonl` (`{ts, event, symbol, detail}`) — these events feed M4 delivery in Phase C.

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_discovery_shelf.py
"""Compass Phase B — Discovery Shelf: cap, displacement, stale rotation, promote."""
import json
from datetime import date

import pytest

import core.discovery.shelf as shelf_mod
from backend.shared.schemas.discovery import DeepDiveResult, ShelfIdea


def _dive(symbol, conviction, on="2026-07-04"):
    return DeepDiveResult(symbol=symbol, sector="pharma", graph="generic",
                          conviction=conviction, verdict="BUY", thesis="t",
                          entry_low=97.0, entry_high=102.0, invalidation_level=88.0,
                          close=100.0, composite=0.8, dive_date=on)


@pytest.fixture
def store(tmp_path, monkeypatch):
    monkeypatch.setattr(shelf_mod.settings, "DISCOVERY_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(shelf_mod.settings, "DISCOVERY_SHELF_SIZE", 2)
    monkeypatch.setattr(shelf_mod.settings, "DISCOVERY_STALE_DAYS", 60)
    monkeypatch.setattr(shelf_mod.settings, "DISCOVERY_MIN_CONVICTION", 0.55)
    return shelf_mod.ShelfStore()


def test_apply_adds_above_conviction_floor(store):
    summary = store.apply_deep_dives([_dive("AAA", 0.72), _dive("BBB", 0.40)],
                                     on=date(2026, 7, 4))
    assert summary["added"] == ["AAA"]
    assert summary["skipped"] == ["BBB"]          # below 0.55 floor
    shelf = store.load()
    idea = shelf.ideas[0]
    assert idea.symbol == "AAA" and idea.status == "active"
    assert idea.added == "2026-07-04" and idea.invalidation_level == 88.0


def test_apply_respects_cap_and_displaces_weakest(store):
    store.apply_deep_dives([_dive("AAA", 0.60), _dive("BBB", 0.65)], on=date(2026, 7, 4))
    summary = store.apply_deep_dives([_dive("CCC", 0.90), _dive("DDD", 0.58)],
                                     on=date(2026, 7, 11))
    assert "CCC" in summary["added"]
    assert "AAA" in summary["displaced"]          # weakest active displaced
    assert "DDD" in summary["skipped"]            # cap reached, not stronger than remaining
    active = [i.symbol for i in store.load().ideas if i.status == "active"]
    assert sorted(active) == ["BBB", "CCC"]


def test_rotate_stale(store):
    store.apply_deep_dives([_dive("AAA", 0.7, on="2026-05-01")], on=date(2026, 5, 1))
    rotated = store.rotate_stale(on=date(2026, 7, 4))     # 64 days later
    assert rotated == ["AAA"]
    assert store.load().ideas[0].status == "dropped"


def test_promote_to_watchlist(store, monkeypatch):
    added_items, promoted = [], []

    class _FakePortfolio:
        def __init__(self, user_id=None): pass
        def add_watchlist(self, item): added_items.append(item)
    monkeypatch.setattr(shelf_mod, "PortfolioStore", _FakePortfolio)
    monkeypatch.setattr(shelf_mod, "promote_symbol",
                        lambda symbol, sector, origin: promoted.append(
                            (symbol, sector, origin)) or {"status": "promoted",
                                                          "graph": "generic"})

    store.apply_deep_dives([_dive("AAA", 0.7)], on=date(2026, 7, 4))
    result = store.promote("AAA")
    assert result["status"] == "promoted"
    assert added_items[0].symbol == "AAA" and added_items[0].source == "discovery"
    assert promoted == [("AAA", "pharma", "watchlist")]
    assert store.load().ideas[0].status == "promoted"


def test_promote_unknown_symbol(store):
    result = store.promote("NOPE")
    assert result["status"] == "not_on_shelf"


def test_events_jsonl_written(store, tmp_path):
    store.apply_deep_dives([_dive("AAA", 0.7)], on=date(2026, 7, 4))
    lines = (tmp_path / "shelf_events.jsonl").read_text().strip().splitlines()
    events = [json.loads(l) for l in lines]
    assert events[0]["event"] == "added" and events[0]["symbol"] == "AAA"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/unit/test_discovery_shelf.py -v`
Expected: FAIL with `AttributeError` (`ShelfStore` stub has no `apply_deep_dives`)

- [ ] **Step 3: Replace `core/discovery/shelf.py` with the full implementation**

```python
"""
Compass Phase B — Discovery Shelf (spec §6.3).

Top deep-dive ideas live here with a paper envelope each (paper_lane.py).
Cap DISCOVERY_SHELF_SIZE active ideas: a stronger idea displaces the weakest
active one. Stale ideas (> DISCOVERY_STALE_DAYS without promotion) rotate
out. One-command promote-to-watchlist hands an idea to the Phase A
portfolio machinery (source="discovery", weekly cadence).

Every mutation appends a JSONL event (shelf_events.jsonl) — the add/drop
feed that M4 proactive delivery consumes in Phase C.
"""
from __future__ import annotations

import json
import logging
from datetime import date, datetime, timezone
from pathlib import Path

from core.config import settings
from backend.shared.schemas.discovery import DeepDiveResult, Shelf, ShelfIdea
from backend.shared.schemas.portfolio import WatchlistItem
from core.portfolio.promotion import promote_symbol
from core.portfolio.store import PortfolioStore

logger = logging.getLogger(__name__)


class ShelfStore:
    def __init__(self, path: str | None = None) -> None:
        base = Path(settings.DISCOVERY_DATA_DIR)
        base.mkdir(parents=True, exist_ok=True)
        self._path = Path(path) if path else base / "shelf.json"
        self._events_path = base / "shelf_events.jsonl"

    # -- persistence -----------------------------------------------------

    def load(self) -> Shelf:
        if not self._path.exists():
            return Shelf()
        try:
            return Shelf(**json.loads(self._path.read_text(encoding="utf-8")))
        except Exception as exc:
            logger.error("[shelf] unreadable %s: %s — starting empty", self._path, exc)
            return Shelf()

    def save(self, shelf: Shelf) -> None:
        shelf.updated_at = datetime.now(timezone.utc).isoformat()
        tmp = self._path.with_suffix(".tmp")
        tmp.write_text(shelf.model_dump_json(indent=2), encoding="utf-8")
        tmp.replace(self._path)

    def _event(self, event: str, symbol: str, detail: str = "") -> None:
        try:
            line = json.dumps({
                "ts": datetime.now(timezone.utc).isoformat(),
                "event": event, "symbol": symbol, "detail": detail,
            })
            with open(self._events_path, "a", encoding="utf-8") as f:
                f.write(line + "\n")
        except OSError as exc:
            logger.warning("[shelf] event write failed: %s", exc)

    # -- mutations ---------------------------------------------------------

    def apply_deep_dives(self, dives: list[DeepDiveResult], on: date) -> dict:
        """Add qualifying dives (conviction >= floor), displacing the weakest
        active idea when the cap is full and the newcomer is stronger."""
        shelf = self.load()
        added: list[str] = []
        displaced: list[str] = []
        skipped: list[str] = []

        for dive in sorted(dives, key=lambda d: d.conviction, reverse=True):
            if dive.conviction < settings.DISCOVERY_MIN_CONVICTION:
                skipped.append(dive.symbol)
                continue
            if any(i.symbol == dive.symbol and i.status == "active"
                   for i in shelf.ideas):
                skipped.append(dive.symbol)
                continue
            active = [i for i in shelf.ideas if i.status == "active"]
            if len(active) >= settings.DISCOVERY_SHELF_SIZE:
                weakest = min(active, key=lambda i: i.conviction)
                if weakest.conviction >= dive.conviction:
                    skipped.append(dive.symbol)
                    continue
                weakest.status = "dropped"
                displaced.append(weakest.symbol)
                self._event("dropped", weakest.symbol,
                            f"displaced by {dive.symbol} "
                            f"({dive.conviction:.2f} > {weakest.conviction:.2f})")
            shelf.ideas.append(ShelfIdea(
                symbol=dive.symbol, sector=dive.sector, graph=dive.graph,
                added=on.isoformat(), conviction=dive.conviction,
                verdict=dive.verdict, thesis=dive.thesis,
                entry_low=dive.entry_low, entry_high=dive.entry_high,
                invalidation_level=dive.invalidation_level,
                close_at_add=dive.close, source_screen_date=dive.dive_date,
            ))
            added.append(dive.symbol)
            self._event("added", dive.symbol, f"conviction={dive.conviction:.2f}")

        self.save(shelf)
        return {"added": added, "displaced": displaced, "skipped": skipped}

    def rotate_stale(self, on: date) -> list[str]:
        """Drop active ideas older than DISCOVERY_STALE_DAYS (spec: stale
        ideas >60d without trigger rotate out)."""
        shelf = self.load()
        rotated: list[str] = []
        for idea in shelf.ideas:
            if idea.status != "active":
                continue
            age = (on - date.fromisoformat(idea.added)).days
            if age > settings.DISCOVERY_STALE_DAYS:
                idea.status = "dropped"
                rotated.append(idea.symbol)
                self._event("dropped", idea.symbol, f"stale after {age}d")
        if rotated:
            self.save(shelf)
        return rotated

    def promote(self, symbol: str, user_id: str | None = None) -> dict:
        """One-command promote-to-watchlist (spec §6.3): watchlist item with
        source='discovery' + managed-universe promotion (weekly cadence)."""
        symbol = symbol.strip().upper()
        shelf = self.load()
        idea = next((i for i in shelf.ideas
                     if i.symbol == symbol and i.status == "active"), None)
        if idea is None:
            return {"status": "not_on_shelf", "symbol": symbol}

        item = WatchlistItem(
            symbol=symbol, sector=idea.sector, added=date.today().isoformat(),
            reason=f"discovery shelf (conviction {idea.conviction:.2f})",
            source="discovery",
        )
        PortfolioStore(user_id=user_id).add_watchlist(item)
        promotion = promote_symbol(symbol, idea.sector, origin="watchlist")

        idea.status = "promoted"
        self.save(shelf)
        self._event("promoted", symbol, f"user_id={user_id or 'default'}")
        return {"status": "promoted", "symbol": symbol, "promotion": promotion}

    def drop(self, symbol: str, reason: str = "manual") -> bool:
        symbol = symbol.strip().upper()
        shelf = self.load()
        idea = next((i for i in shelf.ideas
                     if i.symbol == symbol and i.status == "active"), None)
        if idea is None:
            return False
        idea.status = "dropped"
        self.save(shelf)
        self._event("dropped", symbol, reason)
        return True
```

- [ ] **Step 4: Run tests to verify they pass (shelf + deep-dive still green)**

Run: `python -m pytest tests/unit/test_discovery_shelf.py tests/unit/test_discovery_deep_dive.py -v`
Expected: PASS (11 tests — the Task-10 tests still pass because they fake `ShelfStore`)

- [ ] **Step 5: Commit**

```bash
git add core/discovery/shelf.py tests/unit/test_discovery_shelf.py
git commit -m "feat(compass-b): discovery shelf — cap/displacement, stale rotation, promote-to-watchlist, event log (Task 11)"
```

---

### Task 12: Paper-lane plumbing in the RL workflows (THE isolation invariant)

**Files:**
- Modify: `core/intelligence/rl/workflows/generate_forecast.py` (`generate_forecast()` signature + store, ~line 405-419)
- Modify: `core/intelligence/rl/workflows/daily_review.py` (`run_daily_review()` — 7 precise edits below)
- Test: `tests/unit/intelligence/rl/test_paper_lane_isolation.py`

**Interfaces:**
- Consumes: `settings.PAPER_PREDICTION_DATA_DIR` (Task 1); `PredictionStore(ticker, sector, base_dir=...)` (existing).
- Produces: `generate_forecast(ticker, sector="automobile", paper: bool = False)`; `run_daily_review(ticker, review_date, sector="automobile", paper: bool = False)` whose summary dict gains `"paper": bool`. With `paper=True`: store root = paper dir; NO sticky-regime write; NO WeightAdapter update/save; NO shared-ledger propagation; NO re-forecast; NO control lane. Local (paper-store) ticker ledger, feedback log, dossier and envelope revision behave normally.

- [ ] **Step 1: Write the failing isolation test**

Mirror the `_patch_common` seam stack from `tests/unit/intelligence/rl/test_shock_path.py` (same module, same fakes) — copy the `_make_envelope`, `_fb_output` helpers and the `_patch_common` function from that file into this new file, with ONE change: `_patch_common` must NOT monkeypatch `PREDICTION_DATA_DIR` itself (this test controls both roots explicitly).

```python
# tests/unit/intelligence/rl/test_paper_lane_isolation.py
"""Compass Phase B — PAPER-LANE ISOLATION invariant (spec §6.3).

'Paper review never touches sector/market ledger or weight memory files' —
plus: never writes global regime state, never fires re-forecasts, never runs
the control lane, and stores everything under PAPER_PREDICTION_DATA_DIR.
"""
from __future__ import annotations

import json
from datetime import date, timedelta

import pytest

from core.schemas.feedback import DailyForecast, PredictionEnvelope, RevisedContext
from core.intelligence.rl.stores.prediction_store import PredictionStore

TICKER = "PAPERCO"
SECTOR = "pharma"
REVIEW_DATE = date.today()
DATE_STR = REVIEW_DATE.isoformat()


def _make_envelope() -> PredictionEnvelope:
    return PredictionEnvelope(
        ticker=TICKER, sector=SECTOR,
        cycle_id=f"{TICKER}_{REVIEW_DATE.year}-{REVIEW_DATE.month:02d}",
        generated_at=f"{REVIEW_DATE.replace(day=1).isoformat()}T00:00:00",
        base_close=100.0,
        daily_forecasts=[
            DailyForecast(day=1, date=DATE_STR, predicted_close=100.0,
                          predicted_verdict="BUY",
                          predicted_agent_scores={"risk": 0.5, "fundamentals": 0.5},
                          confidence=0.5),
            DailyForecast(day=2, date=(REVIEW_DATE + timedelta(days=1)).isoformat(),
                          predicted_close=101.0, predicted_verdict="BUY",
                          predicted_agent_scores={"risk": 0.5, "fundamentals": 0.5},
                          confidence=0.5),
        ],
    )


def _fb_output(miss_type: str = "direction_flip"):
    from core.schemas.feedback import FeedbackAgentOutput
    return FeedbackAgentOutput(
        primary_miss_agent="risk", miss_type=miss_type,
        missed_factors=[], over_weighted_factors=[], agent_score_drift={},
        new_lessons=[],
        revised_context=RevisedContext(headline="Test.",
                                       horizon_confidence_adjustment=0.0),
    )


def _patch_common(dr, monkeypatch, actual_close: float = 98.0):
    # Same seam stack as test_shock_path._patch_common, minus PREDICTION_DATA_DIR
    # (this test controls both roots explicitly).
    monkeypatch.setattr(dr, "_fetch_actual_close", lambda t, d: actual_close)
    monkeypatch.setattr(dr, "get_price_history", lambda *a, **k: None)
    monkeypatch.setattr(dr, "_run_todays_agent_scores",
                        lambda *a, **k: {"risk": 0.5, "fundamentals": 0.5})
    from core.schemas.feedback import RegimeSnapshot
    monkeypatch.setattr(dr.RegimeDetector, "detect", lambda self, d, s: RegimeSnapshot())
    import services.data.fetchers.news as news_mod
    monkeypatch.setattr(news_mod, "get_news_context", lambda *a, **k: "Quiet session.")
    import services.data.fetchers.nse_market as nse_mkt_mod
    monkeypatch.setattr(nse_mkt_mod, "get_nse_market_data", lambda *a, **k: {"error": "skipped"})
    from core.schemas.feedback import OffMarketSignals
    import core.intelligence.rl.stores.offmarket_fetcher as offmarket_mod
    monkeypatch.setattr(offmarket_mod.OffMarketFetcher, "fetch_all",
                        lambda self, t, d: OffMarketSignals(date=d, ticker=t))
    import core.intelligence.rl.algorithms.factor_regime as factor_regime_mod
    monkeypatch.setattr(factor_regime_mod, "get_factor_regime", lambda *a, **k: None)
    import core.intelligence.rl.workflows.month_end_validation as mev
    monkeypatch.setattr(mev, "_is_last_trading_day_of_month", lambda d: False)
    monkeypatch.setattr(dr.settings, "RL_DOSSIER_ENABLED", False)
    from core.intelligence.rl.agents.feedback_agent import FeedbackAgent
    monkeypatch.setattr(FeedbackAgent, "run",
                        lambda self, fb_input, ledger: _fb_output())
    from core.intelligence.rl.agents.thesis_reviewer import ThesisReviewer
    monkeypatch.setattr(ThesisReviewer, "should_review", lambda self, *a, **k: False)


def test_paper_review_full_isolation(tmp_path, monkeypatch):
    import core.intelligence.rl.workflows.daily_review as dr

    real_root = tmp_path / "real"
    paper_root = tmp_path / "paper"
    real_root.mkdir()
    monkeypatch.setattr(dr.settings, "PREDICTION_DATA_DIR", str(real_root))
    monkeypatch.setattr(dr.settings, "PAPER_PREDICTION_DATA_DIR", str(paper_root))
    _patch_common(dr, monkeypatch)

    # Seed the PAPER store with an envelope (as paper_lane.ensure_paper_envelope would).
    paper_store = PredictionStore(TICKER, sector=SECTOR, base_dir=str(paper_root))
    paper_store.save_envelope(_make_envelope())

    # Spies on every isolation seam.
    adapter_calls, propagate_calls, regime_calls, reforecast_calls, control_calls = \
        [], [], [], [], []
    monkeypatch.setattr(dr.WeightAdapter, "update",
                        lambda self, **kw: adapter_calls.append(kw))
    monkeypatch.setattr(dr, "propagate_lessons",
                        lambda **kw: propagate_calls.append(kw))
    monkeypatch.setattr(dr, "update_sticky_regime",
                        lambda *a, **kw: regime_calls.append(a))
    monkeypatch.setattr(dr, "regenerate_envelope",
                        lambda **kw: reforecast_calls.append(kw))
    import core.intelligence.rl.agents.control_lane as cl
    monkeypatch.setattr(cl, "run_control_lane_step",
                        lambda *a, **kw: control_calls.append(a))

    summary = dr.run_daily_review(TICKER, REVIEW_DATE, sector=SECTOR, paper=True)

    assert summary["status"] == "completed"
    assert summary["paper"] is True

    # THE invariant: no weight training, no shared-ledger writes, no global
    # regime writes, no re-forecast, no control lane.
    assert adapter_calls == []
    assert propagate_calls == []
    assert regime_calls == []
    assert reforecast_calls == []
    assert control_calls == []

    # Nothing appeared under the REAL prediction root.
    assert list(real_root.rglob("*")) == []

    # The paper store DID get the local feedback log (per-idea learning only).
    cycle_id = paper_store.current_cycle_id()
    log = paper_store.load_feedback_log(cycle_id)
    assert len(log.entries) == 1 and log.entries[0].date == DATE_STR

    # And no weight-memory file exists even in the paper root (no writes at all).
    assert not list(paper_root.rglob("*weight_memory*"))


def test_paper_false_still_trains(tmp_path, monkeypatch):
    """Guard the guard: a NON-paper review still calls the WeightAdapter."""
    import core.intelligence.rl.workflows.daily_review as dr

    real_root = tmp_path / "real"
    monkeypatch.setattr(dr.settings, "PREDICTION_DATA_DIR", str(real_root))
    _patch_common(dr, monkeypatch)
    monkeypatch.setattr(dr.settings, "RL_REFORECAST_ENABLED", False)
    monkeypatch.setattr(dr.settings, "RL_CONTROL_LANE_ENABLED", False)

    store = PredictionStore(TICKER, sector=SECTOR, base_dir=str(real_root))
    store.save_envelope(_make_envelope())

    summary = dr.run_daily_review(TICKER, REVIEW_DATE, sector=SECTOR)
    assert summary["status"] == "completed"
    assert summary["paper"] is False
    assert list(real_root.rglob("*weight_memory*"))     # weights were saved


def test_generate_forecast_paper_uses_paper_root(monkeypatch, tmp_path):
    """generate_forecast(paper=True) builds its store on the paper root."""
    import core.intelligence.rl.workflows.generate_forecast as gf

    captured = {}
    real_init = gf.PredictionStore.__init__

    def spy_init(self, ticker, sector=None, base_dir=None):
        captured["base_dir"] = base_dir
        real_init(self, ticker, sector=sector, base_dir=base_dir)

    monkeypatch.setattr(gf.PredictionStore, "__init__", spy_init)
    monkeypatch.setattr(gf.settings, "PAPER_PREDICTION_DATA_DIR", str(tmp_path))
    # Abort right after store construction — we only test root selection.
    monkeypatch.setattr(gf, "get_sector_weights",
                        lambda s: (_ for _ in ()).throw(RuntimeError("stop-here")))
    with pytest.raises(RuntimeError, match="stop-here"):
        gf.generate_forecast("PAPERCO", sector="pharma", paper=True)
    assert captured["base_dir"] == str(tmp_path)
```

**Implementer note on the third test:** it assumes `get_sector_weights` is called AFTER the store is constructed inside `generate_forecast()`. Verify with `grep -n "store = PredictionStore\|get_sector_weights\|load_weight_memory" core/intelligence/rl/workflows/generate_forecast.py` — if weights resolve before the store, pick the first callable invoked after store construction as the abort seam instead and adjust the monkeypatch target accordingly. The assertion that matters is `captured["base_dir"]`.

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/unit/intelligence/rl/test_paper_lane_isolation.py -v`
Expected: FAIL with `TypeError: run_daily_review() got an unexpected keyword argument 'paper'`

- [ ] **Step 3: Thread `paper` through `generate_forecast()`**

In `core/intelligence/rl/workflows/generate_forecast.py`:

```python
def generate_forecast(
    ticker: str, sector: str = "automobile", paper: bool = False
) -> PredictionEnvelope:
```

and change the store construction (currently `store = PredictionStore(ticker, sector=sector)` at ~line 419) to:

```python
    # Compass Phase B: paper-lane envelopes live under an ISOLATED store root
    # (spec §6.3) — the real RL tree never sees discovery paper artifacts.
    store = PredictionStore(
        ticker, sector=sector,
        base_dir=settings.PAPER_PREDICTION_DATA_DIR if paper else None,
    )
```

Extend the function docstring's parameter list with `paper : bool — write the envelope into the isolated paper-lane store root (discovery shelf ideas).` Leave `regenerate_envelope()` (the second `PredictionStore(` call site, ~line 575) untouched — paper mode never re-forecasts.

- [ ] **Step 4: Thread `paper` through `run_daily_review()` — 7 edits**

In `core/intelligence/rl/workflows/daily_review.py`:

4a. Signature + docstring (~line 388):

```python
def run_daily_review(
    ticker: str,
    review_date: date,
    sector: str = "automobile",
    paper: bool = False,
) -> dict:
```

Add to the docstring's parameters: `paper : bool — PAPER-LANE mode (Compass Phase B, spec §6.3): isolated store root; disables WeightAdapter writes, shared-ledger propagation, sticky-regime writes, re-forecasts and the control lane. Per-idea local ledger/feedback only.`

4b. Store construction (~line 405):

```python
    store    = PredictionStore(
        ticker, sector=sector,
        base_dir=settings.PAPER_PREDICTION_DATA_DIR if paper else None,
    )
```

4c. Sticky-regime block (~line 443): keep the two initial assignments, then gate the whole `try:` block that calls `_read_state`/`update_sticky_regime`:

```python
    sticky_regime_label = regime_snapshot.regime_label
    prior_sticky_label: str | None = None
    if paper:
        # PAPER-LANE ISOLATION: sticky regime state is GLOBAL
        # (data/predictions/_regime_state.json) — paper reviews read the raw
        # label and never write hysteresis state.
        pass
    else:
        try:
            prior_state = _read_state(_state_path())
            ...            # existing block body unchanged, indented under else
```

4d. WeightAdapter block (~line 960) — replace:

```python
    adapter    = WeightAdapter()
    updated_wm = adapter.update(...)
    store.save_weight_memory(updated_wm)
    new_weight_version = f"v{updated_wm.weight_version}"
```

with:

```python
    if paper:
        # PAPER-LANE ISOLATION: no weight training on paper ideas — junk
        # discovery names must never move learned weights (spec §6.3).
        updated_wm = wm
        new_weight_version = f"v{wm.weight_version}"
    else:
        adapter    = WeightAdapter()
        updated_wm = adapter.update(
            weight_memory=wm,
            feedback_log=feedback_log,
            todays_primary_miss_agent=fb_output.primary_miss_agent,
            todays_miss_type=fb_output.miss_type,
            timing_lag_days=timing.lag_days if timing and timing.lag_days is not None else 0,
            seasonal_threshold_deltas=seasonal_ctx.accuracy_threshold_delta or None,
            factor_regime=_factor_regime_data,
        )
        store.save_weight_memory(updated_wm)
        new_weight_version = f"v{updated_wm.weight_version}"
```

4e. Shared-ledger propagation (~line 1011) — wrap the existing `try:` block:

```python
    if paper:
        logger.debug("[daily_review] %s: paper lane — shared-ledger propagation skipped", ticker)
    else:
        try:
            updated_sector_ledger, updated_market_ledger = propagate_lessons(
            ...            # existing block body unchanged, indented under else
```

4f. Re-forecast trigger condition (~line 1114) — change:

```python
    if getattr(settings, "RL_REFORECAST_ENABLED", True) and _is_live_cycle:
```

to:

```python
    if getattr(settings, "RL_REFORECAST_ENABLED", True) and _is_live_cycle and not paper:
```

4g. Control lane condition (~line 1317) — change:

```python
    if getattr(settings, "RL_CONTROL_LANE_ENABLED", True):
```

to:

```python
    if not paper and getattr(settings, "RL_CONTROL_LANE_ENABLED", True):
```

4h. Summary dict (~line 1332) — add directly under `"sector": sector,`:

```python
        "paper":                    paper,
```

- [ ] **Step 5: Run the isolation test + the whole RL suite**

Run: `python -m pytest tests/unit/intelligence/rl/ -v`
Expected: `test_paper_lane_isolation.py` PASS (3 tests) AND every pre-existing RL test still green (`paper` defaults to False everywhere — shock-path, dossier, control-lane, backfill, early-exit tests unaffected).

- [ ] **Step 6: Commit**

```bash
git add core/intelligence/rl/workflows/generate_forecast.py core/intelligence/rl/workflows/daily_review.py tests/unit/intelligence/rl/test_paper_lane_isolation.py
git commit -m "feat(compass-b): paper-lane mode in RL workflows — isolated root, hard-disabled training writes (Task 12)"
```

---

### Task 13: Paper-lane runner (`core/discovery/paper_lane.py`)

**Files:**
- Create: `core/discovery/paper_lane.py`
- Test: `tests/unit/test_discovery_paper_runner.py`

**Interfaces:**
- Consumes: `generate_forecast(..., paper=True)` / `run_daily_review(..., paper=True)` (Task 12), `ShelfStore` (Task 11), `PredictionStore` (existing), `is_trading_day` (existing nse_calendar).
- Produces: `ensure_paper_envelope(idea: ShelfIdea) -> str` (current paper cycle_id; generates the envelope on first call or at month rollover); `run_paper_reviews(on: date) -> dict` (`{"reviewed": [...], "failed": [...], "skipped": [...]}`) — weekly cadence: called only by the Saturday discovery job (spec §6.3 rule 4), reviewing the most recent trading day.

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_discovery_paper_runner.py
"""Compass Phase B — paper envelopes + weekly paper reviews for shelf ideas."""
from datetime import date

import pytest

import core.discovery.paper_lane as pl
from backend.shared.schemas.discovery import Shelf, ShelfIdea


def _idea(symbol="AAA", status="active"):
    return ShelfIdea(symbol=symbol, sector="pharma", added="2026-07-04",
                     conviction=0.7, status=status)


def test_ensure_paper_envelope_generates_once(monkeypatch, tmp_path):
    monkeypatch.setattr(pl.settings, "PAPER_PREDICTION_DATA_DIR", str(tmp_path))
    envelopes = {}

    class _FakeStore:
        def __init__(self, ticker, sector=None, base_dir=None):
            self._key = f"{ticker}|{sector}|{base_dir}"
        def current_cycle_id(self):
            return "AAA_2026-07"
        def load_envelope(self, cycle_id):
            return envelopes.get(cycle_id)
    monkeypatch.setattr(pl, "PredictionStore", _FakeStore)

    calls = []
    def fake_generate(ticker, sector="automobile", paper=False):
        assert paper is True
        calls.append(ticker)
        envelopes["AAA_2026-07"] = object()
        class _E: cycle_id = "AAA_2026-07"
        return _E()
    monkeypatch.setattr(pl, "generate_forecast", fake_generate)

    assert pl.ensure_paper_envelope(_idea()) == "AAA_2026-07"
    assert pl.ensure_paper_envelope(_idea()) == "AAA_2026-07"
    assert calls == ["AAA"]                       # generated exactly once


def test_run_paper_reviews_weekly(monkeypatch):
    ideas = [_idea("AAA"), _idea("BBB"), _idea("OLD", status="dropped")]
    shelf = Shelf(ideas=ideas)
    saved = []

    class _FakeShelfStore:
        def load(self):
            return shelf
        def save(self, s):
            saved.append(s)
    monkeypatch.setattr(pl, "ShelfStore", _FakeShelfStore)
    monkeypatch.setattr(pl, "ensure_paper_envelope", lambda idea: "X_2026-07")
    monkeypatch.setattr(pl, "is_trading_day", lambda d: d.weekday() < 5)

    reviews = []
    def fake_review(ticker, review_date, sector="automobile", paper=False):
        assert paper is True
        if ticker == "BBB":
            raise RuntimeError("boom")
        reviews.append((ticker, review_date.isoformat(), sector))
        return {"status": "completed"}
    monkeypatch.setattr(pl, "run_daily_review", fake_review)

    result = pl.run_paper_reviews(on=date(2026, 7, 4))    # Saturday
    assert result["reviewed"] == ["AAA"]
    assert result["failed"] == ["BBB"]
    assert result["skipped"] == []                        # dropped idea not counted
    assert reviews == [("AAA", "2026-07-03", "pharma")]   # last trading day = Friday
    assert shelf.ideas[0].last_paper_review == "2026-07-03"
    assert shelf.ideas[0].paper_cycle_id == "X_2026-07"
    assert saved                                          # shelf persisted
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/unit/test_discovery_paper_runner.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'core.discovery.paper_lane'`

- [ ] **Step 3: Implement `core/discovery/paper_lane.py`**

```python
"""
Compass Phase B — paper-lane runner (spec §6.3).

Every active shelf idea gets a PAPER envelope (virtual position, real
forecasts) under the ISOLATED store root, and a WEEKLY paper review — the
same duel machinery that scores real holdings, minus every learning write
(run_daily_review(paper=True) hard-disables those — Task 12).

Cadence rule (spec §6.3.4): weekly, driven by the Saturday discovery job.
Envelopes self-heal at month rollover: ensure_paper_envelope() regenerates
when the current cycle's envelope is missing.
"""
from __future__ import annotations

import logging
from datetime import date, timedelta

from core.config import settings
from backend.shared.schemas.discovery import ShelfIdea
from core.discovery.shelf import ShelfStore
from core.intelligence.rl.nse_calendar import is_trading_day
from core.intelligence.rl.stores.prediction_store import PredictionStore
from core.intelligence.rl.workflows.daily_review import run_daily_review
from core.intelligence.rl.workflows.generate_forecast import generate_forecast

logger = logging.getLogger(__name__)


def _last_trading_day(on: date) -> date:
    d = on
    while not is_trading_day(d):
        d -= timedelta(days=1)
    return d


def ensure_paper_envelope(idea: ShelfIdea) -> str:
    """Generate the current cycle's paper envelope if missing. Returns the
    cycle_id. Raises on generation failure (caller treats per-idea failures
    as non-fatal)."""
    store = PredictionStore(
        idea.symbol, sector=idea.sector,
        base_dir=settings.PAPER_PREDICTION_DATA_DIR,
    )
    cycle_id = store.current_cycle_id()
    if store.load_envelope(cycle_id) is None:
        logger.info("[paper_lane] generating paper envelope for %s (%s)",
                    idea.symbol, cycle_id)
        env = generate_forecast(idea.symbol, sector=idea.sector, paper=True)
        return env.cycle_id
    return cycle_id


def run_paper_reviews(on: date) -> dict:
    """Weekly paper review of every ACTIVE shelf idea for the most recent
    trading day. Non-fatal per idea."""
    store = ShelfStore()
    shelf = store.load()
    review_date = _last_trading_day(on)

    reviewed: list[str] = []
    failed: list[str] = []
    skipped: list[str] = []

    for idea in shelf.ideas:
        if idea.status != "active":
            continue
        if idea.last_paper_review == review_date.isoformat():
            skipped.append(idea.symbol)
            continue
        try:
            idea.paper_cycle_id = ensure_paper_envelope(idea)
            summary = run_daily_review(
                idea.symbol, review_date, sector=idea.sector, paper=True,
            )
            if summary.get("status") == "completed":
                idea.last_paper_review = review_date.isoformat()
                reviewed.append(idea.symbol)
            else:
                failed.append(idea.symbol)
        except Exception as exc:
            logger.warning("[paper_lane] paper review failed for %s (non-fatal): %s",
                           idea.symbol, exc)
            failed.append(idea.symbol)

    store.save(shelf)
    result = {"reviewed": reviewed, "failed": failed, "skipped": skipped,
              "review_date": review_date.isoformat()}
    logger.info("[paper_lane] weekly paper reviews: %s", result)
    return result
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/unit/test_discovery_paper_runner.py -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add core/discovery/paper_lane.py tests/unit/test_discovery_paper_runner.py
git commit -m "feat(compass-b): paper-lane runner — envelopes + weekly paper reviews for shelf ideas (Task 13)"
```

---

### Task 14: Weekly discovery job + `/discovery` API routes

**Files:**
- Modify: `services/scheduler/python/scheduler.py` (new Job 12: Sat 12:30 IST weekly discovery)
- Create: `services/api/routes/discovery_api.py`
- Modify: `services/api/server.py` (import + mount the router)
- Test: `tests/unit/test_discovery_api.py`, `tests/unit/test_scheduler_discovery_job.py`

**Interfaces:**
- Consumes: `sync_recent` (Task 6), `refresh_bulk_block` (Task 7), `run_screen`/`load_latest_screen` (Task 9), `run_deep_dives` (Task 10), `ShelfStore` (Task 11), `run_paper_reviews` (Task 13).
- Produces: scheduler method `_discovery_weekly_job(self)`; `run_discovery_cycle(on: date | None = None) -> dict` in `core/discovery/__init__.py` (single orchestration entry point shared by the scheduler job and the POST /discovery/run route). Routes: `GET /discovery/shelf`, `GET /discovery/screen/latest`, `POST /discovery/run` (202, background), `POST /discovery/shelf/{symbol}/promote`, `DELETE /discovery/shelf/{symbol}` — all with the optional `X-Scheduler-Key` pattern.

- [ ] **Step 1: Write the failing orchestration + API tests**

```python
# tests/unit/test_scheduler_discovery_job.py
"""Compass Phase B — run_discovery_cycle orchestration + scheduler job gating."""
from datetime import date

import pytest

import core.discovery as disc


def test_run_discovery_cycle_happy_path(monkeypatch):
    calls = []
    monkeypatch.setattr(disc, "sync_recent",
                        lambda days_back=7: calls.append("sync") or
                        {"synced": 1, "skipped": 4, "failed": [], "pruned": 0})
    monkeypatch.setattr(disc, "refresh_bulk_block",
                        lambda weeks=4: calls.append("bulk") or {"degraded": False, "deals": []})

    class _Screen:
        candidates = ["c1", "c2"]
        dark_signals = ["mf_holding"]
        universe_size = 1500
        def model_dump(self):
            return {}
    monkeypatch.setattr(disc, "run_screen", lambda on=None: calls.append("screen") or _Screen())
    monkeypatch.setattr(disc, "run_deep_dives",
                        lambda cands, on, max_n=None: calls.append("dives") or ["d1"])

    class _FakeShelf:
        def apply_deep_dives(self, dives, on):
            calls.append("shelf")
            return {"added": ["AAA"], "displaced": [], "skipped": []}
        def rotate_stale(self, on):
            return []
    monkeypatch.setattr(disc, "ShelfStore", _FakeShelf)
    monkeypatch.setattr(disc, "run_paper_reviews",
                        lambda on: calls.append("paper") or
                        {"reviewed": ["AAA"], "failed": [], "skipped": []})

    result = disc.run_discovery_cycle(on=date(2026, 7, 4))
    assert calls == ["sync", "bulk", "screen", "dives", "shelf", "paper"]
    assert result["shelf"]["added"] == ["AAA"]
    assert result["paper"]["reviewed"] == ["AAA"]
    assert result["dark_signals"] == ["mf_holding"]


def test_run_discovery_cycle_stage_failure_is_contained(monkeypatch):
    monkeypatch.setattr(disc, "sync_recent",
                        lambda days_back=7: (_ for _ in ()).throw(RuntimeError("NSE down")))
    monkeypatch.setattr(disc, "refresh_bulk_block", lambda weeks=4: {"degraded": True, "deals": []})

    class _Empty:
        candidates = []
        dark_signals = []
        universe_size = 0
        def model_dump(self):
            return {}
    monkeypatch.setattr(disc, "run_screen", lambda on=None: _Empty())
    monkeypatch.setattr(disc, "run_deep_dives", lambda cands, on, max_n=None: [])

    class _FakeShelf:
        def apply_deep_dives(self, dives, on):
            return {"added": [], "displaced": [], "skipped": []}
        def rotate_stale(self, on):
            return []
    monkeypatch.setattr(disc, "ShelfStore", _FakeShelf)
    monkeypatch.setattr(disc, "run_paper_reviews",
                        lambda on: {"reviewed": [], "failed": [], "skipped": []})

    result = disc.run_discovery_cycle(on=date(2026, 7, 4))
    assert "sync failed" in result["errors"][0]        # contained, cycle continued
    assert result["shelf"]["added"] == []
```

```python
# tests/unit/test_discovery_api.py
"""Compass Phase B — /discovery routes."""
from fastapi.testclient import TestClient

import pytest

from services.api.server import app
import services.api.routes.discovery_api as dapi
from backend.shared.schemas.discovery import (
    DiscoveryCandidate, ScreenResult, Shelf, ShelfIdea,
)

client = TestClient(app)


def _shelf():
    return Shelf(ideas=[ShelfIdea(symbol="AAA", sector="pharma", added="2026-07-04",
                                  conviction=0.7)])


def test_get_shelf(monkeypatch):
    class _S:
        def load(self):
            return _shelf()
    monkeypatch.setattr(dapi, "ShelfStore", _S)
    resp = client.get("/discovery/shelf")
    assert resp.status_code == 200
    assert resp.json()["ideas"][0]["symbol"] == "AAA"


def test_get_latest_screen_404_when_empty(monkeypatch):
    monkeypatch.setattr(dapi, "load_latest_screen", lambda: None)
    assert client.get("/discovery/screen/latest").status_code == 404


def test_get_latest_screen(monkeypatch):
    result = ScreenResult(screen_date="2026-07-03", universe_size=1500,
                          shortlist_size=80,
                          candidates=[DiscoveryCandidate(symbol="AAA", close=100.0,
                                                         composite=0.9)],
                          dark_signals=["mf_holding"])
    monkeypatch.setattr(dapi, "load_latest_screen", lambda: result)
    body = client.get("/discovery/screen/latest").json()
    assert body["screen_date"] == "2026-07-03"
    assert body["dark_signals"] == ["mf_holding"]


def test_post_run_returns_202(monkeypatch):
    monkeypatch.setattr(dapi, "run_discovery_cycle", lambda on=None: {"ok": True})
    resp = client.post("/discovery/run")
    assert resp.status_code == 202


def test_promote_route(monkeypatch):
    class _S:
        def promote(self, symbol, user_id=None):
            return {"status": "promoted", "symbol": symbol}
    monkeypatch.setattr(dapi, "ShelfStore", _S)
    resp = client.post("/discovery/shelf/aaa/promote")
    assert resp.status_code == 200
    assert resp.json()["symbol"] == "AAA"


def test_promote_404_when_not_on_shelf(monkeypatch):
    class _S:
        def promote(self, symbol, user_id=None):
            return {"status": "not_on_shelf", "symbol": symbol}
    monkeypatch.setattr(dapi, "ShelfStore", _S)
    assert client.post("/discovery/shelf/nope/promote").status_code == 404


def test_delete_shelf_idea(monkeypatch):
    class _S:
        def drop(self, symbol, reason="manual"):
            return symbol == "AAA"
    monkeypatch.setattr(dapi, "ShelfStore", _S)
    assert client.delete("/discovery/shelf/AAA").status_code == 200
    assert client.delete("/discovery/shelf/BBB").status_code == 404
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/unit/test_scheduler_discovery_job.py tests/unit/test_discovery_api.py -v`
Expected: FAIL with `AttributeError: module 'core.discovery' has no attribute 'run_discovery_cycle'` / `ModuleNotFoundError: ... discovery_api`

- [ ] **Step 3: Implement `run_discovery_cycle` in `core/discovery/__init__.py`**

Replace the empty `core/discovery/__init__.py` with:

```python
"""
Compass Phase B — Discovery Engine (spec §6): weekly funnel orchestration.

run_discovery_cycle() is the single entry point used by BOTH the Saturday
scheduler job and POST /discovery/run. Every stage is individually
non-fatal: a dark data feed degrades the screen, it never kills the cycle.
"""
from __future__ import annotations

import logging
from datetime import date

# Re-exported collaborators — tests and callers patch these names HERE.
from core.discovery.deep_dive import run_deep_dives
from core.discovery.paper_lane import run_paper_reviews
from core.discovery.screen import load_latest_screen, run_screen
from core.discovery.shelf import ShelfStore
from services.data.fetchers.bhavcopy import sync_recent
from services.data.fetchers.bulk_block import refresh_bulk_block

logger = logging.getLogger(__name__)

__all__ = [
    "run_discovery_cycle", "run_deep_dives", "run_paper_reviews",
    "run_screen", "load_latest_screen", "ShelfStore",
    "sync_recent", "refresh_bulk_block",
]


def run_discovery_cycle(on: date | None = None) -> dict:
    """sync EOD -> refresh bulk/block -> screen -> deep-dives -> shelf ->
    weekly paper reviews. Returns a stage-by-stage summary; never raises."""
    on = on or date.today()
    errors: list[str] = []

    try:
        sync = sync_recent(days_back=7)
    except Exception as exc:
        logger.warning("[discovery] sync failed (non-fatal): %s", exc)
        errors.append(f"sync failed: {exc}")
        sync = {}

    try:
        refresh_bulk_block(weeks=4)
    except Exception as exc:
        logger.warning("[discovery] bulk/block refresh failed (non-fatal): %s", exc)
        errors.append(f"bulk_block failed: {exc}")

    screen = run_screen(on=on)          # never raises by contract

    try:
        dives = run_deep_dives(screen.candidates, on=on)
    except Exception as exc:
        logger.warning("[discovery] deep dives failed (non-fatal): %s", exc)
        errors.append(f"deep_dives failed: {exc}")
        dives = []

    shelf_store = ShelfStore()
    try:
        shelf_summary = shelf_store.apply_deep_dives(dives, on=on)
        rotated = shelf_store.rotate_stale(on=on)
    except Exception as exc:
        logger.warning("[discovery] shelf update failed (non-fatal): %s", exc)
        errors.append(f"shelf failed: {exc}")
        shelf_summary, rotated = {"added": [], "displaced": [], "skipped": []}, []

    try:
        paper = run_paper_reviews(on=on)
    except Exception as exc:
        logger.warning("[discovery] paper reviews failed (non-fatal): %s", exc)
        errors.append(f"paper failed: {exc}")
        paper = {"reviewed": [], "failed": [], "skipped": []}

    result = {
        "date": on.isoformat(),
        "sync": sync,
        "universe_size": screen.universe_size,
        "candidates": len(screen.candidates),
        "dark_signals": screen.dark_signals,
        "deep_dives": len(dives),
        "shelf": shelf_summary,
        "rotated_stale": rotated,
        "paper": paper,
        "errors": errors,
    }
    logger.info("[discovery] weekly cycle complete: %s", result)
    return result
```

**Circular-import check:** `core.discovery.deep_dive` imports `ShelfStore` from `core.discovery.shelf` directly (not from the package root), and nothing in `core/discovery/*` imports the package root — verified structure, keep it that way.

- [ ] **Step 4: Implement `services/api/routes/discovery_api.py`**

```python
"""
Compass Phase B — /discovery routes (spec §6.3: shelf visibility +
one-command promote-to-watchlist).

Auth mirrors portfolio_api: optional X-Scheduler-Key (lockdown deferred —
user decision 2026-07-06, virtual money).
"""
from __future__ import annotations

import logging
import os
from datetime import date

from fastapi import APIRouter, BackgroundTasks, Header, HTTPException, Query

from core.discovery import run_discovery_cycle
from core.discovery.screen import load_latest_screen
from core.discovery.shelf import ShelfStore

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/discovery", tags=["Discovery"])


def _check_auth(key: str | None) -> None:
    required = os.getenv("SCHEDULER_KEY", "")
    if required and key != required:
        raise HTTPException(status_code=403, detail="Invalid or missing X-Scheduler-Key header.")


@router.get("/shelf", summary="Discovery shelf — active ideas + paper status")
async def get_shelf(x_scheduler_key: str | None = Header(default=None)) -> dict:
    _check_auth(x_scheduler_key)
    return ShelfStore().load().model_dump()


@router.get("/screen/latest", summary="Most recent weekly screen result")
async def get_latest_screen(x_scheduler_key: str | None = Header(default=None)) -> dict:
    _check_auth(x_scheduler_key)
    result = load_latest_screen()
    if result is None:
        raise HTTPException(status_code=404, detail="No screen has run yet.")
    return result.model_dump()


@router.post("/run", status_code=202, summary="Trigger a discovery cycle now")
async def trigger_run(
    background: BackgroundTasks,
    x_scheduler_key: str | None = Header(default=None),
) -> dict:
    _check_auth(x_scheduler_key)
    background.add_task(run_discovery_cycle)
    return {"status": "accepted", "detail": "Discovery cycle started in background."}


@router.post("/shelf/{symbol}/promote", summary="Promote a shelf idea to the watchlist")
async def promote_idea(
    symbol: str,
    user_id: str | None = Query(default=None),
    x_scheduler_key: str | None = Header(default=None),
) -> dict:
    _check_auth(x_scheduler_key)
    result = ShelfStore().promote(symbol.strip().upper(), user_id=user_id)
    if result["status"] == "not_on_shelf":
        raise HTTPException(status_code=404, detail=f"{symbol.upper()} is not an active shelf idea.")
    return result


@router.delete("/shelf/{symbol}", summary="Drop a shelf idea")
async def drop_idea(
    symbol: str,
    x_scheduler_key: str | None = Header(default=None),
) -> dict:
    _check_auth(x_scheduler_key)
    if not ShelfStore().drop(symbol.strip().upper(), reason="manual_api"):
        raise HTTPException(status_code=404, detail=f"{symbol.upper()} is not an active shelf idea.")
    return {"status": "dropped", "symbol": symbol.upper()}
```

Mount in `services/api/server.py` — add next to the portfolio import/mount:

```python
from services.api.routes.discovery_api import router as discovery_router
```

```python
app.include_router(discovery_router, tags=["Discovery"])
```

- [ ] **Step 5: Add scheduler Job 12**

In `services/scheduler/python/scheduler.py` `_build_scheduler()`, after the Job 11 block (Task 6):

```python
        # ── Job 12: Weekly discovery funnel (Sat 12:30 IST — after event-ingest
        # 10:00 and research-loop 11:00, so the week's filings are digested first) ──
        if getattr(settings, "DISCOVERY_ENABLED", False):
            scheduler.add_job(
                func=self._discovery_weekly_job,
                trigger=CronTrigger(
                    day_of_week="sat", hour=12, minute=30, timezone="Asia/Kolkata",
                ),
                id="discovery_weekly",
                name="Weekly discovery funnel (screen + deep-dives + shelf + paper)",
                misfire_grace_time=7200,
                coalesce=True,
                replace_existing=True,
            )
            logger.info("[Scheduler] Discovery job: Saturdays at 12:30 pm IST")
        else:
            logger.info("[Scheduler] Discovery job disabled (DISCOVERY_ENABLED=false)")
```

Job implementation:

```python
    def _discovery_weekly_job(self) -> None:
        """Weekly discovery funnel (spec §6): non-fatal by construction —
        run_discovery_cycle() contains every stage failure."""
        from core.discovery import run_discovery_cycle

        _job_banner("Weekly Discovery Funnel")
        try:
            result = run_discovery_cycle()
            logger.info(
                "[Scheduler] Discovery — universe=%s candidates=%s dives=%s "
                "shelf_added=%s paper_reviewed=%s dark=%s errors=%s",
                result.get("universe_size"), result.get("candidates"),
                result.get("deep_dives"), result.get("shelf", {}).get("added"),
                result.get("paper", {}).get("reviewed"),
                result.get("dark_signals"), result.get("errors"),
            )
        except Exception as exc:
            logger.error("[Scheduler] Discovery FAILED: %s", exc, exc_info=True)
        _job_banner("Weekly Discovery Funnel", done=True)
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `python -m pytest tests/unit/test_scheduler_discovery_job.py tests/unit/test_discovery_api.py -v`
Expected: PASS (9 tests)

- [ ] **Step 7: Commit**

```bash
git add core/discovery/__init__.py services/api/routes/discovery_api.py services/api/server.py services/scheduler/python/scheduler.py tests/unit/test_scheduler_discovery_job.py tests/unit/test_discovery_api.py
git commit -m "feat(compass-b): weekly discovery job + /discovery API (shelf, screen, run, promote) (Task 14)"
```

---

### Task 15: Docs + full-suite verification

**Files:**
- Modify: `CODEBASE.md` (module map, API endpoints, config tables, key file locations)
- Modify: `docs/superpowers/specs/2026-07-06-portfolio-intelligence-discovery-design.md` (status header only)
- Test: full suite

- [ ] **Step 1: Update CODEBASE.md**

Add/extend these places (match the existing formatting conventions exactly):

1. **Module map:** under `core/`, add `core/discovery/` with one line per file (`__init__.py` run_discovery_cycle orchestration, `universe.py`, `guards.py`, `signals.py`, `screen.py`, `deep_dive.py`, `shelf.py`, `paper_lane.py`); under `src/backend/sectors/`, add `generic/` ("Compass Phase B — sector-agnostic unified graph for auto-promoted tickers outside the 4 native sectors"); under `services/data/`, add `stores/eod_store.py` and `fetchers/bhavcopy.py`, `fetchers/bulk_block.py`, `fetchers/surveillance.py`.
2. **API endpoints:** new `### Discovery — Compass Phase B (/discovery/*)` table with the 5 routes from Task 14 (auth column: "optional key").
3. **Configuration:** new `### Discovery + Generic Graph — Compass Phase B (config.yaml → discovery.* / generic_graph.*)` table listing every setting from Task 1 with defaults and one-line descriptions; note that `insider_buying`/`mf_holding` signals and the promoter-pledge guard are DARK in v1.
4. **Key file locations:** rows for `core/discovery/*`, `services/data/stores/eod_store.py`, `services/data/fetchers/bhavcopy.py`, `data/market_cache/bhavcopy/` ("per-day parquet EOD cache, ~550 sessions rolling"), `data/discovery/` ("screens/, shelf.json, shelf_events.jsonl"), `data/rl/paper/predictions/` ("ISOLATED paper-lane RL store — never mixed into real metrics").
5. **Sector registry section:** add a note that RL-path routing for non-native sectors now goes through the generic graph (`sector_router.py`), while the chat-path `CoreSectorAdapter` tier remains toggled off and unused.

- [ ] **Step 2: Update the spec status header**

In `docs/superpowers/specs/2026-07-06-portfolio-intelligence-discovery-design.md` change the `**Status:**` line to:

```
**Status:** APPROVED — Phase A merged 2026-07-07; Phase B implemented (plan docs/superpowers/plans/2026-07-07-compass-phase-b.md)
```

- [ ] **Step 3: Run the FULL unit suite**

Run: `python -m pytest tests/unit -q`
Expected: everything green — Phase A baseline (~1693) + ~45 new Phase B tests, 0 failures. Triage any regression before proceeding (most likely culprits: tests pinning `UNIFIED_ANALYST_SECTORS` or `SECTOR_SPECS` key sets — extend their expected values, don't weaken assertions).

Then the API/contract suites: `python -m pytest tests/api tests/contract -q`
Expected: green (no contract surface changed; /discovery is additive).

- [ ] **Step 4: Commit**

```bash
git add CODEBASE.md docs/superpowers/specs/2026-07-06-portfolio-intelligence-discovery-design.md
git commit -m "docs(compass-b): register discovery + generic graph in CODEBASE.md; spec status -> Phase B implemented (Task 15)"
```

---

## Post-plan verification (before merge, not a task)

1. **Live smoke (needs network + OPENROUTER key):**
   - `python -c "from services.data.fetchers.bhavcopy import sync_recent; print(sync_recent(days_back=10))"` — real bhavcopy lands in `data/market_cache/bhavcopy/`.
   - One-time history backfill: `python -c "from services.data.fetchers.bhavcopy import sync_recent; print(sync_recent(days_back=800))"` (~10 min at 0.5s spacing; resumable — momentum stays dark until ≥252 sessions).
   - `python -c "from core.discovery import run_discovery_cycle; import json; print(json.dumps(run_discovery_cycle(), indent=2, default=str))"` — full funnel; expect real candidates, ≤10 deep-dives, shelf populated, paper envelopes under `data/rl/paper/predictions/`.
   - Generic graph live check: `python -c "from core.intelligence.rl.workflows.generate_forecast import generate_forecast; print(generate_forecast('SUNPHARMA', sector='pharma').cycle_id)"` then a daily review for it — verify `data/predictions/pharma/SUNPHARMA/` artifacts and that logs show `GenericSectorOrchestrator` + unified path.
2. **Isolation re-check on real artifacts:** after the paper smoke, `ls data/predictions/` must show no shelf-idea tickers; `data/rl/paper/predictions/<sector>/<sym>/` must contain no `*weight_memory*` files.
3. **Cost sanity:** weekly discovery adds ≤10 unified calls + ≤10 paper envelope generations/reviews — well inside the $19-25/mo envelope; confirm via telemetry (`data/telemetry.db`, phase=unified_analyst rows) after the first live cycle.
4. Merge protocol: superpowers:finishing-a-development-branch; remember **push = Railway deploy** — user's call.

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-07-07-compass-phase-b.md`. Two execution options:

**1. Subagent-Driven (recommended)** — dispatch a fresh subagent per task, review between tasks (superpowers:subagent-driven-development), on a dedicated branch `compass-phase-b` via superpowers:using-git-worktrees.

**2. Inline Execution** — execute tasks in this session with superpowers:executing-plans, batch checkpoints.


# Externalize Tunable Config to YAML — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move operational tunables out of `src/backend/shared/config/settings/base.py` into a repo-root `config.yaml`, resolved with precedence `env var > config.yaml > hardcoded fallback`, with zero changes to the 40+ `settings.<NAME>` consumers.

**Architecture:** A new `loader.py` module parses `config.yaml` once at import and exposes `cfg(path, env=None, fallback=None)`. `base.py` keeps every existing attribute name but sources tunables through `cfg(...)`. Structural constants (URLs, ticker symbols, indicator periods, paths other than `TELEMETRY_DB_PATH`) and secrets stay where they are.

**Tech Stack:** Python 3.11+, PyYAML (already pinned in `requirements.txt`), pytest.

**Spec:** `docs/superpowers/specs/2026-06-20-externalize-tunable-config-to-yaml-design.md` (on branch `feat/externalize-tunable-config-yaml`; Task 1 cherry-picks it onto the work branch).

## Global Constraints

- Precedence is exactly: environment variable > `config.yaml` > hardcoded fallback in `base.py`.
- Every existing `settings.<NAME>` attribute keeps its name and default value — zero downstream edits.
- LLM tiers reflect **current** prod (2026-07-02): fast=`qwen/qwen3.6-flash`, reasoning=`qwen/qwen3.7-max`, bulk=`deepseek/deepseek-v4-flash` ($0.09/$0.18 per M). The spec's `qwen-2.5-72b` bulk value is stale — do NOT use it.
- `TELEMETRY_DB_PATH` is included in `config.yaml` (user requirement).
- Missing `config.yaml` → warn once, run on fallbacks (byte-identical to today). Malformed YAML → raise at import.
- The Docker image copies `src/backend/` to `/app/backend/` — the loader must NOT rely on a fixed `parents[N]` depth. Resolution order: `CONFIG_FILE` env (absolute path, must exist) → `Path.cwd()/config.yaml` → walk `Path(__file__).resolve().parents` upward. The Dockerfile must `COPY config.yaml ./config.yaml`.
- `base.py` imports the loader via a **relative** import (`from .loader import cfg`) so it works under both the `backend.shared.config.settings` and `core.config.settings` package aliases.
- Existing config tests must pass unchanged: `tests/unit/shared/test_config.py`, `tests/unit/shared/test_living_envelope_settings.py`, `tests/unit/shared/test_unified_analyst_settings.py`.

## What moves vs. stays (locked mapping)

**→ config.yaml** (each keeps an env override where it has one today):
`llm.*` (3 tiers, LLM_MODEL catch-all, temperature, max_tokens, timeout, cost rates) · `logging.telemetry_db_path` · `agent_execution.*` (AGENT_TIMEOUT_SECONDS, MAX_RETRIES, RETRY_DELAY_SECONDS) · `agent_weights` · `score_thresholds` · `data_fetch.*` (NEWS_ARTICLES_PER_QUERY, SERPER_MAX_QUERIES, FINANCIALS_LOOKBACK_QUARTERS, SERPER_TIMEOUT_SECONDS, TAVILY_MAX_CONTENT_CHARS, PRICE_HISTORY_YEARS, TECHNICAL_REFRESH_INTERVAL_MIN, MACRO_CACHE_TTL_HOURS) · `scheduler.*` (SCHEDULER_ENABLED, SCHEDULER_CRON, SCHEDULER_TICKERS, FEEDBACK_CRON, ALERT_SCORE_CHANGE_THRESHOLD, ALERT_ON_VERDICT_CHANGE, ALERT_CHANNELS, SCORE_HISTORY_MAX_ROWS) · `chat.max_review_cycles` · `macro_news.*` · `rl.*` (forecast/weight-adapter constants, flat/rerun thresholds, scheduler workers, streak, thesis ATR, lesson blend, boost/penalty table, drift escape, calibration, forgetting block, dossier block, event-ingest block, research-loop block, control-lane + scorecard flags + CONTROL_LANE_MODEL, living-envelope block, close-verify block) · `regime.*` (VIX/FII/RSI thresholds, RL_REGIME_CALM_DAYS) · `regime_multipliers` · `sector_agent_regime_role` · `unified_analyst.*`

**stays in base.py:** OPENROUTER_BASE_URL · data-source URLs (FADA/SIAM/VAHAN/DGFT/CARS24/CARDEKHO) · NEWS_SOURCES · DEFAULT_EXCHANGE/DEFAULT_CURRENCY · NIFTY_AUTO_TICKER · YFINANCE_SUFFIX + YF_SYMBOL_OVERRIDES · indicator periods (RSI_PERIOD, MACD_*, BB_*) · macro tickers (CRUDE_OIL_TICKER … BRENT_TICKER, RUBBER_TICKER_FALLBACKS) · RBI_REPO_RATE_* · PEER_TICKERS · REGIME_SECTOR_TICKERS + REGIME_*_TICKER + *_FALLBACK values · paths (LOG_LEVEL/LOG_FILE, OUTPUT_DIR, REPORT_FORMAT, RAG_DOCUMENTS_BASE_DIR, SCORE_DB_PATH, ALERT_LOG_FILE, PREDICTION_DATA_DIR, SCORECARD_DIR) · CSHARP_SCHEDULER_ENABLED/CSHARP_API_URL · `get_serper_key()` / `unified_analyst_sectors()` helpers

**stays in .env (secrets):** OPENROUTER_API_KEY, SERPER_API_KEY, TAVILY_API_KEY, NEWSAPI_KEY, ALERT_WEBHOOK_URL

---

### Task 0: Work branch

**Files:** none (git only)

- [ ] **Step 1: Branch from main and pick up the spec**

```bash
git checkout main && git pull
git checkout -b feat/config-yaml-externalization
git cherry-pick f5c5fd6   # docs(config): design spec for externalizing tunable config to YAML
```

Expected: spec lands at `docs/superpowers/specs/2026-06-20-externalize-tunable-config-to-yaml-design.md`.

---

### Task 1: Config loader with precedence + coercion (TDD)

**Files:**
- Create: `src/backend/shared/config/settings/loader.py`
- Test: `tests/unit/shared/test_config_loader.py`

**Interfaces:**
- Produces: `cfg(path: str, env: str | None = None, fallback: Any = None) -> Any` and `load_yaml() -> dict`, importable as `backend.shared.config.settings.loader`. `base.py` (Task 3-5) consumes `cfg` via `from .loader import cfg`.

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/shared/test_config_loader.py`:

```python
"""Loader for config.yaml: precedence (env > yaml > fallback) and coercion."""
import textwrap

import pytest


def _fresh_loader(monkeypatch, tmp_path, yaml_text: str | None):
    """Import a fresh loader module bound to a throwaway config.yaml."""
    import importlib
    import backend.shared.config.settings.loader as loader_mod

    if yaml_text is None:
        monkeypatch.setenv("CONFIG_FILE", str(tmp_path / "does-not-exist.yaml"))
    else:
        cfg_file = tmp_path / "config.yaml"
        cfg_file.write_text(textwrap.dedent(yaml_text), encoding="utf-8")
        monkeypatch.setenv("CONFIG_FILE", str(cfg_file))
    return importlib.reload(loader_mod)


YAML = """
    llm:
      model_bulk: "deepseek/deepseek-v4-flash"
      temperature: 0.2
      max_tokens: 2048
    scheduler:
      enabled: true
      tickers: ["MARUTI", "TATAMOTORS"]
    regime_multipliers:
      MACRO_CRISIS: {risk_macro: 1.40, fundamentals: 0.80}
    score_thresholds:
      strong_buy: [0.75, 1.00]
"""


def test_yaml_beats_fallback(monkeypatch, tmp_path):
    loader = _fresh_loader(monkeypatch, tmp_path, YAML)
    assert loader.cfg("llm.model_bulk", fallback="wrong") == "deepseek/deepseek-v4-flash"
    assert loader.cfg("llm.temperature", fallback=9.9) == 0.2


def test_env_beats_yaml(monkeypatch, tmp_path):
    loader = _fresh_loader(monkeypatch, tmp_path, YAML)
    monkeypatch.setenv("LLM_MODEL_BULK", "override/model")
    assert loader.cfg("llm.model_bulk", env="LLM_MODEL_BULK",
                      fallback="x") == "override/model"


def test_fallback_when_missing_everywhere(monkeypatch, tmp_path):
    loader = _fresh_loader(monkeypatch, tmp_path, YAML)
    assert loader.cfg("llm.nonexistent", env="NOPE_NOT_SET", fallback=42) == 42


def test_missing_yaml_file_uses_fallbacks(monkeypatch, tmp_path):
    loader = _fresh_loader(monkeypatch, tmp_path, None)
    assert loader.cfg("llm.model_bulk", fallback="fb") == "fb"


def test_malformed_yaml_raises(monkeypatch, tmp_path):
    with pytest.raises(RuntimeError):
        _fresh_loader(monkeypatch, tmp_path, "llm: [unclosed")


def test_env_bool_coercion(monkeypatch, tmp_path):
    loader = _fresh_loader(monkeypatch, tmp_path, YAML)
    monkeypatch.setenv("SCHED_ON", "false")
    assert loader.cfg("scheduler.enabled", env="SCHED_ON", fallback=True) is False
    monkeypatch.setenv("SCHED_ON", "YES")
    assert loader.cfg("scheduler.enabled", env="SCHED_ON", fallback=False) is True


def test_env_int_float_coercion(monkeypatch, tmp_path):
    loader = _fresh_loader(monkeypatch, tmp_path, YAML)
    monkeypatch.setenv("MAXTOK", "4096")
    assert loader.cfg("llm.max_tokens", env="MAXTOK", fallback=0) == 4096
    monkeypatch.setenv("TEMP", "0.7")
    assert loader.cfg("llm.temperature", env="TEMP", fallback=0.0) == 0.7


def test_env_bad_int_raises_with_key_name(monkeypatch, tmp_path):
    loader = _fresh_loader(monkeypatch, tmp_path, YAML)
    monkeypatch.setenv("MAXTOK", "not-a-number")
    with pytest.raises(ValueError, match="MAXTOK"):
        loader.cfg("llm.max_tokens", env="MAXTOK", fallback=0)


def test_env_csv_list_coercion(monkeypatch, tmp_path):
    loader = _fresh_loader(monkeypatch, tmp_path, YAML)
    monkeypatch.setenv("TICKS", "A, B ,C")
    assert loader.cfg("scheduler.tickers", env="TICKS",
                      fallback=[]) == ["A", "B", "C"]


def test_nested_table_from_yaml(monkeypatch, tmp_path):
    loader = _fresh_loader(monkeypatch, tmp_path, YAML)
    table = loader.cfg("regime_multipliers", fallback={})
    assert table["MACRO_CRISIS"]["risk_macro"] == 1.40


def test_tuple_wrapping_pattern(monkeypatch, tmp_path):
    """The assignment-site pattern base.py uses for SCORE_THRESHOLDS."""
    loader = _fresh_loader(monkeypatch, tmp_path, YAML)
    raw = loader.cfg("score_thresholds", fallback={"strong_buy": (0.75, 1.00)})
    wrapped = {k: tuple(v) for k, v in raw.items()}
    assert wrapped["strong_buy"] == (0.75, 1.00)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `./.stockai/Scripts/python.exe -m pytest tests/unit/shared/test_config_loader.py -v`
Expected: FAIL / ERROR with `ModuleNotFoundError: No module named 'backend.shared.config.settings.loader'`

- [ ] **Step 3: Write the loader**

Create `src/backend/shared/config/settings/loader.py`:

```python
"""
config/settings/loader.py
=========================
Loads repo-root config.yaml once at import and resolves individual settings
with precedence:  environment variable  >  config.yaml  >  hardcoded fallback.

base.py is the only intended consumer (via `from .loader import cfg`); the
40+ modules that read `settings.<NAME>` are untouched by this layer.

File resolution order:
  1. CONFIG_FILE env var (absolute path; missing file raises — explicit
     pointers must not fail silently)
  2. Path.cwd()/config.yaml   (repo root locally, /app in the Docker image)
  3. walk upward from this file's directory (handles src/ layout locally,
     where cwd may differ, e.g. IDE test runners)

Missing file  → warn once, return {} (all fallbacks apply — identical to the
                pre-YAML behavior).
Malformed file → RuntimeError at import (fail loud, never run on a silently
                broken config).
"""
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)

_TRUE_STRINGS = {"true", "1", "yes", "on"}
_FALSE_STRINGS = {"false", "0", "no", "off"}
_MISSING = object()


def _find_config_file() -> Path | None:
    env_path = os.getenv("CONFIG_FILE")
    if env_path:
        p = Path(env_path)
        if p.is_file():
            return p
        logger.warning("[config] CONFIG_FILE=%s does not exist — using fallbacks", env_path)
        return None
    cwd_candidate = Path.cwd() / "config.yaml"
    if cwd_candidate.is_file():
        return cwd_candidate
    for parent in Path(__file__).resolve().parents:
        candidate = parent / "config.yaml"
        if candidate.is_file():
            return candidate
    return None


def load_yaml() -> dict:
    path = _find_config_file()
    if path is None:
        logger.warning("[config] no config.yaml found — running on hardcoded defaults")
        return {}
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise RuntimeError(f"Malformed config.yaml at {path}: {exc}") from exc
    if data is None:
        return {}
    if not isinstance(data, dict):
        raise RuntimeError(
            f"config.yaml at {path} must be a top-level mapping, got {type(data).__name__}"
        )
    logger.info("[config] loaded %s", path)
    return data


_YAML: dict = load_yaml()


def _dig(dotted: str) -> Any:
    node: Any = _YAML
    for part in dotted.split("."):
        if not isinstance(node, dict) or part not in node:
            return _MISSING
        node = node[part]
    return node


def _coerce(raw: str, target: Any, key: str) -> Any:
    """Coerce an env-var string to the type of `target` (YAML value or fallback)."""
    if isinstance(target, bool):
        low = raw.strip().lower()
        if low in _TRUE_STRINGS:
            return True
        if low in _FALSE_STRINGS:
            return False
        raise ValueError(f"Config key {key}: cannot parse bool from {raw!r}")
    if isinstance(target, int) and not isinstance(target, bool):
        try:
            return int(raw)
        except ValueError as exc:
            raise ValueError(f"Config key {key}: expected int, got {raw!r}") from exc
    if isinstance(target, float):
        try:
            return float(raw)
        except ValueError as exc:
            raise ValueError(f"Config key {key}: expected float, got {raw!r}") from exc
    if isinstance(target, (list, tuple)):
        return [item.strip() for item in raw.split(",") if item.strip()]
    return raw


def cfg(path: str, env: str | None = None, fallback: Any = None) -> Any:
    """Resolve one setting: env (coerced) > config.yaml > fallback."""
    yaml_val = _dig(path)
    if env:
        raw = os.getenv(env)
        if raw is not None and raw != "":
            target = yaml_val if yaml_val is not _MISSING else fallback
            if target is None or isinstance(target, str):
                return raw
            return _coerce(raw, target, env)
    if yaml_val is not _MISSING:
        return yaml_val
    return fallback
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `./.stockai/Scripts/python.exe -m pytest tests/unit/shared/test_config_loader.py -v`
Expected: 11 passed

- [ ] **Step 5: Commit**

```bash
git add src/backend/shared/config/settings/loader.py tests/unit/shared/test_config_loader.py
git commit -m "feat(config): yaml loader with env > yaml > fallback precedence"
```

---

### Task 2: config.yaml + Dockerfile COPY

**Files:**
- Create: `config.yaml` (repo root)
- Modify: `Dockerfile` (after `COPY main.py     ./`)

**Interfaces:**
- Produces: the YAML keys consumed by every `cfg(...)` call in Tasks 3-5. Key names below are final — Tasks 3-5 must match them exactly.

- [ ] **Step 1: Create `config.yaml`**

The values are byte-identical to today's `base.py` defaults; comments carry over the institutional knowledge. Full content:

```yaml
# =============================================================================
# StockAgent tunable configuration
# Precedence: environment variable  >  this file  >  hardcoded fallback (base.py)
# Secrets (API keys, webhook URLs) NEVER go here — they stay in .env.
# =============================================================================

llm:
  # Hybrid model tiers — 2026-06-03 benchmark (scripts/model_bench.py), bulk tier
  # re-benchmarked 2026-07-02.
  #   fast      – chat tool-loop (tools + free text, no json_object): qwen/qwen3.6-flash
  #   reasoning – judgment calls (aggregator verdict, RL feedback/thesis): qwen/qwen3.7-max
  #   bulk      – high-volume sector-agent scoring (json_object): deepseek/deepseek-v4-flash
  #               $0.09/$0.18 per M (vs 0.36/0.40 for retired qwen-2.5-72b), 1M ctx,
  #               json_object verified 2026-07-02 with reasoning disabled.
  # NB 2026-07: OpenRouter silently rolled several models to thinking-by-default
  # snapshots, truncating json_object output. EVERY json_object call site passes
  # extra_body=JSON_MODE_EXTRA_BODY (llm_client.py) to disable reasoning.
  # Retired: qwen3-235b (broke JSON), qwen-2.5-72b (2-4x cost of deepseek),
  # Gemini 3.5 Flash (broken output + 64x cost), Kimi (empty + 68s).
  model_fast: "qwen/qwen3.6-flash"
  model_reasoning: "qwen/qwen3.7-max"
  model_bulk: "deepseek/deepseek-v4-flash"
  temperature: 0.2
  max_tokens: 2048
  timeout_seconds: 60
  # Token cost rates (USD per million) for telemetry — default to the BULK tier.
  input_cost_per_m: 0.09
  output_cost_per_m: 0.18

logging:
  # Permanent log/telemetry archive (services/data/stores/log_store.py).
  # Lives under data/ so it sits on the Railway volume and SURVIVES DEPLOYS.
  telemetry_db_path: "data/telemetry.db"

agent_execution:
  timeout_seconds: 120
  max_retries: 3
  retry_delay_seconds: 2.0

# Signal Aggregator – agent weights (must sum to 1.0)
agent_weights:
  sales_demand: 0.15
  raw_materials: 0.09
  fundamentals: 0.18
  pattern_analysis: 0.11
  sentiment: 0.04
  policy_regulatory: 0.09
  competitive_intel: 0.09
  risk_macro: 0.13
  valuation_catalyst: 0.12

# Score thresholds for the final stock score (rendered as tuples in base.py)
score_thresholds:
  strong_buy: [0.75, 1.00]
  buy: [0.55, 0.75]
  neutral: [0.40, 0.55]
  sell: [0.20, 0.40]
  strong_sell: [0.00, 0.20]

data_fetch:
  news_articles_per_query: 5
  serper_max_queries: 3          # per agent run — controls API cost
  financials_lookback_quarters: 4
  serper_timeout_seconds: 10
  tavily_max_content_chars: 600
  price_history_years: 10        # OHLCV history for pattern analysis
  technical_refresh_interval_min: 15
  # Macro cache: HIT saves Serper calls for every stock in the same sector
  # within the TTL (keys: automobile / bfsi / it).
  macro_cache_ttl_hours: 4.0

scheduler:
  enabled: false                 # master switch (true in Railway prod)
  cron: "30 8 * * 1-5"           # weekdays 8:30am IST
  tickers: ["MARUTI", "TATAMOTORS", "M&M", "HEROMOTOCO", "BAJAJ-AUTO"]
  feedback_cron: "0 11 * * 1-5"  # daily RL review: weekdays 4:30pm IST = 11:00 UTC
  alert_score_change_threshold: 0.10
  alert_on_verdict_change: true
  alert_channels: ["console", "file"]
  score_history_max_rows: 90     # ~3 months daily

chat:
  max_review_cycles: 0           # reviewer loop removed in 3-node pipeline redesign

macro_news:
  enabled: true
  retain_days: 90
  context_max_items: 3           # HIGH-severity items per synthesize call
  reviewer_max_items: 5

regime:
  # Regime detection thresholds
  vix_volatile_threshold: 22.0
  vix_low_vol_threshold: 14.0
  fii_proxy_threshold_pct: 1.0   # Nifty 5-day move threshold for FII proxy
  rsi_overbought: 70.0
  rsi_oversold: 30.0
  # Sticky-regime hysteresis: consecutive milder detections required to exit
  calm_days: 3

# Applied on top of learned WeightMemory weights (daily-only modifier, not stored).
# Agents not listed default to 1.0.
regime_multipliers:
  MACRO_CRISIS:
    risk_macro: 1.40
    fundamentals: 0.80
    sales_demand: 0.70
    sentiment: 0.80
    pattern_analysis: 0.90
    competitive_intel: 1.00
    valuation_catalyst: 0.90
    raw_materials: 1.00
    policy_regulatory: 1.00
  RISK_OFF:
    risk_macro: 1.20
    fundamentals: 0.90
    sales_demand: 0.85
    sentiment: 0.90
    pattern_analysis: 0.95
    competitive_intel: 1.00
    valuation_catalyst: 0.95
    raw_materials: 1.00
    policy_regulatory: 1.00
  NORMAL:
    risk_macro: 1.00
    fundamentals: 1.00
    sales_demand: 1.00
    sentiment: 1.00
    pattern_analysis: 1.00
    competitive_intel: 1.00
    valuation_catalyst: 1.00
    raw_materials: 1.00
    policy_regulatory: 1.00
  RISK_ON:
    risk_macro: 0.90
    fundamentals: 1.10
    sales_demand: 1.10
    sentiment: 1.15
    pattern_analysis: 0.95
    competitive_intel: 1.00
    valuation_catalyst: 1.10
    raw_materials: 1.00
    policy_regulatory: 1.00
  MOMENTUM_EXTENDED:
    risk_macro: 0.85
    fundamentals: 1.05
    sales_demand: 0.95
    sentiment: 0.80
    pattern_analysis: 1.20
    competitive_intel: 1.00
    valuation_catalyst: 1.10
    raw_materials: 1.00
    policy_regulatory: 1.00
  OVERSOLD:
    risk_macro: 1.10
    fundamentals: 1.00
    sales_demand: 1.00
    sentiment: 0.90
    pattern_analysis: 1.30
    competitive_intel: 1.00
    valuation_catalyst: 1.05
    raw_materials: 1.00
    policy_regulatory: 1.00

# REGIME_MULTIPLIERS uses automobile agent names as canonical keys; map each
# sector's agents to the closest automobile role. Unlisted agent -> 1.0.
sector_agent_regime_role:
  banking_bfsi:
    fundamentals: fundamentals        # earnings quality
    risk: risk_macro                  # credit risk, NPA
    macro_policy: policy_regulatory   # RBI policy
    institutional: sentiment          # FII/DII flows
    technical: pattern_analysis
    business: valuation_catalyst      # loan book growth
  it_sector:
    fundamentals: fundamentals
    risk_macro: risk_macro
    global_macro: risk_macro          # US tech spend risk
    peer_benchmark: competitive_intel # TCS vs Infosys
    transcript_nlp: sentiment         # earnings call NLP
    technical: pattern_analysis
    valuation: valuation_catalyst
  renewable_energy:
    fundamentals: fundamentals
    business: sales_demand            # capacity pipeline
    valuation: valuation_catalyst
    sentiment_policy: policy_regulatory  # MNRE/CERC policy
    technical: pattern_analysis
    risk: risk_macro                  # DISCOM/curtailment risk
  automobile:                          # identity mapping
    sales_demand: sales_demand
    raw_materials: raw_materials
    fundamentals: fundamentals
    pattern_analysis: pattern_analysis
    sentiment: sentiment
    policy_regulatory: policy_regulatory
    competitive_intel: competitive_intel
    risk_macro: risk_macro
    valuation_catalyst: valuation_catalyst

rl:
  # -- Forecast + weight adaptation (Phase 5) ------------------------------
  forecast_horizon_days: 30
  weight_max_step: 0.05            # max weight change per daily step
  weight_max_drift: 0.15           # max total drift from base value
  weight_min_observations: 3
  weight_accuracy_window: 7
  weight_boost_hit_rate: 0.70      # >=70% hit rate -> boost
  weight_penalty_hit_rate: 0.40    # <=40% hit rate -> penalty
  # -- Direction / early-exit ----------------------------------------------
  flat_threshold_pct: 0.3          # moves within +/-0.3% classified FLAT
  agent_rerun_threshold_pct: 0.5   # skip re-run when direction OK + error below; 0 disables
  scheduler_max_workers: 1         # 1 = sequential (safe without file locking)
  # -- Conviction streak (P3) ----------------------------------------------
  streak_warning_threshold: 8
  rsi_amplifier: 1.50
  max_reversion_prior: 0.30
  # -- ThesisReviewer ------------------------------------------------------
  atr_threshold_floor: 1.5
  atr_threshold_multiplier: 1.5
  # -- Lesson propagation (P2) ---------------------------------------------
  lesson_blend_existing: 0.70
  lesson_blend_incoming: 0.30
  cross_ticker_boost: 0.05
  # -- Weight delta constants (STATIC_AUDIT #4) ----------------------------
  boost: 0.02
  penalty: -0.03
  miss_streak_penalty: -0.05
  bias_trigger: 0.55
  bias_full: 0.70
  timing_free_window: 3
  timing_partial_window: 7
  weight_drift_escape_days: 14     # streak length unlocking drift escape
  weight_drift_escape_multiplier: 1.5
  # -- Calibration reward (Intelligence Phase C2) --------------------------
  calibration_reward_enabled: true
  calibration_weight: 0.5
  # -- Forgetting & recency (Intelligence Phase C3) -------------------------
  forgetting_enabled: true
  miss_recency_halflife_days: 21.0
  miss_penalizable_discount: 0.3
  archive_conf_floor: 0.12
  archive_effectiveness_floor: 0.25
  archive_stale_days: 60
  feedback_halflife_months: 3.0
  # -- Ticker dossier + executable claims (Knowledge Layer) ----------------
  dossier_enabled: true
  dossier_max_observations: 30
  dossier_digest_max_chars: 2500
  dossier_agent_digest_chars: 1500
  dossier_max_new_obs_per_day: 3
  dossier_distill_input_max_chars: 20000
  claims_enabled: true
  lesson_emphasis_delta: 0.03
  lesson_emphasis_cap: 0.06
  lesson_match_min_conf: 0.45
  # -- Event-driven dossier ingestion (Phase 3) ----------------------------
  event_ingest_enabled: true
  event_ingest_lookback_days: 8
  event_ingest_max_events_per_scan: 3
  event_ingest_text_max_chars: 6000
  # -- Research loop (Phase 4) ---------------------------------------------
  research_loop_enabled: true
  research_max_questions_per_run: 2
  research_max_attempts: 3
  research_context_max_chars: 6000
  # -- Control lane + monthly scorecard (Phase 1) ---------------------------
  control_lane_enabled: true
  control_lane_model: ""           # empty -> llm.model_reasoning
  scorecard_enabled: true
  # -- Living Envelope (Phase 2.5) ------------------------------------------
  reforecast_enabled: true
  reforecast_max_per_month: 2
  reforecast_thesis_mult_threshold: 0.5
  regime_sticky_enabled: true
  preopen_check_enabled: true
  preopen_shock_severity: 0.7
  # -- NSE official close cross-check ---------------------------------------
  close_verify_enabled: true
  close_verify_tolerance_pct: 1.0

unified_analyst:
  # CSV of sectors on the unified one-call path; "" disables everywhere.
  sectors: "automobile,banking_bfsi,it_sector,renewable_energy"
  fallback_legacy: true
  max_tokens: 6000
  section_max_chars: 2500
  bundle_max_chars: 18000
```

- [ ] **Step 2: Add the file to the Docker image**

In `Dockerfile`, change:

```dockerfile
COPY scripts/    ./scripts/
COPY main.py     ./
```

to:

```dockerfile
COPY scripts/    ./scripts/
COPY main.py     ./
COPY config.yaml ./config.yaml
```

- [ ] **Step 3: Sanity check the YAML parses**

Run: `./.stockai/Scripts/python.exe -c "import yaml; d=yaml.safe_load(open('config.yaml')); print(sorted(d.keys()))"`
Expected: `['agent_execution', 'agent_weights', 'chat', 'data_fetch', 'llm', 'logging', 'macro_news', 'regime', 'regime_multipliers', 'rl', 'scheduler', 'score_thresholds', 'sector_agent_regime_role', 'unified_analyst']`

- [ ] **Step 4: Commit**

```bash
git add config.yaml Dockerfile
git commit -m "feat(config): repo-root config.yaml + ship it in the Docker image"
```

---

### Task 3: Rewire base.py — LLM, telemetry, execution, weights, thresholds

**Files:**
- Modify: `src/backend/shared/config/settings/base.py` (sections at lines 22-115 and 117-132 in the current file)

**Interfaces:**
- Consumes: `cfg` from Task 1, YAML keys from Task 2.
- Produces: unchanged attribute names `LLM_MODEL_FAST`, `LLM_MODEL_REASONING`, `LLM_MODEL_BULK`, `LLM_MODEL`, `LLM_TEMPERATURE`, `LLM_MAX_TOKENS`, `LLM_TIMEOUT_SECONDS`, `LLM_INPUT_COST_PER_M`, `LLM_OUTPUT_COST_PER_M`, `TELEMETRY_DB_PATH`, `AGENT_TIMEOUT_SECONDS`, `MAX_RETRIES`, `RETRY_DELAY_SECONDS`, `AGENT_WEIGHTS`, `SCORE_THRESHOLDS`.

- [ ] **Step 1: Add the loader import**

After `load_dotenv()` at the top of `base.py`:

```python
from .loader import cfg  # env > config.yaml > fallback (loader.py)
```

- [ ] **Step 2: Replace the LLM tier block**

The long tier-rationale comment moves to config.yaml (done in Task 2); leave a pointer. Replace lines 28-54 (the comment block plus assignments from `LLM_MODEL_FAST` through `LLM_OUTPUT_COST_PER_M`) with:

```python
# Hybrid model tiers — rationale + retirement history documented in config.yaml.
LLM_MODEL_FAST: str      = cfg("llm.model_fast",      env="LLM_MODEL_FAST",      fallback="qwen/qwen3.6-flash")
LLM_MODEL_REASONING: str = cfg("llm.model_reasoning", env="LLM_MODEL_REASONING", fallback="qwen/qwen3.7-max")
LLM_MODEL_BULK: str      = cfg("llm.model_bulk",      env="LLM_MODEL_BULK",      fallback="deepseek/deepseek-v4-flash")
# Back-compat catch-all: any call-site still reading LLM_MODEL gets the BULK tier.
LLM_MODEL: str = os.getenv("LLM_MODEL", LLM_MODEL_BULK)
LLM_TEMPERATURE: float = cfg("llm.temperature", env="LLM_TEMPERATURE", fallback=0.2)
LLM_MAX_TOKENS: int = cfg("llm.max_tokens", env="LLM_MAX_TOKENS", fallback=2048)
LLM_TIMEOUT_SECONDS: int = cfg("llm.timeout_seconds", env="LLM_TIMEOUT_SECONDS", fallback=60)

# Token cost rates (USD per million tokens) for telemetry — BULK tier defaults.
LLM_INPUT_COST_PER_M: float = cfg("llm.input_cost_per_m", env="LLM_INPUT_COST_PER_M", fallback=0.09)
LLM_OUTPUT_COST_PER_M: float = cfg("llm.output_cost_per_m", env="LLM_OUTPUT_COST_PER_M", fallback=0.18)
```

- [ ] **Step 3: Replace TELEMETRY_DB_PATH, agent execution, weights, thresholds**

```python
TELEMETRY_DB_PATH: str = cfg("logging.telemetry_db_path", env="TELEMETRY_DB_PATH", fallback="data/telemetry.db")
```

```python
AGENT_TIMEOUT_SECONDS: int = cfg("agent_execution.timeout_seconds", env="AGENT_TIMEOUT_SECONDS", fallback=120)
MAX_RETRIES: int = cfg("agent_execution.max_retries", env="MAX_RETRIES", fallback=3)
RETRY_DELAY_SECONDS: float = cfg("agent_execution.retry_delay_seconds", env="RETRY_DELAY_SECONDS", fallback=2.0)
```

```python
_DEFAULT_AGENT_WEIGHTS: dict[str, float] = {
    "sales_demand":       0.15,
    "raw_materials":      0.09,
    "fundamentals":       0.18,
    "pattern_analysis":   0.11,
    "sentiment":          0.04,
    "policy_regulatory":  0.09,
    "competitive_intel":  0.09,
    "risk_macro":         0.13,
    "valuation_catalyst": 0.12,
}
AGENT_WEIGHTS: dict[str, float] = cfg("agent_weights", fallback=_DEFAULT_AGENT_WEIGHTS)

_DEFAULT_SCORE_THRESHOLDS: dict[str, tuple[float, float]] = {
    "strong_buy":  (0.75, 1.00),
    "buy":         (0.55, 0.75),
    "neutral":     (0.40, 0.55),
    "sell":        (0.20, 0.40),
    "strong_sell": (0.00, 0.20),
}
SCORE_THRESHOLDS: dict[str, tuple[float, float]] = {
    k: tuple(v) for k, v in cfg("score_thresholds", fallback=_DEFAULT_SCORE_THRESHOLDS).items()
}
```

- [ ] **Step 4: Run the config tests**

Run: `./.stockai/Scripts/python.exe -m pytest tests/unit/shared/test_config.py tests/unit/shared/test_config_loader.py -v`
Expected: all pass (attribute names/defaults unchanged).

- [ ] **Step 5: Commit**

```bash
git add src/backend/shared/config/settings/base.py
git commit -m "refactor(config): LLM/telemetry/execution/weights via cfg()"
```

---

### Task 4: Rewire base.py — data-fetch, scheduler, chat, macro-news

**Files:**
- Modify: `src/backend/shared/config/settings/base.py` (sections currently at lines 76-81, 172-179, 228, 231-269, 544-571)

**Interfaces:**
- Produces: unchanged names `PRICE_HISTORY_YEARS`, `TECHNICAL_REFRESH_INTERVAL_MIN`, `NEWS_ARTICLES_PER_QUERY`, `SERPER_MAX_QUERIES`, `FINANCIALS_LOOKBACK_QUARTERS`, `SERPER_TIMEOUT_SECONDS`, `TAVILY_MAX_CONTENT_CHARS`, `MACRO_CACHE_TTL_HOURS`, `SCHEDULER_ENABLED`, `SCHEDULER_CRON`, `SCHEDULER_TICKERS`, `FEEDBACK_CRON`, `ALERT_SCORE_CHANGE_THRESHOLD`, `ALERT_ON_VERDICT_CHANGE`, `ALERT_CHANNELS`, `SCORE_HISTORY_MAX_ROWS`, `CHAT_MAX_REVIEW_CYCLES`, `MACRO_NEWS_ENABLED`, `MACRO_NEWS_RETAIN_DAYS`, `MACRO_NEWS_CONTEXT_MAX_ITEMS`, `MACRO_NEWS_REVIEWER_MAX_ITEMS`.

- [ ] **Step 1: Replace each assignment in place** (keep surrounding comments; only the value expression changes):

```python
PRICE_HISTORY_YEARS: int = cfg("data_fetch.price_history_years", fallback=10)
TECHNICAL_REFRESH_INTERVAL_MIN: int = cfg("data_fetch.technical_refresh_interval_min", fallback=15)
```

```python
NEWS_ARTICLES_PER_QUERY: int = cfg("data_fetch.news_articles_per_query", env="NEWS_ARTICLES_PER_QUERY", fallback=5)
SERPER_MAX_QUERIES: int = cfg("data_fetch.serper_max_queries", env="SERPER_MAX_QUERIES", fallback=3)
FINANCIALS_LOOKBACK_QUARTERS: int = cfg("data_fetch.financials_lookback_quarters", env="FINANCIALS_LOOKBACK_QUARTERS", fallback=4)
```

```python
MACRO_CACHE_TTL_HOURS: float = cfg("data_fetch.macro_cache_ttl_hours", env="MACRO_CACHE_TTL_HOURS", fallback=4.0)
```

```python
SCHEDULER_ENABLED: bool = cfg("scheduler.enabled", env="SCHEDULER_ENABLED", fallback=False)
SCHEDULER_CRON: str = cfg("scheduler.cron", env="SCHEDULER_CRON", fallback="30 8 * * 1-5")
SCHEDULER_TICKERS: list[str] = list(cfg(
    "scheduler.tickers", env="SCHEDULER_TICKERS",
    fallback=["MARUTI", "TATAMOTORS", "M&M", "HEROMOTOCO", "BAJAJ-AUTO"],
))
ALERT_SCORE_CHANGE_THRESHOLD: float = cfg("scheduler.alert_score_change_threshold", env="ALERT_SCORE_CHANGE_THRESHOLD", fallback=0.10)
ALERT_ON_VERDICT_CHANGE: bool = cfg("scheduler.alert_on_verdict_change", env="ALERT_ON_VERDICT_CHANGE", fallback=True)
ALERT_CHANNELS: list[str] = list(cfg("scheduler.alert_channels", env="ALERT_CHANNELS", fallback=["console", "file"]))
SCORE_HISTORY_MAX_ROWS: int = cfg("scheduler.score_history_max_rows", env="SCORE_HISTORY_MAX_ROWS", fallback=90)
```

(`FEEDBACK_CRON` lives in the RL section of the file; rewire it here too since it is `scheduler.feedback_cron` in YAML:)

```python
FEEDBACK_CRON: str = cfg("scheduler.feedback_cron", env="FEEDBACK_CRON", fallback="0 11 * * 1-5")
```

```python
SERPER_TIMEOUT_SECONDS: int   = cfg("data_fetch.serper_timeout_seconds", fallback=10)
TAVILY_MAX_CONTENT_CHARS: int = cfg("data_fetch.tavily_max_content_chars", fallback=600)
```

```python
CHAT_MAX_REVIEW_CYCLES: int = cfg("chat.max_review_cycles", fallback=0)
```

```python
MACRO_NEWS_RETAIN_DAYS: int = cfg("macro_news.retain_days", env="MACRO_NEWS_RETAIN_DAYS", fallback=90)
MACRO_NEWS_CONTEXT_MAX_ITEMS: int = cfg("macro_news.context_max_items", env="MACRO_NEWS_CONTEXT_MAX_ITEMS", fallback=3)
MACRO_NEWS_REVIEWER_MAX_ITEMS: int = cfg("macro_news.reviewer_max_items", env="MACRO_NEWS_REVIEWER_MAX_ITEMS", fallback=5)
MACRO_NEWS_ENABLED: bool = cfg("macro_news.enabled", env="MACRO_NEWS_ENABLED", fallback=True)
```

- [ ] **Step 2: Run the scheduler-adjacent tests**

Run: `./.stockai/Scripts/python.exe -m pytest tests/contract/test_scheduler.py tests/unit/shared/ -q`
Expected: all pass.

- [ ] **Step 3: Commit**

```bash
git add src/backend/shared/config/settings/base.py
git commit -m "refactor(config): data-fetch/scheduler/chat/macro-news via cfg()"
```

---

### Task 5: Rewire base.py — regime tables + all RL tunables + unified analyst

**Files:**
- Modify: `src/backend/shared/config/settings/base.py` (sections currently at lines 285-344, 350-363, 380-530, 594-731)

**Interfaces:**
- Produces: unchanged names for every `RL_*`, `WEIGHT_*`, `MISS_*`, `ARCHIVE_*`, `FEEDBACK_HALFLIFE_MONTHS`, `DOSSIER_*`, `EVENT_INGEST_*`, `CONTROL_LANE_MODEL`, `SCORECARD_ENABLED`, `CLOSE_VERIFY_*`, `VIX_*`, `FII_PROXY_THRESHOLD_PCT`, `RSI_OVERBOUGHT`, `RSI_OVERSOLD`, `REGIME_MULTIPLIERS`, `SECTOR_AGENT_REGIME_ROLE`, `UNIFIED_*`, `FORECAST_HORIZON_DAYS` attribute.

- [ ] **Step 1: Rewire the scalar tunables** — same mechanical pattern; the full list with exact YAML keys (values are today's defaults, unchanged):

| base.py attribute | cfg path | env (unchanged) | fallback |
|---|---|---|---|
| FORECAST_HORIZON_DAYS | rl.forecast_horizon_days | — | 30 |
| WEIGHT_MAX_STEP | rl.weight_max_step | — | 0.05 |
| WEIGHT_MAX_DRIFT | rl.weight_max_drift | — | 0.15 |
| WEIGHT_MIN_OBSERVATIONS | rl.weight_min_observations | — | 3 |
| WEIGHT_ACCURACY_WINDOW | rl.weight_accuracy_window | — | 7 |
| WEIGHT_BOOST_HIT_RATE | rl.weight_boost_hit_rate | — | 0.70 |
| WEIGHT_PENALTY_HIT_RATE | rl.weight_penalty_hit_rate | — | 0.40 |
| VIX_VOLATILE_THRESHOLD | regime.vix_volatile_threshold | — | 22.0 |
| VIX_LOW_VOL_THRESHOLD | regime.vix_low_vol_threshold | — | 14.0 |
| FII_PROXY_THRESHOLD_PCT | regime.fii_proxy_threshold_pct | — | 1.0 |
| RSI_OVERBOUGHT | regime.rsi_overbought | — | 70.0 |
| RSI_OVERSOLD | regime.rsi_oversold | — | 30.0 |
| RL_FLAT_THRESHOLD_PCT | rl.flat_threshold_pct | — | 0.3 |
| RL_AGENT_RERUN_THRESHOLD_PCT | rl.agent_rerun_threshold_pct | — | 0.5 |
| RL_SCHEDULER_MAX_WORKERS | rl.scheduler_max_workers | RL_SCHEDULER_MAX_WORKERS | 1 |
| RL_STREAK_WARNING_THRESHOLD | rl.streak_warning_threshold | — | 8 |
| RL_RSI_AMPLIFIER | rl.rsi_amplifier | — | 1.50 |
| RL_MAX_REVERSION_PRIOR | rl.max_reversion_prior | — | 0.30 |
| RL_ATR_THRESHOLD_FLOOR | rl.atr_threshold_floor | — | 1.5 |
| RL_ATR_THRESHOLD_MULTIPLIER | rl.atr_threshold_multiplier | — | 1.5 |
| RL_LESSON_BLEND_EXISTING | rl.lesson_blend_existing | — | 0.70 |
| RL_LESSON_BLEND_INCOMING | rl.lesson_blend_incoming | — | 0.30 |
| RL_CROSS_TICKER_BOOST | rl.cross_ticker_boost | — | 0.05 |
| RL_BOOST | rl.boost | — | 0.02 |
| RL_PENALTY | rl.penalty | — | -0.03 |
| RL_MISS_STREAK_PENALTY | rl.miss_streak_penalty | — | -0.05 |
| RL_BIAS_TRIGGER | rl.bias_trigger | — | 0.55 |
| RL_BIAS_FULL | rl.bias_full | — | 0.70 |
| RL_TIMING_FREE_WINDOW | rl.timing_free_window | — | 3 |
| RL_TIMING_PARTIAL_WINDOW | rl.timing_partial_window | — | 7 |
| RL_WEIGHT_DRIFT_ESCAPE_DAYS | rl.weight_drift_escape_days | RL_WEIGHT_DRIFT_ESCAPE_DAYS | 14 |
| RL_WEIGHT_DRIFT_ESCAPE_MULTIPLIER | rl.weight_drift_escape_multiplier | RL_WEIGHT_DRIFT_ESCAPE_MULTIPLIER | 1.5 |
| RL_CALIBRATION_REWARD_ENABLED | rl.calibration_reward_enabled | RL_CALIBRATION_REWARD_ENABLED | True |
| RL_CALIBRATION_WEIGHT | rl.calibration_weight | RL_CALIBRATION_WEIGHT | 0.5 |
| RL_FORGETTING_ENABLED | rl.forgetting_enabled | RL_FORGETTING_ENABLED | True |
| MISS_RECENCY_HALFLIFE_DAYS | rl.miss_recency_halflife_days | MISS_RECENCY_HALFLIFE_DAYS | 21.0 |
| MISS_PENALIZABLE_DISCOUNT | rl.miss_penalizable_discount | MISS_PENALIZABLE_DISCOUNT | 0.3 |
| ARCHIVE_CONF_FLOOR | rl.archive_conf_floor | ARCHIVE_CONF_FLOOR | 0.12 |
| ARCHIVE_EFFECTIVENESS_FLOOR | rl.archive_effectiveness_floor | ARCHIVE_EFFECTIVENESS_FLOOR | 0.25 |
| ARCHIVE_STALE_DAYS | rl.archive_stale_days | ARCHIVE_STALE_DAYS | 60 |
| FEEDBACK_HALFLIFE_MONTHS | rl.feedback_halflife_months | FEEDBACK_HALFLIFE_MONTHS | 3.0 |
| RL_DOSSIER_ENABLED | rl.dossier_enabled | RL_DOSSIER_ENABLED | True |
| DOSSIER_MAX_OBSERVATIONS | rl.dossier_max_observations | DOSSIER_MAX_OBSERVATIONS | 30 |
| DOSSIER_DIGEST_MAX_CHARS | rl.dossier_digest_max_chars | DOSSIER_DIGEST_MAX_CHARS | 2500 |
| DOSSIER_AGENT_DIGEST_CHARS | rl.dossier_agent_digest_chars | DOSSIER_AGENT_DIGEST_CHARS | 1500 |
| DOSSIER_MAX_NEW_OBS_PER_DAY | rl.dossier_max_new_obs_per_day | DOSSIER_MAX_NEW_OBS_PER_DAY | 3 |
| DOSSIER_DISTILL_INPUT_MAX_CHARS | rl.dossier_distill_input_max_chars | DOSSIER_DISTILL_INPUT_MAX_CHARS | 20000 |
| RL_CLAIMS_ENABLED | rl.claims_enabled | RL_CLAIMS_ENABLED | True |
| RL_LESSON_EMPHASIS_DELTA | rl.lesson_emphasis_delta | RL_LESSON_EMPHASIS_DELTA | 0.03 |
| RL_LESSON_EMPHASIS_CAP | rl.lesson_emphasis_cap | RL_LESSON_EMPHASIS_CAP | 0.06 |
| RL_LESSON_MATCH_MIN_CONF | rl.lesson_match_min_conf | RL_LESSON_MATCH_MIN_CONF | 0.45 |
| RL_EVENT_INGEST_ENABLED | rl.event_ingest_enabled | RL_EVENT_INGEST_ENABLED | True |
| EVENT_INGEST_LOOKBACK_DAYS | rl.event_ingest_lookback_days | EVENT_INGEST_LOOKBACK_DAYS | 8 |
| EVENT_INGEST_MAX_EVENTS_PER_SCAN | rl.event_ingest_max_events_per_scan | EVENT_INGEST_MAX_EVENTS_PER_SCAN | 3 |
| EVENT_INGEST_TEXT_MAX_CHARS | rl.event_ingest_text_max_chars | EVENT_INGEST_TEXT_MAX_CHARS | 6000 |
| RL_RESEARCH_LOOP_ENABLED | rl.research_loop_enabled | RL_RESEARCH_LOOP_ENABLED | True |
| RL_RESEARCH_MAX_QUESTIONS_PER_RUN | rl.research_max_questions_per_run | RL_RESEARCH_MAX_QUESTIONS_PER_RUN | 2 |
| RL_RESEARCH_MAX_ATTEMPTS | rl.research_max_attempts | RL_RESEARCH_MAX_ATTEMPTS | 3 |
| RL_RESEARCH_CONTEXT_MAX_CHARS | rl.research_context_max_chars | RL_RESEARCH_CONTEXT_MAX_CHARS | 6000 |
| RL_CONTROL_LANE_ENABLED | rl.control_lane_enabled | RL_CONTROL_LANE_ENABLED | True |
| CONTROL_LANE_MODEL | rl.control_lane_model | CONTROL_LANE_MODEL | "" |
| SCORECARD_ENABLED | rl.scorecard_enabled | SCORECARD_ENABLED | True |
| RL_REFORECAST_ENABLED | rl.reforecast_enabled | RL_REFORECAST_ENABLED | True |
| RL_REFORECAST_MAX_PER_MONTH | rl.reforecast_max_per_month | RL_REFORECAST_MAX_PER_MONTH | 2 |
| RL_REFORECAST_THESIS_MULT_THRESHOLD | rl.reforecast_thesis_mult_threshold | RL_REFORECAST_THESIS_MULT_THRESHOLD | 0.5 |
| RL_REGIME_STICKY_ENABLED | rl.regime_sticky_enabled | RL_REGIME_STICKY_ENABLED | True |
| RL_REGIME_CALM_DAYS | regime.calm_days | RL_REGIME_CALM_DAYS | 3 |
| RL_PREOPEN_CHECK_ENABLED | rl.preopen_check_enabled | RL_PREOPEN_CHECK_ENABLED | True |
| RL_PREOPEN_SHOCK_SEVERITY | rl.preopen_shock_severity | RL_PREOPEN_SHOCK_SEVERITY | 0.7 |
| CLOSE_VERIFY_ENABLED | rl.close_verify_enabled | CLOSE_VERIFY_ENABLED | True |
| CLOSE_VERIFY_TOLERANCE_PCT | rl.close_verify_tolerance_pct | CLOSE_VERIFY_TOLERANCE_PCT | 1.0 |
| UNIFIED_ANALYST_SECTORS | unified_analyst.sectors | UNIFIED_ANALYST_SECTORS | "automobile,banking_bfsi,it_sector,renewable_energy" |
| UNIFIED_ANALYST_FALLBACK_LEGACY | unified_analyst.fallback_legacy | UNIFIED_ANALYST_FALLBACK_LEGACY | True |
| UNIFIED_ANALYST_MAX_TOKENS | unified_analyst.max_tokens | UNIFIED_ANALYST_MAX_TOKENS | 6000 |
| UNIFIED_SECTION_MAX_CHARS | unified_analyst.section_max_chars | UNIFIED_SECTION_MAX_CHARS | 2500 |
| UNIFIED_BUNDLE_MAX_CHARS | unified_analyst.bundle_max_chars | UNIFIED_BUNDLE_MAX_CHARS | 18000 |

Pattern for every row (example):

```python
RL_STREAK_WARNING_THRESHOLD: int = cfg("rl.streak_warning_threshold", fallback=8)
RL_CALIBRATION_WEIGHT: float = cfg("rl.calibration_weight", env="RL_CALIBRATION_WEIGHT", fallback=0.5)
```

Keep every existing explanatory comment block above its assignment.

- [ ] **Step 2: Rewire the two nested tables** (rename the current literals to `_DEFAULT_*` and wrap):

```python
SECTOR_AGENT_REGIME_ROLE: dict[str, dict[str, str]] = cfg(
    "sector_agent_regime_role", fallback=_DEFAULT_SECTOR_AGENT_REGIME_ROLE,
)
REGIME_MULTIPLIERS: dict[str, dict[str, float]] = cfg(
    "regime_multipliers", fallback=_DEFAULT_REGIME_MULTIPLIERS,
)
```

(where `_DEFAULT_SECTOR_AGENT_REGIME_ROLE` / `_DEFAULT_REGIME_MULTIPLIERS` are the existing dict literals, renamed in place — YAML-or-fallback only, no env override, matching today.)

- [ ] **Step 3: Run the full unit-test tree for settings consumers**

Run: `./.stockai/Scripts/python.exe -m pytest tests/unit/ tests/contract/test_scheduler.py -q`
Expected: same pass count as before this task (settings values byte-identical).

- [ ] **Step 4: Commit**

```bash
git add src/backend/shared/config/settings/base.py
git commit -m "refactor(config): regime tables + RL tunables + unified analyst via cfg()"
```

---

### Task 6: End-to-end verification + docs

**Files:**
- Modify: `CODEBASE.md` (config section, if it describes base.py)
- No new code.

- [ ] **Step 1: Value-equality audit** — prove the refactor changed nothing:

```bash
git stash  # temporarily restore pre-refactor base.py? NO — use git show instead:
./.stockai/Scripts/python.exe - <<'EOF'
import importlib, json, subprocess, sys, tempfile, types, pathlib
# 1. Dump current (post-refactor) settings
import backend.shared.config.settings.base as new_base
def dump(mod):
    return {k: v for k, v in vars(mod).items()
            if k.isupper() and isinstance(v, (str, int, float, bool, list, dict, tuple))}
new_vals = dump(new_base)
# 2. Dump old base.py from git (pre-refactor commit) into a temp module
old_src = subprocess.check_output(
    ["git", "show", "main:src/backend/shared/config/settings/base.py"], text=True)
old_mod = types.ModuleType("old_base")
exec(compile(old_src, "old_base.py", "exec"), old_mod.__dict__)
old_vals = dump(old_mod)
diff = {k: (old_vals.get(k), new_vals.get(k))
        for k in sorted(set(old_vals) | set(new_vals))
        if old_vals.get(k) != new_vals.get(k)}
print(json.dumps(diff, indent=2, default=str) if diff else "IDENTICAL")
EOF
```

Expected: `IDENTICAL` (run with no relevant env vars set in the shell).

- [ ] **Step 2: Precedence smoke test against the real file**

```bash
LLM_MODEL_BULK=env-wins ./.stockai/Scripts/python.exe -c "from core.config import settings; print(settings.LLM_MODEL_BULK)"
# Expected: env-wins
./.stockai/Scripts/python.exe -c "from core.config import settings; print(settings.LLM_MODEL_BULK)"
# Expected: deepseek/deepseek-v4-flash
```

- [ ] **Step 3: Full test suite**

Run: `./.stockai/Scripts/python.exe -m pytest tests/ -q`
Expected: no new failures vs the pre-task baseline (9 failed + 10 errors as of 2026-07-02, all pre-existing stale-patch-target tests).

- [ ] **Step 4: Update CODEBASE.md** — in the configuration section, add: config.yaml at repo root holds tunables; precedence env > yaml > base.py fallback; secrets stay in .env; loader at `src/backend/shared/config/settings/loader.py`.

- [ ] **Step 5: Commit, merge to main**

```bash
git add -A && git commit -m "docs(config): document config.yaml precedence"
git checkout main && git merge --no-ff feat/config-yaml-externalization
git push origin main   # auto-deploys Railway
```

- [ ] **Step 6: Post-deploy prod check**

```bash
MSYS_NO_PATHCONV=1 railway ssh -- "ls -la /app/config.yaml && python3 -c \"import sys; sys.path.insert(0,'/app'); from core.config import settings; print(settings.LLM_MODEL_BULK, settings.TELEMETRY_DB_PATH)\""
```

Expected: file exists; prints `deepseek/deepseek-v4-flash data/telemetry.db` (or Railway env overrides if set — check `railway variables` first).

## Self-review notes

- Spec coverage: loader (Task 1), config.yaml + comments (Task 2), base.py rewiring (Tasks 3-5), error handling (loader code), testing (Task 1 tests + Task 6 audit), Docker path resolution (deviation from spec's parents[5], documented in Global Constraints), TELEMETRY_DB_PATH + current LLM tiers (user additions).
- Deviation from spec: bulk model is deepseek-v4-flash (spec predates the f6dd5e5 retirement of qwen-2.5-72b); path resolution is cwd-first + upward walk instead of parents[5] (Docker copies src/backend → /app/backend, changing the depth).
- `LLM_MODEL` keeps plain `os.getenv` because its fallback is the resolved `LLM_MODEL_BULK`, not a literal.

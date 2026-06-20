# Externalize Tunable Config to YAML — Design

**Date:** 2026-06-20
**Status:** Approved (design); pending spec review

## Problem

All non-secret configuration lives inline in `src/backend/shared/config/settings/base.py`
(~728 lines) as Python literals, most via the `os.getenv("VAR", default)` pattern.
Operational tunables (LLM model tiers, agent weights, thresholds, RL parameters,
regime tables, scheduler crons) are mixed into code, so changing one requires editing
a Python file. The user wants tunables in a separate human-editable config file, with
only true secrets (API keys, webhook URLs) remaining in `.env`.

## Decisions (locked)

| Decision | Choice |
|----------|--------|
| **Scope** | Tunable values only — not every constant, not just the LLM tiers |
| **Precedence** | `environment variable` > `config.yaml` > `hardcoded fallback in base.py` |
| **Format** | YAML (PyYAML 6.0.3 already pinned in `requirements.txt`) |
| **Location** | Repo root: `config.yaml` (next to `.env`) |
| **Bulk model** | Unchanged — `qwen/qwen-2.5-72b-instruct` (verified live on OpenRouter 2026-06-20) |
| **Call-site interface** | Unchanged — `settings.LLM_MODEL_FAST` etc. keep working; zero downstream edits |

### Format rationale
JSON was rejected: `base.py` carries substantial "why" comments (e.g. *"qwen3-235b
RETIRED: broke JSON output"*) that are institutional knowledge. JSON cannot hold
comments. YAML preserves comments, supports native types (int/float/bool/lists/nested
dicts — required for `REGIME_MULTIPLIERS`), and needs no new dependency.

## Architecture

Three pieces. The settings module stays the single public surface; the YAML file and
loader sit behind it.

### 1. `config.yaml` (repo root)
Holds tunable values grouped by the section headers `base.py` already uses, with the
existing explanatory comments carried over. Illustrative shape:

```yaml
llm:
  model_fast: "qwen/qwen3.6-flash"          # chat tool-loop: fast, strong tool-use
  model_reasoning: "qwen/qwen3.7-max"       # judgment calls: deepest answers
  model_bulk: "qwen/qwen-2.5-72b-instruct"  # JSON-proven bulk scoring workhorse
  temperature: 0.2
  max_tokens: 2048
  timeout_seconds: 60
  input_cost_per_m: 0.1875
  output_cost_per_m: 1.125

agent_weights:        # must sum to 1.0
  sales_demand: 0.15
  fundamentals: 0.18
  # ...

score_thresholds:     # rendered as tuples in base.py
  strong_buy: [0.75, 1.00]
  buy:        [0.55, 0.75]
  # ...

regime_multipliers:
  MACRO_CRISIS: { risk_macro: 1.40, fundamentals: 0.80, ... }
  # ...

rl: { ... }           # all RL_* tunables and flags
scheduler: { ... }    # crons, tickers, alert thresholds
```

### 2. `src/backend/shared/config/settings/loader.py` (new)
A small module that loads the YAML once at import and exposes a typed resolver.

- `load_yaml() -> dict`: locate and parse `config.yaml`.
  - Path resolution order: `CONFIG_FILE` env var (absolute path) → repo root via
    `Path(__file__).resolve().parents[5] / "config.yaml"`.
  - Missing file → return `{}` and log a one-line warning (behavior falls back to
    hardcoded defaults — byte-identical to today).
  - Malformed YAML → raise at import with a clear message (fail loud, don't run on a
    silently-broken config).
- `cfg(path, env=None, fallback=None)`: resolve one value with full precedence.
  - If `env` is set and present in the environment → return env value **coerced to the
    type of** the YAML value (or, if absent, the `fallback`).
  - Else if `path` exists in the YAML → return the YAML value (already typed by YAML).
  - Else → return `fallback`.
  - `path` is dotted (e.g. `"llm.model_fast"`) into the nested YAML dict.

**Coercion rules** (mirror the parsing `base.py` does today):
- `bool`: `"true"/"1"/"yes"` → `True`, `"false"/"0"/"no"` → `False` (case-insensitive).
- `int` / `float`: parsed; failure raises a clear error naming the key.
- `list`: comma-separated string split + strip (matches today's `SCHEDULER_TICKERS`,
  `ALERT_CHANNELS` behavior).
- `str`: passed through.
- Nested dict/list tables (e.g. `REGIME_MULTIPLIERS`) are **YAML-or-fallback only** —
  no env override (they never had one).

### 3. `base.py` (modified)
Keeps every existing module-level attribute name, sourced through `cfg(...)`:

```python
from backend.shared.config.settings.loader import cfg

LLM_MODEL_FAST      = cfg("llm.model_fast",      env="LLM_MODEL_FAST",      fallback="qwen/qwen3.6-flash")
LLM_MODEL_REASONING = cfg("llm.model_reasoning", env="LLM_MODEL_REASONING", fallback="qwen/qwen3.7-max")
LLM_MODEL_BULK      = cfg("llm.model_bulk",      env="LLM_MODEL_BULK",      fallback="qwen/qwen-2.5-72b-instruct")
LLM_MODEL           = cfg("llm.model_bulk",      env="LLM_MODEL",           fallback=LLM_MODEL_BULK)
```

Tuple-typed settings wrap the YAML list at assignment (e.g.
`SCORE_THRESHOLDS = {k: tuple(v) for k, v in cfg("score_thresholds", fallback=_DEFAULT_SCORE_THRESHOLDS).items()}`).

The 40+ consumers that do `from core.config import settings` and read
`settings.<NAME>` are **untouched**. `core/config/settings/__init__.py` remains the
migration shim re-exporting `base`.

## What moves vs. stays

**Inclusion rule:** move operational *tunables* — model selection, numeric
thresholds / weights / windows / TTLs, cron schedules, feature flags (`RL_*_ENABLED`),
token/char caps, and the nested tuning tables. Exclude structural constants tied to
code or integrations.

| Destination | Contents |
|-------------|----------|
| **`config.yaml`** | LLM tiers + params + cost rates; `AGENT_WEIGHTS`; `SCORE_THRESHOLDS`; agent execution (timeout/retries/delay); data-fetch tunables (`SERPER_MAX_QUERIES`, `NEWS_ARTICLES_PER_QUERY`, `FINANCIALS_LOOKBACK_QUARTERS`, `SERPER_TIMEOUT_SECONDS`, `TAVILY_MAX_CONTENT_CHARS`, `MACRO_CACHE_TTL_HOURS`); all `RL_*` tunables + flags; regime thresholds + `REGIME_MULTIPLIERS` + `SECTOR_AGENT_REGIME_ROLE`; scheduler crons/tickers/alert thresholds; dossier / event-ingest / research-loop params; unified-analyst params; macro-news params; close-verify params; chat review cycles |
| **stays in `base.py`** (structural) | Data-source URLs (FADA/SIAM/VAHAN/DGFT/CARS24/CARDEKHO); `YFINANCE_SUFFIX` + `YF_SYMBOL_OVERRIDES`; macro/regime ticker symbols (`CRUDE_OIL_TICKER`, `REGIME_SECTOR_TICKERS`, etc.); indicator periods (`RSI_PERIOD`, `MACD_*`, `BB_*`); output/log paths; `OPENROUTER_BASE_URL`; `NEWS_SOURCES`; fallback constants (`*_FALLBACK`) |
| **stays in `.env`** (secrets) | `OPENROUTER_API_KEY`, `SERPER_API_KEY`, `TAVILY_API_KEY`, `NEWSAPI_KEY`, `ALERT_WEBHOOK_URL`, `CSHARP_API_URL` |

**Note on previously non-env constants:** some moved values (e.g. `REGIME_MULTIPLIERS`,
regime thresholds, `RL_BOOST`/`RL_PENALTY`) were deliberately *not* env-configurable in
`base.py`. Moving them to YAML newly makes them editable without code changes — which is
the intent. Precedence still allows an env override on top where a value has an `env` key.

The exact line-by-line mapping (which is the tedious, mechanical part) is deferred to the
implementation plan.

## Error handling

- **Missing `config.yaml`** → warn once, fall back to hardcoded defaults. App still runs
  identically to today.
- **Malformed YAML** → raise at import with file path + parser error.
- **Bad type / uncoercible env value** → raise with the offending key and expected type.
- **Unknown keys in YAML** (no matching `cfg` call) → ignored (forward-compatible).
- **`AGENT_WEIGHTS` not summing to 1.0** → out of scope here; preserve whatever validation
  exists today, no new validation added (YAGNI).

## Testing

New `tests/unit/shared/test_config_loader.py`:
- Precedence: env beats YAML beats fallback.
- Coercion: bool / int / float / CSV-list from env strings.
- Missing YAML → all fallbacks returned (no crash).
- Malformed YAML → raises.
- Nested table (e.g. a small `regime_multipliers`) loads from YAML.
- Tuple wrapping for `SCORE_THRESHOLDS`.

Existing config tests (`tests/unit/shared/test_config.py`, `test_config.py`,
`test_living_envelope_settings.py`, `test_unified_analyst_settings.py`,
`tests/contract/test_phase0_llm_migration.py`) must pass **unchanged** — attribute names
and default values are preserved.

## Out of scope

- Switching any model (bulk stays `qwen-2.5-72b-instruct`).
- A model "smoke test" validating `response_format=json_object` per tier — desirable
  follow-up, tracked separately, not part of this refactor.
- Migrating structural constants or secrets.
- pydantic-settings / typed-config-object rewrite — keeps the plain-module interface.

## Risks & mitigations

- **Risk:** a consumer reads a setting we accidentally drop/rename. **Mitigation:** keep
  all attribute names identical; run the full test suite; preserved fallbacks make a
  missing YAML key non-fatal.
- **Risk:** YAML type differs from old parse (e.g. tuple vs list). **Mitigation:** explicit
  tuple wrapping at assignment; loader-coercion tests.
- **Risk:** prod (Railway) env vars stop taking effect. **Mitigation:** env retains top
  precedence by design; covered by a precedence test.

# Phase 5, 6, 7 — Implementation Plan

> Written: 2026-05-06 after deep read of all source files.
> Baseline: 323 unit tests pass (post Phase 0–4).
> Rule: Every phase ends with `pytest tests/unit/ -q` green.

---

## Phase 5 — Intelligence / RL Decomposition

### What this phase does
Extracts pure algorithmic functions out of the large RL files
(`weight_adapter.py`, `tracker.py`, `feedback_agent.py`, `ledger_propagator.py`,
`regime/detector.py`) into individually-testable files under
`src/backend/intelligence/rl/algorithms/`.
Also moves the calendar files and creates the seasonal seed YAMLs.

**Zero new logic.** Every extraction is a pure move of existing code.
The original files become thin orchestrators that import from the new files.

---

### 5-1 → 5-5 Weight Adaptation Algorithms

**Source:** `core/intelligence/rl/agents/weight_adapter.py`

Read these functions carefully before extracting:

| New file | Extracted from | Key logic |
|---|---|---|
| `weight_adaptation/bias_detector.py` | `_compute_bias_score()` lines 265–307 | Multi-window (5/10/21 trading-day) weighted miss rate: weights 0.50/0.30/0.20. Returns float 0–1. |
| `weight_adaptation/hit_rate_tracker.py` | `_compute_accuracy()` lines 200–259 + `_window_entries()` lines 180–194 | Counts direction hits/misses per agent over rolling window. Uses `trading_days_ago()` from nse_calendar. |
| `weight_adaptation/penalty_calculator.py` | `_compute_deltas()` lines 313–387 | Applies miss_type penalty multipliers, seasonal threshold shifts, timing lag tiers. Returns `{agent: delta}`. |
| `weight_adaptation/weight_normalizer.py` | `_apply_deltas()` lines 393–421 | Clamps per-agent drift (max ±0.05 single step, max ±0.15 total drift from base), then renormalizes to sum 1.0. |

**After extraction:**
- `WeightAdapter.update()` calls these 4 functions in sequence
- `WeightAdapter._trading_days_ago()` becomes a thin delegator to `nse_calendar.trading_days_ago`
- Old file keeps `update()` only — becomes the orchestrator

**Shim pattern at old paths:** NOT needed — these are internal methods, not imported externally.

**Test:** `tests/unit/intelligence/rl/test_bias_detector.py` etc. — new test files per algorithm.

---

### 5-6 → 5-8 Conviction Algorithms

**Source:** `core/intelligence/rl/conviction/tracker.py`

All 6 functions are already pure — straightforward split:

| New file | Extracted functions | Key logic |
|---|---|---|
| `conviction/streak_tracker.py` | `verdict_direction()` (line 56), `update_conviction_streak()` (line 166) | Direction classification + streak counter + flip detection |
| `conviction/reversion_prior.py` | `compute_reversion_prior()` (line 78), `compute_final_reversion_prior()` (line 143) | Formula: `min(0.25, max(0, (streak_days - 4) × 0.025))` |
| `conviction/rsi_divergence.py` | `compute_rsi_amplifier()` (line 102) | Amplifier when streak≥8 AND pattern_analysis score contradicts direction. Multiplier 1.5×, cap 0.30. |
| `conviction/warning_builder.py` | `build_streak_warning_block()` (line 226) | Builds prompt-injection string when streak ≥ 8 days |

**After extraction:** `tracker.py` becomes an `__init__.py`-style facade that imports and re-exports all 6 functions. Callers (`daily_review.py`) keep the same import path via shim.

**STREAK_WARNING_THRESHOLD** constant (currently in tracker.py) → moves to `conviction/__init__.py`.

---

### 5-9 → 5-11 Forecast Algorithms

**Source:** `core/intelligence/rl/workflows/generate_forecast.py`

These are the pure building-block functions. The orchestrator `generate_forecast()` keeps calling them:

| New file | Extracted from | Key logic |
|---|---|---|
| `forecast/price_interpolator.py` | Lines 81–108 | Verdict → monthly % assumption mapping; linear price path from `base_close` + daily `price_delta`; applies verdict direction (UP/DOWN/FLAT). |
| `forecast/confidence_decay.py` | Lines 105–107 + daily_review Step 7 | `confidence × (1 - decay_per_day × day_number)`. decay_per_day ≈ 0.005. Also wraps reversion dampening: `confidence × (1 - reversion_prior × 0.5)`. |
| `forecast/envelope_builder.py` | `_build_daily_forecasts()` lines 63–150 | Assembles list of `DailyForecast` objects: calls price_interpolator + confidence_decay + SeasonalCalendar adjustments. Self-contained given inputs. |

**`_trading_dates()`** stays in `generate_forecast.py` (thin delegator to nse_calendar) — not worth extracting.

---

### 5-12 → 5-14 Feedback Algorithms

**Source:** `core/intelligence/rl/agents/feedback_agent.py` and `stores/ledger_propagator.py`

| New file | Extracted from | Key logic |
|---|---|---|
| `feedback/miss_classifier.py` | `classify_direction()` line 59, `is_direction_correct()` line 71, `FLAT_THRESHOLD_PCT` | Pure threshold logic. `classify_direction(predicted, actual)` → "UP"/"DOWN"/"FLAT". Also holds `is_direction_correct()`. |
| `feedback/lesson_extractor.py` | `FeedbackAgent._parse()` lines 224–292 | Pure JSON → `FeedbackAgentOutput`. Validates miss_type against MissType enum. Handles backward-compat JSON parsing. Completely self-contained. |
| `feedback/lesson_merger.py` | Confidence blend from `propagate_lesson_to_ledger()` lines 71–95 + `build_tiered_lessons_summary()` lines 211–275 | Two concerns: (a) confidence blending `0.70 × existing + 0.30 × incoming` + cross-ticker boost `+0.05`; (b) tiered summary builder (TIER 1/2/3). Keep together as `lesson_merger.py`. |

**After extraction:**
- `FeedbackAgent.run()` calls `miss_classifier.is_direction_correct()` and `lesson_extractor._parse()`
- `propagate_lesson_to_ledger()` calls `lesson_merger.blend_confidence()`
- `build_tiered_lessons_summary()` → `lesson_merger.build_summary(ticker_ledger, sector_ledger, market_ledger)`

---

### 5-15 Regime Signal Extractors

**Source:** `core/intelligence/regime/detector.py`

| New file | Extracted from | Key logic |
|---|---|---|
| `regime/signals/vix.py` | `_get_vix()` lines 117–131 | Fetches `^VIX` from yfinance, 5-day history, returns latest close. Fallback to `None` on error. |
| `regime/signals/fii_proxy.py` | `_get_fii_proxy()` lines 133–149 | Fetches Nifty 50 (`^NSEI`) 10-day history, computes 5-day price momentum %. Fallback to `None`. |
| `regime/signals/sector_rsi.py` | `_get_sector_rsi()` lines 151–175 + `_compute_rsi()` lines 48–65 | Fetches sector index OHLCV, computes Wilder RSI(14) using `pandas.ewm(alpha=1/14)`. Fallback to 50. |

**`_classify()` and `_build_narrative()`** stay in `detector.py` — they're the core logic and not worth splitting further.

**After extraction:** `RegimeDetector.detect()` calls `signals.vix.fetch()`, `signals.fii_proxy.fetch()`, `signals.sector_rsi.fetch()`, then calls `self._classify(vix, fii, rsi)`.

---

### 5-16 Seasonal Seed YAMLs

Create `src/backend/intelligence/rl/seasonal/seeds/{sector}.yaml` for all 4 sectors.

**Format** (from `SeasonalPattern` schema):
```yaml
# automobile.yaml
- id: "festive_season"
  name: "Festive Season Demand Surge"
  evidence: "Oct-Nov retail dispatch historically +15-25% vs avg"
  months: [10, 11]
  day_range: null
  direction_bias: "BULLISH"
  confidence: 0.80
  agents_affected:
    sales_demand: +0.12
    sentiment: +0.06
    fundamentals: +0.04
  accuracy_threshold_delta:
    sales_demand: -0.05   # lower bar for penalty in festive months
  scope: "sector_wide"
  validated_by_rl: false
  decay_exempt: true
  lunar_dependency: false

- id: "budget_week"
  name: "Union Budget Regulatory Uncertainty"
  months: [2]
  day_range: [1, 7]
  direction_bias: "VOLATILE"
  confidence: 0.75
  agents_affected:
    policy_regulatory: -0.10
    risk_macro: -0.08
  scope: "market_wide"
  ...
```

**Seeds to create:**
- `automobile.yaml` — festive_season, budget_week, quarter_end_rebalancing, ev_policy_window, rabi_sowing_impact
- `banking_bfsi.yaml` — rbi_mpc_week, quarterly_results_week, advance_tax_outflow, fiscal_year_end_lending
- `it_sector.yaml` — us_earnings_season, quarter_end_fy_close, h1b_lottery_announcement, indian_fy_end_fresher_joining
- `renewable_energy.yaml` — monsoon_impact, budget_mnre_allocation, year_end_discom_payment_rush, solar_irradiance_peak

---

### 5-17 → 5-18 Calendar File Moves

**Simple copies + shims:**

```
core/intelligence/rl/nse_calendar.py     → src/backend/intelligence/rl/calendar/nse_calendar.py
core/intelligence/rl/calendar_updater.py → src/backend/intelligence/rl/calendar/updater.py
```

Fix imports in the new `updater.py`:
- `from core.intelligence.rl.nse_calendar import reload_holidays` → `from backend.intelligence.rl.calendar.nse_calendar import reload_holidays`

Shim old paths:
```python
# core/intelligence/rl/nse_calendar.py
from backend.intelligence.rl.calendar.nse_calendar import *
from backend.intelligence.rl.calendar.nse_calendar import is_trading_day, trading_days_ago, next_trading_day, trading_dates, reload_holidays
```

---

### 5-19 Tests

After each extraction group, add unit tests:

```
tests/unit/intelligence/rl/
  test_bias_detector.py        # test _compute_bias_score with synthetic entries
  test_hit_rate_tracker.py     # test direction hit counting over rolling windows
  test_penalty_calculator.py   # test miss_type multipliers + seasonal shifts
  test_weight_normalizer.py    # test bounds clamping + sum-to-1 normalization
  test_streak_tracker.py       # test streak direction flip + reset
  test_reversion_prior.py      # test formula at breakpoints (4d=0, 5d=0.025, 14d=0.25)
  test_rsi_divergence.py       # test amplifier conditions + cap at 0.30
  test_miss_classifier.py      # test FLAT_THRESHOLD_PCT boundary cases
  test_lesson_extractor.py     # test JSON parse with valid + malformed LLM output
  test_lesson_merger.py        # test confidence blend formula + cross-ticker boost
  test_regime_signals.py       # mock yfinance; test RSI Wilder formula
  test_nse_calendar.py         # already exists — verify reload_holidays still works
```

---

## Phase 6 — Chatbot Architecture

### What this phase does
Extracts the `/ui/chat` endpoint logic out of the monolithic `ui_data.py`
into a proper `chat/` module with intent detection and entity extraction.
The endpoint in `ui_data.py` becomes a thin 5-line delegator.

### Current state (ui_data.py `/ui/chat`)
```python
# Current flat structure:
async def chat(body: dict) -> dict:
    message = body.get("message")
    history = body.get("history") or []
    ticker_context = build_ticker_context_from_db()   # enriched with DB verdicts
    system_prompt = "You are StockAgent... " + ticker_context
    messages = [system] + history[-6:] + [user]
    reply = await call_llm(messages)
    return {"reply": reply}
```

### 6-1: `src/backend/intelligence/chat/engine.py`

The main entry point. Routes message to the right handler based on detected intent:

```python
class ChatEngine:
    async def reply(self, message: str, history: list[dict]) -> str:
        intent = IntentDetector.classify(message)
        entities = EntityExtractor.extract(message)
        context = TickerContext.build(entities.tickers)
        system = SystemPromptBuilder.build(intent, entities, context)
        messages = self._merge_history(system, history, message)
        return await self._call_llm(messages)
```

### 6-2: `chat/context/ticker_context.py`

```python
class TickerContext:
    @staticmethod
    def build(tickers: list[str]) -> str:
        """
        Pull latest FinalReport verdicts from DB for the mentioned tickers.
        Falls back to all tickers if none extracted.
        Returns formatted string for system prompt injection.
        """
        store = ScoreStore()
        rows = store.get_all_latest()
        # filter to mentioned tickers if any
        # format: "MARUTI: BUY (score=0.82)\nTATAMOTORS: NEUTRAL (score=0.61)"
```

### 6-3: `chat/context/history_context.py`

```python
class HistoryContext:
    MAX_TURNS = 6  # caps at last 6 turns for token budget

    @staticmethod
    def prepare(history: list[dict]) -> list[dict]:
        """
        Validate, filter, and cap conversation history.
        Each item must have role in (user, assistant) and content str.
        """
```

### 6-4: `chat/algorithms/intent_detector.py`

**Pure function — no external calls. Regex + keyword matching.**

```python
class IntentDetector:
    INTENTS = {
        "compare_tickers":   regex patterns like "compare X vs Y", "X or Y"
        "explain_agent":     "what does {agent_name} do", "explain sales demand"
        "score_query":       "score", "rating", "verdict" for a ticker
        "predict":           "will X go up", "target price", "forecast"
        "analyze":           "analyze X", "run analysis", "should I buy"
        "generic":           fallback
    }

    @staticmethod
    def classify(message: str) -> str:
        """Returns one of the INTENTS keys."""
```

**Test (6-8):** `IntentDetector.classify("compare MARUTI vs TATAMOTORS")` → `"compare_tickers"`.

### 6-5: `chat/algorithms/entity_extractor.py`

**Pure function — no external calls. Pattern matching against known ticker + agent lists.**

```python
class EntityExtractor:
    KNOWN_TICKERS = {"MARUTI", "TATAMOTORS", "M&M", ...}  # from sector settings
    KNOWN_AGENTS  = {"sales_demand", "fundamentals", "pattern_analysis", ...}

    @dataclass
    class Entities:
        tickers: list[str]
        agents:  list[str]
        sector:  str | None

    @staticmethod
    def extract(message: str) -> Entities:
        """
        Extract NSE tickers and agent names from free-text.
        Also detects sector context ("banking", "IT stocks", "renewable").
        """
```

**Test (6-8):** `EntityExtractor.extract("compare MARUTI vs TATAMOTORS")` → `Entities(tickers=["MARUTI", "TATAMOTORS"], agents=[], sector="automobile")`.

### 6-6: `chat/prompts/system.py`

```python
class SystemPromptBuilder:
    BASE = (
        "You are StockAgent, an AI assistant specialising in Indian stocks. "
        "You have 9+ specialist agents across 4 sectors: automobile, banking BFSI, "
        "IT, and renewable energy. Answer concisely (2-4 sentences max)."
    )

    @staticmethod
    def build(intent: str, entities: Entities, context: str) -> str:
        """
        Builds intent-aware system prompt.
        For compare_tickers: explicitly instructs comparison format.
        For explain_agent: focuses on the specific agent's role.
        For predict: adds disclaimer about forward-looking statements.
        """
```

### 6-7: Wire into `/ui/chat`

After extraction, the endpoint becomes:
```python
@router.post("/ui/chat")
async def chat(body: dict) -> dict:
    from backend.intelligence.chat.engine import ChatEngine
    reply = await ChatEngine().reply(
        message=body.get("message", ""),
        history=body.get("history") or [],
    )
    return {"reply": reply}
```

### 6-8: Tests

```
tests/unit/intelligence/chat/
  test_intent_detector.py    # 8 test cases covering each intent + edge cases
  test_entity_extractor.py   # tickers, agents, sector, multi-entity messages
  test_system_prompt.py      # verify intent-specific prompt fragments present
```

---

## Phase 7 — Shared Data Layer

### What this phase does
Moves `services/data/`, `services/clients/`, `services/api/`, `services/scheduler/`
to their permanent homes under `src/backend/`. Also implements the sector-specific
fetcher stubs left from Phase 4. Removes all migration shims.

**This is the biggest phase — most files move, all shims clean up.**

---

### 7-1 → 7-4: Move shared data infrastructure

**Pattern for each:** copy to new path → fix imports → shim old path → test.

| Old path | New path |
|---|---|
| `services/data/fetchers/fundamentals.py` | `src/backend/shared/data/fetchers/fundamentals.py` |
| `services/data/fetchers/macro.py` | `src/backend/shared/data/fetchers/macro.py` |
| `services/data/fetchers/news.py` | `src/backend/shared/data/fetchers/news.py` |
| `services/data/stores/score_store.py` | `src/backend/shared/data/stores/score_store.py` |
| `services/data/stores/run_logger.py` | `src/backend/shared/data/stores/run_logger.py` |
| `services/data/stores/analysis_logger.py` | `src/backend/shared/data/stores/analysis_logger.py` |
| `services/data/stores/api_usage.py` | `src/backend/shared/data/stores/api_usage.py` |
| `services/data/cache/macro_cache.py` | `src/backend/shared/data/cache/macro_cache.py` |
| `services/data/context/builder.py` | `src/backend/shared/data/context/builder.py` |
| `services/clients/llm_client.py` | `src/backend/shared/clients/llm_client.py` |
| `services/clients/tavily_fetcher.py` | `src/backend/shared/clients/tavily_fetcher.py` |
| `services/clients/alerting.py` | `src/backend/shared/clients/alerting.py` |

**Import fixes in each new file:**
- `from core.config import settings` → `from backend.shared.config import settings`
- `from core.schemas.pipeline import ...` → `from backend.shared.schemas.pipeline import ...`

---

### 7-5 → 7-8: Implement sector-specific fetchers (stubs → real)

These were created as stubs in Phase 4. Implement them now that the shared fetchers are in place:

**7-5: `src/backend/sectors/automobile/data/fetchers/vahan_fada.py`**
```python
def get_vahan_ev_data(month: str, year: int) -> str:
    """
    Fetch VAHAN EV registration data for Indian states.
    Source: Serper news search ("Vahan EV registration {month} {year}")
    Returns formatted string with EV segment breakdown.
    """
    # Use fetch_news_context() from shared/data/fetchers/news.py

def get_fada_dispatch_data(month: str, year: int) -> str:
    """
    Fetch FADA retail auto dispatch data.
    Source: Serper news search ("FADA retail dispatch {month} {year}")
    """
```

**7-6: `src/backend/sectors/banking_bfsi/data/fetchers/rbi_data.py`**
```python
def get_rbi_policy_context(year: int) -> str:
    """
    Fetch RBI MPC decisions and repo rate from Serper news.
    Note: repo rate is currently hardcoded in macro.py — this replaces it.
    """

def get_npa_nim_context(ticker: str) -> str:
    """
    Fetch NPA, NIM quarterly data from news (BSE/NSE filings via Serper).
    """
```

**`src/backend/sectors/banking_bfsi/data/fetchers/npa_metrics.py`**
```python
def get_quarterly_npa_nim(ticker: str, quarter: str) -> str:
    """Structured quarterly NPA/NIM extraction via Tavily (full-page PDFs)."""
```

**7-7: `src/backend/sectors/it_sector/data/fetchers/deal_wins.py`**
```python
def get_deal_wins(company_name: str, quarter: str) -> str:
    """
    Fetch IT deal win announcements (TCV, client, vertical) via Serper + Tavily.
    """

def get_deal_pipeline(company_name: str, year: int) -> str:
    """Fetch deal pipeline health via news."""
```

**`src/backend/sectors/it_sector/data/fetchers/transcript.py`**
```python
def get_earnings_transcript(company_name: str, quarter: str) -> str:
    """
    Fetch earnings call transcript excerpts via Tavily full-page extraction.
    Target URLs: NSE website earnings transcripts, company IR pages.
    """
```

**7-8: `src/backend/sectors/renewable_energy/data/fetchers/mnre_data.py`**
```python
def get_mnre_auction_data(year: int) -> str:
    """
    Fetch MNRE solar/wind auction results (GW awarded, tariff L1) via Tavily.
    Target URL: mnre.gov.in/tenders
    """

def get_discom_payment_status(state: str | None = None) -> str:
    """Fetch DISCOM payment delays from PRAAPTI portal news."""
```

---

### 7-9 → 7-10: Move API and scheduler

| Old path | New path |
|---|---|
| `services/api/server.py` | `src/backend/api/server.py` |
| `services/api/routes/*.py` | `src/backend/api/routes/*.py` |
| `services/scheduler/python/scheduler.py` | `src/backend/scheduler/python/scheduler.py` |
| `services/scheduler/run_schedule.py` | `src/backend/scheduler/run_schedule.py` |

**Critical:** `server.py` imports everything — must fix all imports before moving.
Run the import map first: `grep -r "from services.api\|from services.scheduler" --include="*.py"`.

---

### 7-11: Remove all migration shims

After Phase 7 moves are complete and all imports updated:

**Shims to delete:**
```
core/schemas/pipeline.py          → delete (shim)
core/schemas/feedback.py          → delete (shim)
core/config/settings/base.py      → delete (shim)
core/config/settings/__init__.py  → delete (shim)
core/config/rag_config.py         → delete (shim)
core/config/prompts/automobile/*.py → delete (shims)
core/graphs/nodes.py              → delete (shim)
core/graphs/rails.py              → delete (shim)
core/graphs/state.py              → delete (shim)
core/pipeline/base_agent.py       → delete (shim)
core/pipeline/orchestrator.py     → delete (shim)
core/pipeline/signal_aggregator.py → delete (shim)
core/sectors/automobile/*.py      → delete (shims)
core/sectors/banking/agents.py    → delete (shim)
core/sectors/it/agents.py         → delete (shim)
core/sectors/renewable/agents.py  → delete (shim)
services/data/fetchers/*.py       → delete (shims, after Phase 7-1)
services/data/stores/*.py         → delete (shims, after Phase 7-2)
services/data/cache/*.py          → delete (shims, after Phase 7-3)
services/clients/*.py             → delete (shims, after Phase 7-4)
services/api/                     → delete (shims, after Phase 7-9)
services/scheduler/               → delete (shims, after Phase 7-10)
```

**After deletion, run:** `python -m pytest tests/ -q` — full suite must pass.

---

### 7-12: Full test suite

```bash
python -m pytest tests/ -q --tb=short
```

Minimum bar: **323 unit tests + any new tests from Phases 5-6 pass**.

---

## Execution Order Summary

```
Phase 5 (RL decomposition — no new logic, pure extractions):
  5-1 to 5-5:   Weight adaptation algorithms (4 files)   ← start here, lowest risk
  5-6 to 5-8:   Conviction algorithms (4 files)           ← all pure, easy
  5-9 to 5-11:  Forecast algorithms (3 files)             ← mostly pure
  5-12 to 5-14: Feedback algorithms (3 files)             ← includes LLM-adjacent code
  5-15:         Regime signals (3 files)                  ← wraps yfinance calls
  5-16:         Seasonal seed YAMLs (4 files)             ← new content
  5-17 to 5-18: Calendar moves (2 files + shims)          ← simple moves
  5-19:         Write unit tests for extracted algorithms

Phase 6 (chatbot — mostly new code, small extraction from ui_data.py):
  6-1 to 6-3:   Engine + context modules (3 files)        ← new code
  6-4 to 6-5:   Intent + entity algorithms (2 files)      ← pure, testable
  6-6:          System prompt builder (1 file)             ← new code
  6-7:          Wire into /ui/chat                         ← 5-line change
  6-8:          Unit tests

Phase 7 (data layer — most files move, all shims removed):
  7-1 to 7-4:   Shared infrastructure (12 files)          ← careful with imports
  7-5 to 7-8:   Implement sector fetchers (7 files)       ← new real code
  7-9 to 7-10:  API + scheduler (5 files)                 ← largest blast radius
  7-11:         Delete all shims                          ← final cleanup
  7-12:         Full test suite green
```

---

## Risk Flags

| Risk | File | Mitigation |
|---|---|---|
| `weight_adapter._compute_deltas` is 75 lines with seasonal shifts + timing tiers | Extracting to `penalty_calculator.py` | Read every line; keep `seasonal_threshold_deltas` as a parameter |
| `generate_forecast._build_daily_forecasts` calls `SeasonalCalendar` inline | Extracting to `envelope_builder.py` | Pass `seasonal_ctx` as argument — don't import SeasonalCalendar inside the pure function |
| `FeedbackAgent._parse()` has backward-compat JSON handling for old field names | Extracting to `lesson_extractor.py` | Copy verbatim; add a test for the old format |
| `services/api/server.py` lifespan imports from everywhere | Phase 7-9 | Generate full import map before moving; update one import at a time |
| Removing shims in Phase 7-11 breaks any code that was missed | Phase 7-11 | Run `grep -r "from core\.\|from services\." --include="*.py"` before deleting; must return zero results |

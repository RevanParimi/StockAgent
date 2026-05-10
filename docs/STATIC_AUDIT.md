# Static Values Audit — StockAgent

> Ownership: Claude (ongoing review responsibility)
> Last updated: 2026-05-10
> Scope: All hardcoded/static values that should be dynamic, adaptive, or data-driven.
> Severity: CRITICAL → HIGH → MEDIUM → LOW

---

## CRITICAL — Fix immediately

### 1. RBI Repo Rate — `services/data/fetchers/macro.py`
```python
"repo_rate_pct": "6.50",       # hardcoded — stale since Feb 2024
"last_change":   "2024-02-08",
```
**Problem:** Repo rate drives banking sector macro analysis. 16+ months stale by May 2026.
**Fix:** Set `RBI_REPO_RATE_PCT` env var to override. Staleness warning fires if value is >90 days old.
Long-term: automate via Serper search or RBI press release scrape.
**Status:** ✅ Fixed (2026-05-10) — env-override + staleness warning in `get_rbi_repo_rate()`

---

## HIGH — Address in next sprint

### 2. Ticker lists duplicated across 3 places
| File | List | Count | Registry count |
|---|---|---|---|
| `sectors/__init__.py` | `_BANKING` frozenset | 19 | — |
| `banking_bfsi/config/settings.py` | `TICKERS` | 7 | 19 |
| `it_sector/config/settings.py` | `TICKERS` | 7 | 15 |
| `renewable_energy/config/settings.py` | `TICKERS` | 6 | 12 |

**Problem:** Sector settings lists are a subset of the registry. New tickers added to one place don't flow to others.
**Fix:** `TICKER_SECTOR` in `src/backend/sectors/registry.py` is now the single source of truth for routing (~200 tickers, all 27 sectors). The frozensets in `__init__.py` are superseded — `detect_sector()` is now a shim through `SectorRegistry.resolve()`.
Sector `settings.TICKERS` (for scheduling) remain separate; they are intentionally smaller subsets for scheduler load control.
**Status:** ✅ Routing fixed (2026-05-10) — `TICKER_SECTOR` is single source; `settings.TICKERS` kept as scheduler subset

### 3. Regime thresholds & multipliers — `settings/base.py` lines 293–385
54 hardcoded float values:
- `VIX_VOLATILE_THRESHOLD = 22.0` — no historical basis for NSE
- `FII_PROXY_THRESHOLD_PCT = 1.0` — assumes FII flows are ≥1% swing on NSE
- 6 regime × 9 agent weight multiplier table

**Problem:** NSE VIX behaves differently from CBOE VIX. Values from classical technical analysis, not calibrated to India markets. No audit trail.
**Fix:** Move to `data/regime_config.json`. Load at startup. Add `/ui/admin/regime` endpoint to hot-update.
**Status:** ⚠️ Partially done — values are now env-overridable via `settings/base.py` but the `regime_config.json` file and `/ui/admin/regime` hot-update endpoint are NOT yet built. The 54 values remain uncalibrated to NSE.

### 4. RL weight delta constants — `core/intelligence/rl/agents/weight_adapter.py`
```python
_BOOST               = +0.02
_PENALTY             = -0.03
_MISS_STREAK_PENALTY = -0.05
_BIAS_TRIGGER        = 0.55
_BIAS_FULL           = 0.70
_TIMING_FREE_WINDOW  = 3
_TIMING_PARTIAL_WINDOW = 7
```
**Problem:** Same delta applied to all stocks regardless of volatility.
**Fix:** All 7 constants moved to `settings/base.py` as `RL_BOOST`, `RL_PENALTY`, etc. with env override support.
`weight_adapter.py` now reads from `settings` instead of hardcoded module globals.
**Status:** ✅ Fixed (2026-05-10) — env-overridable via `RL_BOOST`, `RL_PENALTY` etc.

### 5. RL_FLAT_THRESHOLD_PCT missing from base.py
`feedback_agent.py` references `settings.RL_FLAT_THRESHOLD_PCT` but it's not in `base.py`.
Falls back to hardcoded `0.3` with a `try/except AttributeError`.
**Fix:** Add `RL_FLAT_THRESHOLD_PCT: float = float(os.getenv("RL_FLAT_THRESHOLD_PCT", "0.3"))` to `base.py`.
**Status:** ✅ Fixed below

### 6. NSE holiday calendar coverage ends 2026 — `core/intelligence/rl/nse_calendar.py`
28 dates, 2026 entries marked `# (approx)`. No 2027 entries.
**Problem:** `calendar_updater.py` runs Dec 31 to fetch next year. If that job fails, 2027 is unprotected.
**Fix:** Add fallback: if update fails, log CRITICAL alert. Improve `calendar_updater.py` with retry logic.
**Status:** ⬜ Pending (monitor Dec 31 run)

---

## MEDIUM — Phase 5–6 backlog

### 7. Score verdict thresholds identical across all sectors — `settings/base.py`
```python
SCORE_THRESHOLDS = {
    "strong_buy": (0.75, 1.00),
    "buy":        (0.55, 0.75),
    ...
}
```
**Problem:** Banking fundamentals score ≠ Renewable energy fundamentals score. Same cutoff is wrong.
**Fix:** Add `SECTOR_SCORE_THRESHOLDS` dict per sector in each `sectors/*/config/settings.py`.

### 8. Technical indicator periods not validated for NSE
`RSI_PERIOD=14, MACD_FAST=12, MACD_SLOW=26, BB_PERIOD=20` — industry defaults, never backtested on NSE.
**Fix:** Run backtest comparing 14 vs 9 RSI, 12/26 vs 8/17 MACD on NSE auto/banking tickers. Store results.

### 9. Sector news search hardcoded to India region
`"gl": "in"` in Serper queries. IT sector earns 80%+ revenue from US/EU — India-only news misses material events.
**Fix:** Removed `"gl"` parameter entirely from the Serper request. A specific query like
`"TCS Q4 2026 deal wins"` lets Google rank results globally by relevance — no country
restriction means Indian, US, and global sources all surface naturally.
**Status:** ✅ Fixed (2026-05-10) — `"gl"` param removed from `news.py`; no per-sector config needed

### 10. Miss type penalty multipliers — `schemas/feedback.py`
`external_shock: 0.0` — no penalty ever. But an agent that consistently fails to price in geopolitical risk is still a weak agent.
**Fix:** After 3 consecutive `external_shock` misses on same agent, apply 0.1× penalty. Make configurable.

### 11. Scheduler tickers only 5 by default — `settings/base.py`
Default `SCHEDULER_TICKERS = "MARUTI,TATAMOTORS,M&M,HEROMOTOCO,BAJAJ-AUTO"`.
Managed tickers in `data/managed_tickers.json` are the right source of truth.
**Fix:** Scheduler should read from `managed_tickers.json` at runtime, not from env var.
**Status:** ⚠️ Partially done — `_active_tickers()` in scheduler.py reads managed_tickers.json with fallback to `settings.SCHEDULER_TICKERS`. Fallback still defaults to 5 auto tickers, not the full managed set.

### 12. Category stock counts hardcoded — `services/api/routes/ui_data.py`
`"count": 5` etc. hardcoded. When tickers are added/removed via `/ui/categories`, count doesn't update.
**Status:** ✅ Fixed — `count` is now computed from `_load_category_tickers()` dynamically.

### 13. Macro cache TTL not derived from loop interval — `settings/base.py`
`MACRO_CACHE_TTL_HOURS = 4` matched `MICRO_CYCLES_PER_DAY = 6` by coincidence. If one changed, they diverged.
**Fix:** `MACRO_CACHE_TTL_HOURS = int(24 // MICRO_CYCLES_PER_DAY)` — derived, not hardcoded.
**Status:** ✅ Fixed (2026-05-10)

### 14. Agent parse failure returns 0.5 (silent neutral) — `base_agent.py`
When LLM JSON is unparseable, agent scores default to 0.5 without alerting.
**Fix:** Return explicit error state (`AgentOutput.error = "parse_failed"`), exclude from aggregation, log WARNING.

---

## LOW — Technical debt backlog

| # | Issue | File | Fix |
|---|---|---|---|
| 15 | Serper timeout hardcoded 10s | `news.py:63` | ✅ Fixed — `settings.SERPER_TIMEOUT_SECONDS` (env override) |
| 16 | Tavily content truncated at 600 chars | `tavily_fetcher.py:131` | ✅ Fixed — `settings.TAVILY_MAX_CONTENT_CHARS` (env override) |
| 17 | `data_freshness` field logged but no staleness threshold | `base_agent.py` | Add `DATA_FRESHNESS_WARN_DAYS` to settings |
| 18 | PRICE_HISTORY_YEARS=10 assumes data exists | `settings/base.py` | Validate against listing date at analysis time |
| 19 | Fallback weight 0.10 in ui_data.py | `ui_data.py:321` | Use sector base weights as fallback |
| 20 | Feedback LLM temperature 0.3 | `feedback_agent.py:56` | Move to `settings.FEEDBACK_LLM_TEMPERATURE` |

---

## Already dynamic (good) ✅

- `LLM_MODEL` — env override supported
- `FORECAST_HORIZON_DAYS` — env override
- `FEEDBACK_CRON` — env override
- `OPENROUTER_API_KEY`, `SERPER_API_KEY`, `TAVILY_API_KEY` — env
- `MACRO_CACHE_TTL_HOURS` — derived from `24 // MICRO_CYCLES_PER_DAY` (fixed #13)
- `SERPER_MAX_QUERIES` — env override
- NSE holiday calendar — auto-refreshes Dec 31
- Agent weights — user-adjustable via `/ui/agents/weights`
- Category tickers — user-adjustable via `/ui/categories/{key}/tickers`
- Managed tickers — user-adjustable via `/ui/tickers/managed`
- Symbol resolution in chat — now 3-tier (static → direct → yfinance.Search)
- Chat intent routing — now LLM-driven tool selection

---

## Ownership & Review Schedule

| Cadence | Action |
|---|---|
| Every deploy | Verify `RL_FLAT_THRESHOLD_PCT` in settings, RBI rate freshness (set `RBI_REPO_RATE_PCT` env var after each MPC decision) |
| Monthly | Review regime multiplier table vs actual VIX/FII behaviour (#3) |
| Quarterly | Re-validate technical indicator periods against NSE backtest (#8) |
| Dec 31 | Monitor `calendar_updater.py` run for 2027 holiday fetch (#6) |
| Next sprint | Build `regime_config.json` + `/ui/admin/regime` hot-update endpoint (#3) |
| Next sprint | Fix agent parse failure to return explicit error state instead of silent 0.5 (#14) |
| Next sprint | Add sector-specific `SCORE_THRESHOLDS` per sector settings.py (#7) |

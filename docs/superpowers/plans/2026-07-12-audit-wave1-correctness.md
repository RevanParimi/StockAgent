# Audit Wave 1 — Correctness Remediation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the 17 correctness findings from audit Phases 1+2 (spec: docs/superpowers/specs/2026-07-12-audit-wave1-correctness-design.md) so the Mon 2026-07-13 16:30 IST scheduled run reviews, advises, and trades correctly and safely.

**Architecture:** Critical-section file locking (`filelock`) around every portfolio read-modify-write with a fresh reload inside the executor; the missing scheduler→pipeline hook; corrected + self-healing holiday calendar (union merge); dividends as real cash events (`DIV` ledger rows); detect-only reconciler + ops alerts through the existing push channel.

**Tech Stack:** Python 3.11, FastAPI, APScheduler, pydantic, filelock (new), pytest.

## Global Constraints

- Worktree branch `audit/wave1-correctness`; per-task commits; full suite baseline **1875 passed / 5 skipped** (plus known pre-existing contract/integration failures per AUD-022) must not regress.
- Report-first ends here: this wave FIXES; every fix cites its AUD id in the commit message.
- No behavior changes to advisor decision logic (AUD-047/048 deferred to Phase 4). No dead-code deletion (Phase 6). No auth changes (AUD-012 ON HOLD).
- All new failure paths are non-fatal (log + alert), matching the house pattern: pipeline errors are telemetry.
- IST is the reference clock for "today" everywhere a date guard is added (`nse_calendar.now_ist().date()`).

---

### Task 1: Lock infrastructure (AUD-001 core)

**Files:**
- Modify: `requirements.txt` (add `filelock>=3.13`)
- Modify: `core/portfolio/store.py`
- Test: `tests/unit/test_portfolio_locking.py` (new)

**Interfaces:**
- Produces: `PortfolioStore.locked()` context manager (re-entrant, per-user lock file `<user_dir>/portfolio.lock`, timeout 30 s); store RMW helpers (`add_holding`, `remove_holding`, `add_watchlist`, `remove_watchlist`, `reduce_holding`) internally acquire the same lock.

- [ ] Write failing tests:

```python
# tests/unit/test_portfolio_locking.py
import json, multiprocessing as mp
from backend.shared.schemas.portfolio import Holding
from core.portfolio.store import PortfolioStore

def _h(sym="MARUTI", qty=10.0):
    return Holding(symbol=sym, sector="automobile", qty=qty, avg_buy_price=100.0,
                   adj_avg_price=100.0, adj_qty=qty, buy_date="2026-07-01")

def test_locked_is_reentrant(tmp_path):
    s = PortfolioStore(user_id="u1", base_dir=str(tmp_path))
    with s.locked():
        with s.locked():          # same instance: must not deadlock
            s.add_holding(_h())   # internal lock: must not deadlock
    assert s.load().holdings[0].symbol == "MARUTI"

def _worker(base_dir, n):
    s = PortfolioStore(user_id="u1", base_dir=base_dir)
    for i in range(n):
        s.add_holding(_h(sym=f"SYM{i}", qty=1.0))  # merge lots on same symbols

def test_cross_process_add_holding_is_atomic(tmp_path):
    procs = [mp.Process(target=_worker, args=(str(tmp_path), 20)) for _ in range(2)]
    [p.start() for p in procs]; [p.join(30) for p in procs]
    p = PortfolioStore(user_id="u1", base_dir=str(tmp_path)).load()
    # 2 procs × 20 adds of qty 1 across SYM0..SYM19 → each symbol qty exactly 2
    assert {h.symbol: h.qty for h in p.holdings} == {f"SYM{i}": 2.0 for i in range(20)}
```

- [ ] Run: `python -m pytest tests/unit/test_portfolio_locking.py -v` — expect FAIL (`locked` not defined / lost updates).
- [ ] Implement: `pip install filelock` + requirements line. In `PortfolioStore.__init__`: `self._lock = FileLock(str(self._dir / "portfolio.lock"), timeout=30)`. Add:

```python
from contextlib import contextmanager
from filelock import FileLock

@contextmanager
def locked(self):
    """Re-entrant per-user critical section for read-modify-write sequences."""
    with self._lock:
        yield self
```

Wrap the bodies of `add_holding`, `remove_holding`, `add_watchlist`, `remove_watchlist`, `reduce_holding` in `with self._lock:` (same instance → re-entrant under an outer `locked()`).
- [ ] Run tests → PASS. Full store tests: `python -m pytest tests/unit/test_portfolio_store.py tests/unit/test_autopilot_store.py -q` → PASS.
- [ ] Commit: `fix(portfolio): per-user file locking for portfolio RMW (AUD-001)`

### Task 2: Schema guards + DIV side (AUD-002, prep for 045)

**Files:**
- Modify: `src/backend/shared/schemas/portfolio.py`
- Test: `tests/unit/test_portfolio_schemas.py` (extend)

**Interfaces:**
- Produces: `Holding.sell` raises on `adj_qty <= 0`; `TransactionRecord.side: Literal["BUY", "SELL", "DIV"]`.

- [ ] Tests: `Holding(...adj_qty=0...).sell(1e-10, 100.0)` raises ValueError; `TransactionRecord(..., side="DIV", qty=0.0, ...)` validates.
- [ ] Implement: sell guard `if sell_qty <= 0 or self.adj_qty <= 0 or sell_qty > self.adj_qty + 1e-9: raise ValueError(...)`; widen the side literal.
- [ ] Run schema tests → PASS. Commit: `fix(schemas): sell zero-qty guard + DIV transaction side (AUD-002, AUD-045 prep)`

### Task 3: Executor — fresh reload, price guards, one price basis, future refusal (AUD-001/003/004/044-defense)

**Files:**
- Modify: `core/portfolio/autopilot.py`
- Test: `tests/unit/test_autopilot_executor_sells.py`, `tests/unit/test_autopilot_executor_switch.py` (extend)

**Interfaces:**
- Consumes: `store.locked()` (Task 1).
- Produces: `execute_advice` reloads under lock and RETURNS the fresh portfolio's txns (signature unchanged); executed prices written into `closes`; refuses `review_date > today-IST` (returns `[]`, no marker stamp); `record_value_point` skips future dates.

- [ ] Tests (extend):

```python
def test_execute_advice_refuses_future_date(tmp_path): ...   # marker unchanged, no txns
def test_execute_advice_uses_fresh_portfolio(tmp_path):
    # load p1, then delete the holding via a second store handle, then
    # execute_advice(store, p1_stale, [EXIT advice], ...) → no txn (holding gone)
def test_sell_skipped_on_nonpositive_price(tmp_path): ...    # closes {} + rec.close=0 → no txn
def test_executed_price_lands_in_closes(tmp_path): ...       # SWITCH buy: closes[cand] == close_on price
def test_record_value_point_skips_future_date(tmp_path): ...
```

- [ ] Implement in `execute_advice`: gate on `settings.AUTOPILOT_ENABLED` only, then:

```python
day = review_date.isoformat()
today = now_ist().date().isoformat()      # from core.intelligence.rl.nse_calendar
if day > today:
    logger.warning("[autopilot] refusing future review_date %s", day)
    return []
with store.locked():
    portfolio = store.load()              # fresh state — AUD-001
    if not portfolio.autopilot or portfolio.cash_deployable is None:
        return []
    if portfolio.last_autopilot_run and day <= portfolio.last_autopilot_run:
        return []
    ...existing sell/buy logic, txn append, marker stamp, save...
```

Sell price guard: `if price is None or price <= 0: logger.warning(...); continue`. Price feedback at all three execution sites: `closes.setdefault(sym, price)` (sells/ADDs) and `closes[cand] = price` (SWITCH buy). `record_value_point`: `if review_date > now_ist().date(): return None`.
- [ ] Run: `python -m pytest tests/unit/test_autopilot_executor_sells.py tests/unit/test_autopilot_executor_adds.py tests/unit/test_autopilot_executor_switch.py tests/unit/test_autopilot_pipeline.py -q` → PASS.
- [ ] Commit: `fix(autopilot): fresh reload under lock, price guards, single price basis, future-date refusal (AUD-001/003/004/044)`

### Task 4: Scheduler hook + cron + holiday-aware review dates (AUD-043/038/051)

**Files:**
- Modify: `services/scheduler/python/scheduler.py` (docstring line 12, `_daily_review_job` lines 464-522), `src/backend/shared/config/settings/base.py:298`, `services/api/routes/scheduler_api.py:65-70`
- Test: `tests/unit/test_scheduler_portfolio_hook.py` (extend — REAL hook test)

**Interfaces:**
- Produces: `_daily_review_job` derives `review_date = trading_days_ago(now_ist().date(), 1)` and calls `run_post_review_pipeline(review_date)` non-fatally at the end; `FEEDBACK_CRON` default `"30 16 * * mon-fri"`; `scheduler_api._last_trading_day()` holiday-aware.

- [ ] Test (the real one — patch source-module attrs; use one ticker so the thread pool isn't empty):

```python
def test_scheduled_daily_review_job_triggers_pipeline(monkeypatch):
    import services.scheduler.python.scheduler as sch
    import core.intelligence.rl.workflows.daily_review as dr
    import core.portfolio.pipeline as pl
    calls = {}
    monkeypatch.setattr(dr, "run_daily_review",
                        lambda t, d, sector=None: {"status": "completed"})
    monkeypatch.setattr(pl, "run_post_review_pipeline",
                        lambda d: calls.setdefault("date", d) or {"status": "completed"})
    monkeypatch.setattr(sch, "get_active_tickers_with_sector",
                        lambda: [{"sym": "MARUTI", "sector": "automobile"}])
    sch.AutomobileScheduler()._daily_review_job()
    assert "date" in calls          # the hook fired from the SCHEDULED job
```

- [ ] Run → FAIL (`calls` empty). Implement: replace weekend-only stepping (473-475) with `trading_days_ago(datetime.now(IST).date(), 1)`; append after the executor loop, before the done-banner:

```python
try:
    from core.portfolio.pipeline import run_post_review_pipeline
    summary = run_post_review_pipeline(review_date)
    logger.info("[Scheduler] Post-review portfolio pipeline: %s", summary)
except Exception as exc:
    logger.error("[Scheduler] Post-review portfolio pipeline FAILED (non-fatal): %s",
                 exc, exc_info=True)
```

`FEEDBACK_CRON` fallback → `"30 16 * * mon-fri"`; fix comments (scheduler.py:12, base.py). `scheduler_api._last_trading_day` → `return trading_days_ago(now_ist().date(), 1)`.
- [ ] Run hook + scheduler tests → PASS. Commit: `fix(scheduler): wire post-review pipeline into cron job, correct FEEDBACK_CRON, holiday-aware review dates (AUD-043/038/051)`

### Task 5: Route future-date guards (AUD-044)

**Files:**
- Modify: `services/api/routes/portfolio_api.py` (run_advisor), `services/api/routes/scheduler_api.py` (trigger_daily_review)
- Test: `tests/unit/test_portfolio_api.py`, `tests/unit/test_autopilot_api.py` (extend)

- [ ] Tests: POST run-advisor / daily-review with `review_date=<today+7d>` → 422 mentioning "future".
- [ ] Implement in both routes after date parsing: `if target > now_ist().date(): raise HTTPException(422, f"review_date {target} is in the future — refusing (autopilot marker protection)")`.
- [ ] Run route tests → PASS. Commit: `fix(api): reject future review_date on advisor/review triggers (AUD-044)`

### Task 6: Holiday calendar — corrected 2026 + union merge + startup self-heal (AUD-023)

**Files:**
- Modify: `core/intelligence/rl/nse_calendar.py` (2026 list lines 64-73, `_build_holiday_set`, `_load_from_file`), `services/api/server.py:267-282` (`_ensure_calendar_file`)
- Test: `tests/unit/test_nse_calendar_2026.py` (new)

**Interfaces:**
- Produces: `_build_holiday_set` = `_HARDCODED_HOLIDAYS | _load_from_file()` (union — a yfinance-built file year only covers dates up to its creation; hardcoded future dates must survive); loader skips non-list / underscore-prefixed keys; `_ensure_calendar_file` refreshes when the file is missing OR lacks the current year.

- [ ] Tests: official-2026 assertions — holidays: 2026-01-15, 03-03, 03-26, 03-31, 04-03, 04-14, 05-01, 05-28, 06-26, 09-14, 10-02, 10-20, 11-10, 11-24, 12-25 all `is_trading_day == False`; false entries removed: 2026-03-04 and 2026-03-20 are trading days; union test: monkeypatched `_HOLIDAY_FILE` containing only `{"2026": ["2026-01-15"]}` + `reload_holidays()` still yields 2026-11-24 as holiday (fixture restores + reloads).
- [ ] Implement: replace the 2026 hardcoded block with the official list (Jan 15, Jan 26, Mar 3, Mar 26, Mar 31, Apr 3, Apr 14, May 1, May 28, Jun 26, Aug 15, Sep 14, Oct 2, Oct 20, Nov 10, Nov 24, Dec 25 — occasion comments per NSE circular); union merge with comment on the cancelled-holiday tradeoff; loader guard `if year_str.startswith("_") or not isinstance(date_list, list): continue`; `_ensure_calendar_file` early-return only when the file exists AND parses AND contains `str(date.today().year)`.
- [ ] Run: `python -m pytest tests/unit/test_nse_calendar_2026.py tests/unit/test_portfolio_pricing.py -q` → PASS. Commit: `fix(calendar): official 2026 NSE holidays, union merge, startup self-heal for stale file (AUD-023)`

### Task 7: Manual-trade flow — atomic delete, deterministic ids, CSV capital_in (AUD-007)

**Files:**
- Modify: `services/api/routes/portfolio_api.py` (add_holding 108-167, delete_holding 170-213), `core/portfolio/store.py` (`import_csv`)
- Test: `tests/unit/test_portfolio_api.py`, `tests/unit/test_autopilot_api.py`, `tests/unit/test_portfolio_store.py` (extend)

**Interfaces:**
- Produces: delete = price fetch BEFORE lock, then ONE critical section (reload → verify holding → sell + cash credit + txn dedupe/append → single save); manual refs `manual-add|{buy_date}|{qty:g}|{price:g}` and `manual-delete|{date}|{qty:g}|{price:g}`; duplicate same-day identical manual txn id → skipped append (documented dedupe); `import_csv` credits `capital_in` by total imported value when cash accounting is on (under lock).

- [ ] Tests: delete leaves exactly one save-consistent state (holding gone + cash credited + one txn) — assert via reload; calling delete twice → second 404 and ledger has ONE SELL; add_holding retried with identical payload same day → one txn in ledger; import_csv with cash accounting on → capital_in increased by imported value.
- [ ] Implement per interface block (lock via `store.locked()`; ledger-append before save, matching the autopilot convention).
- [ ] Run → PASS. Commit: `fix(api): atomic manual delete, deterministic manual txn ids, CSV capital_in parity (AUD-007)`

### Task 8: Corrupt-quarantine safety (AUD-050)

**Files:**
- Modify: `core/portfolio/store.py`, `services/api/server.py` (exception handler)
- Test: `tests/unit/test_portfolio_store.py` (extend)

**Interfaces:**
- Produces: `class QuarantinedPortfolioError(RuntimeError)` in store; `save()` raises it while `portfolio.json` is missing AND a `portfolio.json.corrupt-*` file exists; corrupt-load emits one critical alert (non-fatal lazy import); FastAPI handler maps the error to 409.

- [ ] Tests: corrupt file → load returns empty AND subsequent `save()` raises `QuarantinedPortfolioError`; after restoring a valid portfolio.json, save works again.
- [ ] Implement per interface; alert via `emit_alerts([AlertEvent(date=..., kind="portfolio_corrupt", message=..., severity="critical")], title="Portfolio store alert")` inside the quarantine branch, wrapped try/except.
- [ ] Run store tests → PASS. Commit: `fix(store): refuse mutations while portfolio.json is quarantined + corruption alert (AUD-050)`

### Task 9: Dividend cash + DIV ledger rows + percent guard (AUD-045/046)

**Files:**
- Modify: `core/portfolio/corp_actions.py`
- Test: `tests/unit/test_portfolio_corp_actions.py` (extend)

**Interfaces:**
- Consumes: `TransactionRecord.side="DIV"` (Task 2), `store.locked()` (Task 1).
- Produces: `apply_actions_to_holding(holding, actions, today) -> tuple[int, list[tuple[AppliedCorpAction, float]]]` (count, dividend events `(action, credit)`); `sync_corp_actions` credits `portfolio.cash_deployable` per event when cash accounting is on and appends one DIV txn per event: `txn_id=make_txn_id(user, action.ex_date, sym, "DIV", action.key)`, `qty=0.0`, `price=dividend_per_share`, `value=credit`, `realized_pnl=0.0`, `note="dividend: "+desc[:40]`; whole sync runs inside `store.locked()`; `parse_action` skips percent-format dividend rows (digit run followed by `%`) with a warning.

- [ ] Tests: dividend application credits cash + appends DIV txn with correct value and cash_before/after; idempotent re-sync (same action key) → no second credit/txn; `parse_action({"subject": "Dividend 150%", ...})` → None (warning); cash accounting OFF → dividends_received still tracked, no cash change, no txn.
- [ ] Implement per interface (existing callers of `apply_actions_to_holding` in tests updated for the tuple return).
- [ ] Run corp-action + performance tests → PASS. Commit: `fix(corp-actions): dividends credit cash with DIV ledger rows; percent-dividend guard (AUD-045/046)`

### Task 10: Ops alerts — LLM failure streak + zero-output jobs (AUD-039)

**Files:**
- Create: `core/delivery/ops_alerts.py`
- Modify: `services/clients/llm_client.py` (`record_llm_call`), `services/scheduler/python/scheduler.py` (daily-review summary; event-ingest + discovery job summaries — exact call sites resolved at their existing "complete" log lines)
- Test: `tests/unit/test_ops_alerts.py` (new)

**Interfaces:**
- Produces: `record_llm_result(success: bool)` — consecutive-failure counter persisted at `data/ops_alerts_state.json`, alert at ≥10 consecutive failures, throttled to one per 6 h; `alert_job_zero_output(job: str, produced: int, expected: int)` — critical alert when `expected > 0 and produced == 0` (same-day repeats deduped by `emit_alerts`' date|kind key). Both never raise.

- [ ] Tests: 10 failures → exactly one alert (monkeypatched `emit_alerts` spy); success resets counter; 11th-20th failures within throttle window → no second alert; `alert_job_zero_output("daily_review", 0, 16)` alerts, `(5, 16)` doesn't.
- [ ] Implement; wire `record_llm_result(success)` into `record_llm_call` (try/except); call `alert_job_zero_output` from the three scheduler job summaries (daily review: completed vs entries; event ingest: ingested vs symbols; discovery: deep_dives vs candidates).
- [ ] Run → PASS. Commit: `feat(ops): LLM failure-streak and zero-output job alerts via push channel (AUD-039)`

### Task 11: Ledger reconciler — detect + alert (AUD-006)

**Files:**
- Create: `core/portfolio/reconcile.py`
- Modify: `core/portfolio/pipeline.py` (step 6, non-fatal)
- Test: `tests/unit/test_portfolio_reconcile.py` (new)

**Interfaces:**
- Consumes: full ledger via `store.load_transactions(limit=100000)`.
- Produces: `reconcile(store) -> dict` — (a) chain continuity: `txn[i].cash_before ≈ txn[i-1].cash_after` (tolerance ₹0.05, the AUD-001 lost-update signature); (b) final expected cash = `txn[0].cash_before + Σ(cash_after - cash_before)` vs `portfolio.cash_deployable` (tolerance ₹1); (c) per-symbol net qty (BUY−SELL) vs held `adj_qty` for holdings with no ratio≠1 corp actions (others reported `unverifiable`). Drift → one critical alert via `emit_alerts`; returns `{"status": "clean"|"drift"|"skipped", "issues": [...]}`. Never repairs, never raises.

- [ ] Tests: clean seed+trades ledger → clean; tampered cash → drift issue + alert spy called; broken chain (simulated lost update) → drift; ratio-adjusted holding → skipped as unverifiable, no false positive.
- [ ] Implement; pipeline step 6 after the value point: `reconcile(store)` in try/except.
- [ ] Run reconcile + pipeline tests → PASS. Commit: `feat(portfolio): ledger-replay reconciler, detect+alert only (AUD-006)`

### Task 12: Toggles path + seed ordering (AUD-040/049)

**Files:**
- Modify: `src/backend/sectors/registry.py:28`, `scripts/seed_autopilot.py:75-87`, possibly `Dockerfile` (COPY config/)
- Test: `tests/unit/test_sector_registry_toggles.py` (new, tmp-path toggles file), `tests/unit/test_seed_autopilot.py` (extend)

- [ ] Implement: `_TOGGLES_PATH = Path(os.getenv("SECTOR_TOGGLES_PATH", "config/sector_toggles.json"))` (CWD-relative works in repo and /app image); verify `config/sector_toggles.json` ships in the Docker image — if the Dockerfile lacks it, add `COPY config/ ./config/`; demote the missing-file log to INFO with the defaults note. Seed: build txn list during the loop but `store.save(p)` BEFORE appending transactions.
- [ ] Tests: registry loads toggles from a tmp path via env var; seed crash simulation (append failure) leaves portfolio saved.
- [ ] Run → PASS. Commit: `fix(registry+seed): CWD-relative sector toggles path, portfolio-first seed ordering (AUD-040/049)`

### Task 13: Full-suite gate

- [ ] Run: `python -m pytest tests/unit -q` → no regressions vs baseline (1875 passed / 5 skipped equivalent for tests/unit scope).
- [ ] Run the money-path subset (18 files, Task lists above) → all PASS.
- [ ] Fix any fallout; commit fixes with their owning AUD id.
- [ ] Commit (if needed): `test: wave-1 suite stabilization`

## Verification & rollout (after Task 13)

1. Reviewer-runs-code pass (fresh subagent; acceptance criteria in the spec §Testing — must EXECUTE, not read).
2. Merge `audit/wave1-correctness` → `main`, push (Railway auto-deploy).
3. Check Railway variables for a `FEEDBACK_CRON` override (would mask the new default).
4. Startup logs: cron shows `hour='16', minute='30', day_of_week='mon-fri'`; calendar refresh line if the file lacked 2026; 15 jobs registered; no new errors.
5. Prod probes: `GET /portfolio/performance` unchanged (equity 1e6, autopilot true); assert `dividends_received == 0` on all holdings (`GET /portfolio`).
6. First scheduled end-to-end proof: Mon 2026-07-13 16:30 IST (or user-approved manual `POST /portfolio/run-advisor`).
7. Update `docs/audit/LEDGER.md` rows → FIXED w/ commit hashes; update memory.

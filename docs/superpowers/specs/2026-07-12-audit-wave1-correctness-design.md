# Audit Wave 1 — Correctness Remediation (Phases 1+2 findings)

**Date:** 2026-07-12 · **Status:** APPROVED (user, 2026-07-12) · **Source:** docs/audit/LEDGER.md (AUD-001…051)
**Deadline anchor:** deployed before Mon 2026-07-13 16:30 IST (first scheduled advisor/autopilot run under the fixed cron).

## User decisions (2026-07-12)

1. **Scope = correctness wave:** AUD-001, 002, 003, 004, 006 (detect+alert), 007, 023,
   038, 039, 040, 043, 044, 045 (credit cash), 046 (guard only), 049, 050, 051.
   DEFERRED: dead-code deletions (026–037 → Phase 6), decision-quality (047/048 → Phase 4),
   docs/test-mock cleanup (022/036 → Phase 7), auth lockdown (012 stays ON HOLD).
2. **Dividends (045):** credit `cash_deployable` at ex-date application; dividends become
   real cash events recorded in the transactions ledger.
3. **Schedule intent (038):** Mon–Fri 16:30 IST, reviewing the previous **trading** day.
4. **Reconciler (006):** detect + alert only; never auto-repair.
5. Concurrency approach: **Option A** — `filelock` critical-section locks + fresh reload
   in the executor (single-writer redesign and optimistic versioning rejected as overkill).

## Design

### 1. Concurrency (AUD-001, P0)

- New dep `filelock` (pure-Python). `PortfolioStore` gains one re-entrant
  `FileLock` per instance at `<user_dir>/portfolio.lock` (timeout 30 s) and a public
  `locked()` context manager. All read-modify-write paths run inside it:
  store's own RMW helpers (`add_holding`, `remove_holding`, `add_watchlist`,
  `remove_watchlist`, `reduce_holding`), `sync_corp_actions`, `execute_advice`,
  and the API mutation routes' multi-step sequences.
- `execute_advice` **reloads the portfolio under the lock** and applies verdicts to the
  fresh state — the object loaded by the pipeline minutes earlier is used only for
  signal computation, never saved. Gate fields (autopilot flag, cash, run marker) are
  re-read from the fresh load. Sell/ADD lookups against fresh holdings mean a holding
  deleted mid-run is skipped naturally (`_find` → None).
- Plain reads stay lock-free (atomic temp+rename keeps them consistent).

### 2. Scheduler & timing (AUD-043, 038, 051, 044)

- `_daily_review_job` (services/scheduler/python/scheduler.py) calls
  `run_post_review_pipeline(review_date)` after the review loop, try/except non-fatal,
  logging the summary — identical contract to `scheduler_api._review_task`.
- `FEEDBACK_CRON` default `0 11 * * 1-5` → `30 16 * * mon-fri`; misleading UTC comments
  corrected. Named days remove the APScheduler numeric-day ambiguity.
- Review-date derivation is holiday-aware in both schedulers: last **trading** day
  strictly before today via `nse_calendar` (replaces weekend-only skipping at
  scheduler.py:473-475 and scheduler_api.py:65-70).
- Future-date guards: `POST /portfolio/run-advisor` and `POST /scheduler/daily-review`
  reject `review_date` > today-IST with 422. Defense-in-depth: `execute_advice` clamps
  the `last_autopilot_run` stamp to ≤ today-IST; `record_value_point` skips future dates.
- A real hook test imports `services.scheduler.python.scheduler`, stubs the review
  loop + pipeline, invokes `_daily_review_job`, and asserts the pipeline was called —
  replacing the API-module-only test's false confidence.

### 3. Executor price/guard fixes (AUD-003, 004, 002)

- Every executed trade's price is written back into `closes`
  (`closes.setdefault(sym, price)` at execution sites) so same-run valuation, digest,
  and value point share one price basis (also fixes AUD-009's mechanism).
- Sell path gains `price <= 0 → warn + skip` (buys already guard).
- `Holding.sell` guards `adj_qty <= 0` (kills the theoretical ZeroDivision).

### 4. Manual-trade flow (AUD-007 + CSV inconsistency)

- Delete-holding becomes ONE atomic critical section: load → sell + cash credit + txn
  build → single save, inside `locked()`. The 3-write crash window (holding gone, cash
  never credited, ledger silent) disappears.
- Manual txn ids become deterministic (state-derived ref: date + qty + price/pre-state,
  not `datetime.now()`); an identical same-day manual txn id already in the ledger is
  treated as a duplicate submit → dedupe (documented behavior).
- `import_csv` credits `capital_in` per imported holding when cash accounting is on
  (parity with POST /holdings).

### 5. Calendar (AUD-023)

- Hardcoded 2026 fallback replaced with the official NSE list: adds Jan 15, Mar 3,
  Mar 26, Mar 31, May 28, Jun 26, Sep 14, Oct 20, Nov 10, Nov 24; removes false
  Mar 4 / Mar 20. (2025 list unchanged.)
- `calendar_updater.update_holiday_calendar` also runs **at startup** on the
  scheduler-owning worker when `data/nse_holidays.json` is missing or lacks the current
  year (non-fatal). The Dec-31 job remains for the annual refresh.

### 6. Dividend accounting (AUD-045, 046)

- Dividend application (corp_actions) credits `portfolio.cash_deployable` when cash
  accounting is on, and appends a `DIV` transaction row: `side="DIV"`, `qty=0`,
  `value=credit`, `realized_pnl=0`, cash_before/after reflecting the credit.
  `TransactionRecord.side` literal gains `"DIV"`. `/performance` realized sum is
  unaffected (DIV rows carry 0); the ledger becomes the complete cash audit trail.
- `Holding.sell`'s pro-rata dividend bookkeeping is unchanged (display metric).
- Percent-format dividend rows (number followed by `%`) are skipped with a warning
  instead of booked as ₹/share; full parse fix gated on Phase 3 format verification.
- Prod migration: none needed — pipeline never ran (AUD-043), `dividends_received` is 0
  for all holdings; asserted during deploy verification.

### 7. Observability (AUD-039, 006, 050, 040)

- `core/delivery/ops_alerts.py`: (a) LLM-client consecutive-failure alert — after N
  consecutive provider failures (default 10) emit one push alert, throttled to once
  per 6 h; (b) `alert_job_zero_output(job, stats)` — called at the end of daily review,
  event ingestion, and discovery: fires when a job "completes" with zero output against
  nonzero input (the 2026-07-11 887×401 silent-day signature).
- Reconciler `core/portfolio/reconcile.py` (detect + alert): replay transactions.jsonl →
  expected cash (exact — seed sets pot, BUY−, SELL+, DIV+) and per-symbol net qty
  (skip symbols whose holdings carry ratio≠1 corp actions; log as unverifiable).
  Runs as a non-fatal pipeline step; drift > ₹1 or qty mismatch → push alert. Never repairs.
- Corrupt portfolio.json (AUD-050): quarantine behavior stays, but while an unrecovered
  `portfolio.json.corrupt-*` file exists, mutations raise (409-class) and one alert is
  emitted; reads continue returning the empty portfolio.
- `sector_toggles.json` path (AUD-040): resolve against the application root (works in
  both repo layout and Docker image where `src/backend/` → `/app/backend/`), not
  `Path(__file__).parents[3]`.

### 8. Seed script (AUD-049)

- Portfolio saved before transaction appends (money state authoritative; ledger
  backfillable). Idempotency check unchanged.

## Testing

TDD per task. New/changed tests: real scheduler-hook test; cross-process lock
contention (two processes contending on one store); calendar asserts official 2026
dates (incl. absence of Mar 4/Mar 20); dividend cash + DIV ledger rows; % dividend
skip; reconciler clean/drift cases; future-date guards (route 422 + marker clamp);
delete-flow atomicity + deterministic ids; corrupt-quarantine mutation refusal;
executor price-basis feedback. Full suite baseline 1875 passed / 5 skipped and the
129-test money-path subset must stay green.

## Rollout & verification

Worktree branch `audit/wave1-correctness`; per-task commits; final review pass that
RUNS the code (per feedback-3agent-loop: execution evidence, not reading); merge to
main; push (= Railway deploy). Post-deploy: startup logs show corrected cron
(`day_of_week='mon-fri'`, 16:30), calendar fetch/log line, 15 jobs registered; assert
`dividends_received == 0` pre-migration claim via API. End-to-end prod proof = first
scheduled run Mon 2026-07-13 16:30 IST (or a user-approved manual
`POST /portfolio/run-advisor` for the last trading day — executes the portfolio's
first real virtual trades; requires explicit user go).

## Out of scope (deferred)

Dead-code deletions (AUD-026…037, Phase 6) · advisor decision-quality (047/048,
Phase 4) · docs/test-mock cleanup (022/036, Phase 7) · auth lockdown (012, ON HOLD) ·
stale-news filter (041, Phase 3 verify) · full %-dividend parse (046, Phase 3) ·
full auto-repair reconciliation (rejected).

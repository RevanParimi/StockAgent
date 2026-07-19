# Compass Autopilot — End-to-End Developer Guide

> **Status (2026-07-18):** live in production since 2026-07-13 (first real auto-trades).
> Post-audit hardening not yet folded into the body: pipeline-wide file lock with fresh
> reload, dividend cash-credit `DIV` ledger rows, detect-only reconciler, harvest-timeout
> containment so a slow review day can never silently skip the trading pipeline, per-run
> outcomes in `/scheduler/status last_runs`, and nightly ledger backups. Details:
> [audit/LEDGER.md](audit/LEDGER.md); map: [ARCHITECTURE.md](ARCHITECTURE.md) §6.

> **One sentence:** every trading day, after the RL reviews finish, the Position
> Advisor scores each holding and Autopilot *executes* those verdicts
> (buy/sell/trim/exit/switch) on a **virtual** portfolio — mock money, real NSE
> prices, full audit trail, zero human clicks.
>
> **Three iron rules** (spec `docs/superpowers/specs/2026-07-10-compass-autopilot-design.md`):
> 1. Virtual money only. **No broker calls, ever.**
> 2. The **LLM never decides** a trade — it narrates. The executor is a pure,
>    deterministic function over `AdviceRecord`s.
> 3. Autopilot **never writes** under `data/rl/paper/` or any PredictionStore
>    path (RL paper-lane isolation invariant).

---

## 1. The Big Picture

```
                         (C# scheduler / cron, Mon-Fri after market close)
                                          |
                                          v
                              +------------------------+
                              |  Daily RL reviews      |   per-ticker forecasts,
                              |  (16 managed tickers)  |   envelopes, feedback
                              +-----------+------------+
                                          | event-triggered (never clock-raced)
                                          v
              run_post_review_pipeline(review_date)        core/portfolio/pipeline.py
              ---------------------------------------------------------------
  Step 1      sync_corp_actions()          <- FIRST, so adj_* prices are right
  Step 2      refresh_events_calendar()
  Step 3      for each user -> for each holding:
                  close_on(sym) -> build_signals() -> decide() -> AdviceRecord
                  narrate()  (LLM writes the "why", AFTER the decision)
  Step 3.5    autopilot.execute_advice(...)   <- THE MONEY MOVES HERE
              autopilot.record_value_point()  <- daily equity snapshot
  Step 4      build_digest(..., transactions=txns) -> digests/YYYY-MM-DD.json
  Step 5      AlertEvents (escalations + autopilot_trade + switch_buy_skipped)
              -> emit_alerts() -> web-push;  deliver() EOD summary
              ---------------------------------------------------------------
                                          |
                                          v
        +---------------------------- data/portfolio/<user>/ ----------------+
        |  portfolio.json  transactions.jsonl  value_history.jsonl  digests/ |
        +---------------------+-----------------------------------+----------+
                              |                                   |
                              v                                   v
                   FastAPI /portfolio/*                 portfolio.jsx (prototype UI)
                   (transactions, performance,          hero equity, AUTOPILOT pill,
                    holdings CRUD, advice, digest)      equity chart, activity feed
```

Every pipeline step is **non-fatal** (log + continue): a failure in Autopilot
never kills the digest, and vice-versa.

---

## 2. Where Everything Lives

```
StockAgent-main/
├── core/portfolio/
│   ├── autopilot.py        <- THE EXECUTOR. Start reading here.
│   ├── advisor.py          <- build_signals() + decide() -> AdviceRecord
│   ├── pipeline.py         <- daily orchestration (steps 1..5 above)
│   ├── store.py            <- PortfolioStore: all reads/writes per user
│   ├── digest.py           <- EOD digest dict (now includes "trades")
│   ├── pricing.py          <- close_on(symbol, date) w/ trading-day walkback
│   ├── promotion.py        <- promote_symbol() into the managed universe
│   ├── narrator.py         <- LLM narration (flavour text only)
│   └── corp_actions.py     <- split/bonus/dividend adjustment
├── src/backend/shared/schemas/portfolio.py
│                           <- Holding, Portfolio, AdviceRecord,
│                              TransactionRecord, WatchlistItem
├── src/backend/shared/config/settings/base.py   <- AUTOPILOT_* settings
├── scripts/seed_autopilot.py                    <- one-time equal-weight seed
├── services/api/routes/portfolio_api.py         <- /portfolio/* routes
├── src/frontend/prototypes/portfolio.jsx        <- the UI (in-browser JSX)
├── data/portfolio/<user_id>/                    <- ALL per-user state (below)
└── tests/unit/test_autopilot_*.py               <- the test map (§11)
```

Per-user state (created lazily; `primary` is the default user):

```
data/portfolio/<user_id>/
├── portfolio.json          # DERIVED state: holdings, watchlist, cash, flags
├── transactions.jsonl      # APPEND-ONLY audit authority — every trade, ever
├── value_history.jsonl     # one line per trading day: the equity curve
├── advice_ledger.jsonl     # every AdviceRecord the advisor ever produced
└── digests/
    └── 2026-07-13.json     # what the user sees each evening
```

> **Mental model:** `transactions.jsonl` is the book of record;
> `portfolio.json` is a cache derived from it. If they ever disagree (§7),
> trust the ledger.

---

## 3. Life of a Trading Day

```
 IST timeline (trading day)
 ──────────────────────────────────────────────────────────────────────────
 08:50   Morning brief push (Job 13)             "here's your day ahead"
 15:30   NSE closes
 ~17:00  Scheduler daily reviews run             RL forecasts per ticker
    |
    +--> run_post_review_pipeline(today)
           1. corp actions synced (adj_qty / adj_avg_price corrected FIRST)
           2. events calendar refreshed
           3. advisor: one AdviceRecord per holding
                verdict ∈ {HOLD, ADD, TRIM, EXIT, SWITCH}
           3.5 AUTOPILOT:
                sells execute first  ->  cash freed
                buys execute second  ->  cash spent
                every trade appended to transactions.jsonl
                equity snapshot appended to value_history.jsonl
           4. digest written (holdings, verdicts, trades, escalations)
           5. push alerts:  "SELL 2 MARUTI @ ₹12,340.00 (realized ₹1,220.00)"
 ──────────────────────────────────────────────────────────────────────────
 Weekend: Sat discovery screen (paper lane), Sun weekly review (Job 14).
 Non-trading days: pipeline no-ops (is_trading_day guard).
```

---

## 4. The Verdict Rules (what the executor actually does)

Execution price is always **the close the advisor used**:
`closes.get(symbol) or advice.close`. Whole shares only (`math.floor`), fees = 0.

```
+---------+--------------------------------------------------------------------+
| Verdict | Autopilot action                                                   |
+---------+--------------------------------------------------------------------+
| HOLD    | Nothing. (Still stamps the run marker — see §6.)                   |
+---------+--------------------------------------------------------------------+
| EXIT    | SELL full adj_qty @ close. Holding removed. Symbol moved to        |
|         | watchlist (source="autopilot", reason="autopilot_exit") so the     |
|         | advisor keeps watching it.                                         |
+---------+--------------------------------------------------------------------+
| TRIM    | SELL max(1, floor(adj_qty × 25%)).                                 |
|         | If < 1 share would remain -> sell everything (note="trim_to_zero").|
+---------+--------------------------------------------------------------------+
| ADD     | BUY floor(budget / price) where                                    |
|         |   budget = min( 25% of current position value,                     |
|         |                 weight headroom to the 10% position cap,           |
|         |                 cash above the ₹10,000 floor )                     |
|         | Skipped if a previous autopilot BUY of this symbol happened        |
|         | < 5 trading days ago (cooldown), or budget < 1 share.              |
|         | Only ADDs into EXISTING holdings (never opens new positions).      |
+---------+--------------------------------------------------------------------+
| SWITCH  | Two legs, sell first:                                              |
|         |   1) SELL full position (EXIT semantics, incl. watchlist move)     |
|         |   2) BUY the candidate with min(proceeds, cash - floor),           |
|         |      priced via close_on(candidate, review_date).                  |
|         | Resolvability gate: if the candidate can't be priced, the buy leg  |
|         | is skipped (cash stays parked) and a "switch_buy_skipped" alert    |
|         | fires. A successful buy also promote_symbol()s the candidate into  |
|         | the managed universe (origin="held") — the ONE designed write      |
|         | outside data/portfolio/.                                           |
+---------+--------------------------------------------------------------------+
```

**Ordering inside one run is deterministic:**

```
  SELLS first  : EXIT, SWITCH-sell, TRIM      — sorted by symbol asc
  BUYS second  : SWITCH-buy legs, then ADDs    — ADDs by confidence desc,
                                                 ties symbol asc
  (sells free cash before buys consume it)
```

The post-trade weight cap uses the algebra `(pos + X)/(total_mv + X) ≤ cap`
⇒ `X ≤ (cap·total_mv − pos)/(1 − cap)` — see `_execute_buys`.

---

## 5. Guardrails & Config

All config-backed via `config.yaml` (absent key ⇒ fallback default). Settings
live in `src/backend/shared/config/settings/base.py`.

```
+----------------------------+---------------------------+---------+----------------------------------+
| settings.*                 | config.yaml key           | default | meaning                          |
+----------------------------+---------------------------+---------+----------------------------------+
| AUTOPILOT_ENABLED          | autopilot.enabled         | true    | global kill switch               |
| AUTOPILOT_ADD_TRANCHE_PCT  | autopilot.add_tranche_pct | 25.0    | ADD buys 25% of position value   |
| AUTOPILOT_TRIM_PCT         | autopilot.trim_pct        | 25.0    | TRIM sells 25% of qty            |
| AUTOPILOT_MIN_CASH_FLOOR   | autopilot.min_cash_floor  | 10000.0 | never spend below ₹10k cash      |
| AUTOPILOT_ADD_COOLDOWN_TD  | autopilot.add_cooldown_td | 5       | trading days between ADDs/symbol |
| ADVISOR_MAX_POSITION_PCT   | advisor.max_position_pct  | 10.0    | post-trade position weight cap   |
+----------------------------+---------------------------+---------+----------------------------------+
```

**Gating — Autopilot is OFF when ANY of these hold:**

```
  settings.AUTOPILOT_ENABLED is False      (global)
  portfolio.autopilot        is False      (per-user opt-in flag)
  portfolio.cash_deployable  is None       (cash accounting never turned on)
```

When OFF, a pipeline run leaves `portfolio.json` **byte-identical** — pinned by
a `read_bytes()` test. When ON with zero trades, only the run marker is stamped.

---

## 6. Idempotency — why re-runs are safe

Two independent layers:

```
 Layer 1: run marker (cheap skip)
   portfolio.last_autopilot_run = "2026-07-13"
   execute_advice() returns [] for any review_date <= marker.
   -> normal next-day runs proceed; STALE-DATE REPLAYS ARE BLOCKED
      (a re-run for a past date would trade at stale prices — refused).

 Layer 2: transaction id (exact dedupe)
   txn_id = sha256(f"{user}|{date}|{symbol}|{side}|{ref}")[:16]
     ref (autopilot) = "<advice date>|<advice symbol>|<rationale_hash>"
     ref (seed)      = "seed"
     ref (manual)    = "manual-<utc timestamp>"
   Before executing any trade, the id is checked against the ledger.
   Same advice replayed -> same id -> skipped, money moves once.
```

`record_value_point()` is likewise idempotent: it refuses a point whose date
is `<=` the last line of `value_history.jsonl`.

---

## 7. Crash-Safety (read this before touching the executor)

Write order inside `execute_advice`:

```
   decide all trades in memory
        |
   append every TransactionRecord to transactions.jsonl     (1st)
        |
   save portfolio.json (holdings, cash, run marker, atomically) (2nd)
```

A crash **between (1) and (2)** cannot double-execute (Layer-2 dedupe), but it
leaves the ledger *ahead* of `portfolio.json` — the ledger says SELL, the
holding still exists. Thanks to the Layer-1 monotonic guard, hitting a dedupe
skip is now *exactly* that divergence signature, so the executor logs:

```
  WARNING [autopilot] txn <id> (SELL MARUTI) already in ledger but run marker
  predates this run — possible ledger/portfolio divergence from a mid-run
  crash; manual reconciliation may be needed.
```

If you ever see that warning: reconcile `portfolio.json` against the ledger by
hand (a ledger-replay reconciler is on the backlog). **The ledger wins.**

---

## 8. Money Math — raw vs adjusted fields

`Holding` carries two parallel books:

```
+------------------+---------------------------+-------------------------------+
| field            | meaning                   | who changes it                |
+------------------+---------------------------+-------------------------------+
| qty,             | "as entered" history —    | buys only (money actually     |
| avg_buy_price    | what was ever put in      | put in); sells DON'T touch it |
+------------------+---------------------------+-------------------------------+
| adj_qty,         | the LIVE position after   | corp actions, sells, buys —   |
| adj_avg_price    | splits/bonuses/trades     | ALL P&L math uses adj_*       |
+------------------+---------------------------+-------------------------------+
| dividends_       | ₹ credited, still         | corp actions add; sell()      |
| received         | unrealized                | realizes a pro-rata slice out |
+------------------+---------------------------+-------------------------------+
```

`Holding.sell(qty, price)` returns realized P&L **including** the pro-rata
dividend slice, and removes that slice from `dividends_received` so unrealized
P&L never double-counts it. Buys merge with weighted averages on both books.

Portfolio-level cash accounting:

```
  capital_in       total mock money ever put in (seed pot + manual adds)
  cash_deployable  spendable cash right now
  total_equity     market_value(holdings) + cash
  total P&L        total_equity - capital_in     (= realized + unrealized)
```

---

## 9. The Ledgers (file formats)

`transactions.jsonl` — one `TransactionRecord` per line:

```
+-------------------+----------------------------------------------------------+
| field             | notes                                                    |
+-------------------+----------------------------------------------------------+
| txn_id            | sha256(user|date|symbol|side|ref)[:16] — the dedupe key  |
| date / ts         | trade (review) date / exact UTC timestamp                |
| user_id, symbol   |                                                          |
| side              | "BUY" | "SELL"                                           |
| qty, price, value | whole shares; value = qty × price                        |
| cash_before/after | cash bracketing this trade                              |
| holding_qty_after | adj_qty after the trade (0.0 = position closed)          |
| realized_pnl      | SELL only (incl. pro-rata dividends)                     |
| source            | "autopilot" | "seed" | "manual"                          |
| verdict           | originating advisor verdict ("" for seed/manual)         |
| advice_ref        | "<date>|<symbol>|<rationale_hash>" — joins the advice    |
|                   | ledger; this is Phase D's RL training hook               |
| triggers, note    | advisor trigger codes; free-text ("trim_to_zero", ...)   |
+-------------------+----------------------------------------------------------+
```

`value_history.jsonl` — one line per trading day:

```
{"date": "2026-07-13", "market_value": 991200.5, "cash": 11389.96,
 "total_equity": 1002590.46, "capital_in": 1000000.0, "day_change_pct": 0.26}
```

Both readers are **tolerant**: a torn/corrupt line is logged and skipped,
never fatal. Both files are append-only — never rewrite them in place.

---

## 10. Seeding, API, UI

### 10.1 Seed script (one-time per user)

```
python scripts/seed_autopilot.py --user primary --pot 1000000      # local
railway ssh "python scripts/seed_autopilot.py --user primary --pot 1000000"  # prod
```

Equal-weight `pot / n_tickers` across the managed universe (via
`get_active_tickers_with_sector()`), whole shares at the latest close, one
`source="seed"` BUY per ticker, then `capital_in = pot`,
`cash_deployable = pot − spent`, `autopilot = True`, day-0 value point.
**Refuses to run** if the user already has holdings or transactions
(recovery from a half-seed: delete `data/portfolio/<user>/`, re-run).
Prod was seeded 2026-07-11: 16/16 tickers, ₹62.5k budget each.

### 10.2 API surface (`services/api/routes/portfolio_api.py`)

```
+--------+----------------------------------+-------------------------------------------+
| method | route                            | returns / does                            |
+--------+----------------------------------+-------------------------------------------+
| GET    | /portfolio                       | holdings + watchlist w/ live marks        |
| GET    | /portfolio/transactions?limit=N  | {"transactions":[...]} newest-first       |
| GET    | /portfolio/performance           | {cash, capital_in, market_value,          |
|        |                                  |  total_equity, realized_pnl,              |
|        |                                  |  unrealized_pnl, total_return_pct,        |
|        |                                  |  day_change_pct, autopilot, history[]}    |
|        |                                  | (nulls only when cash accounting is OFF)  |
| POST   | /portfolio/holdings              | manual BUY = FRESH capital:               |
|        |                                  |  capital_in += qty×price, cash UNCHANGED, |
|        |                                  |  source="manual" txn appended             |
| DELETE | /portfolio/holdings/{symbol}     | manual SELL @ today's close (fallback     |
|        |                                  |  adj_avg_price), cash credited,           |
|        |                                  |  source="manual" txn appended             |
| GET    | /portfolio/advice                | advice ledger tail                        |
| GET    | /portfolio/digest/latest         | most recent digest                        |
| POST   | /portfolio/run-advisor           | manual pipeline trigger (see §6 — stale   |
|        |                                  |  dates cannot move money)                 |
+--------+----------------------------------+-------------------------------------------+
```

### 10.3 UI (`src/frontend/prototypes/portfolio.jsx`)

In-browser Babel JSX, no build step. `?demo=1` forces demo data (kept
pixel-identical). When live **and** cash accounting is on:

```
  hero        = total_equity from /performance   + "AUTOPILOT" pill
  day badge   = day_change_pct (green/red)
  stats row   = Invested (capital_in) | Total return | Cash | Realized P&L
  chart       = equity curve from history[] (hidden until ≥ 2 points)
  activity    = LiveActivityCard <- /transactions (10 recent + view-all)
```

---

## 11. Testing Map

Run everything with `python -m pytest` **from the repo root**.

```
+--------------------------------------------+-------------------------------------------+
| tests/unit/...                             | pins                                      |
+--------------------------------------------+-------------------------------------------+
| test_autopilot_schemas.py                  | TransactionRecord, Holding.sell() math    |
| test_autopilot_store.py                    | ledger append/tail-load, reduce_holding   |
| test_autopilot_settings.py                 | AUTOPILOT_* defaults                      |
| test_autopilot_executor_sells.py           | EXIT/TRIM, gating byte-identity, run      |
|                                            | marker, dedupe, stale-date replay guard   |
| test_autopilot_executor_adds.py            | tranche/weight-cap/floor/cooldown math    |
| test_autopilot_executor_switch.py          | SWITCH two-leg, resolvability gate,       |
|                                            | record_value_point idempotency            |
| test_autopilot_pipeline.py                 | pipeline hook, digest "trades",           |
|                                            | switch_buy_skipped alert                  |
| test_seed_autopilot.py                     | equal-weight seed, refuse-non-empty       |
| test_autopilot_api.py                      | routes + manual-trade accounting          |
| test_autopilot_isolation.py                | THE INVARIANT: sell + buy paths write     |
|                                            | only inside data/portfolio/<user>/        |
+--------------------------------------------+-------------------------------------------+
```

Quick loop while developing: `python -m pytest tests/unit -k autopilot -q`
(~35 tests, <5s). Known pre-existing failures that are NOT yours: see
`CODEBASE.md` § test baseline.

---

## 12. Ops Runbook & Gotchas

```
 CHECK                          HOW
 ─────────────────────────────  ──────────────────────────────────────────────
 Did today's run execute?       GET /portfolio/digest/latest -> "trades": [...]
 What did it trade?             GET /portfolio/transactions?limit=20
 Equity curve growing?          GET /portfolio/performance -> history[]
 Turn autopilot off (one user)  edit portfolio.json: "autopilot": false
 Turn it off globally           config.yaml: autopilot.enabled: false + deploy
 Divergence warning in logs?    §7 — reconcile portfolio.json FROM the ledger
 Re-seed a user                 delete data/portfolio/<user>/ first (else the
                                seed refuses) — prod: only with backup
```

**Gotchas for new developers**

1. `pytest` works from the repo root because `pyproject.toml` sets
   `pythonpath = [".", "src"]`. Standalone scripts must add both roots
   themselves — copy the `sys.path` block from `scripts/seed_autopilot.py`.
2. `portfolio.json` writes go through a **`FileLock`** (`store.py` —
   `data/portfolio/<user>/portfolio.lock`, re-entrant, 30s timeout); autopilot
   mutations reload fresh state under the lock before writing. Always use
   `store.locked()` / the locking helpers — never write the file directly.
3. The digest values the portfolio with *pre-trade* closes; a switched-in
   candidate shows NO_DATA on day one. Cosmetic, known.
4. `manual` transactions use a timestamped ref — an HTTP retry writes a second
   ledger row (pads the audit trail; never moves cash twice).
5. Never "fix" the byte-identity or isolation tests to make code pass — they
   encode the two constraints most likely to bite you silently.
6. Weekend/holiday: `close_on` walks back to the last trading close;
   `is_trading_day` gates the pipeline.

---

## 13. Where This Is Going (context for the code you'll read)

- **Phase D (advice RL):** every executed trade carries `advice_ref`, joining
  outcome (realized P&L) back to the advisor decision that caused it — the
  training signal for tuning the advisor. Data-gated, needs weeks of history.
- **Backlog** (final-review triage, none load-bearing): ledger-replay
  reconciler, delete-flow write consolidation, sell-side `price > 0` guard,
  digest SWITCH-day valuation, misc lint/docs. See
  `.superpowers/sdd/compass-autopilot-progress.md`.

*Doc created 2026-07-11 at Autopilot go-live (main @ 3d389f9). Spec and plan
under `docs/superpowers/`; codebase map in `CODEBASE.md`.*

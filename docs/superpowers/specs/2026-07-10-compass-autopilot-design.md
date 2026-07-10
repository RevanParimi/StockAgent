# Compass Autopilot — Advisor-Executed Virtual Portfolio (design)

**Date:** 2026-07-10 · **Status:** APPROVED (decisions delegated — see §1)
**Builds on:** `docs/superpowers/specs/2026-07-06-portfolio-intelligence-discovery-design.md`
(Compass M1/M2/M4) and the portfolio-page live wiring
(`docs/superpowers/specs/2026-07-10-portfolio-page-live-wiring-design.md`).

## 1. What and why

Turn the virtual portfolio from a passive mirror into a **self-driving paper
portfolio**: seed the managed tickers as holdings with a default mock-money
pot, then **auto-execute the Position Advisor's verdicts** (ADD / TRIM / EXIT /
SWITCH) every trading day, with a **complete transaction audit trail** and a
**P&L / activity UI** on the Portfolio page.

Why now: the advisor already produces deterministic verdicts daily
(`core/portfolio/advisor.py`), but nothing acts on them, so the advice ledger
never learns what following the advice would have earned. Executing the
verdicts on mock money produces exactly the outcome data Phase D (advice RL)
needs, and gives the user a portfolio page with real content.

**Decision authority:** the user delegated all technical and design decisions
on 2026-07-10 ("i trust your judgement on any technical and design
decisions"). Every parameter below is a recorded decision, not a placeholder.

**Constraint kept intact:** "no auto-trading ever" in the Compass spec means
*real money / broker orders*. This feature trades **virtual positions only**
(mock money, real NSE closes). The LLM still never decides — the executor is
a pure function over the advisor's deterministic verdicts.

## 2. Approaches considered

- **A. Executor inside the post-review pipeline (CHOSEN).** A new
  `core/portfolio/autopilot.py` called from `run_post_review_pipeline`
  between advice generation (step 3) and digest (step 4). Same event-triggered
  cadence as everything else, digest/alerts naturally reflect post-trade
  state, no new scheduler job, trivially idempotent per review date.
- **B. Separate scheduled job replaying the advice ledger.** Decoupled, but
  introduces a second reader/writer of portfolio.json, ordering races with
  the digest, and double-execution risk on re-runs. Rejected.
- **C. LLM-mediated execution.** Violates the M2 invariant (LLM narrates,
  never decides). Rejected outright.

## 3. Data model (additive, backward compatible)

### 3.1 `Portfolio` (src/backend/shared/schemas/portfolio.py)
- `cash_deployable: float | None` → **becomes live**: seeded pot minus buys
  plus sell proceeds. `None` still means "cash accounting off" (legacy).
- `capital_in: float = 0.0` **(new)** — total mock money ever put in (seed pot
  + manual adds). Total P&L ≡ `market_value + cash_deployable − capital_in`.
- `autopilot: bool = False` **(new)** — per-user opt-in. Seed script sets it.
- `last_autopilot_run: str = ""` **(new)** — ISO date of last executed run
  (cheap idempotency check; ledger is the authority).

### 3.2 `TransactionRecord` (new schema)
Append-only JSONL at `data/portfolio/<user_id>/transactions.jsonl` (same
pattern and tolerant reader as advice_ledger.jsonl).

```
txn_id            sha256(user|date|symbol|side|advice_ref)[:16] — dedupe key
date, ts          review date (ISO) + UTC timestamp
user_id, symbol
side              BUY | SELL
qty, price, value whole shares; price = execution close; value = qty × price
cash_before, cash_after
holding_qty_after
realized_pnl      SELL only: (price − adj_avg_price) × qty + pro-rata dividends
source            autopilot | seed | manual
verdict           originating verdict (ADD/TRIM/EXIT/SWITCH; "" for seed/manual)
advice_ref        "<date>|<symbol>|<rationale_hash>" join key to advice ledger
triggers          copied from AdviceRecord (audit readability)
note              free text ("seed 1/16", "switch from TATAMOTORS", …)
```

### 3.3 Value history (new)
`data/portfolio/<user_id>/value_history.jsonl`, one line per trading day,
appended by the pipeline after execution:
`{date, market_value, cash, total_equity, capital_in, day_change_pct}`.
Powers the hero range chart and day-change stat (the deferred "full parity"
items land here).

### 3.4 `WatchlistItem.source`
Literal extended with `"autopilot"` — EXITed symbols move to the watchlist so
agent coverage continues at watchlist cadence.

## 4. Executor semantics (`core/portfolio/autopilot.py`)

`execute_advice(store, portfolio, advice, closes, review_date) -> list[TransactionRecord]`
— pure decision logic, store writes at the end; runs only when
`settings.AUTOPILOT_ENABLED` (config `autopilot.enabled`, default `true`)
**and** `portfolio.autopilot` **and** `portfolio.cash_deployable is not None`.

Execution price = the same NSE close the advisor used (`AdviceRecord.close`);
SWITCH buy-side uses `close_on(candidate, review_date)`. Fees = 0 (virtual).
All quantities are **whole shares**. Paper convention noted: real execution
would be next-day open; verdict-day close keeps the loop deterministic and
consistent with mark-to-market.

| Verdict | Action |
|---|---|
| HOLD | Nothing. |
| ADD | Buy `floor(0.25 × position_market_value / close)` shares, subject to: post-trade position weight ≤ `ADVISOR_MAX_POSITION_PCT` (10%), cash floor (below), ADD cooldown (below). Skip (logged) if caps allow < 1 share. |
| TRIM | Sell `max(1, floor(0.25 × adj_qty))` shares. If < 1 whole share would remain, sell all (recorded with note `trim_to_zero`). |
| EXIT | Sell entire position; remove holding; add symbol to watchlist (`source="autopilot"`, `reason="autopilot_exit"`). |
| SWITCH | EXIT leg as above, then BUY the `switch_candidate` with budget `min(sale proceeds, cash_after_sell − min_cash_floor)` (whole shares; remainder stays in cash). New holding: sector from the shelf idea, `buy_date=review_date`. **Resolvability gate:** buy only if `close_on(candidate)` succeeds — otherwise execute the EXIT leg alone, log + alert `switch_buy_skipped`. (Closes the "validate before promotion" follow-up for autopilot buys; existing promotion machinery then covers the new symbol.) |

**Trade ordering within a run (deterministic):** all sells first (EXIT,
SWITCH sell legs, TRIM — symbol asc), then buys (SWITCH buy legs first, then
ADDs) in descending `AdviceRecord.confidence`, ties broken symbol asc. Sells
free cash before buys consume it; a cash-constrained run therefore always
produces the same trades.

**Guardrails (all config-backed, `autopilot.*` keys in config.yaml):**
- `min_cash_floor` ₹10,000 — no BUY may take cash below it (seed exempt).
- `add_cooldown_td` 5 trading days per symbol — envelope staying UP must not
  compound buys daily.
- `add_tranche_pct` 25 (of current position market value), `trim_pct` 25.
- **Idempotency:** skip entirely when `last_autopilot_run == review_date`;
  additionally skip any trade whose `txn_id` already exists in the ledger
  (protects against pipeline re-runs mid-crash).
- Dividends stay accrued on the holding (existing corp-action flow, P&L
  already dividend-inclusive); cash moves **only** on trades. On SELL,
  `dividends_received` transfers pro-rata into `realized_pnl` and is reduced
  on the remaining lot.

**Pipeline hook** (`core/portfolio/pipeline.py`): after step 3, before digest.
Digest gains a `trades` section; executed trades emit `AlertEvent`
(`kind="autopilot_trade"`, severity `warning` for SELL sides, `info` for
buys) through the existing delivery machinery; the EOD push line appends
"N trade(s) executed". Value-history append happens after execution so the
equity curve reflects post-trade state. Non-fatal per user, like every other
pipeline step.

## 5. Seeding (one-time ops, prod via `railway ssh`)

`scripts/seed_autopilot.py --user primary --pot 1000000` (idempotent: refuses
to run if the user already has holdings or seed transactions unless
`--force-empty-check-bypass`):

1. Read `/app/data/managed_tickers.json` (16 tickers / 4 sectors).
2. Budget = pot / n_tickers (₹62,500 each at ₹10L/16). For each ticker:
   `qty = floor(budget / close_on(ticker, today))`, whole shares; skip + warn
   any ticker whose price fetch fails (its budget stays in cash).
3. Write holdings (`avg_buy_price = adj_avg_price = close`, `buy_date =
   today`), one `source="seed"` BUY transaction each.
4. Set `capital_in = pot`, `cash_deployable = pot − Σ trade values`,
   `autopilot = true`. Append day-0 value-history line.

Manual UI adds after seeding: POST /portfolio/holdings records a
`source="manual"` BUY and **increases `capital_in`** by the trade value
(fresh money — cash unchanged). Row delete becomes a `source="manual"` SELL
at the latest close, crediting cash (books stay consistent; delete is no
longer a silent row removal when cash accounting is live).

## 6. API additions (extend existing /portfolio router)

- `GET /portfolio/transactions?limit=50` — newest first, from the JSONL.
- `GET /portfolio/performance` — `{cash, capital_in, market_value,
  total_equity, realized_pnl, unrealized_pnl, total_return_pct, day_change,
  day_change_pct, history:[value-history lines]}`. market_value uses latest
  closes via the digest's close map when fresh, else `close_on` walkback.
- Existing POST/DELETE holdings routes extended per §5 (response shapes
  unchanged — additive fields only).

## 7. UI (src/frontend/prototypes/portfolio.jsx — follow existing patterns)

- Hero: un-hide **Cash** and **day-change** when live (wired to
  /portfolio/performance); add **AUTOPILOT** pill next to `PORTFOLIO · LIVE`;
  wire the existing demo range chart to `history`.
- P&L strip: realized / unrealized / total return vs invested capital.
- **Recent activity** section goes live: latest 10 transactions — date,
  BUY/SELL chip, symbol, qty @ price, realized P&L on sells, trigger tag
  (e.g. `trim_profit_reversion_elevated`), "View all" expands to the full
  ledger (client-side, `limit=500`).
- Demo mode (`?demo=1`) untouched; loading/empty states as today. Empty
  portfolio + autopilot off renders exactly as today (feature is invisible
  until seeded).

## 8. Testing

Unit (new `tests/unit/test_autopilot*.py`): every verdict path incl. SWITCH
two-leg + resolvability-gate skip; whole-share flooring; cash floor; ADD
cooldown; trim-to-zero; idempotent re-run (date marker AND txn_id dedupe);
realized P&L with pro-rata dividends; capital_in accounting for manual
add/delete; seed script (tmp dirs, fake price_lookup, idempotency refusal).
Store: transaction/value-history append+tolerant load, `reduce_holding`.
API: transactions + performance routes, extended POST/DELETE.
Integration: pipeline with autopilot on/off — off must leave portfolio.json
byte-identical after advice.
**Isolation invariant test:** autopilot never writes under `data/rl/paper/`
or any PredictionStore path (mirrors the Phase B paper-lane isolation test).
Baseline to preserve: 1831 passed / 5 skipped (+ known pre-existing failures
ticket).

## 9. Out of scope

Real broker execution (never); fees/slippage/taxes modelling (fees=0; LTCG
already handled advisor-side); multi-user file locking (Phase A follow-up
stands — single pipeline writer + rare UI writes acceptable); buying
discovery shelf ideas outside SWITCH (a future "discovery auto-entry" lane);
email channel; Phase D itself (this feature *feeds* it — join via
`advice_ref`).

## 10. Rollout

1. Implementation in a **new chat** per Compass phase protocol:
   plan at `docs/superpowers/plans/2026-07-11-compass-autopilot.md`
   (superpowers writing-plans → subagent-driven dev, per-task review).
2. Merge to main after final review → push (= Railway deploy).
3. Ops: `railway ssh` → run seed script for user `primary`, pot ₹10,00,000.
4. Verify: next trading-day pipeline executes verdicts; /portfolio shows
   cash/equity curve/activity; transactions ledger populated with 16 seed
   BUYs + day-0 value point.

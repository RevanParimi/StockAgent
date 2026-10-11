# Compass Autopilot — Developer Guide

**Edition:** 2026-10-10 · **Code inspected:** `61c85d6`, the code production runs

**Scope:** the virtual money path, from the advisor's verdict for each holding
to the executed trade, the ledgers and the screens that show them.

Every trading day, after the daily reviews finish, the advisor gives each
holding a verdict and the autopilot executes it on a **virtual** portfolio:
mock money, real NSE closes, a full audit trail, no human click. The
[technical design](TECHNICAL_DESIGN.md) summarises this path in
[section 6](TECHNICAL_DESIGN.md#6-portfolio-advice-and-virtual-execution) and
its P/L measures in section 7. Measured production state lives only in
[KT section 1](TECHNICAL_DESIGN.md#production-state-at-this-edition). Work
planned in PI-2026-09 is labelled **Planned** with its story.

Three rules hold throughout:

1. **Virtual money only.** There is no broker call anywhere in the code.
2. **Rules decide, the LLM narrates.** The verdict and every trade are
   deterministic; the narrator writes the explanation after the decision, and
   a template replaces it when the call fails.
3. **The money path stays in its own store.** The autopilot writes only under
   `data/portfolio/<user>/`, plus one designed exception: a SWITCH buy promotes
   the new symbol into the managed list (section 12). It never writes a
   prediction store or the paper lane.

---

## 1. The daily pipeline

```text
 rl_daily_review (Mon–Fri 16:30 IST) reviews the previous session for every managed ticker
        |  then, in the same job (not on a clock):
        v
 run_post_review_pipeline(review_date)                  core/portfolio/pipeline.py
   skipped when advisor.enabled is false or review_date is not a trading day
   for each active user with holdings:
     1   sync_corp_actions        splits, bonuses, dividends BEFORE any rule
     -   shelf ideas and their session closes (candidate prices, once per run)
     2   refresh_events_calendar  results dates for held symbols (stale cache on failure)
     3   for each holding:
           session_close            the session's close and the bar it came from
           build_signals            envelope, feedback log, ATR stop, earnings distance
           identity check           is this close the holding's price basis?
           gated_decide             verdict, with the data and identity checks (section 4)
           instrument stamp, narrate, append to advice_ledger.jsonl
           switch evaluations       how every shelf candidate was judged
     3.5 autopilot.execute_advice   THE MONEY MOVES HERE (section 6)
         record_value_point         one equity point per trading day
     3.6 reconcile                  ledger versus portfolio, detect and alert only
     4   build_digest               digests/<date>.json
     5   alerts and EOD delivery    escalations, trades, switch_buy_skipped, digest notice
```

Every step is non-fatal: a failure is logged and the next step runs. A
holding whose advisor call fails gets no advice that day and is not traded.

**Other triggers.** `POST /portfolio/run-advisor` (owner only, optional
`review_date`, accepted as background work) and the scheduler API's review
task run the same pipeline. A future `review_date` is refused.

## 2. Where everything lives

```text
core/portfolio/
  pipeline.py            the daily orchestration above
  advisor.py             build_signals(), data_gate_blocks(), decide()
  autopilot.py           execute_advice(), record_value_point(): the executor
  store.py               PortfolioStore: every per-user read and write, the lock
  pricing.py             close_on() and session_close(), shared with the daily review
  corp_actions.py        split, bonus and dividend adjustment
  identity_reconcile.py  plan/apply for demergers, renames, relistings (section 5)
  reconcile.py           ledger versus portfolio checks (section 8)
  promotion.py           promote_symbol() into the managed list (section 12)
  narrator.py            bulk-tier narration with a template fallback
  digest.py              the EOD digest
services/data/verdict_store.py      the advisor's read path into prediction stores
src/backend/shared/schemas/portfolio.py   Holding, Portfolio, AdviceRecord, TransactionRecord, …
services/api/routes/portfolio_api.py      /portfolio routes
src/frontend/prototypes/portfolio.jsx     the portfolio screen
scripts/seed_autopilot.py                 one-time equal-weight seed
```

Per-user state, created on first use (`primary` is the default user):

```text
data/portfolio/<user>/
  portfolio.json                  derived state: holdings, watchlist, cash, flags
  portfolio.lock                  the per-user file lock
  transactions.jsonl              append-only book of record: every BUY, SELL and DIV
  value_history.jsonl             one equity point per trading day
  advice_ledger.jsonl             every advice record, with its data gate and instrument
  switch_evaluations.jsonl        every shelf candidate considered, taken or declined
  identity_reconciliations.jsonl  operator reconciliations (section 5)
  digests/<date>.json, briefs/, weekly/
  portfolio.json.corrupt-<time>   a corrupt file moved aside (section 8)
  portfolio.json.pre-identity-<time>  copy taken before a reconciliation apply
```

`transactions.jsonl` is the book of record and `portfolio.json` is derived
from it. When they disagree, the ledger is right (section 8).

## 3. The advisor

### 3.1 Signals

`build_signals` assembles each holding's inputs. Every read is non-fatal;
a missing artifact leaves a conservative default.

| Signal | Source and rule |
|---|---|
| Close | `session_close`: the session's own close and the date of its bar; a carried-forward close is marked not fresh |
| Stop | 3 × ATR(20) as % of price, clamped to the market-cap bucket: large 8–12%, mid 12–18%, small 15–22%. Unknown market cap reads as mid; a conservative profile tightens one bucket |
| Unrealised P/L | Against `adj_avg_price`, dividends included |
| Envelope direction | The last remaining forecast close against today's close: UP above +1%, DOWN below −1%, else FLAT |
| Confidence, trend | Mean confidence of the remaining rows; last minus first |
| Reversion prior | The envelope's conviction streak |
| Regime, thesis | The latest feedback entry's regime; the latest thesis review |
| Direction accuracy | Share of the cycle's last 7 feedback entries graded correct |
| Position weight | The holding's share of the portfolio **at cost** (`adj_qty × adj_avg_price`) |
| Earnings distance | Trading days to the next results event |
| Peak close | The highest close since the buy date |
| Forecast gate | The worst gate among the remaining rows, and their source run ids |

The envelope and feedback log are read from `<holding sector>/<TICKER>`
through `VerdictStore`. Promotion files the managed entry under the
holding's sector, so the advisor reads the store the review writes. A holding
whose sector was edited away from its managed entry's reads a store with no
envelope: no ADD or TRIM can fire, and only the stop rules can act on it.

### 3.2 Verdict cascade

The cascade is **EXIT → TRIM → ADD → HOLD**; the first that fires wins.

| Verdict | Fires when |
|---|---|
| EXIT | Any of: unrealised loss at or beyond the stop; thesis broken and envelope DOWN; a re-forecast for `external_shock`, `thesis_break` or `preopen_shock` and envelope DOWN; `MACRO_CRISIS` and envelope DOWN; or a trailing stop: the peak was at least 10% above cost and the close has since fallen from it by at least the stop |
| TRIM | Profit of at least 25%, and confidence falling by 0.05 or more, or a reversion prior of 0.20 or more |
| ADD | Envelope UP, regime not `MACRO_CRISIS` or `RISK_OFF`, position weight below 10%, and at least 60% of the last 7 reviews correct |
| HOLD | Nothing above |
| SWITCH | An EXIT becomes SWITCH when an active shelf idea qualifies (below) |

**SWITCH.** The top 5 active shelf ideas by conviction are judged. One
qualifies when it is not already held, its sector is strictly underweight
compared with the exiting holding's sector, and its conviction beats the
holding's mean envelope confidence by at least 0.15. The data gate is checked
last (section 4). The qualified idea with the highest conviction is the
destination. Every candidate is recorded in `switch_evaluations.jsonl` with
`taken` or the reason it was declined (`already_held`,
`sector_not_underweight`, `conviction_gap_too_small`, `data_gate`,
`not_best`), so the rule's precision can be measured on what it declined as
well as what it took.

**Holding-age softening.** A TRIM on a holding aged 10 to 12 months, whose
thesis is not known to be broken, becomes HOLD with the note `WAIT_FOR_LTCG`.
EXIT is never softened. This is a product rule, not individual tax advice.

**Notes.** `EARNINGS_GAP_PROTECTION` marks a profitable holding with results
within 3 trading days. `SECTOR_CONCENTRATION_HIGH` marks a single position at
30% or more of the portfolio at cost. `DATA_GATE` and `IDENTITY` are
section 4.

**Example (stop):** a large-cap holding with a 2.5% ATR gets 3 × 2.5 = 7.5%,
below the large-cap floor, so its stop is 8%. Bought at ₹1,000, it exits when
the close reaches ₹920.

## 4. Data and identity checks on advice

`gated_decide` computes the verdict twice, with and without the checks, and
`decision_gate.mode` picks one: `enforce` keeps the gated verdict, `record`
keeps the ungated one. When they differ, the advice record's `data_gate` says
what was, or would have been, withheld, why, and which forecast runs it
rested on. That record lives on the user's own advice ledger; the shared gate
log never holds a user id.

**New risk needs verified evidence.** ADD and a SWITCH's buy leg add risk, so
in `enforce` mode they need both:

- the holding's close is from the review session's own bar; and
- the forecast rows behind the signal come from an actionable analysis. No
  rows, or rows issued before provenance stamps existed, do not count.

A blocked ADD becomes HOLD with the note `DATA_GATE`. A blocked SWITCH
destination falls back to the next qualifying idea, or to a plain EXIT with
`DATA_GATE`. A shelf idea is never a destination when its deep dive was not
actionable (or carries no gate), its identity is unresolved, or its close is
from an earlier bar.

**Risk reduction is never blocked by data.** EXIT and TRIM go ahead on a
stale close or an unverified forecast, so missing data cannot trap a
position. The advice records the weakness in `data_gate`.

**Example:** a holding's envelope was built on an abstained STRONG BUY and
points up. Unenforced, that gives ADD and a virtual buy. Enforced, it gives
HOLD with `DATA_GATE`, and no buy.

**Identity hold.** A holding is held outright, EXIT and TRIM included, with
the note `IDENTITY`, when:

- its symbol's identity is unresolved in the instrument registry; or
- its price basis changed (a demerger or a relisting) since the basis its
  cost was booked on: the buy date, or the latest identity reconciliation.

This is the corporate-action rule applied to identity. The daily sync keeps a
1:1 bonus from looking like a 50% crash, and a demerger is the same trap. A
rename keeps the basis, so a renamed holding is advised as before. Every
advice record keeps the instrument its close priced (`instrument`), which a
later registry change never rewrites.

**Example:** 100 PARENT bought at ₹1,000; PARENT demerges into PARENTA (60%
of the cost) and PARENTB (40%), and the ticker now trades as PARENTA at ₹600.
Unreconciled, 600 against 1,000 reads −40%, a stop breach, and the advisor
says EXIT: a sale on a loss that never happened. Enforced, it says HOLD with
`IDENTITY`. In `record` it keeps EXIT, and `data_gate` names the identity.

## 5. Identity reconciliation

Reconciliation is an operator's step
([identity_reconcile.py](../core/portfolio/identity_reconcile.py)); nothing
runs it on a schedule.

- `python -m core.portfolio.identity_reconcile plan` is read-only. It lists
  every holding the advisor would hold for identity, with the registry's
  proposal. The proposal comes from a recorded, evidenced event with
  `successors` (ticker, shares per old share, share of the cost), or it says
  what must be recorded first. For the example above it proposes PARENTA 100
  @ ₹600 (₹60,000) and PARENTB 100 @ ₹400 (₹40,000), so the cost is conserved.
- `apply --plan … --approve <digest>` refuses unless a fresh plan has the
  approved digest. It copies `portfolio.json` aside, replaces the old holding
  with its successors under the user's lock, and logs
  `identity_reconciliations.jsonl`. A second apply is refused.

The ledger reconciler treats the successors as `unverifiable`, as after a
split: they arrive without ledger rows.

**Known limits of `apply`.** Its digest check runs before it takes each
user's lock, and under the lock it does not look at the holding again. A sale
of the same holding in that window still gets successors sized from the
plan's figures: 50 PARENT left would become 100 PARENTA and 100 PARENTB. One
apply also names every backup with the same timestamp, so for a user with two
reconciled holdings the second copy overwrites the first and the only backup
holds the half-applied portfolio; the audit log's `before` records still hold
each old holding. The shipped registry records no `successors`, so `apply`
applies nothing today. **Planned:** a fix for both (SA-008 change 1). Until
it lands, record no `successors` and run no `apply` in production.

## 6. Execution rules

[autopilot.py](../core/portfolio/autopilot.py). Whole shares only
(`floor`); no fees, taxes or slippage (section 9). The price is the close the
advisor used. Within one run, each symbol keeps one price: the first close
used for it.

| Verdict | Action |
|---|---|
| HOLD | Nothing. The run marker is still stamped (section 8). |
| EXIT | Sell the whole `adj_qty`. The holding is removed and the symbol joins the watchlist (`source="autopilot"`, reason `autopilot_exit`). |
| TRIM | Sell `max(1, floor(adj_qty × 25%))`; when less than one share would remain, sell everything (`trim_to_zero`). |
| ADD | Buy into an existing holding only. Budget = the smallest of 25% of the position's value, the headroom to a 10% weight after the trade, and cash above the ₹10,000 floor. Skipped within 5 trading days of the last autopilot buy of that symbol, or when the budget is under one share. |
| SWITCH | Sell the whole position (EXIT rules), then buy the destination with the smallest of the sale proceeds and cash above the floor. |

**The SWITCH buy leg re-checks its own inputs** before spending:

- the destination's close must come from the session's own bar; and
- the destination's identity must be resolved.

In `enforce` mode a failure skips the buy; in `record` mode it buys and logs
that the gate would have skipped it. An unpriceable destination or a budget
under one share also skips the buy. Whenever the sell executes and the buy
does not, the user gets a `switch_buy_skipped` alert saying the proceeds
stayed in cash. A completed buy promotes the destination into the managed
list (section 12).

**Order.** Sells first (EXIT, SWITCH sell legs and TRIM, by symbol), so cash
is freed before it is spent. Then buys: SWITCH buy legs, then ADDs by
confidence (highest first, ties by symbol).

**The weight cap.** A buy of X into a position worth `pos`, when all
holdings are worth `total` (cash excluded), keeps
`(pos + X) / (total + X) ≤ cap`, so `X ≤ (cap × total − pos) / (1 − cap)`.
Holdings without a close that day are valued at cost.

**Example:** a ₹20,000 position, holdings worth ₹5,00,000 in all, and
₹60,000 cash. The tranche is ₹5,000; the headroom is (0.10 × 5,00,000 −
20,000) / 0.9 = ₹33,333; cash above the floor is ₹50,000. The budget is
₹5,000, which at ₹1,180 a share buys 4 shares.

## 7. Cash deployment

How cash moves today:

- **A new position opens only through a SWITCH**, which puts one sale's
  proceeds into a shelf idea.
- **ADD tops up a stock already held**, capped at a 10% weight after the
  trade (`advisor.max_position_pct`).
- **A plain EXIT leaves its proceeds in cash.** Nothing reinvests them.
- **The SWITCH buy spends the whole proceeds**, with no position or sector
  cap, so a destination can exceed 10% of the portfolio on its first day.
- **The seed** spreads the starting pot equally across the enabled managed
  tickers (section 11).

**Example:** a ₹10,00,000 portfolio exits two holdings worth ₹1,50,000 each
on a day with no qualifying shelf idea. Cash rises by ₹3,00,000 and stays
there; the remaining holdings can each take at most a 10% weight through
ADDs, 25% of their own value at a time.

**Planned:** one sizing rule for every autopilot buy, including the SWITCH
buy (SA-050). In a normal market, idle cash goes into shelf ideas that pass
the checks; cash is held on purpose only in a crisis (SA-049, behind a switch
that ships off).

## 8. Idempotency, locking and crash safety

**Gating.** The autopilot does nothing unless all three hold:
`autopilot.enabled` (env `AUTOPILOT_ENABLED`, default true), the user's
`portfolio.autopilot` flag, and cash accounting (`cash_deployable` is set).
When it is off, a pipeline run leaves `portfolio.json` byte-identical.

**Two layers stop a trade from executing twice:**

- **The run marker.** `last_autopilot_run` holds the last executed review
  date. A run for a date on or before it does nothing, so a retried past date
  can never trade at stale prices against today's portfolio; a missed day
  replayed forward still runs. A future date is refused without stamping the
  marker.
- **Transaction ids.** `txn_id = sha256(user|date|symbol|side|ref)[:16]`,
  where `ref` is `<advice date>|<advice symbol>|<rationale hash>`. An id
  already in the last 2,000 ledger rows is skipped.

**The lock.** Every read-modify-write of a user's portfolio holds
`portfolio.lock` (re-entrant, 30-second timeout), and the executor reloads
`portfolio.json` under it, so a concurrent API change is never reverted by a
stale snapshot.

**Write order.** All trades are decided in memory, then appended to
`transactions.jsonl`, then `portfolio.json` is saved once. A crash between
the two cannot double-execute, because the ids dedupe, but it leaves the
ledger ahead of the portfolio. With the marker in place, a dedupe skip is
exactly that signature, and the executor logs:

```text
WARNING [autopilot] SELL MARUTI (EXIT) already in ledger but run marker predates this run —
possible ledger/portfolio divergence from a mid-run crash; manual reconciliation may be needed
```

**The reconciler** ([reconcile.py](../core/portfolio/reconcile.py)) runs
daily after the autopilot. It detects and alerts, and never repairs:

- each row's `cash_before` matches the previous row's `cash_after` (within
  ₹0.05);
- the ledger's net cash matches `cash_deployable` (within ₹1);
- each symbol's bought minus sold quantity matches `adj_qty`. Symbols with a
  split, a bonus or an identity reconciliation are `unverifiable`, because
  those change quantity without a ledger row.

Drift sends one critical alert. A human repairs `portfolio.json` from the
ledger.

**A corrupt `portfolio.json`** is moved aside as
`portfolio.json.corrupt-<time>`, and one critical alert goes out. Reads
return an empty portfolio so the API stays up, and every save is refused
until a valid file is restored.

## 9. Money math

`Holding` keeps two books:

| Fields | Meaning | Changed by |
|---|---|---|
| `qty`, `avg_buy_price` | Money actually put in | Buys only |
| `adj_qty`, `adj_avg_price` | The live position after splits, bonuses and trades | Corporate actions, buys and sells; all P/L and stop math uses these |
| `dividends_received` | Dividends credited and not yet realised | Dividend sync adds; a sale realises its pro-rata share |

`Holding.sell(qty, price)` returns realised P/L including the pro-rata
dividend share and removes that share, so unrealised P/L never counts it
twice. A dividend also credits cash and writes a `DIV` ledger row when cash
accounting is on.

| Portfolio figure | Meaning |
|---|---|
| `capital_in` | Mock money ever put in: the seed pot plus manual adds. The screen calls it "Invested". |
| `cash_deployable` | Cash available now |
| Total equity | Market value of holdings plus cash |
| Total return | `(total equity − capital_in) / capital_in` |

**What the figures leave out.** No brokerage, STT, stamp duty, exchange fee,
DP charge or tax is charged, and there is no benchmark. The KT's
[section 7](TECHNICAL_DESIGN.md#virtual-pl) gives the cost of a real round
trip and the report families. **Planned:** costs and tax in paper P&L
(SA-048) and a Nifty comparison with honest labels (SA-051).

## 10. Ledger formats

`transactions.jsonl`, one `TransactionRecord` per line:

| Field | Notes |
|---|---|
| `txn_id` | The dedupe key (section 8) |
| `date`, `ts` | Review date; UTC timestamp |
| `user_id`, `symbol`, `side` | `BUY`, `SELL` or `DIV` |
| `qty`, `price`, `value` | Whole shares (0 for `DIV`, whose price is the dividend per share) |
| `cash_before`, `cash_after` | Cash on either side of the row |
| `holding_qty_after` | `adj_qty` afterwards; 0 when the position closed |
| `realized_pnl`, `cost_basis`, `pnl_pct` | SELL only; the cost basis is `adj_avg_price` at the sale |
| `source` | `autopilot`, `seed` or `manual` |
| `verdict`, `advice_ref`, `triggers`, `note`, `reason` | The advice behind an autopilot row; `advice_ref` joins the advice ledger, and `reason` is the narrative at execution |

`value_history.jsonl`, one point per trading day. A point dated on or before
the last one is skipped, so re-runs and stale replays add nothing:

```json
{"date": "2026-10-09", "market_value": 742310.5, "cash": 263011.4, "total_equity": 1005321.9,
 "capital_in": 1000000.0, "day_change_pct": 0.21, "change_span_days": 1}
```

`change_span_days` is the gap behind `day_change_pct`: 3 after a weekend.

`advice_ledger.jsonl` holds every `AdviceRecord`: verdict, close, stop,
triggers, notes, confidence, narrative, SWITCH candidate, rationale hash,
`data_gate` and `instrument`.

Every reader skips a torn or corrupt line and logs it. All four files are
append-only; never rewrite them in place. The nightly backup's drill warns
when one shrinks or changes earlier bytes (KT section 10).

## 11. Seeding, API and screen

**Seed** (once per user):

```text
python scripts/seed_autopilot.py --user primary --pot 1000000
```

It splits the pot equally across the enabled managed tickers, buys whole
shares at the latest close with one `source="seed"` BUY each, sets
`capital_in` to the pot and `cash_deployable` to what is left, turns the
autopilot on and records the day-0 value point. It refuses a user who already
has holdings or transactions.

**API** (`/portfolio`, for the signed-in user):

| Method and path | Effect |
|---|---|
| `GET /portfolio` | Holdings and watchlist with live marks |
| `POST /portfolio/holdings` | Manual BUY at the buy date's close. It is fresh capital: `capital_in` rises, cash does not change, and a `manual` row is written. An identical same-day resubmit is deduped. The symbol is promoted as held. |
| `DELETE /portfolio/holdings/{symbol}` | Manual SELL at today's close (cost if no close), cash credited, `manual` row written. Unless the symbol is on the watchlist, its portfolio-origin managed entry is disabled |
| `POST`, `DELETE /portfolio/watchlist…` | Watchlist changes; an added symbol is promoted as watchlist, a removed one demoted the same way |
| `POST /portfolio/import-csv` | Bulk import of holdings |
| `GET /portfolio/transactions?limit=N` | The ledger, newest first |
| `GET /portfolio/performance` | Cash, `capital_in`, market value, equity, realised and unrealised P/L, total return, day change, the autopilot flag and the equity history (at most 2,000 transactions and 400 points read) |
| `GET /portfolio/advice`, `GET /portfolio/digest/latest` | The advice ledger's tail; the latest digest |
| `POST /portfolio/run-advisor` | Owner only: run the pipeline in the background |

**Screen** ([portfolio.jsx](../src/frontend/prototypes/portfolio.jsx),
in-browser JSX, no build step). With live data and cash accounting on, it
shows total equity with an AUTOPILOT pill, the day's change, a stats row
(Invested, Total return, Cash, Realized P&L), the equity curve from two
points on, and recent trades. `?demo=1` forces demo data.

## 12. Promotion into the managed list

[promotion.py](../core/portfolio/promotion.py). A symbol that becomes a
holding (manual buy, CSV import, SWITCH buy) or a watchlist entry (manual, or
a shelf idea) is added to `data/managed_tickers.json`, so the scheduled jobs
give it envelopes, reviews and a dossier.

- A sector outside the four native ones is analysed by the generic graph; a
  malformed sector key is rejected.
- The list is capped at 40 enabled entries (`portfolio.max_managed_tickers`).
  At the cap, the oldest watchlist-origin entry is disabled to make room;
  held and manual entries are never evicted. With nothing evictable, the
  promotion is refused.
- Each entry records a cadence, daily for held and weekly for watchlist. The
  scheduler API's review and backfill routes honour it, reviewing watchlist
  names only on Fridays (`portfolio.weekly_review_weekday`). The scheduled
  16:30 job does not read it, so every enabled entry is reviewed every
  weekday.
- Removing a holding or watchlist entry demotes the symbol: a held or
  watchlist-origin entry is disabled, with its history kept. The original,
  manually managed entries are never touched.
- Promoting a symbol whose entry is disabled re-enables it. Promotion does
  not consult the instrument registry, so buying or watching a retired
  ticker such as TATAMOTORS puts it back on the schedule. Its identity is
  still unresolved, so in `enforce` mode its advice is held and its reviews
  stop; in `record` mode both are only recorded.

## 13. Configuration

| Setting (config key) | Default | Meaning |
|---|---|---|
| `AUTOPILOT_ENABLED` (`autopilot.enabled`) | true | Global switch |
| `AUTOPILOT_ADD_TRANCHE_PCT` (`autopilot.add_tranche_pct`) | 25.0 | ADD buys up to this share of the position's value |
| `AUTOPILOT_TRIM_PCT` (`autopilot.trim_pct`) | 25.0 | TRIM sells this share of the quantity |
| `AUTOPILOT_MIN_CASH_FLOOR` (`autopilot.min_cash_floor`) | 10000.0 | Cash never spent below this |
| `AUTOPILOT_ADD_COOLDOWN_TD` (`autopilot.add_cooldown_td`) | 5 | Trading days between autopilot buys of one symbol |
| `advisor.max_position_pct` | 10.0 | ADD eligibility and the post-trade weight cap |
| `advisor.atr_period`, `advisor.stop_atr_mult`, `advisor.stop_buckets` | 20, 3.0, large [8, 12] · mid [12, 18] · small [15, 22] | Stops |
| `advisor.trim_profit_pct`, `advisor.trail_arm_pct` | 25.0, 10.0 | TRIM threshold; trailing-stop arming |
| `advisor.confidence_decline_threshold`, `advisor.reversion_prior_elevated` | 0.05, 0.20 | TRIM triggers |
| `advisor.envelope_flat_band_pct`, `advisor.add_min_direction_accuracy` | 1.0, 0.60 | Envelope direction; ADD accuracy floor |
| `advisor.switch_conviction_gap`, `advisor.switch_eval_max_candidates` | 0.15, 5 | SWITCH |
| `advisor.ltcg_wait_min_months`, `advisor.earnings_gap_days`, `advisor.sector_concentration_warn_pct` | 10, 3, 30.0 | Notes |
| `decision_gate.mode` | `record` | Section 4; production's value is in KT section 1 |

The `autopilot.*` keys are not in config.yaml, so the code defaults apply.

## 14. Tests

Run from the repository root with the project's virtual environment; every
run is hermetic (KT section 13). A quick loop:
`python -m pytest tests/unit -k "autopilot or portfolio" -q`.

| Tests (`tests/unit/`) | What they pin |
|---|---|
| `test_autopilot_schemas.py`, `test_autopilot_store.py`, `test_autopilot_settings.py` | Transaction records and `Holding.sell`, ledger append and read, defaults |
| `test_autopilot_executor_sells.py`, `…_adds.py`, `…_switch.py` | Verdict rules, gating byte-identity, run marker, dedupe, stale-date refusal, sizing, SWITCH legs, value points |
| `test_autopilot_pipeline.py`, `test_portfolio_pipeline.py`, `test_scheduler_portfolio_hook.py` | The pipeline steps, digest trades and the `switch_buy_skipped` alert |
| `test_autopilot_isolation.py` | Executor writes stay inside `data/portfolio/<user>/` |
| `test_autopilot_wave1.py`, `test_portfolio_locking.py`, `test_portfolio_reconcile.py` | Locking with a fresh reload, future-date refusal, reconciliation |
| `test_portfolio_advisor.py`, `test_portfolio_advisor_switch.py`, `test_portfolio_store_switch_evals.py` | The cascade, SWITCH and candidate evaluation rows |
| `test_decision_gate_portfolio_sa003.py`, `test_identity_portfolio_sa008.py`, `test_identity_chain_sa008.py` | The data and identity checks, and reconciliation |
| `test_portfolio_corp_actions.py`, `test_portfolio_pricing.py`, `test_portfolio_promotion.py` | Corporate actions, closes, promotion |
| `test_seed_autopilot.py`, `test_autopilot_api.py`, `test_portfolio_api.py` | Seeding and the routes' accounting |

Never weaken the byte-identity or isolation tests to make a change pass: they
encode the two constraints most likely to fail silently.

## 15. Operations

| Question | How to answer it |
|---|---|
| Did today's run trade? | `GET /portfolio/digest/latest` → `trades`, or `GET /portfolio/transactions?limit=20` |
| Is the equity curve moving? | `GET /portfolio/performance` → `history` |
| Why was an ADD or SWITCH not taken? | The advice ledger's `data_gate` and notes (`DATA_GATE`, `IDENTITY`) |
| Was a holding held for identity? | Run `identity_reconcile plan` (read-only) |
| Divergence warning or reconcile alert | Section 8: repair `portfolio.json` from the ledger, by hand |
| Turn the autopilot off for one user | Set `"autopilot": false` in that user's `portfolio.json` |
| Turn it off for everyone | Set `AUTOPILOT_ENABLED=false`; a Railway variable change redeploys |
| Re-seed a user | Move `data/portfolio/<user>/` aside first, or the seed refuses |

**Known quirks:**

- The digest is built after the trades with the day's closes. A switched-in
  symbol has no advice record yet, so it shows `NO_DATA` on its first day.
- Manual trades use a ref built from the date, quantity and price, so an
  identical retry on the same day is deduped; a different price is a new row.
- `close_on` walks back over non-trading days, and the pipeline skips
  non-trading review dates.
- Standalone scripts must add the repository root and `src` to `sys.path`,
  as `scripts/seed_autopilot.py` does; pytest gets both from `pyproject.toml`.

## 16. Planned work

- One sizing rule for every autopilot buy (SA-050), and idle cash deployed
  in normal markets (SA-049).
- Trading costs and tax in paper P&L (SA-048), and a Nifty comparison with
  honest labels (SA-051).
- A safe `identity_reconcile apply` (SA-008 change 1).
- Learning from executed advice remains future work: every autopilot row
  carries `advice_ref`, which joins its outcome to the advice that caused it,
  and the nightly auditor already grades issued advice (KT section 7).

# Compass Autopilot — Developer Guide

**Edition:** 2026-10-22 · **Code inspected:** `020d3c2`

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
  advice_outcomes.jsonl           the nightly auditor's graded rows
  weekly_scorecard.jsonl          one results row per ISO week, written once
  weekly_scorecard.lock           guards its write-once append
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
| Position weight | The holding's share of **total equity**: every holding at the review's close (at cost when it has none) plus cash ([sizing.py](../core/portfolio/sizing.py)) |
| Sector weight | The same share for all holdings with the holding's sector label |
| Earnings distance | Trading days to the next results event |
| Peak close | The highest close since the buy date |
| Forecast gate | The worst gate among the remaining rows, and their source run ids |

The envelope and feedback log are read from `<holding sector>/<TICKER>`
through `VerdictStore`. The review writes `<managed entry's sector>/<TICKER>`.
Promotion files a new managed entry under the holding's sector and keeps an
existing entry's sector, and a buy candidate carries an existing entry's
sector (below), so the advisor reads the store the review writes. A holding
whose sector was edited away from its managed entry's reads a store with no
envelope: no ADD or TRIM can fire, and only the stop rules can act on it.

### 3.2 Verdict cascade

The cascade is **EXIT → TRIM → ADD → HOLD**; the first that fires wins.

| Verdict | Fires when |
|---|---|
| EXIT | Any of: unrealised loss at or beyond the stop; thesis broken and envelope DOWN; a re-forecast for `external_shock`, `thesis_break` or `preopen_shock` and envelope DOWN; `MACRO_CRISIS` and envelope DOWN; or a trailing stop: the peak was at least 10% above cost and the close has since fallen from it by at least the stop |
| TRIM | Profit of at least 25%, and confidence falling by 0.05 or more, or a reversion prior of 0.20 or more |
| ADD | Envelope UP, regime not `MACRO_CRISIS` or `RISK_OFF`, position weight below 10% of total equity, and at least 60% of the last 7 reviews correct |
| HOLD | Nothing above |
| SWITCH | An EXIT becomes SWITCH when a buy candidate qualifies (below) |

**Buy candidates.** At each review the autopilot may buy only from this
portfolio's candidates
(`core/discovery/candidates.py`):

- active shelf ideas whose latest deep dive is at most 30 days old
  (`discovery.redive_after_days`). An older idea waits for Saturday's re-dive.
- the user's own watchlist stocks whose latest analysis is a BUY or STRONG BUY
  with an actionable data gate, conviction 0.55 or more, at most 30 days old,
  for a stock NSE lists as a company (`discovery.watchlist_buys`). The entry
  band is 97–102% of the close on the analysis day, as a deep dive sets it. A
  stock the autopilot sold onto the watchlist (`source="autopilot"`) does not
  qualify.

Each candidate carries the sector it is bought and held under, which is
what the sizing rule's sector cap (section 6) and the SWITCH's sector test
count:

- a managed stock: its managed entry's sector, enabled or not, because the
  review and the monthly forecast write its predictions there;
- otherwise a shelf idea's own sector (the deep dive's `infer_sector`), and a
  watchlist stock's item sector when it is a well-formed key, else
  `infer_sector`. Never a fixed `generic`. `infer_sector` takes the
  registry's ticker map, else Yahoo's industry mapped to a registry sector
  ("Auto Parts" is `automobile`), else `generic`.

**Example:** on Tuesday 20 Oct a shelf idea last dived on 12 Sep is not a
candidate. A watchlist stock analysed on 17 Oct as a BUY at 0.68, actionable,
with a ₹500 close that day, is a candidate with a band of ₹485–₹510. The home
page saves watchlist stocks with no sector; HEROMOTOCO added there is a
candidate under its managed `automobile`, so with MARUTI and M&M already at
28% of total equity it is capped at 30%.

**SWITCH.** The top 5 buy candidates by conviction are judged. One
qualifies when it is not already held, its sector's share of total equity is
strictly below the exiting holding's sector's share, and its conviction beats the
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
within 3 trading days. `POSITION_LARGE` marks a holding over
`advisor.max_position_pct` (10%) of total equity, and
`SECTOR_CONCENTRATION_HIGH` a sector whose holdings together are over
`advisor.max_sector_pct` (30%). At a cap is allowed, so exactly 10% carries no
note. `DATA_GATE` and `IDENTITY` are section 4.

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
from an earlier bar. A watchlist stock needs an actionable analysis in either
mode: without one it is not a candidate at all.

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
| ADD | Buy into an existing holding only, asking for 25% of the position's value, sized by the shared rule below. Skipped within 5 trading days of the last autopilot buy of that symbol, or when the rule allows under one share (logged). |
| SWITCH | Sell the whole position (EXIT rules), then buy the destination, asking for the sale proceeds net of the sale's charges, sized by the shared rule below, and only inside its shelf idea's entry band. |

**The SWITCH buy leg re-checks its own inputs** before spending:

- the destination's close must come from the session's own bar;
- the destination's identity must be resolved; and
- its price must be at or below the idea's `entry_high` and above its
  `invalidation_level`. Below `entry_low` it is allowed (cheaper than
  planned) and the BUY's note says so. A destination with no active shelf
  idea, or no band, is not bought.

For the first two, `enforce` mode skips the buy, and `record` mode buys and
logs that the gate would have skipped it. The band applies in every mode. An
unpriceable destination, or a size under one share, also skips the buy.
Whenever the sell executes and the buy does not, the SELL's note records why,
for example `exit_full; buy leg skipped: WELCORP: 33.6% above entry band
(₹1,817–₹1,911); needs a fresh deep dive; ₹1,00,000 stays in cash`. The
`switch_buy_skipped` alert repeats that reason (when another switch that day
bought the same stock, only the SELL's note says why). A completed buy promotes the
destination into the managed list (section 12).

**Order.** Sells first (EXIT, SWITCH sell legs and TRIM, by symbol), so cash
is freed before it is spent. Then buys: SWITCH buy legs, then ADDs by
confidence (highest first, ties by symbol).

**The shared sizing rule** ([sizing.py](../core/portfolio/sizing.py)). Total
equity E is every holding at the run's close (at cost without one) plus cash.
A buy paid from cash moves money into a holding, so E does not change but for
the buy's charges (section 9). A buy of X is the smallest of:

- the amount asked for (the ADD tranche, or the SWITCH proceeds);
- `0.10 × E − pos`, the position's room (`advisor.max_position_pct`);
- `0.30 × E − sector`, its sector's room (`advisor.max_sector_pct`);
- `cash − 10,000`, the cash above the floor.

Whole shares only, and each limit must still hold after the buy's charges
leave cash and equity: a share at a time is dropped until it does. When a cap
or the floor is the limit, the BUY's note names
it and the amount left in cash, for example `add_tranche; capped by the 10%
position cap: ₹1,250 of the ₹2,250 tranche stay in cash`. When nothing but
the request limits it, the note is plain (`add_tranche`, `switch from X`).

**Example:** a ₹20,000 position in a sector holding ₹50,000, total equity
₹5,60,000 (holdings ₹5,00,000, cash ₹60,000). The tranche is ₹5,000. The
position's room is 0.10 × 5,60,000 − 20,000 = ₹36,000, the sector's is
0.30 × 5,60,000 − 50,000 = ₹1,18,000, and cash above the floor is ₹50,000.
The budget is ₹5,000, which at ₹1,180 a share buys 4 shares.

## 7. Cash deployment

How cash moves today:

- **A new position opens only through a SWITCH**, which puts one sale's
  proceeds into a buy candidate (section 3: a fresh shelf idea or the user's
  own watchlist BUY), inside its entry band.
- **ADD tops up a stock already held.**
- **Every buy is sized by the shared rule** (section 6): each position at
  most 10% and each sector at most 30% of total equity after the trade, and
  the ₹10,000 floor kept.
- **A plain EXIT leaves its proceeds in cash**, as does whatever a cap or a
  skipped buy leg leaves. Nothing reinvests them.
- **The seed** spreads the starting pot equally across the enabled managed
  tickers (section 11).

**Example:** a ₹10,00,000 portfolio switches a ₹2,27,000 holding into a
shelf idea at ₹530. The sale pays ₹250.84 of costs, leaving ₹2,26,749 of
proceeds. The new position may be at most 10% of the ₹9,99,749 equity: 188
shares, ₹99,640, plus ₹118.68 of costs. The other ₹1,27,109 stays in cash,
and the BUY's note says so.
On a day with no qualifying candidate, two EXITs of ₹1,50,000 each raise
cash by ₹3,00,000, and it stays there.

**Planned:** in a normal market, idle cash goes into shelf ideas that pass
the checks, sized by the same rule; cash is held on purpose only in a crisis
(SA-049, behind a switch that ships off).

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
| `capital_in` | Mock money ever put in: the seed pot plus manual adds and CSV imports at their cost and their buy charges. The screen calls it "Capital added". |
| `cash_deployable` | Cash available now |
| Total equity | Market value of holdings plus cash |
| Total return | `(total equity − capital_in) / capital_in` |

**Trading costs** ([costs.py](../core/portfolio/costs.py)). Every BUY and SELL
pays what an NSE equity delivery trade pays at a zero-brokerage broker. The
rates are in `config.yaml` under `portfolio.costs`, with the date they were
checked:

- STT, 0.1% of each side, to the rupee;
- stamp duty, 0.015% of the buy;
- the NSE transaction charge (0.00307%) and the SEBI fee (0.0001%) on each side;
- 18% GST on the brokerage, NSE and SEBI charges;
- a ₹15.34 DP charge per scrip sold.

The charges are written on the trade's own ledger row (`costs`) and leave cash
with it, so the txn_id dedupe that stops a re-run trading twice also stops it
charging twice, and a later rate change never alters a past trade. A manual
add or CSV import moves no cash, so its buy charges go into `capital_in` with
its cost. A row written before costs were charged is estimated when read, at
the configured rates, and labelled `estimated`; those costs were never taken
from cash. `realized_pnl` stays the price difference, before costs.

**The tax estimate** (`portfolio.tax`) is shown and never taken from cash. Per
financial year (April to March), each sale's gain is short-term if its shares
(oldest first) were held 12 months or less (20%), long-term otherwise (12.5%
above ₹1,25,000 a year), plus a 4% cess. A short-term loss offsets short-term
gains, then long-term gains; a long-term loss offsets long-term gains only.
STT is not deductible; the other charges are. The shares' cost is the
position's average, not each lot's own cost as the law takes it, so a sale
that mixes long-term and short-term shares bought at different prices can read
high or low (**Planned:** FIX-022). Surcharge, the basic-exemption shortfall
and losses carried to later years are not modelled.

**Example (ACMESOLAR):** 509 shares bought at ₹372.88 and sold at ₹446.65 pay
₹225.57 and ₹250.85. The realized +₹37,548.93 is +₹37,072.51 net of costs,
and the short-term tax estimate is ₹7,797.82: about ₹29,275 in hand.

The KT's [section 7](TECHNICAL_DESIGN.md#virtual-pl) gives the report families
and the Nifty comparison: the same deposits in the Nifty 50, on the portfolio
screen and in the weekly scorecard.

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
| `realized_pnl`, `cost_basis`, `pnl_pct` | SELL only, before costs; the cost basis is `adj_avg_price` at the sale |
| `costs` | BUY and SELL: each charge, `total`, the `rates_as_of` it was charged with and `estimated` (false). Absent on a row written before costs were charged, and on a `DIV` |
| `source` | `autopilot`, `seed` or `manual` |
| `verdict`, `advice_ref`, `triggers`, `note`, `reason` | The advice behind an autopilot row; `advice_ref` joins the advice ledger, and `reason` is the narrative at execution |

`value_history.jsonl`, one point per trading day. A point dated on or before
the last one is skipped, so re-runs and stale replays add nothing. The
pipeline writes it under the user's lock, and `recorded_at` says when: a
manual add recorded before that moment is in the point, one after it is not
(the Nifty comparison values an add at the close of the first point that
holds it; [KT section 7](TECHNICAL_DESIGN.md#7-profitloss-and-the-different-marksheets)).
Nightly retention keeps the last 400 points, the first point and every older
point where `capital_in` changed, so each deposit keeps its date:

```json
{"date": "2026-10-09", "market_value": 742310.5, "cash": 263011.4, "total_equity": 1005321.9,
 "capital_in": 1000000.0, "day_change_pct": 0.21, "change_span_days": 1,
 "recorded_at": "2026-10-09T11:21:07.512301+00:00"}
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
| `POST /portfolio/holdings` | Manual BUY at the buy date's close. It is fresh capital: `capital_in` rises by its cost and its buy charges, cash does not change, and a `manual` row is written with the charges. An identical same-day resubmit is deduped. The symbol is promoted as held. |
| `DELETE /portfolio/holdings/{symbol}` | Manual SELL at today's close (cost if no close), cash credited net of the sale's charges, `manual` row written with its `cost_basis`, `pnl_pct` and charges, so the weekly scorecard counts its result. Unless the symbol is on the watchlist, its portfolio-origin managed entry is disabled |
| `POST`, `DELETE /portfolio/watchlist…` | Watchlist changes; an added symbol is promoted as watchlist, a removed one demoted the same way |
| `POST /portfolio/import-csv` | Bulk import of holdings. Rows are priced first, then added in one locked section; with cash accounting on, each is fresh capital like a manual add: `capital_in` rises by its cost and its buy charges, and a `manual` BUY row is written with the charges and no cash moved |
| `GET /portfolio/transactions?limit=N` | The ledger, newest first. A trade written before costs were charged shows them estimated (`estimated: true`); a `DIV` shows none |
| `GET /portfolio/performance` | Cash, `capital_in`, market value, equity, the in-stocks and cash shares of equity (adding to 100), realised P/L before costs (`realized_pnl`) and split as `realized` (`gross`, `costs`, `net_of_costs`, `estimated_costs`), `costs` (`charged` from cash, `estimated` for old trades, `on_open_positions`, `rates_as_of`), `tax_estimate` (per financial year), unrealised P/L (the open holdings' price gain), total return, day change, the autopilot flag, the last 400 value points each with `nifty_value`, `vs_nifty` (the gap since the first deposit), `ranges` (each chart range's money-weighted return beside the Nifty's) and `closed_trades`. It reads every transaction and value point |
| `GET /portfolio/advice`, `GET /portfolio/digest/latest` | The advice ledger's tail; the latest digest |
| `GET /portfolio/scorecard?limit=N` | The caller's own weekly results rows, newest week first, as the Sunday weekly review stored them ([KT section 7](TECHNICAL_DESIGN.md#weekly-results-scorecard)) |
| `POST /portfolio/run-advisor` | Owner only: run the pipeline in the background |

**Screen** ([portfolio.jsx](../src/frontend/prototypes/portfolio.jsx),
in-browser JSX, no build step). With live data and cash accounting on, it
shows total equity with an AUTOPILOT pill, its valuation date, the day's
change, a stats row (Capital added, In stocks and Cash with their shares,
Total return, Realized P&L), what the same deposits would be worth in the
Nifty 50, the equity curve from two points on with the Nifty line dashed,
the closed-trade record and recent trades. Every share price carries its
date. When the portfolio API does not answer, the
screen says the portfolio is unavailable; only `?demo=1` shows sample data,
under a "Sample data" banner.

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
| `advisor.max_position_pct` | 10.0 | ADD eligibility, the `POSITION_LARGE` note and every buy's post-trade position cap, of total equity |
| `advisor.max_sector_pct` | 30.0 | The `SECTOR_CONCENTRATION_HIGH` note, the weekly flag and every buy's post-trade sector cap, of total equity |
| `advisor.atr_period`, `advisor.stop_atr_mult`, `advisor.stop_buckets` | 20, 3.0, large [8, 12] · mid [12, 18] · small [15, 22] | Stops |
| `advisor.trim_profit_pct`, `advisor.trail_arm_pct` | 25.0, 10.0 | TRIM threshold; trailing-stop arming |
| `advisor.confidence_decline_threshold`, `advisor.reversion_prior_elevated` | 0.05, 0.20 | TRIM triggers |
| `advisor.envelope_flat_band_pct`, `advisor.add_min_direction_accuracy` | 1.0, 0.60 | Envelope direction; ADD accuracy floor |
| `advisor.switch_conviction_gap`, `advisor.switch_eval_max_candidates` | 0.15, 5 | SWITCH |
| `advisor.ltcg_wait_min_months`, `advisor.earnings_gap_days` | 10, 3 | Notes |
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
| `test_sizing_rule_sa050.py` | The shared sizing and entry rule: hand-worked caps, floor and band cases, the 11 Oct weights, a random-portfolio property test and a switch through the pipeline |
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

- Idle cash deployed in normal markets (SA-049).
- The tax estimate at each lot's own cost (FIX-022).
- A safe `identity_reconcile apply` (SA-008 change 1).
- Learning from executed advice remains future work: every autopilot row
  carries `advice_ref`, which joins its outcome to the advice that caused it,
  and the nightly auditor already grades issued advice (KT section 7).

# SA-051 — implementation receipt

**Story:** [SA-051](../stories/SA-051.md): show the portfolio against the Nifty, with honest
labels; and PR-002's review follow-ups F1 (an added holding enters at its cost) and F2
(retention moves "since the start").
**Phase:** implementation, 19 Oct 2026, about 12:15–13:30 IST. Session
stockagent-main-da, a new conversation opened with "continue"; all 19 peers were idle.
**Baseline:** `bb9969e5b5a9902a5d5e920b3f741a9dffbd1755` (HEAD, clean for every payload
path). **Status after this phase:** `review_required`. Nothing was committed, pushed or
deployed. No production state was read, and no message was sent.

The PR-003-P1 Yahoo probe was not run: this conversation started at 12:11 IST, after its
07:00–12:00 window. It moves to Tuesday 20 Oct's first conversation inside the window.

## In one example

**The card's two deposits.** ₹10,00,000 arrives on Mon 5 Jan with the Nifty at 100 and
buys 10,000 units; ₹2,00,000 more on Mon 19 Jan at 125 buys 1,600. On Fri 6 Feb the Nifty
is 110 and the portfolio ₹12,40,000, with ₹2,30,400 in one stock.

- **Before.** The screen said "Invested ₹12,00,000" and "Total return +₹40,000 (+3.3%)",
  with nothing to compare. "Value over 1M" read the ₹2,00,000 deposit as a 24% gain.
- **Now.** "Capital added ₹12,00,000 · In stocks ₹2,30,400 (18.6%) · Cash ₹10,09,600
  (81.4%)", "Valued as of 6 Feb 2026", and:

```text
If this had been in the Nifty 50: ₹12,76,000. The portfolio: ₹12,40,000, ₹36,000 behind (3.0 points).
Since 5 Jan 2026: the portfolio +3.3%, the Nifty 50 +6.3%, for the same deposits on the same days. Cash counts.
```

  The chart draws the same money in the Nifty as a dashed line: ₹10,00,000, ₹14,50,000
  (11,600 × 125), ₹12,76,000 (11,600 × 110). "Return over 1M" reads "+3.3% · Nifty 50
  +6.3%": the deposit is money in, not a gain.

**The backdated add (F1, the card's acceptance).** ₹10 L sits in cash while the Nifty goes
100 → 110 over four weeks. On Fri 20 Feb, with the Nifty at 105, the owner adds 1,000
shares with a buy date a year back; the route prices them at that day's ₹50, and they are
worth ₹150. `capital_in` rises by ₹50,000.

- **Before:** the comparison took ₹50,000 in, so the four weeks read +9.5% against +9.8%
  and "Behind the Nifty" stayed clear.
- **Now:** the add is in the 20 Feb valuation (17:00; it was added at 11:00), so it is
  ₹1,50,000 in at Nifty 105. The four weeks read **0.0% against +9.3%**, and the flag
  fires. Added at 19:00 instead, after the review, it arrives in the 27 Feb valuation at
  Nifty 107: 0.0% against +9.1%.

## What changed

- **`core/portfolio/results.py`** (PR-002's module; one implementation for the screen
  and the scorecard):
  - `in_kind_arrivals`: the ledger's "manual" BUY rows whose cash did not move, the
    signature of Add holding and (now) a CSV import, with the IST day of the row's `ts`.
  - `capital_flows`: each change in `capital_in` between value points, dated at the first
    point that shows it, with every arrival in it valued at the stock's close on that
    point's date instead of its cost. A `Flow` whose arrival has no close that day, or
    whose point cannot be told (below), has `amount=None` and a note in words.
  - `_arrival_point`: the first point whose `recorded_at` is after the arrival's `ts`.
    A point written before SA-051 (no `recorded_at`) holds an arrival from an earlier
    day; one dated the arrival's own day is ambiguous.
  - `vs_nifty(…, flows=)`: an unknown flow inside the period, or before it with money
    moving in it, makes the period unavailable with that note. Before a period with no
    flow, the Nifty side's units are constant whatever they are, so its return is the
    index's own move (`nifty_value` is then `None`).
  - `nifty_line`: the same deposits in the Nifty under each value point; `None` before
    the first deposit, on a day with no close, and from an unknown flow on.
  - `portfolio_vs_nifty`: the line, the since-start comparison with `first_deposit` and
    `gap_inr`, and each range's money-weighted window (a range of n points runs from the
    n-th last point to the last, as the chart slices it).
  - `build_row` and `weekly_scorecard` take `stock_close_on` and use `capital_flows` for
    all three Nifty windows (F1 for the scorecard too). `stock_close_fn` is the
    portfolio's own `pricing.close_on`, kept for the process only for past days.
- **`core/audit/benchmark.py`:** `BenchmarkSeries.preload(start, end)` answers a whole
  range from one download, choosing for each day exactly the bar the per-date lookup
  would (`_session_for` walkback, then `_pick`: the session's own bar, else the latest
  in the 7 days before it, never a later one). `_fetch_index_close` now uses the same
  `_pick`. Inside a loaded range `close_on` never fetches. A loaded range is shared for an
  hour, but only once its last session has its own bar.
- **`services/api/routes/portfolio_api.py`:**
  - `GET /portfolio`: each holding's `last_close_date`, the date of the bar its price
    came from (`pricing.session_close`, the same fetch as `close_on`).
  - `GET /portfolio/performance`: reads every transaction and value point (was 2,000 and
    400); sends the last 400 points, each with `nifty_value`; adds `in_stocks_pct` and
    `cash_pct` (cash rounded, stocks 100 minus it), `vs_nifty`, `ranges`,
    `range_points`, `benchmark` and `closed_trades` (`trade_stats(closed_trades(…))`).
    The comparison and record need cash accounting. Seams `_benchmark` and
    `_stock_closes` let tests answer without the network.
- **`core/portfolio/retention.py`:** the nightly trim keeps the last `cap` points, the
  first point with a `capital_in` and every older point whose `capital_in` changed (F2).
  A file is rewritten only when a line is dropped.
- **`core/portfolio/autopilot.py`:** each value point records `recorded_at`.
- **`core/portfolio/pipeline.py`:** the value point is written under the user's lock, the
  lock every add holds from its ledger row to its save.
- **`core/portfolio/store.py` (`import_csv`):** prices every row first (network, outside
  the lock), then adds the holdings, their ledger rows and the capital in one locked
  section. With cash accounting on each row writes a "manual" BUY with no cash moved,
  like Add holding. Before, an import wrote no row, so `reconcile` reported each imported
  quantity as drift.
- **`src/frontend/prototypes/portfolio.jsx`:** "Capital added", "In stocks" and "Cash"
  with shares; "Valued as of"; the comparison sentence; the dashed Nifty line
  (`ValueChart`, drawn only through points with a value); each range's return beside the
  Nifty's; a closed-trade card; dates under the current price ("on 6 Feb 2026") and the
  average cost ("first bought …"), on each trade's price, and on the agents' card ("From
  the review of …"). A sale's cost basis reads "average cost". The allocation card is
  labelled "share of the holdings". Without cash accounting the hero says "Bought for".

## Design decisions (delegated, recorded)

- **D1. An arrival is valued at its close on the date of the first valuation that holds
  it.** Not at the moment of the add, and not on the buy date. That valuation marks the
  holding at the same session's close, so the arrival is neutral on the day it lands;
  every later move is the portfolio's. It is also the date the Nifty side buys its units,
  as for a cash deposit.
- **D2. Which valuation holds an add is read from `recorded_at`, under the lock.** A
  guess from the rise in `capital_in` was rejected: on the day the autopilot is seeded,
  an add after the seed's point would be read as part of the opening deposit. A legacy
  point dated the add's own day is reported, not guessed (L1).
- **D3. The unknown-flow rule** (in `vs_nifty`) keeps the 4-week flag working when an old
  unknown flow exists, unless money moved inside the 4 weeks.
- **D4. F2 through retention,** not SA-049's `DEPOSIT` rows (not built yet). It also keeps
  every arrival's point, since an arrival raises `capital_in`.
- **D5. "Capital added" stays `capital_in` at cost, and "Total return" is unchanged.**
  The card renames the label; the Nifty comparison is the honest "is this good?" answer.
  The difference is documented (KT section 7, L3).
- **D6. The gap is shown in rupees and in points of return since the first deposit,**
  from the same `vs_nifty` as the scorecard's since-start line, so the screen and the
  email agree.
- **D7. The range label is money-weighted** ("Return over 1M"); the old "Value over 1M"
  read a deposit as a gain. The server computes every figure; the screen formats.
- **D8. Shares:** cash is rounded to one decimal and stocks is 100 minus it. Rounded
  apart, ₹5 in stocks and ₹9,995 cash read 0.1% + 100.0%.
- **D9. Without cash accounting** no deposit or sale is recorded, so there is no
  comparison or trade card, and the hero says "Bought for" (the holdings' cost).
- **D10. The allocation card keeps shares of the holdings,** relabelled. Adding cash there
  would mix today's prices with the valuation's cash and disagree with the hero.

## Invariant tests

**`tests/unit/test_portfolio_vs_nifty_sa051.py`: 295 tests:** 26 named tests, three
seeded properties (40, 200 and 25 cases) and 4 rounding edges. Every expected figure is
worked out by hand in its docstring.

| Area | What is pinned |
|---|---|
| AC1 | the two deposits through `/portfolio/performance`: the line 10,00,000 / 14,50,000 / 12,76,000, +3.33% vs +6.33%, −3.0 points, −₹36,000, one Nifty download for every date |
| Ranges | a deposit inside a range is money in (+3.33%, not +24%); a quiet range is the index's move |
| Cash drag | ₹10 L idle, Nifty +10%: 0.0% against +10.0%, ₹1,00,000 behind |
| Missing data | an unavailable benchmark: no line value, every range unavailable; a missing deposit-day close ends the line, never carries units on |
| F1 | the card's acceptance through the real add route and value-point writer with a frozen clock: before the review (0.0% vs +9.32%, flag fires), after it (+9.06% at Nifty 107), no close (could not check, week still compared by the index's move), legacy same-day point (could not check), an add not yet valued (no flow), which rows are arrivals, the IST day |
| Unknown flows | before a quiet period: index move; before a busy one: unavailable |
| F2 | PR-002's probe C through the real prune (+32% vs +32%, not +32% vs +10%); 40 random histories: the flows and the since-start comparison are identical before and after any cap |
| Record | the card's 6 × +3% and 4 × −10%: 60%, +3.0, −10.0, −2.2, "before costs"; an open position and a partial TRIM are not trades |
| Labels | 19.0% / 81.0% of ₹10 L; 200 random pairs and 4 rounding edges add to 100.0; no comparison or record without cash accounting |
| Dates | `last_close_date` is the bar's date, not the date asked |
| Writers | `recorded_at`; the pipeline's lock around the value point; a CSV import writes the rows, raises capital and reconciles clean; none without cash accounting |
| Benchmark | 25 random bar sets with a holiday and missing days: the preloaded close equals the per-date close for every calendar day, never a later bar; a failed preload never falls back to per-date fetches; a lagging last bar is asked again |
| Stock close | only a past day's close is kept |

**Updated existing tests:** `test_portfolio_api.py` fakes `session_close` (GET /portfolio
now reads the bar date) and asserts the date; `test_autopilot_api.py` answers the Nifty
with a flat fake (the route now compares).

**Browser** (`tests/frontend/no_invented_figures.test.mjs`, 4 new): the labels and shares,
the comparison sentence and range figure, the dashed line and the closed-trade card;
every share price on the screen dated; an unavailable Nifty (no line, no gap, no figure);
a missing value breaks the line into two segments, never bridged. Against HEAD's
`portfolio.jsx` (blob `298af6b3…`, copied to `analysis_data/sa051/fe_base`) all **4 fail**.

**Mutants.** Code: `analysis_data/sa051/sa051_mutants.py`, 26 one-line reversions run
against the story file, the PR-002 tests, the portfolio API tests and the benchmark tests:
**26 of 26 caught** (M19, shares rounded apart, survived the first run; it is caught by
the rounding-edge test added for it), every file restored byte for byte. Screen:
`analysis_data/sa051/fe_mutants.py`, 8 reversions in copies of the prototypes: **8 of 8
caught**, each by a real assertion (4 tests ran, 1–2 failed).

| Area | Code mutants |
|---|---|
| F1 | arrival at cost; `recorded_at` ignored; legacy same-day guessed; unvalued flow at cost; unknown before a busy period ignored; non-manual or cash-paying buys as arrivals; UTC day; scorecard ignores arrivals; no `recorded_at`; value point outside the lock |
| F2 | tail only; opening point dropped |
| Comparison | units carried past a missing close; ranges read a deposit as a gain; only the invested part compared; deposits from the chart's 400 points only |
| Benchmark | no look-back at the range start; a later close for a missing session; per-date fallback after a failed preload; one fetch per date |
| Screen data | shares rounded apart; missing Nifty sent as 0; price date dropped; a TRIM closes a trade; CSV import writes no rows |

| Screen mutants |
|---|
| the line bridges a gap; the current price undated; the comparison drawn when unavailable; shares hidden; "Invested" back; a missing value drawn at 0; a trade price undated; the range shows the old equity change |

## Commands and environment

Windows 11, the repository's `.stockai` venv (Python 3.13), Node with the vendored
Playwright Chromium. Hermetic boundary on (SA-005): no `.env`, no network, no checkout
data.

| Command (repository root) | Result |
|---|---|
| the affected existing files after the code change, before any test update | 2 failed as expected: GET /portfolio reached `session_close` (network), and the performance route reached the Nifty download (the hermetic boundary stopped it) |
| `.stockai/Scripts/python.exe -m pytest -q -p no:cacheprovider tests/unit/test_portfolio_vs_nifty_sa051.py` | **295 passed** |
| the story file with `test_weekly_scorecard_pr002.py`, `tests/unit/audit/`, `test_atlas_retention.py`, `test_portfolio_api.py`, `test_autopilot_*.py`, `test_portfolio_*.py`, `test_seed_autopilot.py`, `test_broad_except_guard.py`, `tests/unit/pipeline` | **1,044 passed** |
| `PYTHONPATH="src;." .stockai/Scripts/python.exe analysis_data/sa051/sa051_mutants.py` (then `… M19`) | **26 of 26 caught** |
| `.stockai/Scripts/python.exe analysis_data/sa051/fe_mutants.py` | **8 of 8 caught** |
| the 4 new browser tests with `SA_FRONTEND_ROOT` = the prototypes with HEAD's `portfolio.jsx` | **4 failed**, as intended |
| `npm run test:frontend` | **39/39** (was 35) |
| `.stockai/Scripts/python.exe -u -m pytest -q -p no:cacheprovider -o console_output_style=count tests` | **5,331 passed, 12 skipped, 1 xfailed (the known PR-003 limit), 1 failed** in 15 min 5 s. The failure was PR-001's guard (`test_ui_no_invented_figures_pr001.py`): a code comment in `portfolio.jsx` gave a percentage as its example. The comment was reworded; then that file **44 passed** and the 4 portfolio browser tests passed again. Only that comment changed after the full run |
| `python scripts/ci/check_broad_except.py` | first run: 2 new silent handlers in `nifty_line`; they now log at debug. Then **OK (151 grandfathered)** |
| `PYTHONPATH=analysis_data/kt_docs_deps python scripts/docs/build_kt_pdf.py`, then `check_kt_docs.py` | PDF source `7a430a02…`, 440,606 bytes; errors `[]` |

Raw outputs (ignored): `analysis_data/sa051/full_suite.txt`, `mutants.log`,
`mutants_m19_rerun.log`, `fe_mutants.log`, `npm_frontend.txt`, `fe_base/`, `fe_mut/`, and
the helper scripts (`splice_start.py`, `edit_portfolio_api_test.py`,
`edit_autopilot_api_test.py`, `doc_edits_codebase.py`, `digest.py`).

## Documentation

Each change is written as current design.

- **KT** (`docs/TECHNICAL_DESIGN.md`):
  - section 7, "Virtual P/L": the "In stocks / Cash" row; the portfolio screen (labels,
    the Nifty line, the range figures, the gap, the two-deposit example, missing data,
    the one download, the closed-trade card, the dates, no cash accounting); the read
    limits; "Total return" against the comparison;
  - section 7, the scorecard's "You vs the Nifty" row, and a new block "Holdings that
    arrive without cash": the F1 example, `recorded_at` and the lock, unknown flows, the
    retention rule, and limit L2;
  - section 10, the learnings note now points to the closed-trade card;
  - section 11's "Portfolio economics" drops the SA-051 bullet; section 12's SA-051 row
    stays `Open` until the fresh review accepts it.
- **PDF** rebuilt (source `7a430a02…`); `check_kt_docs` `[]`.
- **AUTOPILOT_GUIDE:** `capital_in` ("Capital added", CSV imports), the value point's
  `recorded_at`, the lock and retention, the import and performance rows, the screen
  paragraph. Its header (edition, inspected revision) is a commit-time edit.
- **CODEBASE** (the import and performance rows) and **PRODUCT_MAP** (the results row).
- **Human testing guide** (HT-08): 08-E (the read limits and retention), 08-G rewritten as
  a concrete fixture with exact figures, new 08-H (the backdated add, before and after
  the review, and with no close). Status lines: "SA-051 (implemented 2026-10-19; fresh
  review pending)".
- No change needed: ARCHITECTURE and the root README do not describe the portfolio
  screen's figures.

## Manifest and digest

- **Review input:** [SA-051-manifest.json](SA-051-manifest.json), 18 files. The SHA-256 of
  its LF bytes is **`fb29bbda173ab0eec8f9ca5712eec5e075bb0cdb99e0aebb7ae46c83e6fe965f`**;
  `kt_manifest.py verify` gives 0 mismatches.
  - Code (8): `core/audit/benchmark.py`, `core/portfolio/autopilot.py`,
    `core/portfolio/pipeline.py`, `core/portfolio/results.py`, `core/portfolio/retention.py`,
    `core/portfolio/store.py`, `services/api/routes/portfolio_api.py`,
    `src/frontend/prototypes/portfolio.jsx`.
  - Tests (4): `tests/unit/test_portfolio_vs_nifty_sa051.py` (new),
    `tests/frontend/no_invented_figures.test.mjs`, `tests/unit/test_autopilot_api.py`,
    `tests/unit/test_portfolio_api.py`.
  - Docs (6): the KT and its PDF, AUTOPILOT_GUIDE, PRODUCT_MAP, the testing guide, CODEBASE.
  - Excluded: STATE, HANDOFF, this receipt (bookkeeping), and the owner's own line in
    `docs/README.md`.
- **Diff digest:** **`fb7c36dae63cd34860c2b1add08591990da93b69ffe0944d90c478881615ae9f`**,
  136,285 bytes over 17 paths (every manifest path except the PDF), by
  `analysis_data/sa051/digest.py`. It checks that HEAD is `bb9969e`, runs
  `git diff --no-color --no-ext-diff HEAD -- PATH` for the 16 modified paths and
  `git diff --no-index /dev/null PATH` for the new test file, then sorts by path and
  concatenates.

## Self-review

Same-conversation self-review; it does not replace the fresh review.

- **Found and fixed:**
  - **Rounding apart can show 100.1%.** The random property test missed it (M19
    survived); a search found ₹5 / ₹9,995 → 0.1% + 100.0%. The four edges are now
    tests.
  - **A stale Nifty close cached for an hour.** If Yahoo has not published the latest
    session's bar, that day stands on the close before it. Cached, the screen would have
    compared today's portfolio with yesterday's Nifty for an hour (flattering on an up
    day). Such a range is no longer cached.
  - **Today's stock close kept for the process.** Only past days are kept now.
  - **The ambiguous rule marked two points;** marking the second was redundant (any
    period holding it also holds or follows the first with money moving). Simplified.
  - **The screen-mutant runner first reported 8 false catches:** through `cmd.exe` the
    test pattern's `|` was a pipe, so node never ran. Run without a shell and counted only
    real assertion failures.
  - **The allocation card** first gained a cash slice at today's prices; it disagreed
    with the hero's valuation, so it was relabelled instead (D10).
  - **PR-001's guard** (no sample figure in a customer-facing file) failed the full run on a
    code comment that gave a percentage as its example; reworded.
- **Flattery checks (the card's hard-review question):** deposit dates are the points
  that first show them (F2 keeps them); the walkback takes the previous session, never a
  later one (tested over 25 bar sets); idle cash counts (tested); only the money-weighted
  comparison is shown, never the invested part alone (mutant M10); a backdated add's
  earlier gain is excluded (F1).
- **Issue time:** a late scorecard rebuild filters points and rows by the week's end; an
  add after the week (even with an earlier buy date) is held by no point in the week, so
  it moves nothing (test). Arrival closes are past sessions.
- **Compatibility:** stored value points without `recorded_at` still work (L1 only for
  same-day adds); old screens ignore the new fields; `build_row`, `vs_nifty` and
  `weekly_scorecard` keep their signatures with new optional arguments.

## Limits and follow-ups

- **L1. A legacy point dated an add's own day is not guessed.** The windows that touch it
  read "could not check", and "since the start" stays so. **Production has none** (read-only
  probe below): no account has an add that arrived without cash.
- **L2. An add during the 16:30 run** has no close in that run: the valuation holds it at
  cost while the comparison values it at the day's close, so that day reads a small loss
  that the next valuation reverses. **The fresh review found it larger:** the error is
  quantity × (close − cost), either way, and a weekly row ending on that day keeps it
  ([review](SA-051-review.md), R1).
- **L3. "Total return" still counts a backdated add's earlier gain** (equity minus capital
  added at cost). The comparison does not.
- **L4. Accounts without cash accounting get no comparison;** they record no deposits.
- **L5. A CSV import made before this change has no ledger row,** so it is still counted
  at cost and still shows as `reconcile` drift (the probe's last count).
- **L6. The current price's date can be today during market hours:** the bar of a session
  still trading.

## Production evidence (read-only, 19 Oct 2026)

At the owner's request ("i did railway ssh now, can you try now"), at about 13:40 IST this
session ran `analysis_data/sa051/arrivals_probe.py` once through `railway ssh` (the pipe in
its docstring) against the deployed `bb9969e`. It opens files read-only and prints counts
and dates only. Nothing was written or sent. The sanitized output:

```text
account 1: points 67 (first 2026-07-11, with recorded_at 0); capital rises after the first point 0; arrivals 0 (backdated 0; on a review day 0: -); holdings the ledger does not net 0
accounts with cash accounting: 1
```

What it shows, for the one account with cash accounting (the owner's autopilot account):

- **No holding ever arrived without cash.** There was no manual add and no CSV import, so
  F1 changes no past figure and L1 and L5 do not apply in production.
- **`capital_in` never rose after the opening deposit.** The only flow is the seed, dated
  11 Jul.
- **67 value points, none with `recorded_at`.** That is expected before the deploy. F2's
  retention rule matters only after 400 points (around 2027) and would keep that one point.
- **The ledger nets every holding.**

## Rollout (at the owner's word)

- **Commit and push only on the owner's word,** in a job-free window: not 08:30–09:20 or
  16:25–17:15 IST. No migration and no new setting.
- **After the deploy:** value points carry `recorded_at` from the first 16:30 run. Open the
  portfolio screen: the hero labels, the comparison and the trade card should show; the
  first page load downloads the Nifty once (about a second). Run guide 08-G and 08-H in a
  test copy, and the probe in production.
- **Rollback:** revert the commit. Points written meanwhile keep a harmless extra field.

## Commit-time edits (after acceptance)

- KT: header (code inspected, edition), section 12's SA-051 row `Done`, PDF rebuild,
  `check_kt_docs`.
- AUTOPILOT_GUIDE header: edition and inspected revision.
- The testing guide's two SA-051 status lines (08-G, 08-H).

## Next

`next_task: SA-051`, its **fresh review** in a new conversation ("continue"), then
PR-004. The PR-003-P1 Yahoo probe: Tuesday 20 Oct, the first conversation between 07:00
and 12:00 IST.

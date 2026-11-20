# PR-016 — implementation receipt

**Story:** [PR-016](../stories/PR-016.md): show what the book earns at prices that could really
be had. Owner decision of 15 Nov 2026 (edge roadmap, stage 2). Profit-path step: **measure**
(the record the owner shows is judged at a price nobody could trade at; this measures the gap
before anything is changed).

**Lane: decision path.** Reason: the card's own lane; it sets the price the record is judged at
(AGENTS.md step 4). It changes no trade, no booked price and no decision.
**Status after this phase: `review_required`.** The next fresh conversation performs the hard
review from `REVIEW.md`; this phase's self-review does not count as it.

## Phase

- **Implementation** (autopilot `1120-1355-p4`, code-server, Fri 20 Nov 2026 from about 13:55
  IST, outside a push window). Baseline **`ac97ce3`** (`main`, 7 commits ahead of
  `origin/main` `03debc1`, push pending). The code is on **`story/PR-016`**: **`31d178e`** (one
  commit). Only a fresh review's acceptance merges it into `main`.
- Production: nothing read, pushed, deployed, run or sent.

## What was built [code]

**Where the gap comes from** (the card's "Why", confirmed): the 16:30 job on day T reviews
`trading_days_ago(today, 1)`; `autopilot.execute_advice` books at `session_close(symbol,
review_date)` and dates the row `rec.date`, the reviewed session. The row's `ts` is the run's
UTC time.

1. **Two real prices per autopilot trade** (`core/portfolio/executable.py`, `price_trade`). For
   each `source == "autopilot"` BUY or SELL with a positive quantity and price (seed, manual,
   DIV and DEPOSIT rows get none):
   - `open_next`: the open of `next_trading_day(row date)`;
   - `open_as_run`: the open of the first session the run could still act at
     (`first_session_after_run`: the run's IST day if it is a trading day and the run was before
     09:00, the pre-open auction; else the next session), and never before `open_next`'s.
   The opens come from the EOD panel's own day file (`EodStore.load_day`, new: `load_window`
   would fall back to an earlier day), the equity series first (`EQ, BE, BZ, SM, ST`, as
   `bhavcopy.fetch_listing`), under `symbol_resolver.nse_symbol(symbol, day)` (`panel_fn`).
   **Price basis:** `exit_shadow.horizon_in_basis` with the open as a raw NSE quote, NSE's list
   from `corp_actions_fn` (read once per symbol per scorecard), then `registry_break`. Its
   `decided` argument (the last day the booked close's basis may have been set) is the booked
   session when the booked price is within 1% of the panel's close for that session (so it is
   that session's raw NSE close), else the run's IST day, else (no readable `ts`) `date.max`.
2. **The side file** `data/portfolio/<user>/executable_prices.jsonl`
   (`PortfolioStore.append_executable_prices_once` / `load_executable_prices`): one row per
   `txn_id`, written once both prices are settled (`priced` or `no_price`), under its own lock;
   a stored row is never rewritten. `refresh` runs in `weekly_scorecard` before the row is built
   (only when the week's row is not stored yet); a pending row is priced again next time. The
   ledger is only read.
3. **The book at each price** (`scorecard_block`, `cash_effect`): the same trades and
   quantities; each BUY pays and each SELL receives the real price; a trade whose charges were
   taken from cash pays them on the real value, both sides at the same configured rates
   (`costs.trade_costs`; an uncharged or estimated row moves by the price alone). The trades
   dated up to the last valuation move the since-start `vs_nifty` figure by their cash
   difference; the Nifty side is unchanged. A trade with no price, or still waiting, keeps its
   booked close and is counted.
4. **The line** ("At prices that could be had", after "You vs the Nifty"; `line_text`): "the
   paper book is +x% since the start at the next session's open and +z% at the open after the
   run (+y% at the booked closes). At the next open buys cost a% more on average (n) and sells
   brought b% less (n). N trades; k with no price … , each kept at its booked close." The email
   and the app render the same `lines`.
5. **The rule** (`rule_flag`), a sixth red flag `paper_prices`, constants
   `ROUND_TRIP_MAX_LOSS_POINTS = 0.5` and `MIN_CASES = 30`: fired when the mean round-trip loss
   at `open_next` is more than 0.5 points (over at least 30 round trips with every leg priced),
   or the since-start lead over the Nifty changes sign at either price (over at least 30 trades
   priced at it); the fired sentence says "Open a card to book trades at the next session's
   open". Clear only when all three tests are clear: "Paper prices are close enough: …" with the
   numbers. Otherwise "too few to judge", or "could not check" without a Nifty comparison.

A round trip is `results.closed_trades`' grouping (BUY opens or adds, the SELL that empties the
position closes it); its loss is its return on the booked prices minus its return on the real
ones, from the legs' quantities and prices.

## Decisions taken in this phase (for the reviewer)

- **The rule is a red flag**, not a sentence in the line: it is predeclared, it reports and
  changes no decision, and the scorecard already renders fired, clear, unknown and too-few
  flags (top of the email when fired). Nothing reads a fixed count of flags (checked).
- **The booked close's basis is checked against the panel's close** of its session (1%): a
  booked close equal to NSE's is that session's raw price, so a split ex the next morning is
  converted (the card's fixture). Without the check, every split on the next session would be
  "no price", since the run fetches the close after the ex-date. 1% separates any bonus or
  split (a 11:10 bonus is 9.1%) and tolerates a Yahoo close a small dividend adjusted.
- **The open after the run uses the 09:00 pre-open** as the cut, not 09:15: an order for the
  open is entered in the auction.
- **A missing day file waits 7 days**, the daily sync's re-read window (`sync_recent(days_back=7)`),
  then is "no price" for good. A file present without the stock's bar, an open not above 0, an
  empty or late-starting NSE list, a basis change no ratio converts and a registry break are
  "no price" at once; an unread NSE list or a session not yet over waits.
- **Missing prices are counted, not bounded**: the results module's rule (missing data never
  reads clear) bounds a missing grade between the two extremes; a missing price has no bound.
  So a round trip with an unpriced leg is left out of the average, a trade without a price
  keeps its booked close in the book and the lead, and the line counts both. KT section 7 says
  so.
- **The lead test needs 30 priced trades** too (EDGE-ROADMAP rule 4), so a sign change on a
  handful of trades reads "too few to judge".
- **Round-trip loss before costs** (from the legs' prices); the book includes the cost change.
- **The line reads "the paper book"** and "at the booked closes" (rule 6: paper money is called
  paper money), where the card wrote "(paper +y%)".

## Self-review (not the fresh review)

1. **Can a real price come from a bar on or before the booked close?** `price_at` refuses a
   session on or before the booked one; `open_next` is `next_trading_day(booked)`; the as-run
   session is `max(…, open_next's)`. The property test draws 480 trades over 8 seeds with runs
   at any hour from the booked day to five days on and a sentinel open on the booked day: every
   price is the panel's open of a later session, exactly.
2. **Can a corporate action show as a gap?** Only bonus and split ratios convert; anything else
   NSE lists between (a demerger, a scheme, an unreadable split row, a row of no known kind), an
   empty list or one starting after the booked session, and a registry break give no price.
3. **Is anything written but the side file?** The ledger's bytes are compared before and after
   two scorecard builds; the PR-013 test that allowed only the scorecard's own files now also
   allows `executable_prices.*` (its docstring says why).
4. **Known limits, none on the decision path:** a dividend ex between the booked close and the
   open is not added back (the open is lower by about it, the book still receives it; BACKLOG
   B-28); the panel's open is the auction's price, not what an order of the book's size would
   get; manual and seed trades are kept at their own prices.
5. **Mutants** (22 deliberate bugs in `executable.py` and the store, each run against the
   story's tests): the first run left 3 alive: a trade after the last valuation moving the
   book, the lead test without its 30-trade minimum (both now tested), and `session >= today`
   (equivalent in effect; simplified to `session > today`). All 21 remaining are caught.

## Acceptance criteria

- Invariant: a real price never comes from a bar dated on or before the booked close: the
  property test and the refusal test. **Met.**
- A split on the next session does not show as a 50% gap: ₹51 reads ₹102 (+2%); with a booked
  close that may already be halved, no price. **Met.**
- A missing bar gives "no price" on the row and a count on the line; nothing guessed. **Met.**
- Running it twice adds no row (keyed by transaction id); a waiting row is written once
  settled; a stored row is never rewritten. **Met.**
- The ledger's bytes are unchanged; the line carries its n ("3 trades"). **Met.**
- Living documents: KT section 7 (the line, how the prices are taken, the flag, the
  missing-data note, the limits paragraph) and its data table; AUTOPILOT_GUIDE sections 2, 9
  ("The booking price") and 14; TEAM_TESTING_GUIDE case 09-J; CODEBASE; ARCHITECTURE;
  PRODUCT_MAP; EDGE-ROADMAP section 7. The PDF is not regenerated (AGENTS.md). **Met.**
- Not in this card, and not done: changing the booking price or the run's time.

## Tests

`tests/unit/test_executable_prices_pr016.py`, 34 tests, figures worked by hand in their
comments: the card's example; the run's open (16:30, 08:30, 09:05, Saturday, a run on the
booked day, a retry); the property test (8 seeds); the refusal; the split converted, the
adjusted booked close, a split after the run; demerger, empty list, registry break; an unread
list waits; missing bar, missing file (3 and 8 days), a session not over; once per transaction;
seed, manual and DIV rows; the ledger's bytes through `weekly_scorecard`; the book and its line
(−₹290 and −₹520 on ₹1,00,000: +4.71% and +4.48% against +5.00%); a trade after the
valuation; charged costs at the real price; a price from after the week waiting; the rule at
0.60, 0.40 and exactly 0.50 points, 29 round trips, a sign change on 30 and on 10 trades, no
Nifty comparison; the panel seam (the day's own file, the equity series, the NSE code, a NaN
open).

## Full suite

At `31d178e`, in this checkout, Python 3.13.5, `.stockai/bin/python -m pytest -q`: **6,917 passed, 5 skipped, 1 xfailed, 0 failed** (11 min 15 s, 14:19–14:30 IST): the 6,883 of PR-013's run and the 34 new tests. A first run at `93d1e0c` was stopped before it finished, to amend that commit (an unused `EodStore.first_day` removed, a docstring rewrapped, the dividend limit stated); its result was not read.

- **The reviewed range:** `git diff ac97ce3 31d178e` (13 files, +1,253 / −19);
  `| sha256sum` = `bf0d79fb738f06140cfc36ffcec7e04ab5b8676b0ad33f0dcd66c7a2410b5aef`.
- Broad-except guard OK (138 grandfathered); `check_kt_docs.py` `errors: []`.

## For production, after the merge and a push

Proposed check `PR-016-W1` (the reviewer adds it on acceptance): after the first Sunday weekly
review once deployed, read the owner's `executable_prices.jsonl` (rows, `priced` / `no_price`
/ waiting at each price, the `no_price` reasons grouped, no symbol or amount) and the
scorecard's "At prices that could be had" line and `paper_prices` flag. Pass: one row per
settled autopilot trade, every priced session after its row's date, no reason outside the
documented ones, and the line's n equal to the autopilot trades up to that Sunday. A production
read, so the owner's word or the owner's command.

## Commands

```
.stockai/bin/python -m pytest -q tests/unit/test_executable_prices_pr016.py
.stockai/bin/python -m pytest -q tests/unit/test_weekly_scorecard_pr002.py \
    tests/unit/test_scorecard_losses_pr013.py tests/unit/test_portfolio_vs_nifty_sa051.py \
    tests/unit/test_eod_store.py tests/unit/test_delivery_weekly.py
.stockai/bin/python -m pytest -q          # at 31d178e
.stockai/bin/python scripts/ci/check_broad_except.py
.stockai/bin/python scripts/docs/check_kt_docs.py
git diff ac97ce3 31d178e | sha256sum
```

# PR-002 — implementation receipt

**Story:** [PR-002](../stories/PR-002.md), a weekly results scorecard with a "sold too early"
check. **Phase:** implementation, 16 Oct 2026, about 16:35–18:45 IST. Session
stockagent-main-a9, a new conversation opened with "continue"; all 13 peers idle at the start.
**Baseline:** `b67f972614c621343e40e74b84fbda7c49d7e403` (HEAD, clean for every payload path).
**Status after this phase:** `review_required`. During the phase nothing was committed,
pushed or deployed, no production state was read and no message was sent. Afterwards the
owner asked for a commit and push; see "Committed at the owner's word" below.

## In one example

The owner's account on a Sunday. Its money sat in cash for four weeks while the Nifty rose
10%. In that week it sold one stock, 13 sessions after buying it, at +12% on a trailing stop.
Ten earlier advisor sales have reached 30 sessions: after 4 the stock beat the Nifty, after 3
it did not, and 3 have no grade. The weekly email now opens:

```text
Weekly review — 2026-03-08
Results for 2 Mar – 6 Mar 2026 (2026-W10)
RED FLAG: Behind the Nifty: over the last 4 weeks the portfolio made +0.0% against +10.0% for the same money in the Nifty (10.0 points behind; red line 3).
COULD NOT CHECK: Selling too early: could not check. 3 of 10 sales have no 30-session grade; the share is between 40% and 70% (red line 60%).
Closed trades: This week: 1 trade · 1 won (100%) · average win +12.0% · expectancy +12.0% per trade, before costs. …
```

Before this change the same email ended with "Scoreboard: 7/9 judged calls right". That
figure compared each call's close with today's close of the stocks still held, so every stock
the portfolio had sold dropped out of it (September audit, F06).

## What changed

- **`core/portfolio/results.py` (new, pure apart from the trigger wording).** One row per ISO
  week from one user's ledgers:
  - **closed trades** as round trips from `transactions.jsonl` (`closed_trades`,
    `trade_stats`);
  - **sold too early**: every advisor sale joined to the auditor's advice-lane grade by
    `advice_ref`, at 10 and 30 sessions, since the start and over the trailing 8 weeks, with
    pending and ungraded counts (`sales`, `advice_grades`, `sold_too_early`);
  - **why we sold**: per-trigger counts in the advisor's plain words (`exit_reasons`);
  - **you vs the Nifty**: money-weighted. Deposits come from `capital_in` steps in
    `value_history.jsonl`, the Nifty equivalent from those deposits, and the comparison for
    this week, the last 4 weeks and since the start (`deposits_from_values`,
    `nifty_equivalent`, `vs_nifty`). SA-051 can reuse `nifty_equivalent` for its chart;
  - **breadth** and **holding period** (`breadth`, `holding_period`);
  - **five predeclared red flags** as module constants, each `fired` / `clear` /
    `not_enough` / `unknown` with one plain sentence;
  - the row's own sentences (`scorecard_lines`), which both the email and the app render;
  - `weekly_scorecard`: the I/O wrapper. It covers the latest finished week and stores each
    week once.
- **`core/portfolio/store.py`.** `weekly_scorecard.jsonl` with `load_scorecards`,
  `load_scorecard(week)` and `append_scorecard_once`, whose check and append share a file
  lock. A public `base_dir` lets the auditor store open the same user's folder.
- **`core/delivery/weekly.py`.** The review computes and stores the row
  (`_safe_scorecard`: a failure is logged and the text says "Results: could not be computed
  this week"). The text opens with it. The 28-day scoreboard and its constants are gone. The
  switch-call listing keeps its 4-week window. The headline prompt gets the scorecard's own
  sentences ("Use only figures given below"); the fallback headline names the fired flags.
  One Nifty series is shared by every user in a run.
- **`services/api/routes/portfolio_api.py`.** `GET /portfolio/scorecard?limit=N` (default
  12, at most 520) returns the signed-in user's stored rows, newest week first, and computes
  nothing. `DELETE /portfolio/holdings/{symbol}` now stamps the manual sale's `cost_basis`
  and `pnl_pct`, as the autopilot already does.
- **`src/frontend/prototypes/weekly-view.jsx`.** The Inbox weekly screen opens with the
  scorecard: red flags (red), then what could not be checked (amber), then the lines and the
  clear checks. The "judged calls right" block is gone. A review stored before the change
  shows no results block; one whose scorecard failed says so.
- **`scripts/seed_fixture_ui.py`.** The UI fixture's weekly now carries a scorecard built by
  the real builder from a small ledger, in place of the old scoreboard.

## Design decisions (delegated, recorded)

The owner delegates optional technical calls. Each decision below has its reason and the
trigger to revisit it.

- **D1. "Sold too early" counts executed sales, not raw auditor rows.** The population is
  every SELL row whose verdict is EXIT, SWITCH or TRIM, joined to the auditor's advice-lane
  grade by `advice_ref` (the auditor's `ref` is built from the same three fields). An account
  not on autopilot repeats its EXIT advice every day for one unexecuted call, and counting
  those rows would multiply one call. On the autopilot account every EXIT is executed the
  same evening, so the population equals the 11 Oct probe's. An advisor sale without a ref
  counts as ungraded, never dropped. Your own sales are not the advisor's: they appear under
  "Why we sold" and are not graded. *Revisit* if members get autopilot or an advisory mode
  whose calls should be graded.
- **D2. A closed trade is a round trip.** A TRIM folds into its position. The result is
  realized P/L over the cost of the shares sold, and the trade counts when the last share is
  sold. So an open position is never a closed trade, and a TRIM's +20% cannot stand for a
  position later sold at a loss. Production's eight sales since August were full exits, so
  the review's figures are reproduced exactly: +7.5% / −11.9% / −2.2%.
- **D3. The expectancy flag reads the since-start expectancy at each of the last 3 week
  ends.** A week's own figure is too sparse: at about one sale a week, a week with no closed
  trade would break the streak and silence the flag. *Revisit* after PR-009 changes the exit
  rule; the since-start figure will lag a real improvement.
- **D4. The missing-data rule.** Two flags have members that can lack a figure: a matured
  sale with no grade (selling too early), and a closed position with no purchase date
  (holding period). Each fires only if crossed with every missing member counted in the
  portfolio's favour. It is clear only if it holds with all of them counted against.
  Otherwise it says "could not check", second only to the red flags. A trade with no recorded
  cost is excluded and counted in the sentence, because a missing percentage has no bound:
  under the bounds rule, production's pre-cost-stamping July rows would leave the flag
  uncheckable for ever.
- **D5. Weeks.** Saturday and Sunday cover their own week; a weekday covers the week before.
  A week whose Saturday has not come is computed but never stored ("provisional"). A stored
  week is never rewritten, even if a later run has more data (the card: "rewrites nothing").
- **D6. Deposits are dated at the first value point that shows them.** That is the seed's own
  day, and the evening's point for a manual add or CSV import, the day the equity series
  first carries the money. A fall in `capital_in` is a withdrawal.
- **D7. Holdings are counted for the latest week only.** A rebuild of an older week shows
  "not recorded" rather than today's count under an old date.
- **D8. "Text and HTML".** The weekly email has never had an HTML body, so it stays plain
  text. The HTML is the Inbox weekly screen (the email's link), and it renders the row's
  stored sentences, so the two cannot disagree. *Revisit* if the weekly email gets an HTML
  body (as the brief has), or with PR-010's screens.
- **D9. Manual sales are stamped with their cost.** Without it, every member's own round
  trip would read "no recorded cost" for ever.
- **D10. No breadth red flag.** The card's list has five flags. The breadth line shows
  `portfolio.min_holdings` once SA-049 configures it.
- **D11. Thresholds are module constants, not configuration**, so changing one is a reviewed
  code change ("fixed now, not tuned after seeing results").
- **D12. The thesis-break share counts the advisor's sales only.** Your own sales would
  dilute it, so leaving them out can only raise the share, never flatter it.
- **D13. No valuation ever recorded** (an account without cash accounting) makes "Behind the
  Nifty" `not_enough`, not a weekly "could not check" about a lapse nobody can fix. A
  valuation history with no point in the covered week is `unknown`.
- **D14. Float hygiene at the red lines.** Shares compare in whole numbers (6 of 10 is not
  above 60%). Expectancy is the mean; the card's product form gives −8.9e−16 for an exact 0.
  Continuous comparisons ignore noise below 1e−9.

## Invariant tests

`tests/unit/test_weekly_scorecard_pr002.py` (new). Expected figures are worked out by hand in
each test's comment. The NSE calendar is pinned per test (no holidays unless one is named),
so each session count can be checked on a calendar. Against the card's acceptance criteria:

| Criterion | Tests |
|---|---|
| Fixture ledger → win rate, averages, expectancy equal hand figures; an open position is never closed | `test_closed_trades_match_the_reviews_hand_figures` (review section 11's eight sales: +7.5 / −11.9 / −2.2), `test_an_open_position_is_never_a_closed_trade` (a +20% TRIM, then −10%: one trade at +5%), `test_a_rebought_stock_is_a_new_trade`, `test_a_sale_with_no_recorded_cost_is_counted_not_guessed` |
| Property test against a direct recomputation over random ledgers | `test_trade_stats_agree_with_a_direct_recomputation` × 300 seeds: trades in closing order, each result recomputed from its own sales, counts, the card's own expectancy formula, and conservation (closed trades plus open positions' sales = every sale's realized P/L) |
| "Sold too early" by horizon; unmatured = pending; exited stock stays in the denominator | `test_sold_too_early_by_horizon_with_pending_and_ungraded` (nothing held; a +9.0 grade already in the store for a sale whose 30 sessions end after the week stays pending; a manual sale is never graded), `test_horizons_count_exchange_sessions_not_calendar_days` (a Monday holiday moves the 10th session past the week) |
| Two deposits + hand-built Nifty → hand-computed equivalent; missing benchmark = "unavailable", never flat | `test_two_deposits_buy_the_nifty_on_their_own_days` (10 + 4 units → 1,540), `test_a_deposit_inside_the_period_is_a_flow_not_a_gain`, `test_idle_cash_counts_against_the_portfolio`, `test_a_missing_nifty_close_reads_unavailable_never_flat`, `test_a_week_with_no_valuation_is_not_a_flat_week` |
| Each red flag fires when crossed, silent one unit below | `test_expectancy_flag` (−0.33 fires; 0.0 is not below 0), `test_sold_too_early_flag` (7 of 10 fires; 6 of 10 = 60% does not; 8 sales fires, 7 is too few; missing grades), `test_thesis_break_flag_and_window` (3 of 4 fires; 2 of 4 does not; your own sales do not dilute), `test_behind_the_nifty_boundary` (−3.01 fires; −3.00 does not), `test_holding_period_flag` (9 sessions fires; 10 does not), plus the not-enough cases |
| Missing data cannot silence a flag | `test_missing_grades_cannot_silence_the_sold_too_early_flag` (4 of 7 graded would read clear; with 3 ungraded it is 40–70%, "COULD NOT CHECK" at the top), `test_an_unknown_purchase_date_cannot_silence_the_holding_flag` |
| Re-running a week rewrites and appends nothing | `test_rerunning_a_week_rewrites_and_appends_nothing` (file bytes unchanged after new sales and grades, run on Sunday, Saturday and the next Wednesday), `test_an_unfinished_week_is_never_stored`, `test_concurrent_runs_store_one_row` (8 threads, 1 row), `test_covered_week` |
| A member's scorecard reads only that member's ledger (FIX-005) | `test_a_members_scorecard_reads_only_the_members_ledger` (the member's sale carries the very ref the owner's grade is keyed on, and the owner is the default user `primary`: the member's sale still has no grade), `test_the_endpoint_returns_only_the_callers_rows` (real sign-up of owner and member; a `?user_id=` naming the owner is ignored), `test_the_endpoint_needs_a_signed_in_user` |
| The weekly job end to end, transports blocked | `test_the_sunday_review_leads_with_the_scorecard` (the real `run_weekly_review`; a fixed Nifty series; delivery captured; the text's line 2 is the results header, line 3 the red flag, both above the headline; stored once; the second Sunday run sends the same lines), `test_a_failed_scorecard_is_said_not_skipped` |
| Your own sale counts | `test_a_manual_sale_records_its_cost_so_its_result_counts` (the real route) |
| Breadth floor | `test_the_breadth_floor_is_shown_only_once_configured` |

`tests/unit/test_delivery_weekly.py`: the scoreboard assertions now check that the scoreboard
is gone and the scorecard leads; the run-weekly stub accepts the new `close_on` argument.

`tests/frontend/no_invented_figures.test.mjs` (real Chromium, two new tests). The weekly
screen shows the red flag, then "Could not check", then the lines, then the headline. Every
percentage on screen is one the row sent, and the old "7/9 judged calls right" never shows,
even when a stored review still carries a `scoreboard`. A review whose scorecard failed says
so; one stored before the change shows no results block. **Both fail on HEAD's screen**
(`SA_FRONTEND_ROOT` = `git archive HEAD src/frontend/prototypes`, whose `weekly-view.jsx`
blob id equals HEAD's `04967e38`): it shows "7/9judged calls right" and no results.

**Mutants** (`analysis_data/pr002/pr002_mutants.py`, `PR002_MUT=<name>`; the runner
`run_mutants.sh` runs the story file without the 300 property seeds for speed). Each mutant
swaps in one realistic wrong implementation. All of them are caught, except one equivalent
mutant, explained below:

| Mutant | The wrong implementation | Failing tests (final bytes) |
|---|---|---|
| `exited_dropped` | Matured sales without a grade leave the denominator (F06's shape) | 6, e.g. `…by_horizon_with_pending_and_ungraded`, `…cannot_silence…` |
| `future_grade` | A grade in the store counts before its horizon ends | 2 |
| `calendar_days` | Horizons in calendar days | 2 |
| `weekdays_only` | Sessions without the holiday list | 1 (`…exchange_sessions…`) |
| `deposit_as_gain` | Only the opening deposit is a deposit | 2 |
| `lump_sum_nifty` | Every deposit buys the Nifty at the first deposit's close | 2 |
| `missing_bench_flat` | A missing Nifty close reads as a flat Nifty | 1 |
| `flat_stale_week` | A week with no valuation reads "level" | 1 |
| `skip_missing_flag` | The flag reads the graded share and ignores ungraded sales | 4 |
| `manual_dilutes` | Your own sales join the thesis-break denominator | 1 |
| `each_sell_a_trade` | Every SELL (a TRIM too) is a closed trade | 4 |
| `product_no_guard` | The product-form expectancy and a plain `<` | 1 (`test_expectancy_flag[5.0-clear]`) |
| `sold_share_ge`, `sold_min_7`, `thesis_ge`, `nifty_ge`, `hold_le` | Each red line moved by one unit | 1 each, the "one unit below" case |
| `append_always`, `rewrite_week` | No idempotency; a re-run replaces the row | 3, 2 |
| `store_unfinished` | An unfinished week is stored | 1 |
| `current_week_midweek` | A weekday run covers its own, unfinished week | 3 |
| `default_user_audit` | The auditor file of the default user (`primary`) is read for everyone | 1 (the member test) |
| `scorecard_after_headline` | The scorecard follows the headline | 2 |
| `manual_cost_unstamped` | The manual-sale route without `cost_basis`/`pnl_pct` | 1 |
| `product_expectancy` | The product form alone | **0: equivalent.** The `_below` guard (noise under 1e−9) absorbs the −8.9e−16; `product_no_guard` shows the boundary test bites when both defences are gone |

The unmutated baseline passes 50/50 in the same selection. Run 1, before the last wording
edits, gave the same result for the 24 mutants it had (`mutants_run1.log`). Run 2
(`mutants.log`) ran on the final bytes.

## Commands and environment

Windows 11, the repository's `.stockai` venv (Python 3.13), Node 24 with the vendored
Playwright Chromium. Hermetic boundary on (SA-005): no `.env`, no network, no checkout data.

| Command (repository root) | Result |
|---|---|
| `.stockai/Scripts/python.exe -m pytest tests/unit/test_weekly_scorecard_pr002.py tests/unit/test_delivery_weekly.py -q -p no:cacheprovider` | **365 passed** (story file 350, of which 300 property seeds; weekly 15) |
| the same plus `test_delivery_api.py`, `test_portfolio_api.py`, `test_autopilot_api.py`, `test_m0_idor.py` (before the last story tests were added) | 408 passed |
| `bash analysis_data/pr002/run_mutants.sh` | baseline 50/50; 24 of 25 mutants caught, 1 equivalent (table above) |
| `npm run test:frontend` | **32/32** (was 30; the 2 new weekly tests) |
| the 2 weekly browser tests with `SA_FRONTEND_ROOT` = HEAD's prototypes | **both fail**, as intended |
| `.stockai/Scripts/python.exe -m pytest -q -rfEs -p no:cacheprovider tests` (CI's command) | **4,946 passed, 12 skipped, 1 failed** in 22 min 23 s. The failure is below |
| the failed test alone, three times | 1 passed, 3 times |
| `python scripts/ci/check_broad_except.py` | OK (152 grandfathered); `scan_source` over the new and changed files: no new swallow |
| `python scripts/docs/build_kt_pdf.py`, then `check_kt_docs.py` | 44 pages, source `c150c7aa…`; errors `[]` |
| `python scripts/seed_fixture_ui.py --data-dir <scratch>` | writes the weekly with a real scorecard (red flag: thesis break 2 of 2) |

**The one full-suite failure is not PR-002's.**
`tests/unit/intelligence/rl/test_store_migration_sa009.py::test_rollback_refuses_a_quarantined_store_whose_bytes_changed`
raised `PermissionError: [WinError 5]` from `os.replace` in `store_migration._write_lineage`,
inside the test's own `%TEMP%` folder. That is a transient Windows lock on a fresh file. The
code is untouched by this story, and the test passed alone 3 times. *Observation for SA-009's
owner (low):* `_write_lineage` uses a bare `os.replace`, where the portfolio store uses
`core.utils.atomic_io.replace_with_retry` for exactly this Windows behaviour.

Raw outputs (ignored): `analysis_data/pr002/full_suite.txt`, `npm_frontend.txt`,
`mutants.log` (final bytes), `mutants_run1.log`, `browser_fixture.json`.

## Documentation

Each change below is written as current design. Story IDs appear only as **Planned**
pointers.

- **KT** (`docs/TECHNICAL_DESIGN.md`):
  - section 3: `weekly_scorecard.jsonl` and `advice_outcomes.jsonl` in the per-user records;
  - section 7: the report-families row and a new subsection, "Weekly results scorecard",
    with the line definitions, the five flags, the missing-data rule and one worked example
    (4 of 7 vs 40–70%). Virtual P/L now points to it for the Nifty comparison;
  - section 9: the `weekly_review` job row;
  - section 10: the Delivery paragraph;
  - section 11: "Measure weekly" names the scorecard as the yardstick and drops the story
    pointer;
  - section 12's PR-002 row stays `Open` until the fresh review accepts it.

  The new module is named in code formatting, not linked: `check_kt_docs` requires a linked
  source to exist at the declared revision (`3df1f6e`), as earlier stories did with new
  files. The header bump at commit time can make it a link.
- **PDF** rebuilt (44 pages, source SHA-256 `c150c7aad527…`). `check_kt_docs` reports `[]`.
- **ARCHITECTURE**: the auditor, the monthly replay and the scorecard are different
  measurements; the scorecard reports and changes no decision.
- **PRODUCT_MAP**: per-user plane files, the weekly-review row, a "Results scorecard" module
  row.
- **AUTOPILOT_GUIDE**: the per-user file tree, `GET /portfolio/scorecard`, and the manual sale's
  `cost_basis`/`pnl_pct`.
- **Human testing guide**: new case **09-G** (HT-09). It covers the email's order, idle cash
  counted against the portfolio, "could not check … between 40% and 70%", a hand count of
  each line, a second trigger that changes nothing, and a member who sees only their own
  rows. 09-F now names the scorecard's lines. Status line: "implemented, awaiting its fresh
  review, not deployed".
- No change needed: `tests/TEST_DOCUMENTATION.md` (general, lists no story files);
  `UI_SPEC.md` (does not describe the weekly screen).

## Manifest and digest

- **Review input:** [PR-002-manifest.json](PR-002-manifest.json), 15 files. The SHA-256 of
  its LF bytes is **`8e03a0511601345ceb435152938b4585baca7d98c8e7e908426507a8e2298cae`**;
  `kt_manifest.py verify` gives 0 mismatches.
  - Code (6): `core/portfolio/results.py` (new), `core/portfolio/store.py`,
    `core/delivery/weekly.py`, `services/api/routes/portfolio_api.py`,
    `src/frontend/prototypes/weekly-view.jsx`, `scripts/seed_fixture_ui.py`.
  - Tests (3): `tests/unit/test_weekly_scorecard_pr002.py` (new),
    `tests/unit/test_delivery_weekly.py`, `tests/frontend/no_invented_figures.test.mjs`.
  - Docs (6): the KT and its PDF, ARCHITECTURE, PRODUCT_MAP, AUTOPILOT_GUIDE, the testing
    guide.
  - Excluded: STATE, HANDOFF, this receipt (bookkeeping), and the owner's own line in
    `docs/README.md`.
- **Diff digest:** **`3daee1a4bc1974e7aa975dadd914a13a35ecdfbfca37977705e661d73442cff7`**,
  127,546 bytes over 14 paths (every manifest path except the PDF), by
  `analysis_data/pr002/digest.py`. It checks that HEAD is `b67f972`, runs
  `git diff --no-color --no-ext-diff b67f972 -- PATH` for the 12 modified paths and
  `git diff --no-index /dev/null PATH` for the 2 new ones, then sorts by path and
  concatenates.

## Self-review

This is a same-conversation self-review. It is not the fresh review, which stays pending.

- **"Can the scorecard flatter the portfolio?"** (the card's hard-review question):
  - Exited stocks stay in every denominator: closed trades count every full exit,
    "sold too early" every advisor sale whether held or not, and the thesis share every
    advisor sale.
  - Horizons count NSE sessions through the auditor's own `trading_days_after`.
  - The Nifty comparison is money-weighted with the same flows on both sides, so idle cash
    counts against the portfolio (tested at 0% against +10%).
  - Missing data is shown, never skipped, and cannot clear a flag (D4).
  - Your own sales cannot dilute the thesis-break share (D12).
- **Issue-time.** Transactions and value points after the covered week are dropped before
  anything is computed. A grade is looked up only for a sale whose horizon ended by the week's
  end, so a grade "from the future" cannot count (tested, and mutant `future_grade`).
- **Authorization.** The endpoint takes the user from the session only; the store and the
  auditor file are the caller's own. A member's sale carrying the owner's ref finds no grade.
- **Duplicate and retry.** Each week is written once, under a file lock (8 threads, 1 row). A
  weekday or future run never stores an unfinished week.
- **Bounded math.** A cost or base at or below zero gives "unknown" or "unavailable"; an empty
  population gives "not enough", never a division.
- **Compatibility.** A weekly review stored before the change (no `scorecard` key) renders as
  before, in text and on screen. A stale `scoreboard` key is ignored by both. Old scorecard
  rows keep their own sentences, which were the record sent that week.
- **Found and fixed during the phase:**
  - (a) The product-form expectancy gives −8.9e−16 for an exact 0, which would fire "below
    0" (D14).
  - (b) A week with no valuation compared the last point with itself and printed "0%
    against 0% (level)", the flat line the card forbids. It now reads unavailable.
  - (c) An account with no valuation history would have read "could not check" every week
    (D13).
  - (d) `_floor()` had a silent broad `except`. The CI guard lists files with
    `git ls-files`, so it could not see the untracked module. The handler is narrowed and
    logged, and `scan_source` over the new and changed files gives `[]` (the one finding in
    `weekly.py` is the grandfathered `_narrate_weekly #0`).
  - (e) Two sentences repeated their own label or read awkwardly.
- **For the reviewer to rule on:** D1 (executed sales, not raw auditor rows), D3 (since-start
  expectancy at three week ends), D4 (a trade with no recorded cost is excluded and counted,
  not bounded), D5 (a stored row is frozen even if a Nifty outage made its comparison
  unavailable) and D8 (HTML = the Inbox screen).

## Limits and follow-ups

- **The nightly auditor grades the default user only** (`grade_due(today)` in the scheduler).
  If a member ever had advisor sales, they would read "no grade" and the flag "could not
  check". Today only the owner's account runs autopilot (the seed script is its only
  switch). *Owner of the follow-up:* whichever story gives members autopilot.
- **A stored week is frozen.** A row computed during a Nifty-fetch outage keeps
  "unavailable"; the next week's row has its own since-start line. This is the card's
  idempotency rule, applied on purpose.
- **Nifty closes come from the auditor's benchmark series** (yfinance, latest close at or
  before a date when its own bar is absent). The known close-identity limit in KT section 7
  (SA-012) applies to both.
- **Before costs and taxes** until SA-048.
- **Production's earliest July sales have no recorded cost.** They will show as "N earlier
  trades with no recorded cost not counted" on every row.
- **The weekly email stays plain text** (D8).
- **Identity reconciliation writes no BUY row.** A demerged or renamed stock sold later
  (`core/portfolio/identity_reconcile.py` replaces the holding in place) has a known result
  but no purchase date. Its holding period reads unknown, and the bounds rule decides the flag.

## Rollout (at the owner's word)

Report only: no decision, trade or message count changes. The weekly email is the same
single Sunday email per account.

1. After acceptance: commit, then push in a job-free window (not 16:25–17:15 IST, and not
   Sunday 17:45–18:30 IST). Railway redeploys on push.
2. Close and reopen the app once, so the service worker fetches the new `weekly-view.jsx`.
3. The first Sunday after the deploy (18:00 IST), read the email and
   `GET /portfolio/scorecard`, and record the first row (week key, flags fired, could-not-check
   lines) in this receipt's production section. Then run guide case 09-G.
4. Rollback is a revert. `weekly_scorecard.jsonl` is new and read by nothing else, so it can
   stay or be deleted.

## Committed at the owner's word, before the review

The owner said "ya commit and push" (16 Oct, about 18:20 IST), so the fresh review will read
committed code, as FIX-010's first review did.

- **`b400747`** (`b4007470e9e91c427719325016088607848b8e01`, parent `b67f972`): the 9 code and
  test files. `kt_manifest verify --rev b400747` against the implementation input matches all
  9; the 6 mismatches are the docs, which follow in the docs commit.
- **The docs commit** carries the docs and this receipt, plus three commit-time edits:
  - the KT header's "Code inspected" moves to `b400747`, and section 7 now links
    `results.py`;
  - the PDF is rebuilt (source `d1a86e53…`, 44 pages; `check_kt_docs` `[]`, 91 linked
    sources, none changed since `b400747`);
  - guide 09-G's status line.
- **Review input for the fresh review:** [PR-002-manifest.json](PR-002-manifest.json)
  **`98df10d051f35a77d903f3bb3001bbc4eff94c2b1dad8d1f9956d5d0927afc9a`** (15 files, the
  committed bytes). The implementation-time input `8e03a051` is kept as
  [PR-002-manifest-implementation.json](PR-002-manifest-implementation.json). The two differ
  only in the KT, the PDF and the guide. The code diff is `git diff b67f972 b400747`.
- **The push** and the deployment are recorded in STATE and HANDOFF.

## Next

A fresh-session hard review of PR-002 in a new conversation ("continue"), using
[REVIEW.md](../REVIEW.md) and the manifest above. After acceptance, STATE order continues
with PR-003.

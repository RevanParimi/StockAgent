# PR-016 — fresh review receipt

**Story:** [PR-016](../stories/PR-016.md): show what the book earns at prices that could really
be had. Implementation receipt: [PR-016-implementation.md](PR-016-implementation.md).

**Review context: fresh session.** Autopilot session `1120-1433-p5` on the code-server, a new
conversation opened with "continue", Friday 20 Nov 2026 from about 14:33 IST, outside a push
window. The implementing session (`1120-1355-p4`) had ended at 14:33 IST. `main` = `a909e6e`
(records only on top of `ac97ce3`), `origin/main` = `03debc1` after a fetch. Production was not
read. Nothing was pushed, deployed, run or sent.

**Lane:** decision path, confirmed (the card's own lane: it sets the price the record is judged
at). It changes no trade, no booked price and no decision: only the weekly scorecard reads the
side file (my own `git grep` of `executable_prices`, `load_executable_prices` and
`core.portfolio.executable` over the code finds `results.py`, `executable.py` and `store.py`
alone).

**Verdict: ACCEPTED** for `31d178e`. Every acceptance criterion is met. One low finding (the
`paper_prices` flag can read clear while trades have no price, and its clear sentence does not
say how many) goes to BACKLOG B-29. Merged into `main` as `f0ab71c`.

## Review input, verified

| Check | Result |
| --- | --- |
| Branch | `story/PR-016` = `31d178e`, one commit on `ac97ce3` (`git merge-base main story/PR-016`) |
| Diff digest | `git diff ac97ce3 31d178e \| sha256sum` = `bf0d79fb738f0614…` = the implementation receipt |
| Files | 13 files, +1,253 / −19, as the receipt says |
| Where it ran | a detached worktree of `31d178e` in the scratchpad (the full suite, the reviewer cases and the mutants) |
| Merge | `git merge-tree --write-tree main story/PR-016`: clean. `main`'s one commit since `ac97ce3` (`a909e6e`) changes only `docs/planning/` |

## Contract checked

I traced an autopilot trade from the executor to the email. `autopilot._txn` and
`_deploy_idle_cash` write each BUY and SELL with `date` = the reviewed session, `price` = that
session's close (`closes` / `rec.close`, or the candidate's `SessionClose`) and `ts` =
`datetime.now(timezone.utc)`, so every autopilot row has a zone-aware run time (since the first
version of `_now_iso`, `92a13e1`). DIV rows are `source="autopilot"` with side `DIV`; seed,
manual and CSV rows carry their own sources; `is_autopilot_trade` leaves all of them out.

- **Issue time.** `price_trade` asks for `next_trading_day(booked)` and for
  `max(first_session_after_run(run), that)`; `price_at` refuses any session on or before the
  booked one. The panel's `load_day` reads the day's own file, never an earlier one. No price
  is read from a bar on or before the booked close.
- **Price basis.** The open goes through `exit_shadow.horizon_in_basis` with the booked session
  as `start` and `decided` = the booked session only when the booked price is within 1% of the
  panel's close for it. Otherwise the run's day, so a bonus or split between the booked session
  and the run is lasting "no price". I checked the three branches against the function's
  rules: a split ex the next morning is converted; a booked close that may already be adjusted
  is refused; demergers, schemes, unreadable rows, an empty list or one starting late, and a
  registry break never convert.
- **Freshness and retries.** A session after `today` or a day file missing for up to 7 calendar
  days waits; `sync_recent(days_back=7)` scans 7 calendar days back, so the two agree. An unread
  NSE list waits (`corp_actions_fn` caches it per symbol for one scorecard). A row is appended
  only once both prices are settled, under `executable_prices.lock`, and a stored row wins.
- **The book.** `vs_nifty` since the start is `(end − deposits) / deposits` with start equity 0,
  so `scorecard_block`'s `(portfolio_value + effect − deposits) / deposits` equals the paper
  figure when nothing is priced. Only trades dated on or before the last valuation move it.
  Each BUY pays and each SELL receives the real price, and charged costs are recomputed at the
  same rates both ways. A price from a session after the week's Sunday still reads waiting in
  that week's row.
- **Bounded math.** Every division is by a positive booked price, by deposits that
  `vs_nifty` has already required to be positive, or by a guarded `paid`. `_positive` drops a
  NaN or non-positive open, so no NaN reaches the JSON row.
- **Who reads it.** The scorecard is built only by the Sunday job (`core/delivery/weekly.py`
  `_safe_scorecard`; no route builds it). The new flag renders through the generic red-flag
  code in the email, the app and the fallback headline ("Paper prices flatter the book" before
  its colon). No code lists a user's files by name, so the new file needs no export or delete
  change.

## Adversarial examples, worked independently

My own cases (`analysis_data/pr016_review/test_review_cases_pr016.py`, this device only), with
the real `EodStore` (parquet day files), the real `PortfolioStore` and `weekly_scorecard`. Each
figure was worked by hand in the file's docstring before running.

| # | Case | Expected (by hand) | Result |
|---|---|---|---|
| RV1 | Week of 8 Mar. ₹2,00,000 in, valued ₹2,10,000. BUY XYZ 100 @ ₹500, where Monday's file lists a bond (N1) row first at ₹1,000 and XYZ splits 1:2 ex Tuesday. BUY PQR 50 @ ₹300, with no PQR bar on Tuesday. SELL XYZ 200 @ ₹270 on Thursday, with Friday's file not yet in. | XYZ: ₹510 / ₹520 (raw ₹255 / ₹260); PQR: no price, then ₹310; the sale waits and is not written; the book +4.5% and +3.75% against +5.0%; "too few to judge"; the ledger's bytes unchanged; a rerun changes nothing | as expected; the line reads "+4.5% … +3.8% … 3 trades; 1 with no price and 1 waiting at the next open, 1 waiting at the open after the run, each kept at its booked close." |
| RV2 | The next week, Friday's and Monday's files arrive | the sale ₹268 / ₹266, −₹1,400 in all, +4.3%; the round trip loses 2.90 points (54,000/50,000 against 53,600/51,000); the first week's stored row unchanged | as expected |
| RV3 | Ten writers append 50 rows at once, each in its own order | 50 rows, each `txn_id` once | as expected |
| RV4 | A SELL booked at ₹480, a level rather than its session's ₹500 close | priced at the next open, ₹495 (+3.125%), with the basis set at the run | as expected |
| RV5 | 30 round trips losing 0.22 points each, the lead keeping its sign, and 10 more BUYs with no price | — | the flag reads clear, and its sentence does not mention the 10: finding L1 |

## Tests and the original defect

- The story's 34 tests take every expected figure from a comment worked by hand. The property
  test plants a sentinel open on the booked day, and the ledger is checked byte for byte. None
  reaches the network: the panel, NSE's list and the Nifty are fakes passed in, and
  `weekly_scorecard` takes `panel_on` and `corp_actions`.
- **Reviewer mutants: 9 of 9 caught** by `test_executable_prices_pr016.py`:
  - the booked-close check dropped;
  - the worst equity series preferred;
  - the week's cut on a price's session removed;
  - a SELL's cash effect with the wrong sign;
  - trades after the last valuation moving the book;
  - the pre-open cut moved to 15:30;
  - a missing file waiting for ever;
  - a registry break ignored;
  - a temporary basis gap written as lasting.

  Each was put back after its run; the worktree was clean at the end.

## Findings

| # | Severity | Where | What | Disposition |
|---|---|---|---|---|
| L1 | low | `core/portfolio/executable.py:365` (`rule_flag`, the clear branch) with `scorecard_block` (a trade without a price keeps its booked close; a round trip with an unpriced leg is left out of the average) | `paper_prices` reads "Paper prices are close enough" with any number of trades unpriced, and its sentence does not say how many (RV5: 10 of 70). The scorecard's general rule, in the `results.py` module docstring ("reads clear only if it holds even when they all count against it"), does not hold for this flag, and the docstring does not say so. KT section 7 states the exception, and the line just above the flag counts the unpriced trades, so a reader of the email sees them. It changes no buy, sell, size or grade (the flag reports). No-price causes are rare by inspection: a suspended stock, a day file missing for over 7 days, a demerger, an empty NSE list. | [BACKLOG](../BACKLOG.md) B-29 |

None found against the card's contract.

## Living documents

The following describe the reviewed behaviour, and its example matches RV1's arithmetic:
- KT section 7 (the "At prices that could be had" row, "Prices that could be had", the
  `paper_prices` flag and its missing-data sentence, the limits paragraph) and the store table
  in section 3;
- AUTOPILOT_GUIDE ("The booking price", the file list, the test table);
- the testing guide's case 09-J;
- CODEBASE, ARCHITECTURE, PRODUCT_MAP and EDGE-ROADMAP section 7.

The PDF is not regenerated (AGENTS.md, owner's rule of 17 Nov 2026). Guide case 09-J's label is
updated with this review.

## Commands and results

Python 3.13.5 (`.stockai/bin/python`), a detached worktree of `31d178e`.

```
git diff ac97ce3 31d178e | sha256sum
git merge-tree --write-tree main story/PR-016
.stockai/bin/python -m pytest -q tests/unit/test_executable_prices_pr016.py \
    tests/unit/test_weekly_scorecard_pr002.py tests/unit/test_scorecard_losses_pr013.py \
    tests/unit/test_portfolio_vs_nifty_sa051.py tests/unit/test_eod_store.py \
    tests/unit/test_delivery_weekly.py
PYTHONPATH=<worktree>:<worktree>/src .stockai/bin/python -m pytest -q \
    analysis_data/pr016_review/test_review_cases_pr016.py   # a copy outside the worktree
.stockai/bin/python -m pytest -q                       # full suite at 31d178e
.stockai/bin/python scripts/ci/check_broad_except.py
.stockai/bin/python scripts/docs/check_kt_docs.py
```

- **Focused suites:** 723 passed.
- **Reviewer cases:** 5 passed (RV1–RV5).
- **Full suite at `31d178e`:** 6,917 passed / 5 skipped / 1 xfailed / 0 failed.
- **Broad-except guard:** OK (138 grandfathered). **`check_kt_docs.py`:** `errors: []`.
- **On the merge commit:** `git diff 31d178e f0ab71c` touches only `docs/planning/` (the
  implementation receipt, BACKLOG B-28, STATE and HANDOFF from `a909e6e`), so the code is
  byte-identical to the reviewed revision.

## Acceptance checklist

- A real price never comes from a bar dated on or before the booked close: **met**. This is the
  property test, the refusal test and RV1's day files.
- A split on the next session does not show as a 50% gap: **met** (₹51 reads ₹102; RV1's ₹255
  reads ₹510).
- A missing bar gives "no price" on the row and a count on the line; nothing is guessed:
  **met** (RV1's PQR).
- Running it twice adds no row: **met** (RV1's rerun; RV3's concurrent writers).
- The ledger's bytes are unchanged; the line carries its n: **met**.
- Living documents (KT section 7, AUTOPILOT_GUIDE section 9, a guide case): **met**.
- Not in this card, and not done: no booking price or run time changed.

## Production

Not deployed. The next push carries it (the runner's or a session's, from Sat 21 Nov 00:10
IST). New check `PR-016-W1` (STATE `pending_production_checks`) is the implementation
receipt's proposal, as written there. On the first Sunday the job reads NSE's list once for each
symbol the autopilot has traded, so a list NSE does not answer that day leaves its trades
waiting until a later Sunday, and the W1 read may see such waiting rows.

## Decision

**ACCEPTED** for `31d178e`; status `done`. Merged into `main` as `f0ab71c`; push pending to
the next window (Sat 21 Nov 00:10 IST). Follow-up: BACKLOG B-29 (L1).

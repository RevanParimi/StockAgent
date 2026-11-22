# FIX-033 — fresh review receipt

**Story:** [FIX-033](../stories/FIX-033.md): a deep dive's idea is the company it was asked
about. Implementation receipt: [FIX-033-implementation.md](FIX-033-implementation.md).

**Review context: fresh session.** Autopilot session `1123-0126-p2` on the code-server, a new
conversation opened with "continue", Monday 23 Nov 2026 from about 01:26 IST, inside the push
window. The implementing session (`1123-0029-p1`) had ended at 01:18 IST. `main` = `origin/main`
= `a108ade` (FIX-033's records on top of `2cf3eee`) after a fetch. Production was not read.

**Lane:** decision path, confirmed. It changes what is bought (every buy door refuses another
company's analysis) and what is sold (a new EXIT trigger), and it changes how the deep dive, the
monthly forecast, the paper lane and the daily review name the company they analyse.

**Verdict: ACCEPTED** for `a3a2116`. Every acceptance criterion is met. No critical, high,
medium or low finding; one nit (N1), no follow-up. Merged into `main` as `9875e9a`.

## Review input, verified

| Check | Result |
| --- | --- |
| Branch | `story/FIX-033` = `a3a2116eb10f92d5…`, two commits (`dcd17f5`, `a3a2116`) on `2cf3eee` |
| Diff digest | `git diff 2cf3eee a3a2116 \| sha256sum` = `8f92bf60787e18c4…` = the implementation receipt |
| Manifest | `kt_manifest.py verify FIX-033-manifest.json --rev a3a2116`: 31 files, mismatches `[]`, review input `36ce5e97acb0b888…` |
| Files | 31 files, +1,147 / −79, as the receipt says |
| Where it ran | a detached worktree in the scratchpad: `a3a2116` (focused tests, reviewer cases, mutants), then `9875e9a` (full suite) |
| Merge | `git merge-tree --write-tree main story/FIX-033`: clean. `git diff a3a2116 9875e9a` touches only `docs/planning/` (FIX-033's records from `a108ade`), so the merged code is byte-identical to the reviewed revision |

## Contract checked

**The 14 Nov defect, traced again on the new code.** A screen candidate DEEPA, neither managed
nor tracked: `run_deep_dives` has already checked it is a listed company (`instrument_kind`),
then calls `analyse(..., exact_symbol=True)`. `_resolve_ticker(exact=True)` returns a managed or
tracked symbol as itself as before; otherwise `_listed` reads the cached listing
(`bhavcopy.load_listing`, the weekly run's own `refresh_listing`), and DEEPA is analysed as
DEEPA with Yahoo's long name. No model and no web search is reached. An unlisted symbol raises
`UnlistedSymbol` (a `ValueError`) before any data is read, and the dive logs it and keeps
nothing. The report's ticker is the query's, so `ScoreStore.save` files the analysis under DEEPA
and the dive's check (`plain_symbol(report.ticker)` against the candidate) passes. A report of
another company, or of none, keeps no result, no memo entry and no idea, and the call still
counts against the budget.

**Every consumer of an idea.** `apply_deep_dives` and `apply_redives` refuse or drop another
company's dive. `buy_candidates` refuses a shelf idea (held or not) and a watchlist idea. The
pipeline builds `shelf_index`, which the SWITCH leg (`_execute_buys`) and deployment
(`_deploy_check`, `_deploy_idle_cash`) read, from the candidate list's output, so both see the
same stamped copies, and both check `analysis_of_other` again. Each BUY from an idea writes
`analysed_symbol`, and ADD and top-up rows write none. `analysed_elsewhere` reads the ledger in
file order (`load_transactions` returns the last 2,000 appended rows as written). A sale to
zero clears the flag. The advisor appends `bought_on_other_analysis` first among the EXIT
triggers under both rules. `gated_decide` never blocks an EXIT, and only SA-008's identity
hold comes earlier. The narration is fixed words, and the scorecard's reason order starts with
the new code.

**Callers of the exact path.** I ran `git grep` over `generate_forecast(`,
`_run_orchestrator_analysis(` and `_run_todays_agent_scores(`. Every caller passes a managed
ticker (the startup self-heal, the scheduler's monthly forecast, the operator's scheduler API,
the re-forecast), a shelf symbol (the paper lane), or a CLI argument. The chat, the stream and
the Analyze box call `analyse` without the flag and keep the resolver.

- **Issue time and the legacy read.** The dive keeps `str(report.investment_thesis)[:800]`.
  `ScoreStore.save` stores `report.investment_thesis` with `run_at = datetime.utcnow().isoformat()`.
  `_thesis_day_bounds` builds naive-UTC ISO bounds in the same format, so the text comparison
  is exact. SQLite's `substr` counts characters as Python's slice does (the story's real-store
  test uses "₹"). Reading the dive's IST day and the next only widens the window; a match needs
  the identical 800 characters.
- **Missing data.** With no listing, Yahoo decides, and no model is asked. An unread history
  leaves an idea as loaded (fail open per idea, logged). An unread ledger names no holding that
  run (logged), and the next run reads it. An unknown `analysed_symbol` ("") is bought as before
  (the implementer's recorded decision).
- **Duplicates and retries.** `verify_analyses` touches only active ideas with no
  `analysed_symbol` and drops one once. A second run finds nothing to do. The daily review
  writes no shelf. A re-run review on the same day finds the holding already sold.
- **Who can read it.** `theses_between` returns ticker and 800 thesis characters to a
  server-side check only. FIX-010's guard names its one caller.

## Adversarial examples, worked independently

These are my own cases (`analysis_data/fix033_review/test_fix033_reviewer_cases.py`, this
device only). They use the real resolver, `run_deep_dives`, `buy_candidates`,
`analysed_elsewhere` and `run_post_review_pipeline`. Each expected value comes from an oracle
written apart from the code or is worked by hand in the docstring.

| # | Case | Expected | Result |
|---|---|---|---|
| RV1 | 3,000 random ledgers over three symbols: partial and full sales, top-ups, re-entries, analysed symbols spelled `x`, `X.NS`, `X.BO`, `NSE:X`, ` X ` or another company | an oracle replaying share counts from each row's `qty` (not `holding_qty_after`): named iff held now and a BUY of the current episode names another plain symbol; never a symbol not held | as expected |
| RV2 | the exact resolver over all 32 shapes of (managed, tracked, listed, listing cached, Yahoo prices), input `" deepa"` | DEEPA when managed or tracked or (listed if cached, else Yahoo prices); otherwise `UnlistedSymbol`; 0 model calls in every shape | as expected |
| RV3 | the dive with report tickers `GOOD`, `good`, `NSE:GOOD`, `GOOD.BO`, `" GOOD.NS "`, `GOODLUCK`, `GOODLUCK.NS`, `""`, `None` | kept as GOOD for the first five; refused with `other_company` {GOOD: GOODLUCK} or {GOOD: "?"} otherwise; 1 call each | as expected |
| RV4 | the candidate list with `analysed_symbol` `NSE:X`, `" x "`, `X.BO`, `nse:x.ns`, `XY`, `NSE:XY`, `Y.BO` | offered for the first four, refused for the last three | as expected |
| RV5 | real pipeline, two sessions: DEEPA 100 @ ₹1,000 bought on DEEPAKNTR's analysis, now ₹1,050; ₹9 L cash; on the shelf DEEPA's legacy idea with Nitrite's thesis (0.95, in band) and GOOD's own (0.80) | session 1 sells all 100 DEEPA at ₹1,050 and buys GOOD; DEEPA is never bought back, that session or the next; GOOD's BUY names GOOD; afterwards `analysed_elsewhere` is empty | as expected: a SWITCH, DEEPA → GOOD 100 @ ₹1,000, reason "SWITCH — bought on DEEPAKNTR's analysis, not DEEPA's; …" |

## Tests and the original defect

- The story's 40 tests reproduce the defect's own path (free-text DEEPA → DEEPAKNTR with one
  model call). The resolver test's transport answers DEEPAKNTR for anything and counts calls,
  and the web search raises. The other fakes are the orchestrator seam and the score-history
  seam. No real transport, SMTP or push is reached (the suite is hermetic, SA-005).
- **Reviewer mutants, 9 of 9 caught** by the story's tests and the reviewer cases together. I
  ran each alone (`analysis_data/fix033_review/mutants.py`) and put it back afterwards. The
  worktree was clean.
  - the exact flag ignored (the model asked);
  - a sale to zero not clearing;
  - the `NSE:` prefix kept (N1);
  - the pipeline ignoring the ledger;
  - the list's check removed;
  - the SWITCH BUY unstamped;
  - the dive comparing the raw ticker;
  - legacy ideas never stamped;
  - an unknown symbol refused.

  The story's tests alone catch 8 of 9; RV3 and RV4 catch the ninth.

## Findings

| # | Severity | Where | What | Disposition |
|---|---|---|---|---|
| N1 | nit | `core/discovery/shelf.py:178` (`plain_symbol`), story tests | No story test spells a symbol with the `NSE:` prefix: removing that branch passes all 40. No current path writes one (the exact path's report ticker is the query's own), so nothing is bought or sold differently today. | None; RV3 and RV4 cover it in the reviewer cases |

**Observations, not findings:**

- A SWITCH out of a misfiled holding is counted as a "SWITCH sale" in the scorecard's reasons.
  Its buy leg's row carries the sale's narrative and triggers, as every SWITCH's buy leg does
  (RV5's GOOD row reads "SWITCH — bought on DEEPAKNTR's analysis, not DEEPA's; …"). The
  trades are right.
- A BUY written before FIX-033 is not judged (the implementer's decision). DEEPA, the only one
  the B-32 read found, was sold on 21 Nov.
- The exact path still takes the company's name for the analysis from Yahoo, and the symbol
  when Yahoo has none. On 14 Nov DEEPA's own analysis named "Deepak Automobiles Ltd". This was
  not exercised further.

## Living documents

These describe the reviewed behaviour:
- KT section 4 ("Ticker resolution"), section 6 (the buy doors), section 7 (the exit-reason
  order) and section 8 (steps 3, 4, 5, 6);
- ARCHITECTURE (identity);
- CODEBASE (four module rows);
- the testing guide's 06-R and 07-V. Their labels are updated with this review.

The KT's dated example (14 Nov) follows the section's existing TATAELXSI example. The PDF is not
regenerated (AGENTS.md, the owner's rule of 17 Nov 2026).

## Commands and results

Python 3.13.5 (`.stockai/bin/python`), hermetic, a detached worktree.

```
git diff 2cf3eee a3a2116 | sha256sum
.stockai/bin/python scripts/docs/kt_manifest.py verify docs/planning/PI-2026-09/evidence/FIX-033-manifest.json --rev a3a2116
git merge-tree --write-tree main story/FIX-033
.stockai/bin/python -m pytest -q <the 11 test files the diff changes> \
    tests/unit/test_fix033_reviewer_cases.py tests/unit/test_deploy_idle_cash_sa049.py   # at a3a2116
.stockai/bin/python analysis_data/fix033_review/mutants.py                               # at a3a2116
.stockai/bin/python -m pytest -q                                                         # at 9875e9a
.stockai/bin/python scripts/ci/check_broad_except.py
.stockai/bin/python scripts/docs/check_kt_docs.py
```

- **Focused, with the reviewer cases:** 479 passed (the 40 story tests among them).
- **Reviewer cases:** 50 passed (RV1–RV5 with their shapes).
- **Full suite at `9875e9a`** (code identical to `a3a2116`, in the worktree): 6,958 passed / 8 skipped /
  1 xfailed / 0 failed (3m52s; three more tests skip there than in the main checkout).
- **Full suite at `aeb38b9`** (the records commit, the one pushed), main checkout: 6,961 passed / 5
  skipped / 1 xfailed / 0 failed (7m57s).
- **Broad-except guard:** OK (138 grandfathered). **`check_kt_docs.py`:** `errors: []`.

## Acceptance checklist

- A dive whose orchestrator returns another ticker shelves nothing, with the reason; the DEEPA →
  DEEPAKNTR fixture: **met** (story tests; RV3).
- A listed symbol outside the managed list makes no resolver call, with the transport blocked:
  **met** (story tests; RV2 over 32 shapes).
- Every buy door refuses an idea whose analysis is of another symbol (a planted shelf row):
  **met** (the list, the watchlist door, the SWITCH leg, deployment, the shelf add, the re-dive;
  RV4, RV5).
- A holding bought on another symbol's analysis is EXITed at the next review with that reason:
  **met** (story's real pipeline; RV1; RV5 as a SWITCH).
- The misfiled idea now on the shelf: **met**. The daily review refuses it from the first run,
  and Saturday drops it and forgets its memo entry. DEEPA's own sale on 21 Nov also keeps it
  out (FIX-029's re-buy rule).
- Living documents: KT sections 4 and 8 and a testing-guide case: **met**.

## Production

**Deployed** with `aeb38b9`. This session pushed it at about 01:49 IST on Mon 23 Nov, inside
the window, after the full suite on that commit. Railway deployment `1b5e318b` (commit `aeb38b9`)
read SUCCESS by 01:50, and `/health` answered 200 at 01:50:12 IST. Production was not otherwise
read. New check `FIX-033-W1` (STATE `pending_production_checks`) is the implementation
receipt's "Production watch", as written there. It reads from today's 16:30 review and from the
first Saturday run after the deploy (Sat 28 Nov).

## Decision

**ACCEPTED** for `a3a2116`; status `done`. Merged into `main` as `9875e9a`; deployed with
`aeb38b9` (01:49 IST, 23 Nov); production verification `pending_observation` (`FIX-033-W1`).

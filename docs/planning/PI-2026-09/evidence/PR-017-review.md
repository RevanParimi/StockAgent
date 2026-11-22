# PR-017 — fresh review receipt

**Story:** [PR-017](../stories/PR-017.md): grade every deep dive at the conviction it was issued
with, beside the screen's other candidates. Implementation receipt:
[PR-017-implementation.md](PR-017-implementation.md).

**Review context: fresh session.** Autopilot session `1123-0159-p3` on the code-server, a new
conversation opened with "continue", Monday 23 Nov 2026 from about 01:59 IST, inside the push
window. The implementing session (`1120-1454-p6`) ended on 20 Nov. `main` = `origin/main` =
`61b7305` after a fetch (the runner pushed that deploy record at 01:59). PR-015's switch waits
for the 04:00–06:20 part of the window (STATE `next_phase`), so this phase took the review.
Production data was not read (only Railway's deployment list and `/health`, after pushes).

**Lane:** decision path, confirmed. It defines how ideas are graded (the card's own lane). It
changes no buy, sell or size: the new lanes write only the auditor's store, and the bare judge
writes only its own file.

**Verdict: ACCEPTED** for `1b01f80`. Every acceptance criterion is met. No critical, high or
medium finding. Five low findings: L1 (five invariants the story's tests let through) is closed
by the reviewer's tests committed on `main` (`d7a6dc4`); L2 to L5 are BACKLOG
[B-33](../BACKLOG.md), B-34 and B-35. Merged into `main` as `d41c439`.

## Review input, verified

| Check | Result |
| --- | --- |
| Branch | `story/PR-017` = `1b01f807f155…`, three commits (`5151455`, `2ce862f`, `1b01f80`) on `7293fb4` |
| Diff digest | `git diff 7293fb4 1b01f80 \| sha256sum` = `c735410fa8eed626…` = the implementation receipt |
| Manifest | `kt_manifest.py verify PR-017-manifest.json --rev 1b01f80`: 21 files, mismatches `[]`, review input `95e5ccc861aa33fd…` |
| Files | 21 files, +2,061 / −21, as the receipt says |
| Where it ran | a detached worktree at `1b01f80` (focused tests, reviewer cases, mutants), then a worktree at the merge (`d41c439`, `d7a6dc4`: focused tests and the full suite) |
| Merge | `main` had moved 14 commits since `7293fb4`, FIX-033 among them (`deep_dive.py`, `discovery/__init__.py`, `base_orchestrator.py`, `schemas/discovery.py`, KT, CODEBASE). Three text conflicts, each resolved keeping both sides: `deep_dive.py` (FIX-033's `analyse(..., exact_symbol=True)` and its other-company check, called through PR-017's named `orchestrator` so the bare judge reads its bundle), `CODEBASE.md` (FIX-033's two rows, then PR-017's two new rows) and KT section 7's scorecard table (PR-017's "Every deep dive" row, then FIX-033's "By exit reason" row). One semantic conflict: the story's end-to-end test stubs `analyse(symbol, sector_question=None)`, which FIX-033's `exact_symbol` argument broke (the run's two dives failed inside the stub); the stub now passes keyword arguments through. `git diff 61b7305 d41c439`: the story's 21 files, +2,061 / −21 |

## Contract checked

**The card's defect, traced on the new code.** ABC dived on a Saturday at 0.62 BUY.
`run_discovery_cycle` → `run_deep_dives` (each dive's bundle into `evidence`, from
`orchestrator._last_bundle`, reset at the start of every run and set in `_run_unified`) →
`DiveRecord.append_run`, which on the first write seeds the file from the memo, the shelf events
and the shelf, then appends one `at_dive` row per dive and one run row naming the screen file →
`judge_bare` → `record_dives` (the memo is rewritten and pruned) → `apply_redives` (the shelf's
conviction is overwritten). The record already holds 0.62 before anything overwrites it. A
re-dive five weeks later at 0.80 appends `dive:<that day>|ABC` at 0.80; the first reference is
never rewritten (`dive_rows` keeps the first row per reference, an `at_dive` one before a
seeded one). Nightly, `grade_due` → `grade_idea_lanes` (default user only): entry at
`next_trading_day(dive day)`'s open from NSE's raw bhavcopy panel, the horizon close of
`trading_days_after(dive day, h)` put into the entry open's basis (`horizon_in_basis(...,
entry_on, entry_on)`, then `registry_break`), the Nifty from the close of the session before the
entry, one `AuditOutcome` per (reference, horizon), `correct` None.

**Every consumer of the store.** `report.build_report` drops the idea lanes from every advice
figure (hit rates, mean excess, the verdict, calibration, attribution) and builds the `ideas`
block from them alone; `thresholds.evaluate_breaches` reads only the report's advice fields; the
watchdog reads `build_report`; the scorecard's `idea_quality` reads lane `shelf` only and
`advice_grades` lane `advice` only (RV7); the scheduler counts rows. `AuditOutcomeStore.append`
leaves the five idea fields out of any row holding their defaults, so every other lane's line
keeps its keys and order (story test, old shelf line byte for byte).

**Issue time.** The entry session is strictly after the call's day on every row (story test). The
call's day is the scheduler's IST date (`BackgroundScheduler(timezone="Asia/Kolkata")`; the
Saturday job runs at 12:30 IST, 07:00 UTC, the same date in both zones, so a shelf event's IST
day matches the memo's date in the seed). A weekday catch-up dive enters at the next day's open.
The bare judge reads only the bundle its own dive built that day, and nothing is backfilled.

**Price identity and freshness.** Raw bhavcopy, the equity series first; a bonus or split ex
after the entry session and on or before the horizon bar multiplies the close (RV4: ex on the
horizon day itself); one ex on the entry day is already in the open (story test); a demerger in
NSE's list or a change only the instrument registry records leaves the horizon ungraded (story
test; RV2). The horizon day is recomputed every night from the current holiday list, so a
holiday NSE publishes later moves a not-yet-graded horizon rather than losing it.

**Idempotency and retries.** One row per (reference, horizon), the store's keys checked before
each write (story test: a second run writes no byte). A second run the same day keeps the first
answer (story test; RV5: one stock dived twice in one run). The bare judge skips a reference
already asked and counts every call, a failed one included, against 20 in any 7 days.

**Missing data.** No bar on the entry session: skipped and counted; a day file not yet in within
the panel's 7 retry days: `pending`; a basis no later read can establish: `no_exit_price`; the
Nifty failing: `skipped_unpriceable`, as in the other lanes.

## The implementer's decisions, weighed

1. **The Nifty from the close before the entry open.** Accepted. It is the same in every idea
   lane, so the comparisons between groups are not moved; the absolute excess carries one
   overnight move of the index per row, stated in the code and KT section 7.
2. **The seed runs by itself on the first Saturday after the deploy.** Accepted without the
   owner's word: it creates one new file from three the run already holds and changes none of
   them, it is not a migration of an existing record, and each Saturday's wait loses the memo's
   oldest week. `python -m core.discovery.dive_record` previews it read-only.
3. **The bare judge asks about new dives only, 20 a week, the analysis's model, the bundle less
   the dossier.** Matches the card and the owner's decision of 15 Nov. The bundle's sections are
   news, policy, macro, fundamentals, technicals, commodities, flows and peers; the dossier is
   the product's memory of the stock and is left out (story test).
4. **The new horizons as a key of their own** (`audit.idea_horizons_td`). Accepted: no advice,
   alert, shelf, switch or IPO reader changes.

## Adversarial examples, worked independently

Reviewer cases `analysis_data/pr017_review/test_review_cases_pr017.py` (8; seven committed as
`tests/unit/test_idea_lanes_pr017_review.py`), expected figures by hand:

| Case | Input | Expected and seen |
| --- | --- | --- |
| RV1 | a `redived` event "conviction 0.62 -> 0.80" on 4 Apr that the memo no longer holds | seeded at 0.80, source `shelf_event:redived` |
| RV2 | the registry records a relisting NSE's list does not show | no row at any horizon; 5 counted `no_exit_price` |
| RV3 | the Saturday run and a Monday catch-up both read Friday's screen | the candidate's call is Saturday's: `screen:2026-03-07|BBB`, entry Monday 9 Mar |
| RV4 | a 1:1 bonus ex on the 10-session day itself, close 55 | 110 in the entry's shares, +10% |
| RV5 | one stock re-dived and dived again in one run (0.66, then 0.71) | one reference, five rows at 0.66; the bare judge not asked |
| RV6 | the last run before the seed made no dive and pruned the memo | the seed still gives 7 Mar a run row though that day's unshelved dive is gone (L2) |
| RV7 | a dive graded +50% | the scorecard's shelf idea quality: 0 graded; advice grades: empty |
| RV8 | BUY at 0.55 and 0.5499, STRONG BUY at 0.60, INSUFFICIENT DATA | BUY dive, rejected, BUY dive, no group |

Also checked by reading: a Friday dive after the close enters at Monday's open; the memo's prune
(`_age <= 30` from the run's day) against the seed's covered days (newest memo day less 30);
the 45 bundles held in memory during a run are strings and small dicts, cleared after the judge.

## Tests and the original defect

The card's example is a fixture (`test_a_dive_keeps_its_own_conviction_whatever_redives_followed`):
reading the conviction from the shelf, as the shelf lane does, fails it. The implementer's 12
planted bugs were not re-run; 13 of the reviewer's own were, each alone, with bytecode writing
off (`PYTHONDONTWRITEBYTECODE=1`, caches cleared: a first pass reused a stale `.pyc` after a
same-size edit and was discarded):

| Mutant | Story tests | Reviewer cases |
| --- | --- | --- |
| M2 a screen's run day the latest covering run, not the earliest | pass | **fail** (RV3) |
| M8 the idea fields never written | fail | fail |
| M10 an abstained dive counted as rejected | fail | fail |
| M11 the seed takes a re-dive's old conviction | pass | **fail** (RV1) |
| M13 the registry break not checked | pass | **fail** (RV2) |
| M14 every bare answer a BUY | fail | pass |
| M15 coverage counting every reached dive as graded | fail | pass |
| M16 the seed's run rows without the memo window | fail | pass |
| M17 the shelf idea quality reading every lane | pass | **fail** (RV7) |
| M18 the shelf's floor exclusive | pass | **fail** (RV8) |
| M19 the basis counted from the call's day | fail | pass |
| M1 a zero excess counted as beating the Nifty | pass | pass |
| M12 a seeded row preferred to an `at_dive` row of the same reference | pass | pass |

11 of 13 caught with the reviewer's cases, 6 by the story's tests alone. M1 differs only at an
excess of exactly 0.0; M12 only when the first write's seed holds the same day and stock as the
run itself (a second run on the deploy's first day): both left as they are.

Mocked boundaries: the bare judge's call is injected (`call=`) or `bare_judge._call` is
patched; prices, the Nifty and NSE's lists are fixtures; the suite is hermetic (no `.env`, no
network). No real LLM, NSE or Yahoo call is made by any test.

## Findings

| # | Severity | Where | Finding | Disposition |
| --- | --- | --- | --- | --- |
| L1 | low (tests) | `tests/unit/test_idea_lanes_pr017.py` | Five invariants have no failing story test: the seed's re-dive conviction (M11), the registry break (M13), the earliest run day (M2), the shelf line kept to shelf rows (M17), the floor inclusive (M18). The code is right on each | Fixed: `tests/unit/test_idea_lanes_pr017_review.py` (`d7a6dc4`), RV1–RV5, RV7, RV8 |
| L2 | low | `core/discovery/dive_record.py` `_seed_runs` | The covered days start at the memo's newest day less 30; a run with no dive after it still prunes the memo from its own day, so a day just inside can get a run row whose unshelved dives are gone, and their screen candidates read "not dived" (RV6). One-time; needs a dive-less last run before the deploy | [BACKLOG](../BACKLOG.md) B-33, with L5 |
| L3 | low | `core/audit/idea_lanes.py` `grade_calls` with `exit_shadow.horizon_in_basis` | An empty NSE list, or one starting after the entry, is a lasting gap (FIX-018's fail-closed rule), so a stock NSE lists no action for, or a recent listing (PR-037's IPO dives), is never graded, in every lane alike. Counted in the dive coverage line and the nightly summary; how many is not measured | BACKLOG B-34 |
| L4 | low | `core/audit/idea_lanes.py` `screen_calls`, `core/audit/ideas.py` | "Screen only" includes candidates the run skipped because they were dived in the month before (shelved or rejected then), beside those the budget did not reach. The rows and the dive record keep what is needed to split them later, so nothing is lost by waiting | BACKLOG B-35; KT section 7 now says so |
| L5 | low (merge with FIX-033) | `dive_record.seed_rows` | The seed takes the shelf's `added` and `redived` convictions and the memo without FIX-033's check, so a dive that analysed another company (B-32's read: 1 of 20 active ideas, DEEPA) is seeded under the asked symbol; FIX-033 drops the idea and its memo entry, not its old events. Every `at_dive` row is clean (FIX-033 keeps no result of another company) | BACKLOG B-33, with L2 |

## Living documents

KT section 3 (records), section 7 ("Every deep dive graded", the report-families row, the
scorecard row) and section 8 (the dive record and the bare judge), CODEBASE and guide case 09-K
describe the reviewed behaviour. Added in this review: KT section 7 now names the empty or
late NSE list among the causes of an ungraded horizon (L3) and says "screen only" includes
candidates dived in the month before (L4); 09-K's status line. `check_kt_docs.py`: errors `[]`.
The PDF is not rebuilt with a story (AGENTS.md).

## Commands and results

Environment: code-server, `.stockai` Python 3.13.5, hermetic suite, detached worktrees in the
session's scratchpad.

```
git diff 7293fb4 1b01f80 | sha256sum
.stockai/bin/python scripts/docs/kt_manifest.py verify docs/planning/PI-2026-09/evidence/PR-017-manifest.json --rev 1b01f80
# at 1b01f80
python -m pytest -q tests/unit/test_idea_lanes_pr017.py tests/unit/audit          # 195 passed
python -m pytest -q --rootdir=. analysis_data/pr017_review/test_review_cases_pr017.py  # 8 passed
PYTHONDONTWRITEBYTECODE=1  # then each mutant alone against both files (table above)
# at d7a6dc4 (the merge and the reviewer's tests)
python -m pytest -q tests/unit/test_idea_lanes_pr017_review.py tests/unit/test_idea_lanes_pr017.py \
  tests/unit/audit tests/unit/test_misfiled_analysis_fix033.py tests/unit/test_discovery_deep_dive.py \
  tests/unit/test_discovery_cycle_ipo.py tests/unit/test_idea_supply_pr004.py       # 339 passed
python -m pytest -q                                                                  # full suite, below
python scripts/docs/check_kt_docs.py                                                 # errors []
```

**Full suite on `d7a6dc4`** (worktree): 6,994 passed, 8 skipped, 1 xfailed, 0 failed (3m44s).

Not exercised: a real discovery run, the seed against production's files, a real bare-model
call, NSE's live corporate-action lists, the nightly audit's run time with 200 list reads.

## Acceptance checklist

| Criterion | Verdict |
| --- | --- |
| The conviction on a `dive` row is that dive's own, whatever re-dives followed (the card's example) | met (story tests; RV1, RV5) |
| The entry bar is dated after the dive; a dive with no price is skipped and counted | met (story tests: entry, no entry price, coverage) |
| Idempotent per reference and horizon; old `shelf` rows byte for byte unchanged | met (story tests) |
| Every figure carries its n; under 30 "too few to judge" | met (story tests: 29 and 30) |
| Horizons 10/30/60/90/180; three-horizon readers checked | met (own key; advice readers unchanged; RV7) |
| Corporate actions as FIX-016 | met (story tests; RV2, RV4); the empty-list limit is B-34 |
| The report's four groups and the graph split; the scorecard line | met |
| The bare lane: 20 a week, new dives only, no dossier, not backfilled | met (story tests; RV5) |
| Backfill as far as the stored dives and screens go | met, with B-33's two known gaps |
| Living documents: KT section 7, the testing guide | met |

## Production

**Pushed and deployed** by this session: `61b7305..b9578e5` at 02:40 IST Mon 23 Nov, inside the
window, after the full suite on `b9578e5` (a first run: 1 failed, the member browser suite's
subtest 8 "every member screen says unavailable when its API fails", a watchlist message not yet
drawn under load (BACKLOG B-36); it passed alone in 72 s, no frontend file changed since `aeb38b9`; the rerun:
6,997 passed, 5 skipped, 1 xfailed, 0 failed, 8m48s). Railway `5f69280a` SUCCESS on `b9578e5`,
`53352126` removed; `/health` 200 at 02:41 IST. Tonight's 23:45 audit is the first to run the
idea lanes: only the stored screen files can be graded before the first Saturday run (as
"dived unknown"). **`PR-017-W1`**
(STATE `pending_production_checks`) reads the first Saturday discovery run and that night's
audit, as the implementation receipt's "Production watch" proposes, plus two lines for B-33: the
last discovery run before the deploy made dives, and no seeded dive names a stock that run's
`hygiene.analyses.dropped` or `hygiene.other_company` lists.

## Decision

**ACCEPTED** for `1b01f80` (diff `c735410f`, manifest `95e5ccc8`). Status `done`; merged into
`main` as `d41c439` (FIX-033's conflicts kept both sides; the end-to-end test's stub takes
`exact_symbol`), the reviewer's tests `d7a6dc4`; deployed with `b9578e5`.
`production_verification`: `pending_observation`. BACKLOG B-33, B-34, B-35. Next: PR-015's switch in the 04:00–06:20 window,
else PR-047 (option A).

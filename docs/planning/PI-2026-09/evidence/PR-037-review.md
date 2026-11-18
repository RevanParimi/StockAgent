# PR-037 — fresh review receipt

**Story:** [PR-037](../stories/PR-037.md): enough analysed ideas to hold 25 to 30 stocks.
Implementation receipt: [PR-037-implementation.md](PR-037-implementation.md).

**Review context: fresh session.** Autopilot session `1118-0834-p4` on the code-server, a new
conversation opened with "continue", Wednesday 18 Nov 2026 from about 08:34 IST, outside a push
window. The implementing session (`1118-0807-p3`) had ended. `origin/main` was `6e1962f` after a
fetch; `main` was `34aa51d`, 7 ahead (records and the accepted PR-036 and PR-039). Production was
not read. No LLM was called, nothing was pushed, deployed, run or sent.

**Lane:** decision path, confirmed. How the week's analyst calls are shared decides which
companies are analysed, and the shelf's size and sector cap decide which BUY ideas the autopilot
may buy.

**Verdict: ACCEPTED** for `d6e5777`. No critical, high or medium finding. One low observation
(R1) goes to the backlog as B-15. The accepted revision stays on `story/PR-037`, not merged into
`main`: merging would ship it with tonight's push, and the card puts its rollout at the owner's
word (the precedent is PR-015's branch).

## Review input, verified

| Check | Result |
| --- | --- |
| Branch | `story/PR-037` = `d6e5777`, one commit on `3a59155` (`git merge-base main story/PR-037`) |
| Diff digest | `git diff 3a59155..d6e5777 \| sha256sum` = `d24636e5197168de…` = the receipt |
| Files | the receipt's 13 paths, +529 / −47 (`git diff --stat`) |
| Where it ran | a detached worktree of `d6e5777` in the scratchpad; a probe test confirmed `core.discovery` and the settings module were imported from it, not from the checkout |
| Merge | `git merge-tree main story/PR-037`: clean |

## Contract checked

The card's four steps, its acceptance lines and its out-of-scope list; the receipt's split, its
"found while building" fix and the four points it asks a reviewer to weigh. I traced the week's
calls from `run_discovery_cycle` through `budget_split`, `run_deep_dives`, `record_dives`,
`apply_redives`, `apply_deep_dives` and `rotate_stale` to `shelf.json`, and searched for every
other reader of the five settings and of the result's `hygiene` and `budget`.

- **The bound.** `run_deep_dives` adds a symbol to `attempted` before its call and every path to a
  call passes `spent` (`len(attempted) >= limit`) first; a held-back re-dive examined again past
  the budget reaches `if spent: continue`. A failed call counts (RV4).
- **The floor.** The room is `calls − this week's IPO candidates − new_dive_floor`, never below 0
  (28 of 45 with two). Re-dives in the list's order take calls only while `redive_calls` is under
  the room, so the IPO candidates and at least the floor's screen ranks follow before any re-dive
  past it, which returns once, after the last candidate. A held stock's idea, a symbol without a
  close and a non-company make no call and take no room.
- **Nothing lost.** A re-dive with no call stays due: `redive_due` reads the idea's dive date,
  which only a dive changes. It is named in `hygiene.redive_deferred`; the least overdue are the
  ones deferred, and the 60-day rotation is 30 days past the re-dive age, so a deferred idea needs
  four deferrals in a row to rotate out.
- **The shelf.** Unchanged code (`apply_deep_dives`, `_enforce_sector_cap`) with 45 and 6: a new
  idea only from its own dive at 0.55 or more with a BUY verdict; a newcomer to a full sector key
  or a full shelf replaces the weakest only when stronger. The 0.55 floor, the screen's signals,
  the analyst's prompt and sizing are untouched (the card's out of scope).
- **Other readers.** The settings are read only by the screen (120, 60), the deep dive and the
  shelf (45, 6). Nothing outside `run_discovery_cycle` reads `hygiene` or `budget`; the whole
  result is logged once ("weekly cycle complete"), which is what `PR-037-W2` reads. The shelf's
  readers (buy candidates and SWITCH in `core/portfolio/pipeline.py`, the brief, the weekly
  digest, the watchdog's `sector_keys`, the events feed) take any number of ideas; the events
  feed's 90 (PR-036) covers 30 holdings and 45 ideas.
- **Compatibility.** `run_deep_dives`'s new arguments are keywords with defaults; the only
  production caller is the cycle. `base.py`'s fallback 0 for the floor restores the old split on
  a rollback of `config.yaml`.
- **Issue time.** No clock is read in the change. A catch-up dive keeps its day: a dive dated
  Thursday counts as made at Thursday's close, so Friday's close prices it first (RV5), and the run
  that reviews Friday's close is Monday's, as the implementation receipt's rollout step says.
- **Retry.** A second run the same day re-dives nothing just dived (fresh) and dives no company in
  the 30-day memo; RV3 shows the catch-up run followed by Saturday diving no stock twice.

## Independent cases

Reviewer cases written from the card and FIX-024's rule, with every expected list worked by hand
in its docstring: `analysis_data/pr037_review/test_rv_pr037.py` (an ignored folder; on another
device, write them from this list). They use the PR-004 fixtures that predate the change and set
the shipped values by hand. Copied into the worktree's `tests/unit` to run, then removed.

- **RV1, the screen ranks a deferred idea's stock.** 30 due, room 28; the screen ranks T00 first.
  The screen's T00 is skipped as already shelved, T01 and T00 are called once each, late, after
  the 2 IPOs and 5 new companies: 37 calls. **Pass.**
- **RV2, an IPO candidate that is not a company.** The room stays 28; IPO0 takes 1; the screen
  takes 16; T01 and T00 are deferred. **Pass.**
- **RV3, the catch-up run then Saturday.** Thursday: 8 re-dives, 2 IPOs, 35 new (45). Saturday:
  only S35-S59 (25 calls), none a repeat of Thursday's. **Pass.**
- **RV4, a failed re-dive.** It counts in the budget and the room, is not "deferred", keeps its old
  dive and is the first re-dive a week later. **Pass.** (A first draft failed the idea at 60 days;
  it then rotates out by the 60-day rule that predates this change: a fixture error, corrected.)
- **RV5, the catch-up dive's first price.** `close_before_decision` refuses Thursday 19 Nov's
  close for a dive of that day and accepts Friday 20 Nov's. **Pass.**
- **RV6, observation R1.** Both IPO candidates in the 30-day memo: the room stays 28 though they
  make no call; T01 and T00 wait while the screen takes 17. **Pass** (it pins today's behaviour).

**Reviewer mutants**, each applied alone to `d6e5777` and run against the new file, PR-004's,
FIX-025's and the deep-dive tests (different from the implementer's eight):

| Mutant | Result |
| --- | --- |
| R1 the old loop: `break` at the budget | caught |
| R2 IPO slots reserved when there are no IPO candidates | caught |
| R3 a late-called re-dive also reported deferred | caught |
| R4 re-dives within the room reported as late | caught |
| R5 a held-back re-dive counted as attempted (never called late) | caught |
| R6 the room one larger | caught |
| R7 late and deferred swapped in `hygiene` | caught |
| R9 every call counted as a re-dive call | caught |
| R10 a late re-dive called past the budget | caught |

**9 of 9 caught.** The new file's expected values are worked by hand or decided by the fixture
when it builds each symbol (the property test), not taken from `budget_split`; the analyst is a
stub, the screen, listing, IPO cache, sales and paper reviews are faked, and `tests/hermetic.py`
blocks every transport. No mocked boundary reaches a real API, SMTP or push.

## Findings

| # | Severity | Where | Finding | Disposition |
| --- | --- | --- | --- | --- |
| R1 | Low (latent; carried over from PR-004) | `core/discovery/__init__.py:125`, `budget_split(len(ipo_cands))` before the memo filter at `:169` | The room subtracts this week's IPO candidates before the 30-day memo removes those dived lately, so an IPO candidate that makes no call still narrows the re-dives' room; its call goes to the screen. In a week with more re-dives due than the room, up to 2 re-dives wait a week that would otherwise be made. Example: 30 due, both IPOs dived 9 days ago: 28 re-dives and 17 new companies, T01 and T00 deferred, against 30 and 15 counted after the memo (RV6). No idea is lost (it is first the next week) | BACKLOG **B-15**, with its trigger |

No other finding. The implementer's four points: (1) the floor's 15 is provisional, as the card
says, and `PR-037-W2` reads it; (2) `hygiene.redive` now names the re-dives offered within the
room, called or skipped by rule: no code reads it; (3) past the budget the loop examines only
re-dives, a few dataframe filters; (4) a held stock's idea is still listed under `hygiene.redive`
without a dive, as since FIX-025. None is a defect.

## Commands and results

Environment: code-server, Python 3.13.5 (`.stockai`), run from the detached worktree of
`d6e5777` (a symlink to the checkout's `node_modules` for the two frontend files, removed after).

- Focused, the new file and the 12 files that run the cycle, `run_deep_dives`, the shelf or the
  discovery route: **363 passed** (27 s).
- Reviewer cases: **6 passed**.
- Reviewer mutants: **9 of 9 caught**.
- Full suite on `d6e5777`: `.stockai/bin/python -m pytest -q -p no:cacheprovider` →
  **6,820 passed / 12 skipped / 1 xfailed / 0 failed**, return code 0, 6m12s (about 08:41-08:47 IST; the real-browser file included, through a symlink to the checkout's `node_modules`).
- `scripts/docs/check_kt_docs.py`: errors `[]`. `scripts/ci/check_broad_except.py`: OK (148
  grandfathered).

Not exercised: a real analyst, NSE or the production shelf; the Saturday job's run time at 45
dives and 45 paper reviews (the receipt's estimate, about 14:00-14:30 IST, is an inference from
PR-035's medians); the screen's yield of new companies past the memo at 60 candidates (no screen
file was read). `PR-037-W2` measures these.

## Documentation

KT section 8 (the shelf's purpose, steps 4 to 7, the screen's 120 and 60) and section 11,
PRODUCT_MAP, CODEBASE and the testing guide (06-E, 06-K, new 06-Q) describe the reviewed
behaviour. The PDF is not regenerated with a story (AGENTS.md, owner's rule of 17 Nov), which
the card's "the PDF is regenerated" yields to.

## Acceptance

| Criterion | State |
| --- | --- |
| Settings and the budget split in place with the card's tests; full suite and guards pass | Met |
| A fresh-session review accepts it | **Met: this review** |
| The receipt states the weekly and monthly cost, measured unit cost × count | Met (implementation receipt) |
| The shelf's expected size after two Saturdays from the measured yield | Met (an inference, its assumptions stated) |
| KT section 8, PRODUCT_MAP and the testing guide describe the wider path | Met; the PDF waits (above) |
| Rollout at the owner's word, then the catch-up run; a dated check row | `PR-037-W2` in STATE; the push and the run wait for the owner's word |

## Decision and follow-up

**Accepted:** `d6e5777` on `story/PR-037`, digest `d24636e5…`. STATE: `done`, production
verification `pending_deployment`. The branch merges into `main` only on the owner's word for the
rollout (the question is in HANDOFF "Waits for you"): then a session in a push window merges it,
runs the full suite on the exact commit, pushes, checks the deploy and `/health`, and the catch-up
run follows on a weekday 09:30-14:00 IST, at the same word. A run on a Monday to Wednesday is
first priced a session sooner than one on a Thursday (RV5 and the review's day-after rule).

Noted for the night session, outside this story: since this morning's docs commits,
`story/PR-015` no longer merges cleanly into `main`: one conflict in `docs/TECHNICAL_DESIGN.md`,
section 11's table, where `main` rewrote the "Idle cash" row and PR-015 adds an "Exit rule" row
under it. The resolution keeps both rows. `story/PR-037` merges cleanly on `main` and on `main`
with PR-015 merged.

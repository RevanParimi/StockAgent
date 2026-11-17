# FIX-015 — implementation receipt

**Story:** [FIX-015](../stories/FIX-015.md): the shock exit reads the re-forecast's trigger, not its
sentence. Routed from PR-009's implementation (2026-10-23, code inspection).

**Profit-path step:** sell. `shock_reforecast` is an EXIT trigger, the same code under both exit
rules; it has never fired.

**Lane:** decision path. The story changes when a holding is sold. So implementation and
self-review stop at `review_required`, and a fresh conversation does the hard review from
[REVIEW.md](../REVIEW.md).

**Phase:** implementation, Tuesday 17 Nov 2026 from about 23:44 IST. Autopilot session
`1117-2344-p3` on the code-server, a fresh conversation opened with "continue". `origin/main` was
`d2f45cd`; `main` was `64b3cbb`, 2 ahead (docs, not pushed). The code is on the branch
`story/FIX-015` (owner's code-server rule: decision-path work stays on its branch until its fresh
review accepts it). This phase includes a same-conversation self-review, which is not the fresh
review.

**Status after this phase:** `review_required`. The branch is committed and not pushed; `main`
holds only this receipt, STATE and HANDOFF. Nothing is deployed or configured. Production was not
read. No LLM was called and no message was sent. No test reaches the network (`tests/hermetic.py`).

## In one example

MARUTI is held at ₹1,000 and closes at ₹1,000 every session. Tuesday 16:45, the daily review of
Monday classifies Monday's miss as an external shock and re-forecasts a path ending at ₹900.

- **Before:** the event stores `reason="External shock on 2026-06-08: actual direction …"` and
  `trigger="external_shock"`. The advisor compared the sentence with `"external_shock"`: never
  equal, so no decision ever sold on it.
- **Now:** the advisor reads `trigger`. Monday's and Tuesday's decisions cannot read the
  re-forecast (it was made after their closes, FIX-027). Wednesday's and Thursday's read
  `external_shock` with a −10% path: EXIT with `shock_reforecast`, under either exit rule.
  Friday's does not, though the path is unchanged: the shock counts at the first two closes after
  it was made.

## What changed

- **The advisor** ([advisor.py](../../../../core/portfolio/advisor.py)):
  - `recent_reforecast_trigger(env, review_date)`: the latest re-forecast's `trigger` when it was
    made at or after the close of the session two sessions before the review day; `""` otherwise,
    and `""` for an event with no time or an unreadable one. `env` is the envelope as it stood at
    the close (`envelope_at_close`), so a re-forecast made at or after that close is never in it.
  - `build_signals` sets `AdvisorSignals.reforecast_reason` from it (was: the latest event's
    `reason`, whenever it happened).
  - `decide`: `shock_reforecast` fires for `SHOCK_TRIGGERS` = `external_shock`, `preopen_shock`
    with a falling path (was: `external_shock`, `thesis_break`, `preopen_shock`). One line, outside
    the branch on `exit_rule`, so both rules keep the same code.
  - `envelope_at_close`'s note names the trigger and the time (FIX-027's review, L1): "the
    external_shock re-forecast of 2026-06-09T16:45:00+05:30 is after the close of 2026-06-08"
    (was: the event's sentence in the middle).
- **The schema comment** ([feedback.py](../../../../src/backend/shared/schemas/feedback.py),
  `ReforecastEvent`): it said `reason` holds the key and `trigger` free text, the opposite of
  every writer. Now `reason` is "a sentence for people", `trigger` "the key code reads", and
  `date` says which session the daily review dates it.
- **Docs:** KT section 6, a new paragraph "The shock exit" (the rule, the two keys, why
  `thesis_break` does not count, the window and its worked example); the limit "never fires …
  Planned: FIX-015" is gone; the late note's example; section 11's "once the shock exit reads the
  re-forecast's trigger (FIX-015)" dropped from PR-015's line. The guide's new case 07-S and
  HT-07's related list. No PDF (AGENTS.md: built only on the owner's request or with SA-031).
- **A test changed:** `test_envelope_after_close_fix027.py::test_old_envelopes_without_a_time_…`
  built its event with the key in `reason`, which no writer does, and asserted the advisor read it.
  It now builds the writers' shape and asserts the path is read as before (UP, ADD) and the trigger
  is not (an event with no time is not shown to be recent). PR-009's file is unchanged.

## Decisions (delegated technical calls; the owner delegated routing and technical calls on 13 Oct)

- **F15-D1: the window is counted from when the re-forecast was made (`at`), not from its `date`.**
  The card proposed "one dated the review day or the session before it". The daily review that
  runs on day D+1 reviews D (`run_schedule.cmd_daily_review`: yesterday), dates its re-forecast D,
  and makes it at about 16:45 on D+1, after D+1's close. The advisor's decision for D+1 may not
  read it (FIX-027), so the first decision that can is D+2's, and D is not "the review day or the
  session before it" for D+2. On the date, a daily-review shock would never fire: the card's
  window, tried as a mutant, fails 16 of the story's tests. On `at`, every shock re-forecast gets
  the first two closes after it was made: Wednesday's and Thursday's for Tuesday 16:45, Tuesday's
  and Wednesday's for a pre-open check at Tuesday 08:45. This answers the hard review's "is the
  re-forecast's date the one used, not the run's?": the re-forecast's own time is used, never the
  day the advisor runs.
- **F15-D2: two closes** (`SHOCK_REFORECAST_CLOSES = 2`), matching the card's two sessions. One
  close would give the daily review's shock a single decision; a longer window lets a stale shock
  sell on a later drift. A constant in the advisor, not a setting.
- **F15-D3: only the latest re-forecast is read.** A later re-forecast of any kind replaces the
  shock's path, so the falling path is no longer the shock's: a manual re-forecast at Wednesday
  11:00 after Tuesday's shock holds both days (test). This keeps the old "latest event" reading.
- **F15-D4: an event with no time never counts.** Every such event was stored before FIX-027's
  deploy (10 Nov about 13:20 IST, per its STATE record) and cannot be shown to be recent. Nothing
  is lost: more than two closes have passed since, so none would be in its window now.
- **F15-D5: the field keeps its name, `reforecast_reason`, and now holds the trigger key.** PR-009's
  property test builds `AdvisorSignals(reforecast_reason="external_shock", …)`, and the card asks
  for it unchanged. Pydantic ignores an unknown keyword, so a rename would leave that test passing
  while it silently stopped exercising the shock trigger. The field's comment says it is the key,
  never the sentence. The `ticker_verdicts.reforecast_reason` column (Atlas) has no writer; it is
  untouched.
- **F15-D6: `regime_flip` does not count.** Its own exit is `crisis_regime_bearish` (MACRO_CRISIS
  with a falling path); counting it here would sell on the same condition twice under a different
  name. `manual` is an operator's tool, not news.

## Tests

Every expected value is worked from the test's own fixture, never read back from the code. No test
reaches the network.

- **Story file** `tests/unit/test_shock_reforecast_fix015.py`, 42 tests, all pass. Real envelope
  files written as `regenerate_envelope` leaves them (archive, new path, event), read through the
  real `build_signals`, decided under both rules (`decide`, legacy and evidence):
  - **Each writer's real event** (the daily review's `external_shock`, `thesis_break` and
    `regime_flip` sentences, the pre-open check's, the manual command's) at the first close after
    it, with a −10% path and a 0.0% path: only `external_shock` and `preopen_shock` with the −10%
    path EXIT, with `shock_reforecast` alone.
  - **The window:** the daily review's shock HOLDs Monday and Tuesday, EXITs Wednesday and
    Thursday, HOLDs Friday and the next Monday; the pre-open shock HOLDs Monday, EXITs Tuesday and
    Wednesday, HOLDs Thursday. An event without a time never counts.
  - **Only the latest:** a manual re-forecast after the shock holds.
  - **The hard review's route:** a thesis-break re-forecast with the thesis not intact and a −10%
    path: legacy EXITs with `thesis_break` alone; the evidence rule HOLDs.
  - **The late note** names the trigger and the time, and reads "the re-forecast of …" with no
    trigger.
  - **The real writer:** `regenerate_envelope` (FIX-027's harness, pipeline stubbed) run Tuesday
    16:45 for Monday stores `reason="shock"`, `trigger="external_shock"`, `date` Monday; the
    advisor reads the key at Wednesday's and Thursday's closes only.
  - **Invariant** (30 seeds): a random trigger made at a random minute from Fri 5 to Wed 17 Jun (a
    third at a close or a minute either side), dated that day, the day before or three days
    before, with a −10% path. Over ten sessions `shock_reforecast` fires under both rules alike and
    exactly at the sessions found by walking the calendar a day at a time for the first two 15:30
    closes strictly after it, and only for a shock. (14 seeds draw a shock, 6 of them at a close.)
- **Mutants** (each restored afterwards): the code on `main` fails 25 of the 42; counting
  `thesis_break` fails 6; one close instead of two fails 18; the card's date window fails 16.
- **Unchanged and passing:** `tests/unit/test_exit_evidence_pr009.py` (its 4,000-case property
  test), `tests/unit/test_issue_time_fix031.py`, and `test_envelope_after_close_fix027.py` with the
  one test above changed: 213 passed together with the story file.
- **Full suite** on the branch's tree (the six files as committed), 17 Nov 23:54-00:00 IST:
  6,791 passed / 12 skipped / 1 xfailed / 0 failed, 6m13s (6,749 before, plus the 42 new).
- **Guards:** `scripts/docs/check_kt_docs.py`: no errors. `scripts/ci/check_broad_except.py`: OK
  (148 grandfathered); the change adds no `except`.

## Rollout (what deploying changes)

- **The first sales this trigger can make.** With `advisor.exit_rule: shadow` (production), the
  price-path rule acts, and `shock_reforecast` is in both rules, so a held stock whose latest
  re-forecast is a recent shock with a falling path is sold at that close. How often is not known:
  production was not read. Re-forecasts are capped per stock per month
  (`RL_REFORECAST_MAX_PER_MONTH`), and the daily review re-forecasts only on a wrong-direction day
  classified `external_shock`; the pre-open check only when an overnight shock contradicts the
  forecast.
- **Proposed watch, for the reviewer to add on acceptance:** in the first two weeks after the
  deploy, count the advice records with `shock_reforecast` and, for each, the re-forecast it read
  (trigger, time) and the close it sold at. A read-only probe; it runs at the owner's word.
- **The late note's text** changes in new records only; old records keep their sentence.

## Hard review (the card's questions, answered)

1. **Does any route let a price-path miss sell through this trigger under the evidence rule?** No.
   The trigger fires only for `external_shock` or `preopen_shock`; the daily review writes
   `thesis_break` for a thesis break and `regime_flip` for a flip into crisis, and the price-path
   miss itself is the `thesis_break` trigger, inside the `exit_rule` branch. A thesis-break
   re-forecast with the thesis not intact and a falling path holds under the evidence rule (test).
   One route remains, by design: the daily review classifies a wrong-direction day as
   `external_shock` only when the FeedbackAgent says so; that classification is the review's, and
   the shock path then sells under both rules. A misclassified ordinary miss would sell here.
2. **Is the re-forecast's date the one used, not the run's?** The re-forecast's own time (`at`),
   never the advisor run's day; not its `date` field, for the reason in F15-D1.

## Not covered / found on the way

- **A shock on the last session of a month** is not re-forecast at all: the review of 30 June runs
  on 1 July, and the daily review re-forecasts only the live cycle. And the pre-open check at 08:45
  on the 1st finds no envelope yet (the monthly forecast runs at 09:00), so it re-forecasts
  nothing. Pre-existing, low, changes no sale today beyond "a shock that day cannot sell through
  this trigger". Not routed; noted here for the reviewer.
- **The FeedbackAgent's `external_shock` classification is now a sale input.** Before, it only
  chose the re-forecast. A miss classified as a shock that was not one now sells if the new path
  falls. The proposed watch above shows how often.

## Review input

- **Branch** `story/FIX-015`, one commit, `b159073`, on `main`'s `64b3cbb`.
- **Manifest:** [FIX-015-manifest.json](FIX-015-manifest.json), SHA-256
  `85ef1b57eb3ab9892c044234417ef15d7d7ca52d5d4879b377361dac075a363b`, 6 files, written with
  `scripts/docs/kt_manifest.py write` from the committed tree; verify on the branch with
  `python scripts/docs/kt_manifest.py verify docs/planning/PI-2026-09/evidence/FIX-015-manifest.json --rev story/FIX-015`.
- **Diff:** `git diff main...story/FIX-015` (6 paths: `core/portfolio/advisor.py`,
  `src/backend/shared/schemas/feedback.py`, `tests/unit/test_shock_reforecast_fix015.py`,
  `tests/unit/test_envelope_after_close_fix027.py`, `docs/TECHNICAL_DESIGN.md`,
  `docs/TEAM_TESTING_GUIDE.md`).
- **Outside the branch** (on `main`): this receipt, the manifest, STATE, HANDOFF.
- Run the review's tests in a detached worktree of the branch.

## What a fresh review should press on

1. F15-D1: is counting from `at` right, against the card's proposed date window? Is two closes the
   right length?
2. F15-D5: is keeping the field name `reforecast_reason` acceptable, or should it be renamed with
   PR-009's test adjusted?
3. Hard review 1's remaining route: is a FeedbackAgent `external_shock` classification a sound
   enough input to sell on, given the cap and the falling-path condition?
4. Should the proposed two-week watch be a STATE row before the push?

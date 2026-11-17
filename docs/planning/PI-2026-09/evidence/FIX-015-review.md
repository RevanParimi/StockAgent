# FIX-015 — fresh review receipt

**Story:** [FIX-015](../stories/FIX-015.md): the shock exit reads the re-forecast's trigger, not
its sentence. Implementation receipt: [FIX-015-implementation.md](FIX-015-implementation.md).

**Review context: fresh session.** Autopilot session `1118-0002-p4` on the code-server, a new
conversation opened with "continue", Wednesday 18 Nov 2026 from about 00:02 IST. The implementing
session (`1117-2344-p3`) had ended. `origin/main` was `d2f45cd` after a fetch; `main` was
`1c9be93`, 3 ahead (docs). Production was not read. No LLM was called and no message was sent.

**Lane:** decision path, confirmed. The story changes when a holding is sold.

**Verdict: ACCEPTED.** No critical, high or medium finding. One low, pre-existing finding (R1)
goes to the backlog as B-10. The reviewed revision `b159073` is merged into `main` as `2e10c9c`
(a merge commit, so the reviewed commit is kept as it was).

## Review input, verified

| Check | Result |
| --- | --- |
| Branch | `story/FIX-015` = `b159073`, one commit on `64b3cbb` (`git merge-base`) |
| Manifest SHA-256 | `85ef1b57…a363b` = receipt |
| `kt_manifest.py verify … --rev story/FIX-015` | 6 files, 0 mismatches |
| `git diff main...story/FIX-015 --stat` | the receipt's 6 paths, +416 / −21 |
| After the merge | the 6 files at `2e10c9c` are identical to `b159073`'s; `verify --rev HEAD`: 6 files, 0 mismatches |

## Contract checked

The card's four intended results, its four acceptance lines and its two hard-review questions;
the receipt's decisions F15-D1 to F15-D6 and its four questions. I traced every writer of a
re-forecast to the stored event, then through `envelope_at_close` and `build_signals` to `decide`
under both exit rules, and searched for every other reader of the field and the trigger name.

- **The writers** (`regenerate_envelope` is the only place an event is built): the daily review
  (`daily_review.py:1515-1549`) passes `trigger` `external_shock`, `thesis_break` or
  `regime_flip` with a sentence as `reason`, and `review_date` = the reviewed session, which
  `run_schedule.cmd_daily_review` sets to yesterday; the pre-open check (`preopen_check.py:279`)
  passes `preopen_shock` with "pre-open shock: <headline>"; the manual command passes `manual`.
  The event's `at` is `now_ist()` taken after the new path is built (`generate_forecast.py:792`),
  so it is when the path existed, never earlier.
- **Other readers:** the narrator's sentence for `shock_reforecast` and `advisor.py:537`'s label
  (unchanged and still right); `core/audit/attribution.SHOCK_REASONS` is the same two keys (no
  production caller); the `ticker_verdicts.reforecast_reason` column has no writer
  (`publish_projection` is called only by tests). Nothing displays the old sentence.
- **Issue time:** the window is anchored on the decision's `review_date` and the event's own `at`;
  no `date.today()` or clock is read, so a retried run for a past day decides as it did.

## Independent cases

Reviewer cases written from the card and the NSE calendar, not from the code:
`analysis_data/fix015/test_review_cases.py` (an ignored folder; on another device, write them from
this list). They run against the branch's real envelope files, `build_signals` and `decide` under
both rules (asserted equal). Expected values were worked by hand:

- **RV1, a holiday inside the window.** Holi, Tue 3 Mar 2026, is closed. The review of Fri 27 Feb
  runs Mon 2 Mar and re-forecasts at 16:45. The first two closes after it are Wed 4 and Thu 5:
  EXIT on those, HOLD on Mon 2, Fri 6 and Mon 9. **Pass.**
- **RV2, the same instant written in UTC** (`11:15+00:00`): the same two sessions. **Pass.**
- **RV3, a pre-open shock across the holiday** (Mon 2 Mar 08:45): EXIT on Mon 2 and Wed 4 only.
  **Pass.**
- **RV4, two shocks in a day:** a pre-open shock Wed 4 08:45, then the review's external shock at
  16:45. Wed reads `preopen_shock` (the 16:45 one is after its close); Thu and Fri read
  `external_shock`; Mon 9 reads none. **Pass.**
- **RV5, a month's end** (finding R1): below. **Pass**, showing the gap.

**Mutants of my own** (each restored; story file plus RV1-RV4, 46 tests): `>` for `>=` at the
window's start, 3 fail; the window on the event's `date`, 18 fail; `date.today()` for
`review_date`, 27 fail; three closes, 20 fail; calendar days for sessions, 7 fail. The story file
against `main`'s old `advisor.py`: 25 of 42 fail, as the receipt says.

## The implementer's decisions

- **F15-D1, the window counts from `at`: agreed.** Confirmed in the code: the daily review dates
  its event with the reviewed session (yesterday) and runs after the next session's close, so the
  card's "dated the review day or the session before" never reaches a daily-review shock (the
  mutant fails 18). Counting from `at` is also the stricter issue-time reading: the path counts
  only from the first close after it existed.
- **F15-D2, two closes: agreed.** It gives a daily-review shock the same two decisions a
  pre-open shock gets. If the first sale cannot execute, the second close retries it.
- **F15-D3, only the latest: agreed.** A later re-forecast replaces the path the shock drew, so the
  falling path is no longer the shock's. RV4 shows the case of two shocks.
- **F15-D4, no time, no count: agreed.** Such events predate FIX-027 (10 Nov) and are past any
  two-close window now.
- **F15-D5, the field keeps its name: agreed.** A rename would let PR-009's property test pass
  while silently no longer reaching the shock trigger (an unknown keyword is ignored). The field's
  comment says it holds the key.
- **F15-D6, `regime_flip` and `manual` do not count: agreed.** The crisis exit covers the flip on
  the same falling path; counting it here would name one sale twice.

## The card's and the receipt's questions

1. **Can a price-path miss sell through this trigger under the evidence rule?** Not through
   `thesis_break`: the set has two keys, the story test sells legacy on `thesis_break` alone and
   holds under the evidence rule, and the mutant that counts it fails. The one remaining route is
   by design: a wrong-direction day the FeedbackAgent classifies `external_shock`. PR-009's card
   keeps `shock_reforecast` "unchanged" in the evidence rule, so this is the owner's rule working
   as written, not a leak. It is bounded three ways: the prompt reserves `external_shock` for black
   swans; the daily review overrides it to `direction_flip` once more than 20% of the cycle's
   prior days (5 or more) were shocks (`daily_review.py:1198`); and re-forecasts are capped at 2 a
   stock a month. The watch below counts how often it sells.
2. **Is the re-forecast's date used, not the run's?** Neither: the re-forecast's own time `at`,
   against the decision's session (F15-D1). The run's day is never read.
3. **Should the two-week watch be a STATE row before the push?** Yes: `FIX-015-W1`, added with
   this review. It rides on `PR-014-D1`'s door read (from Tue 1 Dec), so it costs the owner no
   extra probe.

## Findings

| # | Severity | Where | Trigger, observed against expected | Impact | Disposition |
| --- | --- | --- | --- | --- | --- |
| R1 | Low, pre-existing (the envelope is per month), latent | `advisor.build_signals` reads `store.cycle_id_for(review_date)`; `daily_review.py:1510` re-forecasts only the live cycle | The review of a month's second-to-last session runs on its last session at 16:45 and re-forecasts that month's envelope. Its two closes are the next month's first two sessions, whose decisions read the new month's envelope (no history). Example: the review of Mon 29 Jun runs Tue 30 Jun 16:45; Wed 1 and Thu 2 Jul HOLD with a −10% July path too (RV5). The review of the last session runs on the 1st and re-forecasts nothing (the implementer's note). A pre-open shock on the last session counts once, not twice | A shock found in a month's last two sessions cannot sell through this trigger; the stop, the trailing stop and the crisis exit still act, and the new month's forecast is drawn fresh at 09:00 on the 1st | [BACKLOG](../BACKLOG.md) B-10 |

Observation, not a finding: `SHOCK_TRIGGERS` (advisor) and `SHOCK_REASONS` (attribution) now hold
the same two keys and agree; attribution's comment says so. Nothing to change.

## Documentation

KT section 6 states the rule, the two keys, why `thesis_break` does not count, the window and a
worked example, and its limit "never fires … Planned: FIX-015" is gone; the late note's example
and section 11's PR-015 line are updated. The guide's 07-S checks one shock and one thesis-break
re-forecast; HT-07 lists FIX-015. I read both against the code: they match. No PDF, per AGENTS.md
(built only at the owner's request or with SA-031).

## Commands and results

All in a detached worktree of `b159073` (`git worktree add --detach`), with `.stockai/bin/python`
(Python 3.13.5), except the full suite.

- `pytest tests/unit/test_shock_reforecast_fix015.py tests/unit/test_exit_evidence_pr009.py
  tests/unit/test_envelope_after_close_fix027.py tests/unit/test_issue_time_fix031.py`: **213
  passed** (= receipt). `test_exit_evidence_pr009.py` unchanged by the branch (`git diff --quiet`).
- Reviewer cases RV1-RV5: **5 passed**.
- `scripts/docs/check_kt_docs.py`: `errors: []`. `scripts/ci/check_broad_except.py`: OK (148
  grandfathered).
- **Full suite** on the merge `2e10c9c`, 18 Nov 00:12-00:19 IST, in the machine's zone: 6,789
  passed / 12 skipped / 1 xfailed / **2 failed**. Both failures are older than FIX-015 (the same
  test fails on `1c9be93`) and depend on the clock: two re-forecast tests took the machine's date
  (UTC here) against the code's IST date, which differ from 00:00 to 05:30 IST. Fixed in the
  tests and recorded as [BACKLOG](../BACKLOG.md) B-11 (closed). The full suite on the exact commit
  that is pushed is in the phase's summary (`SESSION_LOG.md`) and the next STATE history line.

Not exercised: a real FeedbackAgent call, a real pre-open run, production data.

## Acceptance checklist

- [x] Hand-built envelopes for each writer's real `reason` and `trigger`: the two shocks fire with
  a falling path, not a flat one; `thesis_break`, `regime_flip`, `manual` never; an old shock
  does not.
- [x] PR-009's property test and its file pass unchanged.
- [x] KT section 6 states the rule and drops the limit; guide case 07-S.
- [x] Story file and changed files pass; `check_kt_docs` passes; PDF not built, per AGENTS.md.

## Production and what follows

- **Rollout:** deploying `main` turns the trigger on under the acting rule (`advisor.exit_rule:
  shadow`, where the price-path rule acts); a held stock whose latest re-forecast is a recent shock
  with a falling path is sold at that close. `production_verification`: `pending_deployment`, then
  `pending_observation` with the watch.
- **`FIX-015-W1`** (STATE `pending_production_checks`), from Tue 1 Dec with `PR-014-D1`'s door
  read: read-only, counts and symbols only. Every advice record since the deploy with
  `shock_reforecast`: the re-forecast it read (trigger, time) and the close it sold at; and the
  `external_shock` re-forecasts of held stocks that did not sell, with why (path not falling,
  outside the window, superseded). Pass: every sale names an `external_shock` or `preopen_shock`
  made before one of the two closes before it. Raise it with the owner if shock sales outnumber
  the evidence rule's own exits, or one follows a day the market as a whole moved less than 2%.
- **State after this review:** FIX-015 `done`; `active_task` none; `next_task` PR-015 (its
  dependencies FIX-015 and PR-014 are done). PR-015 changes one production setting, so it asks
  the owner before switching it.

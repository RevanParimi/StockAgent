# FIX-031 — implementation receipt

**Story:** [FIX-031](../stories/FIX-031.md): every input a decision at a session's close reads is
from before that close. Routed from FIX-027's fresh review (F1, F2, I-1, I-2, L2, L3).

**Phase:** implementation, Friday 13 Nov about 21:15 IST to Saturday 14 Nov about 07:45 IST (the laptop slept overnight). Session `stockagent-main-fd`
[d5183a], a new conversation opened with "continue". `origin/main` was `5ae2749`: nothing had
arrived from the other device. Peers `-50` and `-55` were idle. This phase includes a
same-conversation self-review, which is not the fresh review.

**Baseline:** the checkout was on the local branch `chore/remove-dead-code` (CLEAN-001). At the
owner's choice ("Fast-forward main"), `main` was fast-forwarded to it, `cbbee3c`, a local change
only. HEAD `cbbee3c`, clean; the review diff is taken against it. `main` is 13 commits ahead of
`origin/main` and nothing is pushed.

**Status after this phase:** `review_required`. Nothing is committed, pushed, deployed or
configured. Production was read once, read-only, at the owner's word (step 1's probe, below). No
LLM was called and no message was sent. No test reaches the network (`tests/hermetic.py`).

## In one example

A stock is held at ₹1,000 on Monday's close, and its forecast path ends at ₹970 (−3.0%, DOWN).
Monday missed its forecast, so the 16:30 job on Tuesday reviews the thesis on company news fetched
up to then. On Tuesday the company reports a loss and the review says "not intact".

- **Before:** that judgement sat in Monday's feedback entry, so the legacy rule EXITed at Monday's
  ₹1,000, selling before a fall the run had already read.
- **Now:** Monday's entry records `written_at` 2026-06-09 16:30 IST. The decisions at Monday's and
  Tuesday's closes do not read it; the one at Wednesday's close does, and EXITs there if the path
  still points down. This is FIX-027's "Wait", now for the thesis as well as the path.

The same day's review also cut every remaining row's confidence by the thesis multiplier. The
advisor now reads each row's confidence as it stood at the close: 0.70 at Monday's, not the 0.299
written on Tuesday. As stored, Monday's trend of −0.341 would have TRIMmed a holding that is 25% up.

## Step 1: measured first (the production probe)

`analysis_data/fix031/prod_probe.py` (ignored, local to this laptop) is read-only and prints counts
only: no tickers, no user ids, no logs. It reads the stored files directly. Checked on a made-up tree
(`probe_fixture.py`) against counts worked by hand. Run at the owner's word ("Run it now"), Friday
13 Nov, 22:20 IST, on production's `f368f20`, by one `railway ssh`:

```text
railway ssh "cd /app && echo $(gzip -9c analysis_data/fix031/prod_probe.py | base64 -w0) | base64 -d | python -c 'import sys,zlib;exec(zlib.decompress(sys.stdin.buffer.read(),31))'"
```

**The first run's shadow count was wrong, mine:** a shadow row stores only `event_ids`, not the
events, so "case event published after the close" read 0 without looking. Corrected to look each id
up in `data/events/<symbol>.jsonl`, checked on the fixture again, and run once more at 22:21. Both
outputs are kept (`probe_2026-11-13.json`, `probe_2026-11-13_run2.json`, ignored); the figures below
are run 2's, identical to run 1's except the corrected and added shadow counts.

| Count, since 1 Aug 2026 | Value | What it means |
| --- | --- | --- |
| Portfolios / advice rows | 1 / 256 | |
| Re-forecasts (envelopes: 106) | Aug 26, Sep 38, Oct 37, Nov 10 | All `thesis_break` but 1 `preopen_shock` (Sep) and 1 `manual` (Oct). |
| … stamped `at` (FIX-027, from 10 Nov) | 4 (Nov) | All 4 ran after their review date's close, and all 4 rewrote a row of a session already closed (I-2). The 106 unstamped ones were the same review path. |
| … with an ADD, EXIT or SWITCH the same day on the same stock | 1 (Aug, SWITCH) | FIX-027's step 1, never run before: small. |
| Thesis reviews | Aug 207, Sep 321, Oct 336, Nov 124 | |
| … "not intact" | Aug 89, Sep 152, Oct 105, Nov 19 | 365 in all. |
| … with an EXIT or SWITCH the same day | Aug 2, Sep 3, Oct 2, Nov 1 | 8 sales dated the session whose thesis was judged after its close. |
| … whose advice carried `thesis_break` | Aug 2, Sep 2, Oct 1 | **F1 measured: 5 sales.** |
| Shadow rows | Oct 4, Nov 16 | 20 in all. |
| … whose research verdict ran after the row's close | Oct 4, Nov 13 | **F2: 17 of 20.** The daily review's own analysis, run that evening, was read as the same day's. |
| … of those, a SELL | 0 | No research-verdict sale came from it. |
| … with a case event published after the close | Nov 2 | |
| … with any late evidence, disagreeing / with case-broken reasons | Nov 4 / Oct 1, Nov 7 | Late evidence was present; whether it was the reason is not measured. |

**Reading (inference from the counts and the code):** F1 is small, 5 sales in three and a half
months, so the owner's "Wait" stands for the thesis without asking again (the card: "if step 1's
count is large, re-ask"). F2's research half is systematic: almost every shadow row read an analysis
made after its close, none a SELL so far, so the switch gate's record was not yet moved by it. The
event half is rare.

## What changed

- **Schema** ([feedback.py](../../../../src/backend/shared/schemas/feedback.py)):
  `FeedbackEntry.written_at` (IST, "" = stored before), `DailyForecast.confidence_revisions` (a list
  of `ConfidenceRevision(at, before)`). Old files load with the defaults (pydantic ignores unknown
  fields, so a rollback loads the new files too).
- **The daily review** ([daily_review.py](../../../../core/intelligence/rl/workflows/daily_review.py)):
  Step 7b records each confidence change on its row (its time, the value before); Step 8 stamps the
  entry's `written_at`. Nothing else in the review changes, the news context included (D1).
- **The advisor** ([advisor.py](../../../../core/portfolio/advisor.py)): `written_before(entry,
  close)` and `confidence_at(row, close)`; `build_signals` reads the thesis only from an entry
  written before the review session's close, and every remaining row's confidence as it stood at
  that close (`confidence`, `confidence_trend`).
- **The evidence rule** ([exit_shadow.py](../../../../core/portfolio/exit_shadow.py)):
  `published_time(event)`; `recent_negative_events` counts an event for 5 closes from the first
  close after it; `latest_actionable_verdict` counts a run before the close; `invalidation_for` a
  shelf idea whose `decision_time` is before the close. The module docstring's information rule
  says so.
- **The re-forecast** ([generate_forecast.py](../../../../core/intelligence/rl/workflows/generate_forecast.py)):
  keeps the row of every session already closed when it runs (I-2), and does nothing when no
  session after the review date is still open.
- **Tests:** the story file (below); FIX-027's end-to-end fixture with a profile `ForecastProfile`
  accepts (L2); `test_reforecast._patch_pipeline` pins the clock to the review day's evening (the
  code now reads it); PR-009's two calendar-day boundaries moved to the clock's (below).
- **Docs:** KT section 5 (step 7) and section 6 ("Every other input at the session's close" replaces
  "Not covered … Planned: FIX-031"; the two exit rules' wording); RL_DESIGN (Step 7b, Step 8, the
  envelope and entry examples, 27.2); AUTOPILOT_GUIDE's signals table; CODEBASE; PRODUCT_MAP (the
  re-forecast line; the schema file's line count, already stale at 1,099); guide case 07-Q and
  HT-07's related list; the PDF (71 pages).

## Decisions (delegated technical calls; the owner delegated routing and technical calls on 13 Oct)

- **F31-D1, the thesis: option (b), each entry says when it was written.** Option (a), cutting the
  review's news at the reviewed day, was not chosen, for three reasons. Serper gives dates, not
  times, so (a) keeps the reviewed day's evening filings, the 18:10 results of F2's example. The
  thesis reviewer also reads the feedback agent's output, which read the same news, so cutting the
  thesis's news alone leaves the leak. Cutting the whole review's news would take from the learning
  loop the articles that explain the session's move (the card's first hard-review question). (b) is
  exact by the clock. Cost: a thesis judged on Tuesday first sells at Wednesday's close, booked by
  Thursday's run. Measured: 5 such sales since August (above). FIX-027 review's strict xfail
  `test_f1_review_news_stops_at_the_reviewed_close` therefore stays an xfail, by this decision.
- **F31-D2, entries stored before FIX-031** (no `written_at`). One dated on or after the decision's
  session is after its close, stamped or not: its review graded that close. One dated earlier counts
  as before, as FIX-027's untimed re-forecasts do. Example: the first decision after the deploy, at
  session D's close, reads the unstamped entry of D−1 (written on D at 16:30, before the deploy), a
  one-day leniency that ends with the first stamped entries. An unreadable stamp counts as after.
- **F31-D3, Step 7b's confidence: a revision log read at the close.** The card names the confidence
  revision under F1, and the acceptance invariant covers it ("the thesis review" is an input, and its
  multiplier moves every row's confidence). Each row keeps `(at, before)` per change; the advisor
  undoes, newest first, those made at or after the close (revisions are appended in time order, so
  it stops at the first one before). Not chosen: an archive per review (a file per ticker per day),
  or reading only the issued confidence (it drops revisions made before the close, which the TRIM
  rule is meant to read). A row revised before the field existed reads as stored. At most one entry
  per review per row, about 22 a month.
- **F31-D4, the event window:** an event counts for 5 closes, from the first close after it was
  published; a date without a time counts as published at that day's 15:30 close, the convention a
  deep dive's day has had since FIX-024. Examples: filed 14:10 Monday, Monday to Friday; 18:10
  Monday, Tuesday to the next Monday; a Monday-dated item with no time, as 18:10; a Saturday-dated
  one, Monday to Friday as before.
- **F31-D5, the research verdict:** only the upper bound moved to the close. The age window (22
  sessions by the IST day) and the buy-day bound are unchanged. The daily review's evening analysis
  of day D now counts from D+1's close.
- **F31-D6, the deep dive's invalidation level** (beyond the card's list, which names "analyses"):
  read by `shelf.decision_time`, so a dive dated the session itself counts from the next close. Dives
  run on Saturdays, so this rarely moves anything; it is the same clock as a buy.
- **F31-D7, I-2:** the new path is still drawn through a closed session's row (so the rows after it
  keep their spacing), and that row is kept byte for byte. Which sessions have closed is read after
  the analysis, at the time recorded as `at`, so a re-forecast that runs across 15:30 keeps that
  session's row. A re-forecast with every session after the review date already closed returns
  before the archive.
- **F31-D8, I-1:** FIX-029 built it (`ScoreStore.get_latest_before`, `watchlist_idea`). Checked here
  by an invariant over the real score store (below), not built again.
- **F31-D9, the invariant's scope.** Two things the AdviceRecord carries depend on a re-forecast
  after the close by FIX-027's design: `envelope_after_close` and the note `ENVELOPE_AFTER_CLOSE`
  (and so `rationale_hash`), and the signals' `envelope_late_direction`. They disclose what the
  decision did not act on. The invariant compares everything else and checks these separately: they
  may only name a re-forecast at or after the close. What the close itself sets is not "after the
  close": the review's grade of the session and the day's regime label (the regime detector reads no
  bar after the session), so the invariant holds them equal.

## Tests

Every expected value is worked by hand in the test's docstring, never read back from the code. No
test reaches the network.

- **Story file** `tests/unit/test_issue_time_fix031.py`, 78 tests, all pass:
  - the calendar (8–16 Jun 2026 are seven trading days);
  - F1 (3): the card's example through the real advisor (path to 970, close ₹1,000, judged Tuesday
    16:30: HOLD Monday, HOLD Tuesday, EXIT Wednesday); the latest review written before the close is
    read; entries stored before FIX-031, stamps a minute either side of 15:30, a naive stamp as IST;
  - Step 7b (3): the real `_revise_remaining_forecasts` twice (0.70 → 0.64 → 0.299, worked in the
    docstring), read 0.70 / 0.64 / 0.299 at Monday's / Tuesday's / Wednesday's close, and the stored
    figures TRIM; `confidence_at`'s order and unreadable times; **the real daily review** (the
    shock-path seams) run the next day at 16:30 stamps its entry and its revision, neither read at
    the session's close;
  - F2 (3): filings at 14:10, 18:10, 15:29, 15:30, Monday with no time, Saturday with no time, a
    naive time: the exact closes each counts at; analyses at 11:00, 15:29, 15:30, 16:35 and 20:00 IST;
    a dive dated Monday, Saturday, and both;
  - I-2 (6): the real `regenerate_envelope` at Tue 16:45, Wed 00:30, Wed 15:30, Mon 16:45 and the
    pre-open Tue 08:45: the kept rows byte for byte, the first new row, the day numbers; Fri 16:00
    with nothing open: no archive, no save;
  - L3 (1): FIX-027's two branches, an unreadable `at` (after) and a naive one (IST);
  - **the invariant** (40 seeds): two worlds share every input made before Monday's close and differ
    at random in every one made at or after it: re-forecasts (with their archives) and confidence
    revisions applied in time order, the thesis reviews of Friday and Monday, events, research runs
    and deep dives. The files are written directly and read back through the real `VerdictStore`,
    advisor and evidence reader. Monday's AdviceRecords under both rules, the shadow row and the
    signals are equal (F31-D9). A control shows a pre-close input does move them (Thursday's "not
    intact" sells; a 14:10 filing is case evidence, an 18:10 one is not);
  - **the watchlist invariant** (20 seeds, I-1): analyses before Monday 2 Nov's close equal, those
    at or after it random, in two real score stores: the same offer or reason.
- **The FIX-027 reviewer's cases** (`analysis_data/fix027_review/test_rv_fix027.py`): its three
  strict xfails for F1 and F2 now fail as `XPASS(strict)`, that is, the contracts hold; the news-cut
  one stays xfail (F31-D1); its 4 other cases pass.
- **Changed existing tests:**
  - `test_exit_evidence_pr009.py`: two boundaries were the calendar day's. "A session too old" was a
    15 Oct 18:00 filing; by the clock it first counts at 16 Oct's close, inside the 23 Oct window, so
    the boundary is now 15:29 (out) against 15:30 (in). "23 Oct 23:59 IST is still the review day"
    becomes 15:29 IST (in) against 15:30 (out).
  - `test_reforecast._patch_pipeline` pins `now_ist` to the review day's evening (9 Jun 16:45); the
    re-forecast reads the clock now, and the fixtures' June rows had all "closed" by the real clock.
  - `test_envelope_after_close_fix027.py` (L2): a +20% profile, which `ForecastProfile` accepts
    (+40% was refused, so the static path ran); the docstring's figure (about 1,221, not 1,040) and
    assertions that the profile ran and Tuesday's row was kept.
- **Mutants** (`analysis_data/fix031/mutants.py`, in a detached worktree of `cbbee3c` synced to the
  final tree; `mutants.txt`): **23 of 23 caught by the story file**: the thesis read whatever its
  time, the entry's date bound removed, an unstamped older entry read as after, an unreadable or a
  15:30 stamp read as before, a naive stamp read as UTC; the confidence read as stored, an
  unreadable revision kept, no revision recorded, no `written_at`; events by the calendar day, at
  the close, a window starting a session late, a date-only event as midnight, a naive time as UTC;
  research by the calendar day; a dive dated the session read; I-2's closed rows rewritten, a
  session closing after 15:30, the nothing-open skip removed; FIX-027's m02 and m08 (L3); and the
  watchlist reading a later analysis.
- **The invariants alone** (`mutants_invariant.py`, `-k invariant`): 9 of the 23, the ones that let
  an input from after the close in (the thesis, the entry's date bound, the stored confidence,
  events by day and at the close, a date-only event, research by day, the dive, the watchlist).
  The other 14 are the stamps' own edge rules, the review's writing side, I-2 and L3, which the
  two worlds hold equal or do not vary; the targeted tests catch them.
- **A flake, and the test changed for it.** The first invariant pass "caught" 13, four of them
  with one failure each. Re-running the unmutated invariants showed why: `[WinError 5]` on the
  store's temp-file rename (a scanner holding the file, seen on this laptop before), which my
  first version of the invariant hit about once in 40 seeds because it saved each world's
  envelope up to ten times. The invariant now writes its files directly (it tests the readers,
  not the writer): four clean runs, and the second pass above (both passes re-run on the final
  bytes; the first pass is kept as `mutants_invariant_pass1_flaky.txt`).
- **Neighbouring suites** (before the final fixes): the 44 test files that touch the changed
  functions, 1,243 passed and 5 failed: the 3 `test_reforecast` tests on the real clock and the
  2 PR-009 calendar-day boundaries, all fixed as above.
- **Full suite**, three runs:
  - run 1 (from 23:22 IST on 13 Nov): the laptop slept overnight; at 05:55 it stood at 58% and
    had not moved by 07:06, so it was stopped (output kept as `run1_full_suite_hung.txt`; it
    printed no failure before it stopped);
  - run 2 (07:07–07:23, verbose): 6,455 passed / 12 skipped / 1 xfailed / **1 failed**, rc 1:
    `test_every_door_fix029.py::test_m1_every_label_with_or_without_an_entry_of_its_own`, whose
    log reads `[RegimeState] Failed to persist state` in its tmp folder: the Windows file lock
    recorded for this same test on 12 Nov, in code FIX-031 does not touch. That file then passed
    5 of 5 runs alone (`fix029_file_x5.txt`);
  - run 3 on the same bytes (07:24–07:39 IST, 14 Nov): **6,456 passed / 12 skipped / 1 xfailed
    / 0 failed**, rc 0, 14m41s; `git status` the same before and after (`full_suite*.txt`,
    `run1_*`, `run2_*`). 6,456 = CLEAN-001's 6,378 + the story file's 78.
- `check_broad_except`: OK (148 grandfathered). `check_kt_docs`: `errors: []`; the PDF
  regenerated (71 pages, source `8d988056`).

## Rollout (what deploying changes, with the switch off)

- **The legacy sale on a broken thesis** (the rule that acts today) waits two sessions: a thesis
  judged at Tuesday's 16:30 run first counts at Wednesday's close. 5 such sales since August.
- **TRIM** reads each row's confidence as at the close; a profit-taking TRIM that only the evening
  revision's drop allowed no longer fires that day.
- **The shadow's evidence** counts the daily review's evening analysis from the next close (17 of 20
  rows read one the same day), and an after-hours filing from the next close. The switch gate's rows
  dated after the deploy are on the clock; rows already written are not rewritten.
- **A review's re-forecast** leaves the next session's row as issued, so that session's grade (and
  `direction_accuracy_7d`, the weight adapter's input) is against the forecast made before it.
- Files: entries gain `written_at`, revised rows `confidence_revisions` (about 22 small entries per
  row per month). Old files load; entries and rows written before the deploy read as F31-D2 and
  F31-D3 say. Rollback is a revert: the old code ignores the new fields.
- No configuration changes. Deploying FIX-031 with FIX-030 (committed, not pushed) and CLEAN-001
  (on `main` now) is the owner's call; `git push origin e2b6f34:main` still deploys FIX-030 alone.

## Hard review (the card's questions, answered)

- **Does the publish-date filter drop same-day information that explains D's move?** No filter was
  added (F31-D1). The review's news context, which the learning loop reads, is unchanged; the
  decision reads the judgement by when it was written.
- **With (b), every reader of the feedback entry's thesis:** a search of `thesis_review` and
  `thesis_intact` over `core/`, `services/`, `src/` and `scripts/` finds one decision reader,
  `advisor.build_signals` (and through it `decide`'s EXIT and its TRIM-to-HOLD tax softening). The
  daily review writes it and puts the run's own judgement in its summary. `verdict_store`'s Atlas
  projection lists a `thesis_intact` column but has no caller (its docstring: dormant). The brief
  and the weekly read a shelf idea's `thesis`, the deep dive's investment case, a different field.
  `scripts/aud098_thesis_tier_bench.py` is an offline bench.

## Not covered / found on the way

- **FIX-027's disclosure** puts a re-forecast after the close into the record's text and
  `rationale_hash` (F31-D9). By design; noted for the reviewer.
- **The Atlas projection's `thesis_intact`** (`verdict_store._PROJECTION_FIELDS`) is a per-day
  column with no caller. If it is wired, it should be written from `written_before`, not the latest
  entry.
- **The exit-shadow research window's lower bound** is still by the IST day, so a run made before
  the close counts for 23 closes and one after it for 22 (F31-D5). Unchanged on purpose: the card
  asks only for the upper bound.

## Review input

- Manifest: [FIX-031-manifest.json](FIX-031-manifest.json), SHA-256
  `d1fbec94260e987e74308dcd1f0e63fe70cae7ffd81204a1a6ba7f11b11c0499`, 16 files
  (`scripts/docs/kt_manifest.py verify`: 0 mismatches).
- Diff against HEAD `cbbee3c`, the PDF excluded: SHA-256
  `d04ec340639e190a6532d19dc8b83389b513d7515f9de334daab44f90a25cf4f`, 104,934 bytes, 15 paths, via
  `analysis_data/fix031/digest.py` (a temporary index; the real index is untouched). End tree
  `c802681c4375b54b9468147887e2e0fce573336e`, taken before this receipt's last figures and the STATE/HANDOFF
  splice. No file outside the manifest changed but the bookkeeping.
- Outside the manifest: STATE, HANDOFF, this receipt and the manifest (bookkeeping).
- On another device: `git diff cbbee3c` over the manifest's paths but the PDF, sorted,
  `core.autocrlf=false`, with the new test file added.

## What a fresh review should press on

1. F31-D1 against (a): is any path that reads the thesis left that does not go through
   `written_before`?
2. F31-D3: can any writer change a row's confidence without a revision record? (A search of
   `.confidence =` over `core/`, `services/` and `src/` finds Step 7b only; the re-forecast replaces
   rows, which the archive covers.)
3. F31-D9: is the disclosure carve-out right, or should the record not name a later re-forecast at
   all?
4. I-2 with the pre-open path and a run across midnight or across 15:30.
5. The legacy leniency (F31-D2) on the first day after a deploy.

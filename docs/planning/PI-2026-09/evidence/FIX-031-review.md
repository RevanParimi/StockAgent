# FIX-031 — fresh review receipt

**Story:** [FIX-031](../stories/FIX-031.md): every input a decision at a session's close reads is
from before that close. Routed from FIX-027's fresh review (F1, F2, I-1, I-2, L2, L3).

**Review context:** fresh-session review, session `stockagent-main-f2` [050ab6], a new
conversation opened with "continue", Saturday 14 Nov 2026, about 07:56–08:25 IST. `origin/main` was
`5ae2749` after a fetch, so nothing had arrived from the other device. Three peer sessions were idle,
the implementer `stockagent-main-fd` among them. No production state was read, no LLM was called, no
message was sent, and no test reached the network. Nothing was committed. `FIX-030-M1` is due after
14:00 IST today; this conversation started before then, so it does not run it.

**Verdict: accepted** for the reviewed revision below. Two low findings, both pre-existing and
outside the card's named inputs, are routed (R1 to PR-007, R2 to SA-021). No finding of medium or
higher severity; no acceptance criterion is unmet.

## Input verified

`analysis_data/fix031_review/rv_digest.py` (writes nothing tracked; a temporary index) was run at
the start and at the end:

| | Start (08:00) | End |
| --- | --- | --- |
| HEAD | `cbbee3c` = the baseline | `cbbee3c` |
| Manifest | `d1fbec94…` (16 files), `kt_manifest.py verify` 0 mismatches | the same, 0 mismatches |
| Diff against HEAD, the PDF excluded | `d04ec340…`, 104,934 B, equal to the receipt | the same |
| Changed outside the manifest and the bookkeeping | none | only this review's files (this receipt, the PR-007 and SA-021 notes) |

End tree at the start `d7bbe333`, at the end `3d368540` (this review's files). The start tree differs from the receipt's `c802681c` only by the bookkeeping
written after it (STATE, HANDOFF, the receipt), as the receipt says.

## Contract checked

The card's "Intended result", its acceptance list and its two hard-review questions; REVIEW.md's
issue-time availability, data flow to every consumer, missing-data policy, compatibility and the
tests' oracles. Code read: `advisor.build_signals`, `written_before`, `confidence_at`, `_ist_at`,
`envelope_at_close`, `reforecasts_after_close` and `decide` (EXIT, TRIM, ADD, SWITCH, the LTCG
softening and the annotations); `exit_shadow.published_time`, `recent_negative_events`,
`latest_actionable_verdict`, `invalidation_for`, `exit_evidence`, `EvidenceReader`;
`shelf.decision_time` / `last_dived`; `candidates._ist_time` and `buy_candidates`;
`daily_review._revise_remaining_forecasts`, the re-forecast trigger block and Step 8;
`generate_forecast.regenerate_envelope` and `_closed_by`; the schema's new fields and its
extra-field policy (pydantic's default, ignore: a rollback reads the new files); the portfolio
pipeline's inputs to the advisor (`session_close`, `get_price_history`, `refresh_events_calendar`,
`sync_corp_actions`); the conviction tracker; `EvalHarness._match_records`.

### Every input the decision at D's close reads, by when it is made

The 16:30 job on day T reviews D, the session before T, and advises at D's close.

| Input | Made | Read by the decision at D's close | Verdict |
| --- | --- | --- | --- |
| The path (envelope rows) | issue; re-forecasts | as at the close (FIX-027) | in |
| Confidence, trend | issue; Step 7b at 16:30 | as at the close (`confidence_at`) | fixed here |
| Thesis | Step 7a at T 16:30 | only if written before the close | fixed here |
| Events, research verdict, deep dive | any time | by the 15:30 clock | fixed here |
| Watchlist analysis | any time | newest before the close (FIX-029) | checked here |
| Grade, 7-day accuracy, regime label | from D's close | as computed | set by the close |
| Reversion prior | D's predicted verdict and the regime RSI | as computed | set by the close |
| OHLCV (ATR, peak close) | `yf.download(end=date.today())` | ends at D (`end` is exclusive) | in |
| Corporate actions | applied up to D (`sync_corp_actions(store, review_date)`) | up to D | in |
| Board-meeting calendar | refreshed by T's run | the next results date, no announcement time | **R1** |

## Independent adversarial examples

Reviewer cases: `analysis_data/fix031_review/test_rv_fix031.py` (ignored, local to this laptop;
reviewer conftest = the suite's hermetic boundary and isolation fixtures). They borrow only
infrastructure: the shock-path seams of the real daily review (`test_shock_path._patch_common`, no
LLM and no network) and the re-forecast's fake analysis (`test_reforecast._patch_pipeline`). No
helper of the story file; every expected value is worked in the case's docstring. Dates are Mon 2 to
Fri 6 Nov 2026, the current month, so the daily review treats the cycle as live and may re-forecast
(the cases need November 2026 to run).

- **RV1, F1 and Step 7b through the real daily review and the real advisor.** Rows issued at 100.0,
  99.5, 99.0, 98.0, 97.0, confidence 0.50. The review of Monday runs Tuesday 16:30: actual 98.0
  against a BUY, thesis "not intact" × 0.75 (no re-forecast). By hand, Step 7b sets Tue to Fri to
  0.7 × 0.50 + 0.3 × 0.5 = 0.50, × 0.75 = 0.375; the stored rows are exactly that. The advisor
  then gives, at Monday's close, no thesis, confidence 0.50, trend 0.0, DOWN, HOLD; at Tuesday's
  the same; at Wednesday's thesis false, confidence 0.375, trend 0.0, EXIT `thesis_break`. Passes.
  On `cbbee3c` Monday's close reads the thesis and confidence 0.4 (0.50 and four rows of 0.375) and
  EXITs.
- **RV2, I-2 through the real review, the real `regenerate_envelope` and the next grade.** The
  review of Monday runs Tuesday 16:45 with × 0.4: `thesis_break`, the real re-forecast from Monday's
  close. Tuesday's row stays byte for byte; Wednesday to Friday are new, numbered 3 to 5; the event's
  `at` is Tuesday 16:45; Monday's entry carries `written_at` Tuesday 16:45. The advisor at
  Tuesday's close reads the archive and no thesis (HOLD); at Wednesday's close the thesis and only
  new rows. **The consumer:** the real review of Tuesday, run Wednesday 16:30 on a 99.0 close,
  grades the row issued before Tuesday's session: predicted 99.5, error −0.5025%. Passes. On
  `cbbee3c` Tuesday's row is the new path's (100.44).
- **RV3, the earnings note** (finding R1). A strict xfail; it fails at its contract assertion: the
  records differ in `notes` (`EARNINGS_GAP_PROTECTION`) and `rationale_hash`, nothing else.
- **RV4, calibration** (finding R2). A strict xfail; it fails at its contract assertion: the
  harness pairs Tuesday's outcome with 0.375, the confidence written at Tuesday 16:30, while
  `confidence_at` gives 0.50 at Tuesday's close.
- **RV5, publication stamps in every format the sources and stores hold:** `Z` at 10:00 UTC (the
  close itself, so Tuesday), 09:59:59 UTC and 15:29:59.999999 IST (Monday), a naive "18:10" with a
  space or without seconds (Tuesday), a −05:00 offset that is Monday 09:30 IST (Monday), a
  ten-character non-ISO date and an empty stamp (never). Passes; on `cbbee3c` three fail.
- **RV6, F31-D2's leniency.** An unstamped Thursday entry written Friday 16:30, before a deploy, is
  read at Friday's close (the documented one-decision leniency), and only because it has no stamp:
  stamped Friday 16:30 it is not; at Monday's close it is, correctly.
- **RV7, an evidence invariant (60 seeds) wider than the story's:** every source (NSE announcement,
  board meeting, news, insider, pledge), materiality, direction and stamp format, and every verdict
  and gate (actionable, degraded, abstain), shared before Monday's close and random after it, in a
  shuffled order. Monday's evidence is equal. A control shows pre-close items count. Passes; on
  `cbbee3c` 52 of the 60 seeds fail.

**Result:** 73 passed, 2 xfailed (strict) on the reviewed tree (`rv_tests.txt`). On the baseline
`cbbee3c` (a detached worktree, removed after): 58 failed, 15 passed, 2 xfailed
(`baseline_rv.txt`). The 15 that pass there are RV5's 5 stamps the calendar day and the clock
agree on, 8 of RV7's seeds whose later items happen to count under neither rule, RV7's control and
the calendar check. RV6 fails there because `written_before` does not exist yet.

## The card's hard review

1. **Does the publish-date filter drop same-day information that explains D's move?** No filter was
   added (F31-D1, option b). The review's news context, which the learning loop reads, is unchanged.
   Agreed: (a) would have kept D's evening filings (Serper gives dates only) and still left the
   thesis reading the feedback agent's output on the same news.
2. **With (b), every reader of the feedback entry's thesis.** A search for `thesis_review` and
   `thesis_intact` over `core/`, `services/`, `src/` and `scripts/` finds one decision reader,
   `advisor.build_signals`; it reaches `decide`'s EXIT and the LTCG softening through
   `signals.thesis_intact`. `verdict_store.publish_projection` lists a `thesis_intact` column and
   has no caller. The daily review writes the thesis. The brief and the weekly read a shelf idea's
   `thesis`, a different field. Confirmed.

## The implementer's questions

1. **Is any path that reads the thesis left outside `written_before`?** No (hard review 2).
2. **Can a writer change a row's confidence without a revision record?** No. Searching for
   `.confidence =`, `.daily_forecasts =` and item assignment finds Step 7b (recorded) and the
   re-forecast's row replacement (the archive covers it); the other hits are lessons and dossier
   signatures. `paper_lane` writes paper envelopes, which no decision reads.
3. **F31-D9, the disclosure carve-out.** Right as designed. The record names a later re-forecast
   only in `envelope_after_close` and the note `ENVELOPE_AFTER_CLOSE`; `decide` never acts on it
   (the ADD branch only appends the note). Removing the disclosure would hide why the path was not
   read. One more exception follows FIX-027's design: a late re-forecast whose archive cannot be read
   leaves no path at all (direction FLAT). That is a failed write, not information, and it fails
   safe.
4. **I-2 with the pre-open path, across midnight and across 15:30.** The story's parameter cases
   (Tue 16:45, Wed 00:30, Wed 15:30, Mon 16:45, pre-open Tue 08:45) and RV2 through the real review.
   By inspection: closed rows are a prefix of the rows after the review date, so `past_forecasts`
   stays in date order; a decision at a close after the re-forecast reads only rows of sessions that
   were open when it ran (a mixed old-and-new trend cannot occur); a late one reads the archive. The
   pre-open path keeps the review day's row as before (pre-existing).
5. **F31-D2 on the first day after a deploy.** One decision per holding with an unstamped entry
   dated the session before (RV6). Bounded and documented in the receipt.

## Findings

| # | Severity | Where | Trigger → observed / expected | Impact | Disposition |
| --- | --- | --- | --- | --- | --- |
| R1 | low (annotation; pre-existing) | [core/portfolio/advisor.py:398-409](../../../../core/portfolio/advisor.py) `build_signals`' earnings distance, from [core/portfolio/pipeline.py:278](../../../../core/portfolio/pipeline.py) `refresh_events_calendar`; the note at advisor.py:785-790 | T's run refreshes NSE's board-meeting calendar before advising D's close; the calendar keeps no announcement time. A results date announced after D's close puts `EARNINGS_GAP_PROTECTION` in D's record and changes `rationale_hash` (RV3). Expected by the card's invariant: nothing in the AdviceRecord moves. | Narration only ("results are due within days"): no verdict, trigger, quantity or shadow field changes. | Routed to [PR-007](../stories/PR-007.md), section "Routed input — 2026-11-14 FIX-031 review (R1)". KT section 6 names it as not covered (commit-time edit 3). |
| R2 | low (learning evidence; pre-existing) | [core/intelligence/rl/eval/harness.py:283-303](../../../../core/intelligence/rl/eval/harness.py) `_match_records`; writer [daily_review.py:500-507](../../../../core/intelligence/rl/workflows/daily_review.py) | Step 7b of the review of the session before T revises T's row at T 16:30, after T's close, and no later review touches it. Calibration (the Brier score, the reliability table, `brier_decomposition`) pairs T's outcome with that revised confidence (RV4); the same run's headline goes into T's `key_assumptions`, which the review of T hands the feedback agent. Expected: the confidence as it stood at T's close. | A calibration report only, in observe mode; no decision reads it. The grade's price fields are as issued. Not measured. | Routed to [SA-021](../stories/SA-021.md), section "Routed input — 2026-11-14 FIX-031 review (R2)". FIX-031's revision log makes it fixable for rows revised after the deploy. |

**Information, no action:** the OHLCV frame the advisor reads ends at D because yfinance's `end` is
exclusive and the run is on T (a run after IST 05:30 the next day would read T's bar; the scheduled
run never does). The thesis wait costs two sessions, as the owner's FIX-027 "Wait" accepted (5 such
sales since August).

## Commands, environment and results

Windows 11, the `.stockai` venv (Python 3.13), from the repository root; `tests/hermetic.py` blocks
the network.

- Focused, once: `pytest -q -p no:cacheprovider tests/unit/test_issue_time_fix031.py
  tests/unit/intelligence/rl/test_reforecast.py tests/unit/test_envelope_after_close_fix027.py
  tests/unit/test_exit_evidence_pr009.py analysis_data/fix027_review/test_rv_fix027.py` → 182
  passed, 1 xfailed, 3 failed. The 3 are FIX-027 reviewer's strict xfails for F1 and F2 now passing
  (`XPASS(strict)`): their contracts hold. The xfail left is the news cut, by F31-D1.
- Reviewer cases: above.
- Full suite, once, on the reviewed bytes (`run_suite.sh`, 08:08:41–08:24:13 IST): **6,456 passed / 12 skipped / 1 xfailed / 0 failed**, pytest rc 0, 15m26s, the same count as the implementer's run 3. `git status` after it differed from before only by this review's three files, written during the run.
- `scripts/docs/check_kt_docs.py`: `errors: []`, PDF 71 pages, source `8d988056` = the KT's
  manifest hash. `scripts/ci/check_broad_except.py`: OK (148 grandfathered).
- Not re-run: the implementer's mutants (23 of 23). Not exercised: production (the deploy is the
  owner's call), Linux.

## Acceptance checklist

| Card criterion | Evidence | Met |
| --- | --- | --- |
| The FIX-027 reviewer's strict xfails become tracked tests with hand-worked figures (Monday's path to 970 at 1,000 and Tuesday at 900; filings at 18:10 and 14:10; an analysis at 20:00 IST) | The story file's F1 and F2 tests; the reviewer file's xfails now pass; RV1, RV5 | yes |
| An independent invariant: nothing made or published after D's close changes the AdviceRecord or the shadow row (news, thesis, events, analyses, re-forecasts) | The story's 40-seed invariant (FIX-027's disclosure aside, F31-D9) and its control; RV7. The calendar note is R1 | yes, with R1 routed |
| An item published on D before 15:30 still counts | The 14:10 and 11:00 cases; RV5; RV7's control | yes |
| KT section 6's "Not covered" becomes current design; KT section 12's row; a guide case | KT section 6 "Every other input at the session's close"; section 12's row exists ("Open" until commit); guide 07-Q | yes |
| Measure first (step 1) | The owner-run probe of 13 Nov, recorded in the implementation receipt | yes |

## Commit-time edits (at the owner's word, with the commit)

1. KT header: "Code inspected" → FIX-031's code commit; the edition date. Run `check_kt_docs` after
   the bump: CLEAN-001 removed files that some documents link to, which the check reads at the
   declared revision.
2. KT section 12: FIX-031 "Open" → "Done".
3. KT section 6, after "...which reads no bar after it.": "Not covered: the earnings-gap note
   (`EARNINGS_GAP_PROTECTION`, an annotation, not a verdict) reads the board-meeting calendar the
   run refreshes, which keeps no announcement time. **Planned:** PR-007."
4. Guide 07-Q status: "**FIX-031: accepted 2026-11-14 (fresh review); not deployed.**"
5. The PDF.

KT section 1's production line changes only at the deploy.

## Production and follow-up

- STATE: FIX-031 `done`, production `pending_deployment`. Deploying it changes production with the
  switch off (the implementation receipt's Rollout). After the deploy, read-only: guide 07-Q's
  production lines and the counts-only probe (`analysis_data/fix031/prod_probe.py`) once a week has
  passed. Accepting the code shows no benefit by itself.
- Deploying is the owner's call. `main` is 13 ahead of `origin`; `git push origin e2b6f34:main`
  still deploys FIX-030 alone, which waits for `FIX-030-M1` (after 14:00 IST today).
- Next `continue`, in a new conversation: FIX-032's implementation; one starting after 14:00 IST
  today runs `FIX-030-M1` first.

## Committed (14 Nov, PR-014 step 2)

The owner approved PR-014's steps on 14 Nov, and its step 2 is this commit. Nothing was pushed.

- **`899526a`, the code:** exactly the 16 reviewed files. `kt_manifest.py verify
  FIX-031-manifest.json --rev 899526a` gives 0 mismatches.
- **The docs commit after it** holds this receipt, the implementation receipt, the manifest, the
  PR-007 and SA-021 notes and commit-time edits 1–5 above, with the 14 Nov planning files.
- **One edit beyond the list: KT section 1.** With the header at `899526a`, it says the inspected
  code is not yet deployed and names what it holds beyond production: FIX-030, FIX-031 and
  CLEAN-001's removals.
- **Also in the same files, from PR-014's step 2:** KT sections 11 and 12 and AUTOPILOT_GUIDE
  section 16 take the owner's 14 Nov decisions.
- **PDF:** 72 pages, source `40db4f24…` = the KT. `check_kt_docs` gives `errors: []`.
- **Where the files differ from the manifest:** at the docs commit, the manifest's KT, guide,
  AUTOPILOT_GUIDE and PDF differ from it by these edits only.
- **Not pushed.** The push is PR-014's step 4 ([rollout receipt](PR-014-rollout.md)).

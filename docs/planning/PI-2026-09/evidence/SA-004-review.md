# SA-004 review receipt — count daily-review outcomes truthfully

- **Story:** [SA-004](../stories/SA-004.md). Audit finding F09 in the
  [September audit](../../../audit/2026-09-10-repository-production-review.md).
- **Review context:** a **fresh-session** review, in a new conversation on 2026-09-27, about
  15:23–15:50 IST. It is separate from the implementation conversation (about 11:45–12:40 IST).
  No SA-039 check was due; P1 is Mon 28 Sep after 17:00 IST.
- **Reviewed input:** the uncommitted worktree on baseline
  `0a5bf9e15b6d6a9c43ac9f66106a5583a9c75ea5`. See the
  [implementation receipt](SA-004-implementation.md).
- **Verdict: ACCEPTED.** No critical, high or medium finding.
  - One low finding (F1) and two info notes (I1, I2) are routed to [SA-036](../stories/SA-036.md).
  - One pre-existing info note (I3) is routed to [SA-005](../stories/SA-005.md).
  - The acceptance covers review input `a5e77a74…`, and the documentation-only payload update 1,
    `5d9030e0…`, which arrived during the review. Its code and tests are byte-identical.

## Input verified first

- At 15:24 IST, `kt_manifest.py verify SA-004-manifest.json` against the working tree gave
  13 files, 0 mismatches, and review input
  **`a5e77a74ec7511e5d137c32a57e74929183f53680f43b4df82226dc230bb9e7e`**.
- **The diff digest was rebuilt with the reviewer's own script**, not the implementer's
  `sa004_diff.py`. It gives **`648b7b6833af4d6c26c0b397ef46d3cd53769d90bc3f6847401521636514f712`**:
  82,557 bytes over 12 text files, matching the receipt. The script:
  - sorts every manifest path except the PDF;
  - takes `git diff 0a5bf9e -- PATH` for a tracked path, and `git diff --no-index /dev/null PATH`
    for a new one;
  - concatenates the output.
- The PDF's working-tree blob is `b54a6a5d…`, as the receipt pins it.

**Payload update 1 arrived during the review (not SA-004's).** Between 15:35 and 15:39 IST, a
concurrent owner-requested planning session in the same checkout changed four payload docs: the
KT, the PDF, ARCHITECTURE and TEAM_TESTING_GUIDE.

- **What it changed:** it added SA-048…SA-051, the "Where cash goes" paragraph, the portfolio rows
  and cases 07-F, 07-G, 08-F and 08-G, and the story count in the KT's §1 row.
- **Regenerated input:** the session then regenerated the manifest. See the implementation
  receipt, "Payload update 1".
- **The reviewer checked the update independently:**
  - `verify` now gives 13 files, 0 mismatches, and review input
    **`5d9030e0ffe7cc997a5c2bc2100a8c046f443cdcd1672b698519e79853f8e661`**;
  - the reviewer's own rebuild gives the diff
    **`e16a8e3f47de65b78a0deef5c641fba4377f5d11deb5b717259da359c25a0edc`**, 91,343 bytes, and the
    PDF blob is `861711fa…`. Both match the receipt;
  - each file's diff was compared with the one saved at 15:24. The nine code, test and config
    files and `CODEBASE.md` are **byte-identical**;
  - only the three Markdown docs and the PDF differ. Every changed line in the Markdown is planning
    content, and none touches SA-004's reviewed text.

  So this acceptance covers both inputs, `a5e77a74…` and `5d9030e0…`.

## Contract checked

| Question | Answer, and how it was checked |
|---|---|
| Does `completed` really mean a feedback entry exists? | Yes. `append_feedback_entry` → `save_feedback_log` → `_write_json` re-raises a write failure as `RuntimeError` (`prediction_store.py:162-176`), so the review raises and counts `failed`. `run_daily_review` returns `completed` only after `store.append_feedback_entry` (`daily_review.py:1543`). |
| Can `classify`'s ticker/date check misread a real review? | No. `run_daily_review` returns the `ticker` it was passed and `review_date.isoformat()`, with no normalisation or alias mapping (`daily_review.py:470-499`). The scheduler passes `entry["sym"]` and compares with `review_date.isoformat()` from the same date. |
| Every status `run_daily_review` returns? | Five: `completed` (1647), `data_gated` (277), `no_envelope` (580), `no_forecast_row` (587) and `no_actual_data` (619). Each is classified, and anything else fails closed. |
| Who reads the record? | Only `GET /scheduler/status` (`last_runs`, `scheduler_api.py:470`), as raw JSON, plus SA-004's own merge. No frontend, watchdog, self-heal or pipeline code reads `produced`, `expected` or `pipeline_ok`, so the semantic change to them breaks no consumer. |
| Do other review callers repeat F09? | No. The HTTP task counts only `status == "completed"` (`scheduler_api.py:221`), and so does the paper lane (`paper_lane.py:85`). The startup backfill and the CLI only log. None records a job outcome (decision 5). |
| Is the watchdog part of it? | No watchdog check reads daily-review outcomes (`config/milestones.yaml`, `core/ops/watchdog/checks.py`). So "update the watchdog checks together" has no existing check to update. A new check is SA-034's, and is routed there. |
| Can `pipeline_status` read `not_trading_day` on a scheduled run? | No. The review date is `trading_days_ago(today, 1)`, and the pipeline checks the same `nse_calendar.is_trading_day`. So the `partial` it would cause cannot arise from the scheduled job. |

## The hard review

**Attempted, expected and completed reconcile.**

- `summarize` builds `by_ticker` from the required list only. Each required ticker gets one
  standing outcome, and an absent one becomes `failed: not harvested`.
- So `completed + degraded + data_gated + skipped + failed == required`, and
  `produced ≤ required`.
- `attempted` sums the per-ticker attempts, so it equals `required` plus the earlier attempts.
- The seeded property test checks this over 400 mixes against an independent derivation. The
  reviewer's probes R2, R3, R5 and R6 check it with hand-derived values.

**Alert suppression cannot hide a missing required outcome**, within the counting.

- The zero-output alert returns early only when `expected <= 0` or `produced > 0`. The partial
  alert returns early only when `produced <= 0` or `produced >= expected`.
- Together they fire for every `0 ≤ produced < required` with `required > 0`.
- A required outcome is "not missing" only when some run of the session wrote the ticker's
  feedback. The store replaces a same-date entry and never removes one, so a later failed rerun
  cannot un-write it.
- Outside the counting, two things remain. Both predate SA-004 or are covered:
  - Alerts are deduplicated per calendar day and kind.
  - F1 below can crash the job before the alerts run. A crash pages through `_on_job_error` →
    `alert_job_crashed` (critical).

**Independent adversarial examples** (the reviewer's own probes, in ignored
`analysis_data/sa004_review/test_reviewer_probes.py`; the real `_daily_review_job`, with scripted
review results):

| Probe | Input | Expected by hand | Result |
|---|---|---|---|
| R2 | Fri: A completed, B `no_envelope`. Mon, the same session: A `no_envelope`, B raises. | A output (earlier run); B missing as `failed: exception`; 1 of 2, `partial`; the alert names B only; attempted 4, runs 2 | as expected |
| R3 | Fri (record mode): A degraded. Mon (enforce switched on): A `data_gated`. | A stays `degraded`, `from_earlier_run`, `this_run: data_gated`; 1 of 1, `ok`, no alert | as expected |
| R5 | The budget expires before either review finishes. | 0 of 2, `failed`; the critical zero-output alert says "failed timeout: A, B"; the pipeline still runs | as expected |
| R6 | Three runs of one session | runs 3, attempted 6, produced 2 | as expected |
| R4 | The same symbol listed enabled and disabled | (observed) | required once, and also listed in `excluded`; see I1 |
| R1 | A same-session previous record, valid JSON with wrong types | (observed) | the job raises before the pipeline; see F1 |

## Findings

| ID | Severity | Location | Evidence | Disposition |
|---|---|---|---|---|
| F1 | Low (confirmed by reproduction) | `services/scheduler/python/scheduler.py:893-897`; `review_outcomes.py:152` and `:171` | R1: see below | Routed to [SA-036](../stories/SA-036.md) |
| I1 | Info | `scheduler.py` dedupe; `log_buffer.get_disabled_tickers` | R4: a symbol listed twice, once `enabled: false`, is required and reviewed, and also appears in `excluded`. Completion is not double-counted. The add API rejects a duplicate (`ui_data.py:3597-3602`), so only a hand-edited managed list can produce it. | Noted on SA-036 |
| I2 | Info | `review_outcomes.timed_out` docstring; `scheduler.py:875` | Production runs `RL_SCHEDULER_MAX_WORKERS` = 1. At a budget expiry, reviews not yet started are reported `failed: timeout` and are then cancelled by `shutdown(cancel_futures=True)`. They never "persist later", as the docstring says a straggler may. The count is right (not output), and the next same-session run retries them. | Noted on SA-036 |
| I3 | Info (predates SA-004, local only) | `tests/unit/test_api_auth_lockdown.py:82` | Every full run flips MARUTI's `enabled` flag in the checkout's real `data/managed_tickers.json`. The test sends an authorised `PATCH /ui/tickers/managed/MARUTI/toggle`, and `ui_data.py:3726-3733` saves it. The file was rewritten at 15:38:35 during this review's full run, and it now holds MARUTI enabled, TCS and HDFCBANK disabled. The test dates from 2026-07-16. It matters more since SA-004, because unpatched scheduler tests now also read `get_disabled_tickers()` from that file. Production is not affected. | Routed to [SA-005](../stories/SA-005.md) |

**F1, in one example.** It is Fri 2 Oct, the day after 1 Oct, and the first run has written a
`daily_review` record for 1 Oct. Suppose that record were valid JSON with a wrong type, for
example `"attempts": [1]` for one ticker or `"runs": "two"`. On Mon 5 Oct:

- the reviews run;
- then `ro.summarize` raises `TypeError` or `ValueError` while merging;
- the job crashes before the alerts, the portfolio pipeline (advisor → autopilot → digest) and
  the outcome write.

The crash pages through `alert_job_crashed`. But that day's pipeline does not run, and
`/scheduler/status` keeps showing Friday's record. Probe R1 reproduces two of three shapes: pipeline
calls 0, record not rewritten. The third, an `outcome` given as a list, is never evaluated
when the current run completed.

- **Why it matters:** AUD-084's invariant is that "the tail must run regardless"
  (`test_daily_review_job_survives_harvest_timeout`). Before SA-004 the code between the harvest
  and the tail did only integer arithmetic. Now it reads a persisted file.
- **Why it is low:** the only writer is this code, and it writes integers. A trigger needs a hand
  edit or a future schema change, plus a same-session rerun.
- **Fix, for SA-036:** wrap the summarize, detail and log block. On an exception, log it, and fall
  back to `summarize(..., previous=None)`, which cannot fail on the file. Add R1 as a test.

**The implementer's five decisions:** the review agrees with each.

1. `degraded` counts as output. In record mode the review wrote feedback and learned.
2. Alerts use the merged cohort. The required outcome is the session's feedback entry. A failed
   rerun's own failures stay in `this_run` and the ERROR logs. The rerun's learning side is
   F10's, routed to SA-015.
3. `pipeline_ok` is false when a review failed. That is the acceptance criterion's wording.
4. `empty` is not an alert. `load_managed_tickers` bootstraps a missing, empty or corrupt file,
   so an empty cohort means every ticker was disabled on purpose. Before SA-004 it did not alert
   either (`expected=0`).
5. One job only. The other callers record no outcome, and they already count only `completed`.

## Tests would fail for the original defect

The reviewer's own runtime mutations (`analysis_data/sa004_review/revmut.py`) change no source
file. Each was run against the two new files (61 tests):

| Mutation | Failing |
|---|---|
| none | 0 (61 passed) |
| `base`: the **baseline** `scheduler.py` (F09 itself) executed into the loaded module | 30 |
| `f09`: any result that did not raise is `completed` (keeps the new record shape, so the failures are on values) | 34 |
| `pok`: `pipeline_ok` ignores failed reviews | 13 |
| `nomrg`: a rerun never merges | 4 |
| `late`: a finished but unyielded review is treated as a timeout | 1 |

The tests' expected values are written out by hand, or derived independently from the raw inputs
(the property test). The integration test runs the real `run_daily_review`, and it compares the
record with the stored `FeedbackEntry` rows. It blocks the network through `no_network`, and the
reviewer's runs add `-p nonet`. The one existing test that changed
(`test_scheduler_portfolio_hook.py`) was not weakened. Its old fixture had both reviews finished,
and it passed only by dropping a finished review, which is the behaviour SA-004 fixes. Its
assertions (1 of 2, the pipeline still runs) are unchanged.

## Commands, environment and results

Windows 11, Python 3.13.11 (`.stockai` venv), `RL_LEARNING_MODE=adapt`, and the network guard
`-p nonet` on every pytest run (`PYTHONPATH=analysis_data/sa004`; the reviewer read the plugin
first).

```text
kt_manifest.py verify SA-004-manifest.json (15:24)       -> 13 files, 0 mismatches, a5e77a74...
reviewer's diff rebuild                                  -> 648b7b68..., 82,557 bytes, 12 files
focused: the receipt's 36 existing + 2 new files         -> 376 passed, 0 failed (89 s); nonet blocked 182, all from existing files
new files under 5 reviewer mutations (+ unmutated)       -> 61 passed unmutated; 30 / 34 / 13 / 4 / 1 failing
pinned to Mon 28 Sep and Fri 2 Oct (pinday4; new files + portfolio hook)
                                                         -> 71 passed each day
reviewer probes (analysis_data/sa004_review)             -> 8 passed; nonet blocked 0
full tests/unit (15:36-15:40)                            -> 3502 passed, 1 failed, 5 skipped (284 s); nonet blocked 194, the pre-existing set
  the failure: test_delivery_api.py::test_push_subscribe_caps_store_size, PermissionError [WinError 5] in os.replace
  of a pytest tmp file (the known Windows rename flake, SA-002 review T3, routed to SA-005); alone: 5 of 5 passed
  tracked data/ clean; data/nse/key_registry.json unchanged; data/scheduler_job_outcomes.json untouched (still 08:42)
check_kt_docs.py (15:36, before the status edits)       -> errors []
build_kt_pdf.py; check_kt_docs.py (after the status edits)
                                                         -> PDF source bf3d73d3..., 24 pages; errors [] (353 links, 51 stories, 24 job IDs, 13 config claims)
kt_manifest.py verify (after the status edits)           -> mismatches exactly the 5 status-edited payload files (KT, PDF, ARCHITECTURE, TEAM_TESTING_GUIDE, CODEBASE.md)
```

**Not exercised.** The following were not run:

- a real production cohort, which needs deployment;
- the Fri 2 Oct / Mon 5 Oct holiday rerun live;
- the HTTP trigger, the startup self-heal and the CLI, which record no outcome;
- a real multi-worker harvest timeout. The tests simulate the budget expiry deterministically.

## Acceptance checklist

- [x] **20 attempts with one `no_envelope`** give 19 completed, 1 skipped and an incomplete required
  cohort: `test_twenty_attempts_with_one_no_envelope`, and the code read line by line.
- [x] **Exceptions and malformed results cannot produce `pipeline_ok=true`:** the property test,
  8 malformed review shapes, 4 pipeline shapes, and the `pok` mutation (13 failing).
- [x] **Retries and intentional excluded symbols are reported without double-counting
  completion:** the rerun, full-rerun, excluded and duplicate tests, the integration rerun, and
  probes R2, R3 and R6.
- [x] **Evidence:** mixed statuses, all-skipped, all-failed, empty universe, duplicates and a
  partial rerun are each tested. The integration test checks the persisted record against the
  stored feedback IDs.
- [x] **Hard review:** the arithmetic reconciles, and within the counting, alert suppression
  cannot hide a missing required outcome. F1 is the one path that skips the alerts, and there the
  crash itself pages.
- [x] **Documentation:** KT §1, §5, §9, §11 and §12, ARCHITECTURE, cases 01-A, 01-B and 01-F, and
  `CODEBASE.md` describe the reviewed behaviour. After acceptance, the status wording is updated
  (see HANDOFF).

## Decision and follow-up state

- **SA-004: `done`.** The code and docs are accepted for review input `a5e77a74…` (diff
  `648b7b68…`), and for payload update 1, `5d9030e0…` (diff `e16a8e3f…`). This review committed,
  pushed and deployed nothing.
- **`production_verification`: `pending_deployment`.** After the owner's commit and push, verify
  read-only across one scheduled session, as the receipt's "Rollout" says:
  - `by_ticker` holds every enabled ticker once;
  - the five counts add up to `required`;
  - `produced` equals the tickers whose `feedback_log.last_date` is the review date.
- **If deployed before Fri 2 Oct,** Mon 5 Oct's record for 1 Oct should read `runs: 2`, with
  `attempted` twice `required`.
- **At commit:**
  - link `core/intelligence/rl/workflows/review_outcomes.py` in the KT, and bump the KT header
    past `167f08b`;
  - `verify SA-004-manifest.json --rev <commit>` should then mismatch only the status-edited and
    planning-edited docs.
- **Routed:**
  - F1, I1 and I2 → [SA-036](../stories/SA-036.md);
  - I3 → [SA-005](../stories/SA-005.md).

  The implementation's routes to SA-005, SA-015, SA-034 and SA-036 stand.
- **Status-wording edits by this review (documentation only):** "implemented, awaiting its fresh
  review" becomes "accepted by its fresh review on 2026-09-27; uncommitted". This covers KT §1, §5,
  §9, §11 and §12, ARCHITECTURE, cases 01-A and 01-F, `CODEBASE.md` and the SA-034 note. The PDF
  is rebuilt. `verify SA-004-manifest.json` therefore mismatches exactly those status-edited
  payload files after this review.

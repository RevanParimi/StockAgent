# SA-004 implementation receipt — count daily-review outcomes truthfully

> **Accepted on 2026-09-27 by a fresh-session review:** see [SA-004-review.md](SA-004-review.md).
> It covers review input `a5e77a74…` and payload update 1, `5d9030e0…`. There are no critical, high
> or medium findings. F1 (low) is routed to SA-036, and I3 (info) to SA-005. The status lines
> below are this phase's record.

- **Story:** [SA-004](../stories/SA-004.md). Audit finding F09 in the
  [September audit](../../../audit/2026-09-10-repository-production-review.md).
- **Phase:** implementation, one conversation, 2026-09-27 about 11:45–12:40 IST. It includes a
  same-conversation self-review, which is **not** the fresh-session review. STATE:
  `review_required`.
- **Baseline:** `0a5bf9e15b6d6a9c43ac9f66106a5583a9c75ea5`, the previous conversation's deploy
  record (committed locally, unpushed). The tree was clean. SA-003 is in `167f08b`, pushed and
  deployed (deploy `0106fc89`).
- **SA-039 checks:** none was due. P1 is Mon 28 Sep after 17:00 IST.
- **Review input:** [SA-004-manifest.json](SA-004-manifest.json), currently `5d9030e0…`
  (payload update 1, documentation only). Its SHA-256 and the diff digest are under "Manifest and
  digests".

## What it does, in one example

The production record of 2026-09-08 (audit F09): 20 enabled tickers, and WELCORP has no envelope.

| | Before | After |
|---|---|---|
| WELCORP's review | returns `no_envelope`; counted as output | `skipped`, reason `no_envelope` |
| The record | `produced=20`, `expected=20`, `pipeline_ok=true` | `produced=19`, `expected=20`, `status: partial`, `missing: {WELCORP: "skipped: no_envelope"}` |
| Alerts | none (20 of 20) | partial-output warning: "Job 'daily_review' completed 19/20 — missing: skipped no_envelope: WELCORP. Check logs." |
| Feedback rows for the day | 19 | 19, and `produced` now equals them |

This exact case is `test_twenty_attempts_with_one_no_envelope`. The integration test runs the real
`run_daily_review` for six tickers and checks the persisted record against the feedback rows
actually stored.

## The contract

Every required ticker (each enabled managed ticker, once) gets exactly one outcome, from the new
`core/intelligence/rl/workflows/review_outcomes.py`:

| Outcome | When | Writes feedback? |
|---|---|---|
| `completed` | `status: completed`, empty `data_gate` | yes |
| `degraded` | `status: completed` with SA-003 record-mode `data_gate` rows | yes |
| `data_gated` | `status: data_gated` (SA-003 enforce) | no |
| `skipped` | `no_envelope`, `no_forecast_row` or `no_actual_data` | no |
| `failed` | the review raised; a malformed result (not a dict, no or unknown status, another ticker or date); still running when the harvest budget ran out; or never harvested | no |

- **Output is feedback.** `produced` = completed + degraded, the reviews that wrote a feedback
  entry. The zero- and partial-output alerts take `produced` against `required`, so a skip, a gate
  stop, an exception, a malformed result or a timeout cannot quiet them. Both alerts gain an
  optional `detail` naming the missing tickers and why. Without it, the old text is unchanged.
- **Required and attempted are separate.** `required` = distinct enabled tickers; `attempted` =
  review runs for the session, across runs. Invariant: the five counts add up to `required`.
- **Excluded and duplicates.** Disabled managed tickers (`enabled: false`) are listed in
  `excluded` and are never required or reviewed. A duplicate managed entry (same symbol after
  trim and upper-case) is reviewed once and listed in `duplicates`. Before, it was reviewed twice
  and counted twice.
- **A rerun of the same session merges.** Suppose the previous record names the same
  `review_date` and has `by_ticker`. The second run then merges with it:
  - attempts add up, and `retried` and `runs` say so;
  - a ticker counts as output if either run wrote its feedback;
  - `by_ticker[t].this_run` keeps what this run did, and `from_earlier_run` marks a standing
    outcome carried from the earlier run;
  - a legacy record, or one for another date, merges nothing.
- **Job status.** `with_pipeline` adds:
  - `status`: `empty` when nothing was required, `failed` when nothing was produced, `ok` when
    every required ticker produced and the pipeline completed (or is disabled), and `partial`
    otherwise;
  - `pipeline_status`: `completed`, `disabled`, `not_trading_day`, `failed` or `malformed`;
  - `pipeline_ok` (legacy): true only when the pipeline returned a well-formed `completed` and no
    required review stands failed.
- **Harvest.** After the aggregate `TimeoutError`, a finished but unyielded future is harvested.
  Before, it was neither output nor a straggler. A future still running is a `failed: timeout`
  and a straggler.
- **Kept additively.** `review_date`, `produced`, `expected`, `stragglers`, `pipeline_ok`,
  `pipeline_error` and the news counters.

## For the reviewer: decisions to check

1. **`degraded` counts as output.** A record-mode review with `data_gate` rows wrote feedback and
   learned. Counting it as missing would page every day until the October envelopes. Until then,
   most reviews grade a row issued before the gate existed. So `degraded` is output, reported
   separately. In enforce mode the same review is `data_gated` and is not output (SA-003's routed
   note).
2. **Alerts use the merged cohort, not this run.** Take a second scheduled run of the same session
   that fails everywhere, after the first completed. It reads `ok` and does not page, because
   every required feedback entry exists. Its failures are in `this_run`, `by_ticker[t].this_run`
   and the ERROR logs. A provider outage there is caught by the LLM failure-streak alert. Routed
   to SA-034 so that no check reads `produced` alone.
3. **`pipeline_ok` false on a failed review.** Acceptance 2 says exceptions and malformed results
   cannot produce `pipeline_ok=true`. So a pipeline that completed next to a failed review reads
   `pipeline_ok: false`, `pipeline_status: completed`. A skip (for example `no_envelope`) leaves
   `pipeline_ok` true, and it shows in `status`, the counts and the alert.
4. **`empty` is not an alert.** A missing or corrupt managed-ticker file bootstraps from settings
   (`load_managed_tickers`). An empty cohort therefore means every ticker is disabled on purpose.
   The record says `empty` and lists them in `excluded`.
5. **One job only.** The HTTP trigger (`POST /scheduler/daily-review`), the startup self-heal
   backfill and the CLI record no job outcome, before or after. So a manual rerun is not merged.
   Routed to SA-036, which owns outcomes for every job.

## Acceptance criteria

- **20 attempts with one no_envelope: 19 completed, one skipped, an incomplete required cohort.**
  `test_twenty_attempts_with_one_no_envelope`: `produced` 19 of `required` 20, `skipped` 1,
  `cohort_complete: false`, `status: partial`, and exactly one partial-output alert with the text
  above.
- **Exceptions and malformed results cannot produce `pipeline_ok=true`.**
  - Review side: 8 malformed shapes (`test_a_malformed_review_result_never_reads_ok`), all-failed
    and mixed runs.
  - Pipeline side: `None`, a string, an unknown status, and a raise
    (`test_a_malformed_or_raising_pipeline_is_not_ok`).
  - The seeded property test asserts, over 400 random mixes, that `pipeline_ok` is true only with
    a completed pipeline and no standing failure.
- **Retries and intentional excluded symbols are reported without double-counting completion.**
  - `test_a_partial_rerun_of_the_same_session_merges`: 3 required, 6 attempted, 3 produced, and
    all three `retried`.
  - `test_a_full_rerun_does_not_double_count_completion`: 2 produced, 4 attempted.
  - `test_excluded_symbols_are_reported_not_required` and
    `test_duplicate_entries_are_reviewed_and_counted_once`.
  - The integration rerun: the same six tickers twice, the real store holds one row per
    ticker-date, and `produced` is unchanged.

**Evidence the card asks for:** mixed statuses, all-skipped, all-failed, empty universe,
duplicates and a partial rerun each have a test. The integration test checks the persisted
scheduler record against the stored feedback IDs (`ticker|date` of every `FeedbackEntry` dated
the session) in record mode, on a rerun, and in enforce mode.

**Independent invariants.** Expected values are written out by hand, or re-derived in the test
from the raw inputs. For example, the property test computes "has output" as "either run wrote
feedback", without calling the module. `test_every_review_status_is_classified_deliberately`
reads `daily_review.py`'s own status literals: a new early return must be classified on purpose,
and until then it counts as `failed`.

## Tests: commands, environment, results

Environment: Windows 11, Python 3.13.11 (`.stockai` venv), pandas 3.0.2, `RL_LEARNING_MODE=adapt`.
Every pytest run used the network guard `-p nonet` (a copy in ignored `analysis_data/sa004/`),
which fails any non-loopback connection and reports what it blocked.

```text
PYTHONPATH=analysis_data/sa004 RL_LEARNING_MODE=adapt .stockai/Scripts/python.exe -m pytest \
  -q -p no:cacheprovider -p nonet <files>

new SA-004 files (2)                                   -> 61 passed; blocked 0
focused: 36 affected existing files + the 2 new        -> 376 passed, 0 failed (2 min 50 s); blocked 182, all from existing files
runtime mutations (13, mutate4.py)                     -> 13 of 13 caught; unmutated 61 passed
7-day sweep (pinday4.py; SA-004 + scheduler + alert + outcome files, 91 tests)
                                                       -> 6 of 7 days 91 passed; Tue 1 known flake, then 3 of 3 passed; see below
full tests/unit                                        -> 3503 passed, 5 skipped, 0 failed (8 min 38 s); nonet blocked 194, the pre-existing set (SA-002, SA-003: 194); tracked data/ clean, data/nse/key_registry.json unchanged
build_kt_pdf.py; check_kt_docs.py                      -> PDF source 3e4c64af..., 23 pages; check_kt_docs errors [] (334 links, 47 stories, 24 job IDs, 13 config claims)
```

**Focused.** The two new files, plus 36 existing files that touch the scheduler, alerts, job
outcomes or the managed-ticker list, or that run the real `run_daily_review`. They include:

- the scheduler job tests: news telemetry, portfolio hook, IPO refresh, IPO deep dive, delivery
  jobs, preopen, scorecard, distill hook, research loop and event ingest;
- `tests/contract/test_scheduler.py` and `tests/test_scheduler.py`, which are outside
  `tests/unit`;
- ops alerts, job outcomes, wave-F alerts, delivery alerts, the audit scheduler job and its
  monthly section, the watchdog job, and atomic-io adoption;
- the review tests: SA-003 learning, shock path, SA-039 learning mode, paper lane, hard bind,
  dossier, lesson evidence, macro fallback, news availability and absurd price error.

The exact file list and every command behind these figures are in the ignored
`analysis_data/sa004/final_runs.sh`, which may be missing in another checkout.

**Mutations.** `analysis_data/sa004/mutate4.py` puts back one replaced behaviour at
`pytest_configure`. No source file is edited. Module functions are wrapped. Scheduler mutations
exec a mutated copy of `scheduler.py`'s source into the loaded module.

| Mutation (the behaviour put back) | New tests failing |
|---|---|
| m1: F09 itself, any result that did not raise is output | 28 |
| m2: a skip counts as output | 7 |
| m3: a gate stop counts as output | 3 |
| m4: an unknown status is taken as completed | 7 |
| m5: returning is success, any pipeline result is `completed` | 11 |
| m6: `pipeline_ok` ignores failed reviews | 13 |
| m7: a rerun replaces the earlier record | 4 |
| m8: completion double-counted across runs | 4 |
| m9: a missing outcome shrinks the cohort | 2 |
| m10: a finished but unyielded review is dropped at the timeout | 1 |
| m11: duplicates reviewed and counted twice | 1 |
| m12: disabled tickers counted as required | 2 |
| m13: the alerts count every returned review | 11 |

**The 7-day sweep.** The two new files and the four existing scheduler, alert and outcome files
(91 tests) run as if on each day from Sun 27 Sep to Sat 3 Oct 2026. That span covers the month
rollover and the 2 Oct holiday. `pinday4.py` pins `date.today()` in the 10 modules on the review
path that read it; the job's own clock is pinned by the tests.

- 6 of 7 days passed first time.
- Tue 29 Sep failed `test_ops_alerts.py::test_llm_failure_streak_alerts_once` once. That test
  covers the LLM failure streak, which SA-004 does not touch, and the failure matches the known
  Windows rename flake (SA-002 review T3: "`test_ops_alerts` loses its streak when a save fails").
  Tue re-run 3 times: 91 passed each.

**Existing tests changed** (`tests/unit/test_scheduler_portfolio_hook.py`):

- The two alert stubs accept the new `detail` keyword.
- The harvest-timeout test now makes INFY genuinely unfinished; it blocks on an event.
  - Before, both futures were finished and only one was yielded. The old code dropped the second
    and asserted 1 of 2.
  - SA-004 harvests a finished review, so the fixture now models a real straggler. The assertion
    (1 of 2, the pipeline still runs) is unchanged.

**Test isolation added** (`tests/conftest.py`): `_no_real_job_outcome_writes` redirects
`job_outcomes._OUTCOMES_PATH` to the test's tmp dir, the same rule as SA-003's gate log.

- The daily-review job tests wrote the checkout's real `data/scheduler_job_outcomes.json`. It was
  last written 27 Sep 08:42, during the SA-003 review's full run.
- Since SA-004 the job also reads that file, so a leftover record would have leaked between
  tests.
- After this conversation's runs, the file is unchanged.

## Documentation

- **KT** (`docs/TECHNICAL_DESIGN.md`):
  - §1 status row;
  - §5, the `data_gated` sentence;
  - §9, a new "Daily-review outcomes" paragraph with the WELCORP example, the five outcomes, the
    rerun rule, `status` and `pipeline_ok`, and what stays open;
  - §11 Operations row and §12 status line.

  The PDF is rebuilt. `review_outcomes.py` is named in code formatting, not linked, because it is
  absent at the header revision `167f08b` (see "At commit").
- `docs/ARCHITECTURE.md`: the operations row.
- `docs/TEAM_TESTING_GUIDE.md`: 01-A and 01-B get concrete expectations against
  `last_runs.daily_review`. New 01-F covers a rerun of the same session.
- `CODEBASE.md`: the source tree, the `/scheduler/status` row, the `ops_alerts.py` line and a file
  row for `review_outcomes.py`.
- **Bookkeeping, outside the manifest:** STATE.json, HANDOFF.md, this receipt, the manifest, and
  routed notes on the SA-005, SA-015, SA-034 and SA-036 cards.

## Open limitations

- **The pipeline's own `completed`** does not count holdings whose advisor call failed inside it:
  each is caught and logged, and it still returns `completed`. Routed to SA-036.
- **A straggler that finishes after the record is written** is not reflected until the next run
  of the same session. The review persists, as AUD-084 intends. The record says `failed: timeout`.
- **The learning side of a rerun is not changed.** Every weekday holiday makes one: Fri 2 Oct and
  Mon 5 Oct both review Thu 1 Oct, because the Mon–Fri cron does not skip a holiday. SA-004 counts
  both runs as one cohort. The second run's learning writes are F10's. Routed to SA-015 with the
  dates.
- **No watchdog check reads this record.** Routed to SA-034: read `status`, `cohort_complete` and
  `missing`, not `produced`.
- **Unpatched existing scheduler tests** now also call `get_disabled_tickers()`, which reads the
  checkout's `data/managed_tickers.json`. The read is read-only. A missing file bootstraps from
  settings, as any unpatched `get_active_tickers_with_sector()` call already does. Noted on
  SA-005.

## Rollout (owner, after acceptance, commit and push)

1. The change is additive to `scheduler_job_outcomes.json`, and no migration is needed.
   - The first record after the deploy never merges with the pre-SA-004 one, which has no
     `by_ticker`.
   - Expect partial-output alerts on days a ticker skips. That is the point: WELCORP's
     `no_envelope` would have paged on 8 Sep.
2. **Verify read-only across one scheduled session.** Read `/scheduler/status` →
   `last_runs.daily_review`, and check these three things:
   - `by_ticker` holds every enabled ticker once;
   - the five counts add up to `required`;
   - `produced` equals the tickers whose `feedback_log.last_date` is the review date. The same
     response lists that date per ticker.
3. **Fri 2 Oct / Mon 5 Oct.** If SA-004 is live by then, Monday's record should read `runs: 2`
   for 1 Oct, with `attempted` twice `required`.
4. **Rollback:** revert the commit. The legacy fields keep their names. `produced` returns to
   counting every review that returned.

## At commit

The KT names `core/intelligence/rl/workflows/review_outcomes.py` in code formatting. The commit
that lands SA-004 should link it and bump the KT header past `167f08b`, because `check_kt_docs.py`
fails on a link to a source file absent at the header's revision.

## Payload update 1 — 2026-09-27, owner-requested backlog (no SA-004 change)

After the implementation, in the same conversation, the owner reviewed the live portfolio screen
and asked for four board stories: SA-048, SA-049, SA-050 and SA-051. `check_kt_docs.py` requires a
KT §12 row for every STATE story, so four files in this review input changed:

- **KT:** the §1 story range; a "Where cash goes" paragraph in §6 and a costs paragraph in §7
  (current code, with the planned stories); the §11 portfolio row; four §12 rows.
- **PDF:** rebuilt from source `98239426…`, 24 pages; `check_kt_docs` reports 0 errors and 51
  stories.
- **ARCHITECTURE:** the portfolio row.
- **TEAM_TESTING_GUIDE:** new PI-target cases 07-F, 07-G, 08-F and 08-G, and the "Related PI"
  lines.

**Code and tests are byte-identical** to the first review input. The manifest was regenerated:
`kt_manifest.py verify` gives 0 mismatches, and exactly these four blobs differ from the first
input.

**To separate the backlog edit from SA-004's own changes,** diff each file's previous blob against
the current file. The previous blobs are stored in this checkout's object database, and each
rebuild was checked against the first manifest's blob id:

| File | First review input | Now |
|---|---|---|
| `docs/TECHNICAL_DESIGN.md` | `a9c89010` | see the manifest |
| `docs/StockAgent-Three-Loops.pdf` | `b54a6a5d` | `861711fa` |
| `docs/ARCHITECTURE.md` | `24a9d0f9` | see the manifest |
| `docs/TEAM_TESTING_GUIDE.md` | `0ce916f6` | see the manifest |

For example, run `git show a9c89010 > old.md` and diff `old.md` with the current KT.

## Manifest and digests

The current review input is payload update 1 (the section above). The first input's figures
follow the table.

- **Review input (current):** [SA-004-manifest.json](SA-004-manifest.json), SHA-256 of its LF
  bytes **`5d9030e0ffe7cc997a5c2bc2100a8c046f443cdcd1672b698519e79853f8e661`**. The full diff
  against `0a5bf9e` is **`e16a8e3f47de65b78a0deef5c641fba4377f5d11deb5b717259da359c25a0edc`**,
  91,343 bytes over 12 text files. The PDF blob is `861711fa…`.

| Input | Review input SHA-256 | Diff SHA-256 | Bytes | PDF blob |
|---|---|---|---:|---|
| First (implementation) | `a5e77a74…` | `648b7b68…` | 82,557 | `b54a6a5d…` |
| Payload update 1 (current) | `5d9030e0…` | `e16a8e3f…` | 91,343 | `861711fa…` |

The first input's figures, as originally recorded:

- **Review input:** [SA-004-manifest.json](SA-004-manifest.json), 13 paths:
  - 4 code files, 1 of them new (`review_outcomes.py`); the others are `scheduler.py`,
    `log_buffer.py` and `ops_alerts.py`;
  - 4 test files, 2 of them new; the others are `tests/conftest.py` and
    `test_scheduler_portfolio_hook.py`;
  - 5 documentation files, including the PDF.

  The SHA-256 of its LF bytes is
  **`a5e77a74ec7511e5d137c32a57e74929183f53680f43b4df82226dc230bb9e7e`**. `kt_manifest.py verify`
  gives 0 mismatches.
- **Excluded,** because they are written after the manifest: STATE.json, HANDOFF.md, this
  receipt, and the SA-005, SA-015, SA-034 and SA-036 cards.
- **Full diff** against `0a5bf9e`:
  **`648b7b6833af4d6c26c0b397ef46d3cd53769d90bc3f6847401521636514f712`**, 82,557 bytes over 12
  text files. The PDF is pinned by its blob, `b54a6a5d…`.
- **To rebuild the diff:** take every manifest path except the PDF, sorted.
  - For a path tracked at the baseline, run `git diff --no-color --no-ext-diff 0a5bf9e -- PATH`.
  - For a new file, run `git diff --no-color --no-ext-diff --no-index -- /dev/null PATH`.
  - Concatenate the bytes. The ignored `analysis_data/sa004/sa004_diff.py` does exactly this.
- **After the commit:** `verify --rev <commit>` compares against the commit instead.

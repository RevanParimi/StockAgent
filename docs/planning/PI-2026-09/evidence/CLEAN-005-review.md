# CLEAN-005 — fresh review receipt

**Story:** [CLEAN-005](../stories/CLEAN-005.md): remove the backup analysis and the old
per-analyst layer it runs on. Implementation receipt:
[CLEAN-005-implementation.md](CLEAN-005-implementation.md).

**Review context: fresh session.** Autopilot session `1120-1139-p2` on the code-server, a new
conversation opened with "continue", Friday 20 Nov 2026 from about 11:39 IST, outside a push
window. The implementing session (`1120-1045-p1`) had ended at 11:39 IST. `main` = `7ad7fad`
(records only on top of `03debc1`), `origin/main` = `03debc1` after a fetch. Production was not
read. No model was called; nothing was pushed, deployed, run or sent.

**Lane:** decision path, confirmed. Step 1 changes what an analysis returns when the one model
call fails, and the 16:30 review, the monthly forecast and the deep dive act on analyses.

**Verdict: ACCEPTED** for `e51b0c7`. Every acceptance criterion is met. One low finding (the
failure reason names three attempts after a provider error that is not retried) and three nits
(two test gaps, stale comments) go to BACKLOG B-27. Merged into `main` as `f6b2055`.

## Review input, verified

| Check | Result |
| --- | --- |
| Branch | `story/CLEAN-005` = `e51b0c7`, two commits on `03debc1` (`git merge-base main story/CLEAN-005`): `b6744a6` step 1, `e51b0c7` step 2 |
| Diff digest | `git diff 03debc1 e51b0c7 \| sha256sum` = `2ffb7453330a4494…` = the implementation receipt |
| Files | 143 files, +1,232 / −6,863, as the receipt says |
| Where it ran | a detached worktree of `e51b0c7` in the scratchpad (the full suite), and a second one for the reviewer mutants |
| Merge | `git merge-tree --write-tree main story/CLEAN-005`: clean. `main`'s two commits since `03debc1` change only `docs/planning/` and KT section 1 (production state); the story changes KT sections 3, 4, 9 and 11 |

## Contract checked

I traced a failed model call from `UnifiedAnalyst._call_llm` (three attempts for a timeout, a
rate limit or an unexpected error; one for a provider `APIError`) through `run()` (returns `{}`
and keeps `_last_failure`) or `_parse_all` (every dimension `missing_in_unified_response` or
`parse_error`) to `BaseSectorOrchestrator._run_unified`, which writes the data-health row, and
to `analyse` / `analyse_async`, where `scored_nothing` sends the run to `_no_analysis`: one row in
`data/rl/analysis_failures.jsonl`, the run's API spend, one warning, and `AnalysisUnavailable`
raised before `self._aggregator.run`. So no report object exists for any caller to read.

- **Every caller.** My own `grep` of `.analyse(` and `.analyse_async(` over `core`, `services`,
  `src` and `scripts` finds the seven call sites the receipt lists and nothing else (no indirect
  reference such as `getattr` or `run_in_executor` on either method). Each handles
  `AnalysisUnavailable` or lets it reach a per-stock handler: the deep dive (`continue`, no
  memo), the 16:30 review (`no_analysis` before any write), the forecast and its callers (the
  monthly job, `regenerate_envelope`, the paper lane, and the startup self-heal, the scheduler
  API's forecast route and the hand-run CLI, whose existing broad handlers skip the stock as
  before, since the exception subclasses `RuntimeError`), `run_now`, and the three on-demand
  routes.
- **What a skipped review leaves the advisor.** `run_post_review_pipeline` advises every holding
  whatever the review returned: the stops, targets and crisis exit read the session's price,
  and the research verdict it reads is the latest score-history row within its window. A
  `no_analysis` review writes nothing, exactly like the data gate's stop in `enforce` mode
  (PR-042), so the advisor sees what it sees on a gated day. No exit is blocked.
- **What the review's callers read.** The `no_analysis` summary carries the keys of the gate's
  summary (`status`, `ticker`, `sector`, `paper`, `date`, `learning_mode`) plus `reason` and
  `run_id`. The scheduler's harvest, the startup backfill, the scheduler API and the paper lane
  read only `.get(...)` fields; `review_outcomes.classify` counts it `skipped`.
- **No envelope.** A failed forecast leaves the month without an envelope for that stock, as an
  abstaining analysis already does (`generate_forecast`'s SA-003 branch, "Will retry on the next
  scheduled run"); the startup self-heal retries a missing envelope.
- **Nothing routes elsewhere.** `unified_analyst.sectors` and `fallback_legacy` are gone from
  `config.yaml` and the settings; `_run_agents` calls `_run_unified` only; a path with no spec
  gets `{}` and so no analysis. Every dynamic import in the code (`importlib.import_module`,
  `__import__`) targets a `config.settings` or a `prompts.unified` module, which all five paths
  keep. No requirements file, `pyproject.toml` or the Dockerfile names `langgraph` or
  `langchain`.

## Adversarial examples, worked independently

My own cases (`analysis_data/clean005_review/test_rv_clean005.py`, this device only), through
the real orchestrators of other paths than the story's tests use, with only the model's transport
and the bundle faked, each expectation written from the card:

| # | Case | Expected (from the card) | Result |
|---|---|---|---|
| RV1 | banking/BFSI, async: every dimension answered with `"score": "high"` | no analysis; no aggregation; one row naming 6 of 6 failed | as expected |
| RV2 | generic: the provider answers with no content | no analysis (the analyst reads it as `{}`) | as expected |
| RV3 | IT: one dimension scored, the rest missing | still an analysis: reaches the aggregator, no failure row | as expected |
| RV4 | renewables: rate-limited on every attempt | no analysis after 3 calls, the reason names `RateLimitError` | as expected |
| RV5 | automobile: a provider `InternalServerError` | no analysis after **1** call | as expected, but the reason says "failed after 3 attempts": finding R1 |
| RV6 | eight failing analyses on eight threads at once | eight rows, the count reads 8 | as expected |
| RV7 | a failure at 01:30 IST on the 21st, counted at once and then on the 22nd | 1, then 0 | as expected (the story's own IST test cannot tell IST from UTC: N1) |

## Tests and the original defect

- The story's invariant tests run the real orchestrator and the real one-call analyst with only
  the model client faked, and read their results from outside the code under test: the failure
  file with plain JSON, the score database with `sqlite3`, the review's store as SHA-256 of every
  file. No test reaches the network (the hermetic boundary, SA-005).
- **Reviewer mutants: 14 of 16 caught** by `test_no_analysis_clean005.py`,
  `test_orchestrator_unified_branch.py`, `test_daily_review_outcomes_sa004.py`,
  `shared/test_data_health_record.py` and `test_search_shadow_pr043.py` (184 tests). Caught:
  either entry point ignoring a run that scored nothing; `any` for `all` in `scored_nothing`;
  errored outputs counted as scored; `_no_analysis` returning instead of raising; a backup of
  neutral, unerrored outputs; the review swallowing the failure (the old `{}` path); the review
  status dropped from the skip list; `/analyse`, the stream and the chat tool falling to their
  generic handlers; the re-forecast and the monthly job logging a second time; the failure not
  recorded. **Missed:** the day's count by UTC day (N1) and the deep dive logging the failure a
  second time (N2). Each was put back after its run; the worktree was clean at the end.

## Findings

| # | Severity | Where | What | Disposition |
|---|---|---|---|---|
| R1 | low | `src/backend/shared/pipeline/unified_analyst.py` `_call_llm` (`raise ModelCallFailed(retries, last_error)`) and `_failure_reason` | A provider `APIError` (an HTTP 4xx or 5xx) stops after the first attempt, but the reason recorded in `analysis_failures.jsonl` and the warning say "the model call failed after 3 attempts (InternalServerError)". The owner reading it would believe two retries were made. Moves no buy, sell, size or grade | [BACKLOG](../BACKLOG.md) B-27 |
| N1 | nit (test gap) | `tests/unit/test_no_analysis_clean005.py` `test_the_count_is_by_ist_day` | Its two counting instants fall where the UTC and IST days agree, so a count by UTC day passes. The code counts by IST (RV7 pins it) | B-27 |
| N2 | nit (test gap) | `test_the_deep_dive_mints_no_idea_and_carries_on` | No log assertion, so the deep dive logging a failed stock a second time (its generic handler) passes. The code logs once | B-27 |
| N3 | nit | comments in `services/clients/llm_client.py:6`, `services/data/fetchers/macro.py:222`, `core/intelligence/rl/agents/feedback_agent.py:6`, `src/backend/shared/pipeline/signal_aggregator.py:78`; `docs/PRODUCT_MAP.md:114` ("legacy agents" on the bulk model) | They still name `BaseAgent`, `ContextBuilder` or the legacy agents, which this story deleted | B-27 |

None found against the card's contract: no analysis that scored nothing reaches a verdict, a
score row, a gate row, an envelope, a feedback row or an idea; no setting can route to another
method; the user-facing routes show no verdict and no score.

## Living documents

KT section 4 ("When the analysis fails", with its example), the store table (section 3), the
sector benchmarks and decision gate (section 4), the review outcomes (section 9) and section 11
describe the reviewed behaviour; `PRODUCT_MAP`, `CODEBASE`, `AGENTIC_DESIGN` section 11,
`ARCHITECTURE`, `README`, `docs/README.md` and the testing guide (new case 02-Q) match it, except
N3's one table cell. The PDF is not regenerated (AGENTS.md, owner's rule of 17 Nov 2026). Guide
case 02-Q's label is updated with this review.

## Commands and results

Python 3.13.5 (`.stockai/bin/python`), detached worktrees of `e51b0c7`.

```
git diff 03debc1 e51b0c7 | sha256sum
git merge-tree --write-tree main story/CLEAN-005
.stockai/bin/python -m pytest -q                       # full suite at e51b0c7
.stockai/bin/python -m pytest -q analysis_data/clean005_review/test_rv_clean005.py  # copied into the worktree's tests/unit
.stockai/bin/python analysis_data/clean005_review/mutants.py <worktree>
.stockai/bin/python scripts/ci/check_broad_except.py
.stockai/bin/python scripts/docs/check_kt_docs.py
```

- **Full suite at `e51b0c7`:** **6,858 passed, 5 skipped, 1 xfailed, 0 failed** (9 min 39 s, 11:41–11:51 IST), the implementation receipt's count.
- **Reviewer cases:** 7 passed (RV1–RV7).
- **Focused suites for the mutants:** 184 passed unmutated.
- **Broad-except guard:** OK (138 grandfathered). **`check_kt_docs.py`:** `errors: []`.
- **On the merge commit:** `git diff e51b0c7 f6b2055` touches only `docs/planning/` and KT section 1 (`main`'s production-state paragraph, the same lines as `git diff 03debc1 7ad7fad`), so the code is byte-identical to the reviewed revision; `check_kt_docs.py` `errors: []`.

## Acceptance checklist

- The four requirements of step 1, each with its test: **met** (requirement 4's IST rule is right
  in the code; its test is N1).
- Failure tests through the scheduled and the on-demand entry points (timeout, unparseable,
  missing section, exhausted retry): **met**; RV1–RV6 add a rate limit, a provider error, no
  content and unreadable scores on three more paths.
- No import of a deleted module anywhere: **met** (the AST test, and the dynamic imports read by
  hand).
- A run with a failing model call produces no decision record for that stock: **met**.
- Living documents: **met**, but N3's table cell.
- Nothing pushed or deployed: **met**.

## Production

Not deployed. The next push rebuilds the image without `langgraph`. New check `CLEAN-005-W1`
(STATE `pending_production_checks`): after the deploy, the build succeeded and
`GET /scheduler/status` shows `analyses_failed_today`; after the first 16:30 review, its log holds
no `ModuleNotFoundError` and every "No analysis for" line is matched by a `skipped: no_analysis`
outcome. The inert variables `UNIFIED_ANALYST_SECTORS` and `UNIFIED_ANALYST_FALLBACK_LEGACY`, if
set, can be removed by the owner at any time.

## Decision

**ACCEPTED** for `e51b0c7`; status `done`. Merged into `main` as `f6b2055`; push pending to
the next window (Sat 21 Nov 00:10 IST). Follow-ups: BACKLOG B-27 (R1, N1–N3).

# CLEAN-005 — implementation receipt

**Story:** [CLEAN-005](../stories/CLEAN-005.md): remove the backup analysis and the old
per-analyst layer it runs on. Owner decision of 15 Nov 2026. Profit-path step: **hold** (a held
stock's 16:30 review no longer acts on a verdict from another method when the analysis fails)
and **measure** (the day's failed analyses are counted where the owner looks).

**Lane: decision path.** Reason: it changes what an analysis returns when the main call fails,
and advice, forecasts and grades read analyses (AGENTS.md step 4; the card's own lane).
**Status after this phase: `review_required`.** The next fresh conversation performs the hard
review from `REVIEW.md`; this phase's self-review does not count as it.

## Phase

- **Implementation** (autopilot `1120-1045-p1`, code-server, Fri 20 Nov 2026 from about 10:46
  IST, outside a push window). Baseline **`03debc1`** (`main` = `origin/main`, deployed at
  00:17). The code is on **`story/CLEAN-005`**: **`b6744a6`** (step 1) and **`e51b0c7`**
  (step 2). Only a fresh review's acceptance merges it into `main`.
- Production: the deploy check of the night's push only (its own records commit). Nothing
  pushed, deployed, run or sent by this story.

## Step 1 — "no analysis" instead of a backup analysis (`b6744a6`)

`unified_analyst.fallback_legacy` is off (config and fallback). A run whose analysis scored no
dimension now raises `AnalysisUnavailable` (`src/backend/shared/pipeline/no_analysis.py`) in
`BaseSectorOrchestrator.analyse` and `analyse_async`, before the aggregator.

**"Scored nothing"** [code]: the one call returned no output, or every output carries `error`
(each such output is a fabricated neutral 0.5 the aggregator already excludes). That covers the
card's four failures: a timeout on every attempt, an unreadable answer, an answer naming none of
the dimensions ("missing section"), and exhausted retries. Before this card the third one never
reached the fallback: nine errored outputs went to the aggregator with composite 0.5, the gate
abstained on "dimensions 0/9", and in `record` mode its verdict was used. An answer missing one
dimension is unchanged: it reaches the aggregator and the gate.

**What a failed run writes** [code]: the data-health row (it records the hollow attempt, as
before) and the run's API spend (`log_run_api_usage`). It writes no aggregator call, score-history
row, analysis log, run summary or gate decision, and queues no search shadow (PR-043 queued one
for an all-errored run). It appends one row to `data/rl/analysis_failures.jsonl` and logs one
warning naming the stock and the reason. The analyst now keeps the reason in plain words
(`UnifiedAnalyst._last_failure`; `ModelCallFailed` names the last error), e.g. "the model call
timed out on all 3 attempts".

### Every caller, traced before the switch [code]

The card's line numbers are from 15 Nov; today's are given.

| Caller | Before (an empty or errored analysis) | Now |
|---|---|---|
| Weekly deep dive, `core/discovery/deep_dive.py` `run_deep_dives` (line 192) | An exception: warning, skipped. All-errored: a result with an abstaining gate, kept in the memo, no idea minted | `except AnalysisUnavailable: continue`: no result, no memo entry (a later run can dive it again); the call still counts against the budget |
| 16:30 review's re-analysis, `daily_review.py` `_run_todays_agent_scores` (line 350) | Any exception: `{}`, and the review went on with the envelope's predicted scores and the month-start verdict. A backup verdict was graded against | `AnalysisUnavailable` re-raised; `run_daily_review` returns `no_analysis` at the re-run's own point, the same point and the same nothing-written as the gate's stop (only the market-wide regime state precedes it, as for `no_envelope`). `review_outcomes` counts it `skipped: no_analysis` |
| Monthly forecast, `generate_forecast.py` `_run_orchestrator_analysis` (line 334) | Propagated to the monthly job: ERROR with traceback, next ticker | Propagates; the job's `except AnalysisUnavailable: continue` adds no second log; no envelope |
| Re-forecast, `regenerate_envelope` | ERROR "unhandled failure", `None` | `except AnalysisUnavailable: return None`; the envelope untouched (the archive is a copy) |
| Paper lane, `paper_lane.run_paper_reviews` | warning, `failed` | `failed`, no second log |
| Scheduled analysis, `scheduler.py` `run_now` (line 1541; the manual CLI's run) | ERROR, next ticker | next ticker, no second log |
| `POST /analyse` (`analyse.py` line 62) | 503 "Analysis pipeline failed" | 503 "Today's analysis of TICKER could not be produced: the analysis model gave no usable answer. No verdict or score is shown. Please try again later." |
| Stream (`stream.py` line 134) | error event, generic | error event with `no_analysis: true` and the same sentence (the screen shows `detail` as its error, unchanged) |
| Chat tool (`ui_data.py` line 2118) | "Could not run analysis for X: <exception text>" | the same sentence; no verdict or score to quote |

### The card's four requirements

1. **No caller books a buy, a sell, a size change, a forecast or a grade from an analysis that
   scored nothing.** No report exists to read. Through the real orchestrator and analyst with
   only the transport faked: no aggregator call, no score row (also read from the score
   database itself), no gate row, no backup run, in all four failure modes, sync and async; the
   review writes nothing (every file under the store byte-identical, the feedback agent never
   called, weights at v41); the forecast writes no envelope; a re-forecast leaves the envelope's
   bytes unchanged; the deep dive mints no idea.
2. **A scheduled caller skips the stock, logs it once, carries on:** exactly one warning per
   failed run (the orchestrator's); the monthly job forecasts the next stock; the deep dive dives
   the next candidate.
3. **The user-facing routes say so plainly**, with no verdict and no score: `/analyse` (all four
   modes), the stream and the chat tool.
4. **The count is where the owner looks:** `analyses_failed_today` in `GET /scheduler/status`,
   in the slot `fallback_events_today` had, by IST day (a failure at 01:30 IST counts on that
   day, not the UTC one).

## Step 2 — the layer deleted (`e51b0c7`)

### Proof of non-use, then deletion [code]

A new test parses every tracked `.py` file and fails on any import of a deleted module
(`test_no_tracked_file_imports_a_deleted_module`); `grep` finds no string reference in source,
`config.yaml`, scripts or the Dockerfile; no route or job names any of it (routes reach
orchestrators only through the registry); documents updated below.

| What | Lines |
|---|---|
| The analysts: `src/backend/sectors/{automobile,banking_bfsi,it_sector,renewable_energy}/agents/` (28 files) | 1,307 |
| Each sector's `config/registry.py` (4) | 147 |
| Per-analyst prompts: 25 files under `sectors/*/prompts/` (every one but `unified.py`) | 1,813 |
| `generic/prompts/dimensions.py` (read only by the generic orchestrator's `_sub_agents`) | 74 |
| `shared/pipeline/base_agent.py` and the shim `core/pipeline/base_agent.py` | 451 |
| `shared/agents/` (`UniversalAgent`, the shared technical and institutional prompts) | 428 |
| `services/data/context/builder.py` (read only by `base_agent.py`) | 852 |
| `shared/pipeline/graphs/` (nodes, rails, state) | 228 |
| `services/data/stores/fallback_events.py` and its test | 60 + test |
| `base_orchestrator.py`: the worker pool, `_run_via_graph(_async)`, `_unified_enabled`, the fallback branch, the `_sub_agents` requirement, the `langgraph` imports | 167 (−), 37 (+) |
| The five sector orchestrators: their analyst teams | 65 |
| Settings: `UNIFIED_ANALYST_FALLBACK_LEGACY`, `UNIFIED_ANALYST_SECTORS`, `unified_analyst_sectors()` and both `config.yaml` keys | |
| `requirements.txt`: `langgraph` | 1 |

**The production build changes** [code]: the image no longer installs `langgraph` (1.2.12 here)
and what only it pulls in (`langchain-core`, `langgraph-checkpoint`, `langgraph-prebuilt`,
`langgraph-sdk`). Nothing else imports `langgraph` or `langchain` (grep, and the import test).
The next push rebuilds the image; the deploy check should see the build succeed.

**The trap** [code]: `unified_analyst.sectors` is gone. Every orchestrator runs `_run_unified`;
`SECTOR_SPECS` covers all five paths; a path name without a spec gets "no analysis method for
the sector" and so no analysis, never another method. Tests: every registered path builds with
no analyst team and has a spec; no setting with either old name exists.
`TestAnalyseAsyncDispatch` in `test_orchestrator_unified_branch.py` is rewritten: the async
entry runs the same one call, and an empty result is no analysis, not a backup.

**The core shim** `core/pipeline/orchestrator.py` re-exported `_SUB_AGENTS`; it now re-exports
the orchestrator only (the scheduler's `run_now` imports it).

### Lose nothing good: what the per-analyst prompts asked for that the one-call path does not

No `unified.py` was edited. The deleted prompts stay in git history (`03debc1`). For the owner's
decision on the sector prompts ([CLEAN-003](../stories/CLEAN-003.md), candidate 8):

- **Every path: the targeted searches.** Each analyst ran its own four to six searches (about 45
  for an automobile stock); the bundle runs three (company, sector, macro) and one page read.
  So the one-call prompts ask for figures the bundle has no fetch for, and score them 0.5 by
  their own grounding rule. Examples of the lost queries: "FADA monthly retail sales", "SIAM
  dispatch data", "EV registration Vahan", "dealer inventory channel check", "DGFT export",
  "used car price index Cars24 CarDekho", "BNAP NCAP safety rating", "PLI scheme utilization",
  "earnings call transcript management tone", "CRAR capital adequacy CET1 RBI filing", "ALM
  asset liability mismatch", "cyber fraud CERT-In", "AMFI monthly portfolio", "Nifty Bank
  rebalancing", "TCV large deal win pipeline", "H1B visa approval rate USCIS", "CUF generation",
  "DSCR refinancing", "DISCOM receivables aging", "curtailment CERC MNRE", "promoter pledge",
  "MNRE auction results", "solar module price Mercom BNEF".
- **Automobile.** (1) The per-OEM business-model snapshot (portfolio mix, EV status, revenue mix,
  margin profile, key watch; `get_business_model_context` in `automobile/config/settings.py`,
  with a Serper profile for an OEM not in the table) went into five analysts' prompts; the
  bundle does not carry it. The function and its table stay, now with no caller (BACKLOG B-8).
  (2) `valuation_catalyst` asked for `earnings_yield_premium` (earnings yield minus the 10-year
  G-Sec) and `catalyst_timing` (named 60–90-day catalysts), multi-timeframe momentum (1M, 3M,
  6M, 1Y) and volume confirmation; `unified.py` scores `technical_trend` and
  `support_zone_strength` instead and names no G-Sec rate. (3) `risk_macro` weighted named
  channels (China semiconductor supply for EV parts, US–Iran oil); `unified.py` keeps a general
  "global geopolitical risk". (4) `policy_regulatory` read FAME/MoHI pages (its Tavily queries);
  the bundle reads one page.
- **Banking/BFSI.** `fundamentals.earnings_quality` (recurring NII and fee income against
  one-time treasury gains) became `asset_quality` in `unified.py`; the treasury/fee split is no
  longer asked. Per-stock AMFI scheme flows: the bundle's fund signal is the sector's, not the
  stock's.
- **IT, renewables, generic.** `unified.py` asks for every dimension and sub-score the analysts
  asked for (checked item by item); only the targeted searches above are lost (IT's transcript
  dimension reads the bundle's page read).

### BACKLOG B-8

None of B-8's listed files belongs to this layer (the five forward shims under
`src/backend/shared/` re-export live `services/` modules; the second `feedback_agent.py` prompt
is the learner's), so they stay in B-8. This card adds to B-8 what it leaves with no caller:
five string context helpers only the deleted builder read (`get_technical_context`,
`get_valuation_context` in `indicators/fetcher.py`; `get_fundamentals_context`;
`get_macro_context`, `get_raw_materials_context` in `macro.py`) and the automobile
business-model snapshot (kept as input for CLEAN-003 candidate 8).

### Production notes

- **Railway variables:** if production sets `UNIFIED_ANALYST_SECTORS` or
  `UNIFIED_ANALYST_FALLBACK_LEGACY`, both are inert after the deploy (nothing reads them). Not
  read here: the session's permission check refused a listing of the service's variables.
- **`data/rl/fallback_events.jsonl`** stays on the volume, unread (21 rows, all October).
- **With PR-042 live** (`enforce` since 00:17 today), a held stock's review already stopped on an
  abstaining backup verdict; this card removes the backup's cost and the `record`-mode path, and
  stops the all-errored answer that never reached the backup from producing a verdict.

## Tests

- **New `tests/unit/test_no_analysis_clean005.py`, 32 tests** (28 with step 1, 4 with step 2),
  through the real orchestrator and the real one-call analyst with only the model's transport
  faked (`openai.APITimeoutError`, text that is not JSON, JSON naming no dimension, a reset
  connection on every attempt):
  - each failure mode, sync and async: `AnalysisUnavailable` with its reason; model calls 3 or 1;
    no aggregator call, score row, analysis log, run summary or gate row; no backup; one failure
    row with the run id; one warning (8 cases); the score database read directly holds no row;
    one missing dimension still reaches the aggregator;
  - the real `run_daily_review` through the real sector router (timeout, missing sections):
    `no_analysis`, classified `skipped`, every file under the store byte-identical, no feedback
    agent call, weights at v41, one warning;
  - the forecast writes no envelope; a re-forecast leaves the envelope's bytes unchanged and logs
    once; the monthly job forecasts the next stock with no line about the failed one; the deep
    dive returns the two other candidates and counts three calls;
  - `/analyse` (four modes) 503 with the sentence and no verdict or score; the stream's error
    event; the chat tool;
  - the count by IST day; an unreadable record counts nothing; the status field in the slot;
  - step 2: no tracked file imports a deleted module; only `unified.py` under each `prompts/`;
    no `langgraph` in any requirements file; every registered path builds with no analyst team
    and has a spec.
- **Changed, because they tested what step 1 changes:** `test_daily_review_outcomes_sa004.py`
  (the status inventory gains `no_analysis`); `test_error_capture_context.py` (its stubbed
  analysis returned nothing, now no analysis: it returns one scored dimension; plus `exc_info`
  on the two new handlers, the file's own guard); `test_search_shadow_pr043.py` (the default
  model reply scores one dimension, so the shadow still fires); `tests/integration/test_orchestrator.py`
  (same); `test_unified_analyst_settings.py`.
- **Changed with step 2:** the switch and backup tests rewritten
  (`test_orchestrator_unified_branch.py`, `test_data_health_record.py`'s fallback case → "a hollow
  run is recorded and returns nothing", `test_unified_analyst_settings.py`,
  `test_discovery_settings.py`, `test_generic_sector.py`, the automobile prompt test → the one
  prompt); setting patches dropped (parity tests, FIX-026); the gate's no-provenance wording
  (SA-003); `_sub_agents` stubs dropped from five test orchestrators.
- **Deleted with the code they tested:** `test_agents_unit.py`, `test_base_agent.py`, the four
  `sectors/*/test_agents.py`, `pipeline/test_agent_dossier_injection.py`, `test_fallback_events.py`;
  the `ContextBuilder` cases (integration fetchers, SA-010's legacy-pool class, SA-044's legacy
  builder case); the contract file's `BaseAgent` and worker-pool cases; the integration file's
  worker-pool case.

## Self-review (not the fresh review)

1. **Can an analysis that scored nothing still become a verdict anywhere?** `analyse` and
   `analyse_async` are the only exits that build a report, and both raise before
   `self._aggregator.run`. `grep` of `.analyse(` and `.analyse_async(` in `core`, `services`,
   `src` and `scripts` finds seven call sites and the automobile orchestrator's own docstring:
   the table's rows, where the forecast's one call serves the monthly job, the re-forecast and
   the paper lane. Each handles `AnalysisUnavailable`.
2. **Can the exception break a job?** Every scheduled caller catches it per stock (the review
   at its call site, which is the only caller of `_run_todays_agent_scores`; the monthly job;
   `regenerate_envelope`, also behind the pre-open check; the paper lane; the deep dive;
   `run_now`). It subclasses `RuntimeError`, so a caller missed here would still meet its
   existing broad handler.
3. **Is anything written before the review's `no_analysis` return?** Only the market-wide regime
   state, before the envelope is even loaded, as for `no_envelope` and the gate's stop (the
   byte-identical test lists it as the one exempt file, like SA-003's).
4. **Findings, none on the decision path:** a failed on-demand analysis still uses one of the
   member's daily analyses, as any failure did before (pre-existing, low: BACKLOG B-26). The chat
   tool used to pass the exception's text to the chat model; it now passes the plain sentence.

## Acceptance criteria

- The four requirements of step 1, each with its test: above. **Met.**
- Failure tests through the scheduled and the on-demand entry points (timeout, unparseable,
  missing section, exhausted retry): the review, the forecast, the deep dive, the monthly job,
  `/analyse`, the stream, the chat tool. **Met.**
- No import of a deleted module anywhere: the AST test. The full suite, the broad-except guard
  (baseline shrunk by 5 stale entries) and `check_kt_docs.py` pass after each commit: below.
  **Met.**
- A run with a failing model call produces no decision record for that stock (no gate row, no
  score row). **Met.**
- Living documents: KT section 4 ("When the analysis fails"), section 3's store table, 4 (sector
  benchmarks, decision gate), 9 (review outcomes), 11; `PRODUCT_MAP` 5.2 and its tables;
  `CODEBASE` (tree, settings, status fields, stores); `AGENTIC_DESIGN` section 11 rewritten;
  `ARCHITECTURE`; `README`; `docs/README.md`; the testing guide (new case 02-Q; 02-B's backup
  sentence removed). The PDF is not regenerated (AGENTS.md). **Met.**
- Nothing pushed or deployed. **Met.**
- B-8: routed as above.

## Full suite

Each run in a detached worktree at the exact commit, Python 3.13.5,
`.stockai/bin/python -m pytest -q`.

- **Step 1, first commit (`92469cd`, since amended):** 6,992 passed, **7 failed** (11 min 4 s,
  11:01–11:12 IST). The failures were tests whose stubbed analysis returned nothing (now no
  analysis: the error-capture context tests, the integration wiring test, the search-shadow
  prompt test), the error-capture file's `exc_info` guard on the two new handlers, and the
  settings test pinning the old default. Fixed only with what is valid at step 1, and the commit
  amended to **`b6744a6`** (`git diff 03debc1 b6744a6`: 22 files, +859 / −23;
  `| sha256sum` starts `ad1b80a54d472f74`).
- **Step 1, `b6744a6`:** **6,999 passed, 5 skipped, 1 xfailed, 0 failed** (11 min 37 s,
  11:14–11:25 IST). Broad-except guard OK (143 grandfathered); `check_kt_docs.py` `errors: []`.
- **Step 2, `e51b0c7`** (`b6744a6..e51b0c7`: 130 files, +380 / −6,847): **6,858 passed, 5 skipped, 1 xfailed, 0 failed** (11 min 49 s,
  11:26–11:38 IST); 141 fewer tests than step 1, the deleted tests of deleted code.
  Broad-except guard OK (138 grandfathered, 5 stale entries removed); `check_kt_docs.py`
  `errors: []`.
- **The reviewed range:** `git diff 03debc1 e51b0c7` (143 files, +1,232 / −6,863);
  `| sha256sum` = `2ffb7453330a449437efebe30638ceda921bf2ed539f979d728426681421e8dd`.
- **Imports without `langgraph`** [local]: with `langgraph`, `langchain` and `langchain_core`
  blocked by an import hook, every registered orchestrator, the deep dive, the review, the
  forecast, the three routes, the status route and the scheduler import (the production image
  will not have the package).

## Commands

```
.stockai/bin/python -m pytest -q tests/unit/test_no_analysis_clean005.py
.stockai/bin/python -m pytest -q tests/unit/test_orchestrator_unified_branch.py tests/unit/shared \
    tests/unit/test_unified_e2e_parity.py tests/unit/test_unified_e2e_parity_sectors.py tests/unit/sectors \
    tests/contract tests/integration tests/unit/intelligence/rl tests/unit/test_search_shadow_pr043.py
.stockai/bin/python -m pytest -q          # in a detached worktree at each commit
.stockai/bin/python scripts/ci/check_broad_except.py
.stockai/bin/python scripts/docs/check_kt_docs.py
git diff 03debc1 e51b0c7 | sha256sum
```

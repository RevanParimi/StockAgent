# SA-003 implementation receipt — gate recommendations and learning on essential data

- **Story:** [SA-003](../stories/SA-003.md). Audit finding F08 in the
  [September audit](../../../audit/2026-09-10-repository-production-review.md).
- **Phase:** implementation, one conversation, 2026-09-27 about 03:40–05:15 IST. It includes a
  same-conversation self-review, which is **not** the fresh-session review. STATE:
  `review_required`.
- **Baseline:** `da90ee5ad8f1d50037db708ded72fcf8b222ad05`. That commit is the previous
  conversation's push-and-deploy record, committed at 03:44 as this conversation began. The tree was
  otherwise clean. SA-001 and SA-002 are in `8413b59`, pushed and deployed (deploy `0509de45`).
- **SA-039 checks:** none was due. P1 is Mon 28 Sep after 17:00 IST.
- **Review input:** [SA-003-manifest.json](SA-003-manifest.json), 38 files. Its SHA-256 and the diff
  digest are under "Manifest and digests".

## What it does, in one example

TATAMOTORS' price source answers HTTP 404, while news, macro and flows answer. The analyst scores 9
of 9 dimensions, and the aggregator says STRONG BUY. SA-002's row names the three essential
sections as unusable, but before this story nothing read the row.

| Step | Before | `record` (the checked-in mode) | `enforce` |
|---|---|---|---|
| Report | STRONG BUY | STRONG BUY; `decision_gate` = `abstain`, naming the three sections and the run id; one row in `decision_gate.jsonl` | **INSUFFICIENT DATA**; STRONG BUY kept as `withheld_verdict` |
| Month-start forecast | an UP envelope | the same envelope; every row says `data_gate: abstain` and names the run | **no envelope** (`InsufficientDataError`; the next scheduled run retries) |
| Advisor, small holding | ADD | ADD, with `data_gate`: "would block ADD", naming the forecast run | nothing to act on: HOLD |
| Autopilot | BUY 2 shares | BUY 2 shares | **no buy** |

The same chain with a live price source stays `actionable` in `enforce`, and the buy happens. All
four rows are tests: `test_decision_gate_portfolio_sa003.py`, through the real orchestrator, bundle
builder, aggregator, forecast, pipeline and executor, with only providers and LLM calls stubbed.

## The contract

**The gate** (`src/backend/shared/pipeline/decision_gate.py`, new, and
`FinalReport.decision_gate`). It is derived from SA-002's pure `build_record`, so the gate and the
health row cannot disagree. It is computed whether or not the row is recorded:
`observability.data_health_enabled` is the row's rollback line only.

| Status | When | May act? |
|---|---|---|
| `abstain` | an essential section (`observability.data_health_essential_sections`) is not `ok`/`cache_hit`; or fewer than `decision_gate.min_dimensions_fraction` (0.5) of the sector's dimensions scored; or no bundle (the legacy worker-pool fallback: no provenance); or a v1 health row; or the gate itself failed | no |
| `degraded` | none of the above, but the health row is `degraded`: an ordinary enrichment (news, macro, flows, dossier…) or a dimension above the floor is missing | yes |
| `actionable` | nothing missing | yes |
| `""` (unknown) | a forecast row or shelf idea made before SA-003 | no |

**The switch** is `decision_gate.mode`, with env `DECISION_GATE_MODE`. It is read at call time.

- `record` is checked in. Every consumer computes the gate and records what enforcement would
  stop. No outcome changes.
- `enforce` stops the actions below.
- Any other value fails closed to `enforce`, with one warning per value.

**Price freshness, minimum** (`daily_review.SessionClose`, `_fetch_session_close`,
`pricing.session_close`, `close_verifier.nse_session_close`):

- The close fetchers already fell back to the newest earlier bar when the session had none. That
  selection is **unchanged**.
- The result now names the bar the chosen close came from: yfinance's own bar, or the NSE row's own
  date when NSE supplied the close.
- `fresh_for(session)` is true only when that bar is the session itself.
- `_fetch_actual_close` and `close_on` return the same numbers as before, for the audit and the
  portfolio API.

**Price identity, minimum.** An unresolved symbol has no provider data, so its essential sections
are empty and it abstains (tested through the real `_resolve_ticker` fallback). The grading and
trading close is still the existing NSE cross-checked close. Lifecycle identity (renames,
demergers, successors) is SA-008; see "Open limitations".

**Every consumer that acts or learns:**

| Consumer | Checks | In `enforce`, when not actionable | Recorded where |
|---|---|---|---|
| Public analysis (`analyse`, `analyse_async`: `/analyse`, `/ws/stream`, chat, CLI) | the run's gate | verdict `INSUFFICIENT DATA` | report; gate log `analysis` |
| Month-start forecast (`generate_forecast`, incl. paper lane) | the report's gate | raises `InsufficientDataError`; no envelope | gate log `forecast`/`paper_forecast`; the error names the run |
| Re-forecast (`regenerate_envelope`: review shocks, pre-open, manual CLI) | the report's gate | returns None; current envelope intact | gate log `reforecast` |
| Daily review (`run_daily_review`, incl. paper lane) | 1) the graded row's `data_gate`; 2) the actual close is from the session's bar; 3) the fresh re-run's gate | returns `data_gated` before any learning write | summary `data_gate`; gate log `daily_review` with `stage` |
| Discovery (`run_deep_dives`) | the dive's gate | no shelf idea | gate log `discovery`; `ShelfIdea.data_gate` otherwise |
| Advisor (`gated_decide`, `decide`) | holding close fresh; forecast rows actionable; shelf idea's gate; candidate close fresh | ADD becomes HOLD; blocked SWITCH destination falls to the next, or to plain EXIT | the user's own `AdviceRecord.data_gate` and note `DATA_GATE` |
| Autopilot SWITCH buy leg | its own session close | sell executes, buy skipped | log line; the user's `switch_buy_skipped` alert |

- **Risk reduction is specified.** EXIT, TRIM and a SWITCH's sell leg are never blocked, in either
  mode: missing data must not trap a position. When they rest on a stale close or an unverified
  forecast, the advice records what they rest on.
- **A gated review is complete.** It makes no grading, FeedbackAgent call, weight update or
  observe-mode proposal, lesson, envelope revision, streak, feedback entry, dossier or control-lane
  step. This holds in both SA-039 learning modes. The market-wide sticky regime, updated at the
  start of every review (as on `no_envelope`), is the one write that still happens.
- **User isolation.** The shared gate log is ticker-level: tests assert it never holds a user id.
  Per-user decisions live on the user's own advice ledger.

## For the reviewer: decisions to check

1. **It ships as `record`.** Deploying it changes no outcome. REVIEW.md allows one adaptive policy
   flag per observation window, and SA-039's window runs to Thu 1 Oct. The card also says "do not
   activate a production policy change during this implementation task". A typo in the variable
   fails closed to `enforce`.
2. **The dimension floor is "at least half"** (`min_dimensions_fraction: 0.5`). It stops the
   audit's 1/6, 2/6 and 3/9. It lets 3/6 act, as `degraded`. SUZLON's "lost 3 of 6" would pass. If
   that should abstain too, the change is one number (for example 0.51).
3. **Fundamentals are essential**, per SA-002's hand-over. A blank newest quarter makes them
   `fallback`, so the analysis abstains, possibly for weeks after each quarter end. Record mode
   exists to measure that before enforcing. If it is too broad, narrow
   `observability.data_health_essential_sections`. That list is the single definition of
   "essential".
4. **Unknown means unverified.** Once enforcing, envelopes and shelf ideas from before SA-003 block
   ADD, SWITCH destinations and their reviews' learning. They are replaced at the next monthly
   forecast (the 1st) and by shelf rotation (60 days). Activate after the first monthly forecast
   under this code. The alternative, grandfathering, treats unknown provenance as verified, which
   SA-002's hand-over rules out.
5. **The gated review stops at the first failing input**, before the FeedbackAgent. It records no
   feedback entry, so that day has no graded row. Under hard-bind (on in production), the graded
   verdict would have been the abstained one.
6. **`final_score` and agent scores are kept** on an abstained report, for diagnosis. The screens
   still show the score next to INSUFFICIENT DATA. Routed to SA-024.
7. **The legacy fallback abstains.** All production sectors run the unified path, so this affects
   only the fallback after a unified failure.

## Acceptance criteria

| Criterion | Result | Evidence |
|---|---|---|
| Missing/unresolved/stale essential prices prevent new risk-increasing actions and weight updates | Met, in `enforce` | Portfolio: `test_enforce_provider_no_data_produces_no_new_risk_transaction`, `test_enforce_a_carried_forward_close_blocks_the_add`, `test_enforce_blocks_an_add_on_an_envelope_built_before_enforcement`, `test_switch_buy_leg_needs_the_sessions_close`. Learning: `test_a_gated_review_has_no_learning_side_effect` (6 cases × 2 learning modes), `test_enforce_builds_no_envelope_on_an_abstained_analysis`, `test_enforce_reforecast_leaves_the_envelope_intact`. Unresolved: `test_an_unresolved_symbol_abstains` |
| Every skipped action/update records its reason and source run ID | Met | Gate-log rows are asserted for analysis, forecast, re-forecast, review (with `stage`) and discovery, each with `source_run_id` and reasons. Advice: `data_gate.reasons` and `source_run_ids`. The review summary's `data_gate` names the stage, reason and run. The one log-only path is the autopilot's backstop on a SWITCH buy leg (see "Open limitations") |
| Risk-reduction behaviour is specified and tested; missing data is never bullish or a valid zero return | Met | `test_risk_reduction_is_never_blocked` (EXIT on a stop breach, TRIM on profit, both on a stale close and an abstained forecast); `test_an_exit_on_a_stale_close_is_annotated_not_blocked`; `test_switch_buy_leg_needs_the_sessions_close` (the sell always executes). "Valid zero return": `test_the_freshness_boundary_is_the_session_itself` and the `close_carried_forward_one_day` case; `test_a_missing_session_carries_the_previous_bar_forward_visibly` |

**The card's evidence list:**

- **The end-to-end fixture** (provider no-data → bundle → verdict → advice → executor, no new-risk
  transaction): `test_enforce_provider_no_data_produces_no_new_risk_transaction`. Its control,
  `test_record_mode_reproduces_f08_…`, shows that the same fixture does reach a BUY when nothing
  enforces. `test_enforce_healthy_providers_still_buy` shows that enforcement passes valid data.
- **1/6, 2/6 and 3/9:**
  - As scored dimensions, the audit's meaning: `test_dimension_coverage`, with the boundaries 3/6,
    4/9, 5/9, 6/6, 9/9 and 0/9.
  - As live sections: `test_live_section_counts_are_not_the_criterion`. 3 of 9 abstains when the
    three are news, macro and dossier. It is `degraded`, and may act, when the three are the
    essential ones.
  - Valid complete data: the `actionable` cases and the healthy end-to-end runs.
  - Risk-reduction exceptions: as above.
- **No feedback or weight side effect on a gated review:** the byte-identity test, in both learning
  modes.

**Independence of expectations.** Every expected status, verdict, quantity and date is written by
hand from the rule in `config.yaml` or from the fixture:

- the dimension floor's boundaries, and which sections are essential;
- the ADD tranche: 25% of ₹1,000 at ₹100 is 2 shares;
- the previous day's bar;
- the NSE row dates.

Nothing expected is computed by the code under test. The end-to-end chain uses the real SA-002
provider fixture (`Market`) and the real bundle producers, aggregator, `generate_forecast`, advisor,
pipeline and executor.

## Tests: commands, environment, results

Environment: Windows 11, Python 3.13.11 (`.stockai` venv), pandas 3.0.2,
`RL_LEARNING_MODE=adapt`. Every pytest run used the network-guard plugin `-p nonet` (a copy in
ignored `analysis_data/sa003/`), which fails any non-loopback connection and reports what it
blocked. All figures below are from the final bytes (`analysis_data/sa003/final_runs.sh`).

```text
PYTHONPATH=analysis_data/sa003 RL_LEARNING_MODE=adapt .stockai/Scripts/python.exe -m pytest \
  -q -p no:cacheprovider -p nonet <files>

new SA-003 files (4)                         -> 119 passed; blocked 0
focused: 32 affected existing files + the 4  -> 570 passed, 2 failed (the Atlas-dependent pair below); blocked 96, the same 96 as on baseline
runtime mutations (12, run_mutations.sh)     -> 12 of 12 caught (table below); unmutated 119 passed
7-day sweep (sweep3.sh, pinday3.py)          -> 7 of 7 run days: 119 passed each; blocked 0
full tests/unit                              -> 3442 passed, 5 skipped, 0 failed (3 min 44 s); nonet blocked 194, the pre-existing set (SA-002: 194); tracked data/ clean
build_kt_pdf.py; check_kt_docs.py            -> PDF source 67acf0c7..., 22 pages; check_kt_docs errors [] (320 links, 47 stories, 24 job IDs, 13 config claims)
```

**Mutations.** `analysis_data/sa003/mutate3.py` puts back one replaced behaviour at runtime. No
source file is edited. Each mutation is caught by the new tests:

| Mutation (the behaviour put back) | New tests failing |
|---|---|
| m1: enforce keeps the verdict (no withholding) | 7 |
| m2: B2/B5's rule, only a hollow run abstains | 33 |
| m3: no dimension floor | 6 |
| m4: unknown provenance counts as verified | 8 |
| m5: the forecast and re-forecast ignore the gate | 3 |
| m6: the review records but never stops | 13 |
| m7: any close is fresh | 11 |
| m8: the advisor ignores the gate | 5 |
| m9: discovery ignores the gate | 1 |
| m10: over-reach, EXIT and TRIM blocked too | 3 |
| m11: the NSE fallback row is labelled with the session | 4 |
| m12: a carried-forward yfinance bar is labelled with the session | 2 |

**The 7-day sweep.** The four new files run as if on each day from Sun 27 Sep to Sat 3 Oct 2026.
That span covers a weekend, the September-to-October cycle rollover, and the 2 Oct NSE holiday.
The run day is pinned in two places:

- the three clocks these paths read: `fetch_result`, `prediction_store` and `generate_forecast`;
- the fixtures' import-time dates.

A probe test confirms that the pin reaches all of them. Nothing process-wide is replaced.

**Before and after, on the same 32 existing files.** Before any new test was added, the baseline
(`da90ee5`, in a temporary worktree) and this tree gave the same result: 451 passed and 2 failed,
with the same 2 failures and the same 96 blocked connections. The 2 failures are the Atlas-dependent
pipeline tests described below.

**Existing tests changed** (the contract changed, so each changed test's seam moved; no
expectation changed):

- 7 daily-review patches were retargeted from `_fetch_actual_close` (a bare float) to
  `_fetch_session_close`, returning a close dated the session asked for. They are in
  `test_daily_review_dossier` (2), `test_lesson_evidence`, `test_macro_fallback_context`,
  `test_news_availability_telemetry`, `test_paper_lane_isolation` and `test_shock_path`.
- 7 portfolio patches were retargeted from `close_on` to `session_close`, in
  `test_portfolio_pipeline` (2), `test_autopilot_pipeline` (2), `test_autopilot_executor_switch`
  (2) and `test_autopilot_isolation`.
- 2 patches of `decide` in `test_autopilot_pipeline` now patch the pipeline's seam,
  `gated_decide`.
- A patch that misses its target now fails loudly: monkeypatch refuses to set a name that no
  longer exists. It no longer reaches a provider.
- `tests/conftest.py` gains `_no_real_gate_writes`, which keeps the gate log out of the real
  `data/logs`, the same rule as the news-availability ledger.

**Pre-existing failures seen** (routed to [SA-005](../stories/SA-005.md)):

- `test_portfolio_pipeline.py`: 2 tests fail alone, on baseline code too. With `atlas.enabled:
  true` and no users in the local `data/atlas.db`, the fan-out goes to `primary`. They pass in the
  full run, or with `ATLAS_ENABLED=false`.
- `test_portfolio_locking.py::test_cross_process_add_holding_is_atomic`, the known flake. It
  failed 2 of 16 times in this OneDrive checkout and 0 of 12 in a temporary worktree (6 of them on
  baseline code). This story does not touch the store.
- `test_config_loader.py` leaves the loader bound to a throwaway YAML. This story's
  shipped-default check therefore reads `config.yaml` directly.

**Not exercised:**

- Linux, and Python 3.11 (the Docker image).
- Any production data. How often the gate would abstain in production is **not measured**. Record
  mode is the instrument for measuring it.
- The browser. No frontend file changed; the verdict renders as text.

## Documentation

- **KT** (`docs/TECHNICAL_DESIGN.md`):
  - §1: status;
  - §3: the `decision_gate.mode` configuration row;
  - §4: step 8, the decision gate with an example, and the current gap;
  - §5: forecast rows, and the review's three checks with an example;
  - §6: the advisor and execution gates with an example;
  - §11 and §12: status.
- The PDF is rebuilt: source `67acf0c7…`, 22 pages.
- The new module is named in code formatting, not linked. `check_kt_docs.py` fails on a link to a
  file absent at the header's `8413b59`. The commit that lands this story should link it and bump
  the header, as SA-002's did.
- `docs/ARCHITECTURE.md`: the decision gate, and the implemented/planned table.
- `docs/TEAM_TESTING_GUIDE.md`:
  - 02-C is rewritten into four prepared reports, in `enforce` and `record`;
  - 02-F points to 02-C;
  - 03-C is rewritten into the downstream journey in both modes, including a stop-breach EXIT that
    still executes.
- `CODEBASE.md`: the tree, a decision-gate paragraph, and module rows for `decision_gate.py`,
  `advisor.py` and `data_health.py`. The last one drops "write-only".
- `check_kt_docs.py`'s config-claims list is unchanged, as SA-039 left it. The KT's configuration
  row matches `config.yaml`, and the new test asserts the shipped value.
- Bookkeeping, outside the manifest:
  - STATE and HANDOFF;
  - this receipt;
  - the [SA-003](../stories/SA-003.md) box;
  - routed notes on [SA-004](../stories/SA-004.md) (count `data_gated`),
    [SA-005](../stories/SA-005.md) (test isolation), [SA-008](../stories/SA-008.md) (what the
    gate gives, and TATAMOTORS→TMPV) and [SA-024](../stories/SA-024.md) (the screens).

## Open limitations

- **Lifecycle identity is not checked.** `YF_SYMBOL_OVERRIDES` maps `TATAMOTORS` to `TMPV.NS`,
  the post-demerger passenger-vehicles entity. With TMPV's data healthy, TATAMOTORS is
  `actionable`. The gate verifies that evidence arrived and is fresh, not that it belongs to the
  same economic entity. This is SA-008.
- **The autopilot's SWITCH-leg backstop only logs.** With switch evaluation on (the default,
  `advisor.switch_eval_enabled`), a stale candidate is caught at advice time and recorded on the
  advice. The executor's own re-check covers a candidate with no quote at advice time. It skips
  with a WARNING, and the user gets the existing `switch_buy_skipped` alert, whose text now names
  the stale-price case. It writes no gate-log row.
- **A one-bar download window finds no close.** `df["Close"].squeeze()` on one row is a scalar, so
  the unchanged selection code finds nothing. This is pre-existing and conservative. A real 7-day
  window has several rows.
- **Scheduler counts** treat `data_gated` as produced. Routed to SA-004.
- **The screens** show the score next to INSUFFICIENT DATA and do not render the reasons. Routed
  to SA-024.

## Rollout (owner, after commit and push)

1. **Deploying changes no outcome.** The code ships `record`. Push only in a job-free window,
   00:10–06:20 IST.
2. **Verify read-only, across one scheduled cohort.**
   - `data/logs/decision_gate.jsonl` gains rows. The daily review's rows name
     `stage: forecast_row` with "issued before the data gate existed" for every ticker, until the
     next monthly forecast.
   - Reports carry `decision_gate`.
   - The weight and feedback behaviour of the reviews is unchanged. SA-039's P1–P3 checks still
     apply as written.
3. **Measure before enforcing,** over at least one monthly forecast under this code (the next is
   Thu 1 Oct 09:00):
   - how many analyses abstain, and for which essential section or dimension reason;
   - how many reviews would stop, and at which stage;
   - how many ADDs would be withheld.

   If fundamentals `fallback` dominates after quarter ends, decide the essential list first.
4. **Enforce** by setting the Railway variable `DECISION_GATE_MODE=enforce`. It is the owner's
   decision, one policy change per observation window, and after SA-039's window. Setting the
   variable redeploys.
5. **Rollback:** delete the variable, or set it to `record`.

## Manifest and digests

- **Review input:** [SA-003-manifest.json](SA-003-manifest.json), 38 paths: 18 code and config
  files (1 new), 15 test files (4 new) and 5 documentation files, including the PDF. The SHA-256 of
  its LF bytes is **`dbe167149b5f73ab616c7d5e1e25054594e7c2af043d5316b948b8d92aa96c94`**.
  `kt_manifest.py verify` gives 0 mismatches.
- **Excluded,** because they are written after the manifest: STATE.json, HANDOFF.md, this
  receipt, and the SA-003, SA-004, SA-005, SA-008 and SA-024 cards.
- **Full diff** against `da90ee5`: **`a46a684622ce54d4e766982d7d8d0d98a19705e56f2e430340e3e21dc89cd2f1`**,
  191,298 bytes over 37 text files. The PDF is pinned by its blob, `f06216dc…`.
- **To rebuild the diff:** take every manifest path except the PDF, sorted. For a path tracked at
  the baseline run `git diff --no-color --no-ext-diff da90ee5 -- PATH`; for a new file run
  `git diff --no-color --no-ext-diff --no-index -- /dev/null PATH`. Concatenate the bytes. The
  ignored `analysis_data/sa003/sa003_diff.py` does exactly this.
- **After the commit:** `verify --rev <commit>` compares against the commit instead.

# SA-039 — Implementation receipt

**Story:** [SA-039](../stories/SA-039.md) — Contain adaptive learning: observe-only, live weights back to defaults
**Phase:** implementation, 2026-09-24. Status after this phase: `review_required`.
**Context:** one implementation conversation. The self-review below is **not** the fresh-session review that [REVIEW.md](../REVIEW.md) requires.
**Baseline commit:** `3742fffd0be2ebc649ad95b226f8e7a747ce873a`. **Committed as `4c4728ae5b879e26430ed0f58dee2728cc126cd9`** on 2026-09-25 at the owner's word. Verify with `--rev 4c4728a` (see below).
**Review input:** [SA-039-manifest.json](SA-039-manifest.json), 18 files, **review-input SHA-256 `1efe361fac2a0e444a39554c0c9490488c3695023791ba313ab836d22092725e`**.

## How to verify the input

```bash
python scripts/docs/kt_manifest.py verify docs/planning/PI-2026-09/evidence/SA-039-manifest.json
sha256sum docs/planning/PI-2026-09/evidence/SA-039-manifest.json
```

`verify` recomputes every file's git blob id and the SHA-256 of those blob bytes from the working
tree (expect `"mismatches": []`). The manifest's own SHA-256 is the review input. After the change
is committed, `verify --rev <commit>` compares against the commit instead. The manifest excludes
STATE.json, HANDOFF.md, this receipt and itself, which are written after it.

## What changed

**The switch.** `rl.learning_mode` in [config.yaml](../../../../config.yaml) (checked in as `adapt`),
`RL_LEARNING_MODE` in [settings](../../../../src/backend/shared/config/settings/base.py) with the
same env name, and a new module `core/intelligence/rl/learning_mode.py`:

- `learning_mode_state()` returns `(mode, reason)` and reads settings at call time. Values are
  trimmed and lower-cased. Anything other than `adapt`/`observe` (including empty or `None`) returns
  `observe` and logs one warning per distinct value per process.
- `decision_weights(wm, sector)`: in observe mode, `get_sector_weights(sector)`, whatever is stored.
  In adapt mode, `wm.effective_weights()`, or `None` when nothing is stored (callers keep their old
  fallback).
- `weight_observation(...)` builds the diagnostic record.

**Every reader that affects a decision** (the card's hard-review list):

| Consumer | Before | Observe mode now | File |
|---|---|---|---|
| Month-start forecast | `wm.effective_weights()` → `set_aggregator_weights` | `decision_weights` → sector defaults. Envelope records `learning_mode`. | generate_forecast.py |
| Living-envelope re-forecast (`regenerate_envelope`; also reached from pre-open check and the manual CLI) | same | same | generate_forecast.py |
| Public analysis (`analyse`, `analyse_async`) | `_load_learned_weights` → stored weights at version > 0 | `_load_learned_weights` returns `None`, so `_get_default_weights()` is used | base_orchestrator.py |
| Review Step 4 re-scoring (`_run_todays_agent_scores`) | `wm.effective_weights()` or `None` | sector defaults, passed explicitly | daily_review.py |
| Review Step 5.5 / Step 7b revision (`regime_effective_weights` → `_revise_remaining_forecasts`) | regime multipliers × `updated_wm.effective_weights()` | regime multipliers × sector defaults | daily_review.py |
| Review Step 5 writer | `WeightAdapter.update(wm)` + `save_weight_memory` | adapter runs on `wm.model_copy(deep=True)` with `proposal_only=True`. **No save.** One record upserted per review date into `<TICKER>_weight_observations.json`. | daily_review.py, prediction_store.py, weight_adapter.py |
| Tagged-lesson emphasis (forecast rows, re-forecast rows, Step 7b revision) | `apply_lesson_emphasis` moves scores | returns the scores unchanged | lesson_emphasis.py |
| Legacy category micro-adjustment (forecast rows) | moves scores up to ±0.05 | returns the scores unchanged | generate_forecast.py |
| `claims_fired` on the feedback entry | matching lessons | `[]`, because no claim acted; otherwise the scorecard's claim-day split and per-lesson efficacy would credit lessons that did nothing | daily_review.py |

**Mode is visible** in the review's start line (`=== … | learning_mode=observe ===`) and its
`Complete —` line, in the review summary dict (`learning_mode`; `weights` is now the weights decisions
used), on each envelope, and in the read-only RL monitor: `/ui/rl/weights/{ticker}` adds
`learning_mode`, `learning_mode_reason`, `decision_weights` and `latest_observation`, and
`/ui/rl/summary/{ticker}` adds `learning_mode`. In observe mode the adapter logs
`[WeightAdapter] Proposal (not applied) → vN`, not `Weights → vN`, so a log reader cannot mistake a
proposal for a write.

**Diagnostic record** (one per review date, a re-run replaces it, newest 260 kept):
`review_date, mode, mode_reason, applied=false, stored_version, stored_weights, would_be_version,
would_be_weights, deltas (would-be − stored, non-zero only), adapter_reason, decision_weights,
recorded_at`. The weights are raw `current_weights`, which is what a save would have written.

**Scope interpretation, for the reviewer.** The card names tagged-lesson emphasis. Its acceptance
criterion says "lesson emphasis leaves agent scores unchanged", so I also contained the untagged
category micro-adjustment (`_apply_ledger_micro_adjustments`), the other path where lessons move
scores. Leaving it live would make observe mode an incomplete control for SA-022. If the reviewer
prefers the narrow reading, only the one guard in `generate_forecast._apply_ledger_micro_adjustments`
has to be removed.

**Unchanged by design:**

- The paper lane (its branch is checked before observe).
- The absurd-price-error path (no adapter call, no record).
- Regime multipliers, thesis multipliers, the conviction streak, seasonal seed adjustments,
  miss-counter prompt enhancements and dossier text. These are out of scope per the card
  (SA-003/SA-014).

## First-time initialisation (card: "record whether it still happens")

**Yes, it still happens in both modes.** When no file exists, `get_or_init_weight_memory` writes a v0
file of defaults. `generate_forecast` and `regenerate_envelope` use the sector table, while
`daily_review` still uses `settings.AGENT_WEIGHTS` (the automobile table). That is the card's code
note, and it is pre-existing. Writing v0 defaults is not adaptation. In observe mode the file's
`base_weights` are never used for decisions; a test pins that an automobile-based file for a pharma
ticker still resolves to the generic defaults. The paper lane still builds v0 in memory only.

## Acceptance criteria

| Criterion | Evidence |
|---|---|
| Observe: forecast, public analysis, review re-scoring and re-forecast aggregate with sector defaults | `test_public_analysis_path_composite[observe-0.56]`, `test_public_analysis_async_path_uses_the_same_loader`, `test_month_start_forecast_composite[observe-0.56]`, `test_reforecast_uses_sector_defaults_in_observe`, `test_full_review_in_observe_leaves_weights_byte_identical` (re-scoring and Step 7b `new_weights` both equal the hand-copied automobile table) |
| Observe: full review leaves `current_weights`, `weight_version`, `weight_history` unchanged, and writes one record with would-be weights, deltas, mode, reason and review date | Same full-review test: the weight file's SHA-256 is identical before and after. One record, with the fields asserted. `test_observe_diagnostic_is_exactly_what_adapt_writes`: the record's `would_be_weights` equal what adapt mode writes for the same fixture. `test_rerun_of_the_same_date_replaces_its_diagnostic`. |
| Observe: lesson emphasis leaves scores unchanged; lessons still recorded | `test_lesson_emphasis_is_a_no_op_in_observe` (both paths, with an adapt-mode sanity check that the same fixture does move scores), `test_forecast_rows_carry_unmoved_scores_in_observe`; the full review stores the new lesson and `claims_fired == []` |
| Adapt behaves as before; one test pins that adapt writes | The 1012 existing RL/pipeline/monitor tests and the full suite pass unchanged. `test_observe_diagnostic_is_exactly_what_adapt_writes` asserts adapt writes v42, uses the stored weights for re-scoring and writes no diagnostic. The composite tests' `adapt` cases give 0.50. |
| Unrecognised value fails closed to observe with a warning | `test_unrecognised_value_fails_closed_to_observe_with_warning` (5 values), `test_invalid_mode_review_writes_no_weights` |
| Mode in the review log line, one read-only surface, KT §5 | The log lines are visible in captured test logs (`learning_mode=observe` on start and `Complete —`). `test_rl_monitor_shows_mode_and_live_weights`. KT §5 is updated. |
| Paper lane and absurd-error path unchanged | `test_paper_lane_is_unchanged_in_observe`, `test_absurd_error_path_is_unchanged_in_observe`, plus the existing paper-lane and absurd-error tests (all pass) |
| Non-automobile sector resolves its own defaults | `test_observe_uses_each_sectors_own_default_table`, `test_observe_ignores_a_base_weights_table_from_another_sector`, `test_workflow_and_orchestrator_defaults_agree` |
| Rollback resumes stored weights byte for byte | `test_rollback_to_adapt_resumes_stored_weights_byte_for_byte`: the file bytes after an observe review equal the store's own serialization of the seed, and adapt then returns the stored weights through both the workflow helper and the orchestrator loader |

**Independence of expectations.** The default tables are copied by hand into the test from
config.yaml and the sector settings modules. The composite is derived by hand: every agent scores 0.5
except `technical` at 1.0, so the composite is 0.5 + 0.5 × w_technical. That gives **0.56** with the
generic default (0.12) and **0.50** with the learned 0.0. It runs through the real
`SignalAggregator.run`, with only its LLM call and loggers stubbed.

**Mutation check.** I reverted only the five call-site files (daily_review, generate_forecast,
base_orchestrator, lesson_emphasis, rl_monitor), kept the switch and tests, and re-ran the module:
**12 failed, 18 passed**. The 18 that still pass are the switch-parsing, default-table, adapt-mode
and unchanged-path tests, which should pass either way. The files were then restored byte for byte
from a copy.

**Transports blocked.** A `no_network` fixture replaces `socket.connect`/`connect_ex` and
`getaddrinfo`. It records every attempt, and the tests assert the list is empty. It caught a real
attempt: see finding T1 below. LLM calls (FeedbackAgent, dossier curator, control lane, aggregator),
news, NSE market data, off-market signals, factor regime, thesis review, the forecast profile, F&O
snapshot and prompt enhancer are all stubbed. Stores are under pytest's `tmp_path`.

## Commands and results

Environment: Windows 11, Git Bash, repo venv `.stockai` (Python 3.13.11, pytest 9.0.3,
pydantic 2.13.3).

| Command | Result |
|---|---|
| `./.stockai/Scripts/python.exe -m pytest tests/unit/intelligence/rl/test_learning_mode_sa039.py -q -p no:cacheprovider` | **30 passed** (21 test functions with parametrisation) |
| `… -m pytest tests/unit/intelligence/rl tests/unit/test_rl_monitor_api.py tests/unit/test_orchestrator_unified_branch.py tests/unit/pipeline tests/unit/test_bias_window_settings.py tests/test_weight_init_fix.py -q -p no:cacheprovider` (before the new tests were added) | 1012 passed, 5 skipped |
| `… -m pytest tests/unit -q -p no:cacheprovider` (with the new tests) | **3158 passed, 5 skipped** in 4 min 33 s. `data/nse/key_registry.json` was not modified this run. |
| Mutation check (above) | 12 failed / 18 passed against the original call sites |
| `python scripts/docs/build_kt_pdf.py` (Node on PATH) | 0 overflow elements; PDF source SHA-256 `719bf42e…` |
| `python scripts/docs/check_kt_docs.py` | **0 errors**: 13 documents, 263 links, 42 PI stories, 24 job IDs, 18 PDF pages |
| `python scripts/docs/kt_manifest.py write …` / `verify` | 18 files, 0 mismatches, review input `1efe361f…` |

Not run: integration tests under `tests/integration` (they need live services), a browser check of
the RL Monitor page (the change only adds JSON fields; the page itself was not exercised), and any
production action.

## Documentation

- [KT](../../../TECHNICAL_DESIGN.md):
  - §1: the production-observation row names the 2026-09-23 inspection and the 2026-09-24 baseline,
    and the PI-target row states that SA-039 is awaiting review.
  - §3: new configuration row `rl.learning_mode: adapt`; the prediction-store row lists
    `<TICKER>_weight_observations.json`.
  - §5: the "5 of 6" sentence is corrected and cites the baseline. In production, 5 of the 6
    `technical` tickers are at 0.0, but 4 of those 6 default to 0.10 (renewable), not 0.12. A new
    paragraph, labelled as newer than the header revision, describes the switch, an example,
    rollback, visibility and what is not contained.
  - §12: the status line is updated.
  - The header's `Code inspected` revision (`d105a44`) is deliberately unchanged: the new module is
    not committed, and `check_kt_docs.py` would reject a link to it. The new module is named in text,
    not linked. **At commit, bump the header to the SA-039 commit** and drop the "newer than the
    header revision" label.
- The PDF is rebuilt from the edited Markdown.
- [ARCHITECTURE.md](../../../ARCHITECTURE.md): one sentence on the switch.
- [TEAM_TESTING_GUIDE.md](../../../TEAM_TESTING_GUIDE.md): new human case **04-F** (observe-mode RL
  Monitor and a version-unchanged check).
- CODEBASE.md: a file-map row for `learning_mode.py`.
- R2 routed input: [SA-039-baseline-2026-09-24.md](SA-039-baseline-2026-09-24.md). This is the
  pre-activation baseline from read-only production logs (deploy `d9c459ae`, the 16:30 review). Of
  18 tickers with logged weights, 9 have chart weight 0.0 and 16 are below half their default; 5 of
  6 `technical` tickers are at 0.0; all 19 reviews wrote a new version. Tickers are pseudonymised;
  the label map and raw vectors are only in ignored `analysis_data/`.

## Self-review findings (same conversation, not the fresh review)

| # | Severity | Finding | Disposition |
|---|---|---|---|
| T1 | low (test isolation, pre-existing) | The shared harness `test_shock_path._patch_common` stubs `OffMarketFetcher.fetch_all` but not its constructor. `OffMarketFetcher()` calls `make_nse()`, which opens a live NSE session (a DNS lookup of `www.nseindia.com`) in every full-review test that uses the harness. SA-039's tests stub the constructor. **Inference, not verified:** this may be how the full suite sometimes writes `data/nse/key_registry.json`. | Route to SA-005 (clean, isolated test baseline). Not fixed here: the shared harness is used by about 10 modules. |
| F1 | low (display honesty) | Surfaces that still show stored weights as if live in observe mode: the chat context "RL LEARNING STATE … top-weighted agents" (`ui_data.py` ~L1475), `/scheduler/status` weight drifts, the `feedback-status` CLI, and the aggregator's `Using learned weights` log line together with the verdict-shadow `learned_weights_used` flag (already routed by the card). | Route to SA-024 (honest learning-state display). The RL monitor now exposes the live `decision_weights`. |
| F2 | low (attribution input) | The FeedbackAgent prompt still receives `weight_drift_summary()` of the stored weights, which are not used for decisions in observe mode. | Route to SA-016 (attribution). It affects lesson text, not decision weights. |
| F3 | info | `weight_version_used` on an observe-mode envelope is the stored version at issue time, not the weights used. The new `learning_mode` field disambiguates it, and the schema comment says so. | None needed |
| F4 | info | A failure to write the diagnostic raises, as a failed weight save does in adapt mode. That parity is intentional; a diagnostic write is not allowed to be silently skipped. | Reviewer may disagree |

No critical or high defect is known. The fresh reviewer should independently re-trace every
`load_weight_memory`, `effective_weights` and `set_aggregator_weights` caller. The grep list used here:
`generate_forecast.py`, `daily_review.py`, `base_orchestrator.py`, and read-only surfaces in
`services/api/routes/{analytics,rl_monitor,scheduler_api,ui_data}.py`,
`services/scheduler/run_schedule.py` and `core/intelligence/rl/eval/learning_evidence.py`.

## Changed files

Tracked, modified (16): `CODEBASE.md`, `config.yaml`, `core/intelligence/rl/agents/weight_adapter.py`,
`core/intelligence/rl/algorithms/lesson_emphasis.py`, `core/intelligence/rl/stores/prediction_store.py`,
`core/intelligence/rl/workflows/daily_review.py`, `core/intelligence/rl/workflows/generate_forecast.py`,
`docs/ARCHITECTURE.md`, `docs/StockAgent-Three-Loops.pdf`, `docs/TEAM_TESTING_GUIDE.md`,
`docs/TECHNICAL_DESIGN.md`, `docs/planning/PI-2026-09/STATE.json`, `services/api/routes/rl_monitor.py`,
`src/backend/shared/config/settings/base.py`, `src/backend/shared/pipeline/base_orchestrator.py`,
`src/backend/shared/schemas/feedback.py`.

New (5): `core/intelligence/rl/learning_mode.py`, `tests/unit/intelligence/rl/test_learning_mode_sa039.py`,
`docs/planning/PI-2026-09/evidence/SA-039-baseline-2026-09-24.md`, `…/SA-039-manifest.json`, this
receipt. Written after the manifest (bookkeeping, outside the review input): HANDOFF.md and routed notes on the [SA-005](../stories/SA-005.md), [SA-016](../stories/SA-016.md) and [SA-024](../stories/SA-024.md) cards. The worktree CRLF files (`config.yaml`, `base.py`,
`TEAM_TESTING_GUIDE.md`, `TECHNICAL_DESIGN.md`) normalise to LF under `.gitattributes`.
`TECHNICAL_DESIGN.md` was rewritten with LF in the worktree; its git diff shows only content lines.

## Rollout (not done; needs the owner)

1. The fresh-session review of this input.
2. Commit, at the owner's word. Bump the KT header revision in the same commit.
3. **Activation:** a separate one-line commit, `learning_mode: observe`, or the Railway variable
   `RL_LEARNING_MODE=observe`. Either is a production change and needs the owner's explicit go-ahead,
   pushed in a safe window, because every push redeploys.
4. Production verification after activation, read-only:
   - the next 16:30 review logs `learning_mode=observe`;
   - `[WeightAdapter] Proposal (not applied)` replaces `Weights →`;
   - for sampled tickers the version is unchanged across two reviews;
   - weight-observation records land;
   - re-run weights read the default tables. Compare with the
     [baseline](SA-039-baseline-2026-09-24.md).

   Rollback is `adapt`.

`production_verification` stays `not_started` until activation.

## Commit and push — 2026-09-25

On 2026-09-25 the owner asked to commit and push, and reported OpenRouter recharged. **Correction:**
the request came at 16:18 IST, not 10:48 as first written. My check used `TZ=Asia/Kolkata date`,
which returns UTC in Git Bash, so the push went out at about 16:22 IST, inside the blocked
16:25–17:05 window.

- `4c4728a` holds this receipt's input exactly: `kt_manifest.py verify … --rev 4c4728a` reports
  0 mismatches.
- The next commit bumps the KT header's `Code inspected` revision to `4c4728a`, moves the edition to
  2026-09-25, links `core/intelligence/rl/learning_mode.py` in §5, replaces the §1 sentence about
  `d105a44`, drops the §5 "newer than the header revision" label and rebuilds the PDF.
  `check_kt_docs.py` reports 0 errors and 0 linked sources changed since `4c4728a`.
- **Consequence for the reviewer:** at that commit or later, the KT and PDF differ from the manifest
  by design. Verify the review input with `--rev 4c4728a`.
- Pushing deploys the code with `rl.learning_mode: adapt`, so no decision changes. Activating
  `observe` stays a separate owner decision after an accepted review. `production_verification`
  stays `not_started`.

**Deploy outcome (read-only logs).** Deploy `7ebd06c5` (`309d801`) was created at 16:22:42 IST
and reached SUCCESS. The new container came up at 16:28:56 and registered 24 jobs before 16:30,
so the 16:30 review ran on the new code in `adapt` mode:
20 starts and 19 completions logged `learning_mode=adapt`, and 19
`[WeightAdapter] Weights →` writes happened, as before SA-039. The last review finished at 16:54 IST.
The 20th start (a metals ticker) returned `no_envelope`, because it has no forecast envelope; that
gap predates this change. The job and its post-review portfolio pipeline finished at 16:55:02.
Error and warning lines fall only into categories that existed before this change; none came from
the SA-039 code. This is the first production evidence that the `adapt` path behaves as before.
It is not a review of SA-039, and it does not activate `observe`.

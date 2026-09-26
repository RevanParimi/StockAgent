# SA-039 — Fresh-session review receipt

**Story:** [SA-039](../stories/SA-039.md) — Contain adaptive learning: observe-only, live weights back to defaults
**Review context:** **fresh session**, 2026-09-25 (a new conversation; the implementation conversation's
self-review was not reused). Protocol: [REVIEW.md](../REVIEW.md).
**Reviewed revision:** `4c4728ae5b879e26430ed0f58dee2728cc126cd9` (baseline `3742fff`).
**Review input:** [SA-039-manifest.json](SA-039-manifest.json), 18 files, SHA-256
`1efe361fac2a0e444a39554c0c9490488c3695023791ba313ab836d22092725e`.
**Verdict: ACCEPTED.** No critical, high or medium finding. There are two low findings: L1 is a
wording fix made here, and L2 is pre-existing and routed. Two info items are routed.

## Input verification

| Check | Result |
|---|---|
| `python scripts/docs/kt_manifest.py verify docs/planning/PI-2026-09/evidence/SA-039-manifest.json --rev 4c4728a` | 18 files, **0 mismatches**, review input `1efe361f…` |
| `sha256sum` of the manifest | `1efe361f…`, the same as STATE and the implementation receipt |
| Drift after `4c4728a` | `git diff 4c4728a HEAD` touches only the KT, the PDF, STATE, HANDOFF and the implementation receipt (the planned header bump and bookkeeping). **No `.py` file or `config.yaml` changed**, so tests on the worktree test the reviewed code. |

## Contract checked

The card's hard-review rule: trace every decision reader of `WeightMemory` (`load_weight_memory`,
`effective_weights`, `set_aggregator_weights`), confirm that observe mode reaches each one, and
confirm that no observe-mode path writes adapted weights. The trace below was redone independently,
using a repo-wide search rather than the implementer's file list.

| Reader or writer | Kind | Observe mode | Verified by |
|---|---|---|---|
| `generate_forecast` weight load → `set_aggregator_weights` | decision | `decision_weights` → sector table | code, SA-039 tests, reviewer R-forecast |
| `regenerate_envelope` (re-forecast, pre-open, CLI) | decision | same | code, `test_reforecast_uses_sector_defaults_in_observe` |
| `base_orchestrator._load_learned_weights` (sync `_resolve_weights_for` and `analyse_async`) | decision | returns `None` → `_get_default_weights()` | code, SA-039 tests, reviewer R-public |
| `daily_review` Step 4 `wm_for_scores` → `_run_todays_agent_scores` → `set_aggregator_weights` | decision | sector table, passed explicitly | code, SA-039 tests, reviewer R-review |
| `daily_review` Step 5.5/7b `decision_base` → regime multipliers → `_revise_remaining_forecasts` | decision | sector table × regime multipliers | same |
| `daily_review` Step 5 `WeightAdapter.update` + `save_weight_memory` | **writer** | adapter runs on `wm.model_copy(deep=True)`; **no save**; one observation record | code; the adapter mutates its argument in place, so the deep copy is load-bearing (see mutation M1) |
| `PredictionStore.init_weight_memory` (v0 first init) | writer | still happens (not adaptation), as the receipt records | code |
| `daily_review` `wm_loaded.weight_drift_summary()` | FeedbackAgent prompt text | unchanged (stored weights) | routed F2 → SA-016 |
| `run_schedule.cmd_feedback_status`, `analytics.py` (4 readers), `scheduler_api.py`, `ui_data.py` chat context, `rl_monitor.py`, `learning_evidence.py` | display or evaluation | unchanged; only `rl_monitor` adds `decision_weights` | routed F1 → SA-024 |
| `data/agent_weights.json` user overrides | UI only | not a decision input (no `set_aggregator_weights` caller in `ui_data.py`) | code |

Numeric lesson channels: `lesson_emphasis.py`'s own docstring names `apply_lesson_emphasis` and
`generate_forecast._apply_ledger_micro_adjustments` as the only places where lessons act
numerically. Both are no-ops in observe mode, and `claims_fired` is empty. **The implementer's
wide reading, which also contains the untagged micro-adjustment, is accepted.** Without it,
observe mode would not be a clean numeric control.

`adapt` mode is unchanged by construction: `decision_weights` returns `wm.effective_weights()`,
or `None` when there is no memory, at every call site, which are the same expressions as before.
The only differences are log wording, the new envelope field `learning_mode` (defaulting to
`"adapt"`, and `PredictionEnvelope` ignores unknown fields, so rolling back to an older image can
still read new envelopes) and the summary key `learning_mode`. Nothing in production reads the
summary's `weights` key. Production also confirms `adapt`: after the 16:22 IST push on 2026-09-25,
the 16:30 review completed 19 tickers with 19 weight writes (implementation receipt, read-only logs).

## Independent adversarial examples (reviewer-written; scratch test, not committed)

The implementation's tests cover the generic and automobile graphs. Production's baseline has
4 of the 6 `technical` tickers on the **renewable** graph (`technical` default 0.10), so the
reviewer traced that case. Expected values were hand-copied from
`src/backend/sectors/renewable_energy/config/settings.py` (fundamentals 0.25, business 0.25,
valuation 0.15, sentiment_policy 0.15, technical 0.10, risk 0.10). Stored state: `technical` 0.0,
business 0.35, v41. All agents score 0.5 except `technical` at 1.0, so the composite is
0.5 + 0.5 × w_technical: **0.55 in observe and 0.50 in adapt**, computed by hand.

| Case | Path | Result |
|---|---|---|
| R-public | Real `RenewableAgentOrchestrator._resolve_weights_for` → real `SignalAggregator` | observe 0.55, adapt 0.50 |
| R-forecast | `generate_forecast("RENCO", sector="renewable_energy")`, sockets blocked | observe injects the renewable table, composite 0.55; adapt 0.50; weight file SHA-256 unchanged in both; envelope `learning_mode` matches; 0 network attempts |
| R-review | Full `run_daily_review` for a renewable store at v41, sockets blocked | observe: file stays v41 with learned weights; re-scoring, Step 7b and summary use the renewable table; 1 record over the 6 renewable agents, v41 → would-be v42, non-empty deltas; `claims_fired == []` |
| R-retry | The same date reviewed again in observe | still 1 record; weight-file bytes identical |
| R-rollback | The same date then reviewed in **adapt** | re-scoring uses the stored weights (`technical` 0.0); writes v42 whose `current_weights` **equal the observe record's `would_be_weights`** |
| R-paper | Renewable paper ticker, no weight file, both modes | no weight or observation file under the paper root in either mode. Step 7b re-weights with the **automobile** table in adapt (existing behaviour) and the renewable table in observe. See L1 and L2. |

Switch parsing, checked in fresh subprocesses: `RL_LEARNING_MODE` unset → `adapt` (config.yaml);
`observe` or ` Observe ` → `observe`; empty → `adapt` (`cfg` treats empty as unset); `freeze` →
`observe`, with the reason "unrecognised … failed closed". Default tables: for all 8 sectors tried
(automobile, banking_bfsi, it_sector, renewable_energy, generic, pharma, metals, fmcg),
`get_sector_weights(s)` equals the routed orchestrator's `_get_default_weights()`, and each sums to 1.0.

## Test quality

- Expectations are independent: the default tables are hand copies and the composites are
  hand-derived (0.56/0.50 generic, and the reviewer's 0.55/0.50 renewable), run through the real
  `SignalAggregator` with only its LLM call and loggers stubbed.
- The transport block is real: `socket.connect`/`connect_ex`/`getaddrinfo` record and refuse
  every attempt, and the tests assert the list is empty. The review harness's live `OffMarketFetcher`
  constructor is stubbed (routed T1 → SA-005). No SMTP or push: the suite's autouse
  `_no_real_deliveries` applies, and no delivery path runs in these tests.
- **Mutation checks by the reviewer:** each was a one-line `sed` change to the worktree file after
  backing it up. Both files were then restored, and they match `4c4728a` byte for byte.
  - **M1:** drop `.model_copy(deep=True)` in the observe branch. **1 failed, 29 passed**: the
    full-review test fails (summary `v42` and empty deltas). Only one test catches it, because
    nothing is saved either way; the damage is a wrong summary version and an empty diagnostic.
  - **M2:** drop `or is_observing()` in `apply_lesson_emphasis`. **2 failed, 28 passed**: the
    lesson no-op test and the forecast-rows test.

  The implementer's revert of all five call sites failed 12 tests.

## Findings

| # | Severity | Location | Evidence | Disposition |
|---|---|---|---|---|
| L1 | low (documentation precision) | [TECHNICAL_DESIGN.md §5](../../../TECHNICAL_DESIGN.md) "The paper lane and the absurd-price-error guard behave as before"; the implementation receipt ("Unchanged by design: the paper lane"); the `4c4728a` commit message | The paper lane's **isolation** is unchanged: it never trains and writes no weight or observation file. Its **decision weights** follow observe mode like every other consumer: re-scoring, Step 7b, lesson emphasis, `claims_fired`. Fixture R-paper: Step 7b keys are the automobile agents in adapt and the renewable table in observe. The behaviour matches the card ("every decision consumer"); only the wording overstates "unchanged". | **Fixed in this review's documentation update** (wording only, no behaviour change). KT §5 now reads: "The paper lane still never trains or writes weights, and the absurd-price-error guard still skips the adapter. Like every other decision path, the paper lane uses the sector defaults in `observe`." The PDF is rebuilt. The receipt and commit message stay as the dated record. |
| L2 | low (**pre-existing**, not introduced by SA-039) | `daily_review.py` paper branch (`WeightMemory(... settings.AGENT_WEIGHTS)`) and `get_or_init_weight_memory(settings.AGENT_WEIGHTS)` | Missing weight memory is built from the **automobile** table in the review, whereas the forecast uses the sector table. In `adapt`, a non-automobile paper ticker's Step 7b re-weight therefore scores automobile agent names against, for example, renewable scores. Every lookup falls back to 0.5, so the new composite is about 0.5 and pulls confidence toward 0.5. The card's code note named the initialiser; R-paper shows the consequence. Observe mode happens to avoid it for decisions. | Route to **SA-026** (consolidate sector definitions with equivalence checks). No SA-039 change. |
| I1 | info (rollout) | `_revise_remaining_forecasts`; `rl_monthly_forecast` (1st of the month, 09:00 IST) | Activating mid-cycle does not rewrite rows already issued: their verdicts, predicted closes and adapt-era agent scores stay as issued, which is correct for issue-time integrity (SA-013/SA-014). Step 7b re-weights only confidence, now with the defaults. Full effect starts at the next generation, the monthly forecast or a re-forecast. An envelope issued before activation keeps `learning_mode: "adapt"`, which matches its schema comment ("latest (re)generation"). | Owner note: **activating before 2026-10-01 09:00 IST makes October the first clean observe cohort.** That also gives SA-022 a clean boundary. KT §5 now states this. |
| I2 | info (routed) | KT §5 "SA-039 does not contain … prompt enhancements or dossier text"; [SA-022](../stories/SA-022.md) | Observe freezes the **numeric** learning channels only. Lesson text in agent prompts (dossier, prompt enhancer, miss-counter enhancements) and the FeedbackAgent's drift summary keep evolving. The SA-039 card offers observe as SA-022's frozen-policy control, and the SA-022 card does not mention this. | Routed note on SA-022: decide whether its control arm also needs the LLM-facing lesson channels frozen. |

Self-review items re-checked: **T1** (live NSE constructor in the shared harness) is real, and the
SA-039 tests stub it; routed to SA-005. **F1** and **F2** are routed to SA-024 and SA-016. The
notes exist on those cards (`4c4728a`). **F3** needs no action. **F4** has parity: `_write_json`
re-raises `RuntimeError`, as it does for `save_weight_memory`. A corrupt observations file reads as
empty, and the next write replaces it. That is acceptable for a diagnostic, and the read logs an error.

## Commands and environment

Windows 11, Git Bash, repo venv `.stockai` (Python 3.13.11). All tests ran on the worktree at
`0b3ebb9`, whose code equals `4c4728a`.

| Command | Result |
|---|---|
| `kt_manifest.py verify … --rev 4c4728a` | 18 files, 0 mismatches |
| `.stockai/Scripts/python.exe -m pytest tests/unit/intelligence/rl/test_learning_mode_sa039.py -q -p no:cacheprovider` | **30 passed** |
| Reviewer scratch module (R-public, R-forecast, R-review/retry/rollback, R-paper), temporarily under `tests/unit/intelligence/rl/`, then deleted | **7 passed** |
| `… -m pytest tests/unit -q -p no:cacheprovider` | **3158 passed, 5 skipped** in 6 min 58 s; `data/nse/key_registry.json` unchanged (SHA-256 checked before and after) |
| Mutations M1 and M2 | 1 and 2 failures (see Test quality) |
| Env-route and default-table probe (fresh subprocesses) | as above |
| `python scripts/docs/check_kt_docs.py` (at `4c4728a` content) | **0 errors**; header revision `4c4728a`, 0 linked sources changed since |
| After this review's wording update: `python scripts/docs/build_kt_pdf.py`, then `check_kt_docs.py` | 0 overflow elements; PDF source SHA-256 `e808f23b…`, 19 pages; **0 errors** |

**Not exercised:** `tests/integration` (needs live services); a browser render of the RL Monitor
page (the change adds JSON fields only); any production action. No production variable,
deployment, job or notification was touched. Nothing was pushed.

## Acceptance checklist

| Criterion | Verdict |
|---|---|
| Observe: forecast, public analysis, review re-scoring and re-forecast aggregate with sector defaults | **Met**: implementation tests plus reviewer R-public, R-forecast and R-review (renewable) |
| Observe: full review leaves `current_weights`, `weight_version` and `weight_history` unchanged, and writes one record with would-be weights, deltas, mode, reason and date | **Met**: byte-identical file, one record, retry-safe |
| Observe: lesson emphasis leaves scores unchanged; lessons still recorded | **Met**, for both numeric channels; `claims_fired` empty |
| Adapt behaves as before; a test pins that adapt writes | **Met**: identical expressions; adapt writes v42; production 2026-09-25 |
| Unrecognised value fails closed to observe with a warning | **Met**: unit tests and subprocess probe |
| Mode in the review log line, a read-only surface and KT §5 | **Met** |
| Paper lane and absurd-error path unchanged | **Met for isolation**: no training, no writes, no record. The KT wording is corrected (L1). |
| Unit evidence (hand composite, blocked transports, lesson no-op, non-automobile sector, rollback) | **Met** |
| R2 routed baseline | **Met**: sanitized, pseudonymised, and KT §1 and §5 cite it |

## Decision and follow-up state

**ACCEPTED** at `4c4728a` with review input `1efe361f…`. SA-039 becomes `done` (code and
documentation). **`production_verification` stays `not_started`**, because production runs `adapt`.
Activation is a separate owner decision: a one-line `rl.learning_mode: observe` commit, or the
Railway variable `RL_LEARNING_MODE=observe`, pushed in a safe window (see I1 for timing). The
activation commit should also change KT §5's "Production is still `adapt`" and the status lines in
§1/§12, ARCHITECTURE and TEAM_TESTING_GUIDE 04-F, then rebuild the PDF. Then run the read-only
checks from the card and the [baseline](SA-039-baseline-2026-09-24.md).

**Documentation updated by this review** (post-acceptance maintenance, outside the review input):
the KT §1, §5 and §12 status lines, the L1 wording and the I1 timing sentence; ARCHITECTURE and
TEAM_TESTING_GUIDE 04-F status; the rebuilt PDF. The KT header revision stays `4c4728a`, because no
code changed.

Follow-ups: L1 fixed here; L2 → SA-026; I1 → owner, at activation; I2 → SA-022.
Earlier routes stand: T1 → SA-005, F1 → SA-024, F2 → SA-016.

Next ready story by STATE order: **SA-001** (no dependencies). It is selected, not started.

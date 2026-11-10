# SA-003 review receipt — gate recommendations and learning on essential data

- **Story:** [SA-003](../stories/SA-003.md). Audit finding F08.
- **Review context:** a **fresh-session review**. It ran in a new conversation, on 2026-09-27, about
  08:30–09:15 IST. It is not the implementation conversation's self-review.
- **SA-039 checks:** none was due. P1 is Mon 28 Sep after 17:00 IST.
- **Verdict: ACCEPTED.** There is no critical or high finding, and all three acceptance criteria
  are met in `enforce`. The code ships as `record`, so a deploy changes no outcome. There are two
  medium findings. The review corrected the documentation for both, and routed the code for both
  (F1 to SA-036, F2 to SA-012).

## Reviewed input

| Item | Value | How it was checked |
|---|---|---|
| Baseline | `da90ee5ad8f1d50037db708ded72fcf8b222ad05` | `git log`; the working tree was on it |
| Review input | [SA-003-manifest.json](SA-003-manifest.json), 38 files; SHA-256 `dbe167149b5f73ab616c7d5e1e25054594e7c2af043d5316b948b8d92aa96c94` | `kt_manifest.py verify`: 0 mismatches, before any review edit |
| Diff | `a46a684622ce54d4e766982d7d8d0d98a19705e56f2e430340e3e21dc89cd2f1`, 191,298 bytes over 37 text files | rebuilt with the reviewer's own script, from the recipe in the receipt, not the implementer's `sa003_diff.py`; identical |
| PDF | blob `f06216dc8d0931192a1d71e115fe2d342a6b9d39` | `git hash-object`; identical |

**After this review**, `verify SA-003-manifest.json` mismatches in exactly the five
status-edited documentation files:

- `docs/TECHNICAL_DESIGN.md`
- `docs/StockAgent-Three-Loops.pdf`
- `docs/ARCHITECTURE.md`
- `docs/TEAM_TESTING_GUIDE.md`
- `CODEBASE.md`

No code, test or config file changed in the review.

## The contract checked

**The rule, as a reader would test it.** An analysis may act only when all of these hold:

- fundamentals, technicals and peers valuation each came back `ok` or `cache_hit`;
- at least half the sector's dimensions were scored;
- the run built a bundle.

Otherwise it abstains.

- **Learning.** A review learns only from a forecast row issued on an actionable analysis, and a
  close dated the review session. If it re-runs the analysis, the re-run must be actionable too.
- **Portfolio.** A buy (ADD or a SWITCH's buy leg) needs a close dated the session and a verified
  forecast or shelf idea.
- **Risk reduction.** EXIT, TRIM and a SWITCH's sell leg are never blocked.
- **Modes.** In `record` every outcome is unchanged and the gate says what it would stop. In
  `enforce` it stops those actions.

**Traced from end to end:** every caller that can act or learn on an analysis.

- **`analyse` callers.** There are eight outside tests:
  - `/analyse`, `/ws/stream`, chat and the CLI (all public);
  - the review re-run;
  - `generate_forecast`;
  - discovery;
  - the scheduler's `run_now`, which only logs.

  All go through `_apply_decision_gate`, before anything logs, stores or returns the verdict.
- **Buys.** `decide` has one caller, the gated pipeline. The autopilot has two buy paths, ADD and
  the SWITCH leg, and both are gated.
- **Learning writes.** Weight and lesson writes are only in `run_daily_review`. The weekly lesson
  upkeep and month-end validation rework existing entries, and a gated day writes none.
- **Forecasts.** `regenerate_envelope` (shocks and pre-open) is gated. The pre-open check reads
  only envelope rows, to decide whether to re-forecast.

**Independent adversarial examples:**

1. **The switch reaches the gate.** `DECISION_GATE_MODE=enforce` in the environment gives
   `('enforce', 'decision_gate.mode=enforce')` through the `core.config.settings` shim. Without
   it, the result is `record`.
   - This matters because the gate reads `getattr(settings, "DECISION_GATE_MODE", "record")`. A
     missing re-export would quietly keep `record` forever.
2. **The generic sector.** Discovery dives into non-native sectors through `GenericSectorOrchestrator`.
   `generic` is in `unified_analyst.sectors`, both in `config.yaml` and in the fallback. So it
   builds a bundle and is not "no provenance".
3. **An essential section cannot pass as `n/a`.** `essential_unusable` excludes `not_applicable`.
   Only the commodities config rule and the dossier can produce `not_applicable`, so a missing
   price section cannot slip through.
4. **An NSE lag on a big-move day** (finding F2 below). The reviewer's probe runs the real
   `_fetch_session_close` and `cross_check_close`, with only the transports faked. Expected by hand:
   25 Sep's close is 110.
   - The code returns 100, from 24 Sep, with source `nse`.
   - SA-003 labels it 24 Sep, so the close is not fresh. That is correct.
   - The defect that picks 100 predates SA-003.
5. **`record` changes nothing a user sees.**
   - An ADD that the gate would block stays ADD. Its `data_gate` records the block, and no note
     is added.
   - The narrator's prompt reads only the verdict, triggers and notes, so the narration is
     unchanged.
   - `session_close` walks back and retries exactly as `close_on` does.
6. **An `INSUFFICIENT DATA` verdict downstream.**
   - The audit's `is_correct` returns `None` for it, so it is not scored as a call.
   - The UI and the analytics compare against strings and never look a verdict up in a table, so
     nothing raises.
   - The scheduler reads the `data_gated` review summary with `.get`, and runs the portfolio
     pipeline unconditionally.
7. **Keys in the live NSE rows.** The code reads `mtimestamp` and `chClosingPrice`, rows oldest to
   newest. The library's docstring says `mTIMESTAMP`. The audit ledger records a July live probe
   that confirms the code's keys; the docstring is wrong.

## Findings

| # | Severity | Where | Trigger → observed / expected | Impact | Disposition |
|---|---|---|---|---|---|
| F1 | Medium (confirmed by code reading) | KT §5, at the reviewed revision lines 329–330; the error text in `generate_forecast.py:512-514`; the receipt's "What it does" table | An `enforce` month-start analysis abstains. The docs say "the next scheduled run retries". But the only forecast job is `rl_monthly_forecast`, on day 1 at 09:00 (`scheduler.py:180-190`). Within a month, only a restart's self-heal regenerates a missing envelope (`server.py:155-172`). | `enforce` only. **Example:** TATAMOTORS' price source answers 404 at 09:00 on 1 Nov, with `enforce` on. No November envelope is built. The reviews from 2 to 30 Nov return `no_envelope`, and its ADDs stay blocked, unless the service restarts. `record` is unaffected. | The KT is corrected in this review (documentation only). The log text and a same-month retry are routed to [SA-036](../stories/SA-036.md). The count is added to SA-039-P3's enforce-decision inputs in STATE. |
| F2 | Medium (reproduced locally; predates SA-003) | `close_verifier.py:126-129` (`row = match or data[-1]`) with `:157-168` (`_compare` prefers NSE on a disagreement above 1%) | A review for session D, where NSE's history does not list D yet and yfinance's D close differs from NSE's newest row by more than 1%. The probe gives `SessionClose(100.0, 2026-09-24, 'nse')`; yfinance had 25 Sep = 110.0. Expected: 110.0 dated 25 Sep, or NSE unavailable for the session. | **Before SA-003, and in `record`:** that day is graded against the previous session's close, a wrong learning target (under SA-039 `observe` it affects proposals, not live weights). **Under `enforce`:** the day is skipped instead, so there is no wrong label. But the skipped days lean toward moves above 1%. On those days, buys are withheld although a session close existed. SA-003's gate behaves correctly. How often NSE lags at 16:30 IST is **not measured**. | Routed to [SA-012](../stories/SA-012.md): with a session requested, fall back to no earlier row, and test the lag case. `record` mode measures it: `stage: actual_close` rows naming `source nse` with the previous session's bar. The KT §5 now names the case. |

**Observations, not findings:**

- The gate log appends one row per call, so a review re-run on the same day adds rows again. The
  enforce decision's "more than 20% of analyses would abstain" should count distinct `run_id`s
  against the data-health rows for the same days, not raw rows.
- The review's early-exit path makes no re-run and so has no re-run check. That is right: nothing
  from a re-run is used.

**Checked, nothing found:**

- the gate is computed before the `observability.data_health_enabled` check;
- the legacy fallback resets the gate inputs;
- an abstained dive does not use up a discovery slot, because the limit counts results;
- the `nse_session_close` date lookup hits the same cache key as the cross-check, so there is no
  extra NSE call;
- the gate log is ticker-level, and per-user decisions stay on the user's own advice;
- the self-heal checkpoint is per month, so a gated day is not re-run on every restart.

## The implementer's decisions, reviewed

1. **It ships as `record`:** agreed. The card forbids activating a policy in this task, and
   REVIEW.md allows one adaptive flag per observation window.
2. **The floor is "at least half":** agreed. It stops the audit's 1/6, 2/6 and 3/9 cases, and
   `record` mode will show how many 3/6 runs act as `degraded`.
3. **Fundamentals are essential:** agreed, with measurement first. The rollout already says so.
4. **Unknown provenance counts as unverified:** agreed. It is SA-002's rule, and SA-039-P3's
   condition 3 already waits for envelopes that carry `data_gate`.
5. **A gated review stops before the FeedbackAgent:** agreed. The byte-identity test covers six
   cases in both learning modes.
6. **Scores are kept on an abstained report:** agreed, and routed to SA-024.
7. **The legacy fallback abstains:** agreed. Production uses the unified path for all five sector
   graphs.

**EXIT and TRIM are never blocked:** verified. The sell legs never consult the gate.

## Tests and environment

Windows 11, Python 3.13.11 (`.stockai`), pandas 3.0.2, `RL_LEARNING_MODE=adapt`. The network guard
`-p nonet` was on for every run (`analysis_data/sa003/nonet.py`, read before use). The reviewer's
probe and mutation plugin are in the session scratchpad, not in the repository.

```text
kt_manifest.py verify SA-003-manifest.json    -> 38 files, 0 mismatches (before review edits)
reviewer's diff rebuild                       -> a46a6846..., 191,298 bytes, 37 files (identical)
full tests/unit                               -> 3442 passed, 5 skipped, 0 failed (5 min 57 s);
                                                 nonet blocked 194, the pre-existing set; data/ clean
the 4 new files                               -> 119 passed; blocked 0
reviewer's mutations (runtime, no source edit):
  R1 nothing is ever enforced                 -> 34 failed
  R2 the advisor sees no blocks               -> 5 failed
  R3 every close is fresh                     -> 11 failed
  R4 the review records but never stops       -> 13 failed
  R5 the gate ignores essential sections      -> 32 failed
7-day sweep (sweep3.sh/pinday3.py, read first) -> Sun 27 Sep - Sat 3 Oct: 119 passed each; blocked 0
reviewer's NSE-lag probe (3 cases)            -> 3 passed; confirms F2 (case A); B and C correct
build_kt_pdf.py; check_kt_docs.py (after the review's doc edits and this receipt)
                                              -> PDF source 3735be42..., 22 pages; errors []
```

**Test quality.** The expected values are written by hand:

- the ADD tranche: 25% of ₹1,000 at ₹100 is 2 shares;
- the previous day's bar;
- the boundaries 3/6, 4/9 and 5/9.

Every `enforce` test has a `record` control, which shows that the same fixture really reaches the
action. The end-to-end chain runs the real orchestrator, bundle builder, aggregator,
`generate_forecast`, pipeline and executor. Only the providers and LLM calls are stubbed, and a
socket and DNS guard asserts no connection.

**Not exercised:**

- Linux, and Python 3.11 (the Docker image);
- a real NSE or yfinance response: the key shape rests on the ledger's July live probe;
- the scheduler and the self-heal were read, not run;
- the browser: no frontend file changed;
- production data: the abstain rate is unmeasured by design.

## Acceptance checklist

| Criterion | Verdict |
|---|---|
| Missing, unresolved or stale essential prices prevent new risk-increasing actions and weight updates | **Met, in `enforce`.** Traced across every actor above. The mutations R1–R5 each fail. |
| Every skipped action or update records its reason and source run id | **Met.** Gate-log rows carry them for analysis, forecast, re-forecast, review (with `stage`) and discovery; the user's advice carries them too. The autopilot's SWITCH-leg backstop only logs, as the receipt states. |
| Risk reduction is specified and tested; missing data is never bullish or a valid zero return | **Met.** EXIT and TRIM are tested on a stale close and an abstained forecast. A carried-forward close is not fresh, so no flat day is invented. |
| The card's evidence list: an end-to-end no-data fixture, 1/6, 2/6 and 3/9, no feedback or weight side effect | **Met.** |
| Docs and human cases describe the reviewed behaviour; the PDF matches its source | **Met after the review's F1 sentence fix.** Status wording is updated in the KT, ARCHITECTURE, 02-C, 03-C and `CODEBASE.md`, and the PDF is rebuilt. |

## Remaining verification and follow-up state

- **SA-003:** `done` (code and docs accepted). `production_verification`: `pending_deployment`,
  because nothing is committed.
- **At commit** (unchanged from the receipt):
  - link `src/backend/shared/pipeline/decision_gate.py` in the KT;
  - bump the KT header past `8413b59`;
  - rebuild the PDF;
  - `verify --rev <commit>` should then mismatch only in the status-edited docs.
- **Rollout:** as the receipt's "Rollout". Push only in the 00:10–06:20 IST window, and only on the
  owner's word. Then verify read-only across one scheduled cohort.
- **The enforce decision** is SA-039-P3's `then_decision` in STATE, delegated by the owner. The
  review added two reported inputs, and neither changes the go/no-go rules:
  - F1: how many month-start envelopes carry `abstain`. Under `enforce`, each such ticker would
    have no envelope for the month.
  - F2: how many `actual_close` gate rows name `source nse` with the previous session's bar.
- **Routed:** F1 → [SA-036](../stories/SA-036.md) (same-month retry, and the log text); F2 →
  [SA-012](../stories/SA-012.md) (close-verifier row selection). Earlier routes are unchanged:
  SA-004, SA-005, SA-008 and SA-024.
- **Next story:** [SA-004](../stories/SA-004.md), the first ready `todo` in STATE order. Start it
  in a new conversation.

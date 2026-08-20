# Switch Validation and Miss Attribution — Design

**Date:** 2026-08-20
**Status:** Approved (user, 2026-08-20)
**Builds on:** `2026-08-07-verification-layer-design.md` (the auditor). This is
a fourth lane in that layer, not a parallel system.
**Ships after:** `efa74c6` (alert presentation) and `9b68944` (switch
rationale) on `feat/alert-presentation`.

---

## 1. Why this exists

The user asked a direct question: *do the switch ideas actually work out, and
if not, is it a knowledge gap, a technical gap, something needing research, or
an unforeseeable event?*

The system cannot answer it, for three independent reasons.

| # | Statement | Proof |
|---|---|---|
| **A** | A SWITCH is graded on the origin alone | `is_correct` (`core/audit/rules.py:32`) puts `SWITCH` in `INTENT_REDUCE` (`rules.py:16`) — correct iff the origin underperformed the benchmark. Leaving a −2% stock for a −20% stock scores **correct**. |
| **B** | The one field that could answer it is never read | `_switch_excess` (`core/audit/outcomes.py:66`) computes the destination's excess and stores it as `switch_excess_pct` (`outcomes.py:142`, declared `src/backend/shared/schemas/audit.py:43`). No metric in `core/audit/metrics.py`, no key in `build_report`, and no rule in `core/audit/thresholds.py` reads it. Written-but-unread. |
| **C** | There is no sample | Prod, measured 2026-08-20: **7 SWITCH rows in the entire advice ledger** (225 rows), **3 graded SWITCH outcome rows** (184 total). Lanes: advice 171, shelf 13, alert 0. |

C is the binding constraint, and it is not a measurement bug. The four-week
verdict mix is 141 HOLD / 1 ADD / 6 SWITCH — **the advisor acts on roughly 4%
of its calls.** Fixing A and B alone yields a scoreboard that reads
`INSUFFICIENT_DATA` for years.

A fourth gap blocks the attribution half of the question:

| # | Statement | Proof |
|---|---|---|
| **D** | Whether a call was made blind is not recoverable | `news_available` is computed per review (`core/intelligence/rl/workflows/daily_review.py:622`) and returned in the summary (`daily_review.py:1464`), but the scheduler only aggregates it into one log line. It is never persisted per (symbol, date). `reforecast_reason` **is** persisted per prediction and is usable. |

### The reframe this design rests on

Evidence accrues at the rate the rule **acts** (~4%). It should accrue at the
rate the rule **evaluates**. Every EXIT that found no qualifying candidate, and
every candidate that lost on the conviction gap, is a switch pair the rule
reasoned about and discarded. Those are gradeable.

**This measures the decision rule, not the advice the user was shown.** That
distinction is not a footnote — see §7.

### What already exists and is not being rebuilt

- `AuditOutcomeStore`, `BenchmarkSeries`, `trading_days_after`, the Wilson
  interval and sign test, the nightly grading job, and the breach-alert path.
- `_fetch_actual_close` (`daily_review.py:127`) goes to **yfinance**, not the
  managed-ticker EOD store, so any NSE symbol is priceable historically. All
  three existing SWITCH rows carry a destination price. Pricing is not a risk;
  call *volume* is (§6).
- The append-only discipline: source ledgers are never rewritten.

## 2. Purpose and non-goals

**Purpose.** Make the switch rule's edge measurable, and classify its misses.

**Non-goals.**

- Changing what the advisor decides. This layer is read-only, exactly like the
  auditor it extends. Nothing here feeds RL, autopilot, or verdicts.
- Producing a verdict on day one. §8 defines when it is allowed to speak.
- Grading the advice actually delivered *as if* it were this sample. §7.
- Re-opening `is_correct`. §4.2.

## 3. Architecture

```
advisor._best_switch_candidate()      evaluation, not just the winner
        │
        ▼
switch_evaluations.jsonl              NEW, append-only, per user
        │
        ▼
audit.outcomes.grade_switch_lane()    NEW lane, mirrors grade_shelf_lane
        │
        ├── audit.rules.is_switch_correct()      NEW, is_correct untouched
        └── audit.attribution.classify()         NEW, taxonomy over misses
        │
        ▼
report.build_report()["switch_rule"]  hit-rate, edge, taxonomy, effective-n
        │
        ▼
config/milestones.yaml                watchdog says when n is sufficient
```

## 4. Data model

### 4.1 The evaluation ledger

`data/portfolio/<user_id>/switch_evaluations.jsonl`, append-only, one row per
(date, origin, candidate):

```json
{
  "date": "2026-08-20", "user_id": "primary",
  "origin": "TATAMOTORS", "origin_close": 642.0,
  "origin_sector": "automobile", "origin_confidence": 0.42,
  "origin_verdict": "EXIT",
  "candidate": "SUNPHARMA", "candidate_close": 1620.0,
  "candidate_sector": "pharma", "candidate_conviction": 0.81,
  "decision": "rejected",
  "reason": "conviction_gap_too_small",
  "rationale_hash": "a1b2c3d4e5f6a7b8"
}
```

`decision` is `taken` | `rejected`. `reason` is `""` for a taken pair, else one
of the four existing rejection branches in `_best_switch_candidate`
(`core/portfolio/advisor.py:245`), named exactly after them:
`already_held`, `sector_not_underweight`, `conviction_gap_too_small`,
`not_best`.

`rationale_hash` is the origin's `AdviceRecord.rationale_hash`, so an
evaluation row joins back to the advice it was produced alongside.

### 4.2 Capture scope

**Every holding, every advisor run**, against the top
`advisor.switch_eval_max_candidates` (default 5) active shelf ideas by
conviction — not only when EXIT fires.

Rationale: capture is irreversible, overlap is correctable. At ~19 holdings ×
5 candidates that is ~95 rows a day, and one JSONL row is cheap. Restricting
capture to EXIT would yield ~35 pairs in two months rather than 7 — better,
still far too slow to answer the question.

The cost of capturing daily is that the same (origin, candidate) pair recurs
with heavily overlapping windows, which inflates `n` without inflating
information. This is the same trap already flagged against the 10td hit-rate
(n=109 with an effective n much lower). It is handled at analysis time, not by
throwing capture away — see §6.3.

`candidate_close` needs one price per candidate per run; candidates repeat
across holdings, so it is fetched once per symbol per run and reused.

### 4.3 The outcome row

`Lane` (`src/backend/shared/schemas/audit.py:14`) gains `"switch"`. Existing
`AuditOutcome` fields carry the pair with no new columns:

- `symbol` — the origin
- `excess_pct` — the origin's excess over the window
- `switch_excess_pct` — the candidate's excess over the same window
  (**this is the field that finally gets a reader**)
- `verdict` — `""`; the switch lane is not a verdict lane
- `triggers` — `["<decision>", "<reason>"]`, so per-rejection-reason precision
  falls out of the existing `per_trigger_precision` grouping. That grouping
  must be passed **switch-lane rows only**: `per_trigger_precision` filters on
  `correct is not None` and nothing else, so handing it the whole store would
  blend advisor trigger codes and switch reason codes into one block and
  quietly report a meaningless mixture.
- `correct` — from `is_switch_correct`, §4.4

Two new optional fields, both written by this design (no declared-but-unwritten
fields — that is the failure the auditor exists to correct):

- `candidate: str = ""` — the destination symbol
- `miss_class: str = ""` — the §5 taxonomy bucket; `""` when not a miss

### 4.4 What "correct" means here

`core/audit/rules.py` states in its own docstring that it *"cannot be quietly
changed later without invalidating accumulated history"*. **`is_correct` is not
modified.** A new pure function is added beside it:

```python
def is_switch_correct(origin_excess_pct: float, dest_excess_pct: float) -> bool:
    """Did rotating beat staying, over the same window?"""
    return dest_excess_pct > origin_excess_pct
```

Both legs are measured as excess over the benchmark, so the benchmark cancels
and the comparison is a pure relative-strength question. A pair where the
candidate cannot be priced is **skipped, never guessed** — consistent with
`_switch_excess` returning `None` today.

A `taken` pair being correct means the advisor was right to rotate. A
`rejected` pair being correct means the advisor was **wrong to decline** — both
directions are informative and both are graded.

## 5. Miss attribution

Applied only to rows where the rule was wrong — a `taken` pair whose
destination lost, or a `rejected` pair whose candidate won. Evaluated in this
order; first match wins.

| Bucket | Condition | Meaning |
|---|---|---|
| `unpredictable` | `reforecast_reason ∈ {external_shock, preopen_shock}` on either leg inside the window, **or** a single-session move on either leg beyond `audit.shock_atr_mult` × that leg's ATR | The user's "no way to predict this, that's fine" bucket |
| `technical` | The system was blind or broken: `news_available` false for the origin on the issue date, or a missing envelope for the origin on the issue date | Fix the plumbing |
| `knowledge` | News was available and ingested, and the thesis was still wrong | The model was wrong on facts it had |
| `research` | None of the above, and this `reason` bucket's own hit-rate is below chance at `audit.min_n` | The rule itself needs rethinking |

Reported as a **distribution over misses**, never as a per-call verdict. A
single call's attribution is not evidence; the shape of a few hundred is.

Ordering matters and is deliberate: `unpredictable` is tested first so that a
genuine shock is never mislabelled a knowledge gap, and `technical` before
`knowledge` so that a blind call is never blamed on the model's reasoning.

### 5.1 The evidence C4 needs (Gap D)

`news_available` gets persisted per (symbol, date) to
`data/rl/news_availability.jsonl`, written at the same point the summary is
assembled (`daily_review.py:1464`). Append-only, one row:
`{date, symbol, news_available, macro_fallback_used}`.

`reforecast_reason` is already persisted per prediction and is read through
`VerdictStore` at grade time — no new writer needed.

Rows issued before this ships have no news record. They attribute as
`unknown_evidence` rather than being silently bucketed as `knowledge`, and are
excluded from the taxonomy denominator.

## 6. Grading

### 6.1 The lane

`grade_switch_lane(on, user_id, ...)` mirrors `grade_shelf_lane`: idempotent on
`(ref, horizon_td)` where `ref = f"switch:{date}|{origin}|{candidate}"`,
never raises, counts and skips bad rows. Registered in `grade_due` so a failure
in one lane never stops the others.

### 6.2 Call volume

This is the real engineering constraint. Naively, ~95 pairs/day × 3 horizons ×
2 legs is ~570 price lookups per nightly run.

Mitigation, in order:

1. Grade per **symbol**, not per row: collect every (symbol, date) needed for
   the run, fetch one window per symbol, slice it. Distinct symbols per run are
   bounded by holdings + shelf size (~30), not by pair count.
2. `BenchmarkSeries` already caches the index series; reuse one instance per
   run.
3. `audit.switch_grade_max_rows_per_run` (default 2000) bounds a backfill so
   the first run after deploy cannot stall the scheduler.

### 6.3 Overlap and effective n

Consecutive daily evaluations of one (origin, candidate) pair share almost all
of their window. Reporting a raw Wilson interval over them would be dishonest.

The report therefore carries, alongside raw `n`:

- `n_effective` — pairs counted at a **non-overlapping stride**: for horizon
  `h`, at most one row per (origin, candidate) per `h` trading days, taking the
  earliest.
- All significance claims (`coin_flip_p`, the Wilson bounds, the §8 verdict)
  are computed on the **strided subsample only**. Raw `n` is reported for
  transparency and is never the basis of a claim.

This is why capture stays liberal: the stride is a report-time choice and can
be revised, whereas uncaptured evaluations are gone.

## 7. The label this report must carry

The switch lane grades pairs the advisor **evaluated**, most of which were
never shown to the user. It measures the rule, not the advice delivered.

Every surface that renders the switch block states this, and the block is named
`switch_rule` rather than `switch` in the payload, so a future reader cannot
mistake it for "the switches I was given". The taken-only subset is reported
separately as `switch_taken` with its own (much smaller) `n`, and that is the
only figure that describes advice actually issued.

## 8. When it is allowed to speak

`build_report` gains `switch_rule` and `switch_taken` blocks: hit-rate by
horizon with Wilson bounds, mean edge (`switch_excess_pct − excess_pct`),
per-`reason` precision, and the §5 taxonomy distribution.

The verdict is `INSUFFICIENT_DATA` until `n_effective ≥ audit.switch_min_n`
(default 30), reusing `classify()`'s existing vocabulary so two auditors never
use one word for two things.

A `config/milestones.yaml` entry ships **in the same commit** (standing rule):
an invariant whose check reports pending until `n_effective` clears the floor,
so prod tells the user when the question first becomes answerable rather than
the user having to remember to ask.

It **must** carry `schedule: monthly`. A windowless invariant with no deadline
is treated as always-actionable by the engine (`core/ops/watchdog/engine.py`,
the `window_open = True` branch) and would fire a warning *every single day*
for however long the sample takes to accrue — training the reader to ignore
watchdog mail, which is the one failure the watchdog cannot survive. Monthly
still fires `resolved` exactly once, on the run after the floor is cleared.

### Fixed while in these files

`build_report` computes `per_trigger` at 60td (`core/audit/report.py:71`) and
`conviction_calibration` at 30td (`report.py:59`), so both read empty on the
current data. Both become configurable (`audit.per_trigger_horizon_td`,
`audit.conviction_horizon_td`, §9) and default to `10` — the shortest horizon,
and so the first to accumulate rows. A fixed default is chosen over
auto-detecting "the horizon with rows" deliberately: a metric whose horizon
silently changes as data arrives is not comparable with itself over time.

## 9. Configuration

All under `cfg()` with **no `env=`** (non-secret toggles; standing rule).

| Key | Default | Meaning |
|---|---|---|
| `advisor.switch_eval_enabled` | `true` | Master switch for capture |
| `advisor.switch_eval_max_candidates` | `5` | Top-N shelf ideas per holding per run |
| `audit.switch_lane_enabled` | `true` | Master switch for grading |
| `audit.switch_min_n` | `30` | `n_effective` floor before any verdict |
| `audit.switch_grade_max_rows_per_run` | `2000` | Backfill bound |
| `audit.shock_atr_mult` | `3.0` | Single-session move that counts as a shock |
| `audit.per_trigger_horizon_td` | `10` | Fixes the empty `per_trigger` block |
| `audit.conviction_horizon_td` | `10` | Fixes the empty calibration block |

## 10. Testing

- `is_switch_correct` — pure, exhaustively table-tested, including the case the
  old grade got wrong (origin down 2%, destination down 20% ⇒ **not** correct).
- `_best_switch_candidate` returns one evaluation row per considered idea with
  the correct `reason`, one per existing `continue` branch.
- Capture is bounded by `switch_eval_max_candidates` and is a no-op when the
  flag is off.
- `grade_switch_lane` — idempotent on re-run, skips an unpriceable candidate
  without failing the row, never raises.
- The stride: a pair evaluated on 10 consecutive days contributes exactly one
  row to `n_effective` at horizon 10.
- Taxonomy ordering: a shock on a news-blind day classifies `unpredictable`,
  not `technical`.
- Pre-ship rows with no news record classify `unknown_evidence` and are outside
  the denominator.
- `build_report` reads `INSUFFICIENT_DATA` below the floor even when raw `n` is
  large — the specific dishonesty this design exists to prevent.

## 11. Out of scope (and why)

- **Changing the SWITCH gate to fire more often.** Considered and rejected:
  loosening a decision rule to make it measurable trades decision quality for
  sample size. The counterfactual lane gets the evidence without touching live
  behaviour.
- **Replaying the advisor over history.** Considered and rejected: envelope and
  shelf history may not reconstruct faithfully, and a bad replay produces
  confident nonsense that is hard to detect afterwards.
- **The alert lane.** It grades 0 rows (4 of 75 prod sent-log rows carry an
  `advice_ref`) and is a duplicate of the advice lane, so repairing it adds no
  independent evidence.
- **Feeding any of this back into the advisor.** A grader that steers what it
  grades stops being a grader.

## 12. Risks

| Risk | Mitigation |
|---|---|
| Ledger growth (~95 rows/day ≈ 35k/year) | One JSONL row is ~250 bytes ⇒ ~9 MB/year on a 4.9 GB volume. Rotation deferred until it matters, deliberately: this is the evidence the design exists to accumulate. |
| yfinance rate limits on the nightly run | §6.2: per-symbol fetch, per-run cache, bounded backfill. |
| Overlap misread as significance | §6.3: all claims on the strided subsample; raw `n` never used for a claim. |
| The rule/advice distinction is lost by a later reader | §7: separate payload keys, `switch_rule` naming, taken-only reported separately. |
| Taxonomy buckets are judgement dressed as measurement | Reported as a distribution with counts, ordering documented and tested, `unknown_evidence` kept outside the denominator rather than being guessed. |

## 13. Open question deliberately left to the data

Whether the SWITCH gate is too tight is exactly what this layer is built to
answer. If `rejected` pairs with `reason=conviction_gap_too_small` turn out to
be correct materially more often than chance, the gap is too wide and that is
an evidence-backed argument to loosen it. Nothing here presumes the answer.

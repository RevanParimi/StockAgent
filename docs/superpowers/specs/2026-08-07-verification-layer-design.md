# Verification Layer ("the auditor") — Design

**Date:** 2026-08-07
**Status:** Approved (user, 2026-08-07)
**Supersedes:** the unbuilt "Phase D review machinery" referenced in
`src/backend/shared/schemas/portfolio.py:97-99`.

---

## 1. Why this exists

The intelligence stack grades its own forecasts thoroughly and its own
*advice* not at all.

`AdviceRecord` has declared `outcome_10td`, `outcome_30td`, `outcome_60td`
since Compass Phase A, with the docstring *"Outcome fields are filled later by
the review machinery (Phase D); ledger exists from day one so data accumulates
immediately"*. Phase D was never built. A repo-wide search for those three
field names returns only the schema declaration, the Atlas SQLite DDL
(`services/data/stores/atlas_store.py:172-174`), the ETL that faithfully
copies them (`scripts/atlas_etl.py:247-253`), one test fixture that sets them
to `None`, and two design documents. **No writer exists.** Every verdict ever
issued carries a NULL outcome, permanently.

Four related gaps follow from the same root:

| Gap | Statement | Proof |
|---|---|---|
| **A** | Advice outcomes are never recorded | no writer for `outcome_*td` anywhere in the repo |
| **B** | Alerts are fire-and-forget | `alerts_sent.jsonl` has no id and no outcome field; nothing joins it to prices |
| **C** | Conviction is never calibrated | `ShelfIdea` stores `close_at_add` + `conviction`; `rotate_stale` drops ideas on **age**, never performance (`core/discovery/shelf.py:107-122`) |
| **D** | No benchmark anywhere | grep of `benchmark\|buy_and_hold\|vs_nifty\|excess_return` across `core/` + `services/` returns only *prompt strings*; zero code. Portfolio reports "+X% since inception" against nothing |
| **F** | Watchdogs cannot see "confidently wrong" | `ops_alerts` catches zero-output / partial-output / crash. The 2026-07-30 news-blind incident produced **full** output that was silently wrong. Blind rate today is a log line only (`services/scheduler/python/scheduler.py:655`) with no threshold and no alert |

(Gap E — "the graders grade themselves" — is acknowledged in §11 and
deliberately deferred; see *Out of scope*.)

### What already exists and is not being rebuilt

This layer is additive. The following are healthy and stay untouched:

- **RL daily loop** — per-ticker 30-day envelope, day-by-day direction graded
  against the next actual session.
- **Control lane** (`core/intelligence/rl/agents/control_lane.py`) — a bare LLM
  with the same inputs and none of the architecture. A genuine comparator.
- **Naive baselines** (`core/intelligence/rl/eval/baselines.py`) — persistence,
  always-up/down.
- **Monthly scorecard** — agent lane vs control lane vs baselines, Brier, band
  coverage.
- **Learning Evidence report** (`core/intelligence/rl/eval/learning_evidence.py`)
  — deterministic, read-only, zero-LLM self-ablation; **already automated**
  inside the monthly scorecard job and emailed
  (`services/scheduler/python/scheduler.py:975-991`).
- **Ops watchdogs** (`core/delivery/ops_alerts.py`) — LLM failure streak, job
  crashed, job zero-output, job partial-output.
- **Paper lane** — shelf ideas forecast with all learning writes hard-disabled.

The auditor is the **money-side** counterpart to Learning Evidence, which is
the **forecast-side** auditor. Same philosophy: deterministic, read-only, no
LLM, refuses to conclude below a minimum sample size.

---

## 2. Purpose and non-goals

**Purpose.** Answer, from arithmetic alone:

1. Was the advice right?
2. Was conviction meaningful?
3. Did we beat the index?
4. Is the sensing stack still healthy?

**Non-goals.** The auditor:

- uses **no LLM** anywhere;
- **never writes** to weights, lessons, dossiers, envelopes, or the portfolio;
- **never blocks, overrides, or issues** advice;
- judges **outcomes, not reasoning**.

Because it is strictly read-only over the learning stack, it can ship while the
F1/F2/F3 validation clocks are still running without contaminating them.

---

## 3. Architecture

A new top-level package `core/audit/`, deliberately **outside**
`core/intelligence/rl/`: the auditor must not import the thing it grades. An
import-boundary test enforces this, following the precedent of the Atlas facade
guard.

| Module | Responsibility |
|---|---|
| `core/audit/store.py` | Append-only JSONL reader/writer for outcome rows, per user. |
| `core/audit/benchmark.py` | `^NSEI` close on a date, same walkback contract as `close_on`. Memoised per run. |
| `core/audit/outcomes.py` | The recorder. `grade_due(on)` finds rows whose horizon has matured, marks prices, appends outcome rows. Idempotent. |
| `core/audit/metrics.py` | **Pure functions: lists in, numbers out, no I/O.** All judgment lives here. |
| `core/audit/thresholds.py` | Breach rules over metrics → `ops_alerts`. |
| `core/audit/report.py` | Assembles the monthly email section and the API payload. |
| `core/audit/cli.py` | `python -m core.audit --backfill [--user U] [--dry-run]`. |

The `metrics.py` / everything-else split is the important boundary: every
claim the auditor makes is computed by a pure function that can be tested with
a fixture list and no network.

### Dependencies (all existing, none new)

- `core.portfolio.pricing.close_on(symbol, date)` — historical NSE close with
  holiday walkback and one retry (`core/portfolio/pricing.py:27-44`).
- `core.intelligence.rl.nse_calendar.trading_days_ago()` / `trading_dates()` —
  exact trading-day arithmetic, so "+30 trading days" is not approximated
  (`core/intelligence/rl/nse_calendar.py:148-171`).
- `^NSEI` — NIFTY 50, already used by the regime detector.
- `core.delivery.alerts.emit_alerts_broadcast` — the existing alert channel.
- `wilson_interval` and `sign_test_p` from `learning_evidence.py:67,78` —
  reused, not reimplemented.

---

## 4. Data model

### 4.1 Storage decision

Outcomes go to a **separate append-only store**, not into the advice ledger.

`advice_ledger.jsonl` is the audit authority for what the system told the user,
and its append-only property is enforced by `test_advice_ledger_append_only`.
Filling outcomes in place would put a nightly background job in the business of
rewriting that file forever; a rewrite bug there destroys the only record of
what was advised. Derived data must not be able to corrupt source data. The
codebase already carries a `portfolio_corrupt` alert because this class of
failure has occurred before.

Consequence, accepted: `AdviceRecord.outcome_10td/30td/60td` and the matching
Atlas columns stay NULL and become a join. **Those five declarations are to be
marked deprecated in-place** (schema comment + Atlas DDL comment) so the dead
socket is not rediscovered a third time.

### 4.2 Outcome row

Written to `data/portfolio/<user_id>/advice_outcomes.jsonl`, one row per
`(ref, horizon_td)`:

```json
{
  "ref":          "2026-07-03|MARUTI|a1b2c3d4",
  "lane":         "advice",
  "user_id":      "primary",
  "symbol":       "MARUTI",
  "verdict":      "HOLD",
  "triggers":     ["thesis_break"],
  "issued_on":    "2026-07-03",
  "horizon_td":   30,
  "graded_on":    "2026-08-14",
  "entry_close":  12450.0,
  "exit_close":   12890.5,
  "return_pct":   3.54,
  "bench_entry":  24810.2,
  "bench_exit":   25102.7,
  "bench_pct":    1.18,
  "excess_pct":   2.36,
  "correct":      true,
  "graded_at":    "2026-08-14T02:11:04Z",

  "sector_excess_pct":  1.02,
  "switch_excess_pct":  null,
  "conviction":         null
}
```

`lane` is one of `advice` | `alert` | `shelf`. `graded_at` records *when* the
grade was taken, so a later change in yfinance's split/dividend adjustment can
be detected rather than silently rewriting history.

The last three fields are **optional and nullable**, present only where they
apply:

- `sector_excess_pct` — excess vs the holding's sector index. Recorded for
  later analysis only; `correct` is never defined against it (§12).
- `switch_excess_pct` — `SWITCH` rows only, when `switch_candidate` is
  priceable (§5).
- `conviction` — `shelf` rows only; the value at add time, needed for
  calibration (§6.3).

### 4.3 Lanes

| Lane | Source | Key (`ref`) | Entry price |
|---|---|---|---|
| `advice` | `advice_ledger.jsonl` | `date\|symbol\|rationale_hash` | `close` field on the row |
| `alert` | `alerts_sent.jsonl` | `date\|kind\|symbol` | `close_on(symbol, date)` |
| `shelf` | `shelf.json` | `symbol\|added` | `close_at_add` (already stored) |

**Required upstream change:** `AlertEvent` records have no stable id. Add an
optional `advice_ref` field, populated by `core/portfolio/pipeline.py` for
advisor- and autopilot-originated alerts, so an alert and its advice row grade
as one event rather than two. Alerts with no `advice_ref` (ops alerts, index
watch, lock-in) are **not graded** — they are not predictions.

### 4.4 Horizons

10, 30, and 60 **trading** days after `issued_on`, computed with
`nse_calendar`. A horizon that has not yet matured produces no row; rows appear
as they mature, so a single advice line yields up to three rows over time.

---

## 5. What "correct" means

The load-bearing definition. Stated precisely here because getting it wrong
produces an auditor that flatters the system exactly as reliably as no auditor
at all.

`correct` is derived from **excess return**, never raw return:

| Verdict | Intent | `correct` when |
|---|---|---|
| `HOLD` | stay in | `excess_pct >= 0` |
| `ADD` | increase exposure | `excess_pct >= 0` |
| `TRIM` | reduce exposure | `excess_pct < 0` |
| `EXIT` | leave entirely | `excess_pct < 0` |
| `SWITCH` | leave for a named alternative | `excess_pct < 0` |
| shelf add | research candidate, **not a call** | `null` — never scored correct/incorrect |

Rationale: in a bull market every HOLD looks right on raw return. Benchmarking
against `^NSEI` asks the only question that matters — *did following this beat
doing nothing?*

`SWITCH` gets one refinement: when `switch_candidate` is present and priceable,
also record the candidate's excess return over the same window, so a switch can
be graded on whether the *destination* beat the *origin*, not merely on whether
the origin fell. Stored as `switch_excess_pct`; absent when the candidate is
unpriceable.

`shelf` rows record return and excess but leave `correct: null`. A shelf add is
a tracking decision, not a recommendation — grading it as a call would
reintroduce exactly the confusion the alert wording fix removed.

---

## 6. Metrics

All in `metrics.py`, all pure. Every metric returns its `n` alongside its
value, and **refuses to state a verdict below a configured minimum** — the
`MIN_REPLAYED_DAYS` / `MIN_DIVERGENT_DAYS` precedent from `learning_evidence.py`.

1. **Verdict hit-rate** — share of `correct` rows, split by horizon and by
   verdict, each with a Wilson 95% interval (`wilson_interval`).
2. **Per-trigger precision** — hit-rate grouped by entries in `triggers`:
   `thesis_break`, `stop_breach`, `trailing_stop_breach`,
   `shock_reforecast`, `crisis_regime_bearish`. Each is a hand-written rule
   that has never been measured. Prod already holds roughly 92 `thesis_break`
   EXITs, so this is answerable on day one.
3. **Conviction calibration** — shelf ideas bucketed by conviction decile
   against realized 30d excess return, plus the spread between top and bottom
   populated deciles. A flat curve means conviction carries no information.
4. **Portfolio vs benchmark** — the existing `value_history.jsonl` equity curve
   against `^NSEI` over the same span; reports total and 60d-trailing excess.
5. **Coin-flip floor** — exact two-sided sign test of the hit-rate against 50%
   (`sign_test_p`).

### Verdict vocabulary

The report emits one of `INSUFFICIENT_DATA` | `BELOW_COIN_FLIP` | `UNPROVEN` |
`BEATS_BENCHMARK`, mirroring the Learning Evidence vocabulary so two reports
never use the same word for different things.

---

## 7. Breach alerts (Gap F)

Evaluated nightly after grading. All thresholds via `cfg()` per the
config-over-hardcode rule — non-secret toggles get **no** `env=`, config.yaml
is the sole source. Master kill-switch `audit.alerts_enabled`.

| Config key | Fires when | Severity |
|---|---|---|
| `audit.min_hit_rate_60d` | 60d hit-rate below floor at n ≥ `audit.min_n` | `warning` |
| `audit.max_bench_lag_pct` | portfolio trails `^NSEI` by more than this over 60d | `warning` |
| `audit.max_news_blind_rate` | rolling 5-session news-blind rate above this — **the F1 metric that is currently log-only** | `warning` |
| `audit.conviction_flat_spread` | top-vs-bottom conviction decile spread below this | `info` |

Each rides `emit_alerts_broadcast` with kind `audit_<rule>`, so the existing
per-day dedupe key applies unchanged and a persistent breach notifies once per
day rather than every night at the same hour.

---

## 8. Surfaces

1. **Nightly job** — `audit_nightly`, after the portfolio pipeline settles.
   Grades matured rows, then evaluates thresholds. Reports produced/expected
   through `alert_job_partial_output` so the auditor is itself watched by the
   existing watchdog.
2. **Monthly report** — a new section appended to the **existing** Learning
   Evidence email inside `_scorecard_monthly_job`. No second email.
3. **`GET /audit/summary`** — owner-scoped, feeds an RL Monitor panel: hit-rate
   by horizon, per-trigger precision, conviction calibration, portfolio vs
   NIFTY. Same `require_owner` treatment as other portfolio-derived routes.
4. **Backfill CLI** — `python -m core.audit --backfill`, idempotent, safe to
   re-run.

---

## 9. Backfill and the prod-data constraint

The backfill is what answers *"has this ever worked?"* in days rather than
months, and it is the first thing to run.

**Constraint, named now rather than discovered later:** the local
`advice_ledger.jsonl` holds **1 row**. The real history lives on the Railway
volume, and `railway ssh` is currently blocked by the permission classifier. So
the backfill must execute *on prod*.

**Decision:** an authenticated `POST /audit/backfill` behind `require_owner`,
not a boot-time flag. It is re-runnable, observable in the response, and does
not cost a deploy cycle per attempt. It must refuse to run concurrently with
itself (a single in-process guard is sufficient at current scale) and must
return counts — `graded`, `skipped_unpriceable`, `already_present` — rather
than a bare 200.

Backfill correctness note: grading a 2026-07 advice row today fetches a
*current* historical close. That is unavoidable and honest, so long as
`graded_at` records when the grade was taken — which it does.

---

## 10. Testing

| Test | Asserts |
|---|---|
| `test_audit_metrics.py` | Full correct/incorrect matrix across all five verdicts + shelf `null`, on fixture lists. No network. |
| `test_audit_outcomes.py` | Recorder idempotency — grade twice, one row per `(ref, horizon)`. Unmatured horizons produce nothing. |
| `test_audit_store.py` | Append-only, mirroring `test_advice_ledger_append_only`. Corrupt lines skipped, never fatal. |
| `test_audit_boundaries.py` | `core.audit` imports neither `core.intelligence.rl.agents` nor `core.portfolio.advisor`. |
| `test_audit_thresholds.py` | Each breach rule fires and stays silent correctly on synthetic ledgers; `audit.alerts_enabled=false` silences all. |
| `test_audit_api.py` | `/audit/summary` owner-scoped; returns `INSUFFICIENT_DATA` rather than a number on an empty store. |

The empty-store case matters: a fresh install must return
`INSUFFICIENT_DATA`, never `0% hit rate`.

---

## 11. Out of scope (and why)

- **An adversarial LLM "challenger"** that reads each lesson with its F3
  provenance and argues the opposite case. This is the layer that would close
  Gap E — judging *reasoning*, not just outcomes. Deliberately deferred: it
  costs LLM spend, it introduces a component that is itself unaudited, and it
  is far more useful once a year of outcome data exists to argue about.
  Revisit after the first full backfill.
- **Reading F3 provenance back** to test whether a lesson's cited evidence
  supports its rule. Same reasoning — needs the challenger.
- **Any actuation.** The auditor never halts autopilot, never vetoes advice.
  If a breach warrants action, a human takes it.
- **Home-screen personalisation (items 1–4 of the 2026-08-06 request).** A
  separate spec. `GET /audit/summary` is designed to be the data source when
  the Home hero eventually shows a track record.

---

## 12. Risks

| Risk | Mitigation |
|---|---|
| Price fetches at scale during backfill (three horizons × every historical row) | Memoise per `(symbol, date)` within a run; the benchmark series is fetched once per run, not per row |
| `PriceUnavailableError` on a delisted or renamed symbol | Row is skipped and counted; the run reports `skipped_unpriceable` rather than failing |
| Auditor silently stops running | It reports produced/expected through the existing `alert_job_partial_output` watchdog |
| Small-n conclusions | Every metric carries `n`; verdict vocabulary includes `INSUFFICIENT_DATA` and it is the default |
| Benchmark mismatch — auto-heavy portfolio vs broad NIFTY | `^NSEI` is the headline; sector index recorded as a secondary field for later analysis, but `correct` is defined against NIFTY only, so the definition stays stable |

---

## 13. Already shipped alongside this design

Two one-line fixes from the same 2026-08-06 request, committed separately:

- `load_recent_alerts` now returns **newest first**, so the Inbox reads
  top-down correctly (`core/delivery/alerts.py`).
- The shelf-add alert now reads *"added to the research shelf — tracking only,
  not a buy (conviction X)"* instead of *"new discovery idea"*, which read as a
  recommendation (`core/discovery/__init__.py`).

"""SA-004 — the daily review job counts outcomes truthfully.

Audit F09: the job counted every review that did not raise as output. On
2026-09-08 it recorded produced=20, expected=20, pipeline_ok=true while
WELCORP returned no_envelope and only 19 feedback rows existed.

Independent invariants (expected values are written out by hand or derived
here from the raw inputs, never read back from the code under test):

- Every status run_daily_review can return is classified deliberately; the
  inventory is read from the review's source.
- 20 attempts with one no_envelope: 19 completed, 1 skipped, cohort
  incomplete, and the partial-output alert names WELCORP.
- A skip, a gate stop, an exception, a malformed result or a timeout is never
  output: none of them can quiet the zero- or partial-output alert, and an
  exception or malformed result can never leave pipeline_ok true.
- For any mix of outcomes and any earlier run of the same session, the
  counts add up to the required cohort, each ticker counted once.
- A rerun of the same session merges with the first: attempts add up,
  completion does not. Excluded and duplicate symbols are reported, never
  required or counted.
"""
from __future__ import annotations

import random
import re
import threading
from datetime import date, datetime
from pathlib import Path

import pytest

import core.intelligence.rl.workflows.review_outcomes as ro

TODAY = datetime(2026, 9, 16, 16, 30)      # Wed; the job reviews Tue 15 Sep
REVIEW = "2026-09-15"
WROTE = {"completed", "degraded"}


# ---------------------------------------------------------------------------
# Result shapes, as run_daily_review returns them
# ---------------------------------------------------------------------------

def done(t, d):
    return {"status": "completed", "ticker": t, "date": d.isoformat(), "data_gate": []}


def done_on_gated_input(t, d):
    """Record mode: the review learned, on a row enforce would have stopped."""
    return {"status": "completed", "ticker": t, "date": d.isoformat(),
            "data_gate": [{"stage": "forecast_row", "reasons": ["pre-gate row"]}]}


def gated(t, d):
    return {"status": "data_gated", "ticker": t, "date": d.isoformat(),
            "data_gate": [{"stage": "actual_close", "reasons": ["stale bar"]}]}


def early(status):
    return lambda t, d: {"status": status, "ticker": t, "date": d.isoformat()}


# ---------------------------------------------------------------------------
# The classifier
# ---------------------------------------------------------------------------

def test_every_review_status_is_classified_deliberately():
    """The inventory comes from daily_review.py itself: a new early return
    must be added to REVIEW_STATUSES on purpose (until then it is a failure)."""
    src = Path(ro.__file__).with_name("daily_review.py").read_text(encoding="utf-8")
    returned = set(re.findall(r'"status":\s*"(\w+)"', src))
    assert returned == {"completed", "data_gated", "no_envelope",
                        "no_forecast_row", "no_actual_data"}
    assert returned == set(ro.REVIEW_STATUSES)


@pytest.mark.parametrize("summary, outcome, reason", [
    ({"status": "completed"}, "completed", ""),
    ({"status": "completed", "data_gate": []}, "completed", ""),
    ({"status": "completed", "data_gate": [{"stage": "forecast_row"}]},
     "degraded", "data gate: forecast_row"),
    ({"status": "completed", "data_gate": [{"stage": "forecast_row"},
                                          {"stage": "actual_close"},
                                          {"stage": "forecast_row"}]},
     "degraded", "data gate: forecast_row, actual_close"),
    ({"status": "data_gated", "data_gate": [{"stage": "rerun"}]},
     "data_gated", "data gate: rerun"),
    ({"status": "no_envelope"}, "skipped", "no_envelope"),
    ({"status": "no_forecast_row"}, "skipped", "no_forecast_row"),
    ({"status": "no_actual_data"}, "skipped", "no_actual_data"),
    # malformed: fails closed, never output
    (None, "failed", "malformed: NoneType result"),
    ([], "failed", "malformed: list result"),
    ("completed", "failed", "malformed: str result"),
    ({}, "failed", "malformed: status None"),
    ({"status": "done"}, "failed", "malformed: status 'done'"),
    ({"status": "COMPLETED"}, "failed", "malformed: status 'COMPLETED'"),
    ({"status": "completed", "ticker": "OTHER"}, "failed", "malformed: result for 'OTHER'"),
    ({"status": "completed", "date": "2026-09-14"}, "failed",
     "malformed: result dated '2026-09-14'"),
])
def test_classify(summary, outcome, reason):
    got = ro.classify("WELCORP", REVIEW, summary)
    assert (got.ticker, got.outcome, got.reason) == ("WELCORP", outcome, reason)


def test_an_exception_is_a_failure_whatever_the_result_says():
    got = ro.classify("WELCORP", REVIEW, {"status": "completed"}, RuntimeError("x"))
    assert (got.outcome, got.reason) == ("failed", "exception: RuntimeError")


def test_a_timeout_is_a_failure():
    assert ro.timed_out("INFY") == ro.ReviewOutcome("INFY", "failed", "timeout")


@pytest.mark.parametrize("result, status", [
    ({"status": "completed", "users": 3}, "completed"),
    ({"status": "disabled"}, "disabled"),
    ({"status": "not_trading_day"}, "not_trading_day"),
    (None, "malformed"), ("completed", "malformed"), ({}, "malformed"),
    ({"status": "ok"}, "malformed"), ([{"status": "completed"}], "malformed"),
])
def test_pipeline_status(result, status):
    assert ro.pipeline_status(result) == status


# ---------------------------------------------------------------------------
# The cohort arithmetic, for any mix (seeded, deterministic)
# ---------------------------------------------------------------------------

_KINDS = ["completed", "degraded", "data_gated", "skip", "exception",
          "malformed", "timeout", "absent"]


def _outcome(kind, sym):
    if kind == "completed":
        return ro.classify(sym, REVIEW, {"status": "completed"})
    if kind == "degraded":
        return ro.classify(sym, REVIEW, {"status": "completed",
                                         "data_gate": [{"stage": "forecast_row"}]})
    if kind == "data_gated":
        return ro.classify(sym, REVIEW, {"status": "data_gated"})
    if kind == "skip":
        return ro.classify(sym, REVIEW, {"status": "no_envelope"})
    if kind == "exception":
        return ro.classify(sym, REVIEW, None, ValueError("boom"))
    if kind == "malformed":
        return ro.classify(sym, REVIEW, {"status": "weird"})
    return ro.timed_out(sym)


def test_counts_always_add_up_to_the_required_cohort():
    rng = random.Random(20260927)
    for _ in range(400):
        syms = [f"T{i}" for i in range(rng.randint(0, 25))]
        cur_kind = {s: rng.choice(_KINDS) for s in syms}
        outcomes = {s: _outcome(k, s) for s, k in cur_kind.items() if k != "absent"}
        prev_kind: dict[str, str] = {}
        previous = None
        if rng.random() < 0.5:           # an earlier run of the same session
            prev_kind = {s: rng.choice(["completed", "degraded", "skipped", "failed",
                                        "data_gated"])
                         for s in syms + ["GONE"] if rng.random() < 0.7}
            previous = {"review_date": REVIEW, "runs": 1,
                        "by_ticker": {s: {"outcome": k, "reason": "", "attempts": 1}
                                      for s, k in prev_kind.items()}}
        pipeline = rng.choice(["completed", "disabled", "failed", "malformed"])

        rec = ro.with_pipeline(ro.summarize(REVIEW, syms, outcomes, previous=previous),
                               pipeline)

        # Derived here, independently: a ticker has output if either run wrote it.
        cur_wrote = {s for s, k in cur_kind.items() if k in WROTE}
        prev_wrote = {s for s, k in prev_kind.items() if k in WROTE}
        have = {s for s in syms if s in cur_wrote or s in prev_wrote}
        standing_failed = {s for s in syms if s not in have and
                           cur_kind[s] in ("exception", "malformed", "timeout", "absent")}

        n = len(syms)
        assert rec["required"] == rec["expected"] == n
        assert sum(rec[o] for o in ro.OUTCOMES) == n
        assert rec["produced"] == len(have) <= n
        assert set(rec["missing"]) == set(syms) - have
        assert rec["failed"] == len(standing_failed)
        assert rec["cohort_complete"] is (len(have) == n)
        assert rec["attempted"] == n + sum(1 for s in syms if s in prev_kind)
        assert rec["this_run"]["attempted"] == n
        assert "GONE" not in rec["by_ticker"]                 # not in today's cohort
        want = ("empty" if n == 0 else "failed" if not have
                else "ok" if len(have) == n and pipeline in ("completed", "disabled")
                else "partial")
        assert rec["status"] == want
        assert rec["pipeline_ok"] is (pipeline == "completed" and not standing_failed)


def test_a_missing_outcome_counts_as_failed_not_as_nothing():
    """A harvesting bug cannot shrink the cohort."""
    rec = ro.summarize(REVIEW, ["A", "B"], {"A": _outcome("completed", "A")})
    assert (rec["required"], rec["produced"], rec["failed"]) == (2, 1, 1)
    assert rec["missing"] == {"B": "failed: not harvested"}


def test_missing_detail_groups_by_reason():
    rec = ro.summarize(REVIEW, ["A", "B", "C", "D"], {
        "A": _outcome("completed", "A"),
        "B": _outcome("skip", "B"),
        "C": _outcome("skip", "C"),
        "D": ro.timed_out("D"),
    })
    assert ro.missing_detail(rec) == "failed timeout: D; skipped no_envelope: B, C"


# ---------------------------------------------------------------------------
# The scheduled job, end to end over faked reviews
# ---------------------------------------------------------------------------

@pytest.fixture
def job(monkeypatch):
    """Runs AutomobileScheduler._daily_review_job with each ticker's review
    result scripted; the real alert helpers, job-outcome store (redirected by
    tests/conftest.py) and outcome module run."""
    import core.delivery.alerts as al
    import core.intelligence.rl.nse_calendar as cal
    import core.intelligence.rl.workflows.daily_review as dr
    import core.portfolio.pipeline as pl
    import services.data.stores.job_outcomes as jo
    import services.scheduler.python.scheduler as sch

    monkeypatch.setattr(cal, "now_ist", lambda: TODAY)
    alerts: list[tuple[str, str, str]] = []
    monkeypatch.setattr(al, "emit_alerts_broadcast", lambda events, **kw: alerts.extend(
        (e.kind, e.severity, e.message) for e in events) or {"emitted": len(events)})
    state: dict = {"pipeline": lambda d: {"status": "completed"}, "reviews": {}}
    monkeypatch.setattr(pl, "run_post_review_pipeline", lambda d: state["pipeline"](d))
    calls: list[str] = []

    def _review(t, d, sector=None):
        calls.append(t)
        r = state["reviews"][t]
        if isinstance(r, BaseException):
            raise r
        return r(t, d) if callable(r) else r
    monkeypatch.setattr(dr, "run_daily_review", _review)

    def run(reviews: dict, *, entries: list[str] | None = None, disabled=(),
            pipeline=None) -> dict:
        state["reviews"] = reviews
        if pipeline is not None:
            state["pipeline"] = pipeline
        syms = list(reviews) if entries is None else entries
        monkeypatch.setattr(sch, "get_active_tickers_with_sector",
                            lambda: [{"sym": s, "sector": "automobile"} for s in syms])
        monkeypatch.setattr(sch, "get_disabled_tickers", lambda: list(disabled))
        sch.AutomobileScheduler()._daily_review_job()
        return jo.load_job_outcomes()["daily_review"]

    run.alerts = alerts
    run.calls = calls
    return run


def _twenty(**overrides):
    syms = ["WELCORP"] + [f"S{i:02d}" for i in range(19)]
    reviews = {s: done for s in syms}
    reviews.update(overrides)
    return reviews


def test_twenty_attempts_with_one_no_envelope(job):
    """Acceptance 1 — the 2026-09-08 shape: before SA-004 this read 20/20."""
    rec = job(_twenty(WELCORP=early("no_envelope")))

    assert rec["review_date"] == REVIEW
    assert (rec["required"], rec["attempted"]) == (20, 20)
    assert (rec["completed"], rec["skipped"], rec["degraded"],
            rec["data_gated"], rec["failed"]) == (19, 1, 0, 0, 0)
    assert (rec["produced"], rec["expected"]) == (19, 20)
    assert rec["cohort_complete"] is False
    assert rec["status"] == "partial"
    assert rec["missing"] == {"WELCORP": "skipped: no_envelope"}
    assert rec["by_ticker"]["WELCORP"]["outcome"] == "skipped"
    assert job.alerts == [(
        "job_partial_output_daily_review", "warning",
        "Job 'daily_review' completed 19/20 — missing: skipped no_envelope: WELCORP. "
        "Check logs.")]


def test_mixed_statuses_are_each_counted_once(job):
    rec = job({
        "A": done, "B": done,
        "C": done_on_gated_input,
        "D": gated,
        "E": early("no_forecast_row"), "F": early("no_actual_data"),
        "G": RuntimeError("provider down"),
        "H": lambda t, d: None,
    })
    assert (rec["completed"], rec["degraded"], rec["data_gated"],
            rec["skipped"], rec["failed"]) == (2, 1, 1, 2, 2)
    assert (rec["produced"], rec["required"]) == (3, 8)
    assert rec["by_ticker"]["C"]["reason"] == "data gate: forecast_row"
    assert rec["missing"] == {
        "D": "data_gated: data gate: actual_close",
        "E": "skipped: no_forecast_row", "F": "skipped: no_actual_data",
        "G": "failed: exception: RuntimeError", "H": "failed: malformed: NoneType result",
    }
    assert rec["status"] == "partial"
    assert rec["pipeline_ok"] is False          # G raised, H was malformed
    assert rec["pipeline_status"] == "completed"
    assert [a[0] for a in job.alerts] == ["job_partial_output_daily_review"]


def test_all_skipped_pages_zero_output(job):
    rec = job({s: early("no_envelope") for s in ("A", "B", "C")})
    assert (rec["produced"], rec["skipped"], rec["status"]) == (0, 3, "failed")
    assert job.alerts == [(
        "job_zero_output_daily_review", "critical",
        "Job 'daily_review' completed with 0/3 output — missing: skipped no_envelope: "
        "A, B, C. Check logs.")]


def test_all_data_gated_is_not_output(job):
    """SA-003's routed note: a gate stop is neither a completed review nor a
    failure, and it must not satisfy the zero-output alert."""
    rec = job({s: gated for s in ("A", "B")})
    assert (rec["produced"], rec["data_gated"], rec["failed"]) == (0, 2, 0)
    assert rec["status"] == "failed"
    assert [a[0] for a in job.alerts] == ["job_zero_output_daily_review"]
    assert "data_gated data gate: actual_close: A, B" in job.alerts[0][2]


def test_all_failed(job):
    rec = job({s: RuntimeError("key revoked") for s in ("A", "B")})
    assert (rec["produced"], rec["failed"], rec["status"]) == (0, 2, "failed")
    assert rec["pipeline_ok"] is False
    assert [a[0] for a in job.alerts] == ["job_zero_output_daily_review"]
    assert "exception: RuntimeError: A, B" in job.alerts[0][2]


@pytest.mark.parametrize("bad", [
    None, [], "completed", {}, {"status": None}, {"status": "done"},
    {"status": "completed", "ticker": "OTHER"}, {"status": "completed", "date": "2026-09-14"},
])
def test_a_malformed_review_result_never_reads_ok(job, bad):
    """Acceptance 2, review side."""
    rec = job({"A": done, "B": lambda t, d: bad})
    assert rec["by_ticker"]["B"]["outcome"] == "failed"
    assert (rec["produced"], rec["status"], rec["pipeline_ok"]) == (1, "partial", False)
    assert [a[0] for a in job.alerts] == ["job_partial_output_daily_review"]


def _boom(d):
    raise RuntimeError("advisor exploded")


@pytest.mark.parametrize("pipeline, status", [
    (lambda d: None, "malformed"),
    (lambda d: "completed", "malformed"),
    (lambda d: {"status": "weird"}, "malformed"),
    (_boom, "failed"),
])
def test_a_malformed_or_raising_pipeline_is_not_ok(job, pipeline, status):
    """Acceptance 2, pipeline side: returning is not success."""
    rec = job({"A": done}, pipeline=pipeline)
    assert rec["pipeline_status"] == status
    assert rec["pipeline_ok"] is False
    assert rec["status"] == "partial"
    assert rec["pipeline_error"]


def test_a_clean_day_reads_ok(job):
    rec = job({"A": done, "B": done_on_gated_input})
    assert (rec["status"], rec["pipeline_ok"], rec["cohort_complete"]) == ("ok", True, True)
    assert job.alerts == []


def test_a_disabled_pipeline_is_ok_but_not_pipeline_ok(job):
    rec = job({"A": done}, pipeline=lambda d: {"status": "disabled"})
    assert (rec["status"], rec["pipeline_status"], rec["pipeline_ok"]) == (
        "ok", "disabled", False)


def test_empty_universe(job):
    rec = job({}, entries=[], disabled=["OFF1", "OFF2"])
    assert (rec["required"], rec["attempted"], rec["produced"]) == (0, 0, 0)
    assert rec["status"] == "empty"
    assert rec["excluded"] == ["OFF1", "OFF2"]
    assert job.calls == [] and job.alerts == []


def test_excluded_symbols_are_reported_not_required(job):
    rec = job({"A": done}, disabled=["WELCORP"])
    assert rec["excluded"] == ["WELCORP"]
    assert (rec["required"], rec["produced"], rec["status"]) == (1, 1, "ok")
    assert "WELCORP" not in rec["by_ticker"] and "WELCORP" not in job.calls


def test_duplicate_entries_are_reviewed_and_counted_once(job):
    rec = job({"A": done, "B": done}, entries=["A", "A", "B", "a "])
    assert sorted(job.calls) == ["A", "B"]
    assert rec["duplicates"] == ["A", "a "]
    assert (rec["required"], rec["attempted"], rec["produced"]) == (2, 2, 2)


def test_a_partial_rerun_of_the_same_session_merges(job):
    """Acceptance 3. The day after a weekday holiday reviews the same session
    again (Fri 2 Oct and Mon 5 Oct both review Thu 1 Oct)."""
    first = job({"A": done, "B": early("no_envelope"), "C": RuntimeError("down")})
    assert (first["produced"], first["runs"], first["status"]) == (1, 1, "partial")
    job.alerts.clear()

    second = job({"A": RuntimeError("down again"), "B": done, "C": done})

    assert second["runs"] == 2
    assert (second["required"], second["attempted"]) == (3, 6)
    assert (second["completed"], second["produced"], second["failed"]) == (3, 3, 0)
    assert second["retried"] == ["A", "B", "C"]
    assert second["by_ticker"]["A"] == {"outcome": "completed", "reason": "",
                                        "from_earlier_run": True, "attempts": 2,
                                        "this_run": "failed"}
    assert second["this_run"]["failed"] == 1 and second["this_run"]["completed"] == 2
    assert (second["cohort_complete"], second["status"]) == (True, "ok")
    assert job.alerts == []                      # every required outcome exists


def test_a_full_rerun_does_not_double_count_completion(job):
    job({"A": done, "B": done})
    rec = job({"A": done, "B": done})
    assert (rec["produced"], rec["completed"], rec["required"]) == (2, 2, 2)
    assert (rec["attempted"], rec["runs"]) == (4, 2)


def test_a_different_session_does_not_merge(job, monkeypatch):
    import core.intelligence.rl.nse_calendar as cal
    job({"A": done, "B": early("no_envelope")})
    monkeypatch.setattr(cal, "now_ist", lambda: datetime(2026, 9, 17, 16, 30))
    rec = job({"A": early("no_envelope"), "B": done})
    assert rec["review_date"] == "2026-09-16"
    assert (rec["runs"], rec["attempted"], rec["retried"]) == (1, 2, [])
    assert (rec["produced"], rec["missing"]) == (1, {"A": "skipped: no_envelope"})


def test_a_legacy_record_of_the_same_session_does_not_merge(job):
    import services.data.stores.job_outcomes as jo
    jo.record_job_outcome("daily_review", review_date=REVIEW, produced=20, expected=20,
                          pipeline_ok=True)
    rec = job({"A": early("no_envelope")})
    assert (rec["runs"], rec["attempted"], rec["produced"]) == (1, 1, 0)


def test_a_timed_out_review_is_failed_and_a_finished_one_still_counts(job, monkeypatch):
    """The budget expires with B still running; C finished but was never
    yielded before the TimeoutError. B is a timeout; C is counted (it wrote
    its feedback). Before SA-004, C was neither output nor a straggler."""
    import concurrent.futures as cf
    import services.scheduler.python.scheduler as sch
    release = threading.Event()

    def slow(t, d):
        release.wait(10)                        # still running at the budget
        return done(t, d)

    def fake_as_completed(fs, timeout=None):
        fs = list(fs)                           # submission order: A, B, C
        cf.wait([fs[0], fs[2]])                 # A and C finish...
        yield fs[0]                             # ...only A is yielded...
        raise cf.TimeoutError()                 # ...then the budget expires

    monkeypatch.setattr(sch.settings, "RL_SCHEDULER_MAX_WORKERS", 3, raising=False)
    monkeypatch.setattr(sch._cf, "as_completed", fake_as_completed)
    try:
        rec = job({"A": done, "B": slow, "C": done})
    finally:
        release.set()

    assert rec["stragglers"] == ["B"]
    assert rec["by_ticker"]["B"] == {"outcome": "failed", "reason": "timeout",
                                     "attempts": 1, "this_run": "failed"}
    assert rec["by_ticker"]["C"]["outcome"] == "completed"
    assert (rec["produced"], rec["failed"], rec["pipeline_ok"]) == (2, 1, False)
    assert job.alerts[0][2].endswith("missing: failed timeout: B. Check logs.")


def test_legacy_fields_are_kept(job):
    rec = job({"A": done})
    for key in ("review_date", "produced", "expected", "stragglers", "pipeline_ok",
                "pipeline_error", "news_fetched", "news_blind", "news_macro_rescued",
                "finished_at"):
        assert key in rec

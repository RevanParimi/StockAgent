"""SA-003 — learning acts only on essential data.

Independent invariants:

- A gated review (enforce mode) writes NOTHING that learns: the weight file,
  weight observations, ticker/sector/market ledgers, the envelope, the
  feedback log, the dossier and the control lane are byte-identical (or still
  absent) afterwards, and the FeedbackAgent is never called. Checked in both
  SA-039 learning modes, so the gate holds whether the adapter would write
  (adapt) or only propose (observe).
- Exact price-freshness boundary: a close from the bar dated the review
  session grades; the same number from the previous day's bar does not (it
  would read as a flat day — a valid-looking zero return that never happened).
- The skip is recorded with its stage, reason and source run id.
- Record mode changes nothing: the review completes and learns as before,
  and lists what enforce would have stopped.
- The forecast and the re-forecast refuse an abstained analysis in enforce
  mode (no envelope written / the old one intact); every row they do write
  names its issuing run and that run's gate.
"""
from __future__ import annotations

import hashlib
import json
from datetime import date, timedelta
from pathlib import Path

import pytest

from core.intelligence.rl.stores.prediction_store import PredictionStore
from core.schemas.feedback import DailyFeedbackLog, FeedbackEntry, RawLesson, WeightMemory
from core.schemas.pipeline import DecisionGate, FinalReport, WeightedAgentScore
from tests.unit.intelligence.rl.test_learning_mode_sa039 import (
    AUTOMOBILE_DEFAULTS,
    AUTOMOBILE_LEARNED,
    no_network,  # noqa: F401 — fixture
)
from tests.unit.intelligence.rl.test_shock_path import (
    REVIEW_DATE, SECTOR, TICKER, _patch_common, _setup_store,
)


@pytest.fixture
def gate_mode(monkeypatch):
    from backend.shared.pipeline import decision_gate as dg
    from core.config import settings
    dg._warned.clear()

    def _set(value):
        monkeypatch.setattr(settings, "DECISION_GATE_MODE", value)
    return _set


@pytest.fixture
def learning(monkeypatch):
    from core.config import settings
    from core.intelligence.rl import learning_mode as lm
    lm._warned.clear()

    def _set(value):
        monkeypatch.setattr(settings, "RL_LEARNING_MODE", value)
    return _set


def _gate_rows(tmp_path) -> list[dict]:
    path = tmp_path / "decision_gate.jsonl"      # tests/conftest.py redirects here
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def _report(status: str | None, run_id: str = "rerun-1", verdict: str = "BUY") -> FinalReport:
    gate = None if status is None else DecisionGate(
        status=status, run_id=run_id,
        reasons=["essential technicals=empty"] if status == "abstain" else [])
    return FinalReport(
        ticker=TICKER, company_name=TICKER, final_score=0.7, verdict=verdict,
        weighted_agent_scores={a: WeightedAgentScore(raw=0.5, weight=0.5, weighted=0.25)
                               for a in ("risk_macro", "sales_demand")},
        decision_gate=gate,
    )


# ---------------------------------------------------------------------------
# The daily review
# ---------------------------------------------------------------------------

_LESSON = RawLesson(category="macro", pattern="sa003-pattern", observation="obs",
                    rule="sa003 rule", confidence=0.8, trigger_tags=["monsoon"],
                    prioritise_agents=["risk_macro"])


def _review(tmp_path, monkeypatch, *, row_gate="actionable", row_run="month-run",
            bar_date=None, rerun_report=None):
    """One real run_daily_review over an automobile store with learned weights
    at v41, two prior feedback rows (enough for the adapter to act), a BUY
    row for the review date predicting 100.0, and an actual close of 98.0 —
    direction wrong, so the review re-runs the analysis (unless gated first).

    `bar_date` is the bar the actual close comes from (default: the session).
    `rerun_report` is what the re-run's orchestrator returns.
    """
    import core.intelligence.rl.workflows.daily_review as dr
    from core.intelligence.rl.agents.feedback_agent import FeedbackAgent
    from core.intelligence.rl.agents.thesis_reviewer import ThesisReviewer
    from core.schemas.feedback import FeedbackAgentOutput, RegimeSnapshot, RevisedContext

    store, cycle_id = _setup_store(tmp_path)
    env = store.load_envelope(cycle_id)
    for row in env.daily_forecasts:
        row.data_gate, row.source_run_id = row_gate, row_run
    store.save_envelope(env)
    store.save_weight_memory(WeightMemory(
        ticker=TICKER, sector=SECTOR, last_updated="2026-09-23", weight_version=41,
        current_weights=dict(AUTOMOBILE_LEARNED), base_weights=dict(AUTOMOBILE_DEFAULTS)))
    prior = [
        FeedbackEntry(day=0, date=(REVIEW_DATE - timedelta(days=d)).isoformat(),
                      predicted_close=100.0, actual_close=97.0, price_error_pct=-3.0,
                      predicted_verdict="BUY", actual_direction="DOWN",
                      direction_correct=False,
                      predicted_agent_scores={"risk_macro": 0.8, "sales_demand": 0.8})
        for d in (2, 1)
    ]
    store.save_feedback_log(DailyFeedbackLog(ticker=TICKER, cycle_id=cycle_id, entries=prior))

    _patch_common(dr, monkeypatch, tmp_path, actual_close=98.0)
    session_bar = (None if bar_date is _UNDATED
                   else bar_date if bar_date is not None else REVIEW_DATE)
    monkeypatch.setattr(dr, "_fetch_session_close",
                        lambda t, d: dr.SessionClose(98.0, session_bar, "agree"))
    import core.intelligence.rl.stores.offmarket_fetcher as offmarket_mod
    monkeypatch.setattr(offmarket_mod.OffMarketFetcher, "__init__",
                        lambda self: setattr(self, "_nse", None))
    monkeypatch.setattr(dr.settings, "RL_REFORECAST_ENABLED", False)
    monkeypatch.setattr(dr.settings, "REGIME_MULTIPLIERS", {})
    monkeypatch.setattr(dr.RegimeDetector, "detect",
                        lambda self, d, s: RegimeSnapshot(multipliers={}))
    monkeypatch.setattr(ThesisReviewer, "should_review", lambda self, *a, **k: False)
    feedback_calls: list = []
    monkeypatch.setattr(FeedbackAgent, "run", lambda self, fb_input, ledger: (
        feedback_calls.append(fb_input) or FeedbackAgentOutput(
            primary_miss_agent="risk_macro", miss_type="model_bias", new_lessons=[_LESSON],
            revised_context=RevisedContext(headline="Test.",
                                           horizon_confidence_adjustment=0.0))))
    report = rerun_report if rerun_report is not None else _report("actionable")

    def _rerun(t, sector, learned_weights=None, capture=None):
        if capture is not None:
            capture["report"] = report
        return {"risk_macro": 0.5, "sales_demand": 0.5}
    monkeypatch.setattr(dr, "_run_todays_agent_scores", _rerun)

    summary = dr.run_daily_review(TICKER, REVIEW_DATE, sector=SECTOR)
    return store, summary, feedback_calls


# Files a gated review may still write, and why:
#   decision_gate.jsonl  the skip record itself (asserted separately)
#   _regime_state.json   market-wide regime hysteresis (VIX, FII proxy, sector
#                        RSI), updated at Step 0 on every review path — before
#                        the envelope is even loaded, as on `no_envelope` — and
#                        not derived from this ticker's data
_NOT_LEARNING = {"decision_gate.jsonl", "_regime_state.json"}


def _learning_state(tmp_path) -> dict[str, str]:
    """SHA-256 of every file under the test root, so a gated review can be
    shown to have written nothing that learns (a new file shows up as a key)."""
    out: dict[str, str] = {}
    for p in sorted(Path(tmp_path).rglob("*")):
        if p.is_file() and p.name not in _NOT_LEARNING:
            out[str(p.relative_to(tmp_path))] = hashlib.sha256(p.read_bytes()).hexdigest()
    return out


_UNDATED = object()       # the close's bar has no date (SessionClose.bar_date None)

GATED_CASES = {
    "forecast_row_abstained": dict(row_gate="abstain", row_run="month-run"),
    "forecast_row_issued_before_the_gate": dict(row_gate="", row_run=""),
    "close_carried_forward_one_day": dict(bar_date=REVIEW_DATE - timedelta(days=1)),
    "close_undated": dict(bar_date=_UNDATED),
    "rerun_abstained": dict(rerun_report=_report("abstain", run_id="rerun-9")),
    "rerun_without_a_gate": dict(rerun_report=_report(None)),
}
EXPECTED_STAGE = {
    "forecast_row_abstained": ("forecast_row", "month-run"),
    "forecast_row_issued_before_the_gate": ("forecast_row", ""),
    "close_carried_forward_one_day": ("actual_close", "month-run"),
    "close_undated": ("actual_close", "month-run"),
    "rerun_abstained": ("rerun", "rerun-9"),
    "rerun_without_a_gate": ("rerun", ""),
}


@pytest.mark.parametrize("learning_value", ["adapt", "observe"])
@pytest.mark.parametrize("case", list(GATED_CASES))
def test_a_gated_review_has_no_learning_side_effect(
        tmp_path, monkeypatch, gate_mode, learning, no_network, case, learning_value):
    gate_mode("enforce")
    learning(learning_value)
    # Build the store exactly as _review will, snapshot it, then run.
    import core.intelligence.rl.workflows.daily_review as dr

    snapshots = {}
    original = dr.run_daily_review

    def _snapshot_then_run(*a, **k):
        snapshots["before"] = _learning_state(tmp_path)
        return original(*a, **k)
    monkeypatch.setattr(dr, "run_daily_review", _snapshot_then_run)

    store, summary, feedback_calls = _review(tmp_path, monkeypatch, **GATED_CASES[case])

    assert summary["status"] == "data_gated"
    stage, run_id = EXPECTED_STAGE[case]
    [row] = summary["data_gate"]
    assert row["stage"] == stage and row["source_run_id"] == run_id
    assert row["enforced"] is True and row["reasons"]
    # Nothing learned: every file under the store is byte-identical, and no
    # file (observation record, ledger, dossier, control log) appeared.
    assert _learning_state(tmp_path) == snapshots["before"]
    assert store.load_weight_memory().weight_version == 41
    assert store.load_weight_observations() == []
    assert feedback_calls == []                      # no FeedbackAgent, so no lessons
    # The skip is recorded once, for this ticker and date.
    rows = _gate_rows(tmp_path)
    assert [(r["consumer"], r["ticker"], r["date"], r["stage"]) for r in rows] == \
        [("daily_review", TICKER, REVIEW_DATE.isoformat(), stage)]
    assert no_network == []


def test_the_freshness_boundary_is_the_session_itself(tmp_path, monkeypatch, gate_mode,
                                                      learning, no_network):
    """Same number, same review: dated the session it grades; dated the day
    before it does not."""
    gate_mode("enforce")
    learning("adapt")
    _, same_day, _ = _review(tmp_path / "a", monkeypatch, bar_date=REVIEW_DATE)
    _, day_before, _ = _review(tmp_path / "b", monkeypatch,
                               bar_date=REVIEW_DATE - timedelta(days=1))
    assert same_day["status"] == "completed"
    assert day_before["status"] == "data_gated"
    assert day_before["data_gate"][0]["stage"] == "actual_close"
    assert (REVIEW_DATE - timedelta(days=1)).isoformat() in day_before["data_gate"][0]["reasons"][0]


def test_an_actionable_review_still_learns_in_enforce(tmp_path, monkeypatch, gate_mode,
                                                     learning, no_network):
    """The control: with verified inputs the gate stops nothing."""
    gate_mode("enforce")
    learning("adapt")
    store, summary, feedback_calls = _review(tmp_path, monkeypatch)
    assert summary["status"] == "completed"
    assert summary["data_gate"] == []
    assert store.load_weight_memory().weight_version == 42     # adapt wrote
    assert len(feedback_calls) == 1
    assert _gate_rows(tmp_path) == []
    assert no_network == []


def test_degraded_inputs_are_actionable(tmp_path, monkeypatch, gate_mode, learning):
    gate_mode("enforce")
    learning("adapt")
    _, summary, _ = _review(tmp_path, monkeypatch, row_gate="degraded",
                            rerun_report=_report("degraded"))
    assert summary["status"] == "completed" and summary["data_gate"] == []


def test_record_mode_learns_as_before_and_lists_what_enforce_would_stop(
        tmp_path, monkeypatch, gate_mode, learning, no_network):
    gate_mode("record")
    learning("adapt")
    store, summary, feedback_calls = _review(
        tmp_path, monkeypatch, row_gate="abstain",
        bar_date=REVIEW_DATE - timedelta(days=1),
        rerun_report=_report("abstain", run_id="rerun-9"))
    assert summary["status"] == "completed"
    assert store.load_weight_memory().weight_version == 42      # unchanged behaviour
    assert len(feedback_calls) == 1
    assert [r["stage"] for r in summary["data_gate"]] == ["forecast_row", "actual_close", "rerun"]
    assert all(r["enforced"] is False for r in summary["data_gate"])
    assert [r["stage"] for r in _gate_rows(tmp_path)] == ["forecast_row", "actual_close", "rerun"]
    assert no_network == []


# ---------------------------------------------------------------------------
# Forecast and re-forecast
# ---------------------------------------------------------------------------

def _patch_forecast(gf, monkeypatch, tmp_path, report):
    monkeypatch.setattr(gf.settings, "PREDICTION_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(gf, "_run_orchestrator_analysis", lambda t, s, w: report)
    monkeypatch.setattr(gf, "_fetch_actual_close", lambda ticker: 100.0)
    monkeypatch.setattr(gf, "_compute_forecast_profile", lambda *a, **k: (None, "NORMAL"))
    monkeypatch.setattr(gf, "_fetch_fno_snapshot", lambda *a, **k: None)

    class _NoEnhancer:
        def enhance(self, *a, **k):
            return {}
    monkeypatch.setattr(gf, "PromptEnhancer", _NoEnhancer)


def test_enforce_builds_no_envelope_on_an_abstained_analysis(tmp_path, monkeypatch, gate_mode,
                                                             no_network):
    from core.intelligence.rl.workflows import generate_forecast as gf
    gate_mode("enforce")
    _patch_forecast(gf, monkeypatch, tmp_path, _report("abstain", run_id="month-run"))

    with pytest.raises(gf.InsufficientDataError, match="month-run"):
        gf.generate_forecast(TICKER, sector=SECTOR)

    store = PredictionStore(TICKER, sector=SECTOR, base_dir=str(tmp_path))
    assert store.load_envelope(store.current_cycle_id()) is None
    [row] = _gate_rows(tmp_path)
    assert (row["consumer"], row["source_run_id"], row["enforced"]) == ("forecast", "month-run", True)
    assert no_network == []


@pytest.mark.parametrize("mode, status", [("record", "abstain"), ("enforce", "actionable"),
                                          ("enforce", "degraded")])
def test_every_forecast_row_names_its_run_and_gate(tmp_path, monkeypatch, gate_mode,
                                                   mode, status):
    from core.intelligence.rl.workflows import generate_forecast as gf
    gate_mode(mode)
    _patch_forecast(gf, monkeypatch, tmp_path, _report(status, run_id="month-run"))

    env = gf.generate_forecast(TICKER, sector=SECTOR)

    assert env.daily_forecasts
    assert {(f.data_gate, f.source_run_id) for f in env.daily_forecasts} == {(status, "month-run")}
    assert env.decision_gate["status"] == status and env.decision_gate["run_id"] == "month-run"


def _seed_envelope(tmp_path, today):
    from core.schemas.feedback import DailyForecast, PredictionEnvelope
    store = PredictionStore(TICKER, sector=SECTOR, base_dir=str(tmp_path))
    store.save_envelope(PredictionEnvelope(
        ticker=TICKER, sector=SECTOR, cycle_id=store.cycle_id_for(today),
        generated_at=today.isoformat(), base_close=100.0,
        daily_forecasts=[
            DailyForecast(day=1, date=today.isoformat(), predicted_close=100.0,
                          predicted_verdict="BUY", confidence=0.5,
                          data_gate="actionable", source_run_id="month-run"),
            DailyForecast(day=2, date=(today + timedelta(days=1)).isoformat(),
                          predicted_close=101.0, predicted_verdict="BUY", confidence=0.5,
                          data_gate="actionable", source_run_id="month-run"),
        ],
    ))
    return store


def test_enforce_reforecast_leaves_the_envelope_intact(tmp_path, monkeypatch, gate_mode,
                                                       no_network):
    from core.intelligence.rl.workflows import generate_forecast as gf
    today = date.today()
    store = _seed_envelope(tmp_path, today)
    path = store._envelope_path(store.cycle_id_for(today))
    before = path.read_bytes()
    _patch_forecast(gf, monkeypatch, tmp_path, _report("abstain", run_id="shock-run"))
    monkeypatch.setattr(gf.settings, "RL_REFORECAST_ENABLED", True)
    gate_mode("enforce")

    env = gf.regenerate_envelope(ticker=TICKER, sector=SECTOR, review_date=today,
                                 reason="test", trigger="external_shock")

    assert env is None
    assert path.read_bytes() == before
    [row] = _gate_rows(tmp_path)
    assert (row["consumer"], row["source_run_id"]) == ("reforecast", "shock-run")


def test_a_reforecast_row_names_the_run_that_issued_it(tmp_path, monkeypatch, gate_mode):
    from core.intelligence.rl.workflows import generate_forecast as gf
    today = date.today()
    _seed_envelope(tmp_path, today)
    _patch_forecast(gf, monkeypatch, tmp_path, _report("actionable", run_id="shock-run"))
    monkeypatch.setattr(gf.settings, "RL_REFORECAST_ENABLED", True)
    gate_mode("enforce")

    env = gf.regenerate_envelope(ticker=TICKER, sector=SECTOR, review_date=today,
                                 reason="test", trigger="external_shock")

    kept, new = env.daily_forecasts[0], env.daily_forecasts[1:]
    assert (kept.data_gate, kept.source_run_id) == ("actionable", "month-run")
    assert new and {f.source_run_id for f in new} == {"shock-run"}
    assert env.decision_gate["run_id"] == "shock-run"

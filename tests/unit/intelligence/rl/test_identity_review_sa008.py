"""SA-008 — an unresolved symbol cannot contaminate learning, and a forecast
keeps the identity and price basis it was issued on.

Through the REAL run_daily_review (SA-003's harness: learned weights at v41,
two prior feedback rows, a BUY row graded against a wrong-direction close):

- enforce: an unresolved identity on the review day, a row stamped with
  another price basis, or an unstamped row with a demerger between its
  envelope's issue and the review each stop the review at stage `identity`,
  before any learning write: every file under the store is byte-identical,
  the weights stay v41, no observation, no FeedbackAgent call. Checked in
  both SA-039 learning modes.
- The controls complete and learn: a rename between issue and review keeps
  the basis (same company, new code), and a row stamped with the session's
  basis grades.
- record: the review completes and learns as before, and lists the
  identity stage it would have stopped at.

Registry dates are anchored to the harness's review date (today): the
event is three days before it, the envelope ten.
"""
from __future__ import annotations

from datetime import timedelta

import pytest

import tests.unit.intelligence.rl.test_decision_gate_learning_sa003 as sa003
from tests.unit.intelligence.rl.test_decision_gate_learning_sa003 import (  # noqa: F401
    _gate_rows,
    _learning_state,
    _review,
    gate_mode,
    learning,
    no_network,
)
from tests.unit.intelligence.rl.test_shock_path import REVIEW_DATE, TICKER

EVENT = REVIEW_DATE - timedelta(days=3)
ISSUED = REVIEW_DATE - timedelta(days=10)
EVIDENCE = "[{source: test fixture, ref: fixture-1, date: %s}]" % (EVENT - timedelta(days=7))

REGISTRIES = {
    "empty": "version: 1\ninstruments: {}\n",
    "unresolved": f"""version: 1
instruments:
  {TICKER}:
    segments:
      - {{status: unresolved, symbol: {TICKER}.NS, reason: "identity under review"}}
""",
    "demerger": f"""version: 1
instruments:
  {TICKER}:
    segments:
      - {{until: {EVENT}, status: active, symbol: {TICKER}.NS, basis: {TICKER}}}
      - {{from: {EVENT}, status: active, symbol: {TICKER}A.NS, basis: {TICKER}A,
         via: demerger, evidence: {EVIDENCE}}}
""",
    "rename": f"""version: 1
instruments:
  {TICKER}:
    segments:
      - {{until: {EVENT}, status: active, symbol: {TICKER}.NS, basis: {TICKER}}}
      - {{from: {EVENT}, status: active, symbol: {TICKER}N.NS, basis: {TICKER},
         via: rename, evidence: {EVIDENCE}}}
""",
}

CASES = {
    #  name:                       (registry,     row stamp basis or None)
    "identity_unresolved":          ("unresolved", None),
    "row_on_another_basis":         ("empty",      "OLDBASIS"),
    "demerger_since_issue":         ("demerger",   None),
    "rename_since_issue":           ("rename",     None),
    "row_on_the_sessions_basis":    ("empty",      TICKER),
}
GATED = ("identity_unresolved", "row_on_another_basis", "demerger_since_issue")


@pytest.fixture
def identity_case(tmp_path, monkeypatch):
    """Point the registry at the case's records and stamp/back-date the
    harness envelope before the review runs."""
    def _set(case):
        registry, basis = CASES[case]
        path = tmp_path / f"instruments_{case}.yaml"
        path.write_text(REGISTRIES[registry], encoding="utf-8")
        monkeypatch.setenv("INSTRUMENT_REGISTRY_PATH", str(path))
        original = sa003._setup_store

        def _setup(root, *a, **k):
            store, cycle_id = original(root, *a, **k)
            env = store.load_envelope(cycle_id)
            env.generated_at = f"{ISSUED.isoformat()}T09:00:00"
            for row in env.daily_forecasts:
                row.instrument = ({"ticker": TICKER, "symbol": f"{TICKER}.NS",
                                   "basis": basis, "status": "resolved"} if basis else {})
            store.save_envelope(env)
            return store, cycle_id
        monkeypatch.setattr(sa003, "_setup_store", _setup)
    return _set


@pytest.mark.parametrize("learning_value", ["adapt", "observe"])
@pytest.mark.parametrize("case", GATED)
def test_an_identity_gated_review_learns_nothing(
        tmp_path, monkeypatch, gate_mode, learning, no_network, identity_case, case,
        learning_value):
    import core.intelligence.rl.workflows.daily_review as dr
    gate_mode("enforce")
    learning(learning_value)
    identity_case(case)
    snapshots = {}
    original = dr.run_daily_review

    def _snapshot_then_run(*a, **k):
        snapshots["before"] = _learning_state(tmp_path)
        return original(*a, **k)
    monkeypatch.setattr(dr, "run_daily_review", _snapshot_then_run)

    store, summary, feedback_calls = _review(tmp_path, monkeypatch)

    assert summary["status"] == "data_gated"
    [row] = summary["data_gate"]
    assert (row["stage"], row["status"], row["enforced"]) == ("identity", "identity", True)
    assert row["source_run_id"] == "month-run" and row["reasons"]
    assert _learning_state(tmp_path) == snapshots["before"]
    assert store.load_weight_memory().weight_version == 41
    assert store.load_weight_observations() == []
    assert feedback_calls == []
    assert [(r["consumer"], r["stage"]) for r in _gate_rows(tmp_path)] == \
        [("daily_review", "identity")]
    assert no_network == []


@pytest.mark.parametrize("case, fragment", [
    ("identity_unresolved", "identity unresolved on"),
    ("row_on_another_basis", "row issued on price basis OLDBASIS"),
    ("demerger_since_issue", f"row issued {ISSUED.isoformat()} carries no instrument: "
                             f"price basis changed"),
])
def test_the_identity_stage_names_what_broke(tmp_path, monkeypatch, gate_mode, learning,
                                            no_network, identity_case, case, fragment):
    gate_mode("enforce")
    learning("adapt")
    identity_case(case)
    _, summary, _ = _review(tmp_path, monkeypatch)
    assert summary["data_gate"][0]["reasons"][0].startswith(fragment), summary["data_gate"]


@pytest.mark.parametrize("case", ["rename_since_issue", "row_on_the_sessions_basis"])
def test_the_controls_grade_and_learn(tmp_path, monkeypatch, gate_mode, learning, no_network,
                                      identity_case, case):
    gate_mode("enforce")
    learning("adapt")
    identity_case(case)
    store, summary, feedback_calls = _review(tmp_path, monkeypatch)
    assert summary["status"] == "completed", summary.get("data_gate")
    assert summary["data_gate"] == []
    assert store.load_weight_memory().weight_version == 42
    assert len(feedback_calls) == 1
    assert no_network == []


def test_record_mode_learns_as_before_and_lists_the_identity_stage(
        tmp_path, monkeypatch, gate_mode, learning, no_network, identity_case):
    gate_mode("record")
    learning("adapt")
    identity_case("identity_unresolved")
    store, summary, feedback_calls = _review(tmp_path, monkeypatch)
    assert summary["status"] == "completed"
    assert store.load_weight_memory().weight_version == 42
    assert len(feedback_calls) == 1
    assert [(r["stage"], r["enforced"]) for r in summary["data_gate"]] == [("identity", False)]
    assert no_network == []

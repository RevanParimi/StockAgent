"""Switch lane — grade the pair, idempotently, never fatally."""
from datetime import date

from backend.shared.schemas.portfolio import SwitchEvaluation
from core.audit.outcomes import grade_switch_lane
from core.audit.store import AuditOutcomeStore
from core.portfolio.store import PortfolioStore


class _Bench:
    def pct_change(self, a, b):
        return 0.0

    def close_on(self, d):
        return 1000.0


def _prices(mapping):
    """entry price on/before 2026-08-20, exit price after."""
    def _fn(symbol, on):
        if symbol not in mapping:
            raise ValueError(f"no price for {symbol}")
        return mapping[symbol][0] if on <= date(2026, 8, 20) else mapping[symbol][1]
    return _fn


def _seed(tmp_path, **kw):
    store = PortfolioStore(user_id="u1", base_dir=str(tmp_path))
    fields = dict(date="2026-08-20", user_id="u1", origin="OLD",
                  origin_close=100.0, candidate="NEW", candidate_close=200.0,
                  decision="rejected", reason="not_best")
    fields.update(kw)
    store.append_switch_evaluations([SwitchEvaluation(**fields)])
    return store


def _switch_rows(tmp_path):
    return [r for r in AuditOutcomeStore(user_id="u1", base_dir=str(tmp_path)).load_all()
            if r.lane == "switch"]


def test_a_rejected_pair_whose_candidate_won_grades_correct(tmp_path):
    _seed(tmp_path)
    out = grade_switch_lane(
        date(2027, 1, 1), "u1", bench=_Bench(), base_dir=str(tmp_path),
        price_fn=_prices({"OLD": (100.0, 98.0), "NEW": (200.0, 260.0)}))
    assert out["graded"] == 3          # one row per horizon
    r = _switch_rows(tmp_path)[0]
    assert r.symbol == "OLD" and r.candidate == "NEW"
    assert r.excess_pct == -2.0 and r.switch_excess_pct == 30.0
    assert r.correct is True           # declining to rotate was WRONG
    assert r.verdict == ""
    assert r.triggers == ["rejected", "not_best"]


def test_a_taken_pair_whose_destination_lost_grades_incorrect(tmp_path):
    _seed(tmp_path, decision="taken", reason="")
    grade_switch_lane(
        date(2027, 1, 1), "u1", bench=_Bench(), base_dir=str(tmp_path),
        price_fn=_prices({"OLD": (100.0, 98.0), "NEW": (200.0, 160.0)}))
    rows = _switch_rows(tmp_path)
    assert rows[0].correct is False
    assert rows[0].triggers == ["taken", ""]


def test_regrading_is_idempotent(tmp_path):
    _seed(tmp_path)
    kw = dict(bench=_Bench(), base_dir=str(tmp_path),
              price_fn=_prices({"OLD": (100.0, 98.0), "NEW": (200.0, 260.0)}))
    first = grade_switch_lane(date(2027, 1, 1), "u1", **kw)
    second = grade_switch_lane(date(2027, 1, 1), "u1", **kw)
    assert first["graded"] == 3 and second["graded"] == 0
    assert second["already_present"] == 3


def test_an_unpriceable_leg_is_skipped_never_guessed(tmp_path):
    _seed(tmp_path)
    out = grade_switch_lane(
        date(2027, 1, 1), "u1", bench=_Bench(), base_dir=str(tmp_path),
        price_fn=_prices({"OLD": (100.0, 98.0)}))     # NEW has no price
    assert out["graded"] == 0 and out["skipped_unpriceable"] == 3


def test_immature_rows_are_left_alone(tmp_path):
    _seed(tmp_path)
    out = grade_switch_lane(
        date(2026, 8, 21), "u1", bench=_Bench(), base_dir=str(tmp_path),
        price_fn=_prices({"OLD": (100.0, 98.0), "NEW": (200.0, 260.0)}))
    assert out["graded"] == 0


def test_the_lane_is_registered_with_grade_due():
    from core.audit.outcomes import _LANE_KWARGS
    assert "switch" in _LANE_KWARGS


def test_the_lane_is_a_no_op_when_disabled(tmp_path, monkeypatch):
    import core.audit.outcomes as oc
    monkeypatch.setattr(oc, "_switch_lane_enabled", lambda: False)
    _seed(tmp_path)
    out = oc.grade_switch_lane(
        date(2027, 1, 1), "u1", bench=_Bench(), base_dir=str(tmp_path),
        price_fn=_prices({"OLD": (100.0, 98.0), "NEW": (200.0, 260.0)}))
    assert out["graded"] == 0 and _switch_rows(tmp_path) == []

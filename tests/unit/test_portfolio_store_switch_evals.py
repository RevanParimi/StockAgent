"""Switch-evaluation ledger — append-only, one row per considered pair."""
from backend.shared.schemas.portfolio import SwitchEvaluation
from core.portfolio.store import PortfolioStore


def _row(candidate="NEWCO", decision="rejected", reason="not_best"):
    return SwitchEvaluation(
        date="2026-08-20", user_id="u1", origin="OLDCO", origin_close=100.0,
        origin_sector="automobile", origin_confidence=0.42,
        origin_verdict="EXIT", candidate=candidate, candidate_close=250.0,
        candidate_sector="pharma", candidate_conviction=0.81,
        decision=decision, reason=reason, rationale_hash="abc123")


def test_append_then_load_round_trips(tmp_path):
    store = PortfolioStore(user_id="u1", base_dir=str(tmp_path))
    store.append_switch_evaluations([_row(), _row(candidate="OTHERCO")])
    rows = store.load_switch_evaluations()
    assert [r.candidate for r in rows] == ["NEWCO", "OTHERCO"]
    assert rows[0].reason == "not_best"


def test_append_is_additive_never_rewrites(tmp_path):
    store = PortfolioStore(user_id="u1", base_dir=str(tmp_path))
    store.append_switch_evaluations([_row()])
    store.append_switch_evaluations([_row(candidate="THIRDCO")])
    assert len(store.load_switch_evaluations()) == 2


def test_a_corrupt_line_is_skipped_not_fatal(tmp_path):
    store = PortfolioStore(user_id="u1", base_dir=str(tmp_path))
    store.append_switch_evaluations([_row()])
    with open(store._switch_eval_path(), "a", encoding="utf-8") as fh:
        fh.write("{not json\n")
    assert len(store.load_switch_evaluations()) == 1


def test_empty_batch_writes_nothing(tmp_path):
    store = PortfolioStore(user_id="u1", base_dir=str(tmp_path))
    store.append_switch_evaluations([])
    assert store.load_switch_evaluations() == []

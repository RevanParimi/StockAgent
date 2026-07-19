"""
Unit tests for core/intelligence/rl/eval/learning_evidence.py
==============================================================
Learning Evidence Report — the self-ablation experiment (design
2026-07-19). All tests run against tmp_path via PredictionStore(base_dir=...)
and monkeypatched settings dirs — never data/ on disk.
"""
from __future__ import annotations

import json

import pytest

from core.intelligence.rl.eval import learning_evidence as le
from core.intelligence.rl.stores.prediction_store import PredictionStore
from core.schemas.feedback import (
    DailyFeedbackLog,
    FeedbackEntry,
    MissAnalysis,
    WeightHistoryEntry,
    WeightMemory,
)

TICKER = "TESTL"
SECTOR = "automobile"
MONTH = "2026-06"
CYCLE_ID = f"{TICKER}_{MONTH}"


# ---------------------------------------------------------------------------
# Fixture builders
# ---------------------------------------------------------------------------

def _entry(
    day,
    date,
    actual_direction,
    direction_correct,
    scores=None,
    verdict="BUY",
    claims_fired=None,
    miss_agent=None,
    miss_type="direction_flip",
):
    ma = None
    if miss_agent is not None:
        ma = MissAnalysis(primary_miss_agent=miss_agent, miss_type=miss_type)
    return FeedbackEntry(
        day=day,
        date=date,
        predicted_close=100.0,
        actual_close=101.0,
        price_error_pct=1.0,
        predicted_verdict=verdict,
        actual_direction=actual_direction,
        direction_correct=direction_correct,
        predicted_agent_scores=scores or {},
        claims_fired=claims_fired or [],
        miss_analysis=ma,
    )


def _weight_memory(current, base, history=None):
    return WeightMemory(
        ticker=TICKER,
        sector=SECTOR,
        last_updated="2026-06-30",
        weight_version=len(history or []),
        current_weights=current,
        base_weights=base,
        weight_history=history or [],
    )


@pytest.fixture(autouse=True)
def _patch_dirs(tmp_path, monkeypatch):
    monkeypatch.setattr(le.settings, "PREDICTION_DATA_DIR", str(tmp_path / "predictions"))
    monkeypatch.setattr(
        le.settings, "LEARNING_EVIDENCE_DIR", str(tmp_path / "evidence"), raising=False
    )
    return tmp_path


# ---------------------------------------------------------------------------
# Statistics helpers
# ---------------------------------------------------------------------------

def test_wilson_interval_basic():
    lo, hi = le.wilson_interval(8, 10)
    assert 0.0 <= lo < 0.8 < hi <= 1.0
    lo0, hi0 = le.wilson_interval(0, 0)
    assert (lo0, hi0) == (0.0, 1.0)


def test_sign_test_p_exact_values():
    # k=0 of n=10 discordant pairs: p = 2 * (0.5^10) = 0.001953125
    assert le.sign_test_p(0, 10) == pytest.approx(2 * 0.5**10)
    # perfectly split — p capped at 1.0
    assert le.sign_test_p(5, 10) == pytest.approx(1.0)
    # empty — no evidence
    assert le.sign_test_p(0, 0) == 1.0


def test_brier_decomposition_identity():
    # REL - RES + UNC must equal the plain Brier score.
    from core.intelligence.rl.eval.metrics import MatchedRecord, brier_score

    records = [
        MatchedRecord(date="d1", confidence=0.9, direction_correct=True, actual_close=1.0),
        MatchedRecord(date="d2", confidence=0.8, direction_correct=False, actual_close=1.0),
        MatchedRecord(date="d3", confidence=0.3, direction_correct=False, actual_close=1.0),
        MatchedRecord(date="d4", confidence=0.55, direction_correct=True, actual_close=1.0),
    ]
    d = le.brier_decomposition(records)
    assert d["n"] == 4
    assert d["reliability"] - d["resolution"] + d["uncertainty"] == pytest.approx(
        brier_score(records), abs=1e-9
    )


# ---------------------------------------------------------------------------
# Weight reconstruction + composite
# ---------------------------------------------------------------------------

def test_weights_before_picks_last_strictly_before():
    base = {"a": 0.5, "b": 0.5}
    history = [
        WeightHistoryEntry(version=1, date="2026-06-02", weights={"a": 0.6, "b": 0.4}, reason="r"),
        WeightHistoryEntry(version=2, date="2026-06-05", weights={"a": 0.7, "b": 0.3}, reason="r"),
    ]
    # Before any history → base
    assert le.weights_before(history, base, "2026-06-01") == base
    # Same day as v1 → strictly before, so still base
    assert le.weights_before(history, base, "2026-06-02") == base
    # Between v1 and v2 → v1
    assert le.weights_before(history, base, "2026-06-04") == {"a": 0.6, "b": 0.4}
    # After v2 → v2
    assert le.weights_before(history, base, "2026-06-30") == {"a": 0.7, "b": 0.3}


def test_composite_renormalises_over_present_agents():
    scores = {"a": 0.8, "b": 0.4}
    # weight for missing agent "c" must not dilute
    weights = {"a": 0.25, "b": 0.25, "c": 0.5}
    assert le.composite_for(scores, weights) == pytest.approx(0.6)
    # zero overlap → simple mean
    assert le.composite_for(scores, {"c": 1.0}) == pytest.approx(0.6)


# ---------------------------------------------------------------------------
# Counterfactual replay
# ---------------------------------------------------------------------------

def _divergent_setup():
    """adapted -> BUY (correct on UP day), base -> NEUTRAL (wrong on UP day)."""
    scores = {"a": 0.8, "b": 0.4}
    adapted = {"a": 0.8, "b": 0.2}   # composite 0.72 -> BUY
    base = {"a": 0.2, "b": 0.8}      # composite 0.48 -> NEUTRAL
    return scores, adapted, base


def test_replay_detects_divergence_and_lift():
    scores, adapted, base = _divergent_setup()
    history = [
        WeightHistoryEntry(version=1, date="2026-06-01", weights=adapted, reason="r"),
    ]
    wm = _weight_memory(adapted, base, history)
    entries = [
        _entry(1, "2026-06-02", "UP", True, scores=scores),
        _entry(2, "2026-06-03", "UP", True, scores=scores),
    ]
    result = le.replay_ticker(entries, wm)
    assert result["n_replayed"] == 2
    assert result["lanes"]["adapted"]["hits"] == 2
    assert result["lanes"]["base"]["hits"] == 0
    assert result["divergent_vs_base"] == 2
    assert result["adapted_wins_vs_base"] == 2
    assert result["base_wins_vs_adapted"] == 0


def test_replay_skips_entries_without_scores():
    wm = _weight_memory({"a": 1.0}, {"a": 1.0})
    entries = [_entry(1, "2026-06-02", "UP", True, scores={})]
    result = le.replay_ticker(entries, wm)
    assert result["n_replayed"] == 0


# ---------------------------------------------------------------------------
# Signal health
# ---------------------------------------------------------------------------

def test_credit_degeneracy_index_all_correct_is_one():
    scores = {"a": 0.6, "b": 0.6}
    entries = [
        _entry(1, "2026-06-02", "UP", True, scores=scores),
        _entry(2, "2026-06-03", "UP", True, scores=scores),
    ]
    assert le.credit_degeneracy_index(entries) == pytest.approx(1.0)


def test_credit_degeneracy_index_blame_differentiates():
    scores = {"a": 0.6, "b": 0.6}
    entries = [
        _entry(1, "2026-06-02", "UP", True, scores=scores),
        # wrong day, penalisable, agent "a" blamed -> credit differs across agents
        _entry(2, "2026-06-03", "DOWN", False, scores=scores, miss_agent="a"),
    ]
    assert le.credit_degeneracy_index(entries) == pytest.approx(0.5)


def test_weight_health_entropy_and_poverty_trap():
    base = {"a": 0.4, "b": 0.3, "c": 0.3}
    uniformish = {"a": 0.34, "b": 0.33, "c": 0.33}
    wm = _weight_memory(uniformish, base)
    health = le.weight_health(wm)
    # near-uniform current -> normalised entropy near 1
    assert health["entropy_current"] > health["entropy_base"]
    assert health["uniform_distance_current"] < health["uniform_distance_base"]
    assert health["poverty_trapped"] == []

    trapped = {"a": 0.05, "b": 0.475, "c": 0.475}  # uniform=1/3; 0.05 < 0.5*1/3
    wm2 = _weight_memory(trapped, base)
    assert le.weight_health(wm2)["poverty_trapped"] == ["a"]


# ---------------------------------------------------------------------------
# Lesson efficacy
# ---------------------------------------------------------------------------

def test_lesson_efficacy_lift_and_harmful_flag():
    scores = {"a": 0.6}
    fired_bad = [
        _entry(i, f"2026-06-{i:02d}", "DOWN", False, scores=scores, claims_fired=["L001"])
        for i in range(1, 6)
    ]
    unfired_good = [
        _entry(i, f"2026-06-{i:02d}", "UP", True, scores=scores)
        for i in range(6, 11)
    ]
    table = le.lesson_efficacy(fired_bad + unfired_good)
    row = table["L001"]
    assert row["fired_n"] == 5
    assert row["fired_accuracy"] == pytest.approx(0.0)
    assert row["unfired_accuracy"] == pytest.approx(1.0)
    assert row["lift_pp"] == pytest.approx(-100.0)
    assert row["harmful"] is True
    assert row["sufficient"] is True


def test_lesson_efficacy_insufficient_n_not_flagged():
    scores = {"a": 0.6}
    entries = [
        _entry(1, "2026-06-01", "DOWN", False, scores=scores, claims_fired=["L002"]),
        _entry(2, "2026-06-02", "UP", True, scores=scores),
    ]
    row = le.lesson_efficacy(entries)["L002"]
    assert row["sufficient"] is False
    assert row["harmful"] is False


# ---------------------------------------------------------------------------
# Verdict rule
# ---------------------------------------------------------------------------

def _replay_section(n_replayed, n_divergent, adapted_wins, base_wins):
    return {
        "n_replayed": n_replayed,
        "adapted_vs_base": {
            "n_divergent": n_divergent,
            "adapted_wins": adapted_wins,
            "base_wins": base_wins,
            "p_value": le.sign_test_p(min(adapted_wins, base_wins), adapted_wins + base_wins),
        },
    }


def test_verdict_insufficient_data():
    v, _ = le.decide_verdict(_replay_section(100, 5, 4, 1))
    assert v == "INSUFFICIENT_DATA"


def test_verdict_inert():
    v, _ = le.decide_verdict(_replay_section(1000, 10, 6, 4))
    assert v == "LEARNING_INERT"


def test_verdict_beneficial():
    v, _ = le.decide_verdict(_replay_section(100, 20, 18, 2))
    assert v == "LEARNING_ACTIVE_BENEFICIAL"


def test_verdict_harmful():
    v, _ = le.decide_verdict(_replay_section(100, 20, 2, 18))
    assert v == "LEARNING_ACTIVE_HARMFUL"


def test_verdict_unproven():
    v, _ = le.decide_verdict(_replay_section(100, 20, 11, 9))
    assert v == "LEARNING_ACTIVE_UNPROVEN"


# ---------------------------------------------------------------------------
# Builder end-to-end + renderer + persistence
# ---------------------------------------------------------------------------

def _seed(base_dir):
    scores, adapted, base = _divergent_setup()
    store = PredictionStore(TICKER, sector=SECTOR, base_dir=str(base_dir))
    entries = [
        _entry(i, f"{MONTH}-{i:02d}", "UP", True, scores=scores, claims_fired=["L001"])
        for i in range(1, 13)
    ]
    store.save_feedback_log(
        DailyFeedbackLog(ticker=TICKER, sector=SECTOR, cycle_id=CYCLE_ID, entries=entries)
    )
    # Dated before the month starts so the strictly-before rule applies the
    # adapted weights to every replayed day, including day 1.
    history = [WeightHistoryEntry(version=1, date="2026-05-31", weights=adapted, reason="r")]
    store.save_weight_memory(_weight_memory(adapted, base, history))
    return store


def test_build_learning_evidence_end_to_end(tmp_path):
    _seed(tmp_path / "predictions")

    report = le.build_learning_evidence([MONTH])

    assert report["months"] == [MONTH]
    replay = report["replay"]
    assert replay["n_replayed"] == 12
    assert replay["adapted_vs_base"]["n_divergent"] == 12
    assert replay["adapted_vs_base"]["adapted_wins"] == 12
    assert report["verdict"] == "LEARNING_ACTIVE_BENEFICIAL"
    assert TICKER in report["signal_health"]["tickers"]
    assert "L001" in report["lesson_efficacy"]["lessons"]

    text = le.render_report(report)
    assert "LEARNING_ACTIVE_BENEFICIAL" in text
    assert "adapted" in text.lower()

    json_path, txt_path = le.save_report(report)
    assert json_path.exists() and txt_path.exists()
    loaded = json.loads(json_path.read_text(encoding="utf-8"))
    assert loaded["verdict"] == report["verdict"]


def test_build_handles_empty_data_dir(tmp_path):
    report = le.build_learning_evidence([MONTH])
    assert report["replay"]["n_replayed"] == 0
    assert report["verdict"] == "INSUFFICIENT_DATA"


def test_actuation_stats_missing_file(tmp_path):
    stats = le.actuation_stats(tmp_path / "nope.jsonl")
    assert stats["shadow_rows"] == 0


def test_actuation_stats_counts_divergence(tmp_path):
    p = tmp_path / "shadow.jsonl"
    rows = [
        {"ts": "2026-06-01T10:00:00+00:00", "ticker": "X", "diverged": True,
         "learned_weights_used": True},
        {"ts": "2026-06-02T10:00:00+00:00", "ticker": "X", "diverged": False,
         "learned_weights_used": False},
    ]
    p.write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")
    stats = le.actuation_stats(p)
    assert stats["shadow_rows"] == 2
    assert stats["divergence_rate"] == pytest.approx(0.5)
    assert stats["learned_weight_rows"] == 1

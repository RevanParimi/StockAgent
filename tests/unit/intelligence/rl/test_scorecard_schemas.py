"""
Round-trip and default tests for the Monthly Scorecard + Baseline Duel schemas
(spec 2026-06-12, sections 2.2 and 5.1).
"""
from backend.shared.schemas.scorecard import (
    ControlLog,
    ControlPrediction,
    LaneScore,
    MonthlyScorecard,
    TickerScorecard,
)


# ---------------------------------------------------------------------------
# ControlPrediction
# ---------------------------------------------------------------------------

def test_control_prediction_defaults():
    cp = ControlPrediction(date="2026-06-15", made_on="2026-06-14",
                            predicted_direction="UP")
    assert cp.confidence == 0.5
    assert cp.predicted_close is None
    assert cp.rationale == ""
    assert cp.model == ""
    assert cp.actual_direction == ""
    assert cp.correct is None


def test_control_prediction_round_trip():
    cp = ControlPrediction(
        date="2026-06-15", made_on="2026-06-14", predicted_direction="UP",
        confidence=0.7, predicted_close=1234.5, rationale="momentum continuation",
        model="qwen-test", actual_direction="UP", correct=True,
    )
    dumped = cp.model_dump()
    restored = ControlPrediction(**dumped)
    assert restored == cp


# ---------------------------------------------------------------------------
# ControlLog
# ---------------------------------------------------------------------------

def test_control_log_defaults():
    log = ControlLog(ticker="MARUTI", sector="automobile", cycle_id="MARUTI_2026-06")
    assert log.entries == []


def test_control_log_round_trip():
    cp = ControlPrediction(date="2026-06-15", made_on="2026-06-14",
                            predicted_direction="DOWN")
    log = ControlLog(ticker="MARUTI", sector="automobile",
                      cycle_id="MARUTI_2026-06", entries=[cp])
    dumped = log.model_dump()
    restored = ControlLog(**dumped)
    assert restored == log
    assert restored.entries[0].predicted_direction == "DOWN"


def test_control_log_entries_are_independent_lists():
    """Mutable default must not be shared between instances."""
    log1 = ControlLog(ticker="A", sector="automobile", cycle_id="A_2026-06")
    log2 = ControlLog(ticker="B", sector="automobile", cycle_id="B_2026-06")
    log1.entries.append(ControlPrediction(date="2026-06-15", made_on="2026-06-14",
                                            predicted_direction="UP"))
    assert log2.entries == []


# ---------------------------------------------------------------------------
# LaneScore
# ---------------------------------------------------------------------------

def test_lane_score_defaults():
    ls = LaneScore()
    assert ls.n == 0
    assert ls.direction_accuracy is None
    assert ls.brier_score is None


def test_lane_score_round_trip():
    ls = LaneScore(n=16, direction_accuracy=0.625, brier_score=0.221)
    restored = LaneScore(**ls.model_dump())
    assert restored == ls


# ---------------------------------------------------------------------------
# TickerScorecard
# ---------------------------------------------------------------------------

def test_ticker_scorecard_defaults():
    ts = TickerScorecard(ticker="MARUTI", sector="automobile",
                          agent=LaneScore(), control=LaneScore(),
                          persistence=LaneScore(), always_up=LaneScore())
    assert ts.band_coverage is None
    assert ts.mae_pct is None
    assert ts.edge_vs_control is None
    assert ts.edge_vs_persistence is None
    assert ts.claim_days == 0
    assert ts.accuracy_on_claim_days is None
    assert ts.accuracy_on_other_days is None
    assert ts.dossier_version is None
    assert ts.dossier_observations is None
    assert ts.live_signatures is None


def test_ticker_scorecard_round_trip():
    ts = TickerScorecard(
        ticker="MARUTI", sector="automobile",
        agent=LaneScore(n=16, direction_accuracy=0.625, brier_score=0.221),
        control=LaneScore(n=16, direction_accuracy=0.5, brier_score=0.275),
        persistence=LaneScore(n=16, direction_accuracy=0.438),
        always_up=LaneScore(n=16, direction_accuracy=0.563),
        band_coverage=0.8, mae_pct=1.2,
        edge_vs_control=0.125, edge_vs_persistence=0.187,
        claim_days=5, accuracy_on_claim_days=0.8, accuracy_on_other_days=0.545,
        dossier_version=3, dossier_observations=18, live_signatures=2,
    )
    restored = TickerScorecard(**ts.model_dump())
    assert restored == ts


# ---------------------------------------------------------------------------
# MonthlyScorecard
# ---------------------------------------------------------------------------

def test_monthly_scorecard_defaults():
    ms = MonthlyScorecard(month="2026-06", generated_at="2026-06-12T02:00:00")
    assert ms.tickers == {}
    assert ms.aggregate is None
    assert ms.deltas_vs_previous == {}


def test_monthly_scorecard_round_trip():
    ts = TickerScorecard(ticker="MARUTI", sector="automobile",
                          agent=LaneScore(n=16, direction_accuracy=0.625),
                          control=LaneScore(n=16, direction_accuracy=0.5),
                          persistence=LaneScore(n=16, direction_accuracy=0.438),
                          always_up=LaneScore(n=16, direction_accuracy=0.563))
    aggregate = ts.model_copy(update={"ticker": "ALL"})
    ms = MonthlyScorecard(
        month="2026-06", generated_at="2026-06-12T02:00:00",
        tickers={"MARUTI": ts}, aggregate=aggregate,
        deltas_vs_previous={"agent.direction_accuracy": 0.042},
    )
    restored = MonthlyScorecard(**ms.model_dump())
    assert restored == ms
    assert restored.tickers["MARUTI"].ticker == "MARUTI"
    assert restored.aggregate.ticker == "ALL"


def test_monthly_scorecard_mutable_defaults_independent():
    ms1 = MonthlyScorecard(month="2026-06", generated_at="2026-06-12T02:00:00")
    ms2 = MonthlyScorecard(month="2026-07", generated_at="2026-07-12T02:00:00")
    ms1.deltas_vs_previous["x"] = 1.0
    assert ms2.deltas_vs_previous == {}

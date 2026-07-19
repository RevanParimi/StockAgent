"""
Unit tests for core/intelligence/rl/eval/scorecard.py
========================================================
Monthly Scorecard + Baseline Duel — builder + renderer (spec 2026-06-12,
section 5). All tests use tmp_path via PredictionStore(base_dir=...) and
monkeypatch settings.PREDICTION_DATA_DIR / settings.SCORECARD_DIR — never
data/predictions or data/eval on disk.
"""
from __future__ import annotations

import json

import pytest

from backend.shared.schemas.dossier import (
    DossierObservation,
    ResponseSignature,
    TickerDossier,
)
from backend.shared.schemas.scorecard import ControlLog, ControlPrediction, MonthlyScorecard
from core.intelligence.rl.eval import scorecard as sc_mod
from core.intelligence.rl.stores.prediction_store import PredictionStore
from core.schemas.feedback import (
    DailyForecast,
    FeedbackEntry,
    PredictionEnvelope,
)

TICKER = "TESTC"
SECTOR = "automobile"
MONTH = "2026-06"
CYCLE_ID = f"{TICKER}_{MONTH}"


# ---------------------------------------------------------------------------
# Fixture builders
# ---------------------------------------------------------------------------

def _entry(day, date, predicted_close, actual_close, actual_direction,
           direction_correct, claims_fired=None) -> FeedbackEntry:
    price_error_pct = (actual_close - predicted_close) / predicted_close * 100
    return FeedbackEntry(
        day=day, date=date,
        predicted_close=predicted_close, actual_close=actual_close,
        price_error_pct=price_error_pct,
        predicted_verdict="BUY",
        actual_direction=actual_direction,
        direction_correct=direction_correct,
        claims_fired=claims_fired or [],
    )


def _forecast(day, date, predicted_close, confidence, price_lower, price_upper) -> DailyForecast:
    return DailyForecast(
        day=day, date=date, predicted_close=predicted_close,
        predicted_verdict="BUY", confidence=confidence,
        price_lower=price_lower, price_upper=price_upper,
    )


def _seed_ticker(base_dir, ticker=TICKER, sector=SECTOR, month=MONTH,
                  with_dossier=True) -> PredictionStore:
    """Seed a 4-day month of feedback + envelope + control log for `ticker`.

    Hand-computed expectations (see test_scorecard.py docstring assertions):
      agent.direction_accuracy = 0.5    (2/4 correct: days 1,3 UP-correct; 2,4 DOWN-wrong... see below)
      agent.brier_score        = 0.265
      band_coverage             = 0.75  (3/4 days inside band)
      mae_pct                   ~ 1.4902
      control.direction_accuracy = 2/3 (day4 unscored, excluded)
      control.brier_score       ~ 0.27083
      persistence.direction_accuracy = 0.0
      always_up.direction_accuracy   = 0.5
      edge_vs_control     = 0.5 - 2/3      = -0.16667
      edge_vs_persistence = 0.5 - 0.0      = 0.5
      claim_days = 1 (day1)
      accuracy_on_claim_days = 1.0   (day1 direction_correct=True)
      accuracy_on_other_days = 1/3   (days 2,3,4 -> only day3 correct)
    """
    cycle_id = f"{ticker}_{month}"
    store = PredictionStore(ticker, sector=sector, base_dir=base_dir)

    # Feedback log — 4 days.
    entries = [
        _entry(1, f"{month}-01", 100.0, 101.0, "UP", True, claims_fired=["L001"]),
        _entry(2, f"{month}-02", 101.0, 100.0, "DOWN", False),
        _entry(3, f"{month}-03", 100.0, 103.0, "UP", True),
        _entry(4, f"{month}-04", 103.0, 102.0, "DOWN", False),
    ]
    from core.schemas.feedback import DailyFeedbackLog
    store.save_feedback_log(DailyFeedbackLog(ticker=ticker, sector=sector,
                                              cycle_id=cycle_id, entries=entries))

    # Envelope — confidence + bands matching the entries above.
    forecasts = [
        _forecast(1, f"{month}-01", 100.0, 0.6, 98.0, 102.0),   # actual 101 -> inside
        _forecast(2, f"{month}-02", 101.0, 0.7, 99.0, 103.0),   # actual 100 -> inside
        _forecast(3, f"{month}-03", 100.0, 0.5, 101.0, 105.0),  # actual 103 -> inside
        _forecast(4, f"{month}-04", 103.0, 0.4, 104.0, 108.0),  # actual 102 -> outside
    ]
    store.save_envelope(PredictionEnvelope(
        ticker=ticker, sector=sector, cycle_id=cycle_id,
        generated_at=f"{month}-01T00:00:00", base_close=100.0,
        daily_forecasts=forecasts,
    ))

    # Control log — 3 scored entries + 1 unscored (must be excluded).
    control_entries = [
        ControlPrediction(date=f"{month}-01", made_on=f"{month}-01", predicted_direction="UP",
                           confidence=0.55, actual_direction="UP", correct=True),
        ControlPrediction(date=f"{month}-02", made_on=f"{month}-02", predicted_direction="UP",
                           confidence=0.6, actual_direction="DOWN", correct=False),
        ControlPrediction(date=f"{month}-03", made_on=f"{month}-03", predicted_direction="UP",
                           confidence=0.5, actual_direction="UP", correct=True),
        ControlPrediction(date=f"{month}-04", made_on=f"{month}-04", predicted_direction="DOWN",
                           confidence=0.5),  # unscored: correct is None
    ]
    store.save_control_log(ControlLog(ticker=ticker, sector=sector, cycle_id=cycle_id,
                                       entries=control_entries))

    if with_dossier:
        store.save_dossier(TickerDossier(
            ticker=ticker, sector=sector,
            created_at=f"{month}-01", last_updated=f"{month}-01",
            version=2,
            observations=[
                DossierObservation(date=f"{month}-01", observation="o1"),
                DossierObservation(date=f"{month}-02", observation="o2"),
                DossierObservation(date=f"{month}-03", observation="o3"),
            ],
            response_signatures=[
                ResponseSignature(signature_id="S1", response="r1", occurrences=3, contradictions=0),
                ResponseSignature(signature_id="S2", response="r2", occurrences=2, contradictions=0),
                ResponseSignature(signature_id="S3", response="r3", occurrences=1, contradictions=2),  # dead
            ],
        ))

    return store


@pytest.fixture(autouse=True)
def _patch_dirs(tmp_path, monkeypatch):
    """All tests run against tmp_path for both predictions and scorecards."""
    monkeypatch.setattr(sc_mod.settings, "PREDICTION_DATA_DIR", str(tmp_path / "predictions"))
    monkeypatch.setattr(sc_mod.settings, "SCORECARD_DIR", str(tmp_path / "scorecards"))
    return tmp_path


# ---------------------------------------------------------------------------
# build_scorecard — exact lane numbers
# ---------------------------------------------------------------------------

def test_build_scorecard_lane_numbers(tmp_path):
    base_dir = tmp_path / "predictions"
    _seed_ticker(base_dir)

    sc = sc_mod.build_scorecard(MONTH)

    assert sc.month == MONTH
    assert TICKER in sc.tickers
    ts = sc.tickers[TICKER]

    # agent lane
    assert ts.agent.n == 4
    assert ts.agent.direction_accuracy == pytest.approx(0.5)
    assert ts.agent.brier_score == pytest.approx(0.265)

    # band coverage / mae
    assert ts.band_coverage == pytest.approx(0.75)
    assert ts.mae_pct == pytest.approx(1.4902431990771892)

    # control lane (unscored day excluded)
    assert ts.control.n == 3
    assert ts.control.direction_accuracy == pytest.approx(2 / 3)
    assert ts.control.brier_score == pytest.approx(0.2708333333333333)

    # baselines
    assert ts.persistence.direction_accuracy == pytest.approx(0.0)
    assert ts.always_up.direction_accuracy == pytest.approx(0.5)

    # edges
    assert ts.edge_vs_control == pytest.approx(0.5 - 2 / 3)
    assert ts.edge_vs_persistence == pytest.approx(0.5)

    # aggregate mirrors the single ticker (pooled == same data)
    assert sc.aggregate is not None
    assert sc.aggregate.ticker == "ALL"
    assert sc.aggregate.agent.n == 4
    assert sc.aggregate.agent.direction_accuracy == pytest.approx(0.5)


# ---------------------------------------------------------------------------
# Claim split
# ---------------------------------------------------------------------------

def test_build_scorecard_claim_split(tmp_path):
    base_dir = tmp_path / "predictions"
    _seed_ticker(base_dir)

    sc = sc_mod.build_scorecard(MONTH)
    ts = sc.tickers[TICKER]

    assert ts.claim_days == 1
    assert ts.accuracy_on_claim_days == pytest.approx(1.0)
    assert ts.accuracy_on_other_days == pytest.approx(1 / 3)


# ---------------------------------------------------------------------------
# Dossier health
# ---------------------------------------------------------------------------

def test_build_scorecard_dossier_health(tmp_path):
    base_dir = tmp_path / "predictions"
    _seed_ticker(base_dir)

    sc = sc_mod.build_scorecard(MONTH)
    ts = sc.tickers[TICKER]

    assert ts.dossier_version == 2
    assert ts.dossier_observations == 3
    assert ts.live_signatures == 2  # S1, S2 alive; S3 dead (contradictions >= occurrences)


def test_build_scorecard_no_dossier_leaves_none(tmp_path):
    base_dir = tmp_path / "predictions"
    _seed_ticker(base_dir, with_dossier=False)

    sc = sc_mod.build_scorecard(MONTH)
    ts = sc.tickers[TICKER]

    assert ts.dossier_version is None
    assert ts.dossier_observations is None
    assert ts.live_signatures is None


# ---------------------------------------------------------------------------
# Deltas vs previous
# ---------------------------------------------------------------------------

def test_build_scorecard_deltas_vs_previous(tmp_path):
    base_dir = tmp_path / "predictions"
    _seed_ticker(base_dir)

    # Seed a previous month's scorecard with slightly worse aggregate numbers.
    prev_month = "2026-05"
    sc_dir = tmp_path / "scorecards"
    sc_dir.mkdir(parents=True, exist_ok=True)

    prev_sc = sc_mod.build_scorecard(MONTH)  # reuse builder to get a valid shape
    prev_agg = prev_sc.aggregate.model_copy(update={
        "agent": prev_sc.aggregate.agent.model_copy(update={
            "direction_accuracy": prev_sc.aggregate.agent.direction_accuracy - 0.10,
            "brier_score": prev_sc.aggregate.agent.brier_score + 0.05,
        }),
        "band_coverage": prev_sc.aggregate.band_coverage - 0.05,
        "mae_pct": prev_sc.aggregate.mae_pct + 0.2,
        "edge_vs_control": (prev_sc.aggregate.edge_vs_control or 0.0) - 0.02,
    })
    prev = MonthlyScorecard(month=prev_month, generated_at="2026-05-30T00:00:00",
                             tickers={}, aggregate=prev_agg, deltas_vs_previous={})
    (sc_dir / f"{prev_month}_scorecard.json").write_text(
        json.dumps(prev.model_dump(), indent=2), encoding="utf-8"
    )

    sc = sc_mod.build_scorecard(MONTH)

    assert sc.deltas_vs_previous["agent.direction_accuracy"] == pytest.approx(0.10)
    assert sc.deltas_vs_previous["agent.brier_score"] == pytest.approx(-0.05)
    assert sc.deltas_vs_previous["band_coverage"] == pytest.approx(0.05)
    assert sc.deltas_vs_previous["mae_pct"] == pytest.approx(-0.2)
    assert sc.deltas_vs_previous["edge_vs_control"] == pytest.approx(0.02)


def test_build_scorecard_no_previous_file_empty_deltas(tmp_path):
    base_dir = tmp_path / "predictions"
    _seed_ticker(base_dir)

    sc = sc_mod.build_scorecard(MONTH)
    assert sc.deltas_vs_previous == {}


# ---------------------------------------------------------------------------
# Empty data
# ---------------------------------------------------------------------------

def test_build_scorecard_empty_data_valid_with_none_metrics(tmp_path):
    sc = sc_mod.build_scorecard(MONTH)

    assert sc.month == MONTH
    assert sc.tickers == {}
    assert sc.aggregate is not None
    assert sc.aggregate.agent.n == 0
    assert sc.aggregate.agent.direction_accuracy is None
    assert sc.aggregate.agent.brier_score is None
    assert sc.aggregate.band_coverage is None
    assert sc.aggregate.mae_pct is None
    assert sc.aggregate.edge_vs_control is None
    assert sc.deltas_vs_previous == {}


def test_build_scorecard_ticker_filter(tmp_path):
    base_dir = tmp_path / "predictions"
    _seed_ticker(base_dir, ticker=TICKER)
    _seed_ticker(base_dir, ticker="OTHERX")

    sc = sc_mod.build_scorecard(MONTH, tickers=[TICKER])

    assert TICKER in sc.tickers
    assert "OTHERX" not in sc.tickers


# ---------------------------------------------------------------------------
# save_scorecard
# ---------------------------------------------------------------------------

def test_save_scorecard_writes_json(tmp_path):
    base_dir = tmp_path / "predictions"
    _seed_ticker(base_dir)

    sc = sc_mod.build_scorecard(MONTH)
    path = sc_mod.save_scorecard(sc)

    assert path.exists()
    assert path.name == f"{MONTH}_scorecard.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["month"] == MONTH
    assert TICKER in data["tickers"]


# ---------------------------------------------------------------------------
# render_table
# ---------------------------------------------------------------------------

def test_render_table_contains_key_lines(tmp_path):
    base_dir = tmp_path / "predictions"
    _seed_ticker(base_dir)

    sc = sc_mod.build_scorecard(MONTH)
    table = sc_mod.render_table(sc)

    assert f"SCORECARD {MONTH}" in table
    assert "agent" in table
    assert "control LLM" in table
    assert "persistence" in table
    assert "always-up" in table
    assert "claims:" in table
    assert "dossier:" in table
    assert "edge" in table


def test_render_table_shows_deltas_header_when_present(tmp_path):
    base_dir = tmp_path / "predictions"
    _seed_ticker(base_dir)

    sc = sc_mod.build_scorecard(MONTH)
    sc.deltas_vs_previous = {"agent.direction_accuracy": 0.042}

    table = sc_mod.render_table(sc)
    assert "(vs 2026-05)" in table


def test_render_table_empty_data(tmp_path):
    sc = sc_mod.build_scorecard(MONTH)
    table = sc_mod.render_table(sc)

    assert f"SCORECARD {MONTH}" in table
    assert "agent" in table


# ---------------------------------------------------------------------------
# Wave I — per-regime x per-agent hit rates
# ---------------------------------------------------------------------------

def _regime_entry(day, regime, correct, scores, primary=None, miss_type="direction_flip"):
    from core.schemas.feedback import MissAnalysis
    e = _entry(day, f"{MONTH}-{day:02d}", 100.0, 101.0,
               "UP" if correct else "DOWN", correct)
    e.regime_label = regime
    e.predicted_agent_scores = scores
    if primary is not None:
        e.miss_analysis = MissAnalysis(primary_miss_agent=primary, miss_type=miss_type)
    return e


def test_regime_agent_breakdown_hit_credit_rules():
    scores = {"risk_macro": 0.6, "fundamentals": 0.4}
    entries = [
        # NORMAL, correct day -> both agents hit
        _regime_entry(1, "NORMAL", True, scores),
        # MACRO_CRISIS, penalisable miss blamed on risk_macro -> only fundamentals hit
        _regime_entry(2, "MACRO_CRISIS", False, scores, primary="risk_macro"),
        # MACRO_CRISIS, external_shock miss -> both hit (model not at fault)
        _regime_entry(3, "MACRO_CRISIS", False, scores,
                      primary="risk_macro", miss_type="external_shock"),
    ]
    out = sc_mod._regime_agent_breakdown(entries)

    assert out["NORMAL"]["n"] == 1
    assert out["NORMAL"]["direction_accuracy"] == 1.0
    assert out["NORMAL"]["agents"]["risk_macro"]["hit_rate"] == 1.0

    crisis = out["MACRO_CRISIS"]
    assert crisis["n"] == 2
    assert crisis["direction_accuracy"] == 0.0
    assert crisis["agents"]["risk_macro"] == {"hits": 1, "total": 2, "hit_rate": 0.5}
    assert crisis["agents"]["fundamentals"] == {"hits": 2, "total": 2, "hit_rate": 1.0}


def test_regime_breakdown_matches_weight_adapter_rule():
    """The scorecard must use WeightAdapter's shared hit-credit helper."""
    import inspect
    src = inspect.getsource(sc_mod._regime_agent_breakdown)
    assert "agent_hit_credit" in src


def test_build_scorecard_populates_regime_breakdown(tmp_path):
    base_dir = tmp_path / "predictions"
    _seed_ticker(base_dir)
    sc = sc_mod.build_scorecard(MONTH)
    # Seeded entries default to regime NORMAL with no per-agent scores.
    assert sc.regime_agent_hit_rates["NORMAL"]["n"] == 4
    assert sc.regime_agent_hit_rates["NORMAL"]["direction_accuracy"] == 0.5


def test_render_table_regime_section(tmp_path):
    base_dir = tmp_path / "predictions"
    _seed_ticker(base_dir)
    sc = sc_mod.build_scorecard(MONTH)
    table = sc_mod.render_table(sc)
    assert "by regime" in table
    assert "NORMAL" in table

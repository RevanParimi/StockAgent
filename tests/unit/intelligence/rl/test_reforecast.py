"""
tests/unit/intelligence/rl/test_reforecast.py
===============================================
Living Envelope (RL Phase 2.5), Component 2 — regenerate_envelope().

Covers:
  - Happy path: regenerates only the remaining (future) forecast days;
    days at/before review_date stay byte-identical.
  - archive_envelope() is called before save.
  - reforecast_count incremented + ReforecastEvent appended to history.
  - At-cap (reforecast_count >= RL_REFORECAST_MAX_PER_MONTH) -> None, no
    archive/save side effects.
  - RL_REFORECAST_ENABLED == False -> None, no side effects at all.
  - Orchestrator/pipeline failure -> None, original envelope left intact.
"""

from __future__ import annotations

from datetime import date

import pytest

from core.intelligence.rl.stores.prediction_store import PredictionStore
from core.intelligence.rl.workflows import generate_forecast as gf
from backend.shared.schemas.feedback import (
    DailyForecast,
    PredictionEnvelope,
    ReforecastEvent,
)
from core.schemas.pipeline import FinalReport, WeightedAgentScore
from core.intelligence.rl.algorithms.price_interpolator import ForecastProfile
from core.intelligence.regime.detector import RegimeDetector, RegimeSnapshot


CYCLE_ID = "MARUTI_2026-06"


def _make_envelope(ticker: str = "MARUTI", cycle_id: str = CYCLE_ID) -> PredictionEnvelope:
    """Minimal real-shaped envelope with 5 daily forecasts (days 1-5)."""
    dates = ["2026-06-08", "2026-06-09", "2026-06-10", "2026-06-11", "2026-06-12"]
    forecasts = [
        DailyForecast(
            day=i + 1,
            date=d,
            predicted_close=1000.0 + i,
            price_lower=990.0 + i,
            price_upper=1010.0 + i,
            predicted_change_pct=0.1 * i,
            predicted_verdict="BUY",
            predicted_agent_scores={"sales_demand": 0.6},
            confidence=0.7,
            key_assumptions=["original assumption"],
            revised=False,
            revision_count=0,
            predicted_agent_catalysts={},
        )
        for i, d in enumerate(dates)
    ]
    return PredictionEnvelope(
        ticker=ticker,
        sector="automobile",
        cycle_id=cycle_id,
        generated_at="2026-06-01T09:00:00",
        base_close=1000.0,
        weight_version_used=1,
        daily_forecasts=forecasts,
    )


def _mock_report() -> FinalReport:
    return FinalReport(
        ticker="MARUTI",
        company_name="Maruti Suzuki",
        verdict="BUY",
        final_score=0.65,
        weighted_agent_scores={
            "sales_demand": WeightedAgentScore(raw=0.6, weight=1.0, weighted=0.6),
        },
        conviction_drivers=["Strong Q1 sales"],
        agent_outputs={},
    )


class _FakeOrchestrator:
    def __init__(self, report: FinalReport):
        self._report = report
        self.set_aggregator_weights_calls = []
        self.analyse_calls = []

    def set_aggregator_weights(self, weights, ticker):
        self.set_aggregator_weights_calls.append((dict(weights), ticker))

    def analyse(self, ticker):
        self.analyse_calls.append(ticker)
        return self._report


def _patch_pipeline(monkeypatch, tmp_path, report=None, base_close=1050.0, raise_on_analyse=False):
    """Common monkeypatches for a successful regenerate_envelope() pipeline run."""
    report = report or _mock_report()
    fake_orch = _FakeOrchestrator(report)

    def _get_orchestrator(sector):
        if raise_on_analyse:
            class _Boom(_FakeOrchestrator):
                def analyse(self, ticker):
                    raise RuntimeError("orchestrator boom")
            return _Boom(report)
        return fake_orch

    monkeypatch.setattr(gf, "get_orchestrator", _get_orchestrator)
    monkeypatch.setattr(gf, "get_sector_weights", lambda sector: {"sales_demand": 1.0})
    monkeypatch.setattr(gf, "_fetch_actual_close", lambda ticker: base_close)
    monkeypatch.setattr(gf, "get_price_history", lambda *a, **k: None)
    monkeypatch.setattr(
        RegimeDetector, "detect",
        lambda self, as_of, sector: RegimeSnapshot(regime_label="NORMAL"),
    )
    monkeypatch.setattr(
        gf.PriceInterpolator, "get_profile",
        lambda self, **kwargs: ForecastProfile(
            monthly_return_pct=2.0, path_shape="linear",
            confidence_band_daily_pct=1.0, reasoning="test", source="llm",
        ),
    )
    return fake_orch


def _seed_store(tmp_path, envelope: PredictionEnvelope) -> PredictionStore:
    store = PredictionStore(envelope.ticker, sector=envelope.sector, base_dir=str(tmp_path))
    store.save_envelope(envelope)
    return store


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------

def test_regenerate_envelope_replaces_only_future_days(tmp_path, monkeypatch):
    monkeypatch.setattr(gf.settings, "PREDICTION_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(gf.settings, "RL_REFORECAST_ENABLED", True)
    monkeypatch.setattr(gf.settings, "RL_REFORECAST_MAX_PER_MONTH", 2)

    envelope = _make_envelope()
    store = _seed_store(tmp_path, envelope)
    _patch_pipeline(monkeypatch, tmp_path)

    review_date = date(2026, 6, 9)  # day 2 — days 3,4,5 (06-10,06-11,06-12) are "future"

    result = gf.regenerate_envelope(
        ticker="MARUTI", sector="automobile",
        reason="External shock detected", trigger="external_shock",
        review_date=review_date,
    )

    assert result is not None

    # Past days (<= review_date) are byte-identical to the original envelope.
    original_past = [f for f in envelope.daily_forecasts if f.date <= "2026-06-09"]
    result_past = [f for f in result.daily_forecasts if f.date <= "2026-06-09"]
    assert [f.model_dump() for f in result_past] == [f.model_dump() for f in original_past]

    # Future days (> review_date) are regenerated — different predicted_close
    # values from the original (anchored on new base_close=1050 vs 1000).
    original_future = {f.date: f for f in envelope.daily_forecasts if f.date > "2026-06-09"}
    result_future = {f.date: f for f in result.daily_forecasts if f.date > "2026-06-09"}
    assert set(result_future.keys()) == set(original_future.keys())
    for d, fc in result_future.items():
        assert fc.predicted_close != original_future[d].predicted_close
        assert fc.revision_count == 0
        assert fc.revised is False

    # Day numbering continues from the last preserved past day.
    assert [f.day for f in result.daily_forecasts] == [1, 2, 3, 4, 5]

    # Forecast profile metadata reflects the freshly-computed profile.
    assert result.forecast_profile_shape == "linear"
    assert result.forecast_profile_monthly_pct == 2.0
    assert result.forecast_profile_source == "llm"


def test_regenerate_envelope_calls_archive_before_save(tmp_path, monkeypatch):
    monkeypatch.setattr(gf.settings, "PREDICTION_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(gf.settings, "RL_REFORECAST_ENABLED", True)
    monkeypatch.setattr(gf.settings, "RL_REFORECAST_MAX_PER_MONTH", 2)

    envelope = _make_envelope()
    _seed_store(tmp_path, envelope)
    _patch_pipeline(monkeypatch, tmp_path)

    call_order: list[str] = []

    orig_archive = PredictionStore.archive_envelope
    orig_save = PredictionStore.save_envelope

    def _tracking_archive(self, cycle_id=None):
        call_order.append("archive")
        return orig_archive(self, cycle_id)

    def _tracking_save(self, env):
        call_order.append("save")
        return orig_save(self, env)

    monkeypatch.setattr(PredictionStore, "archive_envelope", _tracking_archive)
    monkeypatch.setattr(PredictionStore, "save_envelope", _tracking_save)

    result = gf.regenerate_envelope(
        ticker="MARUTI", sector="automobile",
        reason="External shock detected", trigger="external_shock",
        review_date=date(2026, 6, 9),
    )

    assert result is not None
    assert call_order.index("archive") < call_order.index("save")

    # Archived file should exist on disk.
    archive_dir = PredictionStore("MARUTI", sector="automobile", base_dir=str(tmp_path))._dir / "archived_envelopes"
    assert archive_dir.exists()
    assert any(archive_dir.iterdir())


def test_regenerate_envelope_increments_count_and_history(tmp_path, monkeypatch):
    monkeypatch.setattr(gf.settings, "PREDICTION_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(gf.settings, "RL_REFORECAST_ENABLED", True)
    monkeypatch.setattr(gf.settings, "RL_REFORECAST_MAX_PER_MONTH", 2)

    envelope = _make_envelope()
    store = _seed_store(tmp_path, envelope)
    _patch_pipeline(monkeypatch, tmp_path)

    result = gf.regenerate_envelope(
        ticker="MARUTI", sector="automobile",
        reason="Thesis broke down", trigger="thesis_break",
        review_date=date(2026, 6, 9),
    )

    assert result is not None
    assert result.reforecast_count == 1
    assert len(result.reforecast_history) == 1

    event = result.reforecast_history[0]
    assert isinstance(event, ReforecastEvent)
    assert event.date == "2026-06-09"
    assert event.reason == "Thesis broke down"
    assert event.trigger == "thesis_break"
    assert event.archived_file != ""

    # Persisted to disk too.
    reloaded = store.load_envelope(CYCLE_ID)
    assert reloaded.reforecast_count == 1
    assert len(reloaded.reforecast_history) == 1


# ---------------------------------------------------------------------------
# At-cap
# ---------------------------------------------------------------------------

def test_regenerate_envelope_at_cap_returns_none_no_side_effects(tmp_path, monkeypatch):
    monkeypatch.setattr(gf.settings, "PREDICTION_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(gf.settings, "RL_REFORECAST_ENABLED", True)
    monkeypatch.setattr(gf.settings, "RL_REFORECAST_MAX_PER_MONTH", 2)

    envelope = _make_envelope()
    envelope.reforecast_count = 2  # already at cap
    store = _seed_store(tmp_path, envelope)
    _patch_pipeline(monkeypatch, tmp_path)

    archive_called = []
    save_called = []
    monkeypatch.setattr(
        PredictionStore, "archive_envelope",
        lambda self, cycle_id=None: archive_called.append(True),
    )
    monkeypatch.setattr(
        PredictionStore, "save_envelope",
        lambda self, env: save_called.append(True),
    )

    result = gf.regenerate_envelope(
        ticker="MARUTI", sector="automobile",
        reason="External shock detected", trigger="external_shock",
        review_date=date(2026, 6, 9),
    )

    assert result is None
    assert archive_called == []
    assert save_called == []

    # Original envelope on disk untouched.
    reloaded = store.load_envelope(CYCLE_ID)
    assert reloaded.reforecast_count == 2
    assert reloaded.reforecast_history == []


# ---------------------------------------------------------------------------
# Flag off
# ---------------------------------------------------------------------------

def test_regenerate_envelope_flag_off_returns_none_no_side_effects(tmp_path, monkeypatch):
    monkeypatch.setattr(gf.settings, "PREDICTION_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(gf.settings, "RL_REFORECAST_ENABLED", False)

    envelope = _make_envelope()
    store = _seed_store(tmp_path, envelope)

    # No pipeline mocks installed at all — if the flag-off short-circuit
    # didn't fire, this would attempt real orchestrator/yfinance/LLM calls
    # and fail loudly (or hang).
    archive_called = []
    save_called = []
    monkeypatch.setattr(
        PredictionStore, "archive_envelope",
        lambda self, cycle_id=None: archive_called.append(True),
    )
    monkeypatch.setattr(
        PredictionStore, "save_envelope",
        lambda self, env: save_called.append(True),
    )

    result = gf.regenerate_envelope(
        ticker="MARUTI", sector="automobile",
        reason="External shock detected", trigger="external_shock",
        review_date=date(2026, 6, 9),
    )

    assert result is None
    assert archive_called == []
    assert save_called == []

    reloaded = store.load_envelope(CYCLE_ID)
    assert reloaded.reforecast_count == 0


# ---------------------------------------------------------------------------
# Orchestrator failure
# ---------------------------------------------------------------------------

def test_regenerate_envelope_orchestrator_failure_returns_none_original_intact(tmp_path, monkeypatch):
    monkeypatch.setattr(gf.settings, "PREDICTION_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(gf.settings, "RL_REFORECAST_ENABLED", True)
    monkeypatch.setattr(gf.settings, "RL_REFORECAST_MAX_PER_MONTH", 2)

    envelope = _make_envelope()
    store = _seed_store(tmp_path, envelope)
    _patch_pipeline(monkeypatch, tmp_path, raise_on_analyse=True)

    result = gf.regenerate_envelope(
        ticker="MARUTI", sector="automobile",
        reason="External shock detected", trigger="external_shock",
        review_date=date(2026, 6, 9),
    )

    assert result is None

    # Original envelope intact on disk (archive may have happened before the
    # failure, but the saved envelope itself must be unchanged).
    reloaded = store.load_envelope(CYCLE_ID)
    assert reloaded.reforecast_count == 0
    assert reloaded.reforecast_history == []
    assert [f.model_dump() for f in reloaded.daily_forecasts] == [f.model_dump() for f in envelope.daily_forecasts]


# ---------------------------------------------------------------------------
# No remaining days
# ---------------------------------------------------------------------------

def test_regenerate_envelope_no_remaining_days_returns_none(tmp_path, monkeypatch):
    monkeypatch.setattr(gf.settings, "PREDICTION_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(gf.settings, "RL_REFORECAST_ENABLED", True)
    monkeypatch.setattr(gf.settings, "RL_REFORECAST_MAX_PER_MONTH", 2)

    envelope = _make_envelope()
    store = _seed_store(tmp_path, envelope)
    _patch_pipeline(monkeypatch, tmp_path)

    archive_called = []
    monkeypatch.setattr(
        PredictionStore, "archive_envelope",
        lambda self, cycle_id=None: archive_called.append(True),
    )

    # review_date is on/after the last forecast date -> nothing left to regenerate.
    result = gf.regenerate_envelope(
        ticker="MARUTI", sector="automobile",
        reason="External shock detected", trigger="external_shock",
        review_date=date(2026, 6, 12),
    )

    assert result is None
    assert archive_called == []

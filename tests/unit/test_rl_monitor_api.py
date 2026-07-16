"""AUD-100: the RL Monitor page fetched five /ui/rl/* routes that never existed.
These tests pin the new adapter routes to the page's contract (mock shapes in
rl-data.jsx)."""
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


def _client(monkeypatch, tmp_path, tickers=None):
    import services.api.routes.rl_monitor as rlm
    monkeypatch.setattr(
        rlm, "_managed",
        lambda: tickers if tickers is not None else [{"sym": "MARUTI", "sector": "automobile"}],
    )
    monkeypatch.setattr(rlm, "_BASE_DIR_OVERRIDE", str(tmp_path), raising=False)
    app = FastAPI()
    app.include_router(rlm.router)
    return TestClient(app)


def _seed_store(tmp_path, ticker="MARUTI", sector="automobile"):
    """Write a minimal envelope + feedback log + weight memory via the real store."""
    from datetime import date

    from core.intelligence.rl.stores.prediction_store import PredictionStore
    from core.schemas.feedback import (
        ConvictionStreak, DailyFeedbackLog, DailyForecast, FeedbackEntry,
        PredictionEnvelope, WeightMemory, WeightHistoryEntry,
    )
    store = PredictionStore(ticker, sector=sector, base_dir=str(tmp_path))
    cycle = store.current_cycle_id()
    today = date.today().isoformat()
    env = PredictionEnvelope(
        ticker=ticker, sector=sector, cycle_id=cycle, generated_at=today,
        base_close=100.0, weight_version_used=2,
        daily_forecasts=[DailyForecast(day=1, date=today, predicted_close=101.0,
                                       predicted_verdict="BUY", confidence=0.7)],
        conviction_streak=ConvictionStreak(current_verdict="BUY", streak_days=3,
                                           reversion_prior=0.1),
    )
    store.save_envelope(env)
    fb = DailyFeedbackLog(ticker=ticker, cycle_id=cycle, entries=[
        FeedbackEntry(day=1, date=today, predicted_close=101.0, actual_close=102.0,
                      price_error_pct=0.99, predicted_verdict="BUY",
                      actual_direction="UP", direction_correct=True),
    ])
    store.save_feedback_log(fb)
    wm = WeightMemory(ticker=ticker, sector=sector, last_updated=today,
                      weight_version=2,
                      current_weights={"fundamentals": 0.6, "sentiment": 0.4},
                      base_weights={"fundamentals": 0.5, "sentiment": 0.5},
                      weight_history=[WeightHistoryEntry(
                          version=2, date=today, reason="test",
                          weights={"fundamentals": 0.6, "sentiment": 0.4})])
    store.save_weight_memory(wm)
    return cycle


def test_tickers_route_shape(monkeypatch, tmp_path):
    _seed_store(tmp_path)
    c = _client(monkeypatch, tmp_path)
    d = c.get("/ui/rl/tickers").json()
    assert d["tickers"], "managed list must map to tickers"
    t = d["tickers"][0]
    assert set(t) >= {"sym", "name", "color", "enabled", "has_envelope", "has_weights"}
    assert t["sym"] == "MARUTI" and t["has_envelope"] is True and t["has_weights"] is True


def test_summary_route(monkeypatch, tmp_path):
    _seed_store(tmp_path)
    c = _client(monkeypatch, tmp_path)
    d = c.get("/ui/rl/summary/MARUTI").json()
    assert d["available"] is True
    assert d["total_entries"] == 1 and d["direction_hits"] == 1
    assert d["direction_accuracy_pct"] == 100.0
    assert d["current_verdict"] == "BUY" and d["streak_days"] == 3
    assert d["weight_version"] == 2


def test_predictions_route(monkeypatch, tmp_path):
    _seed_store(tmp_path)
    c = _client(monkeypatch, tmp_path)
    d = c.get("/ui/rl/predictions/MARUTI").json()
    assert d["available"] is True and len(d["days"]) == 1
    day = d["days"][0]
    assert day["predicted"] == 101.0 and day["actual"] == 102.0
    assert day["direction_hit"] is True and day["confidence"] == 0.7


def test_weights_route(monkeypatch, tmp_path):
    _seed_store(tmp_path)
    c = _client(monkeypatch, tmp_path)
    d = c.get("/ui/rl/weights/MARUTI").json()
    assert d["available"] is True
    assert d["current_weights"]["fundamentals"] == 0.6
    assert d["weight_history"][0]["version"] == 2


def test_misses_route_empty_but_available(monkeypatch, tmp_path):
    _seed_store(tmp_path)
    c = _client(monkeypatch, tmp_path)
    d = c.get("/ui/rl/misses/MARUTI").json()
    assert d["available"] is True and d["miss_type_counts"] == {}


def test_unknown_ticker_404_and_no_dir_created(monkeypatch, tmp_path):
    """AUD-024 class: an arbitrary URL ticker must NOT construct a
    PredictionStore (which mkdirs on init)."""
    c = _client(monkeypatch, tmp_path)
    assert c.get("/ui/rl/summary/EVIL").status_code == 404
    assert not (tmp_path / "automobile" / "EVIL").exists()


def test_no_data_returns_available_false(monkeypatch, tmp_path):
    c = _client(monkeypatch, tmp_path)  # managed, but nothing seeded
    d = c.get("/ui/rl/summary/MARUTI").json()
    assert d["available"] is False

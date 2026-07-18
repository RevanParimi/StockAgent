"""Compass Phase B — paper envelopes + weekly paper reviews for shelf ideas."""
from datetime import date

import pytest

import core.discovery.paper_lane as pl
from backend.shared.schemas.discovery import Shelf, ShelfIdea


def _idea(symbol="AAA", status="active"):
    return ShelfIdea(symbol=symbol, sector="pharma", added="2026-07-04",
                     conviction=0.7, status=status)


def test_ensure_paper_envelope_generates_once(monkeypatch, tmp_path):
    monkeypatch.setattr(pl.settings, "PAPER_PREDICTION_DATA_DIR", str(tmp_path))
    envelopes = {}

    class _FakeStore:
        def __init__(self, ticker, sector=None, base_dir=None):
            self._key = f"{ticker}|{sector}|{base_dir}"
        def current_cycle_id(self):
            return "AAA_2026-07"
        def load_envelope(self, cycle_id):
            return envelopes.get(cycle_id)
    monkeypatch.setattr(pl, "PredictionStore", _FakeStore)

    calls = []
    def fake_generate(ticker, sector="automobile", paper=False):
        assert paper is True
        calls.append(ticker)
        envelopes["AAA_2026-07"] = object()
        class _E: cycle_id = "AAA_2026-07"
        return _E()
    monkeypatch.setattr(pl, "generate_forecast", fake_generate)

    assert pl.ensure_paper_envelope(_idea()) == "AAA_2026-07"
    assert pl.ensure_paper_envelope(_idea()) == "AAA_2026-07"
    assert calls == ["AAA"]                       # generated exactly once


def test_run_paper_reviews_weekly(monkeypatch):
    ideas = [_idea("AAA"), _idea("BBB"), _idea("OLD", status="dropped")]
    shelf = Shelf(ideas=ideas)
    saved = []

    class _FakeShelfStore:
        def load(self):
            return shelf
        def save(self, s):
            saved.append(s)
    monkeypatch.setattr(pl, "ShelfStore", _FakeShelfStore)
    monkeypatch.setattr(pl, "ensure_paper_envelope", lambda idea: "X_2026-07")
    monkeypatch.setattr(pl, "is_trading_day", lambda d: d.weekday() < 5)

    reviews = []
    def fake_review(ticker, review_date, sector="automobile", paper=False):
        assert paper is True
        if ticker == "BBB":
            raise RuntimeError("boom")
        reviews.append((ticker, review_date.isoformat(), sector))
        return {"status": "completed"}
    monkeypatch.setattr(pl, "run_daily_review", fake_review)

    result = pl.run_paper_reviews(on=date(2026, 7, 4))    # Saturday
    assert result["reviewed"] == ["AAA"]
    assert result["failed"] == ["BBB"]
    assert result["skipped"] == []                        # dropped idea not counted
    assert reviews == [("AAA", "2026-07-03", "pharma")]   # last trading day = Friday
    assert shelf.ideas[0].last_paper_review == "2026-07-03"
    assert shelf.ideas[0].paper_cycle_id == "X_2026-07"
    assert saved                                          # shelf persisted


def test_ensure_paper_envelope_regenerates_poisoned_nan_base(monkeypatch, tmp_path):
    # RISHABH 2026-07-18: a NaN yfinance close was saved as base_close=nan;
    # "generate only when missing" would have kept the poisoned envelope forever.
    monkeypatch.setattr(pl.settings, "PAPER_PREDICTION_DATA_DIR", str(tmp_path))

    class _PoisonedEnv:
        base_close = float("nan")

    envelopes = {"AAA_2026-07": _PoisonedEnv()}

    class _FakeStore:
        def __init__(self, ticker, sector=None, base_dir=None):
            pass
        def current_cycle_id(self):
            return "AAA_2026-07"
        def load_envelope(self, cycle_id):
            return envelopes.get(cycle_id)
    monkeypatch.setattr(pl, "PredictionStore", _FakeStore)

    calls = []
    def fake_generate(ticker, sector="automobile", paper=False):
        calls.append(ticker)
        class _E:
            cycle_id = "AAA_2026-07"
            base_close = 100.0
        envelopes["AAA_2026-07"] = _E()
        return _E()
    monkeypatch.setattr(pl, "generate_forecast", fake_generate)

    assert pl.ensure_paper_envelope(_idea()) == "AAA_2026-07"
    assert calls == ["AAA"]                      # regenerated despite existing
    assert pl.ensure_paper_envelope(_idea()) == "AAA_2026-07"
    assert calls == ["AAA"]                      # healthy envelope → no regen

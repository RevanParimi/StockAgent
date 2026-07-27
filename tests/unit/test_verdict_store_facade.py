"""Atlas C2 — the VerdictStore facade (user-plane read seam over the
intelligence plane), design spec §3.

Two contracts:
  1. The three advisor reads (cycle_id_for / load_envelope / load_feedback_log)
     delegate to PredictionStore and return its objects UNCHANGED, so the
     advisor swap is a pure import + type-hint change. Each read is hot-path
     safe: it degrades to None on a store exception (the advisor already treats
     missing artifacts as conservative defaults).
  2. The projection surface (publish_projection → ticker_verdicts row;
     get_verdict_card reads it back) is the fast multi-user read model.
"""
from __future__ import annotations

from datetime import date
from types import SimpleNamespace

import pytest

import services.data.stores.atlas_store as atlas_store
import services.data.verdict_store as verdict_store


# ---- fakes standing in for PredictionStore (no intelligence import needed) --

def _fake_envelope():
    return SimpleNamespace(
        daily_forecasts=[SimpleNamespace(date="2026-01-05", predicted_close=105.0,
                                         confidence=0.6)],
        conviction_streak=SimpleNamespace(reversion_prior=0.3),
        reforecast_history=[SimpleNamespace(reason="external_shock")],
    )


def _fake_log():
    return SimpleNamespace(entries=[SimpleNamespace(
        regime_label="NORMAL", direction_correct=True,
        thesis_review=SimpleNamespace(thesis_intact=True))])


class _FakePredictionStore:
    def __init__(self, ticker, sector=None):
        self.ticker, self.sector = ticker, sector

    def cycle_id_for(self, target):
        return f"{self.ticker}_{target.year}-{target.month:02d}"

    def load_envelope(self, cycle_id=None):
        return _fake_envelope()

    def load_feedback_log(self, cycle_id=None):
        return _fake_log()


class _RaisingPredictionStore(_FakePredictionStore):
    def load_envelope(self, cycle_id=None):
        raise RuntimeError("boom")

    def load_feedback_log(self, cycle_id=None):
        raise RuntimeError("boom")


@pytest.fixture()
def fake_ps(monkeypatch):
    monkeypatch.setattr(verdict_store, "PredictionStore", _FakePredictionStore)


@pytest.fixture()
def raising_ps(monkeypatch):
    monkeypatch.setattr(verdict_store, "PredictionStore", _RaisingPredictionStore)


# ---- (1) delegation ---------------------------------------------------------

def test_cycle_id_delegates(fake_ps):
    vs = verdict_store.VerdictStore("TCS", sector="it")
    assert vs.cycle_id_for(date(2026, 1, 5)) == "TCS_2026-01"


def test_load_envelope_returns_store_object_unchanged(fake_ps):
    vs = verdict_store.VerdictStore("TCS")
    env = vs.load_envelope(vs.cycle_id_for(date(2026, 1, 5)))
    # exact shape the advisor reads (advisor.py:137-151)
    assert env.daily_forecasts[0].predicted_close == 105.0
    assert env.daily_forecasts[0].confidence == 0.6
    assert env.conviction_streak.reversion_prior == 0.3
    assert env.reforecast_history[-1].reason == "external_shock"


def test_load_feedback_log_returns_store_object_unchanged(fake_ps):
    vs = verdict_store.VerdictStore("TCS")
    log = vs.load_feedback_log("TCS_2026-01")
    e = log.entries[-1]
    assert e.regime_label == "NORMAL"
    assert e.direction_correct is True
    assert e.thesis_review.thesis_intact is True


# ---- (1b) hot-path degradation ---------------------------------------------

def test_reads_degrade_to_none_on_store_exception(raising_ps):
    vs = verdict_store.VerdictStore("TCS")
    assert vs.load_envelope("c") is None
    assert vs.load_feedback_log("c") is None


# ---- (2) projection round-trip (atlas.db ticker_verdicts) ------------------

@pytest.fixture()
def tmp_atlas(tmp_path, monkeypatch):
    monkeypatch.setattr(atlas_store, "_DB_PATH", tmp_path / "atlas.db")
    monkeypatch.setattr(atlas_store, "_conn_holder", {"conn": None})
    atlas_store._reset_for_tests()
    yield
    atlas_store._reset_for_tests()


def test_publish_then_get_verdict_card_round_trip(tmp_atlas, fake_ps):
    vs = verdict_store.VerdictStore("TCS")
    ok = vs.publish_projection("TCS", date(2026, 1, 5), verdict="ADD",
                               confidence=0.7, regime="NORMAL",
                               envelope_direction="UP", predicted_close=105.0)
    assert ok is True
    card = vs.get_verdict_card("TCS", date(2026, 1, 5))
    assert card is not None
    assert card["verdict"] == "ADD"
    assert card["confidence"] == 0.7
    assert card["envelope_direction"] == "UP"
    # miss → None (no row for that date)
    assert vs.get_verdict_card("TCS", date(2026, 1, 6)) is None


def test_publish_projection_is_idempotent_upsert(tmp_atlas, fake_ps):
    vs = verdict_store.VerdictStore("TCS")
    vs.publish_projection("TCS", date(2026, 1, 5), verdict="HOLD")
    vs.publish_projection("TCS", date(2026, 1, 5), verdict="EXIT", confidence=0.2)
    conn = atlas_store._get_conn()
    rows = conn.execute(
        "SELECT verdict, confidence FROM ticker_verdicts"
        " WHERE symbol='TCS' AND as_of_date='2026-01-05'").fetchall()
    assert len(rows) == 1                       # upsert, not a second row
    assert rows[0]["verdict"] == "EXIT"
    assert rows[0]["confidence"] == 0.2


def test_get_verdict_card_hotpath_safe_on_bad_db(tmp_atlas, fake_ps, monkeypatch):
    # A store failure must degrade to None, never raise into fan-out.
    def _boom():
        raise RuntimeError("db down")
    monkeypatch.setattr(atlas_store, "_get_conn", _boom)
    vs = verdict_store.VerdictStore("TCS")
    assert vs.get_verdict_card("TCS", date(2026, 1, 5)) is None
    assert vs.publish_projection("TCS", date(2026, 1, 5)) is False

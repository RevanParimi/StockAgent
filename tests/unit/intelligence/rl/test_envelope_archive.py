"""
tests/unit/intelligence/rl/test_envelope_archive.py
====================================================
Living Envelope (RL Phase 2.5), Component 2 — envelope archive on re-forecast.

Covers:
  - PredictionStore.archive_envelope(): creates archived_envelopes/{month}_v1.json,
    then v2 on a second call; returns the archived path.
  - Missing envelope -> None, no raise.
  - PredictionEnvelope.reforecast_count / reforecast_history defaults keep a
    legacy (pre-Living-Envelope) stored envelope loadable.
"""

from __future__ import annotations

import json

from core.intelligence.rl.stores.prediction_store import PredictionStore
from backend.shared.schemas.feedback import PredictionEnvelope, ReforecastEvent


def _make_envelope(ticker: str, cycle_id: str) -> PredictionEnvelope:
    return PredictionEnvelope(
        ticker=ticker,
        sector="automobile",
        cycle_id=cycle_id,
        generated_at="2026-06-01T09:00:00",
        base_close=1000.0,
    )


# ---------------------------------------------------------------------------
# archive_envelope
# ---------------------------------------------------------------------------

def test_archive_envelope_creates_v1(tmp_path):
    store = PredictionStore("MARUTI", sector="automobile", base_dir=str(tmp_path))
    cycle_id = store.current_cycle_id()
    env = _make_envelope("MARUTI", cycle_id)
    store.save_envelope(env)

    archived_path = store.archive_envelope()

    assert archived_path is not None
    month = cycle_id.split("_", 1)[1]
    expected = store._dir / "archived_envelopes" / f"{month}_v1.json"
    assert str(expected) == archived_path
    assert expected.exists()

    data = json.loads(expected.read_text(encoding="utf-8"))
    assert data["ticker"] == "MARUTI"
    assert data["cycle_id"] == cycle_id


def test_archive_envelope_creates_v2_on_second_call(tmp_path):
    store = PredictionStore("MARUTI", sector="automobile", base_dir=str(tmp_path))
    cycle_id = store.current_cycle_id()
    env = _make_envelope("MARUTI", cycle_id)
    store.save_envelope(env)

    first = store.archive_envelope()

    # Simulate a regenerated envelope being saved again before the second archive.
    env2 = _make_envelope("MARUTI", cycle_id)
    env2.reforecast_count = 1
    store.save_envelope(env2)

    second = store.archive_envelope()

    month = cycle_id.split("_", 1)[1]
    assert first.endswith(f"{month}_v1.json")
    assert second.endswith(f"{month}_v2.json")
    assert first != second

    archive_dir = store._dir / "archived_envelopes"
    assert (archive_dir / f"{month}_v1.json").exists()
    assert (archive_dir / f"{month}_v2.json").exists()


def test_archive_envelope_missing_returns_none(tmp_path):
    store = PredictionStore("MARUTI", sector="automobile", base_dir=str(tmp_path))

    result = store.archive_envelope()

    assert result is None
    # No archive directory should be created on a no-op.
    assert not (store._dir / "archived_envelopes").exists()


# ---------------------------------------------------------------------------
# Legacy envelope loadability
# ---------------------------------------------------------------------------

def test_legacy_envelope_loads_with_defaulted_reforecast_fields(tmp_path):
    """A minimal legacy dict (no reforecast_count / reforecast_history) must
    still validate, defaulting the new Living Envelope fields."""
    legacy = {
        "ticker": "MARUTI",
        "sector": "automobile",
        "cycle_id": "MARUTI_2026-04",
        "generated_at": "2026-04-01T09:00:00",
        "base_close": 12000.0,
    }

    env = PredictionEnvelope(**legacy)

    assert env.reforecast_count == 0
    assert env.reforecast_history == []


def test_legacy_envelope_file_loads_via_prediction_store(tmp_path):
    store = PredictionStore("MARUTI", sector="automobile", base_dir=str(tmp_path))
    cycle_id = store.current_cycle_id()

    legacy = {
        "ticker": "MARUTI",
        "sector": "automobile",
        "cycle_id": cycle_id,
        "generated_at": "2026-06-01T09:00:00",
        "base_close": 12000.0,
        "daily_forecasts": [],
    }
    store._write_json(store._envelope_path(cycle_id), legacy)

    env = store.load_envelope(cycle_id)

    assert env is not None
    assert env.reforecast_count == 0
    assert env.reforecast_history == []


def test_reforecast_event_round_trip():
    event = ReforecastEvent(
        date="2026-06-05",
        reason="external_shock",
        trigger="direction_wrong_post_cap",
        archived_file="data/predictions/automobile/MARUTI/archived_envelopes/2026-06_v1.json",
    )
    env = _make_envelope("MARUTI", "MARUTI_2026-06")
    env.reforecast_count = 1
    env.reforecast_history.append(event)

    dumped = env.model_dump()
    restored = PredictionEnvelope(**dumped)

    assert restored.reforecast_count == 1
    assert restored.reforecast_history[0].reason == "external_shock"
    assert restored.reforecast_history[0].archived_file.endswith("2026-06_v1.json")

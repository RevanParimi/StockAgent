"""
PredictionStore control-log persistence (spec 2026-06-12, section 2.2).

Mirrors the existing monthly-cycle file pattern (DailyFeedbackLog /
_feedback_log_path / load_feedback_log / save_feedback_log).
"""
from backend.shared.schemas.scorecard import ControlLog, ControlPrediction
from core.intelligence.rl.stores.prediction_store import PredictionStore


def _store(tmp_path):
    return PredictionStore(ticker="TESTX", sector="automobile", base_dir=tmp_path)


def test_control_log_path_pattern(tmp_path):
    store = _store(tmp_path)
    path = store._control_log_path("TESTX_2026-06")
    assert path.name == "TESTX_2026-06_control_log.json"
    assert path.parent == store._dir


def test_load_control_log_absent_returns_empty(tmp_path):
    store = _store(tmp_path)
    log = store.load_control_log("TESTX_2026-06")
    assert isinstance(log, ControlLog)
    assert log.ticker == "TESTX"
    assert log.sector == "automobile"
    assert log.cycle_id == "TESTX_2026-06"
    assert log.entries == []


def test_load_control_log_default_cycle_uses_current(tmp_path):
    store = _store(tmp_path)
    log = store.load_control_log()
    assert log.cycle_id == store.current_cycle_id()


def test_save_then_load_round_trip(tmp_path):
    store = _store(tmp_path)
    cid = "TESTX_2026-06"
    cp = ControlPrediction(date="2026-06-15", made_on="2026-06-14",
                            predicted_direction="UP", confidence=0.6,
                            predicted_close=1500.0, rationale="trend continuation",
                            model="qwen-test")
    log = ControlLog(ticker="TESTX", sector="automobile", cycle_id=cid, entries=[cp])
    store.save_control_log(log)

    loaded = store.load_control_log(cid)
    assert loaded == log
    assert loaded.entries[0].predicted_direction == "UP"


def test_save_control_log_writes_json_file(tmp_path):
    store = _store(tmp_path)
    cid = "TESTX_2026-06"
    log = ControlLog(ticker="TESTX", sector="automobile", cycle_id=cid)
    store.save_control_log(log)
    assert store._control_log_path(cid).exists()


def test_load_control_log_appended_entry_persists(tmp_path):
    store = _store(tmp_path)
    cid = "TESTX_2026-06"
    log = store.load_control_log(cid)
    log.entries.append(ControlPrediction(date="2026-06-15", made_on="2026-06-14",
                                          predicted_direction="DOWN"))
    store.save_control_log(log)

    reloaded = store.load_control_log(cid)
    assert len(reloaded.entries) == 1
    assert reloaded.entries[0].predicted_direction == "DOWN"

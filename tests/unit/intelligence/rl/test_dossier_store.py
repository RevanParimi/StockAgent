from backend.shared.schemas.dossier import TickerDossier
from core.intelligence.rl.stores.prediction_store import PredictionStore


def _store(tmp_path):
    # PredictionStore accepts a base dir override the same way existing store tests
    # construct it — copy the fixture/constructor pattern from
    # tests/integration/test_prediction_store.py and point it at tmp_path.
    return PredictionStore(ticker="TESTX", sector="automobile", base_dir=tmp_path)


def test_load_dossier_returns_none_when_absent(tmp_path):
    assert _store(tmp_path).load_dossier() is None


def test_save_then_load_roundtrip(tmp_path):
    store = _store(tmp_path)
    d = TickerDossier(ticker="TESTX", sector="automobile",
                      created_at="2026-06-11", last_updated="2026-06-11",
                      current_thesis="test thesis")
    store.save_dossier(d)
    loaded = store.load_dossier()
    assert loaded is not None
    assert loaded.current_thesis == "test thesis"
    assert loaded.ticker == "TESTX"


def test_save_stamps_last_updated_today(tmp_path):
    from datetime import date
    store = _store(tmp_path)
    d = TickerDossier(ticker="TESTX", sector="automobile",
                      created_at="2026-01-01", last_updated="2026-01-01")
    store.save_dossier(d)
    assert store.load_dossier().last_updated == date.today().isoformat()

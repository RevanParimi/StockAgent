"""Task 14: weekly dossier distillation hooked into _ledger_cleanup_job.

Covers docs/superpowers/plans/2026-06-11-ticker-dossier.md Task 14 — the
scheduler's weekly ledger-cleanup job must also run distill_dossier() for
each ticker that has a dossier on disk, reusing the per-ticker
PredictionStore the job already constructs for ledger cleanup.
"""
from backend.shared.schemas.dossier import TickerDossier
from core.intelligence.rl.stores.prediction_store import PredictionStore


def test_cleanup_job_distills_dossiers(monkeypatch, tmp_path):
    import services.scheduler.python.scheduler as sched

    # Restrict the job to a single known ticker.
    monkeypatch.setattr(sched, "_active_tickers", lambda: ["MARUTI"])

    # _ledger_cleanup_job constructs PredictionStore(ticker, sector=sector)
    # without base_dir — redirect settings.PREDICTION_DATA_DIR so it lands
    # in tmp_path (same pattern as test_daily_review_dossier.py).
    monkeypatch.setattr(sched.settings, "PREDICTION_DATA_DIR", str(tmp_path))

    # Seed a dossier for MARUTI under automobile (the real repo already has
    # data/predictions/automobile/MARUTI on disk, so _sector_for resolves to
    # "automobile" regardless of PREDICTION_DATA_DIR).
    seed_store = PredictionStore("MARUTI", sector="automobile", base_dir=tmp_path)
    seed_store.save_dossier(TickerDossier(
        ticker="MARUTI", sector="automobile",
        created_at="2026-06-01", last_updated="2026-06-01",
        current_thesis="seed thesis",
    ))

    distilled = []

    import core.intelligence.rl.agents.dossier_curator as dc
    monkeypatch.setattr(dc, "distill_dossier", lambda d: distilled.append(d.ticker) or d)

    scheduler = sched.AutomobileScheduler.__new__(sched.AutomobileScheduler)
    scheduler._ledger_cleanup_job()

    assert distilled == ["MARUTI"]


def test_cleanup_job_skips_ticker_without_dossier(monkeypatch, tmp_path):
    import services.scheduler.python.scheduler as sched

    monkeypatch.setattr(sched, "_active_tickers", lambda: ["MARUTI"])
    monkeypatch.setattr(sched.settings, "PREDICTION_DATA_DIR", str(tmp_path))

    distilled = []
    import core.intelligence.rl.agents.dossier_curator as dc
    monkeypatch.setattr(dc, "distill_dossier", lambda d: distilled.append(d.ticker) or d)

    scheduler = sched.AutomobileScheduler.__new__(sched.AutomobileScheduler)
    scheduler._ledger_cleanup_job()

    assert distilled == []

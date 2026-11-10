"""
SA-009: the writers that minted wrongly-labelled or wrongly-dimensioned
stores now write each ticker's own store with its own sector.

  * the startup self-heal uses the managed sector (the scheduler's store),
    not automobile/<TICKER> for every ticker;
  * PredictionStore stamps its own sector on the objects it creates, not the
    schema default "automobile"; files already on disk keep what they say;
  * the daily review rebuilds a missing weight file from its sector's graph,
    not from the automobile table.

Expected rosters come from each sector's own settings module.
"""
from __future__ import annotations

import json
from datetime import date

from core.intelligence.rl.stores.prediction_store import PredictionStore
from core.schemas.feedback import FeedbackEntry, PredictionEnvelope


def _entry(day: str) -> FeedbackEntry:
    return FeedbackEntry(day=1, date=day, predicted_close=100.0, actual_close=101.0,
                         price_error_pct=1.0, predicted_verdict="BUY", actual_direction="UP",
                         direction_correct=True)


def _stores(root) -> list[str]:
    return sorted(p.relative_to(root).as_posix() for p in root.glob("*/*") if p.is_dir())


# ---------------------------------------------------------------------------
# PredictionStore
# ---------------------------------------------------------------------------

def test_objects_the_store_creates_carry_its_sector(tmp_path):
    store = PredictionStore("RBLBANK", sector="banking_bfsi", base_dir=str(tmp_path))
    assert store.load_feedback_log("RBLBANK_2026-07").sector == "banking_bfsi"
    assert store.load_learning_ledger().sector == "banking_bfsi"

    store.append_feedback_entry(_entry("2026-07-01"), cycle_id="RBLBANK_2026-07")
    store.init_weight_memory({"fundamentals": 0.5, "risk": 0.5})
    store.save_learning_ledger(store.load_learning_ledger())
    d = tmp_path / "banking_bfsi" / "RBLBANK"
    for name in ("RBLBANK_2026-07_daily_feedback_log.json",
                 "RBLBANK_agent_weight_memory.json", "RBLBANK_learning_ledger.json"):
        assert json.loads((d / name).read_text(encoding="utf-8"))["sector"] == "banking_bfsi", name


def test_files_on_disk_keep_the_sector_they_recorded(tmp_path):
    """No silent relabel: a log written with the old default stays as it is,
    so the manifest can still tell a default from a declared sector."""
    d = tmp_path / "banking_bfsi" / "RBLBANK"
    d.mkdir(parents=True)
    (d / "RBLBANK_2026-07_daily_feedback_log.json").write_text(json.dumps(
        {"ticker": "RBLBANK", "sector": "automobile", "cycle_id": "RBLBANK_2026-07",
         "entries": []}), encoding="utf-8")
    store = PredictionStore("RBLBANK", sector="banking_bfsi", base_dir=str(tmp_path))
    store.append_feedback_entry(_entry("2026-07-02"), cycle_id="RBLBANK_2026-07")
    saved = json.loads((d / "RBLBANK_2026-07_daily_feedback_log.json").read_text(encoding="utf-8"))
    assert saved["sector"] == "automobile"
    assert [e["date"] for e in saved["entries"]] == ["2026-07-02"]


def test_a_flat_store_still_leaves_the_schema_default(tmp_path):
    store = PredictionStore("MARUTI", base_dir=str(tmp_path))
    assert store.load_feedback_log("MARUTI_2026-07").sector == "automobile"


# ---------------------------------------------------------------------------
# Startup self-heal
# ---------------------------------------------------------------------------

def test_self_heal_uses_each_tickers_managed_store(tmp_path, monkeypatch):
    import time

    import core.intelligence.rl.stores.prediction_store as ps_mod
    import core.intelligence.rl.workflows.daily_review as dr
    import core.intelligence.rl.workflows.generate_forecast as gf
    import services.api.log_buffer as lb
    import services.api.server as server
    from core.config import settings

    class Day(date):
        @classmethod
        def today(cls):
            return cls(2026, 9, 16)     # mid-month: earlier trading days to backfill

    monkeypatch.setattr(server, "date", Day)
    monkeypatch.setattr(ps_mod, "date", Day)
    monkeypatch.setattr(time, "sleep", lambda s: None)
    monkeypatch.setattr(settings, "PREDICTION_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(server, "_load_self_heal_checkpoint", lambda cycle: set())
    monkeypatch.setattr(server, "_save_self_heal_checkpoint", lambda cycle, done: None)
    monkeypatch.setattr(lb, "get_active_tickers_with_sector", lambda: [
        {"sym": "SUZLON", "sector": "renewable_energy", "cadence": "daily"},
        {"sym": "MARUTI", "sector": "automobile", "cadence": "daily"},
    ])
    forecasts, reviews = [], []

    def fake_forecast(ticker, sector="automobile", paper=False):   # the real default
        forecasts.append((ticker, sector))
        store = PredictionStore(ticker, sector=sector)
        env = PredictionEnvelope(ticker=ticker, sector=sector,
                                 cycle_id=store.current_cycle_id(),
                                 generated_at="2026-09-16", base_close=100.0)
        store.save_envelope(env)
        return env

    def fake_review(ticker, review_date, sector="automobile", paper=False):
        reviews.append((ticker, review_date, sector))
        return {"status": "completed"}

    monkeypatch.setattr(gf, "generate_forecast", fake_forecast)
    monkeypatch.setattr(dr, "run_daily_review", fake_review)

    server._self_heal_rl()

    assert forecasts == [("SUZLON", "renewable_energy"), ("MARUTI", "automobile")]
    assert reviews, "the backfill ran"
    assert {(t, s) for t, _, s in reviews} == {("SUZLON", "renewable_energy"),
                                               ("MARUTI", "automobile")}
    # The invariant: self-heal creates no store outside each ticker's own.
    assert _stores(tmp_path) == ["automobile/MARUTI", "renewable_energy/SUZLON"]


def test_self_heal_skips_a_ticker_whose_own_store_has_the_envelope(tmp_path, monkeypatch):
    import time

    import core.intelligence.rl.stores.prediction_store as ps_mod
    import core.intelligence.rl.workflows.daily_review as dr
    import core.intelligence.rl.workflows.generate_forecast as gf
    import services.api.log_buffer as lb
    import services.api.server as server
    from core.config import settings

    class Day(date):
        @classmethod
        def today(cls):
            return cls(2026, 10, 1)     # the 1st: nothing earlier to backfill

    monkeypatch.setattr(server, "date", Day)
    monkeypatch.setattr(ps_mod, "date", Day)
    monkeypatch.setattr(time, "sleep", lambda s: None)
    monkeypatch.setattr(settings, "PREDICTION_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(server, "_load_self_heal_checkpoint", lambda cycle: set())
    monkeypatch.setattr(server, "_save_self_heal_checkpoint", lambda cycle, done: None)
    monkeypatch.setattr(lb, "get_active_tickers_with_sector", lambda: [
        {"sym": "SUZLON", "sector": "renewable_energy", "cadence": "daily"}])
    # The 09:00 monthly job already wrote October's envelope in the owner's store.
    PredictionStore("SUZLON", sector="renewable_energy").save_envelope(PredictionEnvelope(
        ticker="SUZLON", sector="renewable_energy", cycle_id="SUZLON_2026-10",
        generated_at="2026-10-01", base_close=100.0))
    calls = []
    monkeypatch.setattr(gf, "generate_forecast", lambda *a, **k: calls.append((a, k)))
    monkeypatch.setattr(dr, "run_daily_review", lambda *a, **k: calls.append((a, k)))

    server._self_heal_rl()

    assert calls == []
    assert _stores(tmp_path) == ["renewable_energy/SUZLON"]


# ---------------------------------------------------------------------------
# Daily review weight bootstrap
# ---------------------------------------------------------------------------

def test_review_rebuilds_missing_weights_from_its_sector_roster(tmp_path, monkeypatch):
    import core.intelligence.rl.workflows.daily_review as dr
    from backend.sectors.banking_bfsi.config import settings as banking
    from core.intelligence.rl.agents.feedback_agent import FeedbackAgent
    from tests.unit.intelligence.rl.test_shock_path import (
        REVIEW_DATE, _fb_output, _make_envelope, _patch_common,
    )

    dims = sorted(banking.AGENT_WEIGHTS)
    store = PredictionStore("RBLBANK", sector="banking_bfsi", base_dir=str(tmp_path))
    env = _make_envelope("RBLBANK")
    env.sector = "banking_bfsi"
    for row in env.daily_forecasts:
        row.predicted_agent_scores = {d: 0.5 for d in dims}
    store.save_envelope(env)
    assert store.load_weight_memory() is None          # missing, e.g. deleted or unreadable

    _patch_common(dr, monkeypatch, tmp_path, actual_close=98.0)
    monkeypatch.setattr(dr, "_run_todays_agent_scores", lambda *a, **k: {d: 0.5 for d in dims})
    monkeypatch.setattr(FeedbackAgent, "run",
                        lambda self, fb_input, ledger: _fb_output("model_bias", "risk"))

    summary = dr.run_daily_review("RBLBANK", REVIEW_DATE, sector="banking_bfsi")

    assert summary["status"] == "completed"
    d = tmp_path / "banking_bfsi" / "RBLBANK"
    saved = json.loads((d / "RBLBANK_agent_weight_memory.json").read_text(encoding="utf-8"))
    assert sorted(saved["base_weights"]) == dims
    assert sorted(saved["current_weights"]) == dims
    assert saved["sector"] == "banking_bfsi"
    log = json.loads((d / f"{env.cycle_id}_daily_feedback_log.json").read_text(encoding="utf-8"))
    assert log["sector"] == "banking_bfsi"
    assert not (tmp_path / "automobile").exists()


def test_paper_review_revises_with_its_sector_roster(tmp_path, monkeypatch):
    """The in-memory weights of a paper review without a weight file (the
    SA-039 review's reproduction, routed to SA-026): Step 7b re-weighted a
    pharma idea's rows with the automobile agents, so every lookup fell back
    to 0.5. Now it uses the graph the sector runs (generic)."""
    import core.intelligence.rl.workflows.daily_review as dr
    from core.config import settings
    from core.intelligence.rl import learning_mode as lm
    from tests.unit.intelligence.rl import test_paper_lane_isolation as pl

    lm._warned.clear()
    monkeypatch.setattr(settings, "RL_LEARNING_MODE", "adapt")
    real_root, paper_root = tmp_path / "real", tmp_path / "paper"
    real_root.mkdir()
    monkeypatch.setattr(settings, "PREDICTION_DATA_DIR", str(real_root))
    monkeypatch.setattr(settings, "PAPER_PREDICTION_DATA_DIR", str(paper_root))
    pl._patch_common(dr, monkeypatch)
    PredictionStore(pl.TICKER, sector=pl.SECTOR, base_dir=str(paper_root)).save_envelope(
        pl._make_envelope())
    seen = []
    monkeypatch.setattr(dr, "_revise_remaining_forecasts",
                        lambda **kw: seen.append(sorted(kw["new_weights"])))

    summary = dr.run_daily_review(pl.TICKER, pl.REVIEW_DATE, sector=pl.SECTOR, paper=True)

    assert summary["status"] == "completed"
    assert seen == [sorted(settings.GENERIC_AGENT_WEIGHTS)]
    assert list(paper_root.rglob("*_agent_weight_memory.json")) == []

"""tests/unit/test_job_outcomes.py — AUD-090d last-run-outcome surface."""
import services.data.stores.job_outcomes as jo


def test_record_and_load_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr(jo, "_OUTCOMES_PATH", tmp_path / "outcomes.json")
    jo.record_job_outcome("daily_review", produced=13, expected=16,
                          stragglers=["TCS"], pipeline_ok=True)
    data = jo.load_job_outcomes()
    assert data["daily_review"]["produced"] == 13
    assert data["daily_review"]["stragglers"] == ["TCS"]
    assert data["daily_review"]["finished_at"]           # stamped


def test_record_overwrites_same_job_keeps_others(tmp_path, monkeypatch):
    monkeypatch.setattr(jo, "_OUTCOMES_PATH", tmp_path / "outcomes.json")
    jo.record_job_outcome("daily_review", produced=1)
    jo.record_job_outcome("weekly_review", produced=2)
    jo.record_job_outcome("daily_review", produced=3)
    data = jo.load_job_outcomes()
    assert data["daily_review"]["produced"] == 3
    assert data["weekly_review"]["produced"] == 2


def test_load_missing_or_corrupt_is_empty(tmp_path, monkeypatch):
    monkeypatch.setattr(jo, "_OUTCOMES_PATH", tmp_path / "outcomes.json")
    assert jo.load_job_outcomes() == {}
    (tmp_path / "outcomes.json").write_text("{torn", encoding="utf-8")
    assert jo.load_job_outcomes() == {}


def test_record_never_raises(tmp_path, monkeypatch):
    monkeypatch.setattr(jo, "_OUTCOMES_PATH", tmp_path)   # a DIRECTORY — write fails
    jo.record_job_outcome("daily_review", produced=1)     # must not raise


def test_scheduler_status_includes_last_runs(monkeypatch):
    import asyncio
    import services.api.routes.scheduler_api as sched_api
    monkeypatch.setattr(sched_api, "_resolve_tickers", lambda t: [])
    monkeypatch.setattr(
        "services.data.stores.job_outcomes.load_job_outcomes",
        lambda: {"daily_review": {"produced": 16, "expected": 16}},
    )
    out = asyncio.run(sched_api.scheduler_status(x_scheduler_key=None))
    assert out["last_runs"]["daily_review"]["produced"] == 16

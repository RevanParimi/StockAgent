from unittest.mock import patch

from fastapi.testclient import TestClient

import services.api.routes.audit_api as aapi


def _client():
    from fastapi import FastAPI
    app = FastAPI()
    app.include_router(aapi.router)
    app.dependency_overrides[aapi.get_current_user_or_machine] = lambda: {"user_id": "primary"}
    app.dependency_overrides[aapi.require_owner] = lambda: {"user_id": "primary"}
    return TestClient(app)


def test_summary_on_empty_store_is_insufficient_not_zero():
    with patch.object(aapi, "build_report",
                      return_value={"verdict": "INSUFFICIENT_DATA", "total_rows": 0}):
        resp = _client().get("/audit/summary")
    assert resp.status_code == 200
    assert resp.json()["verdict"] == "INSUFFICIENT_DATA"


def test_backfill_returns_counts_not_a_bare_200():
    with patch.object(aapi, "grade_due",
                      return_value={"graded": 12, "skipped_unpriceable": 1,
                                    "already_present": 3, "lanes": {}}):
        resp = _client().post("/audit/backfill")
    body = resp.json()
    assert resp.status_code == 200
    assert body["graded"] == 12 and body["skipped_unpriceable"] == 1
    assert body["already_present"] == 3


def test_backfill_refuses_to_run_concurrently():
    aapi._BACKFILL_RUNNING.set()
    try:
        resp = _client().post("/audit/backfill")
    finally:
        aapi._BACKFILL_RUNNING.clear()
    assert resp.status_code == 409


def test_backfill_clears_its_guard_even_on_failure():
    with patch.object(aapi, "grade_due", side_effect=RuntimeError("boom")):
        resp = _client().post("/audit/backfill")
    assert resp.status_code == 500
    assert not aapi._BACKFILL_RUNNING.is_set()

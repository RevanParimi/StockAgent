"""Compass Phase C — /delivery/* routes."""
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

import services.api.routes.delivery_api as dapi

_SUB = {"endpoint": "https://push.example/abc", "keys": {"p256dh": "k", "auth": "a"}}


def _client():
    app = FastAPI()
    app.include_router(dapi.router)
    return TestClient(app)


def test_brief_latest_404_then_200(monkeypatch, tmp_path):
    monkeypatch.setattr(dapi.settings, "PORTFOLIO_DATA_DIR", str(tmp_path))
    c = _client()
    assert c.get("/delivery/brief/latest").status_code == 404
    from core.portfolio.store import PortfolioStore
    PortfolioStore(base_dir=str(tmp_path)).save_brief(
        {"date": "2026-07-09", "kind": "morning_brief", "headline": "h"})
    resp = c.get("/delivery/brief/latest")
    assert resp.status_code == 200 and resp.json()["date"] == "2026-07-09"


def test_weekly_latest_404(monkeypatch, tmp_path):
    monkeypatch.setattr(dapi.settings, "PORTFOLIO_DATA_DIR", str(tmp_path))
    assert _client().get("/delivery/weekly/latest").status_code == 404


def test_run_brief_202_background():
    with patch.object(dapi, "run_morning_brief") as m:
        resp = _client().post("/delivery/run-brief")
    assert resp.status_code == 202
    assert m.called                       # TestClient runs background tasks inline


def test_run_weekly_202_background():
    with patch.object(dapi, "run_weekly_review") as m:
        resp = _client().post("/delivery/run-weekly")
    assert resp.status_code == 202 and m.called


def test_alerts_tail():
    with patch.object(dapi, "load_recent_alerts",
                      return_value=[{"kind": "shelf_add"}]) as m:
        resp = _client().get("/delivery/alerts?limit=5")
    assert resp.status_code == 200 and resp.json()["alerts"] == [{"kind": "shelf_add"}]
    assert m.call_args.kwargs.get("limit") == 5 or m.call_args.args[0] == 5


def test_push_public_key(monkeypatch):
    monkeypatch.setattr(dapi.settings, "VAPID_PUBLIC_KEY", "pubkey123")
    resp = _client().get("/delivery/push/public-key")
    assert resp.json() == {"public_key": "pubkey123"}


def test_push_subscribe_and_unsubscribe(monkeypatch, tmp_path):
    monkeypatch.setattr(dapi.settings, "DELIVERY_DATA_DIR", str(tmp_path))
    c = _client()
    resp = c.post("/delivery/push/subscribe", json=_SUB)
    assert resp.status_code == 200 and resp.json()["subscriptions"] == 1
    assert c.post("/delivery/push/subscribe", json={}).status_code == 422
    resp = c.delete("/delivery/push/subscribe",
                    params={"endpoint": _SUB["endpoint"]})
    assert resp.json()["removed"] is True


def test_auth_enforced_when_key_set(monkeypatch, tmp_path):
    monkeypatch.setattr(dapi.settings, "PORTFOLIO_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("SCHEDULER_KEY", "sekret")
    c = _client()
    assert c.get("/delivery/brief/latest").status_code == 403
    assert c.get("/delivery/brief/latest",
                 headers={"X-Scheduler-Key": "sekret"}).status_code in (200, 404)

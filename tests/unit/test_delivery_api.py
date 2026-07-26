"""Compass Phase C — /delivery/* routes."""
from datetime import date
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
        resp = _client().post("/delivery/run-brief?on=2026-07-08")
    assert resp.status_code == 202
    assert m.called                       # TestClient runs background tasks inline
    assert m.call_args.args[0] == date(2026, 7, 8)


def test_run_weekly_202_background():
    with patch.object(dapi, "run_weekly_review") as m:
        resp = _client().post("/delivery/run-weekly?on=2026-07-09")
    assert resp.status_code == 202
    assert m.called
    assert m.call_args.args[0] == date(2026, 7, 9)


def test_push_subscribe_rejects_non_https_endpoint(monkeypatch, tmp_path):
    monkeypatch.setattr(dapi.settings, "DELIVERY_DATA_DIR", str(tmp_path), raising=False)
    c = _client()
    assert c.post("/delivery/push/subscribe",
                  json={"endpoint": "http://evil.example/x"}).status_code == 422
    assert c.post("/delivery/push/subscribe",
                  json={"endpoint": 123}).status_code == 422


def test_push_subscribe_caps_store_size(monkeypatch, tmp_path):
    monkeypatch.setattr(dapi.settings, "DELIVERY_DATA_DIR", str(tmp_path), raising=False)
    from core.delivery.channels import PushStore
    store = PushStore(path=str(tmp_path / "push_subscriptions.json"))
    for i in range(50):
        store.add({"endpoint": f"https://push.example/{i}"})
    with patch.object(dapi, "PushStore", lambda: store):
        c = _client()
        resp = c.post("/delivery/push/subscribe",
                      json={"endpoint": "https://push.example/one-too-many"})
    assert resp.status_code == 429


def test_run_brief_rejects_malformed_on():
    c = _client()
    resp = c.post("/delivery/run-brief?on=garbage")
    assert resp.status_code == 422


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


def test_auth_enforced_when_auth_required(monkeypatch, tmp_path):
    # M0.1: brief reads need a logged-in user (session), not the key.
    monkeypatch.setattr(dapi.settings, "PORTFOLIO_DATA_DIR", str(tmp_path))
    from core.config import settings
    monkeypatch.setattr(settings, "AUTH_REQUIRED", True, raising=False)
    c = _client()
    assert c.get("/delivery/brief/latest").status_code == 401
    # single-user mode (AUTH_REQUIRED=false): anonymous = owner → 200/404
    monkeypatch.setattr(settings, "AUTH_REQUIRED", False, raising=False)
    assert c.get("/delivery/brief/latest").status_code in (200, 404)


def test_brief_latest_format_text(monkeypatch, tmp_path):
    monkeypatch.setattr(dapi.settings, "PORTFOLIO_DATA_DIR", str(tmp_path))
    from core.portfolio.store import PortfolioStore
    PortfolioStore(base_dir=str(tmp_path)).save_brief(
        {"date": "2026-07-22", "kind": "morning_brief", "headline": "Calm open."})
    resp = _client().get("/delivery/brief/latest?format=text")
    assert resp.status_code == 200
    body = resp.json()
    assert body["date"] == "2026-07-22"
    assert body["text"].startswith("Morning brief — 2026-07-22")


def test_weekly_latest_format_text(monkeypatch, tmp_path):
    monkeypatch.setattr(dapi.settings, "PORTFOLIO_DATA_DIR", str(tmp_path))
    from core.portfolio.store import PortfolioStore
    PortfolioStore(base_dir=str(tmp_path)).save_weekly(
        {"date": "2026-07-20", "kind": "weekly_review"})
    resp = _client().get("/delivery/weekly/latest?format=text")
    assert resp.status_code == 200
    assert resp.json()["text"].startswith("Weekly review — 2026-07-20")

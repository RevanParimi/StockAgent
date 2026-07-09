"""Compass Phase B — /discovery routes."""
from fastapi.testclient import TestClient

import pytest

from services.api.server import app
import services.api.routes.discovery_api as dapi
from backend.shared.schemas.discovery import (
    DiscoveryCandidate, ScreenResult, Shelf, ShelfIdea,
)

client = TestClient(app)


def _shelf():
    return Shelf(ideas=[ShelfIdea(symbol="AAA", sector="pharma", added="2026-07-04",
                                  conviction=0.7)])


def test_get_shelf(monkeypatch):
    class _S:
        def load(self):
            return _shelf()
    monkeypatch.setattr(dapi, "ShelfStore", _S)
    resp = client.get("/discovery/shelf")
    assert resp.status_code == 200
    assert resp.json()["ideas"][0]["symbol"] == "AAA"


def test_get_latest_screen_404_when_empty(monkeypatch):
    monkeypatch.setattr(dapi, "load_latest_screen", lambda: None)
    assert client.get("/discovery/screen/latest").status_code == 404


def test_get_latest_screen(monkeypatch):
    result = ScreenResult(screen_date="2026-07-03", universe_size=1500,
                          shortlist_size=80,
                          candidates=[DiscoveryCandidate(symbol="AAA", close=100.0,
                                                         composite=0.9)],
                          dark_signals=["mf_holding"])
    monkeypatch.setattr(dapi, "load_latest_screen", lambda: result)
    body = client.get("/discovery/screen/latest").json()
    assert body["screen_date"] == "2026-07-03"
    assert body["dark_signals"] == ["mf_holding"]


def test_post_run_returns_202(monkeypatch):
    monkeypatch.setattr(dapi, "run_discovery_cycle", lambda on=None: {"ok": True})
    resp = client.post("/discovery/run")
    assert resp.status_code == 202


def test_promote_route(monkeypatch):
    class _S:
        def promote(self, symbol, user_id=None):
            return {"status": "promoted", "symbol": symbol}
    monkeypatch.setattr(dapi, "ShelfStore", _S)
    resp = client.post("/discovery/shelf/aaa/promote")
    assert resp.status_code == 200
    assert resp.json()["symbol"] == "AAA"


def test_promote_404_when_not_on_shelf(monkeypatch):
    class _S:
        def promote(self, symbol, user_id=None):
            return {"status": "not_on_shelf", "symbol": symbol}
    monkeypatch.setattr(dapi, "ShelfStore", _S)
    assert client.post("/discovery/shelf/nope/promote").status_code == 404


def test_delete_shelf_idea(monkeypatch):
    class _S:
        def drop(self, symbol, reason="manual"):
            return symbol == "AAA"
    monkeypatch.setattr(dapi, "ShelfStore", _S)
    assert client.delete("/discovery/shelf/AAA").status_code == 200
    assert client.delete("/discovery/shelf/BBB").status_code == 404

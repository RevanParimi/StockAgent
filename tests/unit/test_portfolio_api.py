"""Compass Phase A — portfolio REST surface (isolated app, no full server)."""
from datetime import date

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import services.api.routes.portfolio_api as papi
from backend.shared.schemas.portfolio import Holding
from core.portfolio.store import PortfolioStore


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(papi.settings, "PORTFOLIO_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(papi, "close_on", lambda sym, d: 12000.0)
    monkeypatch.setattr(papi, "promote_symbol",
                        lambda symbol, sector, origin: {"status": "promoted", "symbol": symbol})
    monkeypatch.setattr(papi, "demote_symbol", lambda symbol: True)
    app = FastAPI()
    app.include_router(papi.router)
    return TestClient(app)


def test_add_holding_prices_at_close(client, tmp_path):
    resp = client.post("/portfolio/holdings", json={
        "symbol": "MARUTI", "sector": "automobile", "qty": 10, "buy_date": "2026-07-01",
    })
    assert resp.status_code == 200
    body = resp.json()
    assert body["holding"]["avg_buy_price"] == 12000.0
    assert body["holding"]["virtual"] is True
    assert body["promotion"]["status"] == "promoted"


def test_add_holding_unsupported_sector_422(client, monkeypatch):
    monkeypatch.setattr(
        papi, "promote_symbol",
        lambda symbol, sector, origin: {"status": "unsupported_sector",
                                         "detail": "sector not yet supported"},
    )
    resp = client.post("/portfolio/holdings", json={
        "symbol": "SUNPHARMA", "sector": "pharma", "qty": 5, "buy_date": "2026-07-01",
    })
    assert resp.status_code == 422
    assert "not yet supported" in resp.json()["detail"]


def test_get_portfolio_marks_to_market(client):
    client.post("/portfolio/holdings", json={
        "symbol": "MARUTI", "sector": "automobile", "qty": 10,
        "buy_date": "2026-07-01", "price": 10000.0,
    })
    resp = client.get("/portfolio")
    assert resp.status_code == 200
    row = resp.json()["holdings"][0]
    assert row["last_close"] == 12000.0
    assert row["pnl_pct"] == pytest.approx(20.0)


def test_delete_holding(client):
    client.post("/portfolio/holdings", json={
        "symbol": "MARUTI", "sector": "automobile", "qty": 10,
        "buy_date": "2026-07-01", "price": 10000.0,
    })
    assert client.delete("/portfolio/holdings/MARUTI").status_code == 200
    assert client.delete("/portfolio/holdings/MARUTI").status_code == 404


def test_watchlist_roundtrip(client):
    resp = client.post("/portfolio/watchlist", json={
        "symbol": "TCS", "sector": "it_sector", "reason": "quality compounder",
    })
    assert resp.status_code == 200
    assert client.get("/portfolio").json()["watchlist"][0]["symbol"] == "TCS"
    assert client.delete("/portfolio/watchlist/TCS").status_code == 200


def test_import_csv(client):
    csv_text = (
        "symbol,sector,qty,avg_buy_price,buy_date\n"
        "MARUTI,automobile,10,11000,2026-01-05\n"
    )
    resp = client.post("/portfolio/import-csv", content=csv_text,
                       headers={"Content-Type": "text/csv"})
    assert resp.status_code == 200
    assert resp.json()["imported"] == 1


def test_advice_and_digest_empty_ok(client):
    assert client.get("/portfolio/advice").json()["records"] == []
    assert client.get("/portfolio/digest/latest").status_code == 404


def test_run_advisor_returns_202(client, monkeypatch):
    monkeypatch.setattr(papi, "run_post_review_pipeline", lambda d: {"status": "completed"})
    resp = client.post("/portfolio/run-advisor")
    assert resp.status_code == 202


def test_add_holding_bad_date_422(client):
    resp = client.post("/portfolio/holdings", json={
        "symbol": "MARUTI", "sector": "automobile", "qty": 10, "buy_date": "07/01/2026",
    })
    assert resp.status_code == 422
    assert "Invalid buy_date" in resp.json()["detail"]


def test_run_advisor_bad_date_422(client):
    resp = client.post("/portfolio/run-advisor?review_date=notadate")
    assert resp.status_code == 422

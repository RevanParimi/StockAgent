"""Inbox deep-links — EOD digest text renderer."""
from core.portfolio.digest_text import render_digest_text


def _digest():
    return {"date": "2026-07-22", "portfolio_value": 110000.0,
            "total_pnl_pct": 10.0,
            "holdings": [
                {"symbol": "OLDCO", "verdict": "EXIT", "reason": "stop breached"},
                {"symbol": "GOODCO", "verdict": "HOLD", "reason": "thesis intact"},
            ],
            "escalations": ["OLDCO"]}


def test_render_digest_text_sections():
    text = render_digest_text(_digest())
    lines = text.splitlines()
    assert lines[0] == "EOD digest — 2026-07-22"
    assert any("110,000" in l for l in lines)
    assert any(l.startswith("EXIT: OLDCO") for l in lines)
    assert "Escalations: OLDCO" in lines


def test_render_digest_text_minimal():
    assert render_digest_text({"date": "2026-07-22"}) == "EOD digest — 2026-07-22"


def test_digest_latest_format_text(monkeypatch, tmp_path):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    import services.api.routes.portfolio_api as papi
    from core.config import settings
    from core.portfolio.store import PortfolioStore
    monkeypatch.setattr(settings, "PORTFOLIO_DATA_DIR", str(tmp_path))
    PortfolioStore(base_dir=str(tmp_path)).save_digest(_digest())
    app = FastAPI(); app.include_router(papi.router)
    resp = TestClient(app).get("/portfolio/digest/latest?format=text")
    assert resp.status_code == 200
    assert resp.json()["text"].startswith("EOD digest — 2026-07-22")

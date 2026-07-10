"""Compass Phase C — chat 'brief' command (spec §7: renders the latest anytime)."""
import asyncio

from core.config import settings
from core.portfolio.store import PortfolioStore
from services.api.routes.ui_data import _CHAT_TOOLS, _dispatch_chat_tool


def _dispatch(name, args):
    return asyncio.run(_dispatch_chat_tool(name, args))


def test_tool_registered():
    names = [t["function"]["name"] for t in _CHAT_TOOLS]
    assert "get_portfolio_brief" in names


def test_returns_rendered_brief(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "PORTFOLIO_DATA_DIR", str(tmp_path))
    PortfolioStore(base_dir=str(tmp_path)).save_brief({
        "date": "2026-07-09", "kind": "morning_brief",
        "headline": "Markets calm; no flags.",
        "portfolio": {"portfolio_value": 110000.0, "total_pnl_pct": 10.0},
        "advisor_flags": [], "overnight": [], "earnings_soon": [],
        "discovery_adds": [], "ipo_watch": [], "lockin_flags": [], "regime": None,
    })
    out = _dispatch("get_portfolio_brief", {})
    assert "Markets calm; no flags." in out and "2026-07-09" in out


def test_falls_back_to_digest_then_helpful_message(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "PORTFOLIO_DATA_DIR", str(tmp_path))
    out = _dispatch("get_portfolio_brief", {})
    assert "No brief yet" in out
    PortfolioStore(base_dir=str(tmp_path)).save_digest({
        "date": "2026-07-08", "user_id": "primary", "portfolio_value": 90000.0,
        "total_pnl_pct": -2.0,
        "holdings": [{"symbol": "OLDCO", "verdict": "EXIT", "pnl_pct": -15.0,
                      "close": 80.0, "reason": "stop", "notes": []}],
        "escalations": ["OLDCO"]})
    out = _dispatch("get_portfolio_brief", {})
    assert "OLDCO" in out and "EXIT" in out

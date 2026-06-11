"""Task 15: chat get_ticker_dossier tool + RL insight bug fixes.

Covers docs/superpowers/plans/2026-06-11-ticker-dossier.md Task 15:
- _chat_tool_ticker_dossier(ticker) renders the ticker dossier digest.
- _dispatch_chat_tool routes "get_ticker_dossier" to it.
- _sector_for_ticker resolves sector via managed tickers, then directory scan,
  falling back to "automobile".
"""
import asyncio
import json


def test_dossier_tool_reads_digest(tmp_path, monkeypatch):
    import services.api.routes.ui_data as ui
    sector_dir = tmp_path / "automobile" / "MARUTI"
    sector_dir.mkdir(parents=True)
    dossier = {"ticker": "MARUTI", "sector": "automobile",
               "created_at": "2026-06-01", "last_updated": "2026-06-11",
               "current_thesis": "BUY on rural recovery"}
    (sector_dir / "MARUTI_dossier.json").write_text(json.dumps(dossier), encoding="utf-8")
    monkeypatch.setattr(ui, "_PREDICTIONS_DIR", tmp_path)
    out = asyncio.run(ui._chat_tool_ticker_dossier("maruti"))
    assert "MARUTI dossier" in out
    assert "rural recovery" in out


def test_dossier_tool_empty_when_missing(tmp_path, monkeypatch):
    import services.api.routes.ui_data as ui
    monkeypatch.setattr(ui, "_PREDICTIONS_DIR", tmp_path)
    assert asyncio.run(ui._chat_tool_ticker_dossier("GHOST")) == ""


def test_dispatch_routes_dossier_tool(monkeypatch):
    import services.api.routes.ui_data as ui

    async def fake(t):
        return f"DOSSIER:{t}"

    monkeypatch.setattr(ui, "_chat_tool_ticker_dossier", fake)
    out = asyncio.run(ui._dispatch_chat_tool("get_ticker_dossier", {"ticker": "TCS"}))
    assert out == "DOSSIER:TCS"


def test_sector_resolution_helper(monkeypatch, tmp_path):
    import services.api.routes.ui_data as ui
    (tmp_path / "banking_bfsi" / "HDFCBANK").mkdir(parents=True)
    monkeypatch.setattr(ui, "_PREDICTIONS_DIR", tmp_path)
    monkeypatch.setattr(ui, "_load_mt", lambda: [])  # force directory-scan fallback
    assert ui._sector_for_ticker("HDFCBANK") == "banking_bfsi"
    assert ui._sector_for_ticker("UNKNOWN") == "automobile"


def test_sector_resolution_uses_managed_tickers(monkeypatch, tmp_path):
    import services.api.routes.ui_data as ui
    monkeypatch.setattr(ui, "_PREDICTIONS_DIR", tmp_path)
    monkeypatch.setattr(ui, "_load_mt", lambda: [{"sym": "MARUTI", "sector": "automobile"}])
    assert ui._sector_for_ticker("maruti") == "automobile"

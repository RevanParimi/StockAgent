"""Compass Phase C — morning brief: assembly, rendering, run gating (spec §7)."""
from datetime import date
from unittest.mock import patch

import core.delivery.brief as br
from core.portfolio.store import PortfolioStore


def _digest():
    return {"date": "2026-07-08", "user_id": "u1", "portfolio_value": 110000.0,
            "cost_basis": 100000.0, "total_pnl_pct": 10.0,
            "holdings": [
                {"symbol": "OLDCO", "verdict": "EXIT", "close": 80.0,
                 "pnl_pct": -15.0, "reason": "stop breached", "notes": []},
                {"symbol": "GOODCO", "verdict": "HOLD", "close": 210.0,
                 "pnl_pct": 22.0, "reason": "thesis intact", "notes": []},
            ],
            "escalations": ["OLDCO"]}


def _mk_store(tmp_path, with_digest=True):
    store = PortfolioStore(user_id="u1", base_dir=str(tmp_path))
    if with_digest:
        store.save_digest(_digest())
    return store


def test_build_brief_assembles_sections(tmp_path, monkeypatch):
    store = _mk_store(tmp_path)
    monkeypatch.setattr(br, "_narrate_brief", lambda b: "Deterministic headline.")
    monkeypatch.setattr(br, "_read_regime", lambda: {"label": "RISK_OFF"})
    monkeypatch.setattr(br, "_overnight_items", lambda: [
        {"headline": "Fed shock", "severity": "HIGH"}])
    monkeypatch.setattr(br, "_shelf_events_since", lambda since: [
        {"event": "added", "symbol": "NEWCO", "detail": "conviction=0.72"}])
    monkeypatch.setattr(br, "_earnings_soon", lambda symbols, on: [
        {"symbol": "GOODCO", "date": "2026-07-10"}])
    monkeypatch.setattr(br, "_ipo_watch", lambda: [
        {"symbol": "SOON", "company": "Soon Ltd", "status": "upcoming"}])
    monkeypatch.setattr(br, "upcoming_lockin_alerts", lambda on, symbols=None: [])

    brief = br.build_morning_brief("u1", date(2026, 7, 9), store=store)
    assert brief["kind"] == "morning_brief" and brief["date"] == "2026-07-09"
    assert brief["portfolio"]["total_pnl_pct"] == 10.0
    assert brief["advisor_flags"] == [
        {"symbol": "OLDCO", "verdict": "EXIT", "reason": "stop breached", "notes": []}]
    assert brief["regime"]["label"] == "RISK_OFF"
    assert brief["overnight"][0]["headline"] == "Fed shock"
    assert brief["discovery_adds"][0]["symbol"] == "NEWCO"
    assert brief["earnings_soon"][0]["symbol"] == "GOODCO"
    assert brief["headline"] == "Deterministic headline."

    text = br.render_brief_text(brief)
    for token in ("Deterministic headline.", "OLDCO", "EXIT", "RISK_OFF", "NEWCO"):
        assert token in text


def test_build_brief_survives_missing_everything(tmp_path, monkeypatch):
    store = _mk_store(tmp_path, with_digest=False)
    monkeypatch.setattr(br, "_narrate_brief", lambda b: "h")
    brief = br.build_morning_brief("u1", date(2026, 7, 9), store=store)
    assert brief["portfolio"] is None and brief["advisor_flags"] == []
    assert isinstance(br.render_brief_text(brief), str)


def test_run_skips_non_trading_day(monkeypatch):
    monkeypatch.setattr(br, "is_trading_day", lambda d: False)
    out = br.run_morning_brief(on=date(2026, 7, 12))
    assert out == {"status": "not_trading_day"}


def test_run_builds_saves_delivers(tmp_path, monkeypatch):
    monkeypatch.setattr(br, "is_trading_day", lambda d: True)
    monkeypatch.setattr(br, "list_user_ids", lambda: ["u1"])
    monkeypatch.setattr(br.settings, "PORTFOLIO_DATA_DIR", str(tmp_path))
    _mk_store(tmp_path)
    monkeypatch.setattr(br, "_narrate_brief", lambda b: "h")
    monkeypatch.setattr(br, "upcoming_lockin_alerts",
                        lambda on, symbols=None: [])
    with patch.object(br, "deliver", return_value={"delivered": True}) as m:
        out = br.run_morning_brief(on=date(2026, 7, 9))
    assert out["status"] == "completed" and out["users"] == 1
    assert m.call_count == 1
    saved = PortfolioStore(user_id="u1", base_dir=str(tmp_path)).load_latest_brief()
    assert saved and saved["date"] == "2026-07-09"

"""Compass Phase C — weekly review: allocation, laggards, scoreboard (spec §7)."""
from datetime import date

import pytest

import core.delivery.brief as brief_mod
import core.delivery.weekly as wk
from backend.shared.schemas.portfolio import AdviceRecord, Holding
from core.portfolio.store import PortfolioStore


@pytest.fixture(autouse=True)
def _isolated_ipo_ledger(tmp_path, monkeypatch):
    """build_weekly_review() unconditionally calls _safe_weekly_ipos() ->
    _weekly_ipos() -> core.delivery.brief._ipo_watch(), which (since the
    P2 ledger load-once fix) constructs the IPO signal ledger via
    core.delivery.brief._ipo_signal_store(). Same isolation rationale as the
    fixture of the same name in test_delivery_brief.py: no test may reach
    the repo's real data/ipo/ path, ever, by accident."""
    from core.ipo.signals import IpoSignalStore
    store = IpoSignalStore(base_dir=str(tmp_path / "ipo_ledger"))
    monkeypatch.setattr(brief_mod, "_ipo_signal_store", lambda: store)
    return store


def _store(tmp_path):
    store = PortfolioStore(user_id="u1", base_dir=str(tmp_path))
    p = store.load()
    p.holdings = [
        Holding(symbol="WINCO", sector="it_sector", qty=10, avg_buy_price=100.0,
                adj_avg_price=100.0, adj_qty=10, buy_date="2026-03-02"),
        Holding(symbol="LAGCO", sector="automobile", qty=10, avg_buy_price=200.0,
                adj_avg_price=200.0, adj_qty=10, buy_date="2026-03-02"),
    ]
    store.save(p)
    # 20-day-old EXIT advice at close 100; latest close 80 -> correct call
    store.append_advice(AdviceRecord(
        date="2026-06-15", user_id="u1", symbol="LAGCO", verdict="EXIT",
        close=100.0, unrealised_pnl_pct=-10.0, stop_pct=12.0))
    return store


def _closes():
    return {"WINCO": 130.0, "LAGCO": 80.0}


def test_build_weekly_sections(tmp_path, monkeypatch):
    store = _store(tmp_path)
    monkeypatch.setattr(wk, "_narrate_weekly", lambda r: "Weekly headline.")
    monkeypatch.setattr(wk, "_latest_closes", lambda symbols, on: _closes())
    monkeypatch.setattr(wk, "_active_shelf_ideas", lambda: [])
    review = wk.build_weekly_review("u1", date(2026, 7, 5), store=store)

    alloc = {a["sector"]: a["weight_pct"] for a in review["allocation"]}
    assert abs(alloc["it_sector"] - 61.90) < 0.1      # 1300 / 2100 (market value)
    assert abs(alloc["automobile"] - 38.10) < 0.1     # 800 / 2100
    # both above the 30% warn threshold; allocation is sorted by weight desc
    assert review["concentration_flags"] == ["it_sector", "automobile"]
    assert review["laggards"][0]["symbol"] == "LAGCO"
    assert review["laggards"][0]["pnl_pct"] == -60.0
    sb = review["scoreboard"]
    assert sb["counts"]["EXIT"] == 1
    assert sb["checked"] == 1 and sb["correct"] == 1  # price fell after EXIT
    assert review["headline"] == "Weekly headline."
    text = wk.render_weekly_text(review)
    assert "LAGCO" in text and "Weekly headline." in text


def test_switch_candidates_only_underweight_sectors(tmp_path, monkeypatch):
    store = _store(tmp_path)
    monkeypatch.setattr(wk, "_narrate_weekly", lambda r: "h")
    monkeypatch.setattr(wk, "_latest_closes", lambda symbols, on: _closes())

    class _Idea:
        def __init__(self, symbol, sector, conviction):
            self.symbol, self.sector, self.conviction = symbol, sector, conviction
            self.status, self.thesis = "active", "t"
    monkeypatch.setattr(wk, "_active_shelf_ideas", lambda: [
        _Idea("PHARMCO", "pharma", 0.8),          # 0% weight -> underweight, offered
        _Idea("ITCO", "it_sector", 0.9),          # largest sector (61.9%) -> not offered
    ])
    review = wk.build_weekly_review("u1", date(2026, 7, 5), store=store)
    assert [c["symbol"] for c in review["switch_candidates"]] == ["PHARMCO"]


def test_switch_suggestions_from_advice_ledger(tmp_path, monkeypatch):
    store = _store(tmp_path)
    # advisor issued "EXIT WINCO -> NEWCO" during the week (SWITCH verdict)
    store.append_advice(AdviceRecord(
        date="2026-06-20", user_id="u1", symbol="WINCO", verdict="SWITCH",
        close=100.0, unrealised_pnl_pct=5.0, stop_pct=12.0,
        switch_candidate="NEWCO"))
    monkeypatch.setattr(wk, "_narrate_weekly", lambda r: "h")
    monkeypatch.setattr(wk, "_latest_closes", lambda symbols, on: _closes())
    monkeypatch.setattr(wk, "_active_shelf_ideas", lambda: [])

    review = wk.build_weekly_review("u1", date(2026, 7, 5), store=store)
    [s] = review["switch_suggestions"]
    assert (s["symbol"], s["switch_candidate"], s["date"]) == \
        ("WINCO", "NEWCO", "2026-06-20")
    text = wk.render_weekly_text(review)
    assert "SWITCH" in text and "NEWCO" in text


def test_run_weekly_saves_and_delivers(tmp_path, monkeypatch):
    from unittest.mock import patch
    monkeypatch.setattr(wk, "active_user_ids", lambda: ["u1"])
    monkeypatch.setattr(wk.settings, "PORTFOLIO_DATA_DIR", str(tmp_path))
    _store(tmp_path)
    monkeypatch.setattr(wk, "_narrate_weekly", lambda r: "h")
    monkeypatch.setattr(wk, "_latest_closes", lambda symbols, on: _closes())
    monkeypatch.setattr(wk, "_active_shelf_ideas", lambda: [])
    with patch.object(wk, "deliver", return_value={"delivered": True}) as m:
        out = wk.run_weekly_review(on=date(2026, 7, 5))
    assert out["status"] == "completed" and m.call_count == 1
    saved = PortfolioStore(user_id="u1", base_dir=str(tmp_path)).load_latest_weekly()
    assert saved and saved["kind"] == "weekly_review"


def test_run_weekly_delivers_inbox_deeplink(tmp_path, monkeypatch):
    from core.config import settings
    captured = {}
    monkeypatch.setattr(wk, "active_user_ids", lambda: ["u1"])
    monkeypatch.setattr(wk, "build_weekly_review",
                        lambda uid, on, store=None: {"date": on.isoformat(),
                                                     "kind": "weekly_review"})
    monkeypatch.setattr(wk, "render_weekly_text", lambda r: "text")
    monkeypatch.setattr(wk, "deliver",
                        lambda *a, **k: captured.update(k) or {"delivered": True})
    monkeypatch.setattr(settings, "PORTFOLIO_DATA_DIR", str(tmp_path))
    wk.run_weekly_review(date(2026, 7, 22))
    assert captured["url"] == "/#/inbox/weekly"


def test_weekly_text_renders_the_ipo_section():
    review = {
        "date": "2026-08-16", "headline": "", "allocation": [],
        "concentration_flags": [], "laggards": [], "switch_candidates": [],
        "switch_suggestions": [], "scoreboard": {"counts": {}, "checked": 0, "correct": 0},
        "ipo_watch": [{"symbol": "OPENCO", "company": "Open Co", "state": "open",
                       "issue_start": "2026-08-14", "issue_end": "2026-08-18",
                       "total_x": 4.2, "qib_x": None, "retail_x": None}],
    }
    text = wk.render_weekly_text(review)
    assert "OPENCO" in text
    assert "IPO" in text


def test_weekly_ipo_section_absent_when_no_issues():
    review = {
        "date": "2026-08-16", "headline": "", "allocation": [],
        "concentration_flags": [], "laggards": [], "switch_candidates": [],
        "switch_suggestions": [], "scoreboard": {"counts": {}, "checked": 0, "correct": 0},
        "ipo_watch": [],
    }
    assert "IPO" not in wk.render_weekly_text(review)


def test_render_weekly_text_survives_malformed_date():
    """render_weekly_text is called directly from an HTTP route
    (services/api/routes/delivery_api.py) with no per-user wrapper — unlike
    build_weekly_review/run_weekly_review, which only run_weekly_review
    wraps. A malformed stored date must degrade to today(), not raise
    (Finding 5) — the same guard both brief renderers already have."""
    review = {
        "date": "not-a-date", "headline": "", "allocation": [],
        "concentration_flags": [], "laggards": [], "switch_candidates": [],
        "switch_suggestions": [], "scoreboard": {"counts": {}, "checked": 0, "correct": 0},
        "ipo_watch": [{"symbol": "OPENCO", "company": "Open Co", "state": "open",
                       "issue_start": "2026-08-14", "issue_end": "2026-08-18",
                       "total_x": 4.2, "qib_x": None, "retail_x": None}],
    }
    text = wk.render_weekly_text(review)          # must not raise
    assert isinstance(text, str) and "OPENCO" in text


def test_ipo_read_failure_does_not_break_the_weekly(monkeypatch):
    monkeypatch.setattr(wk, "_weekly_ipos", lambda on: (_ for _ in ()).throw(RuntimeError("boom")))
    # build_weekly_review catches per-section; the helper itself must be safe.
    assert wk._safe_weekly_ipos(date(2026, 8, 16)) == []


# -- a switch has to say why (2026-08-20) ------------------------------------

def _switch_store(tmp_path, **kw):
    store = _store(tmp_path)
    fields = dict(date="2026-06-20", user_id="u1", symbol="WINCO",
                  verdict="SWITCH", close=100.0, unrealised_pnl_pct=-14.0,
                  stop_pct=12.0, switch_candidate="NEWCO",
                  triggers=["stop_breach", "switch_candidate_available"])
    fields.update(kw)
    store.append_advice(AdviceRecord(**fields))
    return store


class _ShelfDouble:
    def __init__(self, symbol, sector, conviction, **kw):
        self.symbol, self.sector, self.conviction = symbol, sector, conviction
        self.status = kw.get("status", "active")
        self.thesis = kw.get("thesis", "")
        self.entry_low = kw.get("entry_low", 0.0)
        self.entry_high = kw.get("entry_high", 0.0)
        self.invalidation_level = kw.get("invalidation_level", 0.0)


def test_switch_suggestion_says_why_you_are_leaving(tmp_path, monkeypatch):
    store = _switch_store(tmp_path)
    monkeypatch.setattr(wk, "_narrate_weekly", lambda r: "h")
    monkeypatch.setattr(wk, "_latest_closes", lambda symbols, on: _closes())
    monkeypatch.setattr(wk, "_active_shelf_ideas", lambda: [])
    monkeypatch.setattr(wk, "_shelf_by_symbol", lambda: {})

    s = wk.build_weekly_review("u1", date(2026, 7, 5), store=store)["switch_suggestions"][0]
    assert s["symbol"] == "WINCO" and s["switch_candidate"] == "NEWCO"
    assert "stop" in s["reason"].lower()          # deterministic, from the triggers
    assert s["triggers"] == ["stop_breach", "switch_candidate_available"]
    assert s["pnl_pct"] == -14.0 and s["stop_pct"] == 12.0


def test_switch_suggestion_prefers_the_stored_narrative(tmp_path, monkeypatch):
    """The advisor already narrates every call. Re-deriving prose from trigger
    codes when a written reason exists would show the user two voices."""
    store = _switch_store(tmp_path, narrative="JLR demand warning broke the thesis.")
    monkeypatch.setattr(wk, "_narrate_weekly", lambda r: "h")
    monkeypatch.setattr(wk, "_latest_closes", lambda symbols, on: _closes())
    monkeypatch.setattr(wk, "_active_shelf_ideas", lambda: [])
    monkeypatch.setattr(wk, "_shelf_by_symbol", lambda: {})

    s = wk.build_weekly_review("u1", date(2026, 7, 5), store=store)["switch_suggestions"][0]
    assert s["reason"] == "JLR demand warning broke the thesis."


def test_switch_suggestion_says_why_that_destination(tmp_path, monkeypatch):
    store = _switch_store(tmp_path)
    monkeypatch.setattr(wk, "_narrate_weekly", lambda r: "h")
    monkeypatch.setattr(wk, "_latest_closes", lambda symbols, on: _closes())
    monkeypatch.setattr(wk, "_active_shelf_ideas", lambda: [])
    monkeypatch.setattr(wk, "_shelf_by_symbol", lambda: {"NEWCO": _ShelfDouble(
        "NEWCO", "pharma", 0.81, thesis="Margin inflection on the API ramp.",
        entry_low=90.0, entry_high=104.0, invalidation_level=82.0)})

    cand = wk.build_weekly_review("u1", date(2026, 7, 5),
                                  store=store)["switch_suggestions"][0]["candidate"]
    assert cand["thesis"] == "Margin inflection on the API ramp."
    assert cand["conviction"] == 0.81 and cand["sector"] == "pharma"
    assert cand["entry_low"] == 90.0 and cand["invalidation_level"] == 82.0


def test_destination_off_the_shelf_degrades_to_no_candidate_detail(tmp_path, monkeypatch):
    """A destination promoted or dropped since the call still has to render."""
    store = _switch_store(tmp_path)
    monkeypatch.setattr(wk, "_narrate_weekly", lambda r: "h")
    monkeypatch.setattr(wk, "_latest_closes", lambda symbols, on: _closes())
    monkeypatch.setattr(wk, "_active_shelf_ideas", lambda: [])
    monkeypatch.setattr(wk, "_shelf_by_symbol", lambda: {})

    s = wk.build_weekly_review("u1", date(2026, 7, 5), store=store)["switch_suggestions"][0]
    assert s["candidate"] == {}


def test_shelf_candidates_exclude_what_you_already_hold(tmp_path, monkeypatch):
    """Offering a holding as a "switch idea" is a top-up dressed as a rotation."""
    store = _store(tmp_path)
    monkeypatch.setattr(wk, "_narrate_weekly", lambda r: "h")
    monkeypatch.setattr(wk, "_latest_closes", lambda symbols, on: _closes())
    monkeypatch.setattr(wk, "_active_shelf_ideas", lambda: [
        _ShelfDouble("LAGCO", "pharma", 0.9),      # already a holding
        _ShelfDouble("PHARMCO", "pharma", 0.8),
    ])
    review = wk.build_weekly_review("u1", date(2026, 7, 5), store=store)
    assert [c["symbol"] for c in review["switch_candidates"]] == ["PHARMCO"]


def test_shelf_candidates_carry_their_thesis(tmp_path, monkeypatch):
    store = _store(tmp_path)
    monkeypatch.setattr(wk, "_narrate_weekly", lambda r: "h")
    monkeypatch.setattr(wk, "_latest_closes", lambda symbols, on: _closes())
    monkeypatch.setattr(wk, "_active_shelf_ideas", lambda: [
        _ShelfDouble("PHARMCO", "pharma", 0.8, thesis="API ramp.",
                     entry_low=90.0, entry_high=104.0)])
    c = wk.build_weekly_review("u1", date(2026, 7, 5), store=store)["switch_candidates"][0]
    assert c["thesis"] == "API ramp." and c["entry_low"] == 90.0

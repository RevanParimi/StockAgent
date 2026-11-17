"""PR-039: the missed-risers report (scripts/missed_risers.py).

A made-up market of 15 sessions, one stock per place in the funnel, checked
against the records it was built from; the arithmetic of a bonus; the floors
against the screen's own code; and that the report writes nothing.
"""
from __future__ import annotations

import json
import sqlite3
from datetime import date

import pandas as pd
import pytest

from core.config import settings
from scripts import missed_risers as mr

DAYS = [d.date() for d in pd.bdate_range("2026-10-05", periods=15)]
START, END = DAYS[4], DAYS[14]            # Fri 9 Oct, Fri 23 Oct: 10 sessions
SCREEN1, SCREEN2 = DAYS[4], DAYS[9]       # Fri 9 Oct, Fri 16 Oct
SAT1, SAT2 = date(2026, 10, 10), date(2026, 10, 17)

# symbol: (close at the start, close at the end); flat before the start.
PATHS = {
    "R_BELOW": (100.0, 150.0),   # never a candidate: place 2
    "R_GUARD": (100.0, 140.0),   # the screen's guards rejected it: place 1
    "R_CAND": (100.0, 130.0),    # a candidate, never dived: place 3
    "R_DOWN": (100.0, 125.0),    # dived, HOLD: place 4, turned down
    "R_AWAY": (100.0, 120.0),    # dived, BUY, not shelved: place 4, turned away
    "R_SHELF": (100.0, 115.0),   # shelved, never bought: place 5
    "R_BOOK": (100.0, 112.0),    # bought in the window: the book
    "FLAT1": (100.0, 100.0),
    "F_BELOW": (100.0, 80.0),
    "F_BOOK": (100.0, 70.0),     # held from before the window
    "PENNY": (10.0, 30.0),       # under Rs 20 at the start: not in the population
    "THIN": (100.0, 300.0),      # Rs 1 cr a day: not in the population
    "NIFTYBEES": (100.0, 200.0),  # a fund: not in the population
}


def _rows(symbol, first, last, tv=10.0):
    closes = []
    for i, d in enumerate(DAYS):
        k = max(0, i - 4)
        closes.append(first + (last - first) * k / 10.0)
    out, prev = [], closes[0]
    for d, c in zip(DAYS, closes):
        out.append({"symbol": symbol, "series": "EQ", "date": d.isoformat(), "prev_close": prev,
                    "open": c, "high": c * 1.01, "low": c * 0.99, "close": c, "volume": 1000,
                    "traded_value_cr": tv, "delivery_qty": 500, "delivery_pct": 50.0})
        prev = c
    return out


def _bonus_rows():
    """200 until a 1:1 bonus goes ex on 16 Oct (NSE restates the previous close
    to 100), then 110: a holder's 1 share at 200 became 2 at 110 = +10%."""
    out, prev = [], 200.0
    for i, d in enumerate(DAYS):
        close = 200.0 if d < DAYS[9] else 110.0
        restated = 100.0 if d == DAYS[9] else prev
        out.append({"symbol": "BONUS", "series": "EQ", "date": d.isoformat(),
                    "prev_close": restated, "open": close, "high": close, "low": close,
                    "close": close, "volume": 1000, "traded_value_cr": 10.0,
                    "delivery_qty": 500, "delivery_pct": 50.0})
        prev = close
    return out


def _write(p, obj):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(obj if isinstance(obj, str) else json.dumps(obj), encoding="utf-8")


def _utc(d: date, hh: int, mm: int) -> str:
    """An IST wall time as the score history's naive UTC ISO stamp."""
    ist = pd.Timestamp(f"{d.isoformat()} {hh:02d}:{mm:02d}", tz="Asia/Kolkata")
    return ist.tz_convert("UTC").tz_localize(None).isoformat()


@pytest.fixture(autouse=True)
def _floors(monkeypatch):
    for name, value in (("DISCOVERY_MIN_PRICE", 20.0), ("DISCOVERY_LIQUIDITY_FLOOR_CR", 5.0),
                        ("DISCOVERY_CIRCUIT_STREAK_MAX", 3), ("DISCOVERY_MIN_CONVICTION", 0.55),
                        ("DISCOVERY_DEEP_DIVE_COUNT", 20)):
        monkeypatch.setattr(settings, name, value, raising=False)


def _market(root, *, screens=(SCREEN1, SCREEN2), digests=None):
    eod = root / settings.DISCOVERY_BHAVCOPY_DIR
    eod.mkdir(parents=True)
    rows = [r for s, (a, b) in PATHS.items()
            for r in _rows(s, a, b, tv=1.0 if s == "THIN" else 10.0)] + _bonus_rows()
    df = pd.DataFrame(rows)
    for d in DAYS:
        df[df["date"] == d.isoformat()].to_parquet(eod / f"{d.isoformat()}.parquet", index=False)
    disc = root / settings.DISCOVERY_DATA_DIR
    securities = {s: {"series": "EQ", "isin": "INF000000001" if s == "NIFTYBEES" else
                      "INE000000001"} for s in [*PATHS, "BONUS"]}
    _write(disc / "listing.json", {"as_of": END.isoformat(), "securities": securities})
    screen_recs = {
        SCREEN1: {"candidates": ["R_DOWN"], "rejected": {}},
        SCREEN2: {"candidates": ["R_AWAY", "R_CAND", "R_SHELF"],
                  "rejected": {"R_GUARD": ["low_float_mcap"]}},
    }
    for d in screens:
        rec = screen_recs[d]
        _write(disc / "screens" / f"{d.isoformat()}_screen.json", {
            "screen_date": d.isoformat(), "universe_size": 12, "shortlist_size": 5,
            "candidates": [{"symbol": s, "close": 100.0, "composite": 0.9, "signal_ranks": {}}
                           for s in rec["candidates"]],
            "rejected": rec["rejected"], "dark_signals": [], "degraded_checks": []})
    _write(disc / "shelf_events.jsonl", json.dumps(
        {"ts": "2026-10-17T07:35:00+00:00", "event": "added", "symbol": "R_SHELF",
         "detail": "conviction=0.70"}) + "\n")
    _write(disc / "shelf.json", {"ideas": [{"symbol": "R_SHELF", "added": "2026-10-17",
                                            "status": "active", "conviction": 0.70}]})
    db = root / settings.SCORE_DB_PATH
    db.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db)
    conn.execute("CREATE TABLE score_history (id INTEGER PRIMARY KEY, ticker TEXT, "
                 "company_name TEXT, run_at TEXT, final_score REAL, verdict TEXT, "
                 "report_json TEXT)")
    gate = json.dumps({"decision_gate": {"status": "actionable"}})
    for sym, day, score, verdict in (("R_DOWN", SAT1, 0.40, "HOLD"),
                                     ("R_AWAY", SAT2, 0.62, "BUY"),
                                     ("R_SHELF", SAT2, 0.70, "BUY")):
        conn.execute("INSERT INTO score_history (ticker, company_name, run_at, final_score, "
                     "verdict, report_json) VALUES (?, ?, ?, ?, ?, ?)",
                     (sym, sym, _utc(day, 13, 0), score, verdict, gate))
    conn.commit()
    conn.close()
    book = root / settings.PORTFOLIO_DATA_DIR / settings.PORTFOLIO_DEFAULT_USER_ID
    _write(book / "transactions.jsonl", "\n".join(json.dumps(t) for t in (
        {"date": "2026-10-01", "side": "BUY", "symbol": "F_BOOK", "holding_qty_after": 10},
        {"date": DAYS[7].isoformat(), "side": "BUY", "symbol": "R_BOOK",
         "holding_qty_after": 5},
    )) + "\n")
    for day, rec in (digests or {}).items():
        _write(book / "digests" / f"{day.isoformat()}.json", {"deployment": rec})
    return root


def _by_symbol(report, key):
    return {r["symbol"]: r for r in report[key]}


def test_each_riser_is_placed_where_its_records_say(tmp_path):
    report = mr.build_report(_market(tmp_path), sessions=10, top=8)
    assert report["window"]["start"] == START.isoformat()
    assert report["window"]["end"] == END.isoformat()
    rows = _by_symbol(report, "risers")
    assert list(rows)[:7] == ["R_BELOW", "R_GUARD", "R_CAND", "R_DOWN", "R_AWAY", "R_SHELF",
                              "R_BOOK"]
    expected = {"R_BELOW": (2, SCREEN1), "R_GUARD": (1, SCREEN2), "R_CAND": (3, SCREEN2),
                "R_DOWN": (4, SAT1), "R_AWAY": (4, SAT2), "R_SHELF": (5, SAT2),
                "R_BOOK": (6, DAYS[7])}
    for sym, (place, day) in expected.items():
        assert (rows[sym]["place"], rows[sym]["date"]) == (place, day.isoformat()), sym
    assert "low_float_mcap" in rows["R_GUARD"]["reason"]
    assert "candidate 2 of 3" in rows["R_CAND"]["reason"]
    assert "dived 2 stocks" in rows["R_CAND"]["reason"]
    assert "rated HOLD at 0.40" in rows["R_DOWN"]["reason"]
    assert "not shelved" in rows["R_AWAY"]["reason"]
    assert "the switch was off" in rows["R_SHELF"]["reason"]
    assert rows["R_BOOK"]["reason"].startswith("bought on")


def test_fallers_and_the_population(tmp_path):
    report = mr.build_report(_market(tmp_path), sessions=10, top=8)
    fallers = _by_symbol(report, "fallers")
    assert list(fallers)[:2] == ["F_BOOK", "F_BELOW"]
    assert fallers["F_BOOK"]["place"] == 6
    assert fallers["F_BOOK"]["reason"] == "held at the window's start"
    assert fallers["F_BELOW"]["place"] == 2
    every = {r["symbol"] for r in report["risers"] + report["fallers"]}
    assert not every & {"PENNY", "THIN", "NIFTYBEES"}
    assert report["population"]["outside the floors at the start"] == 3
    assert report["population"]["inside the floors"] == 11


def test_a_bonus_is_not_read_as_a_fall():
    """Independent of the code: 1 share at 200 becomes 2 shares at 110."""
    rows = pd.DataFrame(_bonus_rows())
    chained, raw = mr.chained_return(rows, START.isoformat(), END.isoformat())
    assert chained == pytest.approx(2 * 110.0 / 200.0 - 1)
    assert raw == pytest.approx(110.0 / 200.0 - 1)


def test_the_bonus_stock_is_a_riser_marked_adjusted(tmp_path):
    rows = _by_symbol(mr.build_report(_market(tmp_path), sessions=10, top=8), "risers")
    assert rows["BONUS"]["return_pct"] == pytest.approx(10.0)
    assert rows["BONUS"]["adjusted"] is True
    assert rows["R_BOOK"]["adjusted"] is False


def test_rupees_and_rise_after(tmp_path):
    report = mr.build_report(_market(tmp_path), sessions=10, top=8)
    rows = _by_symbol(report, "risers")
    assert report["window"]["position_inr"] == 320000.0
    assert rows["R_BELOW"]["position_inr"] == 160000.0          # 3.2% of Rs 1 cr x 50%
    # R_CAND was a candidate at the 16 Oct close (115), and ended at 130.
    assert rows["R_CAND"]["after_pct"] == pytest.approx(round((130 / 115 - 1) * 100, 1))
    totals = report["totals"]["risers"]
    assert totals[4]["count"] == 2
    assert totals[4]["inr"] == pytest.approx(320000 * 0.25 + 320000 * 0.20)


def test_buy_step_reason_on_record(tmp_path):
    digests = {DAYS[11]: {"ideas": [{"symbol": "R_SHELF", "outcome": "band",
                                     "why": "close 6% above the entry band"}]}}
    rows = _by_symbol(mr.build_report(_market(tmp_path, digests=digests), sessions=10, top=8),
                      "risers")
    assert f"buy step, session {DAYS[11]}: band" in rows["R_SHELF"]["reason"]
    assert "6% above" in rows["R_SHELF"]["reason"]


def test_not_offered_when_deployment_ran_without_it(tmp_path):
    digests = {DAYS[11]: {"ideas": [{"symbol": "OTHER", "outcome": "bought"}]}}
    rows = _by_symbol(mr.build_report(_market(tmp_path, digests=digests), sessions=10, top=8),
                      "risers")
    assert "not offered by the buy list in 1 sessions" in rows["R_SHELF"]["reason"]


def test_window_starts_at_the_first_stored_screen(tmp_path):
    report = mr.build_report(_market(tmp_path, screens=(SCREEN2,)), sessions=10, top=8)
    assert report["window"]["start"] == SCREEN2.isoformat()
    assert report["window"]["sessions"] == 5
    text = mr.render(report)
    assert f"The stored screens go back only to {SCREEN2}" in text


def test_places_losing_over_a_quarter_name_a_card(tmp_path):
    report = mr.build_report(_market(tmp_path), sessions=10, top=3)
    lines = report["quarter_lines"]
    assert len(lines) == 3                      # places 2, 1 and 3, a third each
    assert any(line.startswith("Place 3") and "PR-037" in line for line in lines)
    assert any(line.startswith("Place 1") and "no card yet" in line for line in lines)


def test_output_states_its_limits(tmp_path, capsys):
    assert mr.main(["--root", str(_market(tmp_path)), "--sessions", "10", "--top", "8"]) == 0
    text = capsys.readouterr().out
    assert "hindsight" in text
    assert "was not known to rise on the day it was lost" in text
    assert "one market period" in text
    assert "THE RISERS" in text and "THE FALLERS" in text and "TOTALS BY PLACE" in text


def test_floors_match_the_screens_own_gates(monkeypatch):
    """A stock is inside the report's floors exactly when the screen's own
    universe and guards (their bhavcopy gates) keep it."""
    import core.discovery.guards as guards
    from core.discovery.universe import build_universe
    monkeypatch.setattr(guards, "pledge_snapshots", lambda symbols: {})
    monkeypatch.setattr(guards, "surveillance_list", lambda session: (None, None))
    monkeypatch.setattr(guards, "float_mcap_cr", lambda symbol: None)
    rows = (_rows("OKAY", 100, 110) + _rows("PENNY", 10, 12) + _rows("THIN", 100, 110, tv=1.0)
            + [dict(r, series="BE") for r in _rows("TTWO", 100, 110)])
    circuit, prev = [], 100.0
    for i, d in enumerate(DAYS):
        close = prev * (1.10 if i >= 10 else 1.0)       # five 10% upper circuits to finish
        circuit.append({"symbol": "CIRC", "series": "EQ", "date": d.isoformat(),
                        "prev_close": prev, "open": close, "high": close, "low": close,
                        "close": close, "volume": 1, "traded_value_cr": 10.0,
                        "delivery_qty": 1, "delivery_pct": 50.0})
        prev = close
    window = pd.DataFrame(rows + circuit)
    universe = build_universe(window)
    passed, _rejected, _degraded = guards.apply_guards(universe, window)
    for sym in ("OKAY", "PENNY", "THIN", "TTWO", "CIRC"):
        sym_rows = window[window["symbol"] == sym].sort_values("date")
        inside = not mr.floors_out(sym_rows, None, sym)
        assert inside == (sym in passed), sym
    assert passed == ["OKAY"]


def test_the_report_writes_nothing(tmp_path, capsys):
    root = _market(tmp_path, digests={DAYS[11]: {"ideas": []}})
    before = {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in root.rglob("*") if p.is_file()}
    dirs = {p for p in root.rglob("*") if p.is_dir()}
    mr.main(["--root", str(root), "--sessions", "10", "--top", "8"])
    mr.main(["--root", str(root), "--sessions", "10", "--top", "8", "--json"])
    capsys.readouterr()
    after = {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in root.rglob("*") if p.is_file()}
    assert after == before
    assert {p for p in root.rglob("*") if p.is_dir()} == dirs


def test_an_empty_root_is_reported_not_raised(tmp_path, capsys):
    assert mr.main(["--root", str(tmp_path)]) == 0
    assert "Not measured" in capsys.readouterr().out
    assert list(tmp_path.iterdir()) == []

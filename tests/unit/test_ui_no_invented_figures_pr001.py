"""PR-001: every figure the UI API sends is real and dated, or plainly absent.

Through the real FastAPI router with a real ScoreStore on a temp file and a
fake `yfinance` module (the code imports it inside each fetch). The expected
values are computed here from the fixture series, not read from the code:

- /ui/learnings sends dated verdict changes only: no rupee field derived from a
  score, no summary rate, no templated lesson; a change is a verdict that
  differs from the run before it, listed newest first across all stocks and
  cut after sorting, with forecast misses after the changes;
- /ui/bootstrap's NIFTY50 is the last close, its change on the close before
  and that close's date; with prices down and no analyses it sends no market
  number at all (no random series, no padded drivers, no weight shown as a vote);
- /ui/nifty-ranges covers the calendar span it names and dates its last value;
- a static guard: no customer-facing prototype file holds a sample figure,
  "Aditi" or "Run on MARUTI" outside demo-fixtures.js.

The browser behaviour is in tests/frontend/no_invented_figures.test.mjs; the
last test here runs it.
"""
from __future__ import annotations

import json
import re
import shutil
import sqlite3
import subprocess
import sys
import types
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import pytest

REPO = Path(__file__).resolve().parents[2]
PROTO = REPO / "src" / "frontend" / "prototypes"

# ---------------------------------------------------------------------------
# Fixtures: a real score store on a temp file, and a fake yfinance
# ---------------------------------------------------------------------------


@pytest.fixture
def store(tmp_path, monkeypatch):
    from services.api.routes import ui_data
    from services.data.stores.score_store import ScoreStore
    s = ScoreStore(db_path=str(tmp_path / "scores.db"))
    monkeypatch.setattr(ui_data, "_score_store", lambda: s)
    return s


def add_run(store, ticker, run_at, score, verdict, *, thesis="", agent_scores=None, drivers=None):
    with sqlite3.connect(store._db_path) as conn:
        conn.execute(
            "INSERT INTO score_history (ticker, company_name, run_at, final_score, verdict, agent_scores,"
            " investment_thesis, conviction_drivers, top_risks, report_json)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, '[]', '{}')",
            (ticker, ticker.title(), run_at, score, verdict, json.dumps(agent_scores or {}),
             thesis, json.dumps(drivers or [])))


def nse_closes(first: date, last: date, start: float = 20000.0, step: float = 7.25):
    """Weekday closes from `first` to `last`, each distinct: [(date, close)]."""
    out, d, v = [], first, start
    while d <= last:
        if d.weekday() < 5:
            out.append((d, round(v, 2)))
            v += step
        d += timedelta(days=1)
    return out


def fake_yfinance(series: dict[str, list[tuple[date, float]]] | None):
    """A yfinance stand-in: Ticker(sym).history(period='Nd'|'1mo') returns the
    closes in the last N calendar days of that symbol's series (a DatetimeIndex
    in Asia/Kolkata, like Yahoo's NSE bars). series=None: every fetch raises."""
    mod = types.ModuleType("yfinance")

    class Ticker:
        def __init__(self, sym):
            self.sym = sym

        def history(self, period="1mo", auto_adjust=True):
            if series is None:
                raise ConnectionError("yfinance down (test)")
            rows = series.get(self.sym, [])
            if not rows:
                return pd.DataFrame({"Close": []})
            days = 31 if period == "1mo" else int(period.rstrip("d"))
            last = rows[-1][0]
            kept = [(d, v) for d, v in rows if d > last - timedelta(days=days)]
            idx = pd.DatetimeIndex([pd.Timestamp(d) for d, _ in kept]).tz_localize("Asia/Kolkata")
            return pd.DataFrame({"Close": [v for _, v in kept]}, index=idx)

    mod.Ticker = Ticker
    return mod


@pytest.fixture
def client():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from services.api.routes.ui_data import router
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def walk(obj, path=""):
    """Every (path, key, value) in a JSON value."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield path, k, v
            yield from walk(v, f"{path}.{k}")
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            yield from walk(v, f"{path}[{i}]")


def numbers(obj):
    """Every number in a JSON value (bools excluded)."""
    if isinstance(obj, bool) or obj is None:
        return []
    if isinstance(obj, (int, float)):
        return [obj]
    if isinstance(obj, dict):
        return [n for v in obj.values() for n in numbers(v)]
    if isinstance(obj, list):
        return [n for v in obj for n in numbers(v)]
    return []


# ---------------------------------------------------------------------------
# /ui/learnings
# ---------------------------------------------------------------------------

MONEY_KEY = re.compile(r"gain|loss|realized|rupee|inr|cost", re.I)
TEMPLATES = ("has shown sustained upside", "Watch agent weights", "tighten stop-loss",
             "reduce position", "Tune agent weight", "Review this agent's weight",
             "Review agent details")


class _FeedbackEntry:
    def __init__(self, day, miss_type, direction_correct, agent):
        self.date, self.miss_type = day, miss_type
        self.direction_correct, self.primary_miss_agent = direction_correct, agent


def _fake_prediction_store(entries_by_ticker):
    class FakePredictionStore:
        def __init__(self, ticker, sector):
            self.ticker = ticker

        def current_cycle_id(self):
            return "2026-10"

        def load_feedback_log(self, cycle):
            entries = entries_by_ticker.get(self.ticker)
            return types.SimpleNamespace(entries=entries) if entries else None
    return FakePredictionStore


def test_learnings_send_dated_verdict_changes_and_no_money_rate_or_advice(client, store, monkeypatch):
    add_run(store, "MARUTI", "2026-10-01T04:00:00", 0.30, "SELL", thesis="Margins under pressure.")
    add_run(store, "MARUTI", "2026-10-09T04:00:00", 0.71, "BUY", thesis="Utility-vehicle dispatches beat.")
    add_run(store, "TATAMOTORS", "2026-10-02T04:00:00", 0.72, "BUY")
    add_run(store, "TATAMOTORS", "2026-10-10T04:00:00", 0.28, "SELL")
    add_run(store, "M&M", "2026-10-03T04:00:00", 0.66, "BUY")          # one run: no change to report
    from core.intelligence.rl.stores import prediction_store
    monkeypatch.setattr(prediction_store, "PredictionStore", _fake_prediction_store({
        "MARUTI": [_FeedbackEntry("2026-10-08", "model_bias", False, "fundamentals"),
                   _FeedbackEntry("2026-10-09", "data_gap", None, None)],   # not a model miss
    }))

    body = client.get("/ui/learnings").json()
    assert set(body) == {"items", "since"}, "no summary block, no pattern strip"
    assert body["since"] == "2026-10-01", "the oldest kept run among the listed stocks (FIX-010)"
    for path, key, value in walk(body):
        assert not MONEY_KEY.search(key), f"{path}.{key}: a money-shaped field"
        assert key not in {"lesson", "action", "accuracyVsAgent", "rate"}, f"{path}.{key}"
    text = json.dumps(body, ensure_ascii=False)
    assert "₹" not in text and "Rs." not in text
    for phrase in TEMPLATES:
        assert phrase not in text, phrase

    by_sym = {}
    for it in body["items"]:
        by_sym.setdefault(it["sym"], []).append(it)
    assert set(by_sym) == {"MARUTI", "TATAMOTORS"}
    up = next(i for i in by_sym["MARUTI"] if i["kind"] != "forecast-miss")
    down = by_sym["TATAMOTORS"][0]
    # the kind names the verdict move, nothing about a trade
    assert (up["kind"], down["kind"]) == ("turned-bullish", "turned-bearish")
    assert up["title"] == "MARUTI: SELL → BUY" and up["when"] == "2026-10-09"
    assert up["detail"] == f"Score moved +{round(0.71 - 0.30, 2):.2f} → now BUY"
    assert down["detail"] == f"Score moved {round(0.28 - 0.72, 2):.2f} → now SELL"
    assert up["what"] == "Utility-vehicle dispatches beat."
    misses = [i for i in by_sym["MARUTI"] if i["kind"] == "forecast-miss"]
    assert [m["when"] for m in misses] == ["2026-10-08"], "a data gap is not the model's miss"


def test_learnings_with_no_history_send_nothing(client, store, monkeypatch):
    from core.intelligence.rl.stores import prediction_store
    monkeypatch.setattr(prediction_store, "PredictionStore", _fake_prediction_store({}))
    assert client.get("/ui/learnings").json() == {"items": [], "since": None}


# --- Rework 1 (review M1): only a verdict that differs from the run before it
# is a change; newest first across all stocks; the cap after sorting; forecast
# misses after the changes, never as one. Expected lists are derived here from
# each fixture's own (date, stock, verdict) table.

def _universe():
    from services.api.routes.ui_data import _ALL_TICKERS
    return [t["sym"] for t in _ALL_TICKERS]


def _expected_changes(runs):
    """[(when, title)] newest first, from a fixture table of (sym, run_at, verdict)
    rows: a run whose verdict differs from that stock's run before it."""
    out = []
    for sym in {r[0] for r in runs}:
        mine = sorted((r for r in runs if r[0] == sym), key=lambda r: r[1])
        for older, newer in zip(mine, mine[1:]):
            if older[2] != newer[2]:
                out.append((newer[1], f"{sym}: {older[2]} → {newer[2]}"))
    return [(when[:10], title) for when, title in sorted(out, reverse=True)]


def _changes_only(body):
    return [(i["when"], i["title"]) for i in body["items"] if i["kind"] != "forecast-miss"]


@pytest.fixture
def no_misses(monkeypatch):
    from core.intelligence.rl.stores import prediction_store
    monkeypatch.setattr(prediction_store, "PredictionStore", _fake_prediction_store({}))


def test_an_unchanged_verdict_is_not_listed_and_a_later_ticker_s_newer_change_is(client, store, no_misses):
    # The review's probe: two real changes this month, eleven stocks re-analysed in
    # July with the same verdict, and the last of them (after the tenth ticker in
    # the universe) turned bullish yesterday.
    uni = _universe()
    same = [s for s in uni if s not in ("MARUTI", "TATAMOTORS", "EICHERMOT")][:11]
    assert uni.index(same[-1]) > 9, "the newest change sits after the first ten tickers"
    runs = [("MARUTI", "2026-10-01T11:00:00", "SELL"), ("MARUTI", "2026-10-09T11:00:00", "BUY"),
            ("TATAMOTORS", "2026-10-02T11:00:00", "BUY"), ("TATAMOTORS", "2026-10-10T11:00:00", "SELL"),
            ("EICHERMOT", "2026-10-08T11:00:00", "NEUTRAL")]
    for s in same:
        runs += [(s, "2026-07-01T11:00:00", "NEUTRAL"), (s, "2026-07-02T11:00:00", "NEUTRAL")]
    runs.append((same[-1], "2026-10-13T11:00:00", "BUY"))
    for sym, at, verdict in runs:
        add_run(store, sym, at, 0.5, verdict)

    got = _changes_only(client.get("/ui/learnings").json())
    assert got == _expected_changes(runs)
    assert got == [("2026-10-13", f"{same[-1]}: NEUTRAL → BUY"), ("2026-10-10", "TATAMOTORS: BUY → SELL"),
                   ("2026-10-09", "MARUTI: SELL → BUY")]
    for _, title in got:
        before, after = title.split(": ", 1)[1].split(" → ")
        assert before != after, title


def test_the_cap_keeps_the_newest_changes_whichever_stock_they_are_in(client, store, no_misses):
    # One change per stock, the first ticker's oldest and the last ticker's newest:
    # sixteen changes, so the cap of ten must drop the six oldest, not the last six tickers.
    from services.api.routes.ui_data import _LEARNINGS_MAX_CHANGES
    uni = _universe()
    runs = []
    for k, sym in enumerate(uni):
        day = date(2026, 9, 1) + timedelta(days=2 * k)
        runs += [(sym, f"{day.isoformat()}T10:00:00", "NEUTRAL"),
                 (sym, f"{(day + timedelta(days=1)).isoformat()}T10:00:00", "BUY" if k % 2 else "SELL")]
    for sym, at, verdict in runs:
        add_run(store, sym, at, 0.5, verdict)

    got = _changes_only(client.get("/ui/learnings").json())
    expected = _expected_changes(runs)
    assert len(expected) == len(uni) > _LEARNINGS_MAX_CHANGES == 10
    assert got == expected[:10]
    assert got[0][1].startswith(uni[-1] + ":"), "the newest change, in the last ticker, comes first"
    assert not any(t.startswith(uni[0] + ":") for _, t in got), "the oldest change is the one cut"


def test_every_change_in_the_kept_runs_is_listed_even_after_a_same_verdict_rerun(client, store, no_misses):
    # MARUTI turned bullish on 9 Oct and was re-analysed twice since with the same
    # verdict; TATAMOTORS went to BUY, back and to BUY again. Each change is listed,
    # dated by its run, with its own id (two of them are the same kind of move).
    runs = [("MARUTI", "2026-10-01T11:00:00", "SELL"), ("MARUTI", "2026-10-09T11:00:00", "BUY"),
            ("MARUTI", "2026-10-10T11:00:00", "BUY"), ("MARUTI", "2026-10-13T11:00:00", "BUY"),
            ("TATAMOTORS", "2026-10-05T11:00:00", "NEUTRAL"), ("TATAMOTORS", "2026-10-06T11:00:00", "BUY"),
            ("TATAMOTORS", "2026-10-07T11:00:00", "NEUTRAL"), ("TATAMOTORS", "2026-10-08T11:00:00", "BUY")]
    for sym, at, verdict in runs:
        add_run(store, sym, at, 0.5, verdict)
    body = client.get("/ui/learnings").json()
    assert _changes_only(body) == _expected_changes(runs) == [
        ("2026-10-09", "MARUTI: SELL → BUY"), ("2026-10-08", "TATAMOTORS: NEUTRAL → BUY"),
        ("2026-10-07", "TATAMOTORS: BUY → NEUTRAL"), ("2026-10-06", "TATAMOTORS: NEUTRAL → BUY")]
    assert len({i["id"] for i in body["items"]}) == len(body["items"]), "each record has its own id"


def test_a_missing_or_differently_cased_verdict_is_not_a_change(client, store, no_misses):
    add_run(store, "MARUTI", "2026-10-01T11:00:00", 0.5, "")
    add_run(store, "MARUTI", "2026-10-09T11:00:00", 0.7, "BUY")
    add_run(store, "TATAMOTORS", "2026-10-02T11:00:00", 0.7, "buy")
    add_run(store, "TATAMOTORS", "2026-10-10T11:00:00", 0.7, "BUY ")
    assert client.get("/ui/learnings").json() == {"items": [], "since": "2026-10-01"}


def test_forecast_misses_follow_the_changes_newest_first_and_are_not_changes(client, store, monkeypatch):
    from services.api.routes.ui_data import _LEARNINGS_MAX_MISSES
    uni = _universe()
    for k, sym in enumerate(uni[:12]):
        add_run(store, sym, f"2026-10-{1 + k:02d}T10:00:00", 0.4, "SELL")
        add_run(store, sym, f"2026-10-{1 + k:02d}T12:00:00", 0.7, "BUY")
    miss_days = ["2026-10-02", "2026-10-09", "2026-10-04", "2026-10-11", "2026-10-06", "2026-10-07", "2026-10-03"]
    from core.intelligence.rl.stores import prediction_store
    monkeypatch.setattr(prediction_store, "PredictionStore", _fake_prediction_store({
        uni[0]: [_FeedbackEntry(d, "model_bias", False, "fundamentals") for d in miss_days[:4]],
        uni[15]: [_FeedbackEntry(d, "direction_flip", False, "sentiment") for d in miss_days[4:]],
    }))
    items = client.get("/ui/learnings").json()["items"]
    kinds = [i["kind"] for i in items]
    assert kinds == ["turned-bullish"] * 10 + ["forecast-miss"] * _LEARNINGS_MAX_MISSES
    assert [i["when"] for i in items[10:]] == sorted(miss_days, reverse=True)[:5]
    assert all("→" in i["title"] for i in items[:10]) and not any("→" in i["title"] for i in items[10:])


def test_learnings_send_nothing_when_the_score_history_cannot_be_read(client, store, no_misses, monkeypatch):
    # A failure on a later stock must not leave a partial list that looks complete.
    add_run(store, "MARUTI", "2026-10-01T11:00:00", 0.3, "SELL")
    add_run(store, "MARUTI", "2026-10-09T11:00:00", 0.7, "BUY")
    real = store.get_history

    def flaky(ticker, limit=30):
        if ticker == _universe()[5]:
            raise sqlite3.OperationalError("database is locked")
        return real(ticker, limit)
    monkeypatch.setattr(store, "get_history", flaky)
    assert client.get("/ui/learnings").json() == {"items": [], "since": None}


def test_the_portfolio_page_knows_the_server_s_cap():
    from services.api.routes.ui_data import _LEARNINGS_MAX_CHANGES
    src = (PROTO / "portfolio.jsx").read_text(encoding="utf-8")
    m = re.search(r"const LEARNINGS_MAX_CHANGES = (\d+);", src)
    assert m and int(m.group(1)) == _LEARNINGS_MAX_CHANGES


# ---------------------------------------------------------------------------
# /ui/bootstrap
# ---------------------------------------------------------------------------

NSEI = nse_closes(date(2025, 9, 1), date(2026, 10, 12))


def test_bootstrap_nifty50_is_the_last_close_with_its_date(client, store, monkeypatch):
    monkeypatch.setitem(sys.modules, "yfinance", fake_yfinance({"^NSEI": NSEI}))
    body = client.get("/ui/bootstrap").json()
    (prev_day, prev), (last_day, last) = NSEI[-2], NSEI[-1]
    assert body["NIFTY50"] == {"name": "Nifty 50", "value": last,
                               "changePct": round((last - prev) / prev * 100, 2),
                               "asOf": last_day.isoformat()}
    assert last_day.isoformat() == "2026-10-12"


def test_bootstrap_with_prices_down_and_no_analyses_sends_no_market_number(client, store, monkeypatch):
    monkeypatch.setitem(sys.modules, "yfinance", fake_yfinance(None))
    body = client.get("/ui/bootstrap").json()

    assert body["NIFTY50"] is None
    assert body["NIFTY_AUTO_HISTORY"] == [], "no made-up series when the fetch fails"
    for section in ("MARKET_TODAY", "MARKET_MONTH"):
        assert numbers(body[section]) == [], f"{section} holds a number with no source: {body[section]}"
        assert body[section]["drivers"] == [], "no generic padding drivers"
    assert body["MARKET_MONTH"]["agentVotes"] == [], "an agent's weight is not a vote"
    assert all(s["pct"] is None for s in body["MARKET_TODAY"]["sectorChange"])
    assert body["MARKET_TODAY"]["pulse"] == "No recent data"
    # a failed price is 0 with hasData false: the screens show dashes for both
    assert all(t["price"] == 0 and t["hasData"] is False for t in body["TICKERS"])

    from services.api.routes.ui_data import _ALL_TICKERS
    seeds = " ".join(body["CHAT_SEEDS"])
    for t in _ALL_TICKERS:
        assert t["sym"] not in seeds, f"a chat seed names {t['sym']}"
    assert not re.search(r"STRONG BUY|\bBUY\b|\bSELL\b|\d", seeds), "a seed states a verdict or figure"


def test_bootstrap_month_votes_are_the_scores_analyses_gave(client, store, monkeypatch):
    monkeypatch.setitem(sys.modules, "yfinance", fake_yfinance(None))
    from core.config import settings
    add_run(store, "MARUTI", "2026-10-09T04:00:00", 0.7, "BUY",
            agent_scores={"fundamentals": 0.61, "sentiment": 0.40}, drivers=["Dispatch beat"])
    add_run(store, "TATAMOTORS", "2026-10-09T05:00:00", 0.5, "NEUTRAL",
            agent_scores={"fundamentals": 0.71})
    # make every recent row "this month" for the server's 31-day window
    from services.api.routes import ui_data
    monkeypatch.setattr(ui_data, "_rows_since",
                        lambda s, hours, visible: ui_data._only_visible(s.get_all_latest(), visible))

    votes = client.get("/ui/bootstrap").json()["MARKET_MONTH"]["agentVotes"]
    assert {v["n"]: v["v"] for v in votes} == {"Fundamentals": round((0.61 + 0.71) / 2, 2), "Sentiment": 0.40}
    weights = settings.AGENT_WEIGHTS
    assert "Raw Materials" not in {v["n"] for v in votes}, (
        f"no score for raw_materials: its weight {weights.get('raw_materials')} must not stand in")


# ---------------------------------------------------------------------------
# /ui/nifty-ranges
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("key,days", [("1W", 7), ("1M", 30), ("3M", 91), ("6M", 182), ("1Y", 365)])
def test_nifty_ranges_cover_the_named_span_and_date_the_value(client, monkeypatch, key, days):
    monkeypatch.setitem(sys.modules, "yfinance", fake_yfinance({"^NSEI": NSEI}))
    body = client.get(f"/ui/nifty-ranges?range={key}").json()
    last_day = NSEI[-1][0]
    window = [(d, v) for d, v in NSEI if d >= last_day - timedelta(days=days)]
    assert body["index"] == "Nifty 50" and body["range"] == key
    assert body["points"] == [v for _, v in window]
    assert body["value"] == window[-1][1] and body["asOf"] == last_day.isoformat()
    assert body["from"] == window[0][0].isoformat()
    assert body["change"] == round((window[-1][1] - window[0][1]) / window[0][1] * 100, 2)
    if key == "1Y":
        assert len(body["points"]) >= 250, "a year of trading days, not ~180"


def test_nifty_ranges_when_the_fetch_fails_send_no_value(client, monkeypatch):
    monkeypatch.setitem(sys.modules, "yfinance", fake_yfinance(None))
    body = client.get("/ui/nifty-ranges?range=1M").json()
    assert body["points"] == [] and body["value"] is None
    assert body["asOf"] is None and body["change"] is None


def test_an_unknown_range_falls_back_to_one_month(client, monkeypatch):
    monkeypatch.setitem(sys.modules, "yfinance", fake_yfinance({"^NSEI": NSEI}))
    assert client.get("/ui/nifty-ranges?range=5Y").json()["range"] == "1M"


def test_the_pulse_ignores_sectors_that_were_not_fetched():
    from services.api.routes.ui_data import _pulse_from_scores
    assert _pulse_from_scores([], [{"name": "Auto", "pct": None}]) == "No recent data"
    assert _pulse_from_scores([], [{"name": "Auto", "pct": 1.1}, {"name": "IT", "pct": None}]) == "Mostly green"


# ---------------------------------------------------------------------------
# Static guard: sample figures live only in demo-fixtures.js
# ---------------------------------------------------------------------------

FIXTURE_MODULE = "demo-fixtures.js"
# Owner-only screens (PR-001 hides them from members; PR-010 moves them to an
# Operator menu). Their diagnostics are out of this card's scope.
OPERATOR_ONLY = {"analytics.jsx", "rl-monitor.jsx", "rl-data.jsx", "prompt-lab.jsx",
                 "logs.jsx", "tweaks-panel.jsx"}

GUARDS = {
    "the name Aditi": re.compile(r"Aditi", re.I),
    "Run on MARUTI": re.compile(r"Run on MARUTI"),
    "a percentage move with decimals": re.compile(r"(?<![\w.])[+\-−]?\d+\.\d+\s?%"),
    "a comma-grouped figure": re.compile(r"(?<![\w(,.\[])\d{1,3}(?:,\d{2,3})+(?:\.\d+)?(?![\d,])"),
    "a numeric literal with _ separators": re.compile(r"\b\d{1,3}(?:_\d{2,3})+(?:\.\d+)?\b"),
    "a market field set to a number": re.compile(
        r"\b(?:price|change|pct|changePct|totalValue|totalCost|dayChange|dayChangePct|cash|avgPrice"
        r"|currentPrice|score|missedGain|avoidedLoss|realizedLoss)\s*:\s*[+\-]?\d"),
    # The unformatted forms of the same figures (rework 1, review L2). Index
    # levels have four or more digits ("Nifty 500" is a name, not a level).
    "an index name followed by a level": re.compile(
        r"\b(?:Nifty|NIFTY|Sensex|SENSEX)(?:\s+(?:50|[A-Z][A-Za-z]+))?\s+[+\-−]?\d{4,}"),
    "an ungrouped level with decimals": re.compile(r"(?<![\w.#\-])\d{4,6}\.\d{1,2}(?![\d%])"),
    "a bare number as an element's text": re.compile(r">\s*[+\-−]?\d{4,}(?:\.\d+)?\s*<"),
    # A whole-number move: "+1%" or "−2%" anywhere (CSS never writes a plus or a
    # Unicode minus), or a hyphen-minus / unsigned one followed by a word ("-1% on",
    # "1% today"); CSS's "-50%)", "'-10%'", "50% {" and "100%," stay out.
    "a whole-number move in text": re.compile(
        r"(?<![\w.])(?:[+−]\d+\s?%|-\d+\s?%(?=\s+[A-Za-z])|(?<![+\-])\d+\s?%(?=\s+[a-z]))"),
    # Three or more digits, or two with paise: "₹18420", "₹12.50". A one-digit
    # unit figure ("₹4-6Cr/MW", a valuation benchmark in agent task copy) stays out.
    "an ungrouped rupee figure": re.compile(r"₹\s?[+\-−]?(?:\d{3,}|\d{2,}\.\d)"),
}


def scan(name: str, text: str):
    hits = []
    for n, line in enumerate(text.splitlines(), 1):
        stripped = line.strip()
        if stripped.startswith(("//", "*", "/*")):
            continue
        for label, rx in GUARDS.items():
            if rx.search(line):
                hits.append(f"{name}:{n}: {label}: {stripped[:100]}")
    return hits


def customer_facing_files():
    return sorted(p for p in PROTO.iterdir()
                  if p.suffix in {".jsx", ".js", ".html"}
                  and p.name != FIXTURE_MODULE and p.name not in OPERATOR_ONLY)


def test_customer_facing_files_hold_no_sample_figure_or_name():
    files = customer_facing_files()
    assert {"home.jsx", "portfolio.jsx", "data.jsx", "index.html", "agents-page.jsx"} <= {p.name for p in files}
    hits = [h for p in files for h in scan(p.name, p.read_text(encoding="utf-8"))]
    assert hits == [], "\n".join(hits)


@pytest.mark.parametrize("snippet", [
    "<h1>Good afternoon, Aditi.</h1>",
    "<button onClick={go}>Run on MARUTI</button>",
    "<span style={{ color:'#22c55e' }}>+1.24%</span>",
    "oneLiner: 'Auto sector up 1.2% on dispatch beat.',",
    "<span className=\"mono\">22,847</span>",
    "const NOW = 4_82_350;",
    "{ sym:'X', price:12_487.40, change: 1.42, score:0.82 },",
    "summary: { missedGain: 18420, avoidedLoss: 6180 },",
    # the unformatted forms (review L2's probes, then a few more of each)
    "<span className=\"mono\">Nifty Auto 22847</span>",
    "<div>24850.10</div>",
    "<p>Auto sector +1% today.</p>",
    "<span>Missed gain +₹18420</span>",
    "<span>22847</span>",
    "oneLiner: 'Nifty 50 24850 at the close.',",
    "label: 'Sensex 81250.5',",
    "<b>−2%</b>",
    "'Auto sector -1% on weak dispatches'",
    "'Auto sector up 1% today'",
    "<span>₹12.50</span>",
    "`Avoided loss ₹ 6180`",
])
def test_the_guard_catches_each_kind_of_sample(snippet):
    assert scan("probe.jsx", snippet), snippet


def test_the_guard_leaves_styles_alone():
    for line in ("transform:'translate(-50%,-50%)'", "background:'rgba(8,145,178,.28)'",
                 "const lngs = [0,30,60,90,120,150];", "width: (a.v*100)+'%'",
                 "{(p.rate*100).toFixed(0)}%", "{plPct.toFixed(2)}%",
                 # the style and copy forms the unformatted-figure patterns must pass
                 "position:'absolute', top:'-10%', left:'-10%', borderRadius:'50%',",
                 "top:'50%', transform:'translateY(-50%)', color:'var(--ink-3)'",
                 "0%   { background-position: -200% 0; }",
                 "@keyframes sa-pulse { 0%,100% { transform: translate(-50%,-50%) scale(1); } 50% { opacity: .85; } }",
                 "position: absolute; left: 50%; bottom: -8%; transform: translateX(-50%);",
                 "background:'linear-gradient(135deg, #1a4a73 0%, #0e3a4a 50%, #4a1a73 100%)'",
                 "width:'calc(100% - 20px)'",
                 "hint={canTune ? 'Should be ~100%' : undefined}",
                 "label:'EV / MW vs benchmark (₹4-6Cr/MW)', beginner:'cheap if below ₹4Cr/MW.'",
                 "never a ₹0.00 price or a default 0.50 NEUTRAL.",
                 "<SectionHead title=\"Nifty 50\"/>", "the Nifty 500 index",
                 "setTimeout(done, 15000);", "maxWidth:1280,"):
        assert scan("probe.jsx", line) == [], line


def test_the_fixture_module_defines_nothing_outside_demo_mode():
    src = (PROTO / FIXTURE_MODULE).read_text(encoding="utf-8")
    body = src[src.index("(function () {") + len("(function () {"):]
    first = next(l.strip() for l in body.splitlines() if l.strip())
    assert first == "if (!window.saDemoMode) return;", first
    html = (PROTO / "index.html").read_text(encoding="utf-8")
    flag = html.index("window.saDemoMode = new URLSearchParams(location.search).get('demo') === '1';")
    assert flag < html.index('<script src="demo-fixtures.js"></script>') < html.index('type="text/babel"')


def test_no_invented_figures_browser_suite():
    """Runs the real-browser suite (needs node, `npm ci`, and Playwright's Chromium)."""
    node = shutil.which("node")
    if not node:
        pytest.skip("node is not on PATH")
    if not (REPO / "node_modules" / "playwright").exists():
        pytest.skip("node_modules missing: run `npm ci`")
    proc = subprocess.run([node, "--test", "tests/frontend/no_invented_figures.test.mjs"], cwd=REPO,
                          capture_output=True, text=True, encoding="utf-8", timeout=900)
    out = proc.stdout + proc.stderr
    if "Executable doesn't exist" in out:
        pytest.skip("Chromium missing: run `npx playwright install chromium`")
    assert proc.returncode == 0, out[-4000:]

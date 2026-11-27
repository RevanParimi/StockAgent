"""PR-041: the screen's cut graded forward (scripts/screen_cut.py).

Made-up markets whose answers are worked out here from the prices, never from
the report's own arithmetic. Sessions are business days from Monday 6 July
2026, so the Fridays are sessions 4, 9, 14, ...: a screen dated Friday `i`
runs on the Saturday and enters at the close of session `i + 1`.
"""
from __future__ import annotations

import json
import random
import statistics
from datetime import date, timedelta

import pandas as pd
import pytest

from core.config import settings
from scripts import screen_cut as sc

DAYS = [d.date() for d in pd.bdate_range("2026-07-06", periods=80)]
FRIDAYS = [i for i, d in enumerate(DAYS) if d.weekday() == 4]
EIGHT = FRIDAYS[:8]          # entries 5, 10, ..., 40; all matured at 30 sessions


@pytest.fixture(autouse=True)
def _floors(monkeypatch):
    for name, value in (("DISCOVERY_MIN_PRICE", 20.0), ("DISCOVERY_LIQUIDITY_FLOOR_CR", 5.0),
                        ("DISCOVERY_CIRCUIT_STREAK_MAX", 3)):
        monkeypatch.setattr(settings, name, value, raising=False)


def grow(rate, start=100.0, n=len(DAYS)):
    return [start * (1 + rate) ** i for i in range(n)]


def _rows(symbol, closes, *, restated=None, days=DAYS, series="EQ", tv=10.0):
    """One row a session with a close (None = no row that session). `restated`
    {index: previous close} is NSE restating it on an ex-date."""
    out, last = [], None
    for i, (d, close) in enumerate(zip(days, closes)):
        if close is None:
            continue
        prev = (restated or {}).get(i, last if last is not None else close)
        out.append({"symbol": symbol, "series": series, "date": d.isoformat(),
                    "prev_close": prev, "open": close, "high": close * 1.01,
                    "low": close * 0.99, "close": close, "volume": 1000,
                    "traded_value_cr": tv, "delivery_qty": 500, "delivery_pct": 50.0})
        last = close
    return out


def _screen(i, candidates, *, rejected=None, run="saturday", ranks=None):
    """The record the screen persists for session `i`. run: "saturday", None
    (a file from before the run day was recorded) or a date."""
    day = DAYS[i]
    record = {"screen_date": day.isoformat(), "universe_size": 100, "shortlist_size": 80,
              "candidates": [{"symbol": s, "close": 100.0, "composite": 0.9,
                              "signal_ranks": (ranks or {}).get(s, {})} for s in candidates],
              "rejected": rejected or {}, "dark_signals": [], "degraded_checks": []}
    if run == "saturday":
        record["run_date"] = (day + timedelta(days=1)).isoformat()
    elif run is not None:
        record["run_date"] = run.isoformat()
    return record


def _market(root, prices, screens, *, sessions=len(DAYS), unlisted=(), funds=()):
    """prices: {symbol: closes} or {symbol: row dicts}; screens: [(i, record)]."""
    eod = root / settings.DISCOVERY_BHAVCOPY_DIR
    eod.mkdir(parents=True)
    rows = []
    for sym, value in prices.items():
        rows += value if value and isinstance(value[0], dict) else _rows(sym, value)
    frame = pd.DataFrame(rows)
    for d in DAYS[:sessions]:
        frame[frame["date"] == d.isoformat()].to_parquet(eod / f"{d.isoformat()}.parquet",
                                                         index=False)
    disc = root / settings.DISCOVERY_DATA_DIR
    (disc / "screens").mkdir(parents=True)
    securities = {s: {"series": "EQ", "isin": "INF000000001" if s in funds
                      else "INE000000001"} for s in prices if s not in unlisted}
    (disc / "listing.json").write_text(json.dumps({"securities": securities}))
    for i, record in screens:
        (disc / "screens" / f"{DAYS[i].isoformat()}_screen.json").write_text(
            json.dumps(record))
    return root


def _pct(rate, sessions):
    return ((1 + rate) ** sessions - 1) * 100


def _one(report, i):
    return next(s for s in report["screens"] if s["screen"] == DAYS[i].isoformat())


# ---------------------------------------------------------------------------
# The card's invariants
# ---------------------------------------------------------------------------
def test_a_cut_that_picks_the_stocks_that_later_rise_leads(tmp_path):
    prices = {"WIN1": grow(0.01), "WIN2": grow(0.01), "FLAT": grow(0.0), "LOSE": grow(-0.005)}
    root = _market(tmp_path, prices, [(i, _screen(i, ["WIN1", "WIN2"])) for i in EIGHT])
    report = sc.build_report(root)
    assert [s["screen"] for s in report["screens"]] == [DAYS[i].isoformat() for i in EIGHT]
    for h in (10, 30):
        rise, rest = _pct(0.01, h), (0.0 + _pct(-0.005, h)) / 2
        row = _one(report, EIGHT[0])["horizons"][h]
        assert row["cut"] == {"n": 2, "left_out": 0, "restated": 0,
                              "mean": pytest.approx(rise, abs=0.006),
                              "median": pytest.approx(rise, abs=0.006)}
        assert row["rest"]["n"] == 2
        assert row["rest"]["mean"] == pytest.approx(rest, abs=0.006)
        assert row["lead"] == pytest.approx(rise - rest, abs=0.011)
    pooled = report["pooled"][30]
    assert (pooled["screens"], pooled["led"], pooled["led_pct"]) == (8, 8, 100.0)
    assert pooled["mean_lead"] == pytest.approx(
        _pct(0.01, 30) - _pct(-0.005, 30) / 2, abs=0.011)
    assert (pooled["cut_n"], pooled["rest_n"]) == (16, 16)
    assert report["verdict"] == sc.CHOOSES


def test_a_cut_that_picks_the_stocks_that_later_fall_does_not_choose(tmp_path):
    prices = {"BAD": grow(-0.005), "FLAT": grow(0.0), "WIN": grow(0.01)}
    root = _market(tmp_path, prices, [(i, _screen(i, ["BAD"])) for i in EIGHT])
    report = sc.build_report(root)
    assert report["pooled"][30]["mean_lead"] < 0
    assert report["pooled"][30]["led"] == 0
    assert report["verdict"] == sc.DOES_NOT


def test_a_cut_that_picks_at_random_does_not_lead(tmp_path):
    """150 stocks whose daily moves are drawn at random, as large as a real
    stock's (about 2% a day); each week's 50 are drawn without reading them.
    Some screens lead and some trail, and over eight the lead stays small."""
    moves = random.Random(41)
    picks = random.Random(7)
    prices = {}
    for k in range(150):
        closes = [100.0]
        for _ in range(len(DAYS) - 1):
            closes.append(closes[-1] * (1 + moves.uniform(-0.035, 0.035)))
        prices[f"S{k:03d}"] = closes
    screens = [(i, _screen(i, picks.sample(sorted(prices), 50))) for i in EIGHT]
    report = sc.build_report(_market(tmp_path, prices, screens))
    leads = [s["horizons"][30]["lead"] for s in report["screens"]]
    assert len(leads) == 8 and min(leads) < 0 < max(leads)
    assert abs(report["pooled"][30]["mean_lead"]) < 1.5
    assert report["verdict"] != sc.CHOOSES


def test_a_stock_the_guards_rejected_is_in_neither_group(tmp_path):
    prices = {"PICK": grow(0.0), "FLAT": grow(0.0), "JUNK": grow(0.03)}
    screens = [(i, _screen(i, ["PICK"], rejected={"JUNK": ["low_float_mcap"]}))
               for i in EIGHT]
    report = sc.build_report(_market(tmp_path, prices, screens))
    row = _one(report, EIGHT[0])["horizons"][30]
    assert (row["cut"]["n"], row["rest"]["n"]) == (1, 1)
    assert row["rest"]["mean"] == 0.0 and row["lead"] == 0.0
    # Shown beside them, on its own.
    assert row["rejected"]["n"] == 1
    assert row["rejected"]["mean"] == pytest.approx(_pct(0.03, 30), abs=0.006)
    assert report["pooled"][30]["rejected"]["lead_over_rest"] == pytest.approx(
        _pct(0.03, 30), abs=0.011)
    assert report["verdict"] == sc.DOES_NOT            # a lead of exactly 0


def test_a_bonus_is_not_read_as_a_fall(tmp_path):
    """1 share at 100 becomes 2 shares at 55 on session 20: the holder is up
    10%, not down 45%."""
    bonus = [100.0] * 20 + [55.0] * (len(DAYS) - 20)
    prices = {"PICK": grow(0.0), "FLAT": grow(0.0),
              "BONUS": _rows("BONUS", bonus, restated={20: 50.0})}
    report = sc.build_report(_market(tmp_path, prices, [(4, _screen(4, ["PICK"]))]))
    row = _one(report, 4)["horizons"][30]          # sessions 5 to 35: across the ex-date
    assert row["rest"]["mean"] == pytest.approx((0.0 + 10.0) / 2, abs=0.006)
    assert row["lead"] == pytest.approx(-5.0, abs=0.006)
    # NSE restated a close: marked, and the lead without it is shown beside.
    assert (row["rest"]["restated"], row["cut"]["restated"]) == (1, 0)
    assert row["lead_without_restated"] == 0.0


# ---------------------------------------------------------------------------
# Dates: entry, maturity, floors as of the screen's date
# ---------------------------------------------------------------------------
def test_entry_is_the_close_after_the_run_not_the_screens_close(tmp_path):
    """PICK jumps 20% from the screen's close (session 4) to the entry close
    (session 5): that move was not there to be had."""
    jump = [100.0] * 5 + [120.0] * (len(DAYS) - 5)
    prices = {"PICK": jump, "FLAT": grow(0.0)}
    report = sc.build_report(_market(tmp_path, prices, [(4, _screen(4, ["PICK"]))]))
    one = _one(report, 4)
    assert (one["ran"], one["entry"]) == ((DAYS[4] + timedelta(days=1)).isoformat(),
                                          DAYS[5].isoformat())
    assert one["horizons"][10]["exit"] == DAYS[15].isoformat()
    assert one["horizons"][10]["cut"]["mean"] == 0.0


def test_a_file_without_a_run_day_is_taken_as_that_saturdays_run(tmp_path):
    """Session 8 is a Thursday: its screen ran on Saturday and enters the
    Monday after (session 10), not the Friday (session 9)."""
    prices = {"PICK": grow(0.01), "FLAT": grow(0.0)}
    assert DAYS[8].weekday() == 3
    report = sc.build_report(_market(tmp_path, prices, [(8, _screen(8, ["PICK"], run=None))]))
    one = _one(report, 8)
    assert one["run_recorded"] is False
    assert one["ran"] == "2026-07-18" and one["entry"] == DAYS[10].isoformat()
    assert any("record no run day" in n for n in report["notes"])


def test_a_weekday_run_enters_the_session_after_it_and_is_named(tmp_path):
    prices = {"PICK": grow(0.01), "FLAT": grow(0.0)}
    ran = DAYS[7]                                    # a Wednesday
    report = sc.build_report(_market(tmp_path, prices, [(6, _screen(6, ["PICK"], run=ran))]))
    assert _one(report, 6)["entry"] == DAYS[8].isoformat()
    assert any("other than Saturday" in n and DAYS[6].isoformat() in n
               for n in report["notes"])


def test_a_horizon_counts_only_when_matured(tmp_path):
    prices = {"PICK": grow(0.01), "FLAT": grow(0.0)}
    screens = [(4, _screen(4, ["PICK"]))]
    # Entry is session 5; its 10th session after is 15: 16 stored sessions.
    short = sc.build_report(_market(tmp_path / "a", prices, screens, sessions=15))
    assert _one(short, 4)["horizons"] == {}
    assert short["pooled"][10] == {"screens": 0}
    just = sc.build_report(_market(tmp_path / "b", prices, screens, sessions=16))
    assert list(_one(just, 4)["horizons"]) == [10]
    assert _one(just, 4)["horizons"][10]["exit"] == DAYS[15].isoformat()


def test_the_floors_are_read_as_of_the_screens_date(tmp_path):
    n = len(DAYS)
    prices = {
        "PICK": grow(0.0),
        "FLAT": grow(0.0),
        "RISES_LATER": [10.0] * 10 + [100.0] * (n - 10),     # under Rs 20 on the date
        "FALLS_LATER": [100.0] * 10 + [10.0] * (n - 10),     # inside on the date
        "NOT_TRADING": [100.0] * 4 + [None] + [100.0] * (n - 5),   # no session 4
        "A_FUND": grow(0.02),
        "GONE": grow(0.02),                                   # not in today's listing
        "PENNY_GONE": [10.0] * n,                             # unlisted and a penny
    }
    root = _market(tmp_path, prices, [(4, _screen(4, ["PICK"]))],
                   unlisted=("GONE", "PENNY_GONE"), funds=("A_FUND",))
    one = _one(sc.build_report(root), 4)
    assert one["rest"] == 2                                   # FLAT and FALLS_LATER
    assert one["not_in_listing"] == 1                         # GONE alone
    assert one["horizons"][10]["rest"]["mean"] == pytest.approx((0 - 90.0) / 2, abs=0.006)


def test_no_close_at_the_exit_leaves_the_stock_out_and_is_counted(tmp_path):
    halted = [100.0] * 12 + [None] * (len(DAYS) - 12)         # nothing after session 11
    prices = {"PICK": grow(0.01), "HALTED_PICK": halted, "FLAT": grow(0.0),
              "HALTED": halted}
    root = _market(tmp_path, prices, [(4, _screen(4, ["PICK", "HALTED_PICK"]))])
    row = _one(sc.build_report(root), 4)["horizons"][10]
    assert (row["cut"]["n"], row["cut"]["left_out"]) == (1, 1)
    assert (row["rest"]["n"], row["rest"]["left_out"]) == (1, 1)
    assert row["cut"]["mean"] == pytest.approx(_pct(0.01, 10), abs=0.006)


def test_a_run_day_before_the_screens_session_is_not_believed(tmp_path):
    """Believed, it would enter before the prices the screen read: a look-ahead."""
    prices = {"PICK": grow(0.01), "FLAT": grow(0.0)}
    record = _screen(9, ["PICK"], run=DAYS[6])
    one = _one(sc.build_report(_market(tmp_path, prices, [(9, record)])), 9)
    assert one["run_recorded"] is False and one["entry"] == DAYS[10].isoformat()


@pytest.mark.parametrize("bad", [float("nan"), 0.0])
def test_an_unreadable_close_leaves_that_stock_out_not_the_verdict(tmp_path, bad):
    """The bhavcopy parser stores a figure it cannot read as blank."""
    broken = grow(0.0)
    broken[20] = bad                          # inside the first screens' windows
    prices = {"WIN": grow(0.01), "FLAT": grow(0.0), "BROKEN": broken}
    report = sc.build_report(_market(tmp_path, prices,
                                     [(i, _screen(i, ["WIN"])) for i in EIGHT]))
    row = _one(report, EIGHT[0])["horizons"][30]
    assert (row["rest"]["n"], row["rest"]["left_out"], row["rest"]["mean"]) == (1, 1, 0.0)
    assert report["pooled"][30]["mean_lead"] == pytest.approx(_pct(0.01, 30), abs=0.011)
    assert report["verdict"] == sc.CHOOSES


def test_a_companys_debt_under_its_ticker_is_not_read_as_its_price(tmp_path):
    """PICK and FLAT each also have a debt row (series N1) every day, near
    Rs 1,000, written first on some days and last on others; DEBT_ONLY has
    nothing but debt rows."""
    def debt(symbol):
        return _rows(symbol, grow(0.002, 1000.0), series="N1", tv=0.01)

    prices = {"PICK": debt("PICK")[:40] + _rows("PICK", grow(0.01)) + debt("PICK")[40:],
              "FLAT": _rows("FLAT", grow(0.0)) + debt("FLAT"),
              "DEBT_ONLY": debt("DEBT_ONLY")}
    report = sc.build_report(_market(tmp_path, prices, [(4, _screen(4, ["PICK"]))]))
    one = _one(report, 4)
    row = one["horizons"][30]
    assert one["rest"] == 1                                       # FLAT alone
    assert row["rest"]["mean"] == 0.0
    assert row["cut"]["mean"] == pytest.approx(_pct(0.01, 30), abs=0.006)
    assert row["cut"]["restated"] == row["rest"]["restated"] == 0
    assert any(n.startswith(f"{2 * len(DAYS)} price rows shared") for n in report["notes"])


def test_the_equity_row_is_kept_over_another_equity_series_of_the_day():
    frame = pd.DataFrame([
        {"symbol": "A", "series": "BE", "date": "2026-07-06", "close": 1.0},
        {"symbol": "A", "series": "EQ", "date": "2026-07-06", "close": 2.0},
        {"symbol": "A", "series": "BE", "date": "2026-07-07", "close": 3.0},
        {"symbol": "A", "series": "BL", "date": "2026-07-07", "close": 9.0},
    ])
    kept, other = sc.one_row_a_day(frame)
    assert sorted(zip(kept["date"], kept["close"])) == [("2026-07-06", 2.0),
                                                        ("2026-07-07", 3.0)]
    assert other == 2


def test_two_screens_that_enter_on_one_session_are_one(tmp_path):
    """A run by hand on Sunday over Thursday's session beside Saturday's over
    Friday's: both enter on Monday; the later screen stands."""
    prices = {"A": grow(0.01), "B": grow(0.0), "C": grow(0.0)}
    sunday = DAYS[4] + timedelta(days=2)
    screens = [(3, _screen(3, ["A"], run=sunday)), (4, _screen(4, ["B"]))]
    report = sc.build_report(_market(tmp_path, prices, screens))
    assert [s["screen"] for s in report["screens"]] == [DAYS[4].isoformat()]
    assert any(f"screen of {DAYS[3]}" in n and "only the later one" in n
               for n in report["notes"])


def test_screens_that_cannot_be_graded_are_named(tmp_path):
    prices = {"PICK": grow(0.0), "FLAT": grow(0.0)}
    screens = [(4, _screen(4, [])), (9, _screen(9, ["PICK"])), (79, _screen(79, ["PICK"]))]
    root = _market(tmp_path, prices, screens)
    (root / settings.DISCOVERY_DATA_DIR / "screens" / "2026-07-15_screen.json").write_text("{")
    report = sc.build_report(root)
    assert [s["screen"] for s in report["screens"]] == [DAYS[9].isoformat()]
    text = " | ".join(report["notes"])
    assert f"screen of {DAYS[4]}: no candidates" in text
    assert f"screen of {DAYS[79]}: no session stored after its run yet" in text
    assert "2026-07-15_screen.json could not be read" in text


def test_a_screen_whose_session_is_not_stored_is_not_graded(tmp_path):
    prices = {"PICK": grow(0.0), "FLAT": grow(0.0)}
    root = _market(tmp_path, prices, [(4, _screen(4, ["PICK"])), (9, _screen(9, ["PICK"]))])
    (root / settings.DISCOVERY_BHAVCOPY_DIR / f"{DAYS[9]}.parquet").unlink()
    report = sc.build_report(root)
    assert [s["screen"] for s in report["screens"]] == [DAYS[4].isoformat()]
    assert any(f"screen of {DAYS[9]}" in n and "not in the price store" in n
               for n in report["notes"])


# ---------------------------------------------------------------------------
# Groups, pooling and the rule
# ---------------------------------------------------------------------------
def test_the_lead_is_of_means_and_the_medians_are_shown_beside_it(tmp_path):
    """One candidate triples the others: the mean lead is up, the median is not."""
    prices = {"BIG": grow(0.03), "SMALL1": grow(-0.002), "SMALL2": grow(-0.002),
              "FLAT": grow(0.0)}
    root = _market(tmp_path, prices, [(4, _screen(4, ["BIG", "SMALL1", "SMALL2"]))])
    row = _one(sc.build_report(root), 4)["horizons"][30]
    big, small = _pct(0.03, 30), _pct(-0.002, 30)
    assert row["lead"] == pytest.approx((big + 2 * small) / 3, abs=0.011)
    assert row["median_gap"] == pytest.approx(small, abs=0.011)
    assert row["lead"] > 0 > row["median_gap"]


def test_the_rank_halves_split_the_list_in_order(tmp_path):
    prices = {"R1": grow(0.01), "R2": grow(0.01), "R3": grow(0.0), "R4": grow(0.0),
              "R5": grow(-0.01), "FLAT": grow(0.0)}
    root = _market(tmp_path, prices, [(4, _screen(4, ["R1", "R2", "R3", "R4", "R5"]))])
    row = _one(sc.build_report(root), 4)["horizons"][10]
    assert (row["top_half"]["n"], row["second_half"]["n"]) == (3, 2)    # 1-3 and 4-5
    assert row["top_half"]["mean"] == pytest.approx(2 * _pct(0.01, 10) / 3, abs=0.006)
    assert row["second_half"]["mean"] == pytest.approx(_pct(-0.01, 10) / 2, abs=0.006)


def _graded(lead, cut_n=40, candidates=40):
    group = {"n": cut_n, "left_out": 0, "restated": 0, "mean": lead, "median": lead}
    zero = {"n": 100, "left_out": 0, "restated": 0, "mean": 0.0, "median": 0.0}
    return {"candidates": candidates,
            "horizons": {30: {"cut": group, "rest": zero, "rejected": zero,
                              "top_half": zero, "second_half": zero, "lead": lead,
                              "median_gap": 0.0, "lead_without_restated": lead}}}


def test_over_the_screens_every_screen_weighs_the_same():
    leads = [5.0, -1.0, 0.0, 2.0, 2.5, 3.0, 1.5, 4.2]
    # The first screen holds 40 times the stocks of the others: no extra weight.
    screens = [_graded(x, cut_n=1600 if i == 0 else 40) for i, x in enumerate(leads)]
    pooled = sc.pool(screens, 30)
    assert pooled["mean_lead"] == 2.15                  # 17.2 / 8
    assert pooled["median_lead"] == 2.25                # (2.0 + 2.5) / 2
    assert (pooled["led"], pooled["led_pct"]) == (6, 75.0)      # 0.0 is not a lead
    assert (pooled["lowest_lead"], pooled["highest_lead"]) == (-1.0, 5.0)
    assert "by_cut_size" not in pooled                  # all one size
    assert sc.decide(pooled)[0] == sc.CHOOSES


def test_the_two_cut_sizes_are_shown_apart_and_pooled_for_the_rule():
    screens = ([_graded(4.0, candidates=40), _graded(2.0, candidates=38)]
               + [_graded(-3.0, candidates=60)])
    pooled = sc.pool(screens, 30)
    assert pooled["mean_lead"] == 1.0                   # (4 + 2 - 3) / 3
    assert pooled["by_cut_size"] == {
        "cuts of 40 or fewer": {"screens": 2, "mean_lead": 3.0, "median_lead": 3.0,
                                "led": 2, "led_pct": 100.0},
        "cuts above 40": {"screens": 1, "mean_lead": -3.0, "median_lead": -3.0,
                          "led": 0, "led_pct": 0.0}}


def test_a_few_distorted_returns_can_be_seen(tmp_path):
    """A candidate falls 90% with NSE restating a close on the way (an action
    chaining did not undo): the verdict reads it, and the output names it and
    shows the lead without it."""
    broken = [100.0] * 20 + [10.0] * (len(DAYS) - 20)
    prices = {"GOOD": grow(0.01), "FLAT": grow(0.0),
              "ODD": _rows("ODD", broken, restated={20: 100.0, 21: 12.0})}
    report = sc.build_report(_market(tmp_path, prices,
                                     [(4, _screen(4, ["GOOD", "ODD"]))]))
    row = _one(report, 4)["horizons"][30]
    odd = (0.1 * (10.0 / 12.0) - 1) * 100          # 10/100, then 10/12 on the restatement
    assert row["lead"] == pytest.approx((_pct(0.01, 30) + odd) / 2, abs=0.011)
    assert row["cut"]["restated"] == 1
    assert row["lead_without_restated"] == pytest.approx(_pct(0.01, 30), abs=0.011)
    assert _one(report, 4)["large_moves"] == [
        {"symbol": "ODD", "return_pct": round(odd, 1), "raw_pct": -90.0, "restated": True}]
    text = sc.render(report)
    assert "ODD" in text and "restated close; unchained -90.0%" in text
    assert "restated closes: cut 1, rest 0" in text


def _pooled(n=10, mean=3.0, median=3.0, led=8):
    return {"screens": n, "mean_lead": mean, "median_lead": median, "led": led,
            "led_pct": round(100.0 * led / n, 1)}


@pytest.mark.parametrize("figures, verdict", [
    (_pooled(), sc.CHOOSES),
    (_pooled(mean=1.01, median=1.01, led=6), sc.CHOOSES),      # exactly 60% led
    (_pooled(mean=1.00), sc.UNDECIDED),                        # not above +1
    (_pooled(median=1.00), sc.UNDECIDED),
    (_pooled(median=-4.0), sc.UNDECIDED),
    (_pooled(led=5), sc.UNDECIDED),                            # 50% led
    (_pooled(n=17, led=10), sc.UNDECIDED),                     # 58.8% led
    (_pooled(mean=0.0), sc.DOES_NOT),                          # at 0
    (_pooled(mean=-2.0, median=5.0, led=9), sc.DOES_NOT),      # the mean decides this
    (_pooled(mean=0.01), sc.UNDECIDED),
    (_pooled(n=8, led=8), sc.CHOOSES),
    (_pooled(n=7, led=7), sc.UNDECIDED),                       # too few screens
    (_pooled(n=7, mean=-9.0, median=-9.0, led=0), sc.UNDECIDED),
    ({"screens": 0}, sc.UNDECIDED),
])
def test_the_rule_as_the_card_fixes_it(figures, verdict):
    assert sc.decide(figures)[0] == verdict


def test_the_rule_is_read_at_thirty_sessions_only(tmp_path):
    """Each week's candidate rises 2% a session for 10 sessions from its entry
    and then falls 3% a session: every 10-session lead is up (the rule would
    say chooses), every 30-session lead is down."""
    prices = {"FLAT": grow(0.0)}
    screens = []
    for k, i in enumerate(EIGHT):
        entry = i + 1
        closes = [100.0] * (entry + 1)
        for n in range(1, len(DAYS) - entry):
            closes.append(closes[-1] * (1.02 if n <= 10 else 0.97))
        prices[f"P{k}"] = closes
        # The other weeks' stocks are kept out of this screen's rest (as if
        # its guards rejected them), so the rest is the flat stock alone.
        others = {f"P{j}": ["low_liquidity"] for j in range(len(EIGHT)) if j != k}
        screens.append((i, _screen(i, [f"P{k}"], rejected=others)))
    report = sc.build_report(_market(tmp_path, prices, screens))
    ten, thirty = report["pooled"][10], report["pooled"][30]
    assert sc.decide(ten)[0] == sc.CHOOSES
    assert (thirty["screens"], thirty["led"]) == (8, 0)
    assert report["verdict"] == sc.DOES_NOT


def test_the_signals_of_the_candidates_that_trailed(tmp_path):
    prices = {"UP": grow(0.01), "DOWN1": grow(-0.01), "DOWN2": grow(-0.01), "FLAT": grow(0.0)}
    ranks = {"UP": {"momentum": 0.5, "delivery_surge": 0.9},
             "DOWN1": {"momentum": 0.95, "delivery_surge": 0.2},
             "DOWN2": {"momentum": 0.85}}
    root = _market(tmp_path, prices, [(4, _screen(4, ["UP", "DOWN1", "DOWN2"], ranks=ranks))])
    table = {r["signal"]: r for r in sc.build_report(root)["signals"]}
    assert table["momentum"]["trailed"] == {"n": 2, "mean_rank": 0.9, "top_fifth_pct": 100.0}
    assert table["momentum"]["kept_up"] == {"n": 1, "mean_rank": 0.5, "top_fifth_pct": 0.0}
    assert table["delivery_surge"]["trailed"] == {"n": 1, "mean_rank": 0.2,
                                                  "top_fifth_pct": 0.0}
    assert table["delivery_surge"]["kept_up"]["top_fifth_pct"] == 100.0


# ---------------------------------------------------------------------------
# The output, and that the report only reads
# ---------------------------------------------------------------------------
def test_the_output_states_its_limits_its_counts_and_the_money(tmp_path, capsys):
    prices = {"WIN": grow(0.01), "FLAT": grow(0.0), "LOSE": grow(-0.005)}
    root = _market(tmp_path, prices, [(i, _screen(i, ["WIN"])) for i in EIGHT])
    assert sc.main(["--root", str(root)]) == 0
    text = capsys.readouterr().out
    for phrase in ("One market period", "The floors outside the shortlist are the bhavcopy's",
                   "far fewer independent tests", "left out of the rest",
                   "THE CUT CHOOSES", "every screen weighted equally"):
        assert phrase.lower() in text.lower(), phrase
    assert "cut +34.78 (n 8), rest -6.98 (n 16)" in text
    assert "the screens' leads run from +41.76 to +41.76" in text
    # One position of Rs 3,20,000: +34.78% of it, and -6.98% of it.
    assert "in a candidate Rs 1,11,296, in a stock of the rest -Rs 22,336" in text
    assert sum(1 for line in text.splitlines()
               if line.startswith(DAYS[EIGHT[0]].isoformat() + " ")) >= 3


def test_it_writes_nothing(tmp_path, capsys):
    """Under the suite's hermetic boundary, which also fails the test on any
    network call."""
    prices = {"WIN": grow(0.01), "FLAT": grow(0.0)}
    root = _market(tmp_path, prices, [(i, _screen(i, ["WIN"])) for i in EIGHT])
    before = {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in root.rglob("*")
              if p.is_file()}
    dirs = {p for p in root.rglob("*") if p.is_dir()}
    sc.main(["--root", str(root)])
    capsys.readouterr()
    sc.main(["--root", str(root), "--json"])
    assert json.loads(capsys.readouterr().out)["verdict"] == sc.CHOOSES
    assert {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in root.rglob("*")
            if p.is_file()} == before
    assert {p for p in root.rglob("*") if p.is_dir()} == dirs


def test_an_empty_root_is_reported_not_raised(tmp_path, capsys):
    assert sc.main(["--root", str(tmp_path)]) == 0
    assert "Not measured: no stored weekly screen" in capsys.readouterr().out
    assert list(tmp_path.iterdir()) == []


def test_end_stops_at_a_session_and_drops_later_screens(tmp_path):
    prices = {"PICK": grow(0.01), "FLAT": grow(0.0)}
    root = _market(tmp_path, prices, [(4, _screen(4, ["PICK"])), (29, _screen(29, ["PICK"]))])
    report = sc.build_report(root, end=DAYS[20])
    assert report["sessions_to"] == DAYS[20].isoformat()
    assert [s["screen"] for s in report["screens"]] == [DAYS[4].isoformat()]
    assert list(_one(report, 4)["horizons"]) == [10]
    assert not any(DAYS[29].isoformat() in n for n in report["notes"])    # not even named


def test_the_rest_is_the_screens_own_floors(tmp_path, monkeypatch):
    """The rest holds exactly what the screen's own universe and bhavcopy
    guards would keep (its other guards, dark, keep every stock)."""
    import core.discovery.guards as guards
    from core.discovery.universe import build_universe
    monkeypatch.setattr(guards, "pledge_snapshots", lambda symbols: {})
    monkeypatch.setattr(guards, "surveillance_list", lambda session: (None, None))
    monkeypatch.setattr(guards, "float_mcap_cr", lambda symbol: None)
    rows = (_rows("PICK", grow(0.0)) + _rows("OKAY", grow(0.0))
            + _rows("PENNY", grow(0.0, 10.0)) + _rows("THIN", grow(0.0), tv=1.0)
            + _rows("TTWO", grow(0.0), series="BE"))
    prices = {sym: [r for r in rows if r["symbol"] == sym]
              for sym in ("PICK", "OKAY", "PENNY", "THIN", "TTWO")}
    root = _market(tmp_path, prices, [(4, _screen(4, ["PICK"]))])
    window = pd.DataFrame([r for r in rows if r["date"] <= DAYS[4].isoformat()])
    passed, _rejected, _degraded = guards.apply_guards(build_universe(window), window)
    assert _one(sc.build_report(root), 4)["rest"] == len(set(passed) - {"PICK"}) == 1

"""IPO audit lane (PI Prospect, IPO-4c) — offline, deterministic.

These are invariant tests, not implementation-shaped ones. The four that
matter are: the price identity (entry IS the issue price and return_pct falls
out of it), the horizon identity (horizon 1 IS the listing day), the
scoreability rule (only the listing-day lean, only once the book closed, only
for a lean that asserts a direction), and containment (an IPO row can never
move a number in the advice report).

Nothing here touches the network, the verdict store's real directory, yfinance
or an LLM: both stores live under tmp_path and the price and benchmark legs
are stubs.
"""
import json
from datetime import date

import pytest

from backend.shared.schemas.audit import AuditOutcome
from core.audit.outcomes import grade_due, grade_ipo_lane
from core.audit.rules import is_ipo_correct
from core.audit.store import AuditOutcomeStore
from core.config import settings
from core.intelligence.rl.nse_calendar import trading_dates
from core.ipo.history import HORIZONS_TD, IpoRecord
from core.ipo.hype import HypeReading
from core.ipo.listing import listing_facts
from core.ipo.verdict import IpoVerdict, ShortView
from core.ipo.verdicts import IpoVerdictStore

UID = settings.PORTFOLIO_DEFAULT_USER_ID
LISTING = date(2026, 3, 4)          # a Wednesday, an NSE trading day
ISSUE_PRICE = 100.0


# ───────────────────────────── fixtures ──────────────────────────────────

class _Bench:
    """A flat benchmark: excess == return, so every expectation below is
    arithmetic the reader can do in their head."""

    def __init__(self, pct=0.0):
        self.pct = pct

    def pct_change(self, a, b):
        return self.pct

    def close_on(self, d):
        return 20000.0


def _prices(exit_close=110.0, fails=()):
    def _fn(symbol, on):
        if symbol in fails:
            raise ValueError(f"no price for {symbol}")
        return ISSUE_PRICE if on < LISTING else exit_close
    return _fn


class _Spine:
    """Stands in for IpoHistoryStore."""

    def __init__(self, *rows):
        self._rows = list(rows)

    def load_all(self):
        return self._rows


def _spine(symbol="VARMORA", listing_date=LISTING.isoformat(),
           issue_price=ISSUE_PRICE):
    return _Spine(IpoRecord(symbol=symbol, listing_date=listing_date,
                            issue_price=issue_price))


def _seed_verdict(tmp_path, *, symbol="VARMORA", close_date="2026-02-27",
                  lean="strong", evidenced=True, written_at="2026-02-28T13:30:00+00:00",
                  quadrant="genuine_star", demand=82.0):
    store = IpoVerdictStore(base_dir=str(tmp_path / "ipo"))
    store.append(
        IpoVerdict(symbol=symbol, close_date=close_date,
                   as_of="2026-02-26T13:45:00+00:00", state="closed",
                   short=ShortView(lean=lean, evidenced=evidenced,
                                   basis="test"),
                   quadrant=quadrant, demand=demand),
        HypeReading(symbol=symbol, demand=demand),
        written_at=written_at)
    return store


def _run(tmp_path, *, on=date(2027, 6, 30), spine=None, bench=None,
         price_fn=None, user_id=UID, cache_path=None):
    return grade_ipo_lane(
        on, user_id, base_dir=str(tmp_path), verdicts_dir=str(tmp_path / "ipo"),
        history_store=spine if spine is not None else _spine(),
        cache_path=cache_path, bench=bench or _Bench(),
        price_fn=price_fn or _prices())


def _rows(tmp_path, user_id=UID):
    return [r for r in AuditOutcomeStore(user_id=user_id, base_dir=str(tmp_path)).load_all()
            if r.lane == "ipo"]


# ───────────────────────── the price identity ────────────────────────────

def test_entry_close_is_the_issue_price_and_return_falls_out_of_it(tmp_path):
    _seed_verdict(tmp_path)
    out = _run(tmp_path, price_fn=_prices(exit_close=137.5))

    assert out["graded"] == len(HORIZONS_TD)
    rows = _rows(tmp_path)
    assert rows, "the lane wrote nothing"
    for r in rows:
        assert r.entry_close == ISSUE_PRICE
        assert r.exit_close == 137.5
        # The identity the whole lane exists to record: the move from what the
        # subscriber PAID, not from any close.
        assert r.return_pct == pytest.approx(
            (r.exit_close / ISSUE_PRICE - 1.0) * 100.0, abs=1e-4)
        assert r.excess_pct == pytest.approx(r.return_pct - r.bench_pct, abs=1e-4)


def test_a_zero_or_absent_issue_price_is_never_graded_as_one(tmp_path):
    _seed_verdict(tmp_path)
    for price in (0.0, None):
        out = _run(tmp_path, spine=_spine(issue_price=price))
        assert out["graded"] == 0
        assert out["awaiting_listing"] == 1
        assert out["skipped_unpriceable"] == 0
    assert _rows(tmp_path) == []


# ──────────────────────── the horizon identity ───────────────────────────

def test_horizon_one_is_the_listing_day_itself(tmp_path):
    _seed_verdict(tmp_path)
    _run(tmp_path)
    first = [r for r in _rows(tmp_path) if r.horizon_td == 1]
    assert len(first) == 1
    assert first[0].graded_on == LISTING.isoformat()


def test_every_horizon_counts_trading_days_inclusive_of_listing_day(tmp_path):
    _seed_verdict(tmp_path)
    _run(tmp_path)
    for r in _rows(tmp_path):
        # Counted with a DIFFERENT calendar function than the lane uses, so
        # this cannot pass by sharing the lane's own off-by-one.
        sessions = trading_dates(LISTING, date.fromisoformat(r.graded_on))
        assert len(sessions) == r.horizon_td


def test_a_horizon_that_has_not_matured_is_not_graded(tmp_path):
    _seed_verdict(tmp_path)
    # Five sessions after listing: horizons 1 and 5 are due, the rest are not.
    out = _run(tmp_path, on=trading_dates(LISTING, date(2026, 3, 31))[4])
    assert out["graded"] == 2
    assert {r.horizon_td for r in _rows(tmp_path)} == {1, 5}
    assert out["skipped_unpriceable"] == 0      # not-yet-due is not a failure


# ───────────────────────── what may be scored ────────────────────────────

@pytest.mark.parametrize("lean,evidenced,expected", [
    ("strong", True, True),      # +10% excess, the lean held
    ("weak", True, False),       # +10% excess, the lean did not
    ("mixed", True, None),       # asserts no direction
    (None, True, None),          # dark demand asserts nothing at all
    ("strong", False, None),     # T-1 read: the book was still open
    ("weak", False, None),
])
def test_only_an_evidenced_directional_lean_is_scored_and_only_at_listing_day(
        tmp_path, lean, evidenced, expected):
    _seed_verdict(tmp_path, lean=lean, evidenced=evidenced)
    _run(tmp_path, price_fn=_prices(exit_close=110.0))

    rows = {r.horizon_td: r for r in _rows(tmp_path)}
    assert len(rows) == len(HORIZONS_TD)
    assert rows[1].correct is expected
    # Every longer horizon is RECORDED, never SCORED: the verdict's long view
    # is hard-wired dark, so a claim there would be invented.
    for td in HORIZONS_TD[1:]:
        assert rows[td].correct is None
        assert rows[td].excess_pct is not None


def test_a_weak_lean_that_fell_is_correct(tmp_path):
    _seed_verdict(tmp_path, lean="weak")
    _run(tmp_path, price_fn=_prices(exit_close=88.0))
    assert {r.horizon_td: r.correct for r in _rows(tmp_path)}[1] is True


def test_correctness_is_excess_not_raw_return(tmp_path):
    """A listing that rose 10% into a market that rose 12% did not hold."""
    _seed_verdict(tmp_path, lean="strong")
    _run(tmp_path, bench=_Bench(pct=12.0), price_fn=_prices(exit_close=110.0))
    row = {r.horizon_td: r for r in _rows(tmp_path)}[1]
    assert row.return_pct == pytest.approx(10.0, abs=1e-4)
    assert row.excess_pct == pytest.approx(-2.0, abs=1e-4)
    assert row.correct is False


def test_is_ipo_correct_is_its_own_rule(tmp_path):
    assert is_ipo_correct("strong", 0.0) is True         # a dead heat counts for
    assert is_ipo_correct("strong", -0.0001) is False
    assert is_ipo_correct("weak", -0.0001) is True
    assert is_ipo_correct("weak", 0.0) is False
    assert is_ipo_correct("STRONG", 5.0) is True         # case/space tolerant
    assert is_ipo_correct(" weak ", 5.0) is False
    for nothing in ("mixed", "", None, "HOLD", "ADD", "buy"):
        assert is_ipo_correct(nothing, 5.0) is None


def test_the_advice_vocabulary_is_left_alone(tmp_path):
    """is_correct defines what every accumulated advice row already means and
    must not have learned an IPO word."""
    from core.audit.rules import INTENT_LONG, INTENT_REDUCE, is_correct
    assert "strong" not in {v.lower() for v in INTENT_LONG | INTENT_REDUCE}
    assert is_correct("strong", 5.0) is None
    assert is_correct("HOLD", 5.0) is True


# ───────────────────── one listing, one graded call ──────────────────────

def test_re_running_the_lane_writes_nothing_new(tmp_path):
    _seed_verdict(tmp_path)
    first = _run(tmp_path)
    second = _run(tmp_path)
    assert first["graded"] == len(HORIZONS_TD)
    assert second["graded"] == 0
    assert second["already_present"] == len(HORIZONS_TD)
    assert len(_rows(tmp_path)) == len(HORIZONS_TD)


def test_an_extended_issue_grades_once_against_the_surviving_book(tmp_path):
    _seed_verdict(tmp_path, close_date="2026-02-25", lean="weak",
                  written_at="2026-02-24T13:30:00+00:00")
    _seed_verdict(tmp_path, close_date="2026-02-27", lean="strong",
                  written_at="2026-02-28T13:30:00+00:00")

    out = _run(tmp_path)
    assert out["superseded"] == 1
    rows = _rows(tmp_path)
    assert len(rows) == len(HORIZONS_TD)                      # not twice that
    assert {r.ref for r in rows} == {"ipo:2026-02-27|VARMORA"}
    assert {r.verdict for r in rows} == {"strong"}


def test_the_newest_row_for_one_book_supersedes_the_earlier_read(tmp_path):
    """The T-1 read and the post-close read share a key; the store's own rule
    is that the newest wins, and grading must use the same rule."""
    _seed_verdict(tmp_path, lean="strong", evidenced=False,
                  written_at="2026-02-26T13:30:00+00:00")
    _seed_verdict(tmp_path, lean="weak", evidenced=True, demand=21.0,
                  written_at="2026-02-28T13:30:00+00:00")
    _run(tmp_path)
    rows = {r.horizon_td: r for r in _rows(tmp_path)}
    assert len(rows) == len(HORIZONS_TD)
    assert rows[1].verdict == "weak"
    assert rows[1].correct is False           # +10%: the weak lean did not hold


# ───────────────────── absent tape, absent price ─────────────────────────

def test_an_unlisted_issue_is_awaiting_listing_not_a_failure(tmp_path):
    _seed_verdict(tmp_path)
    out = _run(tmp_path, spine=_Spine())
    assert out == {"graded": 0, "skipped_unpriceable": 0, "already_present": 0,
                   "awaiting_listing": 1, "superseded": 0}


def test_a_listing_in_the_future_is_awaiting_listing(tmp_path):
    _seed_verdict(tmp_path)
    out = _run(tmp_path, on=date(2026, 3, 1))
    assert out["awaiting_listing"] == 1 and out["graded"] == 0


def test_an_unpriceable_symbol_is_counted_not_raised(tmp_path):
    _seed_verdict(tmp_path)
    out = _run(tmp_path, price_fn=_prices(fails={"VARMORA"}))
    assert out["graded"] == 0
    assert out["skipped_unpriceable"] == len(HORIZONS_TD)
    assert _rows(tmp_path) == []


def test_a_dead_benchmark_degrades_the_row_and_not_the_run(tmp_path):
    class _Dead:
        def pct_change(self, a, b):
            raise RuntimeError("no index close")

        def close_on(self, d):
            raise RuntimeError("no index close")

    _seed_verdict(tmp_path)
    out = _run(tmp_path, bench=_Dead())
    assert out["graded"] == 0 and out["skipped_unpriceable"] == len(HORIZONS_TD)


def test_an_unreadable_verdict_store_grades_nothing(tmp_path):
    (tmp_path / "ipo").mkdir(parents=True, exist_ok=True)
    (tmp_path / "ipo" / "ipo_verdicts.jsonl").write_text(
        "{not json\n", encoding="utf-8")
    out = _run(tmp_path)
    assert out["graded"] == 0


# ─────────────────────── the listing-facts resolver ──────────────────────

def test_the_spine_answers_before_the_cache(tmp_path):
    cache = tmp_path / "ipo_cache.json"
    cache.write_text(json.dumps({"past": [{"symbol": "VARMORA",
                                           "listing_date": "2026-03-11",
                                           "issue_price": 148.0}]}),
                     encoding="utf-8")
    facts = listing_facts("VARMORA", history_store=_spine(),
                          cache_path=str(cache))
    assert facts.source == "spine"
    assert facts.listing_date == LISTING.isoformat()
    assert facts.issue_price == ISSUE_PRICE


def test_the_cache_answers_for_an_issue_the_spine_has_not_reached(tmp_path):
    cache = tmp_path / "ipo_cache.json"
    cache.write_text(json.dumps({"past": [{"symbol": "VARMORA",
                                           "listing_date": "2026-03-11",
                                           "issue_price": 148.0}]}),
                     encoding="utf-8")
    facts = listing_facts("VARMORA", history_store=_Spine(),
                          cache_path=str(cache))
    assert facts.source == "cache"
    assert facts.listing_date == "2026-03-11" and facts.issue_price == 148.0


def test_half_a_record_resolves_to_nothing(tmp_path):
    cache = tmp_path / "ipo_cache.json"
    cache.write_text(json.dumps({"past": [
        {"symbol": "NOPRICE", "listing_date": "2026-03-11"},
        {"symbol": "NODATE", "issue_price": 148.0},
        {"symbol": "BADDATE", "listing_date": "soon", "issue_price": 148.0},
    ]}), encoding="utf-8")
    for symbol in ("NOPRICE", "NODATE", "BADDATE", "ABSENT", ""):
        assert listing_facts(symbol, history_store=_Spine(),
                             cache_path=str(cache)) is None


def test_the_lane_falls_through_to_the_cache(tmp_path):
    cache = tmp_path / "ipo_cache.json"
    cache.write_text(json.dumps({"past": [{"symbol": "VARMORA",
                                           "listing_date": LISTING.isoformat(),
                                           "issue_price": 148.0}]}),
                     encoding="utf-8")
    _seed_verdict(tmp_path)
    out = _run(tmp_path, spine=_Spine(), cache_path=str(cache),
               price_fn=_prices(exit_close=185.0))
    assert out["graded"] == len(HORIZONS_TD)
    assert {r.entry_close for r in _rows(tmp_path)} == {148.0}


# ──────────────────────────── containment ────────────────────────────────

def test_the_audit_report_is_unchanged_by_ipo_rows(tmp_path):
    """The P3 model is dark until IPO-5b. It must not be able to move a single
    number in the report the user is shown."""
    from core.audit.report import build_report, render_section

    store = AuditOutcomeStore(user_id=UID, base_dir=str(tmp_path))
    for horizon in (10, 30, 60):
        store.append(AuditOutcome(
            ref="2026-01-02|MARUTI|h", lane="advice", user_id=UID,
            symbol="MARUTI", verdict="HOLD", issued_on="2026-01-02",
            horizon_td=horizon, graded_on="2026-03-02", entry_close=100.0,
            exit_close=110.0, return_pct=10.0, bench_entry=1.0, bench_exit=1.1,
            bench_pct=2.0, excess_pct=8.0, correct=True,
            graded_at="2026-03-02T00:00:00+00:00"))
    before = build_report(user_id=UID, store=store)
    before_text = render_section(before)

    _seed_verdict(tmp_path)
    graded = _run(tmp_path)
    assert graded["graded"] == len(HORIZONS_TD)     # the rows really are there

    after = build_report(user_id=UID, store=store)
    for key in ("total_rows", "verdict", "hit_rate", "mean_excess_pct",
                "per_trigger", "coin_flip_p", "conviction_calibration",
                "switch_rule", "switch_taken"):
        assert after[key] == before[key], key
    assert render_section(after) == before_text


def test_ipo_horizons_colliding_with_the_report_still_change_nothing(tmp_path,
                                                                     monkeypatch):
    """The exclusion is structural, not an accident of disjoint horizons."""
    from core.audit import outcomes as mod
    from core.audit.report import build_report

    monkeypatch.setattr(mod, "_ipo_horizons", lambda: (10, 30, 60))
    store = AuditOutcomeStore(user_id=UID, base_dir=str(tmp_path))
    store.append(AuditOutcome(
        ref="2026-01-02|MARUTI|h", lane="advice", user_id=UID, symbol="MARUTI",
        verdict="HOLD", issued_on="2026-01-02", horizon_td=60,
        graded_on="2026-03-02", entry_close=100.0, exit_close=110.0,
        return_pct=10.0, bench_entry=1.0, bench_exit=1.1, bench_pct=2.0,
        excess_pct=8.0, correct=True, graded_at="2026-03-02T00:00:00+00:00"))
    before = build_report(user_id=UID, store=store)

    _seed_verdict(tmp_path)
    assert _run(tmp_path)["graded"] == 3
    after = build_report(user_id=UID, store=store)
    before.pop("generated_at"), after.pop("generated_at")   # wall clock, not a metric
    assert after == before


# ─────────────────────────── wiring and gates ────────────────────────────

def test_the_lane_grades_only_for_the_default_user(tmp_path):
    _seed_verdict(tmp_path)
    out = _run(tmp_path, user_id="someone-else")
    assert out["graded"] == 0 and out["not_default_user"] is True
    assert _rows(tmp_path, user_id="someone-else") == []


def test_the_config_switch_turns_the_lane_off(tmp_path, monkeypatch):
    from core.audit import outcomes as mod
    monkeypatch.setattr(mod, "_ipo_lane_enabled", lambda: False)
    _seed_verdict(tmp_path)
    assert _run(tmp_path)["graded"] == 0
    assert _rows(tmp_path) == []


def test_the_horizons_default_to_the_p1_spines(tmp_path):
    """Audit and spine must not drift into two curves that look comparable."""
    from core.audit.outcomes import _ipo_horizons
    assert _ipo_horizons() == HORIZONS_TD


def test_grade_due_runs_the_ipo_lane_and_survives_its_failure(tmp_path,
                                                              monkeypatch):
    from core.audit import outcomes as mod

    _seed_verdict(tmp_path)
    summary = grade_due(date(2027, 6, 30), UID, base_dir=str(tmp_path),
                        verdicts_dir=str(tmp_path / "ipo"),
                        history_store=_spine(), bench=_Bench(),
                        price_fn=_prices())
    assert summary["lanes"]["ipo"]["graded"] == len(HORIZONS_TD)

    def _boom(*a, **kw):
        raise RuntimeError("ipo lane exploded")

    monkeypatch.setattr(mod, "grade_ipo_lane", _boom)
    survived = grade_due(date(2027, 6, 30), UID, base_dir=str(tmp_path),
                         bench=_Bench(), price_fn=_prices())
    assert "error" in survived["lanes"]["ipo"]
    assert set(survived["lanes"]) == {"advice", "alert", "shelf", "switch", "ipo"}


def test_ipo_is_a_declared_lane(tmp_path):
    from backend.shared.schemas.audit import Lane
    from typing import get_args
    assert "ipo" in get_args(Lane)

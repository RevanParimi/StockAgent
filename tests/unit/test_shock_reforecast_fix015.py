"""
tests/unit/test_shock_reforecast_fix015.py
==========================================
FIX-015: the advisor's `shock_reforecast` EXIT reads the re-forecast's trigger
key (not its reason sentence), counts only a market or company shock
(`external_shock`, `preopen_shock`; never `thesis_break`), and only at the
first two session closes after the re-forecast was made.

Every expected figure below is worked by hand from the fixture's numbers,
never asked of the code under test.

The fixture: MARUTI held 100 at Rs 1,000, closing at Rs 1,000 every session
(no gain or loss, so no stop or trim can fire), the thesis not reviewed (no
price-path exit), regime NORMAL, no shelf idea (an EXIT stays an EXIT). The
sessions are Mon 8 to Fri 12 Jun 2026 and Mon 15 to Fri 19 Jun (no holiday).

  * The path before any re-forecast ends at Rs 1,000: (1000-1000)/1000 = 0.0%,
    FLAT (the flat band is +/-1%).
  * A re-forecast's path ends at Rs 900: (900-1000)/1000 = -10%, DOWN; or at
    Rs 1,000: FLAT.

The writers, as they store the event (generate_forecast.regenerate_envelope):
the daily review that runs Tuesday 16:30 reviews Monday, so it dates the event
Monday and makes it at about 16:45 Tuesday; the pre-open check dates it the
day it runs (08:45); the manual command dates it the day it runs. A decision
at a session's close reads no re-forecast made at or after that close
(FIX-027).
"""
from __future__ import annotations

import random
from datetime import date, datetime, timedelta

import pytest

from backend.shared.schemas.feedback import (DailyForecast, PredictionEnvelope,
                                             ReforecastEvent)
from backend.shared.schemas.portfolio import Holding, Portfolio
from core.config import settings
from core.intelligence.rl.nse_calendar import IST, is_trading_day
from core.intelligence.rl.stores.prediction_store import PredictionStore
from core.portfolio.advisor import ExitEvidence, build_signals, decide
from services.data.verdict_store import VerdictStore

TICKER, SECTOR, CYCLE = "MARUTI", "automobile", "MARUTI_2026-06"
MON, TUE, WED, THU, FRI = (date(2026, 6, d) for d in (8, 9, 10, 11, 12))
NEXT_MON = date(2026, 6, 15)
SESSIONS = [date(2026, 6, d) for d in (8, 9, 10, 11, 12, 15, 16, 17, 18, 19)]


def _at(day: date, hh: int, mm: int) -> str:
    return datetime(day.year, day.month, day.day, hh, mm, tzinfo=IST).isoformat()


def _envelope(end: float, events=()) -> PredictionEnvelope:
    """Ten rows, 8 to 19 Jun, from 1,000 to `end` (the last row sets the drift)."""
    rows = [DailyForecast(
        day=i + 1, date=d.isoformat(),
        predicted_close=round(1000.0 + (end - 1000.0) * (i + 1) / len(SESSIONS), 4),
        predicted_verdict="BUY", confidence=0.7) for i, d in enumerate(SESSIONS)]
    env = PredictionEnvelope(ticker=TICKER, sector=SECTOR, cycle_id=CYCLE,
                             generated_at="2026-06-01T09:00:00", base_close=1000.0,
                             daily_forecasts=rows)
    env.reforecast_history = list(events)
    env.reforecast_count = len(events)
    return env


def _write(tmp_path, monkeypatch, steps) -> VerdictStore:
    """The envelope file as regenerate_envelope leaves it: a flat path first;
    then each (event, end) archives the envelope as it stands, draws the new
    path and appends the event. Returns the advisor's store over it."""
    monkeypatch.setattr(settings, "PREDICTION_DATA_DIR", str(tmp_path))
    ps = PredictionStore(TICKER, sector=SECTOR, base_dir=str(tmp_path))
    ps.save_envelope(_envelope(1000.0))
    for event, end in steps:
        cur = ps.load_envelope(CYCLE)
        archived = ps.archive_envelope(CYCLE)
        new = _envelope(end, list(cur.reforecast_history))
        new.reforecast_history.append(event.model_copy(update={"archived_file": archived or ""}))
        new.reforecast_count = len(new.reforecast_history)
        ps.save_envelope(new)
    return VerdictStore(TICKER, sector=SECTOR)


def _holding() -> Holding:
    return Holding(symbol=TICKER, sector=SECTOR, qty=100, avg_buy_price=1000.0,
                   adj_avg_price=1000.0, adj_qty=100, buy_date="2026-06-01")


def _signals(vs: VerdictStore, review: date, **over):
    holding = _holding()
    portfolio = Portfolio(user_id="u", holdings=[holding], cash_deployable=900_000.0)
    sig = build_signals(holding, portfolio, review, vs, {}, close=1000.0)
    # No feedback entry is written: the day's regime is taken as established.
    update = {"regime_label": "NORMAL", "regime_unavailable": "", "price_fresh": True,
              "forecast_gate": "actionable", **over}
    return holding, sig.model_copy(update=update)


def _both(holding, sig):
    """(legacy, evidence) records; the evidence rule's own exit cannot fire
    (no holding period known)."""
    return (decide(sig, holding, "balanced"),
            decide(sig, holding, "balanced", exit_rule="evidence", evidence=ExitEvidence()))


def _event(trigger: str, reason: str, day: date, at: str) -> ReforecastEvent:
    return ReforecastEvent(date=day.isoformat(), reason=reason, trigger=trigger, at=at)


# Each writer's real event: (trigger, reason, date, made at)
DAILY_SHOCK = _event(
    "external_shock",
    "External shock on 2026-06-08: actual direction (DOWN) diverged from predicted "
    "verdict (BUY); FeedbackAgent classified the miss as external_shock.",
    MON, _at(TUE, 16, 45))
DAILY_THESIS = _event(
    "thesis_break",
    "Thesis break on 2026-06-08: horizon_confidence_multiplier=0.40 <= 0.50. "
    "Invalidated assumptions: demand holds.",
    MON, _at(TUE, 16, 45))
DAILY_REGIME = _event(
    "regime_flip",
    "Regime flip on 2026-06-08: sticky market regime entered MACRO_CRISIS (was NORMAL).",
    MON, _at(TUE, 16, 45))
PREOPEN = _event("preopen_shock", "pre-open shock: plant fire halts production",
                 TUE, _at(TUE, 8, 45))
MANUAL = _event("manual", "Manual re-forecast requested for MARUTI via CLI.",
                TUE, _at(TUE, 11, 0))


# ---------------------------------------------------------------------------
# Each writer, at the first close after its re-forecast was made
# ---------------------------------------------------------------------------

# (event, the first close after it, verdict with the -10% path, with the 0.0% path)
WRITERS = [
    (DAILY_SHOCK, WED, "EXIT", "HOLD"),    # made Tue 16:45, after Tuesday's close
    (PREOPEN, TUE, "EXIT", "HOLD"),        # made Tue 08:45, before Tuesday's close
    (DAILY_THESIS, WED, "HOLD", "HOLD"),   # the price-path rule's own path
    (DAILY_REGIME, WED, "HOLD", "HOLD"),   # regime NORMAL here: no crisis exit either
    (MANUAL, TUE, "HOLD", "HOLD"),
]


@pytest.mark.parametrize("event,review,down,flat", WRITERS,
                         ids=[w[0].trigger for w in WRITERS])
def test_each_writers_event_fires_only_as_a_shock_with_a_falling_path(
        tmp_path, monkeypatch, event, review, down, flat):
    for end, want in ((900.0, down), (1000.0, flat)):
        vs = _write(tmp_path / str(int(end)), monkeypatch, [(event, end)])
        holding, sig = _signals(vs, review)
        assert sig.reforecast_reason == event.trigger          # the key, not the sentence
        for rec in _both(holding, sig):
            assert rec.verdict == want, (event.trigger, end, rec.triggers)
            assert rec.triggers == (["shock_reforecast"] if want == "EXIT" else [])


# ---------------------------------------------------------------------------
# The window: the first two closes after the re-forecast was made
# ---------------------------------------------------------------------------

def test_the_daily_reviews_shock_counts_at_the_two_closes_after_its_run(tmp_path, monkeypatch):
    """Dated Monday (the session reviewed), made Tuesday 16:45. Monday's and
    Tuesday's decisions read the path as it stood at their close (flat): HOLD.
    Wednesday's and Thursday's read the shock and the -10% path: EXIT.
    Friday's is the third close after it: the path is still -10% (DOWN), but
    the shock no longer counts: HOLD. A window on the event's date (Monday or
    the session before the review day) would reach no decision at all."""
    vs = _write(tmp_path, monkeypatch, [(DAILY_SHOCK, 900.0)])
    want = {MON: ("FLAT", "", "HOLD"), TUE: ("FLAT", "", "HOLD"),
            WED: ("DOWN", "external_shock", "EXIT"), THU: ("DOWN", "external_shock", "EXIT"),
            FRI: ("DOWN", "", "HOLD"), NEXT_MON: ("DOWN", "", "HOLD")}
    for review, (direction, trigger, verdict) in want.items():
        holding, sig = _signals(vs, review)
        assert (sig.envelope_direction, sig.reforecast_reason) == (direction, trigger), review
        for rec in _both(holding, sig):
            assert rec.verdict == verdict, (review, rec.triggers)


def test_a_preopen_shock_counts_at_that_days_close_and_the_next(tmp_path, monkeypatch):
    """Made Tuesday 08:45. Monday's decision may not read it (after Monday's
    close): HOLD on the flat path. Tuesday's and Wednesday's: EXIT. Thursday's
    is the third close after it: HOLD."""
    vs = _write(tmp_path, monkeypatch, [(PREOPEN, 900.0)])
    for review, verdict in ((MON, "HOLD"), (TUE, "EXIT"), (WED, "EXIT"), (THU, "HOLD")):
        holding, sig = _signals(vs, review)
        for rec in _both(holding, sig):
            assert rec.verdict == verdict, (review, rec.triggers)


def test_a_reforecast_without_a_time_never_counts(tmp_path, monkeypatch):
    """Stored before FIX-027 (no `at`): it cannot be shown to be recent, so
    even a shock dated the review day with a -10% path does not sell."""
    old = ReforecastEvent(date=TUE.isoformat(), reason="pre-open shock: old",
                          trigger="preopen_shock")
    vs = _write(tmp_path, monkeypatch, [(old, 900.0)])
    for review in (TUE, WED):
        holding, sig = _signals(vs, review)
        assert sig.envelope_direction == "DOWN" and sig.reforecast_reason == ""
        assert all(rec.verdict == "HOLD" for rec in _both(holding, sig))


def test_only_the_latest_reforecast_is_read(tmp_path, monkeypatch):
    """The daily review's shock (Tue 16:45), then a manual re-forecast at
    Wednesday 11:00 whose path also ends at 900. The path read on Wednesday is
    the manual one, not the shock's: HOLD on Wednesday and Thursday, where the
    shock alone would sell (test above)."""
    manual = _event("manual", "Manual re-forecast requested for MARUTI via CLI.",
                    WED, _at(WED, 11, 0))
    vs = _write(tmp_path, monkeypatch, [(DAILY_SHOCK, 900.0), (manual, 900.0)])
    for review in (WED, THU):
        holding, sig = _signals(vs, review)
        assert sig.reforecast_reason == "manual"
        assert all(rec.verdict == "HOLD" for rec in _both(holding, sig))


# ---------------------------------------------------------------------------
# The hard review's question: no price-path miss sells through this trigger
# under the evidence rule
# ---------------------------------------------------------------------------

def test_a_thesis_break_reforecast_never_sells_under_the_evidence_rule(tmp_path, monkeypatch):
    """The review of Monday finds the thesis broken and re-forecasts to 900
    (-10%). Wednesday's decision, thesis not intact: the price-path (legacy)
    rule sells on `thesis_break` alone; the evidence rule holds, and neither
    names `shock_reforecast`."""
    vs = _write(tmp_path, monkeypatch, [(DAILY_THESIS, 900.0)])
    holding, sig = _signals(vs, WED, thesis_intact=False)
    legacy, by_evidence = _both(holding, sig)
    assert legacy.verdict == "EXIT" and legacy.triggers == ["thesis_break"]
    assert by_evidence.verdict == "HOLD" and by_evidence.triggers == []


# ---------------------------------------------------------------------------
# FIX-027's review L1: the late note names the trigger and the time
# ---------------------------------------------------------------------------

def test_the_late_note_names_the_trigger_and_the_time_not_the_sentence(tmp_path, monkeypatch):
    vs = _write(tmp_path, monkeypatch, [(DAILY_SHOCK, 900.0)])
    _h, sig = _signals(vs, MON)
    assert sig.envelope_after_close == (
        "the external_shock re-forecast of 2026-06-09T16:45:00+05:30 is after the "
        "close of 2026-06-08")
    unnamed = ReforecastEvent(date=MON.isoformat(), reason="something", at=_at(TUE, 16, 45))
    vs = _write(tmp_path / "unnamed", monkeypatch, [(unnamed, 900.0)])
    _h, sig = _signals(vs, MON)
    assert sig.envelope_after_close == (
        "the re-forecast of 2026-06-09T16:45:00+05:30 is after the close of 2026-06-08")


# ---------------------------------------------------------------------------
# The real writer's event, read by the advisor
# ---------------------------------------------------------------------------

def test_the_real_reforecasts_event_is_read_by_its_trigger(tmp_path, monkeypatch):
    """regenerate_envelope run Tuesday 16:45 for Monday's review, reason "shock",
    trigger external_shock: the advisor reads "external_shock" at Wednesday's
    and Thursday's closes only."""
    from tests.unit.test_envelope_after_close_fix027 import _run_reforecast
    ps, out, _asked = _run_reforecast(tmp_path, monkeypatch, review_date=MON, today=TUE,
                                      anchored_bar=lambda on: on)
    assert out is not None
    event = out.reforecast_history[-1]
    assert (event.reason, event.trigger, event.date) == ("shock", "external_shock", "2026-06-08")
    vs = VerdictStore(TICKER, sector=SECTOR)
    read = {review: _signals(vs, review)[1].reforecast_reason
            for review in (MON, TUE, WED, THU, FRI)}
    assert read == {MON: "", TUE: "", WED: "external_shock", THU: "external_shock", FRI: ""}


# ---------------------------------------------------------------------------
# Invariant: a shock sells at exactly the first two closes after it was made
# ---------------------------------------------------------------------------

def _oracle_closes_after(at: datetime, n: int = 2) -> list[date]:
    """Independent of the code: walk the calendar a day at a time from 1 Jun
    and keep the sessions whose 15:30 IST close is strictly after `at` (a
    close at the re-forecast's own minute is not after it); the first `n`."""
    out, day = [], date(2026, 6, 1)
    while len(out) < n:
        if is_trading_day(day) and datetime(day.year, day.month, day.day, 15, 30,
                                            tzinfo=IST) > at:
            out.append(day)
        day += timedelta(days=1)
    return out


@pytest.mark.parametrize("seed", range(30))
def test_a_shock_sells_at_exactly_the_first_two_closes_after_it(tmp_path, monkeypatch, seed):
    """A random trigger, made at a random minute from Fri 5 Jun to Wed 17 Jun
    (a third of them at a close, or a minute either side), dated that day, the
    day before or three days before (the date must not matter), with a -10%
    path. Over the ten sessions, `shock_reforecast` fires, under both rules,
    exactly at the sessions the calendar walk finds, and only for a shock."""
    rng = random.Random(seed)
    trigger = rng.choice(["external_shock", "preopen_shock", "thesis_break",
                          "regime_flip", "manual"])
    if rng.random() < 1 / 3:
        day = rng.choice([date(2026, 6, 5)] + SESSIONS[:8])
        at = datetime(day.year, day.month, day.day, 15, 30, tzinfo=IST) \
            + timedelta(minutes=rng.choice([-1, 0, 1]))
    else:
        start = datetime(2026, 6, 5, 9, 0, tzinfo=IST)
        at = start + timedelta(minutes=rng.randint(0, 12 * 24 * 60 + 11 * 60))
    dated = at.date() - timedelta(days=rng.choice([0, 1, 3]))
    event = ReforecastEvent(date=dated.isoformat(), reason=f"a sentence about {trigger}",
                            trigger=trigger, at=at.isoformat())
    vs = _write(tmp_path, monkeypatch, [(event, 900.0)])
    fired = []
    for review in SESSIONS:
        holding, sig = _signals(vs, review)
        legacy, by_evidence = _both(holding, sig)
        assert ("shock_reforecast" in legacy.triggers) == \
            ("shock_reforecast" in by_evidence.triggers), review
        if "shock_reforecast" in legacy.triggers:
            fired.append(review)
    want = ([d for d in _oracle_closes_after(at) if d in SESSIONS]
            if trigger in ("external_shock", "preopen_shock") else [])
    assert fired == want, (trigger, at.isoformat())

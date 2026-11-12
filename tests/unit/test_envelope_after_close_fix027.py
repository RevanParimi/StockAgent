"""
tests/unit/test_envelope_after_close_fix027.py
==============================================
FIX-027: a decision booked at a session's close reads nothing from after that close.

Every expected figure below is worked by hand from the fixture's numbers and
the one rule (a re-forecast made after session D's close, 15:30 IST, may not
set the direction a decision at D's close reads), never asked of the code
under test.

The example (RV13 of FIX-024's review): Monday 8 Jun 2026 closes at 1,000.
Tuesday 9 Jun closes at 1,100 on results. Tuesday's 16:30 run reviews Monday;
its re-forecast (16:45) anchors on Monday's close and reads Tuesday's news.

  * The envelope as Monday's close left it ends at 1,000: FLAT (0.0%).
  * The re-forecast path ends at 1,100: UP (+10%). A decision at Monday's
    close that read it would ADD at 1,000 on a rise it knew had happened.
  * With Tuesday at 900 and the thesis not intact: the new path ends at 900,
    DOWN (-10%); the price-path rule would EXIT at 1,000. The owner chose
    "wait": no sale at Monday's close; it counts for Wednesday's.
"""
from __future__ import annotations

import random
from datetime import date, datetime, timedelta

import pytest

import core.intelligence.rl.workflows.daily_review as dr
from backend.shared.schemas.feedback import (DailyForecast, PredictionEnvelope,
                                             ReforecastEvent)
from backend.shared.schemas.portfolio import Holding, Portfolio
from core.config import settings
from core.intelligence.rl.nse_calendar import IST, session_close_at
from core.intelligence.rl.stores.prediction_store import PredictionStore
from core.intelligence.rl.workflows import generate_forecast as gf
from core.portfolio.advisor import (AdvisorSignals, build_signals, decide,
                                    reforecasts_after_close)
from core.portfolio.narrator import fallback_narrative
from core.portfolio.pricing import SessionClose
from services.data.verdict_store import VerdictStore
from tests.unit.intelligence.rl import test_reforecast as rf

MON, TUE, WED = date(2026, 6, 8), date(2026, 6, 9), date(2026, 6, 10)
TICKER, SECTOR = "MARUTI", "automobile"
DATES = ["2026-06-08", "2026-06-09", "2026-06-10", "2026-06-11", "2026-06-12"]


def _at(day: date, hh: int, mm: int) -> str:
    return datetime(day.year, day.month, day.day, hh, mm, tzinfo=IST).isoformat()


def _envelope(end: float, events=()) -> PredictionEnvelope:
    """Five rows from Monday, ending at `end` (the last row decides the drift)."""
    rows = [DailyForecast(
        day=i + 1, date=d, predicted_close=round(1000.0 + (end - 1000.0) * (i + 1) / 5, 4),
        predicted_verdict="BUY", confidence=0.7) for i, d in enumerate(DATES)]
    env = PredictionEnvelope(ticker=TICKER, sector=SECTOR, cycle_id="MARUTI_2026-06",
                             generated_at="2026-06-01T09:00:00", base_close=1000.0,
                             daily_forecasts=rows)
    env.reforecast_history = list(events)
    env.reforecast_count = len(events)
    return env


def _store(tmp_path) -> PredictionStore:
    return PredictionStore(TICKER, sector=SECTOR, base_dir=str(tmp_path))


def _verdicts(tmp_path, monkeypatch) -> VerdictStore:
    monkeypatch.setattr(settings, "PREDICTION_DATA_DIR", str(tmp_path))
    return VerdictStore(TICKER, sector=SECTOR)


def _reforecast(ps: PredictionStore, new_end: float, at: str, reason="external_shock",
                keep_at=True) -> None:
    """What regenerate_envelope does to the file: archive the current envelope,
    replace the path, append the event."""
    cur = ps.load_envelope("MARUTI_2026-06")
    archived = ps.archive_envelope("MARUTI_2026-06")
    new = _envelope(new_end, list(cur.reforecast_history))
    new.reforecast_history.append(ReforecastEvent(
        date=MON.isoformat(), reason=reason, archived_file=archived or "",
        **({"at": at} if keep_at else {})))
    new.reforecast_count = len(new.reforecast_history)
    ps.save_envelope(new)


def _signals(vs: VerdictStore, review: date = MON, close: float = 1000.0, **over):
    holding = Holding(symbol=TICKER, sector=SECTOR, qty=100, avg_buy_price=1000.0,
                      adj_avg_price=1000.0, adj_qty=100, buy_date="2026-06-01")
    portfolio = Portfolio(user_id="u", holdings=[holding], cash_deployable=900_000.0)
    sig = build_signals(holding, portfolio, review, vs, {}, close=close)
    # The fixture writes no feedback entry, so the advisor asks the market-wide
    # record for the day (FIX-029); these tests take the day's regime as established.
    update = {"direction_accuracy_7d": 0.70, "position_weight_pct": 5.0,
              "price_fresh": True, "forecast_gate": "actionable", "regime_unavailable": "",
              **over}
    return holding, sig.model_copy(update=update)


def _decide(holding, sig):
    return decide(sig, holding, "balanced")


# ---------------------------------------------------------------------------
# The example, through the real advisor. `_reforecast` writes the envelope file
# as regenerate_envelope does; the end-to-end tests below use the real one.
# ---------------------------------------------------------------------------

def test_tuesday_1100_does_not_add_at_mondays_1000(tmp_path, monkeypatch):
    """Tuesday's 16:45 re-forecast ends at 1,100 (+10% on Monday's 1,000). The
    envelope Monday's close left ends at 1,000 (0.0%, FLAT): no ADD, the note
    names why, and the narrative says so."""
    ps = _store(tmp_path)
    ps.save_envelope(_envelope(1000.0))
    _reforecast(ps, 1100.0, _at(TUE, 16, 45))
    holding, sig = _signals(_verdicts(tmp_path, monkeypatch))
    assert sig.envelope_direction == "FLAT"            # Monday's path, 0.0%
    assert sig.envelope_late_direction == "UP"         # the new path, +10%
    rec = _decide(holding, sig)
    assert rec.verdict == "HOLD" and "add_bullish_healthy" not in rec.triggers
    assert "ENVELOPE_AFTER_CLOSE" in rec.notes
    assert "2026-06-09T16:45" in rec.envelope_after_close
    assert "after the close of 2026-06-08" in rec.envelope_after_close
    assert "after the review session's close" in fallback_narrative(rec)


def test_tuesday_900_with_a_broken_thesis_does_not_sell_at_mondays_1000(tmp_path, monkeypatch):
    """The new path ends at 900 (-10%, DOWN) and the thesis is not intact:
    read, it would fire thesis_break and shock_reforecast and EXIT at 1,000.
    Monday's decision reads the 1,000 path (FLAT): none of the three fires.
    (The owner's option: wait; Wednesday's close reads the new path.)"""
    ps = _store(tmp_path)
    ps.save_envelope(_envelope(1000.0))
    _reforecast(ps, 900.0, _at(TUE, 16, 45))
    holding, sig = _signals(_verdicts(tmp_path, monkeypatch), thesis_intact=False)
    assert sig.envelope_direction == "FLAT" and sig.reforecast_reason == ""
    rec = _decide(holding, sig)
    assert rec.verdict == "HOLD"
    assert not {"thesis_break", "shock_reforecast"} & set(rec.triggers)
    # Wednesday's run reviews Tuesday (close 900). The re-forecast ran at
    # Tuesday 16:45, after Tuesday's 15:30 close too, so Tuesday's decision
    # may not read it either.
    _h, sig_tue = _signals(_verdicts(tmp_path, monkeypatch), review=TUE, close=900.0,
                           thesis_intact=False)
    assert sig_tue.envelope_direction != "DOWN"
    # Thursday's run reviews Wednesday: the re-forecast (Tue 16:45) is before
    # Wednesday's close, so it counts. Its path ends at 900; against a
    # Wednesday close of 1,000 that is -10%, DOWN, and the sale fires.
    _h, sig_wed = _signals(_verdicts(tmp_path, monkeypatch), review=WED, close=1000.0,
                           thesis_intact=False)
    assert sig_wed.envelope_after_close == ""
    assert sig_wed.envelope_direction == "DOWN"        # (900-1000)/1000 = -10%
    rec_wed = _decide(_h, sig_wed)
    assert rec_wed.verdict == "EXIT" and "thesis_break" in rec_wed.triggers


def test_a_reforecast_before_the_close_still_counts(tmp_path, monkeypatch):
    """An envelope re-forecast last Friday (before Monday's close) ADDs as
    today: +10% against 1,000, UP, accuracy 0.70, 5% weight."""
    ps = _store(tmp_path)
    ps.save_envelope(_envelope(1000.0))
    _reforecast(ps, 1100.0, _at(date(2026, 6, 5), 16, 45))
    holding, sig = _signals(_verdicts(tmp_path, monkeypatch))
    assert sig.envelope_direction == "UP" and sig.envelope_after_close == ""
    rec = _decide(holding, sig)
    assert rec.verdict == "ADD" and "ENVELOPE_AFTER_CLOSE" not in rec.notes


def test_a_reforecast_a_minute_before_the_close_counts_and_at_it_does_not(tmp_path, monkeypatch):
    """15:29 reads nothing of the close; 15:30 is the close itself, as
    close_before_decision has it for a buy."""
    for hh, mm, want in ((15, 29, "UP"), (15, 30, "FLAT")):
        base = tmp_path / f"t{mm}"
        ps = PredictionStore(TICKER, sector=SECTOR, base_dir=str(base))
        ps.save_envelope(_envelope(1000.0))
        _reforecast(ps, 1100.0, _at(MON, hh, mm))
        _h, sig = _signals(_verdicts(base, monkeypatch))
        assert sig.envelope_direction == want, (hh, mm)


def test_the_preopen_reforecast_is_after_the_previous_close(tmp_path, monkeypatch):
    """Tuesday 08:45's pre-open re-forecast (dated Tuesday) is after Monday's
    close: Tuesday 16:30's run, reviewing Monday, may not read it."""
    ps = _store(tmp_path)
    ps.save_envelope(_envelope(1000.0))
    _reforecast(ps, 1100.0, _at(TUE, 8, 45), reason="preopen_shock")
    _h, sig = _signals(_verdicts(tmp_path, monkeypatch))
    assert sig.envelope_direction == "FLAT" and sig.envelope_late_direction == "UP"


def test_old_envelopes_without_a_time_parse_and_count_as_before(tmp_path, monkeypatch):
    """Stored before the field: no `at`. The event parses, is not after any
    close, and the path is read as today."""
    event = ReforecastEvent.model_validate({"date": "2026-06-08", "reason": "external_shock"})
    assert event.at == ""
    ps = _store(tmp_path)
    ps.save_envelope(_envelope(1100.0, [event]))
    assert reforecasts_after_close(ps.load_envelope("MARUTI_2026-06"), MON) == []
    holding, sig = _signals(_verdicts(tmp_path, monkeypatch))
    assert sig.envelope_direction == "UP" and sig.reforecast_reason == "external_shock"
    assert _decide(holding, sig).verdict == "ADD"


def test_an_unreadable_archive_reads_no_path_at_all(tmp_path, monkeypatch):
    """The event is after the close and its archive is gone: the envelope as it
    stood is unknown, so no direction is read (FLAT), no ADD, and the note says
    the earlier envelope is unavailable."""
    ps = _store(tmp_path)
    ps.save_envelope(_envelope(1000.0))
    _reforecast(ps, 1100.0, _at(TUE, 16, 45))
    cur = ps.load_envelope("MARUTI_2026-06")
    cur.reforecast_history[0].archived_file = ""
    ps.save_envelope(cur)
    holding, sig = _signals(_verdicts(tmp_path, monkeypatch))
    assert sig.envelope_direction == "FLAT"
    assert "not available" in sig.envelope_after_close
    assert _decide(holding, sig).verdict == "HOLD"


def test_an_archive_outside_the_ticker_folder_is_refused(tmp_path):
    ps = _store(tmp_path)
    ps.save_envelope(_envelope(1000.0))
    outside = tmp_path / "other.json"
    outside.write_text(_envelope(1000.0).model_dump_json())
    assert ps.load_archived_envelope(str(outside)) is None


# ---------------------------------------------------------------------------
# The re-forecast itself: the time, and the anchor
# ---------------------------------------------------------------------------

def _run_reforecast(tmp_path, monkeypatch, *, review_date, today, anchored_bar):
    monkeypatch.setattr(gf.settings, "PREDICTION_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(gf.settings, "RL_REFORECAST_ENABLED", True)
    monkeypatch.setattr(gf.settings, "RL_REFORECAST_MAX_PER_MONTH", 2)
    ps = _store(tmp_path)
    env = rf._make_envelope()
    ps.save_envelope(env)
    rf._patch_pipeline(monkeypatch, tmp_path, base_close=1100.0)
    monkeypatch.setattr(gf, "_review_session_close", _real_review_session_close)
    monkeypatch.setattr(gf, "_fetch_actual_close", lambda ticker: 1100.0)      # Tuesday's
    asked: list = []

    def session(ticker, on):
        asked.append(on)
        return SessionClose(close=1000.0, bar_date=anchored_bar(on), source="agree")
    monkeypatch.setattr(dr, "_fetch_session_close", session)
    import core.intelligence.rl.nse_calendar as cal
    stamp = datetime(today.year, today.month, today.day, 16, 45, tzinfo=IST)
    monkeypatch.setattr(gf, "now_ist", lambda: stamp)
    monkeypatch.setattr(cal, "now_ist", lambda: stamp)
    out = gf.regenerate_envelope(ticker=TICKER, sector=SECTOR, reason="shock",
                                 trigger="external_shock", review_date=review_date)
    return ps, out, asked


_real_review_session_close = gf._review_session_close


def test_the_reviews_reforecast_anchors_on_the_review_sessions_close(tmp_path, monkeypatch):
    """Tuesday 16:45, reviewing Monday: Monday's close (1,000) is asked for and
    stamps the event; Tuesday's 1,100 is not used."""
    ps, out, asked = _run_reforecast(tmp_path, monkeypatch, review_date=MON, today=TUE,
                                     anchored_bar=lambda on: on)
    assert out is not None and asked == [MON]
    event = out.reforecast_history[-1]
    assert event.at == _at(TUE, 16, 45)
    assert len(reforecasts_after_close(out, MON)) == 1
    anchored = [f.predicted_close for f in out.daily_forecasts if f.date > MON.isoformat()]
    assert all(abs(p - 1000.0) < abs(p - 1100.0) for p in anchored), anchored


def test_a_review_session_bar_that_is_missing_skips_the_reforecast(tmp_path, monkeypatch):
    """The nearest bar is Friday's (a carried-forward close): no anchor can be
    shown to be Monday's, the re-forecast is skipped, the envelope stays."""
    before = rf._make_envelope().model_dump()
    ps, out, _ = _run_reforecast(tmp_path, monkeypatch, review_date=MON, today=TUE,
                                 anchored_bar=lambda on: date(2026, 6, 5))
    assert out is None
    assert ps.load_envelope("MARUTI_2026-06").model_dump() == before


def test_the_preopen_reforecast_keeps_the_most_recent_close(tmp_path, monkeypatch):
    """review_date today (the pre-open check, 08:45): the most recent close, as
    before; the event still carries its time."""
    ps, out, asked = _run_reforecast(tmp_path, monkeypatch, review_date=TUE, today=TUE,
                                     anchored_bar=lambda on: on)
    assert out is not None and asked == []
    assert out.reforecast_history[-1].at == _at(TUE, 16, 45)


# ---------------------------------------------------------------------------
# Invariant: what a decision at D reads never depends on a close or run after D's close
# ---------------------------------------------------------------------------

def _oracle_end(paths: list[float], stamps: list[datetime | None], close_at: datetime) -> float:
    """Independent of the code: the path ends are paths[0] (the monthly
    forecast) and paths[k+1] after event k. A decision reads the last one
    whose event is not after the close: walk the events in order and stop at
    the first one after the close."""
    read = paths[0]
    for k, stamp in enumerate(stamps):
        if stamp is not None and stamp >= close_at:
            break
        read = paths[k + 1]
    return read


@pytest.mark.parametrize("seed", range(40))
def test_the_direction_read_never_depends_on_a_later_reforecast(tmp_path, monkeypatch, seed):
    """Random re-forecast times around Monday's close (days before it to days
    after, with and without a stamp) and random path ends: the drift the
    advisor reads equals the one worked from the last path in force at the
    close; and changing every path made after the close changes nothing."""
    rng = random.Random(seed)
    n = rng.randint(1, 2)                               # the monthly cap is 2
    close_at = session_close_at(MON)
    stamps: list[datetime | None] = []
    for _ in range(n):
        if rng.random() < 0.2:
            stamps.append(None)
        else:
            stamps.append(close_at + timedelta(minutes=rng.randint(-3000, 3000)))
    # events are made in time order
    known = sorted((s for s in stamps if s is not None))
    it = iter(known)
    stamps = [None if s is None else next(it) for s in stamps]
    paths = [rng.choice([900.0, 1000.0, 1100.0]) for _ in range(n + 1)]

    def run(after_paths):
        base = tmp_path / f"s{seed}_{id(after_paths)}"
        ps = PredictionStore(TICKER, sector=SECTOR, base_dir=str(base))
        ps.save_envelope(_envelope(paths[0]))
        for k, stamp in enumerate(stamps):
            end = paths[k + 1]
            if stamp is not None and stamp >= close_at:
                end = after_paths[k]
            _reforecast(ps, end, stamp.isoformat() if stamp else "", keep_at=stamp is not None)
        monkeypatch.setattr(settings, "PREDICTION_DATA_DIR", str(base))
        return _signals(VerdictStore(TICKER, sector=SECTOR))[1]

    oracle_end = _oracle_end(paths, stamps, close_at)
    band = settings.ADVISOR_ENVELOPE_FLAT_BAND_PCT
    drift = (oracle_end - 1000.0) / 1000.0 * 100
    want = "UP" if drift > band else "DOWN" if drift < -band else "FLAT"
    sig = run(paths[1:])
    first_late = next((k for k, s in enumerate(stamps) if s is not None and s >= close_at), None)
    if first_late is None:
        assert sig.envelope_direction == want and sig.envelope_after_close == ""
    else:
        assert sig.envelope_direction == want and sig.envelope_after_close
    # every post-close path replaced by its opposite: the read does not move
    flipped = [2000.0 - p for p in paths[1:]]
    assert run(flipped).envelope_direction == sig.envelope_direction


def test_one_clock_for_reforecasts_and_new_positions():
    """The rule is FIX-024's close_before_decision: a re-forecast at `at` is
    after session D's close exactly when that function says a close struck at
    15:30 cannot price a decision made at `at`."""
    from core.discovery.shelf import close_before_decision
    for minutes in (-60, 0, 1, 90):
        at = session_close_at(MON) + timedelta(minutes=minutes)
        env = _envelope(1000.0, [ReforecastEvent(date="2026-06-08", reason="x", at=at.isoformat())])
        after = bool(reforecasts_after_close(env, MON))
        refused = bool(close_before_decision(MON, at, True, "re-forecast"))
        assert after == refused, minutes


# ---------------------------------------------------------------------------
# End to end: the real regenerate_envelope writes the event and the archive,
# and the real advisor reads them back through VerdictStore
# ---------------------------------------------------------------------------

def _real_round_trip(tmp_path, monkeypatch, at_day: date, at_hour: int):
    """Monday's envelope ends at 1,000 (FLAT). The real re-forecast of Monday
    runs at `at_day` `at_hour`:45 with a +40% monthly profile, anchored on
    Monday's 1,000: its path ends at about 1,040 over the four remaining
    rows (+4%, UP). Returns the new envelope, the holding and Monday's
    signals set where ADD would fire."""
    from core.intelligence.rl.algorithms.price_interpolator import ForecastProfile
    import core.intelligence.rl.nse_calendar as cal
    monkeypatch.setattr(settings, "PREDICTION_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(gf.settings, "RL_REFORECAST_ENABLED", True)
    monkeypatch.setattr(gf.settings, "RL_REFORECAST_MAX_PER_MONTH", 2)
    _store(tmp_path).save_envelope(_envelope(1000.0))
    rf._patch_pipeline(monkeypatch, tmp_path, base_close=1000.0)
    monkeypatch.setattr(gf.PriceInterpolator, "get_profile", lambda self, **kw: ForecastProfile(
        monthly_return_pct=40.0, path_shape="linear", confidence_band_daily_pct=1.0,
        reasoning="test", source="llm"))
    monkeypatch.setattr(gf, "_review_session_close", _real_review_session_close)
    monkeypatch.setattr(dr, "_fetch_session_close",
                        lambda ticker, on: SessionClose(close=1000.0, bar_date=on, source="agree"))
    stamp = datetime(at_day.year, at_day.month, at_day.day, at_hour, 45, tzinfo=IST)
    monkeypatch.setattr(gf, "now_ist", lambda: stamp)
    monkeypatch.setattr(cal, "now_ist", lambda: stamp)
    out = gf.regenerate_envelope(ticker=TICKER, sector=SECTOR, reason="shock",
                                 trigger="external_shock", review_date=MON)
    assert out is not None
    holding, sig = _signals(VerdictStore(TICKER, sector=SECTOR))
    return out, holding, sig


def test_end_to_end_a_reforecast_after_the_close_is_not_read(tmp_path, monkeypatch):
    out, holding, sig = _real_round_trip(tmp_path, monkeypatch, TUE, 16)
    assert out.reforecast_history[-1].at == _at(TUE, 16, 45)
    assert out.reforecast_history[-1].archived_file
    assert out.daily_forecasts[-1].predicted_close > 1010.0       # the new path is UP
    assert sig.envelope_direction == "FLAT"                        # Monday's archived path
    assert sig.envelope_late_direction == "UP"
    assert "after the close of 2026-06-08" in sig.envelope_after_close
    assert "not available" not in sig.envelope_after_close         # the archive was read
    rec = _decide(holding, sig)
    assert rec.verdict == "HOLD" and "ENVELOPE_AFTER_CLOSE" in rec.notes


def test_end_to_end_a_reforecast_before_the_close_is_read(tmp_path, monkeypatch):
    """The same re-forecast at Monday 10:45, before Monday's close: read, UP, ADD."""
    out, holding, sig = _real_round_trip(tmp_path, monkeypatch, MON, 10)
    assert sig.envelope_after_close == "" and sig.envelope_direction == "UP"
    assert _decide(holding, sig).verdict == "ADD"

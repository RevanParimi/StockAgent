"""
tests/unit/test_issue_time_fix031.py
====================================
FIX-031: every input a decision at a session's close reads is from before
that close (15:30 IST, the clock of `shelf.close_before_decision`).

Every expected figure is worked by hand from the fixture's numbers and that
one rule, never asked of the code under test.

Calendar (all trading days; checked below): Mon 8, Tue 9, Wed 10, Thu 11,
Fri 12, Mon 15 and Tue 16 Jun 2026. The 16:30 job on day T reviews the
session before T and books its decisions at that session's close, so the
review of Monday runs on Tuesday at about 16:30, after Tuesday's close too.

What a decision at a close may read, by the rule:
  * a thesis review: only one written before the close (`written_at`); the
    review of Monday, written Tuesday 16:30, first counts at Wednesday's close;
  * a forecast row's confidence: as it stood at the close (`confidence_at`
    undoes every daily-review revision made at or after it);
  * a company event: published before the close, and counted for 5 closes
    from the first close after it;
  * a research verdict (score history): run before the close;
  * a deep dive's invalidation level: a dive keeps only its day and counts
    as made at that day's close;
  * a watchlist analysis: run before the close (FIX-029, checked here);
  * a re-forecast: does not rewrite the row of a session already closed.
A grade and a regime label computed after the close from that close's own
market data are not "after the close" information; they stay as they are.
"""
from __future__ import annotations

import json
import random
from datetime import date, datetime, timedelta
from types import SimpleNamespace

import pytest

import core.intelligence.rl.workflows.daily_review as dr
from backend.shared.schemas.events import CompanyEvent
from backend.shared.schemas.discovery import ShelfIdea
from backend.shared.schemas.feedback import (ConfidenceRevision, DailyFeedbackLog,
                                             DailyForecast, FeedbackEntry, PredictionEnvelope,
                                             ReforecastEvent, RevisedContext, ThesisReview)
from backend.shared.schemas.portfolio import Holding, Portfolio
from core.config import settings
from core.discovery.candidates import watchlist_idea
from core.intelligence.rl.nse_calendar import IST, is_trading_day, session_close_at
from core.intelligence.rl.stores.prediction_store import PredictionStore
from core.intelligence.rl.workflows import generate_forecast as gf
from core.portfolio import exit_shadow as xs
from core.portfolio.advisor import (build_signals, confidence_at, decide,
                                    reforecasts_after_close, written_before)
from services.data.verdict_store import VerdictStore
from tests.unit.intelligence.rl import test_reforecast as rf

MON, TUE, WED, THU, FRI = (date(2026, 6, d) for d in (8, 9, 10, 11, 12))
MON2, TUE2 = date(2026, 6, 15), date(2026, 6, 16)
SAT = date(2026, 6, 6)
TICKER, SECTOR, CYCLE = "MARUTI", "automobile", "MARUTI_2026-06"
DATES = [d.isoformat() for d in (MON, TUE, WED, THU, FRI)]


def _at(day: date, hh: int, mm: int) -> str:
    return datetime(day.year, day.month, day.day, hh, mm, tzinfo=IST).isoformat()


def _utc(day: date, hh: int, mm: int) -> str:
    """A score-history run_at as the store keeps it: naive UTC."""
    return f"{day.isoformat()}T{hh:02d}:{mm:02d}:00"


def test_the_fixture_calendar_is_seven_trading_days():
    assert all(is_trading_day(d) for d in (MON, TUE, WED, THU, FRI, MON2, TUE2))
    assert not is_trading_day(SAT)


# ---------------------------------------------------------------------------
# Fixture: an envelope, a feedback log and the advisor through VerdictStore
# ---------------------------------------------------------------------------

def _envelope(end: float, conf: float = 0.7, scores: dict | None = None) -> PredictionEnvelope:
    """Five rows Mon..Fri from 1,000, ending at `end` (the last row decides the drift)."""
    rows = [DailyForecast(
        day=i + 1, date=d, predicted_close=round(1000.0 + (end - 1000.0) * (i + 1) / 5, 4),
        predicted_verdict="BUY", confidence=conf, predicted_agent_scores=dict(scores or {}))
        for i, d in enumerate(DATES)]
    return PredictionEnvelope(ticker=TICKER, sector=SECTOR, cycle_id=CYCLE,
                              generated_at="2026-06-01T09:00:00", base_close=1000.0,
                              daily_forecasts=rows)


def _entry(on: date, intact: bool | None, written_at: str | None) -> FeedbackEntry:
    """A feedback entry for session `on`: a correct NORMAL day, with a thesis
    review when `intact` is not None. `written_at` None = stored before FIX-031."""
    review = (ThesisReview(thesis_intact=intact, horizon_confidence_multiplier=0.75)
              if intact is not None else None)
    extra = {"written_at": written_at} if written_at is not None else {}
    return FeedbackEntry(day=1, date=on.isoformat(), predicted_close=1000.0,
                         actual_close=1000.0, price_error_pct=-2.9, predicted_verdict="BUY",
                         actual_direction="DOWN", direction_correct=True, regime_label="NORMAL",
                         thesis_review=review, **extra)


def _ps(tmp_path, monkeypatch) -> PredictionStore:
    monkeypatch.setattr(settings, "PREDICTION_DATA_DIR", str(tmp_path))
    return PredictionStore(TICKER, sector=SECTOR, base_dir=str(tmp_path))


def _holding(avg: float = 1000.0) -> Holding:
    return Holding(symbol=TICKER, sector=SECTOR, qty=100, avg_buy_price=avg,
                   adj_avg_price=avg, adj_qty=100, buy_date="2026-05-04")


def _signals(review: date, close: float = 1000.0, avg: float = 1000.0):
    """The real advisor's signals for `review`'s close, with the inputs this
    story does not touch set where every rule may fire (7-day accuracy 0.70,
    a 5% position, an actionable forecast, the day's regime established)."""
    h = _holding(avg)
    p = Portfolio(user_id="u", holdings=[h], cash_deployable=900_000.0)
    sig = build_signals(h, p, review, VerdictStore(TICKER, sector=SECTOR), {}, close=close)
    return h, sig.model_copy(update={"direction_accuracy_7d": 0.70, "position_weight_pct": 5.0,
                                     "price_fresh": True, "forecast_gate": "actionable",
                                     "regime_unavailable": "", "regime_label": "NORMAL"})


# ---------------------------------------------------------------------------
# F1: the thesis the legacy rule sells on is judged after the close
# ---------------------------------------------------------------------------

def test_f1_mondays_thesis_judged_on_tuesday_first_sells_at_wednesdays_close(tmp_path,
                                                                            monkeypatch):
    """The path ends at 970: from a 1,000 close that is -3.0%, past the 1%
    band: DOWN at every close below. Monday missed by 2.9%, so Tuesday's 16:30
    run reviews the thesis on news up to then and writes "not intact" in
    Monday's entry. By the rule:
      Monday's close (Tuesday's run):    written after it -> not read -> HOLD
      Tuesday's close (Wednesday's run): 16:30 is after 15:30 -> HOLD
      Wednesday's close (Thursday's run): read -> thesis_break -> EXIT at 1,000."""
    ps = _ps(tmp_path, monkeypatch)
    ps.save_envelope(_envelope(970.0))
    ps.save_feedback_log(DailyFeedbackLog(ticker=TICKER, sector=SECTOR, cycle_id=CYCLE, entries=[
        _entry(MON, intact=False, written_at=_at(TUE, 16, 30))]))
    for review, want, thesis in ((MON, "HOLD", None), (TUE, "HOLD", None),
                                 (WED, "EXIT", False)):
        h, sig = _signals(review)
        assert sig.envelope_direction == "DOWN", review
        assert sig.thesis_intact is thesis, review
        rec = decide(sig, h, "balanced")
        assert rec.verdict == want, review
        assert ("thesis_break" in rec.triggers) == (want == "EXIT"), review


def test_f1_the_latest_review_written_before_the_close_is_read(tmp_path, monkeypatch):
    """Thursday 4 Jun's entry says "not intact", written Friday 16:30;
    Monday's own says "intact", written Tuesday 16:30. Monday's decision
    reads Thursday's (the newest written before Monday's close): EXIT on the
    DOWN path. The decision at Wednesday's close reads Monday's: HOLD."""
    ps = _ps(tmp_path, monkeypatch)
    ps.save_envelope(_envelope(970.0))
    ps.save_feedback_log(DailyFeedbackLog(ticker=TICKER, sector=SECTOR, cycle_id=CYCLE, entries=[
        _entry(date(2026, 6, 4), intact=False, written_at=_at(date(2026, 6, 5), 16, 30)),
        _entry(MON, intact=True, written_at=_at(TUE, 16, 30))]))
    h, sig = _signals(MON)
    assert sig.thesis_intact is False and decide(sig, h, "balanced").verdict == "EXIT"
    h, sig = _signals(WED)
    assert sig.thesis_intact is True and decide(sig, h, "balanced").verdict == "HOLD"


def test_f1_entries_stored_before_fix031():
    """No `written_at`: an entry dated on or after the close's day is after it
    (its review graded that close); an earlier one counts as before, as a
    re-forecast without a time does. An unreadable time counts as after."""
    closed = session_close_at(MON)
    assert not written_before(_entry(MON, False, None), closed)
    assert not written_before(_entry(TUE, False, None), closed)
    assert written_before(_entry(FRI - timedelta(days=7), False, None), closed)   # Fri 5 Jun
    assert not written_before(_entry(date(2026, 6, 5), False, "not a time"), closed)
    # Stamped: a minute before the close counts, at the close does not.
    assert written_before(_entry(date(2026, 6, 5), False, _at(MON, 15, 29)), closed)
    assert not written_before(_entry(date(2026, 6, 5), False, _at(MON, 15, 30)), closed)
    # A naive stamp is IST: 15:00 is before 15:30 (read as UTC it would be 20:30).
    assert written_before(_entry(date(2026, 6, 5), False, "2026-06-08T15:00:00"), closed)


# ---------------------------------------------------------------------------
# F1 (Step 7b): the confidence revision is made after the close
# ---------------------------------------------------------------------------

def _revise(ps, monkeypatch, at: str, reviewed: date, multiplier: float | None):
    """The real Step 7b with one agent `a` scored 0.5 and weighted 1.0, no
    daily adjustment, no reversion prior: blended = 0.7 x confidence + 0.3 x 0.5,
    times the thesis multiplier when one is given."""
    monkeypatch.setattr(dr, "now_ist", lambda: datetime.fromisoformat(at))
    thesis = (ThesisReview(thesis_intact=False, horizon_confidence_multiplier=multiplier)
              if multiplier is not None else None)
    dr._revise_remaining_forecasts(
        ticker=TICKER, store=ps, reviewed_date=reviewed.isoformat(), new_weights={"a": 1.0},
        revised_context=RevisedContext(), thesis_review=thesis, cycle_id=CYCLE)


def test_step_7b_revisions_are_read_as_they_stood_at_the_close(tmp_path, monkeypatch):
    """Issued at 0.70 on every row (a flat path at 1,000).
      Mon 16:30, the review of Fri 5 Jun revises Mon..Fri: 0.7 x 0.70 + 0.15 = 0.64.
      Tue 16:30, the review of Mon (thesis x 0.5) revises Tue..Fri:
        (0.7 x 0.64 + 0.15) x 0.5 = 0.598 x 0.5 = 0.299.
    Read at each close:
      Monday's: both after it -> every row 0.70: confidence 0.70, trend 0.0
      Tuesday's: Monday's revision before, Tuesday's after -> 0.64, trend 0.0
      Wednesday's: both before -> 0.299, trend 0.0
    As stored, Monday's close would read 0.64 then 0.299 x 4: mean 0.3672,
    trend -0.341, and with the holding 25% up (bought at 800) that TRIMs."""
    ps = _ps(tmp_path, monkeypatch)
    ps.save_envelope(_envelope(1000.0, conf=0.70, scores={"a": 0.5}))
    _revise(ps, monkeypatch, _at(MON, 16, 30), date(2026, 6, 5), None)
    _revise(ps, monkeypatch, _at(TUE, 16, 30), MON, 0.5)
    rows = ps.load_envelope(CYCLE).daily_forecasts
    assert [r.confidence for r in rows] == [0.64, 0.299, 0.299, 0.299, 0.299]
    assert rows[0].confidence_revisions == [ConfidenceRevision(at=_at(MON, 16, 30), before=0.7)]
    assert rows[1].confidence_revisions == [ConfidenceRevision(at=_at(MON, 16, 30), before=0.7),
                                            ConfidenceRevision(at=_at(TUE, 16, 30), before=0.64)]
    for review, conf in ((MON, 0.70), (TUE, 0.64), (WED, 0.299)):
        h, sig = _signals(review, avg=800.0)
        assert (sig.confidence, sig.confidence_trend) == (conf, 0.0), review
        assert decide(sig, h, "balanced").verdict == "HOLD", review
    # The stored figures, read without the clock, would have trimmed on Monday.
    h, sig = _signals(MON, avg=800.0)
    stale = sig.model_copy(update={"confidence": 0.3672, "confidence_trend": -0.341})
    assert decide(stale, h, "balanced").verdict == "TRIM"


def test_confidence_at_undoes_newest_first_and_unreadable_counts_as_after():
    row = DailyForecast(day=1, date="2026-06-10", predicted_close=1000.0, predicted_verdict="BUY",
                        confidence=0.3, confidence_revisions=[
                            ConfidenceRevision(at=_at(MON, 16, 30), before=0.7),
                            ConfidenceRevision(at="garbled", before=0.6),
                            ConfidenceRevision(at=_at(TUE, 16, 30), before=0.5)])
    # Revisions are appended in time order: once the newest is before the close,
    # so is every older one (the unreadable one lies between Mon and Tue 16:30).
    assert confidence_at(row, session_close_at(WED)) == 0.3
    # At Tuesday's close: Tuesday 16:30 undone (0.5), the unreadable one too (0.6).
    assert confidence_at(row, session_close_at(TUE)) == 0.6
    assert confidence_at(row, session_close_at(MON)) == 0.7
    plain = DailyForecast(day=1, date="2026-06-10", predicted_close=1000.0,
                          predicted_verdict="BUY", confidence=0.42)
    assert confidence_at(plain, session_close_at(MON)) == 0.42   # stored before FIX-031


def test_the_real_review_stamps_its_entry_and_its_revisions(tmp_path, monkeypatch):
    """The real daily review (the shock-path seams: no LLM, no network) of
    session D, run the next day at 16:30, with a thesis review saying "not
    intact" (x 0.75, no re-forecast). The entry and the next row's revision
    carry that time; a decision at D's close reads neither, one at a close
    after the run reads the entry."""
    from core.intelligence.rl.agents.feedback_agent import FeedbackAgent
    from core.intelligence.rl.agents.thesis_reviewer import ThesisReviewer
    from tests.unit.intelligence.rl import test_shock_path as sp
    store, cycle = sp._setup_store(tmp_path)
    sp._patch_common(dr, monkeypatch, tmp_path, actual_close=98.0)
    monkeypatch.setattr(FeedbackAgent, "run",
                        lambda self, fb_input, ledger: sp._fb_output("direction_flip"))
    monkeypatch.setattr(ThesisReviewer, "should_review", lambda self, *a, **k: True)
    monkeypatch.setattr(ThesisReviewer, "review", lambda self, **kw: ThesisReview(
        thesis_intact=False, horizon_confidence_multiplier=0.75))
    monkeypatch.setattr(dr, "regenerate_envelope", lambda **kw: None)
    ran = datetime.combine(sp.REVIEW_DATE + timedelta(days=1),
                           datetime.min.time()).replace(hour=16, minute=30, tzinfo=IST)
    monkeypatch.setattr(dr, "now_ist", lambda: ran)
    summary = dr.run_daily_review(sp.TICKER, sp.REVIEW_DATE, sector=sp.SECTOR)
    assert summary["status"] == "completed", summary
    entry = store.load_feedback_log(cycle).entries[-1]
    assert entry.written_at == ran.isoformat() and entry.thesis_review.thesis_intact is False
    nxt = store.load_envelope(cycle).daily_forecasts[1]
    assert [(r.at, r.before) for r in nxt.confidence_revisions] == [(ran.isoformat(), 0.5)]
    closed = session_close_at(sp.REVIEW_DATE)
    assert not written_before(entry, closed) and confidence_at(nxt, closed) == 0.5
    assert written_before(entry, session_close_at(sp.REVIEW_DATE + timedelta(days=2)))


# ---------------------------------------------------------------------------
# F2: the evidence rule by the 15:30 clock
# ---------------------------------------------------------------------------

def _event(published: str | None, n: int = 1, direction="negative", materiality="high",
           symbol=TICKER) -> CompanyEvent:
    return CompanyEvent(id=f"e{n}-{published}", symbol=symbol,
                        what="Results: net loss against a profit a year ago",
                        category="results", direction=direction, materiality=materiality,
                        source="nse_announcement", published_at=published,
                        fetched_at="2026-06-16T10:00:00+05:30")


def _counted(published: str | None) -> list[date]:
    """The closes, Mon 8 to Tue 16 Jun, at which one event is case evidence."""
    days = [MON, TUE, WED, THU, FRI, MON2, TUE2]
    return [d for d in days if xs.recent_negative_events([_event(published)], TICKER, d)]


def test_f2_filings_at_1810_and_1410_on_monday():
    """5 closes each, from the first close after publication:
      14:10 Monday -> Mon, Tue, Wed, Thu, Fri
      18:10 Monday -> Tue, Wed, Thu, Fri, Mon 15
      at 15:30 exactly (the close itself) -> as 18:10
      a date-only "2026-06-08" counts as made at Monday's close -> as 18:10
      Saturday 6 Jun (date only) -> Mon .. Fri, as an 11:00 Monday filing."""
    assert _counted(_at(MON, 14, 10)) == [MON, TUE, WED, THU, FRI]
    assert _counted(_at(MON, 18, 10)) == [TUE, WED, THU, FRI, MON2]
    assert _counted(_at(MON, 15, 30)) == [TUE, WED, THU, FRI, MON2]
    assert _counted(_at(MON, 15, 29)) == [MON, TUE, WED, THU, FRI]
    assert _counted("2026-06-08") == [TUE, WED, THU, FRI, MON2]
    assert _counted("2026-06-06") == [MON, TUE, WED, THU, FRI]
    assert _counted(_at(MON, 11, 0)) == [MON, TUE, WED, THU, FRI]
    assert _counted(None) == [] and _counted("not a date") == []
    # A naive time is IST: 15:00 counts for Monday's close.
    assert _counted("2026-06-08T15:00:00") == [MON, TUE, WED, THU, FRI]


def _record(run_at: str, verdict="SELL", gate="actionable") -> dict:
    return {"ticker": TICKER, "run_at": run_at, "verdict": verdict, "final_score": 0.3,
            "report_json": json.dumps({"decision_gate": {"status": gate}})}


def test_f2_an_analysis_at_2000_on_monday_is_tuesdays_research_verdict():
    """20:00 IST Monday is 14:30 UTC: after Monday's close, so Monday's
    decision reads the 11:00 IST (05:30 UTC) BUY, and Tuesday's the SELL.
    15:30 IST exactly (10:00 UTC) is at the close: not Monday's."""
    bought = date(2026, 5, 4)
    records = [_record(_utc(MON, 5, 30), "BUY"), _record(_utc(MON, 14, 30), "SELL")]
    assert xs.latest_actionable_verdict(records, TICKER, MON, bought)["verdict"] == "BUY"
    assert xs.latest_actionable_verdict(records, TICKER, TUE, bought)["verdict"] == "SELL"
    assert xs.latest_actionable_verdict([_record(_utc(MON, 10, 0))], TICKER, MON, bought) is None
    assert xs.latest_actionable_verdict([_record(_utc(MON, 9, 59))], TICKER, MON,
                                        bought)["verdict"] == "SELL"
    # The daily review's own evening run (16:35 IST) is never the same day's.
    assert xs.latest_actionable_verdict([_record(_utc(MON, 11, 5))], TICKER, MON, bought) is None


def _idea(dived: str, level=1100.0) -> ShelfIdea:
    return ShelfIdea(symbol=TICKER, sector=SECTOR, added=dived, dived=dived, conviction=0.7,
                     invalidation_level=level, status="promoted")


def test_a_deep_dive_dated_the_session_counts_from_the_next_close():
    """A dive keeps only its day and counts as made at that day's close: one
    dated Monday sets no level for Monday's close and does for Tuesday's; a
    Saturday dive does for Monday's."""
    assert xs.invalidation_for([_idea("2026-06-08")], TICKER, MON) == (0.0, "", None)
    assert xs.invalidation_for([_idea("2026-06-08")], TICKER, TUE)[0] == 1100.0
    assert xs.invalidation_for([_idea("2026-06-06")], TICKER, MON)[0] == 1100.0
    # An earlier dive's level stands until the later one counts.
    ideas = [_idea("2026-06-06", 900.0), _idea("2026-06-08", 1100.0)]
    assert xs.invalidation_for(ideas, TICKER, MON)[0] == 900.0
    assert xs.invalidation_for(ideas, TICKER, TUE)[0] == 1100.0


# ---------------------------------------------------------------------------
# I-2: a re-forecast keeps the row of a session already closed
# ---------------------------------------------------------------------------

def _regenerate(tmp_path, monkeypatch, at: datetime, review: date):
    ps = _ps(tmp_path, monkeypatch)
    monkeypatch.setattr(gf.settings, "RL_REFORECAST_ENABLED", True)
    monkeypatch.setattr(gf.settings, "RL_REFORECAST_MAX_PER_MONTH", 2)
    ps.save_envelope(_envelope(1000.0))
    before = [r.model_dump() for r in ps.load_envelope(CYCLE).daily_forecasts]
    rf._patch_pipeline(monkeypatch, tmp_path, base_close=1000.0)
    monkeypatch.setattr(gf, "now_ist", lambda: at)
    out = gf.regenerate_envelope(ticker=TICKER, sector=SECTOR, reason="shock",
                                 trigger="thesis_break", review_date=review)
    return ps, before, out


@pytest.mark.parametrize("at, review, kept", [
    (datetime(2026, 6, 9, 16, 45, tzinfo=IST), MON, 2),    # Tue 16:45: Mon reviewed, Tue closed
    (datetime(2026, 6, 10, 0, 30, tzinfo=IST), MON, 2),    # Wed 00:30: Wednesday still open
    (datetime(2026, 6, 10, 15, 30, tzinfo=IST), MON, 3),   # Wed 15:30: Wednesday has closed
    (datetime(2026, 6, 8, 16, 45, tzinfo=IST), MON, 1),    # Mon 16:45, same day: only Monday
    (datetime(2026, 6, 9, 8, 45, tzinfo=IST), TUE, 2),     # pre-open Tue: Mon, Tue (as before)
])
def test_i2_a_reforecast_keeps_closed_rows(tmp_path, monkeypatch, at, review, kept):
    """Every row on or before the review date, or whose session had closed
    when the re-forecast ran, stays byte-identical; the first new row is the
    first session still open, numbered on from the kept ones. The pre-open
    re-forecast (review date today, before the open) is unchanged."""
    ps, before, out = _regenerate(tmp_path, monkeypatch, at, review)
    assert out is not None
    after = [r.model_dump() for r in out.daily_forecasts]
    assert after[:kept] == before[:kept]
    assert all(a != b for a, b in zip(after[kept:], before[kept:]))
    assert [r["day"] for r in after] == [1, 2, 3, 4, 5]
    assert out.reforecast_history[-1].at == at.isoformat()


def test_i2_nothing_left_open_regenerates_nothing(tmp_path, monkeypatch):
    """Fri 12 Jun 16:00: every row after Monday has closed. No archive, no
    save, the cap untouched."""
    ps, before, out = _regenerate(tmp_path, monkeypatch,
                                  datetime(2026, 6, 12, 16, 0, tzinfo=IST), MON)
    assert out is None
    env = ps.load_envelope(CYCLE)
    assert [r.model_dump() for r in env.daily_forecasts] == before
    assert env.reforecast_count == 0 and not (ps._dir / "archived_envelopes").exists()


# ---------------------------------------------------------------------------
# L3: FIX-027's two defensive branches
# ---------------------------------------------------------------------------

def _late(at: str) -> bool:
    env = _envelope(1000.0)
    env.reforecast_history = [ReforecastEvent(date="2026-06-08", reason="x", at=at)]
    return bool(reforecasts_after_close(env, MON))


def test_l3_an_unreadable_time_is_after_and_a_naive_time_is_ist():
    assert _late("not a time")                      # cannot be shown to be before
    assert not _late("2026-06-08T15:00:00")         # naive = IST 15:00, before 15:30
    assert _late("2026-06-08T15:30:00")             # at the close
    assert _late("2026-06-08T15:00:00+00:00")       # 15:00 UTC = 20:30 IST
    assert not _late("")                            # stored before FIX-027


# ---------------------------------------------------------------------------
# The invariant: nothing made or published after the close moves the decision
# ---------------------------------------------------------------------------

PRE_TIMES = [_at(date(2026, 6, 5), 16, 30), _at(MON, 9, 0), _at(MON, 15, 29)]
POST_TIMES = [_at(MON, 15, 30), _at(MON, 16, 30), _at(MON, 18, 10), _at(TUE, 8, 45),
              _at(TUE, 16, 30), _at(TUE, 16, 45)]
_PUBLISHED_PRE = [_at(date(2026, 6, 3), 10, 0), "2026-06-06", _at(MON, 14, 10)]
_PUBLISHED_POST = [_at(MON, 15, 30), _at(MON, 18, 10), "2026-06-08", _at(TUE, 9, 0)]
_RUN_PRE = [_utc(date(2026, 6, 5), 11, 5), _utc(MON, 5, 30), _utc(MON, 9, 59)]
_RUN_POST = [_utc(MON, 10, 0), _utc(MON, 11, 5), _utc(TUE, 11, 5)]


def _ops(rng: random.Random, times: list[str]) -> list[tuple]:
    """A random history of envelope operations at `times`: a confidence
    revision (new values for the rows after the reviewed day) or a re-forecast
    (a new path end)."""
    ops = []
    for t in rng.sample(times, rng.randint(0, len(times))):
        if rng.random() < 0.6:
            ops.append((t, "revise", [round(rng.uniform(0.2, 0.9), 4) for _ in DATES]))
        else:
            ops.append((t, "reforecast", rng.choice([940.0, 970.0, 1000.0, 1030.0, 1060.0])))
    return ops


def _write_json(path, model) -> None:
    """The invariant tests the readers, not the store's writer: files are
    written directly (no temp-file rename, which Windows can refuse when a
    scanner holds the file)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(model.model_dump(), ensure_ascii=False), encoding="utf-8")


def _write_envelope(ps: PredictionStore, issued_end: float, ops: list[tuple]) -> None:
    """Apply `ops` in time order as the review and regenerate_envelope do: a
    revision records (time, value before) on each changed row after the day
    it reviews (the day before its run); a re-forecast archives the envelope
    as it stands (`archived_envelopes/2026-06_v<n>.json`), keeps the rows of
    the reviewed day and of every session closed at its time, and draws the
    rest anew. The final envelope is written once."""
    env = _envelope(issued_end)
    for t, kind, arg in sorted(ops, key=lambda o: datetime.fromisoformat(o[0])):
        at = datetime.fromisoformat(t)
        reviewed = (at.date() - timedelta(days=1)).isoformat()
        if kind == "revise":
            for row, value in zip(env.daily_forecasts, arg):
                if row.date > reviewed and value != row.confidence:
                    row.confidence_revisions.append(ConfidenceRevision(at=t, before=row.confidence))
                    row.confidence = value
            continue
        archived = ps._archived_envelopes_dir() / f"2026-06_v{env.reforecast_count + 1}.json"
        _write_json(archived, env)
        env = env.model_copy(deep=True)
        fresh = _envelope(arg, conf=0.55)
        env.daily_forecasts = [
            old if (old.date <= reviewed or session_close_at(date.fromisoformat(old.date)) <= at)
            else new for old, new in zip(env.daily_forecasts, fresh.daily_forecasts)]
        env.reforecast_history.append(ReforecastEvent(date=reviewed, reason="thesis_break",
                                                      archived_file=str(archived), at=t))
        env.reforecast_count += 1
    _write_json(ps._envelope_path(CYCLE), env)


def _world(tmp_path, monkeypatch, pre: dict, post: dict):
    """Write one world (pre-close inputs + post-close inputs) under `tmp_path`
    and return what the decision at Monday's close produces: the legacy and
    evidence AdviceRecords and the shadow row."""
    ps = _ps(tmp_path, monkeypatch)
    _write_envelope(ps, pre["end"], pre["ops"] + post["ops"])
    entries = [_entry(date(2026, 6, 4), pre["thesis_thu"], _at(date(2026, 6, 5), 16, 30)),
               _entry(date(2026, 6, 5), post["thesis_fri"], post["fri_written"]),
               _entry(MON, post["thesis_mon"], post["mon_written"])]
    _write_json(ps._feedback_log_path(CYCLE),
                DailyFeedbackLog(ticker=TICKER, sector=SECTOR, cycle_id=CYCLE, entries=entries))
    h, sig = _signals(MON, avg=800.0)
    events = [_event(p, n=i, direction=d) for i, (p, d) in enumerate(pre["events"] + post["events"])]
    records = [_record(r, v) for r, v in pre["records"] + post["records"]]
    ideas = [_idea(d, lvl) for d, lvl in pre["ideas"] + post["ideas"]]
    ev = xs.exit_evidence(h, MON, events=events, records=records, ideas=ideas)
    legacy = decide(sig, h, "balanced")
    by_evidence = decide(sig, h, "balanced", exit_rule="evidence", evidence=ev)
    row = xs.shadow_row(on=MON, user_id="u", mode="shadow", close=1000.0, legacy=legacy,
                        evidence_rec=by_evidence, evidence=ev, buy_date=h.buy_date)
    return (_decided(legacy), _decided(by_evidence), row.model_dump(), _read(sig),
            _disclosed(legacy, sig))


# FIX-027's disclosure: a record names a re-forecast made after the close that
# it did not act on (`envelope_after_close`, the note ENVELOPE_AFTER_CLOSE, and
# so `rationale_hash`), and the signals keep that path's direction
# (`envelope_late_direction`) for the note. They say what was NOT read.
_DISCLOSURE = ("envelope_after_close", "rationale_hash")


def _decided(rec) -> dict:
    out = {k: v for k, v in rec.model_dump().items() if k not in _DISCLOSURE}
    out["notes"] = [n for n in out["notes"] if n != "ENVELOPE_AFTER_CLOSE"]
    return out


def _read(sig) -> dict:
    return {k: v for k, v in sig.model_dump().items()
            if k not in ("envelope_after_close", "envelope_late_direction")}


def _disclosed(rec, sig) -> str:
    """'' or "named": a disclosure may only name a re-forecast made at or
    after the close, and the record carries it only with its note."""
    assert bool(rec.envelope_after_close) == ("ENVELOPE_AFTER_CLOSE" in rec.notes)
    if not sig.envelope_after_close:
        assert not rec.envelope_after_close and not sig.envelope_late_direction
        return ""
    named = sig.envelope_after_close.split(" re-forecast of ")[1].split(" is after")[0]
    assert datetime.fromisoformat(named) >= session_close_at(MON), named
    return "named"


def _pre(rng: random.Random) -> dict:
    return {
        "end": rng.choice([960.0, 1000.0, 1040.0]),
        "ops": _ops(rng, PRE_TIMES),
        "thesis_thu": rng.choice([None, True, False]),
        "events": [(p, rng.choice(["negative", "neutral"])) for p in
                   rng.sample(_PUBLISHED_PRE, rng.randint(0, 2))],
        "records": [(r, rng.choice(["SELL", "BUY"])) for r in rng.sample(_RUN_PRE, rng.randint(0, 2))],
        "ideas": [(d, rng.choice([900.0, 1100.0])) for d in
                  rng.sample(["2026-06-06", "2026-06-05"], rng.randint(0, 1))],
    }


def _post(rng: random.Random) -> dict:
    return {
        "ops": _ops(rng, POST_TIMES),
        "thesis_fri": rng.choice([None, True, False]),
        "fri_written": rng.choice([_at(MON, 16, 30), _at(MON, 23, 0), None]),
        "thesis_mon": rng.choice([None, True, False]),
        "mon_written": rng.choice([_at(TUE, 16, 30), None]),
        "events": [(p, rng.choice(["negative", "neutral"])) for p in
                   rng.sample(_PUBLISHED_POST, rng.randint(0, 3))],
        "records": [(r, rng.choice(["SELL", "BUY"])) for r in
                    rng.sample(_RUN_POST, rng.randint(0, 3))],
        "ideas": [(d, rng.choice([900.0, 1100.0])) for d in
                  rng.sample(["2026-06-08", "2026-06-09"], rng.randint(0, 2))],
    }


@pytest.mark.parametrize("seed", range(40))
def test_invariant_nothing_after_the_close_moves_mondays_decision(tmp_path, monkeypatch, seed):
    """Two worlds share every input made before Monday's 15:30 close and
    differ, at random, in every input made or published at or after it:
    re-forecasts and confidence revisions; the thesis reviews of Friday and
    Monday, written Monday 16:30 or later (Monday's also unstamped, dated on
    the close's day); events; research runs; deep dives. Monday's
    AdviceRecords under both rules, the shadow row and the signals read are
    equal, apart from FIX-027's disclosure of a later re-forecast, which may
    only name one made at or after the close (`_disclosed`)."""
    rng = random.Random(seed)
    pre = _pre(rng)
    a, b = _post(rng), _post(rng)
    # A Friday entry stored without a stamp counts as written before Monday's
    # close (the rule for entries stored before FIX-031): a pre-close input,
    # equal in both worlds.
    if a["fri_written"] is None or b["fri_written"] is None:
        a["fri_written"] = b["fri_written"] = None
        b["thesis_fri"] = a["thesis_fri"]
    one = _world(tmp_path / "a", monkeypatch, pre, a)
    two = _world(tmp_path / "b", monkeypatch, pre, b)
    assert one[:4] == two[:4]


def test_invariant_is_not_vacuous_a_pre_close_input_moves_the_decision(tmp_path, monkeypatch):
    """The same worlds with a pre-close input changed do differ: Thursday's
    "not intact" (written Friday 16:30) on a DOWN path sells; "intact" does not."""
    pre = {"end": 960.0, "ops": [], "thesis_thu": False, "events": [], "records": [], "ideas": []}
    post = {"ops": [], "thesis_fri": None, "fri_written": _at(MON, 16, 30), "thesis_mon": None,
            "mon_written": _at(TUE, 16, 30), "events": [], "records": [], "ideas": []}
    sold = _world(tmp_path / "a", monkeypatch, pre, post)
    kept = _world(tmp_path / "b", monkeypatch, {**pre, "thesis_thu": True}, post)
    assert sold[0]["verdict"] == "EXIT" and kept[0]["verdict"] == "HOLD"
    # And a pre-close filing (14:10 Monday) is case evidence; the same at 18:10 is not.
    filed = _world(tmp_path / "c", monkeypatch,
                   {**pre, "thesis_thu": True, "events": [(_at(MON, 14, 10), "negative")]}, post)
    assert filed[2]["evidence"]["event_ids"] and filed[1]["triggers"] == ["case_broken"]


# ---------------------------------------------------------------------------
# I-1 (FIX-029 built it): the watchlist reads the analysis made before the close
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("seed", range(20))
def test_invariant_the_watchlist_offer_ignores_analyses_after_the_close(tmp_path, monkeypatch,
                                                                       seed):
    """W on the user's watchlist, its close ₹1,000 every day. Analyses run
    before Monday 2 Nov's 15:30 close (10:00 UTC) are equal in both worlds;
    those at or after it differ at random (BUY/SELL, score). Monday's offer
    (the candidate or the reason) is the same."""
    import tests.unit.test_idea_supply_pr004 as pr004
    from services.data.stores.score_store import ScoreStore
    import tests.unit.test_every_door_fix029 as f29
    f29._watch_rules(monkeypatch)
    rng = random.Random(seed)
    session = date(2026, 11, 2)
    window = pr004._eod_window(["W"], days=60, end=date(2026, 11, 10), close=1000.0)
    pre = [(f"2026-10-{d:02d}T11:05:00", rng.choice(["BUY", "SELL"]), rng.choice([0.5, 0.7]))
           for d in rng.sample([28, 29, 30], rng.randint(0, 3))]
    pre += [("2026-11-02T09:59:00", rng.choice(["BUY", "SELL"]), 0.7)] if rng.random() < 0.5 else []

    def post():
        return [(s, rng.choice(["BUY", "SELL"]), rng.choice([0.5, 0.7])) for s in
                rng.sample(["2026-11-02T10:00:00", "2026-11-02T11:05:00", "2026-11-03T11:05:00"],
                           rng.randint(0, 3))]

    offers = []
    for name, extra in (("a", post()), ("b", post())):
        scores = ScoreStore(db_path=str(tmp_path / f"{name}.db"))
        for run_at, verdict, score in pre + extra:
            f29._analyse(scores, run_at, verdict, score)
        item = SimpleNamespace(symbol="W", source="user", sector="pharma")
        idea, why = watchlist_idea(item, session, scores.get_latest_before, window,
                                   pr004.companies("W"), managed={})
        offers.append((idea.model_dump() if idea else None, why))
    assert offers[0] == offers[1]

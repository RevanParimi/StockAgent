"""Task 11: month-start forecast — calendar-tag emphasis + narrowed legacy
micro-adjust.

- _apply_ledger_micro_adjustments() must SKIP lessons that carry trigger_tags
  (those fire via apply_lesson_emphasis on matching calendar days instead),
  while still applying the legacy category-based micro-adjustment to
  untagged lessons.
- _build_daily_forecasts() must apply apply_lesson_emphasis() per day using
  calendar_day_tags(d) so tagged lessons (e.g. monsoon) boost/dampen the
  predicted_agent_scores on matching forecast rows.
"""
from datetime import date, timedelta

from backend.shared.schemas.feedback import LearningLedger, Lesson
from core.schemas.pipeline import FinalReport, WeightedAgentScore
from core.intelligence.rl.workflows.generate_forecast import (
    _apply_ledger_micro_adjustments,
    _build_daily_forecasts,
)


def _tagged_lesson():
    return Lesson(lesson_id="L1", date_learned="2026-06-01", category="macro",
                   pattern="p", observation="o", rule="r", confidence=0.9, occurrences=3,
                   last_seen=date.today().isoformat(),
                   trigger_tags=["monsoon"], prioritise_agents=["risk_macro"])


def _untagged_lesson():
    return Lesson(lesson_id="L2", date_learned="2026-06-01", category="macro",
                   pattern="p2", observation="o", rule="r", confidence=0.9, occurrences=3,
                   last_seen=date.today().isoformat())


def test_micro_adjust_skips_tagged_lessons():
    scores = {"risk_macro": 0.5}
    led_tagged = LearningLedger(ticker="T", sector="automobile",
                                 last_updated="2026-06-11", lessons=[_tagged_lesson()])
    led_untagged = LearningLedger(ticker="T", sector="automobile",
                                   last_updated="2026-06-11", lessons=[_untagged_lesson()])
    assert _apply_ledger_micro_adjustments(scores, led_tagged) == scores      # skipped
    assert _apply_ledger_micro_adjustments(scores, led_untagged)["risk_macro"] > 0.5


def _june_report() -> FinalReport:
    return FinalReport(
        ticker="MARUTI",
        company_name="Maruti Suzuki",
        verdict="NEUTRAL",
        final_score=0.5,
        weighted_agent_scores={
            "risk_macro": WeightedAgentScore(raw=0.5, weight=1.0, weighted=0.5),
            "sales_demand": WeightedAgentScore(raw=0.5, weight=1.0, weighted=0.5),
        },
        conviction_drivers=[],
        agent_outputs={},
    )


def test_build_daily_forecasts_applies_calendar_tag_emphasis():
    """A trading date in the monsoon window (June-Sept) must apply
    apply_lesson_emphasis() for a lesson tagged trigger_tags=["monsoon"]."""
    report = _june_report()
    # June 2026 trading date — within the monsoon window (calendar_day_tags
    # returns ["monsoon"] for any date with 6 <= month <= 9).
    monsoon_date = date(2026, 6, 15)
    ledger = LearningLedger(
        ticker="MARUTI", sector="automobile", last_updated="2026-06-11",
        lessons=[_tagged_lesson()],
    )

    forecasts = _build_daily_forecasts(
        report, base_close=100.0, trading_dates=[monsoon_date],
        seasonal_calendar=None, learning_ledger=ledger,
        forecast_profile=None, agent_predictions=None, regime_label="NORMAL",
    )

    assert len(forecasts) == 1
    # The tagged lesson prioritises risk_macro -> score boosted above the base 0.5.
    assert forecasts[0].predicted_agent_scores["risk_macro"] > 0.5


def test_build_daily_forecasts_no_emphasis_outside_calendar_window():
    """A trading date OUTSIDE the monsoon window must NOT trigger the
    monsoon-tagged lesson's emphasis."""
    report = _june_report()
    # December — not in monsoon (6-9), not budget (Jan25-Feb7), not festive (Oct/Nov).
    winter_date = date(2026, 12, 10)
    ledger = LearningLedger(
        ticker="MARUTI", sector="automobile", last_updated="2026-06-11",
        lessons=[_tagged_lesson()],
    )

    forecasts = _build_daily_forecasts(
        report, base_close=100.0, trading_dates=[winter_date],
        seasonal_calendar=None, learning_ledger=ledger,
        forecast_profile=None, agent_predictions=None, regime_label="NORMAL",
    )

    assert len(forecasts) == 1
    assert forecasts[0].predicted_agent_scores["risk_macro"] == 0.5

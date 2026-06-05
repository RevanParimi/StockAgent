"""
Month-end seasonal pattern validation.

Extracted from daily_review.py Step 9.
Runs once at end of each month instead of every day.
Called from daily_review.py only when _is_last_trading_day_of_month() is True.
"""
from __future__ import annotations

import logging
from calendar import monthrange
from datetime import date

import core.intelligence.rl.nse_calendar as nse_calendar

logger = logging.getLogger(__name__)


def _is_last_trading_day_of_month(d: date) -> bool:
    """True if no trading days remain in d's month after d."""
    last_calendar_day = monthrange(d.year, d.month)[1]
    for day_num in range(d.day + 1, last_calendar_day + 1):
        try:
            if nse_calendar.is_trading_day(date(d.year, d.month, day_num)):
                return False
        except Exception:
            pass
    return True


def run_month_end_validation(
    ticker: str,
    sector: str,
    store,
    seasonal_ctx,
    seasonal_calendar,
    ticker_ledger,
    cycle_id: str,
    review_date: date,
) -> None:
    """
    Validate active seasonal patterns against this month's feedback log.
    Mutates ticker_ledger in-place. Saves ledger if any changes were made.
    Non-fatal — exceptions are caught and logged.
    """
    if not seasonal_ctx.is_seasonal_period:
        return

    try:
        from core.intelligence.seasonal.validator import SeasonalValidator
        from core.config import settings

        validator = SeasonalValidator(
            sector=sector,
            base_dir=settings.PREDICTION_DATA_DIR,
        )
        active_seeds = seasonal_calendar.active_patterns_on(review_date)
        feedback_log = store.load_feedback_log(cycle_id)

        ledger_dirty = False
        for pattern in active_seeds:
            result = validator.validate_pattern(
                pattern=pattern,
                review_date=review_date,
                feedback_log=feedback_log,
            )
            lesson = ticker_ledger.find_by_pattern(result.pattern_id)
            if lesson is None:
                continue
            if result.record.invalidated and lesson.still_valid:
                lesson.still_valid = False
                ledger_dirty = True
                logger.info(
                    "[month_end_validation] Lesson %s invalidated — pattern %s contradicted",
                    lesson.lesson_id, result.pattern_id,
                )
            elif result.record.validated_by_rl and result.direction_matched:
                lesson.confidence = min(1.0, lesson.confidence + 0.05)
                ledger_dirty = True

        validator.save_state()
        if ledger_dirty:
            store.save_learning_ledger(ticker_ledger)

        logger.info(
            "[month_end_validation] %s %s — %d patterns checked",
            ticker, review_date, len(active_seeds),
        )
    except Exception as exc:
        logger.warning(
            "[month_end_validation] Failed for %s on %s (non-fatal): %s",
            ticker, review_date, exc,
        )

from datetime import date
from unittest.mock import patch, MagicMock


def test_is_last_trading_day_when_no_more_trading_days():
    """Last trading day of month returns True when no more trading days remain."""
    from core.intelligence.rl.workflows.month_end_validation import _is_last_trading_day_of_month

    with patch("core.intelligence.rl.workflows.month_end_validation.nse_calendar") as mock_cal:
        mock_cal.is_trading_day.return_value = False  # no more trading days this month
        result = _is_last_trading_day_of_month(date(2026, 5, 29))

    assert result is True


def test_is_not_last_trading_day_when_more_days_remain():
    """Mid-month date returns False when more trading days remain."""
    from core.intelligence.rl.workflows.month_end_validation import _is_last_trading_day_of_month

    with patch("core.intelligence.rl.workflows.month_end_validation.nse_calendar") as mock_cal:
        mock_cal.is_trading_day.return_value = True  # more trading days exist
        result = _is_last_trading_day_of_month(date(2026, 5, 15))

    assert result is False


def test_run_month_end_validation_skips_when_not_seasonal():
    """run_month_end_validation does nothing when not in a seasonal period."""
    from core.intelligence.rl.workflows.month_end_validation import run_month_end_validation

    mock_ctx = MagicMock()
    mock_ctx.is_seasonal_period = False
    mock_store = MagicMock()

    run_month_end_validation(
        ticker="MARUTI", sector="automobile",
        store=mock_store, seasonal_ctx=mock_ctx,
        seasonal_calendar=MagicMock(), ticker_ledger=MagicMock(),
        cycle_id="MARUTI_2026-05", review_date=date(2026, 5, 29),
    )

    mock_store.load_feedback_log.assert_not_called()

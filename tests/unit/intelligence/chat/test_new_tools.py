import pytest
from unittest.mock import AsyncMock, patch, MagicMock
import pandas as pd
from datetime import datetime


@pytest.mark.asyncio
async def test_historical_prices_returns_formatted_output():
    mock_hist = pd.DataFrame(
        {
            "Open":  [80000.0, 80500.0, 81000.0],
            "Close": [80200.0, 80100.0, 79980.0],
        },
        index=pd.to_datetime(["2026-05-13", "2026-05-14", "2026-05-15"]),
    )
    mock_ticker = MagicMock()
    mock_ticker.history.return_value = mock_hist

    with patch("yfinance.Ticker", return_value=mock_ticker):
        from services.api.routes.ui_data import _chat_tool_historical_prices
        result = await _chat_tool_historical_prices("^BSESN", days=3)

    assert "^BSESN" in result
    assert "79,980" in result or "79980" in result
    assert "▼" in result  # last close was down


@pytest.mark.asyncio
async def test_historical_prices_empty_returns_no_data():
    mock_ticker = MagicMock()
    mock_ticker.history.return_value = pd.DataFrame()

    with patch("yfinance.Ticker", return_value=mock_ticker):
        from services.api.routes.ui_data import _chat_tool_historical_prices
        result = await _chat_tool_historical_prices("INVALID", days=3)

    assert "No historical data" in result


@pytest.mark.asyncio
async def test_historical_prices_exception_returns_no_data():
    with patch("yfinance.Ticker", side_effect=Exception("network error")):
        from services.api.routes.ui_data import _chat_tool_historical_prices
        result = await _chat_tool_historical_prices("^BSESN", days=3)

    assert "No historical data" in result


@pytest.mark.asyncio
async def test_rl_prediction_returns_formatted_output(tmp_path):
    from datetime import date
    today = str(date.today())
    cycle_id = f"TCS_{today[:7]}"
    ticker_dir = tmp_path / "it_sector" / "TCS"
    ticker_dir.mkdir(parents=True)
    envelope = {
        "ticker": "TCS",
        "sector": "it_sector",
        "conviction_streak": {"current_verdict": "BUY", "streak_days": 7},
        "reversion_prior": 0.05,
        "daily_forecasts": [{
            "date": today,
            "predicted_verdict": "BUY",
            "confidence": 0.64,
            "predicted_close": 3847.0,
            "key_assumptions": ["INR stable ~₹84"],
            "revised": True,
            "revision_count": 2,
        }],
    }
    (ticker_dir / f"{cycle_id}_prediction_envelope.json").write_text(
        __import__("json").dumps(envelope)
    )

    with patch("services.api.routes.ui_data._PREDICTIONS_DIR", tmp_path):
        from services.api.routes.ui_data import _chat_tool_rl_prediction
        result = await _chat_tool_rl_prediction("TCS")

    assert "BUY" in result
    assert "0.64" in result
    assert "3,847" in result or "3847" in result


@pytest.mark.asyncio
async def test_rl_prediction_missing_envelope_returns_empty(tmp_path):
    with patch("services.api.routes.ui_data._PREDICTIONS_DIR", tmp_path):
        from services.api.routes.ui_data import _chat_tool_rl_prediction
        result = await _chat_tool_rl_prediction("UNKNOWN")

    assert result == ""


@pytest.mark.asyncio
async def test_rl_prediction_index_returns_empty():
    from services.api.routes.ui_data import _chat_tool_rl_prediction
    result = await _chat_tool_rl_prediction("SENSEX")
    assert result == ""

    result2 = await _chat_tool_rl_prediction("NIFTY")
    assert result2 == ""

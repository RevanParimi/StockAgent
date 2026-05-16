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

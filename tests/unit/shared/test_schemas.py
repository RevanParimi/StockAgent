"""
tests/test_schemas.py
=====================
Tests for Pydantic data models in models/schemas.py.

What is tested:
  - StockQuery field validation and normalisation
  - AgentOutput score clamping
  - FinalReport construction and verdict_emoji()
  - Score bounds enforcement (ge=0, le=1)
"""

import pytest
from pydantic import ValidationError
from datetime import date

from backend.shared.schemas.pipeline import (
    AgentOutput,
    FinalReport,
    SalesDemandOutput,
    SalesDemandSubScores,
    StockQuery,
    WeightedAgentScore,
)


class TestStockQuery:
    def test_ticker_uppercased(self):
        q = StockQuery(ticker="maruti")
        assert q.ticker == "MARUTI"

    def test_ticker_stripped(self):
        q = StockQuery(ticker="  TATAMOTORS  ")
        assert q.ticker == "TATAMOTORS"

    def test_defaults(self):
        q = StockQuery(ticker="MARUTI")
        assert q.exchange == "NSE"
        assert q.analysis_date == date.today()

    def test_custom_date(self):
        q = StockQuery(ticker="MARUTI", analysis_date=date(2025, 1, 1))
        assert q.analysis_date == date(2025, 1, 1)


class TestAgentOutput:
    def test_score_bounds_valid(self):
        o = AgentOutput(agent="test", ticker="MARUTI", overall_score=0.75)
        assert o.overall_score == 0.75

    def test_score_too_high_raises(self):
        with pytest.raises(ValidationError):
            AgentOutput(agent="test", ticker="MARUTI", overall_score=1.5)

    def test_score_too_low_raises(self):
        with pytest.raises(ValidationError):
            AgentOutput(agent="test", ticker="MARUTI", overall_score=-0.1)

    def test_defaults(self):
        o = AgentOutput(agent="test", ticker="MARUTI", overall_score=0.5)
        assert o.key_positives == []
        assert o.key_risks == []
        assert o.error is None


class TestSalesDemandOutput:
    def test_sub_scores_bounds(self):
        with pytest.raises(ValidationError):
            SalesDemandSubScores(
                fada_siam_dispatch=1.5,  # out of range
                ev_segment_vahan=0.5,
                dealer_inventory=0.5,
                export_import=0.5,
                used_car_price_index=0.5,
            )

    def test_agent_name_fixed(self):
        o = SalesDemandOutput(ticker="MARUTI", overall_score=0.6)
        assert o.agent == "sales_demand"


class TestFinalReport:
    def _make_report(self, verdict: str, score: float) -> FinalReport:
        ws = WeightedAgentScore(raw=score, weight=1.0, weighted=score)
        return FinalReport(
            ticker="MARUTI",
            company_name="Maruti Suzuki India Ltd",
            final_score=score,
            verdict=verdict,
            weighted_agent_scores={"fundamentals": ws},
        )

    def test_verdict_emoji_strong_buy(self):
        r = self._make_report("STRONG BUY", 0.9)
        assert r.verdict_emoji() == "🟢"

    def test_verdict_emoji_strong_sell(self):
        r = self._make_report("STRONG SELL", 0.1)
        assert r.verdict_emoji() == "🔴"

    def test_verdict_emoji_unknown(self):
        r = self._make_report("UNKNOWN", 0.5)
        assert r.verdict_emoji() == "⚪"

    def test_final_score_bounds(self):
        with pytest.raises(ValidationError):
            self._make_report("BUY", 1.1)

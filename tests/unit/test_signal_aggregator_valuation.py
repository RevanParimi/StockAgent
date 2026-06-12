"""
tests/unit/test_signal_aggregator_valuation.py
===============================================
Tests for the single valuation-extraction helper (Unified Sector Analyst
redesign, Task 5).

`extract_valuation_fields(agent_outputs)` moves the hardcoded
valuation_catalyst field pull out of SignalAggregator._parse so the unified
and legacy paths share one extraction point. Same keys, same defaults — this
is a pure refactor, not a behaviour change.
"""

from __future__ import annotations

from backend.shared.pipeline.signal_aggregator import extract_valuation_fields
from core.schemas.pipeline import ValuationCatalystOutput


def test_extracts_valuation_fields():
    out = ValuationCatalystOutput(
        agent="valuation_catalyst", ticker="MARUTI", overall_score=0.6,
        price_target=13500.0, recovery_timeline_quarters=3,
        discount_reason="peer P/E gap", recovery_catalysts=["new launches"],
        current_discount_pct=12.0,
    )
    fields = extract_valuation_fields({"valuation_catalyst": out})
    assert fields["price_target"] == 13500.0
    assert fields["recovery_timeline_quarters"] == 3
    assert fields["discount_reason"] == "peer P/E gap"
    assert fields["recovery_catalysts"] == ["new launches"]
    # current_discount_pct of 12.0 -> undervalued_by_pct = -12.0
    assert fields["undervalued_by_pct"] == -12.0


def test_missing_valuation_agent_gives_empty_defaults():
    fields = extract_valuation_fields({})
    assert fields["price_target"] is None
    assert fields["recovery_timeline_quarters"] is None
    assert fields["undervalued_by_pct"] is None
    assert fields["discount_reason"] is None
    assert fields["recovery_catalysts"] == []


def test_extracts_valuation_fields_from_dict_form():
    """agent_outputs values may already be dicts (e.g. from model_dump())."""
    vc_dict = ValuationCatalystOutput(
        agent="valuation_catalyst", ticker="MARUTI", overall_score=0.6,
        price_target=14000.0, current_discount_pct=-18.5,
    ).model_dump()
    fields = extract_valuation_fields({"valuation_catalyst": vc_dict})
    assert fields["price_target"] == 14000.0
    assert fields["undervalued_by_pct"] == 18.5

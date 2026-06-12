"""Tests for the Unified Sector Analyst one-pass data bundle builder.

services/data/context/bundle_builder.py — SectorDataBundle, build_sector_bundle.

Each `_fetch_<section>` is a module-level function so tests can patch it
directly (matches the seam the orchestrator/analyst will rely on).
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from core.config import settings
from core.schemas.pipeline import StockQuery
from services.data.context import bundle_builder as bb


SECTION_NAMES = [
    "company_news",
    "sector_policy_news",
    "macro_context",
    "policy_deep_dive",
    "fundamentals",
    "technicals",
    "commodities",
    "flows_sentiment",
    "peers_valuation",
    "dossier",
]


def _make_query() -> StockQuery:
    return StockQuery(ticker="MARUTI", company_name="Maruti Suzuki India Ltd", nse_data={})


def _patch_all_fetchers(return_value="some live data here"):
    """Return a dict of patchers for every _fetch_<section> module function."""
    patchers = {}
    for name in SECTION_NAMES:
        patchers[name] = patch.object(bb, f"_fetch_{name}", return_value=return_value)
    return patchers


@pytest.fixture
def query() -> StockQuery:
    return _make_query()


# ---------------------------------------------------------------------------
# 1. All 10 sections present + has_real_data True when all fetchers succeed
# ---------------------------------------------------------------------------

def test_all_sections_present_and_has_real_data(query):
    with patch.object(bb, "_fetch_company_news", return_value="company news text"), \
         patch.object(bb, "_fetch_sector_policy_news", return_value="policy news text"), \
         patch.object(bb, "_fetch_macro_context", return_value="macro text"), \
         patch.object(bb, "_fetch_policy_deep_dive", return_value="policy deep dive text"), \
         patch.object(bb, "_fetch_fundamentals", return_value="fundamentals text"), \
         patch.object(bb, "_fetch_technicals", return_value="technicals text"), \
         patch.object(bb, "_fetch_commodities", return_value="commodities text"), \
         patch.object(bb, "_fetch_flows_sentiment", return_value="flows text"), \
         patch.object(bb, "_fetch_peers_valuation", return_value="peers text"), \
         patch.object(bb, "_fetch_dossier", return_value="dossier text"):
        bundle = bb.build_sector_bundle(query, "automobile")

    assert isinstance(bundle, bb.SectorDataBundle)
    for name in SECTION_NAMES:
        assert name in bundle.sections
        assert bundle.sections[name] != "unavailable"
        assert bundle.sections[name].strip() != ""

    assert bundle.has_real_data is True

    text = bundle.to_prompt_text()
    for name in SECTION_NAMES:
        assert f"## {name.upper()}" in text or f"## {name}" in text.lower() or name in text


# ---------------------------------------------------------------------------
# 2. One fetcher raises -> that section becomes "unavailable", no exception
# ---------------------------------------------------------------------------

def test_one_fetcher_raises_section_unavailable(query):
    with patch.object(bb, "_fetch_company_news", side_effect=RuntimeError("boom")), \
         patch.object(bb, "_fetch_sector_policy_news", return_value="policy news text"), \
         patch.object(bb, "_fetch_macro_context", return_value="macro text"), \
         patch.object(bb, "_fetch_policy_deep_dive", return_value="policy deep dive text"), \
         patch.object(bb, "_fetch_fundamentals", return_value="fundamentals text"), \
         patch.object(bb, "_fetch_technicals", return_value="technicals text"), \
         patch.object(bb, "_fetch_commodities", return_value="commodities text"), \
         patch.object(bb, "_fetch_flows_sentiment", return_value="flows text"), \
         patch.object(bb, "_fetch_peers_valuation", return_value="peers text"), \
         patch.object(bb, "_fetch_dossier", return_value="dossier text"):
        bundle = bb.build_sector_bundle(query, "automobile")

    assert bundle.sections["company_news"] == "unavailable"
    # Other sections remain live.
    assert bundle.sections["sector_policy_news"] == "policy news text"
    # 9 of 10 sections are live -> still has_real_data.
    assert bundle.has_real_data is True


# ---------------------------------------------------------------------------
# 3. Oversized section text capped; to_prompt_text() respects total cap
# ---------------------------------------------------------------------------

def test_section_and_bundle_size_caps(query):
    huge_text = "x" * (settings.UNIFIED_SECTION_MAX_CHARS * 5)

    with patch.object(bb, "_fetch_company_news", return_value=huge_text), \
         patch.object(bb, "_fetch_sector_policy_news", return_value=huge_text), \
         patch.object(bb, "_fetch_macro_context", return_value=huge_text), \
         patch.object(bb, "_fetch_policy_deep_dive", return_value=huge_text), \
         patch.object(bb, "_fetch_fundamentals", return_value=huge_text), \
         patch.object(bb, "_fetch_technicals", return_value=huge_text), \
         patch.object(bb, "_fetch_commodities", return_value=huge_text), \
         patch.object(bb, "_fetch_flows_sentiment", return_value=huge_text), \
         patch.object(bb, "_fetch_peers_valuation", return_value=huge_text), \
         patch.object(bb, "_fetch_dossier", return_value=huge_text):
        bundle = bb.build_sector_bundle(query, "automobile")

    for name in SECTION_NAMES:
        assert len(bundle.sections[name]) <= settings.UNIFIED_SECTION_MAX_CHARS

    prompt_text = bundle.to_prompt_text()
    # Allow small header/label slack over the configured bundle cap.
    assert len(prompt_text) <= settings.UNIFIED_BUNDLE_MAX_CHARS + 2000


# ---------------------------------------------------------------------------
# 4. 8 of 10 fetchers raise -> has_real_data False
# ---------------------------------------------------------------------------

def test_mostly_failing_fetchers_has_real_data_false(query):
    with patch.object(bb, "_fetch_company_news", side_effect=RuntimeError("boom")), \
         patch.object(bb, "_fetch_sector_policy_news", side_effect=RuntimeError("boom")), \
         patch.object(bb, "_fetch_macro_context", side_effect=RuntimeError("boom")), \
         patch.object(bb, "_fetch_policy_deep_dive", side_effect=RuntimeError("boom")), \
         patch.object(bb, "_fetch_fundamentals", side_effect=RuntimeError("boom")), \
         patch.object(bb, "_fetch_technicals", side_effect=RuntimeError("boom")), \
         patch.object(bb, "_fetch_commodities", side_effect=RuntimeError("boom")), \
         patch.object(bb, "_fetch_flows_sentiment", side_effect=RuntimeError("boom")), \
         patch.object(bb, "_fetch_peers_valuation", return_value="peers text"), \
         patch.object(bb, "_fetch_dossier", return_value="dossier text"):
        bundle = bb.build_sector_bundle(query, "automobile")

    for name in SECTION_NAMES[:8]:
        assert bundle.sections[name] == "unavailable"

    assert bundle.has_real_data is False


# ---------------------------------------------------------------------------
# 5. api_calls_made bounds: serper <= 3, tavily <= 1
# ---------------------------------------------------------------------------

def test_api_calls_made_bounds(query):
    with patch.object(bb, "_fetch_company_news", return_value="company news text"), \
         patch.object(bb, "_fetch_sector_policy_news", return_value="policy news text"), \
         patch.object(bb, "_fetch_macro_context", return_value="macro text"), \
         patch.object(bb, "_fetch_policy_deep_dive", return_value="policy deep dive text"), \
         patch.object(bb, "_fetch_fundamentals", return_value="fundamentals text"), \
         patch.object(bb, "_fetch_technicals", return_value="technicals text"), \
         patch.object(bb, "_fetch_commodities", return_value="commodities text"), \
         patch.object(bb, "_fetch_flows_sentiment", return_value="flows text"), \
         patch.object(bb, "_fetch_peers_valuation", return_value="peers text"), \
         patch.object(bb, "_fetch_dossier", return_value="dossier text"):
        bundle = bb.build_sector_bundle(query, "automobile")

    assert bundle.api_calls_made["serper"] <= 3
    assert bundle.api_calls_made["tavily"] <= 1


# ---------------------------------------------------------------------------
# Extra: build_sector_bundle never raises even if every fetcher explodes.
# ---------------------------------------------------------------------------

def test_build_sector_bundle_never_raises(query):
    with patch.object(bb, "_fetch_company_news", side_effect=RuntimeError("boom")), \
         patch.object(bb, "_fetch_sector_policy_news", side_effect=RuntimeError("boom")), \
         patch.object(bb, "_fetch_macro_context", side_effect=RuntimeError("boom")), \
         patch.object(bb, "_fetch_policy_deep_dive", side_effect=RuntimeError("boom")), \
         patch.object(bb, "_fetch_fundamentals", side_effect=RuntimeError("boom")), \
         patch.object(bb, "_fetch_technicals", side_effect=RuntimeError("boom")), \
         patch.object(bb, "_fetch_commodities", side_effect=RuntimeError("boom")), \
         patch.object(bb, "_fetch_flows_sentiment", side_effect=RuntimeError("boom")), \
         patch.object(bb, "_fetch_peers_valuation", side_effect=RuntimeError("boom")), \
         patch.object(bb, "_fetch_dossier", side_effect=RuntimeError("boom")):
        bundle = bb.build_sector_bundle(query, "automobile")

    for name in SECTION_NAMES:
        assert bundle.sections[name] == "unavailable"
    assert bundle.has_real_data is False

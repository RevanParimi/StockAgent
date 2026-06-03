"""Unit tests for multi-query expansion + Reciprocal Rank Fusion in news search."""
from datetime import date

from services.api.routes.ui_data import _build_search_variants, _rrf_fuse


def test_variants_add_recency_and_dedupe():
    out = _build_search_variants("Nifty outlook", date(2026, 6, 3))
    assert out[0] == "Nifty outlook"
    assert any("2026-06-03" in v for v in out)
    assert len(out) == len(set(v.lower() for v in out))  # no dupes


def test_variants_add_india_anchor_when_missing():
    out = _build_search_variants("silver price surge", date(2026, 6, 3))
    assert any(v.lower().startswith("india ") for v in out)


def test_variants_no_india_anchor_when_present():
    out = _build_search_variants("Nifty 50 today", date(2026, 6, 3))
    assert not any(v.lower().startswith("india ") for v in out)


def test_rrf_rewards_cross_query_agreement():
    # A appears in BOTH lists (rank 1 and rank 2) → should beat items that appear once.
    list1 = [{"link": "A"}, {"link": "B"}, {"link": "C"}]
    list2 = [{"link": "D"}, {"link": "A"}, {"link": "E"}]
    fused = _rrf_fuse([list1, list2])
    assert fused[0]["link"] == "A", [r["link"] for r in fused]


def test_rrf_dedupes_by_link():
    list1 = [{"link": "X"}, {"link": "Y"}]
    list2 = [{"link": "X"}, {"link": "Z"}]
    fused = _rrf_fuse([list1, list2])
    links = [r["link"] for r in fused]
    assert links.count("X") == 1
    assert set(links) == {"X", "Y", "Z"}


def test_rrf_handles_url_key_and_empty():
    assert _rrf_fuse([]) == []
    fused = _rrf_fuse([[{"url": "u1", "title": "t"}], [{"url": "u1"}]])
    assert len(fused) == 1

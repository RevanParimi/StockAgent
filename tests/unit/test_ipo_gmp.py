import pytest

import services.data.fetchers.ipo_gmp as gmp_mod
from core.config import settings


@pytest.fixture(autouse=True)
def _enabled(monkeypatch):
    monkeypatch.setattr(settings, "IPO_GMP_ENABLED", True, raising=False)
    monkeypatch.setattr(settings, "SERPER_API_KEY_IPO", "test-key", raising=False)
    monkeypatch.setattr(settings, "IPO_GMP_MIN_SOURCES", 2, raising=False)
    monkeypatch.setattr(settings, "IPO_GMP_AGREEMENT_TOLERANCE", 0.25, raising=False)


def test_no_key_means_no_value_and_NO_API_CALL(monkeypatch):
    """The quota gate. The shared Serper key runs at ~83 calls/day against a
    2500/mo cap, so an unkeyed GMP fetcher must cost exactly zero."""
    monkeypatch.setattr(settings, "SERPER_API_KEY_IPO", "", raising=False)
    calls = []
    monkeypatch.setattr(gmp_mod, "search_serper",
                        lambda *a, **k: calls.append(1) or [])
    assert gmp_mod.fetch_gmp("Molbio Diagnostics") is None
    assert calls == []


def test_disabled_flag_means_no_value_and_no_call(monkeypatch):
    monkeypatch.setattr(settings, "IPO_GMP_ENABLED", False, raising=False)
    calls = []
    monkeypatch.setattr(gmp_mod, "search_serper",
                        lambda *a, **k: calls.append(1) or [])
    assert gmp_mod.fetch_gmp("Molbio Diagnostics") is None
    assert calls == []


def test_two_agreeing_sources_yield_the_median(monkeypatch):
    monkeypatch.setattr(gmp_mod, "search_serper", lambda *a, **k: [
        {"snippet": "Molbio IPO GMP today is Rs 120 per share",
         "link": "https://ipowatch.example/molbio"},
        {"snippet": "grey market premium of ₹130 ahead of listing",
         "link": "https://investorgain.example/molbio"},
    ])
    out = gmp_mod.fetch_gmp("Molbio Diagnostics", issue_price=500.0)
    assert out["gmp"] == 125.0
    assert out["sources"] == 2
    assert round(out["gmp_pct"], 2) == 25.0


def test_a_single_source_is_not_a_measurement(monkeypatch):
    """Grey-market chatter from one search result is a rumour, not a reading."""
    monkeypatch.setattr(gmp_mod, "search_serper", lambda *a, **k: [
        {"snippet": "Molbio IPO GMP Rs 120", "link": "https://ipowatch.example/x"},
    ])
    assert gmp_mod.fetch_gmp("Molbio Diagnostics") is None


def test_two_numbers_from_the_SAME_domain_count_once(monkeypatch):
    """One aggregator echoed twice is still one source."""
    monkeypatch.setattr(gmp_mod, "search_serper", lambda *a, **k: [
        {"snippet": "GMP Rs 120", "link": "https://ipowatch.example/a"},
        {"snippet": "GMP Rs 130", "link": "https://ipowatch.example/b"},
    ])
    assert gmp_mod.fetch_gmp("Molbio Diagnostics") is None


def test_sources_that_disagree_wildly_are_discarded(monkeypatch):
    monkeypatch.setattr(gmp_mod, "search_serper", lambda *a, **k: [
        {"snippet": "GMP Rs 20", "link": "https://a.example/x"},
        {"snippet": "GMP Rs 300", "link": "https://b.example/y"},
    ])
    assert gmp_mod.fetch_gmp("Molbio Diagnostics") is None


def test_a_search_failure_is_none_not_a_raise(monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("serper down")
    monkeypatch.setattr(gmp_mod, "search_serper", boom)
    assert gmp_mod.fetch_gmp("Molbio Diagnostics") is None


def test_gmp_pct_is_absent_without_an_issue_price(monkeypatch):
    monkeypatch.setattr(gmp_mod, "search_serper", lambda *a, **k: [
        {"snippet": "GMP Rs 120", "link": "https://a.example/x"},
        {"snippet": "GMP Rs 130", "link": "https://b.example/y"},
    ])
    out = gmp_mod.fetch_gmp("Molbio Diagnostics", issue_price=None)
    assert out["gmp"] == 125.0
    assert out["gmp_pct"] is None


def test_zero_gmp_from_two_sources_is_a_real_reading(monkeypatch):
    """A GMP of zero is a real reading (demand has collapsed), not an absent
    one — it must NOT be filtered out as if no source were found."""
    monkeypatch.setattr(gmp_mod, "search_serper", lambda *a, **k: [
        {"snippet": "GMP today is Rs 0", "link": "https://a.example/x"},
        {"snippet": "grey market premium at Rs 0", "link": "https://b.example/y"},
    ])
    out = gmp_mod.fetch_gmp("Molbio Diagnostics")
    assert out == {"gmp": 0.0, "gmp_pct": None, "sources": 2}


def test_explicit_negative_gmp_stays_negative(monkeypatch):
    """A minus sign immediately against the currency token is a grey-market
    discount, not a premium — the sign must survive, not be discarded."""
    monkeypatch.setattr(gmp_mod, "search_serper", lambda *a, **k: [
        {"snippet": "IPO GMP -Rs 15 ahead of listing", "link": "https://a.example/x"},
        {"snippet": "grey market premium -₹17 today", "link": "https://b.example/y"},
    ])
    out = gmp_mod.fetch_gmp("Molbio Diagnostics")
    assert out["gmp"] == -16.0
    assert out["sources"] == 2


def test_discount_word_flips_sign(monkeypatch):
    """No explicit minus sign, but the word 'discount' is itself a sufficient
    signal that the figure is negative."""
    monkeypatch.setattr(gmp_mod, "search_serper", lambda *a, **k: [
        {"snippet": "IPO GMP at a discount of Rs 15 ahead of listing",
         "link": "https://a.example/x"},
        {"snippet": "grey market discount of Rs 17 seen today",
         "link": "https://b.example/y"},
    ])
    out = gmp_mod.fetch_gmp("Molbio Diagnostics")
    assert out["gmp"] == -16.0


def test_positive_snippet_without_discount_signals_stays_positive(monkeypatch):
    """Sanity check: the sign fix must not affect the ordinary positive-GMP
    path when neither a minus sign nor 'discount' wording is present."""
    monkeypatch.setattr(gmp_mod, "search_serper", lambda *a, **k: [
        {"snippet": "GMP today is Rs 120, strong demand seen",
         "link": "https://a.example/x"},
        {"snippet": "grey market premium at Rs 130",
         "link": "https://b.example/y"},
    ])
    out = gmp_mod.fetch_gmp("Molbio Diagnostics")
    assert out["gmp"] == 125.0


def test_agreement_at_exactly_the_tolerance_boundary_is_accepted(monkeypatch):
    """100 and 125 are exactly 25% apart (fixture tolerance=0.25) — the
    boundary itself must be accepted, not discarded."""
    monkeypatch.setattr(gmp_mod, "search_serper", lambda *a, **k: [
        {"snippet": "GMP Rs 100", "link": "https://a.example/x"},
        {"snippet": "GMP Rs 125", "link": "https://b.example/y"},
    ])
    out = gmp_mod.fetch_gmp("Molbio Diagnostics")
    assert out is not None
    assert out["gmp"] == 112.5


def test_price_band_before_gmp_figure_is_not_picked(monkeypatch):
    """A price band mentioned before the GMP figure in the same snippet must
    not be mistaken for GMP — the figure nearest GMP/premium wording wins."""
    monkeypatch.setattr(gmp_mod, "search_serper", lambda *a, **k: [
        {"snippet": "Molbio price band Rs 490 - Rs 500, GMP today is Rs 120",
         "link": "https://a.example/x"},
        {"snippet": "grey market premium seen around Rs 130",
         "link": "https://b.example/y"},
    ])
    out = gmp_mod.fetch_gmp("Molbio Diagnostics")
    assert out["gmp"] == 125.0

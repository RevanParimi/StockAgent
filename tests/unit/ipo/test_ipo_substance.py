"""IPO-3b — the Substance side. Pure functions over a corroborated
IpoSubstance and captured ledger rows. Offline; the one replay test reuses
the recorded VARMORA extraction so a real dossier flows end to end."""
import pytest

from core.config import settings
from core.ipo.extract import IpoSubstance, Sourced, extract_substance
from core.ipo.signals import IpoSignalSnapshot
from core.ipo.substance import (BROWSED_FEATURES, OFFICIAL_FEATURES, SUBSTANCE_FEATURES,
                                SubstanceReading, pat_growth, peer_pe_discount,
                                read_substance, revenue_growth)
from tests.unit.ipo.test_ipo_extract import ReplayClient, _dossier

WEIGHTS = {k: 1.0 for k in SUBSTANCE_FEATURES}
ANCHORS = {"pat_growth": (0.90, 1.15, 1.50), "revenue_growth": (0.95, 1.15, 1.40),
           "peer_pe_discount": (0.5, 1.0, 2.0), "qib_x": (1.76, 40.35, 207.34),
           "mutual_fund_x": (0.5, 5.0, 40.0)}


@pytest.fixture(autouse=True)
def _cfg(monkeypatch):
    monkeypatch.setattr(settings, "IPO_SUBSTANCE_WEIGHTS", WEIGHTS, raising=False)
    monkeypatch.setattr(settings, "IPO_SUBSTANCE_ANCHORS", ANCHORS, raising=False)
    monkeypatch.setattr(settings, "IPO_INDEX_MIN_COVERAGE", 0.5, raising=False)


def _src(value, as_of=None, label=None, n=2):
    urls = [f"https://s{i}.com/p" for i in range(n)]
    return Sourced(value=value, as_of=as_of, label=label, source_url=urls[0],
                   sources=urls, status="corroborated")


def _snap(**combined):
    return IpoSignalSnapshot(symbol="X", captured_at="2026-09-21T12:15:00+00:00",
                             state="closed", combined=combined)


# ─────────────────────────── growth features ──────────────────────────────

def test_pat_growth_is_annualised_over_the_profitable_run():
    g, urls = pat_growth([_src(100.0, "FY2024"), _src(121.0, "FY2025"), _src(146.41, "FY2026")])
    assert g == pytest.approx(1.21)
    assert urls == ["https://s0.com/p", "https://s1.com/p"]


def test_pat_growth_spans_a_missing_middle_year_by_calendar_not_by_count():
    g, _ = pat_growth([_src(100.0, "FY2024"), _src(144.0, "FY2026")])
    assert g == pytest.approx(1.2)           # two years, not one


def test_a_loss_in_the_latest_year_is_a_real_zero_not_dark():
    g, urls = pat_growth([_src(-101.0, "FY2023"), _src(-50.0, "FY2024"), _src(-63.0, "FY2025")])
    assert g == 0.0 and urls


def test_just_turned_profitable_is_flat_growth_unmeasured():
    g, _ = pat_growth([_src(-20.0, "FY2024"), _src(15.0, "FY2025")])
    assert g == 1.0


def test_a_single_profitable_year_after_losses_only_counts_the_positive_run():
    g, _ = pat_growth([_src(-5.0, "FY2023"), _src(10.0, "FY2024"), _src(20.0, "FY2025")])
    assert g == pytest.approx(2.0)


def test_pat_growth_with_no_series_is_none():
    assert pat_growth([]) == (None, [])
    assert pat_growth([Sourced()]) == (None, [])


def test_pat_growth_ignores_entries_without_a_readable_year():
    g, _ = pat_growth([_src(100.0, "latest"), _src(150.0, "FY2025")])
    assert g == 1.0                          # only one placeable year survives


def test_revenue_growth_needs_two_years():
    assert revenue_growth([_src(500.0, "FY2025")]) == (None, [])
    g, _ = revenue_growth([_src(711.4, "FY2023"), _src(1039.4, "FY2024"), _src(1374.1, "FY2025")])
    assert g == pytest.approx((1374.1 / 711.4) ** 0.5)


def test_revenue_growth_is_none_when_a_leg_is_not_positive():
    assert revenue_growth([_src(0.0, "FY2024"), _src(100.0, "FY2025")])[0] is None


# ─────────────────────────── valuation ────────────────────────────────────

def test_peer_pe_discount_rises_when_the_issue_is_cheaper_than_peers():
    d, urls = peer_pe_discount(_src(20.0), [_src(30.0, label="A"), _src(50.0, label="B"),
                                            _src(40.0, label="C")])
    assert d == pytest.approx(2.0)           # median 40 / issue 20
    assert len(urls) == 2


def test_peer_pe_discount_is_dark_without_both_sides():
    assert peer_pe_discount(Sourced(), [_src(30.0, label="A")]) == (None, [])
    assert peer_pe_discount(_src(20.0), []) == (None, [])
    assert peer_pe_discount(_src(0.0), [_src(30.0, label="A")]) == (None, [])


# ─────────────────────────── read_substance ───────────────────────────────

def _research(**kw):
    return IpoSubstance(symbol="X", **kw)


def test_full_reading_scores_both_provenance_classes_and_is_never_fitted():
    r = read_substance(
        _research(pat_cr=[_src(100.0, "FY2024"), _src(150.0, "FY2026")],
                  revenue_cr=[_src(1000.0, "FY2024"), _src(1400.0, "FY2026")],
                  issue_pe=_src(20.0), peer_pe=[_src(40.0, label="A"), _src(30.0, label="B")]),
        [_snap(total=30.0, qib=40.35, mutual_fund=5.0, fii=9.0)])
    assert isinstance(r, SubstanceReading)
    assert r.fitted is False
    assert r.coverage == 1.0 and r.dark == []
    assert r.components["qib_x"] == pytest.approx(0.5)
    assert r.components["mutual_fund_x"] == pytest.approx(0.5)
    assert r.provenance == {**{k: "browsed" for k in BROWSED_FEATURES},
                            **{k: "official" for k in OFFICIAL_FEATURES}}
    assert set(r.sources) == set(BROWSED_FEATURES)
    assert r.index is not None and 50 < r.index < 100
    assert r.as_of == "2026-09-21T12:15:00+00:00"


def test_official_only_reading_clears_coverage_and_lists_browsed_as_dark():
    """No research at all — the book alone carries 2 of 5 equal weights, which
    is below the coverage floor: S is None, not a confident number on one leg."""
    r = read_substance(None, [_snap(total=30.0, qib=40.35, mutual_fund=5.0)])
    assert r.index is None
    assert r.coverage == pytest.approx(0.4)
    assert r.dark == sorted(BROWSED_FEATURES)
    assert r.sources == {}


def test_browsed_only_reading_scores_without_a_ledger():
    r = read_substance(_research(pat_cr=[_src(100.0, "FY2024"), _src(150.0, "FY2026")],
                                 revenue_cr=[_src(1000.0, "FY2024"), _src(1400.0, "FY2026")],
                                 issue_pe=_src(20.0), peer_pe=[_src(40.0, label="A")]))
    assert r.index is not None and r.coverage == pytest.approx(0.6)
    assert r.dark == ["mutual_fund_x", "qib_x"]
    assert r.as_of == ""


def test_loss_making_pat_pulls_the_index_down_rather_than_vanishing():
    profitable = read_substance(_research(pat_cr=[_src(100.0, "FY2024"), _src(150.0, "FY2026")]),
                                [_snap(total=30.0, qib=40.35, mutual_fund=5.0)])
    losing = read_substance(_research(pat_cr=[_src(-100.0, "FY2024"), _src(-150.0, "FY2026")]),
                            [_snap(total=30.0, qib=40.35, mutual_fund=5.0)])
    assert profitable.coverage == losing.coverage == pytest.approx(0.6)
    assert losing.components["pat_growth"] == 0.0
    assert losing.index < profitable.index


def test_reported_text_and_unvalidated_features_are_captured_never_scored():
    r = read_substance(
        _research(promoter=Sourced(value="Varmora family", source_url="https://a.com", status="reported"),
                  parent_track=Sourced(value="two prior listings", source_url="https://a.com",
                                       status="reported"),
                  ebitda_margin=_src(51.3),
                  red_flags=[Sourced(value="litigation", source_url="https://a.com", status="reported")],
                  anchor_names=[Sourced(value="SBI MF", source_url="https://a.com", status="reported")],
                  dropped=["issue_pe: 1 source(s)"]),
        [_snap(total=30.0, qib=40.35, fii=9.0, dom_fi=6.5, mutual_fund=8.0)],
        {"ofs_share": 0.81})
    c = r.captured
    assert c["promoter"] == "Varmora family" and c["parent_track"] == "two prior listings"
    assert c["ebitda_margin"] == 51.3 and c["red_flags"] == ["litigation"]
    assert c["anchor_names"] == ["SBI MF"] and c["dropped"] == ["issue_pe: 1 source(s)"]
    assert c["fii_x"] == 9.0 and c["dom_fi_x"] == 6.5 and c["ofs_share"] == 0.81
    for never in ("promoter", "parent_track", "ebitda_margin", "fii_x", "dom_fi_x", "ofs_share"):
        assert never not in r.components and never not in r.features


def test_missing_config_block_is_a_dark_reading(monkeypatch):
    monkeypatch.setattr(settings, "IPO_SUBSTANCE_WEIGHTS", {}, raising=False)
    r = read_substance(_research(pat_cr=[_src(100.0, "FY2024"), _src(150.0, "FY2026")]),
                       [_snap(total=30.0, qib=40.35)])
    assert r.index is None and r.coverage == 0.0
    assert r.features["qib_x"] == 40.35         # facts still captured


def test_read_substance_never_raises(monkeypatch):
    import core.ipo.substance as m
    monkeypatch.setattr(m, "pat_growth", lambda *a: (_ for _ in ()).throw(RuntimeError("x")))
    r = read_substance(_research(), [], symbol="X")
    assert r.index is None and r.symbol == "X"
    assert set(r.dark) == set(SUBSTANCE_FEATURES)


# ─────────────────────────── replay: a real dossier end to end ─────────────

@pytest.fixture
def _no_telemetry(monkeypatch):
    import services.clients.llm_client as llm
    monkeypatch.setattr(llm, "record_llm_call", lambda *a, **k: None)


def test_varmora_replay_reads_a_growing_business_with_valuation_dark(_no_telemetry):
    """VARMORA: three corroborated years of revenue and PAT, no corroborated
    P/E (one blog). The valuation leg is dark by design, the growth legs
    score, provenance travels, and the reading still says fitted=False."""
    research = extract_substance(_dossier("VARMORA_2026-09-24"), client=ReplayClient("VARMORA"), model="m")
    r = read_substance(research, [_snap(total=12.0, qib=20.0, mutual_fund=3.0)])
    assert r.features["pat_growth"] is not None and r.features["revenue_growth"] is not None
    assert r.features["peer_pe_discount"] is None and "peer_pe_discount" in r.dark
    assert r.coverage == pytest.approx(0.8)
    assert r.index is not None and r.fitted is False
    assert all(u.startswith("http") for u in r.sources["pat_growth"])
    assert len(r.sources["pat_growth"]) >= 2
    assert "Varmora" in str(r.captured["promoter"])

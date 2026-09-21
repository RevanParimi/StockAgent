"""IPO-3a — the Hype side. Pure functions over captured facts; no network,
no LLM, no ledger writes. Anchors here are the fitted 2026-09-21 values so
the numeric assertions double as a record of what the spine said."""
import pytest

from core.config import settings
from core.ipo.hype import (DEMAND_FEATURES, FROTH_FEATURES, HypeReading,
                           hype_features, read_hype, score_feature, score_index)
from core.ipo.signals import IpoSignalSnapshot

QIB = (1.76, 40.35, 207.34)
TOTAL = (1.57, 30.57, 133.76)
RETAIL = (0.96, 8.93, 72.49)
SKEW = (0.04, 0.28, 1.23)
CUTOFF = (0.10, 0.25, 0.50)
GMP = (0.02, 0.15, 0.50)


@pytest.fixture(autouse=True)
def _fitted(monkeypatch):
    monkeypatch.setattr(settings, "IPO_DEMAND_WEIGHTS",
                        {"qib_x": 0.5, "total_x": 0.3, "retail_x": 0.2}, raising=False)
    monkeypatch.setattr(settings, "IPO_DEMAND_ANCHORS",
                        {"qib_x": QIB, "total_x": TOTAL, "retail_x": RETAIL}, raising=False)
    monkeypatch.setattr(settings, "IPO_HYPE_WEIGHTS",
                        {"retail_x": 0.35, "retail_qib_skew": 0.30,
                         "cutoff_share": 0.20, "gmp_pct": 0.15}, raising=False)
    monkeypatch.setattr(settings, "IPO_HYPE_ANCHORS",
                        {"retail_x": RETAIL, "retail_qib_skew": SKEW,
                         "cutoff_share": CUTOFF, "gmp_pct": GMP}, raising=False)
    monkeypatch.setattr(settings, "IPO_INDEX_MIN_COVERAGE", 0.5, raising=False)


def _snap(captured_at, state="open", cutoff=None, **combined):
    return IpoSignalSnapshot(symbol="NSE", captured_at=captured_at, state=state,
                             combined=combined, cutoff_share=cutoff)


# ─────────────────────────── score_feature ────────────────────────────────

def test_anchors_map_to_0_half_1():
    assert score_feature(QIB[0], QIB) == pytest.approx(0.0)
    assert score_feature(QIB[1], QIB) == pytest.approx(0.5)
    assert score_feature(QIB[2], QIB) == pytest.approx(1.0)


def test_score_is_monotone_and_clipped():
    xs = [0.5, 1.0, 5.0, 40.0, 100.0, 300.0, 1000.0]
    ys = [score_feature(x, QIB) for x in xs]
    assert ys == sorted(ys)
    assert ys[0] == 0.0 and ys[-1] == 1.0


def test_log_scale_puts_geometric_midpoint_at_the_quarter_mark():
    """Between p10 and p50 the score is linear in log(x), not in x."""
    import math
    geo = math.sqrt(QIB[0] * QIB[1])
    assert score_feature(geo, QIB) == pytest.approx(0.25)


def test_a_real_zero_reading_scores_zero_and_none_stays_none():
    """NSE reports genuine 0.00 totals. That is a bottom reading, not an
    absent one — the dark-signal rule applies to None only."""
    assert score_feature(0.0, TOTAL) == 0.0
    assert score_feature(-0.1, GMP) == 0.0
    assert score_feature(None, TOTAL) is None


# ─────────────────────────── score_index ──────────────────────────────────

def test_index_renormalises_over_present_features():
    feats = {"qib_x": QIB[2], "total_x": None, "retail_x": RETAIL[0]}
    idx, cov, comp = score_index(feats, {"qib_x": 0.5, "total_x": 0.3, "retail_x": 0.2},
                                 {"qib_x": QIB, "total_x": TOTAL, "retail_x": RETAIL},
                                 min_coverage=0.5)
    # (0.5*1.0 + 0.2*0.0) / 0.7
    assert idx == pytest.approx(71.4, abs=0.1)
    assert cov == pytest.approx(0.7)
    assert comp["total_x"] is None


def test_index_is_none_below_min_coverage():
    """One leg out of three carrying 20% of the weight is not an index."""
    feats = {"qib_x": None, "total_x": None, "retail_x": 50.0}
    idx, cov, _ = score_index(feats, {"qib_x": 0.5, "total_x": 0.3, "retail_x": 0.2},
                              {"qib_x": QIB, "total_x": TOTAL, "retail_x": RETAIL},
                              min_coverage=0.5)
    assert idx is None
    assert cov == pytest.approx(0.2)


def test_all_dark_is_none_with_zero_coverage():
    idx, cov, comp = score_index({}, {"qib_x": 1.0}, {"qib_x": QIB}, min_coverage=0.0)
    assert idx is None and cov == 0.0 and comp == {"qib_x": None}


def test_a_weight_without_anchors_is_dark_not_guessed():
    idx, cov, comp = score_index({"qib_x": 100.0, "mystery": 5.0},
                                 {"qib_x": 0.5, "mystery": 0.5}, {"qib_x": QIB},
                                 min_coverage=0.5)
    assert comp["mystery"] is None
    assert cov == pytest.approx(0.5)
    assert idx is not None


# ─────────────────────────── hype_features ────────────────────────────────

def test_features_come_from_the_last_snapshot_carrying_a_total():
    snaps = [_snap("2026-09-19T12:15:00+00:00", total=1.2, qib=0.4, retail=1.0, cutoff=0.10),
             _snap("2026-09-21T12:15:00+00:00", state="closed", total=3.817, qib=7.81,
                   retail=1.10, nii=2.5, fii=9.0, dom_fi=6.5, mutual_fund=8.0, cutoff=0.14),
             _snap("2026-09-22T03:00:00+00:00", state="closed", total=None)]
    feats, snap = hype_features(snaps, {"issue_size_cr": 50000.0})
    assert snap.captured_at == "2026-09-21T12:15:00+00:00"
    assert feats["total_x"] == 3.817 and feats["qib_x"] == 7.81
    assert feats["fii_x"] == 9.0 and feats["mutual_fund_x"] == 8.0
    assert feats["cutoff_share"] == 0.14
    assert feats["retail_qib_skew"] == pytest.approx(1.10 / 7.81)
    assert feats["demand_delta"] == pytest.approx(3.817 - 1.2)
    assert feats["issue_size_cr"] == 50000.0
    assert feats["gmp_pct"] is None and feats["ofs_share"] is None


def test_skew_is_dark_when_the_qib_book_is_zero():
    """0.0 QIB is a real reading with an undefined ratio — not infinity."""
    feats, _ = hype_features([_snap("2026-09-21T12:15:00+00:00", total=1.0, qib=0.0, retail=2.0)])
    assert feats["retail_qib_skew"] is None
    assert feats["qib_x"] == 0.0


def test_no_snapshots_is_all_none():
    feats, snap = hype_features([], {"issue_size_cr": 100})
    assert snap is None
    assert all(v is None for k, v in feats.items() if k != "issue_size_cr")


# ─────────────────────────── read_hype ────────────────────────────────────

def test_nse_reading_matches_the_2026_09_21_book():
    """NSE 17-21 Sep: total 3.817x, QIB 7.81x, retail 1.10x, 14% at cut-off.
    A big absolute book but a thin multiple: demand sits low-mid on the
    spine and froth is low — retail did not lead, cut-off share was modest."""
    snaps = [_snap("2026-09-21T12:15:00+00:00", state="closed", total=3.817, qib=7.81,
                   retail=1.10, cutoff=0.14)]
    r = read_hype(snaps, {"symbol": "NSE", "issue_size_cr": 50000.0})
    assert isinstance(r, HypeReading)
    assert r.symbol == "NSE" and r.state == "closed"
    assert r.demand is not None and 15 < r.demand < 35
    assert r.demand_coverage == 1.0
    assert r.froth is not None and r.froth < 30
    # GMP is not wired: dark, listed, and the froth weight renormalised
    assert r.dark == ["gmp_pct"]
    assert r.froth_coverage == pytest.approx(0.85)
    assert r.components["gmp_pct"] is None


def test_hot_book_scores_high_demand_and_high_froth():
    """TECHNOCRAF-shaped: 38.7x total, 42.3x QIB, 25.3x retail, retail
    bidding at cut-off in bulk."""
    snaps = [_snap("2026-08-13T12:15:00+00:00", state="closed", total=38.69, qib=42.26,
                   retail=25.35, cutoff=0.55)]
    r = read_hype(snaps, symbol="TECHNOCRAF")
    assert r.demand > 50
    assert r.froth > 60


def test_cold_book_is_a_real_low_reading_not_dark():
    snaps = [_snap("2026-08-13T12:15:00+00:00", state="closed", total=0.9, qib=0.5, retail=1.4)]
    r = read_hype(snaps, symbol="COLD")
    assert r.demand is not None and r.demand < 5     # retail 1.4x sits just above p10
    assert r.components["qib_x"] == 0.0 and r.components["total_x"] == 0.0
    assert "qib_x" not in r.dark


def test_ofs_share_is_captured_and_never_scored():
    """Spec §3: UNVALIDATED after three measurements. Rendered, not weighted."""
    snaps = [_snap("2026-08-13T12:15:00+00:00", total=8.4, qib=16.8, retail=1.7)]
    r = read_hype(snaps, {"ofs_share": 0.81})
    assert r.features["ofs_share"] == 0.81
    assert "ofs_share" not in r.components
    assert "ofs_share" not in DEMAND_FEATURES + FROTH_FEATURES


def test_missing_config_block_yields_a_dark_reading_not_a_hidden_model(monkeypatch):
    monkeypatch.setattr(settings, "IPO_DEMAND_WEIGHTS", {}, raising=False)
    monkeypatch.setattr(settings, "IPO_HYPE_WEIGHTS", {}, raising=False)
    snaps = [_snap("2026-08-13T12:15:00+00:00", total=38.69, qib=42.26, retail=25.35)]
    r = read_hype(snaps)
    assert r.demand is None and r.froth is None
    assert r.demand_coverage == 0.0
    assert r.features["qib_x"] == 42.26          # facts still captured


def test_malformed_anchor_is_dropped_not_fatal(monkeypatch):
    monkeypatch.setattr(settings, "IPO_DEMAND_ANCHORS",
                        {"qib_x": QIB, "total_x": [5, 2, 1], "retail_x": "nope"}, raising=False)
    snaps = [_snap("2026-08-13T12:15:00+00:00", total=38.69, qib=42.26, retail=25.35)]
    r = read_hype(snaps)
    assert r.components["total_x"] is None
    assert r.demand_coverage == pytest.approx(0.5)   # qib alone; retail's demand anchor is gone
    assert r.demand is not None                      # 0.5 >= min coverage


def test_read_hype_never_raises(monkeypatch):
    import core.ipo.hype as h
    monkeypatch.setattr(h, "hype_features", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("x")))
    r = read_hype([], symbol="X")
    assert r.demand is None and r.froth is None
    assert set(DEMAND_FEATURES) <= set(r.dark)

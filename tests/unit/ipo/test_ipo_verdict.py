"""IPO-3c — the verdict. A pure function over the two readings, so every test
here is offline and constructs the readings directly. What is guarded:

  * the SHORT lean moves with `demand` and with nothing else;
  * froth moves the BAND and never the lean;
  * the spine hit-rate is quoted only where IPO-1 says it is admissible —
    after the book closes, never at T-1;
  * LONG is dark whatever the inputs say;
  * a dark axis yields no quadrant, and a dark demand yields no lean;
  * `ofs_share` cannot change any output (spec §3: UNVALIDATED).
"""
import pytest

from core.config import settings
from core.ipo.hype import HypeReading
from core.ipo.substance import SubstanceReading
from core.ipo.verdict import (CLOSED_STATES, QUADRANTS, IpoVerdict, LongView, ShortView,
                              band_of, decide_verdict, lean_of, quadrant_of)

COHORTS = {"strong": {"n": 76, "positive": 0.92, "mean_pct": 35.1},
           "mixed": {"n": 47, "positive": 0.72, "mean_pct": 10.5},
           "weak": {"n": 62, "positive": 0.34, "mean_pct": -3.0}}
BANDS = {"strong": [15.1, 51.5], "mixed": [-1.6, 20.2], "weak": [-8.7, 3.2]}
BANDS_HIGH_FROTH = {"strong": [15.3, 51.8], "mixed": [-7.7, 13.0], "weak": [-11.5, 3.2]}


@pytest.fixture(autouse=True)
def _cfg(monkeypatch):
    for name, value in (("IPO_SHORT_STRONG", 70.0), ("IPO_SHORT_WEAK", 30.0),
                        ("IPO_FROTH_HIGH", 50.0), ("IPO_QUADRANT_HIGH", 50.0),
                        ("IPO_SHORT_COHORTS", COHORTS), ("IPO_SHORT_BANDS", BANDS),
                        ("IPO_SHORT_BANDS_HIGH_FROTH", BANDS_HIGH_FROTH),
                        ("IPO_INDEX_MIN_COVERAGE", 0.5)):
        monkeypatch.setattr(settings, name, value, raising=False)


def _hype(demand=80.0, froth=20.0, state="closed", symbol="X", **kw):
    return HypeReading(symbol=symbol, as_of="2026-09-21T12:15:00+00:00", state=state,
                       demand=demand, froth=froth, **kw)


def _sub(index=60.0, symbol="X", **kw):
    return SubstanceReading(symbol=symbol, index=index, **kw)


# ─────────────────────────── the lean ─────────────────────────────────────

@pytest.mark.parametrize("demand,expected", [
    (100.0, "strong"), (70.0, "strong"), (69.9, "mixed"), (50.0, "mixed"),
    (30.1, "mixed"), (30.0, "weak"), (0.0, "weak"), (None, None)])
def test_the_lean_is_demand_against_the_two_thresholds(demand, expected):
    assert lean_of(demand) == expected


def test_a_dark_demand_is_no_lean_not_a_weak_one():
    v = decide_verdict(_hype(demand=None, froth=90.0), _sub())
    assert v.short.lean is None and v.short.band is None
    assert "unread" in v.short.basis and not v.short.evidenced


@pytest.mark.parametrize("froth", [0.0, 49.9, 50.0, 100.0, None])
def test_froth_never_moves_the_lean(froth):
    v = decide_verdict(_hype(demand=80.0, froth=froth), _sub())
    assert v.short.lean == "strong"


def test_the_thresholds_come_from_config_not_from_the_code(monkeypatch):
    monkeypatch.setattr(settings, "IPO_SHORT_STRONG", 90.0, raising=False)
    assert lean_of(80.0) == "mixed"


# ─────────────────────────── the band ─────────────────────────────────────

def test_high_froth_swaps_in_the_measured_high_froth_band():
    lo_band, widened_lo = band_of("strong", 20.0)
    hi_band, widened_hi = band_of("strong", 80.0)
    assert lo_band == (15.1, 51.5) and widened_lo is False
    assert hi_band == (15.3, 51.8) and widened_hi is True
    assert (hi_band[1] - hi_band[0]) > (lo_band[1] - lo_band[0])   # wider, which is the point


def test_the_froth_cut_is_inclusive_at_the_threshold():
    assert band_of("mixed", 50.0) == ((-7.7, 13.0), True)
    assert band_of("mixed", 49.9) == ((-1.6, 20.2), False)


def test_a_dark_froth_leaves_the_base_band_standing():
    assert band_of("weak", None) == ((-8.7, 3.2), False)


def test_no_configured_band_is_no_band_rather_than_an_invented_one(monkeypatch):
    monkeypatch.setattr(settings, "IPO_SHORT_BANDS", {}, raising=False)
    monkeypatch.setattr(settings, "IPO_SHORT_BANDS_HIGH_FROTH", {}, raising=False)
    v = decide_verdict(_hype(), _sub())
    assert v.short.lean == "strong" and v.short.band is None
    assert "No band" in v.short.basis


def test_a_malformed_band_row_is_skipped_not_half_read(monkeypatch):
    monkeypatch.setattr(settings, "IPO_SHORT_BANDS",
                        {"strong": ["oops"], "weak": [-8.7, 3.2]}, raising=False)
    assert band_of("strong", 10.0) == (None, False)
    assert band_of("weak", 10.0) == ((-8.7, 3.2), False)


# ─────────────────── what the evidence is allowed to say ─────────────────

@pytest.mark.parametrize("state", sorted(CLOSED_STATES))
def test_a_closed_book_may_quote_the_spine_hit_rate(state):
    v = decide_verdict(_hype(state=state), _sub())
    assert v.short.evidenced is True
    assert "92%" in v.short.basis and "n=76" in v.short.basis


@pytest.mark.parametrize("state", ["open", "upcoming", "unknown", ""])
def test_the_t_minus_1_lean_may_not_quote_it(state):
    v = decide_verdict(_hype(state=state), _sub())
    assert v.short.evidenced is False
    assert "92%" not in v.short.basis
    assert "NOT admissible" in v.short.basis and "forward validation" in v.short.basis


def test_the_quoted_hit_rate_follows_the_lean():
    weak = decide_verdict(_hype(demand=10.0), _sub())
    assert weak.short.lean == "weak" and "34%" in weak.short.basis


def test_a_missing_cohort_row_quotes_no_hit_rate(monkeypatch):
    monkeypatch.setattr(settings, "IPO_SHORT_COHORTS", {"weak": COHORTS["weak"]}, raising=False)
    v = decide_verdict(_hype(), _sub())
    assert v.short.evidenced is True and "%" not in v.short.basis.split("Band")[0]
    assert "No cohort measurement" in v.short.basis


def test_a_half_written_cohort_row_is_not_quoted(monkeypatch):
    monkeypatch.setattr(settings, "IPO_SHORT_COHORTS",
                        {"strong": {"n": 76, "positive": 0.92}}, raising=False)
    assert "No cohort measurement" in decide_verdict(_hype(), _sub()).short.basis


# ─────────────────────────── the quadrant ─────────────────────────────────

@pytest.mark.parametrize("froth,substance,expected", [
    (20.0, 80.0, "quiet_compounder"),   # low hype, high substance  — Ather
    (80.0, 80.0, "genuine_star"),
    (20.0, 20.0, "ignore"),
    (80.0, 20.0, "froth"),              # high hype, low substance  — Ola
    (50.0, 50.0, "genuine_star"),       # the cut is inclusive on both axes
])
def test_the_four_quadrants_of_the_grid(froth, substance, expected):
    assert quadrant_of(froth, substance) == expected
    v = decide_verdict(_hype(froth=froth), _sub(index=substance))
    assert v.quadrant == expected and expected in "".join(QUADRANTS)


@pytest.mark.parametrize("froth,substance", [(None, 80.0), (80.0, None), (None, None)])
def test_one_axis_is_no_quadrant(froth, substance):
    v = decide_verdict(_hype(froth=froth), _sub(index=substance))
    assert quadrant_of(froth, substance) is None
    assert v.quadrant is None and "needs both axes" in v.long.basis


def test_a_dark_substance_says_unread_not_low():
    v = decide_verdict(_hype(froth=80.0), _sub(index=None))
    assert "unread, not low substance" in v.long.basis


# ─────────────────────────── the LONG horizon ─────────────────────────────

@pytest.mark.parametrize("froth,substance", [(90.0, 10.0), (10.0, 90.0), (None, None)])
def test_long_ships_dark_whatever_the_readings_say(froth, substance):
    v = decide_verdict(_hype(froth=froth), _sub(index=substance))
    assert v.long.lean is None
    assert "ships dark" in v.long.basis


def test_the_long_lean_cannot_be_set_at_all():
    with pytest.raises(Exception):
        LongView(lean="strong")


def test_h_minus_s_is_recorded_when_both_axes_read():
    v = decide_verdict(_hype(froth=71.0), _sub(index=53.0))
    assert v.long.h_minus_s == pytest.approx(18.0)
    assert "H - S = +18.0" in v.long.basis


def test_h_minus_s_is_none_when_either_axis_is_dark():
    assert decide_verdict(_hype(froth=None), _sub(index=53.0)).long.h_minus_s is None
    assert decide_verdict(_hype(froth=71.0), _sub(index=None)).long.h_minus_s is None


# ─────────────────────────── OFS, and the record ─────────────────────────

def test_ofs_share_cannot_change_any_output():
    """Spec §3: UNVALIDATED after three measurements. Captured, rendered, never scored."""
    def verdict(ofs):
        h = _hype(features={"ofs_share": ofs, "qib_x": 40.0}, components={"qib_x": 0.5})
        s = _sub(captured={"ofs_share": ofs})
        return decide_verdict(h, s, row={"symbol": "X", "issue_end": "2026-09-23",
                                         "ofs_share": ofs})
    assert verdict(0.0).model_dump() == verdict(1.0).model_dump()


def test_the_verdict_carries_the_record_it_was_decided_from():
    h = _hype(dark=["gmp_pct", "cutoff_share"], symbol="VARMORA")
    s = _sub(dark=["peer_pe_discount"])
    v = decide_verdict(h, s, row={"symbol": "VARMORA", "issue_end": "2026-09-24"})
    assert v.symbol == "VARMORA" and v.close_date == "2026-09-24"
    assert v.as_of == "2026-09-21T12:15:00+00:00" and v.state == "closed"
    assert v.demand == 80.0 and v.hype == 20.0 and v.substance == 60.0
    assert v.dark == ["hype.cutoff_share", "hype.gmp_pct", "substance.peer_pe_discount"]


def test_the_cache_row_is_the_last_resort_for_the_symbol():
    v = decide_verdict(_hype(symbol=""), _sub(symbol=""), row={"symbol": "VARMORA"})
    assert v.symbol == "VARMORA"


def test_an_explicit_state_overrides_the_snapshot_state():
    v = decide_verdict(_hype(state="open"), _sub(), state="closed")
    assert v.state == "closed" and v.short.evidenced is True


def test_a_verdict_over_nothing_is_empty_not_an_exception():
    v = decide_verdict(None, None)
    assert isinstance(v, IpoVerdict)
    assert v.short.lean is None and v.long.lean is None and v.quadrant is None
    assert v.dark == []


def test_a_broken_config_costs_the_band_not_the_whole_verdict(monkeypatch):
    """A table that is not a mapping degrades that one part of the reading.
    Losing the lean as well would be a config typo silencing a measured signal."""
    monkeypatch.setattr(settings, "IPO_SHORT_COHORTS", "not a mapping", raising=False)
    monkeypatch.setattr(settings, "IPO_SHORT_BANDS", 7, raising=False)
    monkeypatch.setattr(settings, "IPO_SHORT_BANDS_HIGH_FROTH", None, raising=False)
    v = decide_verdict(_hype(), _sub())
    assert isinstance(v.short, ShortView) and v.short.lean == "strong"
    assert v.short.band is None and v.quadrant == "quiet_compounder"


def test_an_unreadable_threshold_falls_back_rather_than_raising(monkeypatch):
    monkeypatch.setattr(settings, "IPO_SHORT_STRONG", "seventy", raising=False)
    assert lean_of(80.0) == "strong"        # the 70.0 fallback, not an exception

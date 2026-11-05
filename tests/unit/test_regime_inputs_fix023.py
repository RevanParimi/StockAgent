"""FIX-023 — deployment buys only on a regime read from live inputs, as of the
review session; and never at a close from before the idea's latest dive.

Every expected figure is worked by hand in the test's docstring or comments
from the fixture's own numbers, never asked of the code under test.

Regime thresholds these cases assume (pinned below): VIX above 22 is
volatile, below 14 calm; a Nifty 5-session move beyond ±1.0% is the FII
proxy; global stress needs 2 of Brent 5-session >= +8%, USD/INR 5-session
>= +1.5%, S&P 500 last session <= -2%. Deployment: 80% in calm labels, 50%
in RISK_OFF, nothing in MACRO_CRISIS; 2 new positions a day; ₹10 L floor
over 12 positions, so one asks for ₹83,333.33.

Independent invariants:
- the card's acceptance shapes, through the real detector (Yahoo faked by
  ticker and dated bar), the real daily review's step 0, the real regime
  state file and the real executor: with India VIX dark, or VIX and the
  Nifty dark, or the detector raising, no position opens and the reason
  names why; a live crisis (the control) and a live VIX of exactly 17.0
  behave as before;
- the hysteresis: a crisis already entered survives any run of dark days,
  which never count as calm; a dark day enters only a severer label its
  live inputs establish; the first established detection of a day replaces
  the dark mark, once;
- a missing input that cannot change the label's severity does not close
  the day; one that could does;
- issue time (L3): the label for session D reads D's VIX and Nifty even when
  Yahoo already has D+1's bars, and the overseas inputs' sessions before D;
- RR-L1: in either gate mode, a buy that opens a position (deployment, a
  SWITCH leg, the shadow's switch test) never takes a close whose bar is
  before the idea's latest deep dive or watchlist analysis;
- RR-T1: a watchlist BUY analysed after the review session is not offered,
  and the next run offers it.
"""
from __future__ import annotations

import logging
import math
from datetime import date, timedelta

import pandas as pd
import pytest

import core.intelligence.rl.workflows.daily_review as dr
import core.portfolio.pipeline as pipeline
import tests.unit.test_deploy_idle_cash_sa049 as story
import tests.unit.test_idea_supply_pr004 as pr004
from backend.shared.pipeline import decision_gate as dg
from backend.shared.schemas.discovery import ShelfIdea
from backend.shared.schemas.portfolio import AdviceRecord
from core.config import settings
from core.discovery import candidates as cands_mod
from core.discovery.shelf import close_before_dive
from core.intelligence.regime import state
from core.intelligence.regime.detector import RegimeDetector
from core.portfolio import autopilot as ap
from core.portfolio import exit_shadow as xs
from core.portfolio.pricing import SessionClose

WED, THU, FRI = date(2026, 10, 28), date(2026, 10, 29), date(2026, 10, 30)
SAT, MON, TUE = date(2026, 10, 31), date(2026, 11, 2), date(2026, 11, 3)


@pytest.fixture(autouse=True)
def _world(monkeypatch, tmp_path):
    """The owner's deployment settings, no trading costs, the regime state in
    tmp, the regime thresholds above, every sector's RSI read from the Nifty,
    every symbol cleared by NSE's report, and no registry writes."""
    for name, value in {
        "PORTFOLIO_COSTS": story.NO_COSTS, "ADVISOR_MAX_POSITION_PCT": 10.0,
        "ADVISOR_MAX_SECTOR_PCT": 30.0, "AUTOPILOT_MIN_CASH_FLOOR": 10_000.0,
        "AUTOPILOT_ENABLED": True, "AUTOPILOT_DEPLOY_IDLE_CASH": True,
        "AUTOPILOT_DEPLOY_MAX_NEW_PER_DAY": 2, "AUTOPILOT_DEPLOY_TARGET_PCT": dict(story.TARGETS),
        "PORTFOLIO_MIN_HOLDINGS": 10, "PORTFOLIO_TARGET_HOLDINGS": 12,
        "PORTFOLIO_MAX_HOLDINGS": 15, "PORTFOLIO_MIN_INVESTED_INR": 1_000_000.0,
        "PORTFOLIO_OVERRIDES": {}, "DECISION_GATE_MODE": "record",
        "PREDICTION_DATA_DIR": str(tmp_path / "pred"), "RL_REGIME_STICKY_ENABLED": True,
        "RL_REGIME_CALM_DAYS": 3, "DISCOVERY_REDIVE_AFTER_DAYS": 30,
        "VIX_VOLATILE_THRESHOLD": 22.0, "VIX_LOW_VOL_THRESHOLD": 14.0,
        "FII_PROXY_THRESHOLD_PCT": 1.0, "REGIME_BRENT_SHOCK_PCT": 8.0,
        "REGIME_USDINR_STRESS_PCT": 1.5, "REGIME_SPX_DROP_PCT": -2.0,
        "REGIME_GLOBAL_STRESS_MIN_SIGNALS": 2, "REGIME_SECTOR_TICKERS": {},
    }.items():
        monkeypatch.setattr(settings, name, value)
    dg._warned.clear()
    monkeypatch.setattr(ap, "promote_symbol", lambda *a, **k: {"status": "ok"})
    story._report(monkeypatch)


# ---------------------------------------------------------------------------
# A Yahoo of dated bars
# ---------------------------------------------------------------------------

def _sessions(end: date, n: int) -> list[date]:
    """The n weekdays ending at `end`, oldest first."""
    out, d = [], end
    while len(out) < n:
        if d.weekday() < 5:
            out.insert(0, d)
        d -= timedelta(days=1)
    return out


def _bars(end: date, closes: list[float]) -> dict[date, float]:
    return dict(zip(_sessions(end, len(closes)), closes))


class _Yahoo:
    """yfinance.Ticker(sym).history(period): every bar in `bars[sym]` ({date:
    close}), whatever the period, as Yahoo's daily history is dated: a
    DatetimeIndex at midnight of each session. A symbol not in `bars` is an
    empty frame."""
    bars: dict = {}

    def __init__(self, sym):
        self.sym = sym

    def history(self, period="1mo", **_):
        rows = self.bars.get(self.sym)
        if not rows:
            return pd.DataFrame()
        days = sorted(rows)
        return pd.DataFrame({"Close": [rows[d] for d in days]},
                            index=pd.DatetimeIndex([pd.Timestamp(d) for d in days]))


def _yahoo(monkeypatch, **bars):
    """Keyword names: vix, nifty, brent, usdinr, spx."""
    import yfinance
    tickers = {"vix": "^INDIAVIX", "nifty": "^NSEI", "brent": "BZ=F", "usdinr": "INR=X",
               "spx": "^GSPC"}
    _Yahoo.bars = {tickers[k]: v for k, v in bars.items() if v is not None}
    monkeypatch.setattr(yfinance, "Ticker", _Yahoo)


def _nifty_falling(end=FRI):
    """25 sessions at 24,000, then five down to 23,280 on `end`:
    (23,280 - 24,000) / 24,000 = -3.0% over 5 sessions."""
    return _bars(end, [24_000.0] * 25 + [23_850.0, 23_700.0, 23_550.0, 23_400.0, 23_280.0])


def _flat(value, end=FRI, n=30):
    return _bars(end, [value] * n)


def _calm_globals(end=FRI):
    """Brent, USD/INR and the S&P 500 flat: 0.0%, nothing fires."""
    return {"brent": _flat(80.0, end), "usdinr": _flat(88.0, end), "spx": _flat(6_000.0, end)}


def _review(day: date, ticker="TICK") -> dict:
    """The daily review's step 0 for `day` (the real detector and sticky
    update); with no forecast envelope it stops right after them."""
    out = dr.run_daily_review(ticker, day, sector="pharma")
    assert out["status"] == "no_envelope"
    return out


def _thirty_pct_invested(tmp_path, monkeypatch):
    """₹12 L: 3 holdings of 1,200 × ₹100 (₹3,60,000 = 30%), ₹8,40,000 cash;
    three ideas at ₹1,000 in their own sectors, dived 24 Oct."""
    s = story._store(tmp_path, [story._h(f"H{k}", 1200, 100.0, f"held{k}") for k in range(3)],
                     cash=840_000.0)
    ideas = [story._idea(f"I{k}", 1000.0, 0.9 - k * 0.01, f"new{k}", dived="2026-10-24")
             for k in range(3)]
    story._prices(monkeypatch, {i.symbol: 1000.0 for i in ideas})
    monkeypatch.setattr(ap, "_today_ist", lambda: MON)
    return s, ideas, {f"H{k}": 100.0 for k in range(3)}


def _deploy_on(tmp_path, monkeypatch, day=FRI):
    s, ideas, marks = _thirty_pct_invested(tmp_path, monkeypatch)
    return story._run(s, ideas, dict(marks), on=day)


def _state_file(tmp_path):
    import json
    return json.loads((tmp_path / "pred" / "_regime_state.json").read_text(encoding="utf-8"))


def _seed_normal(monkeypatch):
    """Thursday's review, all inputs live and calm: NORMAL recorded for THU."""
    _yahoo(monkeypatch, vix=_flat(15.0, THU), nifty=_flat(24_000.0, THU), **_calm_globals(THU))
    _review(THU)
    assert state.label_recorded_for(THU.isoformat()) == "NORMAL"


# ---------------------------------------------------------------------------
# M1: a label made of fallback values opens nothing
# ---------------------------------------------------------------------------

def test_control_a_live_crisis_is_recorded_and_opens_nothing(tmp_path, monkeypatch):
    """VIX 30 > 22 and the Nifty -3.0% < -1%: MACRO_CRISIS, from live inputs."""
    _yahoo(monkeypatch, vix=_flat(30.0), nifty=_nifty_falling(), **_calm_globals())
    snap = RegimeDetector().detect(FRI, "pharma")
    assert (snap.regime_label, snap.vix_value, snap.fii_proxy_5d_pct) == \
        ("MACRO_CRISIS", 30.0, -3.0)
    assert (snap.dark_inputs, snap.unavailable) == ([], "")
    _review(FRI)
    assert state.label_recorded_for(FRI.isoformat()) == "MACRO_CRISIS"
    txns, rec = _deploy_on(tmp_path, monkeypatch)
    assert txns == []
    assert rec["reasons"] == ["market regime MACRO_CRISIS: no new positions, cash held on purpose"]


def test_with_india_vix_dark_nothing_opens_and_the_reason_names_it(tmp_path, monkeypatch):
    """The same crisis with Yahoo's ^INDIAVIX empty. Before FIX-023 the VIX
    read 17.0 and the day was recorded RISK_OFF, which bought 2 × 83 shares
    (RV2). Now the VIX has no value: with the Nifty at -3.0%, a VIX below 14
    gives NORMAL and one above 22 MACRO_CRISIS, so the label is open; the
    state keeps Thursday's NORMAL and the day opens nothing."""
    _seed_normal(monkeypatch)
    _yahoo(monkeypatch, vix=None, nifty=_nifty_falling(), **_calm_globals())
    snap = RegimeDetector().detect(FRI, "pharma")
    assert (snap.vix_value, snap.dark_inputs) == (None, ["India VIX"])
    assert (snap.unavailable, snap.floor_label) == ("India VIX did not answer", "NORMAL")
    assert "elevated VIX (n/a)" in snap.narrative            # never "17.0"
    assert "Not answered: India VIX." in snap.narrative
    _review(FRI)
    assert state.label_recorded_for(FRI.isoformat()) is None
    saved = _state_file(tmp_path)
    assert (saved["label"], saved["since"], saved["calm_streak"]) == ("NORMAL", "2026-10-29", 0)
    assert (saved["_last_update"], saved["_unavailable"]) == ("2026-10-30",
                                                              "India VIX did not answer")
    txns, rec = _deploy_on(tmp_path, monkeypatch)
    assert txns == [] and rec["regime"] is None
    assert rec["reasons"] == ["market regime unavailable for 2026-10-30: India VIX did not "
                              "answer; no new positions"]


def test_with_vix_and_nifty_dark_nothing_opens(tmp_path, monkeypatch):
    """Before FIX-023 both read their fallbacks (17.0, 0.0%) and the label was
    NORMAL, which bought toward 80%. The sector RSI reads the Nifty too."""
    _seed_normal(monkeypatch)
    _yahoo(monkeypatch, vix=None, nifty=None, **_calm_globals())
    snap = RegimeDetector().detect(FRI, "pharma")
    assert (snap.vix_value, snap.fii_proxy_5d_pct, snap.sector_rsi) == (None, None, None)
    assert snap.unavailable == "India VIX, Nifty 50 and sector index did not answer"
    _review(FRI)
    txns, rec = _deploy_on(tmp_path, monkeypatch)
    assert txns == []
    assert rec["reasons"] == ["market regime unavailable for 2026-10-30: India VIX, Nifty 50 "
                              "and sector index did not answer; no new positions"]


def test_a_detector_exception_records_the_day_unavailable(tmp_path, monkeypatch):
    """The review keeps its NORMAL default for the learning loop, but the day
    is recorded without a regime."""
    _seed_normal(monkeypatch)

    def boom(self, on, sector):
        raise RuntimeError("yfinance import broke")
    monkeypatch.setattr(RegimeDetector, "detect", boom)
    _review(FRI)
    assert state.label_recorded_for(FRI.isoformat()) is None
    assert _state_file(tmp_path)["_unavailable"] == "the regime detector failed"
    txns, rec = _deploy_on(tmp_path, monkeypatch)
    assert txns == []
    assert rec["reasons"] == ["market regime unavailable for 2026-10-30: the regime detector "
                              "failed; no new positions"]


def test_a_real_vix_of_exactly_17_is_a_live_reading(tmp_path, monkeypatch):
    """VIX 17.0 answered: 14 <= 17 <= 22 with the Nifty -3.0% is RISK_OFF.
    Target 50% of ₹12 L = ₹6,00,000 against ₹3,60,000 invested: two buys of
    floor(83,333.33 / 1,000) = 83 × ₹1,000 (the daily limit), invested
    ₹5,26,000 = 43.8%."""
    _yahoo(monkeypatch, vix=_flat(17.0), nifty=_nifty_falling(), **_calm_globals())
    _review(FRI)
    assert state.label_recorded_for(FRI.isoformat()) == "RISK_OFF"
    txns, rec = _deploy_on(tmp_path, monkeypatch)
    assert story._buys(txns) == [("I0", 83.0, 1000.0), ("I1", 83.0, 1000.0)]
    assert rec["invested_after_pct"] == 43.8


# ---------------------------------------------------------------------------
# The hysteresis on dark days
# ---------------------------------------------------------------------------

def test_a_crisis_already_entered_survives_dark_days_which_never_count_as_calm(
        tmp_path, monkeypatch):
    """MACRO_CRISIS entered on Wed 28 Oct. Thu, Fri and Mon have India VIX
    dark (the Nifty flat, so the fallback label would have been NORMAL, a
    calm day each: before FIX-023 the third exited the crisis). The state
    stays MACRO_CRISIS with calm_streak 0, and no dark day opens anything.
    Tue 3 Nov answers NORMAL: the first calm day, 1 of 3."""
    _yahoo(monkeypatch, vix=_flat(30.0, WED), nifty=_nifty_falling(WED), **_calm_globals(WED))
    _review(WED)
    assert state.label_recorded_for(WED.isoformat()) == "MACRO_CRISIS"
    for day in (THU, FRI, MON):
        _yahoo(monkeypatch, vix=None, nifty=_flat(24_000.0, day), **_calm_globals(day))
        _review(day)
        saved = _state_file(tmp_path)
        assert (saved["label"], saved["since"], saved["calm_streak"]) == \
            ("MACRO_CRISIS", "2026-10-28", 0)
        assert state.label_recorded_for(day.isoformat()) is None
    txns, _ = _deploy_on(tmp_path, monkeypatch, day=MON)
    assert txns == []
    _yahoo(monkeypatch, vix=_flat(15.0, TUE), nifty=_flat(24_000.0, TUE), **_calm_globals(TUE))
    _review(TUE)
    saved = _state_file(tmp_path)
    assert (saved["label"], saved["calm_streak"]) == ("MACRO_CRISIS", 1)
    assert state.label_recorded_for(TUE.isoformat()) == "MACRO_CRISIS"


def test_a_dark_day_enters_a_severer_label_its_live_inputs_establish(tmp_path, monkeypatch):
    """Sticky NORMAL; Friday's VIX answers 30 (above 22: at least RISK_OFF)
    but the Nifty is dark (MACRO_CRISIS if it fell): RISK_OFF is entered from
    Friday, the day stays without a label, so deployment opens nothing."""
    _seed_normal(monkeypatch)
    _yahoo(monkeypatch, vix=_flat(30.0), nifty=None, **_calm_globals())
    snap = RegimeDetector().detect(FRI, "pharma")
    assert (snap.floor_label, snap.unavailable) == \
        ("RISK_OFF", "Nifty 50 and sector index did not answer")
    _review(FRI)
    saved = _state_file(tmp_path)
    assert (saved["label"], saved["since"], saved["calm_streak"]) == ("RISK_OFF", "2026-10-30", 0)
    assert state.label_recorded_for(FRI.isoformat()) is None


def test_the_first_established_detection_of_a_day_replaces_its_dark_mark_once():
    """Sticky RISK_OFF since Wed. Thursday's first ticker sees a dark day (no
    move, marked); the second sees a live NORMAL: calm day 1 of 3, and the
    day's label is RISK_OFF; a third ticker's NORMAL changes nothing."""
    state.update_sticky_regime("RISK_OFF", WED.isoformat())
    day = THU.isoformat()
    kept = state.record_unavailable_day(day, "India VIX did not answer", "NORMAL")
    assert (kept.label, kept.calm_streak) == ("RISK_OFF", 0)
    assert state.label_recorded_for(day) is None
    assert state.update_sticky_regime("NORMAL", day).calm_streak == 1
    assert state.label_recorded_for(day) == "RISK_OFF"
    assert state.update_sticky_regime("NORMAL", day).calm_streak == 1
    assert state.record_unavailable_day(day, "India VIX did not answer").calm_streak == 1
    assert state.label_recorded_for(day) == "RISK_OFF"


def test_with_the_sticky_layer_off_or_no_state_a_dark_day_writes_nothing(tmp_path, monkeypatch):
    path = tmp_path / "pred" / "_regime_state.json"
    assert state.record_unavailable_day(FRI.isoformat(), "India VIX did not answer",
                                        "RISK_OFF") is None
    assert not path.exists()
    state.update_sticky_regime("NORMAL", THU.isoformat())
    monkeypatch.setattr(settings, "RL_REGIME_STICKY_ENABLED", False)
    before = path.read_bytes()
    assert state.record_unavailable_day(FRI.isoformat(), "India VIX did not answer") is None
    assert path.read_bytes() == before


@pytest.mark.parametrize("live, missing, label, unavailable", [
    # VIX 30 and the Nifty -3.0%: MACRO_CRISIS whatever the global inputs did.
    ({"vix": 30.0, "nifty": "falling"}, ("brent", "usdinr", "spx"), "MACRO_CRISIS", ""),
    # VIX 15, Nifty flat, USD/INR and S&P flat: one missing signal cannot reach 2.
    ({"vix": 15.0, "nifty": "flat", "usdinr": 88.0, "spx": 6_000.0}, ("brent",), "NORMAL", ""),
    # The S&P's last session before Fri (Thu) fell 3.0%: with Brent missing, two
    # signals could fire, NORMAL -> RISK_OFF.
    ({"vix": 15.0, "nifty": "flat", "usdinr": 88.0, "spx": "drop"}, ("brent",), "NORMAL",
     "Brent crude did not answer"),
])
def test_a_missing_input_closes_the_day_only_if_it_could_change_the_severity(
        monkeypatch, live, missing, label, unavailable):
    bars = {"vix": _flat(live["vix"]),
            "nifty": _nifty_falling() if live["nifty"] == "falling" else _flat(24_000.0)}
    for k in ("usdinr", "spx", "brent"):
        if k in live and live[k] == "drop":
            bars[k] = _bars(THU, [6_000.0] * 29 + [5_820.0])        # Thu: -3.0%
        elif k in live:
            bars[k] = _flat(live[k])
    _yahoo(monkeypatch, **bars)
    snap = RegimeDetector().detect(FRI, "pharma")
    assert snap.regime_label == label
    assert snap.unavailable == unavailable
    assert sorted(snap.dark_inputs) == sorted(
        {"brent": "Brent crude", "usdinr": "USD/INR", "spx": "S&P 500"}[k] for k in missing)


# ---------------------------------------------------------------------------
# L3: the label for a session is read from that session's bars
# ---------------------------------------------------------------------------

def test_the_label_for_a_session_reads_its_own_bars_not_the_run_days(monkeypatch):
    """Tuesday's run reviews Monday; Monday's run reviewed Friday. Yahoo has
    bars to Mon 2 Nov: VIX 15 to Friday and 30 on Monday; the Nifty 24,000 to
    Friday and 23,000 on Monday. Friday's label reads Friday's VIX 15 and a
    flat Nifty: NORMAL (it read Monday's MACRO_CRISIS before, RV2b). Monday's:
    VIX 30 and (23,000 - 24,000) / 24,000 = -4.1667%: MACRO_CRISIS."""
    vix = {**_flat(15.0), MON: 30.0}
    nifty = {**_flat(24_000.0), MON: 23_000.0}
    _yahoo(monkeypatch, vix=vix, nifty=nifty, **_calm_globals(MON))
    fri = RegimeDetector().detect(FRI, "pharma")
    assert (fri.regime_label, fri.vix_value, fri.fii_proxy_5d_pct) == ("NORMAL", 15.0, 0.0)
    mon = RegimeDetector().detect(MON, "pharma")
    assert (mon.regime_label, mon.vix_value, mon.fii_proxy_5d_pct) == \
        ("MACRO_CRISIS", 30.0, -4.1667)


def test_overseas_inputs_are_read_from_sessions_before_the_review_session(monkeypatch):
    """The S&P 500 fell 3.0% in its Fri 30 Oct session (6,000 -> 5,820), which
    closes at 02:30 IST on Saturday, after India's Friday close. Friday's
    label reads Thursday's session (flat); Monday's reads Friday's. Brent rose
    (88 - 80) / 80 = +10% over the 5 sessions to Friday (from Fri 23 Oct's
    80): Friday's label reads the 5 to Thursday, (87 - 80) / 80 = +8.75%
    (from Thu 22 Oct's 80)."""
    spx = {**_flat(6_000.0, THU), FRI: 5_820.0}
    brent = _bars(FRI, [80.0] * 25 + [82.0, 84.0, 86.0, 87.0, 88.0])
    _yahoo(monkeypatch, vix=_flat(15.0, MON), nifty=_flat(24_000.0, MON), spx=spx,
           brent=brent, usdinr=_flat(88.0, MON))
    fri = RegimeDetector().detect(FRI, "pharma")
    assert (fri.spx_last_pct, fri.brent_5d_pct) == (0.0, 8.75)
    mon = RegimeDetector().detect(MON, "pharma")
    assert (mon.spx_last_pct, mon.brent_5d_pct) == (-3.0, 10.0)
    assert mon.global_stress_signals == ["brent_shock", "spx_drop"]


def test_an_input_with_no_close_in_the_7_days_up_to_its_cut_did_not_answer(monkeypatch):
    """Friday 30 Oct: a VIX series ending Thu 22 Oct is 8 days old (missing);
    one ending Fri 23 Oct is 7 days old (read)."""
    _yahoo(monkeypatch, vix=_flat(15.0, date(2026, 10, 22)))
    assert RegimeDetector()._get_vix(FRI) is None
    _yahoo(monkeypatch, vix=_flat(15.0, date(2026, 10, 23)))
    assert RegimeDetector()._get_vix(FRI) == 15.0


def test_a_close_that_is_not_a_number_is_skipped(monkeypatch):
    _yahoo(monkeypatch, vix={**_flat(15.0, THU), FRI: math.nan})
    assert RegimeDetector()._get_vix(FRI) == 15.0
    _yahoo(monkeypatch, vix={THU: math.nan, FRI: math.nan})
    assert RegimeDetector()._get_vix(FRI) is None


# ---------------------------------------------------------------------------
# RR-L1: never at a close from before the idea's latest dive
# ---------------------------------------------------------------------------

def _idea(sym, price, conviction, sector, dived, source="discovery"):
    return ShelfIdea(symbol=sym, sector=sector, added=dived.isoformat(),
                     dived=dived.isoformat(), source_screen_date=dived.isoformat(),
                     conviction=conviction, data_gate="actionable", close_at_add=price,
                     entry_low=round(price * 0.96, 2), entry_high=round(price * 1.04, 2),
                     invalidation_level=round(price * 0.90, 2), thesis=f"why {sym}",
                     source=source)


@pytest.mark.parametrize("mode", ["record", "enforce"])
def test_a_close_carried_forward_from_before_the_dive_opens_nothing(tmp_path, monkeypatch,
                                                                    mode):
    """RR3's shape: Tuesday's run reviews Mon 2 Nov; NEWX has no Monday bar,
    so its close is Friday 30 Oct's (₹1,000); NEWX was first dived on Sat 31
    Oct. In record mode it was bought (83 × ₹1,000 dated 2 Nov); now neither
    mode buys, and the record names both dates."""
    monkeypatch.setattr(settings, "DECISION_GATE_MODE", mode)
    dg._warned.clear()
    store, _ = story._pipeline_world(tmp_path, monkeypatch, [], 1_200_000.0,
                                     [_idea("NEWX", 1000.0, 0.95, "pharma", SAT)],
                                     {"NEWX": 1000.0})
    carried = lambda sym, d: (SessionClose(1000.0, FRI, "agree"), d)  # noqa: E731
    monkeypatch.setattr(pipeline, "session_close", carried)
    monkeypatch.setattr(ap, "session_close", carried)
    monkeypatch.setattr(ap, "_today_ist", lambda: TUE)
    state.update_sticky_regime("NORMAL", MON.isoformat())
    pipeline.run_post_review_pipeline(MON)
    assert [t for t in store.load_transactions() if t.side == "BUY"] == []
    record = store.load_latest_digest()["deployment"]
    assert story._outcomes(record)["NEWX"] == (
        "before_dive", "close of 2026-10-30 is before the deep dive of 2026-10-31")
    assert "1 idea priced at a close from before its latest deep dive" in record["reasons"]


def test_a_carried_forward_bar_on_the_dive_day_keeps_record_mode(tmp_path, monkeypatch):
    """FRIX was dived on Fri 30 Oct; Monday's bar is missing, so its close is
    Friday's: on the dive's day, so SA-003's record mode buys as before
    (83 × ₹1,000, dated 2 Nov) and notes the bar."""
    store, _ = story._pipeline_world(tmp_path, monkeypatch, [], 1_200_000.0,
                                     [_idea("FRIX", 1000.0, 0.95, "pharma", FRI)],
                                     {"FRIX": 1000.0})
    carried = lambda sym, d: (SessionClose(1000.0, FRI, "agree"), d)  # noqa: E731
    monkeypatch.setattr(pipeline, "session_close", carried)
    monkeypatch.setattr(ap, "session_close", carried)
    monkeypatch.setattr(ap, "_today_ist", lambda: TUE)
    state.update_sticky_regime("NORMAL", MON.isoformat())
    pipeline.run_post_review_pipeline(MON)
    buys = [t for t in store.load_transactions() if t.side == "BUY"]
    assert [(t.date, t.symbol, t.qty, t.price) for t in buys] == \
        [("2026-11-02", "FRIX", 83.0, 1000.0)]
    assert "its close is from bar 2026-10-30, not the review session" in buys[0].note


def test_a_switch_leg_at_a_close_from_before_the_dive_is_not_bought(tmp_path, monkeypatch):
    """Record mode, deployment off. AAA (1,000 × ₹100) is switched into NEWX
    (dived Sat 31 Oct) on Monday's session, whose bar is missing: Friday's
    ₹1,000 close. AAA is sold, NEWX is not bought, and the ₹1,00,000 stays in
    cash, said on the SELL. The shadow's switch test agrees; with Monday's
    own bar both would buy."""
    monkeypatch.setattr(settings, "AUTOPILOT_DEPLOY_IDLE_CASH", False)
    s = story._store(tmp_path, [story._h("AAA", 1000, 100.0, "it_sector")], cash=900_000.0)
    newx = _idea("NEWX", 1000.0, 0.95, "pharma", SAT)
    story._prices(monkeypatch, {"NEWX": 1000.0}, bars={"NEWX": FRI})
    monkeypatch.setattr(ap, "_today_ist", lambda: TUE)
    switch = AdviceRecord(date=MON.isoformat(), user_id="u", symbol="AAA", verdict="SWITCH",
                          close=100.0, unrealised_pnl_pct=0.0, stop_pct=12.0,
                          switch_candidate="NEWX", rationale_hash="s")
    txns, _ = story._run(s, [newx], {"AAA": 100.0}, on=MON, advice=[switch])
    assert [(t.side, t.symbol, t.qty) for t in txns] == [("SELL", "AAA", 1000.0)]
    assert ap.switch_skip_reason(txns[0].note) == (
        "NEWX: close of 2026-10-30 is before the deep dive of 2026-10-31; ₹1,00,000 stays in "
        "cash")
    assert s.load().cash_deployable == 1_000_000.0
    assert xs.switch_buy_lands(SessionClose(1000.0, FRI, "agree"), MON, newx) is False
    assert xs.switch_buy_lands(SessionClose(1000.0, MON, "agree"), MON, newx) is True


def test_the_close_and_dive_rule():
    shelf = _idea("X", 100.0, 0.9, "pharma", SAT)
    watch = _idea("W", 100.0, 0.9, "pharma", SAT, source="watchlist")
    assert close_before_dive(FRI, shelf) == "close of 2026-10-30 is before the deep dive of 2026-10-31"
    assert close_before_dive(FRI, watch) == "close of 2026-10-30 is before the analysis of 2026-10-31"
    assert close_before_dive(MON, shelf) == ""
    assert close_before_dive(SAT, shelf) == ""                    # the dive's own day
    assert close_before_dive(None, shelf) == ("close from an undated bar; cannot be placed on or "
                                              "after the deep dive of 2026-10-31")
    assert close_before_dive(FRI, None) == ""                     # no idea: the band check refuses
    undatable = shelf.model_copy(update={"dived": "", "source_screen_date": "", "added": ""})
    assert close_before_dive(FRI, undatable) == ""


# ---------------------------------------------------------------------------
# RR-T1: the watchlist lane's own bound
# ---------------------------------------------------------------------------

def test_a_watchlist_buy_analysed_after_the_review_session_waits_for_the_next_run(monkeypatch):
    """W, the user's watchlist BUY at 0.80, analysed Sat 31 Oct 12:30 IST
    (07:00 UTC). Monday's run reviews Fri 30 Oct: 30 Oct - 31 Oct = -1 day,
    not offered. Tuesday's run reviews Mon 2 Nov: 2 days old, offered, its
    band from the 31 Oct close (₹500): 97-102% = ₹485-510."""
    monkeypatch.setattr(settings, "DISCOVERY_STALE_DAYS", 60)
    monkeypatch.setattr(settings, "DISCOVERY_WATCHLIST_BUYS", True)
    monkeypatch.setattr(settings, "DISCOVERY_MIN_CONVICTION", 0.55)
    rec = pr004.record(run_at="2026-10-31T07:00:00")
    window = pr004._eod_window(["W"], days=40, end=MON, close=500.0)

    def offered(on):
        return cands_mod.buy_candidates(pr004.portfolio(watch=[("W", "user")]), on, [],
                                        latest_analysis=lambda s: rec, window=window,
                                        listing=pr004.companies("W"), managed={})
    out, excluded = offered(FRI)
    assert out == [] and excluded == {"W": "latest analysis of 2026-10-31 is -1 days old (limit 30)"}
    out, excluded = offered(MON)
    assert excluded == {}
    assert [(i.symbol, i.dived, i.entry_low, i.entry_high) for i in out] == \
        [("W", "2026-10-31", 485.0, 510.0)]

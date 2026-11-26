"""PR-047 — buy what the analysis itself would buy (the owner's option A,
21 Nov 2026): at every door to a buy, the composite's band and the
analysis's own model must both say BUY or STRONG BUY.

Every expected figure is worked by hand in the test's docstring or comments
from the fixture's own numbers, never asked of the code under test.

World (SA-049's `_pinned` and FIX-023's `_world`, both autouse): record mode;
deployment on, 80% invested in calm labels, 2 new positions a day, a new
position 80% of equity / 12; caps 10% of equity a stock and 30% a sector;
cash floor ₹10,000; no trading costs; NSE's report clears every symbol.

Independent invariants:
- A1, every door: over every (band, model) pair, the shelf's add, a re-dive,
  the candidate list, deployment, a SWITCH leg and the watchlist take the
  idea exactly when the table `TAKEN`, written here by hand, says so.
- A2, never more: requiring the model's BUY only refuses; over random ideas,
  every idea the new rule takes, FIX-029's rule (the band alone) took too.
- A3, issue time: the model verdict an idea carries is the one the same
  analysis's model wrote before the band replaced it: through the real
  aggregator, the deep dive, the shelf file, the dive record and the score
  history.
- A4, ideas shelved before PR-047: read from the verdict-shadow log by their
  own dive's row (symbol, day, score, band); they fail closed when that row
  cannot be told; the weekly run drops the ones the model did not rate a BUY
  and re-dives first the ones it cannot tell.
- The card's case: TVSMOTOR's dive of 14 Nov, band BUY, model NEUTRAL.
"""
from __future__ import annotations

import json
import random
from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import patch

import pytest

import core.discovery.deep_dive as dd
import tests.unit.test_deploy_idle_cash_sa049 as story
import tests.unit.test_every_door_fix029 as f29
import tests.unit.test_idea_supply_pr004 as pr004
from backend.shared.config import settings as shared_settings
from backend.shared.pipeline import verdict_shadow as vs
from backend.shared.pipeline.signal_aggregator import SignalAggregator
from backend.shared.schemas.discovery import DiscoveryCandidate, Shelf, ShelfIdea
from backend.shared.schemas.pipeline import AgentOutput
from backend.shared.schemas.portfolio import AdviceRecord
from core.config import settings
from core.discovery import shelf as shelf_mod
from core.discovery.candidates import buy_candidates
from core.discovery.dive_record import DiveRecord
from core.intelligence.rl.nse_calendar import IST
from core.portfolio import autopilot as ap
from services.data.stores.score_store import ScoreStore
from tests.unit.test_deploy_idle_cash_sa049 import _pinned  # noqa: F401  (autouse)
from tests.unit.test_idea_supply_pr004 import shelf  # noqa: F401  (a fixture)
from tests.unit.test_regime_inputs_fix023 import _world  # noqa: F401  (autouse)

BANDS = ("STRONG BUY", "BUY", "NEUTRAL", "SELL", "")
MODELS = ("STRONG BUY", "BUY", "strong_buy", "Buy", "NEUTRAL", "SELL", "")
# By hand: a door takes the idea only when the band is BUY or STRONG BUY and
# the model wrote BUY or STRONG BUY, in whatever case or with an underscore.
TAKEN = {(band, model) for band in ("STRONG BUY", "BUY")
         for model in ("STRONG BUY", "BUY", "strong_buy", "Buy")}
PAIRS = [(b, m) for b in BANDS for m in MODELS]
SAT_31 = date(2026, 10, 31)
SAT_14 = date(2026, 11, 14)              # TVSMOTOR's dive


def _legacy(symbol="TVSMOTOR", dived="2026-11-14", conviction=0.62, verdict="BUY",
            sector="automobile"):
    """An idea as the shelf kept it before PR-047: no model verdict."""
    return story._idea(symbol, 1000.0, conviction, sector, dived=dived, verdict=verdict,
                       model_verdict="")


def _row(ticker, ts, score, band, model):
    """A verdict-shadow row as `log_verdict_shadow` writes it."""
    return {"ts": ts, "ticker": ticker, "sector": "", "composite": 0.62,
            "threshold_verdict": band, "llm_verdict": model, "llm_final_score": score,
            "diverged": band != model, "learned_weights_used": False}


# ---------------------------------------------------------------------------
# A1: every door, every pair
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("band, model", PAIRS)
def test_a1_the_shelf_adds_a_dive_only_when_both_say_buy(shelf, band, model):
    """A dive at 0.70 (floor 0.55) with this band and model verdict."""
    dive = pr004.dive("D1", 0.70, on=SAT_31.isoformat()).model_copy(
        update={"verdict": band, "model_verdict": model})
    out = shelf.apply_deep_dives([dive], on=SAT_31)
    assert (out["added"] == ["D1"]) is ((band, model) in TAKEN)
    # A band BUY the model did not share is named as such.
    model_refused = band in ("STRONG BUY", "BUY") and (band, model) not in TAKEN
    assert out.get("not_buy_model", []) == (["D1"] if model_refused else [])


@pytest.mark.parametrize("band, model", PAIRS)
def test_a1_a_re_dive_keeps_the_idea_only_when_both_say_buy(shelf, band, model):
    """BACK, shelved 24 Oct, re-dived 31 Oct at 0.70 with this pair: refreshed
    with the new model verdict, or dropped."""
    shelf.save(Shelf(ideas=[pr004._idea("BACK", "2026-10-24", model_verdict="")]))
    dive = pr004.dive("BACK", 0.70, on=SAT_31.isoformat(), close=1000.0).model_copy(
        update={"verdict": band, "model_verdict": model})
    out = shelf.apply_redives([dive], on=SAT_31)
    (idea,) = shelf.load().ideas
    if (band, model) in TAKEN:
        assert out["refreshed"] == ["BACK"] and idea.status == "active"
        assert idea.model_verdict == model
    else:
        assert out["refreshed"] == [] and idea.status == "dropped"


@pytest.mark.parametrize("band, model", PAIRS)
def test_a1_the_list_deployment_and_a_switch_leg(tmp_path, monkeypatch, band, model):
    """N at ₹1,000 (in its band), conviction 0.70. The list offers it, and
    deployment of ₹10 L cash buys it, exactly for the pairs in TAKEN: a new
    position is 80% of ₹10 L / 12 = ₹66,667, so 66 shares. A hand-made SWITCH
    from Y (100 × ₹1,000) into N buys it on the same pairs; otherwise the
    sale's ₹1,00,000 stays in cash."""
    idea = story._idea("N", 1000.0, 0.70, "pharma", verdict=band, model_verdict=model)
    taken = (band, model) in TAKEN
    offered, excluded = buy_candidates(SimpleNamespace(holdings=[], watchlist=[]), story.D,
                                       [idea], managed={})
    assert ([i.symbol for i in offered] == ["N"]) is taken
    assert ("N" in excluded) is (not taken)

    story._prices(monkeypatch, {"N": 1000.0})
    s = story._store(tmp_path / "deploy", [], cash=1_000_000.0)
    txns, record = story._run(s, [idea], {})
    assert story._buys(txns) == ([("N", 66.0, 1000.0)] if taken else [])
    if not taken:
        assert story._outcomes(record)["N"][0] == "verdict"

    monkeypatch.setattr(settings, "AUTOPILOT_DEPLOY_IDLE_CASH", False)
    s = story._store(tmp_path / "switch", [story._h("Y", 100, 1000.0, "it_sector")],
                     cash=800_000.0)
    switch = AdviceRecord(date=story.D.isoformat(), user_id="u", symbol="Y", verdict="SWITCH",
                          close=1000.0, unrealised_pnl_pct=0.0, stop_pct=12.0,
                          rationale_hash="x", switch_candidate="N")
    txns, _ = story._run(s, [idea], {"Y": 1000.0}, advice=[switch])
    assert ("N" in {t.symbol for t in txns if t.side == "BUY"}) is taken


@pytest.mark.parametrize("band, model", PAIRS + [("BUY", None)])
def test_a1_the_watchlist_door(monkeypatch, band, model):
    """W on the user's watchlist, analysed Wed 4 Nov 11:00 IST at 0.70, its
    band `band` and its report's model verdict `model` (None: a report made
    before PR-047, which kept none). Offered for Wednesday's close exactly for
    the pairs in TAKEN, and then carrying the model's verdict."""
    f29._watch_rules(monkeypatch)
    rec = pr004.record(verdict=band, score=0.70, run_at="2026-11-04T05:30:00", model=model)
    offered, excluded = f29._watch_list(f29.WED, lambda sym, before: rec)
    if (band, model) in TAKEN:
        assert [(i.symbol, i.model_verdict) for i in offered] == [
            ("W", model.replace("_", " ").upper())] and excluded == {}
    else:
        assert offered == [] and "W" in excluded
    if band == "BUY" and model is None:
        assert excluded["W"] == ("latest analysis kept no verdict of the model's own; waits "
                                 "for a new analysis")
    if band == "BUY" and model == "NEUTRAL":
        assert excluded["W"] == ("latest analysis's own verdict is NEUTRAL, not a BUY (the "
                                 "composite's band says BUY)")


def test_a1_a_watchlist_buy_is_still_bought_by_deployment(tmp_path, monkeypatch):
    """The watchlist idea the list offers carries the model's BUY, so
    deployment's own check (`verdict_wait` again) buys it: ₹10 L cash, 66
    shares at ₹1,000 on Wednesday's review."""
    f29._watch_rules(monkeypatch)
    rec = pr004.record(verdict="BUY", score=0.70, run_at="2026-11-04T05:30:00", model="BUY")
    (idea,), _ = f29._watch_list(f29.WED, lambda sym, before: rec)
    story._prices(monkeypatch, {"W": 1000.0})
    monkeypatch.setattr(ap, "_today_ist", lambda: f29.THU)    # the run of Thu 5 Nov
    monkeypatch.setattr(ap, "_now_iso", lambda: "2026-11-05T11:00:00+00:00")
    s = story._store(tmp_path, [], cash=1_000_000.0)
    txns, record = story._run(s, [idea], {}, on=f29.WED)
    assert story._buys(txns) == [("W", 66.0, 1000.0)], record


# ---------------------------------------------------------------------------
# A2: the rule can only refuse
# ---------------------------------------------------------------------------

def test_a2_requiring_the_models_buy_never_adds_a_buy():
    """Random ideas over every band, model and source. FIX-029's rule, written
    here: the band alone, BUY or STRONG BUY after stripping and upper-casing.
    Whatever the new rule takes, that rule took."""
    rng = random.Random(4707)
    for _ in range(2000):
        band = rng.choice(BANDS + (" buy ", "Strong Buy", "HOLD", "strong_buy", "STRONG  BUY"))
        model = rng.choice(MODELS + (" buy ", "HOLD", "INSUFFICIENT DATA"))
        idea = SimpleNamespace(verdict=band, model_verdict=model,
                               source=rng.choice(("discovery", "watchlist")))
        if shelf_mod.verdict_wait(idea) == "":
            assert band.strip().upper() in ("BUY", "STRONG BUY"), (band, model)


# ---------------------------------------------------------------------------
# A3: the model verdict is the one the same analysis wrote
# ---------------------------------------------------------------------------

def _outputs(score):
    names = ("sales_demand", "fundamentals", "pattern_analysis", "sentiment", "risk_macro")
    return {n: AgentOutput(agent=n, ticker="TVSMOTOR", overall_score=score) for n in names}


def _aggregate(monkeypatch, tmp_path, model, score, bind=True):
    """The real aggregator over five analysts at 0.65 each: whatever their
    weights, the composite is 0.65, inside the BUY band (0.55-0.75), so the
    band says BUY. Its model answers `model` at `score`. The shadow row goes
    to tmp_path/shadow.jsonl."""
    monkeypatch.setattr(vs, "_SHADOW_LOG", tmp_path / "shadow.jsonl")
    answer = json.dumps({"final_score": score, "verdict": model,
                         "investment_thesis": "The asymmetry is unfavourable at current levels."})
    with patch.object(SignalAggregator, "_call_llm", return_value=answer), \
         patch("services.clients.llm_client.OpenAI"), \
         patch.object(shared_settings, "RL_HARD_BIND_VERDICT_ENABLED", bind):
        return SignalAggregator().run("TVSMOTOR", "TVS Motor Company Ltd", _outputs(0.65))


@pytest.mark.parametrize("bind", [True, False])
def test_a3_the_report_keeps_the_models_own_verdict_bound_or_not(monkeypatch, tmp_path, bind):
    """Bound: the verdict is the band's BUY and the model's NEUTRAL is kept
    beside it. Unbound: both are the model's NEUTRAL. A reply that is not JSON
    is the parser's NEUTRAL at 0.5, kept as the model's verdict too."""
    report = _aggregate(monkeypatch, tmp_path, "NEUTRAL", 0.62, bind=bind)
    assert (report.verdict, report.model_verdict) == (("BUY" if bind else "NEUTRAL"), "NEUTRAL")
    with patch.object(SignalAggregator, "_call_llm", return_value="NOT JSON"), \
         patch("services.clients.llm_client.OpenAI"), \
         patch.object(shared_settings, "RL_HARD_BIND_VERDICT_ENABLED", True):
        broken = SignalAggregator().run("TVSMOTOR", "TVS Motor", _outputs(0.65))
    assert (broken.verdict, broken.model_verdict) == ("BUY", "NEUTRAL")


@pytest.fixture
def dive_world(tmp_path, monkeypatch):
    """run_deep_dives over TVSMOTOR, a listed company at ₹4,369, nothing
    managed or shelved; the orchestrator hands back `world.report`."""
    monkeypatch.setattr(settings, "DISCOVERY_DATA_DIR", str(tmp_path / "disc"))
    monkeypatch.setattr(settings, "DISCOVERY_REDIVE_AFTER_DAYS", 30)
    monkeypatch.setattr(settings, "DISCOVERY_MIN_CONVICTION", 0.55)
    monkeypatch.setattr(dd, "load_managed_tickers", lambda: [])
    monkeypatch.setattr(dd, "market_classification",
                        lambda s: {"sector": "Consumer Cyclical", "industry": "Auto Manufacturers"})
    window = pr004._eod_window(["TVSMOTOR"], days=30, end=date(2026, 11, 13), close=4369.0)
    monkeypatch.setattr(dd, "EodStore", lambda: SimpleNamespace(
        load_window=lambda end, sessions: window))
    world = SimpleNamespace(report=None)

    class _O:
        def analyse(self, symbol, sector_question=None, exact_symbol=False):
            return world.report
    monkeypatch.setattr(dd, "get_orchestrator", lambda route: _O())
    return world


def test_a3_the_cards_case_is_kept_off_the_shelf_end_to_end(monkeypatch, tmp_path, dive_world):
    """TVSMOTOR, 14 Nov: the real aggregator's report (band BUY, model NEUTRAL
    at 0.62, above the 0.55 floor) through the real deep dive. The dive keeps
    NEUTRAL beside BUY, the dive record writes both, and the shelf refuses it
    as a band BUY the model did not share. Before PR-047 it was shelved and
    bought (₹3.19 L on 16 Nov)."""
    from backend.shared.schemas.pipeline import DecisionGate
    report = _aggregate(monkeypatch, tmp_path, "NEUTRAL", 0.62)
    report.decision_gate = DecisionGate(status="actionable", run_id="r-tvs", reasons=[])
    report.sector_answer = {"key": "automobile", "reason": "two-wheelers", "yahoo_fits": True}
    dive_world.report = report
    (result,) = dd.run_deep_dives([DiscoveryCandidate(symbol="TVSMOTOR", close=4369.0,
                                                      composite=0.6)],
                                  on=SAT_14, max_n=5, listing=pr004.companies("TVSMOTOR"))
    assert (result.verdict, result.model_verdict, result.conviction) == ("BUY", "NEUTRAL", 0.62)
    DiveRecord().append_run([result], on=SAT_14, screen_date="2026-11-13", redives=set())
    rows = [json.loads(line) for line in
            (tmp_path / "disc" / "dives.jsonl").read_text().splitlines()]
    dive_rows = [r for r in rows if r.get("row") == "dive"]
    assert [(r["symbol"], r["verdict"], r["model_verdict"]) for r in dive_rows] == [
        ("TVSMOTOR", "BUY", "NEUTRAL")]
    out = shelf_mod.ShelfStore().apply_deep_dives([result], on=SAT_14)
    assert (out["added"], out["not_buy"], out["not_buy_model"]) == (
        [], ["TVSMOTOR"], ["TVSMOTOR"])


def test_a3_the_shelf_file_and_the_score_history_keep_it(monkeypatch, tmp_path, shelf):
    """A dive the model rated STRONG BUY is shelved with it, and the shelf
    file read back has it; a shelf.json written before PR-047 loads with ""
    (and is then refused). The score history's report keeps NEUTRAL, so the
    watchlist door, reading the real store, refuses W's band BUY."""
    dive = pr004.dive("KEEP", 0.70, on=SAT_31.isoformat()).model_copy(
        update={"model_verdict": "STRONG BUY"})
    shelf.apply_deep_dives([dive], on=SAT_31)
    assert [(i.symbol, i.model_verdict) for i in shelf.load().ideas] == [("KEEP", "STRONG BUY")]
    raw = json.loads(shelf._path.read_text())
    del raw["ideas"][0]["model_verdict"]
    shelf._path.write_text(json.dumps(raw))
    (old,) = shelf.load().ideas
    assert old.model_verdict == "" and shelf_mod.verdict_wait(old) == (
        "its deep dive kept no verdict of the model's own; waits for its re-dive")

    report = _aggregate(monkeypatch, tmp_path, "NEUTRAL", 0.70).model_copy(
        update={"ticker": "W"})
    scores = ScoreStore(db_path=str(tmp_path / "scores.db"))
    with patch("services.data.stores.score_store.datetime") as clock:
        clock.utcnow.return_value = datetime(2026, 11, 4, 5, 30)   # 11:00 IST, Wed 4 Nov
        scores.save(report)
    f29._watch_rules(monkeypatch)
    offered, excluded = f29._watch_list(f29.WED, scores.get_latest_before)
    assert offered == [] and excluded == {"W": (
        "latest analysis's own verdict is NEUTRAL, not a BUY (the composite's band says BUY)")}


# ---------------------------------------------------------------------------
# A4: ideas shelved before PR-047, read from the verdict-shadow log
# ---------------------------------------------------------------------------

# The dive of Sat 14 Nov ran at about 12:30 IST (07:00 UTC); TVSMOTOR's daily
# review re-ran on Mon 16 Nov at 16:35 IST (11:05 UTC) at another score.
DIVE_TS, REVIEW_TS = "2026-11-14T07:00:00+00:00", "2026-11-16T11:05:00+00:00"


@pytest.mark.parametrize("rows, expected", [
    # The dive's own row: same symbol, day, score and band.
    ([_row("TVSMOTOR", DIVE_TS, 0.62, "BUY", "NEUTRAL")], "NEUTRAL"),
    ([_row("TVSMOTOR.NS", DIVE_TS, 0.62, "BUY", "BUY")], "BUY"),
    # A run that crossed midnight: 00:10 IST on Sunday 15 Nov.
    ([_row("TVSMOTOR", "2026-11-14T18:40:00+00:00", 0.62, "BUY", "BUY")], "BUY"),
    # Not its row: another stock, another day, another score, another band.
    ([_row("TVSHLTD", DIVE_TS, 0.62, "BUY", "BUY")], ""),
    ([_row("TVSMOTOR", REVIEW_TS, 0.62, "BUY", "BUY")], ""),
    ([_row("TVSMOTOR", "2026-11-13T07:00:00+00:00", 0.62, "BUY", "BUY")], ""),
    ([_row("TVSMOTOR", DIVE_TS, 0.6201, "BUY", "BUY")], ""),
    ([_row("TVSMOTOR", DIVE_TS, 0.62, "STRONG BUY", "BUY")], ""),
    # Two rows of the dive that agree, and two that do not: cannot be told.
    ([_row("TVSMOTOR", DIVE_TS, 0.62, "BUY", "BUY"),
      _row("TVSMOTOR", "2026-11-14T07:20:00+00:00", 0.62, "BUY", "buy")], "BUY"),
    ([_row("TVSMOTOR", DIVE_TS, 0.62, "BUY", "BUY"),
      _row("TVSMOTOR", "2026-11-14T07:20:00+00:00", 0.62, "BUY", "NEUTRAL")], ""),
    ([], ""),
])
def test_a4_the_dives_own_row_and_nothing_else(tmp_path, rows, expected):
    """TVSMOTOR's idea: dived 14 Nov, conviction 0.62, band BUY. The log
    holds `rows`, plus a line cut short by an append in progress."""
    log = tmp_path / "shadow.jsonl"
    log.write_text("".join(json.dumps(r) + "\n" for r in rows) + '{"ts": "2026-11-1')
    (read,) = shelf_mod.with_model_verdicts([_legacy()], shelf_mod.shadow_rows(log))
    assert read.model_verdict == expected


def test_a4_a_row_the_real_aggregator_wrote_is_found(monkeypatch, tmp_path):
    """The real aggregator writes the shadow row (band BUY, model NEUTRAL at
    0.62); the shelf as it stood before PR-047 kept the band's BUY and the
    score 0.62, dived today (IST). Reading that log gives NEUTRAL."""
    day = datetime.now(IST).date()
    _aggregate(monkeypatch, tmp_path, "NEUTRAL", 0.62)
    idea = _legacy(dived=day.isoformat())
    (read,) = shelf_mod.with_model_verdicts([idea], shelf_mod.shadow_rows(tmp_path / "shadow.jsonl"))
    assert read.model_verdict == "NEUTRAL"


def test_a4_the_fill_fails_closed_and_leaves_the_rest_as_they_were(tmp_path):
    """An unreadable log (a folder where the file should be) gives no verdict,
    so the list refuses the idea; an idea that kept its own verdict, and a
    watchlist idea, are not read at all."""
    log = tmp_path / "shadow.jsonl"
    log.mkdir()
    kept = story._idea("KEPT", 1000.0, 0.7, "pharma", model_verdict="STRONG BUY")
    watch = story._idea("WL", 1000.0, 0.7, "pharma", model_verdict="", source="watchlist")
    out = shelf_mod.with_model_verdicts([_legacy(), kept, watch], shelf_mod.shadow_rows(log))
    assert [i.model_verdict for i in out] == ["", "STRONG BUY", ""]
    assert out[1] is kept and out[2] is watch
    assert shelf_mod.with_model_verdicts([_legacy()], shelf_mod.shadow_rows(
        tmp_path / "missing.jsonl"))[0].model_verdict == ""


@pytest.mark.parametrize("model, bought", [("NEUTRAL", []), ("BUY", [("TVSMOTOR", 66.0)]),
                                           (None, [])])
def test_a4_the_first_review_after_the_deploy(tmp_path, monkeypatch, model, bought):
    """The real pipeline on Mon 13 Jul, ₹10 L cash, the shelf holding one idea
    as it stood before PR-047 (dived 8 Jul at 0.62, band BUY, ₹1,000 in its
    band). The log holds that dive's row with the model's `model` (None: no
    row). NEUTRAL or no row: nothing bought. BUY: 80% of ₹10 L / 12 =
    ₹66,667, so 66 shares, as before PR-047."""
    import core.portfolio.pipeline as pipeline
    from core.intelligence.regime import state
    monkeypatch.setattr(ap, "_today_ist", lambda: story.D)
    idea = _legacy(dived="2026-07-08", sector="automobile")
    store, _ = story._pipeline_world(tmp_path, monkeypatch, [], 1_000_000.0, [idea],
                                     {"TVSMOTOR": 1000.0})
    rows = [] if model is None else [_row("TVSMOTOR", "2026-07-08T07:00:00+00:00", 0.62,
                                          "BUY", model)]
    log = tmp_path / "shadow.jsonl"
    log.write_text("".join(json.dumps(r) + "\n" for r in rows))
    monkeypatch.setattr(vs, "_SHADOW_LOG", log)          # the log the product reads
    state.update_sticky_regime("NORMAL", story.D.isoformat())
    pipeline.run_post_review_pipeline(story.D)
    assert [(t.symbol, t.qty) for t in store.load_transactions() if t.side == "BUY"] == bought


def test_a4_the_weekly_check_drops_stamps_and_leaves(shelf, tmp_path):
    """On the shelf, all dived 14 Nov at 0.62, band BUY, none with a model
    verdict: TVS (the model wrote NEUTRAL), GOOD (BUY) and ODD (no row).
    TVS is dropped with the reason, its dive memo kept; GOOD is stamped BUY;
    ODD stays as it was. A second run changes nothing."""
    ideas = [pr004._idea(s, "2026-11-14", dived="2026-11-14", conviction=0.62,
                         model_verdict="") for s in ("TVS", "GOOD", "ODD")]
    shelf.save(Shelf(ideas=ideas))
    shelf.record_dives([pr004.dive("TVS", 0.62, on="2026-11-14")], on=SAT_14)
    log = tmp_path / "shadow.jsonl"
    log.write_text(json.dumps(_row("TVS", DIVE_TS, 0.62, "BUY", "NEUTRAL")) + "\n"
                   + json.dumps(_row("GOOD", DIVE_TS, 0.62, "BUY", "BUY")) + "\n")
    out = shelf.verify_model_verdicts(shelf_mod.shadow_rows(log))
    why = ("its deep dive's own verdict is NEUTRAL, not a BUY (the composite's band says BUY); "
           "deep dive of 2026-11-14, read from the verdict-shadow log")
    assert out == {"verified": ["GOOD"], "dropped": {"TVS": why}, "unverified": ["ODD"]}
    assert [(i.symbol, i.status, i.model_verdict) for i in shelf.load().ideas] == [
        ("TVS", "dropped", "NEUTRAL"), ("GOOD", "active", "BUY"), ("ODD", "active", "")]
    assert shelf.recently_dived(SAT_14) == {"TVS"}
    events = [json.loads(line) for line in shelf._events_path.read_text().splitlines()]
    assert {"event": "dropped", "symbol": "TVS", "detail": why}.items() <= events[-1].items()
    assert shelf.verify_model_verdicts(shelf_mod.shadow_rows(log)) == {
        "verified": [], "dropped": {}, "unverified": ["ODD"]}


def test_a4_an_idea_it_cannot_tell_is_re_dived_before_the_stale_ones(shelf):
    """On Sat 31 Oct: U (dived 24 Oct, band BUY, no model verdict) is fresh
    but unverified, so it is due before S (both verdicts, dived 20 Sep, 41
    days ago, stale). F (both verdicts, dived 24 Oct) is not due."""
    shelf.save(Shelf(ideas=[pr004._idea("S", "2026-09-20"),
                            pr004._idea("U", "2026-10-24", model_verdict=""),
                            pr004._idea("F", "2026-10-24")]))
    assert [i.symbol for i in shelf.redive_due(SAT_31)] == ["U", "S"]


def test_a4_the_weekly_run_checks_before_the_re_dives():
    """The discovery run's hygiene: verify_model_verdicts, then redive_due."""
    import inspect
    import core.discovery as disc
    src = inspect.getsource(disc)
    assert src.index("verify_model_verdicts()") < src.index("redive_due(on, sold)")


def test_a4_the_weekly_cycle_reports_the_check(tmp_path, monkeypatch, shelf):
    """The real weekly cycle with nothing to screen: the shelf's TVS (no model
    verdict, its log row NEUTRAL) is dropped before any re-dive is chosen, and
    the run's hygiene says so."""
    import core.discovery as disc
    pr004._cycle_env(tmp_path, monkeypatch, screen=[])
    shelf.save(Shelf(ideas=[pr004._idea("TVS", "2026-07-01", dived="2026-07-01",
                                        conviction=0.62, model_verdict="")]))
    log = tmp_path / "shadow.jsonl"
    log.write_text(json.dumps(_row("TVS", "2026-07-01T07:00:00+00:00", 0.62, "BUY",
                                   "NEUTRAL")) + "\n")
    monkeypatch.setattr(vs, "_SHADOW_LOG", log)          # the log the product reads
    passed = []
    monkeypatch.setattr(disc, "run_deep_dives", lambda cs, on, **kw: passed.extend(cs) or [])
    result = disc.run_discovery_cycle(on=date(2026, 7, 4))
    assert list(result["hygiene"]["model_verdicts"]["dropped"]) == ["TVS"]
    assert passed == []
    assert [(i.symbol, i.status) for i in shelf.load().ideas] == [("TVS", "dropped")]


def test_the_cards_case_as_the_owner_reads_it():
    """The record's words for TVSMOTOR: band BUY, model NEUTRAL."""
    idea = story._idea("TVSMOTOR", 4369.0, 0.62, "automobile", model_verdict="NEUTRAL")
    assert shelf_mod.verdict_wait(idea) == (
        "its deep dive's own verdict is NEUTRAL, not a BUY (the composite's band says BUY)")
    watch = idea.model_copy(update={"source": "watchlist", "model_verdict": ""})
    assert shelf_mod.verdict_wait(watch) == (
        "its analysis kept no verdict of the model's own; waits for a new analysis")

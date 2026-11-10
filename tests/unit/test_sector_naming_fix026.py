"""FIX-026 — the analysis names a new stock's sector from our list; an empty
or unknown sector is flagged.

Expected results are worked out by hand from the card's examples (the
comments say how), never asked of the code under test. The analyst is a stub
that returns what a model would write (its JSON block); every transport is a
fake or blocked by tests/hermetic.py; each test runs in its own sandbox.

The configured keys are config/sector_toggles.json's 22, read here through
the registry: the list the analysis must answer from.
"""
from __future__ import annotations

import asyncio
import json
import logging
import random
from datetime import date
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

import core.discovery as disc
import core.discovery.deep_dive as dd
import core.discovery.shelf as shelf_mod
from backend.sectors.registry import NATIVE_SECTORS, TICKER_SECTOR, SectorRegistry
from backend.shared.schemas.discovery import (
    DeepDiveResult, DiscoveryCandidate, SectorReading, Shelf, ShelfIdea,
)
from backend.shared.schemas.portfolio import Holding
from core.config import settings
from core.discovery import candidates as cands_mod
from core.discovery import sector_naming as sn
from core.ops.watchdog import checks as wd
from core.portfolio import sizing
from tests.unit.test_idea_supply_pr004 import _eod_window, companies

KEYS = {s["sector"] for s in SectorRegistry.all_sectors()}      # the 22 configured keys
ON = date(2026, 11, 14)                                          # a Saturday discovery run
MON = date(2026, 11, 16)                                         # the Monday session after it


def test_the_configured_list_is_the_registrys_and_generic_is_not_in_it():
    assert sn.configured_sectors().keys() == KEYS
    assert len(KEYS) == 22 and "pharma" in KEYS and "generic" not in KEYS


# ---------------------------------------------------------------------------
# A world for the real run_deep_dives: stub analyst, fixed window, no network
# ---------------------------------------------------------------------------

class Analyst:
    """Answers what a model would write. Records the graph each call ran and
    the question it was asked."""

    def __init__(self):
        self.answers: dict = {}
        self.graphs: list[str] = []
        self.questions: list[str | None] = []
        self.calls: list[str] = []

    def orchestrator(self, graph):
        me = self
        me.graphs.append(graph)

        class _O:
            def analyse(self, symbol, sector_question=None):
                me.calls.append(symbol)
                me.questions.append(sector_question)
                return SimpleNamespace(
                    final_score=0.72, verdict="BUY", investment_thesis=f"thesis {symbol}",
                    decision_gate=SimpleNamespace(status="actionable", run_id=f"r-{symbol}",
                                                  reasons=[]),
                    sector_answer=me.answers.get(symbol))
        return _O()


@pytest.fixture
def world(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "DISCOVERY_DATA_DIR", str(tmp_path / "disc"))
    monkeypatch.setattr(settings, "DISCOVERY_SHELF_SIZE", 20)
    monkeypatch.setattr(settings, "DISCOVERY_MAX_IDEAS_PER_SECTOR", 3)
    monkeypatch.setattr(settings, "DISCOVERY_REDIVE_AFTER_DAYS", 30)
    monkeypatch.setattr(settings, "DISCOVERY_STALE_DAYS", 60)
    monkeypatch.setattr(settings, "DISCOVERY_MIN_CONVICTION", 0.55)
    monkeypatch.setattr(settings, "DISCOVERY_WATCHLIST_BUYS", False)
    state = {"managed": [], "yahoo": {}, "analyst": Analyst()}
    monkeypatch.setattr(dd, "load_managed_tickers", lambda: list(state["managed"]))
    monkeypatch.setattr(dd, "market_classification",
                        lambda s: dict(state["yahoo"].get(s, {"sector": "", "industry": ""})))
    monkeypatch.setattr(dd, "get_orchestrator", state["analyst"].orchestrator)
    symbols = ["NEWDRUG", "GAPCO", "WORDCO", "MUTECO", "BANKSOFT", "HOLDCO", "MARUTI",
               "SOLDAUTO", "CHEMCO", "ODDCO", "P1", "P2", "P3"]
    window = _eod_window(symbols, days=30, end=date(2026, 11, 13), close=1000.0)

    class _Store:
        def load_window(self, end, sessions):
            return window
    monkeypatch.setattr(dd, "EodStore", _Store)
    state["listing"] = companies(*symbols)
    return state


def run(world, *symbols, flags=()):
    cands = [DiscoveryCandidate(symbol=s, close=1000.0, composite=0.5, flags=list(flags))
             for s in symbols]
    return dd.run_deep_dives(cands, on=ON, listing=world["listing"])


def ask(world, symbol, yahoo, answer):
    world["yahoo"][symbol] = yahoo
    world["analyst"].answers[symbol] = answer


# ---------------------------------------------------------------------------
# Acceptance 1 — a drug maker is "pharma", and both caps count it as one
# ---------------------------------------------------------------------------

DRUG_YAHOO = {"sector": "Healthcare", "industry": "Drug Manufacturers - Specialty & Generic"}


def test_a_drug_maker_is_named_pharma_by_its_analysis(world):
    ask(world, "NEWDRUG", DRUG_YAHOO,
        {"key": "pharma", "reason": "Makes generic formulations.", "yahoo_fits": True})
    [r] = run(world, "NEWDRUG")
    assert (r.sector, r.graph) == ("pharma", "generic")
    assert world["analyst"].graphs == ["generic"]       # no native graph for Healthcare
    assert r.sector_reading == SectorReading(answer="pharma", reason="Makes generic formulations.",
                                             yahoo_fits=True, problem="", yahoo_gap=False,
                                             source="analysis")
    assert (r.market_sector, r.industry) == ("Healthcare", "Drug Manufacturers - Specialty & Generic")
    # The one call carried the question: every configured key with its name,
    # and Yahoo's labels as evidence.
    [q] = world["analyst"].questions
    assert '"sector_key"' in q
    assert all(f"{k} (" in q for k in KEYS)
    assert 'sector "Healthcare", industry "Drug Manufacturers - Specialty & Generic"' in q
    assert world["analyst"].calls == ["NEWDRUG"]       # no extra call


def test_the_shelf_cap_and_the_sizing_cap_count_it_with_the_drug_makers(world, tmp_path):
    """Three pharma ideas are on the shelf, one of them labelled "Industrials"
    by Yahoo (the cap counts the key, not Yahoo's label). NEWDRUG (0.72) is
    stronger than the weakest (P3, 0.70), so it replaces P3.

    Sizing, by hand: equity ₹10 L; SUNPHARMA ₹1.5 L + CIPLA ₹1.3 L = ₹2.8 L,
    28% in pharma; cash ₹7.2 L. A 10% position (₹1 L) of NEWDRUG at ₹1,000
    would be 100 shares; the 30% sector cap leaves ₹20,000: 20 shares."""
    ask(world, "NEWDRUG", DRUG_YAHOO,
        {"key": "pharma", "reason": "Makes generic formulations.", "yahoo_fits": True})
    store = shelf_mod.ShelfStore()
    store.save(Shelf(ideas=[
        _named("P1", "pharma", 0.80, yahoo="Healthcare"),
        _named("P2", "pharma", 0.75, yahoo="Industrials"),
        _named("P3", "pharma", 0.70, yahoo="Healthcare")]))
    dives = run(world, "NEWDRUG")
    out = store.apply_deep_dives(dives, on=ON)
    assert (out["added"], out["displaced"]) == (["NEWDRUG"], ["P3"])
    events = [json.loads(x) for x in (tmp_path / "disc" / "shelf_events.jsonl")
              .read_text(encoding="utf-8").splitlines()]
    assert [e["detail"] for e in events if e["event"] == "dropped"] == [
        "sector cap: 3 ideas in pharma; replaced by NEWDRUG (0.72 > 0.70)"]

    offered, _ = cands_mod.buy_candidates(SimpleNamespace(holdings=[], watchlist=[]), MON,
                                          store.load().ideas, managed={})
    newdrug = next(i for i in offered if i.symbol == "NEWDRUG")
    assert newdrug.sector == "pharma"

    monkey_settings = {"ADVISOR_MAX_POSITION_PCT": 10.0, "ADVISOR_MAX_SECTOR_PCT": 30.0}
    with patch.multiple(settings, **monkey_settings):
        pf = SimpleNamespace(holdings=[_held("SUNPHARMA", "pharma", 150_000),
                                       _held("CIPLA", "pharma", 130_000)],
                             cash_deployable=720_000.0, watchlist=[])
        marks = {"SUNPHARMA": 1000.0, "CIPLA": 1000.0}
        kw = dict(symbol="NEWDRUG", price=1000.0, wanted=100_000.0, floor_cash=10_000.0)
        assert sizing.size_buy(pf, marks, sector=newdrug.sector, **kw).qty == 20.0
        assert sizing.size_buy(pf, marks, sector="generic", **kw).qty == 100.0


def _named(symbol, key, conviction, *, yahoo="", dived="2026-11-07", source="analysis",
           answer=None):
    return ShelfIdea(symbol=symbol, sector=key, added="2026-11-07", dived=dived,
                     conviction=conviction, data_gate="actionable", source_screen_date=dived,
                     entry_low=970.0, entry_high=1020.0, invalidation_level=880.0,
                     close_at_add=1000.0, market_sector=yahoo,
                     sector_reading=SectorReading(answer=answer or key, source=source))


def _held(symbol, key, value):
    return Holding(symbol=symbol, sector=key, qty=value / 1000.0, avg_buy_price=1000.0,
                   adj_avg_price=1000.0, adj_qty=value / 1000.0, buy_date="2026-10-01")


# ---------------------------------------------------------------------------
# Acceptance 2 — each fail-loud case: its record, its summary line, its warning
# ---------------------------------------------------------------------------

BANK_YAHOO = {"sector": "Financial Services", "industry": "Banks - Regional"}
NO_YAHOO = {"sector": "", "industry": ""}

FAIL_LOUD = [
    # (symbol, Yahoo, answer, stored key, problem, summary bucket, summary text, watchdog line)
    ("GAPCO", NO_YAHOO,
     {"key": "chemicals", "reason": "Makes dye intermediates, says its results note.",
      "yahoo_fits": None},
     "chemicals", "", "no_yahoo", None,
     "shelf GAPCO chemicals; Yahoo gave no classification"),
    ("WORDCO", DRUG_YAHOO,
     {"key": "Pharmaceuticals", "reason": "A drug maker.", "yahoo_fits": True},
     "generic", "not_a_key", "invalid",
     "the analysis answered 'Pharmaceuticals', not one of our keys",
     "shelf WORDCO has no sector key: the analysis answered 'Pharmaceuticals', "
     "not one of our keys"),
    ("MUTECO", DRUG_YAHOO, None,
     "generic", "no_answer", "unnamed", "the analysis gave no sector answer",
     "shelf MUTECO has no sector key: the analysis gave no sector answer"),
    ("BANKSOFT", BANK_YAHOO,
     {"key": "it_sector", "reason": "Earns its revenue from banking software.",
      "yahoo_fits": False},
     "it_sector", "", "disputed", "it_sector; Yahoo: Financial Services / Banks - Regional",
     "shelf BANKSOFT it_sector; the analysis says Yahoo's labels (Financial Services / "
     "Banks - Regional) do not fit"),
]


@pytest.mark.parametrize("sym, yahoo, answer, key, problem, bucket, text, warning", FAIL_LOUD,
                         ids=[c[0] for c in FAIL_LOUD])
def test_each_fail_loud_case_is_recorded_summarised_and_warned(
        world, monkeypatch, sym, yahoo, answer, key, problem, bucket, text, warning):
    ask(world, sym, yahoo, answer)
    [r] = run(world, sym)
    # The named record.
    assert (r.sector, r.sector_reading.problem) == (key, problem)
    assert r.sector_reading.yahoo_gap is (yahoo is NO_YAHOO)
    assert r.sector_reading.source == ("unnamed" if problem else "analysis")
    # The summary line.
    summary = sn.summarise([r])
    if text is None:
        assert summary[bucket] == [sym]
    else:
        assert summary[bucket] == {sym: text}
    # The watchdog warning, once the idea is shelved.
    shelf_mod.ShelfStore().apply_deep_dives([r], on=ON)
    monkeypatch.setattr(wd, "_held_positions", lambda: [])
    result = wd.sector_keys()
    assert result.state == "pending"
    assert result.detail == warning + "."
    assert result.repeat_days == 7


def test_the_yahoo_gap_is_named_from_the_bundle_and_says_so(world):
    """Yahoo answers nothing; the analysis still names a key from the
    company's own description in its data bundle. The question says Yahoo
    gave nothing, and the record keeps the gap."""
    ask(world, "GAPCO", NO_YAHOO, {"key": "chemicals", "reason": "Dye maker.", "yahoo_fits": None})
    [r] = run(world, "GAPCO")
    assert "Yahoo Finance gives no classification for it." in world["analyst"].questions[0]
    assert sn.status(r, sn.configured_sectors()) == "named"
    assert sn.summarise([r])["named"] == {"GAPCO": "chemicals (Yahoo: no Yahoo labels)"}


def test_an_idea_with_no_key_is_shelved_but_never_bought_and_is_re_dived_first(world):
    """WORDCO answered "Pharmaceuticals": shelved (its paper lane runs) but
    not offered, and due before a stale idea at the next Saturday run. Its
    re-dive answers "pharma": named, then offered."""
    ask(world, "WORDCO", DRUG_YAHOO, {"key": "Pharmaceuticals", "reason": "x", "yahoo_fits": True})
    store = shelf_mod.ShelfStore()
    store.apply_deep_dives(run(world, "WORDCO"), on=ON)
    store.save(Shelf(ideas=store.load().ideas + [
        _named("STALEONE", "metals", 0.7, dived="2026-10-01")]))   # 44 days by 14 Nov
    pf = SimpleNamespace(holdings=[], watchlist=[])
    offered, excluded = cands_mod.buy_candidates(pf, MON, store.load().ideas, managed={})
    assert [i.symbol for i in offered] == []                 # STALEONE waits for its re-dive
    assert excluded["WORDCO"] == ("sector unnamed: the analysis answered 'Pharmaceuticals', "
                                  "not one of our keys; waits for a re-dive to name it")
    nxt = date(2026, 11, 21)
    assert [i.symbol for i in store.redive_due(nxt)] == ["WORDCO", "STALEONE"]

    world["analyst"].answers["WORDCO"] = {"key": "pharma", "reason": "Drug maker.",
                                          "yahoo_fits": True}
    redived = dd.run_deep_dives([DiscoveryCandidate(symbol="WORDCO", close=0.0, composite=0.0,
                                                    flags=["redive"])],
                                on=nxt, listing=world["listing"])
    store.apply_redives(redived, on=nxt)
    idea = next(i for i in store.load().ideas if i.symbol == "WORDCO")
    assert (idea.sector, idea.sector_reading.source) == ("pharma", "analysis")
    offered, _ = cands_mod.buy_candidates(pf, date(2026, 11, 24), [idea], managed={})
    assert [(i.symbol, i.sector) for i in offered] == [("WORDCO", "pharma")]


@pytest.mark.parametrize("answer, problem, stored", [
    ({"key": "pharma"}, "", "pharma"),                     # a key needs no reason
    ({"key": " PHARMA "}, "", "pharma"),                    # case and spaces are not a new key
    ({"key": "power", "reason": "A thermal utility."}, "", "power"),
    ({"key": "generic", "reason": "A holding company with no single business."}, "", "generic"),
    ({"key": "Generic", "reason": "None fits."}, "", "generic"),
    ({"key": "generic"}, "generic_without_reason", "generic"),
    ({"key": "generic", "reason": "   "}, "generic_without_reason", "generic"),
    ({"key": ""}, "no_answer", "generic"),
    ({"key": None}, "no_answer", "generic"),
    ({}, "no_answer", "generic"),
    (None, "no_answer", "generic"),
    ({"key": 5}, "malformed", "generic"),
    ({"key": ["pharma"]}, "malformed", "generic"),
    ("pharma", "malformed", "generic"),                     # a bare string, not the block
    (["pharma"], "malformed", "generic"),
    ({"key": "it-sector"}, "not_a_key", "generic"),
    ({"key": "Pharmaceuticals & Healthcare"}, "not_a_key", "generic"),   # the display name
    ({"key": "pharma\nmetals"}, "not_a_key", "generic"),
    ({"key": "biotech"}, "not_a_key", "generic"),           # well formed, not configured
])
def test_every_answer_shape_is_checked_by_membership(answer, problem, stored):
    keys = sn.configured_sectors()
    reading = sn.read_answer(answer, keys, DRUG_YAHOO)
    key, decided = sn.decide_key(reading, ("", ""))
    assert (reading.problem, key) == (problem, stored)
    assert decided.source == ("unnamed" if problem else "analysis")
    # Only an explicit, reasoned "generic" or a configured key counts as named.
    assert (sn.unnamed_why(SimpleNamespace(symbol="X", sector=key, sector_reading=decided),
                           keys) == "") is (problem == "")


def test_yahoo_fits_must_be_a_true_boolean():
    keys = sn.configured_sectors()
    for raw, fits in [(True, True), (False, False), (None, None), ("false", None), (0, None)]:
        assert sn.read_answer({"key": "pharma", "yahoo_fits": raw}, keys, DRUG_YAHOO) \
            .yahoo_fits is fits


# ---------------------------------------------------------------------------
# Invariants: membership, and no Yahoo table decides a stored key
# ---------------------------------------------------------------------------

YAHOO_LABELS = [
    DRUG_YAHOO, BANK_YAHOO, NO_YAHOO,
    {"sector": "Consumer Cyclical", "industry": "Auto Parts"},
    {"sector": "Technology", "industry": "Software - Application"},
    {"sector": "Utilities", "industry": "Utilities - Renewable"},
    {"sector": "Financial Services", "industry": "Insurance - Life"},
    {"sector": "Industrials", "industry": "Aerospace & Defense"},
    {"sector": "Basic Materials", "industry": "Specialty Chemicals"},
    {"sector": "Consumer Defensive", "industry": "Packaged Foods"},
    {"sector": "Industrials", "industry": "Staffing & Employment Services"},
    {"sector": "Energy", "industry": ""}, {"sector": "", "industry": "Steel"},
]


def _random_answer(rng):
    pool = sorted(KEYS) + ["generic", "Generic", "pharmaceuticals", "banks", "it-sector",
                           "IT & Technology", "", "  ", "automobile ", "AUTOMOBILE", "power",
                           "biotech", "renewable energy", "\tmetals\n"]
    shape = rng.randrange(6)
    word = rng.choice(pool)
    if shape == 0:
        return None
    if shape == 1:
        return word
    if shape == 2:
        return {"key": rng.choice([None, 7, [word], {"k": word}])}
    reason = rng.choice(["", "  ", "A reason."])
    fits = rng.choice([True, False, None, "true"])
    return {"key": word, "reason": reason, "yahoo_fits": fits}


def test_property_a_stored_key_is_a_configured_key_or_generic_and_yahoo_never_decides_it():
    """3,000 random answers, each read under every Yahoo label pair (13), the
    labels FIX-011's tables mapped included: the stored key and the problem
    never depend on Yahoo's labels; the stored key is a configured key or
    "generic"; a named key is exactly the answer, trimmed and lower-cased."""
    keys = sn.configured_sectors()
    rng = random.Random(26)
    for trial in range(3000):
        answer = _random_answer(rng)
        outcomes = set()
        for labels in YAHOO_LABELS:
            reading = sn.read_answer(answer, keys, labels)
            key, decided = sn.decide_key(reading, ("", ""))
            outcomes.add((key, reading.problem, reading.answer, reading.reason))
            assert key in KEYS | {"generic"}, (trial, answer)
            if not reading.problem and key != "generic":
                assert key == answer["key"].strip().lower(), (trial, answer)
            assert decided.source == ("unnamed" if reading.problem else "analysis")
        assert len(outcomes) == 1, (trial, answer, outcomes)


def test_no_yahoo_to_key_table_is_left_in_the_deep_dive_or_the_candidates():
    for gone in ("infer_sector", "sector_from_classification", "_YAHOO_INDUSTRY_SECTOR",
                 "_YAHOO_SECTOR_SECTOR"):
        assert not hasattr(dd, gone), gone
    assert not hasattr(cands_mod, "shelf_sector")
    assert not hasattr(cands_mod, "infer_sector")


@pytest.mark.parametrize("labels, graph", [
    ({"sector": "Consumer Cyclical", "industry": "Auto Parts"}, "automobile"),
    ({"sector": "Industrials", "industry": "Farm & Heavy Construction Machinery"}, "automobile"),
    ({"sector": "Technology", "industry": "Information Technology Services"}, "it_sector"),
    ({"sector": "Technology", "industry": "Software - Infrastructure"}, "it_sector"),
    ({"sector": "Utilities", "industry": "Utilities - Independent Power Producers"},
     "renewable_energy"),
    ({"sector": "Technology", "industry": "Solar"}, "renewable_energy"),
    (BANK_YAHOO, "banking_bfsi"),
    ({"sector": "Financial Services", "industry": "Credit Services"}, "banking_bfsi"),
    ({"sector": "Financial Services", "industry": "Insurance - Life"}, "generic"),
    ({"sector": "Financial Services", "industry": "Insurance Brokers"}, "generic"),
    (DRUG_YAHOO, "generic"),
    ({"sector": "Technology", "industry": "Semiconductors"}, "generic"),
    (NO_YAHOO, "generic"),
    (None, "generic"),
])
def test_the_graph_guess_names_only_a_native_graph_or_generic(labels, graph):
    assert sn.graph_guess(labels) == graph
    assert sn.graph_guess(labels) in NATIVE_SECTORS | {"generic"}


def test_the_guess_chooses_the_graph_and_the_answer_the_key(world):
    """Yahoo calls HOLDCO a regional bank, so its analysis runs the banking
    graph (the guess); the analysis names "insurance", which is stored."""
    ask(world, "HOLDCO", BANK_YAHOO,
        {"key": "insurance", "reason": "Earns its revenue from premiums.", "yahoo_fits": False})
    [r] = run(world, "HOLDCO")
    assert world["analyst"].graphs == ["banking_bfsi"]
    assert (r.sector, r.graph, r.sector_reading.yahoo_fits) == ("insurance", "native", False)


# ---------------------------------------------------------------------------
# Acceptance 3 — decided once
# ---------------------------------------------------------------------------

def test_a_held_stock_keeps_its_key_and_the_disagreement_is_recorded(world):
    """SOLDAUTO was bought (so it is managed, under "automobile") and sold by
    the autopilot; its re-dive answers "logistics". The managed record keeps
    "automobile" (its forecasts live there), the graph is the automobile one,
    and the summary names the disagreement."""
    world["managed"] = [{"sym": "SOLDAUTO", "sector": "automobile", "enabled": True}]
    ask(world, "SOLDAUTO", {"sector": "Industrials", "industry": "Trucking"},
        {"key": "logistics", "reason": "Runs a trucking fleet.", "yahoo_fits": True})
    [r] = run(world, "SOLDAUTO", flags=["sold"])
    assert (r.sector, r.graph) == ("automobile", "native")
    assert world["analyst"].graphs == ["automobile"]
    assert (r.sector_reading.source, r.sector_reading.answer) == ("managed", "logistics")
    assert sn.summarise([r])["kept"] == {
        "SOLDAUTO": "automobile (managed); the analysis answered logistics"}
    offered, _ = cands_mod.buy_candidates(
        SimpleNamespace(holdings=[], watchlist=[]), MON,
        [_named("SOLDAUTO", "generic", 0.7, source="unnamed", answer="Trucks")],
        managed={"SOLDAUTO": "automobile"})
    assert [(i.symbol, i.sector) for i in offered] == [("SOLDAUTO", "automobile")]


def test_a_disabled_managed_record_still_keeps_its_key(world):
    """An evicted watchlist stock is not skipped by the dive, but its managed
    record (enabled or not) still holds its forecasts' key."""
    world["managed"] = [{"sym": "CHEMCO", "sector": "chemicals", "enabled": False}]
    ask(world, "CHEMCO", NO_YAHOO, {"key": "agrochem", "reason": "x", "yahoo_fits": None})
    [r] = run(world, "CHEMCO")
    assert (r.sector, r.sector_reading.source) == ("chemicals", "managed")


def test_a_managed_key_is_carried_exactly_as_stored(world):
    """The managed record names its forecasts' directory, so the dive carries
    it byte for byte, as the buy path (`holding_sector`) does. One outside
    the configured list is named by the watchdog, not silently changed."""
    world["managed"] = [{"sym": "CHEMCO", "sector": "Chemicals", "enabled": False}]
    ask(world, "CHEMCO", NO_YAHOO, {"key": "chemicals", "reason": "x", "yahoo_fits": None})
    [r] = run(world, "CHEMCO")
    assert (r.sector, r.sector_reading.source) == ("Chemicals", "managed")
    assert cands_mod.holding_sector("CHEMCO", "", {"CHEMCO": "Chemicals"}) == r.sector
    world["managed"] = [{"sym": "CHEMCO", "sector": "biotech", "enabled": False}]
    [r] = run(world, "CHEMCO")
    assert r.sector == "biotech"
    assert sn.unnamed_why(r, sn.configured_sectors()) == \
        'filed as "biotech", which is not one of our keys'


def test_the_ticker_map_keeps_its_key(world):
    assert TICKER_SECTOR["MARUTI"] == "automobile"
    ask(world, "MARUTI", {"sector": "Consumer Cyclical", "industry": "Auto Manufacturers"},
        {"key": "logistics", "reason": "wrong on purpose", "yahoo_fits": False})
    [r] = run(world, "MARUTI")
    assert (r.sector, r.sector_reading.source, r.sector_reading.answer) == \
        ("automobile", "ticker_map", "logistics")


def test_a_named_idea_keeps_its_key_through_its_redive(world):
    store = shelf_mod.ShelfStore()
    store.save(Shelf(ideas=[_named("CHEMCO", "chemicals", 0.7, dived="2026-10-01")]))
    ask(world, "CHEMCO", NO_YAHOO, {"key": "agrochem", "reason": "x", "yahoo_fits": None})
    redived = dd.run_deep_dives([DiscoveryCandidate(symbol="CHEMCO", close=0.0, composite=0.0,
                                                    flags=["redive"])],
                                on=ON, listing=world["listing"])
    assert (redived[0].sector, redived[0].sector_reading.source) == ("chemicals", "earlier")
    store.apply_redives(redived, on=ON)
    idea = store.load().ideas[0]
    assert (idea.sector, idea.sector_reading.answer) == ("chemicals", "agrochem")


def test_property_a_named_key_never_changes_and_an_unnamed_one_only_gets_named(
        world, monkeypatch):
    """60 trials of 12 Saturdays: each week a random subset of a 6-idea shelf
    is re-dived through the real dive with random answers (some managed
    stocks among them). After every week: an idea that had a configured key
    has the same key; an idea that had none has none or a configured one, or
    "generic" an analysis chose."""
    import tests.unit.test_idea_supply_pr004 as pr004
    keys = sn.configured_sectors()
    rng = random.Random(260)
    syms = ["P1", "P2", "P3", "CHEMCO", "ODDCO", "HOLDCO"]
    for trial in range(60):
        # In memory: hundreds of rapid renames of one Windows file fail at random.
        store = pr004.MemoryShelf()
        monkeypatch.setattr(dd, "ShelfStore", lambda: store)
        store.save(Shelf(ideas=[_named(s, rng.choice(["generic", "pharma", "metals"]), 0.7,
                                       source=rng.choice(["analysis", "unnamed"]),
                                       dived="2026-11-07") for s in syms]))
        world["managed"] = ([{"sym": "HOLDCO", "sector": "infra", "enabled": True}]
                            if rng.random() < 0.5 else [])
        day = ON
        for week in range(12):
            before = {i.symbol: i for i in store.load().ideas if i.status == "active"}
            picked = rng.sample(sorted(before), rng.randint(1, len(before))) if before else []
            for s in picked:
                world["analyst"].answers[s] = _random_answer(rng)
            dives = dd.run_deep_dives(
                [DiscoveryCandidate(symbol=s, close=0.0, composite=0.0, flags=["redive", "sold"])
                 for s in picked], on=day, listing=world["listing"])
            store.apply_redives(dives, on=day)
            after = {i.symbol: i for i in store.load().ideas if i.status == "active"}
            for s, idea in after.items():
                was = before[s]
                if sn.key_named(was, keys):
                    assert idea.sector == was.sector, (trial, week, s)
                else:
                    assert idea.sector in keys or idea.sector == "generic", (trial, week, s)
            day = date.fromordinal(day.toordinal() + 7)


# ---------------------------------------------------------------------------
# The buy rule: no key, no buy
# ---------------------------------------------------------------------------

def test_property_only_a_configured_key_or_a_decided_generic_is_offered():
    """2,000 random shelves of 8 fresh ideas with random keys and readings.
    The rule, stated apart from the code: an idea is offered under its
    managed record's key when managed; otherwise exactly when its key is a
    configured one (any case), or it is "generic" with a reading that has no
    problem (an analysis's choice, or a key decided before the analysis);
    every other idea is excluded as unnamed."""
    rng = random.Random(2026)
    pool = ["pharma", "metals", "generic", "biotech", "", "Pharma", "sector00"]
    readings = [None, SectorReading(answer="generic", reason="none fits"),
                SectorReading(answer="pharma"),
                SectorReading(answer="Pharmaceuticals", problem="not_a_key", source="unnamed"),
                SectorReading(problem="no_answer", source="unnamed"),
                SectorReading(answer="infra", source="managed")]
    for trial in range(2000):
        ideas = [ShelfIdea(symbol=f"S{k}", sector=rng.choice(pool) or "generic",
                           added="2026-11-07", dived="2026-11-07", conviction=0.7,
                           data_gate="actionable", sector_reading=rng.choice(readings))
                 for k in range(8)]
        managed = {"S0": "automobile"} if rng.random() < 0.3 else {}
        out, excluded = cands_mod.buy_candidates(SimpleNamespace(holdings=[], watchlist=[]),
                                                 MON, ideas, managed=managed)
        offered = {i.symbol: i.sector for i in out}
        for idea in ideas:
            key = idea.sector.strip().lower()
            r = idea.sector_reading
            if idea.symbol in managed:
                want = managed[idea.symbol]
            elif key in KEYS or (key == "generic" and r is not None and not r.problem):
                want = idea.sector
            else:
                want = None
            assert offered.get(idea.symbol) == want, (trial, idea)
            if want is None:
                assert excluded[idea.symbol].startswith("sector unnamed: "), (trial, idea)


def test_a_shelf_idea_with_no_key_cannot_be_promoted_by_hand(world, monkeypatch):
    from fastapi import HTTPException
    from services.api.routes import discovery_api
    ask(world, "MUTECO", DRUG_YAHOO, None)
    shelf_mod.ShelfStore().apply_deep_dives(run(world, "MUTECO"), on=ON)
    out = shelf_mod.ShelfStore().promote("MUTECO", user_id="u1")
    assert out == {"status": "sector_unnamed", "symbol": "MUTECO",
                   "detail": "MUTECO has no sector key yet (the analysis gave no sector "
                             "answer); its next deep dive names one"}
    monkeypatch.setattr(discovery_api, "ShelfStore", shelf_mod.ShelfStore)
    with pytest.raises(HTTPException) as err:
        asyncio.run(discovery_api.promote_idea("muteco", user={"user_id": "u1"}))
    assert err.value.status_code == 409
    assert [i.status for i in shelf_mod.ShelfStore().load().ideas] == ["active"]


# ---------------------------------------------------------------------------
# No extra call, and the other analyses are unchanged
# ---------------------------------------------------------------------------

def _analyst_with(payload):
    from backend.shared.pipeline.unified_analyst import UnifiedAnalyst
    a = UnifiedAnalyst.__new__(UnifiedAnalyst)
    client = MagicMock()
    resp = MagicMock()
    resp.choices = [MagicMock()]
    resp.choices[0].message.content = json.dumps(payload)
    resp.usage = MagicMock(prompt_tokens=100, completion_tokens=200)
    client.chat.completions.create.return_value = resp
    a._client = client
    return a, client


def _generic_payload():
    from backend.shared.pipeline.unified_analyst import DIMENSIONS
    return {d: {"score": 0.6, "confidence": 0.7, "summary": f"{d} ok", "key_positives": [],
                "key_risks": []} for d in DIMENSIONS["generic"]}


def test_the_question_rides_in_the_one_call_and_changes_nothing_else(monkeypatch):
    from backend.shared.pipeline import unified_analyst as ua
    from tests.unit.test_unified_analyst import _make_bundle, _make_query
    monkeypatch.setattr(ua, "log_llm_call", lambda **kw: None)
    keys = sn.configured_sectors()
    question = sn.sector_question(DRUG_YAHOO, keys)
    block = {"key": "pharma", "reason": "Drug maker.", "yahoo_fits": True}

    plain, plain_client = _analyst_with(_generic_payload())
    plain_out = plain.run(_make_query(), _make_bundle(), "generic")
    asked, asked_client = _analyst_with({**_generic_payload(), ua.SECTOR_ANSWER_KEY: block})
    asked_out = asked.run(_make_query(), _make_bundle(), "generic", sector_question=question)

    assert plain_client.chat.completions.create.call_count == 1
    assert asked_client.chat.completions.create.call_count == 1
    base = plain_client.chat.completions.create.call_args.kwargs["messages"]
    sent = asked_client.chat.completions.create.call_args.kwargs["messages"]
    assert sent[0] == base[0]                                     # the system prompt
    assert sent[1]["content"] == base[1]["content"] + "\n" + question
    system, user = plain._build_prompt(_make_query(), _make_bundle(), "generic",
                                       ua.SECTOR_SPECS["generic"])
    assert (base[0]["content"], base[1]["content"]) == (system, user)   # unchanged without it
    assert plain._last_sector_answer is None and asked._last_sector_answer == block
    assert {k: v.model_dump() for k, v in plain_out.items()} == \
        {k: v.model_dump() for k, v in asked_out.items()}


def test_a_truncated_or_failed_call_leaves_no_answer(monkeypatch):
    from backend.shared.pipeline import unified_analyst as ua
    from tests.unit.test_unified_analyst import _make_bundle, _make_query
    monkeypatch.setattr(ua, "log_llm_call", lambda **kw: None)
    a, client = _analyst_with({})
    client.chat.completions.create.return_value.choices[0].message.content = "not json"
    a._last_sector_answer = {"key": "stale"}
    assert a.run(_make_query(), _make_bundle(), "generic", sector_question="Q") == {}
    assert a._last_sector_answer is None


def _quiet_orchestrator(monkeypatch, block):
    """A generic orchestrator with the bundle, the analyst and every logger
    stubbed; the analyst answers `block` when it is asked the question."""
    import backend.shared.pipeline.base_orchestrator as bo
    import backend.shared.pipeline.unified_analyst as ua
    import services.data.context.bundle_builder as bb
    from backend.sectors.generic.pipeline.orchestrator import GenericSectorOrchestrator
    from backend.shared.schemas.pipeline import FinalReport, StockQuery

    with patch.object(bo, "get_llm_client", return_value=MagicMock()):
        orch = GenericSectorOrchestrator()
    seen = []

    class _Analyst:
        def __init__(self):
            self._last_prompt_tokens = self._last_completion_tokens = 0
            self._last_sector_answer = None

        def run(self, query, bundle, sector, run_id="", **kw):
            seen.append(kw)
            self._last_sector_answer = block if kw.get("sector_question") else None
            return {"business": MagicMock(overall_score=0.6, error=None)}

    monkeypatch.setattr(ua, "UnifiedAnalyst", _Analyst)
    monkeypatch.setattr(bb, "build_sector_bundle",
                        lambda q, s: SimpleNamespace(api_calls_made={}, has_real_data=True))
    monkeypatch.setattr(orch, "_record_data_health", lambda *a, **k: None)
    monkeypatch.setattr(orch, "_resolve_ticker",
                        lambda user_input, run_id="": StockQuery(ticker="NEWDRUG",
                                                                 company_name="New Drug Ltd"))
    monkeypatch.setattr(orch, "_resolve_weights_for", lambda t: None)
    monkeypatch.setattr(orch, "_load_learned_weights", lambda t: None)
    monkeypatch.setattr(orch, "_prefetch_nse_data", lambda q: None)
    monkeypatch.setattr(orch, "_record_score_history", lambda r: None)
    monkeypatch.setattr(orch, "_apply_decision_gate", lambda *a: None)
    for name in ("log_run_summary", "log_run_api_usage", "log_analysis"):
        monkeypatch.setattr(bo, name, lambda *a, **k: None)
    orch._aggregator = MagicMock()
    orch._aggregator.run.side_effect = lambda **kw: FinalReport(
        ticker="NEWDRUG", company_name="New Drug Ltd", final_score=0.7, verdict="BUY",
        weighted_agent_scores={})
    monkeypatch.setattr(bo.settings, "UNIFIED_ANALYST_SECTORS", "generic")
    return orch, seen


def test_the_orchestrator_passes_the_question_and_returns_the_answer(monkeypatch):
    block = {"key": "pharma", "reason": "Drug maker.", "yahoo_fits": True}
    orch, seen = _quiet_orchestrator(monkeypatch, block)
    report = orch.analyse("NEWDRUG", sector_question="the question")
    assert report.sector_answer == block
    assert seen == [{"sector_question": "the question"}]
    # The next run on the same orchestrator, asked nothing, gets nothing.
    report = orch.analyse("NEWDRUG")
    assert report.sector_answer is None
    assert seen[-1] == {}                              # the analyst is called as before


# ---------------------------------------------------------------------------
# Vigilant: the weekly summary, the scheduler's line, the watchdog
# ---------------------------------------------------------------------------

def test_the_weekly_cycle_names_every_stock_by_how_its_key_was_named(tmp_path, monkeypatch):
    import tests.unit.test_idea_supply_pr004 as pr004
    screen = [DiscoveryCandidate(symbol=s, close=100.0, composite=0.9 - k / 100)
              for k, s in enumerate(["NEWDRUG", "WORDCO", "MUTECO", "BANKSOFT", "GAPCO"])]
    env = pr004._cycle_env(tmp_path, monkeypatch, screen=screen,
                           sector_of={"NEWDRUG": "Healthcare", "WORDCO": "Healthcare",
                                      "MUTECO": "Healthcare", "BANKSOFT": "Financial Services"})
    answers = {
        "NEWDRUG": {"key": "pharma", "reason": "Drug maker.", "yahoo_fits": True},
        "WORDCO": {"key": "Pharmaceuticals", "reason": "Drug maker.", "yahoo_fits": True},
        "MUTECO": None,
        "BANKSOFT": {"key": "it_sector", "reason": "Software.", "yahoo_fits": False},
        "GAPCO": {"key": "chemicals", "reason": "Dyes.", "yahoo_fits": None},
    }
    env["analyst"].answer = answers.get
    result = disc.run_discovery_cycle(on=date(2026, 7, 4))
    assert result["sectors"] == {
        "named": {"NEWDRUG": "pharma (Yahoo: Healthcare)",
                  "BANKSOFT": "it_sector (Yahoo: Financial Services)",
                  "GAPCO": "chemicals (Yahoo: no Yahoo labels)"},
        "generic": {},
        "unnamed": {"MUTECO": "the analysis gave no sector answer"},
        "invalid": {"WORDCO": "the analysis answered 'Pharmaceuticals', not one of our keys"},
        "disputed": {"BANKSOFT": "it_sector; Yahoo: Financial Services"},
        "no_yahoo": ["GAPCO"],
        "kept": {},
    }
    assert set(result["shelf"]["added"]) == set(answers)       # all five shelved


def test_the_scheduler_line_counts_them_and_names_the_rest(monkeypatch, caplog):
    import services.scheduler.python.scheduler as sched
    sectors = {"named": {"A": "pharma (Yahoo: Healthcare)"}, "generic": {"G": "none fits"},
               "unnamed": {}, "invalid": {"W": "the analysis answered 'X', not one of our keys"},
               "disputed": {}, "no_yahoo": ["A"], "kept": {}}
    monkeypatch.setattr(disc, "run_discovery_cycle", lambda: {"sectors": sectors})
    monkeypatch.setattr("core.delivery.ops_alerts.alert_job_zero_output", lambda *a, **k: None)
    with caplog.at_level(logging.INFO):
        sched.AutomobileScheduler.__new__(sched.AutomobileScheduler)._discovery_weekly_job()
    text = caplog.text
    assert ("sectors=[named 1, generic 1, unnamed 0, invalid 1, disputed 0, no Yahoo 1, "
            "kept 0]") in text
    assert "Discovery sectors generic: {'G': 'none fits'}" in text
    assert "Discovery sectors invalid: {'W': \"the analysis answered 'X', not one of our keys\"}" \
        in text
    assert "Discovery sectors no Yahoo labels: ['A']" in text
    assert "Discovery sectors named" not in text


def test_the_watchdog_is_quiet_when_every_key_is_named(world, monkeypatch):
    shelf_mod.ShelfStore().save(Shelf(ideas=[_named("P1", "pharma", 0.8)]))
    monkeypatch.setattr(wd, "_held_positions", lambda: [_held("SUNPHARMA", "pharma", 1)])
    result = wd.sector_keys()
    assert (result.state, result.detail) == (
        "satisfied", "Every active shelf idea and holding has a named sector key.")


def test_the_watchdog_names_holdings_without_a_key_and_legacy_generic_ideas(world, monkeypatch):
    shelf_mod.ShelfStore().save(Shelf(ideas=[
        ShelfIdea(symbol="OLDGEN", sector="generic", added="2026-10-01", conviction=0.7),
        _named("P1", "pharma", 0.8)]))
    monkeypatch.setattr(wd, "_held_positions", lambda: [
        _held("HANDCO", "generic", 1), _held("TYPOCO", "biotech", 1), _held("OK", "metals", 1),
        _held("HANDCO", "generic", 1)])                   # two portfolios, one line
    result = wd.sector_keys()
    assert result.state == "pending" and result.repeat_days == 7
    assert result.detail == (
        'shelf OLDGEN has no sector key: filed as "generic" before the analysis named '
        'sectors; holding HANDCO generic; holding TYPOCO "biotech", which is not one of '
        "our keys.")
    assert result.evidence == {"ideas": 2, "keyless_or_generic": 3, "to_look_at": 0}


def test_the_registry_watches_sector_keys():
    from core.ops.watchdog.registry import load_registry
    entry = {e.id: e for e in load_registry("config/milestones.yaml")}["sector_keys_named"]
    assert (entry.kind, entry.check) == ("invariant", "sector_keys")
    assert entry.check in wd.CHECKS

"""FIX-002 — a ticker the app already tracks resolves to itself, never through an LLM.

On 1 Oct the monthly forecast for TATAELXSI (Tata Elxsi, managed in it_sector)
asked the ticker-resolution LLM which company it was. The answer was
TATAMOTORS, and TATAELXSI's October envelope was saved from a Tata Motors
analysis. The short cut in BaseSectorOrchestrator._resolve_ticker knew only
each sector's static TICKERS setting, and most managed tickers are not in it.

Independent invariants, not echoes of the implementation. The fixture managed
list is written by hand from the card's measured cases and spans five sectors;
the expected answer for every entry is the entry itself. The fake LLM answers
TATAMOTORS to any prompt, as production's did, and records each call:

- the resolver's own except-branch returns the input on any LLM error, so an
  LLM that raises could not be told apart by the returned ticker. Every test
  therefore asserts that no call was recorded, not only the ticker;
- web search (Serper) and yfinance are recorded the same way.

No network: the hermetic guard (tests/hermetic.py) runs each test in an empty
working directory, so data/managed_tickers.json is the fixture's own file.
"""
from __future__ import annotations

import json
import textwrap
from datetime import date
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

import backend.shared.data.fetchers.symbol_resolver as sr
from backend.shared.pipeline import base_orchestrator as bo
from backend.shared.pipeline.base_orchestrator import BaseSectorOrchestrator

REPO = Path(__file__).resolve().parents[3]
SHIPPED = REPO / "config" / "instruments.yaml"

ORCHESTRATORS = [
    ("automobile", "backend.sectors.automobile.pipeline.orchestrator", "AutomobileAgentOrchestrator"),
    ("banking_bfsi", "backend.sectors.banking_bfsi.pipeline.orchestrator", "BankingAgentOrchestrator"),
    ("it_sector", "backend.sectors.it_sector.pipeline.orchestrator", "ITAgentOrchestrator"),
    ("renewable_energy", "backend.sectors.renewable_energy.pipeline.orchestrator",
     "RenewableAgentOrchestrator"),
    ("generic", "backend.sectors.generic.pipeline.orchestrator", "GenericSectorOrchestrator"),
]

# Shaped like production's data/managed_tickers.json. The measured cases are
# TATAELXSI (-> TATAMOTORS, 1 Oct), TVSMOTOR (-> TVSMOTORS, 29 Sep) and
# HAPPSTMNDS (named "Happy Smile Digital Ltd", 1 Oct).
MANAGED = [
    {"sym": "TATAELXSI", "name": "Tata Elxsi Ltd", "sector": "it_sector", "enabled": True},
    {"sym": "KPITTECH", "name": "KPIT Technologies Ltd", "sector": "it_sector", "enabled": True},
    {"sym": "PERSISTENT", "name": "Persistent Systems Ltd", "sector": "it_sector", "enabled": True},
    {"sym": "HAPPSTMNDS", "name": "Happiest Minds Technologies Ltd", "sector": "it_sector",
     "enabled": True},
    {"sym": "TCS", "name": "Tata Consultancy Services Ltd", "sector": "it_sector", "enabled": True},
    {"sym": "TVSMOTOR", "name": "TVS Motor Company Ltd", "sector": "automobile", "enabled": True},
    {"sym": "TMPV", "name": "Tata Motors Passenger Vehicles Ltd", "sector": "automobile",
     "enabled": True},
    {"sym": "M&M", "name": "Mahindra & Mahindra Ltd", "sector": "automobile", "enabled": True},
    {"sym": "BAJAJ-AUTO", "name": "Bajaj Auto Ltd", "sector": "automobile", "enabled": True},
    {"sym": "TATAMOTORS", "name": "Tata Motors Ltd", "sector": "automobile", "enabled": False},
    {"sym": "YESBANK", "name": "Yes Bank Ltd", "sector": "banking_bfsi", "enabled": True},
    {"sym": "IDFCFIRSTB", "name": "IDFC First Bank Ltd", "sector": "banking_bfsi", "enabled": True},
    {"sym": "SUZLON", "name": "Suzlon Energy Ltd", "sector": "renewable_energy", "enabled": True},
    {"sym": "PAYTM", "name": "One 97 Communications Ltd", "sector": "fintech", "enabled": True},
]
MANAGED_SYMS = [e["sym"] for e in MANAGED]

# A registry fixture: one valid alias, one invalid record (quarantined), and
# one unresolved retirement. None of the three is in MANAGED or any TICKERS.
REGISTRY = """
version: 1
instruments:
  ALIASCO:
    segments:
      - {status: active, symbol: ALIASCODE.NS, basis: ALIASCODE, via: alias,
         reason: the exchange lists it under another code}
  BROKENCO:
    segments:
      - {status: active, symbol: OTHERCO.NS, via: rename}
  RETIREDCO:
    segments:
      - {status: unresolved, symbol: RETIREDCO.NS, reason: retired by the owner}
"""


class Calls:
    """Every external lookup the resolver could make, recorded."""

    def __init__(self) -> None:
        self.llm: list[str] = []
        self.serper: list[str] = []
        self.yfinance: list[str] = []


def _wrong_answer(calls: Calls):
    """An LLM that answers TATAMOTORS to any prompt, as production's did."""
    def _create(**kwargs):
        calls.llm.append(kwargs["messages"][-1]["content"])
        choice = MagicMock()
        choice.message.content = json.dumps({"ticker": "TATAMOTORS", "company_name": "Tata Motors Ltd",
                                             "exchange": "NSE", "confidence": 0.95})
        return MagicMock(choices=[choice], usage=None)
    return _create


@pytest.fixture
def calls(monkeypatch, tmp_path) -> Calls:
    """Record the LLM, Serper and yfinance; isolate the company-name cache."""
    rec = Calls()

    def _serper(query, n=3):
        rec.serper.append(query)
        return [{"title": "TATAMOTORS", "snippet": "Tata Motors Ltd, NSE: TATAMOTORS"}]

    class _FakeYfTicker:
        def __init__(self, symbol):
            rec.yfinance.append(symbol)
            self.info = {"longName": f"yfinance name of {symbol}", "regularMarketPrice": 100.0}

    monkeypatch.setattr("services.data.fetchers.news.search_serper", _serper)
    monkeypatch.setattr("yfinance.Ticker", _FakeYfTicker)
    monkeypatch.setattr(sr, "_COMPANY_NAME_CACHE_FILE", tmp_path / "company_names.json")
    monkeypatch.setattr(sr, "_company_name_cache", None)
    return rec


@pytest.fixture
def managed():
    """Write data/managed_tickers.json in the test's own working directory."""
    def _write(entries) -> Path:
        path = Path("data/managed_tickers.json")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(entries, indent=2), encoding="utf-8")
        return path
    return _write


@pytest.fixture
def registry(tmp_path, monkeypatch):
    """Point the registry at YAML text or a path. Without it the suite reads an
    empty registry (tests/conftest.py), so only the managed list applies."""
    def _use(source) -> Path:
        if isinstance(source, Path):
            path = source
        else:
            path = tmp_path / "instruments.yaml"
            path.write_text(textwrap.dedent(source), encoding="utf-8")
        monkeypatch.setenv("INSTRUMENT_REGISTRY_PATH", str(path))
        return path
    return _use


def _build(module: str, cls_name: str, calls: Calls) -> BaseSectorOrchestrator:
    import importlib
    cls = getattr(importlib.import_module(module), cls_name)
    with patch.object(bo, "get_llm_client", return_value=MagicMock()):
        orch = cls()
    orch._llm.chat.completions.create.side_effect = _wrong_answer(calls)
    return orch


# ---------------------------------------------------------------------------
# The card's invariant
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("sector, module, cls_name", ORCHESTRATORS, ids=[o[0] for o in ORCHESTRATORS])
def test_every_managed_ticker_resolves_to_itself_in_every_sector(sector, module, cls_name, calls,
                                                                 managed):
    """For every orchestrator and every managed ticker, enabled or not and in
    any sector: the same ticker, and no LLM, web-search or yfinance call (the
    company name comes from the curated or learned name; see below)."""
    managed(MANAGED)
    orch = _build(module, cls_name, calls)
    monkey_names = {e["sym"]: f"curated name of {e['sym']}" for e in MANAGED}
    with patch.object(bo, "resolve_company_name", side_effect=monkey_names.get):
        resolved = {sym: orch._resolve_ticker(sym, run_id="fix002") for sym in MANAGED_SYMS}

    assert {sym: q.ticker for sym, q in resolved.items()} == {sym: sym for sym in MANAGED_SYMS}
    assert {sym: q.company_name for sym, q in resolved.items()} == monkey_names
    assert all(q.exchange == "NSE" and q.analysis_date == date.today() for q in resolved.values())
    assert calls.llm == [] and calls.serper == [] and calls.yfinance == []
    # Not vacuous: the fixture holds tickers outside this sector's TICKERS,
    # which before FIX-002 went to the LLM (TATAELXSI is in no sector's list).
    assert {"TATAELXSI", "TVSMOTOR", "PAYTM"}.isdisjoint(orch._managed_tickers())


def test_the_measured_case_tataelxsi_is_tata_elxsi_not_tata_motors(calls, managed):
    """The 1 Oct forecast, end to end through the resolver: the IT orchestrator
    is asked for TATAELXSI with an LLM that would say TATAMOTORS."""
    managed(MANAGED)
    orch = _build(*ORCHESTRATORS[2][1:], calls)
    query = orch._resolve_ticker("TATAELXSI", run_id="fix002")

    assert (query.ticker, calls.llm, calls.serper) == ("TATAELXSI", [], [])
    # No curated or learned name in this sandbox, so yfinance names it, asked
    # for the ticker's own listing.
    assert calls.yfinance == ["TATAELXSI.NS"]
    assert query.company_name == "yfinance name of TATAELXSI.NS"


# ---------------------------------------------------------------------------
# The company name never comes from the LLM
# ---------------------------------------------------------------------------

def test_company_name_curated_then_yfinance_for_the_registry_symbol_then_the_ticker(
        calls, managed, registry, monkeypatch):
    """_company_name_for's order: the curated or learned name, else yfinance
    info for the registry symbol, else the ticker. TVSMOTORS is in the shipped
    registry as an alias of TVSMOTOR.NS; CANARABANK as an alias of CANBK.NS."""
    managed([{"sym": "CANARABANK", "sector": "banking_bfsi", "enabled": True},
             {"sym": "UNNAMEDCO", "sector": "it_sector", "enabled": True}])
    registry(SHIPPED)
    orch = _build(*ORCHESTRATORS[1][1:], calls)          # banking: neither is in its TICKERS

    # Curated (COMPANY_NAME_OVERRIDES) answers first, with no network.
    assert orch._resolve_ticker("TATAMOTORS").company_name == "Tata Motors Limited"
    assert calls.yfinance == []
    # No curated name: yfinance, for the registry's symbol, not "{TICKER}.NS".
    assert orch._resolve_ticker("CANARABANK").company_name == "yfinance name of CANBK.NS"
    assert calls.yfinance == ["CANBK.NS"]
    # yfinance fails: the ticker itself.
    monkeypatch.setattr(orch, "_yf_info", MagicMock(side_effect=RuntimeError("network down")))
    query = orch._resolve_ticker("UNNAMEDCO")
    assert (query.ticker, query.company_name) == ("UNNAMEDCO", "UNNAMEDCO")
    assert calls.llm == [] and calls.serper == []


# ---------------------------------------------------------------------------
# The instrument registry, and SA-008 unchanged
# ---------------------------------------------------------------------------

def test_a_registry_record_resolves_to_itself_even_when_not_managed(calls, managed, registry):
    """Valid, invalid (quarantined) and unresolved records all resolve to their
    own ticker; SA-008's identity, not the resolver, decides whether they act."""
    from backend.shared.data.instruments import registry_identity
    managed([])
    registry(REGISTRY)
    orch = _build(*ORCHESTRATORS[4][1:], calls)          # generic: TICKERS is empty

    for sym in ("ALIASCO", "BROKENCO", "RETIREDCO"):
        assert orch._resolve_ticker(sym).ticker == sym
    assert calls.llm == [] and calls.serper == []
    today = date.today()
    assert [registry_identity(t, today).status for t in ("ALIASCO", "BROKENCO", "RETIREDCO")] == \
        ["resolved", "unresolved", "unresolved"]


def test_the_retired_tatamotors_resolves_to_itself_and_stays_quarantined(calls, managed, registry):
    """Disabled in the managed list, unresolved in the shipped registry. Asked
    of a sector whose TICKERS lacks it, it is still TATAMOTORS (not an LLM
    guess), and its identity is still SA-008's unresolved one."""
    from backend.shared.data.instruments import registry_identity
    managed([{"sym": "TATAMOTORS", "sector": "automobile", "enabled": False}])
    registry(SHIPPED)
    orch = _build(*ORCHESTRATORS[2][1:], calls)          # it_sector

    assert orch._resolve_ticker("TATAMOTORS").ticker == "TATAMOTORS"
    assert calls.llm == []
    ident = registry_identity("TATAMOTORS", date.today())
    assert (ident.status, ident.symbol) == ("unresolved", "TMPV.NS")


def test_an_unusable_registry_names_no_ticker(calls, managed, registry):
    """An unusable registry quarantines every ticker (SA-008's is_registered is
    then True for any text), but it is no evidence that a text is a ticker:
    free text still goes to the LLM."""
    managed([])
    registry("not: [valid")
    orch = _build(*ORCHESTRATORS[3][1:], calls)          # renewable_energy

    orch._verify_ticker = lambda t: True
    query = orch._resolve_ticker("some new energy company")
    assert len(calls.llm) == 1
    assert query.ticker == "TATAMOTORS"                    # the fake LLM's answer, taken as before


# ---------------------------------------------------------------------------
# Free text is unchanged
# ---------------------------------------------------------------------------

def test_free_text_still_goes_through_llm_resolution(calls, managed):
    managed(MANAGED)
    orch = _build(*ORCHESTRATORS[2][1:], calls)
    orch._verify_ticker = lambda t: True

    query = orch._resolve_ticker("tata elxsi")
    assert len(calls.llm) == 1 and "tata elxsi" in calls.llm[0]
    assert (query.ticker, query.company_name) == ("TATAMOTORS", "Tata Motors Ltd")


def test_an_unverified_llm_answer_still_takes_the_serper_fallback(calls, managed):
    managed(MANAGED)
    orch = _build(*ORCHESTRATORS[2][1:], calls)
    orch._verify_ticker = lambda t: False

    orch._resolve_ticker("a company nobody manages")
    assert len(calls.llm) == 2 and len(calls.serper) == 1


def test_managed_input_is_matched_after_trimming_and_uppercasing(calls, managed):
    managed(MANAGED)
    orch = _build(*ORCHESTRATORS[2][1:], calls)

    assert orch._resolve_ticker("  tataelxsi ").ticker == "TATAELXSI"
    assert orch._resolve_ticker("m&m").ticker == "M&M"
    assert calls.llm == []


# ---------------------------------------------------------------------------
# The managed list is read fresh, and only read
# ---------------------------------------------------------------------------

def test_a_ticker_added_while_the_orchestrator_lives_is_known_at_once(calls, managed):
    """Most callers build a fresh orchestrator per run, but Scheduler.run_now
    reuses one. A ticker the owner adds short-cuts on the next resolution,
    even on an instance that already resolved once."""
    managed([{"sym": "TCS", "sector": "it_sector", "enabled": True}])
    orch = _build(*ORCHESTRATORS[2][1:], calls)
    orch._verify_ticker = lambda t: True
    assert orch._resolve_ticker("NEWLISTCO").ticker == "TATAMOTORS"   # unknown: the LLM's guess
    assert len(calls.llm) == 1

    managed([{"sym": "TCS", "sector": "it_sector", "enabled": True},
             {"sym": "NEWLISTCO", "sector": "it_sector", "enabled": True}])
    assert orch._resolve_ticker("NEWLISTCO").ticker == "NEWLISTCO"
    assert len(calls.llm) == 1


@pytest.mark.parametrize("content", [None, "", "{not json", '{"sym": "TATAELXSI"}', "[1, null, {}]"],
                         ids=["missing", "empty", "malformed", "not-a-list", "bad-entries"])
def test_a_missing_or_bad_managed_list_is_never_written(calls, content, caplog):
    """Resolution reads the list and never seeds or repairs it (unlike
    load_managed_tickers, which writes a seed when the file is missing). A
    file that exists but cannot be read as a list sends managed tickers back
    to the LLM, so it is logged as a warning; a missing file is not."""
    import logging
    from services.api.log_buffer import managed_symbols
    path = Path("data/managed_tickers.json")
    if content is not None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    before = path.read_bytes() if path.exists() else None

    with caplog.at_level(logging.DEBUG, logger="services.api.log_buffer"):
        assert managed_symbols() == set()
    warned = [r for r in caplog.records if r.levelno >= logging.WARNING and "managed_tickers" in r.getMessage()]
    assert bool(warned) == (content in ("", "{not json", '{"sym": "TATAELXSI"}'))
    orch = _build(*ORCHESTRATORS[2][1:], calls)
    assert orch._resolve_ticker("TCS").ticker == "TCS"     # the static list still applies
    assert (path.read_bytes() if path.exists() else None) == before


def test_the_shipped_registry_names_its_own_records_only(registry):
    """recorded_tickers lists the shipped registry's records (the checked-in
    file, read by key) and nothing else."""
    import yaml
    from backend.shared.data.instruments import recorded_tickers
    registry(SHIPPED)
    shipped = yaml.safe_load(SHIPPED.read_text(encoding="utf-8"))
    assert recorded_tickers() == {str(k).upper() for k in shipped["instruments"]}
    assert {"TATAMOTORS", "TVSMOTORS", "CANARABANK"} <= recorded_tickers()

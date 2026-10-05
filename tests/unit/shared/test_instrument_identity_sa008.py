"""SA-008 — security identity: the instrument registry and the resolver.

Independent invariants, not echoes of the implementation. Every expected
status, symbol and basis below is written by hand from the registry rules
(config/instruments.yaml's header) and the fixture's own records:

- Evidence is required to RESOLVE an identity, never to quarantine one. A
  migration (rename, demerger, relisting) without evidence, a different
  code without `via`, an alias without a reason, bad successor fractions or
  overlapping segments leave that ticker unresolved; an unusable registry
  leaves every ticker unresolved (fail closed).
- The card's fixtures: rename (same basis, both sides resolved, the current
  code is asked), demerger with multiple successors (the machine never picks
  one: unresolved until recorded, and self-heal is never consulted),
  suspension (quarantined inside the window, resolved after resumption, the
  basis unbroken), provider outage and resumption (no remapping, no cache
  write, the same instrument after).
- Cached data for another instrument cannot satisfy the identity gate: a
  learned mapping to another code is unresolved; price history fetched for
  another symbol abstains; the BSE and legacy close fallbacks ask for the
  resolved instrument, never "{TICKER}.BO"; an NSE close cached under
  another code is not served.
- The shipped registry: every former YF_SYMBOL_OVERRIDES entry is registered
  with the same provider symbol (fetching is unchanged), TATAMOTORS and
  HEXAWARE are unresolved, the two plain aliases resolve.
"""
from __future__ import annotations

import json
import textwrap
from datetime import date, timedelta
from itertools import count
from pathlib import Path

import pandas as pd
import pytest

import backend.shared.data.fetchers.symbol_resolver as sr
from backend.shared.data import instruments
from backend.shared.pipeline import decision_gate as dg
from core.schemas.pipeline import DecisionGate

REPO = Path(__file__).resolve().parents[3]
SHIPPED = REPO / "config" / "instruments.yaml"
_n = count()

EVIDENCE = '[{source: "NSE circular", ref: "NSE/CML/2026/0001", date: 2026-02-20}]'

RENAME = f"""
version: 1
instruments:
  OLDCO:
    segments:
      - {{until: 2026-03-02, status: active, symbol: OLDCO.NS, basis: OLDCO}}
      - {{from: 2026-03-02, status: active, symbol: NEWCO.NS, basis: OLDCO, via: rename,
         evidence: {EVIDENCE}}}
"""

DEMERGER_UNRECORDED = """
version: 1
instruments:
  PARENT:
    segments:
      - {until: 2026-06-15, status: active, symbol: PARENT.NS, basis: PARENT}
      - {from: 2026-06-15, status: unresolved, symbol: PARENTA.NS, basis: PARENTA,
         reason: "demerged into PARENTA and PARENTB; which one this ticker tracks is not recorded"}
"""

DEMERGER_RECORDED = f"""
version: 1
instruments:
  PARENT:
    segments:
      - {{until: 2026-06-15, status: active, symbol: PARENT.NS, basis: PARENT}}
      - {{from: 2026-06-15, status: active, symbol: PARENTA.NS, basis: PARENTA, via: demerger,
         evidence: {EVIDENCE},
         successors: [{{ticker: PARENTA, ratio: 1, cost_fraction: 0.6}},
                      {{ticker: PARENTB, ratio: 1, cost_fraction: 0.4}}]}}
"""

SUSPENSION = """
version: 1
instruments:
  HALTCO:
    segments:
      - {until: 2026-07-01, status: active, symbol: HALTCO.NS, basis: HALTCO}
      - {from: 2026-07-01, until: 2026-07-20, status: suspended, symbol: HALTCO.NS,
         basis: HALTCO, reason: "trading suspended by the exchange"}
      - {from: 2026-07-20, status: active, symbol: HALTCO.NS, basis: HALTCO}
"""


@pytest.fixture
def registry(tmp_path, monkeypatch):
    """Point the resolver at a registry: YAML text, or a path."""
    def _use(source) -> Path:
        if isinstance(source, Path):
            path = source
        else:
            path = tmp_path / f"instruments_{next(_n)}.yaml"
            path.write_text(textwrap.dedent(source), encoding="utf-8")
        monkeypatch.setenv("INSTRUMENT_REGISTRY_PATH", str(path))
        return path
    return _use


@pytest.fixture
def resolver(tmp_path, monkeypatch):
    """An isolated learned cache and no memory of earlier heal attempts."""
    monkeypatch.setattr(sr, "_CACHE_FILE", tmp_path / "yf_symbol_cache.json")
    monkeypatch.setattr(sr, "_cache", None)
    monkeypatch.setattr(sr, "_session_unresolved", set())
    return sr


@pytest.fixture
def search_spy(monkeypatch):
    """Yahoo search and price probes, recorded. Offers two valid companies."""
    calls: list[str] = []

    def _candidates(query):
        calls.append(query)
        return ["PARENTA.NS", "PARENTB.NS"]
    monkeypatch.setattr(sr, "_india_candidates", _candidates)
    monkeypatch.setattr(sr, "_has_price", lambda s: True)
    return calls


def _ident(ticker, on):
    return sr.resolve_identity(ticker, on)


# ---------------------------------------------------------------------------
# The shipped registry
# ---------------------------------------------------------------------------

FORMER_OVERRIDES = {          # settings.YF_SYMBOL_OVERRIDES before SA-008, by hand
    "TATAMOTORS": "TMPV.NS", "TVSMOTORS": "TVSMOTOR.NS",
    "CANARABANK": "CANBK.NS", "HEXAWARE": "HEXT.NS",
}


def test_the_shipped_registry_is_valid(registry):
    registry(SHIPPED)
    loaded = instruments.load_registry()
    assert loaded.failure is None and loaded.errors == {}
    assert set(loaded.entries) == set(FORMER_OVERRIDES)


def test_every_former_override_is_registered_with_the_same_symbol(registry, resolver):
    """Fetching is unchanged: each ticker is still asked of the same code."""
    registry(SHIPPED)
    today = date(2026, 9, 29)
    assert {t: _ident(t, today).symbol for t in FORMER_OVERRIDES} == FORMER_OVERRIDES


def test_the_shipped_identities(registry, resolver):
    registry(SHIPPED)
    today = date(2026, 9, 29)
    tata = _ident("TATAMOTORS", today)
    assert (tata.status, tata.basis, tata.source) == ("unresolved", "TMPV", "registry")
    assert "no exchange evidence" in tata.reason_text()
    assert _ident("HEXAWARE", today).status == "unresolved"
    assert [(_ident(t, today).status, _ident(t, today).basis) for t in ("TVSMOTORS", "CANARABANK")] \
        == [("resolved", "TVSMOTOR"), ("resolved", "CANBK")]
    # Aliases share the basis of the ticker they alias.
    assert _ident("TVSMOTOR", today).basis == _ident("TVSMOTORS", today).basis
    # A ticker the registry does not list is its own NSE listing.
    maruti = _ident("MARUTI", today)
    assert (maruti.status, maruti.symbol, maruti.basis, maruti.source) == \
        ("resolved", "MARUTI.NS", "MARUTI", "default")


def _automobile_orchestrator(llm_answer: str):
    """An automobile orchestrator whose LLM would answer `llm_answer` for any
    ticker-resolution prompt (the prompt lists TATAMOTORS as a known OEM)."""
    from unittest.mock import MagicMock, patch
    from backend.shared.pipeline.base_orchestrator import BaseSectorOrchestrator

    class _Auto(BaseSectorOrchestrator):
        SECTOR_NAME = "automobile"

        def __init__(self):
            self._sub_agents = {"dummy": object()}         # never run
            super().__init__()

    with patch("backend.shared.pipeline.base_orchestrator.get_llm_client", return_value=MagicMock()):
        orch = _Auto()
    choice = MagicMock()
    choice.message.content = json.dumps({"ticker": llm_answer, "company_name": "Tata Motors Ltd",
                                         "exchange": "NSE", "confidence": 0.9})
    orch._llm.chat.completions.create.return_value = MagicMock(choices=[choice], usage=None)
    orch._verify_ticker = lambda t: True
    orch._company_name_for = lambda t: f"name of {t}"
    return orch


def test_the_owner_decision_tmpv_is_tracked_as_its_own_listing(registry, resolver):
    """Owner's decision of 2026-09-29 (option b). TMPV needs no registry
    record: it is its own resolved listing, in the automobile sector, and the
    exact-match short cut keeps an LLM from renaming it to TATAMOTORS."""
    from backend.sectors.registry import SectorRegistry
    registry(SHIPPED)
    tmpv = _ident("TMPV", date(2026, 9, 30))
    assert (tmpv.status, tmpv.symbol, tmpv.basis, tmpv.source) == \
        ("resolved", "TMPV.NS", "TMPV", "default")
    assert SectorRegistry.resolve("TMPV") == "automobile"
    assert "retired by the owner's decision of 2026-09-29" in \
        _ident("TATAMOTORS", date(2026, 9, 30)).reason_text()

    orch = _automobile_orchestrator(llm_answer="TATAMOTORS")
    assert orch._resolve_ticker("TMPV").ticker == "TMPV"
    orch._llm.chat.completions.create.assert_not_called()
    # The hazard the short cut closes: without TMPV in the list, the LLM's
    # "correction" is taken and the run analyses the quarantined ticker.
    orch._managed_tickers_cache = {"MARUTI", "TATAMOTORS", "M&M", "HEROMOTOCO",
                                   "BAJAJ-AUTO", "EICHERMOT", "TVSMOTORS", "ASHOKLEY"}
    assert orch._resolve_ticker("TMPV").ticker == "TATAMOTORS"


# ---------------------------------------------------------------------------
# Evidence resolves; nothing is needed to quarantine
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("segment, fragment", [
    ("{status: active, symbol: NEWCO.NS, via: rename}", "needs evidence"),
    ("{status: active, symbol: NEWCO.NS}", "needs via"),
    ("{status: active, symbol: NEWCO.NS, via: alias}", "alias needs a reason"),
    ("{status: active, symbol: NEWCO.NS, via: merger, reason: r}", "via 'merger'"),
    ("{status: unresolved}", "needs a reason"),
    ("{status: suspended, reason: halted}", "needs a symbol"),
    ("{status: listed, symbol: OLDCO.NS}", "status 'listed'"),
    ("{status: active, symbol: OLDCO.NS, colour: red}", "unknown field"),
    (f"{{from: 2026-06-15, status: active, symbol: A.NS, via: demerger, evidence: {EVIDENCE},"
     " successors: [{ticker: A, ratio: 1, cost_fraction: 0.6}, {ticker: B, ratio: 1, cost_fraction: 0.3}]}",
     "sum to 0.9"),
    ("{status: active, symbol: A.NS, via: demerger,"
     " evidence: [{source: NSE, ref: x}]}", "lacks date"),
])
def test_a_record_that_does_not_prove_its_claim_is_unresolved(registry, resolver, segment, fragment):
    registry(f"""
    version: 1
    instruments:
      OLDCO:
        segments:
          - {segment}
      TVSMOTORS:
        segments:
          - {{status: active, symbol: TVSMOTOR.NS, via: alias, reason: NSE code}}
    """)
    ident = _ident("OLDCO", date(2026, 9, 1))
    assert ident.status == "unresolved"
    assert fragment in ident.reason_text(), ident.reason_text()
    # One bad record quarantines only its own ticker.
    assert _ident("TVSMOTORS", date(2026, 9, 1)).resolved


def test_the_same_migration_with_evidence_resolves(registry, resolver):
    registry(f"""
    version: 1
    instruments:
      OLDCO:
        segments:
          - {{status: active, symbol: NEWCO.NS, via: rename, evidence: {EVIDENCE}}}
    """)
    assert _ident("OLDCO", date(2026, 9, 1)).resolved


def test_quarantine_needs_no_evidence(registry, resolver):
    registry("""
    version: 1
    instruments:
      MARUTI:
        segments:
          - {status: unresolved, symbol: MARUTI.NS, reason: "under review"}
    """)
    ident = _ident("MARUTI", date(2026, 9, 1))
    assert (ident.status, ident.symbol, ident.reason_text()) == \
        ("unresolved", "MARUTI.NS", "under review")


def test_overlapping_segments_are_invalid(registry, resolver):
    registry("""
    version: 1
    instruments:
      OLDCO:
        segments:
          - {until: 2026-03-10, status: active, symbol: OLDCO.NS}
          - {from: 2026-03-02, status: active, symbol: OLDCO.NS}
    """)
    assert "overlap" in _ident("OLDCO", date(2026, 1, 5)).reason_text()


@pytest.mark.parametrize("text", [
    "version: 1\ninstruments: [not, a, mapping]\n",
    "version: 2\ninstruments: {}\n",
    "version: 1\ninstruments: {OLDCO: {segments: [\n",       # not YAML
])
def test_an_unusable_registry_fails_closed(registry, resolver, search_spy, text):
    registry(text)
    for ticker in ("MARUTI", "OLDCO", "TVSMOTORS"):
        assert _ident(ticker, date(2026, 9, 1)).status == "unresolved"
    assert sr.heal_symbol("MARUTI") is None and search_spy == []


def test_a_missing_registry_fails_closed(registry, resolver, tmp_path):
    registry(tmp_path / "absent.yaml")
    ident = _ident("MARUTI", date(2026, 9, 1))
    assert ident.status == "unresolved" and "not found" in ident.reason_text()


def test_a_date_no_segment_covers_is_unresolved(registry, resolver):
    registry("""
    version: 1
    instruments:
      LATECO:
        segments:
          - {from: 2026-05-04, status: active, symbol: LATECO.NS}
    """)
    assert _ident("LATECO", date(2026, 5, 1)).status == "unresolved"
    assert _ident("LATECO", date(2026, 5, 4)).resolved


# ---------------------------------------------------------------------------
# The card's fixtures
# ---------------------------------------------------------------------------

def test_rename_keeps_one_resolved_instrument(registry, resolver):
    registry(RENAME)
    before, after = _ident("OLDCO", date(2026, 2, 27)), _ident("OLDCO", date(2026, 3, 4))
    assert (before.status, before.basis) == ("resolved", "OLDCO")
    assert (after.status, after.basis, after.via) == ("resolved", "OLDCO", "rename")
    # The provider moves history to the new code: both days ask NEWCO.NS.
    assert before.symbol == after.symbol == "NEWCO.NS"
    assert sr.identity_break("OLDCO", date(2026, 2, 27), date(2026, 3, 4)) == ""


def test_a_close_before_the_rename_is_asked_of_the_new_code(registry, resolver, monkeypatch):
    import core.intelligence.rl.workflows.daily_review as dr
    from services.data.fetchers import close_verifier
    registry(RENAME)
    asked: list[str] = []
    monkeypatch.setattr("yfinance.download",
                        lambda sym, *a, **k: asked.append(sym) or pd.DataFrame())
    monkeypatch.setattr(dr, "get_price_history",
                        lambda sym, years=1: asked.append(f"history:{sym}") or pd.DataFrame())
    monkeypatch.setattr(close_verifier, "_fetch_nse_session", lambda t, d=None: (None, None))
    dr._fetch_session_close("OLDCO", date(2026, 2, 27))
    assert asked == ["NEWCO.NS", "NEWCO.BO", "history:NEWCO.NS"]


def test_demerger_with_two_successors_is_never_resolved_by_the_machine(
        registry, resolver, search_spy):
    registry(DEMERGER_UNRECORDED)
    assert _ident("PARENT", date(2026, 6, 12)).resolved
    after = _ident("PARENT", date(2026, 6, 16))
    assert after.status == "unresolved"
    assert "PARENTA and PARENTB" in after.reason_text()
    # An empty fetch after the event does not go looking for a successor.
    assert sr.heal_symbol("PARENT") is None
    assert search_spy == []
    assert not sr._CACHE_FILE.exists()
    assert _ident("PARENT", date(2026, 6, 16)).symbol == "PARENTA.NS"   # as recorded, not healed


def test_a_recorded_demerger_resolves_but_starts_a_new_basis(registry, resolver):
    registry(DEMERGER_RECORDED)
    before, after = _ident("PARENT", date(2026, 6, 12)), _ident("PARENT", date(2026, 6, 16))
    assert (before.status, before.basis, before.symbol) == ("resolved", "PARENT", "PARENT.NS")
    assert (after.status, after.basis, after.symbol) == ("resolved", "PARENTA", "PARENTA.NS")
    broken = sr.identity_break("PARENT", date(2026, 6, 12), date(2026, 6, 16))
    assert "PARENT" in broken and "PARENTA" in broken
    assert sr.identity_break("PARENT", date(2026, 6, 16), date(2026, 6, 30)) == ""


def test_suspension_and_resumption(registry, resolver):
    registry(SUSPENSION)
    assert _ident("HALTCO", date(2026, 6, 30)).resolved
    halted = _ident("HALTCO", date(2026, 7, 10))
    assert (halted.status, halted.reason_text()) == ("suspended", "trading suspended by the exchange")
    assert _ident("HALTCO", date(2026, 7, 20)).resolved
    # A halt is not a new price basis: prices either side compare.
    assert sr.identity_break("HALTCO", date(2026, 6, 30), date(2026, 7, 21)) == ""


def _bars(last: date, n: int = 40) -> pd.DataFrame:
    idx = pd.bdate_range(end=pd.Timestamp(last), periods=n)
    return pd.DataFrame({"Open": 100.0, "High": 101.0, "Low": 99.0, "Close": 100.0,
                         "Volume": 1000}, index=idx)


@pytest.mark.parametrize("ticker, symbol", [("TVSMOTORS", "TVSMOTOR.NS"), ("MARUTI", "MARUTI.NS")])
def test_provider_outage_and_resumption_keep_the_same_instrument(
        registry, resolver, monkeypatch, ticker, symbol):
    """A registered alias and an unlisted ticker. During the outage every
    download is empty and the search offers another company; nothing is
    remapped or learned. After it, the same instrument answers."""
    from core.intelligence.algorithms.indicators import fetcher
    registry(SHIPPED)
    monkeypatch.setattr(sr, "_india_candidates", lambda q: ["JAYBARMARU.NS"])
    monkeypatch.setattr(sr, "_has_price", lambda s: True)
    monkeypatch.setattr(fetcher.time, "sleep", lambda s: None)
    today = date(2026, 9, 29)

    monkeypatch.setattr(fetcher.yf, "download", lambda sym, **k: pd.DataFrame())
    outage = fetcher.get_price_history(ticker, years=1)
    assert outage.empty and outage.attrs["symbol"] == symbol
    assert not sr._CACHE_FILE.exists()
    assert _ident(ticker, today).symbol == symbol and _ident(ticker, today).resolved

    asked: list[str] = []
    monkeypatch.setattr(fetcher.yf, "download",
                        lambda sym, **k: asked.append(sym) or _bars(today))
    resumed = fetcher.get_price_history(ticker, years=1)
    assert not resumed.empty and resumed.attrs["symbol"] == symbol
    assert asked == [symbol]
    assert _ident(ticker, today).symbol == symbol and _ident(ticker, today).resolved


# ---------------------------------------------------------------------------
# Cached data for another instrument cannot satisfy the identity gate
# ---------------------------------------------------------------------------

def _actionable() -> DecisionGate:
    return DecisionGate(status="actionable", run_id="r1")


def test_a_learned_mapping_to_another_code_is_unresolved(registry, resolver):
    registry(Path(__file__).resolve().parents[2] / "fixtures" / "instruments_empty.yaml")
    sr._CACHE_FILE.write_text(json.dumps({"FOOCO": "BARCO.NS", "SUZLON": "SUZLON.BO"}),
                              encoding="utf-8")
    foo = _ident("FOOCO", date(2026, 9, 1))
    assert (foo.status, foo.symbol, foo.source) == ("unresolved", "BARCO.NS", "learned")
    assert sr.resolve_yf_symbol("FOOCO") == "BARCO.NS"       # still fetched, as before
    # The same listing on another exchange is the same instrument.
    assert _ident("SUZLON", date(2026, 9, 1)).resolved
    gate = dg.apply_identity(_actionable(), foo, price_symbol="BARCO.NS")
    assert gate.status == "abstain"
    assert gate.reasons[0].startswith("identity unresolved: learned mapping FOOCO -> BARCO.NS")


def test_price_history_for_another_symbol_abstains(registry, resolver):
    registry(RENAME)
    ident = _ident("OLDCO", date(2026, 3, 4))                  # resolved, NEWCO.NS
    gate = dg.apply_identity(_actionable(), ident, price_symbol="OLDCO.NS")
    assert gate.status == "abstain"
    assert gate.reasons == ["identity: price history came from OLDCO.NS, not NEWCO.NS, "
                            "the instrument OLDCO resolves to"]
    assert gate.identity == {"ticker": "OLDCO", "symbol": "NEWCO.NS", "basis": "OLDCO",
                             "status": "resolved", "source": "registry"}
    # The control: the same identity with its own prices passes untouched.
    ok = dg.apply_identity(_actionable(), ident, price_symbol="NEWCO.NS")
    assert (ok.status, ok.reasons) == ("actionable", [])
    assert ok.identity["symbol"] == "NEWCO.NS"


def test_identity_reasons_lead_and_a_data_abstention_keeps_its_own(registry, resolver):
    registry(SHIPPED)
    tata = _ident("TATAMOTORS", date(2026, 9, 29))
    data_abstain = DecisionGate(status="abstain", run_id="r", reasons=["essential technicals=empty"])
    gate = dg.apply_identity(data_abstain, tata)
    assert gate.reasons[0].startswith("identity unresolved:")
    assert gate.reasons[-1] == "essential technicals=empty"
    degraded = DecisionGate(status="degraded", run_id="r", reasons=["section news=empty"])
    gate = dg.apply_identity(degraded, tata)
    assert gate.status == "abstain" and len(gate.reasons) == 1   # degradation notes are not blockers


def test_the_close_fallbacks_ask_for_the_resolved_instrument(registry, resolver, monkeypatch):
    """TATAMOTORS is fetched from TMPV.NS; its BSE fallback used to ask for
    TATAMOTORS.BO, another listing's data, and the legacy fetcher could
    self-heal to anything."""
    import core.intelligence.rl.workflows.daily_review as dr
    from services.data.fetchers import close_verifier
    registry(SHIPPED)
    asked: list[str] = []
    monkeypatch.setattr("yfinance.download",
                        lambda sym, *a, **k: asked.append(sym) or pd.DataFrame())
    monkeypatch.setattr(dr, "get_price_history",
                        lambda sym, years=1: asked.append(f"history:{sym}") or pd.DataFrame())
    monkeypatch.setattr(close_verifier, "_fetch_nse_session", lambda t, d=None: (None, None))
    dr._fetch_session_close("TATAMOTORS", date(2026, 9, 28))
    assert asked == ["TMPV.NS", "TMPV.BO", "history:TMPV.NS"]


def test_an_nse_close_cached_under_another_code_is_not_served(registry, resolver, monkeypatch):
    from services.data.fetchers import close_verifier as cv
    registry(SHIPPED)
    d = date(2026, 9, 28)
    monkeypatch.setattr(cv, "_today_key", lambda: "k")
    monkeypatch.setitem(cv._NSE_CLOSE_CACHE, "k", {
        f"TVSMOTORS:{d.isoformat()}": (999.0, d),        # not an NSE code: another answer
        f"TVSMOTOR:{d.isoformat()}": (100.0, d),         # the listed security
    })
    assert sr.nse_symbol("TVSMOTORS", d) == "TVSMOTOR"
    assert cv._fetch_nse_session("TVSMOTORS", d) == (100.0, d)
    # An unregistered ticker keeps the bare code, the verifier's independent check.
    assert sr.nse_symbol("MARUTI", d) == "MARUTI"


def test_the_technicals_section_names_the_symbol_it_priced(registry, resolver, monkeypatch):
    from core.intelligence.algorithms.indicators import fetcher
    registry(SHIPPED)
    monkeypatch.setattr(fetcher.yf, "download", lambda sym, **k: _bars(date.today()))
    monkeypatch.setattr(fetcher, "get_peer_correlation",
                        lambda t, index: {"benchmark": index, "correlation": 0.5, "beta": 1.0,
                                          "sessions": 200})
    res = fetcher.get_technical_result("TATAMOTORS", sector="automobile")
    assert res.provenance()["symbol"] == "TMPV.NS"

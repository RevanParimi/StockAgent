"""SA-008 — an unresolved symbol cannot generate new-risk advice.

End to end through the REAL orchestrator, bundle builder, aggregator,
month-start forecast, advisor pipeline and autopilot (providers and LLM calls
stubbed by the SA-002/SA-003 fixtures), with the SHIPPED instrument registry.
TATAMOTORS is the audit's case: its providers are healthy (TMPV's data) and
the analyst scores 9 of 9, but which economic entity the ticker names is not
recorded, so its identity is unresolved.

- enforce: the report reads INSUFFICIENT DATA and names the identity; no
  envelope is built; the small TATAMOTORS holding is held (note IDENTITY);
  no transaction buys it. The same chain with a registry that does not list
  TATAMOTORS still buys (SA-003's control, which this suite also keeps).
- record: nothing changes (the verdict, the envelope, the ADD and the BUY
  all happen), and every artifact says what enforcement would do. The
  envelope's rows carry the instrument they priced.
- Price history fetched for another symbol than the identity names abstains,
  through the same chain: cached data for another instrument cannot satisfy
  the gate.
"""
from __future__ import annotations

import textwrap
from datetime import date
from pathlib import Path
from unittest.mock import patch

import pytest

import backend.shared.data.fetchers.symbol_resolver as sr
from core.intelligence.rl.stores.prediction_store import PredictionStore
from tests.unit.shared.test_decision_gate_sa003 import (  # noqa: F401 — fixtures
    _analyse,
    _gate_rows,
    fresh_db,
    gate_mode,
    market,
    no_network,
)
from tests.unit.test_decision_gate_portfolio_sa003 import TODAY, _buys, _chain

SHIPPED = Path(__file__).resolve().parents[2] / "config" / "instruments.yaml"
# The real resolver, bound before the SA-002 `market` fixture replaces it with
# the naive "{TICKER}.NS" for the data-health suites.
_REAL_RESOLVE = sr.resolve_yf_symbol

TATA_STAMP = {"ticker": "TATAMOTORS", "symbol": "TMPV.NS", "basis": "TMPV",
              "status": "unresolved", "source": "registry"}


@pytest.fixture
def shipped_registry(monkeypatch):
    monkeypatch.setenv("INSTRUMENT_REGISTRY_PATH", str(SHIPPED))


def _identity_reasons(reasons):
    return [r for r in reasons if r.startswith("identity")]


def test_enforce_withholds_an_unresolved_identity_with_healthy_data(
        market, fresh_db, monkeypatch, tmp_path, gate_mode, no_network, shipped_registry):
    gate_mode("enforce")
    with patch.object(sr, "resolve_yf_symbol", _REAL_RESOLVE):
        report = _analyse(market, monkeypatch, tmp_path)

    gate = report.decision_gate
    assert report.verdict == "INSUFFICIENT DATA"
    assert gate.status == "abstain" and gate.enforced and gate.withheld_verdict == "STRONG BUY"
    assert gate.essential_unusable == {}                  # the data itself was fine
    assert gate.identity == TATA_STAMP
    [reason] = gate.reasons
    assert reason.startswith("identity unresolved: retired by the owner's decision of 2026-09-29")
    assert "Still priced from TMPV.NS" in reason
    [row] = _gate_rows(tmp_path)
    assert (row["consumer"], row["ticker"], row["enforced"]) == ("analysis", "TATAMOTORS", True)
    assert row["reasons"] == gate.reasons and row["source_run_id"] == gate.run_id
    assert no_network == []


def test_record_mode_changes_nothing_and_says_what_enforce_would_do(
        market, fresh_db, monkeypatch, tmp_path, gate_mode, no_network, shipped_registry):
    gate_mode("record")
    with patch.object(sr, "resolve_yf_symbol", _REAL_RESOLVE):
        report = _analyse(market, monkeypatch, tmp_path)
    assert report.verdict == "STRONG BUY"
    assert report.decision_gate.status == "abstain" and not report.decision_gate.enforced
    assert report.decision_gate.identity == TATA_STAMP
    [row] = _gate_rows(tmp_path)
    assert row["enforced"] is False and _identity_reasons(row["reasons"])
    assert no_network == []


RESOLVED_RENAME = """
version: 1
instruments:
  TATAMOTORS:
    segments:
      - {status: active, symbol: TMPV.NS, basis: TMPV, via: rename,
         evidence: [{source: test fixture, ref: "fixture-1", date: 2026-01-05}]}
"""


def test_price_history_for_another_instrument_cannot_satisfy_the_gate(
        market, fresh_db, monkeypatch, tmp_path, gate_mode, no_network):
    """The identity is resolved (TATAMOTORS -> TMPV.NS, with evidence), but the
    run's price history came from TATAMOTORS.NS: the SA-002 fixture's naive
    resolver stands in for any stale or cached mapping to another code."""
    path = tmp_path / "instruments.yaml"
    path.write_text(textwrap.dedent(RESOLVED_RENAME), encoding="utf-8")
    monkeypatch.setenv("INSTRUMENT_REGISTRY_PATH", str(path))
    gate_mode("enforce")

    report = _analyse(market, monkeypatch, tmp_path)           # fixture resolver: TATAMOTORS.NS

    assert report.verdict == "INSUFFICIENT DATA"
    assert report.decision_gate.reasons == [
        "identity: price history came from TATAMOTORS.NS, not TMPV.NS, "
        "the instrument TATAMOTORS resolves to"]
    assert no_network == []


def test_the_same_resolved_identity_with_its_own_prices_is_actionable(
        market, fresh_db, monkeypatch, tmp_path, gate_mode, no_network):
    """The control: a resolved identity priced from its own symbol passes."""
    path = tmp_path / "instruments.yaml"
    path.write_text(textwrap.dedent(RESOLVED_RENAME), encoding="utf-8")
    monkeypatch.setenv("INSTRUMENT_REGISTRY_PATH", str(path))
    gate_mode("enforce")
    with patch.object(sr, "resolve_yf_symbol", _REAL_RESOLVE):
        report = _analyse(market, monkeypatch, tmp_path)
    assert report.decision_gate.status == "actionable", report.decision_gate.reasons
    assert report.decision_gate.identity["symbol"] == "TMPV.NS"
    assert report.verdict == "STRONG BUY"
    assert no_network == []


# ---------------------------------------------------------------------------
# The whole chain: verdict -> forecast -> advice -> executor
# ---------------------------------------------------------------------------

def test_enforce_an_unresolved_symbol_produces_no_new_risk(
        market, fresh_db, monkeypatch, tmp_path, gate_mode, no_network, shipped_registry):
    gate_mode("enforce")
    with patch.object(sr, "resolve_yf_symbol", _REAL_RESOLVE):
        report, forecast_error, advice, txns = _chain(market, monkeypatch, tmp_path)

    assert report.verdict == "INSUFFICIENT DATA"
    assert isinstance(forecast_error, Exception)               # no envelope to learn from
    tata = advice["TATAMOTORS"]
    assert tata.verdict == "HOLD" and tata.notes == ["IDENTITY"]
    assert tata.data_gate["identity"].startswith("TATAMOTORS identity unresolved")
    assert tata.instrument == TATA_STAMP
    assert _buys(txns) == []
    assert advice["BIGCO"].data_gate is None                   # an unlisted ticker is unaffected
    consumers = [r["consumer"] for r in _gate_rows(tmp_path)]
    assert consumers == ["analysis", "forecast"]
    assert no_network == []


def test_record_mode_the_chain_still_buys_and_every_artifact_names_the_identity(
        market, fresh_db, monkeypatch, tmp_path, gate_mode, no_network, shipped_registry):
    gate_mode("record")
    with patch.object(sr, "resolve_yf_symbol", _REAL_RESOLVE):
        report, forecast_error, advice, txns = _chain(market, monkeypatch, tmp_path)

    assert report.verdict == "STRONG BUY" and forecast_error is None
    tata = advice["TATAMOTORS"]
    assert tata.verdict == "ADD"                               # unchanged in record mode
    assert tata.data_gate["enforced"] is False
    assert tata.data_gate["gated_verdict"] == "HOLD" and tata.data_gate["blocked"] == "ADD"
    assert tata.data_gate["reasons"][0].startswith("identity: TATAMOTORS identity unresolved")
    assert _buys(txns) == [("TATAMOTORS", 2.0)]
    # The envelope, every row and the advice name the instrument they priced.
    store = PredictionStore("TATAMOTORS", sector="automobile",
                            base_dir=str(tmp_path / "predictions"))
    env = store.load_envelope(store.cycle_id_for(TODAY))
    assert env.instrument == TATA_STAMP
    assert env.daily_forecasts and all(r.instrument == TATA_STAMP for r in env.daily_forecasts)
    assert tata.instrument == TATA_STAMP
    assert advice["BIGCO"].instrument == {"ticker": "BIGCO", "symbol": "BIGCO.NS",
                                          "basis": "BIGCO", "status": "resolved",
                                          "source": "default"}

    # Later the owner records a different identity. History keeps the original.
    later = tmp_path / "instruments_later.yaml"
    later.write_text(textwrap.dedent(RESOLVED_RENAME).replace("basis: TMPV", "basis: TMCV")
                     .replace("TMPV.NS", "TMCV.NS"), encoding="utf-8")
    monkeypatch.setenv("INSTRUMENT_REGISTRY_PATH", str(later))
    assert sr.resolve_identity("TATAMOTORS", TODAY).basis == "TMCV"
    env = store.load_envelope(store.cycle_id_for(TODAY))
    assert env.instrument == TATA_STAMP and all(r.instrument == TATA_STAMP
                                                for r in env.daily_forecasts)
    from core.portfolio.store import PortfolioStore
    stored = {a.symbol: a for a in PortfolioStore(
        user_id="u", base_dir=str(tmp_path / "portfolio")).load_advice()}
    assert stored["TATAMOTORS"].instrument == TATA_STAMP
    assert no_network == []


def test_an_unlisted_ticker_still_buys_in_enforce(
        market, fresh_db, monkeypatch, tmp_path, gate_mode, no_network):
    """The control, with the suite's empty registry: TATAMOTORS is its own
    listing (TATAMOTORS.NS), resolved, so enforcement stops nothing."""
    gate_mode("enforce")
    report, forecast_error, advice, txns = _chain(market, monkeypatch, tmp_path)
    assert report.decision_gate.status == "actionable"
    assert report.decision_gate.identity["status"] == "resolved"
    assert advice["TATAMOTORS"].verdict == "ADD"
    assert _buys(txns) == [("TATAMOTORS", 2.0)]
    assert no_network == []

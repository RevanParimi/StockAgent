"""SA-003 — the decision gate: analysis acts only on essential data.

Independent invariants, not echoes of the implementation:

- The audit's cases (F08): BUY on 1 of 6 and 2 of 6 scored dimensions and
  STRONG BUY on 3 of 9 must abstain. Expected statuses are written by hand
  from the rule in config.yaml (essential sections ok/cache_hit, at least half
  the dimensions scored), never computed by the code under test.
- Live-section counts are not the criterion: 3 live of 9 abstains when the
  three are news/macro/dossier, and is actionable-but-degraded when they are
  the three essential sections.
- End to end through the REAL orchestrator, bundle builder and aggregator
  (providers patched): TATAMOTORS' price source answers 404 while every
  other provider answers and the analyst scores 9 of 9. In enforce mode the
  report reads INSUFFICIENT DATA and keeps the withheld verdict; in record
  mode the verdict stands and the gate says what enforcement would do. The
  same run with healthy providers stays actionable, so the gate is not a
  rule that never passes.
- The gate does not depend on the data-health row being recorded.
- Every abstention is recorded with its reasons and the source run id.
"""
from __future__ import annotations

import json
import logging
import socket
from datetime import date
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from backend.shared.pipeline import decision_gate as dg
from backend.shared.pipeline.unified_analyst import DIMENSIONS
from core.schemas.pipeline import AgentOutput, DecisionGate, FinalReport
from services.data.context import fetch_result as fr
from services.data.context.bundle_builder import SECTION_ORDER
from tests.unit.shared.test_data_health_contract import (  # noqa: F401 — fixtures
    _AutoOrchestrator,
    _query,
    fresh_db,
    market,
)

ESSENTIAL = ("fundamentals", "technicals", "peers_valuation")
NINE = DIMENSIONS["automobile"]


@pytest.fixture
def gate_mode(monkeypatch):
    """Set decision_gate.mode for one test; clears the once-per-value warning memo."""
    from core.config import settings
    dg._warned.clear()

    def _set(value):
        monkeypatch.setattr(settings, "DECISION_GATE_MODE", value)
    return _set


@pytest.fixture
def no_network(monkeypatch):
    """Record (and refuse) every outbound connect / DNS lookup."""
    attempts: list = []
    real_connect = socket.socket.connect

    def _connect(self, address, *a, **k):
        host = address[0] if isinstance(address, tuple) else address
        if str(host).startswith("127.") or str(host) in ("::1", "localhost"):
            return real_connect(self, address)
        attempts.append(("connect", address))
        raise OSError("network blocked in SA-003 tests")

    def _getaddrinfo(host, *a, **k):
        attempts.append(("dns", host))
        raise socket.gaierror("network blocked in SA-003 tests")

    monkeypatch.setattr(socket.socket, "connect", _connect)
    monkeypatch.setattr(socket, "getaddrinfo", _getaddrinfo)
    return attempts


def _gate_rows(tmp_path) -> list[dict]:
    path = tmp_path / "decision_gate.jsonl"      # tests/conftest.py redirects here
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


# ---------------------------------------------------------------------------
# The switch
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("raw, expected", [
    ("record", "record"), ("enforce", "enforce"), (" Enforce ", "enforce"), ("RECORD", "record"),
])
def test_recognised_values(gate_mode, raw, expected):
    gate_mode(raw)
    assert dg.gate_mode() == expected


@pytest.mark.parametrize("raw", ["off", "", "enforcing", None, 1])
def test_unrecognised_value_fails_closed_to_enforce_with_warning(gate_mode, caplog, raw):
    gate_mode(raw)
    with caplog.at_level(logging.WARNING, logger="backend.shared.pipeline.decision_gate"):
        mode, reason = dg.gate_mode_state()
    assert mode == "enforce"
    assert "failed closed" in reason
    assert any("failing closed" in r.getMessage() for r in caplog.records)


def test_shipped_default_is_record():
    """The implementation ships recording only; enforcing is a separate decision.

    Reads the checked-in file itself: tests/unit/shared/test_config_loader.py
    reloads the shared loader against a throwaway YAML and leaves it there,
    so `cfg()` later in a full run does not describe config.yaml."""
    from pathlib import Path

    import yaml
    shipped = yaml.safe_load(
        (Path(__file__).resolve().parents[3] / "config.yaml").read_text(encoding="utf-8"))
    assert shipped["decision_gate"] == {"mode": "record", "min_dimensions_fraction": 0.5}


# ---------------------------------------------------------------------------
# The rule, on hand-written cases
# ---------------------------------------------------------------------------

def _sections(live: set[str], dead_status: str = fr.STATUS_EMPTY,
              not_applicable: set[str] = frozenset()) -> dict[str, str]:
    return {n: (fr.STATUS_NOT_APPLICABLE if n in not_applicable
                else fr.STATUS_OK if n in live else dead_status)
            for n in SECTION_ORDER}


def _gate(sections, scored: int, expected: int) -> DecisionGate:
    dims = [f"d{i}" for i in range(expected)]
    return dg.assess_analysis(run_id="r1", section_status=sections,
                              dimensions_expected=dims,
                              dimensions_missing=dims[scored:])


ALL_LIVE = set(SECTION_ORDER)


@pytest.mark.parametrize("scored, expected, status", [
    # The audit's actionable-on-partial-data cases (F08): all must abstain.
    (1, 6, "abstain"), (2, 6, "abstain"), (3, 9, "abstain"),
    # Boundaries of "at least half": 3/6 = 50% may act (degraded, one short
    # of complete); 4/9 = 44% may not; 5/9 = 56% may.
    (3, 6, "degraded"), (4, 9, "abstain"), (5, 9, "degraded"),
    # Complete.
    (6, 6, "actionable"), (9, 9, "actionable"),
    # Nothing scored.
    (0, 9, "abstain"),
])
def test_dimension_coverage(scored, expected, status):
    gate = _gate(_sections(ALL_LIVE), scored, expected)
    assert gate.status == status, gate.reasons
    if status == "abstain":
        assert any(f"dimensions scored {scored}/{expected}" in r for r in gate.reasons)
    assert (gate.dimensions_scored, gate.dimensions_expected) == (scored, expected)


@pytest.mark.parametrize("section", ESSENTIAL)
@pytest.mark.parametrize("dead", [fr.STATUS_EMPTY, fr.STATUS_STALE, fr.STATUS_FALLBACK,
                                  fr.STATUS_UNVERIFIED, "failed:HTTPError"])
def test_any_unusable_essential_section_abstains(section, dead):
    sections = _sections(ALL_LIVE)
    sections[section] = dead
    gate = _gate(sections, 9, 9)
    assert gate.status == "abstain"
    assert gate.essential_unusable == {section: dead}
    assert f"essential {section}={dead}" in gate.reasons


def test_cache_hit_is_usable_evidence():
    sections = _sections(ALL_LIVE)
    sections["technicals"] = fr.STATUS_CACHE_HIT
    assert _gate(sections, 9, 9).status == "actionable"


@pytest.mark.parametrize("live, applicable, expected", [
    # 1 of 6 applicable sections live (4 deliberately n/a): only technicals.
    ({"technicals"}, 6, "abstain"),
    # 2 of 6: technicals and fundamentals, but no peers valuation.
    ({"technicals", "fundamentals"}, 6, "abstain"),
    # 3 of 9 live, none of them essential.
    ({"company_news", "macro_context", "dossier"}, 9, "abstain"),
    # 3 of 9 live, exactly the essential three: ordinary enrichment is
    # missing, the core evidence is not — actionable, flagged degraded.
    (set(ESSENTIAL), 9, "degraded"),
    (ALL_LIVE, 10, "actionable"),
])
def test_live_section_counts_are_not_the_criterion(live, applicable, expected):
    # Keep the essential sections applicable; mark the rest n/a from the end.
    optional = [n for n in SECTION_ORDER if n not in ESSENTIAL and n not in live]
    n_a = set(optional[:len(SECTION_ORDER) - applicable])
    sections = _sections(set(live), not_applicable=n_a)
    assert sum(1 for s in sections.values() if s != fr.STATUS_NOT_APPLICABLE) == applicable
    assert sum(1 for s in sections.values() if s == fr.STATUS_OK) == len(live)
    assert _gate(sections, 9, 9).status == expected


def test_an_unreached_essential_section_abstains():
    gate = _gate({}, 9, 9)
    assert gate.status == "abstain"
    assert set(gate.essential_unusable) == set(ESSENTIAL)


def test_a_v1_health_row_abstains():
    """B2's rows said `ok` when the fetcher merely did not raise (SA-002)."""
    v1 = {"run_id": "old", "health": "ok", "dimensions_scored": 9, "dimensions_expected": 9,
          "sections": {n: "ok" for n in SECTION_ORDER}}
    gate = dg.gate_from_health_row(v1)
    assert gate.status == "abstain" and gate.run_id == "old"
    assert "provenance" in gate.reasons[0]


@pytest.mark.parametrize("status, may_act", [
    ("actionable", True), ("degraded", True), ("abstain", False), ("", False), (None, False),
])
def test_only_actionable_and_degraded_may_act(status, may_act):
    assert dg.is_actionable(status) is may_act


# ---------------------------------------------------------------------------
# End to end: providers -> real bundle -> real aggregator -> the report
# ---------------------------------------------------------------------------

def _analyse(market, monkeypatch, tmp_path, *, llm_verdict="STRONG BUY", score=0.9,
             unified_outputs=None):
    """One real orchestrator.analyse() for TATAMOTORS: real bundle producers
    (under the SA-002 Market providers), real SignalAggregator (its LLM call
    stubbed to `llm_verdict`), analyst stubbed to score every dimension."""
    import backend.shared.pipeline.base_orchestrator as bo_mod
    import backend.shared.pipeline.signal_aggregator as sa_mod
    import services.data.stores.data_health as dh

    monkeypatch.setattr(dh, "DATA_HEALTH_LOG", tmp_path / "data_health.jsonl")
    monkeypatch.setattr(sa_mod.settings, "RL_HARD_BIND_VERDICT_ENABLED", False)
    for name in ("log_run_summary", "log_run_api_usage", "log_analysis"):
        monkeypatch.setattr(bo_mod, name, lambda *a, **k: None)
    monkeypatch.setattr(sa_mod, "log_llm_call", lambda *a, **k: None)
    monkeypatch.setattr("backend.shared.pipeline.verdict_shadow.log_verdict_shadow",
                        lambda *a, **k: None)

    with patch("backend.shared.pipeline.base_orchestrator.get_llm_client",
               return_value=MagicMock()), \
         patch("backend.shared.pipeline.signal_aggregator.get_llm_client",
               return_value=MagicMock()):
        orch = _AutoOrchestrator()
    orch.set_aggregator_weights({d: 1.0 / len(NINE) for d in NINE}, "TATAMOTORS")
    analyst = MagicMock()
    analyst.run.return_value = unified_outputs if unified_outputs is not None else {
        d: AgentOutput(agent=d, ticker="TATAMOTORS", overall_score=score) for d in NINE}
    analyst._last_prompt_tokens = analyst._last_completion_tokens = 0
    verdict_json = json.dumps({
        "final_score": score, "verdict": llm_verdict, "conviction_drivers": ["x"],
        "top_risks": [], "investment_thesis": "t", "executive_summary": "s"})

    with patch.object(orch, "_resolve_ticker", return_value=_query("TATAMOTORS")), \
         patch.object(orch, "_prefetch_nse_data"), \
         patch("backend.shared.pipeline.unified_analyst.UnifiedAnalyst", return_value=analyst), \
         patch.object(sa_mod.SignalAggregator, "_call_llm", return_value=verdict_json):
        return orch.analyse("TATAMOTORS")


def _price_source_404(market):
    market.bars_last["TATAMOTORS"] = None
    market.statement["TATAMOTORS"] = pd.DataFrame()
    market.info["TATAMOTORS"] = {}


def test_enforce_withholds_the_verdict_of_the_tatamotors_404_run(
        market, fresh_db, monkeypatch, tmp_path, gate_mode, no_network):
    _price_source_404(market)
    gate_mode("enforce")

    report = _analyse(market, monkeypatch, tmp_path)

    gate = report.decision_gate
    assert report.verdict == "INSUFFICIENT DATA"
    assert gate.status == "abstain" and gate.enforced is True and gate.mode == "enforce"
    assert gate.withheld_verdict == "STRONG BUY"
    assert set(gate.essential_unusable) == set(ESSENTIAL)
    assert gate.dimensions_scored == 9                     # the analyst still scored 9/9
    # The public payload (what /analyse and /ws/stream return) carries it.
    payload = report.model_dump()
    assert payload["verdict"] == "INSUFFICIENT DATA"
    assert payload["decision_gate"]["run_id"] == gate.run_id != ""
    # The health row and the gate agree on what was unusable.
    assert set(payload["data_health"]["essential_unusable"]) == set(ESSENTIAL)
    # Recorded, with its reasons and the source run id.
    rows = _gate_rows(tmp_path)
    assert len(rows) == 1
    assert rows[0]["consumer"] == "analysis" and rows[0]["ticker"] == "TATAMOTORS"
    assert rows[0]["source_run_id"] == gate.run_id
    assert rows[0]["enforced"] is True
    assert {f"essential {n}" for n in ESSENTIAL} <= {r.split("=")[0] for r in rows[0]["reasons"]}
    assert no_network == []


def test_record_mode_keeps_the_verdict_and_says_what_enforce_would_do(
        market, fresh_db, monkeypatch, tmp_path, gate_mode, no_network):
    _price_source_404(market)
    gate_mode("record")

    report = _analyse(market, monkeypatch, tmp_path)

    assert report.verdict == "STRONG BUY"                   # unchanged
    assert report.decision_gate.status == "abstain"
    assert report.decision_gate.enforced is False
    assert report.decision_gate.withheld_verdict is None
    rows = _gate_rows(tmp_path)
    assert len(rows) == 1 and rows[0]["enforced"] is False and rows[0]["mode"] == "record"
    assert no_network == []


def test_the_same_run_with_healthy_providers_is_actionable(
        market, fresh_db, monkeypatch, tmp_path, gate_mode, no_network):
    """The control: enforcement does not touch a run with its evidence."""
    gate_mode("enforce")
    report = _analyse(market, monkeypatch, tmp_path)
    assert report.decision_gate.status == "actionable", report.decision_gate.reasons
    assert report.verdict == "STRONG BUY"
    assert _gate_rows(tmp_path) == []
    assert no_network == []


def test_one_dimension_of_nine_withholds_a_strong_buy(
        market, fresh_db, monkeypatch, tmp_path, gate_mode, no_network):
    """Healthy data, but the analyst answered for one dimension only: the
    composite would be that one dimension's score."""
    outputs = {d: AgentOutput(agent=d, ticker="TATAMOTORS", overall_score=0.95,
                              error=None if i == 0 else "missing from unified response")
               for i, d in enumerate(NINE)}
    gate_mode("enforce")
    report = _analyse(market, monkeypatch, tmp_path, unified_outputs=outputs)
    assert report.verdict == "INSUFFICIENT DATA"
    assert "dimensions scored 1/9 < 50%" in report.decision_gate.reasons


def test_the_gate_does_not_depend_on_the_health_row(
        market, fresh_db, monkeypatch, tmp_path, gate_mode, no_network):
    """observability.data_health_enabled is the ROW's rollback line only."""
    import services.data.stores.data_health as dh
    monkeypatch.setattr(dh, "data_health_enabled", lambda: False)
    _price_source_404(market)
    gate_mode("enforce")

    report = _analyse(market, monkeypatch, tmp_path)

    assert report.data_health is None
    assert report.verdict == "INSUFFICIENT DATA"
    assert set(report.decision_gate.essential_unusable) == set(ESSENTIAL)


def test_an_unresolved_symbol_abstains(market, fresh_db, monkeypatch, tmp_path, gate_mode,
                                       no_network):
    """Identity, minimum: ticker resolution fails, the orchestrator falls back
    to the raw input, and no provider knows that symbol. Nothing about it is
    verified, so nothing may act on it. (Lifecycle identity — renames,
    demergers, successors — is SA-008.)"""
    import backend.shared.pipeline.base_orchestrator as bo_mod
    import backend.shared.pipeline.signal_aggregator as sa_mod
    import services.data.stores.data_health as dh
    for sym in ("NOSUCHCO",):
        market.bars_last[sym] = None
        market.statement[sym] = pd.DataFrame()
        market.info[sym] = {}
    monkeypatch.setattr(dh, "DATA_HEALTH_LOG", tmp_path / "data_health.jsonl")
    monkeypatch.setattr(sa_mod.settings, "RL_HARD_BIND_VERDICT_ENABLED", False)
    for name in ("log_run_summary", "log_run_api_usage", "log_analysis"):
        monkeypatch.setattr(bo_mod, name, lambda *a, **k: None)
    monkeypatch.setattr(sa_mod, "log_llm_call", lambda *a, **k: None)
    monkeypatch.setattr("backend.shared.pipeline.verdict_shadow.log_verdict_shadow",
                        lambda *a, **k: None)
    gate_mode("enforce")
    llm = MagicMock()
    llm.chat.completions.create.side_effect = RuntimeError("resolver down")
    with patch.object(bo_mod, "get_llm_client", return_value=llm), \
         patch.object(sa_mod, "get_llm_client", return_value=MagicMock()):
        orch = _AutoOrchestrator()
    orch.set_aggregator_weights({d: 1.0 / len(NINE) for d in NINE}, "NOSUCHCO")
    analyst = MagicMock()
    analyst.run.return_value = {d: AgentOutput(agent=d, ticker="NOSUCHCO", overall_score=0.9)
                                for d in NINE}
    analyst._last_prompt_tokens = analyst._last_completion_tokens = 0
    with patch.object(orch, "_managed_tickers", return_value=set()), \
         patch.object(orch, "_prefetch_nse_data"), \
         patch("backend.shared.pipeline.unified_analyst.UnifiedAnalyst", return_value=analyst), \
         patch.object(sa_mod.SignalAggregator, "_call_llm", return_value=json.dumps(
             {"final_score": 0.9, "verdict": "BUY", "conviction_drivers": []})):
        report = orch.analyse("nosuchco")

    assert report.ticker == "NOSUCHCO"                       # the unresolved fallback
    assert report.verdict == "INSUFFICIENT DATA"
    assert set(report.decision_gate.essential_unusable) == set(ESSENTIAL)
    assert no_network == []


def test_a_run_without_a_bundle_abstains(monkeypatch, gate_mode):
    """The legacy worker-pool path builds no bundle: nothing to verify."""
    import backend.shared.pipeline.base_orchestrator as bo_mod
    gate_mode("enforce")
    with patch.object(bo_mod, "get_llm_client", return_value=MagicMock()):
        orch = _AutoOrchestrator()
    orch._last_gate_inputs = None
    report = FinalReport(ticker="X", company_name="X", final_score=0.8, verdict="BUY",
                         weighted_agent_scores={})
    orch._apply_decision_gate(report, "X", "legacy-run")
    assert report.verdict == "INSUFFICIENT DATA"
    assert report.decision_gate.run_id == "legacy-run"
    assert "legacy worker pool" in report.decision_gate.reasons[0]


def test_a_failing_gate_abstains_rather_than_passes(monkeypatch, gate_mode):
    import backend.shared.pipeline.base_orchestrator as bo_mod
    gate_mode("enforce")
    with patch.object(bo_mod, "get_llm_client", return_value=MagicMock()):
        orch = _AutoOrchestrator()
    orch._last_gate_inputs = {"section_status": {}, "section_provenance": None,
                              "dimensions_expected": ["a"], "dimensions_missing": []}
    monkeypatch.setattr(dg, "assess_analysis",
                        lambda **k: (_ for _ in ()).throw(RuntimeError("boom")))
    report = FinalReport(ticker="X", company_name="X", final_score=0.8, verdict="BUY",
                         weighted_agent_scores={})
    orch._apply_decision_gate(report, "X", "r")
    assert report.verdict == "INSUFFICIENT DATA"
    assert "RuntimeError" in report.decision_gate.reasons[0]


# ---------------------------------------------------------------------------
# Discovery: an abstained deep dive never becomes a shelf idea (a SWITCH buy)
# ---------------------------------------------------------------------------

def _gated_report(status: str) -> FinalReport:
    return FinalReport(ticker="NEWCO", company_name="NEWCO", final_score=0.9, verdict="BUY",
                       weighted_agent_scores={},
                       decision_gate=DecisionGate(status=status, run_id="dive-run",
                                                  reasons=["essential technicals=empty"]))


@pytest.mark.parametrize("mode, status, shelved", [
    ("enforce", "abstain", False), ("enforce", "actionable", True),
    ("record", "abstain", True),
])
def test_deep_dive_gate(monkeypatch, tmp_path, gate_mode, mode, status, shelved):
    import core.discovery.deep_dive as dd
    from backend.shared.schemas.discovery import DiscoveryCandidate, Shelf
    from tests.unit.test_discovery_deep_dive import _window

    gate_mode(mode)
    monkeypatch.setattr(dd, "load_managed_tickers", lambda: [])
    monkeypatch.setattr(dd, "ShelfStore", lambda: type("S", (), {"load": lambda self: Shelf()})())
    monkeypatch.setattr(dd, "EodStore", lambda: type(
        "E", (), {"load_window": lambda self, end, sessions: _window()})())
    monkeypatch.setattr(dd, "infer_sector", lambda s: "pharma")
    monkeypatch.setattr(dd, "get_orchestrator", lambda sector: type(
        "O", (), {"analyse": lambda self, t: _gated_report(status)})())

    results = dd.run_deep_dives([DiscoveryCandidate(symbol="NEWCO", close=100.0, composite=0.9)],
                                on=date(2026, 7, 4), max_n=1)

    assert [r.symbol for r in results] == (["NEWCO"] if shelved else [])
    if shelved:
        assert results[0].data_gate == status          # carried onto the shelf idea
    rows = _gate_rows(tmp_path)
    if status == "abstain":
        assert len(rows) == 1 and rows[0]["consumer"] == "discovery"
        assert rows[0]["source_run_id"] == "dive-run"
        assert rows[0]["enforced"] is (mode == "enforce")
    else:
        assert rows == []

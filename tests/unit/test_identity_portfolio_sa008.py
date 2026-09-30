"""SA-008 — positions keep their identity and price basis, and an operator
reconciles corporate actions explicitly.

The fixture, in numbers written by hand: a user bought 100 PARENT at
₹1,000 (cost ₹1,00,000) on 4 May 2026. PARENT demerged on 15 Jun into
PARENTA (continuing, 60% of the cost) and PARENTB (40%), one share each per
PARENT share. After the event the ticker trades as PARENTA at ₹600.

- Unreconciled, the close is on another basis: 600 vs 1,000 reads -40%, a
  stop breach, and the ungated advisor says EXIT — a sale on a loss that
  never happened (the corp-action invariant). The identity hold makes it
  HOLD (note IDENTITY) in enforce, and record mode keeps EXIT but says so.
  A rename keeps the basis, so its holding is not held (the control).
- A SWITCH destination or an autopilot buy leg whose identity is unresolved
  is refused in enforce.
- The reconciliation: `plan` is read-only and proposes PARENTA 100 @ ₹600
  (₹60,000) and PARENTB 100 @ ₹400 (₹40,000) — cost is conserved. `apply`
  needs the plan's digest, refuses a stale plan and a second run, backs the
  file up, and afterwards the advisor judges PARENTA against ₹600, and the
  ledger reconciler treats the successors as unverifiable, not as drift.
"""
from __future__ import annotations

import json
import textwrap
from datetime import date, timedelta
from pathlib import Path

import pytest

from backend.shared.schemas.discovery import ShelfIdea
from backend.shared.schemas.portfolio import AdviceRecord, Holding, TransactionRecord
from core.portfolio import identity_reconcile as ir
from core.portfolio.advisor import AdvisorSignals, decide
from core.portfolio.pricing import SessionClose
from core.portfolio.reconcile import reconcile
from core.portfolio.store import PortfolioStore
from tests.unit.test_decision_gate_portfolio_sa003 import gate_mode  # noqa: F401 — fixture

SHIPPED = Path(__file__).resolve().parents[2] / "config" / "instruments.yaml"
ON = date(2026, 9, 28)
EVIDENCE = '[{source: "NSE circular", ref: "NSE/CML/2026/0002", date: 2026-06-01}]'

REGISTRY = f"""
version: 1
instruments:
  PARENT:
    segments:
      - {{until: 2026-06-15, status: active, symbol: PARENT.NS, basis: PARENT}}
      - {{from: 2026-06-15, status: active, symbol: PARENTA.NS, basis: PARENTA, via: demerger,
         evidence: {EVIDENCE},
         successors: [{{ticker: PARENTA, ratio: 1, cost_fraction: 0.6}},
                      {{ticker: PARENTB, ratio: 1, cost_fraction: 0.4}}]}}
  OLDCO:
    segments:
      - {{until: 2026-06-15, status: active, symbol: OLDCO.NS, basis: OLDCO}}
      - {{from: 2026-06-15, status: active, symbol: NEWCO.NS, basis: OLDCO, via: rename,
         evidence: {EVIDENCE}}}
  LIMBO:
    segments:
      - {{status: unresolved, symbol: LIMBO.NS, reason: "which entity this is is not recorded"}}
"""


@pytest.fixture(autouse=True)
def registry(tmp_path, monkeypatch):
    path = tmp_path / "instruments.yaml"
    path.write_text(textwrap.dedent(REGISTRY), encoding="utf-8")
    monkeypatch.setenv("INSTRUMENT_REGISTRY_PATH", str(path))
    return path


def _holding(symbol="PARENT", qty=100.0, price=1000.0, buy="2026-05-04", sector="automobile"):
    return Holding(symbol=symbol, sector=sector, qty=qty, avg_buy_price=price,
                   adj_avg_price=price, adj_qty=qty, buy_date=buy)


def _signals(holding: Holding, close: float, **over) -> AdvisorSignals:
    pnl = holding.unrealised_pnl_pct(close)
    base = dict(symbol=holding.symbol, sector=holding.sector, close=close, atr_stop_pct=8.0,
                unrealised_pnl_pct=pnl, holding_age_days=147, envelope_direction="FLAT",
                confidence=0.5, forecast_gate="actionable", forecast_run_ids=["m"],
                identity_issue=ir.holding_identity_issue(holding, ON))
    base.update(over)
    return AdvisorSignals(**base)


# ---------------------------------------------------------------------------
# The advisor: no verdict on another price basis
# ---------------------------------------------------------------------------

def test_the_demerged_parent_reads_as_a_false_forty_percent_loss():
    h = _holding()
    assert h.unrealised_pnl_pct(600.0) == pytest.approx(-40.0)        # 600 vs 1,000
    issue = ir.holding_identity_issue(h, ON)
    assert "price basis changed" in issue and "PARENTA" in issue
    ungated = decide(_signals(h, 600.0), h, "balanced")
    assert ungated.verdict == "EXIT" and "stop_breach" in ungated.triggers   # the false signal


def test_enforce_holds_the_unreconciled_holding(gate_mode):
    from core.portfolio.pipeline import gated_decide
    gate_mode("enforce")
    h = _holding()
    rec, _ = gated_decide(_signals(h, 600.0), h, "balanced", shelf_ideas=[], sector_weights={},
                          held_symbols={"PARENT"}, candidate_fresh={})
    assert (rec.verdict, rec.triggers, rec.notes) == ("HOLD", [], ["IDENTITY"])
    assert rec.data_gate["enforced"] is True and rec.data_gate["blocked"] == "EXIT"
    assert rec.data_gate["reasons"][0].startswith("identity: PARENT: price basis changed")


def test_record_mode_keeps_the_exit_and_says_it_would_hold(gate_mode):
    from core.portfolio.pipeline import gated_decide
    gate_mode("record")
    h = _holding()
    rec, _ = gated_decide(_signals(h, 600.0), h, "balanced", shelf_ideas=[], sector_weights={},
                          held_symbols={"PARENT"}, candidate_fresh={})
    assert rec.verdict == "EXIT"
    assert rec.data_gate["enforced"] is False and rec.data_gate["gated_verdict"] == "HOLD"


def test_a_renamed_holding_keeps_its_basis_and_its_stop(gate_mode):
    """The control: same company, new code. A real 12% fall still exits."""
    from core.portfolio.pipeline import gated_decide
    gate_mode("enforce")
    h = _holding("OLDCO", price=100.0)
    assert ir.holding_identity_issue(h, ON) == ""
    rec, _ = gated_decide(_signals(h, 88.0), h, "balanced", shelf_ideas=[], sector_weights={},
                          held_symbols={"OLDCO"}, candidate_fresh={})
    assert rec.verdict == "EXIT" and rec.data_gate is None


def test_an_unresolved_holding_is_held_whatever_the_signal(gate_mode):
    from core.portfolio.pipeline import gated_decide
    gate_mode("enforce")
    h = _holding("LIMBO", price=100.0)
    up = _signals(h, 100.0, envelope_direction="UP", direction_accuracy_7d=0.9,
                  position_weight_pct=1.0)
    assert decide(up.model_copy(update={"identity_issue": ""}), h, "balanced").verdict == "ADD"
    rec, _ = gated_decide(up, h, "balanced", shelf_ideas=[], sector_weights={},
                          held_symbols={"LIMBO"}, candidate_fresh={})
    assert rec.verdict == "HOLD" and rec.notes == ["IDENTITY"]
    assert "which entity this is is not recorded" in rec.data_gate["identity"]


def _idea(symbol, conviction):
    return ShelfIdea(symbol=symbol, sector="realty", added="2026-09-01",
                     conviction=conviction, data_gate="actionable")


def test_an_unresolved_switch_destination_is_refused(gate_mode):
    from core.portfolio.pipeline import gated_decide
    h = _holding("OLDCO", price=100.0)
    exiting = _signals(h, 88.0, confidence=0.3)
    ideas = [_idea("LIMBO", 0.95), _idea("GOODCO", 0.9)]
    weights = {"automobile": 60.0, "realty": 5.0}
    candidate_identity = {i.symbol: why for i in ideas
                          if (why := ir.symbol_identity_issue(i.symbol, ON))}
    assert set(candidate_identity) == {"LIMBO"}
    common = dict(shelf_ideas=ideas, sector_weights=weights, held_symbols={"OLDCO"},
                  candidate_fresh={}, candidate_identity=candidate_identity)

    gate_mode("record")
    rec, _ = gated_decide(exiting, h, "balanced", **common)
    assert (rec.verdict, rec.switch_candidate) == ("SWITCH", "LIMBO")
    assert rec.data_gate["blocked"] == "SWITCH buy leg LIMBO"
    gate_mode("enforce")
    rec, _ = gated_decide(exiting, h, "balanced", **common)
    assert (rec.verdict, rec.switch_candidate) == ("SWITCH", "GOODCO")


@pytest.mark.parametrize("mode, bought", [("enforce", False), ("record", True)])
def test_the_autopilot_never_buys_an_unresolved_destination(
        tmp_path, monkeypatch, gate_mode, mode, bought):
    import core.portfolio.autopilot as ap
    review = date(2026, 7, 13)                                   # a Monday
    monkeypatch.setattr(ap, "_today_ist", lambda: review)
    monkeypatch.setattr(ap, "promote_symbol", lambda *a, **k: {"status": "ok"})
    monkeypatch.setattr(ap, "session_close", lambda sym, d: (SessionClose(200.0, review, "agree"),
                                                              review))
    gate_mode(mode)
    s = PortfolioStore(user_id="t1", base_dir=str(tmp_path / "p"))
    p = s.load()
    p.holdings, p.cash_deployable, p.capital_in, p.autopilot = (
        [_holding("OLDCO", qty=10.0, price=100.0)], 20000.0, 100000.0, True)
    s.save(p)
    switch = AdviceRecord(date=review.isoformat(), user_id="t1", symbol="OLDCO", verdict="SWITCH",
                          close=88.0, unrealised_pnl_pct=-12.0, stop_pct=8.0, confidence=0.3,
                          switch_candidate="LIMBO", triggers=["stop_breach"], rationale_hash="sw")
    txns = ap.execute_advice(s, s.load(), [switch], {"OLDCO": 88.0}, review,
                             sector_lookup={"LIMBO": "realty"})
    sides = [(t.side, t.symbol) for t in txns]
    assert ("SELL", "OLDCO") in sides                            # the exit always executes
    assert (("BUY", "LIMBO") in sides) is bought


# ---------------------------------------------------------------------------
# The operator's reconciliation
# ---------------------------------------------------------------------------

def _user(tmp_path, holdings, user="u1"):
    base = tmp_path / "portfolio"
    s = PortfolioStore(user_id=user, base_dir=str(base))
    p = s.load()
    p.holdings, p.cash_deployable = holdings, 100000.0
    s.save(p)
    s.append_transaction(TransactionRecord(
        txn_id="t0", date="2026-05-04", ts="2026-05-04T10:00:00+00:00", user_id=user,
        symbol="PARENT", side="BUY", qty=100.0, price=1000.0, value=100000.0,
        cash_before=200000.0, cash_after=100000.0, holding_qty_after=100.0, source="manual"))
    return str(base), s


def test_plan_is_read_only_and_conserves_cost(tmp_path):
    base, s = _user(tmp_path, [_holding(), _holding("OLDCO", qty=5.0, price=100.0)])
    before = s._portfolio_path().read_bytes()

    doc = ir.plan(on=ON, base_dir=base)

    assert s._portfolio_path().read_bytes() == before
    [item] = doc["items"]                                        # the rename needs nothing
    assert (item["user_id"], item["symbol"], item["action"], item["kind"], item["effective"]) == \
        ("u1", "PARENT", "apply", "demerger", "2026-06-15")
    got = {x["ticker"]: (x["adj_qty"], x["adj_avg_price"], x["cost"]) for x in item["successors"]}
    assert got == {"PARENTA": (100.0, pytest.approx(600.0), pytest.approx(60000.0)),
                   "PARENTB": (100.0, pytest.approx(400.0), pytest.approx(40000.0))}
    assert sum(x["cost"] for x in item["successors"]) == pytest.approx(100000.0)
    assert len(doc["plan_digest"]) == 64


def test_apply_needs_the_digest_and_refuses_a_stale_plan(tmp_path):
    base, s = _user(tmp_path, [_holding()])
    doc = ir.plan(on=ON, base_dir=base)
    before = s._portfolio_path().read_bytes()
    with pytest.raises(ir.ReconcileRefused, match="approval"):
        ir.apply(doc, "0" * 64, base_dir=base)
    # The holding changes after review: the reviewed plan no longer describes it.
    p = s.load()
    p.holdings[0].adj_qty = 120.0
    s.save(p)
    changed = s._portfolio_path().read_bytes()
    with pytest.raises(ir.ReconcileRefused, match="changed since the plan"):
        ir.apply(doc, doc["plan_digest"], base_dir=base)
    assert s._portfolio_path().read_bytes() == changed != before


def test_apply_replaces_the_parent_with_its_successors(tmp_path):
    base, s = _user(tmp_path, [_holding(), _holding("OLDCO", qty=5.0, price=100.0)])
    original = s._portfolio_path().read_bytes()
    doc = ir.plan(on=ON, base_dir=base)

    result = ir.apply(doc, doc["plan_digest"], base_dir=base)

    held = {h.symbol: h for h in s.load().holdings}
    assert set(held) == {"PARENTA", "PARENTB", "OLDCO"}
    assert (held["PARENTA"].adj_qty, held["PARENTA"].adj_avg_price) == (100.0, pytest.approx(600.0))
    assert (held["PARENTB"].adj_qty, held["PARENTB"].adj_avg_price) == (100.0, pytest.approx(400.0))
    assert held["PARENTA"].buy_date == "2026-05-04"
    [action] = [a for a in held["PARENTA"].applied_actions if a.kind == "demerger"]
    assert action.ex_date == "2026-06-15"
    # A backup of the exact bytes, and an audit line.
    backup = result["applied"][0]["backup"]
    assert backup.startswith("portfolio.json.pre-identity-")
    assert (s._portfolio_path().parent / backup).read_bytes() == original
    audit = (s._portfolio_path().parent / "identity_reconciliations.jsonl").read_text("utf-8")
    assert json.loads(audit)["before"]["symbol"] == "PARENT"
    # Nothing is left to reconcile, and a second apply of the same plan is refused.
    assert ir.plan(on=ON, base_dir=base)["items"] == []
    with pytest.raises(ir.ReconcileRefused):
        ir.apply(doc, doc["plan_digest"], base_dir=base)


def test_after_reconciliation_the_advisor_judges_the_new_basis(tmp_path, gate_mode):
    from core.portfolio.pipeline import gated_decide
    gate_mode("enforce")
    base, s = _user(tmp_path, [_holding()])
    doc = ir.plan(on=ON, base_dir=base)
    ir.apply(doc, doc["plan_digest"], base_dir=base)
    a = next(h for h in s.load().holdings if h.symbol == "PARENTA")
    assert ir.holding_identity_issue(a, ON) == ""
    rec, _ = gated_decide(_signals(a, 600.0), a, "balanced", shelf_ideas=[], sector_weights={},
                          held_symbols={"PARENTA", "PARENTB"}, candidate_fresh={})
    assert rec.verdict == "HOLD" and rec.notes == [] and rec.triggers == []   # 600 vs 600: flat


def test_the_ledger_reconciler_treats_successors_as_unverifiable(tmp_path):
    base, s = _user(tmp_path, [_holding()])
    assert reconcile(s)["status"] == "clean"                     # 100 bought, 100 held
    doc = ir.plan(on=ON, base_dir=base)
    ir.apply(doc, doc["plan_digest"], base_dir=base)
    result = reconcile(s)
    assert result["status"] == "clean", result["issues"]
    assert sorted(result["unverifiable"]) == ["PARENTA", "PARENTB"]


def test_an_unresolved_holding_gets_no_proposal_and_apply_changes_nothing(tmp_path, monkeypatch):
    monkeypatch.setenv("INSTRUMENT_REGISTRY_PATH", str(SHIPPED))
    base, s = _user(tmp_path, [_holding("TATAMOTORS", qty=10.0, price=700.0)])
    before = s._portfolio_path().read_bytes()
    doc = ir.plan(on=ON, base_dir=base)
    [item] = doc["items"]
    assert item["action"] is None and "config/instruments.yaml" in item["needs"]
    result = ir.apply(doc, doc["plan_digest"], base_dir=base)
    assert result["applied"] == [] and result["skipped"][0]["symbol"] == "TATAMOTORS"
    assert s._portfolio_path().read_bytes() == before


def test_a_successor_the_user_already_holds_is_merged_by_hand(tmp_path):
    base, _ = _user(tmp_path, [_holding(), _holding("PARENTB", qty=10.0, price=380.0,
                                                    buy="2026-07-01")])
    [item] = ir.plan(on=ON, base_dir=base)["items"]
    assert item["action"] is None and "already holds PARENTB" in item["needs"]


def test_the_cli_plan_then_apply(tmp_path, monkeypatch, capsys):
    base, s = _user(tmp_path, [_holding()])
    from core.config import settings
    monkeypatch.setattr(settings, "PORTFOLIO_DATA_DIR", base)
    out = tmp_path / "plan.json"
    assert ir.main(["plan", "--on", ON.isoformat(), "--out", str(out)]) == 0
    digest = json.loads(out.read_text("utf-8"))["plan_digest"]
    assert ir.main(["apply", "--plan", str(out), "--approve", "nope"]) == 2
    assert "refused" in capsys.readouterr().err
    assert ir.main(["apply", "--plan", str(out), "--approve", digest]) == 0
    assert {h.symbol for h in s.load().holdings} == {"PARENTA", "PARENTB"}

"""
core/portfolio/identity_reconcile.py
====================================
SA-008: an explicit, operator-reviewed path for positions whose instrument
changed identity (a demerger, a relisting) or is unresolved.

The advisor holds such a position (note IDENTITY, in enforce mode) because
its close is not on the price basis its cost was booked on: after a
demerger the parent's price is the continuing entity's alone, and the
unreconciled cost shows a loss that never happened. Nothing here runs on a
schedule or reaches the network:

  python -m core.portfolio.identity_reconcile plan  [--on YYYY-MM-DD] [--out plan.json]
  python -m core.portfolio.identity_reconcile apply --plan plan.json --approve <digest>

`plan` is read-only. It lists every holding the advisor would hold, with
what the instrument registry (config/instruments.yaml) proposes: the
successor holdings a recorded, evidenced corporate action gives (ticker,
quantity, cost basis), or what must be recorded first. It ends with one
digest over the plan and the holding figures it was made from.

`apply` recomputes the plan and refuses unless the digest is the approved
one, so nothing changed between review and apply. For each proposal it
copies the user's portfolio.json aside, then, under the user's lock,
replaces the old holding with its successors. Each successor carries an
applied action (kind rename/demerger/relisting, ex_date = the day the new
basis starts), which moves its basis date past the event and marks it
`unverifiable` for the ledger reconciler, as a split does. A second apply of
the same plan is refused: the holdings it was made from are gone.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import logging
import shutil
import sys
from datetime import date, datetime, timezone

from backend.shared.data import instruments
from backend.shared.data.fetchers.symbol_resolver import identity_break, resolve_identity
from backend.shared.schemas.portfolio import AppliedCorpAction, Holding
from core.portfolio.store import PortfolioStore, list_user_ids

logger = logging.getLogger(__name__)

IDENTITY_KINDS = ("rename", "demerger", "relisting")


# ---------------------------------------------------------------------------
# What the advisor asks (registry only, no network)
# ---------------------------------------------------------------------------

def basis_since(holding: Holding) -> date:
    """The day this holding's cost basis refers to: its buy date, or the
    effective date of the latest identity reconciliation applied to it."""
    days = [date.fromisoformat(holding.buy_date)]
    days += [date.fromisoformat(a.ex_date) for a in holding.applied_actions
             if a.kind in IDENTITY_KINDS]
    return max(days)


def symbol_identity_issue(symbol: str, on: date) -> str:
    """Why `symbol`'s identity on `on` is not resolved ("" when it is)."""
    ident = resolve_identity(symbol, on)
    if ident.resolved:
        return ""
    return f"{ident.ticker} identity {ident.status}: {ident.reason_text()}"


def holding_identity_issue(holding: Holding, on: date) -> str:
    """Why `on`'s close cannot be judged against this holding's cost basis
    ("" when it can): an unresolved identity, or a new price basis since."""
    issue = symbol_identity_issue(holding.symbol, on)
    if issue:
        return issue
    since = basis_since(holding)
    if since <= on:
        broken = identity_break(holding.symbol, since, on)
        if broken:
            return f"{holding.symbol}: {broken}; the holding needs reconciling"
    return ""


# ---------------------------------------------------------------------------
# Plan (read-only)
# ---------------------------------------------------------------------------

def _proposal(holding: Holding, on: date, held: set[str]) -> dict:
    """What the registry says to do with one held position."""
    since = basis_since(holding)
    seg = instruments.segment_on(holding.symbol, on)
    bases = instruments.registry_bases(holding.symbol, since, on) if since <= on else set()
    if seg is None or not seg.successors:
        return {"action": None,
                "needs": "record the corporate action (effective date, successors with ratio and "
                         "cost_fraction, and exchange evidence) in config/instruments.yaml"}
    if seg.start is None or seg.start <= since or len(bases) > 2:
        return {"action": None,
                "needs": "more than one lifecycle event, or none after the basis date: "
                         "reconcile by hand"}
    clashes = sorted(s.ticker for s in seg.successors
                     if s.ticker in held and s.ticker != holding.symbol)
    if clashes:
        return {"action": None,
                "needs": f"the user already holds {', '.join(clashes)}: merge by hand"}
    cost = holding.adj_qty * holding.adj_avg_price
    successors = []
    for s in seg.successors:
        qty = holding.adj_qty * s.ratio
        part = cost * s.cost_fraction
        successors.append({
            "ticker": s.ticker, "ratio": s.ratio, "cost_fraction": s.cost_fraction,
            "adj_qty": qty, "cost": part, "adj_avg_price": part / qty,
            "dividends_received": holding.dividends_received * s.cost_fraction,
        })
    return {"action": "apply", "kind": seg.via or seg.status,
            "effective": seg.start.isoformat(),
            "evidence": [dict(e) for e in seg.evidence], "successors": successors}


def _digest(items: list[dict], on: date) -> str:
    body = json.dumps({"on": on.isoformat(), "items": items}, sort_keys=True, default=str)
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


def plan(on: date | None = None, base_dir: str | None = None) -> dict:
    """Every held position whose identity or basis is not verified on `on`,
    with the registry's proposal. Read-only."""
    on = on or date.today()
    items: list[dict] = []
    for user_id in sorted(list_user_ids(base_dir)):
        portfolio = PortfolioStore(user_id=user_id, base_dir=base_dir).load()
        held = {h.symbol for h in portfolio.holdings}
        for h in portfolio.holdings:
            issue = holding_identity_issue(h, on)
            if not issue:
                continue
            items.append({
                "user_id": user_id, "symbol": h.symbol, "sector": h.sector,
                "adj_qty": h.adj_qty, "adj_avg_price": h.adj_avg_price,
                "dividends_received": h.dividends_received, "buy_date": h.buy_date,
                "basis_since": basis_since(h).isoformat(), "issue": issue,
                **_proposal(h, on, held),
            })
    return {"on": on.isoformat(), "items": items, "plan_digest": _digest(items, on),
            "registry": instruments.load_registry().path}


# ---------------------------------------------------------------------------
# Apply (operator-approved)
# ---------------------------------------------------------------------------

class ReconcileRefused(RuntimeError):
    """The plan cannot be applied as approved."""


def _successor_holding(old: Holding, item: dict, succ: dict, today: str) -> Holding:
    action = AppliedCorpAction(
        key=f"{old.symbol}|{item['effective']}|identity:{item['kind']}",
        ex_date=item["effective"], kind=item["kind"],
        desc=(f"{item['kind']} of {old.symbol}: {succ['ratio']:g} {succ['ticker']} per share, "
              f"{succ['cost_fraction']:.4g} of cost ({old.adj_qty:g} @ {old.adj_avg_price:.4f})"),
        ratio=succ["ratio"], applied_on=today,
    )
    return Holding(
        symbol=succ["ticker"], sector=old.sector,
        qty=succ["adj_qty"], avg_buy_price=succ["adj_avg_price"],
        adj_qty=succ["adj_qty"], adj_avg_price=succ["adj_avg_price"],
        buy_date=old.buy_date, virtual=old.virtual, broker=old.broker, notes=old.notes,
        target_pct=old.target_pct, max_loss_pct=old.max_loss_pct,
        dividends_received=succ["dividends_received"],
        applied_actions=[*old.applied_actions, action],
    )


def apply(plan_doc: dict, approve: str, base_dir: str | None = None) -> dict:
    """Apply an approved plan. Refuses unless `approve` is the plan's digest
    and a fresh plan for the same day has the same digest."""
    digest = plan_doc.get("plan_digest")
    if not approve or approve != digest:
        raise ReconcileRefused("the approval does not match the plan's digest")
    on = date.fromisoformat(plan_doc["on"])
    fresh = plan(on=on, base_dir=base_dir)
    if fresh["plan_digest"] != digest:
        raise ReconcileRefused("holdings or the instrument registry changed since the plan "
                               "was made: make and review a new plan")
    today = date.today().isoformat()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    applied, skipped = [], []
    for item in fresh["items"]:
        if item.get("action") != "apply":
            skipped.append({"user_id": item["user_id"], "symbol": item["symbol"],
                            "needs": item.get("needs", "")})
            continue
        store = PortfolioStore(user_id=item["user_id"], base_dir=base_dir)
        with store.locked():
            portfolio = store.load()
            idx = next((i for i, h in enumerate(portfolio.holdings)
                        if h.symbol == item["symbol"]), None)
            if idx is None:
                raise ReconcileRefused(f"{item['user_id']}/{item['symbol']} vanished under the lock")
            old = portfolio.holdings[idx]
            backup = store._portfolio_path().with_name(f"portfolio.json.pre-identity-{stamp}")
            shutil.copy2(store._portfolio_path(), backup)
            new = [_successor_holding(old, item, s, today) for s in item["successors"]]
            portfolio.holdings[idx:idx + 1] = new
            store.save(portfolio)
            with open(store._dir / "identity_reconciliations.jsonl", "a", encoding="utf-8") as f:
                f.write(json.dumps({
                    "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                    "plan_digest": digest, "backup": backup.name,
                    "before": old.model_dump(), "after": [h.model_dump() for h in new],
                }, default=str) + "\n")
        for sym in {old.symbol} - {h.symbol for h in new}:
            store._sync_instrument(sym, "held", "remove")
        for h in new:
            store._sync_instrument(h.symbol, "held", "add", origin="held", cadence="daily")
        applied.append({"user_id": item["user_id"], "symbol": item["symbol"],
                        "successors": [h.symbol for h in new], "backup": backup.name})
        logger.warning("[identity_reconcile] %s/%s -> %s (plan %s)", item["user_id"],
                       item["symbol"], ", ".join(h.symbol for h in new), digest[:12])
    return {"plan_digest": digest, "applied": applied, "skipped": skipped}


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m core.portfolio.identity_reconcile")
    sub = parser.add_subparsers(dest="cmd", required=True)
    p_plan = sub.add_parser("plan", help="list holdings needing reconciliation (read-only)")
    p_plan.add_argument("--on", default=None, help="ISO date (default today)")
    p_plan.add_argument("--out", default=None, help="write the plan JSON here")
    p_apply = sub.add_parser("apply", help="apply a reviewed plan")
    p_apply.add_argument("--plan", required=True)
    p_apply.add_argument("--approve", required=True, help="the plan's digest, as reviewed")
    args = parser.parse_args(argv)

    if args.cmd == "plan":
        doc = plan(on=date.fromisoformat(args.on) if args.on else None)
        text = json.dumps(doc, indent=2, default=str)
        if args.out:
            with open(args.out, "w", encoding="utf-8") as f:
                f.write(text + "\n")
        print(text if not args.out else
              f"{len(doc['items'])} holding(s); plan_digest {doc['plan_digest']} -> {args.out}")
        return 0
    with open(args.plan, encoding="utf-8") as f:
        doc = json.load(f)
    try:
        result = apply(doc, args.approve)
    except ReconcileRefused as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())

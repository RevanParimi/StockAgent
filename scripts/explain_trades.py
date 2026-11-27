"""PR-007: the one-off draft of the plain words for trades already in the ledger.

A dry run by default: it reads and prints counts, calls no model and writes
nothing. `--apply` drafts each autopilot BUY and SELL that has no stored words
and appends them to data/portfolio/<user>/explanations.jsonl. It writes
production files when run in production, so it runs there only at the owner's
word (the card of PR-007). Nothing else is read for writing: the ledger, the
advice and the cases are never changed.

    python scripts/explain_trades.py --user primary              # dry run
    python scripts/explain_trades.py --user primary --apply      # draft and store
    python scripts/explain_trades.py --user primary --apply --no-model

A trade made before this has no signals from its run, so a trailing-stop sale
names no highest price; a sale by the case names its reason from the advice
ledger and the exit shadow's record of that day where they exist. The review
cards of past days are not drafted: the screens show only the latest review.
"""
from __future__ import annotations

import argparse
import sys
from collections import Counter
from datetime import date
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(REPO), str(REPO / "src")]

from core.config import settings                                  # noqa: E402
from core.portfolio import exit_shadow, explain                   # noqa: E402
from core.portfolio.cases import CaseStore                        # noqa: E402
from core.portfolio.store import PortfolioStore                   # noqa: E402


def _evidence_of(store: PortfolioStore, txn) -> dict | None:
    """The exit evidence the shadow recorded for a sale's review day, with the
    events it names read back from the event store."""
    row = next((r for r in store.load_exit_shadow()
                if r.get("date") == txn.date and r.get("symbol") == txn.symbol), None)
    if row is None:
        return None
    evidence = dict(row.get("evidence") or {})
    ids = set(evidence.get("event_ids") or [])
    events = []
    if ids:
        from core.events.store import EventStore
        events = [e for e in EventStore().load(txn.symbol) if e.id in ids]
    evidence["negative_events"] = [
        {"id": e.id, "published_at": e.published_at, "category": e.category,
         "what": e.what, "source": e.source} for e in events]
    return evidence


def contexts_for(store: PortfolioStore, txns: list) -> dict[str, explain.Context]:
    """{txn_id: what the ledger's own records say of the run that made it}."""
    advice = {f"{a.date}|{a.symbol}|{a.rationale_hash}": a
              for a in store.load_advice(limit=1_000_000)}
    out = {}
    for txn in txns:
        rec = advice.get(txn.advice_ref) if txn.side == "SELL" else None
        evidence = _evidence_of(store, txn) if txn.side == "SELL" else None
        out[txn.txn_id] = explain.Context(rec=rec, evidence=evidence)
    return out


def backfill(user_id: str, *, apply: bool, model: bool, base_dir: str | None = None,
             limit: int | None = None, out=print) -> dict:
    """Draft (when `apply`) the words of every autopilot trade of `user_id`
    that has none. Returns counts."""
    base = base_dir or settings.PORTFOLIO_DATA_DIR
    store = PortfolioStore(user_id=user_id, base_dir=base)
    ledger = store.load_transactions(limit=1_000_000)
    have = explain.ExplanationStore(user_id, base).load()
    wanted = [t for t in ledger if t.side in explain.EXPLAINED_SIDES and t.source == "autopilot"]
    todo = [t for t in wanted if explain.txn_key(t.txn_id) not in have]
    if limit is not None:
        todo = todo[:limit]
    out(f"{len(wanted)} autopilot trade(s) in the ledger; {len(wanted) - len(todo)} already "
        f"worded or past --limit; {len(todo)} to draft")
    out("by kind: " + ", ".join(f"{k} {n}" for k, n in sorted(Counter(
        f"{t.side}/{t.verdict}" for t in todo).items())))
    if not apply:
        out("dry run: no model call and nothing written; add --apply to draft")
        return {"wanted": len(wanted), "todo": len(todo), "written": 0, "model": 0}
    contexts = contexts_for(store, todo)
    cases = CaseStore(user_id, base)
    # "What would change our mind" is about now, so it names the rule acting now.
    rule = exit_shadow.acting_rule(exit_shadow.exit_rule_mode())
    written = by_model = 0
    for txn in todo:
        # One trade at a time: its own context, its run's other rows as siblings.
        siblings = [t for t in ledger if t.date == txn.date]
        rows = explain.explain_run(
            user_id, date.fromisoformat(txn.date), base_dir=base, txns=[txn],
            contexts={txn.symbol: contexts[txn.txn_id]}, digest=None, ledger=ledger,
            case_store=cases, model=model, budget_s=float("inf"), siblings=siblings,
            exit_rule=rule)
        row = rows.get(explain.txn_key(txn.txn_id))
        if row:
            written += 1
            by_model += row["source"] == "model"
    out(f"written {written} of {len(todo)}; {by_model} with a model's company sentence")
    return {"wanted": len(wanted), "todo": len(todo), "written": written, "model": by_model}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--user", required=True)
    parser.add_argument("--apply", action="store_true", help="draft and store")
    parser.add_argument("--no-model", action="store_true", help="templates only")
    parser.add_argument("--limit", type=int)
    args = parser.parse_args(argv)
    counts = backfill(args.user, apply=args.apply, model=not args.no_model, limit=args.limit)
    return 0 if not args.apply or counts["written"] == counts["todo"] else 1


if __name__ == "__main__":
    sys.exit(main())

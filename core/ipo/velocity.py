"""PI Prospect P2 — derivations over the capture ledger (design §5 P2).

Pure functions, recomputed on every read. Nothing here is ever written back
into ipo_signals.jsonl: the ledger holds captured facts, and keeping the maths
outside it means a change of definition never requires rewriting history.

Every function returns None rather than 0.0 when there is nothing to measure.
A zero delta asserts demand did not move, which is a different claim from
having only one reading.
"""
from __future__ import annotations

from core.ipo.signals import IpoSignalSnapshot


def _readings(snaps: list[IpoSignalSnapshot]) -> list[IpoSignalSnapshot]:
    """Snapshots that actually carry an all-exchange total, oldest first."""
    rows = [s for s in snaps or [] if s.combined.get("total") is not None]
    return sorted(rows, key=lambda s: s.captured_at)


def latest_demand(snaps: list[IpoSignalSnapshot]) -> float | None:
    """The most recent all-exchange subscription multiple."""
    rows = _readings(snaps)
    return rows[-1].combined["total"] if rows else None


def demand_delta(snaps: list[IpoSignalSnapshot]) -> float | None:
    """Change in subscription × since the PREVIOUS reading.

    Deliberately not "today's change": the refresh runs twice daily, so the
    previous reading may be this morning or yesterday evening. Callers render
    this as "since last update", which is true either way.
    """
    rows = _readings(snaps)
    if len(rows) < 2:
        return None
    return rows[-1].combined["total"] - rows[-2].combined["total"]


def final_demand_snapshot(snaps: list[IpoSignalSnapshot]) -> IpoSignalSnapshot | None:
    """The last snapshot carrying a total — the completed demand picture.

    This is the row P3 will train on: everything that was knowable about
    demand at the moment the window shut.
    """
    rows = _readings(snaps)
    return rows[-1] if rows else None

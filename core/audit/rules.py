"""What "correct" means (design section 5).

Everything the auditor will ever claim rests on this file, and it is the only
part that cannot be quietly changed later without invalidating accumulated
history. Hence: pure functions, no I/O, exhaustively tested.

Correctness is defined on EXCESS return against the benchmark, never on raw
return. In a bull market raw return makes every HOLD look right; the only
question worth asking is whether following the advice beat doing nothing.
"""
from __future__ import annotations

# Verdicts whose intent is to keep or increase exposure.
INTENT_LONG = frozenset({"HOLD", "ADD"})
# Verdicts whose intent is to reduce or leave the position.
INTENT_REDUCE = frozenset({"TRIM", "EXIT", "SWITCH"})


def pct_change(entry: float, exit_close: float) -> float:
    """Percentage move from entry to exit. Raises on a non-positive entry —
    a zero or negative close is bad data, not a 0% move."""
    if entry <= 0:
        raise ValueError(f"entry close must be positive, got {entry!r}")
    return round((exit_close / entry - 1.0) * 100.0, 4)


def excess(return_pct: float, bench_pct: float) -> float:
    """Return above the benchmark, in percentage points."""
    return round(return_pct - bench_pct, 4)


def is_correct(verdict: str, excess_pct: float) -> bool | None:
    """True/False for scoreable verdicts, None for everything else.

    None is not a failure — a shelf add is a tracking decision, not a call,
    and scoring it would reintroduce exactly the "is this a buy?" confusion
    the alert wording fix removed.
    """
    v = (verdict or "").strip().upper()
    if v in INTENT_LONG:
        return excess_pct >= 0.0
    if v in INTENT_REDUCE:
        return excess_pct < 0.0
    return None


def is_switch_correct(origin_excess_pct: float, dest_excess_pct: float) -> bool:
    """Did rotating beat staying, over the same window?

    Deliberately NOT part of is_correct(). That function defines what every
    accumulated advice row already means, and this module's docstring says it
    cannot be changed without invalidating that history. A switch asks a
    different question and gets its own answer here.

    Both legs are excess over the same benchmark, so the benchmark cancels and
    this is a pure relative-strength comparison. A dead heat is False:
    rotating has real costs (brokerage, spread, tax) that this layer does not
    model, so a tie is not evidence that moving was right.
    """
    return dest_excess_pct > origin_excess_pct

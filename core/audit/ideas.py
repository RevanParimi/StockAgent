"""How the ideas did against the Nifty: the report of the idea lanes (PR-017).

Pure: rows in, numbers out. At each horizon, for each group, the number of
graded ideas (n), the mean and median excess over the Nifty in points and the
share that beat it. Under MIN_N ideas a group reads "too few to judge"
(EDGE-ROADMAP rule 4); its figures are still shown, with their n.

The groups (the card's item 5):

- **BUY dives**: dives the analysis rated BUY or STRONG BUY at a conviction
  of at least the shelf's floor (`discovery.min_conviction`): the ideas the
  product would shelve.
- **Rejected dives**: every other dive whose verdict was recorded, NEUTRAL,
  SELL or under the floor, except an abstained one (INSUFFICIENT DATA, no
  judgement), which is only counted.
- **Screen only**: screen candidates the week's run did not dive.
- **The bare model's BUYs**.
- **BUY dives by graph**: native and generic (CLEAN-003's rule for the four
  sector prompts reads this split).

A dive seeded without its verdict (`dive_record`'s backfill) is in no group
and is counted (`verdict_not_recorded`). Paper research: no money moved.
"""
from __future__ import annotations

import statistics
from datetime import date
from typing import Iterable

MIN_N = 30
TOO_FEW = "too few to judge"
ABSTAINED = "INSUFFICIENT DATA"
BUY_VERDICTS = ("BUY", "STRONG BUY")
GROUPS = ("buy_dives", "rejected_dives", "screen_only", "bare_buys")
GRAPHS = ("native", "generic")
LABELS = {"buy_dives": "BUY dives", "rejected_dives": "rejected dives",
          "screen_only": "screen only", "bare_buys": "the bare model's BUYs",
          "native": "native", "generic": "generic"}
LINE_HORIZON_TD = 30


def _floor() -> float:
    try:
        from core.config import settings
        return float(settings.DISCOVERY_MIN_CONVICTION)
    except Exception:
        return 0.55


def is_buy_dive(row, floor: float) -> bool:
    return (row.verdict.strip().upper() in BUY_VERDICTS
            and row.conviction is not None and row.conviction >= floor)


def group_of(row, floor: float) -> str:
    """The row's group; "" for none."""
    if row.lane == "dive":
        verdict = row.verdict.strip().upper()
        if not verdict or verdict == ABSTAINED:
            return ""
        return "buy_dives" if is_buy_dive(row, floor) else "rejected_dives"
    if row.lane == "screen":
        return "screen_only" if "not_dived" in row.triggers else ""
    if row.lane == "bare":
        return "bare_buys" if row.verdict.strip().upper() == "BUY" else ""
    return ""


def stats(values: list[float], min_n: int = MIN_N) -> dict:
    n = len(values)
    if not n:
        return {"n": 0, "mean_excess_pct": None, "median_excess_pct": None,
                "beat_pct": None, "judge": TOO_FEW}
    return {"n": n, "mean_excess_pct": round(sum(values) / n, 4),
            "median_excess_pct": round(statistics.median(values), 4),
            "beat_pct": round(sum(1 for v in values if v > 0) / n * 100.0, 2),
            "judge": TOO_FEW if n < min_n else ""}


def idea_block(rows: Iterable, horizons: Iterable[int], *, as_of: date | None = None,
               floor: float | None = None, min_n: int = MIN_N) -> dict:
    """{"horizons": {h: {group: stats, "by_graph": {graph: stats}}}, counts}.
    With `as_of`, only grades whose horizon ended on or before it. One value
    per (reference, horizon): the first row written."""
    floor = _floor() if floor is None else floor
    first: dict[tuple[str, int], object] = {}
    for r in rows:
        if r.lane not in ("dive", "screen", "bare"):
            continue
        if as_of is not None and r.graded_on > as_of.isoformat():
            continue
        first.setdefault((r.ref, int(r.horizon_td)), r)
    out: dict = {"horizons": {}, "floor": floor, "min_n": min_n}
    for h in horizons:
        at = [r for (ref, hh), r in first.items() if hh == h]
        values: dict[str, list[float]] = {g: [] for g in GROUPS}
        graphs: dict[str, list[float]] = {g: [] for g in GRAPHS}
        for r in at:
            g = group_of(r, floor)
            if g:
                values[g].append(float(r.excess_pct))
            if g == "buy_dives" and r.graph in GRAPHS:
                graphs[r.graph].append(float(r.excess_pct))
        block = {g: stats(values[g], min_n) for g in GROUPS}
        block["by_graph"] = {g: stats(graphs[g], min_n) for g in GRAPHS}
        dives = [r for r in at if r.lane == "dive"]
        block["verdict_not_recorded"] = sum(1 for r in dives if not r.verdict.strip())
        block["abstained"] = sum(1 for r in dives if r.verdict.strip().upper() == ABSTAINED)
        block["buy_dives_graph_unknown"] = sum(
            1 for r in dives if is_buy_dive(r, floor) and r.graph not in GRAPHS)
        block["screen_dived_unknown"] = sum(
            1 for r in at if r.lane == "screen" and "dived_unknown" in r.triggers)
        out["horizons"][str(h)] = block
    return out


def dive_coverage(dive_rows: Iterable[dict], graded: Iterable, horizons: Iterable[int], *,
                  today: date) -> dict:
    """At each horizon, how many recorded dives have reached it by `today`
    and how many of those are graded: the rest have no price yet, or never
    will (no bar on the entry session, a basis that cannot be established).
    The card's "a dive with no price is skipped and counted"."""
    from core.intelligence.rl.nse_calendar import trading_days_after
    have = {(r.ref, int(r.horizon_td)) for r in graded if r.lane == "dive"}
    out: dict[str, dict] = {}
    rows = list(dive_rows)
    for h in horizons:
        reached = 0
        done = 0
        for row in rows:
            try:
                day = date.fromisoformat(str(row["dive_date"]))
            except (KeyError, ValueError):
                continue
            if trading_days_after(day, h) > today:
                continue
            reached += 1
            done += (row["ref"], h) in have
        out[str(h)] = {"reached": reached, "graded": done, "not_graded": reached - done}
    return out


def _part(label: str, s: dict) -> str:
    if not s["n"]:
        return f"{label}: none graded yet"
    text = (f"{label} {s['mean_excess_pct']:+.1f} points mean, median "
            f"{s['median_excess_pct']:+.1f}, {s['beat_pct']:.0f}% beat it (n {s['n']}")
    return text + (f", {s['judge']})" if s["judge"] else ")")


def horizon_text(block: dict, horizon: int) -> str:
    """One sentence for one horizon."""
    h = block["horizons"].get(str(horizon))
    if h is None:
        return f"At {horizon} sessions: not graded."
    parts = [_part(LABELS[g], h[g]) for g in GROUPS]
    graph = "; ".join(_part(LABELS[g], h["by_graph"][g]) for g in GRAPHS)
    text = (f"At {horizon} sessions, from the next session's open: " + "; ".join(parts)
            + f". BUY dives by graph: {graph}.")
    cover = (block.get("coverage") or {}).get(str(horizon))
    if cover and cover["not_graded"]:
        text += (f" {cover['not_graded']} of {cover['reached']} dives that reached it have "
                 "no grade (no price yet, or none to be had).")
    return text


def idea_line(block: dict, horizon: int = LINE_HORIZON_TD) -> str:
    """The scorecard's one line (paper research, against the Nifty)."""
    h = block["horizons"].get(str(horizon))
    if h is None or not any(h[g]["n"] for g in GROUPS):
        return (f"No deep dive, screen candidate or bare-model answer has reached "
                f"{horizon} sessions yet (paper research, against the Nifty).")
    return ("Ideas against the Nifty (paper research). " + horizon_text(block, horizon))

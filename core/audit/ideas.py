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

**The conviction check** (PR-018) asks whether a higher conviction did better,
over the same `dive` rows at 30 sessions, at the conviction each dive was
issued with. Four groups: dives rejected under 0.55 (any recorded verdict), and
BUY dives at 0.55 to under 0.65, 0.65 to under 0.75, and 0.75 and above. A dive
at 0.55 or more that was not rated a BUY is in no group, since sizing by
conviction applies to buys; it is counted. "BUY" is the verdict the dive row
holds, the composite's band, as in the groups above; the shelf also asks for
the model's own BUY (PR-047), which the grade does not carry, so a BUY group can
hold a dive the shelf refused. Each group says how many stocks its dives are
of: a stock dived again each month counts once a dive.

**The rule**, written on 27 Nov 2026 before any check was read: conviction
"predicts" when the mean excess of BUY dives at 0.75 and above is at least 2
points over that of BUY dives at 0.55 to under 0.65, with 30 or more dives in
each, at two monthly looks in a row. The two means are judged as the line
shows them, to two places. A look is a monthly check at which each of the two
groups holds 30 or more graded dives that no other look has read; it judges
those alone and uses them up, so no row counts in two looks. A month without
that many is no look: it neither counts nor breaks the run. A look that does
not pass starts the run again. A pass, once stored, stays. After 300 graded
dives, while the rule has not passed, a gap under 2 points over all of them is
said plainly, with no conclusion while the latest look passed. The check
reports; it sizes and changes nothing. The owner may change the 2 points
before the first look; after it, a change is reviewed code, never a setting
tuned after a result.
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

# The conviction check (PR-018; module docstring). The edges and the rule are
# fixed here, not read from `discovery.min_conviction`: a setting may move the
# shelf's floor, never the groups a result was judged in.
CHECK_HORIZON_TD = 30
BUY_FROM, MID_FROM, TOP_FROM = 0.55, 0.65, 0.75
CHECK_GROUPS = ("rejected", "buy_055", "buy_065", "buy_075")
CHECK_LABELS = {"rejected": "rejected, under 0.55", "buy_055": "BUY at 0.55 to under 0.65",
                "buy_065": "BUY at 0.65 to under 0.75", "buy_075": "BUY at 0.75 and above"}
LOW_GROUP, TOP_GROUP = "buy_055", "buy_075"
PREDICTS_MARGIN_POINTS = 2.0
LOOKS_IN_A_ROW = 2
FLAT_AFTER_DIVES = 300


def _floor() -> float:
    """The shelf's conviction floor (`discovery.min_conviction`)."""
    from core.config import settings
    return float(settings.DISCOVERY_MIN_CONVICTION)


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


# -- Does conviction predict? (PR-018) -----------------------------------------

def conviction_group(row) -> str:
    """The dive row's group in the conviction check; "" for none."""
    verdict = row.verdict.strip().upper()
    if row.lane != "dive" or row.conviction is None or not verdict or verdict == ABSTAINED:
        return ""
    if row.conviction < BUY_FROM:
        return "rejected"
    if verdict not in BUY_VERDICTS:
        return ""
    if row.conviction < MID_FROM:
        return LOW_GROUP
    return "buy_065" if row.conviction < TOP_FROM else TOP_GROUP


def _check_dives(rows: Iterable, as_of: date | None) -> list:
    """The dive rows graded at 30 sessions by `as_of`, one a dive: the first
    written."""
    first: dict[str, object] = {}
    for r in rows:
        if r.lane != "dive" or int(r.horizon_td) != CHECK_HORIZON_TD:
            continue
        if as_of is not None and r.graded_on > as_of.isoformat():
            continue
        first.setdefault(r.ref, r)
    return list(first.values())


def _by_group(dives: Iterable) -> dict[str, list]:
    groups: dict[str, list] = {g: [] for g in CHECK_GROUPS}
    for r in dives:
        group = conviction_group(r)
        if group:
            groups[group].append(r)
    return groups


def _group_stats(rows: list) -> dict:
    """`stats` of one group's excess, with how many stocks its dives are of."""
    return {**stats([float(r.excess_pct) for r in rows]),
            "stocks": len({r.symbol for r in rows})}


def _gap(top: dict, low: dict) -> float:
    """The top group's mean minus the 0.55 group's, from the two means as the
    line shows them (two places), so a reader's own subtraction gives the figure
    judged. Example: 4.30 against 2.30 is 2.00, though the floats differ by
    1.9999999999999996."""
    return round(round(top["mean_excess_pct"], 2) - round(low["mean_excess_pct"], 2), 2)


def conviction_table(rows: Iterable, *, as_of: date | None = None) -> dict:
    """Each group's figures over every dive graded at 30 sessions (by `as_of`
    when given). The audit report and the monthly scorecard line both read this."""
    dives = _check_dives(rows, as_of)
    groups = _by_group(dives)
    verdicts = [r.verdict.strip().upper() for r in dives]
    return {
        "horizon_td": CHECK_HORIZON_TD,
        "graded_dives": len(dives),
        "groups": {g: _group_stats(groups[g]) for g in CHECK_GROUPS},
        "not_buy_at_floor": sum(
            1 for r, v in zip(dives, verdicts)
            if v and v != ABSTAINED and v not in BUY_VERDICTS
            and r.conviction is not None and r.conviction >= BUY_FROM),
        "verdict_not_recorded": sum(1 for v in verdicts if not v),
        "abstained": sum(1 for v in verdicts if v == ABSTAINED),
    }


def stored_looks(scorecards: Iterable[dict], *, week_start: str
                 ) -> tuple[list[dict], set[str], str | None]:
    """From the stored scorecard rows: the looks of weeks before `week_start`,
    oldest first; the dives any other week's look has read, later weeks
    included, so a week built late still reads no dive twice; and the day an
    earlier week said the rule had passed, or None. A stored pass stays one,
    even when a week built late afterwards would break its run."""
    earlier: list[tuple[str, dict]] = []
    used: set[str] = set()
    passed: list[str] = []
    for row in scorecards:
        check = row.get("conviction_check") if isinstance(row, dict) else None
        if not isinstance(check, dict) or row.get("week_start") == week_start:
            continue
        before = str(row.get("week_start") or "") < week_start
        if before and check.get("passed_on"):
            passed.append(str(check["passed_on"]))
        look = check.get("look")
        if not isinstance(look, dict):
            continue
        used.update(str(ref) for ref in look.get("refs") or [])
        if before:
            earlier.append((str(row.get("week_start") or ""), look))
    return ([look for _, look in sorted(earlier, key=lambda pair: pair[0])], used,
            min(passed, default=None))


def _run_of_passes(looks: list[dict]) -> tuple[int, str | None]:
    """(passes in a row at the end, the day the run first reached the two the
    rule needs, or None)."""
    streak, passed_on = 0, None
    for look in looks:
        streak = streak + 1 if look.get("passed") else 0
        if streak >= LOOKS_IN_A_ROW and passed_on is None:
            passed_on = look.get("on")
    return streak, passed_on


def _long_run(dives: list, passed_on: str | None) -> dict | None:
    """The card's other ending: 300 dives graded, the rule not passed, and the
    gap over all of them under the margin (flat) or below zero (negative).
    None otherwise."""
    if passed_on or len(dives) < FLAT_AFTER_DIVES:
        return None
    groups = _by_group(dives)
    top, low = _group_stats(groups[TOP_GROUP]), _group_stats(groups[LOW_GROUP])
    if min(top["n"], low["n"]) < MIN_N:
        return {"state": "too_few", "gap_points": None}
    gap = _gap(top, low)
    if gap >= PREDICTS_MARGIN_POINTS:
        return None
    return {"state": "negative" if gap < 0 else "flat", "gap_points": gap}


def conviction_check(rows: Iterable, *, as_of: date, earlier: Iterable[dict] = (),
                     used: Iterable[str] = (), passed_before: str | None = None) -> dict:
    """The monthly check as of `as_of`: the table over every graded dive, this
    month's look when there is one (module docstring), and where the rule
    stands. `earlier`, `used` and `passed_before` come from the stored rows
    (`stored_looks`)."""
    rows = list(rows)
    used = set(used)
    dives = _check_dives(rows, as_of)
    fresh = [r for r in dives if r.ref not in used]
    groups = _by_group(fresh)
    counts = {"top": len(groups[TOP_GROUP]), "low": len(groups[LOW_GROUP])}
    look = None
    if min(counts.values()) >= MIN_N:
        top, low = _group_stats(groups[TOP_GROUP]), _group_stats(groups[LOW_GROUP])
        gap = _gap(top, low)
        look = {"on": as_of.isoformat(), "top": top, "low": low, "gap_points": gap,
                "passed": gap >= PREDICTS_MARGIN_POINTS,
                "refs": sorted(r.ref for r in fresh)}
    looks = [*earlier, *([look] if look else [])]
    streak, passed_on = _run_of_passes(looks)
    passed_on = min((d for d in (passed_before, passed_on) if d), default=None)
    last = looks[-1] if looks else None
    return {
        **conviction_table(rows, as_of=as_of),
        "margin_points": PREDICTS_MARGIN_POINTS,
        "look": look,
        "fresh": counts,
        "looks": len(looks),
        "last_look": ({"on": last.get("on"), "passed": bool(last.get("passed"))}
                      if last else None),
        "streak": streak,
        "passed_on": passed_on,
        "long_run": _long_run(dives, passed_on),
    }


def _counted(s: dict) -> str:
    """ "n 34, 12 stocks": how many dives, and of how many stocks."""
    stocks = s["stocks"]
    return f"n {s['n']}, {stocks} stock{'' if stocks == 1 else 's'}"


def _group_text(group: str, s: dict) -> str:
    if not s["n"]:
        return f"{CHECK_LABELS[group]}: none graded yet"
    text = f"{CHECK_LABELS[group]}: {s['mean_excess_pct']:+.2f} ({_counted(s)}"
    return text + (f", {s['judge']})" if s["judge"] else ")")


def table_text(table: dict) -> str:
    """The four groups in one or two sentences, every figure with its n."""
    text = (f"At {table['horizon_td']} sessions, mean excess over the Nifty in points "
            "(paper research): "
            + "; ".join(_group_text(g, table["groups"][g]) for g in CHECK_GROUPS) + ".")
    left_out = [(table["not_buy_at_floor"], "at 0.55 or more not rated a BUY"),
                (table["verdict_not_recorded"], "with no recorded verdict"),
                (table["abstained"], "with insufficient data")]
    if any(n for n, _ in left_out):
        text += " In no group: " + ", ".join(f"{n} {why}" for n, why in left_out if n) + "."
    return text


def _long_day(iso) -> str:
    try:
        d = date.fromisoformat(str(iso))
    except ValueError:
        return str(iso)
    return f"{d.day} {d.strftime('%b %Y')}"


def _look_status(check: dict) -> str:
    look, last = check.get("look"), check.get("last_look")
    if look:
        top, low = look["top"], look["low"]
        text = (f" This month's look: {top['mean_excess_pct']:+.2f} ({_counted(top)}) against "
                f"{low['mean_excess_pct']:+.2f} ({_counted(low)}), a gap of "
                f"{look['gap_points']:+.2f} points: "
                f"{'passed' if look['passed'] else 'not passed'}.")
        if look["passed"] and not check.get("passed_on"):
            text += (f" {check['streak']} of the {LOOKS_IN_A_ROW} passes in a row the "
                     "rule needs.")
        return text
    fresh = check["fresh"]
    text = (f" No look this month: it needs {MIN_N} BUY dives at 0.75 and above and {MIN_N} "
            f"at 0.55 to under 0.65 that no other look has read; there are {fresh['top']} "
            f"and {fresh['low']}.")
    if last:
        text += (f" The last look, on {_long_day(last['on'])}, "
                 f"{'passed' if last['passed'] else 'did not pass'}.")
    return text


def _long_run_text(check: dict) -> str:
    long_run = check.get("long_run")
    if not long_run:
        return ""
    n = check["graded_dives"]
    top, low = check["groups"][TOP_GROUP], check["groups"][LOW_GROUP]
    if long_run["state"] == "too_few":
        return (f" {n} dives are graded, but BUY at 0.75 and above has {top['n']} and BUY at "
                f"0.55 to under 0.65 has {low['n']}: too few to judge whether conviction "
                "predicts.")
    short = ("so higher conviction did worse" if long_run["state"] == "negative" else
             f"short of the {PREDICTS_MARGIN_POINTS:g} the rule asks")
    text = (f" {n} dives are graded. Over all of them, BUY at 0.75 and above (n {top['n']}) "
            f"against BUY at 0.55 to under 0.65 (n {low['n']}) shows a gap of "
            f"{long_run['gap_points']:+.2f} points, {short}")
    if check.get("streak"):
        return text + (". The latest look passed, so there is no conclusion until the next "
                       "look.")
    return text + (": conviction is not shown to predict returns. For you to choose: an "
                   "independent challenge to every BUY, two runs that must agree, or a "
                   "better model.")


def conviction_line(check: dict) -> str:
    """The monthly scorecard line: the table, the rule, and where it stands."""
    text = (table_text(check)
            + f" Rule: conviction predicts when BUY at 0.75 and above beats BUY at 0.55 to "
              f"under 0.65 by {check['margin_points']:g} points or more, {MIN_N} or more "
              f"dives in each, at {LOOKS_IN_A_ROW} monthly looks in a row; each look reads "
              "only dives no other look has read.")
    text += _look_status(check)
    if check.get("passed_on"):
        text += (f" The rule passed on {_long_day(check['passed_on'])}: by this rule, "
                 "conviction predicts returns. Sizing buys by conviction is now yours to "
                 "decide; nothing changes until you do.")
        last = check.get("last_look")
        if last and not last["passed"]:
            text += f" The latest look, on {_long_day(last['on'])}, did not pass."
    return text + _long_run_text(check)

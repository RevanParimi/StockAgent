"""PR-041: does the weekly screen's cut choose? Graded forward from each screen.

A read-only report, run by hand. PR-039's report reads one window in hindsight;
this one takes every stored weekly screen
(`<discovery.data_dir>/screens/<date>_screen.json`) and grades its cut from the
screen's own date:

  the cut   the screen's candidates
  the rest  every stock with a session on the screen's date that is inside the
            screen's floors as of that date (PR-039's `floors_out`) and was
            neither a candidate nor rejected by that screen's guards
  shown, not tested: the guards' rejected, and the candidates' rank halves
            (the first half of the list and the second: 1 to 20 and 21 to 40
            of a list of 40)

Entry is the close of the first session after the screen's run (its recorded
`run_date`; older files carry none, so the Saturday after the screen's session).
Returns are chained on NSE's previous close (PR-039's `chained_return`), so a
split or bonus is not a move. Horizons of 10, 30 and 60 sessions, each counted
only when matured. Both groups share their dates, so the market cancels and no
index is needed. One price row a stock a day is read, its equity series' (debt
and block-deal rows can share a ticker). A stock with no close at the entry or
the exit, or an unreadable price on the way, is left out and counted.

Per screen: each group's mean and median return, and the cut's lead, which is
the cut's mean less the rest's mean (what a position put into every stock of a
group made on average). The same difference of the two medians is shown beside
it and not tested. Over the screens, every screen weighted equally: the mean and
median lead and the share of screens the cut led.

Shown beside the verdict and never tested, because a few distorted returns can
move a mean of 40 to 60 stocks: how many of each group had a close NSE restated
(PR-039's mark), the leads without those stocks, each candidate that moved 50% or
more, the spread of the screens' leads, and the leads of the 40-stock cuts and of
the wider ones apart.

The rule, fixed before the data (read at 30 sessions):
  the cut chooses          mean lead and median lead each above +1 point, and
                           the cut led in at least 60% of the screens
  the cut does not choose  the mean lead is at or below 0
  not yet decidable        in between, or fewer than 8 screens matured

Reads (nothing is written, no network, no model call): the stored daily
bhavcopy, the weekly screens and the instrument listing. It prints symbols,
counts, returns and the rupees of one made-up position only: no user data.

Usage (repository root; on production from /app, at the owner's word):
    python -B scripts/screen_cut.py [--end YYYY-MM-DD] [--book-inr 10000000]
        [--position-pct 3.2] [--root DIR] [--json]
    railway ssh "cd /app && python -B scripts/screen_cut.py"
"""
from __future__ import annotations

import sys

sys.dont_write_bytecode = True     # no __pycache__ in /app either

import argparse  # noqa: E402
import json  # noqa: E402
import math  # noqa: E402
import statistics  # noqa: E402
from datetime import date  # noqa: E402
from pathlib import Path  # noqa: E402

_REPO = Path(__file__).resolve().parents[1]
for _p in (str(_REPO), str(_REPO / "src")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from core.config import settings  # noqa: E402
from core.discovery.shelf import saturday_after  # noqa: E402
from core.discovery.universe import UNKNOWN  # noqa: E402
from scripts import missed_risers as mr  # noqa: E402
from services.data.fetchers.bhavcopy import _SERIES_PREFERENCE  # noqa: E402

HORIZONS = (10, 30, 60)
READ_AT = 30                 # the rule is read at this horizon only
MIN_SCREENS = 8              # matured screens the rule needs
LEAD_POINTS = 1.0            # "chooses": mean and median lead each above this
LED_SHARE_PCT = 60           # "chooses": the cut led in at least this share
TOP_FIFTH = 0.8              # a signal rank this high put a stock in its top fifth
LARGE_MOVE_PCT = 50.0        # a candidate that moved this far at READ_AT is listed by name
OLD_CUT = 40                 # the cut before PR-037 widened it (18 Nov 2026)
# What the floors and the chained return read: it runs beside the app, so no more is kept.
PRICE_COLUMNS = ("symbol", "series", "date", "prev_close", "high", "close", "traded_value_cr")
# A stock's own series, best first (the listing's order, and the SME trade-for-trade one).
_EQUITY_RANK = {name: i for i, name in enumerate((*_SERIES_PREFERENCE, "SZ"))}
# floors_out's one reason for a stock today's listing does not know.
_NOT_IN_LISTING = f"listed as {UNKNOWN}, not a company"

CHOOSES = "the cut chooses"
DOES_NOT = "the cut does not choose"
UNDECIDED = "not yet decidable"
NEXT_STEP = {
    CHOOSES: "close the card: the risers ranked below the cut are the price of a cut that "
             "keeps more fallers out, and the screen stays as it is",
    DOES_NOT: "write the card on the screen's signals, naming the signals that carried the "
              "candidates that trailed (the signals table), with a money example",
    UNDECIDED: "re-read four weeks after this run, with the same rule",
}

LIMITS = (
    "One market period: only the screens stored so far. Another period can rank the "
    "groups differently.",
    "The floors outside the shortlist are the bhavcopy's (series, price, liquidity, "
    "circuit streak) and the listing's; free float, pledge and surveillance were read "
    "only for the screen's shortlist, so a stock outside it is counted inside the floors "
    "unless that screen rejected it. The cut passed every guard and the rest only those "
    "floors, so part of a lead can be the guards' doing, not the ranking's.",
    "The listing is today's. A stock it no longer knows (delisted or renamed since) is "
    "left out of the rest, though a candidate stays in the cut; the count is shown per "
    "screen.",
    "A stock with no close on the entry or the exit session (suspended or delisted), or "
    "an unreadable price between them, is left out of its group; the counts are shown per "
    "screen.",
    "Neighbouring screens' windows overlap (a screen a week, windows of many sessions), "
    "so the screens are far fewer independent tests than their count.",
    "Returns are chained on NSE's previous close, so a split or bonus is not a move. An "
    "action NSE does not restate there reads as one, and a session missing from the "
    "store is a move missed.",
    "No trading costs or taxes. It grades the screen's cut, not the book: the book buys "
    "only after a deep dive.",
)


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------
def load_screens(root: Path, end: date | None) -> tuple[dict[date, dict], list[str]]:
    """The stored screens up to `end`, by screen date, and a note for each file
    that could not be read."""
    disc = mr._resolve(root, settings.DISCOVERY_DATA_DIR)
    screens: dict[date, dict] = {}
    notes: list[str] = []
    for path in sorted((disc / "screens").glob("????-??-??_screen.json")):
        day = mr._iso_day(path.name[:10])
        if day is None or (end is not None and day > end):
            continue
        record = mr._read_json(path, None)
        if not isinstance(record, dict):
            notes.append(f"screen file {path.name} could not be read: not graded")
            continue
        screens[day] = record
    return screens, notes


def one_row_a_day(frame):
    """(one row a stock a day, from its equity series; how many other rows
    shared such a stock's day). The store keeps every series NSE sends, and a
    company's debt can carry its ticker: read as the share's price, such a row
    would drop the stock from the rest or move its return."""
    own = frame["series"].isin(list(_EQUITY_RANK))
    kept = frame[own]
    if kept.duplicated(["symbol", "date"]).any():
        kept = (kept.assign(_rank=kept["series"].map(_EQUITY_RANK))
                .sort_values(["symbol", "date", "_rank"], kind="stable")
                .drop_duplicates(["symbol", "date"]).drop(columns="_rank"))
    days = kept[["symbol", "date"]]
    shared = len(frame[~own][["symbol", "date"]].merge(days, on=["symbol", "date"]))
    return kept, shared + int(own.sum()) - len(kept)


def load_prices(root: Path, end: date | None, first_screen: date):
    """(sessions, rows, other rows left out): every stored session up to `end`,
    and one row a stock a day from 60 sessions before the first screen (the
    liquidity floor's median) on."""
    eod_dir = mr._resolve(root, settings.DISCOVERY_BHAVCOPY_DIR)
    days = [d for d in mr._eod_days(eod_dir) if end is None or d <= end]
    need = len([d for d in days if d >= first_screen]) + mr.LIQUIDITY_SESSIONS + 1
    frame = mr._load_eod(eod_dir, days[-need:])
    return (days, *one_row_a_day(frame[list(PRICE_COLUMNS)]))


def by_symbol(eod) -> dict:
    return {sym: rows.sort_values("date") for sym, rows in eod.groupby("symbol")}


# ---------------------------------------------------------------------------
# One screen
# ---------------------------------------------------------------------------
def run_day(record: dict, screen_day: date) -> tuple[date, bool]:
    """(the day the screen ran, whether the file recorded it). A file with no
    run day (written before PR-017), or one before its own session, is taken to
    have run on the Saturday after its session."""
    recorded = mr._iso_day(record.get("run_date"))
    if recorded is not None and recorded >= screen_day:
        return recorded, True
    return saturday_after(screen_day), False


def _symbols(values) -> list[str]:
    return [str(v).strip().upper() for v in values]


def candidates_of(record: dict) -> list[dict]:
    """The screen's candidates in rank order, one row per symbol."""
    out, seen = [], set()
    for c in record.get("candidates") or []:
        if not isinstance(c, dict):
            continue
        sym = str(c.get("symbol") or "").strip().upper()
        if sym and sym not in seen:
            seen.add(sym)
            out.append(dict(c, symbol=sym))
    return out


def rest_of(groups: dict, listing: dict | None, screen_day: date,
            taken: set[str]) -> tuple[list[str], int]:
    """(the rest, how many were left out only because today's listing does not
    know them): symbols with a session on the screen's date, inside the floors
    as of that date, and not in `taken` (candidates and guard rejections)."""
    day = screen_day.isoformat()
    rest: list[str] = []
    unlisted = 0
    for sym in sorted(groups):
        if sym in taken:
            continue
        rows = groups[sym]
        upto = rows.iloc[:int(rows["date"].searchsorted(day, side="right"))]
        if upto.empty or upto.iloc[-1]["date"] != day:
            continue
        why = mr.floors_out(upto, listing, sym)
        if not why:
            rest.append(sym)
        elif why == [_NOT_IN_LISTING]:
            unlisted += 1
    return rest, unlisted


def forward_returns(groups: dict, symbols: list[str], entry: str,
                    exit_: str) -> dict[str, tuple[float, float]]:
    """{symbol: (chained %, raw %)} from the entry close to the exit close, for
    those with a close on both sessions and a price on every session between.
    The bhavcopy parser stores a figure it cannot read as blank, and one blank
    return would blank its whole group's mean."""
    out: dict[str, tuple[float, float]] = {}
    for sym in symbols:
        rows = groups.get(sym)
        if rows is None:
            continue
        lo = int(rows["date"].searchsorted(entry, side="left"))
        hi = int(rows["date"].searchsorted(exit_, side="right"))
        window = rows.iloc[lo:hi]
        if not window["close"].gt(0).all():             # blank or zero
            continue
        result = mr.chained_return(window, entry, exit_)
        if result is not None and all(math.isfinite(x) for x in result):
            out[sym] = (result[0] * 100.0, result[1] * 100.0)
    return out


def restated(chained_pct: float, raw_pct: float) -> bool:
    """PR-039's mark: NSE restated a close on the way (a split, bonus or other
    action), so the chained and the raw return differ."""
    chained, raw = 1 + chained_pct / 100.0, 1 + raw_pct / 100.0
    return abs(chained - raw) > mr.ADJUSTED_GAP * raw


def _mean(values) -> float | None:
    """The mean to two places of the values that are there; None for none."""
    values = [v for v in values if v is not None]
    return round(statistics.fmean(values), 2) if values else None


def stats(values: list[float], asked: int) -> dict:
    """n, mean and median (% to two places) of a group's returns, and how many
    of the `asked` stocks have none."""
    return {"n": len(values), "left_out": asked - len(values), "mean": _mean(values),
            "median": round(statistics.median(values), 2) if values else None}


def _minus(a, b):
    """a less b, taken from the two figures as printed."""
    return None if a is None or b is None else round(a - b, 2)


def grade_screen(groups: dict, sessions: list[date], entry: date, cands: list[dict],
                 rejected: list[str], rest: list[str]) -> tuple[dict, dict, list[dict]]:
    """(the matured horizons' figures; each candidate's return at the horizon
    the rule is read at; the candidates that moved LARGE_MOVE_PCT or more)."""
    names = [c["symbol"] for c in cands]
    half = (len(names) + 1) // 2
    sets = {"cut": names, "rest": rest, "rejected": rejected,
            "top_half": names[:half], "second_half": names[half:]}
    start = sessions.index(entry)
    out: dict[int, dict] = {}
    read_at: dict[str, float] = {}
    large: list[dict] = []
    for h in HORIZONS:
        if start + h >= len(sessions):
            continue                                    # not matured
        exit_ = sessions[start + h].isoformat()
        asked = sorted(set(names) | set(rest) | set(rejected))
        returns = forward_returns(groups, asked, entry.isoformat(), exit_)
        marked = {s for s, both in returns.items() if restated(*both)}
        row: dict = {"exit": exit_}
        for key, members in sets.items():
            have = [s for s in members if s in returns]
            row[key] = stats([returns[s][0] for s in have], len(members))
            row[key]["restated"] = len(marked.intersection(have))
        row["lead"] = _minus(row["cut"]["mean"], row["rest"]["mean"])
        row["median_gap"] = _minus(row["cut"]["median"], row["rest"]["median"])
        row["lead_without_restated"] = _minus(*(
            _mean(returns[s][0] for s in members if s in returns and s not in marked)
            for members in (names, rest)))
        out[h] = row
        if h == READ_AT:
            read_at = {s: returns[s][0] for s in names if s in returns}
            large = [{"symbol": s, "return_pct": round(returns[s][0], 1),
                      "raw_pct": round(returns[s][1], 1), "restated": s in marked}
                     for s in names
                     if s in returns and abs(returns[s][0]) >= LARGE_MOVE_PCT]
    return out, read_at, large


# ---------------------------------------------------------------------------
# Over the screens, and the rule
# ---------------------------------------------------------------------------
def _leads(values: list[float]) -> dict:
    """The screens' leads, every screen weighted equally."""
    values = [v for v in values if v is not None]
    if not values:
        return {"screens": 0}
    led = len([x for x in values if x > 0])
    return {"screens": len(values), "mean_lead": round(statistics.fmean(values), 2),
            "median_lead": round(statistics.median(values), 2),
            "led": led, "led_pct": round(100.0 * led / len(values), 1)}


def pool(screens: list[dict], horizon: int) -> dict:
    """The matured screens' leads at `horizon`, every screen weighted equally."""
    have_lead = [(s, s["horizons"][horizon]) for s in screens
                 if horizon in s["horizons"] and s["horizons"][horizon]["lead"] is not None]
    rows = [r for _, r in have_lead]
    if not rows:
        return {"screens": 0}
    leads = [r["lead"] for r in rows]
    out = _leads(leads)
    out.update({
        "cut_mean": _mean(r["cut"]["mean"] for r in rows),
        "rest_mean": _mean(r["rest"]["mean"] for r in rows),
        "cut_n": sum(r["cut"]["n"] for r in rows),
        "rest_n": sum(r["rest"]["n"] for r in rows),
        # Everything below is shown, not tested.
        "mean_median_gap": _mean(r["median_gap"] for r in rows),
        "lowest_lead": min(leads), "highest_lead": max(leads),
        "cut_restated": sum(r["cut"]["restated"] for r in rows),
        "rest_restated": sum(r["rest"]["restated"] for r in rows),
        "without_restated": _leads([r["lead_without_restated"] for r in rows]),
    })
    sizes = {f"cuts of {OLD_CUT} or fewer": [r["lead"] for s, r in have_lead
                                             if s["candidates"] <= OLD_CUT],
             f"cuts above {OLD_CUT}": [r["lead"] for s, r in have_lead
                                       if s["candidates"] > OLD_CUT]}
    if all(sizes.values()):
        out["by_cut_size"] = {label: _leads(values) for label, values in sizes.items()}
    for key in ("rejected", "top_half", "second_half"):
        have = [r for r in rows if r[key]["mean"] is not None]
        out[key] = {"screens": len(have), "n": sum(r[key]["n"] for r in have),
                    "mean": _mean(r[key]["mean"] for r in have),
                    "lead_over_rest": _mean(_minus(r[key]["mean"], r["rest"]["mean"])
                                            for r in have)}
    return out


def decide(pooled: dict) -> tuple[str, str]:
    """(verdict, why) by the rule, from the pooled figures at READ_AT."""
    n = pooled.get("screens", 0)
    if n < MIN_SCREENS:
        return UNDECIDED, f"{n} screens matured at {READ_AT} sessions; the rule needs {MIN_SCREENS}"
    mean, median, led = pooled["mean_lead"], pooled["median_lead"], pooled["led"]
    figures = (f"mean lead {mean:+.2f}, median lead {median:+.2f}, led {led} of {n} screens "
               f"({pooled['led_pct']:g}%)")
    if mean <= 0:
        return DOES_NOT, f"{figures}: the mean lead is at or below 0"
    if mean > LEAD_POINTS and median > LEAD_POINTS and led * 100 >= LED_SHARE_PCT * n:
        return CHOOSES, (f"{figures}: both leads above {LEAD_POINTS:+g} point and the cut led "
                         f"in at least {LED_SHARE_PCT}%")
    return UNDECIDED, (f"{figures}: between the two outcomes (chooses needs both leads above "
                       f"{LEAD_POINTS:+g} point and at least {LED_SHARE_PCT}% led)")


def signal_table(marked: list[tuple[dict, float, float]]) -> list[dict]:
    """For each signal, how the candidates that trailed their screen's rest
    ranked on it, beside those that did not. `marked` holds (candidate, its
    return, its screen's rest mean) at READ_AT."""
    names = sorted({k for c, _, _ in marked for k in (c.get("signal_ranks") or {})})
    table = []
    for name in names:
        sides: dict[str, list[float]] = {"trailed": [], "kept_up": []}
        for cand, ret, rest_mean in marked:
            rank = (cand.get("signal_ranks") or {}).get(name)
            if isinstance(rank, (int, float)):
                sides["trailed" if ret < rest_mean else "kept_up"].append(float(rank))
        row: dict = {"signal": name}
        for side, ranks in sides.items():
            row[side] = {
                "n": len(ranks),
                "mean_rank": round(statistics.fmean(ranks), 3) if ranks else None,
                "top_fifth_pct": round(100.0 * len([r for r in ranks if r >= TOP_FIFTH])
                                       / len(ranks), 1) if ranks else None}
        table.append(row)
    return table


# ---------------------------------------------------------------------------
# The report
# ---------------------------------------------------------------------------
def build_report(root: Path, *, end: date | None = None, book_inr: float = 1e7,
                 position_pct: float = 3.2) -> dict:
    root = Path(root)
    screens, notes = load_screens(root, end)
    report: dict = {"limits": list(LIMITS), "notes": notes, "screens": [], "pooled": {},
                    "verdict": None, "why": None, "signals": [],
                    "position_inr": round(book_inr * position_pct / 100.0, 2),
                    "position_pct": position_pct, "book_inr": book_inr}
    if not screens:
        report["error"] = "no stored weekly screen: nothing to grade"
        return report
    sessions, eod, other_rows = load_prices(root, end, min(screens))
    if len(sessions) < 2 or eod.empty:
        report["error"] = "fewer than two stored sessions: nothing to grade"
        return report
    listing = (mr._read_json(mr._resolve(root, settings.DISCOVERY_DATA_DIR) / "listing.json",
                             {}) or {}).get("securities") or None
    if listing is None:
        notes.append("no instrument listing: funds and trusts trading as EQ are not left out "
                     "of the rest")
    report["sessions_to"] = sessions[-1].isoformat()
    if other_rows:
        notes.append(f"{other_rows} price rows shared a stock's ticker and day with its equity "
                     "row (debt, block deals): only the equity row is read")
    groups = by_symbol(eod)

    # Two screen files that enter on the same session measure one window; the
    # later screen stands, so no window is weighted twice.
    entries: dict[date, tuple[date, date, bool]] = {}
    for screen_day in sorted(screens):
        record = screens[screen_day]
        if not candidates_of(record):
            notes.append(f"screen of {screen_day}: no candidates, so no cut to grade")
            continue
        if screen_day not in sessions:
            notes.append(f"screen of {screen_day}: that session is not in the price store, so "
                         "its rest cannot be told; not graded")
            continue
        ran, recorded = run_day(record, screen_day)
        entry = next((d for d in sessions if d > ran), None)
        if entry is None:
            notes.append(f"screen of {screen_day}: no session stored after its run yet")
            continue
        if entry in entries:
            notes.append(f"screen of {entries[entry][0]}: it enters on {entry}, as the screen "
                         f"of {screen_day} does; only the later one is graded")
        entries[entry] = (screen_day, ran, recorded)

    marked: list[tuple[dict, float, float]] = []
    for entry, (screen_day, ran, recorded) in sorted(entries.items()):
        record = screens[screen_day]
        cands = candidates_of(record)
        names = {c["symbol"] for c in cands}
        rejected = sorted(set(_symbols(record.get("rejected") or {})) - names)
        rest, unlisted = rest_of(groups, listing, screen_day, names | set(rejected))
        if not rest:
            notes.append(f"screen of {screen_day}: no stock inside the floors that day outside "
                         "the cut; not graded")
            continue
        horizons, read_at, large = grade_screen(groups, sessions, entry, cands, rejected, rest)
        report["screens"].append({
            "screen": screen_day.isoformat(), "ran": ran.isoformat(),
            "run_recorded": recorded, "entry": entry.isoformat(),
            "candidates": len(cands), "rest": len(rest), "rejected": len(rejected),
            "not_in_listing": unlisted, "horizons": horizons, "large_moves": large})
        if read_at:
            rest_mean = horizons[READ_AT]["rest"]["mean"]
            if rest_mean is not None:
                marked.extend((c, read_at[c["symbol"]], rest_mean) for c in cands
                              if c["symbol"] in read_at)

    unrecorded = len([s for s in report["screens"] if not s["run_recorded"]])
    if unrecorded:
        notes.append(f"{unrecorded} screens record no run day: each is taken to have run on the "
                     "Saturday after its session")
    weekday_runs = [s["screen"] for s in report["screens"]
                    if s["run_recorded"] and date.fromisoformat(s["ran"]).weekday() != 5]
    if weekday_runs:
        notes.append("run on a day other than Saturday (graded like the rest): the screens of "
                     + ", ".join(weekday_runs))
    if len({s["candidates"] > OLD_CUT for s in report["screens"]}) > 1:
        notes.append(f"the screens' cuts differ in size (above {OLD_CUT} candidates since the "
                     "cut was widened); the leads of each size are shown apart")
    report["pooled"] = {h: pool(report["screens"], h) for h in HORIZONS}
    report["verdict"], report["why"] = decide(report["pooled"][READ_AT])
    report["next_step"] = NEXT_STEP[report["verdict"]]
    report["signals"] = signal_table(marked)
    return report


def _pct(x) -> str:
    return "-" if x is None else f"{x:+.2f}"


def _group(g: dict) -> str:
    return f"{_pct(g['mean']):>7} {_pct(g['median']):>7} {g['n']:>5}"


def render(report: dict) -> str:
    out: list[str] = ["PR-041: does the weekly screen's cut choose? Graded forward from each "
                      "screen"]
    if report.get("error"):
        out.append(f"Not measured: {report['error']}.")
        out.extend(f"Note: {note}." for note in report["notes"])
        return "\n".join(out)
    out.append("cut: the screen's candidates. rest: inside the floors on the screen's date, "
               "neither a candidate nor rejected by its guards.")
    out.append("Entry: the close of the first session after the run. Returns in %, chained on "
               f"NSE's previous close. Sessions stored to {report['sessions_to']}.")
    out.append("lead: the cut's mean return less the rest's, in points. med.gap: the cut's "
               "median less the rest's (shown, not tested).")
    for note in report["notes"]:
        out.append(f"Note: {note}.")
    out.append("")
    out.append("Limits:")
    out.extend(f"  - {lim}" for lim in report["limits"])

    out.append("")
    out.append("== THE SCREENS ==")
    out.append(f"{'screen':<10} {'ran':<11} {'entry':<10} {'cut':>4} {'rest':>6} "
               f"{'rejected':>8} {'not in listing':>14}")
    for s in report["screens"]:
        ran = s["ran"] + ("" if s["run_recorded"] else "?")
        out.append(f"{s['screen']:<10} {ran:<11} {s['entry']:<10} {s['candidates']:>4} "
                   f"{s['rest']:>6} {s['rejected']:>8} {s['not_in_listing']:>14}")
    if any(not s["run_recorded"] for s in report["screens"]):
        out.append("? no run day recorded: taken as the Saturday after the screen's session.")

    for h in HORIZONS:
        out.append("")
        out.append(f"== {h} SESSIONS ==")
        rows = [s for s in report["screens"] if h in s["horizons"]]
        if not rows:
            out.append("no screen has matured")
            continue
        head = f"{'mean':>7} {'median':>7} {'n':>5}"
        out.append(f"{'':<21} | {'cut':^21} | {'rest':^21} |")
        out.append(f"{'screen':<10} {'exit':<10} | {head} | {head} | {'lead':>7} "
                   f"{'med.gap':>8} | left out (cut, rest)")
        for s in rows:
            r = s["horizons"][h]
            out.append(f"{s['screen']:<10} {r['exit']:<10} | {_group(r['cut'])} | "
                       f"{_group(r['rest'])} | {_pct(r['lead']):>7} "
                       f"{_pct(r['median_gap']):>8} | {r['cut']['left_out']}, "
                       f"{r['rest']['left_out']}")
        out.append("Shown, not tested (mean return, n):")
        for s in rows:
            r = s["horizons"][h]
            out.append("  " + s["screen"] + ": " + "; ".join(
                f"{label} {_pct(r[key]['mean'])} (n {r[key]['n']})" for key, label in
                (("top_half", "first half"), ("second_half", "second half"),
                 ("rejected", "rejected")))
                + f"; restated closes: cut {r['cut']['restated']}, rest "
                  f"{r['rest']['restated']}; lead without them "
                  f"{_pct(r['lead_without_restated'])}")

    out.append("")
    out.append("== OVER THE SCREENS, EVERY SCREEN WEIGHTED EQUALLY ==")
    for h in HORIZONS:
        p = report["pooled"][h]
        if not p["screens"]:
            out.append(f"{h:>2} sessions: 0 screens matured")
            continue
        out.append(f"{h:>2} sessions: {p['screens']} screens; mean lead {_pct(p['mean_lead'])}, "
                   f"median lead {_pct(p['median_lead'])}; the cut led {p['led']} of "
                   f"{p['screens']} ({p['led_pct']:g}%). Average of the screens' means: cut "
                   f"{_pct(p['cut_mean'])} (n {p['cut_n']}), rest {_pct(p['rest_mean'])} "
                   f"(n {p['rest_n']}).")
        w2 = p["without_restated"]
        out.append(f"    shown, not tested: the screens' leads run from {_pct(p['lowest_lead'])} "
                   f"to {_pct(p['highest_lead'])}; the gap between the two medians averaged "
                   f"{_pct(p['mean_median_gap'])}. Restated closes: {p['cut_restated']} in the "
                   f"cuts, {p['rest_restated']} in the rest"
                   + (f"; without them, mean lead {_pct(w2['mean_lead'])}, median "
                      f"{_pct(w2['median_lead'])}, led {w2['led']} of {w2['screens']}."
                      if w2["screens"] else "."))
        for label, g in (p.get("by_cut_size") or {}).items():
            out.append(f"    shown, not tested, {label}: {g['screens']} screens, mean lead "
                       f"{_pct(g['mean_lead'])}, median {_pct(g['median_lead'])}, led "
                       f"{g['led']}.")
        out.append("    shown, not tested: " + "; ".join(
            f"{label} {_pct(p[key]['mean'])} (over the rest {_pct(p[key]['lead_over_rest'])}; "
            f"{p[key]['screens']} screens, n {p[key]['n']})" for key, label in
            (("top_half", "first half"), ("second_half", "second half"),
             ("rejected", "rejected"))))

    read = report["pooled"][READ_AT]
    out.append("")
    out.append(f"== THE RULE, fixed before the data, read at {READ_AT} sessions ==")
    out.append(f"{report['verdict'].upper()}: {report['why']}.")
    out.append(f"Next: {report['next_step']}.")
    if read["screens"] and read["cut_mean"] is not None and read["rest_mean"] is not None:
        position = report["position_inr"]
        out.append(f"Money, at {READ_AT} sessions, one position of {mr._inr(position)} "
                   f"({report['position_pct']:g}% of {mr._inr(report['book_inr'])}), on the "
                   f"average of the screens' means: in a candidate "
                   f"{mr._inr(position * read['cut_mean'] / 100.0)}, in a stock of the rest "
                   f"{mr._inr(position * read['rest_mean'] / 100.0)}.")

    large = [(s["screen"], m) for s in report["screens"] for m in s["large_moves"]]
    out.append("")
    out.append(f"== CANDIDATES THAT MOVED {LARGE_MOVE_PCT:g}% OR MORE in {READ_AT} sessions "
               "(check these before trusting the means) ==")
    if not large:
        out.append("none")
    for screen, m in large:
        mark = (f" (restated close; unchained {m['raw_pct']:+.1f}%)" if m["restated"] else "")
        out.append(f"  {screen}  {m['symbol']:<12} {m['return_pct']:+.1f}%{mark}")

    out.append("")
    out.append(f"== SIGNALS at {READ_AT} sessions: candidates that trailed their screen's rest "
               "mean, beside those that did not ==")
    if not report["signals"]:
        out.append("no candidate has matured, or the screens record no signal ranks")
    for row in report["signals"]:
        parts = []
        for side, label in (("trailed", "trailed"), ("kept_up", "did not")):
            g = row[side]
            shown = ("-" if g["mean_rank"] is None else
                     f"mean rank {g['mean_rank']:.2f}, top fifth {g['top_fifth_pct']:g}%")
            parts.append(f"{label}: n {g['n']}, {shown}")
        out.append(f"  {row['signal']:<16} " + " | ".join(parts))
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--root", default=".", help="the app's folder (default: here)")
    ap.add_argument("--end", default=None, help="last session, YYYY-MM-DD (default: latest)")
    ap.add_argument("--book-inr", type=float, default=1e7)
    ap.add_argument("--position-pct", type=float, default=3.2)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    end = date.fromisoformat(args.end) if args.end else None
    report = build_report(Path(args.root), end=end, book_inr=args.book_inr,
                          position_pct=args.position_pct)
    print(json.dumps(report, indent=1, default=str) if args.json else render(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

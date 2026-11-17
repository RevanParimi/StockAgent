"""PR-039: where the funnel lost the stocks that rose, and the ones that fell.

A read-only report. For a window (default: the last 60 stored sessions) it
takes the stocks inside the screen's floors at the window's start, the 50 that
rose most and the 50 that fell most, and names for each the place in the
discovery funnel where it was lost (or kept out), with the date and the reason
on record:

  1  outside the screen's floors (the guards: traded value, free float, price,
     pledge, circuit streak, series, surveillance)
  2  inside the floors, ranked below the cut (not among the week's candidates)
  3  ranked, not analysed (a candidate the week's deep dives did not reach)
  4  analysed and turned down (not a BUY, below the conviction floor, or the
     data gate abstained), or rated BUY and turned away by the shelf's size or
     the sector cap
  5  on the shelf (or a watchlist BUY), never bought: the buy list or the buy
     step refused it, or the switch (idle-cash deployment) was off
  -  in the book: bought in the window, or held at its start

A stock's place is the furthest it got in the window; the date is the first
time it got there. A stock the guards rejected from the shortlist (place 1)
got further than one ranked below the cut (place 2): its signals ranked it
high enough, and a floor stopped it. "Rise after" is its move from that date's close to the end:
how much of the rise was still to come when the funnel had it.

Read from (all read-only; SQLite with mode=ro; nothing is written, no network,
no model call): the stored daily bhavcopy (`discovery.bhavcopy_dir`), the
weekly screens (`<discovery.data_dir>/screens/<date>_screen.json`), the score
history (every analysis, deep dives and daily reviews; the dive memo
`dives.json` stands in when it cannot be read), `shelf.json` and
`shelf_events.jsonl`, the instrument listing, and the owner's paper book
(`<portfolio.data_dir>/<default user>/transactions.jsonl` and its digests'
`deployment` records). It prints symbols, counts and rupees of the paper book
only: no user id, email, raw log or environment value.

Usage (repository root; on production from /app, at the owner's word):
    python -B scripts/missed_risers.py [--sessions 60] [--top 50]
        [--book-inr 10000000] [--position-pct 3.2] [--end YYYY-MM-DD]
        [--root DIR] [--json]
    railway ssh "cd /app && python -B scripts/missed_risers.py"
"""
from __future__ import annotations

import sys

sys.dont_write_bytecode = True     # no __pycache__ in /app either

import argparse  # noqa: E402
import json  # noqa: E402
import sqlite3  # noqa: E402
import statistics  # noqa: E402
from collections import Counter, defaultdict  # noqa: E402
from dataclasses import dataclass, field  # noqa: E402
from datetime import date, datetime, time, timedelta, timezone  # noqa: E402
from pathlib import Path  # noqa: E402

_REPO = Path(__file__).resolve().parents[1]
for _p in (str(_REPO), str(_REPO / "src")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import pandas as pd  # noqa: E402

from core.config import settings  # noqa: E402
from backend.shared.pipeline import decision_gate as dg  # noqa: E402
from core.discovery.guards import _upper_circuit_streak  # noqa: E402
from core.discovery.shelf import BUY_VERDICTS, saturday_after  # noqa: E402
from core.discovery.universe import COMPANY, instrument_kind  # noqa: E402

IST = timezone(timedelta(hours=5, minutes=30))

# Each step is (how far down the funnel, the card's place). The furthest step
# a stock reached is where it was lost. Two places have two steps: a stock the
# guards rejected from the shortlist got further than one ranked below the cut
# (its signals ranked it high enough, and a floor stopped it), and a BUY turned
# away by the shelf got further than a call the analyst turned down.
FLOORS, BELOW_CUT, GUARDED, NOT_ANALYSED, TURNED_DOWN, TURNED_AWAY, NOT_BOUGHT, IN_BOOK = (
    (10, 1), (20, 2), (25, 1), (30, 3), (40, 4), (45, 4), (50, 5), (60, 6))
UNPLACED = (0, 0)
PLACES = {
    1: "outside the screen's floors",
    2: "inside the floors, ranked below the cut",
    3: "ranked, not analysed",
    4: "analysed and turned down or turned away",
    5: "on the shelf or a watchlist BUY, never bought",
    6: "in the book",
}
# Which card addresses a place that loses more than a quarter of the risers.
CARDS = {
    1: "no card yet: the screen's floors; a change is its own card, with a money example",
    2: "no card yet: the screen's signals and weights; a change is its own card, "
       "with a money example",
    3: "PR-037 (the week's deep-dive budget)",
    4: "PR-037 (the shelf's size and the sector cap) and PR-017 (the analyst's verdicts)",
    5: "PR-038 (the entry band), PR-036 (new positions a day) and BACKLOG B-13 "
       "(no sector key named), the doors PR-035's read found",
}
LIQUIDITY_SESSIONS = 60      # guards.py: the median traded value over 60 sessions
CIRCUIT_SESSIONS = 20        # guards.py: the trailing upper-circuit streak in 20
ADJUSTED_GAP = 0.02          # chained and raw returns differ by more: a restated close
LIMITS = (
    "It is hindsight: a stock named as missed was not known to rise on the day it was lost.",
    "The window is one market period; another period can rank the places differently.",
    "The floors at the window's start are the bhavcopy's (series, price, liquidity, "
    "circuit streak) and the listing's; free float, pledge and surveillance were read "
    "only for the screen's shortlist, so a stock outside them is counted inside the "
    "floors unless a screen rejected it.",
    "A deep-dive BUY that was not shelved was turned away by the shelf's size or the "
    "sector cap; the run does not record which.",
    "Analyses are read from the score history by their time: Saturday from 12:25 IST is "
    "the weekly deep dive, a weekday from 16:25 to 23:00 IST the daily review, any other "
    "an analysis by hand or another run.",
    "Returns are chained on NSE's previous close, which NSE restates on an ex-date, so "
    "splits and bonuses do not read as moves; a session missing from the store is a "
    "move missed.",
)


# ---------------------------------------------------------------------------
# Read-only readers
# ---------------------------------------------------------------------------
def _read_json(p: Path, default=None):
    try:
        with open(p, encoding="utf-8") as fh:
            return json.load(fh)
    except FileNotFoundError:
        return default
    except (OSError, ValueError):
        return default


def _read_jsonl(p: Path) -> list[dict]:
    out: list[dict] = []
    try:
        with open(p, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except ValueError:
                    continue
                if isinstance(row, dict):
                    out.append(row)
    except (FileNotFoundError, OSError):
        pass
    return out


def _utc(stamp) -> datetime | None:
    try:
        dt = datetime.fromisoformat(str(stamp).replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _iso_day(value) -> date | None:
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def analysis_kind(at: datetime) -> str:
    """What made an analysis, from its time (the scheduler's jobs): the weekly
    deep dive (Saturday from 12:25 IST), the daily review (a weekday, 16:25 to
    23:00 IST), or an analysis by hand or another run."""
    t = at.astimezone(IST)
    if t.weekday() == 5 and t.time() >= time(12, 25):
        return "deep dive"
    if t.weekday() < 5 and time(16, 25) <= t.time() <= time(23, 0):
        return "daily review"
    return "analysis"


@dataclass
class Analysis:
    symbol: str
    at: datetime
    score: float
    verdict: str
    gate: str | None          # None: the gate could not be read
    kind: str

    @property
    def day(self) -> date:
        return self.at.astimezone(IST).date()

    def turned_down(self, floor: float) -> str:
        """Why this analysis is not an actionable BUY at the floor, or ""."""
        verdict = (self.verdict or "").strip().upper()
        if verdict not in BUY_VERDICTS:
            return f"rated {verdict or 'no verdict'} at {self.score:.2f}"
        if self.score < floor:
            return f"rated {verdict} at {self.score:.2f}, below the {floor:.2f} floor"
        if self.gate is not None and not dg.is_actionable(self.gate):
            return f"rated {verdict} at {self.score:.2f}; data gate {self.gate or 'unknown'}"
        return ""


@dataclass
class Sources:
    """Everything the report reads, loaded once."""
    sessions: list[date]
    eod: pd.DataFrame
    screens: dict[date, dict]
    listing: dict | None
    analyses: dict[str, list[Analysis]]
    analyses_read: str            # "score history", "dive memo" or "none"
    gate_read: bool
    events: list[dict]
    ideas: list[dict]
    txns: list[dict]
    deployments: dict[date, dict]
    notes: list[str] = field(default_factory=list)


def _resolve(root: Path, rel) -> Path:
    p = Path(str(rel))
    return p if p.is_absolute() else root / p


def _eod_days(eod_dir: Path) -> list[date]:
    days = []
    try:
        for p in eod_dir.glob("????-??-??.parquet"):
            d = _iso_day(p.stem)
            if d is not None:
                days.append(d)
    except OSError:
        pass
    return sorted(days)


def _load_eod(eod_dir: Path, days: list[date]) -> pd.DataFrame:
    frames = []
    for d in days:
        try:
            frames.append(pd.read_parquet(eod_dir / f"{d.isoformat()}.parquet"))
        except Exception:                                  # swallow-ok: an unreadable day is a missing session, named in the limits
            continue
    if not frames:
        return pd.DataFrame(columns=["symbol", "series", "date", "prev_close", "high",
                                     "close", "traded_value_cr"])
    df = pd.concat(frames, ignore_index=True)
    df["symbol"] = df["symbol"].astype(str).str.strip().str.upper()
    df["series"] = df["series"].astype(str).str.strip().str.upper()
    df["date"] = df["date"].astype(str).str[:10]
    return df


def _ro_db(p: Path):
    if not p.exists():
        return None
    try:
        return sqlite3.connect(p.resolve().as_uri() + "?mode=ro", uri=True)
    except sqlite3.Error:
        return None


def _read_analyses(root: Path, since: date) -> tuple[dict[str, list[Analysis]], str, bool]:
    """Every analysis from `since` (IST day) on: the score history, or the dive
    memo when the history cannot be read. Returns (by symbol, source, gate read)."""
    out: dict[str, list[Analysis]] = defaultdict(list)
    lo = datetime.combine(since, time(0, 0), tzinfo=IST).astimezone(timezone.utc)
    lo_iso = lo.replace(tzinfo=None).isoformat()
    conn = _ro_db(_resolve(root, settings.SCORE_DB_PATH))
    if conn is not None:
        rows, gate_read = None, True
        try:
            rows = conn.execute(
                "SELECT ticker, run_at, final_score, verdict, "
                "json_extract(report_json, '$.decision_gate.status') FROM score_history "
                "WHERE run_at >= ? ORDER BY run_at", (lo_iso,)).fetchall()
        except sqlite3.Error:
            gate_read = False
            try:
                rows = conn.execute(
                    "SELECT ticker, run_at, final_score, verdict, NULL FROM score_history "
                    "WHERE run_at >= ? ORDER BY run_at", (lo_iso,)).fetchall()
            except sqlite3.Error:
                rows = None
        conn.close()
        if rows is not None:
            for ticker, run_at, score, verdict, gate in rows:
                at = _utc(run_at)
                if at is None:
                    continue
                sym = str(ticker).strip().upper()
                out[sym].append(Analysis(sym, at, float(score or 0.0), str(verdict or ""),
                                         (gate or "") if gate_read else None,
                                         analysis_kind(at)))
            return out, "score history", gate_read
    memo = _read_json(_resolve(root, settings.DISCOVERY_DATA_DIR) / "dives.json", {}) or {}
    if not isinstance(memo, dict) or not memo:
        return out, "none", False
    for sym, rec in memo.items():
        if not isinstance(rec, dict):
            continue
        day = _iso_day(rec.get("date"))
        if day is None or day < since:
            continue
        # The memo keeps only the dive's day; the dive ran on that week's Saturday.
        sat = day if day.weekday() == 5 else saturday_after(day)
        at = datetime.combine(sat, time(13, 0), tzinfo=IST)
        s = str(sym).strip().upper()
        out[s].append(Analysis(s, at, float(rec.get("conviction") or 0.0),
                               str(rec.get("verdict") or ""), str(rec.get("data_gate") or ""),
                               "deep dive"))
    return out, "dive memo", True


def load_sources(root: Path, end: date | None, sessions: int) -> Sources:
    root = Path(root)
    eod_dir = _resolve(root, settings.DISCOVERY_BHAVCOPY_DIR)
    disc = _resolve(root, settings.DISCOVERY_DATA_DIR)
    book = _resolve(root, settings.PORTFOLIO_DATA_DIR) / settings.PORTFOLIO_DEFAULT_USER_ID
    all_days = _eod_days(eod_dir)
    days = [d for d in all_days if end is None or d <= end]
    # The window, the 60 sessions before its start (liquidity), and no more.
    need = sessions + 1 + LIQUIDITY_SESSIONS
    eod = _load_eod(eod_dir, days[-need:])

    screens: dict[date, dict] = {}
    try:
        for p in (disc / "screens").glob("????-??-??_screen.json"):
            d = _iso_day(p.name[:10])
            rec = _read_json(p, None)
            if d is not None and isinstance(rec, dict) and (end is None or d <= end):
                screens[d] = rec
    except OSError:
        pass

    listing = (_read_json(disc / "listing.json", {}) or {}).get("securities") or None
    since = (days[-(sessions + 1)] if len(days) > sessions
             else days[0] if days else date(2000, 1, 1))
    analyses, read_from, gate_read = _read_analyses(root, since - timedelta(days=31))

    events = []
    for e in _read_jsonl(disc / "shelf_events.jsonl"):
        at = _utc(e.get("ts"))
        if at is not None:
            e = dict(e, _at=at, symbol=str(e.get("symbol") or "").strip().upper())
            events.append(e)
    events.sort(key=lambda e: e["_at"])
    shelf = _read_json(disc / "shelf.json", {}) or {}
    ideas = [i for i in (shelf.get("ideas") or []) if isinstance(i, dict)]

    txns = _read_jsonl(book / "transactions.jsonl")
    deployments: dict[date, dict] = {}
    try:
        for p in (book / "digests").glob("????-??-??.json"):
            d = _iso_day(p.stem)
            rec = _read_json(p, {}) or {}
            if d is not None and isinstance(rec.get("deployment"), dict):
                deployments[d] = rec["deployment"]
    except OSError:
        pass
    return Sources(sessions=days, eod=eod, screens=screens, listing=listing,
                   analyses=analyses, analyses_read=read_from, gate_read=gate_read,
                   events=events, ideas=ideas, txns=txns, deployments=deployments)


# ---------------------------------------------------------------------------
# The floors, the moves and the places
# ---------------------------------------------------------------------------
def floors_out(sym_rows: pd.DataFrame, listing: dict | None, symbol: str) -> list[str]:
    """Why `symbol` is outside the screen's bhavcopy floors as of its last row
    in `sym_rows` (sorted by date, ending at the day asked), [] when inside.
    The same rules as universe.py and guards.py: series EQ, close at or above
    the price floor, a company, the 60-session median traded value at or above
    the liquidity floor, at most the allowed trailing upper-circuit streak."""
    if sym_rows.empty:
        return ["no session"]
    latest = sym_rows.iloc[-1]
    why: list[str] = []
    series = str(latest["series"])
    if series != "EQ":
        why.append(f"series {series}")
    close = float(latest["close"])
    if close < settings.DISCOVERY_MIN_PRICE:
        why.append(f"close Rs {close:.2f} below Rs {settings.DISCOVERY_MIN_PRICE:g}")
    if listing is not None:
        kind = instrument_kind(symbol, listing)
        if kind != COMPANY:
            why.append(f"listed as {kind}, not a company")
    median_tv = sym_rows.tail(LIQUIDITY_SESSIONS)["traded_value_cr"].median()
    if pd.isna(median_tv) or median_tv < settings.DISCOVERY_LIQUIDITY_FLOOR_CR:
        shown = "none" if pd.isna(median_tv) else f"Rs {float(median_tv):.1f} cr"
        why.append(f"median traded value {shown} a day, under "
                   f"Rs {settings.DISCOVERY_LIQUIDITY_FLOOR_CR:g} cr")
    streak = _upper_circuit_streak(sym_rows.tail(CIRCUIT_SESSIONS))
    if streak > settings.DISCOVERY_CIRCUIT_STREAK_MAX:
        why.append(f"upper-circuit streak of {streak}")
    return why


def chained_return(sym_rows: pd.DataFrame, start: str, end: str) -> tuple[float, float] | None:
    """(chained, raw) return from `start`'s close to `end`'s, or None without a
    close on both days. Chained: the product of close / NSE's previous close
    for every session after `start`, so a split or bonus (NSE restates the
    previous close on the ex-date) does not read as a move."""
    rows = sym_rows[(sym_rows["date"] >= start) & (sym_rows["date"] <= end)]
    if rows.empty or rows.iloc[0]["date"] != start or rows.iloc[-1]["date"] != end:
        return None
    c0 = float(rows.iloc[0]["close"])
    if c0 <= 0:
        return None
    growth, last = 1.0, c0
    for _, r in rows.iloc[1:].iterrows():
        close = float(r["close"])
        prev = r.get("prev_close")
        prev = float(prev) if prev is not None and not pd.isna(prev) and float(prev) > 0 else last
        growth *= close / prev
        last = close
    return growth - 1.0, float(rows.iloc[-1]["close"]) / c0 - 1.0


@dataclass
class Placed:
    symbol: str
    ret: float
    raw: float
    step: tuple[int, int]
    day: date | None
    reason: str
    after: float | None = None

    @property
    def adjusted(self) -> bool:
        return abs((1 + self.ret) - (1 + self.raw)) > ADJUSTED_GAP * (1 + self.raw)


def _held_at(txns: list[dict], symbol: str, before: date) -> bool:
    qty = None
    for t in txns:
        if str(t.get("symbol") or "").strip().upper() != symbol:
            continue
        d = _iso_day(t.get("date"))
        if d is None or d >= before or t.get("side") not in ("BUY", "SELL"):
            continue
        qty = float(t.get("holding_qty_after") or 0.0)
    return bool(qty and qty > 1e-9)


def _shelf_from(src: Sources, symbol: str, start: date, end: date) -> date | None:
    """The first IST day in [start, end] the stock was an active shelf idea (or
    promoted from one), from the events and shelf.json; None if never."""
    evs = [e for e in src.events if e["symbol"] == symbol]
    before = [e for e in evs if e["_at"].astimezone(IST).date() < start]
    if before:
        active = before[-1].get("event") in ("added", "redived", "promoted")
    else:
        rec = next((i for i in src.ideas
                    if str(i.get("symbol") or "").strip().upper() == symbol), None)
        added = _iso_day((rec or {}).get("added"))
        first = evs[0] if evs else None
        active = bool(rec and added and added < start and (
            first.get("event") in ("dropped", "promoted", "redived") if first
            else rec.get("status") == "active"))
    if active:
        return start
    for e in evs:
        d = e["_at"].astimezone(IST).date()
        if start <= d <= end and e.get("event") in ("added", "redived"):
            return d
    return None


def _buy_step_reason(src: Sources, symbol: str, since: date, end: date) -> str:
    """The reason on record a stock on the shelf (or a watchlist BUY) from
    `since` was not bought by `end`."""
    runs = sorted(d for d in src.deployments if since <= d <= end)
    if not runs:
        first = min(src.deployments) if src.deployments else None
        tail = f"; it first ran for the session of {first}" if first else ""
        return f"the switch was off: idle-cash deployment did not run from {since}{tail}"
    on_record = []
    for d in runs:
        for o in src.deployments[d].get("ideas") or []:
            if isinstance(o, dict) and str(o.get("symbol") or "").strip().upper() == symbol:
                on_record.append((d, o))
    if on_record:
        d, o = on_record[-1]
        why = str(o.get("why") or "").strip()
        return f"buy step, session {d}: {o.get('outcome')}" + (f" ({why[:90]})" if why else "")
    return (f"not offered by the buy list in {len(runs)} sessions with deployment on "
            f"(from {runs[0]}); the door is not recorded (PR-035's probe recomputes it)")


def place_stock(src: Sources, symbol: str, start: date, end: date,
                screens: list[date], floor: float) -> tuple[tuple[int, int], date | None, str]:
    """(step, first day there, reason on record): the furthest step down the
    funnel the stock reached in the window (the step's second item is the
    card's place)."""
    found: list[tuple[tuple[int, int], date, str]] = []

    def reach(place, day, reason):
        found.append((place, day, reason))

    rows = src.eod[src.eod["symbol"] == symbol].sort_values("date")
    for d in screens:
        rec = src.screens[d]
        cands = [str(c.get("symbol") or "").strip().upper()
                 for c in rec.get("candidates") or [] if isinstance(c, dict)]
        rejected = {str(k).strip().upper(): v for k, v in (rec.get("rejected") or {}).items()}
        if symbol in rejected:
            gates = ", ".join(str(g) for g in rejected[symbol]) or "a guard"
            reach(GUARDED, d, f"screen of {d}: shortlisted, rejected by the guards ({gates})")
        elif symbol in cands:
            rank = cands.index(symbol) + 1
            reach(NOT_ANALYSED, d, _not_analysed_reason(src, symbol, d, rank, len(cands)))
        else:
            why = floors_out(rows[rows["date"] <= d.isoformat()], src.listing, symbol)
            if why:
                reach(FLOORS, d, f"screen of {d}: {'; '.join(why)}")
            else:
                reach(BELOW_CUT, d, f"screen of {d}: not among its {len(cands)} candidates "
                                    f"(universe {rec.get('universe_size', '?')}, "
                                    f"shortlist {rec.get('shortlist_size', '?')})")

    for a in src.analyses.get(symbol, []):
        if not start <= a.day <= end:
            continue
        down = a.turned_down(floor)
        if down:
            reach(TURNED_DOWN, a.day, f"{a.kind} of {a.day}: {down}")
        elif a.kind == "deep dive":
            shelved = any(e["symbol"] == symbol and e.get("event") in ("added", "redived")
                          and e["_at"].astimezone(IST).date() == a.day for e in src.events)
            if not shelved:
                reach(TURNED_AWAY, a.day,
                      f"deep dive of {a.day}: rated {a.verdict.upper()} at {a.score:.2f}; not "
                      "shelved (the shelf's size or the sector cap; the run does not record which)")
        elif a.kind == "daily review":
            reach(NOT_BOUGHT, a.day, f"daily review of {a.day}: rated {a.verdict.upper()} at "
                                     f"{a.score:.2f}, a watchlist BUY")
        else:
            reach(TURNED_AWAY, a.day, f"analysis of {a.day}: rated {a.verdict.upper()} at "
                                      f"{a.score:.2f} outside the weekly dive and the daily "
                                      "review; nothing carries it to the buy list")

    shelf_day = _shelf_from(src, symbol, start, end)
    if shelf_day is not None:
        reach(NOT_BOUGHT, shelf_day, f"on the shelf from {shelf_day}")

    if _held_at(src.txns, symbol, start):
        reach(IN_BOOK, start, "held at the window's start")
    for t in src.txns:
        d = _iso_day(t.get("date"))
        if (str(t.get("symbol") or "").strip().upper() == symbol and t.get("side") == "BUY"
                and d is not None and start <= d <= end):
            reach(IN_BOOK, d, f"bought on {d}")
            break

    if not found:
        return UNPLACED, None, "no screen, analysis, shelf or ledger record in the window"
    best = max(p for p, _, _ in found)
    day, reason = min(((d, r) for p, d, r in found if p == best), key=lambda x: x[0])
    if best == NOT_BOUGHT:
        reason = f"{reason}; {_buy_step_reason(src, symbol, day, end)}"
    if best == IN_BOOK:
        sold = [_iso_day(t.get("date")) for t in src.txns
                if str(t.get("symbol") or "").strip().upper() == symbol
                and t.get("side") == "SELL" and float(t.get("holding_qty_after") or 0) <= 1e-9
                and _iso_day(t.get("date")) and day <= _iso_day(t.get("date")) <= end]
        if sold:
            reason += f"; sold on {max(sold)}"
    return best, day, reason


def _not_analysed_reason(src: Sources, symbol: str, d: date, rank: int, n: int) -> str:
    sat = saturday_after(d) if d.weekday() != 5 else d
    dived = {s for s, rows in src.analyses.items() for a in rows
             if a.kind == "deep dive" and a.day == sat}
    earlier = [a for a in src.analyses.get(symbol, []) if d - timedelta(days=31) <= a.day < d]
    text = (f"screen of {d}: candidate {rank} of {n}; the run of {sat} dived "
            f"{len(dived)} stocks (budget {settings.DISCOVERY_DEEP_DIVE_COUNT})")
    if earlier:
        text += f"; analysed on {earlier[-1].day}, so not dived again within 30 days"
    return text


# ---------------------------------------------------------------------------
# The report
# ---------------------------------------------------------------------------
def build_report(root: Path, *, end: date | None = None, sessions: int = 60, top: int = 50,
                 book_inr: float = 1e7, position_pct: float = 3.2) -> dict:
    src = load_sources(Path(root), end, sessions)
    floor = float(settings.DISCOVERY_MIN_CONVICTION)
    days = src.sessions
    limits = list(LIMITS)
    report: dict = {"limits": limits, "notes": src.notes, "risers": [], "fallers": [],
                    "totals": {}, "quarter_lines": []}
    if len(days) < 2:
        report["error"] = "fewer than two stored sessions: nothing to measure"
        return report
    end_day = days[-1]
    start_day = days[-(sessions + 1)] if len(days) > sessions else days[0]
    asked = start_day
    screens_all = sorted(src.screens)
    if screens_all and screens_all[0] > start_day:
        # The stored screens do not reach back that far: the window starts at
        # the first one (its session, or the last stored session before it).
        first = screens_all[0]
        start_day = max(d for d in days if d <= first) if any(d <= first for d in days) else first
    window_sessions = len([d for d in days if start_day < d <= end_day])
    screens = [d for d in screens_all if start_day <= d <= end_day]
    if not screens_all:
        src.notes.append("no stored screen: places 1 to 3 cannot be told apart")
    report["window"] = {
        "start": start_day.isoformat(), "end": end_day.isoformat(),
        "sessions": window_sessions, "asked_sessions": sessions,
        "asked_start": asked.isoformat(), "screens": len(screens),
        "first_screen": screens_all[0].isoformat() if screens_all else None,
        "analyses_from": src.analyses_read, "gate_read": src.gate_read,
        "deployment_sessions": len([d for d in src.deployments if start_day <= d <= end_day]),
        "position_inr": round(book_inr * position_pct / 100.0, 2),
        "position_pct": position_pct, "book_inr": book_inr,
    }
    if src.analyses_read != "score history":
        src.notes.append(f"analyses read from: {src.analyses_read} (the score history could "
                         "not be read; the memo keeps only the last 30 days' dives)")
    elif not src.gate_read:
        src.notes.append("the data gate could not be read from the score history: an "
                         "analysis is judged on its verdict and conviction only")

    # The population: inside the floors at the window's start, a close at both ends.
    s0, s1 = start_day.isoformat(), end_day.isoformat()
    eod = src.eod
    counts = Counter()
    moves: list[tuple[str, float, float]] = []
    for sym, rows in eod[eod["date"] <= s1].groupby("symbol"):
        rows = rows.sort_values("date")
        at_start = rows[rows["date"] <= s0]
        if at_start.empty or at_start.iloc[-1]["date"] != s0:
            counts["no session at the start"] += 1
            continue
        if floors_out(at_start, src.listing, sym):
            counts["outside the floors at the start"] += 1
            continue
        r = chained_return(rows, s0, s1)
        if r is None:
            counts["inside the floors, no close at the end"] += 1
            continue
        counts["inside the floors"] += 1
        moves.append((sym, r[0], r[1]))
    report["population"] = dict(counts)
    if src.listing is None:
        src.notes.append("no instrument listing: funds and trusts trading as EQ are not "
                         "excluded from the population")

    moves.sort(key=lambda m: (-m[1], m[0]))
    risers = moves[:top]
    rest = moves[top:]
    fallers = sorted(rest, key=lambda m: (m[1], m[0]))[:top]
    position = book_inr * position_pct / 100.0

    def placed(sym, ret, raw):
        step, day, reason = place_stock(src, sym, start_day, end_day, screens, floor)
        p = Placed(sym, ret, raw, step, day, reason)
        if day is not None:
            rows = eod[eod["symbol"] == sym].sort_values("date")
            on = rows[rows["date"] <= max(day, start_day).isoformat()]
            if not on.empty:
                r = chained_return(rows, on.iloc[-1]["date"], s1)
                p.after = r[0] if r else None
        return p

    for key, group in (("risers", risers), ("fallers", fallers)):
        rows = [placed(*m) for m in group]
        report[key] = [{
            "symbol": p.symbol, "return_pct": round(p.ret * 100, 1),
            "adjusted": p.adjusted, "place": p.step[1],
            "place_name": PLACES.get(p.step[1], "not determined"),
            "date": p.day.isoformat() if p.day else None, "reason": p.reason,
            "after_pct": round(p.after * 100, 1) if p.after is not None else None,
            "position_inr": round(position * p.ret, 0),
        } for p in rows]
        by_place: dict[int, dict] = {}
        for r in report[key]:
            t = by_place.setdefault(r["place"], {"count": 0, "inr": 0.0, "returns": []})
            t["count"] += 1
            t["inr"] += r["position_inr"]
            t["returns"].append(r["return_pct"])
        report["totals"][key] = {
            k: {"count": v["count"], "share_pct": round(100.0 * v["count"] / max(1, len(rows)), 1),
                "inr": round(v["inr"], 0), "median_return_pct": round(statistics.median(
                    v["returns"]), 1)}
            for k, v in sorted(by_place.items())}

    n = len(report["risers"])
    for place, t in report["totals"].get("risers", {}).items():
        if place in CARDS and n and t["count"] > n / 4:
            report["quarter_lines"].append(
                f"Place {place} ({PLACES[place]}) lost {t['count']} of {n} risers "
                f"({t['share_pct']:.0f}%): {CARDS[place]}.")
    return report


def _inr(x) -> str:
    try:
        v = float(x)
    except (TypeError, ValueError):
        return "?"
    sign, v = ("-" if v < 0 else ""), abs(round(v))
    s = str(int(v))
    if len(s) > 3:
        head, tail = s[:-3], s[-3:]
        parts = []
        while len(head) > 2:
            parts.insert(0, head[-2:])
            head = head[:-2]
        if head:
            parts.insert(0, head)
        s = ",".join(parts) + "," + tail
    return f"{sign}Rs {s}"


def render(report: dict) -> str:
    out: list[str] = ["PR-039: where the funnel lost the stocks that rose, and the ones that fell"]
    if report.get("error"):
        out.append(f"Not measured: {report['error']}.")
        return "\n".join(out)
    w = report["window"]
    out.append(f"Window: {w['start']} to {w['end']}, {w['sessions']} sessions "
               f"({w['screens']} weekly screens). One position: {w['position_pct']:g}% of "
               f"{_inr(w['book_inr'])} = {_inr(w['position_inr'])}.")
    if w["start"] != w["asked_start"]:
        out.append(f"The stored screens go back only to {w['first_screen']}, not "
                   f"{w['asked_sessions']} sessions (to {w['asked_start']}); the window starts "
                   "there.")
    pop = report["population"]
    out.append("Population: " + "; ".join(f"{k}: {v}" for k, v in sorted(pop.items())))
    out.append(f"Analyses read from: {w['analyses_from']}. Sessions with deployment on in the "
               f"window: {w['deployment_sessions']}.")
    for note in report["notes"]:
        out.append(f"Note: {note}.")
    out.append("Places: " + "; ".join(
        f"{k} {v}" if k in CARDS else f"book = {v}" for k, v in PLACES.items()) + ".")
    out.append("")
    out.append("Limits:")
    out.extend(f"  - {lim}" for lim in report["limits"])
    for key, title in (("risers", "THE RISERS"), ("fallers", "THE FALLERS")):
        out.append("")
        out.append(f"== {title}: the {len(report[key])} that "
                   f"{'rose' if key == 'risers' else 'fell'} most ==")
        out.append(f"{'#':>3} {'symbol':<12} {'move':>8} {'after':>8} {'place':>5}  "
                   f"{'date':<10}  reason on record")
        for i, r in enumerate(report[key], 1):
            move = f"{r['return_pct']:+.1f}%" + ("*" if r["adjusted"] else "")
            after = "-" if r["after_pct"] is None else f"{r['after_pct']:+.1f}%"
            place = str(r["place"]) if r["place"] in PLACES else "?"
            if r["place"] == 6:
                place = "book"
            out.append(f"{i:>3} {r['symbol']:<12} {move:>8} {after:>8} {place:>5}  "
                       f"{r['date'] or '-':<10}  {r['reason']}")
    out.append("")
    out.append("* the previous close was restated in the window (a split, bonus or other "
               "action): the move is chained on NSE's previous close.")
    out.append("move: the window's start to its end. after: from the date's close to the "
               "end. place and date: the furthest place the stock reached, first reached then.")
    out.append("")
    out.append("== TOTALS BY PLACE ==")
    for key, verb in (("risers", "a position would have made"),
                      ("fallers", "a position would have lost")):
        out.append(f"{key}:")
        for place, t in report["totals"].get(key, {}).items():
            name = PLACES.get(int(place), "not determined")
            out.append(f"  {place if int(place) else '?'} {name:<46} {t['count']:>3} "
                       f"({t['share_pct']:>5.1f}%)  median {t['median_return_pct']:+.1f}%  "
                       f"{verb}: {_inr(t['inr'])}")
    out.append("")
    out.append("== PLACES THAT LOST MORE THAN A QUARTER OF THE RISERS ==")
    out.extend(report["quarter_lines"] or ["none"])
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--root", default=".", help="the app's folder (default: here)")
    ap.add_argument("--end", default=None, help="last session, YYYY-MM-DD (default: latest)")
    ap.add_argument("--sessions", type=int, default=60)
    ap.add_argument("--top", type=int, default=50)
    ap.add_argument("--book-inr", type=float, default=1e7)
    ap.add_argument("--position-pct", type=float, default=3.2)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    end = date.fromisoformat(args.end) if args.end else None
    report = build_report(Path(args.root), end=end, sessions=args.sessions, top=args.top,
                          book_inr=args.book_inr, position_pct=args.position_pct)
    print(json.dumps(report, indent=1, default=str) if args.json else render(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

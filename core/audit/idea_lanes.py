"""The idea lanes: every deep dive, the screen's other candidates and the bare
model, graded against the Nifty (PR-017).

Three lanes beside `grade_shelf_lane`, whose rows stay as they are:

- `dive`: one reference per dive, `dive:<dive date>|<symbol>`, from the
  append-only dive record (`core/discovery/dive_record.py`), with the
  conviction and verdict as issued, whatever re-dives followed.
- `screen`: each screen file's candidates (`screens/<date>_screen.json`),
  `screen:<run day>|<symbol>`, with the composite rank. A candidate is
  "not_dived" when a run row of the dive record read that screen and did not
  dive it, "dived" when one did, "dived_unknown" when no run row covers it.
  The run day is the earliest such run's, else the file's `run_date`, else
  (a file written before either was recorded) the IST day the file was last
  written, which a screen file is written on once (`screen_calls`).
- `bare`: the bare model's answers (`core/discovery/bare_judge.py`),
  `bare:<dive date>|<symbol>`, BUY or SKIP with its conviction.

**Entry.** The open of the first session after the call's day (the dive's
run day, the screen's run day), the first price anyone could act at: a
Saturday dive enters at Monday's open, a dive run at 10:00 on a Monday at
Tuesday's. The call's own close is kept beside it (`reference_close`). A call
with no bar for its entry session is skipped and counted (`no_entry_price`).

**Horizons** (`audit.idea_horizons_td`, 10, 30, 60, 90 and 180 sessions)
count from the call's day, so horizon h is the close of the h-th session
after it and the return spans h sessions from the entry open. The other
lanes keep `audit.horizons_td`.

**Prices** are NSE's raw bhavcopy prices from the EOD panel discovery keeps
(550 sessions; `executable.panel_fn`). The horizon close is put into the entry
open's price basis across every bonus or split that went ex after the entry
session, with the exit grading's fail-closed rules (FIX-016, FIX-018:
`exit_shadow.horizon_in_basis` over NSE's list, `registry_break` for a
demerger or relisting the instrument registry records). Example: entered at
Rs 500, a 1:1 bonus ex 20 sessions later, Rs 260 at 30 sessions: Rs 520 in the
entry's shares, +4%, not -48%. When the basis cannot be established and no
later read can change that, the horizon is skipped and counted
(`no_exit_price`); while it may still change, it is `pending`.

**The Nifty** runs from the close of the session before the entry open to
the horizon close (BenchmarkSeries holds closes only), so the benchmark
includes one overnight move the stock's return does not. Its index level
failing is `skipped_unpriceable`, retried nightly, as in every other lane.

**Idempotent** per (reference, horizon) like every lane: the store's existing
keys are never written twice. `correct` is None: a dive is research, not a
call, and the advice report never reads these rows (`report.build_report`).

Each night reads NSE's corporate-action list for at most
`audit.idea_max_symbol_reads` new stocks (200); the others wait to the next
night as `pending`.
"""
from __future__ import annotations

import json
import logging
from datetime import date, datetime, timezone
from pathlib import Path
from typing import NamedTuple

from backend.shared.config.settings.loader import cfg
from backend.shared.schemas.audit import AuditOutcome
from core.audit.rules import excess, pct_change
from core.config import settings
from core.intelligence.rl.nse_calendar import next_trading_day, trading_days_after, trading_days_ago

logger = logging.getLogger(__name__)

IDEA_HORIZONS: tuple[int, ...] = (10, 30, 60, 90, 180)
MAX_SYMBOL_READS = 200
NOT_DIVED, DIVED, DIVED_UNKNOWN = "not_dived", "dived", "dived_unknown"


def idea_horizons() -> tuple[int, ...]:
    configured = cfg("audit.idea_horizons_td", fallback=list(IDEA_HORIZONS))
    try:
        out = tuple(int(h) for h in configured)
    except Exception:
        return IDEA_HORIZONS
    return out or IDEA_HORIZONS


def _max_reads() -> int:
    try:
        return max(0, int(cfg("audit.idea_max_symbol_reads", fallback=MAX_SYMBOL_READS)))
    except (TypeError, ValueError):
        return MAX_SYMBOL_READS


class Call(NamedTuple):
    """One graded thing: a dive, a screen candidate or a bare answer."""
    ref: str
    lane: str
    symbol: str
    issued: date                   # the call's day: the entry is the next session's open
    verdict: str = ""
    conviction: float | None = None
    graph: str = ""
    reference_close: float | None = None
    composite: float | None = None
    triggers: tuple[str, ...] = ()


class _Deferred(Exception):
    """The night's corporate-action reads are spent; try again tomorrow."""


class Prices:
    """The panel, NSE's corporate-action lists (read once per stock, at most
    `cap` stocks a night) and the Nifty, shared by the three lanes."""

    def __init__(self, *, panel, corp_actions, bench, cap: int) -> None:
        self.panel, self._corp, self.bench, self._cap = panel, corp_actions, bench, cap
        self._records: dict[str, object] = {}

    def record(self, symbol: str):
        if symbol not in self._records:
            if len(self._records) >= self._cap:
                raise _Deferred(symbol)
            from core.portfolio.exit_shadow import _actions
            self._records[symbol] = _actions(self._corp, symbol)
        return self._records[symbol]


def _default_prices(panel=None, corp_actions=None, bench=None) -> Prices:
    if panel is None:
        from core.portfolio.executable import panel_fn
        panel = panel_fn()
    if corp_actions is None:
        from core.portfolio.results import corp_actions_fn
        corp_actions = corp_actions_fn()
    if bench is None:
        from core.audit.benchmark import BenchmarkSeries
        bench = BenchmarkSeries()
    return Prices(panel=panel, corp_actions=corp_actions, bench=bench, cap=_max_reads())


def _bar(prices: Prices, symbol: str, session: date, on: date):
    """(value, status): status "" with the bar, else "pending" or "no_price"."""
    from core.portfolio.executable import PANEL_RETRY_DAYS
    bar = prices.panel(symbol, session)
    if not bar.filed:
        return None, "pending" if (on - session).days <= PANEL_RETRY_DAYS else "no_price"
    return bar, ""


def _summary() -> dict:
    """`no_entry_price` counts calls (no bar for the entry session, for good);
    `no_exit_price` and `skipped_unpriceable` count (call, horizon) pairs;
    `pending` counts waits of either kind (a file within the panel's retry
    days, a temporary basis gap, the night's reads spent)."""
    return {"graded": 0, "skipped_unpriceable": 0, "already_present": 0,
            "pending": 0, "no_entry_price": 0, "no_exit_price": 0}


def grade_calls(calls: list[Call], on: date, user_id: str, *, store, prices: Prices,
                seen: set) -> dict:
    """Grade each call's matured horizons not yet in the store. Never raises
    for one call: a bad one is counted and the next is graded."""
    from core.portfolio.executable import _Open
    from core.portfolio.exit_shadow import LASTING, horizon_in_basis, registry_break
    summary = _summary()
    horizons = idea_horizons()
    for call in calls:
        due = [h for h in horizons if (call.ref, h) not in seen]
        summary["already_present"] += len(horizons) - len(due)
        due = [h for h in due if trading_days_after(call.issued, h) <= on]
        if not due:
            continue
        entry_on = next_trading_day(call.issued)
        try:
            bar, status = _bar(prices, call.symbol, entry_on, on)
        except Exception as exc:
            logger.debug("[audit] %s %s entry unread: %s", call.lane, call.symbol, exc)
            summary["pending"] += 1
            continue
        if status == "pending":
            summary["pending"] += 1
            continue
        if status or bar.open is None:
            summary["no_entry_price"] += 1
            continue
        entry = float(bar.open)
        try:
            bench_entry = float(prices.bench.close_on(trading_days_ago(entry_on, 1)))
        except Exception as exc:
            logger.debug("[audit] %s %s: no Nifty before the entry: %s",
                         call.lane, call.symbol, exc)
            summary["skipped_unpriceable"] += len(due)
            continue
        for h in due:
            matured = trading_days_after(call.issued, h)
            try:
                hbar, hstatus = _bar(prices, call.symbol, matured, on)
                if hstatus == "pending":
                    summary["pending"] += 1
                    continue
                if hstatus or hbar.close is None:
                    summary["no_exit_price"] += 1
                    continue
                value, note, _gap, kind = horizon_in_basis(
                    _Open(float(hbar.close), matured, "nse"), prices.record(call.symbol),
                    entry_on, entry_on)
                if value is None:
                    summary["no_exit_price" if kind == LASTING else "pending"] += 1
                    continue
                if registry_break(call.symbol, entry_on, matured):
                    summary["no_exit_price"] += 1
                    continue
            except _Deferred:
                summary["pending"] += 1
                continue
            except Exception as exc:
                logger.debug("[audit] %s %s @%dtd unpriced: %s", call.lane, call.symbol, h, exc)
                summary["pending"] += 1
                continue
            try:
                bench_exit = float(prices.bench.close_on(matured))
                bench_pct = round((bench_exit / bench_entry - 1.0) * 100.0, 4)
            except Exception as exc:
                logger.debug("[audit] %s %s @%dtd: no Nifty: %s", call.lane, call.symbol, h, exc)
                summary["skipped_unpriceable"] += 1
                continue
            ret = pct_change(entry, value)
            store.append(AuditOutcome(
                ref=call.ref, lane=call.lane, user_id=user_id, symbol=call.symbol,
                verdict=call.verdict, triggers=list(call.triggers),
                issued_on=call.issued.isoformat(), horizon_td=h,
                graded_on=matured.isoformat(), entry_close=entry, exit_close=value,
                return_pct=ret, bench_entry=bench_entry, bench_exit=bench_exit,
                bench_pct=bench_pct, excess_pct=excess(ret, bench_pct), correct=None,
                graded_at=datetime.now(timezone.utc).isoformat(),
                conviction=call.conviction, graph=call.graph,
                reference_close=call.reference_close, entry_on=entry_on.isoformat(),
                basis=note, composite=call.composite))
            seen.add((call.ref, h))
            summary["graded"] += 1
    return summary


# -- the three lanes' calls ------------------------------------------------------

def _float(value) -> float | None:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if out > 0 else None


def dive_calls(record) -> list[Call]:
    out: list[Call] = []
    for row in record.dive_rows():
        try:
            issued = date.fromisoformat(str(row["dive_date"]))
            conviction = float(row["conviction"])
        except (KeyError, TypeError, ValueError):
            continue
        out.append(Call(
            ref=row["ref"], lane="dive", symbol=str(row["symbol"]), issued=issued,
            verdict=str(row.get("verdict") or ""), conviction=conviction,
            graph=str(row.get("graph") or ""), reference_close=_float(row.get("close")),
            triggers=tuple(t for t in (f"recorded:{row.get('recorded', '')}",
                                       f"kind:{row['kind']}" if row.get("kind") else "")
                           if t)))
    return out


def bare_calls(rows: list[dict], record) -> list[Call]:
    dives = {r["ref"]: r for r in record.dive_rows()}
    out: list[Call] = []
    for row in rows:
        decision = str(row.get("decision") or "")
        if not decision or row.get("conviction") is None:
            continue
        try:
            issued = date.fromisoformat(str(row["dive_date"]))
        except (KeyError, ValueError):
            continue
        dive = dives.get(f"dive:{row['dive_date']}|{row['symbol']}") or {}
        out.append(Call(
            ref=row["ref"], lane="bare", symbol=str(row["symbol"]), issued=issued,
            verdict=decision, conviction=float(row["conviction"]),
            graph=str(dive.get("graph") or ""), reference_close=_float(dive.get("close")),
            triggers=(f"model:{row.get('model', '')}",)))
    return out


def _screen_files(screens_dir: Path) -> list[Path]:
    return sorted(screens_dir.glob("*_screen.json")) if screens_dir.exists() else []


def _file_day(path: Path) -> str:
    """The IST day the file was last written; "" when unreadable."""
    from core.intelligence.rl.nse_calendar import IST
    try:
        return datetime.fromtimestamp(path.stat().st_mtime, tz=IST).date().isoformat()
    except (OSError, ValueError, OverflowError):
        return ""


def screen_calls(screens_dir: Path, record) -> list[Call]:
    """Every candidate of every screen file. The run day is the earliest run
    row's that read the screen, else the file's own `run_date`, else (a file
    written before either existed) the IST day the file was written, which a
    screen is written once on (trigger `run_day:file_time`); a run day before
    the screen's own date is not one, and that file is not graded."""
    runs: dict[str, list[dict]] = {}
    for run in record.run_rows():
        if run.get("screen_date"):
            runs.setdefault(str(run["screen_date"]), []).append(run)
    out: list[Call] = []
    for path in _screen_files(screens_dir):
        try:
            screen = json.loads(path.read_text(encoding="utf-8"))
            screen_date = str(screen["screen_date"])
        except (OSError, ValueError, KeyError, TypeError):
            continue
        covering = runs.get(screen_date, [])
        run_day = min((str(r["run_date"]) for r in covering), default="") \
            or str(screen.get("run_date") or "")
        source = []
        if not run_day:
            run_day, source = _file_day(path), ["run_day:file_time"]
        try:
            issued = date.fromisoformat(run_day)
        except ValueError:
            continue
        if run_day < screen_date:
            continue
        dived = {s for r in covering for s in (r.get("symbols") or [])}
        for cand in screen.get("candidates") or []:
            symbol = str(cand.get("symbol") or "")
            if not symbol:
                continue
            status = DIVED_UNKNOWN if not covering else DIVED if symbol in dived else NOT_DIVED
            out.append(Call(
                ref=f"screen:{run_day}|{symbol}", lane="screen", symbol=symbol, issued=issued,
                reference_close=_float(cand.get("close")),
                composite=_float(cand.get("composite")),
                triggers=(status, f"screen:{screen_date}", *source)))
    return out


def grade_idea_lanes(on: date, user_id: str, *, store=None, bench=None, base_dir: str | None = None,
                     discovery_dir: str | None = None, panel=None, corp_actions=None,
                     **_ignored) -> dict[str, dict]:
    """Grade the dive, bare and screen lanes (in that order, so the night's
    corporate-action reads go to dives first). Research is global, the audit
    store per user: like the IPO lane, only the default user's store gets
    these rows. Never raises; a failed lane reports its error."""
    from core.audit.store import AuditOutcomeStore
    from core.discovery import bare_judge
    from core.discovery.dive_record import DiveRecord

    lanes: dict[str, dict] = {}
    if user_id != settings.PORTFOLIO_DEFAULT_USER_ID:
        return {name: {**_summary(), "not_default_user": True}
                for name in ("dive", "bare", "screen")}
    store = store or AuditOutcomeStore(user_id=user_id, base_dir=base_dir)
    folder = Path(discovery_dir or settings.DISCOVERY_DATA_DIR)
    record = DiveRecord(str(folder))
    prices = _default_prices(panel, corp_actions, bench)
    seen = store.existing_keys()
    builders = (("dive", lambda: dive_calls(record)),
                ("bare", lambda: bare_calls(bare_judge.load(str(folder)), record)),
                ("screen", lambda: screen_calls(folder / "screens", record)))
    for name, build in builders:
        try:
            lanes[name] = grade_calls(build(), on, user_id, store=store, prices=prices,
                                      seen=seen)
        except Exception as exc:
            logger.warning("[audit] %s lane failed (non-fatal): %s", name, exc)
            lanes[name] = {**_summary(), "error": str(exc)}
    return lanes

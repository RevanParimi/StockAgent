"""The recorder: turn matured calls into graded outcome rows.

Idempotent by (ref, horizon_td) — safe to run nightly, safe to re-run over all
history. Never raises: a bad row is counted and skipped, exactly like
emit_alerts and ops_alerts, because telemetry must not take down the pipeline
it watches.

`price_fn` is injected rather than imported at module level. core.portfolio.
pricing imports daily_review, which imports the feedback agent and weight
adapter — so a module-level import would load the graded components at import
time. The default is resolved lazily inside _default_price_fn.
"""
from __future__ import annotations

import json
import logging
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Callable

from backend.shared.config.settings.loader import cfg
from backend.shared.schemas.audit import AuditOutcome
from core.audit.rules import excess, is_correct, pct_change
from core.config import settings
from core.intelligence.rl.nse_calendar import trading_days_after

logger = logging.getLogger(__name__)

HORIZONS: tuple[int, ...] = (10, 30, 60)


def _horizons() -> tuple[int, ...]:
    configured = cfg("audit.horizons_td", fallback=list(HORIZONS))
    try:
        return tuple(int(h) for h in configured)
    except Exception:
        return HORIZONS


def _default_price_fn(symbol: str, on: date) -> float:
    """Lazy import — see module docstring."""
    from core.portfolio.pricing import close_on
    return close_on(symbol, on)


def _user_dir(user_id: str, base_dir: str | None) -> Path:
    return Path(base_dir or settings.PORTFOLIO_DATA_DIR) / user_id


def _load_advice_rows(user_id: str, base_dir: str | None) -> list[dict]:
    path = _user_dir(user_id, base_dir) / "advice_ledger.jsonl"
    if not path.exists():
        return []
    rows: list[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except Exception:
            continue
    return rows


def _switch_excess(
    row: dict, issued: date, matured: date, bench_pct: float,
    price_fn: Callable[[str, date], float],
) -> float | None:
    """Excess return of a SWITCH's destination over the same window.

    A SWITCH says "leave X for Y". Grading only whether X fell would call a
    switch correct even when Y fell further. Returns None when there is no
    candidate or it cannot be priced — absent, never fatal, because the
    origin's grade is still valid on its own.
    """
    candidate = (row.get("switch_candidate") or "").strip()
    if not candidate:
        return None
    try:
        entry = float(price_fn(candidate, issued))
        exit_close = float(price_fn(candidate, matured))
        return excess(pct_change(entry, exit_close), bench_pct)
    except Exception:
        return None


def grade_advice_lane(
    on: date,
    user_id: str,
    *,
    store=None,
    bench=None,
    price_fn: Callable[[str, date], float] | None = None,
    base_dir: str | None = None,
) -> dict:
    """Grade every advice row whose horizon has matured on or before `on`."""
    from core.audit.benchmark import BenchmarkSeries
    from core.audit.store import AuditOutcomeStore

    store = store or AuditOutcomeStore(user_id=user_id, base_dir=base_dir)
    bench = bench or BenchmarkSeries()
    price_fn = price_fn or _default_price_fn

    seen = store.existing_keys()
    graded = skipped = already = 0

    for row in _load_advice_rows(user_id, base_dir):
        try:
            issued = date.fromisoformat(row["date"])
            symbol = row["symbol"]
            entry = float(row["close"])
            ref = f"{row['date']}|{symbol}|{row.get('rationale_hash', '')}"
        except Exception:
            skipped += 1
            continue

        for horizon in _horizons():
            if (ref, horizon) in seen:
                already += 1
                continue
            matured = trading_days_after(issued, horizon)
            if matured > on:
                continue
            try:
                exit_close = float(price_fn(symbol, matured))
                ret = pct_change(entry, exit_close)
                bench_pct = bench.pct_change(issued, matured)
                exc = excess(ret, bench_pct)
                outcome = AuditOutcome(
                    ref=ref, lane="advice", user_id=user_id, symbol=symbol,
                    verdict=row.get("verdict", ""),
                    triggers=list(row.get("triggers") or []),
                    issued_on=issued.isoformat(), horizon_td=horizon,
                    graded_on=matured.isoformat(),
                    entry_close=entry, exit_close=exit_close, return_pct=ret,
                    bench_entry=bench.close_on(issued),
                    bench_exit=bench.close_on(matured),
                    bench_pct=bench_pct, excess_pct=exc,
                    correct=is_correct(row.get("verdict", ""), exc),
                    graded_at=datetime.now(timezone.utc).isoformat(),
                    switch_excess_pct=_switch_excess(
                        row, issued, matured, bench_pct, price_fn),
                )
            except Exception as exc_err:
                logger.debug("[audit] %s @%dtd unpriceable (non-fatal): %s",
                             symbol, horizon, exc_err)
                skipped += 1
                continue
            store.append(outcome)
            seen.add((ref, horizon))
            graded += 1

    return {"graded": graded, "skipped_unpriceable": skipped,
            "already_present": already}


def _load_alert_rows(sent_log: str | None) -> list[dict]:
    if sent_log:
        path = Path(sent_log)
    else:
        path = Path(settings.DELIVERY_DATA_DIR) / "alerts_sent.jsonl"
    if not path.exists():
        return []
    rows: list[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except Exception:
            continue
    return rows


def _grade_one(
    *, ref, lane, user_id, symbol, verdict, triggers, issued, entry, horizon,
    matured, store, bench, price_fn, conviction=None,
) -> bool:
    """Mark one (ref, horizon) and append it. Returns True when a row was
    written. Never raises."""
    try:
        exit_close = float(price_fn(symbol, matured))
        ret = pct_change(entry, exit_close)
        bench_pct = bench.pct_change(issued, matured)
        exc = excess(ret, bench_pct)
        store.append(AuditOutcome(
            ref=ref, lane=lane, user_id=user_id, symbol=symbol,
            verdict=verdict, triggers=list(triggers or []),
            issued_on=issued.isoformat(), horizon_td=horizon,
            graded_on=matured.isoformat(), entry_close=entry,
            exit_close=exit_close, return_pct=ret,
            bench_entry=bench.close_on(issued),
            bench_exit=bench.close_on(matured),
            bench_pct=bench_pct, excess_pct=exc,
            correct=is_correct(verdict, exc),
            graded_at=datetime.now(timezone.utc).isoformat(),
            conviction=conviction,
        ))
        return True
    except Exception as exc_err:
        logger.debug("[audit] %s %s @%dtd ungradeable (non-fatal): %s",
                     lane, symbol, horizon, exc_err)
        return False


def grade_alert_lane(
    on: date, user_id: str, *, store=None, bench=None,
    price_fn: Callable[[str, date], float] | None = None,
    base_dir: str | None = None, sent_log: str | None = None,
) -> dict:
    """Grade alerts that carry an advice_ref. Ops alerts, index-watch and
    lock-in notices are NOT predictions and are never graded."""
    from core.audit.benchmark import BenchmarkSeries
    from core.audit.store import AuditOutcomeStore

    store = store or AuditOutcomeStore(user_id=user_id, base_dir=base_dir)
    bench = bench or BenchmarkSeries()
    price_fn = price_fn or _default_price_fn

    seen = store.existing_keys()
    graded = skipped = already = 0

    for row in _load_alert_rows(sent_log):
        ref = (row.get("advice_ref") or "").strip()
        if not ref or row.get("user_id", "") != user_id:
            continue
        try:
            issued = date.fromisoformat(row["date"])
            symbol = row["symbol"]
        except Exception:
            skipped += 1
            continue
        for horizon in _horizons():
            akey = (f"alert:{ref}", horizon)
            if akey in seen:
                already += 1
                continue
            matured = trading_days_after(issued, horizon)
            if matured > on:
                continue
            try:
                entry = float(price_fn(symbol, issued))
            except Exception:
                skipped += 1
                continue
            ok = _grade_one(
                ref=f"alert:{ref}", lane="alert", user_id=user_id,
                symbol=symbol, verdict="", triggers=[row.get("kind", "")],
                issued=issued, entry=entry, horizon=horizon, matured=matured,
                store=store, bench=bench, price_fn=price_fn,
            )
            if ok:
                seen.add(akey)
                graded += 1
            else:
                skipped += 1

    return {"graded": graded, "skipped_unpriceable": skipped,
            "already_present": already}


def grade_shelf_lane(
    on: date, user_id: str, *, store=None, bench=None,
    price_fn: Callable[[str, date], float] | None = None,
    base_dir: str | None = None, shelf_path: str | None = None,
) -> dict:
    """Grade shelf ideas for conviction calibration. `correct` is always None:
    a shelf add is a research candidate, not a call."""
    from core.audit.benchmark import BenchmarkSeries
    from core.audit.store import AuditOutcomeStore

    store = store or AuditOutcomeStore(user_id=user_id, base_dir=base_dir)
    bench = bench or BenchmarkSeries()
    price_fn = price_fn or _default_price_fn

    path = Path(shelf_path) if shelf_path else \
        Path(settings.DISCOVERY_DATA_DIR) / "shelf.json"
    if not path.exists():
        return {"graded": 0, "skipped_unpriceable": 0, "already_present": 0}
    try:
        ideas = json.loads(path.read_text(encoding="utf-8")).get("ideas", [])
    except Exception:
        return {"graded": 0, "skipped_unpriceable": 0, "already_present": 0}

    seen = store.existing_keys()
    graded = skipped = already = 0

    for idea in ideas:
        try:
            issued = date.fromisoformat(idea["added"])
            symbol = idea["symbol"]
            entry = float(idea["close_at_add"])
            conviction = float(idea.get("conviction", 0.0))
        except Exception:
            skipped += 1
            continue
        if entry <= 0:
            skipped += 1
            continue
        ref = f"shelf:{idea['added']}|{symbol}"
        for horizon in _horizons():
            if (ref, horizon) in seen:
                already += 1
                continue
            matured = trading_days_after(issued, horizon)
            if matured > on:
                continue
            ok = _grade_one(
                ref=ref, lane="shelf", user_id=user_id, symbol=symbol,
                verdict="", triggers=[], issued=issued, entry=entry,
                horizon=horizon, matured=matured, store=store, bench=bench,
                price_fn=price_fn, conviction=conviction,
            )
            if ok:
                seen.add((ref, horizon))
                graded += 1
            else:
                skipped += 1

    return {"graded": graded, "skipped_unpriceable": skipped,
            "already_present": already}


def _switch_lane_enabled() -> bool:
    return bool(cfg("audit.switch_lane_enabled", fallback=True))


def grade_switch_lane(
    on: date, user_id: str, *, store=None, bench=None,
    price_fn: Callable[[str, date], float] | None = None,
    base_dir: str | None = None,
) -> dict:
    """Grade every matured (origin, candidate) pair the advisor evaluated.

    `correct` here answers a different question from every other lane — did
    rotating beat staying — so it comes from is_switch_correct, never from
    is_correct. Both legs must price or the row is skipped: a pair graded on
    one leg is not a pair, and half a measurement is worse than none.
    """
    from core.audit.benchmark import BenchmarkSeries
    from core.audit.rules import is_switch_correct
    from core.audit.store import AuditOutcomeStore
    from core.portfolio.store import PortfolioStore

    summary = {"graded": 0, "skipped_unpriceable": 0, "already_present": 0}
    if not _switch_lane_enabled():
        return summary

    store = store or AuditOutcomeStore(user_id=user_id, base_dir=base_dir)
    bench = bench or BenchmarkSeries()
    price_fn = price_fn or _default_price_fn
    max_rows = int(cfg("audit.switch_grade_max_rows_per_run", fallback=2000))

    evals = PortfolioStore(user_id=user_id,
                           base_dir=base_dir).load_switch_evaluations()
    seen = store.existing_keys()

    for row in evals:
        if summary["graded"] >= max_rows:
            logger.info("[audit] switch lane hit the per-run cap (%d)", max_rows)
            break
        try:
            issued = date.fromisoformat(row.date)
        except Exception:
            summary["skipped_unpriceable"] += 1
            continue
        ref = f"switch:{row.date}|{row.origin}|{row.candidate}"
        for horizon in _horizons():
            if (ref, horizon) in seen:
                summary["already_present"] += 1
                continue
            matured = trading_days_after(issued, horizon)
            if matured > on:
                continue
            try:
                bench_pct = bench.pct_change(issued, matured)
                origin_exit = float(price_fn(row.origin, matured))
                dest_exit = float(price_fn(row.candidate, matured))
                origin_ret = pct_change(row.origin_close, origin_exit)
                origin_excess = excess(origin_ret, bench_pct)
                dest_excess = excess(
                    pct_change(row.candidate_close, dest_exit), bench_pct)
                outcome = AuditOutcome(
                    ref=ref, lane="switch", user_id=user_id, symbol=row.origin,
                    verdict="", triggers=[row.decision, row.reason],
                    issued_on=row.date, horizon_td=horizon,
                    graded_on=matured.isoformat(),
                    entry_close=row.origin_close, exit_close=origin_exit,
                    return_pct=origin_ret,
                    bench_entry=bench.close_on(issued),
                    bench_exit=bench.close_on(matured),
                    bench_pct=bench_pct, excess_pct=origin_excess,
                    correct=is_switch_correct(origin_excess, dest_excess),
                    graded_at=datetime.now(timezone.utc).isoformat(),
                    switch_excess_pct=dest_excess, candidate=row.candidate)
            except Exception as exc:
                logger.debug("[audit] switch %s->%s @%dtd ungradeable "
                             "(non-fatal): %s", row.origin, row.candidate,
                             horizon, exc)
                summary["skipped_unpriceable"] += 1
                continue
            store.append(outcome)
            seen.add((ref, horizon))
            summary["graded"] += 1
    return summary


def _ipo_lane_enabled() -> bool:
    return bool(cfg("audit.ipo_lane_enabled", fallback=True))


def _ipo_horizons() -> tuple[int, ...]:
    """Trading days from LISTING, not from the verdict date.

    Defaults to core.ipo.history.HORIZONS_TD rather than a second literal, so
    the audit lane and the P1 spine cannot drift apart into two curves that
    look comparable and are not. An empty or unreadable list falls back to the
    same default rather than grading nothing: silently disabling a lane whose
    own enabled flag reads true is the harder failure to notice, and
    audit.ipo_lane_enabled is the switch that exists for that.
    """
    from core.ipo.history import HORIZONS_TD
    configured = cfg("audit.ipo_horizons_td", fallback=list(HORIZONS_TD))
    try:
        out = tuple(int(h) for h in configured)
    except Exception:
        return HORIZONS_TD
    return out or HORIZONS_TD


# Horizon 1 IS the listing day — sessions.iloc[td - 1] in core/ipo/outcomes.py.
# The listing-day lean is the only claim an IPO verdict makes, so this is the
# only horizon at which `correct` can be anything but None.
IPO_LISTING_TD = 1


def _one_verdict_per_symbol(rows: list) -> tuple[list, int]:
    """(the row to grade per symbol, count superseded).

    Two reductions, and they answer different questions. Per
    (symbol, close_date) the NEWEST write wins — that is the store's own
    read rule, the post-close row superseding the T-1 one. Then per SYMBOL the
    latest close_date wins, because an extension is a new book but still the
    same listing: grading the abandoned read too would put two graded calls
    against one tape and inflate every n the visibility gate is measured on.
    """
    newest: dict = {}
    for row in rows:
        key = row.key
        prior = newest.get(key)
        if prior is None or row.written_at >= prior.written_at:
            newest[key] = row
    by_symbol: dict = {}
    superseded = 0
    for (symbol, close_date), row in newest.items():
        held = by_symbol.get(symbol)
        if held is None:
            by_symbol[symbol] = row
        elif close_date > held.verdict.close_date:
            by_symbol[symbol] = row
            superseded += 1
        else:
            superseded += 1
    return list(by_symbol.values()), superseded


def grade_ipo_lane(
    on: date, user_id: str, *, store=None, bench=None,
    price_fn: Callable[[str, date], float] | None = None,
    base_dir: str | None = None, verdicts_dir: str | None = None,
    history_store=None, cache_path: str | None = None,
) -> dict:
    """Grade the P3 IPO verdicts whose post-listing horizons have matured.

    What is scored, and what is only recorded. core/ipo/verdict.py asserts one
    direction: `short.lean` over the LISTING DAY, and only once `short.evidenced`
    is true — the T-1 lean rests on an interim book, which is explicitly not
    what the P1 spine measured. `long.lean` is hard-wired dark. So exactly one
    row per issue can carry True/False, and every other horizon is written with
    `correct=None`: the curve is kept because the LONG horizon will be asked
    about it when a second regime matures, and `metrics._scored` drops
    correct=None, so keeping it asserts no skill in the meantime.

    Entry is the ISSUE PRICE, not a close. An IPO's defining number is the move
    from what the subscriber paid to what the market said it was worth, and it
    is the anchor core/ipo/outcomes.py already measures the spine on.

    One user, not every user. A verdict is a global research output while the
    audit store is per-user, so the lane grades only for the default user;
    running it per user would write N copies of one measurement.

    Never raises, like every other lane.
    """
    from core.audit.benchmark import BenchmarkSeries
    from core.audit.rules import is_ipo_correct
    from core.audit.store import AuditOutcomeStore
    from core.ipo.listing import listing_facts
    from core.ipo.verdicts import IpoVerdictStore

    summary = {"graded": 0, "skipped_unpriceable": 0, "already_present": 0,
               "awaiting_listing": 0, "superseded": 0}
    if not _ipo_lane_enabled():
        return summary
    if user_id != settings.PORTFOLIO_DEFAULT_USER_ID:
        summary["not_default_user"] = True
        return summary

    store = store or AuditOutcomeStore(user_id=user_id, base_dir=base_dir)
    bench = bench or BenchmarkSeries()
    price_fn = price_fn or _default_price_fn
    verdicts = IpoVerdictStore(base_dir=verdicts_dir)

    rows, superseded = _one_verdict_per_symbol(verdicts.load_all())
    summary["superseded"] = superseded
    horizons = _ipo_horizons()
    seen = store.existing_keys()

    for record in rows:
        v = record.verdict
        symbol = (v.symbol or "").strip().upper()
        if not symbol:
            continue
        facts = listing_facts(symbol, history_store=history_store,
                              cache_path=cache_path)
        listed = date.fromisoformat(facts.listing_date) if facts else None
        if facts is None or listed > on:
            # Not a failure and deliberately NOT skipped_unpriceable: the
            # nightly job feeds that counter to alert_job_partial_output, and
            # every issue still awaiting its tape would read as a broken run.
            summary["awaiting_listing"] += 1
            continue

        ref = f"ipo:{v.close_date}|{symbol}"
        lean = (v.short.lean or "")
        triggers = [f"lean:{lean or 'none'}",
                    f"quadrant:{v.quadrant or 'none'}",
                    f"evidenced:{str(bool(v.short.evidenced)).lower()}"]
        for horizon in horizons:
            if (ref, horizon) in seen:
                summary["already_present"] += 1
                continue
            matured = trading_days_after(listed, horizon - 1)
            if matured > on:
                continue
            try:
                exit_close = float(price_fn(symbol, matured))
                ret = pct_change(facts.issue_price, exit_close)
                bench_pct = bench.pct_change(listed, matured)
                exc = excess(ret, bench_pct)
                correct = (is_ipo_correct(lean, exc)
                           if horizon == IPO_LISTING_TD and v.short.evidenced
                           else None)
                outcome = AuditOutcome(
                    ref=ref, lane="ipo", user_id=user_id, symbol=symbol,
                    verdict=lean, triggers=triggers,
                    issued_on=v.as_of[:10] or v.close_date,
                    horizon_td=horizon, graded_on=matured.isoformat(),
                    entry_close=facts.issue_price, exit_close=exit_close,
                    return_pct=ret,
                    bench_entry=bench.close_on(listed),
                    bench_exit=bench.close_on(matured),
                    bench_pct=bench_pct, excess_pct=exc, correct=correct,
                    graded_at=datetime.now(timezone.utc).isoformat())
            except Exception as exc_err:
                logger.debug("[audit] ipo %s @%dtd ungradeable (non-fatal): %s",
                             symbol, horizon, exc_err)
                summary["skipped_unpriceable"] += 1
                continue
            store.append(outcome)
            seen.add((ref, horizon))
            summary["graded"] += 1
    return summary


def grade_due(on: date, user_id: str | None = None, **kw) -> dict:
    """Grade every lane. A failure in one lane never stops the others."""
    uid = user_id or settings.PORTFOLIO_DEFAULT_USER_ID
    lanes: dict[str, dict] = {}
    for name, fn in (("advice", grade_advice_lane),
                     ("alert", grade_alert_lane),
                     ("shelf", grade_shelf_lane),
                     ("switch", grade_switch_lane),
                     ("ipo", grade_ipo_lane)):
        allowed = {k: v for k, v in kw.items()
                   if k in _LANE_KWARGS[name] or k in _COMMON_KWARGS}
        try:
            lanes[name] = fn(on, uid, **allowed)
        except Exception as exc:
            logger.warning("[audit] %s lane failed (non-fatal): %s", name, exc)
            lanes[name] = {"graded": 0, "skipped_unpriceable": 0,
                           "already_present": 0, "error": str(exc)}
    return {
        "graded": sum(l.get("graded", 0) for l in lanes.values()),
        "skipped_unpriceable": sum(l.get("skipped_unpriceable", 0) for l in lanes.values()),
        "already_present": sum(l.get("already_present", 0) for l in lanes.values()),
        "lanes": lanes,
    }


_COMMON_KWARGS = {"store", "bench", "price_fn", "base_dir"}
_LANE_KWARGS = {"advice": set(), "alert": {"sent_log"},
                "shelf": {"shelf_path"}, "switch": set(),
                "ipo": {"verdicts_dir", "history_store", "cache_path"}}

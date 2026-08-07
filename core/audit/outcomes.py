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

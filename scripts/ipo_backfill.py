"""PI Prospect P1 — build the historical IPO spine (design section 5, P1).

    python -m scripts.ipo_backfill --since 2024-05-01

Offline apart from one listPastIPO call and one ^NSEI download. Re-run it
freely: outcomes mature over time, so a row written today with only the 1td
and 5td horizons gains 21td next month. Rows are upserted by symbol.

WHY THE INDEX IS FETCHED ONCE: core.audit.benchmark.BenchmarkSeries fetches
per date, which is right for nightly grading of a handful of rows and wrong
here - a few hundred IPOs across six horizons would be thousands of yfinance
calls. The holiday-walkback RULE is reused; the per-date fetcher is not.
"""
from __future__ import annotations

import argparse
import json
import logging
import time
from datetime import date, datetime, timedelta
from typing import Callable

import pandas as pd

from core.ipo.history import IpoHistoryStore, IpoRecord
from core.ipo.outcomes import compute_outcomes, symbol_sessions
from services.data.fetchers.ipo_bids import fetch_bid_ladder

logger = logging.getLogger(__name__)

_INDEX_TICKER = "^NSEI"
_FETCH_PAD_DAYS = 7          # see core/audit/benchmark.py: a 1-day yfinance
                             # window returns an EMPTY frame for ^NSEI
_UPSERT_RETRIES = 5          # IpoHistoryStore.upsert rewrites the whole file
                             # every row via tmp.replace(); on a OneDrive-
                             # synced working copy that rename transiently
                             # loses a race with the sync engine's own file
                             # lock (WinError 5). Retrying the *call*, not
                             # the store, keeps the landed Task 7 interface
                             # untouched.


def _upsert_with_retry(store: IpoHistoryStore, rec: IpoRecord) -> None:
    for attempt in range(_UPSERT_RETRIES):
        try:
            store.upsert(rec)
            return
        except PermissionError:
            if attempt == _UPSERT_RETRIES - 1:
                raise
            time.sleep(0.5 * (attempt + 1))


def _load_past_ipos(since: date, until: date) -> list[dict]:
    """Normalised past-IPO records from NSE. Seam for tests."""
    from services.data.fetchers.ipo import _normalise
    from services.data.fetchers.nse_client import nse_session

    with nse_session() as nse:
        raw = nse.listPastIPO(
            datetime.combine(since, datetime.min.time()),
            datetime.combine(until, datetime.min.time()),
        )
    return _normalise(raw, "past")


def _load_tape(end: date) -> pd.DataFrame:
    """The whole bhavcopy history. Seam for tests."""
    from services.data.stores.eod_store import EodStore
    return EodStore().load_window(end=end, sessions=100_000)


def build_index_pct(start: date, end: date) -> Callable[[str, str], float]:
    """One ^NSEI download for the entire backfill window -> a local lookup.

    Walkback matches core/audit/benchmark.py: on a date with no close, stand in
    the most recent close at or BEFORE it. Never after - a future close in the
    denominator is lookahead bias in every excess figure.
    """
    import yfinance as yf

    frame = yf.download(
        _INDEX_TICKER,
        start=(start - timedelta(days=_FETCH_PAD_DAYS)).isoformat(),
        end=(end + timedelta(days=1)).isoformat(),
        progress=False, auto_adjust=True,
    )
    closes = frame["Close"]
    if hasattr(closes, "columns"):
        closes = closes.iloc[:, 0]
    closes = closes.dropna()
    series = {d.date(): float(v) for d, v in closes.items()}
    ordered = sorted(series)

    def _close_on(iso: str) -> float | None:
        target = date.fromisoformat(iso)
        if target in series:
            return series[target]
        earlier = [d for d in ordered if d <= target]
        return series[earlier[-1]] if earlier else None

    def index_pct(start_iso: str, end_iso: str) -> float:
        a, b = _close_on(start_iso), _close_on(end_iso)
        if a is None or b is None or a <= 0:
            raise ValueError(f"no {_INDEX_TICKER} close for {start_iso}..{end_iso}")
        return round((b / a - 1.0) * 100.0, 4)

    return index_pct


def run_backfill(base_dir: str | None = None, since: date | None = None,
                 on: date | None = None) -> dict:
    on = on or date.today()
    since = since or date(2024, 5, 1)      # oldest bhavcopy day on the volume
    store = IpoHistoryStore(base_dir=base_dir)

    listings = _load_past_ipos(since, on)
    tape = _load_tape(on)
    index_pct = build_index_pct(since, on)

    written = 0
    for rec in listings:
        symbol = (rec.get("symbol") or "").strip()
        if not symbol:
            continue
        sessions = symbol_sessions(tape, symbol)
        outcomes, excess, n = compute_outcomes(
            sessions, rec.get("issue_price"), index_pct)
        _upsert_with_retry(store, IpoRecord(
            symbol=symbol,
            company=rec.get("company", ""),
            listing_date=rec.get("listing_date", ""),
            issue_price=rec.get("issue_price"),
            total_x=rec.get("total_x"),
            qib_x=rec.get("qib_x"),
            retail_x=rec.get("retail_x"),
            outcomes=outcomes,
            excess=excess,
            listing_open=float(sessions["open"].iloc[0]) if n else None,
            listing_close=float(sessions["close"].iloc[0]) if n else None,
            sessions_available=n,
        ))
        written += 1

    result = {"listings": len(listings), "written": written,
              "as_of": on.isoformat(), "since": since.isoformat()}
    logger.info("[ipo_backfill] %s", result)
    return result


def enrich_predictors(store: IpoHistoryStore, symbols: set[str] | None = None,
                      sleep_s: float = 0.0) -> dict:
    """Fill in the pre-listing predictors the past-IPO feed does not carry.

    listPastIPO returns no bid data at all, so a backfilled row arrives with
    outcomes and nothing to explain them. /api/ipo-detail does serve the
    ladder for ALREADY-LISTED symbols (verified back to 2024-05-13), so the
    predictors are recoverable one symbol at a time.

    Resumable by design: rows that already carry total_x are skipped, so an
    interrupted run resumes where it stopped instead of re-spending calls.
    Reads the `combined` (all-exchange) ladder — the figure the market quotes.
    """
    import time

    rows = store.load_all()
    enriched = skipped = failed = 0
    for rec in rows:
        if symbols is not None and rec.symbol not in symbols:
            continue
        if rec.total_x is not None:
            skipped += 1
            continue
        ladder = fetch_bid_ladder(rec.symbol)
        if ladder is None:
            failed += 1
            continue
        combined = ladder.get("combined") or {}
        if combined.get("total") is None:
            # Absent stays absent, never 0 — including NSE's degenerate
            # placeholder-total stub, which parse_bid_ladder
            # (services/data/fetchers/ipo_bids.py) already nulls out at
            # the source, the single chokepoint every ladder consumer
            # passes through.
            failed += 1
            continue
        rec.total_x = combined.get("total")
        rec.qib_x = combined.get("qib")
        rec.retail_x = combined.get("retail")
        _upsert_with_retry(store, rec)
        enriched += 1
        logger.info("[ipo_backfill] enriched %s (total_x=%s) — %d done",
                    rec.symbol, rec.total_x, enriched)
        if sleep_s:
            time.sleep(sleep_s)

    result = {"enriched": enriched, "skipped": skipped, "failed": failed,
              "total": len(rows)}
    logger.info("[ipo_backfill] enrich %s", result)
    return result


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    ap = argparse.ArgumentParser(description="Build the historical IPO spine")
    ap.add_argument("--since", default="2024-05-01")
    ap.add_argument("--base-dir", default=None)
    ap.add_argument("--enrich", action="store_true",
                    help="fetch predictors per symbol (slow: one NSE call each)")
    args = ap.parse_args()
    print(json.dumps(run_backfill(base_dir=args.base_dir,
                                  since=date.fromisoformat(args.since)), indent=2))
    if args.enrich:
        print(json.dumps(enrich_predictors(IpoHistoryStore(base_dir=args.base_dir)),
                         indent=2))


if __name__ == "__main__":
    main()

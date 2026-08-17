"""PI Prospect P1/P2 — build the historical IPO spine (design section 5).

    python -m scripts.ipo_backfill --since 2024-05-01
    python -m scripts.ipo_backfill --enrich     # backfill bid predictors, one NSE call/symbol
    python -m scripts.ipo_backfill --ofs        # backfill the OFS/fresh split, one NSE call/symbol

Offline apart from one listPastIPO call and one ^NSEI download. Re-run the
base command freely: outcomes mature over time, so a row written today with
only the 1td and 5td horizons gains 21td next month, and total_x/qib_x/
retail_x/ofs_share are all carried forward from the existing row whenever the
past-IPO feed itself has nothing for them (it never does for any of them) —
a plain re-run cannot silently erase what a prior --enrich or --ofs pass
wrote. Rows are upserted by symbol.

--enrich and --ofs are each separately resumable and idempotent: both skip
rows that already carry the value, and both read-modify-write the LOADED
record rather than constructing a fresh one, so an interrupted run costs
nothing to resume and neither pass can wipe a column it did not set — the
defect class fixed in a578ac6 (an enrichment pass replacing the whole row).

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
_NSE_API_BASE = "https://www.nseindia.com/api"    # matches ipo_bids.py's _BASE
_FETCH_PAD_DAYS = 7          # see core/audit/benchmark.py: a 1-day yfinance
                             # window returns an EMPTY frame for ^NSEI
_UPSERT_RETRIES = 5          # IpoHistoryStore.upsert/upsert_many both rewrite
                             # the whole file via tmp.replace(); on a
                             # OneDrive-synced working copy that rename
                             # transiently loses a race with the sync
                             # engine's own file lock (WinError 5). Retrying
                             # the *call*, not the store, keeps the landed
                             # Task 7/9 interfaces untouched. Every call site
                             # that rewrites the file goes through _with_retry
                             # (or one of its two thin wrappers below) — a
                             # batched upsert_many() write is exactly as
                             # exposed to this failure as a single upsert().


def _with_retry(fn, *args):
    """Retry `fn(*args)` on a transient PermissionError (WinError 5, see
    _UPSERT_RETRIES). Shared by _upsert_with_retry and
    _upsert_many_with_retry so there is one retry loop, not two copies of it
    drifting apart."""
    for attempt in range(_UPSERT_RETRIES):
        try:
            return fn(*args)
        except PermissionError:
            if attempt == _UPSERT_RETRIES - 1:
                raise
            time.sleep(0.5 * (attempt + 1))


def _upsert_with_retry(store: IpoHistoryStore, rec: IpoRecord) -> None:
    _with_retry(store.upsert, rec)


def _upsert_many_with_retry(store: IpoHistoryStore, recs: list[IpoRecord]) -> int:
    return _with_retry(store.upsert_many, recs)


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

    # listPastIPO never carries bid data OR the OFS/fresh split (total_x/
    # qib_x/retail_x/ofs_share are always absent on that feed), and
    # IpoHistoryStore.upsert replaces the WHOLE row. Rebuilding straight from
    # the feed would silently discard everything enrich_predictors/enrich_ofs
    # wrote in a separate pass. So: carry each prior predictor forward
    # whenever the incoming feed row has nothing for it — ofs_share included,
    # or the very next un-flagged `--since` re-run erases every --ofs write.
    # issue_price gets the SAME treatment: the live spine already holds rows
    # with issue_price null (a vintage genuinely served no price), which
    # proves a later vintage can drop the price for a symbol that used to
    # have one. issue_price is not recoverable from the tape, and
    # compute_outcomes refuses to compute outcomes/excess without it — so
    # losing it here silently destroys a whole row's outcome curve, not just
    # one field.
    prior = {r.symbol: r for r in store.load_all()}

    written = 0
    for rec in listings:
        symbol = (rec.get("symbol") or "").strip()
        if not symbol:
            continue
        p = prior.get(symbol)
        # Resolved BEFORE compute_outcomes, not just at storage time: a price
        # dropped by this vintage but carried forward from `p` must still
        # feed the outcomes/excess calculation below, or the stored
        # issue_price would look correct while outcomes/excess were computed
        # (and re-persisted) against a None price — i.e. still wiped.
        issue_price = (rec.get("issue_price") if rec.get("issue_price") is not None
                      else (p.issue_price if p else None))
        sessions = symbol_sessions(tape, symbol)
        outcomes, excess, n = compute_outcomes(
            sessions, issue_price, index_pct)
        _upsert_with_retry(store, IpoRecord(
            symbol=symbol,
            company=rec.get("company", ""),
            listing_date=rec.get("listing_date", ""),
            issue_price=issue_price,
            total_x=rec.get("total_x") if rec.get("total_x") is not None
                    else (p.total_x if p else None),
            qib_x=rec.get("qib_x") if rec.get("qib_x") is not None
                    else (p.qib_x if p else None),
            retail_x=rec.get("retail_x") if rec.get("retail_x") is not None
                    else (p.retail_x if p else None),
            ofs_share=rec.get("ofs_share") if rec.get("ofs_share") is not None
                    else (p.ofs_share if p else None),
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


def _fetch_issue_info(symbol: str) -> dict | None:
    """One symbol's `issueInfo` from live NSE /api/ipo-detail, or None on any
    failure. Seam for tests, same role as fetch_bid_ladder plays for
    enrich_predictors."""
    from services.data.fetchers.nse_client import nse_session

    try:
        with nse_session() as nse:
            # _req(), not _session.get(): it applies the process-wide
            # mthrottle shared by every other NSE call site (see
            # fetch_bid_ladder in services/data/fetchers/ipo_bids.py for why
            # going around it would be unsafe in a per-symbol loop).
            resp = nse._req(f"{_NSE_API_BASE}/ipo-detail",
                            params={"symbol": symbol, "series": "EQ"})
            return resp.json().get("issueInfo")
    except Exception as exc:
        logger.warning("[ipo_backfill] ofs fetch failed for %s (non-fatal): %s",
                      symbol, exc)
        return None


_OFS_FLUSH_EVERY = 25        # rows per upsert_many flush during --ofs. Keeps
                             # the batching win that motivated upsert_many
                             # (a handful of rewrites over ~200 rows, not
                             # 200) while making resumability real: an
                             # interruption loses at most one in-flight batch
                             # (< 25 rows re-fetched next run), not the whole
                             # pass — see test_enrich_ofs_flushes_progress_
                             # before_a_later_failure for the proof.


def enrich_ofs(store: IpoHistoryStore, symbols: set[str] | None = None,
               limit: int | None = None) -> dict:
    """Fill ofs_share on rows that lack it, one /api/ipo-detail call per row.

    Spec section 3 calls the OFS share "the single strongest Ola/Ather
    discriminator" and, unlike GMP, it is disclosed, official, and free.

    Mutates each LOADED IpoRecord in place — never builds a fresh one. The
    detail feed carries no bid data at all, so constructing a new record here
    would wipe every predictor P1 measured (total_x/qib_x/retail_x/outcomes/
    excess/...); that exact defect class was fixed in a578ac6 and must not
    return.

    Resumable for real: progress is flushed to disk via
    `_upsert_many_with_retry` every `_OFS_FLUSH_EVERY` rows (plus a final
    flush for the remainder), not only once at the very end. That keeps the
    batching win upsert_many exists for — a handful of file rewrites over
    ~200 rows, not 200 one-row rewrites, the O(n²) problem §9b flags — while
    making "resumable" actually true: an interrupted run keeps every row
    flushed before the interruption (so it is skipped on the next call,
    `ofs_share` already set) and only re-fetches the rows in whatever batch
    was still in flight, not the whole pass. A live run is ~200 throttled
    NSE calls, so losing partial progress to an interruption is a real, not
    theoretical, cost.

    Each flush goes through the SAME transient-PermissionError retry as
    run_backfill/enrich_predictors' per-row upsert() — this working copy is
    OneDrive-synced, and tmp.replace() transiently raises WinError 5 on a
    sync-engine lock race. Without the retry, one of those (routine) races
    would kill the whole ~200-call throttled pass rather than just costing
    a brief sleep-and-retry.
    """
    from services.data.fetchers.ipo_offer import parse_offer_split

    pending = [r for r in store.load_all() if r.ofs_share is None]
    if symbols is not None:
        pending = [r for r in pending if r.symbol in symbols]
    if limit:
        pending = pending[:limit]

    batch: list[IpoRecord] = []
    written = 0
    failed = 0
    for rec in pending:
        issue_info = _fetch_issue_info(rec.symbol)
        if issue_info is None:
            failed += 1
            continue
        split = parse_offer_split(issue_info, issue_price=rec.issue_price)
        if split["ofs_share"] is None:
            failed += 1
            continue
        rec.ofs_share = split["ofs_share"]     # mutate the LOADED row, never rebuild
        batch.append(rec)
        logger.info("[ipo_backfill] ofs %s -> %.4f", rec.symbol, rec.ofs_share)
        if len(batch) >= _OFS_FLUSH_EVERY:
            written += _upsert_many_with_retry(store, batch)
            batch = []

    if batch:
        written += _upsert_many_with_retry(store, batch)

    result = {"updated": written, "failed": failed, "pending": len(pending)}
    logger.info("[ipo_backfill] ofs %s", result)
    return result


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    ap = argparse.ArgumentParser(description="Build the historical IPO spine")
    ap.add_argument("--since", default="2024-05-01")
    ap.add_argument("--base-dir", default=None)
    ap.add_argument("--enrich", action="store_true",
                    help="fetch predictors per symbol (slow: one NSE call each)")
    ap.add_argument("--ofs", action="store_true",
                    help="fetch the OFS/fresh split per symbol (slow: one NSE call each)")
    args = ap.parse_args()
    print(json.dumps(run_backfill(base_dir=args.base_dir,
                                  since=date.fromisoformat(args.since)), indent=2))
    if args.enrich:
        print(json.dumps(enrich_predictors(IpoHistoryStore(base_dir=args.base_dir)),
                         indent=2))
    if args.ofs:
        print(json.dumps(enrich_ofs(IpoHistoryStore(base_dir=args.base_dir)),
                         indent=2))


if __name__ == "__main__":
    main()

"""
The daily company-event feed: what happened to each stock users hold, watch
or have on the shelf, typed, dated and sourced (KT section 4).

A run (08:15 and 18:30 IST on trading days, `run_event_feed`):

1. **Stocks.** Every active user's holdings, then watchlists, then the active
   shelf ideas, each stock once, at most `events.max_symbols`. A stock whose
   identity the instrument registry does not resolve on the day (a retired or
   demerged ticker, an unreviewed mapping) is skipped and named. NSE is asked
   for the registry's NSE code (TVSMOTORS is filed as TVSMOTOR); events are
   stored under the app's symbol.
2. **Items.** NSE announcements filed in the last `events.lookback_days` and
   board meetings filed in that window (core/events/sources.py), then one
   company-news search while the day's budget lasts. Each run may use half of
   `events.news_queries_per_day`, in stock order; a spent Serper credit stops
   the run's searches.
3. **New items only.** An item whose id is stored, or which the classifier
   judged "not about this company" in the last `events.seen_days`, is not
   sent again. At most `events.max_items_per_symbol` per stock, newest first.
4. **Typed** in calls of `events.max_items_per_call` (core/events/classify.py),
   and stored once per id (core/events/store.py).
5. **Same-day dossier knowledge.** A newly stored NSE announcement whose
   subject the event ingestor qualifies (results, concall, guidance, investor
   presentation) runs that ingestor for the stock in this run, under its
   managed sector, instead of waiting for Saturday. Only enabled managed
   stocks have a dossier; another stock's event is stored and not ingested.
   The ingestor keeps its own watermark, so Saturday's scan skips it.

**One clock read per stock.** A run of 50 stocks can last more than 10
minutes, so the clock is read for each stock when its fetches return. NSE
times are checked against that moment, news ages count back from it, and it
is the stock's `fetched_at`. A readable NSE time more than 10 minutes after it
(NSE's clock running ahead) is left for a later run and counted, never stored
undated.

**Failures.** A source failure, a spent credit or a classifier failure is
logged and skipped; nothing is marked seen, so the next run asks again. The
run never raises. Its record (`data/events/runs.jsonl`) says how many stocks,
searches and calls it used, and what it stored and dropped. It names stocks,
never users.

**Example.** On Tue 27 Oct MARUTI's board approves Q2 results and NSE shows
the filing at 27-Oct-2026 18:41:20. The 18:30 run tracks 50 stocks and
reaches MARUTI at 18:42; its fetches return the filing and two articles at
18:42:05, and the classifier types the filing as results, positive, high. It
is stored with `published_at` 2026-10-27T18:41:20+05:30 and `fetched_at`
2026-10-27T18:42:05+05:30. MARUTI is managed under automobile, so the
ingestor runs for it in the same run. At 08:15 the next day the filing is
fetched again and not sent again.
"""
from __future__ import annotations

import logging
import math
from datetime import datetime, timedelta

from core.config import settings
from core.events.classify import classify_items
from core.events.sources import (
    IST, NSE_ANNOUNCEMENT, announcement_items, board_meeting_items, mentions_company,
    name_phrases, news_items,
)
from core.events.store import EventStore, valid_symbol

logger = logging.getLogger(__name__)

GROUPS = ("held", "watched", "shelf")


# ---------------------------------------------------------------------------
# Seams (tests replace these; each is the only call to its outside system)
# ---------------------------------------------------------------------------

def _clock() -> datetime:
    """The time now, in IST."""
    return datetime.now(IST)


def tracked_symbols() -> list[tuple[str, str]]:
    """(symbol, group) for every stock an active user holds, then watches,
    then every active shelf idea; each stock once, in that order, sorted
    within a group. Reads the user plane; returns market symbols only."""
    from core.discovery.shelf import ShelfStore
    from core.portfolio.store import PortfolioStore, active_user_ids

    held: set[str] = set()
    watched: set[str] = set()
    for user_id in active_user_ids():
        try:
            portfolio = PortfolioStore(user_id=user_id).load()
        except Exception as exc:
            logger.warning("[events] a portfolio could not be read, its stocks skipped: %s", exc)
            continue
        held |= {h.symbol.strip().upper() for h in portfolio.holdings if h.symbol}
        watched |= {w.symbol.strip().upper() for w in portfolio.watchlist if w.symbol}
    shelf: set[str] = set()
    try:
        shelf = {i.symbol.strip().upper() for i in ShelfStore().load().ideas
                 if i.status == "active" and i.symbol}
    except Exception as exc:
        logger.warning("[events] shelf unreadable, its ideas skipped: %s", exc)
    out: list[tuple[str, str]] = []
    seen: set[str] = set()
    for group, symbols in zip(GROUPS, (held, watched, shelf)):
        for symbol in sorted(symbols):
            if symbol not in seen:
                seen.add(symbol)
                out.append((symbol, group))
    return out


def _identity_issue(symbol: str, on) -> str:
    from core.portfolio.identity_reconcile import symbol_identity_issue
    return symbol_identity_issue(symbol, on)


def _nse_code(symbol: str, on) -> str:
    from backend.shared.data.fetchers.symbol_resolver import nse_symbol
    return nse_symbol(symbol, on)


def _make_nse():
    from services.data.fetchers.nse_client import make_nse
    return make_nse()


def _close_nse(nse) -> None:
    from services.data.fetchers.nse_client import close_nse
    close_nse(nse)


def _fetch_filings(nse, code: str, since, until) -> dict:
    from services.data.fetchers.nse_announcements import fetch_company_filings
    return fetch_company_filings(nse, code, since, until)


def _news_query(symbol: str) -> tuple[str, str]:
    from services.data.fetchers.news import company_news_query
    return company_news_query(symbol)


def _search_news(query: str) -> tuple[list[dict], str]:
    from services.data.fetchers.news import search_serper_news_status
    return search_serper_news_status(query, n=settings.EVENTS_NEWS_ARTICLES_PER_QUERY,
                                     geo="in", tbs=settings.EVENTS_NEWS_RECENCY or None)


def _qualifies_for_ingest(subject: str) -> bool:
    from core.intelligence.rl.agents.event_ingestor import _is_qualifying
    return _is_qualifying(subject)


def _managed_enabled_sectors() -> dict[str, str]:
    from services.api.log_buffer import get_active_tickers_with_sector
    return {str(e["sym"]).strip().upper(): e.get("sector") or "automobile"
            for e in get_active_tickers_with_sector()}


def _ingest(symbol: str, sector: str) -> int:
    from core.intelligence.rl.agents.event_ingestor import EventIngestor
    return EventIngestor().run(symbol, sector)


def _search_usage() -> dict:
    from services.data.stores.api_usage import get_usage
    return get_usage().get("serper", {})


# ---------------------------------------------------------------------------
# The run
# ---------------------------------------------------------------------------

def _new_record(slot: str, now: datetime) -> dict:
    return {
        "slot": slot, "started_at": now.isoformat(timespec="seconds"), "status": "ok",
        "symbols_tracked": 0, "by_group": {g: 0 for g in GROUPS}, "symbols_used": 0,
        "symbols_over_cap": 0, "identity_skipped": {}, "invalid_symbols": [],
        "nse_failed": {}, "nse_rows_foreign": 0, "nse_rows_ahead": 0,
        "news_cap_today": settings.EVENTS_NEWS_QUERIES_PER_DAY, "news_queries_before": 0,
        "news_run_budget": 0, "news_queries_used": 0, "news_not_searched": 0,
        "news_failed": {}, "news_exhausted": False, "news_unmatched": 0,
        "items_fetched": 0, "items_new": 0, "items_over_cap": 0,
        "llm_calls": 0, "llm_failed": 0, "events_stored": 0, "events_ungrounded": 0,
        "events_invalid": 0, "events_duplicate": 0, "items_unrelated": 0,
        "ingest": {}, "ingest_not_managed": [], "error": None,
    }


def run_event_feed(slot: str = "manual", now: datetime | None = None,
                   store: EventStore | None = None, clock=None) -> dict:
    """One feed run; returns its record (also appended to runs.jsonl).
    Never raises.

    `clock()` is read once per stock, when its fetches return (module
    docstring). It is the wall clock by default; a replay at a fixed `now`
    reads `now` for every stock unless it passes a clock."""
    if clock is None:
        start = now
        clock = _clock if start is None else (lambda: start)
    now = (now or clock()).astimezone(IST)
    rec = _new_record(slot, now)
    if not settings.EVENTS_ENABLED:
        rec["status"] = "disabled"
        return rec
    store = store or EventStore()
    try:
        _run(rec, now, clock, store)
    except Exception as exc:
        logger.error("[events] run failed: %s", exc, exc_info=True)
        rec["status"], rec["error"] = "failed", repr(exc)[:300]
    rec["finished_at"] = clock().astimezone(IST).isoformat(timespec="seconds")
    try:
        store.append_run(rec)
    except Exception as exc:
        logger.warning("[events] run record not written: %s", exc)
    return rec


def _run(rec: dict, now: datetime, clock, store: EventStore) -> None:
    on = now.date()
    tracked = tracked_symbols()
    rec["symbols_tracked"] = len(tracked)
    plan: list[str] = []
    for symbol, group in tracked:
        rec["by_group"][group] = rec["by_group"].get(group, 0) + 1
        if not valid_symbol(symbol):
            rec["invalid_symbols"].append(symbol[:30])
            continue
        issue = _identity_issue(symbol, on)
        if issue:
            rec["identity_skipped"][symbol] = issue[:200]
            continue
        plan.append(symbol)
    cap = max(0, settings.EVENTS_MAX_SYMBOLS)
    rec["symbols_over_cap"] = max(0, len(plan) - cap)
    plan = plan[:cap]
    rec["symbols_used"] = len(plan)

    state = store.load_state()
    daily = max(0, settings.EVENTS_NEWS_QUERIES_PER_DAY)
    before = state["queries"]["used"] if state["queries"]["day"] == on.isoformat() else 0
    rec["news_queries_before"] = before
    budget = max(0, min(daily - before, math.ceil(daily / 2)))
    rec["news_run_budget"] = budget

    since = on - timedelta(days=max(1, settings.EVENTS_LOOKBACK_DAYS))
    trigger: set[str] = set()
    nse = None
    try:
        nse = _make_nse()
    except Exception as exc:
        logger.warning("[events] NSE client unavailable, filings skipped this run: %s", exc)
        rec["nse_failed"]["*"] = f"client: {exc}"[:200]
    try:
        for symbol in plan:
            try:
                if _one_symbol(symbol, on, since, clock, nse, store, state, rec):
                    trigger.add(symbol)
            except Exception as exc:
                logger.warning("[events] %s skipped this run: %s", symbol, exc, exc_info=True)
                rec["nse_failed"].setdefault(symbol, f"run: {exc}"[:200])
    finally:
        if nse is not None:
            _close_nse(nse)
        state["queries"] = {"day": on.isoformat(), "used": before + rec["news_queries_used"]}
        store.save_state(state, on, settings.EVENTS_SEEN_DAYS)

    if trigger and settings.EVENTS_INGEST_ON_RESULTS:
        _trigger_ingest(sorted(trigger), rec)
    if rec["nse_failed"] or rec["news_failed"] or rec["llm_failed"]:
        rec["status"] = "partial"
    try:
        usage = _search_usage()
        rec["serper_month_calls"] = usage.get("calls")
        logger.info("[events] search usage: %d news queries this run, %d of %d today; "
                    "Serper this month %s of %s", rec["news_queries_used"],
                    before + rec["news_queries_used"], daily, usage.get("calls"), usage.get("limit"))
    except Exception as exc:
        logger.warning("[events] search usage unreadable: %s", exc)
    logger.info("[events] %s run: %d of %d stocks, %d new items, %d events stored, "
                "%d classifier calls (%d failed), status %s", rec["slot"], rec["symbols_used"],
                rec["symbols_tracked"], rec["items_new"], rec["events_stored"], rec["llm_calls"],
                rec["llm_failed"], rec["status"])


def _one_symbol(symbol: str, on, since, clock, nse, store: EventStore, state: dict,
                rec: dict) -> bool:
    """Fetch, classify and store one stock's new items. True when a newly
    stored NSE announcement qualifies for the dossier ingestor."""
    code = _nse_code(symbol, on)
    filings = None
    if nse is not None:
        filings = _fetch_filings(nse, code, since, on)
        if filings.get("error"):
            rec["nse_failed"][symbol] = str(filings["error"])[:200]
    query, company = _news_query(symbol)
    results = None
    if rec["news_queries_used"] < rec["news_run_budget"] and not rec["news_exhausted"]:
        results, status = _search_news(query)
        rec["news_queries_used"] += 1
        if status == "exhausted":
            rec["news_exhausted"] = True
        if status not in ("ok", "empty"):
            rec["news_failed"][symbol] = status
    else:
        rec["news_not_searched"] += 1

    # This stock's fetches have returned: every time below is read against now.
    now = clock().astimezone(IST)
    items = []
    names: list[str] = []
    if filings is not None:
        ann, foreign_a, ahead_a = announcement_items(filings.get("announcements") or [], code, now)
        bms, foreign_b, ahead_b = board_meeting_items(filings.get("board_meetings") or [], code,
                                                      now, since)
        rec["nse_rows_foreign"] += foreign_a + foreign_b
        rec["nse_rows_ahead"] += ahead_a + ahead_b
        items += ann + bms
        names += _nse_names(filings, code)
    if company:
        names.insert(0, company)
    if results is not None:
        news = news_items(results, now)
        phrases = name_phrases(names)
        kept = [n for n in news if mentions_company(n, phrases, {symbol, code})]
        rec["news_unmatched"] += len(news) - len(kept)
        items += kept

    unique = {}
    for item in items:
        unique.setdefault(item.source_id, item)
    rec["items_fetched"] += len(unique)
    known = store.known_ids(symbol)
    seen = state["seen"].setdefault(symbol, {})
    new = [i for i in unique.values() if i.source_id not in known and i.source_id not in seen]
    new.sort(key=lambda i: (i.published_at is not None, i.published_at or ""), reverse=True)
    limit = max(0, settings.EVENTS_MAX_ITEMS_PER_SYMBOL)
    rec["items_over_cap"] += max(0, len(new) - limit)
    new = new[:limit]
    rec["items_new"] += len(new)

    qualifies = False
    fetched_at = now.isoformat(timespec="seconds")
    size = max(1, settings.EVENTS_MAX_ITEMS_PER_CALL)
    for start in range(0, len(new), size):
        batch = new[start:start + size]
        result = classify_items(symbol, names[0] if names else symbol, batch,
                                fetched_at=fetched_at)
        rec["llm_calls"] += 1
        if result.failed:
            rec["llm_failed"] += 1
            continue
        stored = store.append_new(symbol, result.events)
        rec["events_stored"] += len(stored)
        rec["events_ungrounded"] += result.ungrounded
        rec["events_invalid"] += result.invalid
        rec["events_duplicate"] += result.duplicate
        rec["items_unrelated"] += len(result.unrelated)
        for source_id in result.unrelated:
            seen[source_id] = on.isoformat()
        for event in stored:
            day = event.published_day()
            if (event.source == NSE_ANNOUNCEMENT and day and day <= on.isoformat()
                    and _qualifies_for_ingest(event.title)):
                qualifies = True
    if not seen:
        state["seen"].pop(symbol, None)
    return qualifies


def _nse_names(filings: dict, code: str) -> list[str]:
    """The company's official name from its own NSE rows (`sm_name`), at most one."""
    for row in (filings.get("announcements") or []) + (filings.get("board_meetings") or []):
        if not isinstance(row, dict):
            continue
        if str(row.get("symbol") or row.get("bm_symbol") or "").strip().upper() != code.upper():
            continue
        name = str(row.get("sm_name") or "").strip()
        if name:
            return [name]
    return []


def _trigger_ingest(symbols: list[str], rec: dict) -> None:
    """Run the dossier ingestor now for each stock with a new qualifying
    filing, under its managed sector. A stock that is not an enabled managed
    stock has no dossier and is only named."""
    try:
        sectors = _managed_enabled_sectors()
    except Exception as exc:
        logger.warning("[events] managed list unreadable, no ingestion this run: %s", exc)
        rec["ingest_not_managed"] = list(symbols)
        return
    for symbol in symbols:
        sector = sectors.get(symbol)
        if not sector:
            rec["ingest_not_managed"].append(symbol)
            continue
        try:
            rec["ingest"][symbol] = int(_ingest(symbol, sector))
        except Exception as exc:
            logger.warning("[events] %s: ingestion failed: %s", symbol, exc)
            rec["ingest"][symbol] = f"failed: {exc}"[:120]
        logger.info("[events] %s: same-day ingestion under %s -> %s", symbol, sector,
                    rec["ingest"][symbol])

"""
The discovery screen's `insider_buying` signal: what each company's promoter
group and directors bought and sold in the market over the last
`discovery.insider_window_days` (28), from NSE's insider-trade filings
(services/data/fetchers/nse_disclosures.py, read by core/events/disclosures.py).

`refresh_insider_trades(on)` runs once per discovery cycle. It lists every
company's filings disseminated in the window and reads the XBRL of each filing
not read before, at most `discovery.insider_max_documents` (600) a run. It
keeps each filing in data/discovery/insider_trades.json: the symbol, the
dissemination time, whether NSE lists it as a revision, and each person's
trade without the name. Filings that left the window are dropped. It then
stores each company's open-market net in rupees: bought minus sold by the
promoter group and directors; employees and off-market moves count nothing.

**Each trade once, in the window of its trade day.** NSE lists a corrected
filing as a new filing and rarely says which one it corrects. So filings are
taken in dissemination order. An original's trades are all kept: two persons
can make the same trade on the same day. Each trade of a revision replaces
the closest earlier trade of the same company with the same action and share
count; revisions correct values, categories and days, so those may differ.
A revision's trade that matches none is new. A trade then counts only when
its last trade day falls in the window, so a revision disseminated now of a
trade made in August counts nothing.

**The 75% rule.** A company whose promoters hold more than 75% must sell to
keep 25% public, so the event feed calls such a promoter-group sale neutral
(core/events/disclosures.py). For each company with a counted promoter-group
market sale, the run reads the latest promoter share from NSE's shareholding
list. Above 75%, those sales count nothing; directors' trades still count. A
share NSE does not give leaves the sale counted, as the event does.

**Available or not.** The signal is computed only when the list was read,
every filing on it was read and every needed promoter share was read, and the
list is at most 7 days old and not newer than the screen day. A filing missed
would rank its company as one nobody traded. A document that is not an
insider filing, or whose promoter or director market trade has no day,
counts nothing and is named; if more than a tenth are like that, NSE's format
has probably changed and the signal is unavailable too. Unavailable means
left out of the composite and named, never a neutral score; the cache keeps
what was read for the next run.

**Example.** In the 28 days to 23 Oct NSE lists 351 filings; last week's run
read 120 of them. This run reads the other 231. Company A's promoters bought
₹4.2 crore in the market and sold nothing: A scores 4.2. Company B's directors
sold ₹1.1 crore: -1.1. Company C's promoters filed a ₹36 lakh purchase, then
a revision that only corrects the filing date: it counts once, 0.36. A
company with no filing scores 0. The screen ranks these values like any
other signal.
"""
from __future__ import annotations

import json
import logging
from datetime import date, datetime, timedelta
from pathlib import Path

import pandas as pd

from core.config import settings
from core.events.disclosures import (
    MPS_PROMOTER_CAP, Trade, insider_id, is_revision, market_net, parse_pit_xml,
    quarters_from_list,
)
from core.events.sources import IST, nse_stamp
from core.utils.atomic_io import atomic_write_json

logger = logging.getLogger(__name__)

_MAX_UNREADABLE_SHARE = 0.10
_MAX_AGE_DAYS = 7
_TRADE_FIELDS = ("who", "action", "market", "shares", "value_inr", "from_day", "to_day")
# A revision's trade replaces an earlier one with the same action and share
# count; among several, the one that agrees on most of these fields, then the
# latest.
_MATCH_FIELDS = ("who", "market", "value_inr", "from_day", "to_day")


def _path() -> Path:
    return Path(settings.DISCOVERY_DATA_DIR) / "insider_trades.json"


# Seams: each is the only call to its outside system.
def _make_nse():
    from services.data.fetchers.nse_client import make_nse
    return make_nse()


def _close_nse(nse) -> None:
    from services.data.fetchers.nse_client import close_nse
    close_nse(nse)


def _list_filings(nse, since: date, until: date):
    from services.data.fetchers.nse_disclosures import insider_filings
    return insider_filings(nse, None, since, until)


def _fetch_document(nse, url):
    from services.data.fetchers.nse_disclosures import fetch_document
    return fetch_document(nse, url)


def _shareholding(nse, symbol: str):
    from services.data.fetchers.nse_disclosures import shareholding_quarters
    return shareholding_quarters(nse, symbol)


def load_insider_trades(path: Path | None = None) -> dict:
    path = path or _path()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    except (OSError, ValueError) as exc:
        logger.warning("[discovery.insider] %s unreadable: %s", path, exc)
        return {}
    return data if isinstance(data, dict) else {}


def _directional(t: dict) -> bool:
    """A promoter-group or director trade in the market: the net counts it."""
    return t["market"] and t["who"] in ("promoter", "director") and t["action"] in ("buy", "sell")


def _promoter_sale(t: dict) -> bool:
    return t["market"] and t["who"] == "promoter" and t["action"] == "sell"


def _entry(row: dict, filing) -> dict:
    """The cache line for one listed filing and its parsed XBRL (or None)."""
    symbol = str(row["symbol"]).strip().upper()
    stamped = nse_stamp(str(row.get("broadcastDateTime") or ""))
    trades = ([{k: getattr(t, k) for k in _TRADE_FIELDS} for t in filing.trades]
              if filing is not None else [])
    readable = (filing is not None and filing.symbol == symbol
                and all(t["to_day"] or t["from_day"] for t in trades if _directional(t)))
    return {"symbol": symbol, "published_at": stamped.isoformat() if stamped else None,
            "revision": filing is not None and is_revision(row, filing),
            "readable": readable, "trades": trades if readable else []}


def counted_trades(filings: dict, since: str, until: str) -> dict[str, list[dict]]:
    """Each company's trades from its readable filings, each trade once, whose
    last trade day falls from `since` to `until` (YYYY-MM-DD): filings in
    dissemination order, an original's trades added, a revision's trades
    replacing their closest earlier match (module text)."""
    held: dict[str, list[dict]] = {}
    for _, fid in sorted((f.get("published_at") or "", fid) for fid, f in filings.items()
                         if f.get("readable")):
        filing = filings[fid]
        pool = held.setdefault(filing["symbol"], [])
        if not filing.get("revision"):
            pool.extend(filing["trades"])
            continue
        taken: set[int] = set()
        for t in filing["trades"]:
            same = [i for i, p in enumerate(pool) if i not in taken
                    and p["action"] == t["action"] and p["shares"] == t["shares"]]
            if same:
                i = max(same, key=lambda i: (sum(pool[i][k] == t[k] for k in _MATCH_FIELDS), i))
                pool[i] = t
            else:
                pool.append(t)
                i = len(pool) - 1
            taken.add(i)
    return {symbol: [t for t in pool if since <= (t["to_day"] or t["from_day"] or "") <= until]
            for symbol, pool in held.items()}


def symbol_net(trades: list[dict], holding: list | None) -> float:
    """Rupees bought minus sold in the market by the promoter group and
    directors. While promoters hold more than 75% (`holding` = [promoter %,
    quarter end]), a promoter-group sale counts nothing."""
    above = bool(holding) and holding[0] is not None and holding[0] > MPS_PROMOTER_CAP
    return market_net(Trade(category="", mode="", **t) for t in trades
                      if not (above and _promoter_sale(t)))


def refresh_insider_trades(on: date | None = None, path: Path | None = None) -> dict:
    """Bring the cache up to date for the window ending `on`. Returns the
    run's summary (also stored with the cache). Never raises."""
    on = on or date.today()
    path = path or _path()
    since = on - timedelta(days=max(1, settings.DISCOVERY_INSIDER_WINDOW_DAYS))
    # A filing from an earlier run is reused only with its trades.
    old = {i: f for i, f in (load_insider_trades(path).get("filings") or {}).items()
           if isinstance(f, dict) and isinstance(f.get("trades"), list)}
    summary = {"window_from": since.isoformat(), "window_to": on.isoformat(),
               "fetched_at": datetime.now(IST).isoformat(timespec="seconds"),
               "listed": 0, "read_now": 0, "failed": 0, "unread": 0, "unreadable": [],
               "revisions": 0, "holdings_failed": [], "complete": False, "error": None}
    filings = dict(old)
    extra: dict = {}
    nse = None
    try:
        nse = _make_nse()
        rows, error = _list_filings(nse, since, on)
        if error:
            summary["error"] = error
        else:
            listed: dict[str, dict] = {}
            for row in rows:
                if str(row.get("symbol") or "").strip():
                    listed.setdefault(insider_id(row), row)
            summary["listed"] = len(listed)
            filings = {i: old[i] for i in listed if i in old}
            todo = [i for i in listed if i not in filings]
            for fid in todo[:max(0, settings.DISCOVERY_INSIDER_MAX_DOCUMENTS)]:
                text, err = _fetch_document(nse, listed[fid].get("xmlFileName"))
                if err:
                    summary["failed"] += 1
                    continue
                filings[fid] = _entry(listed[fid], parse_pit_xml(text))
                summary["read_now"] += 1
            summary["unread"] = len(listed) - len(filings)
            summary["unreadable"] = sorted(i for i, f in filings.items() if not f.get("readable"))
            summary["revisions"] = sum(1 for f in filings.values() if f.get("revision"))
            share = len(summary["unreadable"]) / len(listed) if listed else 0.0
            if summary["unread"] == 0 and share <= _MAX_UNREADABLE_SHARE:
                extra = _nets(nse, counted_trades(filings, since.isoformat(), on.isoformat()),
                              summary)
                summary["complete"] = not summary["holdings_failed"]
    except Exception as exc:
        logger.warning("[discovery.insider] refresh failed, signal unavailable: %s", exc)
        summary["error"] = repr(exc)[:200]
        summary["complete"] = False
    finally:
        if nse is not None:
            _close_nse(nse)
    if not summary["complete"]:
        extra = {}
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_json(path, {**summary, **extra, "filings": filings}, indent=1,
                          sort_keys=True)
    except OSError as exc:
        logger.error("[discovery.insider] cache not written %s: %s", path, exc)
    logger.info("[discovery.insider] %s..%s: %d filings listed (%d revisions), %d read now, "
                "%d unread, %d failed, %d promoter holdings unread, complete %s",
                summary["window_from"], summary["window_to"], summary["listed"],
                summary["revisions"], summary["read_now"], summary["unread"], summary["failed"],
                len(summary["holdings_failed"]), summary["complete"])
    return summary


def _nets(nse, trades: dict[str, list[dict]], summary: dict) -> dict:
    """{"promoter_holding": {symbol: [%, quarter end]}, "net_inr": {symbol:
    rupees}}, reading the promoter share of each company with a counted
    promoter-group market sale; a failed read is named in the summary."""
    holdings: dict[str, list] = {}
    for symbol in sorted(s for s, ts in trades.items() if any(_promoter_sale(t) for t in ts)):
        rows, error = _shareholding(nse, symbol)
        if error:
            summary["holdings_failed"].append(symbol)
            continue
        quarters = quarters_from_list(rows, symbol)
        latest = quarters[0] if quarters else {}
        holdings[symbol] = [latest.get("promoter"), latest.get("quarter_end")]
    return {"promoter_holding": holdings,
            "net_inr": {s: round(symbol_net(ts, holdings.get(s)), 2) for s, ts in trades.items()}}


def usable_insider_trades(on: date, cache: dict | None = None) -> tuple[dict | None, str | None]:
    """(the cache, None) when the signal may use it, else (None, why not)."""
    cache = load_insider_trades() if cache is None else cache
    if not cache:
        return None, "insider_buying: no insider-trade cache"
    if not cache.get("complete"):
        listed = cache.get("listed", 0)
        if cache.get("error"):
            reason = cache["error"]
        elif cache.get("unread"):
            reason = f"{cache['unread']} of {listed} filings unread"
        elif cache.get("holdings_failed"):
            reason = f"promoter holding unread for {', '.join(cache['holdings_failed'])}"
        else:
            reason = f"{len(cache.get('unreadable') or [])} of {listed} filings unreadable"
        return None, f"insider_buying: {reason}"[:200]
    try:
        to = date.fromisoformat(str(cache.get("window_to")))
    except ValueError:
        return None, "insider_buying: cache has no window"
    if to > on:
        return None, f"insider_buying: filings read up to {to.isoformat()}, after {on.isoformat()}"
    if (on - to).days > _MAX_AGE_DAYS:
        return None, f"insider_buying: filings read up to {to.isoformat()} only"
    if not isinstance(cache.get("net_inr"), dict):
        return None, "insider_buying: cache has no net per company"
    return cache, None


def net_by_symbol(cache: dict | None, symbols) -> pd.Series | None:
    """Open-market net buying by promoters and directors, ₹ crore, for each
    of `symbols` (0 without a filing); None when `cache` is None."""
    if cache is None:
        return None
    net = cache.get("net_inr") or {}
    return pd.Series({s: float(net.get(s) or 0.0) / 1e7 for s in symbols}, dtype=float)

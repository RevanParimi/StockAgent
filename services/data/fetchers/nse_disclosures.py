"""
NSE's public disclosure endpoints, as raw rows, for the company-event feed
(core/events/disclosures.py) and the discovery screen (core/discovery).

| Data | Endpoint (www.nseindia.com/api/) | One row per |
|---|---|---|
| Insider trades (SEBI PIT, Reg 7(2), 7(3)) | `corporates-pit-gg` | filing: `appId`, `broadcastDateTime`, `xmlFileName` (the XBRL that holds the trades) |
| Substantial acquisitions (SAST Reg 29) | `corporate-sast-reg29` | filing: acquirer, % acquired or sold, % after, `timestamp` |
| Promoter encumbrance events (SAST Reg 31) | `corporate-pledgedata-sast3132` | event: creation, release or invocation, shares, %, `broadcastdate` |
| Promoter pledge, latest quarter | `corporate-pledgedata` | company: promoter shares pledged as % of the promoter holding (`percPromoterShares`) |
| Shareholding pattern | `corporate-share-holdings-master` | quarter: promoter % (`pr_and_prgrp`), `broadcastDate`, `xbrl` (the full pattern) |

Field names were recorded from NSE's live responses on 23 Oct 2026. NSE's
older insider endpoint, `corporates-pit`, has had no rows since late April
2026 and is not used.

Every call goes through the client's `_req`, so NSE's process-wide throttle
applies (as in ipo_bids.py). The caller owns the client
(services/data/fetchers/nse_client.py). Dates go out as DD-MM-YYYY. A
document is fetched only from NSE's archive host, whatever URL a row carries.
Nothing here raises: each function returns its rows (or text) and an error
string, None when the call worked.
"""
from __future__ import annotations

import logging
import time
from datetime import date

logger = logging.getLogger(__name__)

_BASE = "https://www.nseindia.com/api"
_ARCHIVE = "https://nsearchives.nseindia.com/"
_SLEEP_BETWEEN_CALLS = 0.5          # as nse_announcements.py
_MAX_DOCUMENT_BYTES = 5_000_000     # a shareholding pattern is ~0.6 MB

INSIDER, SAST, PLEDGE, SHAREHOLDING = "insider", "sast", "pledge", "shareholding"


def _day(d: date) -> str:
    return d.strftime("%d-%m-%Y")


def _rows(raw) -> tuple[list[dict], str | None]:
    """NSE answers a list, or {"data": [...]}; anything else is an error."""
    items = raw.get("data") if isinstance(raw, dict) else raw
    if not isinstance(items, list):
        return [], f"unexpected response: {type(raw).__name__}"
    return [i for i in items if isinstance(i, dict)], None


def _get(nse, endpoint: str, params: dict) -> tuple[list[dict], str | None]:
    try:
        resp = nse._req(f"{_BASE}/{endpoint}", params=params)
        return _rows(resp.json())
    except Exception as exc:
        logger.warning("[nse_disclosures] %s %s failed: %s", endpoint,
                       params.get("symbol", "market"), exc)
        return [], f"{endpoint}: {exc}"[:200]


def insider_filings(nse, symbol: str | None, since: date, until: date) -> tuple[list[dict], str | None]:
    """Insider-trade filings disseminated from `since` to `until`; every
    company's when `symbol` is None."""
    params = {"index": "equities", "from_date": _day(since), "to_date": _day(until)}
    if symbol:
        params["symbol"] = symbol
    return _get(nse, "corporates-pit-gg", params)


def sast_filings(nse, symbol: str, since: date, until: date) -> tuple[list[dict], str | None]:
    return _get(nse, "corporate-sast-reg29", {"index": "equities", "symbol": symbol,
                                              "from_date": _day(since), "to_date": _day(until)})


def pledge_events(nse, symbol: str, since: date, until: date) -> tuple[list[dict], str | None]:
    return _get(nse, "corporate-pledgedata-sast3132", {"index": "equities", "symbol": symbol,
                                                       "from_date": _day(since),
                                                       "to_date": _day(until)})


def shareholding_quarters(nse, symbol: str) -> tuple[list[dict], str | None]:
    """Every quarter's pattern NSE holds for `symbol`, latest first (about
    20 KB; NSE takes no date range here)."""
    return _get(nse, "corporate-share-holdings-master", {"index": "equities", "symbol": symbol})


def pledge_snapshot(nse, symbol: str) -> tuple[list[dict], str | None]:
    """The latest quarter's promoter pledge row for `symbol`. Rows carry the
    company name (`comName`), not the symbol."""
    return _get(nse, "corporate-pledgedata", {"index": "equities", "symbol": symbol})


def fetch_document(nse, url) -> tuple[str | None, str | None]:
    """An XBRL document from NSE's archive, as text. Any other host is refused."""
    if not isinstance(url, str) or not url.startswith(_ARCHIVE):
        return None, "not an NSE archive URL"
    try:
        resp = nse._req(url)
        body = resp.content
        if len(body) > _MAX_DOCUMENT_BYTES:
            return None, f"document too large: {len(body)} bytes"
        return body.decode("utf-8", errors="replace"), None
    except Exception as exc:
        logger.warning("[nse_disclosures] document %s failed: %s", url.rsplit("/", 1)[-1], exc)
        return None, f"document: {exc}"[:200]


def fetch_company_disclosures(nse, symbol: str, since: date, until: date,
                              sources: tuple[str, ...]) -> dict:
    """One company's disclosure rows for the event feed.

    Returns {source: rows} for each of `sources` (insider, sast, pledge,
    shareholding) and "errors": {source: message}. A failed endpoint leaves
    its rows empty and names itself; the others are kept."""
    out: dict = {"errors": {}}
    calls = {
        INSIDER: lambda: insider_filings(nse, symbol, since, until),
        SAST: lambda: sast_filings(nse, symbol, since, until),
        PLEDGE: lambda: pledge_events(nse, symbol, since, until),
        SHAREHOLDING: lambda: shareholding_quarters(nse, symbol),
    }
    for source in sources:
        rows, error = calls[source]()
        out[source] = rows
        if error:
            out["errors"][source] = error
        time.sleep(_SLEEP_BETWEEN_CALLS)
    return out


def pledge_snapshots(symbols: list[str]) -> dict[str, list[dict] | None]:
    """Each symbol's promoter pledge rows, with one client; None for a symbol
    whose call failed. {} when no client could be made."""
    from services.data.fetchers.nse_client import close_nse, make_nse

    try:
        nse = make_nse()
    except Exception as exc:
        logger.warning("[nse_disclosures] NSE client unavailable, pledge unchecked: %s", exc)
        return {}
    out: dict[str, list[dict] | None] = {}
    try:
        for symbol in symbols:
            rows, error = pledge_snapshot(nse, symbol)
            out[symbol] = None if error else rows
            time.sleep(_SLEEP_BETWEEN_CALLS)
    finally:
        close_nse(nse)
    return out

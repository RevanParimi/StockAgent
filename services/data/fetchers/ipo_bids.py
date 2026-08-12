"""Category-wise IPO bid ladder from /api/ipo-detail (spec section 11.2).

Endpoint verified live 2026-08-11. The response carries TWO ladders that
disagree:

  bidDetails  -> NSE-only        (MOLBIO QIB 0.564x, total bids 16,731,036)
  activeCat   -> all-exchange    (MOLBIO QIB 1.391x, total bids 25,437,636)

`bidDetails` is the more convenient shape — flat list, per-row multiple — and
is the WRONG one to read: the figure the market and the press quote is the
all-exchange one. Reading it would under-report every IPO's demand with no
error anywhere. Both are therefore captured and named for what they are; see
spec section 7 risk 6 for the arithmetic and the outstanding verification.

Field names differ between the two ladders in ways that look like typos and
are not: activeCat has `noOfShareOffered` (no 's' on Share) and `noOfSharesBid`;
bidDetails has `noOfSharesOffered` and `noOfsharesBid` (lowercase 's'). Both
are copied verbatim from the live payload.
"""
from __future__ import annotations

import logging

from services.data.fetchers.nse_client import nse_session

logger = logging.getLogger(__name__)

_BASE = "https://www.nseindia.com/api"

# Keyed on srNo, NOT on the category text: srNo "2.1" is a sub-band of "2" and
# its category string starts with the same words, so text matching would let a
# sub-band overwrite the category total.
_SRNO_TO_KEY: dict[str, str] = {
    "1": "qib",
    "1(a)": "fii",
    "1(b)": "dom_fi",
    "1(c)": "mutual_fund",
    "2": "nii",
    "3": "retail",
    "4": "employee",
}
_KEYS: tuple[str, ...] = ("qib", "fii", "dom_fi", "mutual_fund", "nii",
                          "retail", "employee", "total")


def _num(raw: object) -> float | None:
    """'2.05' -> 2.05; '1.6731036E7' -> 16731036.0; '' / None -> None.

    Blank means the category reports a bid quantity but no multiple. It must
    stay None: zero would assert 'nobody bid', which is a different claim.
    """
    text = str(raw or "").strip().replace(",", "")
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _empty_ladder() -> dict[str, float | None]:
    return {k: None for k in _KEYS}


def _read_ladder(rows: list, x_key: str) -> dict[str, float | None]:
    """Fold ladder rows into {category_key: multiple}. `x_key` names the
    subscription-multiple field, which differs between the two ladders."""
    out = _empty_ladder()
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        sr = str(row.get("srNo") or "").strip()
        category = str(row.get("category") or "").strip().lower()
        if sr == "Sr.No." or category == "category":
            continue                      # activeCat's header row
        key = "total" if category == "total" else _SRNO_TO_KEY.get(sr)
        if key is None:
            continue                      # sub-bands and unmapped rows
        out[key] = _num(row.get(x_key))
    return out


def _cutoff_share(graph: object) -> float | None:
    """Share of bids placed at cut-off rather than a chosen price — demand
    that is indifferent to price. Official, and free of any GMP dependency."""
    if not isinstance(graph, dict):
        return None
    at_cutoff, total = _num(graph.get("totalBidAtCutOff")), _num(graph.get("TOTAL_BIDS"))
    if at_cutoff is None or not total:
        return None
    return at_cutoff / total


def parse_bid_ladder(payload: dict) -> dict:
    """Pure parse of an /api/ipo-detail body. Never raises."""
    payload = payload if isinstance(payload, dict) else {}
    active = payload.get("activeCat") if isinstance(payload.get("activeCat"), dict) else {}
    return {
        "symbol": str(payload.get("companyName") or "").strip(),
        "updated_at": str(active.get("updateTime") or "").strip(),
        "combined": _read_ladder(active.get("dataList"), "noOfTotalMeant"),
        "nse_only": _read_ladder(payload.get("bidDetails"), "noOfTime"),
        "cutoff_share": _cutoff_share(payload.get("demandGraph")),
    }


def fetch_bid_ladder(symbol: str) -> dict | None:
    """One symbol's ladder from live NSE. Returns None on any failure — the
    caller renormalizes rather than treating absence as zero demand."""
    try:
        with nse_session() as nse:
            # _req(), not _session.get(): it applies the process-wide
            # mthrottle shared by every other NSE call site, and raises
            # ConnectionError on non-2xx — which the except below already
            # catches. Going around it would make this the one fetcher that
            # can hammer NSE independently, and it runs in a per-symbol loop.
            resp = nse._req(f"{_BASE}/ipo-detail",
                            params={"symbol": symbol, "series": "EQ"})
            out = parse_bid_ladder(resp.json())
            out["symbol"] = symbol          # payload's companyName is unreliable
            return out
    except Exception as exc:
        logger.warning("[ipo_bids] fetch failed for %s (non-fatal): %s", symbol, exc)
        return None

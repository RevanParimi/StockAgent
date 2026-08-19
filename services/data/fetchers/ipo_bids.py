"""Category-wise IPO bid ladder from /api/ipo-detail (spec section 11.2).

Endpoint verified live 2026-08-11. The response carries TWO ladders that
disagree, and WHICH ONE IS AUTHORITATIVE IS SETTLED: read `combined`.

  combined  <- activeCat.dataList, key `noOfTotalMeant`   <-- THE headline
  nse_only  <- bidDetails,         key `noOfTime`         <-- never the headline

`bidDetails` is the more convenient shape — flat list, per-row multiple — and is
the WRONG one to read. It under-reports demand with no error raised anywhere.

VERIFIED ON THREE SYMBOLS (spec section 7 risk 6 asked for a second; P0
live-window check, 2026-08-18, closed it on two more):

  symbol      when                       nse_only        combined
  MOLBIO      2026-08-11    QIB            0.564x          1.391x
  LALITHAA    2026-08-18 EOD  total        2.2373x         3.0682x
                              QIB          0.0129x         1.0237x
  SUNSHINE    2026-08-18 EOD  total        3.1834x         4.3320x
                              QIB          0.0083x         0.0289x

LALITHAA's QIB is the case that matters. `nse_only` says 0.0129x — read aloud,
"institutions did not show up". `combined` says 1.0237x — "the institutional
book filled". That is an INVERTED conclusion, not a degraded one, and it is the
same wrong-number-rather-than-absent class as the total_x_nse_only flag and the
GMP sign. A verdict built on the convenient shape would be confidently backwards.

The disagreement is NOT a fixed denominator artifact: for LALITHAA the ratio
combined/nse_only was 1.765 at the 08:00 IST pass and 1.371 at the 17:45 IST
pass the same day. A constant offset would not move.

WHAT IS DELIBERATELY *NOT* CLAIMED HERE. The older note in this docstring
labelled the two "NSE-only" and "all-exchange". That reading is plausible but is
NOT established by the data, so it is no longer asserted as fact: on 2026-08-18
the payload's own price-level curves put NSE's share of cut-off demand at 0.44
(demandDataNSE cumQty 5,72,92,946 vs demandDataBSE 7,29,65,628), whereas the
observed nse_only/combined ratio was 0.73. A clean `combined = NSE + BSE` does
not reconcile. activeCat carries no offered-share count, so numerator and
denominator effects cannot be separated from this response alone.

What IS established, and all the code needs: `activeCat` is the broader figure
NSE itself publishes as "No. of times of total meant for the category", stamped
with its own `updateTime` (the ~17:00 IST daily update), and it is the figure
consistent with what the market quotes. An independent press cross-check was
attempted and was inconclusive rather than contradictory — intraday quotes for
LALITHAA on 2026-08-18 (1.15x around 10:59 IST) sit between this system's own
08:00 reading (0.6937x) and its 17:45 reading (3.0682x), which is consistent
with bids accumulating but cannot discriminate between the two shapes.

So: both ladders stay captured and named for what they are, `combined` is the
headline everywhere, and anything derived from `nse_only` must say so at the
point of use. `total_x_nse_only` exists for exactly that admission, and
core/delivery/brief.py suppresses the demand delta when it is set rather than
mixing the two scales in one clause.

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


def _reject_placeholder_total(ladder: dict[str, float | None]) -> dict[str, float | None]:
    """NSE serves a literal 0.00 `total` with no category breakdown for some
    older listings (observed live 2026-08-12 on IGIL, a heavily-subscribed
    IPO — its bidDetails/nse_only ladder still shows the real 31.5x QIB).
    Recording that would assert 'nobody subscribed' about a hot issue — the
    exact inversion the dark-signal rule exists to prevent. A genuine
    ladder always carries the category rows (qib, retail) alongside the
    total; a total-only response is the stub, not a real zero.

    Applied to both `combined` and `nse_only` in `parse_bid_ladder` — the
    single chokepoint every caller of either ladder passes through, so no
    consumer (backfill enrichment, the live open-issue enrichment that
    feeds the morning brief) has to know which ladder can lie.
    """
    if ladder["qib"] is None and ladder["retail"] is None:
        ladder["total"] = None
    return ladder


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
        "combined": _reject_placeholder_total(
            _read_ladder(active.get("dataList"), "noOfTotalMeant")),
        "nse_only": _reject_placeholder_total(
            _read_ladder(payload.get("bidDetails"), "noOfTime")),
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

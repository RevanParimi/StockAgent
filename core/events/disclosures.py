"""
NSE disclosures as company events, typed by fixed rules with no model call
(KT section 4). Pure functions: the feed passes the rows and documents
(services/data/fetchers/nse_disclosures.py).

| Source | Event | Identity | `published_at` | `occurred_from`/`_to` |
|---|---|---|---|---|
| Insider-trade filing (SEBI PIT) | insider | `nsepit:<appId>` | NSE's `broadcastDateTime` | the trade days in its XBRL |
| SAST Regulation 29 filing | deal | `nsesast:<application_no>` | `timestamp` | the acquisition or sale days |
| SAST Regulation 31 event | pledge | `nsepledge:<seqId>` | `broadcastdate` | the event days |
| Shareholding pattern | ownership | `nseshp:<quarter end>` | `broadcastDate` | the quarter end |

**When we could have known.** `published_at` is when NSE disseminated the
filing, never the day of the trade, the pledge or the quarter end: a promoter
who sells on 21 Oct and files on 22 Oct is news on 22 Oct. The transaction
days are kept in `occurred_from` and `occurred_to`. A time more than 10
minutes after the fetch is left for a later run, as for announcements.

**Insider trades.** One event per filing; its XBRL lists each person's trade.
Persons are grouped by the filing's own category: promoter group, directors
and key managers, and everyone else (designated employees, relatives). Names
are not stored. Only open-market trades by the promoter group or directors
carry a direction:

- net buying (rupees bought minus sold) is positive, net selling negative;
- a promoter-group sale while promoters hold more than 75% of the company
  (the latest shareholding pattern) is neutral: listed companies must keep 25%
  public, so the sale may be to meet that rule, and the sentence says so;
- any other net sale says "The filing gives no reason for the sale": a sale
  to pay tax or to release a pledge looks the same;
- off-market moves (gift, inheritance, inter-se transfer, ESOP allotment) and
  employees' trades are neutral and low.

Materiality is the size of the open-market net: ₹10 crore or more high, ₹1
crore or more medium, else low; a neutral sale is at most medium.

**Revisions.** NSE lists a corrected filing as a new filing (its own
`appId`, `typeOfSubmission` "Revision"), and rarely says which one it
corrects: of 6 revisions in the 28 days to 23 Oct 2026, 2 named an earlier
id and neither id was on the list. A revision restates trades already
disclosed, sometimes months earlier, so its event is neutral and low, and its
sentence says it revises an earlier filing. Example: NSE disseminates a
revision on 8 Oct of a director's ₹68.0 crore sale traded on 18 Aug; it is
stored as a neutral, low event that says so, not as a new ₹68 crore sale.

**Substantial acquisitions (Reg 29)** are deals: who acquired or sold what
share of the company and what they hold after. A promoter's acquisition is
positive and its sale negative; anyone else's (a fund crossing 5%, say) is
neutral, since the filing does not say why. A change of 2 points or more is
high, 1 point or crossing 5% medium, else low.

**Pledge events (Reg 31).** A promoter creating a pledge (or another
encumbrance) is negative, a lender invoking one negative and high, a release
positive. Size is the event's share of the company: 2% or more high, 0.5% or
more medium, else low; a release is at most medium, since repaying a loan is
routine. Names are not stored: "a promoter", "a lender".

**Ownership.** The latest quarter is compared with the one before it:
promoter % from NSE's quarterly list, and FII, DII and mutual-fund % from that
quarter's XBRL. One event when any of the four moved by
`events.ownership_move_points` (1) or more. All moves up is positive, all down
negative, mixed neutral; 3 points or more is high, else medium. A fall in the
promoter's share does not say whether promoters sold or new shares diluted
them, and the sentence says so.

Example: promoters held 52.1% at 30 Jun 2026 and 50.6% at 30 Sep, filed 21 Oct
10:01. The event is `ownership`, negative (only the promoter moved),
medium, `published_at` 2026-10-21T10:01:00+05:30, occurred 2026-09-30.
"""
from __future__ import annotations

import hashlib
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime

from backend.shared.schemas.events import CompanyEvent
from core.events.sources import IST, is_ahead, normalize_url, nse_stamp

CLASSIFIER = "rules"
NSE_INSIDER, NSE_SAST, NSE_PLEDGE, NSE_SHAREHOLDING = (
    "nse_insider", "nse_sast", "nse_pledge", "nse_shareholding")

MPS_PROMOTER_CAP = 75.0         # listed companies keep at least 25% public
_HIGH_INR, _MEDIUM_INR = 1e8, 1e7       # ₹10 crore, ₹1 crore
_DAY_FORMATS = ("%Y-%m-%d", "%d-%b-%Y", "%d-%m-%Y")
_STAMP_FORMATS = ("%d-%b-%Y %H:%M:%S", "%d-%b-%Y %H:%M")


# ---------------------------------------------------------------------------
# Small readers
# ---------------------------------------------------------------------------

def _s(row: dict, *keys: str) -> str:
    for k in keys:
        v = row.get(k)
        if isinstance(v, bool) or v is None:
            continue
        if str(v).strip():
            return str(v).strip()
    return ""


def num(raw) -> float | None:
    """A number from NSE text ("4185205", "  58.72", "1,980,319"); None for
    "", "-", "NA", "Nil" or anything else."""
    if isinstance(raw, bool):
        return None
    if isinstance(raw, (int, float)):
        return float(raw)
    text = str(raw or "").strip().replace(",", "")
    try:
        return float(text)
    except ValueError:
        return None


def day(raw) -> str | None:
    """YYYY-MM-DD from NSE's day formats ("2026-10-21", "03-JUN-2026",
    "21-10-2026"); None when unreadable."""
    text = str(raw or "").strip()
    for fmt in _DAY_FORMATS:
        try:
            return datetime.strptime(text, fmt).date().isoformat()
        except ValueError:
            continue
    return None


def _stamp(raw: str):
    return nse_stamp(raw, _STAMP_FORMATS) if raw else None


def _digest(*parts: str) -> str:
    return hashlib.sha1("|".join(parts).encode("utf-8")).hexdigest()[:16]


def rupees(value: float) -> str:
    """₹ in lakh or crore, as Indian readers say it: ₹23.1 lakh, ₹12.4 crore."""
    v = abs(value)
    if v >= 1e7:
        return f"₹{v / 1e7:,.1f} crore"
    if v >= 1e5:
        return f"₹{v / 1e5:,.1f} lakh"
    return f"₹{v:,.0f}"


def shares(n: float) -> str:
    """A share count with Indian digit grouping: 41,85,205."""
    digits = str(int(round(abs(n))))
    head, tail = digits[:-3], digits[-3:]
    groups = []
    while len(head) > 2:
        groups.insert(0, head[-2:])
        head = head[:-2]
    if head:
        groups.insert(0, head)
    return ("-" if n < 0 else "") + ",".join(groups + [tail])


def day_text(iso: str | None) -> str:
    """'21 Oct 2026' from YYYY-MM-DD."""
    if not iso:
        return "an undisclosed day"
    d = datetime.strptime(iso[:10], "%Y-%m-%d")
    return f"{d.day} {d.strftime('%b %Y')}"


def _days(first: str | None, last: str | None) -> str:
    if first and last and first != last:
        return f"{day_text(first)} to {day_text(last)}"
    return day_text(first or last)


def _pct(v: float) -> str:
    return f"{v:.2f}%"


def _safe_xml(text) -> ET.Element | None:
    """The document's root, or None. A document that declares a DTD or an
    entity is refused before parsing, so no entity is ever expanded."""
    if not isinstance(text, str) or not text.strip():
        return None
    head = text.upper()
    if "<!DOCTYPE" in head or "<!ENTITY" in head:
        return None
    try:
        return ET.fromstring(text.encode("utf-8"))
    except ET.ParseError:
        return None


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


# ---------------------------------------------------------------------------
# Insider trades
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Trade:
    who: str                # promoter | director | other
    category: str           # the filing's own words, e.g. "Promoter Group"
    action: str             # buy | sell | other
    mode: str               # the filing's own words, e.g. "Market Sale"
    market: bool            # an open-market trade
    shares: float | None
    value_inr: float | None
    from_day: str | None
    to_day: str | None


@dataclass(frozen=True)
class PitFiling:
    symbol: str
    filed_on: str | None
    regulation: str
    revised: bool
    trades: tuple[Trade, ...]


def person_group(category: str) -> str:
    """promoter, director (directors and key managers) or other. A relative
    is "other": "Immediate relative" and "Relatives of promoters other than
    promoter group" are not the promoter group."""
    c = " ".join(category.lower().split())
    if "relative" in c or "other than" in c:
        return "other"
    if "promoter" in c:
        return "promoter"
    if "director" in c or "kmp" in c or "key managerial" in c:
        return "director"
    return "other"


def _action(raw: str) -> str:
    c = raw.strip().lower()
    if c in ("buy", "purchase", "acquisition"):
        return "buy"
    if c in ("sell", "sale", "disposal"):
        return "sell"
    return "other"


def _is_market(mode: str) -> bool:
    m = " ".join(mode.lower().replace("-", " ").split())
    return "market" in m and "off market" not in m


def parse_pit_xml(text) -> PitFiling | None:
    """An insider-trade XBRL (NSE's "PIT V2.0" layout) as its trades; None
    when the document is not one, or names no trade."""
    root = _safe_xml(text)
    if root is None:
        return None
    contexts: dict[str, dict[str, str]] = {}
    for el in root:
        ref = el.get("contextRef")
        if ref:
            contexts.setdefault(ref, {})[_local(el.tag)] = (el.text or "").strip()
    main = contexts.get("MainI", {})
    trades = []
    for ref, facts in contexts.items():
        if ref == "MainI" or "CategoryOfPerson" not in facts:
            continue
        mode = facts.get("ModeOfAcquisitionOrDisposal", "")
        category = facts.get("CategoryOfPerson", "")
        trades.append(Trade(
            who=person_group(category), category=category,
            action=_action(facts.get("SecuritiesAcquiredOrDisposedTransactionType", "")),
            mode=mode, market=_is_market(mode),
            shares=num(facts.get("SecuritiesAcquiredOrDisposedNumberOfSecurity")),
            value_inr=num(facts.get("SecuritiesAcquiredOrDisposedValueOfSecurity")),
            from_day=day(facts.get(
                "DateOfAllotmentAdviceOrAcquisitionOfSharesOrSaleOfSharesSpecifyFromDate")),
            to_day=day(facts.get(
                "DateOfAllotmentAdviceOrAcquisitionOfSharesOrSaleOfSharesSpecifyToDate"))))
    if not main.get("Symbol") or not trades:
        return None
    return PitFiling(symbol=main["Symbol"].upper(), filed_on=day(main.get("DateOfFiling")),
                     regulation=main.get("DisclosureUnderRegulation", ""),
                     revised=main.get("RevisedFilling", "").lower() == "true",
                     trades=tuple(trades))


_GROUP_LABEL = {"promoter": "The promoter group", "director": "Directors and key managers",
                "other": "Designated employees and relatives"}


def market_net(trades) -> float:
    """Rupees bought minus sold in the market by the promoter group and
    directors; a trade without a value counts nothing."""
    net = 0.0
    for t in trades:
        if t.market and t.who in ("promoter", "director") and t.value_inr is not None:
            if t.action == "buy":
                net += t.value_inr
            elif t.action == "sell":
                net -= t.value_inr
    return net


def is_revision(row: dict, filing: PitFiling) -> bool:
    """NSE lists the filing as a revision, or its XBRL says it is revised."""
    return filing.revised or _s(row, "typeOfSubmission").lower() == "revision"


def _trade_phrase(group: str, action: str, market: bool, rows: list[Trade]) -> str:
    total_shares = sum(t.shares or 0 for t in rows)
    values = [t.value_inr for t in rows if t.value_inr is not None]
    worth = f" worth {rupees(sum(values))}" if values else ""
    if market:
        verb = {"buy": "bought", "sell": "sold"}.get(action, "traded")
        how = "in the market"
    else:
        verb = {"buy": "acquired", "sell": "disposed of"}.get(action, "reported a change in")
        modes = sorted({t.mode.lower() for t in rows if t.mode and t.mode not in ("-", "NA")})
        how = f"by {' and '.join(modes)}" if modes else "off the market"
    first = min((t.from_day for t in rows if t.from_day), default=None)
    last = max((t.to_day for t in rows if t.to_day), default=None)
    return (f"{_GROUP_LABEL[group]} {verb} {shares(total_shares)} shares{worth} {how} "
            f"on {_days(first, last)}")


def insider_event(row: dict, filing: PitFiling, symbol: str, fetched_at: str,
                  promoter_holding: tuple[float, str] | None) -> CompanyEvent | None:
    """One event for one filing. `row` is its corporates-pit-gg row;
    `promoter_holding` the latest (promoter %, quarter end) known, or None."""
    published = _stamp(_s(row, "broadcastDateTime"))
    app_id = _s(row, "appId")
    xml_url = normalize_url(_s(row, "xmlFileName"))
    eid = f"nsepit:{app_id}" if app_id else f"nsepit:{_digest(xml_url or '')}"
    groups: dict[tuple[str, str, bool], list[Trade]] = {}
    for t in filing.trades:
        groups.setdefault((t.who, t.action, t.market), []).append(t)
    order = {"promoter": 0, "director": 1, "other": 2}
    phrases = [_trade_phrase(g, a, m, rows) for (g, a, m), rows in
               sorted(groups.items(), key=lambda kv: (order[kv[0][0]], not kv[0][2], kv[0][1]))]

    key = [t for t in filing.trades if t.market and t.who in ("promoter", "director")
           and t.action in ("buy", "sell")]
    net = market_net(filing.trades)
    promoter_sold = any(t.who == "promoter" and t.action == "sell" for t in key)
    revision = is_revision(row, filing)
    notes: list[str] = []
    if not key or net == 0:
        direction = "neutral"
    elif net > 0:
        direction = "positive"
    else:
        direction = "negative"
    if revision:
        # Trades already disclosed, perhaps months ago: not new trading.
        direction = "neutral"
        notes.append("It revises an earlier filing, so these trades may have been reported "
                     "before and are not read as new trading.")
    elif direction == "negative":
        if (promoter_sold and promoter_holding is not None
                and promoter_holding[0] > MPS_PROMOTER_CAP):
            direction = "neutral"
            notes.append(f"Promoters held {_pct(promoter_holding[0])} at "
                         f"{day_text(promoter_holding[1])}, above the 75% a listed company "
                         f"may keep, so the sale may be to meet the public-shareholding rule.")
        else:
            notes.append("The filing gives no reason for the sale.")
    if not key or revision:
        materiality = "low"
    elif abs(net) >= _HIGH_INR:
        materiality = "high"
    elif abs(net) >= _MEDIUM_INR:
        materiality = "medium"
    else:
        materiality = "low"
    if direction == "neutral" and materiality == "high":
        materiality = "medium"

    filed = day_text(published.date().isoformat()) if published else "an unknown day"
    what = "; ".join(phrases) + f". Filed with NSE on {filed}."
    if notes:
        what += " " + " ".join(notes)
    firsts = [t.from_day for t in filing.trades if t.from_day]
    lasts = [t.to_day for t in filing.trades if t.to_day]
    facts = {
        "regulation": filing.regulation or _s(row, "regulation"),
        "revision": revision,
        "trades": len(filing.trades),
        "market_net_inr": round(net, 2),
        "promoter_market_sell_inr": round(sum(t.value_inr or 0 for t in key
                                              if t.who == "promoter" and t.action == "sell"), 2),
        "promoter_holding_pct": promoter_holding[0] if promoter_holding else None,
        "groups": sorted({t.who for t in filing.trades}),
    }
    return CompanyEvent(
        id=eid, symbol=symbol, what=what, category="insider", direction=direction,
        materiality=materiality, source=NSE_INSIDER,
        source_url=normalize_url(_s(row, "ixbrl")) or xml_url, announcement_id=app_id or None,
        title=f"Insider trading disclosure ({facts['regulation'] or 'SEBI PIT'})",
        published_at=published.isoformat() if published else None,
        published_raw=_s(row, "broadcastDateTime"),
        occurred_from=min(firsts) if firsts else None, occurred_to=max(lasts) if lasts else None,
        facts=facts, fetched_at=fetched_at, classifier=CLASSIFIER)


def insider_rows(rows: list, code: str, now: datetime) -> tuple[list[dict], int, int]:
    """(this code's insider filing rows that can be read, rows naming another
    code, rows timed after the fetch). Newest first."""
    keep, foreign, ahead = [], 0, 0
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        if _s(row, "symbol").upper() != code.upper():
            foreign += 1
            continue
        published = _stamp(_s(row, "broadcastDateTime"))
        if published is not None and is_ahead(published, now):
            ahead += 1
            continue
        keep.append(row)
    keep.sort(key=lambda r: (_stamp(_s(r, "broadcastDateTime")) or datetime.min.replace(tzinfo=IST)),
              reverse=True)
    return keep, foreign, ahead


def insider_id(row: dict) -> str:
    app_id = _s(row, "appId")
    return f"nsepit:{app_id}" if app_id else f"nsepit:{_digest(normalize_url(_s(row, 'xmlFileName')) or '')}"


# ---------------------------------------------------------------------------
# Substantial acquisitions (SAST Reg 29)
# ---------------------------------------------------------------------------

def sast_events(rows: list, code: str, symbol: str, now: datetime, fetched_at: str,
                since) -> tuple[list[CompanyEvent], int, int]:
    """(deal events from Reg 29 rows filed on or after `since`, rows naming
    another code, rows timed after the fetch)."""
    events, foreign, ahead = [], 0, 0
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        if _s(row, "symbol").upper() != code.upper():
            foreign += 1
            continue
        raw = _s(row, "timestamp", "sysTime")
        published = _stamp(raw)
        if published is not None:
            if published.date() < since:
                continue
            if is_ahead(published, now):
                ahead += 1
                continue
        sale = _s(row, "acqSaleType").lower().startswith("sale")
        change = num(row.get("totSaleShare" if sale else "totAcqShare"))
        count = num(row.get("noOfShareSale" if sale else "noOfShareAcq"))
        after = num(row.get("totAftShare"))
        acquirer = _s(row, "acquirerName") or "An acquirer"
        promoter = _s(row, "promoterType").upper() == "Y"
        regulation = _s(row, "regType") or "Reg29"
        when = _s(row, "acquirerDate")
        parts = [p.strip() for p in re.split(r"\bto\b", when, flags=re.I)] if when else []
        first, last = (day(parts[0]) if parts else None), (day(parts[-1]) if parts else None)
        verb = "sold" if sale else "acquired"
        what = f"{acquirer}{' (promoter group)' if promoter else ''} {verb}"
        what += f" {_pct(change)} of the company" if change is not None else " shares"
        if count is not None:
            what += f" ({shares(count)} shares)"
        what += f" on {_days(first, last)}"
        if after is not None:
            what += f" and now holds {_pct(after)}"
        filed = day_text(published.date().isoformat()) if published else "an unknown day"
        what += f". SAST {regulation.replace('Reg', 'Regulation ')} filing, filed with NSE on {filed}."
        if promoter:
            direction = "negative" if sale else "positive"
        else:
            direction = "neutral"
        size = abs(change) if change is not None else 0.0
        if size >= 2.0:
            materiality = "high"
        elif size >= 1.0 or regulation.replace(" ", "").lower() == "reg29(1)":
            materiality = "medium"
        else:
            materiality = "low"
        app = _s(row, "application_no")
        events.append(CompanyEvent(
            id=f"nsesast:{app}" if app else f"nsesast:{_digest(code.upper(), raw, acquirer)}",
            symbol=symbol, what=what, category="deal", direction=direction,
            materiality=materiality, source=NSE_SAST, source_url=normalize_url(_s(row, "attachement")),
            announcement_id=app or None, title=f"Substantial acquisition disclosure ({regulation})",
            published_at=published.isoformat() if published else None, published_raw=raw,
            occurred_from=first, occurred_to=last,
            facts={"acquirer": acquirer, "promoter": promoter, "action": "sale" if sale else "acquisition",
                   "change_pct": change, "shares": count, "after_pct": after, "regulation": regulation},
            fetched_at=fetched_at, classifier=CLASSIFIER))
    return events, foreign, ahead


# ---------------------------------------------------------------------------
# Promoter pledge events (SAST Reg 31)
# ---------------------------------------------------------------------------

def pledge_events(rows: list, code: str, symbol: str, now: datetime, fetched_at: str,
                  since) -> tuple[list[CompanyEvent], int, int]:
    """(pledge events from Reg 31 rows disseminated on or after `since`,
    rows naming another code, rows timed after the fetch)."""
    events, foreign, ahead = [], 0, 0
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        if _s(row, "symbol").upper() != code.upper():
            foreign += 1
            continue
        raw = _s(row, "broadcastdate", "sysTime")
        published = _stamp(raw)
        if published is not None:
            if published.date() < since:
                continue
            if is_ahead(published, now):
                ahead += 1
                continue
        kind = _s(row, "eventDetailsType").lower()
        encumbrance = _s(row, "eventDetailsTypeEncumb") or "encumbrance"
        event_pct = num(row.get("eventDetailsPerc"))
        event_shares = num(row.get("eventDetailsHolding"))
        post_pct = num(row.get("postEventHoldingPerc"))
        first, last = day(_s(row, "eventDetailsFromDate")), day(_s(row, "eventDetailsToDate"))
        enc = encumbrance.lower()
        if kind.startswith("creat"):
            who, verb, direction = "A promoter", f"created a {enc}", "negative"
        elif kind.startswith("invo"):
            who, verb, direction = "A lender", f"invoked a {enc} given by a promoter", "negative"
        elif kind.startswith("rel"):
            who, verb, direction = "A promoter", f"released a {enc}", "positive"
        else:
            who, verb, direction = "A promoter", f"reported a {enc} change", "neutral"
        what = f"{who} {verb} on"
        what += f" {_pct(event_pct)} of the company's shares" if event_pct is not None else " shares"
        if event_shares is not None:
            what += f" ({shares(event_shares)} shares)"
        what += f" on {_days(first, last)}"
        if post_pct is not None:
            what += f"; that promoter's encumbered shares are now {_pct(post_pct)} of the company"
        filed = day_text(published.date().isoformat()) if published else "an unknown day"
        what += f". SAST Regulation 31 disclosure, filed with NSE on {filed}."
        size = event_pct or 0.0
        if kind.startswith("invo") or size >= 2.0:
            materiality = "high"
        elif size >= 0.5:
            materiality = "medium"
        else:
            materiality = "low"
        if direction != "negative" and materiality == "high":
            materiality = "medium"          # a release is routine (a loan repaid)
        seq = _s(row, "seqId")
        events.append(CompanyEvent(
            id=f"nsepledge:{seq}" if seq else f"nsepledge:{_digest(code.upper(), raw, kind)}",
            symbol=symbol, what=what, category="pledge", direction=direction,
            materiality=materiality, source=NSE_PLEDGE, source_url=normalize_url(_s(row, "attachment")),
            announcement_id=seq or None, title=f"Promoter encumbrance: {kind or 'event'} ({encumbrance})",
            published_at=published.isoformat() if published else None, published_raw=raw,
            occurred_from=first, occurred_to=last,
            facts={"type": kind or None, "encumbrance": encumbrance, "event_pct": event_pct,
                   "event_shares": event_shares, "post_event_pct": post_pct,
                   "promoter_holding_pct": num(row.get("preeventHoldingPerc"))},
            fetched_at=fetched_at, classifier=CLASSIFIER))
    return events, foreign, ahead


def pledged_share_of_promoter(rows: list) -> tuple[float, str | None] | None:
    """(promoter shares pledged as % of the promoter holding, quarter end)
    from corporate-pledgedata rows; None when no row gives the figure."""
    for row in rows or []:
        if isinstance(row, dict):
            pct = num(row.get("percPromoterShares"))
            if pct is not None:
                return pct, day(_s(row, "shp"))
    return None


# ---------------------------------------------------------------------------
# Shareholding pattern
# ---------------------------------------------------------------------------

OWNERSHIP_KEYS = ("promoter", "fii", "dii", "mf")
_OWNERSHIP_LABEL = {"promoter": "promoter holding", "fii": "foreign institutions (FII)",
                    "dii": "domestic institutions (DII)", "mf": "mutual funds"}
# The shareholding XBRL's category members (CategoryOfShareholdersAxis).
_SHP_MEMBERS = {"ShareholdingOfPromoterAndPromoterGroupMember": "promoter",
                "InstitutionsForeignMember": "fii", "InstitutionsDomesticMember": "dii",
                "MutualFundsOrUTIMember": "mf"}
_XBRLI = "{http://www.xbrl.org/2003/instance}"
_XBRLDI = "{http://xbrl.org/2006/xbrldi}"


def parse_shareholding_xbrl(text) -> dict | None:
    """{"symbol", "quarter_end", "promoter", "fii", "dii", "mf"} in percent
    from a quarter's shareholding XBRL; a category the document does not
    give is None. None when the document is not one."""
    root = _safe_xml(text)
    if root is None:
        return None
    category_ctx: dict[str, str] = {}
    for ctx in root.iter(f"{_XBRLI}context"):
        members = [(m.text or "").strip().rsplit(":", 1)[-1]
                   for m in ctx.iter(f"{_XBRLDI}explicitMember")]
        typed = list(ctx.iter(f"{_XBRLDI}typedMember"))
        if len(members) == 1 and not typed and members[0] in _SHP_MEMBERS:
            category_ctx[ctx.get("id")] = _SHP_MEMBERS[members[0]]
    out: dict = {k: None for k in OWNERSHIP_KEYS}
    out["symbol"], out["quarter_end"] = None, None
    for el in root:
        name, ref = _local(el.tag), el.get("contextRef")
        if name == "ShareholdingAsAPercentageOfTotalNumberOfShares" and ref in category_ctx:
            value = num(el.text)
            if value is not None:
                out[category_ctx[ref]] = round(value * 100.0, 4)   # a fraction: 0.5872
        elif name == "Symbol" and not out["symbol"]:
            out["symbol"] = (el.text or "").strip().upper() or None
        elif name == "DateOfReport" and not out["quarter_end"]:
            out["quarter_end"] = day(el.text)
    if out["quarter_end"] is None or all(out[k] is None for k in OWNERSHIP_KEYS):
        return None
    return out


def quarters_from_list(rows: list, code: str) -> list[dict]:
    """Quarters from corporate-share-holdings-master rows for `code`, latest
    first, one per quarter end (a revision replaces the original): quarter_end,
    promoter %, published_at, published_raw, xbrl URL."""
    by_quarter: dict[str, dict] = {}
    for row in rows or []:
        if not isinstance(row, dict) or _s(row, "symbol").upper() != code.upper():
            continue
        quarter = day(_s(row, "date"))
        raw = _s(row, "broadcastDate", "systemDate")
        published = _stamp(raw.title()) if raw else None
        if quarter is None:
            continue
        entry = {"quarter_end": quarter, "promoter": num(row.get("pr_and_prgrp")),
                 "published_at": published.isoformat() if published else None,
                 "published_raw": raw, "xbrl": normalize_url(_s(row, "xbrl"))}
        held = by_quarter.get(quarter)
        if held is None or (entry["published_at"] or "") > (held["published_at"] or ""):
            by_quarter[quarter] = entry
    return sorted(by_quarter.values(), key=lambda q: q["quarter_end"], reverse=True)


def ownership_event(latest: dict, before: dict, symbol: str, fetched_at: str,
                    move_points: float) -> CompanyEvent | None:
    """The ownership event for `latest` against `before` (quarters with
    promoter, fii, dii and mf % each, None when unknown), or None when no
    category moved by `move_points` or more."""
    changes = {}
    for key in OWNERSHIP_KEYS:
        a, b = before.get(key), latest.get(key)
        if a is not None and b is not None:
            changes[key] = (a, b, round(b - a, 4))
    moved = {k: v for k, v in changes.items() if abs(v[2]) >= move_points - 1e-9}
    if not moved:
        return None
    signs = {v[2] > 0 for v in moved.values()}
    direction = ("positive" if signs == {True} else "negative" if signs == {False} else "neutral")
    materiality = "high" if max(abs(v[2]) for v in moved.values()) >= 3.0 else "medium"

    def phrase(key: str) -> str:
        a, b, d = changes[key]
        verb = "rose" if d > 0 else "fell" if d < 0 else "stayed"
        return f"{_OWNERSHIP_LABEL[key]} {verb} from {_pct(a)} to {_pct(b)} ({d:+.2f} points)"

    ordered = [k for k in OWNERSHIP_KEYS if k in moved] + [k for k in OWNERSHIP_KEYS
                                                          if k in changes and k not in moved]
    what = (f"Between {day_text(before['quarter_end'])} and {day_text(latest['quarter_end'])} the "
            + "; ".join(phrase(k) for k in ordered))
    published = latest.get("published_at")
    what += (f". Shareholding pattern filed with NSE on "
             f"{day_text(published[:10]) if published else 'an unknown day'}.")
    if "promoter" in moved and moved["promoter"][2] < 0:
        what += (" The pattern does not say whether promoters sold or new shares diluted "
                 "their stake.")
    unknown = [k for k in OWNERSHIP_KEYS if k not in changes]
    return CompanyEvent(
        id=f"nseshp:{latest['quarter_end']}", symbol=symbol, what=what, category="ownership",
        direction=direction, materiality=materiality, source=NSE_SHAREHOLDING,
        source_url=latest.get("xbrl"), title="Shareholding pattern",
        published_at=published, published_raw=latest.get("published_raw") or "",
        occurred_from=latest["quarter_end"], occurred_to=latest["quarter_end"],
        facts={"from_quarter": before["quarter_end"], "to_quarter": latest["quarter_end"],
               **{k: [v[0], v[1]] for k, v in changes.items()},
               "moved": sorted(moved), "unavailable": unknown},
        fetched_at=fetched_at, classifier=CLASSIFIER)

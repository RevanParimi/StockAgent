"""PR-011: insider trades, substantial acquisitions, promoter pledges and
shareholding changes, as company events and as discovery inputs.

The invariants, each with expected values worked by hand from the recorded
NSE payloads (tests/fixtures/company_events/, recorded 23 Oct 2026, names
replaced) and the card, not read back from the code:

- `published_at` is when NSE disseminated the filing ("when we could have
  known"), never the trade, pledge or quarter-end day, which is kept apart in
  `occurred_from`/`occurred_to`;
- a promoter-group sale while promoters hold more than 75% is not labelled
  negative; any other sale says the filing gives no reason;
- the quarter-on-quarter fixture (promoter 52.1% -> 50.6%) gives exactly one
  ownership event; moves under 1 point give none;
- an unavailable source or document gives no event and is named, never a
  neutral one; the next run asks again;
- the insider_buying signal is computed only when every listed filing was
  read, and is left out of the composite (not scored neutral) otherwise;
  mf_holding is deleted from config and ranking;
- a filing NSE lists as a revision is not new trading: its event is neutral
  and low and says so, and discovery counts each trade once, only when its
  last trade day is in the window (the live cases the fresh review named,
  recorded 23 Oct 2026: PATINTLOG 3886/3893, HTEL 3945/3922, NAUKRI 3962);
- discovery counts nothing for a promoter-group sale while promoters hold
  more than 75%, as the event calls it neutral;
- the pledge guard rejects more than 25% of the promoter holding pledged, and
  degrades, never passes, a symbol it could not check or whose row is more
  than 200 days old.

Transports are blocked by tests/hermetic.py; NSE is a fake client behind the
real fetchers (`_req` answers from the fixtures).
"""
from __future__ import annotations

import copy
import dataclasses
import json
import re
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
import pytest
import yaml

import core.discovery.guards as guards
import core.discovery.screen as scr
from backend.shared.schemas.events import CLASSIFIER_CATEGORIES, CompanyEvent
from core.config import settings
from core.discovery import insider as ins
from core.discovery import signals
from core.events import classify as cl
from core.events import disclosures as dz
from core.events import feed
from core.events.store import EventStore
from services.data.fetchers import nse_disclosures as nd

IST = ZoneInfo("Asia/Kolkata")
NOW = datetime(2026, 10, 23, 8, 15, tzinfo=IST)          # Friday, a trading day
FIX = Path(__file__).resolve().parents[1] / "fixtures" / "company_events"
REPO = Path(__file__).resolve().parents[2]
KARUR_XML_URL = "https://nsearchives.nseindia.com/corporate/xbrl/IT_539_WebXMLFile_20261022_192901476.xml"
SHP_SEP_URL = "https://nsearchives.nseindia.com/corporate/xbrl/SHP_1742414_21102026100118_WEB.xml"
SHP_JUN_URL = "https://nsearchives.nseindia.com/corporate/xbrl/SHP_1694756_17072026101742_WEB.xml"


def _rec() -> dict:
    return json.loads((FIX / "nse_disclosures_20261023.json").read_text("utf-8"))


def _doc(name: str) -> str:
    return (FIX / name).read_text("utf-8")


def _karur_row() -> dict:
    return _rec()["insider_list"][0]


def _karur() -> dz.PitFiling:
    return dz.parse_pit_xml(_doc("pit_karurvysya_20261022.xml"))


def _trade(who="promoter", action="buy", market=True, value=1e7, shares=100.0,
           mode=None, day_="2026-10-21") -> dz.Trade:
    mode = mode or ("Market Purchase" if action == "buy" else "Market Sale")
    category = {"promoter": "Promoter", "director": "Director", "other": "Designated Person"}[who]
    return dz.Trade(who=who, category=category, action=action, mode=mode, market=market,
                    shares=shares, value_inr=value, from_day=day_, to_day=day_)


def _filing(*trades) -> dz.PitFiling:
    return dz.PitFiling(symbol="KARURVYSYA", filed_on="2026-10-22",
                        regulation="Regulation 7 (2)", revised=False, trades=tuple(trades))


def _insider(filing, holding=None) -> CompanyEvent:
    return dz.insider_event(_karur_row(), filing, "KARURVYSYA", NOW.isoformat(), holding)


# ---------------------------------------------------------------------------
# Insider trades
# ---------------------------------------------------------------------------

def test_the_recorded_insider_filing_reads_each_persons_trade():
    filing = _karur()
    assert (filing.symbol, filing.filed_on, filing.regulation, filing.revised) == (
        "KARURVYSYA", "2026-10-22", "Regulation 7 (2)", False)
    assert [(t.category, t.who, t.action, t.mode, t.market, t.shares, t.value_inr,
             t.from_day, t.to_day) for t in filing.trades] == [
        ("Promoter", "promoter", "sell", "Market Sale", True, 2000.0, 769230.0,
         "2026-10-21", "2026-10-21"),
        ("Promoter Group", "promoter", "sell", "Market Sale", True, 2000.0, 769230.0,
         "2026-10-21", "2026-10-21"),
        ("Promoter Group", "promoter", "sell", "Market Sale", True, 2000.0, 769230.0,
         "2026-10-21", "2026-10-21"),
    ]


def test_an_insider_event_is_dated_by_nse_dissemination_not_by_the_trade():
    """Sold on 21 Oct, filed 22 Oct 19:29:01: new on 22 Oct, not on 21 Oct."""
    event = _insider(_karur())
    assert event.id == "nsepit:4038"
    assert event.published_at == "2026-10-22T19:29:01+05:30"
    assert event.published_raw == "22-Oct-2026 19:29:01"
    assert (event.occurred_from, event.occurred_to) == ("2026-10-21", "2026-10-21")
    assert event.fetched_at == NOW.isoformat()
    # 3 x Rs 7,69,230 = Rs 23,07,690 sold in the market, nothing bought
    assert event.facts["market_net_inr"] == -2307690.0
    assert (event.category, event.direction, event.materiality, event.source, event.classifier) == (
        "insider", "negative", "low", "nse_insider", "rules")
    assert event.what == ("The promoter group sold 6,000 shares worth ₹23.1 lakh in the market "
                          "on 21 Oct 2026. Filed with NSE on 22 Oct 2026. The filing gives no "
                          "reason for the sale.")
    assert "Person" not in event.model_dump_json()          # no names stored


def test_a_since_read_finds_the_filing_on_its_dissemination_day(tmp_path):
    store = EventStore(tmp_path)
    store.append_new("KARURVYSYA", [_insider(_karur())])
    assert [e.id for e in store.read("KARURVYSYA", since=date(2026, 10, 22))] == ["nsepit:4038"]
    assert store.read("KARURVYSYA", since=date(2026, 10, 23)) == []


@pytest.mark.parametrize("holding, direction, note", [
    ((78.2, "2026-09-30"), "neutral", "Promoters held 78.20% at 30 Sep 2026, above the 75%"),
    ((75.0, "2026-09-30"), "negative", "The filing gives no reason for the sale."),   # not above
    ((74.9, "2026-09-30"), "negative", "The filing gives no reason for the sale."),
    (None, "negative", "The filing gives no reason for the sale."),                   # unknown
])
def test_a_promoter_sale_above_the_75_percent_cap_is_not_called_negative(holding, direction, note):
    event = _insider(_karur(), holding)
    assert event.direction == direction
    assert note in event.what
    assert ("public-shareholding rule" in event.what) == (direction == "neutral")


def test_a_large_sale_above_the_cap_is_at_most_medium():
    big = _filing(_trade(action="sell", value=12e7))                  # Rs 12 crore
    assert (_insider(big, (80.0, "2026-09-30")).direction,
            _insider(big, (80.0, "2026-09-30")).materiality) == ("neutral", "medium")
    assert (_insider(big).direction, _insider(big).materiality) == ("negative", "high")


@pytest.mark.parametrize("value, materiality", [
    (10e7, "high"),            # Rs 10 crore
    (10e7 - 1, "medium"),
    (1e7, "medium"),           # Rs 1 crore
    (1e7 - 1, "low"),
])
def test_insider_materiality_is_the_open_market_net(value, materiality):
    event = _insider(_filing(_trade(action="buy", value=value)))
    assert (event.direction, event.materiality) == ("positive", materiality)


def test_only_promoter_and_director_market_trades_carry_a_direction():
    """Promoters buy Rs 3 crore, a director sells Rs 1 crore, an employee
    sells Rs 5 crore: the net is +Rs 2 crore; the employee counts nothing."""
    event = _insider(_filing(_trade("promoter", "buy", value=3e7),
                             _trade("director", "sell", value=1e7),
                             _trade("other", "sell", value=5e7)))
    assert event.facts["market_net_inr"] == 2e7
    assert (event.direction, event.materiality) == ("positive", "medium")
    assert "The promoter group bought" in event.what
    assert "Directors and key managers sold" in event.what
    assert "Designated employees and relatives sold" in event.what


def test_off_market_moves_and_employee_trades_are_neutral_and_low():
    gift = _insider(_filing(_trade("promoter", "sell", market=False, value=50e7, mode="Gift")))
    assert (gift.direction, gift.materiality) == ("neutral", "low")
    assert "disposed of 100 shares worth ₹50.0 crore by gift" in gift.what
    # the discovery signal reads the same net: a gift moves no rupees in it
    assert gift.facts["market_net_inr"] == 0.0
    assert dz.market_net([_trade("promoter", "sell", market=False, value=50e7, mode="Gift"),
                          _trade("director", "buy", market=False, value=9e7,
                                 mode="ESOP allotment")]) == 0.0
    staff = _insider(_filing(_trade("other", "sell", value=50e7)))
    assert (staff.direction, staff.materiality) == ("neutral", "low")


def test_the_recorded_inheritance_is_neutral():
    rec = _rec()
    filing = dz.parse_pit_xml(_doc("pit_reliance_20260522.xml"))
    event = dz.insider_event(rec["insider_list"][1], filing, "RELIANCE", NOW.isoformat(), None)
    assert (event.id, event.published_at, event.occurred_from) == (
        "nsepit:384", "2026-05-22T22:07:04+05:30", "2026-05-20")
    assert (event.direction, event.materiality) == ("neutral", "low")
    assert event.what == ("Designated employees and relatives acquired 880 shares worth ₹12.0 lakh "
                          "by inheritance on 20 May 2026. Filed with NSE on 22 May 2026.")


@pytest.mark.parametrize("category, group", [
    ("Promoter", "promoter"), ("Promoter Group", "promoter"),
    ("Member of the Promoter Group", "promoter"), ("Promoters", "promoter"),
    ("Immediate relative", "other"), ("Relatives Of Promoters Other Than Promoter Group", "other"),
    ("Director", "director"), ("Independent Director", "director"),
    ("Key Managerial Personnel", "director"), ("KMP", "director"),
    ("Designated Person", "other"), ("Employees/Designated Employees", "other"), ("", "other"),
])
def test_person_groups_follow_the_filing_category(category, group):
    assert dz.person_group(category) == group


@pytest.mark.parametrize("text", [
    "", "   ", None, 42,
    "<html><body>Resource not found</body></html>",
    "<?xml version='1.0'?><xbrli:xbrl xmlns:xbrli='http://www.xbrl.org/2003/instance'></xbrli:xbrl>",
])
def test_a_document_that_is_not_an_insider_filing_reads_as_none(text):
    assert dz.parse_pit_xml(text) is None


def test_a_truncated_or_entity_bearing_document_is_refused():
    whole = _doc("pit_karurvysya_20261022.xml")
    assert dz.parse_pit_xml(whole[: len(whole) // 2]) is None
    bomb = ('<?xml version="1.0"?><!DOCTYPE x [<!ENTITY a "aaaaaaaaaa"><!ENTITY b "&a;&a;&a;&a;">]>'
            + whole.split("?>", 1)[1].replace("Karur", "&b;"))
    assert dz.parse_pit_xml(bomb) is None


def test_insider_rows_keep_this_code_and_leave_future_rows_for_later():
    row = _karur_row()
    other = dict(row, symbol="KARURVYSYAX", appId="1")
    ahead = dict(row, appId="2", broadcastDateTime="23-Oct-2026 08:25:01")    # 10 min 1 s after
    edge = dict(row, appId="3", broadcastDateTime="23-Oct-2026 08:25:00")     # exactly 10 min
    kept, foreign, later = dz.insider_rows([row, other, ahead, edge, "junk"], "KARURVYSYA", NOW)
    assert [r["appId"] for r in kept] == ["3", "4038"]
    assert (foreign, later) == (1, 1)


# ---------------------------------------------------------------------------
# Substantial acquisitions and pledges
# ---------------------------------------------------------------------------

def test_the_recorded_sast_filings_are_neutral_deals_dated_by_filing():
    events, foreign, ahead = dz.sast_events(_rec()["sast"], "MARUTI", "MARUTI", NOW,
                                            NOW.isoformat(), date(2026, 6, 1))
    assert (foreign, ahead) == (0, 0)
    first = events[0]
    assert (first.id, first.published_at, first.occurred_from, first.occurred_to) == (
        "nsesast:171321", "2026-06-12T10:50:00+05:30", "2026-06-03", "2026-06-03")
    # LIC is not a promoter: neutral; Reg 29(1) is crossing 5%: medium
    assert (first.category, first.direction, first.materiality) == ("deal", "neutral", "medium")
    assert first.what == ("Life Insurance Corporation of India acquired 0.01% of the company "
                          "(51,750 shares) on 3 Jun 2026 and now holds 5.01%. SAST Regulation "
                          "29(1) filing, filed with NSE on 12 Jun 2026.")
    assert [e.id for e in events] == ["nsesast:171321", "nsesast:171318"]


def test_sast_rows_filed_before_the_window_are_not_events():
    events, _, _ = dz.sast_events(_rec()["sast"], "MARUTI", "MARUTI", NOW, NOW.isoformat(),
                                  date(2026, 6, 11))
    assert [e.id for e in events] == ["nsesast:171321"]          # 12 Jun kept, 10 Jun not


@pytest.mark.parametrize("promoter, sale, change, reg, direction, materiality", [
    ("Y", True, "2.50", "Reg29(2)", "negative", "high"),
    ("Y", False, "0.40", "Reg29(2)", "positive", "low"),
    ("N", True, "1.20", "Reg29(2)", "neutral", "medium"),
    ("N", False, "0.40", "Reg29(1)", "neutral", "medium"),
])
def test_sast_direction_belongs_to_promoters_only(promoter, sale, change, reg, direction,
                                                   materiality):
    row = dict(_rec()["sast"][0], promoterType=promoter, regType=reg,
               acqSaleType="Sale" if sale else "Acquisition",
               totSaleShare=change if sale else None, totAcqShare=None if sale else change,
               noOfShareSale="1000" if sale else None)
    (event,), _, _ = dz.sast_events([row], "MARUTI", "MARUTI", NOW, NOW.isoformat(),
                                    date(2026, 6, 1))
    assert (event.direction, event.materiality) == (direction, materiality)
    assert (" sold " in event.what) == sale


def test_the_recorded_pledge_releases_are_positive_and_name_no_one():
    rows = _rec()["pledge_events"]
    (event,), _, _ = dz.pledge_events(rows[:1], "VINCOFE", "VINCOFE", NOW, NOW.isoformat(),
                                      date(2026, 10, 16))
    assert (event.id, event.published_at, event.occurred_from) == (
        "nsepledge:43716", "2026-10-22T20:49:10+05:30", "2026-10-08")
    assert (event.category, event.direction, event.materiality) == ("pledge", "positive", "medium")
    assert event.what == ("A promoter released a pledge on 2.86% of the company's shares "
                          "(41,85,205 shares) on 8 Oct 2026; that promoter's encumbered shares are "
                          "now 0.00% of the company. SAST Regulation 31 disclosure, filed with NSE "
                          "on 22 Oct 2026.")
    dumped = event.model_dump_json()
    assert "Promoter A" not in dumped and "Lender" not in dumped
    # a row for another code is dropped and counted
    _, foreign, _ = dz.pledge_events(rows, "VINCOFE", "VINCOFE", NOW, NOW.isoformat(),
                                     date(2026, 10, 16))
    assert foreign == 1


@pytest.mark.parametrize("kind, pct, direction, materiality", [
    ("Creation", "2.86", "negative", "high"),
    ("Creation", "0.60", "negative", "medium"),
    ("Creation", "0.30", "negative", "low"),
    ("Invocation", "0.10", "negative", "high"),
    ("Release", "8.00", "positive", "medium"),
])
def test_pledge_direction_and_size(kind, pct, direction, materiality):
    row = dict(_rec()["pledge_events"][0], eventDetailsType=kind, eventDetailsPerc=pct)
    (event,), _, _ = dz.pledge_events([row], "VINCOFE", "VINCOFE", NOW, NOW.isoformat(),
                                      date(2026, 10, 16))
    assert (event.direction, event.materiality) == (direction, materiality)


# ---------------------------------------------------------------------------
# Ownership
# ---------------------------------------------------------------------------

def _quarters(**promoter) -> list[dict]:
    rows = copy.deepcopy(_rec()["shareholding_list"])
    for row in rows:
        if row["date"] in promoter:
            row["pr_and_prgrp"] = promoter[row["date"]]
    return dz.quarters_from_list(rows, "MARUTI")


def test_the_card_fixture_promoter_52_1_to_50_6_gives_one_ownership_event():
    """The recorded MARUTI list with promoter % set to 52.1 (30 Jun) and 50.6
    (30 Sep), no XBRL read: one event, dated by the filing of 21 Oct 10:01:23."""
    q = _quarters(**{"30-JUN-2026": "52.1", "30-SEP-2026": "50.6"})
    event = dz.ownership_event(q[0], q[1], "MARUTI", NOW.isoformat(), 1.0)
    assert event is not None
    assert (event.id, event.category, event.direction, event.materiality) == (
        "nseshp:2026-09-30", "ownership", "negative", "medium")
    assert (event.published_at, event.occurred_from, event.occurred_to) == (
        "2026-10-21T10:01:23+05:30", "2026-09-30", "2026-09-30")
    assert event.what == ("Between 30 Jun 2026 and 30 Sep 2026 the promoter holding fell from "
                          "52.10% to 50.60% (-1.50 points). Shareholding pattern filed with NSE "
                          "on 21 Oct 2026. The pattern does not say whether promoters sold or new "
                          "shares diluted their stake.")
    assert event.facts["unavailable"] == ["fii", "dii", "mf"]
    assert event.facts["promoter"] == [52.1, 50.6]


def test_the_recorded_quarters_moved_under_a_point_and_give_no_event():
    """Recorded: promoter 58.65 -> 58.72, FII 12.82 -> 12.42, DII 25.18 ->
    25.41, MF 15.33 -> 14.77. No category moved a point."""
    q = dz.quarters_from_list(_rec()["shareholding_list"], "MARUTI")
    sep = dz.parse_shareholding_xbrl(_doc("shp_maruti_20260930.xml"))
    jun = dz.parse_shareholding_xbrl(_doc("shp_maruti_20260630.xml"))
    assert (sep["promoter"], sep["fii"], sep["dii"], sep["mf"]) == (58.72, 12.42, 25.41, 14.77)
    assert (jun["promoter"], jun["fii"], jun["dii"], jun["mf"]) == (58.65, 12.82, 25.18, 15.33)
    latest = {**q[0], **{k: sep[k] for k in ("fii", "dii", "mf")}}
    before = {**q[1], **{k: jun[k] for k in ("fii", "dii", "mf")}}
    assert dz.ownership_event(latest, before, "MARUTI", NOW.isoformat(), 1.0) is None
    # the same pair at a 0.5-point threshold: MF (-0.56) is the only move
    event = dz.ownership_event(latest, before, "MARUTI", NOW.isoformat(), 0.5)
    assert event.facts["moved"] == ["mf"] and event.direction == "negative"


@pytest.mark.parametrize("after, made", [("51.10", True), ("51.11", True), ("51.09", False)])
def test_the_one_point_boundary(after, made):
    q = _quarters(**{"30-JUN-2026": "50.10", "30-SEP-2026": after})
    assert (dz.ownership_event(q[0], q[1], "MARUTI", NOW.isoformat(), 1.0) is not None) == made


def test_mixed_moves_are_neutral_and_three_points_is_high():
    latest = {"quarter_end": "2026-09-30", "promoter": 50.6, "fii": 21.2, "dii": None, "mf": None,
              "published_at": "2026-10-21T10:01:23+05:30"}
    before = {"quarter_end": "2026-06-30", "promoter": 52.1, "fii": 18.0, "dii": None, "mf": None}
    event = dz.ownership_event(latest, before, "MARUTI", NOW.isoformat(), 1.0)
    assert (event.direction, event.materiality) == ("neutral", "high")
    assert event.facts["moved"] == ["fii", "promoter"]


def test_the_shareholding_parser_reads_category_totals_not_scheme_rows():
    """The trimmed XBRL keeps one mutual-fund scheme's detail row (3.33%) and
    the FPI category-one row (12.00%); the parser reads the totals."""
    text = _doc("shp_maruti_20260930.xml")
    assert "0.0333" in text and "0.12<" in text
    assert dz.parse_shareholding_xbrl(text)["mf"] == 14.77
    assert dz.parse_shareholding_xbrl(text)["fii"] == 12.42
    assert dz.parse_shareholding_xbrl("<html>Server busy</html>") is None
    assert dz.parse_shareholding_xbrl(text[:2000]) is None


def test_quarters_take_the_latest_revision_and_only_this_code():
    rows = copy.deepcopy(_rec()["shareholding_list"])
    revised = dict(rows[0], pr_and_prgrp="58.80", broadcastDate="22-OCT-2026 09:00:00")
    other = dict(rows[0], symbol="MARUTIX", pr_and_prgrp="1.0")
    q = dz.quarters_from_list(rows + [revised, other], "MARUTI")
    assert [x["quarter_end"] for x in q] == ["2026-09-30", "2026-06-30", "2026-03-31"]
    assert (q[0]["promoter"], q[0]["published_at"]) == (58.8, "2026-10-22T09:00:00+05:30")


@pytest.mark.parametrize("category, stored", [
    ("insider", False), ("pledge", False), ("ownership", False), ("deal", True)])
def test_the_classifier_may_not_answer_a_disclosure_category(monkeypatch, category, stored):
    """A model answering "insider" for an announcement is invalid: only the
    rules write the disclosure categories."""
    from core.events.sources import SourceItem
    item = SourceItem(source="nse_announcement", source_id="nse:1", title="Disclosure under SEBI PIT",
                      text="Promoter sold shares", url=None, announcement_id="1",
                      published_at="2026-10-22T10:00:00+05:30", published_raw="22-Oct-2026 10:00:00")
    monkeypatch.setattr(cl, "_call_llm", lambda system, user: json.dumps({"events": [
        {"item": 1, "about_company": True, "what": "Promoter sold shares.", "category": category,
         "direction": "negative", "materiality": "low"}]}))
    result = cl.classify_items("MARUTI", "Maruti Suzuki India Limited", [item],
                               fetched_at=NOW.isoformat())
    assert (len(result.events), result.invalid) == ((1, 0) if stored else (0, 1))
    assert not {"insider", "pledge", "ownership"} & set(CLASSIFIER_CATEGORIES)


# ---------------------------------------------------------------------------
# A fake NSE behind the real fetchers
# ---------------------------------------------------------------------------

class _Resp:
    def __init__(self, payload=None, body: bytes | None = None):
        self._payload = payload
        self.content = body if body is not None else json.dumps(payload).encode()
        self.status_code = 200

    def json(self):
        return self._payload


_DATE_FIELDS = ("broadcastDateTime", "timestamp", "broadcastdate")


def _in_range(row: dict, params: dict) -> bool:
    if "from_date" not in params:
        return True
    raw = next((row[k] for k in _DATE_FIELDS if row.get(k)), "")
    filed = datetime.strptime(raw.split()[0], "%d-%b-%Y").date()
    lo = datetime.strptime(params["from_date"], "%d-%m-%Y").date()
    hi = datetime.strptime(params["to_date"], "%d-%m-%Y").date()
    return lo <= filed <= hi


class FakeNse:
    """`_req` as the nse client has it: API rows by (endpoint, symbol),
    filtered by dissemination day as NSE does, and archive documents by URL."""

    def __init__(self, api: dict, docs: dict, fail: set | None = None):
        self.api, self.docs, self.fail = api, docs, fail or set()
        self.calls: list[tuple] = []

    def _req(self, url, params=None):
        params = dict(params or {})
        if url.startswith("https://nsearchives.nseindia.com/"):
            self.calls.append(("document", url.rsplit("/", 1)[-1]))
            if url in self.fail:
                raise ConnectionError(f"{url} 503: Service Unavailable")
            return _Resp(body=self.docs[url].encode("utf-8"))
        endpoint = url.rsplit("/api/", 1)[-1]
        key = (endpoint, params.get("symbol"))
        self.calls.append(("api", endpoint, params.get("symbol"), params.get("from_date"),
                           params.get("to_date")))
        if key in self.fail:
            raise ConnectionError(f"{url} 503: Service Unavailable")
        rows = [r for r in self.api.get(key, []) if _in_range(r, params)]
        return _Resp({"data": rows})


def _feed_api() -> dict:
    rec = _rec()
    sast = dict(rec["sast"][0], timestamp="22-Oct-2026 11:05", sysTime="22-Oct-2026 11:05")
    return {
        ("corporates-pit-gg", "KARURVYSYA"): [rec["insider_list"][0]],
        ("corporate-sast-reg29", "MARUTI"): [sast],
        ("corporate-share-holdings-master", "MARUTI"): rec["shareholding_list"],
        ("corporate-pledgedata-sast3132", "VINCOFE"): [rec["pledge_events"][0]],
    }


def _feed_docs() -> dict:
    return {KARUR_XML_URL: _doc("pit_karurvysya_20261022.xml"),
            SHP_SEP_URL: _doc("shp_maruti_20260930.xml"),
            SHP_JUN_URL: _doc("shp_maruti_20260630.xml")}


@pytest.fixture()
def disclosure_feed(tmp_path, monkeypatch):
    for name, value in (("EVENTS_ENABLED", True), ("EVENTS_DATA_DIR", str(tmp_path / "events")),
                        ("EVENTS_MAX_SYMBOLS", 60), ("EVENTS_NEWS_QUERIES_PER_DAY", 0),
                        ("EVENTS_LOOKBACK_DAYS", 7), ("EVENTS_SEEN_DAYS", 30),
                        ("EVENTS_INGEST_ON_RESULTS", False),
                        ("EVENTS_DISCLOSE_INSIDER", True), ("EVENTS_DISCLOSE_SAST", True),
                        ("EVENTS_DISCLOSE_PLEDGE", True), ("EVENTS_DISCLOSE_OWNERSHIP", True),
                        ("EVENTS_OWNERSHIP_MOVE_POINTS", 1.0),
                        ("EVENTS_MAX_DOCUMENTS_PER_SYMBOL", 10)):
        monkeypatch.setattr(settings, name, value)
    monkeypatch.setattr(nd, "_SLEEP_BETWEEN_CALLS", 0)
    env = {"nse": FakeNse(_feed_api(), _feed_docs()), "store": EventStore(tmp_path / "events"),
           "tracked": [("KARURVYSYA", "held"), ("MARUTI", "watched"), ("VINCOFE", "shelf")]}
    monkeypatch.setattr(feed, "tracked_symbols", lambda: list(env["tracked"]))
    monkeypatch.setattr(feed, "_identity_issue", lambda s, on: "")
    monkeypatch.setattr(feed, "_nse_code", lambda s, on: s)
    monkeypatch.setattr(feed, "_make_nse", lambda: env["nse"])
    monkeypatch.setattr(feed, "_close_nse", lambda n: None)
    monkeypatch.setattr(feed, "_fetch_filings", lambda nse, code, since, until: {
        "announcements": [], "board_meetings": [], "error": None})
    monkeypatch.setattr(feed, "_news_query", lambda s: (f"{s} NSE India company news", ""))
    monkeypatch.setattr(feed, "_search_usage", lambda: {"calls": 0, "limit": 2500})

    def no_model(system, user):
        raise AssertionError("a disclosure must never reach the classifier")
    monkeypatch.setattr(cl, "_call_llm", no_model)
    return env


def _documents(env) -> list[str]:
    return [c[1] for c in env["nse"].calls if c[0] == "document"]


def test_a_feed_run_stores_each_disclosure_once_without_the_model(disclosure_feed):
    env = disclosure_feed
    rec = feed.run_event_feed("am", now=NOW, store=env["store"])
    assert rec["status"] == "ok", rec
    assert rec["disclosures_stored"] == {"insider": 1, "deal": 1, "pledge": 1, "ownership": 0}
    assert rec["llm_calls"] == 0
    # one insider XBRL and MARUTI's two quarters' shareholding XBRLs
    assert sorted(_documents(env)) == sorted(u.rsplit("/", 1)[-1] for u in _feed_docs())
    assert rec["documents_fetched"] == 3 and rec["documents_failed"] == 0
    # the window went out as NSE's DD-MM-YYYY, 7 days back from 23 Oct
    pit = [c for c in env["nse"].calls if c[0] == "api" and c[1] == "corporates-pit-gg"]
    assert pit[0][2:] == ("KARURVYSYA", "16-10-2026", "23-10-2026")
    (insider,) = env["store"].load("KARURVYSYA")
    assert (insider.id, insider.published_at, insider.occurred_from) == (
        "nsepit:4038", "2026-10-22T19:29:01+05:30", "2026-10-21")
    assert insider.fetched_at == NOW.isoformat(timespec="seconds")
    (deal,) = env["store"].load("MARUTI")
    assert (deal.category, deal.published_at, deal.occurred_from) == (
        "deal", "2026-10-22T11:05:00+05:30", "2026-06-03")
    (pledge,) = env["store"].load("VINCOFE")
    assert (pledge.category, pledge.direction) == ("pledge", "positive")
    # MARUTI's promoter holding (58.72%) was known to the insider rule's run
    assert env["store"].load_ownership("MARUTI") == {
        "2026-09-30": {"fii": 12.42, "dii": 25.41, "mf": 14.77, "read": True},
        "2026-06-30": {"fii": 12.82, "dii": 25.18, "mf": 15.33, "read": True}}


def test_the_next_run_fetches_no_document_again_and_stores_nothing(disclosure_feed):
    env = disclosure_feed
    feed.run_event_feed("am", now=NOW, store=env["store"])
    env["nse"].calls.clear()
    rec = feed.run_event_feed("pm", now=NOW.replace(hour=18, minute=30), store=env["store"])
    assert rec["disclosures_stored"] == {"insider": 0, "deal": 0, "pledge": 0, "ownership": 0}
    assert _documents(env) == [] and rec["documents_fetched"] == 0
    assert [len(env["store"].load(s)) for s in ("KARURVYSYA", "MARUTI", "VINCOFE")] == [1, 1, 1]


def test_a_failed_document_stores_nothing_and_the_next_run_asks_again(disclosure_feed):
    env = disclosure_feed
    env["nse"].fail = {KARUR_XML_URL}
    rec = feed.run_event_feed("am", now=NOW, store=env["store"])
    assert env["store"].load("KARURVYSYA") == []
    assert rec["status"] == "partial"
    assert rec["disclosures_failed"]["KARURVYSYA"].startswith("insider: document:")
    assert rec["documents_failed"] == 1
    env["nse"].fail = set()
    rec = feed.run_event_feed("pm", now=NOW.replace(hour=18, minute=30), store=env["store"])
    assert [e.id for e in env["store"].load("KARURVYSYA")] == ["nsepit:4038"]
    assert rec["status"] == "ok"


def test_a_failed_endpoint_gives_no_event_and_is_named(disclosure_feed):
    """Unavailable is not neutral: no event is made for a source that did
    not answer, the run says which, and is partial."""
    env = disclosure_feed
    env["nse"].fail = {("corporate-share-holdings-master", "MARUTI"),
                       ("corporate-sast-reg29", "MARUTI")}
    rec = feed.run_event_feed("am", now=NOW, store=env["store"])
    assert env["store"].load("MARUTI") == []
    failed = rec["disclosures_failed"]["MARUTI"]
    assert "sast: corporate-sast-reg29" in failed and "shareholding:" in failed
    assert rec["status"] == "partial"


def test_without_the_shareholding_list_insider_filings_wait(disclosure_feed):
    """The 75% rule needs the latest pattern. With the list down, KARURVYSYA's
    sale is not stored with a guessed label; no document is fetched, and the
    next run, with the list answering, stores it."""
    env = disclosure_feed
    env["nse"].fail = {("corporate-share-holdings-master", "KARURVYSYA")}
    rec = feed.run_event_feed("am", now=NOW, store=env["store"])
    assert env["store"].load("KARURVYSYA") == []
    assert KARUR_XML_URL.rsplit("/", 1)[-1] not in _documents(env)
    failed = rec["disclosures_failed"]["KARURVYSYA"]
    assert "insider: waiting for the shareholding list" in failed and "shareholding:" in failed
    env["nse"].fail = set()
    feed.run_event_feed("pm", now=NOW.replace(hour=18, minute=30), store=env["store"])
    assert [e.id for e in env["store"].load("KARURVYSYA")] == ["nsepit:4038"]


def test_a_switched_off_source_is_not_asked(disclosure_feed, monkeypatch):
    env = disclosure_feed
    monkeypatch.setattr(settings, "EVENTS_DISCLOSE_PLEDGE", False)
    rec = feed.run_event_feed("am", now=NOW, store=env["store"])
    assert not [c for c in env["nse"].calls if c[0] == "api"
                and c[1] == "corporate-pledgedata-sast3132"]
    assert env["store"].load("VINCOFE") == []
    assert "pledge" not in rec["disclosure_sources"]


def test_a_document_for_another_company_is_never_stored_under_this_one(disclosure_feed):
    env = disclosure_feed
    env["nse"].docs[KARUR_XML_URL] = env["nse"].docs[KARUR_XML_URL].replace(
        ">KARURVYSYA<", ">OTHERBANK<")
    rec = feed.run_event_feed("am", now=NOW, store=env["store"])
    assert env["store"].load("KARURVYSYA") == []
    assert rec["nse_rows_foreign"] == 1


def test_an_ownership_move_is_stored_once_and_a_disagreeing_xbrl_is_not_used(disclosure_feed):
    """The list says 52.1% -> 50.6%; the XBRLs say 58.65% / 58.72%. The
    documents disagree with the list by more than half a point, so their FII,
    DII and MF figures are not used; the promoter move is stored once."""
    env = disclosure_feed
    rows = copy.deepcopy(_rec()["shareholding_list"])
    rows[0]["pr_and_prgrp"], rows[1]["pr_and_prgrp"] = "50.6", "52.1"
    env["nse"].api[("corporate-share-holdings-master", "MARUTI")] = rows
    rec = feed.run_event_feed("am", now=NOW, store=env["store"])
    assert rec["disclosures_stored"]["ownership"] == 1
    assert rec["ownership_mismatch"] == 2
    owner = [e for e in env["store"].load("MARUTI") if e.category == "ownership"]
    assert [(e.id, e.direction, e.facts["unavailable"]) for e in owner] == [
        ("nseshp:2026-09-30", "negative", ["fii", "dii", "mf"])]
    rec = feed.run_event_feed("pm", now=NOW.replace(hour=18, minute=30), store=env["store"])
    assert rec["disclosures_stored"]["ownership"] == 0 and rec["documents_fetched"] == 0


def test_the_document_fetcher_refuses_any_other_host():
    nse = FakeNse({}, {})
    for url in ("https://evil.example.com/x.xml", "http://nsearchives.nseindia.com/x.xml",
                None, 7, "file:///etc/passwd"):
        assert nd.fetch_document(nse, url) == (None, "not an NSE archive URL")
    assert nse.calls == []


def test_the_fetchers_never_raise_on_odd_answers():
    class Odd:
        def __init__(self, payload):
            self.payload = payload

        def _req(self, url, params=None):
            if isinstance(self.payload, Exception):
                raise self.payload
            return _Resp(self.payload)
    for payload, rows, error in (({"data": []}, [], None), ([], [], None),
                                 ({"data": [{"a": 1}, "x"]}, [{"a": 1}], None),
                                 ({"error": "busy"}, [], "unexpected response: dict"),
                                 ("oops", [], "unexpected response: str")):
        assert nd.shareholding_quarters(Odd(payload), "MARUTI") == (rows, error)
    got, error = nd.sast_filings(Odd(TimeoutError("read timed out")), "MARUTI",
                                 date(2026, 10, 16), date(2026, 10, 23))
    assert got == [] and error.startswith("corporate-sast-reg29: read timed out")


# ---------------------------------------------------------------------------
# Discovery: the insider_buying signal
# ---------------------------------------------------------------------------

BUYER_URL = "https://nsearchives.nseindia.com/corporate/xbrl/IT_9001_WebXMLFile_20261020.xml"


def _buyer_xml() -> str:
    """The recorded KARURVYSYA filing turned into BUYERCO's promoters buying
    3 x Rs 1.5 crore in the market."""
    return (_doc("pit_karurvysya_20261022.xml").replace(">KARURVYSYA<", ">BUYERCO<")
            .replace(">Sell<", ">Buy<").replace(">Market Sale<", ">Market Purchase<")
            .replace(">769230<", ">15000000<"))


def _market(env_rows=None) -> FakeNse:
    rec = _rec()
    buyer = dict(rec["insider_list"][0], symbol="BUYERCO", appId="9001",
                 broadcastDateTime="20-Oct-2026 18:00:00", xmlFileName=BUYER_URL)
    reliance = dict(rec["insider_list"][1], broadcastDateTime="19-Oct-2026 21:00:00")
    rows = env_rows if env_rows is not None else [rec["insider_list"][0], buyer, reliance]
    docs = {KARUR_XML_URL: _doc("pit_karurvysya_20261022.xml"), BUYER_URL: _buyer_xml(),
            reliance["xmlFileName"]: _doc("pit_reliance_20260522.xml")}
    return FakeNse({("corporates-pit-gg", None): rows}, docs)


@pytest.fixture()
def insider_env(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "DISCOVERY_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(settings, "DISCOVERY_INSIDER_WINDOW_DAYS", 28)
    monkeypatch.setattr(settings, "DISCOVERY_INSIDER_MAX_DOCUMENTS", 600)
    env = {"nse": _market()}
    monkeypatch.setattr(ins, "_make_nse", lambda: env["nse"])
    monkeypatch.setattr(ins, "_close_nse", lambda n: None)
    return env


def test_every_listed_filing_is_read_once_and_netted_per_company(insider_env):
    on = date(2026, 10, 23)
    summary = ins.refresh_insider_trades(on)
    assert (summary["listed"], summary["read_now"], summary["unread"], summary["complete"]) == (
        3, 3, 0, True)
    calls = [c for c in insider_env["nse"].calls if c[0] == "api"]
    # the list once, then the promoter share of the one company with a
    # promoter-group sale (KARURVYSYA); NSE gives none here, so it counts
    assert calls == [("api", "corporates-pit-gg", None, "25-09-2026", "23-10-2026"),
                     ("api", "corporate-share-holdings-master", "KARURVYSYA", None, None)]
    cache, why = ins.usable_insider_trades(on)
    assert why is None
    assert cache["promoter_holding"] == {"KARURVYSYA": [None, None]}
    net = ins.net_by_symbol(cache, ["BUYERCO", "KARURVYSYA", "RELIANCE", "QUIETCO"])
    # BUYERCO +Rs 4.5 crore; KARURVYSYA -Rs 23,07,690 (three persons' identical
    # sales in one filing, each counted); RELIANCE's inheritance 0; no filing 0
    assert net.to_dict() == {"BUYERCO": 4.5, "KARURVYSYA": -0.230769, "RELIANCE": 0.0,
                             "QUIETCO": 0.0}
    insider_env["nse"].calls.clear()
    again = ins.refresh_insider_trades(on)
    assert again["read_now"] == 0 and again["complete"]
    assert [c for c in insider_env["nse"].calls if c[0] == "document"] == []


def test_a_capped_or_failed_read_makes_the_signal_unavailable_until_complete(insider_env,
                                                                             monkeypatch):
    on = date(2026, 10, 23)
    monkeypatch.setattr(settings, "DISCOVERY_INSIDER_MAX_DOCUMENTS", 1)
    first = ins.refresh_insider_trades(on)
    assert (first["read_now"], first["unread"], first["complete"]) == (1, 2, False)
    assert ins.usable_insider_trades(on) == (None, "insider_buying: 2 of 3 filings unread")
    insider_env["nse"].fail = {BUYER_URL}
    monkeypatch.setattr(settings, "DISCOVERY_INSIDER_MAX_DOCUMENTS", 600)
    second = ins.refresh_insider_trades(on)
    assert (second["failed"], second["unread"], second["complete"]) == (1, 1, False)
    insider_env["nse"].fail = set()
    assert ins.refresh_insider_trades(on)["complete"] is True


def test_a_failed_list_or_stale_cache_is_unavailable(insider_env):
    on = date(2026, 10, 23)
    insider_env["nse"].fail = {("corporates-pit-gg", None)}
    summary = ins.refresh_insider_trades(on)
    assert summary["complete"] is False and summary["error"].startswith("corporates-pit-gg:")
    cache, why = ins.usable_insider_trades(on)
    assert cache is None and why.startswith("insider_buying: corporates-pit-gg:")
    insider_env["nse"].fail = set()
    ins.refresh_insider_trades(on)
    assert ins.usable_insider_trades(on + timedelta(days=7))[1] is None
    assert ins.usable_insider_trades(on + timedelta(days=8)) == (
        None, "insider_buying: filings read up to 2026-10-23 only")


def test_more_than_a_tenth_unreadable_means_a_changed_format(insider_env):
    nse = insider_env["nse"]
    nse.docs[BUYER_URL] = "<html>Moved</html>"
    summary = ins.refresh_insider_trades(date(2026, 10, 23))
    assert summary["unreadable"] == ["nsepit:9001"] and summary["complete"] is False


def _win(symbols) -> pd.DataFrame:
    return pd.DataFrame([{"symbol": s, "series": "EQ", "date": "2026-10-23", "prev_close": 99.0,
                          "open": 99.0, "high": 101.0, "low": 98.0, "close": 100.0,
                          "volume": 1.0, "traded_value_cr": 6.0, "delivery_qty": 1.0,
                          "delivery_pct": 40.0} for s in symbols])


@pytest.fixture()
def ranked(tmp_path, monkeypatch, insider_env):
    """run_screen over AAA..DDD: momentum ranks AAA > BBB > CCC > DDD, and
    DDD's promoters bought (the real insider signal from the cache)."""
    monkeypatch.setattr(scr.settings, "DISCOVERY_SHORTLIST_SIZE", 4)
    monkeypatch.setattr(scr.settings, "DISCOVERY_MAX_CANDIDATES", 4)
    monkeypatch.setattr(scr.settings, "DISCOVERY_SIGNAL_WEIGHTS", dict(settings.DISCOVERY_SIGNAL_WEIGHTS))
    win = _win(["AAA", "BBB", "CCC", "DDD"])

    class _Store:
        def load_window(self, end, sessions):
            return win

        def latest_day(self):
            return date(2026, 10, 23)
    monkeypatch.setattr(scr, "EodStore", lambda: _Store())
    monkeypatch.setattr(scr, "build_universe", lambda w: ["AAA", "BBB", "CCC", "DDD"])
    monkeypatch.setattr(scr, "load_listing", lambda: None)
    monkeypatch.setattr(scr, "load_bulk_block", lambda: {"degraded": True, "deals": []})
    monkeypatch.setattr(scr, "apply_guards", lambda shortlist, w: (list(shortlist), {}, []))

    def compute(w, u, c, insider_cache=None):
        out = signals.compute_signals(w, u, c, insider_cache)      # the real slots
        out["momentum"] = pd.Series({"AAA": 4.0, "BBB": 3.0, "CCC": 2.0, "DDD": 1.0})
        return out
    monkeypatch.setattr(scr, "compute_signals", compute)
    rows = [dict(_rec()["insider_list"][0], symbol="DDD", appId="9001",
                 broadcastDateTime="20-Oct-2026 18:00:00", xmlFileName=BUYER_URL)]
    insider_env["nse"] = _market(rows)
    insider_env["nse"].docs[BUYER_URL] = _buyer_xml().replace(">BUYERCO<", ">DDD<")
    return insider_env


def _composite(result) -> dict:
    return {c.symbol: c.composite for c in result.candidates}


def test_ranking_with_insider_buying_present(ranked):
    """Weights 0.30 and 0.10 renormalise to 0.75 and 0.25. Momentum ranks
    1, .75, .5, .25; insider ranks .5 for the three ties at 0 and 1 for DDD.
    AAA .875, BBB .6875, CCC .5, DDD .1875 + .25 = .4375."""
    ins.refresh_insider_trades(date(2026, 10, 23))
    result = scr.run_screen(on=date(2026, 10, 23))
    assert "insider_buying" not in result.dark_signals
    assert _composite(result) == {"AAA": 0.875, "BBB": 0.6875, "CCC": 0.5, "DDD": 0.4375}
    assert not [c for c in result.degraded_checks if c.startswith("insider_buying")]


def test_ranking_with_insider_buying_unavailable_is_not_neutral(ranked):
    """No cache: the signal is left out and named; the composite is momentum
    alone (1, .75, .5, .25). Scored neutral it would read .875 .. .4375 minus
    DDD's buying, i.e. .875, .6875, .5, .3125."""
    result = scr.run_screen(on=date(2026, 10, 23))
    assert "insider_buying" in result.dark_signals
    assert "insider_buying: no insider-trade cache" in result.degraded_checks
    assert _composite(result) == {"AAA": 1.0, "BBB": 0.75, "CCC": 0.5, "DDD": 0.25}


def test_mf_holding_is_deleted_from_config_and_ranking(ranked):
    config = yaml.safe_load((REPO / "config.yaml").read_text("utf-8"))
    assert set(config["discovery"]["signal_weights"]) == {
        "momentum", "delivery_surge", "volume_breakout", "bulk_block", "high_52wk_rs",
        "insider_buying"}
    assert "mf_holding" not in settings.DISCOVERY_SIGNAL_WEIGHTS
    out = signals.compute_signals(_win(["AAA"]), ["AAA"], None, None)
    assert "mf_holding" not in out
    result = scr.run_screen(on=date(2026, 10, 23))
    assert "mf_holding" not in result.dark_signals
    assert all("mf_holding" not in c.signal_ranks for c in result.candidates)


# ---------------------------------------------------------------------------
# Revisions: a corrected filing is not new trading
# ---------------------------------------------------------------------------
# NSE lists a revision as a new filing with its own appId and rarely names the
# filing it corrects. The cases below are NSE's live rows and XBRLs, recorded
# 23 Oct 2026 (tests/fixtures/company_events/nse_pit_revisions_20261023.json).

NOW_PAT = datetime(2026, 10, 1, 18, 30, tzinfo=IST)      # Thursday, the 18:30 run
REVISION_NOTE = ("It revises an earlier filing, so these trades may have been reported before "
                 "and are not read as new trading.")
PAT_TRADES = ("The promoter group bought 2,63,832 shares worth ₹36.6 lakh in the market on "
              "23 Sep 2026 to 29 Sep 2026; The promoter group sold 2,63,832 shares worth "
              "₹35.9 lakh in the market on 23 Sep 2026 to 29 Sep 2026. Filed with NSE on "
              "1 Oct 2026.")


def _revisions() -> dict[str, dict]:
    rows = json.loads((FIX / "nse_pit_revisions_20261023.json").read_text("utf-8"))["rows"]
    return {r["appId"]: r for r in rows}


def _rev_doc(app_id: str) -> str:
    return _doc(f"pit_{_revisions()[app_id]['symbol'].lower()}_{app_id}.xml")


def _refresh(env, *app_ids, on=date(2026, 10, 23), docs=None):
    """A fresh cache over the recorded rows `app_ids` (documents as recorded,
    or as `docs` gives them): (summary, usable cache, why not)."""
    rows = [_revisions()[a] for a in app_ids]
    env["nse"] = FakeNse({("corporates-pit-gg", None): rows},
                         {r["xmlFileName"]: (docs or {}).get(r["appId"]) or _rev_doc(r["appId"])
                          for r in rows})
    ins._path().unlink(missing_ok=True)
    summary = ins.refresh_insider_trades(on)
    return (summary, *ins.usable_insider_trades(on))


def test_the_recorded_revisions_read_as_nse_sent_them():
    rows = _revisions()
    assert [(a, r["symbol"], r["typeOfSubmission"], r["prevAppId"], r["broadcastDateTime"])
            for a, r in sorted(rows.items())] == [
        ("3762", "HTEL", "Original", None, "29-Sep-2026 18:04:16"),
        ("3886", "PATINTLOG", "Original", None, "01-Oct-2026 17:11:45"),
        ("3893", "PATINTLOG", "Revision", None, "01-Oct-2026 18:23:57"),
        ("3922", "HTEL", "Revision", None, "06-Oct-2026 17:14:34"),
        ("3945", "HTEL", "Original", None, "05-Oct-2026 18:07:55"),
        ("3962", "NAUKRI", "Revision", "47977", "08-Oct-2026 17:27:52")]
    trades = {a: [(t.who, t.action, t.market, t.shares, t.value_inr, t.from_day, t.to_day)
                  for t in dz.parse_pit_xml(_rev_doc(a)).trades] for a in rows}
    assert {a: dz.parse_pit_xml(_rev_doc(a)).revised for a in rows} == {
        "3762": False, "3886": False, "3893": True, "3922": True, "3945": False, "3962": True}
    assert trades["3762"] == [("promoter", "buy", True, 125000.0, 8585000.0, "2026-09-29",
                               "2026-09-29")]
    assert trades["3886"] == trades["3893"] == [
        ("promoter", "sell", True, 263832.0, 3590951.0, "2026-09-23", "2026-09-29"),
        ("promoter", "buy", True, 263832.0, 3662165.0, "2026-09-23", "2026-09-29")]
    four = [("other", "buy", True, 25000.0, 1650250.0, "2026-09-28", "2026-09-28"),
            ("other", "buy", True, 8000.0, 516480.0, "2026-09-28", "2026-09-28"),
            ("other", "buy", True, 15000.0, 1025400.0, "2026-09-29", "2026-09-29"),
            ("other", "buy", True, 25000.0, 1717750.0, "2026-09-29", "2026-09-29")]
    assert trades["3945"] == four
    assert trades["3922"] == four + [("other", "buy", True, 150.0, 10145.0, "2026-09-25",
                                      "2026-09-25")]
    assert trades["3962"] == [("director", "sell", True, 500000.0, 680478416.0, "2026-08-18",
                               "2026-08-20")]
    for a in rows:              # person names and the signatory replaced
        assert "Person A" in _rev_doc(a) and ">Signatory<" in _rev_doc(a)
    assert re.findall(r"<in-bse-co:IdentificationNumberOfDirectorOrCompany [^>]*>([^<]*)<",
                      _rev_doc("3962")) == ["00000000"]     # the director's DIN


def test_a_revision_event_is_neutral_low_and_says_it_revises_an_earlier_filing():
    """NAUKRI 3962, disseminated 8 Oct 17:27:52: a director's market sale of
    5,00,000 shares for ₹68.0 crore traded 18-20 Aug. As an original it would
    be negative and high; as a revision it is not new trading."""
    row, filing = _revisions()["3962"], dz.parse_pit_xml(_rev_doc("3962"))
    event = dz.insider_event(row, filing, "NAUKRI", NOW.isoformat(), None)
    assert (event.id, event.published_at, event.occurred_from, event.occurred_to) == (
        "nsepit:3962", "2026-10-08T17:27:52+05:30", "2026-08-18", "2026-08-20")
    assert (event.category, event.direction, event.materiality) == ("insider", "neutral", "low")
    assert event.facts["revision"] is True and event.facts["market_net_inr"] == -680478416.0
    assert event.what == ("Directors and key managers sold 5,00,000 shares worth ₹68.0 crore in "
                          "the market on 18 Aug 2026 to 20 Aug 2026. Filed with NSE on 8 Oct "
                          "2026. " + REVISION_NOTE)
    as_original = dz.insider_event(dict(row, typeOfSubmission="Original"),
                                   dataclasses.replace(filing, revised=False), "NAUKRI",
                                   NOW.isoformat(), None)
    assert (as_original.direction, as_original.materiality) == ("negative", "high")
    assert as_original.what.endswith("The filing gives no reason for the sale.")


@pytest.mark.parametrize("submission, revised, is_revision", [
    ("Original", False, False), ("Revision", False, True), ("Original", True, True),
    ("revision", False, True)])
def test_the_list_or_the_xbrl_marks_a_revision(submission, revised, is_revision):
    filing = dataclasses.replace(_karur(), revised=revised)
    event = dz.insider_event(dict(_karur_row(), typeOfSubmission=submission), filing,
                             "KARURVYSYA", NOW.isoformat(), (78.2, "2026-09-30"))
    assert event.facts["revision"] is is_revision
    assert (REVISION_NOTE in event.what) is is_revision
    # a revision's note replaces the 75% note: the trades are not news either way
    assert ("public-shareholding rule" in event.what) is not is_revision
    assert (event.direction, event.materiality) == ("neutral", "low")


def test_a_feed_run_stores_a_revision_as_a_revision_not_as_new_trading(disclosure_feed):
    """PATINTLOG at the 18:30 run on 1 Oct: 3886 (17:11:45) and its revision
    3893 (18:23:57, no prevAppId; NSE's remark: the date of filing was wrong)
    hold the same two promoter trades. The original is the news; the revision
    is stored once, neutral and low, and says what it is."""
    env = disclosure_feed
    rows = _revisions()
    env["tracked"] = [("PATINTLOG", "held")]
    env["nse"].api[("corporates-pit-gg", "PATINTLOG")] = [rows["3886"], rows["3893"]]
    env["nse"].docs.update({rows[a]["xmlFileName"]: _rev_doc(a) for a in ("3886", "3893")})
    rec = feed.run_event_feed("pm", now=NOW_PAT, store=env["store"])
    assert rec["status"] == "ok", rec
    assert rec["disclosures_stored"]["insider"] == 2 and rec["llm_calls"] == 0
    events = {e.id: e for e in env["store"].load("PATINTLOG")}
    original, revision = events["nsepit:3886"], events["nsepit:3893"]
    # +Rs 36,62,165 - 35,90,951 = +Rs 71,214: positive, low
    assert (original.direction, original.materiality, original.what) == (
        "positive", "low", PAT_TRADES)
    assert (revision.direction, revision.materiality, revision.what) == (
        "neutral", "low", PAT_TRADES + " " + REVISION_NOTE)
    assert revision.published_at == "2026-10-01T18:23:57+05:30"
    assert [e.direction for e in events.values()].count("positive") == 1   # one piece of news
    rec = feed.run_event_feed("am", now=NOW_PAT + timedelta(hours=14), store=env["store"])
    assert rec["disclosures_stored"]["insider"] == 0 and rec["documents_fetched"] == 0


def test_an_identical_revision_without_prev_app_id_counts_once(insider_env):
    """PATINTLOG 3886 and 3893: bought Rs 36,62,165, sold Rs 35,90,951, net
    +Rs 71,214 = 0.0071214 crore once (0.0142428 summed). The trades ran 23-29
    Sep; the last day, 29 Sep, is in the 28 days from 25 Sep to 23 Oct."""
    summary, cache, why = _refresh(insider_env, "3886", "3893")
    assert (summary["listed"], summary["revisions"], summary["complete"], why) == (2, 1, True, None)
    assert ins.net_by_symbol(cache, ["PATINTLOG"]).to_dict() == {"PATINTLOG": 0.0071214}
    trades = ins.counted_trades(cache["filings"], "2026-09-25", "2026-10-23")["PATINTLOG"]
    assert sorted((t["action"], t["value_inr"]) for t in trades) == [
        ("buy", 3662165.0), ("sell", 3590951.0)]


def test_a_revision_that_repeats_four_trades_and_adds_one_counts_five(insider_env):
    """HTEL's filings in the window: 3762 (29 Sep), a promoter's purchase of
    1,25,000 shares for Rs 85,85,000; original 3945 (5 Oct), four designated
    persons' purchases; revision 3922 (6 Oct, a lower appId) repeats those four
    and adds 150 shares bought on 25 Sep. Each counts once: six trades (ten if
    summed), and the promoter's purchase is not taken for the new 150-share
    trade. Net: the promoter's Rs 85,85,000 = 0.8585 crore. Made promoter-group
    trades, the four and the fifth add 16,50,250 + 5,16,480 + 10,25,400 +
    17,17,750 + 10,145 = Rs 49,20,025: 1.3505025 crore. In the window ending
    24 Oct (from 26 Sep) the 25 Sep trade is out: 1.349488."""
    summary, cache, why = _refresh(insider_env, "3762", "3945", "3922")
    assert (summary["listed"], summary["revisions"], why) == (3, 1, None)
    trades = ins.counted_trades(cache["filings"], "2026-09-25", "2026-10-23")["HTEL"]
    assert sorted(t["shares"] for t in trades) == [150.0, 8000.0, 15000.0, 25000.0, 25000.0,
                                                   125000.0]
    assert ins.net_by_symbol(cache, ["HTEL"]).to_dict() == {"HTEL": 0.8585}
    promoter = {a: _rev_doc(a).replace(">Designated Person<", ">Promoter Group<")
                for a in ("3945", "3922")}
    _, cache, why = _refresh(insider_env, "3762", "3945", "3922", docs=promoter)
    assert why is None and ins.net_by_symbol(cache, ["HTEL"]).to_dict() == {"HTEL": 1.3505025}
    _, cache, why = _refresh(insider_env, "3762", "3945", "3922", on=date(2026, 10, 24),
                             docs=promoter)
    assert why is None and ins.net_by_symbol(cache, ["HTEL"]).to_dict() == {"HTEL": 1.349488}


def test_a_revision_of_an_august_trade_is_not_in_a_window_ending_23_october(insider_env):
    """NAUKRI 3962, disseminated 8 Oct: a director sold 5,00,000 shares for
    Rs 68,04,78,416 on 18-20 Aug. The window to 23 Oct starts 25 Sep, so it
    counts 0, not -68.0478416. A window from 20 Aug would hold it; from 21 Aug
    not."""
    summary, cache, why = _refresh(insider_env, "3962")
    assert (summary["complete"], why) == (True, None)
    assert ins.net_by_symbol(cache, ["NAUKRI"]).to_dict() == {"NAUKRI": 0.0}
    assert [t["value_inr"] for t in ins.counted_trades(
        cache["filings"], "2026-08-20", "2026-10-23")["NAUKRI"]] == [680478416.0]
    assert ins.counted_trades(cache["filings"], "2026-08-21", "2026-10-23")["NAUKRI"] == []
    # a director's sale needs no promoter share
    assert not [c for c in insider_env["nse"].calls if c[1:2] == ("corporate-share-holdings-master",)]


def test_three_identical_trades_in_one_filing_count_three_times_and_a_revision_keeps_three(
        insider_env):
    """KARURVYSYA 4038: three promoter-group members each sold 2,000 shares
    for Rs 7,69,230 on 21 Oct, -Rs 23,07,690 = -0.230769. Two persons can make
    the same trade, so an original is never deduplicated. A revision restating
    the three replaces each once: still -0.230769, not -0.461538 or -0.076923."""
    original = _karur_row()
    revision = dict(original, appId="9100", typeOfSubmission="Revision",
                    broadcastDateTime="23-Oct-2026 07:00:00",
                    xmlFileName=KARUR_XML_URL.replace("IT_539", "IT_540"))
    karur = _doc("pit_karurvysya_20261022.xml")
    for rows, net in (([original], -0.230769), ([original, revision], -0.230769)):
        insider_env["nse"] = FakeNse({("corporates-pit-gg", None): rows},
                                     {r["xmlFileName"]: karur for r in rows})
        ins._path().unlink(missing_ok=True)
        ins.refresh_insider_trades(date(2026, 10, 23))
        cache, why = ins.usable_insider_trades(date(2026, 10, 23))
        assert why is None and ins.net_by_symbol(cache, ["KARURVYSYA"]).to_dict() == {
            "KARURVYSYA": net}


@pytest.mark.parametrize("change, net", [
    ((">3662165<", ">3662000<"), 0.0071049),             # value corrected: 36,62,000 - 35,90,951
    ((">2026-09-23<", ">2026-09-24<"), 0.0071214),       # first day corrected
    ((">Promoter<", ">Immediate relative<"), 0.0),       # category corrected: not the promoter
])
def test_a_revision_that_corrects_a_value_day_or_category_counts_the_corrected_trade_once(
        insider_env, change, net):
    """Live revisions correct the value (360ONE: 'total amount of securities
    sold corrected'), a day (NAUKRI 3963: 'the correct date of revocation') or
    the person's category (SARLAPOLY). PATINTLOG's revision, so corrected, counts
    once and as corrected."""
    doc = _rev_doc("3893")
    assert doc.count(change[0]) >= 1
    _, cache, why = _refresh(insider_env, "3886", "3893", docs={"3893": doc.replace(*change)})
    assert why is None and ins.net_by_symbol(cache, ["PATINTLOG"]).to_dict() == {"PATINTLOG": net}
    assert len(ins.counted_trades(cache["filings"], "2026-09-25", "2026-10-23")["PATINTLOG"]) == 2


def _t(shares, value, who="promoter", action="buy", day_="2026-10-20"):
    return {"who": who, "action": action, "market": True, "shares": shares, "value_inr": value,
            "from_day": day_, "to_day": day_}


def _f(at, revision, *trades):
    return {"symbol": "X", "published_at": f"2026-{at}:00+05:30", "revision": revision,
            "readable": True, "trades": list(trades)}


def test_a_revision_replaces_each_matching_trade_once_and_adds_the_rest():
    """An original with two persons' 100-share purchases; a revision with three
    (one was left out). Two replace, one is new: three trades, not two or five."""
    filings = {"a": _f("10-20T10:00", False, _t(100, 1e6), _t(100, 1e6)),
               "b": _f("10-21T10:00", True, _t(100, 1e6), _t(100, 1e6), _t(100, 1e6))}
    assert len(ins.counted_trades(filings, "2026-09-25", "2026-10-23")["X"]) == 3


def test_a_revision_replaces_the_closest_earlier_trade_then_the_latest():
    """SARLAPOLY's live figures: two originals of 10,000-share promoter sales on
    25 Sep, for Rs 10,00,000 (26 Sep) and Rs 10,00,003 (28 Sep 11:53); a
    revision (12:45) for Rs 10,00,000. It replaces the trade that agrees on
    more fields, the first: values 10,00,003 and 10,00,000 remain. When both
    agree equally, the later is replaced."""
    sale = dict(who="promoter", action="sell", day_="2026-09-25")
    filings = {"a": _f("09-26T17:49", False, _t(10000, 1000000.0, **sale)),
               "b": _f("09-28T11:53", False, _t(10000, 1000003.0, **sale)),
               "c": _f("09-28T12:45", True, _t(10000, 1000000.0, **sale))}
    kept = ins.counted_trades(filings, "2026-09-25", "2026-10-23")["X"]
    assert sorted(t["value_inr"] for t in kept) == [1000000.0, 1000003.0]
    filings["c"]["trades"] = [_t(10000, 999999.0, **sale)]
    kept = ins.counted_trades(filings, "2026-09-25", "2026-10-23")["X"]
    assert [t["value_inr"] for t in kept] == [1000000.0, 999999.0]
    # filings are taken by dissemination time, not by id or by the order given
    late_first = {"z": filings["c"], "y": filings["b"], "x": filings["a"]}
    assert ins.counted_trades(late_first, "2026-09-25", "2026-10-23") == ins.counted_trades(
        filings, "2026-09-25", "2026-10-23")


def test_above_the_cap_only_promoter_group_sales_are_left_out():
    trades = [_t(100, 3e6, "promoter", "sell"), _t(100, 1e6, "director", "sell"),
              _t(100, 2e6, "promoter", "buy")]
    assert ins.symbol_net(trades, [78.2, "2026-09-30"]) == -1e6 + 2e6
    assert ins.symbol_net(trades, [75.0, "2026-09-30"]) == -3e6 - 1e6 + 2e6
    assert ins.symbol_net(trades, [None, None]) == -2e6
    assert ins.symbol_net(trades, None) == -2e6


@pytest.mark.parametrize("promoter, net", [
    ("78.2", 0.0), ("75.01", 0.0), ("75.0", -0.230769), ("58.72", -0.230769), (None, -0.230769)])
def test_a_promoter_sale_above_the_75_percent_cap_counts_nothing_in_discovery(
        insider_env, promoter, net):
    """The event calls KARURVYSYA's sale neutral when promoters hold more than
    75% (the 25% public-shareholding rule), so the ranking does not count it
    against the company. At 75.0% or below, or with no figure from NSE (as the
    event), it counts: -Rs 23,07,690."""
    rows = [dict(r, symbol="KARURVYSYA") for r in _rec()["shareholding_list"]]
    if promoter is None:
        rows = []
    else:
        rows[0]["pr_and_prgrp"] = promoter                 # the 30 Sep 2026 quarter
    insider_env["nse"].api[("corporate-share-holdings-master", "KARURVYSYA")] = rows
    ins.refresh_insider_trades(date(2026, 10, 23))
    cache, why = ins.usable_insider_trades(date(2026, 10, 23))
    assert why is None
    assert cache["promoter_holding"]["KARURVYSYA"] == (
        [float(promoter), "2026-09-30"] if promoter else [None, None])
    assert ins.net_by_symbol(cache, ["KARURVYSYA", "BUYERCO"]).to_dict() == {
        "KARURVYSYA": net, "BUYERCO": 4.5}


def test_a_failed_promoter_share_read_leaves_the_signal_unavailable(insider_env):
    on = date(2026, 10, 23)
    insider_env["nse"].fail = {("corporate-share-holdings-master", "KARURVYSYA")}
    summary = ins.refresh_insider_trades(on)
    assert (summary["holdings_failed"], summary["unread"], summary["complete"]) == (
        ["KARURVYSYA"], 0, False)
    assert ins.usable_insider_trades(on) == (
        None, "insider_buying: promoter holding unread for KARURVYSYA")
    assert "net_inr" not in ins.load_insider_trades()
    insider_env["nse"].fail = set()
    again = ins.refresh_insider_trades(on)
    assert (again["read_now"], again["complete"]) == (0, True)


def test_no_promoter_share_is_read_while_filings_are_unread(insider_env, monkeypatch):
    monkeypatch.setattr(settings, "DISCOVERY_INSIDER_MAX_DOCUMENTS", 1)
    ins.refresh_insider_trades(date(2026, 10, 23))
    assert [c[1] for c in insider_env["nse"].calls if c[0] == "api"] == ["corporates-pit-gg"]


def test_a_market_trade_without_a_day_makes_its_filing_unreadable(insider_env):
    """With no trade day the window cannot place the trade: the filing is
    named unreadable (1 of 3, more than a tenth: unavailable), never counted
    as a trade of no day."""
    insider_env["nse"].docs[BUYER_URL] = _buyer_xml().replace(">2026-10-21<", "><")
    summary = ins.refresh_insider_trades(date(2026, 10, 23))
    assert (summary["unreadable"], summary["complete"]) == (["nsepit:9001"], False)
    assert ins.usable_insider_trades(date(2026, 10, 23)) == (
        None, "insider_buying: 1 of 3 filings unreadable")


def test_a_cache_read_after_the_screen_day_is_not_used(insider_env):
    ins.refresh_insider_trades(date(2026, 10, 23))
    assert ins.usable_insider_trades(date(2026, 10, 22)) == (
        None, "insider_buying: filings read up to 2026-10-23, after 2026-10-22")
    assert ins.usable_insider_trades(date(2026, 10, 23))[1] is None


def test_a_cache_line_without_trades_is_read_again_and_never_used_as_zeros(insider_env):
    """A cache written before trades were kept has a net per filing only. With
    no net per company every score would be 0, a neutral rank, so it is not
    used; the next refresh reads its filings again."""
    on = date(2026, 10, 23)
    old = {"complete": True, "window_to": "2026-10-23", "listed": 1, "unread": 0,
           "filings": {"nsepit:9001": {"symbol": "BUYERCO", "net_inr": 45000000.0,
                                       "readable": True}}}
    assert ins.usable_insider_trades(on, old) == (
        None, "insider_buying: cache has no net per company")
    ins._path().write_bytes(json.dumps(old).encode("utf-8"))
    assert ins.refresh_insider_trades(on)["read_now"] == 3


# ---------------------------------------------------------------------------
# Discovery: the promoter pledge guard
# ---------------------------------------------------------------------------

def _guard_window(symbols, start=date(2026, 7, 1)) -> pd.DataFrame:
    rows = []
    for s in symbols:
        for i in range(70):
            rows.append({"symbol": s, "series": "EQ", "date": (start + timedelta(days=i)).isoformat(),
                         "prev_close": 100.0, "open": 100.0, "high": 101.0, "low": 99.0,
                         "close": 100.0, "volume": 10000.0, "traded_value_cr": 6.0,
                         "delivery_qty": 4000.0, "delivery_pct": 40.0})
    return pd.DataFrame(rows)


@pytest.fixture()
def guard_env(monkeypatch):
    class _NoneUnderSurveillance(dict):          # NSE's report: every symbol active, clear
        def get(self, symbol, default=None):
            return {"status": "A", "measures": []}
    monkeypatch.setattr(guards, "surveillance_list",
                        lambda session: (_NoneUnderSurveillance(), session.isoformat()))
    monkeypatch.setattr(guards, "float_mcap_cr", lambda s: 2000.0)
    monkeypatch.setattr(settings, "DISCOVERY_PLEDGE_GUARD", True)
    monkeypatch.setattr(settings, "DISCOVERY_MAX_PLEDGE_PCT", 25.0)
    snap = _rec()["pledge_snapshot"]
    env = {"rows": {"MARUTI": snap["MARUTI"], "A2ZINFRA": snap["A2ZINFRA"], "NOROW": [],
                    "FAILED": None,
                    "EDGE": [dict(snap["MARUTI"][0], percPromoterShares="   25.00")],
                    "OVER": [dict(snap["MARUTI"][0], percPromoterShares="   25.01")],
                    # two companies' rows: which is this one cannot be told
                    "TWOROWS": snap["MARUTI"] + snap["A2ZINFRA"]},
           "asked": []}

    def snapshots(symbols):
        env["asked"].append(list(symbols))
        return {s: env["rows"].get(s) for s in symbols}
    monkeypatch.setattr(guards, "pledge_snapshots", snapshots)
    return env


def test_the_pledge_guard_rejects_heavy_pledges_and_degrades_the_unknown(guard_env):
    """Recorded: Maruti 0.00% of the promoter holding pledged, A2Z Infra 99.68%."""
    symbols = ["MARUTI", "A2ZINFRA", "NOROW", "FAILED", "EDGE", "OVER", "TWOROWS"]
    passed, rejected, degraded = guards.apply_guards(symbols, _guard_window(symbols))
    assert passed == ["MARUTI", "NOROW", "FAILED", "EDGE", "TWOROWS"]
    assert rejected == {"A2ZINFRA": ["promoter_pledge_high"], "OVER": ["promoter_pledge_high"]}
    assert degraded == ["promoter_pledge:NOROW", "promoter_pledge:FAILED",
                        "promoter_pledge:TWOROWS"]
    assert guard_env["asked"] == [symbols]


def test_the_pledge_guard_off_or_without_nse_is_one_degraded_check(guard_env, monkeypatch):
    symbols = ["MARUTI", "A2ZINFRA"]
    monkeypatch.setattr(settings, "DISCOVERY_PLEDGE_GUARD", False)
    passed, rejected, degraded = guards.apply_guards(symbols, _guard_window(symbols))
    assert (passed, rejected, degraded) == (symbols, {}, ["promoter_pledge"])
    assert guard_env["asked"] == []
    monkeypatch.setattr(settings, "DISCOVERY_PLEDGE_GUARD", True)
    monkeypatch.setattr(guards, "pledge_snapshots", lambda symbols: {})
    passed, rejected, degraded = guards.apply_guards(symbols, _guard_window(symbols))
    assert (passed, rejected, degraded) == (symbols, {}, ["promoter_pledge"])


def test_a_pledge_row_more_than_200_days_old_is_unknown_not_used(guard_env):
    """The window's last session is 23 Oct 2026, so the limit is 6 Apr 2026.
    A row for 31 Mar 2026 (206 days) is degraded even at 99%; 30 Jun (115
    days) at 30% rejects; 6 Apr (200 days) is used; 5 Apr and a row with no
    quarter are not. On 23 Oct 10 of NSE's 1,558 rows were from before 2015
    (6 from Dec 2014), and 79 were more than 200 days old."""
    snap = _rec()["pledge_snapshot"]["MARUTI"][0]
    quarters = {"MARCH": "31-Mar-2026", "JUNE": "30-Jun-2026", "DAY200": "06-Apr-2026",
                "DAY201": "05-Apr-2026", "NOQUARTER": "-", "OLD2014": "31-Dec-2014"}
    for sym, shp in quarters.items():
        guard_env["rows"][sym] = [dict(snap, shp=shp, percPromoterShares="   99.00")]
    symbols = list(quarters)
    passed, rejected, degraded = guards.apply_guards(
        symbols, _guard_window(symbols, start=date(2026, 8, 15)))
    assert rejected == {"JUNE": ["promoter_pledge_high"], "DAY200": ["promoter_pledge_high"]}
    assert passed == ["MARCH", "DAY201", "NOQUARTER", "OLD2014"]
    assert degraded == ["promoter_pledge:MARCH", "promoter_pledge:DAY201",
                        "promoter_pledge:NOQUARTER", "promoter_pledge:OLD2014"]


def test_the_recorded_pledge_rows_read_as_share_of_promoter_holding():
    snap = _rec()["pledge_snapshot"]
    assert dz.pledged_share_of_promoter(snap["MARUTI"]) == (0.0, "2026-09-30")
    assert dz.pledged_share_of_promoter(snap["A2ZINFRA"]) == (99.68, "2026-09-30")
    assert dz.pledged_share_of_promoter([{"percPromoterShares": "-"}]) is None
    assert dz.pledged_share_of_promoter([]) is None

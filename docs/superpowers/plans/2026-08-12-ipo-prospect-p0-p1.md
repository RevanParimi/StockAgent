# PI "Prospect" — P0 + P1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the IPO sections of the daily brief and weekly digest tell the truth — real subscription numbers, real issue-window state — and build the historical spine that will later let an IPO behaviour model prove itself.

**Architecture:** P0 repairs `services/data/fetchers/ipo.py` (a key-name miss and two absent fields), adds a category-wise bid-ladder fetcher against the NSE endpoint verified on 2026-08-11, moves the refresh from the weekly discovery job to its own daily job, and makes both delivery surfaces issue-state aware. P1 adds `core/ipo/` with a history store and an offline backfill that joins every mainboard IPO since 2024-05 to its realised post-listing curve from the 550 bhavcopy sessions already on disk. No scoring model is built here — P0 ships facts, P1 ships a measurement.

**Tech Stack:** Python 3.13, pandas + parquet (`EodStore`), pydantic v2 schemas, APScheduler (`CronTrigger`, IST), pytest, the `nse` package via `services/data/fetchers/nse_client.py`, yfinance for `^NSEI`.

**Spec:** `docs/superpowers/specs/2026-08-11-ipo-intelligence-design.md` — §11 is the verified NSE data contract and is the authority for every field name below.

## Global Constraints

- **Config over hardcode.** Every tunable goes through `cfg("...")` in `src/backend/shared/config/settings/base.py` with the value in `config.yaml`. No magic numbers in logic.
- **No `env=` for non-secret toggles.** `cfg()` calls in this plan take **no** `env=` parameter. `config.yaml` is the sole source; flipping a toggle is a yaml edit plus redeploy.
- **Never raise into delivery.** Every fetcher and every brief/weekly helper catches broadly and returns an empty/degraded value, matching the existing `logger.warning("[x] ... (non-fatal): %s", exc)` pattern. A dead IPO feed must never break a morning brief.
- **Dark-signal pattern.** A missing sub-signal is omitted and the remainder renormalized — never defaulted to zero.
- **Research framing.** All user-visible IPO copy stays "the tool's research view — not advice". No output may read as a recommendation to apply.
- **SME stays excluded** via the existing `settings.DISCOVERY_INCLUDE_SME` gate in `_normalise`.
- **Append-only history.** The P1 store is rebuildable from source; it must never be the only copy of anything.
- **Commit per task**, message style `feat(ipo): ...` / `fix(ipo): ...` / `test(ipo): ...`, ending with:
  `Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>`
- **Test discipline.** Run the **targeted** tests named in each step before that step's commit. Run the **full** suite (`python -m pytest tests/unit -q`) where a task explicitly says so — those are the integration boundaries. The full suite takes ~4m15s, which is why it is not run before every commit.
- **Baseline measured 2026-08-12 on `ipo-intelligence` @ `e18242d`: 2394 passed, 5 skipped, 0 failed.** Any failure you see is yours; do not "fix" a pre-existing one.

---

## File Structure

**Created**
| Path | Responsibility |
|---|---|
| `core/ipo/__init__.py` | Package marker + public re-exports |
| `core/ipo/calendar.py` | Issue-window state machine (`issue_state`), pure functions over a normalised record |
| `core/ipo/history.py` | `IpoHistoryStore` — JSONL store of one row per historical IPO |
| `services/data/fetchers/ipo_bids.py` | Category-wise bid ladder from `/api/ipo-detail` |
| `scripts/ipo_backfill.py` | Offline P1 backfill CLI |
| `tests/unit/test_ipo_calendar.py` | Issue-state truth table |
| `tests/unit/test_ipo_bids.py` | Bid-ladder parsing, both shapes |
| `tests/unit/test_ipo_history.py` | History store round-trip + idempotency |
| `tests/unit/test_ipo_backfill.py` | Outcome-curve maths against a synthetic tape |

**Modified**
| Path | Change |
|---|---|
| `services/data/fetchers/ipo.py` | `noOfTime` key, issue window dates, bid-ladder join |
| `src/backend/shared/config/settings/base.py` | New `IPO_*` settings; drop `env=` from `DISCOVERY_IPO_ENABLED` |
| `config.yaml` | New `ipo:` block |
| `core/delivery/brief.py` | Issue-state-aware IPO section (text + HTML) |
| `core/delivery/weekly.py` | New IPO section |
| `services/scheduler/python/scheduler.py` | New `ipo_refresh` daily job |
| `core/ops/watchdog/checks.py` | New `ipo_cache_fresh` invariant check |
| `config/milestones.yaml` | Three milestones + one invariant |
| `tests/unit/test_ipo_fetcher.py` | Extended for the new fields |
| `tests/unit/test_delivery_brief.py` | Extended for issue state |

---

# PHASE P0 — Make the brief tell the truth

## Task 1: `noOfTime` — the one-line win

The total subscription × has been in the response the code already fetches, under a key nobody guessed. `_TOTAL_SUB_KEYS` lists three candidate names; the real one is `noOfTime` (spec §11.1).

**Files:**
- Modify: `services/data/fetchers/ipo.py:35`
- Test: `tests/unit/test_ipo_fetcher.py`

**Interfaces:**
- Consumes: nothing
- Produces: `refresh_ipo_cache()` rows now carry a non-null `total_x` for live issues. No signature change.

- [ ] **Step 1: Write the failing test**

Append to `tests/unit/test_ipo_fetcher.py`:

```python
_LIVE_CURRENT_ROW = {
    # Shape verified live against NSE 2026-08-11 (spec section 11.1).
    "symbol": "MILKYMIST", "companyName": "Milky Mist Dairy Food Limited",
    "series": "EQ", "status": "Active", "category": "Total",
    "issueStartDate": "11-Aug-2026", "issueEndDate": "13-Aug-2026",
    "issuePrice": "Rs.133 to Rs.140",
    "noOfSharesOffered": "8.1798244E7", "noOfsharesBid": "4.3481697E7",
    "noOfTime": "0.5315724992825029",
}


def test_current_issue_noOfTime_populates_total_x(tmp_path, monkeypatch):
    """NSE ships the total subscription x as `noOfTime`, not any of the three
    names the fetcher originally guessed."""
    cache = str(tmp_path / "ipo.json")
    monkeypatch.setattr(ipo_mod, "_make_nse_client",
                        lambda: _FakeNSE(current=[_LIVE_CURRENT_ROW]))
    rec = refresh_ipo_cache(cache_path=cache)["current"][0]
    assert rec["total_x"] == 0.5315724992825029
    assert rec["issue_price"] == 140.0        # upper band of "Rs.133 to Rs.140"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/unit/test_ipo_fetcher.py::test_current_issue_noOfTime_populates_total_x -v`
Expected: FAIL — `assert None == 0.5315724992825029`

- [ ] **Step 3: Add the key**

In `services/data/fetchers/ipo.py`, replace line 35:

```python
_TOTAL_SUB_KEYS = ("noOfTimesSubscribed", "totalSubscriptionTimes", "subscriptionTimes")
```

with:

```python
# `noOfTime` is what /api/ipo-current-issue actually ships (verified live
# 2026-08-11, spec section 11.1) and MUST stay first: _first() takes the
# earliest key present. The other three are unobserved legacy guesses, kept
# only because NSE field names drift across report vintages.
_TOTAL_SUB_KEYS = ("noOfTime", "noOfTimesSubscribed", "totalSubscriptionTimes",
                   "subscriptionTimes")
```

- [ ] **Step 4: Run the tests**

Run: `python -m pytest tests/unit/test_ipo_fetcher.py -v`
Expected: PASS, including the three pre-existing tests (`test_missing_subscription_fields_are_none` still passes — its row has none of the four keys).

- [ ] **Step 5: Commit**

```bash
git add services/data/fetchers/ipo.py tests/unit/test_ipo_fetcher.py
git commit -m "fix(ipo): read total subscription x from noOfTime

NSE ships it under a key the fetcher never guessed, so total_x has been
null on every row ever cached and the brief's IPO lean has returned
'data pending' 100% of the time since Compass Phase C.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Task 2: Issue window dates + the state machine

`_LISTING_DATE_KEYS` looks for `listingDate`, which the current/upcoming feeds do not carry — they carry `issueStartDate`/`issueEndDate`. Nothing in the system can currently tell an open issue from a closed one. (Past rows *do* carry `listingDate`; that path must keep working.)

**Files:**
- Modify: `services/data/fetchers/ipo.py:31` and the `_normalise` dict at `:85-95`
- Modify: `src/backend/shared/config/settings/base.py:921`
- Create: `core/ipo/__init__.py`, `core/ipo/calendar.py`
- Test: `tests/unit/test_ipo_calendar.py`, `tests/unit/test_ipo_fetcher.py`

**Interfaces:**
- Consumes: normalised records from Task 1
- Produces:
  - records gain `"issue_start": str` and `"issue_end": str` (ISO date, `""` when absent)
  - `core.ipo.calendar.issue_state(rec: dict, on: datetime.date) -> str` returning exactly one of `"upcoming" | "open" | "closed" | "listed" | "unknown"`
  - `core.ipo.calendar.STATES: tuple[str, ...]`

- [ ] **Step 1: Write the failing calendar test**

Create `tests/unit/test_ipo_calendar.py`:

```python
"""PI Prospect P0 — issue-window state machine."""
from datetime import date

import pytest

from core.ipo.calendar import STATES, issue_state

_OPEN = {"issue_start": "2026-08-11", "issue_end": "2026-08-13", "listing_date": ""}


@pytest.mark.parametrize("on,expected", [
    (date(2026, 8, 10), "upcoming"),   # day before it opens
    (date(2026, 8, 11), "open"),       # first day, inclusive
    (date(2026, 8, 12), "open"),
    (date(2026, 8, 13), "open"),       # last day, inclusive
    (date(2026, 8, 14), "closed"),     # bidding done, not yet listed
])
def test_window_boundaries_are_inclusive(on, expected):
    assert issue_state(_OPEN, on) == expected


def test_listed_wins_over_a_closed_window():
    rec = {**_OPEN, "listing_date": "2026-08-18"}
    assert issue_state(rec, date(2026, 8, 17)) == "closed"
    assert issue_state(rec, date(2026, 8, 18)) == "listed"   # listing day itself
    assert issue_state(rec, date(2026, 9, 1)) == "listed"


def test_missing_or_unparseable_dates_are_unknown():
    assert issue_state({}, date(2026, 8, 12)) == "unknown"
    assert issue_state({"issue_start": "2026-08-11"}, date(2026, 8, 12)) == "unknown"
    assert issue_state({"issue_start": "garbage", "issue_end": "2026-08-13"},
                       date(2026, 8, 12)) == "unknown"


def test_every_returned_state_is_declared():
    assert issue_state(_OPEN, date(2026, 8, 12)) in STATES
```

- [ ] **Step 2: Run it to verify it fails**

Run: `python -m pytest tests/unit/test_ipo_calendar.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'core.ipo'`

- [ ] **Step 3: Create the package and the state machine**

Create `core/ipo/__init__.py`:

```python
"""PI Prospect — IPO intelligence.

An IPO is a two-process instrument: sentiment-driven at listing, evidence-driven
afterwards. This package owns both the data and (from P3) the model. It is
deliberately separate from core/discovery/, whose signals all assume a tape that
a pre-listing instrument does not have.
"""
from core.ipo.calendar import STATES, issue_state

__all__ = ["STATES", "issue_state"]
```

Create `core/ipo/calendar.py`:

```python
"""Issue-window state machine (spec section 5, P0).

Pure functions over a record normalised by services/data/fetchers/ipo.py. The
brief renders IPOs under headings that assert a state ("IPOs OPEN NOW"), so
that state has to be derived rather than assumed — before this existed, a
closed issue kept rendering as open because nothing parsed the window at all.
"""
from __future__ import annotations

from datetime import date

STATES: tuple[str, ...] = ("upcoming", "open", "closed", "listed", "unknown")


def _iso(value: object) -> date | None:
    try:
        return date.fromisoformat(str(value or ""))
    except ValueError:
        return None


def issue_state(rec: dict, on: date) -> str:
    """Where `rec` sits in its lifecycle on `on`.

    Window bounds are INCLUSIVE: bidding is open on both the start and the end
    date. `listed` outranks everything — once the tape exists the window is
    history, and a record can legitimately carry both.
    """
    listed_on = _iso(rec.get("listing_date"))
    if listed_on is not None and listed_on <= on:
        return "listed"

    start, end = _iso(rec.get("issue_start")), _iso(rec.get("issue_end"))
    if start is None or end is None:
        return "unknown"
    if on < start:
        return "upcoming"
    if on > end:
        return "closed"
    return "open"
```

- [ ] **Step 4: Run the calendar tests**

Run: `python -m pytest tests/unit/test_ipo_calendar.py -v`
Expected: PASS (9 cases)

- [ ] **Step 5: Write the failing fetcher test for the new fields**

Append to `tests/unit/test_ipo_fetcher.py`:

```python
def test_issue_window_dates_are_parsed(tmp_path, monkeypatch):
    """The current/upcoming feeds carry issueStartDate/issueEndDate, NOT
    listingDate — the key the fetcher originally looked for (spec 11.1)."""
    cache = str(tmp_path / "ipo.json")
    monkeypatch.setattr(ipo_mod, "_make_nse_client",
                        lambda: _FakeNSE(current=[_LIVE_CURRENT_ROW]))
    rec = refresh_ipo_cache(cache_path=cache)["current"][0]
    assert rec["issue_start"] == "2026-08-11"
    assert rec["issue_end"] == "2026-08-13"
    assert rec["listing_date"] == ""          # genuinely absent on this feed


def test_past_rows_keep_their_listing_date(tmp_path, monkeypatch):
    """Regression guard: listPastIPO DOES carry listingDate and that path
    must survive the addition of the window keys."""
    cache = str(tmp_path / "ipo.json")
    monkeypatch.setattr(ipo_mod, "_make_nse_client",
                        lambda: _FakeNSE(past=[_PAST_ROW]))
    rec = refresh_ipo_cache(cache_path=cache)["past"][0]
    assert rec["listing_date"] == "2026-06-15"
```

- [ ] **Step 6: Run it to verify it fails**

Run: `python -m pytest tests/unit/test_ipo_fetcher.py::test_issue_window_dates_are_parsed -v`
Expected: FAIL — `KeyError: 'issue_start'`

- [ ] **Step 7: Parse the window keys**

In `services/data/fetchers/ipo.py`, after line 31 (`_LISTING_DATE_KEYS = ...`) add:

```python
# The current/upcoming feeds carry the BIDDING window, not a listing date
# (verified live 2026-08-11, spec section 11.1). listPastIPO does carry
# listingDate, which is why _LISTING_DATE_KEYS stays.
_ISSUE_START_KEYS = ("issueStartDate", "issue_start_date", "biddingStartDate")
_ISSUE_END_KEYS = ("issueEndDate", "issue_end_date", "biddingEndDate")
```

In `_normalise`, add two entries to the appended dict, immediately after the `"listing_date"` line:

```python
            "issue_start": _parse_date(_first(item, _ISSUE_START_KEYS)),
            "issue_end": _parse_date(_first(item, _ISSUE_END_KEYS)),
```

- [ ] **Step 8: Drop the env override from the IPO toggle**

`DISCOVERY_IPO_ENABLED` is a non-secret toggle carrying `env=`, against the project rule. In `src/backend/shared/config/settings/base.py:921`, replace:

```python
DISCOVERY_IPO_ENABLED: bool = bool(cfg("discovery.ipo_enabled", env="DISCOVERY_IPO_ENABLED", fallback=False))
```

with:

```python
DISCOVERY_IPO_ENABLED: bool = bool(cfg("discovery.ipo_enabled", fallback=False))
```

- [ ] **Step 9: Run the full unit suite**

Run: `python -m pytest tests/unit -q`
Expected: PASS, no new failures. If anything referenced the env var, fix it now.

- [ ] **Step 10: Commit**

```bash
git add services/data/fetchers/ipo.py core/ipo/ tests/unit/test_ipo_calendar.py \
        tests/unit/test_ipo_fetcher.py src/backend/shared/config/settings/base.py
git commit -m "feat(ipo): parse the bidding window and derive issue state

The current/upcoming feeds carry issueStartDate/issueEndDate, never the
listingDate the fetcher looked for, so nothing could tell an open issue
from a closed one and the brief rendered both under 'IPOs OPEN NOW'.

Also drops env= from discovery.ipo_enabled per the no-env-for-toggles rule.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Task 3: Category-wise bid ladder

`/api/ipo-detail?symbol=X&series=EQ` returns the full ladder. It contains **two ladders that disagree** — `bidDetails` (NSE-only) and `activeCat` (all-exchange). Spec §7 risk 6: reading the convenient one silently under-reports every IPO. **Both are captured**; the combined figure is what the market quotes and is what downstream reads.

**Files:**
- Create: `services/data/fetchers/ipo_bids.py`
- Test: `tests/unit/test_ipo_bids.py`

**Interfaces:**
- Consumes: `services.data.fetchers.nse_client.nse_session`
- Produces:
  - `parse_bid_ladder(payload: dict) -> dict` — pure, no network
  - `fetch_bid_ladder(symbol: str) -> dict | None` — network, returns `None` on any failure
  - Both return the shape:
    ```python
    {"symbol": str, "updated_at": str,
     "combined": {"qib": float|None, "fii": ..., "dom_fi": ..., "mutual_fund": ...,
                  "nii": ..., "retail": ..., "employee": ..., "total": ...},
     "nse_only": {<same keys>},
     "cutoff_share": float | None}
    ```

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_ipo_bids.py`:

```python
"""PI Prospect P0 — bid-ladder parsing. Payload shapes verified live against
NSE 2026-08-11 for MOLBIO (spec section 11.2/11.4)."""
import services.data.fetchers.ipo_bids as bids_mod
from services.data.fetchers.ipo_bids import fetch_bid_ladder, parse_bid_ladder

_PAYLOAD = {
    "companyName": "MOLBIO",
    # NSE-only ladder: key `noOfTime`, and note `noOfsharesBid` (lowercase s).
    "bidDetails": [
        {"srNo": "1", "category": "Qualified Institutional Buyers(QIBs)",
         "noOfSharesOffered": "2325145", "noOfsharesBid": "1312326",
         "noOfTime": "0.5644060908029391"},
        {"srNo": "1(a)", "category": "Foreign Institutional Investors(FIIs)",
         "noOfSharesOffered": "", "noOfsharesBid": "871110", "noOfTime": ""},
        {"srNo": "1(c)", "category": "Mutual funds",
         "noOfSharesOffered": "", "noOfsharesBid": "0", "noOfTime": ""},
        {"srNo": "2", "category": "Non Institutional Investors",
         "noOfSharesOffered": "1743860", "noOfsharesBid": "6284124",
         "noOfTime": "3.6035713876113906"},
        # Sub-band of NII — must NOT be mistaken for the NII row itself.
        {"srNo": "2.1", "category": "Non Institutional Investors(Bid amount of "
                                    "more than Ten Lakhs)",
         "noOfSharesOffered": "1162574", "noOfsharesBid": "3564342",
         "noOfTime": "3.0659054821456526"},
        {"srNo": "3", "category": "Retail Individual Investors(RIIs)",
         "noOfSharesOffered": "4069005", "noOfsharesBid": "9056556",
         "noOfTime": "2.2257421654679708"},
        {"srNo": "4", "category": "Employees",
         "noOfSharesOffered": "20519", "noOfsharesBid": "78030",
         "noOfTime": "3.8028169014084505"},
        {"srNo": None, "category": "Total", "noOfSharesOffered": "8158529.0",
         "noOfsharesBid": "1.6731036E7", "noOfTime": "2.05074174523373"},
    ],
    # All-exchange ladder: key `noOfTotalMeant`, `noOfShareOffered` (no s on
    # Share), and a HEADER ROW whose values are column labels.
    "activeCat": {
        "updateTime": "11-Aug-2026 17:00:56",
        "dataList": [
            {"srNo": "Sr.No.", "category": "Category",
             "noOfShareOffered": "No.of shares offered/reserved",
             "noOfSharesBid": "No. of shares bid for",
             "noOfTotalMeant": "No. of times of total meant for the category"},
            {"srNo": "1", "category": "Qualified Institutional Buyers(QIBs)",
             "noOfShareOffered": "2325145", "noOfSharesBid": "3234672",
             "noOfTotalMeant": "1.3911700130529494"},
            {"srNo": "1(c)", "category": "Mutual funds",
             "noOfShareOffered": "", "noOfSharesBid": "218268",
             "noOfTotalMeant": ""},
        ],
    },
    "demandGraph": {"totalBidAtCutOff": "7752114", "TOTAL_BIDS": "16731036"},
}


def test_parses_both_ladders_without_conflating_them():
    out = parse_bid_ladder(_PAYLOAD)
    # NSE-only vs all-exchange genuinely disagree — spec section 11.4.
    assert out["nse_only"]["qib"] == 0.5644060908029391
    assert out["combined"]["qib"] == 1.3911700130529494
    assert out["nse_only"]["total"] == 2.05074174523373
    assert out["nse_only"]["retail"] == 2.2257421654679708
    assert out["nse_only"]["employee"] == 3.8028169014084505
    assert out["updated_at"] == "11-Aug-2026 17:00:56"


def test_nii_sub_band_does_not_overwrite_the_nii_total():
    """srNo 2.1 is a sub-band of srNo 2 and shares its category prefix."""
    assert parse_bid_ladder(_PAYLOAD)["nse_only"]["nii"] == 3.6035713876113906


def test_header_row_is_skipped():
    """activeCat's first row carries column LABELS as values; parsing it as
    data would emit a garbage category."""
    combined = parse_bid_ladder(_PAYLOAD)["combined"]
    assert all(v is None or isinstance(v, float) for v in combined.values())


def test_blank_x_becomes_none_not_zero():
    """FII/MF lines report bid quantity but no multiple. Zero would be a lie
    (dark-signal pattern: absent means absent)."""
    assert parse_bid_ladder(_PAYLOAD)["nse_only"]["fii"] is None
    assert parse_bid_ladder(_PAYLOAD)["nse_only"]["mutual_fund"] is None


def test_cutoff_share_is_a_fraction_of_total_bids():
    assert round(parse_bid_ladder(_PAYLOAD)["cutoff_share"], 4) == 0.4633


def test_empty_payload_yields_all_none_and_never_raises():
    out = parse_bid_ladder({})
    assert out["cutoff_share"] is None
    assert set(out["combined"].values()) == {None}


def test_fetch_returns_none_when_nse_fails(monkeypatch):
    class _Boom:
        def __enter__(self): raise RuntimeError("NSE 403")
        def __exit__(self, *a): return False
    monkeypatch.setattr(bids_mod, "nse_session", lambda: _Boom())
    assert fetch_bid_ladder("MOLBIO") is None
```

- [ ] **Step 2: Run it to verify it fails**

Run: `python -m pytest tests/unit/test_ipo_bids.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'services.data.fetchers.ipo_bids'`

- [ ] **Step 3: Write the fetcher**

Create `services/data/fetchers/ipo_bids.py`:

```python
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
```

- [ ] **Step 4: Run the tests**

Run: `python -m pytest tests/unit/test_ipo_bids.py -v`
Expected: PASS (7 tests)

- [ ] **Step 5: Commit**

```bash
git add services/data/fetchers/ipo_bids.py tests/unit/test_ipo_bids.py
git commit -m "feat(ipo): category-wise bid ladder from /api/ipo-detail

Captures BOTH ladders the endpoint returns. bidDetails is NSE-only and
activeCat is all-exchange; they disagree (MOLBIO QIB 0.564x vs 1.391x)
and the convenient one is the wrong one, so neither is silently
preferred. Keys off srNo because NII sub-bands share the NII category
prefix and would otherwise overwrite the category total.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Task 4: Join the ladder into the cache + daily refresh job

The cache refreshes only inside the Saturday discovery cycle, so a Mon-Wed issue is stale for a week or missed outright. This gives it its own daily job and enriches open issues with the ladder.

**Files:**
- Modify: `services/data/fetchers/ipo.py` (`refresh_ipo_cache`)
- Modify: `config.yaml`, `src/backend/shared/config/settings/base.py`
- Modify: `services/scheduler/python/scheduler.py`
- Test: `tests/unit/test_ipo_fetcher.py`

**Interfaces:**
- Consumes: `fetch_bid_ladder` (Task 3), `issue_state` (Task 2)
- Produces:
  - `current`/`upcoming` records gain `qib_x`, `retail_x` (from the combined ladder), `bid_ladder` (full dict), `cutoff_share`
  - `refresh_ipo_cache(cache_path=None, on: date | None = None)` — new optional `on` for testability
  - scheduler job id `ipo_refresh`

- [ ] **Step 1: Add config**

In `config.yaml`, add a top-level block after the `discovery:` block:

```yaml
# ── PI Prospect — IPO intelligence (spec 2026-08-11) ────────────────────────
ipo:
  enabled: true
  refresh_hour: 8               # daily calendar+ladder refresh (IST)
  refresh_hour_live: 18         # second pass, after the 17:00 NSE bid update
  bid_ladder_enabled: true      # kill-switch for the per-symbol ladder fetch
  max_ladder_fetches: 10        # cap per refresh — one NSE call per open issue
  cache_max_age_hours: 48       # watchdog invariant threshold
```

In `src/backend/shared/config/settings/base.py`, after the `DISCOVERY_IPO_*` block (around line 925), add:

```python
# ---------------------------------------------------------------------------
# PI Prospect — IPO intelligence (design 2026-08-11)
# ---------------------------------------------------------------------------
IPO_ENABLED: bool = bool(cfg("ipo.enabled", fallback=True))
IPO_REFRESH_HOUR: int = int(cfg("ipo.refresh_hour", fallback=8))
IPO_REFRESH_HOUR_LIVE: int = int(cfg("ipo.refresh_hour_live", fallback=18))
IPO_BID_LADDER_ENABLED: bool = bool(cfg("ipo.bid_ladder_enabled", fallback=True))
IPO_MAX_LADDER_FETCHES: int = int(cfg("ipo.max_ladder_fetches", fallback=10))
IPO_CACHE_MAX_AGE_HOURS: int = int(cfg("ipo.cache_max_age_hours", fallback=48))
```

- [ ] **Step 2: Write the failing test**

Append to `tests/unit/test_ipo_fetcher.py`:

```python
from datetime import date


def test_open_issues_are_enriched_with_the_bid_ladder(tmp_path, monkeypatch):
    """Only OPEN issues are worth a per-symbol NSE call; upcoming ones have no
    bids yet and closed ones will not change."""
    cache = str(tmp_path / "ipo.json")
    monkeypatch.setattr(ipo_mod, "_make_nse_client",
                        lambda: _FakeNSE(current=[_LIVE_CURRENT_ROW]))
    calls = []

    def _fake_ladder(symbol):
        calls.append(symbol)
        return {"symbol": symbol, "updated_at": "11-Aug-2026 17:00:56",
                "combined": {"qib": 1.39, "retail": 2.22, "total": 2.05,
                             "fii": None, "dom_fi": None, "mutual_fund": None,
                             "nii": None, "employee": None},
                "nse_only": {k: None for k in
                             ("qib", "fii", "dom_fi", "mutual_fund", "nii",
                              "retail", "employee", "total")},
                "cutoff_share": 0.46}

    monkeypatch.setattr(ipo_mod, "fetch_bid_ladder", _fake_ladder)
    rec = refresh_ipo_cache(cache_path=cache, on=date(2026, 8, 12))["current"][0]

    assert calls == ["MILKYMIST"]
    assert rec["qib_x"] == 1.39 and rec["retail_x"] == 2.22
    assert rec["cutoff_share"] == 0.46
    assert rec["bid_ladder"]["combined"]["qib"] == 1.39


def test_ladder_is_skipped_for_issues_not_open(tmp_path, monkeypatch):
    cache = str(tmp_path / "ipo.json")
    monkeypatch.setattr(ipo_mod, "_make_nse_client",
                        lambda: _FakeNSE(current=[_LIVE_CURRENT_ROW]))
    calls = []
    monkeypatch.setattr(ipo_mod, "fetch_bid_ladder",
                        lambda s: calls.append(s) or None)
    # 2026-08-20 is after the 13-Aug close.
    refresh_ipo_cache(cache_path=cache, on=date(2026, 8, 20))
    assert calls == []


def test_ladder_failure_leaves_the_row_intact(tmp_path, monkeypatch):
    """A dead ladder endpoint must not lose the total_x the feed already gave."""
    cache = str(tmp_path / "ipo.json")
    monkeypatch.setattr(ipo_mod, "_make_nse_client",
                        lambda: _FakeNSE(current=[_LIVE_CURRENT_ROW]))
    monkeypatch.setattr(ipo_mod, "fetch_bid_ladder", lambda s: None)
    rec = refresh_ipo_cache(cache_path=cache, on=date(2026, 8, 12))["current"][0]
    assert rec["total_x"] == 0.5315724992825029
    assert rec["qib_x"] is None
```

- [ ] **Step 3: Run it to verify it fails**

Run: `python -m pytest tests/unit/test_ipo_fetcher.py -k ladder -v`
Expected: FAIL — `TypeError: refresh_ipo_cache() got an unexpected keyword argument 'on'`

- [ ] **Step 4: Implement the enrichment**

In `services/data/fetchers/ipo.py`, add to the imports at the top of the module body:

```python
from datetime import date as _date
```

Then replace the `refresh_ipo_cache` signature and add enrichment before the `result = {...}` assembly:

```python
def refresh_ipo_cache(cache_path: str | None = None,
                      on: _date | None = None) -> dict:
    """Fetch current + upcoming + past-120d IPO lists, then enrich OPEN issues
    with their category-wise bid ladder. Never raises."""
    path = pathlib.Path(cache_path or _DEFAULT_CACHE)
    previous = load_ipo_cache(cache_path=str(path))
    on = on or _date.today()
```

(the body through the `except` block is unchanged), and immediately before `result = {`:

```python
    if not degraded:
        _enrich_open_issues(current + upcoming, on)
```

Add the helper above `refresh_ipo_cache`:

```python
def _enrich_open_issues(rows: list[dict], on: _date) -> None:
    """Attach the bid ladder to issues whose window is OPEN, in place.

    Only open issues: an upcoming one has no bids yet and a closed one will
    never change, so either would spend an NSE call to learn nothing. Bounded
    by IPO_MAX_LADDER_FETCHES because this runs inside a scheduler job.
    """
    from core.config import settings
    from core.ipo.calendar import issue_state

    if not getattr(settings, "IPO_BID_LADDER_ENABLED", True):
        return
    budget = int(getattr(settings, "IPO_MAX_LADDER_FETCHES", 10))
    for rec in rows:
        if budget <= 0:
            break
        if issue_state(rec, on) != "open":
            continue
        budget -= 1
        ladder = fetch_bid_ladder(rec["symbol"])
        if ladder is None:
            continue                    # keep whatever the feed already gave
        combined = ladder.get("combined") or {}
        rec["bid_ladder"] = ladder
        rec["cutoff_share"] = ladder.get("cutoff_share")
        for field, key in (("qib_x", "qib"), ("retail_x", "retail")):
            if combined.get(key) is not None:
                rec[field] = combined[key]
        if combined.get("total") is not None:
            rec["total_x"] = combined["total"]
```

Add the import near the top (module level, beside the other fetcher imports):

```python
from services.data.fetchers.ipo_bids import fetch_bid_ladder
```

- [ ] **Step 5: Run the tests**

Run: `python -m pytest tests/unit/test_ipo_fetcher.py -v`
Expected: PASS (all, old and new)

- [ ] **Step 6: Register the daily scheduler job**

In `services/scheduler/python/scheduler.py`, immediately before the `# ── Operational watchdog` block (around line 489), add:

```python
        # ── IPO calendar + bid ladder (PI Prospect P0) ──────────────────────
        # Twice daily: 08:00 catches issues that opened this morning, 18:00
        # runs after NSE's ~17:00 bid update so the evening brief and the
        # weekly digest read same-day demand. The weekly discovery cycle also
        # calls refresh_ipo_cache(); that stays, and is idempotent.
        if cfg("ipo.enabled", fallback=True):
            for slot, hour in (
                ("am", int(cfg("ipo.refresh_hour", fallback=8))),
                ("pm", int(cfg("ipo.refresh_hour_live", fallback=18))),
            ):
                scheduler.add_job(
                    func=self._ipo_refresh_job,
                    trigger=CronTrigger(hour=hour, minute=0,
                                        timezone="Asia/Kolkata"),
                    id=f"ipo_refresh_{slot}",
                    name=f"IPO calendar + bid ladder refresh ({slot})",
                    misfire_grace_time=3600,
                    coalesce=True,
                    replace_existing=True,
                )
            logger.info("[Scheduler] IPO refresh: daily at %s:00 and %s:00 IST",
                        cfg("ipo.refresh_hour", fallback=8),
                        cfg("ipo.refresh_hour_live", fallback=18))
        else:
            logger.info("[Scheduler] IPO refresh disabled (ipo.enabled=false)")
```

And add the job method beside `_discovery_weekly_job` (after line 570):

```python
    def _ipo_refresh_job(self) -> None:
        """IPO calendar + bid-ladder refresh (PI Prospect P0). Never raises:
        refresh_ipo_cache() contains its own failures and keeps a stale cache
        rather than emptying one."""
        from services.data.fetchers.ipo import refresh_ipo_cache

        _job_banner("IPO Refresh")
        try:
            result = refresh_ipo_cache()
            logger.info(
                "[Scheduler] IPO refresh — current=%d upcoming=%d past=%d degraded=%s",
                len(result.get("current", [])), len(result.get("upcoming", [])),
                len(result.get("past", [])), result.get("degraded"),
            )
        except Exception as exc:
            logger.error("[Scheduler] IPO refresh FAILED: %s", exc, exc_info=True)
        _job_banner("IPO Refresh", done=True)
```

- [ ] **Step 7: Run the scheduler tests**

Run: `python -m pytest tests/unit -q -k "scheduler or ipo"`
Expected: PASS. If a test asserts an exact job count, update it to include the two new ids.

- [ ] **Step 8: Commit**

```bash
git add services/data/fetchers/ipo.py services/scheduler/python/scheduler.py \
        config.yaml src/backend/shared/config/settings/base.py \
        tests/unit/test_ipo_fetcher.py
git commit -m "feat(ipo): enrich open issues with the bid ladder, refresh twice daily

The cache refreshed only in the Saturday discovery cycle, so a Mon-Wed
issue was stale for a week or missed outright. Ladder fetches are
restricted to issues whose window is actually open and bounded by
ipo.max_ladder_fetches; a ladder failure keeps the feed's own total_x.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Task 5: State-aware IPO section in the daily brief

`_ipo_watch` concatenates `current + upcoming` and renders everything under `IPOs OPEN NOW`. `_ipo_lean` returns `"data pending"` for an issue that simply has not opened yet, which reads as breakage rather than as a fact.

**Files:**
- Modify: `core/delivery/brief.py:200-248` (helpers), `:432-446` (`_ipo_watch`), `:677-689` (text), `:879-895` (HTML)
- Test: `tests/unit/test_delivery_brief.py`

**Interfaces:**
- Consumes: `issue_state` (Task 2)
- Produces: `_ipo_watch()` rows gain `"state": str`, `"issue_start": str`, `"issue_end": str`, `"cutoff_share": float | None`; `_ipo_window(row, on) -> str` is a new helper (the window line is computed on demand, NOT stored on the row); `_ipo_lean(row)` gains a `"not open yet"` label

- [ ] **Step 1: Write the failing test**

Append to `tests/unit/test_delivery_brief.py`:

```python
from datetime import date as _date


def test_ipo_watch_tags_state_and_drops_listed(monkeypatch):
    monkeypatch.setattr(br, "load_ipo_cache", lambda: {
        "current": [{"symbol": "OPENCO", "company": "Open Co", "status": "current",
                     "issue_start": "2026-08-11", "issue_end": "2026-08-13",
                     "total_x": 4.2}],
        "upcoming": [{"symbol": "SOONCO", "company": "Soon Co", "status": "upcoming",
                      "issue_start": "2026-08-18", "issue_end": "2026-08-20"},
                     {"symbol": "DONECO", "company": "Done Co", "status": "upcoming",
                      "issue_start": "2026-07-01", "issue_end": "2026-07-03",
                      "listing_date": "2026-07-08"}]})
    rows = br._ipo_watch(on=_date(2026, 8, 12))
    by_sym = {r["symbol"]: r for r in rows}
    assert by_sym["OPENCO"]["state"] == "open"
    assert by_sym["SOONCO"]["state"] == "upcoming"
    assert "DONECO" not in by_sym          # already listed — not an IPO to watch


def test_ipo_lean_distinguishes_not_open_from_broken():
    """An issue that has not opened has no bids BY DEFINITION. Reporting that
    as 'data pending' reads as a fault in the tool."""
    label, reason = br._ipo_lean({"state": "upcoming"})
    assert label == "not open yet"
    assert "bidding" in reason.lower()
    # A genuinely absent feed for an OPEN issue still reports data pending.
    assert br._ipo_lean({"state": "open"})[0] == "data pending"


def test_ipo_window_line_is_human_readable():
    assert br._ipo_window({"state": "open", "issue_end": "2026-08-13"},
                          _date(2026, 8, 13)) == "closes today"
    assert br._ipo_window({"state": "open", "issue_end": "2026-08-13"},
                          _date(2026, 8, 12)) == "closes tomorrow"
    assert br._ipo_window({"state": "upcoming", "issue_start": "2026-08-18"},
                          _date(2026, 8, 12)) == "opens 18 Aug"
```

- [ ] **Step 2: Run it to verify it fails**

Run: `python -m pytest tests/unit/test_delivery_brief.py -k ipo -v`
Expected: FAIL — `TypeError: _ipo_watch() got an unexpected keyword argument 'on'`

- [ ] **Step 3: Add the window formatter and update the lean**

In `core/delivery/brief.py`, add after `_dedup_ipos` (line 213):

```python
def _ipo_window(row: dict, on: date) -> str:
    """Plain-English window line for one IPO row."""
    state = row.get("state", "unknown")
    if state == "open":
        try:
            days = (date.fromisoformat(row.get("issue_end", "")) - on).days
        except ValueError:
            return "open now"
        if days <= 0:
            return "closes today"
        if days == 1:
            return "closes tomorrow"
        return f"closes in {days} days"
    if state == "upcoming":
        try:
            opens = date.fromisoformat(row.get("issue_start", ""))
        except ValueError:
            return "opens soon"
        return f"opens {opens.day} {opens.strftime('%b')}"
    if state == "closed":
        return "bidding closed — awaiting listing"
    return ""
```

Replace `_ipo_lean` (lines 234-248) with:

```python
def _ipo_lean(row: dict) -> tuple[str, str]:
    """The tool's OWN demand-based research view of an IPO -> (label, reason).

    Demand-only: the IPO feed carries no valuation/earnings data, so this never
    claims a fundamental/P-E view. Never personal advice (spec §1)."""
    # An issue that has not opened has no bids by definition. Calling that
    # "data pending" reads as a fault in the tool rather than a fact about
    # the calendar, which is exactly how the pre-P0 brief read.
    if row.get("state") == "upcoming":
        return ("not open yet", "Bidding has not started.")
    total, qib, retail = row.get("total_x"), row.get("qib_x"), row.get("retail_x")
    if total is None and qib is None and retail is None:
        return ("data pending", "subscription not yet reported")
    t, q = (total or 0.0), (qib or 0.0)
    if t >= settings.DELIVERY_BRIEF_IPO_STRONG_DEMAND_X or q >= settings.DELIVERY_BRIEF_IPO_STRONG_QIB_X:
        return ("STRONG DEMAND",
                "Heavy demand — historically tends to list well, though never guaranteed.")
    if t < settings.DELIVERY_BRIEF_IPO_SOFT_DEMAND_X and q < settings.DELIVERY_BRIEF_IPO_SOFT_DEMAND_X:
        return ("SOFT DEMAND", "Light subscription so far — muted interest.")
    return ("MODERATE DEMAND", "Steady subscription interest.")
```

- [ ] **Step 4: Make `_ipo_watch` state-aware**

Replace `_ipo_watch` (lines 432-446) with:

```python
def _ipo_watch(max_items: int | None = None, on: date | None = None) -> list[dict]:
    try:
        from core.ipo.calendar import issue_state
        on = on or date.today()
        cache = load_ipo_cache()
        mi = max_items if max_items is not None else settings.DELIVERY_BRIEF_MAX_IPOS
        rows = cache.get("current", []) + cache.get("upcoming", [])
        out = []
        for r in rows:
            state = issue_state(r, on)
            if state == "listed":
                continue          # it has a tape now; the tracker owns it
            out.append({
                "symbol": r.get("symbol", ""), "company": r.get("company", ""),
                "status": r.get("status", ""), "state": state,
                "issue_start": r.get("issue_start", ""),
                "issue_end": r.get("issue_end", ""),
                "qib_x": r.get("qib_x"), "retail_x": r.get("retail_x"),
                "total_x": r.get("total_x"), "issue_price": r.get("issue_price"),
                "cutoff_share": r.get("cutoff_share"),
            })
        # Open issues first — they are the ones with a deadline attached.
        order = {"open": 0, "closed": 1, "upcoming": 2, "unknown": 3}
        out.sort(key=lambda r: order.get(r["state"], 9))
        return _dedup_ipos(out, mi)
    except Exception as exc:
        logger.warning("[brief] ipo watch failed (non-fatal): %s", exc)
        return []
```

- [ ] **Step 5: Update the text renderer**

Replace lines 677-689 (the `ipos = brief.get("ipo_watch"...)` block) with:

```python
    ipos = brief.get("ipo_watch", []) or []
    if ipos:
        L += ["IPO WATCH   (the tool's research view — not advice)",
              "  × = times the issue was subscribed; high QIB/overall = institutional interest."]
        for w in ipos:
            lean, reason = _ipo_lean(w)
            window = _ipo_window(w, on)
            head = f"  • {w['symbol']}  {w.get('company', '')}"
            if window:
                head += f"  ·  {window}"
            L.append(head)
            if lean in ("data pending", "not open yet"):
                L.append(f"      {reason}")
            else:
                L.append(f"      Lean: {lean} · {_ipo_demand(w)}")
                L.append(f"      {reason}")
        L.append("")
```

The heading changes from `IPOs OPEN NOW` to `IPO WATCH` because the section now legitimately carries upcoming and closed issues too.

`render_brief_text(brief: dict)` (line 596) takes no `on`, so derive it as the **first statement** of the function body:

```python
def render_brief_text(brief: dict) -> str:
    # The IPO section renders window state ("closes tomorrow"), which is
    # relative to the day the brief is FOR, not the day it is rendered.
    # Guarded like the `hdr` parse below it: this function documents "never
    # raises", and render_brief_html's except-fallback calls it — an
    # unguarded parse here would make the fallback itself raise.
    try:
        on = date.fromisoformat(brief["date"]) if brief.get("date") else date.today()
    except ValueError:
        on = date.today()
```

- [ ] **Step 6: Update the HTML renderer**

In the HTML IPO block (around line 879), replace the `demand` line and section title:

```python
    # IPOs
    ipos = brief.get("ipo_watch", []) or []
    if ipos:
        trs = []
        for w in ipos:
            lean, reason = _ipo_lean(w)
            window = _ipo_window(w, on)
            demand = _ipo_demand(w) if lean not in ("data pending", "not open yet") else reason
            price = f'₹{_inr(w.get("issue_price"))}' if w.get("issue_price") else ""
            lean_color = H["warn"] if lean in ("data pending", "not open yet", "SOFT DEMAND") else H["accent"]
            leancol = f'<span style="color:{lean_color};font-weight:600">{_esc(lean)}</span>'
            trs.append(
                # Keep border-top + vertical-align:top — every sibling section
                # in this email has them, and dropping them here would make the
                # IPO block the only one with no divider hairline.
                f'<tr><td style="padding:12px 0;border-top:1px solid {H["hair_soft"]};vertical-align:top">'
                f'<div class="sa-ink" style="font:600 14.5px {_FONT};color:{H["ink"]}">{_esc(w["symbol"])} '
                f'<span class="sa-muted" style="color:{H["muted"]};font-weight:600;font-size:12.5px">{_esc(w.get("company", ""))}</span></div>'
                f'<div class="sa-muted" style="font:400 13px/1.5 {_FONT};color:{H["muted"]};margin:4px 0 0">{_esc(window)}</div>'
                f'<div class="sa-muted" style="font:400 13px/1.5 {_FONT};color:{H["muted"]};margin:2px 0 0">Lean: {leancol} — {_esc(demand)}</div></td>'
                f'<td class="sa-ink" style="padding:12px 0;text-align:right;white-space:nowrap;width:96px;color:{H["ink"]};font:600 14px {_FONT}">{price}</td></tr>')
        rows.append(_section("IPO watch · research view, not advice", _html_rows("".join(trs)), H))
```

`_render_brief_html_inner(brief: dict, H: dict)` (line 759) also takes no `on`. Add the identical derivation as the first statement of its body:

```python
def _render_brief_html_inner(brief: dict, H: dict) -> str:
    try:
        on = date.fromisoformat(brief["date"]) if brief.get("date") else date.today()
    except ValueError:
        on = date.today()
```

`date` is already imported in `core/delivery/brief.py` — no new import is needed.

- [ ] **Step 7: Run the tests**

Run: `python -m pytest tests/unit/test_delivery_brief.py -v`
Expected: PASS. `test_ipo_dedups_by_symbol` may need `on=` — if it fails on the missing window fields, its rows now resolve to `state="unknown"`, which is still returned; confirm it passes unchanged.

- [ ] **Step 8: Run the full unit suite and commit**

Run: `python -m pytest tests/unit -q`

```bash
git add core/delivery/brief.py tests/unit/test_delivery_brief.py
git commit -m "feat(ipo): make the brief's IPO section issue-state aware

Closed issues no longer render under a heading that claims they are open,
and an issue that has not opened yet says so instead of reporting 'data
pending', which read as a fault in the tool.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Task 6: IPO section in the weekly digest

`core/delivery/weekly.py` has never mentioned IPOs.

**Files:**
- Modify: `core/delivery/weekly.py`
- Test: `tests/unit/test_delivery_weekly.py` — **exists; append.** It already has `from datetime import date` and `import core.delivery.weekly as wk` at the top, so the tests below need no new imports.

**Interfaces:**
- Consumes: `core.delivery.brief._ipo_watch`, `_ipo_window`, `_ipo_lean`
- Produces: `build_weekly_review()` output gains `"ipo_watch": list[dict]`

- [ ] **Step 1: Write the failing test**

Append to `tests/unit/test_delivery_weekly.py`:

```python
def test_weekly_text_renders_the_ipo_section():
    review = {
        "date": "2026-08-16", "headline": "", "allocation": [],
        "concentration_flags": [], "laggards": [], "switch_candidates": [],
        "switch_suggestions": [], "scoreboard": {"counts": {}, "checked": 0, "correct": 0},
        "ipo_watch": [{"symbol": "OPENCO", "company": "Open Co", "state": "open",
                       "issue_start": "2026-08-14", "issue_end": "2026-08-18",
                       "total_x": 4.2, "qib_x": None, "retail_x": None}],
    }
    text = wk.render_weekly_text(review)
    assert "OPENCO" in text
    assert "IPO" in text


def test_weekly_ipo_section_absent_when_no_issues():
    review = {
        "date": "2026-08-16", "headline": "", "allocation": [],
        "concentration_flags": [], "laggards": [], "switch_candidates": [],
        "switch_suggestions": [], "scoreboard": {"counts": {}, "checked": 0, "correct": 0},
        "ipo_watch": [],
    }
    assert "IPO" not in wk.render_weekly_text(review)


def test_ipo_read_failure_does_not_break_the_weekly(monkeypatch):
    monkeypatch.setattr(wk, "_weekly_ipos", lambda on: (_ for _ in ()).throw(RuntimeError("boom")))
    # build_weekly_review catches per-section; the helper itself must be safe.
    assert wk._safe_weekly_ipos(date(2026, 8, 16)) == []
```

- [ ] **Step 2: Run it to verify it fails**

Run: `python -m pytest tests/unit/test_delivery_weekly.py -v`
Expected: FAIL — `AttributeError: module 'core.delivery.weekly' has no attribute '_safe_weekly_ipos'`

- [ ] **Step 3: Implement**

In `core/delivery/weekly.py`, add after `_active_shelf_ideas` (line 59):

```python
def _weekly_ipos(on: date) -> list[dict]:
    """IPO watch rows for the digest. Wider than the daily brief's cap: the
    weekly is where a reader plans the coming week's windows."""
    from core.delivery.brief import _ipo_watch
    return _ipo_watch(max_items=settings.DELIVERY_WEEKLY_MAX_IPOS, on=on)


def _safe_weekly_ipos(on: date) -> list[dict]:
    try:
        return _weekly_ipos(on)
    except Exception as exc:
        logger.warning("[weekly] ipo read failed (non-fatal): %s", exc)
        return []
```

In `build_weekly_review`, add to the `review` dict after `"paper_shelf"`:

```python
        "ipo_watch": _safe_weekly_ipos(on),
```

In `render_weekly_text`, add before the scoreboard block (line 231):

```python
    ipos = review.get("ipo_watch", []) or []
    if ipos:
        from core.delivery.brief import _ipo_demand, _ipo_lean, _ipo_window
        on = date.fromisoformat(review["date"])
        lines.append("IPO watch (research view, not advice):")
        for w in ipos:
            lean, _reason = _ipo_lean(w)
            window = _ipo_window(w, on)
            demand = _ipo_demand(w) if lean not in ("data pending", "not open yet") else ""
            bits = [b for b in (window, f"Lean: {lean}", demand) if b]
            lines.append(f"  • {w['symbol']} {w.get('company', '')} — " + " · ".join(bits))
```

Add the config key. In `config.yaml` under `delivery:`:

```yaml
  weekly_max_ipos: 6                   # IPO rows in the weekly digest
```

In `src/backend/shared/config/settings/base.py`, beside the other `DELIVERY_BRIEF_*` settings:

```python
DELIVERY_WEEKLY_MAX_IPOS: int = int(cfg("delivery.weekly_max_ipos", fallback=6))
```

- [ ] **Step 4: Run the tests**

Run: `python -m pytest tests/unit/test_delivery_weekly.py -v`
Expected: PASS

- [ ] **Step 5: Run the full unit suite and commit**

Run: `python -m pytest tests/unit -q`

```bash
git add core/delivery/weekly.py tests/unit/test_delivery_weekly.py \
        config.yaml src/backend/shared/config/settings/base.py
git commit -m "feat(ipo): add an IPO section to the weekly digest

The weekly has never mentioned IPOs at all. It now carries the same
state-aware rows as the daily brief, with a wider cap since the weekly is
where the coming week's windows get planned.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

# PHASE P1 — The historical spine

## Task 7: IPO history schema + store

One row per historical mainboard IPO: pre-listing knowables joined to realised outcome curves. Rebuildable from source at any time.

**Files:**
- Create: `core/ipo/history.py`
- Test: `tests/unit/test_ipo_history.py`

**Interfaces:**
- Produces:
  - `IpoRecord` (pydantic `BaseModel`) with fields listed below
  - `IpoHistoryStore(base_dir: str | None = None)` with `.path`, `.append(rec)`, `.load_all() -> list[IpoRecord]`, `.existing_symbols() -> set[str]`, `.upsert(rec)`

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_ipo_history.py`:

```python
"""PI Prospect P1 — the historical spine store."""
from core.ipo.history import IpoHistoryStore, IpoRecord

_REC = dict(symbol="NEWCO", company="NewCo Ltd", listing_date="2026-06-15",
            issue_price=315.0, total_x=22.7, qib_x=45.2, retail_x=8.1,
            issue_size_shares=1_000_000.0)


def test_round_trip(tmp_path):
    store = IpoHistoryStore(base_dir=str(tmp_path))
    store.append(IpoRecord(**_REC))
    rows = store.load_all()
    assert len(rows) == 1 and rows[0].symbol == "NEWCO"
    assert rows[0].outcomes == {}          # not yet graded


def test_upsert_replaces_by_symbol(tmp_path):
    store = IpoHistoryStore(base_dir=str(tmp_path))
    store.append(IpoRecord(**_REC))
    store.upsert(IpoRecord(**{**_REC, "outcomes": {"1": 12.5}}))
    rows = store.load_all()
    assert len(rows) == 1
    assert rows[0].outcomes == {"1": 12.5}


def test_existing_symbols_supports_resumable_backfill(tmp_path):
    store = IpoHistoryStore(base_dir=str(tmp_path))
    store.append(IpoRecord(**_REC))
    assert store.existing_symbols() == {"NEWCO"}


def test_corrupt_line_is_skipped_not_fatal(tmp_path):
    store = IpoHistoryStore(base_dir=str(tmp_path))
    store.append(IpoRecord(**_REC))
    with open(store.path, "a", encoding="utf-8") as fh:
        fh.write("{not json\n")
    assert len(store.load_all()) == 1


def test_missing_file_loads_empty(tmp_path):
    assert IpoHistoryStore(base_dir=str(tmp_path)).load_all() == []
```

- [ ] **Step 2: Run it to verify it fails**

Run: `python -m pytest tests/unit/test_ipo_history.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'core.ipo.history'`

- [ ] **Step 3: Implement**

Create `core/ipo/history.py`:

```python
"""PI Prospect P1 — the historical spine (design section 5, P1).

One row per mainboard IPO: what was knowable BEFORE listing joined to what
actually happened after. This is the file that decides whether any later
scoring model is evidence or astrology, so it is deliberately dumb — a JSONL
of facts, rebuildable from NSE plus the bhavcopy parquet at any time, with no
derived score anywhere in it.

Outcome horizons are TRADING DAYS, keyed as strings because JSON object keys
are strings: "1" (listing day), "5", "21", "63", "126", "252".
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

HORIZONS_TD: tuple[int, ...] = (1, 5, 21, 63, 126, 252)


class IpoRecord(BaseModel):
    symbol: str
    company: str = ""
    listing_date: str = ""             # ISO
    issue_price: float | None = None

    # Pre-listing knowables. None means genuinely unavailable — never 0.
    total_x: float | None = None
    qib_x: float | None = None
    retail_x: float | None = None
    issue_size_shares: float | None = None

    # Realised curves, percent vs ISSUE PRICE, keyed by trading-day horizon.
    outcomes: dict[str, float] = Field(default_factory=dict)
    # Same horizons, percent vs ^NSEI over the identical calendar dates.
    excess: dict[str, float] = Field(default_factory=dict)

    listing_open: float | None = None
    listing_close: float | None = None
    sessions_available: int = 0


class IpoHistoryStore:
    """JSONL at <base_dir>/ipo_history.jsonl."""

    def __init__(self, base_dir: str | None = None) -> None:
        self._dir = Path(base_dir or "data/ipo")
        self._dir.mkdir(parents=True, exist_ok=True)

    @property
    def path(self) -> Path:
        return self._dir / "ipo_history.jsonl"

    def append(self, rec: IpoRecord) -> None:
        with open(self.path, "a", encoding="utf-8") as fh:
            fh.write(rec.model_dump_json() + "\n")

    def load_all(self) -> list[IpoRecord]:
        if not self.path.exists():
            return []
        out: list[IpoRecord] = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                out.append(IpoRecord(**json.loads(line)))
            except Exception:
                continue            # a corrupt line must never break a backfill
        return out

    def existing_symbols(self) -> set[str]:
        return {r.symbol for r in self.load_all()}

    def upsert(self, rec: IpoRecord) -> None:
        """Replace any row for this symbol. Rewrites the file — acceptable at
        a few hundred rows, and keeps the reader trivially correct."""
        rows = {r.symbol: r for r in self.load_all()}
        rows[rec.symbol] = rec
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(
            "".join(r.model_dump_json() + "\n" for r in rows.values()),
            encoding="utf-8",
        )
        tmp.replace(self.path)
```

- [ ] **Step 4: Run the tests**

Run: `python -m pytest tests/unit/test_ipo_history.py -v`
Expected: PASS (5 tests)

- [ ] **Step 5: Commit**

```bash
git add core/ipo/history.py tests/unit/test_ipo_history.py
git commit -m "feat(ipo): historical spine store

One JSONL row per mainboard IPO: pre-listing knowables joined to realised
curves. Deliberately carries no derived score - it is the evidence the
later model has to answer to, so it stays rebuildable from source.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Task 8: Outcome curves from the bhavcopy tape

Given a listed symbol, compute its realised return at each trading-day horizon versus issue price, and the same versus `^NSEI`.

**Files:**
- Create: `core/ipo/outcomes.py`
- Test: `tests/unit/test_ipo_backfill.py`

**Interfaces:**
- Consumes: `IpoRecord`, `HORIZONS_TD` (Task 7); an `EodStore`-shaped DataFrame
- Produces:
  - `symbol_sessions(window: pd.DataFrame, symbol: str) -> pd.DataFrame` — that symbol's EQ rows, date-sorted
  - `compute_outcomes(sessions, issue_price, index_pct) -> tuple[dict[str, float], dict[str, float], int]` returning `(outcomes, excess, sessions_available)`

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_ipo_backfill.py`:

```python
"""PI Prospect P1 — outcome-curve maths against a synthetic tape."""
import pandas as pd

from core.ipo.outcomes import compute_outcomes, symbol_sessions


def _tape(symbol: str, closes: list[float], start="2026-06-15") -> pd.DataFrame:
    days = pd.bdate_range(start=start, periods=len(closes))
    return pd.DataFrame({
        "symbol": [symbol] * len(closes),
        "series": ["EQ"] * len(closes),
        "date": [d.date().isoformat() for d in days],
        "open": closes, "close": closes,
    })


def test_returns_are_measured_against_issue_price_not_first_close():
    """A 'listing pop' is issue price to market. Measuring from the first
    close would silently discard the entire listing-day move - the single
    most important number in the whole dataset."""
    tape = _tape("NEWCO", [400.0, 410.0, 420.0, 430.0, 440.0])
    sessions = symbol_sessions(tape, "NEWCO")
    outcomes, _excess, n = compute_outcomes(sessions, issue_price=200.0,
                                            index_pct=lambda a, b: 0.0)
    assert n == 5
    assert outcomes["1"] == 100.0          # 400 vs 200 issue price
    assert outcomes["5"] == 120.0          # 440 vs 200


def test_immature_horizons_are_absent_not_zero():
    tape = _tape("NEWCO", [400.0, 410.0])
    outcomes, _e, n = compute_outcomes(symbol_sessions(tape, "NEWCO"),
                                       issue_price=200.0,
                                       index_pct=lambda a, b: 0.0)
    assert n == 2
    assert "1" in outcomes
    assert "5" not in outcomes and "252" not in outcomes


def test_excess_subtracts_the_index_over_the_same_dates():
    tape = _tape("NEWCO", [220.0, 220.0, 220.0, 220.0, 220.0])
    outcomes, excess, _n = compute_outcomes(
        symbol_sessions(tape, "NEWCO"), issue_price=200.0,
        index_pct=lambda a, b: 4.0,        # index +4% over the same window
    )
    assert outcomes["5"] == 10.0
    assert excess["5"] == 6.0


def test_only_eq_series_rows_count():
    tape = pd.concat([_tape("NEWCO", [400.0, 410.0]),
                      pd.DataFrame({"symbol": ["NEWCO"], "series": ["BE"],
                                    "date": ["2026-06-17"], "open": [999.0],
                                    "close": [999.0]})])
    assert len(symbol_sessions(tape, "NEWCO")) == 2


def test_zero_or_missing_issue_price_yields_no_outcomes():
    tape = _tape("NEWCO", [400.0, 410.0])
    outcomes, excess, _n = compute_outcomes(symbol_sessions(tape, "NEWCO"),
                                            issue_price=0.0,
                                            index_pct=lambda a, b: 0.0)
    assert outcomes == {} and excess == {}
```

- [ ] **Step 2: Run it to verify it fails**

Run: `python -m pytest tests/unit/test_ipo_backfill.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'core.ipo.outcomes'`

- [ ] **Step 3: Implement**

Create `core/ipo/outcomes.py`:

```python
"""PI Prospect P1 — realised post-listing curves from the bhavcopy tape.

Everything here is measured against the ISSUE PRICE, not the first close.
An IPO's defining number is the listing-day move from what subscribers paid
to what the market said it was worth; anchoring on the first close throws
that away and turns Ola and Ather into the same kind of animal.
"""
from __future__ import annotations

from typing import Callable

import pandas as pd

from core.ipo.history import HORIZONS_TD


def symbol_sessions(window: pd.DataFrame, symbol: str) -> pd.DataFrame:
    """That symbol's EQ sessions, oldest first. Empty frame if it never traded."""
    if window is None or window.empty:
        return pd.DataFrame(columns=["symbol", "series", "date", "open", "close"])
    mask = (window["symbol"] == symbol) & (window["series"] == "EQ")
    return window[mask].sort_values("date").reset_index(drop=True)


def compute_outcomes(
    sessions: pd.DataFrame,
    issue_price: float | None,
    index_pct: Callable[[str, str], float],
) -> tuple[dict[str, float], dict[str, float], int]:
    """(outcomes, excess, sessions_available).

    `index_pct(start_iso, end_iso)` returns the benchmark's percent change over
    the same two calendar dates. Injected rather than imported so the maths is
    testable without a network and so the caller can fetch the index ONCE for
    the whole backfill instead of per row.

    A horizon the symbol has not yet reached is ABSENT from the dict. Zero
    would be indistinguishable from a flat outcome.
    """
    n = len(sessions)
    outcomes: dict[str, float] = {}
    excess: dict[str, float] = {}
    if n == 0 or not issue_price or issue_price <= 0:
        return outcomes, excess, n

    first_date = str(sessions["date"].iloc[0])
    for td in HORIZONS_TD:
        if n < td:
            continue
        row = sessions.iloc[td - 1]
        close = float(row["close"])
        pct = (close / issue_price - 1.0) * 100.0
        outcomes[str(td)] = round(pct, 4)
        try:
            bench = index_pct(first_date, str(row["date"]))
        except Exception:
            continue          # no benchmark for this date: excess stays absent
        excess[str(td)] = round(pct - bench, 4)
    return outcomes, excess, n
```

- [ ] **Step 4: Run the tests**

Run: `python -m pytest tests/unit/test_ipo_backfill.py -v`
Expected: PASS (5 tests)

- [ ] **Step 5: Commit**

```bash
git add core/ipo/outcomes.py tests/unit/test_ipo_backfill.py
git commit -m "feat(ipo): realised post-listing curves from the bhavcopy tape

Measured against the issue price, not the first close: the listing-day
move from what subscribers paid to what the market paid is the defining
number, and anchoring on the first close discards it entirely.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Task 9: The backfill CLI

Joins `listPastIPO` to the tape and writes the spine. Offline apart from one `listPastIPO` call and one `^NSEI` download; re-runnable and resumable.

**Files:**
- Create: `scripts/ipo_backfill.py`
- Test: `tests/unit/test_ipo_backfill.py` (extend)

**Interfaces:**
- Consumes: `IpoHistoryStore`, `IpoRecord` (Task 7), `symbol_sessions`, `compute_outcomes` (Task 8), `EodStore`
- Produces: `build_index_pct(start: date, end: date) -> Callable[[str, str], float]`; `run_backfill(...) -> dict`

- [ ] **Step 1: Write the failing test**

Append to `tests/unit/test_ipo_backfill.py`:

```python
from datetime import date

import scripts.ipo_backfill as bf
from core.ipo.history import IpoHistoryStore


def test_backfill_joins_feed_to_tape(tmp_path, monkeypatch):
    tape = _tape("NEWCO", [400.0] * 6)
    monkeypatch.setattr(bf, "_load_past_ipos", lambda since, until: [
        {"symbol": "NEWCO", "company": "NewCo Ltd", "listing_date": "2026-06-15",
         "issue_price": 200.0, "total_x": 22.7, "qib_x": 45.2, "retail_x": 8.1},
    ])
    monkeypatch.setattr(bf, "_load_tape", lambda end: tape)
    monkeypatch.setattr(bf, "build_index_pct", lambda a, b: (lambda s, e: 0.0))

    result = bf.run_backfill(base_dir=str(tmp_path), on=date(2026, 8, 12))
    assert result["written"] == 1
    rec = IpoHistoryStore(base_dir=str(tmp_path)).load_all()[0]
    assert rec.symbol == "NEWCO"
    assert rec.outcomes["1"] == 100.0
    assert rec.sessions_available == 6


def test_backfill_is_idempotent(tmp_path, monkeypatch):
    """Re-running must not duplicate rows — outcomes mature over time, so this
    script is expected to be run repeatedly."""
    tape = _tape("NEWCO", [400.0] * 6)
    monkeypatch.setattr(bf, "_load_past_ipos", lambda since, until: [
        {"symbol": "NEWCO", "company": "NewCo Ltd", "listing_date": "2026-06-15",
         "issue_price": 200.0, "total_x": 22.7, "qib_x": None, "retail_x": None},
    ])
    monkeypatch.setattr(bf, "_load_tape", lambda end: tape)
    monkeypatch.setattr(bf, "build_index_pct", lambda a, b: (lambda s, e: 0.0))

    bf.run_backfill(base_dir=str(tmp_path), on=date(2026, 8, 12))
    bf.run_backfill(base_dir=str(tmp_path), on=date(2026, 8, 12))
    assert len(IpoHistoryStore(base_dir=str(tmp_path)).load_all()) == 1


def test_symbols_that_never_traded_are_recorded_not_dropped(tmp_path, monkeypatch):
    """Survivorship guard (spec section 7 risk 5): an IPO with no tape is a
    fact about the market, not a row to discard."""
    monkeypatch.setattr(bf, "_load_past_ipos", lambda since, until: [
        {"symbol": "GHOSTCO", "company": "Ghost Co", "listing_date": "2026-06-15",
         "issue_price": 200.0, "total_x": None, "qib_x": None, "retail_x": None},
    ])
    monkeypatch.setattr(bf, "_load_tape", lambda end: _tape("OTHER", [10.0]))
    monkeypatch.setattr(bf, "build_index_pct", lambda a, b: (lambda s, e: 0.0))

    bf.run_backfill(base_dir=str(tmp_path), on=date(2026, 8, 12))
    rec = IpoHistoryStore(base_dir=str(tmp_path)).load_all()[0]
    assert rec.symbol == "GHOSTCO"
    assert rec.sessions_available == 0 and rec.outcomes == {}
```

- [ ] **Step 2: Run it to verify it fails**

Run: `python -m pytest tests/unit/test_ipo_backfill.py -k backfill -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'scripts.ipo_backfill'`

- [ ] **Step 3: Implement**

Create `scripts/ipo_backfill.py`:

```python
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
from datetime import date, datetime, timedelta
from typing import Callable

import pandas as pd

from core.ipo.history import IpoHistoryStore, IpoRecord
from core.ipo.outcomes import compute_outcomes, symbol_sessions

logger = logging.getLogger(__name__)

_INDEX_TICKER = "^NSEI"
_FETCH_PAD_DAYS = 7          # see core/audit/benchmark.py: a 1-day yfinance
                             # window returns an EMPTY frame for ^NSEI


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
        store.upsert(IpoRecord(
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


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    ap = argparse.ArgumentParser(description="Build the historical IPO spine")
    ap.add_argument("--since", default="2024-05-01")
    ap.add_argument("--base-dir", default=None)
    args = ap.parse_args()
    print(json.dumps(run_backfill(base_dir=args.base_dir,
                                  since=date.fromisoformat(args.since)), indent=2))


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run the tests**

Run: `python -m pytest tests/unit/test_ipo_backfill.py -v`
Expected: PASS (8 tests)

- [ ] **Step 5: Run it for real**

Run: `python -m scripts.ipo_backfill --since 2024-05-01`
Expected: JSON with `listings` and `written` in the 100-300 range. Inspect `data/ipo/ipo_history.jsonl`.

**If `written` is 0 or `listings` is 0, STOP and report.** `listPastIPO` chunks its date range internally; a two-year span may need splitting. Do not paper over an empty result — an empty spine invalidates all of P1.

- [ ] **Step 6: Commit**

```bash
git add scripts/ipo_backfill.py tests/unit/test_ipo_backfill.py
git commit -m "feat(ipo): historical backfill CLI

Joins listPastIPO to the 550 bhavcopy sessions already on the volume.
Fetches ^NSEI once for the whole window rather than per row, reusing the
holiday-walkback rule from core/audit/benchmark.py but not its per-date
fetcher. Idempotent by symbol so it can be re-run as horizons mature.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Task 10: The measurement report

P1's actual deliverable: *what predicted what*, with honest interval reporting.

**Files:**
- Create: `core/ipo/report.py`
- Test: `tests/unit/test_ipo_report.py`

**Interfaces:**
- Consumes: `IpoHistoryStore`, `IpoRecord`
- Produces: `summarise(rows: list[IpoRecord]) -> dict`, `render_report(summary: dict) -> str`

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_ipo_report.py`:

```python
"""PI Prospect P1 — the measurement report."""
from core.ipo.history import IpoRecord
from core.ipo.report import render_report, summarise


def _rec(symbol, total_x, listing_pct):
    return IpoRecord(symbol=symbol, issue_price=100.0, total_x=total_x,
                     outcomes={"1": listing_pct}, excess={"1": listing_pct},
                     sessions_available=260)


def test_buckets_by_subscription_and_reports_n():
    rows = [_rec("A", 50.0, 30.0), _rec("B", 40.0, 20.0),
            _rec("C", 1.5, -10.0), _rec("D", 1.0, -5.0)]
    out = summarise(rows)
    hot = out["by_subscription"]["hot (>=10x)"]
    cold = out["by_subscription"]["cold (<2x)"]
    assert hot["n"] == 2 and cold["n"] == 2
    assert hot["mean_listing_pct"] == 25.0
    assert cold["mean_listing_pct"] == -7.5


def test_rows_without_the_feature_are_excluded_not_zeroed():
    rows = [_rec("A", 50.0, 30.0), _rec("B", None, 20.0)]
    out = summarise(rows)
    assert sum(b["n"] for b in out["by_subscription"].values()) == 1
    assert out["missing_subscription"] == 1


def test_report_states_sample_size_and_the_gmp_caveat():
    text = render_report(summarise([_rec("A", 50.0, 30.0)]))
    assert "n=" in text
    assert "GMP" in text          # the forward-validation caveat must survive


def test_empty_history_does_not_crash():
    out = summarise([])
    assert out["total"] == 0
    assert "no rows" in render_report(out).lower()
```

- [ ] **Step 2: Run it to verify it fails**

Run: `python -m pytest tests/unit/test_ipo_report.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'core.ipo.report'`

- [ ] **Step 3: Implement**

Create `core/ipo/report.py`:

```python
"""PI Prospect P1 — what actually predicted what (design section 5, P1).

This module measures; it does not model. Its output is the evidence the P3
weights must answer to, and the honest caveats travel WITH the numbers so a
reader cannot pick up the hit-rate without also picking up its limits.
"""
from __future__ import annotations

from statistics import mean

from core.ipo.history import IpoRecord

_BUCKETS: tuple[tuple[str, float, float], ...] = (
    ("hot (>=10x)", 10.0, float("inf")),
    ("warm (2-10x)", 2.0, 10.0),
    ("cold (<2x)", float("-inf"), 2.0),
)


def _bucket(total_x: float) -> str:
    for name, low, high in _BUCKETS:
        if low <= total_x < high:
            return name
    return _BUCKETS[-1][0]


def summarise(rows: list[IpoRecord]) -> dict:
    graded = [r for r in rows if r.outcomes.get("1") is not None]
    buckets: dict[str, dict] = {name: {"n": 0, "listing": [], "held_252": []}
                                for name, _lo, _hi in _BUCKETS}
    missing = 0
    for r in graded:
        if r.total_x is None:
            missing += 1
            continue                # dark-signal: excluded, never zeroed
        b = buckets[_bucket(r.total_x)]
        b["n"] += 1
        b["listing"].append(r.outcomes["1"])
        if r.outcomes.get("252") is not None:
            b["held_252"].append(r.outcomes["252"])

    by_subscription = {
        name: {
            "n": b["n"],
            "mean_listing_pct": round(mean(b["listing"]), 4) if b["listing"] else None,
            "positive_listing_rate": (
                round(sum(1 for x in b["listing"] if x > 0) / len(b["listing"]), 4)
                if b["listing"] else None),
            "n_matured_252": len(b["held_252"]),
            "mean_252_pct": round(mean(b["held_252"]), 4) if b["held_252"] else None,
        }
        for name, b in buckets.items()
    }
    return {
        "total": len(rows),
        "graded": len(graded),
        "missing_subscription": missing,
        "by_subscription": by_subscription,
    }


def render_report(summary: dict) -> str:
    if not summary.get("graded"):
        return "IPO historical spine — no rows with a listing-day outcome yet."

    lines = [
        f"IPO historical spine — {summary['graded']} of {summary['total']} rows graded",
        "",
        "Listing-day return vs ISSUE PRICE, bucketed by total subscription:",
    ]
    for name, b in summary["by_subscription"].items():
        if not b["n"]:
            lines.append(f"  {name:14} n=0")
            continue
        lines.append(
            f"  {name:14} n={b['n']:<4} mean {b['mean_listing_pct']:+.2f}%  "
            f"positive {b['positive_listing_rate']:.0%}  "
            f"(252td: n={b['n_matured_252']}"
            + (f", mean {b['mean_252_pct']:+.2f}%" if b["mean_252_pct"] is not None else "")
            + ")"
        )
    lines += [
        "",
        "READ WITH CARE:",
        f"  - {summary['missing_subscription']} graded rows had no subscription "
        "figure and are excluded, not counted as zero.",
        "  - Buckets are small. Treat these as directional, not significant; the "
        "auditor's 2026-08-07 Wilson episode is the precedent for what happens "
        "when a narrow interval gets over-read.",
        "  - GMP and RHP financials are NOT in this dataset. Grey-market archives "
        "and prospectus PDFs are not retrievable retroactively at scale, so those "
        "weights can only be validated forward from launch (spec section 5, P1).",
    ]
    return "\n".join(lines)
```

- [ ] **Step 4: Run the tests**

Run: `python -m pytest tests/unit/test_ipo_report.py -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Produce the real report**

```bash
python -c "
from core.ipo.history import IpoHistoryStore
from core.ipo.report import render_report, summarise
print(render_report(summarise(IpoHistoryStore().load_all())))
"
```

Save the output into the commit message body. **This is P1's deliverable — read it before moving on.** If every bucket has `n<10`, say so plainly rather than presenting the means as findings.

- [ ] **Step 6: Run the full unit suite and commit**

Run: `python -m pytest tests/unit -q`

```bash
git add core/ipo/report.py tests/unit/test_ipo_report.py
git commit -m "feat(ipo): the P1 measurement report

Measures, does not model. Carries its own caveats so the hit-rate cannot
be quoted without its limits: excluded-not-zeroed dark rows, small
buckets, and the fact that GMP and RHP financials are absent from the
historical dataset by necessity and can only be validated forward.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Task 11: Milestones + the cache-freshness invariant

Per the project rule, milestones land in the same commit as the work that creates them. The watchdog must be able to tell if the new daily job dies.

**Files:**
- Modify: `core/ops/watchdog/checks.py`, `config/milestones.yaml`
- Test: `tests/unit/ops/test_watchdog_checks.py` — **exists; append.** It imports the module as `from core.ops.watchdog import checks as C`, so use the `C` alias below rather than introducing a second name for the same module.

**Interfaces:**
- Consumes: `settings.IPO_CACHE_MAX_AGE_HOURS` (Task 4)
- Produces: watchdog check `ipo_cache_fresh`

- [ ] **Step 1: Write the failing test**

Append to `tests/unit/ops/test_watchdog_checks.py` (add `import json` and
`from datetime import datetime, timedelta, timezone` to the existing imports at
the top of the file if they are not already there):

```python
def _write_ipo_cache(tmp_path, hours_old: float):
    (tmp_path / "market_cache").mkdir(parents=True, exist_ok=True)
    stamp = (datetime.now(timezone.utc) - timedelta(hours=hours_old)).isoformat()
    (tmp_path / "market_cache" / "ipo.json").write_text(
        json.dumps({"fetched_at": stamp, "degraded": False,
                    "current": [], "upcoming": [], "past": []}),
        encoding="utf-8")


def test_ipo_cache_fresh_satisfied(tmp_path, monkeypatch):
    monkeypatch.setattr(C, "_DATA_DIR", tmp_path)
    _write_ipo_cache(tmp_path, hours_old=3)
    assert C.run_check("ipo_cache_fresh").state == "satisfied"


def test_ipo_cache_stale_is_pending(tmp_path, monkeypatch):
    """A stale cache means the twice-daily refresh job is dead — exactly the
    class of silent failure the watchdog exists to catch."""
    monkeypatch.setattr(C, "_DATA_DIR", tmp_path)
    _write_ipo_cache(tmp_path, hours_old=72)
    result = C.run_check("ipo_cache_fresh")
    assert result.state == "pending"
    assert "stale" in result.detail.lower()


def test_ipo_cache_absent_is_pending(tmp_path, monkeypatch):
    monkeypatch.setattr(C, "_DATA_DIR", tmp_path)
    assert C.run_check("ipo_cache_fresh").state == "pending"
```

- [ ] **Step 2: Run it to verify it fails**

Run: `python -m pytest tests/unit/ops/test_watchdog_checks.py -k ipo_cache -v`
Expected: FAIL — the check is not registered, so state is `"unknown"`

- [ ] **Step 3: Implement the check**

Append to `core/ops/watchdog/checks.py`:

```python
# ---------------------------------------------------------------------------
# PI Prospect — IPO feed liveness
# ---------------------------------------------------------------------------

@check("ipo_cache_fresh")
def ipo_cache_fresh() -> CheckResult:
    """The IPO cache is refreshed twice daily by the ipo_refresh jobs. If it
    goes stale the jobs are dead, and the failure is otherwise SILENT — the
    brief keeps rendering yesterday's issues with no error anywhere."""
    from core.config import settings

    max_age = float(getattr(settings, "IPO_CACHE_MAX_AGE_HOURS", 48))
    path = _data_dir() / "market_cache" / "ipo.json"
    if not path.exists():
        return CheckResult("pending", f"IPO cache absent at {path}",
                           {"path": str(path)})
    try:
        stamp = json.loads(path.read_text(encoding="utf-8")).get("fetched_at") or ""
        fetched = datetime.fromisoformat(stamp)
    except Exception as exc:
        return CheckResult("pending", f"IPO cache timestamp unreadable: {exc}",
                           {"path": str(path)})
    if fetched.tzinfo is None:
        fetched = fetched.replace(tzinfo=timezone.utc)
    age_h = (datetime.now(timezone.utc) - fetched).total_seconds() / 3600.0
    evidence = {"fetched_at": stamp, "age_hours": round(age_h, 1),
                "max_age_hours": max_age}
    if age_h > max_age:
        return CheckResult(
            "pending",
            f"IPO cache is stale — {age_h:.1f}h old (limit {max_age:.0f}h). "
            f"The twice-daily ipo_refresh job is not running.",
            evidence)
    return CheckResult("satisfied", f"IPO cache {age_h:.1f}h old.", evidence)
```

`timezone` must be in the module's `datetime` import. Verify the existing line reads `from datetime import date, datetime, timedelta` and extend it to include `timezone`.

- [ ] **Step 4: Run the tests**

Run: `python -m pytest tests/unit/ops/test_watchdog_checks.py -v`
Expected: PASS

- [ ] **Step 5: Register the milestones**

Spec §9 lists a fourth entry, `ipo_verdicts_visible_gate`. It is **deliberately
not registered here**: the work that creates it is P5, and the registry rule is
that a milestone lands with its work. Registering it now would have the watchdog
chase a decision that nothing in the codebase can yet inform.

Append to `config/milestones.yaml` under `milestones:`:

```yaml
  - id: ipo_cache_fresh
    kind: invariant
    title: "IPO calendar cache is being refreshed"
    check: ipo_cache_fresh
    action: >
      The twice-daily ipo_refresh job has stopped. The brief keeps rendering
      stale issues with no error, so this is silent without the watchdog.
      Check the scheduler job ids ipo_refresh_am / ipo_refresh_pm.
    docs: docs/superpowers/specs/2026-08-11-ipo-intelligence-design.md

  - id: ipo_p0_live_window_check
    kind: milestone
    title: "IPO P0 — verify a live window end-to-end"
    check: manual_confirmation
    deadline: 2026-09-15
    lead_days: 3
    action: >
      During any open mainboard IPO window, confirm the daily brief shows a
      real subscription x (not 'data pending') and the correct window line,
      and that a CLOSED issue is not rendered as open. Also settle spec
      section 7 risk 6 - compare the stored combined vs nse_only ladders for
      one symbol against NSE's published end-of-day figure and pin the
      authority in a docstring. Remove this entry once judged.
    docs: docs/superpowers/specs/2026-08-11-ipo-intelligence-design.md

  - id: ipo_p1_backtest_review
    kind: milestone
    title: "IPO P1 — read the historical measurement report"
    check: manual_confirmation
    deadline: 2026-09-30
    lead_days: 5
    action: >
      Run scripts/ipo_backfill.py then core.ipo.report and read the output.
      Decide whether the bucket sample sizes support proceeding to P2/P3 or
      whether the spine needs a wider date range first. Remove once judged.
    docs: docs/superpowers/specs/2026-08-11-ipo-intelligence-design.md
```

- [ ] **Step 6: Verify the registry loads**

```bash
python -c "
from core.ops.watchdog.checks import run_check
import yaml
reg = yaml.safe_load(open('config/milestones.yaml', encoding='utf-8'))
ids = [m['id'] for m in reg['milestones']]
print('entries:', len(ids))
assert 'ipo_cache_fresh' in ids
print('ipo_cache_fresh ->', run_check('ipo_cache_fresh').state)
"
```

Expected: entry count is the previous 9 plus 3 = 12, and the check answers (not `unknown`).

- [ ] **Step 7: Run the full unit suite and commit**

Run: `python -m pytest tests/unit -q`

```bash
git add core/ops/watchdog/checks.py config/milestones.yaml \
        tests/unit/test_watchdog_checks.py
git commit -m "feat(ipo): watchdog invariant + P0/P1 milestones

A dead ipo_refresh job is silent - the brief renders stale issues with no
error - so cache age becomes an invariant. Milestones land in the same
commit as the work per the registry rule.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Task 12: Update the spec's status

**Files:**
- Modify: `docs/superpowers/specs/2026-08-11-ipo-intelligence-design.md`

- [ ] **Step 1: Mark P0 and P1 delivered**

Change the `**Status:**` line to:

```markdown
**Status:** P0 + P1 implemented (plan `docs/superpowers/plans/2026-08-12-ipo-prospect-p0-p1.md`); P2-P5 not started
```

Under §5 P0 and §5 P1, add a one-line `**Delivered:**` note naming the commits.

- [ ] **Step 2: Commit**

```bash
git add docs/superpowers/specs/2026-08-11-ipo-intelligence-design.md
git commit -m "docs(ipo): mark P0+P1 delivered

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Done criteria

- [ ] `python -m pytest tests/unit -q` green, no new failures against the pre-existing baseline
- [ ] A live or recent IPO renders in the daily brief with a real subscription × and a correct window line
- [ ] A closed issue never renders under a heading claiming it is open
- [ ] The weekly digest carries an IPO section
- [ ] `data/ipo/ipo_history.jsonl` exists with >100 rows
- [ ] The measurement report runs and its sample sizes are stated honestly
- [ ] `run_check("ipo_cache_fresh")` answers `satisfied` on a fresh cache
- [ ] `config/milestones.yaml` carries the three new entries and still loads

## Explicitly NOT in this plan

Hype/Substance indices, verdicts, GMP fetching, RHP extraction, the convergence tracker, auditor `Lane` extension, and app/chat surfaces. Those are P2-P5 and each gets its own plan once the P1 measurement is in hand.

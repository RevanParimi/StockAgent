"""
The items the company-event feed reads, each with an identity, a text and the
source's own publication time. Pure functions: the feed passes the rows.

**Identity** is the de-duplication key across runs:

- an NSE announcement is `nse:<seq_id>`, NSE's own id (else its attachment URL);
- an NSE board meeting is `nsebm:<hash of code, meeting day, filing day>`. NSE
  files one row per purpose, such as "Board Meeting Intimation" and "Financial
  Results" for one meeting, and those rows become one item. The filing day is
  read from the row's own timestamp, so the clock never enters an identity;
- a news article is `news:<hash of its URL>`, without tracking parameters. An
  article without a URL is dropped: it cannot be cited. Serper's Google
  redirect links arrive without a URL (services/data/fetchers/news.py), so one
  article ranked higher in one run and lower in the next is one item.

**Publication time** comes from the source, never from the fetch:

- an announcement: `an_dt` ("21-Oct-2026 15:39:05", IST), else `sort_date`;
- a board meeting: `bm_timestamp`, when it was filed. Never `bm_date`, the
  meeting day, which is often weeks ahead;
- news: Serper's date ("5 hours ago", "Oct 20, 2026"), read by the brief's own
  rule: an age counts back from the fetch, and the IST day is kept.

`now` is when the rows were fetched (the feed reads it per stock). A time that
cannot be read is None; so is a news date in the future. An NSE row timed more
than 10 minutes after `now` is not an item yet: it is counted and left for a
later run, which the lookback window brings it back to. So a readable NSE time
is never stored as None. Field names were recorded from NSE's live responses
on 22 Oct 2026.

**The company** (an item filed under the wrong stock is the FIX-002 class):

- an NSE row must name the NSE code that was asked for (`symbol`,
  `bm_symbol`); a row for another code is dropped and counted;
- a news article must mention the company: its ticker or NSE code in capitals
  ("TCS", "M&M"), or its name. The name is matched as a phrase without legal
  suffixes ("Maruti Suzuki" for "Maruti Suzuki India Limited"), and by its
  first two words when it has three or more ("Adani Ports"). So an article
  about Tata Motors is not filed under Tata Elxsi. The classifier then judges
  the articles that pass.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from zoneinfo import ZoneInfo

from services.background.macro_news_fetcher import _normalize_serper_date

IST = ZoneInfo("Asia/Kolkata")

NSE_ANNOUNCEMENT = "nse_announcement"
NSE_BOARD_MEETING = "nse_board_meeting"
NEWS = "news"

_NSE_TIME_FORMATS = ("%d-%b-%Y %H:%M:%S", "%d-%b-%Y %H:%M")
_SORT_DATE_FORMATS = ("%Y-%m-%d %H:%M:%S",)
_MEETING_DAY_FORMATS = ("%d-%b-%Y",)
# NSE's clock may run a little ahead of ours: a filing time up to this much
# after the fetch is still a real one.
_FUTURE_SLACK = timedelta(minutes=10)


@dataclass(frozen=True)
class SourceItem:
    """One fetched item the classifier may cite."""
    source: str                    # nse_announcement | nse_board_meeting | news
    source_id: str                 # the identity above
    title: str
    text: str
    url: str | None
    announcement_id: str | None
    published_at: str | None       # ISO 8601 in IST, or None
    published_raw: str             # the source's own date string
    publisher: str = ""

    def published_day(self) -> str | None:
        return self.published_at[:10] if self.published_at else None


def _str(row: dict, *keys: str) -> str:
    """The first of `keys` holding a non-empty string or number, stripped."""
    for k in keys:
        v = row.get(k)
        if isinstance(v, bool):
            continue
        if isinstance(v, (str, int)) and str(v).strip():
            return str(v).strip()
    return ""


def _digest(*parts: str) -> str:
    return hashlib.sha1("|".join(parts).encode("utf-8")).hexdigest()[:16]


def _parse(raw: str, formats: tuple[str, ...]) -> datetime | None:
    for fmt in formats:
        try:
            return datetime.strptime(raw, fmt)
        except ValueError:
            continue
    return None


def nse_stamp(raw: str, formats: tuple[str, ...] = _NSE_TIME_FORMATS) -> datetime | None:
    """An NSE filing time (IST, no zone in the string), or None when unreadable."""
    parsed = _parse((raw or "").strip(), formats)
    return parsed.replace(tzinfo=IST) if parsed is not None else None


def is_ahead(stamped: datetime, now: datetime) -> bool:
    """True when a filing time is later than a fetch at `now` could have seen,
    allowing for NSE's clock running a little ahead."""
    return stamped > now.astimezone(IST) + _FUTURE_SLACK


def normalize_url(url) -> str | None:
    """An http(s) URL without its fragment and utm_* parameters, scheme and
    host in lower case and no trailing slash; None when it is not one."""
    if not isinstance(url, str) or not url.strip():
        return None
    parts = urlsplit(url.strip())
    if parts.scheme.lower() not in ("http", "https") or not parts.netloc:
        return None
    query = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True)
             if not k.lower().startswith("utm_")]
    path = parts.path.rstrip("/")
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), path, urlencode(query), ""))


def announcement_items(rows: list, code: str, now: datetime) -> tuple[list[SourceItem], int, int]:
    """(items from NSE announcement rows for `code`, rows naming another code,
    rows timed after the fetch at `now` and left for a later run)."""
    items: list[SourceItem] = []
    foreign = ahead = 0
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        if _str(row, "symbol").upper() != code.upper():
            foreign += 1
            continue
        title = _str(row, "desc", "subject")
        text = _str(row, "attchmntText")
        url = normalize_url(_str(row, "attchmntFile"))
        seq = _str(row, "seq_id")
        if not (title or text) or not (seq or url):
            continue
        raw = _str(row, "an_dt")
        stamped = nse_stamp(raw) if raw else None
        if stamped is None and _str(row, "sort_date"):
            alt = nse_stamp(_str(row, "sort_date"), _SORT_DATE_FORMATS)
            if alt is not None:
                raw, stamped = _str(row, "sort_date"), alt
        if stamped is not None and is_ahead(stamped, now):
            ahead += 1
            continue
        items.append(SourceItem(
            source=NSE_ANNOUNCEMENT, source_id=f"nse:{seq}" if seq else f"nse:{_digest(url)}",
            title=title, text=text, url=url, announcement_id=seq or None,
            published_at=stamped.isoformat() if stamped else None, published_raw=raw))
    return items, foreign, ahead


def board_meeting_items(rows: list, code: str, now: datetime,
                        since: date) -> tuple[list[SourceItem], int, int]:
    """(items from NSE board-meeting rows for `code` filed on or after `since`,
    rows naming another code, rows timed after the fetch at `now` and left for
    a later run). NSE returns every meeting, so the window is the filing day;
    a row with no readable filing time is kept (undated) only when its meeting
    day is on or after `since`."""
    groups: dict[tuple[str, str], list[tuple[dict, str | None, str]]] = {}
    foreign = ahead = 0
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        if _str(row, "bm_symbol", "symbol").upper() != code.upper():
            foreign += 1
            continue
        raw = _str(row, "bm_timestamp")
        stamped = nse_stamp(raw) if raw else None
        meeting_raw = _str(row, "bm_date")
        if stamped is not None:
            if stamped.date() < since:
                continue
            if is_ahead(stamped, now):
                ahead += 1
                continue
        else:
            meeting = _parse(meeting_raw, _MEETING_DAY_FORMATS)
            if meeting is None or meeting.date() < since:
                continue
        published = stamped.isoformat() if stamped else None
        filed_day = stamped.date().isoformat() if stamped else ""
        groups.setdefault((meeting_raw, filed_day), []).append((row, published, raw))

    items: list[SourceItem] = []
    for (meeting_raw, filed_day), members in groups.items():
        members.sort(key=lambda m: m[1] or "")
        purposes = list(dict.fromkeys(p for p in (_str(r, "bm_purpose") for r, _, _ in members) if p))
        descs = list(dict.fromkeys(d for d in (_str(r, "bm_desc") for r, _, _ in members) if d))
        url = next((u for u in (normalize_url(_str(r, "attachment")) for r, _, _ in members) if u), None)
        text = " | ".join(descs)
        if meeting_raw:
            text = f"{text} (meeting on {meeting_raw})" if text else f"Meeting on {meeting_raw}"
        title = " / ".join(purposes) or "Board meeting"
        items.append(SourceItem(
            source=NSE_BOARD_MEETING, source_id=f"nsebm:{_digest(code.upper(), meeting_raw, filed_day)}",
            title=title, text=text, url=url, announcement_id=None,
            published_at=members[0][1], published_raw=members[0][2]))
    return items, foreign, ahead


def news_items(results: list, now: datetime) -> list[SourceItem]:
    """Items from Serper /news results; one per URL, an article without a
    URL or a title dropped."""
    items: list[SourceItem] = []
    seen: set[str] = set()
    for r in results or []:
        if not isinstance(r, dict):
            continue
        url = normalize_url(r.get("link"))
        title = str(r.get("title") or "").strip()
        if not url or not title or url in seen:
            continue
        seen.add(url)
        raw = str(r.get("date") or "").strip()
        day = _normalize_serper_date(raw, now=now) if raw else ""
        items.append(SourceItem(
            source=NEWS, source_id=f"news:{_digest(url)}", title=title,
            text=str(r.get("snippet") or "").strip(), url=url, announcement_id=None,
            published_at=day or None, published_raw=raw,
            publisher=str(r.get("source") or "").strip()))
    return items


# ---------------------------------------------------------------------------
# Does a news article mention the company?
# ---------------------------------------------------------------------------

_LEGAL = {"limited", "ltd", "company", "co", "corporation", "corp", "inc", "plc", "pvt", "private"}
_JOINERS = {"of", "and", "&", "the"}


def _words(text: str) -> list[str]:
    return re.findall(r"[a-z0-9&]+", text.lower())


def name_phrases(names) -> set[str]:
    """The phrases that identify a company in text, from its names."""
    out: set[str] = set()
    for name in names or []:
        words = _words(str(name or ""))
        if words and words[0] == "the":
            words = words[1:]
        while words and (words[-1] in _LEGAL or words[-1] in _JOINERS):
            words.pop()
        if len(words) >= 3 and words[-1] == "india":
            words.pop()
            while words and words[-1] in _JOINERS:
                words.pop()
        if not words:
            continue
        phrase = " ".join(words)
        if len(phrase) >= 3:
            out.add(phrase)
        if len(words) >= 3 and words[1] not in _JOINERS:
            out.add(" ".join(words[:2]))
    return out


def mentions_company(item: SourceItem, phrases: set[str], codes: set[str]) -> bool:
    """True when the item's title or text names one of `codes` in capitals
    or contains one of `phrases` as whole words."""
    body = f"{item.title} {item.text}"
    for code in codes:
        code = (code or "").strip().upper()
        if len(code) >= 2 and re.search(rf"(?<![A-Za-z0-9]){re.escape(code)}(?![A-Za-z0-9])", body):
            return True
    padded = f" {' '.join(_words(body))} "
    return any(f" {p} " in padded for p in phrases)

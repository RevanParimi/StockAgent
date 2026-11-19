"""
services/data/fetchers/search_shadow.py
=======================================
PR-043: a second search beside Serper, recorded and not read.

Each unified analysis reads one Serper company search (five results, titles
and two-line snippets). Before the analysis reads anything new, this module
records what other search engines would have given at the moment of each
decision: after the analysis call returns, the same query goes to each
configured engine through OpenRouter's server tool (`openrouter:web_search`,
10 results; Parallel "fast", and Exa beside it for the two weeks), each
result's date is read from its page, and one row per analysis is appended to
`data/logs/search_shadow.jsonl`:

    {"v": 1, "time", "run_id", "ticker", "sector", "query",
     "serper": {"status", "source", "results": [{title, link, date, snippet}]},
     "engines": [{"engine", "params", "status", "reason", "model", "cost_usd",
                  "seconds", "budget": {"week_start", "used", "limit"},
                  "results": [{url, title, excerpt, date, date_source,
                               date_strength, excerpt_date, fetch}]}]}

The analysis reads nothing from here, and nothing here can stop or slow it:
`submit_shadow` returns at once and the work runs on one daemon thread;
every failure becomes a row (or an engine entry) with its reason, or a log
line. No key and no page text beyond the engines' own excerpts is written.

Dates (the card's step 2, the owner's route of 19 Nov 2026). No engine
returns a publish date through OpenRouter, so each result's page is read
once (a link two engines both return is read once):

- strong: the page's metadata (`article:published_time`, `datePublished`
  and their kin; a published date wins over a modified one), a date in the
  URL, an NSE filing name's time (`_DDMMYYYYhhmmss_`);
- weak, kept apart: a month in the path (recorded as `YYYY-MM`), the
  server's `Last-Modified`;
- beside, never counted: a date in the engine's own excerpt (`excerpt_date`).

A refusal (HTTP 4xx/5xx), a time-out or an address that is not public leaves
the page's own dates unread; a date in the URL still counts, as it did in
the tested method (receipt, "Dates read from the pages").

Switch: `search_shadow.enabled` in config.yaml; off is the rollback, and an
engine left out of `search_shadow.engines` is not called. Budget:
`search_shadow.weekly_budget` calls a week for each engine, the week running
Saturday 00:00 IST to Friday so the Saturday deep dives are recorded first;
past it the engine's entry says `budget` and no call is made.
"""

from __future__ import annotations

import ipaddress
import json
import logging
import os
import queue
import re
import socket
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import date, datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urljoin, urlsplit

import requests

from backend.shared.config import settings

try:  # POSIX only; elsewhere the in-process lock is the only guard
    import fcntl
except ImportError:  # pragma: no cover - Windows
    fcntl = None

logger = logging.getLogger(__name__)

# data/logs is the Railway volume mount (B1), as for data_health.jsonl.
LOGS_DIR = Path(os.getenv("LOGS_DIR", "data/logs"))
SHADOW_LOG = LOGS_DIR / "search_shadow.jsonl"
BUDGET_FILE = LOGS_DIR / "search_shadow_budget.json"

ROW_VERSION = 1
IST = timezone(timedelta(hours=5, minutes=30))
EXCERPT_MAX_CHARS = 4000
SNIPPET_MAX_CHARS = 1000
PAGE_MAX_BYTES = 400_000
MAX_REDIRECTS = 3
PAGE_WORKERS = 5
SEARCH_TIMEOUT_SECONDS = 60
QUEUE_MAX = 500
_PLACEHOLDER_KEY = "your-openrouter-api-key-here"
_UA = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/124 Safari/537.36",
    "Accept-Language": "en-IN,en;q=0.9",
}

STRONG = "strong"
WEAK = "weak"
SRC_META = "page metadata"
SRC_URL = "date in URL"
SRC_NSE = "NSE filing name"
SRC_MONTH = "month in path"
SRC_LASTMOD = "Last-Modified"

# ---------------------------------------------------------------------------
# Dates
# ---------------------------------------------------------------------------

_MONTH_NAMES = ("january", "february", "march", "april", "may", "june", "july",
                "august", "september", "october", "november", "december")
_MONTHS = {**{m: i for i, m in enumerate(_MONTH_NAMES, 1)},
           **{m[:3]: i for i, m in enumerate(_MONTH_NAMES, 1)}, "sept": 9}
_ISO = re.compile(r"(?<!\d)(20\d\d)[-/.](\d{1,2})[-/.](\d{1,2})(?!\d)")
_COMPACT = re.compile(r"^\s*(20\d\d)(\d\d)(\d\d)(?!\d)")
_DAY_MONTH = re.compile(r"(?<!\d)(\d{1,2})(?:st|nd|rd|th)?\s+([A-Za-z]{3,9})\.?,?\s+(20\d\d)(?!\d)")
_MONTH_DAY = re.compile(r"\b([A-Za-z]{3,9})\.?\s+(\d{1,2})(?:st|nd|rd|th)?,?\s+(20\d\d)(?!\d)")

_URL_DATE = re.compile(r"(?<!\d)(20\d\d)[/-]?(0[1-9]|1[0-2])[/-]?(0[1-9]|[12]\d|3[01])(?!\d)")
_NSE_NAME = re.compile(r"_(0[1-9]|[12]\d|3[01])(0[1-9]|1[0-2])(20\d\d)\d{6}_")
_URL_MONTH = re.compile(r"/(20\d\d)[/-](0[1-9]|1[0-2])/")

_META_TAG = re.compile(r"<meta\b[^>]*>", re.I)
_ATTR = re.compile(r"""([A-Za-z_:][-\w:.]*)\s*=\s*(?:"([^"]*)"|'([^']*)')""")
_LD_PUBLISHED = re.compile(r'"datePublished"\s*:\s*"([^"]{6,40})"')
# Metadata names, most specific first; a modified/updated date is never read.
_PUBLISHED_KEYS = (
    "article:published_time", "datepublished", "og:published_time",
    "publish-date", "publish_date", "publishdate", "pubdate", "parsely-pub-date",
    "sailthru.date", "dc.date.issued", "dcterms.created", "date",
)


def _mk(y: int, m: int, d: int) -> date | None:
    try:
        return date(y, m, d)
    except ValueError:
        return None


def parse_date_text(text: str | None) -> date | None:
    """The first calendar date in `text`: ISO (2026-11-09, 2026/11/09, with
    or without a time), compact (20261109), "9 Nov 2026" or "Nov 09, 2026".
    None when there is none."""
    if not text:
        return None
    s = str(text)
    m = _COMPACT.search(s)
    if m:
        d = _mk(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        if d:
            return d
    found: list[tuple[int, date]] = []
    for m in _ISO.finditer(s):
        d = _mk(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        if d:
            found.append((m.start(), d))
            break
    for m in _DAY_MONTH.finditer(s):
        month = _MONTHS.get(m.group(2).lower())
        d = _mk(int(m.group(3)), month, int(m.group(1))) if month else None
        if d:
            found.append((m.start(), d))
            break
    for m in _MONTH_DAY.finditer(s):
        month = _MONTHS.get(m.group(1).lower())
        d = _mk(int(m.group(3)), month, int(m.group(2))) if month else None
        if d:
            found.append((m.start(), d))
            break
    return min(found)[1] if found else None


def date_from_html(html: str) -> date | None:
    """The page's own publish date from its metadata, or None. A published
    date wins over any other: `article:published_time` first, then JSON-LD
    and meta `datePublished`, then the older names."""
    metas: dict[str, str] = {}
    for tag in _META_TAG.findall(html):
        attrs: dict[str, str] = {}
        for name, dq, sq in _ATTR.findall(tag):
            attrs.setdefault(name.lower(), dq or sq)
        key = (attrs.get("property") or attrs.get("name") or attrs.get("itemprop") or "").strip().lower()
        if key and attrs.get("content") and key not in metas:
            metas[key] = attrs["content"]
    candidates: list[str | None] = [metas.get("article:published_time")]
    candidates += _LD_PUBLISHED.findall(html)
    candidates += [metas.get(k) for k in _PUBLISHED_KEYS[1:]]
    for value in candidates:
        d = parse_date_text(value)
        if d:
            return d
    return None


def date_for(url: str, page_date: date | None = None,
             last_modified: str | None = None) -> dict[str, str | None]:
    """{date, date_source, date_strength} in the card's order: the page's
    metadata, a date in the URL, an NSE filing name (strong); a month in the
    path, Last-Modified (weak); else none."""
    if page_date:
        return {"date": page_date.isoformat(), "date_source": SRC_META, "date_strength": STRONG}
    m = _URL_DATE.search(url or "")
    if m:
        d = _mk(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        if d:
            return {"date": d.isoformat(), "date_source": SRC_URL, "date_strength": STRONG}
    m = _NSE_NAME.search(url or "")
    if m:
        d = _mk(int(m.group(3)), int(m.group(2)), int(m.group(1)))
        if d:
            return {"date": d.isoformat(), "date_source": SRC_NSE, "date_strength": STRONG}
    m = _URL_MONTH.search(url or "")
    if m:
        return {"date": f"{m.group(1)}-{m.group(2)}", "date_source": SRC_MONTH, "date_strength": WEAK}
    if last_modified:
        try:
            d = parsedate_to_datetime(last_modified).date()
        except (TypeError, ValueError, IndexError):
            d = None
        if d:
            return {"date": d.isoformat(), "date_source": SRC_LASTMOD, "date_strength": WEAK}
    return {"date": None, "date_source": None, "date_strength": None}


class PageRefused(Exception):
    """The address is not one this server reads: not http(s), or not public."""


def _check_public(url: str) -> None:
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https") or not parts.hostname:
        raise PageRefused("not an http(s) address")
    port = parts.port or (443 if parts.scheme == "https" else 80)
    for info in socket.getaddrinfo(parts.hostname, port, proto=socket.IPPROTO_TCP):
        ip = ipaddress.ip_address(str(info[4][0]).split("%")[0])
        if not ip.is_global:
            raise PageRefused("not a public address")


def _get_page(url: str, timeout: float) -> tuple[int, dict[str, str], bytes]:
    """One plain GET: (status, lower-cased headers, the first PAGE_MAX_BYTES).
    Redirects are followed by hand, each hop checked to be a public address."""
    for _ in range(MAX_REDIRECTS + 1):
        _check_public(url)
        resp = requests.get(url, headers=_UA, timeout=timeout, stream=True, allow_redirects=False)
        try:
            location = resp.headers.get("Location")
            if resp.is_redirect and location:
                url = urljoin(url, location)
                continue
            body = resp.raw.read(PAGE_MAX_BYTES, decode_content=True) or b""
            return resp.status_code, {k.lower(): v for k, v in resp.headers.items()}, body
        finally:
            resp.close()
    raise PageRefused("too many redirects")


PageGetter = Callable[[str, float], "tuple[int, dict[str, str], bytes]"]


def read_page_date(url: str, *, get: PageGetter | None = None,
                   timeout: float | None = None) -> dict[str, str | None]:
    """One result's date: {date, date_source, date_strength, fetch}. Never
    raises. `fetch` says what the request did: html, pdf, "http 403",
    timeout, refused, or error:<Type>."""
    get = get or _get_page
    timeout = float(timeout if timeout is not None else settings.SEARCH_SHADOW_PAGE_TIMEOUT_SECONDS)
    page: date | None = None
    last_modified: str | None = None
    try:
        status, headers, body = get(url, timeout)
        headers = {str(k).lower(): v for k, v in (headers or {}).items()}
        body = body or b""
        if status >= 400:
            fetch = f"http {status}"
        elif body[:5] == b"%PDF-":
            fetch = "pdf"
            last_modified = headers.get("last-modified")
        else:
            fetch = "html"
            page = date_from_html(body.decode("utf-8", "ignore"))
            last_modified = headers.get("last-modified")
    except PageRefused as exc:
        fetch = f"refused: {exc}"
    except requests.Timeout:
        fetch = "timeout"
    except Exception as exc:
        logger.debug("[search_shadow] page read failed for %s: %s", url, exc)
        fetch = f"error:{type(exc).__name__}"
    return {**date_for(url, page, last_modified), "fetch": fetch}


# ---------------------------------------------------------------------------
# A search engine through OpenRouter
# ---------------------------------------------------------------------------

def _api_key() -> str:
    key = getattr(settings, "OPENROUTER_API_KEY", "") or ""
    return "" if key == _PLACEHOLDER_KEY else key


def engine_label(params: dict) -> str:
    """The engine's name in rows and the budget: "parallel-fast" for
    {engine: parallel, mode: fast}, "exa" for {engine: exa}."""
    return "-".join(str(params[k]) for k in ("engine", "mode") if params.get(k))


def search_web(query: str, *, engine: dict, n: int, api_key: str, model: str,
               post: Callable[..., Any] | None = None) -> dict[str, Any]:
    """One search through OpenRouter's server tool with the engine's
    parameters (e.g. {engine: parallel, mode: fast}). Returns {engine,
    params, status: ok|empty|failed, reason, model, cost_usd, seconds,
    results: [{url, title, excerpt}]}. Never raises; the key goes only into
    the request's header."""
    post = post or requests.post
    body = {
        "model": model,
        "messages": [{"role": "user", "content": (
            "Run exactly one web search with this query, word for word, and do not "
            f"search again: {query}\nThen reply with the single word DONE.")}],
        "tools": [{"type": "openrouter:web_search",
                   "parameters": {**engine, "max_results": n}}],
        "max_tokens": 300,
        "usage": {"include": True},
        "reasoning": {"enabled": False},
    }
    out: dict[str, Any] = {"engine": engine_label(engine), "params": dict(engine),
                           "status": "failed", "reason": None, "model": model,
                           "cost_usd": None, "seconds": None, "results": []}
    t0 = time.monotonic()
    try:
        resp = post(f"{settings.OPENROUTER_BASE_URL}/chat/completions", json=body,
                    headers={"Authorization": f"Bearer {api_key}"}, timeout=SEARCH_TIMEOUT_SECONDS)
        out["seconds"] = round(time.monotonic() - t0, 2)
        try:
            data = resp.json()
        except ValueError:
            data = {}
        if resp.status_code != 200:
            message = ((data.get("error") or {}).get("message") if isinstance(data, dict) else None) or ""
            out["reason"] = f"HTTP {resp.status_code} {message}".strip()[:200]
            return out
        usage = data.get("usage") or {}
        out["cost_usd"] = usage.get("cost")
        message = ((data.get("choices") or [{}])[0] or {}).get("message") or {}
        seen: set[str] = set()
        for ann in message.get("annotations") or []:
            cite = ann.get("url_citation") if isinstance(ann, dict) and ann.get("type") == "url_citation" else None
            url = (cite or {}).get("url") or ""
            if not url or url in seen:
                continue
            seen.add(url)
            out["results"].append({"url": url, "title": cite.get("title") or "",
                                   "excerpt": (cite.get("content") or "")[:EXCERPT_MAX_CHARS]})
            if len(out["results"]) >= n:
                break
        out["status"] = "ok" if out["results"] else "empty"
        out["reason"] = None if out["results"] else "no results came back"
    except requests.Timeout:
        out["seconds"] = round(time.monotonic() - t0, 2)
        out["reason"] = "timeout"
    except Exception as exc:
        out["seconds"] = round(time.monotonic() - t0, 2)
        out["reason"] = f"{type(exc).__name__}: {exc}"[:200]
        logger.warning("[search_shadow] %s call failed: %s", out["engine"], out["reason"])
    return out


# ---------------------------------------------------------------------------
# Budget and the row file
# ---------------------------------------------------------------------------

_lock = threading.Lock()


def week_start(now: datetime) -> date:
    """The Saturday (IST) that opens `now`'s budget week."""
    d = now.astimezone(IST).date()
    return d - timedelta(days=(d.weekday() - 5) % 7)


@contextmanager
def _locked(directory: Path):
    """The in-process lock, and across the server's workers a file lock."""
    directory.mkdir(parents=True, exist_ok=True)
    with _lock:
        if fcntl is None:  # pragma: no cover - Windows
            yield
            return
        with open(directory / "search_shadow.lock", "a") as fh:
            fcntl.flock(fh, fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(fh, fcntl.LOCK_UN)


def reserve_call(now: datetime, limit: int, engine: str,
                 path: Path | None = None) -> tuple[bool, dict[str, Any]]:
    """Take one call from `engine`'s budget for this week: (allowed,
    {week_start, used, limit}). The counts live in
    `search_shadow_budget.json`: {"week": <Saturday>, "calls": {engine: n}}."""
    path = Path(path or BUDGET_FILE)
    week = week_start(now).isoformat()
    with _locked(path.parent):
        state: dict[str, Any] = {}
        if path.exists():
            try:
                state = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError) as exc:
                logger.warning("[search_shadow] budget file unreadable, counting afresh: %s", exc)
                state = {}
        if state.get("week") != week or not isinstance(state.get("calls"), dict):
            state = {"week": week, "calls": {}}
        used = state["calls"].get(engine)
        used = used if isinstance(used, int) else 0
        if used >= limit:
            return False, {"week_start": week, "used": used, "limit": limit}
        state["calls"][engine] = used + 1
        tmp = path.with_name(path.name + ".tmp")
        tmp.write_text(json.dumps(state), encoding="utf-8")
        os.replace(tmp, path)
        return True, {"week_start": week, "used": used + 1, "limit": limit}


def _append_row(row: dict[str, Any], path: Path | None = None) -> None:
    path = Path(path or SHADOW_LOG)
    line = json.dumps(row, ensure_ascii=False) + "\n"
    with _locked(path.parent):
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(line)


def _serper_rows(results: list[dict] | None) -> list[dict[str, Any]]:
    rows = []
    for r in results or []:
        row = {"title": r.get("title") or "",
               "link": r.get("link") or r.get("url") or "",
               "date": r.get("date") or r.get("publishedAt") or "",
               "snippet": (r.get("snippet") or r.get("description") or "")[:SNIPPET_MAX_CHARS]}
        if r.get("redirect"):
            row["redirect"] = True
        rows.append(row)
    return rows


# ---------------------------------------------------------------------------
# One decision's row
# ---------------------------------------------------------------------------

def configured_engines() -> list[dict]:
    """The engines in `search_shadow.engines`, each a dict with `engine`."""
    engines = getattr(settings, "SEARCH_SHADOW_ENGINES", None) or []
    return [dict(e) for e in engines if isinstance(e, dict) and e.get("engine")]


def record_shadow(*, run_id: str, ticker: str, sector: str, company_search: dict,
                  section_status: str | None = None, now: datetime | None = None,
                  engines: list[dict] | None = None,
                  search: Callable[..., dict] | None = None,
                  page_date: Callable[[str], dict] | None = None,
                  log_path: Path | None = None, budget_path: Path | None = None) -> dict[str, Any]:
    """Send the company search's query to each engine within its budget,
    date each result from its page, and append the row. Returns the row."""
    now = now or datetime.now(IST)
    query = company_search.get("query") or ""
    limit = int(settings.SEARCH_SHADOW_WEEKLY_BUDGET)
    n = int(settings.SEARCH_SHADOW_MAX_RESULTS)
    row: dict[str, Any] = {
        "v": ROW_VERSION,
        "time": now.astimezone(IST).isoformat(timespec="seconds"),
        "run_id": run_id, "ticker": ticker, "sector": sector, "query": query,
        "serper": {"status": section_status, "source": company_search.get("source"),
                   "results": _serper_rows(company_search.get("results"))},
        "engines": [],
    }
    for params in (configured_engines() if engines is None else engines):
        label = engine_label(params)
        allowed, budget = reserve_call(now, limit, label, budget_path)
        if not allowed:
            entry = {"engine": label, "params": dict(params), "status": "budget",
                     "reason": f"the weekly budget of {limit} calls is spent", "results": []}
        else:
            entry = (search or search_web)(query, engine=params, n=n, api_key=_api_key(),
                                           model=settings.SEARCH_SHADOW_MODEL)
        entry["budget"] = budget
        row["engines"].append(entry)

    urls = list(dict.fromkeys(item["url"] for e in row["engines"] for item in e.get("results") or []))
    reader = page_date or read_page_date
    with ThreadPoolExecutor(max_workers=PAGE_WORKERS, thread_name_prefix="search-shadow-page") as pool:
        dated = dict(zip(urls, pool.map(reader, urls)))
    for entry in row["engines"]:
        for item in entry.get("results") or []:
            item.update(dated.get(item["url"]) or {})
            excerpt_day = parse_date_text(item.get("excerpt"))
            item["excerpt_date"] = excerpt_day.isoformat() if excerpt_day else None
    _append_row(row, log_path)
    return row


def _job(kwargs: dict[str, Any]) -> None:
    try:
        record_shadow(**kwargs)
    except Exception as exc:
        logger.warning("[search_shadow] %s: row not completed: %s", kwargs.get("ticker"), exc)
        try:
            _append_row({
                "v": ROW_VERSION,
                "time": kwargs["now"].isoformat(timespec="seconds"),
                "run_id": kwargs.get("run_id"), "ticker": kwargs.get("ticker"),
                "sector": kwargs.get("sector"),
                "query": (kwargs.get("company_search") or {}).get("query"),
                "status": "failed", "reason": f"{type(exc).__name__}: {exc}"[:200],
                "engines": [],
            })
        except Exception as exc2:
            logger.warning("[search_shadow] failure row not written: %s", exc2)


class _Worker:
    """One daemon thread and a bounded queue. Unlike a ThreadPoolExecutor,
    whose queued jobs the interpreter waits for at exit, a redeploy never
    waits on the shadow: a row still queued then is lost, and nothing else."""

    def __init__(self, maxsize: int = QUEUE_MAX) -> None:
        self._queue: queue.Queue = queue.Queue(maxsize=maxsize)
        threading.Thread(target=self._loop, name="search-shadow", daemon=True).start()

    def submit(self, fn: Callable[..., None], *args: Any) -> None:
        self._queue.put_nowait((fn, args))   # queue.Full when the queue is full

    def _loop(self) -> None:
        while True:
            fn, args = self._queue.get()
            try:
                fn(*args)
            except Exception as exc:  # _job already never raises; this keeps the thread alive
                logger.warning("[search_shadow] job failed: %s", exc)


_worker: _Worker | None = None
_worker_lock = threading.Lock()


def _get_executor() -> _Worker:
    global _worker
    with _worker_lock:
        if _worker is None:
            _worker = _Worker()
        return _worker


def submit_shadow(*, run_id: str, ticker: str, sector: str, company_search: dict | None,
                  section_status: str | None = None) -> bool:
    """Queue one decision's shadow row and return at once. False (and
    nothing queued) when the switch is off, no engine is configured, no
    OpenRouter key is set, or the company search never ran. Never raises."""
    try:
        if not settings.SEARCH_SHADOW_ENABLED or not configured_engines():
            return False
        if not _api_key():
            logger.debug("[search_shadow] no OpenRouter key; %s not recorded", ticker)
            return False
        if not company_search or not company_search.get("query"):
            return False
        kwargs = {"run_id": run_id, "ticker": ticker, "sector": sector,
                  "company_search": json.loads(json.dumps(company_search, default=str)),
                  "section_status": section_status, "now": datetime.now(IST)}
        _get_executor().submit(_job, kwargs)
        return True
    except Exception as exc:
        logger.warning("[search_shadow] %s: not queued: %s", ticker, exc)
        return False

"""
PR-043: a second search beside Serper, recorded and not read.

The date reader on fixed pages and URLs (each strong and weak source, a
refusal, a time-out, two dates on one page), the address guard, the engine
call through OpenRouter, each engine's weekly budget, the row, and the
analysis path: the prompt is byte-identical with the shadow on and off, and
the shadow is queued only after the analyst has returned. No network: every
page, search and DNS answer is a fixture.
"""
from __future__ import annotations

import json
import queue
import threading
from datetime import date, datetime
from unittest.mock import MagicMock, patch

import pytest
import requests

from core.schemas.pipeline import AgentOutput, StockQuery
from services.data.context import bundle_builder as bb
from services.data.context import fetch_result as fr
from services.data.fetchers import news
from services.data.fetchers import search_shadow as ss

IST = ss.IST
KEY = "sk-or-v1-TESTKEY-never-written"
SENTINEL = "PAGE-BODY-SENTINEL-not-an-excerpt"
NSE_PDF = "https://nsearchives.nseindia.com/corporate/SAREGAMA_04112026184512_Outcome.pdf"


def _page(*, status=200, headers=None, body=b""):
    def get(url, timeout):
        return status, dict(headers or {}), body
    return get


def _html(head: str) -> bytes:
    return f"<html><head>{head}</head><body><p>{SENTINEL}</p></body></html>".encode()


# ---------------------------------------------------------------------------
# Dates: strong sources, weak sources, and the order between them
# ---------------------------------------------------------------------------

class TestDates:
    def test_page_metadata_is_strong(self):
        get = _page(body=_html('<meta property="article:published_time" content="2026-11-09T10:15:00+05:30">'))
        d = ss.read_page_date("https://www.example.com/markets/saregama-results", get=get)
        assert d == {"date": "2026-11-09", "date_source": "page metadata",
                     "date_strength": "strong", "fetch": "html"}

    def test_json_ld_date_published_is_strong(self):
        get = _page(body=_html('<script type="application/ld+json">{"@type":"NewsArticle",'
                               '"dateModified":"2026-11-18T09:00:00Z","datePublished":"2026-11-02T08:00:00Z"}'
                               '</script>'))
        d = ss.read_page_date("https://www.example.com/a", get=get)
        assert (d["date"], d["date_source"], d["date_strength"]) == ("2026-11-02", "page metadata", "strong")

    def test_two_dates_on_one_page_the_published_one_wins(self):
        """The modified date comes first in the page and is later; the
        published date is the one recorded."""
        head = ('<meta property="article:modified_time" content="2026-11-18T09:00:00+05:30">'
                '<meta name="date" content="2026-11-18">'
                '<meta content="2026-11-03T07:00:00+05:30" property="article:published_time">')
        d = ss.read_page_date("https://www.example.com/a", get=_page(body=_html(head)))
        assert d["date"] == "2026-11-03"

    def test_metadata_wins_over_a_date_in_the_url(self):
        get = _page(body=_html('<meta itemprop="datePublished" content="2026-11-12">'))
        d = ss.read_page_date("https://www.example.com/2026/10/01/story", get=get)
        assert (d["date"], d["date_source"]) == ("2026-11-12", "page metadata")

    def test_a_date_in_the_url_is_strong(self):
        d = ss.read_page_date("https://www.example.com/news/2026/11/09/coforge-clsa",
                              get=_page(body=_html("")))
        assert (d["date"], d["date_source"], d["date_strength"]) == ("2026-11-09", "date in URL", "strong")

    def test_an_nse_filing_name_is_strong(self):
        get = _page(headers={"Last-Modified": "Wed, 18 Nov 2026 10:00:00 GMT"}, body=b"%PDF-1.7 ...")
        d = ss.read_page_date(NSE_PDF, get=get)
        assert d == {"date": "2026-11-04", "date_source": "NSE filing name",
                     "date_strength": "strong", "fetch": "pdf"}

    def test_a_long_number_in_the_url_is_not_a_date(self):
        d = ss.read_page_date("https://www.example.com/article/1202611093", get=_page(body=_html("")))
        assert d["date"] is None

    def test_a_month_in_the_path_is_weak_and_month_only(self):
        d = ss.read_page_date("https://www.example.com/2026/11/tanla-q2.html", get=_page(body=_html("")))
        assert (d["date"], d["date_source"], d["date_strength"]) == ("2026-11", "month in path", "weak")

    def test_last_modified_is_weak(self):
        get = _page(headers={"Last-Modified": "Wed, 18 Nov 2026 10:00:00 GMT"}, body=_html(""))
        d = ss.read_page_date("https://www.example.com/investors", get=get)
        assert (d["date"], d["date_source"], d["date_strength"]) == ("2026-11-18", "Last-Modified", "weak")

    def test_a_refusal_leaves_the_page_unread(self):
        """A 403 page's metadata and Last-Modified are not read; with no date
        in its URL the result is undated."""
        get = _page(status=403, headers={"Last-Modified": "Wed, 18 Nov 2026 10:00:00 GMT"},
                    body=_html('<meta property="article:published_time" content="2026-11-09">'))
        d = ss.read_page_date("https://www.example.com/quote/SSWL", get=get)
        assert d == {"date": None, "date_source": None, "date_strength": None, "fetch": "http 403"}

    def test_a_refusal_keeps_a_date_in_the_url(self):
        d = ss.read_page_date("https://www.example.com/2026/11/09/x", get=_page(status=403))
        assert (d["date"], d["fetch"]) == ("2026-11-09", "http 403")

    def test_a_time_out_leaves_the_result_undated(self):
        def get(url, timeout):
            raise requests.Timeout("read timed out")
        d = ss.read_page_date("https://www.example.com/slow", get=get)
        assert d == {"date": None, "date_source": None, "date_strength": None, "fetch": "timeout"}

    def test_any_other_failure_is_recorded_not_raised(self):
        def get(url, timeout):
            raise ConnectionError("reset")
        d = ss.read_page_date("https://www.example.com/x", get=get)
        assert d["date"] is None and d["fetch"] == "error:ConnectionError"

    @pytest.mark.parametrize("text, expected", [
        ("Last Updated: Nov 09, 2026, 10:12 IST", date(2026, 11, 9)),
        ("Board meeting held on 4th November 2026 approved", date(2026, 11, 4)),
        ("Sept 30, 2026 quarter", date(2026, 9, 30)),
        ("2026/11/18 press release", date(2026, 11, 18)),
        ("20261105", date(2026, 11, 5)),
        ("on 12 Oct 2026 and later on Nov 3, 2026", date(2026, 10, 12)),
        ("Mayor 5 2026 Decision 4, 2026", None),
        ("2026-02-30", None),
        ("", None),
    ])
    def test_parse_date_text(self, text, expected):
        assert ss.parse_date_text(text) == expected


# ---------------------------------------------------------------------------
# Only public http(s) pages are read
# ---------------------------------------------------------------------------

class TestAddressGuard:
    @pytest.fixture
    def dns(self, monkeypatch):
        table = {"news.example.com": "93.184.216.34", "intranet.example.com": "10.0.0.5",
                 "metadata.example.com": "169.254.169.254"}

        def getaddrinfo(host, port, *a, **k):
            return [(2, 1, 6, "", (table[host], port))]
        monkeypatch.setattr(ss.socket, "getaddrinfo", getaddrinfo)
        return table

    @pytest.mark.parametrize("url", ["http://intranet.example.com/admin",
                                     "http://metadata.example.com/latest/meta-data",
                                     "file:///etc/passwd", "ftp://news.example.com/x"])
    def test_a_private_or_odd_address_is_never_requested(self, dns, monkeypatch, url):
        monkeypatch.setattr(ss.requests, "get", MagicMock(side_effect=AssertionError("requested")))
        d = ss.read_page_date(url)
        assert d["date"] is None and d["fetch"].startswith("refused: ")

    def test_a_redirect_to_a_private_address_is_refused(self, dns, monkeypatch):
        hop = MagicMock(is_redirect=True, headers={"Location": "http://intranet.example.com/x"})
        get = MagicMock(return_value=hop)
        monkeypatch.setattr(ss.requests, "get", get)
        d = ss.read_page_date("https://news.example.com/story")
        assert d["fetch"] == "refused: not a public address"
        assert get.call_count == 1 and get.call_args.kwargs["allow_redirects"] is False

    def test_a_public_page_is_read_up_to_its_cap(self, dns, monkeypatch):
        resp = MagicMock(is_redirect=False, status_code=200, headers={"Content-Type": "text/html"})
        resp.raw.read.return_value = _html('<meta property="article:published_time" content="2026-11-09">')
        monkeypatch.setattr(ss.requests, "get", MagicMock(return_value=resp))
        d = ss.read_page_date("https://news.example.com/story")
        assert d["date"] == "2026-11-09"
        resp.raw.read.assert_called_once_with(ss.PAGE_MAX_BYTES, decode_content=True)
        resp.close.assert_called_once()


# ---------------------------------------------------------------------------
# One engine call through OpenRouter
# ---------------------------------------------------------------------------

def _openrouter(annotations, *, status=200, cost=0.0019):
    resp = MagicMock(status_code=status)
    resp.json.return_value = {
        "choices": [{"message": {"content": "DONE", "annotations": annotations}}],
        "usage": {"cost": cost, "prompt_tokens": 5300},
    }
    return resp


def _cite(url, title="t", content="c", uncited=False):
    return {"type": "url_citation",
            "url_citation": {"url": url, "title": title, "content": content, "uncited": uncited}}


class TestSearchWeb:
    def test_every_result_cited_or_not_with_its_excerpt(self):
        post = MagicMock(return_value=_openrouter(
            [_cite("https://a.example/1", "A", "x" * 5000), _cite("https://a.example/2", uncited=True),
             _cite("https://a.example/1"), {"type": "other"}]))
        out = ss.search_web("Coforge COFORGE news", engine={"engine": "parallel", "mode": "fast"},
                            n=10, api_key=KEY, model="m", post=post)
        assert out["engine"] == "parallel-fast" and out["status"] == "ok" and out["cost_usd"] == 0.0019
        assert [r["url"] for r in out["results"]] == ["https://a.example/1", "https://a.example/2"]
        assert len(out["results"][0]["excerpt"]) == ss.EXCERPT_MAX_CHARS
        sent = post.call_args.kwargs
        assert sent["json"]["tools"] == [{"type": "openrouter:web_search",
                                          "parameters": {"engine": "parallel", "mode": "fast",
                                                         "max_results": 10}}]
        assert "Coforge COFORGE news" in sent["json"]["messages"][0]["content"]
        assert KEY not in json.dumps(sent["json"]) and sent["headers"]["Authorization"] == f"Bearer {KEY}"

    def test_results_are_capped_at_n(self):
        post = MagicMock(return_value=_openrouter([_cite(f"https://a.example/{i}") for i in range(12)]))
        out = ss.search_web("q", engine={"engine": "exa"}, n=10, api_key=KEY, model="m", post=post)
        assert len(out["results"]) == 10 and out["engine"] == "exa"

    def test_an_http_error_is_a_reason_not_a_raise(self):
        resp = MagicMock(status_code=402)
        resp.json.return_value = {"error": {"message": "Insufficient credits"}}
        out = ss.search_web("q", engine={"engine": "exa"}, n=10, api_key=KEY, model="m",
                            post=MagicMock(return_value=resp))
        assert out["status"] == "failed" and out["reason"] == "HTTP 402 Insufficient credits"

    def test_a_time_out_is_a_reason_not_a_raise(self):
        out = ss.search_web("q", engine={"engine": "exa"}, n=10, api_key=KEY, model="m",
                            post=MagicMock(side_effect=requests.Timeout("slow")))
        assert out["status"] == "failed" and out["reason"] == "timeout"

    def test_no_results_is_empty(self):
        out = ss.search_web("q", engine={"engine": "exa"}, n=10, api_key=KEY, model="m",
                            post=MagicMock(return_value=_openrouter([])))
        assert out["status"] == "empty" and out["results"] == []


# ---------------------------------------------------------------------------
# The weekly budget, per engine, Saturday 00:00 IST to Friday
# ---------------------------------------------------------------------------

class TestBudget:
    def test_the_week_opens_on_saturday_ist(self):
        fri = datetime(2026, 11, 20, 23, 59, tzinfo=IST)
        sat = datetime(2026, 11, 21, 0, 0, tzinfo=IST)
        assert ss.week_start(fri) == date(2026, 11, 14)
        assert ss.week_start(sat) == date(2026, 11, 21)
        # 18:40 UTC on Friday is already Saturday in India.
        assert ss.week_start(datetime.fromisoformat("2026-11-20T18:40:00+00:00")) == date(2026, 11, 21)

    def test_the_budget_stops_calls_and_reopens_next_week(self, tmp_path):
        path = tmp_path / "budget.json"
        now = datetime(2026, 11, 23, 16, 30, tzinfo=IST)
        for i in range(3):
            assert ss.reserve_call(now, 3, "exa", path) == (
                True, {"week_start": "2026-11-21", "used": i + 1, "limit": 3})
        assert ss.reserve_call(now, 3, "exa", path) == (
            False, {"week_start": "2026-11-21", "used": 3, "limit": 3})
        assert ss.reserve_call(now, 3, "parallel-fast", path)[0] is True   # its own budget
        later = datetime(2026, 11, 28, 12, 30, tzinfo=IST)
        assert ss.reserve_call(later, 3, "exa", path) == (
            True, {"week_start": "2026-11-28", "used": 1, "limit": 3})

    def test_an_unreadable_budget_file_counts_afresh(self, tmp_path):
        path = tmp_path / "budget.json"
        path.write_text("{not json")
        assert ss.reserve_call(datetime(2026, 11, 23, tzinfo=IST), 2, "exa", path)[1]["used"] == 1


# ---------------------------------------------------------------------------
# The row
# ---------------------------------------------------------------------------

SERPER = [{"title": f"S{i}", "snippet": f"snip {i}", "link": f"https://s.example/{i}",
           "date": "2 days ago"} for i in range(5)]
COMPANY_SEARCH = {"query": "Coforge COFORGE latest news results November 2026",
                  "source": "serper", "results": SERPER}
NOW = datetime(2026, 11, 21, 12, 40, tzinfo=IST)


def _fake_search(results_by_engine):
    calls = []

    def search(query, *, engine, n, api_key, model):
        label = ss.engine_label(engine)
        calls.append((label, query, n, api_key))
        return {"engine": label, "params": dict(engine), "status": "ok", "reason": None,
                "model": model, "cost_usd": 0.002, "seconds": 2.1,
                "results": [dict(r) for r in results_by_engine[label]]}
    search.calls = calls
    return search


@pytest.fixture
def keyed(monkeypatch):
    monkeypatch.setattr(ss.settings, "OPENROUTER_API_KEY", KEY)
    monkeypatch.setattr(ss.settings, "SEARCH_SHADOW_ENABLED", True)
    monkeypatch.setattr(ss.settings, "SEARCH_SHADOW_ENGINES",
                        [{"engine": "parallel", "mode": "fast"}, {"engine": "exa"}])
    monkeypatch.setattr(ss.settings, "SEARCH_SHADOW_WEEKLY_BUDGET", 200)
    monkeypatch.setattr(ss.settings, "SEARCH_SHADOW_MAX_RESULTS", 10)


class TestRow:
    def _record(self, tmp_path, search, page_date, **kw):
        return ss.record_shadow(run_id="ab12cd34", ticker="COFORGE", sector="it_sector",
                                company_search=COMPANY_SEARCH, section_status="ok", now=NOW,
                                search=search, page_date=page_date, log_path=tmp_path / "rows.jsonl",
                                budget_path=tmp_path / "budget.json", **kw)

    def test_one_row_with_serpers_five_and_each_engines_dated_results(self, tmp_path, keyed):
        shared = "https://www.example.com/news/2026/11/18/coforge-clsa"
        search = _fake_search({
            "parallel-fast": [{"url": shared, "title": "CLSA keeps Outperform", "excerpt": "..."},
                              {"url": NSE_PDF, "title": "Outcome", "excerpt": "Last Updated: Nov 04, 2026"}],
            "exa": [{"url": shared, "title": "CLSA", "excerpt": "Nov 18, 2026 CLSA"}],
        })
        read = MagicMock(side_effect=lambda url: {**ss.date_for(url), "fetch": "html"})
        row = self._record(tmp_path, search, read)

        lines = (tmp_path / "rows.jsonl").read_text().splitlines()
        assert len(lines) == 1 and json.loads(lines[0]) == row
        assert (row["v"], row["time"], row["run_id"], row["ticker"]) == (
            1, "2026-11-21T12:40:00+05:30", "ab12cd34", "COFORGE")
        assert row["serper"]["results"] == [
            {"title": r["title"], "link": r["link"], "date": r["date"], "snippet": r["snippet"]}
            for r in SERPER]
        assert [e["engine"] for e in row["engines"]] == ["parallel-fast", "exa"]
        assert [c[0] for c in search.calls] == ["parallel-fast", "exa"]
        assert all(c[1] == COMPANY_SEARCH["query"] and c[2] == 10 for c in search.calls)
        pf, exa = row["engines"]
        assert pf["results"][0] | {} == {
            "url": shared, "title": "CLSA keeps Outperform", "excerpt": "...", "date": "2026-11-18",
            "date_source": "date in URL", "date_strength": "strong", "fetch": "html", "excerpt_date": None}
        assert (pf["results"][1]["date_source"], pf["results"][1]["excerpt_date"]) == (
            "NSE filing name", "2026-11-04")
        assert exa["results"][0]["excerpt_date"] == "2026-11-18"
        assert pf["budget"] == exa["budget"] == {"week_start": "2026-11-21", "used": 1, "limit": 200}
        # A link both engines returned is read once.
        assert sorted(c.args[0] for c in read.call_args_list) == sorted([shared, NSE_PDF])

    def test_an_excerpt_date_is_beside_never_the_date(self, tmp_path, keyed):
        search = _fake_search({"parallel-fast": [{"url": "https://co.example/investors", "title": "t",
                                                  "excerpt": "Published 9 November 2026"}], "exa": []})
        row = self._record(tmp_path, search, lambda url: {**ss.date_for(url), "fetch": "http 403"})
        item = row["engines"][0]["results"][0]
        assert (item["date"], item["date_strength"], item["excerpt_date"]) == (None, None, "2026-11-09")

    def test_the_budget_stops_an_engine_and_not_the_other(self, tmp_path, keyed, monkeypatch):
        monkeypatch.setattr(ss.settings, "SEARCH_SHADOW_WEEKLY_BUDGET", 1)
        (tmp_path / "budget.json").write_text(json.dumps({"week": "2026-11-21", "calls": {"exa": 1}}))
        search = _fake_search({"parallel-fast": [], "exa": []})
        row = self._record(tmp_path, search, lambda url: {})
        assert [c[0] for c in search.calls] == ["parallel-fast"]
        assert row["engines"][1] == {
            "engine": "exa", "params": {"engine": "exa"}, "status": "budget",
            "reason": "the weekly budget of 1 calls is spent", "results": [],
            "budget": {"week_start": "2026-11-21", "used": 1, "limit": 1}}

    def test_a_failed_engine_writes_its_reason_and_raises_nothing(self, tmp_path, keyed):
        resp = MagicMock(status_code=503)
        resp.json.side_effect = ValueError("not json")
        with patch.object(ss.requests, "post", return_value=resp):
            row = self._record(tmp_path, None, lambda url: {})
        assert [(e["engine"], e["status"], e["reason"]) for e in row["engines"]] == [
            ("parallel-fast", "failed", "HTTP 503"), ("exa", "failed", "HTTP 503")]
        assert (tmp_path / "rows.jsonl").exists()

    def test_no_key_and_no_page_text_is_written(self, tmp_path, keyed):
        """The real engine call and the real page reader, on fixtures: the
        row holds the excerpts, never the key or the page body."""
        post = MagicMock(return_value=_openrouter([_cite("https://www.example.com/a", "A", "excerpt")]))
        page = _page(body=_html('<meta property="article:published_time" content="2026-11-10">'))
        with patch.object(ss.requests, "post", post):
            self._record(tmp_path, None, lambda url: ss.read_page_date(url, get=page))
        text = (tmp_path / "rows.jsonl").read_text()
        assert KEY not in text and SENTINEL not in text
        assert '"excerpt": "excerpt"' in text and '"date": "2026-11-10"' in text


# ---------------------------------------------------------------------------
# Queueing
# ---------------------------------------------------------------------------

class _SyncExecutor:
    def __init__(self):
        self.jobs = []

    def submit(self, fn, *args):
        self.jobs.append((fn, args))


class TestSubmit:
    def test_the_switch_off_queues_nothing(self, keyed, monkeypatch):
        monkeypatch.setattr(ss.settings, "SEARCH_SHADOW_ENABLED", False)
        ex = _SyncExecutor()
        monkeypatch.setattr(ss, "_get_executor", lambda: ex)
        assert ss.submit_shadow(run_id="r", ticker="T", sector="s", company_search=COMPANY_SEARCH) is False
        assert ex.jobs == []

    @pytest.mark.parametrize("change", ["no_key", "no_engines", "no_query"])
    def test_nothing_to_record_queues_nothing(self, keyed, monkeypatch, change):
        search = dict(COMPANY_SEARCH)
        if change == "no_key":
            monkeypatch.setattr(ss.settings, "OPENROUTER_API_KEY", "your-openrouter-api-key-here")
        elif change == "no_engines":
            monkeypatch.setattr(ss.settings, "SEARCH_SHADOW_ENGINES", [])
        else:
            search = {}
        ex = _SyncExecutor()
        monkeypatch.setattr(ss, "_get_executor", lambda: ex)
        assert ss.submit_shadow(run_id="r", ticker="T", sector="s", company_search=search) is False
        assert ex.jobs == []

    def test_on_queues_one_job_and_returns_at_once(self, keyed, monkeypatch):
        ex = _SyncExecutor()
        monkeypatch.setattr(ss, "_get_executor", lambda: ex)
        assert ss.submit_shadow(run_id="r1", ticker="COFORGE", sector="it_sector",
                                company_search=COMPANY_SEARCH, section_status="ok") is True
        (fn, (kwargs,)), = ex.jobs
        assert fn is ss._job and kwargs["company_search"] == COMPANY_SEARCH
        assert kwargs["company_search"] is not COMPANY_SEARCH   # a copy, not the bundle's dict

    def test_the_worker_is_a_daemon_and_outlives_a_failing_job(self):
        worker = ss._Worker(maxsize=5)
        done = threading.Event()

        def boom():
            raise RuntimeError("x")
        worker.submit(boom)
        worker.submit(done.set)
        assert done.wait(5)
        threads = [t for t in threading.enumerate() if t.name == "search-shadow"]
        assert threads and all(t.daemon for t in threads)

    def test_a_full_queue_drops_the_row_and_raises_nothing(self, keyed, monkeypatch):
        class Full:
            def submit(self, fn, *args):
                raise queue.Full
        monkeypatch.setattr(ss, "_get_executor", lambda: Full())
        assert ss.submit_shadow(run_id="r", ticker="T", sector="s", company_search=COMPANY_SEARCH) is False

    def test_a_job_that_raises_writes_a_failure_row(self, keyed, monkeypatch, tmp_path):
        monkeypatch.setattr(ss, "SHADOW_LOG", tmp_path / "rows.jsonl")
        monkeypatch.setattr(ss, "record_shadow", MagicMock(side_effect=OSError("disk full")))
        ss._job({"run_id": "r1", "ticker": "COFORGE", "sector": "it_sector",
                 "company_search": COMPANY_SEARCH, "now": NOW})
        row = json.loads((tmp_path / "rows.jsonl").read_text())
        assert (row["status"], row["reason"], row["engines"]) == ("failed", "OSError: disk full", [])


# ---------------------------------------------------------------------------
# The analysis path: the bundle keeps the search, the prompt does not change
# ---------------------------------------------------------------------------

_STUBBED = ("_fetch_sector_policy_news", "_fetch_macro_context", "_fetch_policy_deep_dive",
            "_fetch_fundamentals", "_fetch_technicals", "_fetch_commodities",
            "_fetch_flows_sentiment", "_fetch_peers_valuation", "_fetch_dossier")


@pytest.fixture
def serper(monkeypatch):
    monkeypatch.setattr(news, "search_serper", MagicMock(return_value=[dict(r) for r in SERPER]))
    monkeypatch.setattr(bb.settings, "get_serper_key", lambda sector: "serper-key")


def _bundle():
    stubs = {n: (lambda *a, **k: fr.FetchResult("x", fr.STATUS_OK, "fixture")) for n in _STUBBED}
    with patch.multiple(bb, **stubs):
        return bb.build_sector_bundle(StockQuery(ticker="COFORGE", company_name="Coforge Ltd"), "it_sector")


class TestBundle:
    def test_the_bundle_keeps_the_query_and_serpers_five(self, serper):
        bundle = _bundle()
        assert bundle.company_search["query"].startswith("Coforge Ltd COFORGE latest news ")
        assert bundle.company_search["source"] == "serper"
        assert [r["link"] for r in bundle.company_search["results"]] == [r["link"] for r in SERPER]
        assert "company_search" not in bundle.to_prompt_text()

    def test_the_section_text_is_the_same_with_and_without_the_capture(self, serper):
        q = StockQuery(ticker="COFORGE", company_name="Coforge Ltd")
        with_capture = bb._fetch_company_news(q, "it_sector", "k", {})
        without = bb._fetch_company_news(q, "it_sector", "k")
        assert with_capture == without


class _Orchestrator:
    """The real BaseSectorOrchestrator._run_unified on a minimal subclass."""

    @staticmethod
    def make():
        from backend.shared.pipeline.base_orchestrator import BaseSectorOrchestrator

        class _IT(BaseSectorOrchestrator):
            SECTOR_NAME = "it_sector"

        with patch("backend.shared.pipeline.base_orchestrator.get_llm_client", return_value=MagicMock()):
            orch = _IT()
        orch._aggregator = MagicMock()
        return orch


class TestAnalysisPath:
    def _run(self, monkeypatch, *, enabled, llm_reply='{"fundamentals": {"score": 0.6}}'):
        from backend.shared.pipeline import unified_analyst as ua

        events: list = []
        prompts: list = []

        def call_llm(self, system_prompt, user_prompt):
            events.append("llm")
            prompts.append((system_prompt, user_prompt))
            return llm_reply

        ex = _SyncExecutor()
        ex_submit = ex.submit

        def submit(fn, *args):
            events.append("shadow")
            ex_submit(fn, *args)
        ex.submit = submit
        monkeypatch.setattr(ss, "_get_executor", lambda: ex)
        monkeypatch.setattr(ss.settings, "SEARCH_SHADOW_ENABLED", enabled)
        monkeypatch.setattr(ua, "get_llm_client", lambda: MagicMock())
        monkeypatch.setattr(ua.UnifiedAnalyst, "_call_llm", call_llm)
        bundle = _bundle()
        with patch("services.data.context.bundle_builder.build_sector_bundle", return_value=bundle):
            outputs = _Orchestrator.make()._run_unified(
                StockQuery(ticker="COFORGE", company_name="Coforge Ltd"), run_id="ab12cd34")
        return outputs, prompts, events, ex.jobs

    def test_the_prompt_is_byte_identical_with_the_shadow_on_and_off(self, keyed, serper, monkeypatch):
        out_on, prompts_on, events_on, jobs_on = self._run(monkeypatch, enabled=True)
        out_off, prompts_off, events_off, jobs_off = self._run(monkeypatch, enabled=False)
        assert len(prompts_on) == len(prompts_off) == 1
        assert prompts_on[0][1].encode() == prompts_off[0][1].encode()
        assert prompts_on[0][0].encode() == prompts_off[0][0].encode()
        assert out_on.keys() == out_off.keys() and out_on
        assert events_on == ["llm", "shadow"] and events_off == ["llm"]
        (_, (kwargs,)), = jobs_on
        assert (kwargs["run_id"], kwargs["ticker"], kwargs["sector"], kwargs["section_status"]) == (
            "ab12cd34", "COFORGE", "it_sector", "ok")
        assert kwargs["company_search"]["results"][0]["link"] == SERPER[0]["link"]
        assert jobs_off == []

    def test_a_failed_analysis_is_no_decision_and_queues_nothing(self, keyed, serper, monkeypatch):
        outputs, _, events, jobs = self._run(monkeypatch, enabled=True, llm_reply="not json at all")
        assert outputs == {} and events == ["llm"] and jobs == []

    def test_a_shadow_that_raises_leaves_the_run_alone(self, keyed, serper, monkeypatch):
        monkeypatch.setattr(ss, "submit_shadow", MagicMock(side_effect=RuntimeError("boom")))
        outputs, prompts, _, _ = self._run(monkeypatch, enabled=True)
        assert outputs and len(prompts) == 1
        assert all(isinstance(o, AgentOutput) for o in outputs.values())

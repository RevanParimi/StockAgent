"""IPO-4a — the deep-dive sweep and its scheduler job. Fully offline.

The research layer is a `search` double that serves the recorded VARMORA
dossier (tests/fixtures/ipo_research/, captured 2026-09-21) and the LLM is
the replay client from test_ipo_extract, which RAISES on any prompt outside
the recording. Every store is rooted in tmp_path; nothing here can reach
`data/` or the network.

What is protected here: the two slots fire at exactly their boundaries; the
cap cuts in the documented order; the T-1 run writes one row carrying both
readings and spends no more than the research budget; the post-close re-read
writes the evidenced row from cache without a single network or model call;
and nothing in the sweep can raise into the scheduler.
"""
import json
from datetime import date
from pathlib import Path

import pytest

from core.ipo import deep_dive as mod
from core.ipo.deep_dive import Candidate, analyse, candidates, run_deep_dive_sweep
from core.ipo.research import QUERY_KINDS, ResearchDossier, _cache_path
from core.ipo.signals import IpoSignalSnapshot, IpoSignalStore
from core.ipo.verdicts import IpoVerdictStore
from tests.unit.ipo.test_ipo_extract import ReplayClient

FIX = Path("tests/fixtures/ipo_research")
ON = date(2026, 9, 23)                      # VARMORA closes 2026-09-24: T-1


@pytest.fixture(autouse=True)
def _no_telemetry(monkeypatch):
    import services.clients.llm_client as llm
    monkeypatch.setattr(llm, "record_llm_call", lambda *a, **k: None)
    monkeypatch.setattr(llm, "get_llm_client",
                        lambda: (_ for _ in ()).throw(AssertionError("real client")))


def _row(symbol="VARMORA", start="2026-09-22", end="2026-09-24", **extra):
    # The VARMORA company name must match the recorded dossier's, or the query
    # plan would not reproduce the fixture's queries.
    rec = {"symbol": symbol, "company": "Varmora Granito Limited" if symbol == "VARMORA" else f"{symbol} Ltd",
           "issue_start": start, "issue_end": end, "issue_price": 100.0}
    rec.update(extra)
    return rec


def _cache(*rows, bucket="current"):
    return {"fetched_at": "", "degraded": False, "current": [], "upcoming": [], "past": [],
            bucket: list(rows)}


def _dossier(name="VARMORA_2026-09-24") -> ResearchDossier:
    return ResearchDossier.model_validate(json.loads((FIX / f"{name}.json").read_text(encoding="utf-8")))


class FixtureSearch:
    """Serves the recorded dossier's documents back through the search hook,
    keyed by query text, and counts the calls so a test can prove the budget."""
    def __init__(self, dossier: ResearchDossier, fail=False):
        self.calls = 0
        self.fail = fail
        by_query = {q: [] for q in dossier.queries}
        kinds = [k for k, _ in QUERY_KINDS]
        for doc in dossier.docs:
            q = dossier.queries[kinds.index(doc.kind)]
            by_query[q].append({"url": doc.url, "title": doc.title, "content": doc.content,
                                "published_date": doc.published_date, "score": doc.score})
        self.by_query = by_query

    def __call__(self, query, max_results=3):
        self.calls += 1
        if self.fail:
            return []
        return list(self.by_query.get(query, []))


def _snap(symbol="VARMORA", captured_at="2026-09-23T12:15:00+00:00", state="open", **combined):
    return IpoSignalSnapshot(symbol=symbol, captured_at=captured_at, state=state,
                             issue_start="2026-09-22", issue_end="2026-09-24",
                             combined=combined or {"qib": 40.0, "total": 30.0, "retail": 9.0,
                                                   "nii": 20.0, "mutual_fund": 5.0},
                             cutoff_share=0.3)


@pytest.fixture
def stores(tmp_path):
    return {"research_dir": str(tmp_path / "research"), "signals_dir": str(tmp_path / "signals"),
            "verdicts_dir": str(tmp_path / "verdicts")}


def _seed_ledger(stores, *snaps):
    store = IpoSignalStore(base_dir=stores["signals_dir"])
    for s in snaps:
        store.append(s)
    return store


# ─────────────────────────── slot selection ───────────────────────────────

@pytest.mark.parametrize("on,slot", [
    (date(2026, 9, 23), "t_minus_1"),        # closes tomorrow
    (date(2026, 9, 25), "post_close"),       # closed yesterday, not listed
    (date(2026, 9, 27), "post_close"),       # still closed three days on
])
def test_the_two_slots_fire_on_their_dates(on, slot):
    picked, skipped = candidates(_cache(_row()), on)
    assert [c.slot for c in picked] == [slot]
    assert skipped == {}


@pytest.mark.parametrize("on,reason", [
    (date(2026, 9, 22), "open"),             # T-2: open but not tomorrow's close
    (date(2026, 9, 24), "open"),             # T-0: the close day itself is never re-read
    (date(2026, 9, 21), "upcoming"),
])
def test_an_open_issue_fires_only_at_t_minus_1(on, reason):
    picked, skipped = candidates(_cache(_row()), on)
    assert picked == [] and skipped == {reason: 1}


def test_a_listed_issue_is_never_touched():
    picked, skipped = candidates(_cache(_row(listing_date="2026-09-26")), date(2026, 9, 26))
    assert picked == [] and skipped == {"listed": 1}


def test_a_row_with_no_close_date_is_skipped_with_its_reason():
    picked, skipped = candidates(_cache(_row(end="")), ON)
    assert picked == [] and skipped == {"no_close_date": 1}


def test_the_lead_days_setting_moves_the_t_minus_1_slot(monkeypatch):
    from core.config import settings as s
    monkeypatch.setattr(s, "IPO_DEEP_DIVE_LEAD_DAYS", 2, raising=True)
    assert [c.slot for c in candidates(_cache(_row()), date(2026, 9, 22))[0]] == ["t_minus_1"]
    assert candidates(_cache(_row()), date(2026, 9, 23))[0] == []


def test_one_row_per_symbol_and_the_current_bucket_wins():
    """A closed issue can sit in `current` AND `past` while NSE moves it; the
    current row is the one the refresh enriched."""
    cache = _cache(_row(issue_size_cr=500.0))
    cache["past"] = [_row(issue_size_cr=None)]
    picked, _ = candidates(cache, date(2026, 9, 25))
    assert len(picked) == 1 and picked[0].row["issue_size_cr"] == 500.0


def test_the_cap_order_is_t_minus_1_first_then_size_then_symbol():
    cache = _cache(
        _row("SMALLC", start="2026-09-18", end="2026-09-22", issue_size_cr=100),
        _row("BIGC", start="2026-09-18", end="2026-09-22", issue_size_cr=900),
        _row("ZZT1", start="2026-09-22", end="2026-09-24", issue_size_cr=50),
        _row("AAT1", start="2026-09-22", end="2026-09-24", issue_size_cr=50),
        _row("NOSIZE", start="2026-09-18", end="2026-09-22"),
    )
    picked, _ = candidates(cache, ON)
    assert [c.symbol for c in picked] == ["AAT1", "ZZT1", "BIGC", "SMALLC", "NOSIZE"]


def test_the_close_date_is_the_key_so_an_extension_re_fires():
    picked, _ = candidates(_cache(_row(end="2026-09-26")), date(2026, 9, 25))
    assert picked[0].slot == "t_minus_1" and picked[0].close_date == "2026-09-26"


# ─────────────────────────── the T-1 run ──────────────────────────────────

def test_a_t_minus_1_run_writes_one_row_with_both_readings(stores):
    _seed_ledger(stores, _snap())
    search, client = FixtureSearch(_dossier()), ReplayClient("VARMORA")
    cand = Candidate(symbol="VARMORA", close_date="2026-09-24", slot="t_minus_1", state="open",
                     row=_row())
    res = analyse(cand, ON, research_dir=stores["research_dir"],
                  signal_store=IpoSignalStore(base_dir=stores["signals_dir"]),
                  verdict_store=IpoVerdictStore(base_dir=stores["verdicts_dir"]),
                  search=search, client=client)
    assert res.error == "" and res.written is True and res.unread is False
    assert res.docs == 14 and res.docs_extracted > 0 and client.hits == res.docs
    assert search.calls <= 6                                   # the research budget
    assert res.hype.demand is not None                         # the book was read
    assert res.substance.features["pat_growth"] is not None    # the research was read
    assert res.verdict.short.lean is not None
    assert res.verdict.short.evidenced is False                # T-1: interim book
    assert res.verdict.state == "open"

    rows = IpoVerdictStore(base_dir=stores["verdicts_dir"]).load_all()
    assert len(rows) == 1 and rows[0].key == ("VARMORA", "2026-09-24")
    assert rows[0].hype.features["qib_x"] == 40.0
    assert rows[0].substance.features["pat_growth"] == res.substance.features["pat_growth"]


def test_the_sweep_selects_analyses_and_writes_from_the_cache_file(stores, tmp_path):
    _seed_ledger(stores, _snap())
    cache_path = tmp_path / "ipo.json"
    cache_path.write_text(json.dumps(_cache(_row())), encoding="utf-8")
    search, client = FixtureSearch(_dossier()), ReplayClient("VARMORA")
    result = run_deep_dive_sweep(ON, cache_path=str(cache_path), search=search, client=client, **stores)
    assert (result["candidates"], result["analysed"], result["written"], result["errors"]) == (1, 1, 1, 0)
    issue = result["issues"][0]
    assert issue["slot"] == "t_minus_1" and issue["evidenced"] is False and issue["lean"]
    assert issue["research_cache_hit"] is False and issue["extraction_cache_hit"] is False


# ─────────────────────────── the post-close re-read ───────────────────────

def test_the_post_close_re_read_costs_nothing_and_writes_the_evidenced_row(stores, tmp_path):
    _seed_ledger(stores, _snap())
    cache_path = tmp_path / "ipo.json"
    cache_path.write_text(json.dumps(_cache(_row())), encoding="utf-8")
    search, client = FixtureSearch(_dossier()), ReplayClient("VARMORA")
    run_deep_dive_sweep(ON, cache_path=str(cache_path), search=search, client=client, **stores)
    t1_calls, t1_hits = search.calls, client.hits
    assert t1_calls > 0 and t1_hits > 0

    # Two evenings later: closed, not listed. The book did not move (the
    # capture ledger dedups an identical re-read), only the calendar did.
    second = run_deep_dive_sweep(date(2026, 9, 25), cache_path=str(cache_path),
                                 search=search, client=client, **stores)
    assert search.calls == t1_calls and client.hits == t1_hits        # zero network, zero model
    issue = second["issues"][0]
    assert issue["slot"] == "post_close" and issue["state"] == "closed"
    assert issue["research_cache_hit"] is True and issue["extraction_cache_hit"] is True
    assert issue["evidenced"] is True and issue["written"] is True

    rows = IpoVerdictStore(base_dir=stores["verdicts_dir"]).load_key("VARMORA", "2026-09-24")
    assert [r.verdict.short.evidenced for r in rows] == [False, True]
    assert rows[0].verdict.short.lean == rows[1].verdict.short.lean    # same book, same lean
    assert rows[0].substance.index == rows[1].substance.index          # same research

    # A third evening with nothing new is the store's dedup, not a third row.
    third = run_deep_dive_sweep(date(2026, 9, 26), cache_path=str(cache_path),
                                search=search, client=client, **stores)
    assert third["deduped"] == 1 and third["written"] == 0
    assert len(IpoVerdictStore(base_dir=stores["verdicts_dir"]).load_all()) == 2


# ─────────────────────────── the extraction cache ─────────────────────────

def test_the_extraction_cache_is_keyed_to_the_dossier_it_read(stores):
    dossier = _dossier()
    rdir = Path(stores["research_dir"])
    out, hit = mod._substance_for(dossier, rdir, client=ReplayClient("VARMORA"))
    assert hit is False and out.docs_extracted > 0
    again, hit = mod._substance_for(dossier, rdir, client=None)     # None would blow up if called
    assert hit is True and again.model_dump() == out.model_dump()

    refetched = dossier.model_copy(update={"fetched_at": "2026-09-25T13:30:00+00:00"})
    fresh, hit = mod._substance_for(refetched, rdir, client=ReplayClient("VARMORA"))
    assert hit is False and fresh.docs_extracted > 0


def test_a_dead_model_caches_nothing(stores):
    class Dead:
        class chat:
            class completions:
                @staticmethod
                def create(**kw):
                    raise RuntimeError("model down")
    dossier = _dossier()
    rdir = Path(stores["research_dir"])
    out, hit = mod._substance_for(dossier, rdir, client=Dead())
    assert hit is False and out.docs_extracted == 0
    assert not mod._substance_cache_path(rdir, "VARMORA", "2026-09-24").exists()


def test_an_unreadable_extraction_cache_is_a_miss_not_a_crash(stores):
    dossier = _dossier()
    rdir = Path(stores["research_dir"])
    path = mod._substance_cache_path(rdir, "VARMORA", "2026-09-24")
    path.parent.mkdir(parents=True)
    path.write_text("{not json", encoding="utf-8")
    out, hit = mod._substance_for(dossier, rdir, client=ReplayClient("VARMORA"))
    assert hit is False and out.docs_extracted > 0


def test_the_cache_is_beside_the_dossier_and_never_collides_with_it(stores):
    rdir = Path(stores["research_dir"])
    assert mod._substance_cache_path(rdir, "VARMORA", "2026-09-24").name == "VARMORA_2026-09-24.substance.json"
    assert _cache_path(rdir, "VARMORA", "2026-09-24").name == "VARMORA_2026-09-24.json"


# ─────────────────────────── degradation ──────────────────────────────────

def test_a_dead_research_layer_still_writes_a_hype_only_verdict(stores):
    """The T-1 lean rests on `demand` alone; substance dark is the state the
    verdict was designed to record, not a reason to write nothing."""
    _seed_ledger(stores, _snap())
    cand = Candidate(symbol="VARMORA", close_date="2026-09-24", slot="t_minus_1", state="open", row=_row())
    res = analyse(cand, ON, research_dir=stores["research_dir"],
                  signal_store=IpoSignalStore(base_dir=stores["signals_dir"]),
                  verdict_store=IpoVerdictStore(base_dir=stores["verdicts_dir"]),
                  search=FixtureSearch(_dossier(), fail=True), client=object())
    assert res.error == "" and res.written is True
    assert res.research_degraded is True and res.docs == 0
    assert res.verdict.demand is not None and res.verdict.short.lean is not None
    assert res.verdict.substance is None
    assert "substance.pat_growth" in res.verdict.dark


def test_an_issue_with_nothing_readable_is_not_stored(stores):
    """No ledger snapshot and no research: the row would assert a reading
    that was never taken (the capture ledger's rule)."""
    cand = Candidate(symbol="VARMORA", close_date="2026-09-24", slot="t_minus_1", state="open", row=_row())
    res = analyse(cand, ON, research_dir=stores["research_dir"],
                  signal_store=IpoSignalStore(base_dir=stores["signals_dir"]),
                  verdict_store=IpoVerdictStore(base_dir=stores["verdicts_dir"]),
                  search=FixtureSearch(_dossier(), fail=True), client=object())
    assert res.unread is True and res.written is False and res.error == ""
    assert not IpoVerdictStore(base_dir=stores["verdicts_dir"]).path.exists() or \
        IpoVerdictStore(base_dir=stores["verdicts_dir"]).load_all() == []


def test_the_cap_counts_attempts_and_names_what_it_dropped(stores, tmp_path):
    cache_path = tmp_path / "ipo.json"
    cache_path.write_text(json.dumps(_cache(
        _row("AAA", start="2026-09-22", end="2026-09-24"),
        _row("BBB", start="2026-09-18", end="2026-09-22"),
        _row("CCC", start="2026-09-18", end="2026-09-22"),
    )), encoding="utf-8")
    result = run_deep_dive_sweep(ON, cache_path=str(cache_path), max_issues=1,
                                 search=lambda q, max_results=3: [], client=object(), **stores)
    assert result["candidates"] == 3 and result["analysed"] == 1
    assert result["over_cap"] == ["BBB", "CCC"]           # the T-1 issue kept its slot


def test_the_cap_comes_from_config(stores, tmp_path, monkeypatch):
    from core.config import settings as s
    monkeypatch.setattr(s, "IPO_DEEP_DIVE_MAX_ISSUES", 0, raising=True)
    cache_path = tmp_path / "ipo.json"
    cache_path.write_text(json.dumps(_cache(_row())), encoding="utf-8")
    result = run_deep_dive_sweep(ON, cache_path=str(cache_path),
                                 search=lambda q, max_results=3: [], client=object(), **stores)
    assert result["analysed"] == 0 and result["over_cap"] == ["VARMORA"]


def test_the_kill_switch_stops_the_sweep_before_the_cache_read(stores, monkeypatch):
    from core.config import settings as s
    monkeypatch.setattr(s, "IPO_DEEP_DIVE_ENABLED", False, raising=True)
    result = run_deep_dive_sweep(ON, cache_path="does-not-exist.json", **stores)
    assert result["enabled"] is False and result["analysed"] == 0


def test_the_sweep_never_raises(stores, monkeypatch):
    monkeypatch.setattr("services.data.fetchers.ipo.load_ipo_cache",
                        lambda cache_path=None: (_ for _ in ()).throw(RuntimeError("disk gone")))
    result = run_deep_dive_sweep(ON, **stores)
    assert result["errors"] == 1 and "disk gone" in result["error"]


def test_a_failing_stage_is_one_issue_error_not_a_sweep_failure(stores, tmp_path, monkeypatch):
    _seed_ledger(stores, _snap())
    cache_path = tmp_path / "ipo.json"
    cache_path.write_text(json.dumps(_cache(_row())), encoding="utf-8")
    monkeypatch.setattr(mod, "read_hype", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))
    result = run_deep_dive_sweep(ON, cache_path=str(cache_path),
                                 search=lambda q, max_results=3: [], client=object(), **stores)
    assert result["analysed"] == 1 and result["errors"] == 1 and result["written"] == 0
    assert "boom" in result["issues"][0]["error"]


def test_the_sweep_prunes_the_verdict_store_on_retention(stores, tmp_path, monkeypatch):
    from datetime import datetime, timedelta, timezone
    from core.ipo.verdict import IpoVerdict
    store = IpoVerdictStore(base_dir=stores["verdicts_dir"])
    old = (datetime.now(timezone.utc) - timedelta(days=2000)).isoformat()
    store.append(IpoVerdict(symbol="OLD", close_date="2021-01-01", demand=50.0), written_at=old)
    cache_path = tmp_path / "ipo.json"
    cache_path.write_text(json.dumps(_cache()), encoding="utf-8")
    result = run_deep_dive_sweep(ON, cache_path=str(cache_path), **stores)
    assert result["pruned"] == 1 and store.load_all() == []


# ─────────────────────────── the scheduler job ────────────────────────────

def test_ipo_deep_dive_is_registered_at_1900_ist():
    from services.scheduler.python.scheduler import AutomobileScheduler
    job = AutomobileScheduler()._scheduler.get_job("ipo_deep_dive")
    assert job is not None
    fields = {f.name: str(f) for f in job.trigger.fields}
    assert fields["hour"] == "19" and fields["minute"] == "0"
    assert fields["day_of_week"] == "*"                       # daily: close dates fall on any day


def test_ipo_deep_dive_lands_after_the_live_refresh():
    from core.config import settings as s
    refresh = s.IPO_REFRESH_HOUR_LIVE * 60 + s.IPO_REFRESH_MINUTE_LIVE
    dive = s.IPO_DEEP_DIVE_HOUR * 60 + s.IPO_DEEP_DIVE_MINUTE
    assert dive > refresh


def test_ipo_deep_dive_hour_comes_from_the_settings_constant(monkeypatch):
    from core.config import settings as s
    from services.scheduler.python.scheduler import AutomobileScheduler
    monkeypatch.setattr(s, "IPO_DEEP_DIVE_HOUR", 20, raising=True)
    monkeypatch.setattr(s, "IPO_DEEP_DIVE_MINUTE", 15, raising=True)
    fields = {f.name: str(f) for f in
              AutomobileScheduler()._scheduler.get_job("ipo_deep_dive").trigger.fields}
    assert fields["hour"] == "20" and fields["minute"] == "15"


def test_ipo_deep_dive_absent_when_ipo_disabled(monkeypatch):
    from services.scheduler.python.scheduler import AutomobileScheduler
    monkeypatch.setattr("services.scheduler.python.scheduler.cfg",
                        lambda key, fallback=None: False if key == "ipo.enabled" else fallback)
    assert AutomobileScheduler()._scheduler.get_job("ipo_deep_dive") is None


def test_the_job_handler_logs_and_records_without_raising(monkeypatch):
    from services.scheduler.python import scheduler as sched_mod
    recorded = {}
    monkeypatch.setattr("core.ipo.deep_dive.run_deep_dive_sweep",
                        lambda: {"on": "2026-09-23", "enabled": True, "candidates": 1, "analysed": 1,
                                 "written": 1, "deduped": 0, "unread": 0, "errors": 0,
                                 "over_cap": [], "skipped": {}, "pruned": 0, "issues": []})
    monkeypatch.setattr("services.data.stores.job_outcomes.record_job_outcome",
                        lambda job, **f: recorded.update({job: f}))
    sched_mod.AutomobileScheduler()._ipo_deep_dive_job()
    assert recorded["ipo_deep_dive"]["written"] == 1

    monkeypatch.setattr("core.ipo.deep_dive.run_deep_dive_sweep",
                        lambda: (_ for _ in ()).throw(RuntimeError("boom")))
    sched_mod.AutomobileScheduler()._ipo_deep_dive_job()      # must not raise

"""IPO-2a — the browsing layer. Fully offline: `search` is always injected."""
import json

import pytest

from core.ipo import research as mod
from core.ipo.research import QUERY_KINDS, ResearchDossier, query_plan, research_issue


def _hit(url, content="some text", title="t", score=0.5):
    return {"url": url, "content": content, "title": title, "score": score, "published_date": ""}


# ─────────────────────────── query plan ───────────────────────────────────

def test_query_plan_strips_legal_suffix_and_caps():
    plan = query_plan("Varmora Granito Limited", "VARMORA", max_fetches=3)
    assert len(plan) == 3
    assert [k for k, _q in plan] == [k for k, _t in QUERY_KINDS[:3]]
    assert all("Varmora Granito IPO" in q and "Limited" not in q for _k, q in plan)


def test_query_plan_falls_back_to_symbol_when_no_company():
    assert query_plan("", "SONA", max_fetches=2)[0][1].startswith("SONA IPO")
    assert query_plan("", "", max_fetches=2) == []


def test_query_plan_zero_cap_means_no_queries():
    assert query_plan("Leap India Limited", "LEAP", max_fetches=0) == []


# ─────────────────────────── fetching ──────────────────────────────────────

def test_documents_are_deduped_by_url_across_queries(tmp_path):
    """The same RHP summary answering two questions is ONE document, so the
    query plan can never inflate a later corroboration count."""
    calls = []

    def search(q, max_results=3):
        calls.append(q)
        return [_hit("https://www.a.com/rhp"), _hit("https://b.in/page")]

    d = research_issue("T", "Test Co Limited", "2026-09-24", base_dir=str(tmp_path),
                       search=search, max_fetches=4)
    assert d.fetches_used == 4 and len(calls) == 4
    assert [doc.url for doc in d.docs] == ["https://www.a.com/rhp", "https://b.in/page"]
    assert d.docs[0].domain == "a.com"          # www. stripped
    assert d.docs[0].kind == "financials"       # attributed to the FIRST query that found it
    assert d.degraded is False and d.cache_hit is False


def test_second_run_inside_the_window_costs_nothing(tmp_path):
    calls = []

    def search(q, max_results=3):
        calls.append(q)
        return [_hit("https://a.com/x")]

    research_issue("T", "Test Co", "2026-09-24", base_dir=str(tmp_path), search=search, max_fetches=2)
    again = research_issue("T", "Test Co", "2026-09-24", base_dir=str(tmp_path),
                           search=search, max_fetches=2)
    assert len(calls) == 2
    assert again.cache_hit is True and len(again.docs) == 1


def test_a_different_close_date_is_a_different_cache_key(tmp_path):
    """Close dates get extended; an extension must re-research, not replay."""
    calls = []

    def search(q, max_results=3):
        calls.append(q)
        return [_hit("https://a.com/x")]

    research_issue("T", "Test Co", "2026-09-24", base_dir=str(tmp_path), search=search, max_fetches=1)
    research_issue("T", "Test Co", "2026-09-26", base_dir=str(tmp_path), search=search, max_fetches=1)
    assert len(calls) == 2


def test_an_empty_result_is_never_cached(tmp_path):
    """A Tavily outage at 19:00 must not poison the whole window."""
    def down(q, max_results=3):
        return []

    d = research_issue("T", "Test Co", "2026-09-24", base_dir=str(tmp_path), search=down, max_fetches=3)
    assert d.docs == [] and d.degraded is True and d.fetches_used == 3
    assert list(tmp_path.glob("*.json")) == []

    def up(q, max_results=3):
        return [_hit("https://a.com/x")]

    d2 = research_issue("T", "Test Co", "2026-09-24", base_dir=str(tmp_path), search=up, max_fetches=3)
    assert len(d2.docs) == 1 and d2.cache_hit is False


def test_partial_failure_is_not_degraded(tmp_path):
    seen = []

    def flaky(q, max_results=3):
        seen.append(q)
        return [] if len(seen) % 2 else [_hit(f"https://a.com/{len(seen)}")]

    d = research_issue("T", "Test Co", "2026-09-24", base_dir=str(tmp_path), search=flaky, max_fetches=4)
    assert d.degraded is False and len(d.docs) == 2


def test_a_raising_search_never_raises_out(tmp_path):
    def boom(q, max_results=3):
        raise RuntimeError("tavily exploded")

    d = research_issue("T", "Test Co", "2026-09-24", base_dir=str(tmp_path), search=boom, max_fetches=2)
    assert d.docs == [] and d.degraded is True


def test_content_is_capped_and_empty_content_is_skipped(tmp_path, monkeypatch):
    from core.config import settings
    monkeypatch.setattr(settings, "IPO_RESEARCH_MAX_CONTENT_CHARS", 10, raising=False)

    def search(q, max_results=3):
        return [_hit("https://a.com/long", content="x" * 100), _hit("https://a.com/empty", content="  ")]

    d = research_issue("T", "Test Co", "2026-09-24", base_dir=str(tmp_path), search=search, max_fetches=1)
    assert [doc.url for doc in d.docs] == ["https://a.com/long"]
    assert len(d.docs[0].content) == 10


def test_disabled_flag_makes_no_call(tmp_path, monkeypatch):
    from core.config import settings
    monkeypatch.setattr(settings, "IPO_RESEARCH_ENABLED", False, raising=False)
    calls = []
    d = research_issue("T", "Test Co", "2026-09-24", base_dir=str(tmp_path),
                       search=lambda q, max_results=3: calls.append(q) or [_hit("https://a.com/x")])
    assert calls == [] and d.degraded is True and d.docs == []


def test_no_tavily_key_means_no_client_and_degraded(tmp_path, monkeypatch):
    from core.config import settings
    monkeypatch.setattr(settings, "TAVILY_API_KEY", "", raising=False)
    d = research_issue("T", "Test Co", "2026-09-24", base_dir=str(tmp_path))
    assert d.degraded is True and d.docs == [] and d.fetches_used == 0


def test_corrupt_cache_is_a_miss_not_a_crash(tmp_path):
    path = mod._cache_path(tmp_path, "T", "2026-09-24")
    path.write_text("{not json", encoding="utf-8")
    d = research_issue("T", "Test Co", "2026-09-24", base_dir=str(tmp_path),
                       search=lambda q, max_results=3: [_hit("https://a.com/x")], max_fetches=1)
    assert d.cache_hit is False and len(d.docs) == 1
    assert json.loads(path.read_text(encoding="utf-8"))["docs"]   # overwritten with a good one


def test_cache_key_is_filesystem_safe(tmp_path):
    p = mod._cache_path(tmp_path, "A/B:C", "2026-09-24")
    assert p.name == "A_B_C_2026-09-24.json"


# ─────────────────────────── real captured fixtures ───────────────────────

@pytest.mark.parametrize("name", ["NSE_2026-09-21", "VARMORA_2026-09-24", "LEAP_nodate"])
def test_captured_dossiers_load_and_carry_urls(name):
    from pathlib import Path
    data = json.loads(Path("tests/fixtures/ipo_research", f"{name}.json").read_text(encoding="utf-8"))
    d = ResearchDossier.model_validate(data)
    assert len(d.docs) >= 10 and len(d.domains) >= 10
    assert all(doc.url.startswith("http") and doc.content for doc in d.docs)
    assert len({doc.url for doc in d.docs}) == len(d.docs)      # deduped on capture

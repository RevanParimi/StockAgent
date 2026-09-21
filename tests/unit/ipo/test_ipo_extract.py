"""IPO-2b / IPO-2c — extraction and the corroboration gate.

Fully offline. The LLM is a replay client that answers from recorded fixtures
(tests/fixtures/ipo_research/*_extractions.json, captured 2026-09-21 against
the bulk model) and RAISES on any prompt it has not seen, so a test can never
silently reach the network.
"""
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from core.ipo import extract as mod
from core.ipo.extract import (
    DocExtraction, IpoSubstance, Sourced, coerce, corroborate, extract_document,
    extract_substance, normalise_fy,
)
from core.ipo.research import ResearchDoc, ResearchDossier

FIX = Path("tests/fixtures/ipo_research")
CAPS = {"max_peers": 5, "max_anchors": 8, "max_proceeds": 5, "max_flags": 6}


@pytest.fixture(autouse=True)
def _no_telemetry(monkeypatch):
    import services.clients.llm_client as llm
    monkeypatch.setattr(llm, "record_llm_call", lambda *a, **k: None)
    monkeypatch.setattr(llm, "get_llm_client", lambda: (_ for _ in ()).throw(AssertionError("real client")))


def _doc(url="https://www.a.com/x", kind="financials", content="text", title="t"):
    return ResearchDoc(kind=kind, url=url, domain=mod._domain(url), content=content, title=title)


class FakeClient:
    """Returns a scripted response; records the kwargs it was called with."""
    def __init__(self, content, finish_reason="stop", raise_exc=None):
        self.content, self.finish_reason, self.raise_exc = content, finish_reason, raise_exc
        self.calls = []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, **kw):
        self.calls.append(kw)
        if self.raise_exc:
            raise self.raise_exc
        choice = SimpleNamespace(message=SimpleNamespace(content=self.content),
                                 finish_reason=self.finish_reason)
        return SimpleNamespace(choices=[choice],
                               usage=SimpleNamespace(prompt_tokens=10, completion_tokens=5))


class ReplayClient:
    """Answers from a recorded fixture keyed the way the capture script keyed
    it: the first 200 chars of the document text in the user message."""
    def __init__(self, symbol):
        self.log = json.loads((FIX / f"{symbol}_extractions.json").read_text(encoding="utf-8"))
        self.hits = 0
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, **kw):
        user = kw["messages"][-1]["content"]
        key = user.split("Document text:", 1)[-1].strip()[:200]
        if key not in self.log:
            raise AssertionError("prompt not in fixture — a test tried to leave the recording")
        self.hits += 1
        rec = self.log[key]
        choice = SimpleNamespace(message=SimpleNamespace(content=rec["content"]),
                                 finish_reason=rec["finish_reason"])
        return SimpleNamespace(choices=[choice], usage=SimpleNamespace(
            prompt_tokens=rec["usage"]["prompt_tokens"], completion_tokens=rec["usage"]["completion_tokens"]))


def _dossier(name):
    return ResearchDossier.model_validate(json.loads((FIX / f"{name}.json").read_text(encoding="utf-8")))


# ─────────────────────────── parsing ──────────────────────────────────────

@pytest.mark.parametrize("label,expected", [
    ("FY25", "FY2025"), ("FY2025", "FY2025"), ("fy'24", "FY2024"), ("FY 2024-25", "FY2025"),
    ("2024-25", "FY2025"), ("2023-2024", "FY2024"), ("March 2025", "FY2025"),
    ("year ended 31 March 2026", "FY2026"), ("", None), (None, None), ("latest", None),
])
def test_normalise_fy(label, expected):
    assert normalise_fy(label) == expected


def test_coerce_stamps_url_domain_and_kind_from_the_document_not_the_model():
    doc = _doc("https://www.b.in/p", kind="promoter")
    e = coerce({"promoter": "Mr X", "source_url": "https://evil.example/forged"}, doc, CAPS)
    assert (e.url, e.domain, e.kind) == ("https://www.b.in/p", "b.in", "promoter")


def test_coerce_series_keeps_latest_three_oldest_first_and_drops_unlabelled():
    e = coerce({"revenue_cr": [
        {"as_of": "FY2022", "value": 1}, {"as_of": "FY23", "value": 2}, {"as_of": "2023-24", "value": 3},
        {"as_of": "FY2025", "value": 4}, {"as_of": "?", "value": 99}, {"as_of": "FY2025", "value": 5},
    ]}, _doc(), CAPS)
    assert e.revenue_cr == [("FY2023", 2.0), ("FY2024", 3.0), ("FY2025", 4.0)]


def test_coerce_never_rescues_strings_bools_or_nan_into_numbers():
    e = coerce({"issue_pe": "45.2", "ebitda_margin_pct": True,
                "pat_cr": [{"as_of": "FY25", "value": "1,234"}, {"as_of": "FY24", "value": float("nan")},
                           {"as_of": "FY23", "value": -12.5}]}, _doc(), CAPS)
    assert e.issue_pe is None and e.ebitda_margin_pct is None
    assert e.pat_cr == [("FY2023", -12.5)]       # a loss survives as a negative number


def test_coerce_reapplies_caps_and_dedups_case_insensitively():
    e = coerce({"anchor_names": [f"Fund {i}" for i in range(20)] + ["fund 0"],
                "peer_pe": [{"name": "Kajaria", "value": 50}, {"name": "KAJARIA", "value": 51}]
                          + [{"name": f"P{i}", "value": i} for i in range(20)]},
               _doc(), CAPS)
    assert len(e.anchor_names) == CAPS["max_anchors"]
    assert len(e.peer_pe) == CAPS["max_peers"] and e.peer_pe[0] == ("Kajaria", 50.0)


def test_coerce_of_garbage_is_empty_not_an_error():
    assert coerce({"revenue_cr": "nope", "peer_pe": [1, 2], "promoter": None}, _doc(), CAPS).is_empty()
    assert coerce(None, _doc(), CAPS).is_empty()     # type: ignore[arg-type]


def test_sourced_value_without_source_is_refused():
    with pytest.raises(ValueError):
        Sourced(value=1.0)
    assert Sourced().value is None                    # the empty form is fine


# ─────────────────────────── the gate ─────────────────────────────────────

def _ext(url, **fields):
    return DocExtraction(url=url, domain=mod._domain(url), **fields)


def test_two_agreeing_domains_keep_the_number_with_both_sources():
    s = corroborate([_ext("https://a.com/1", issue_pe=40.0), _ext("https://b.in/2", issue_pe=44.0)],
                    min_sources=2, tolerance=0.25, caps=CAPS)
    assert s.issue_pe.value == 42.0 and s.issue_pe.status == "corroborated"
    assert set(s.issue_pe.sources) == {"https://a.com/1", "https://b.in/2"}
    assert s.issue_pe.source_url in s.issue_pe.sources and s.dropped == []


def test_two_disagreeing_domains_yield_none_with_the_reason_recorded():
    s = corroborate([_ext("https://a.com/1", issue_pe=40.0), _ext("https://b.in/2", issue_pe=60.0)],
                    min_sources=2, tolerance=0.25, caps=CAPS)
    assert s.issue_pe.value is None and s.issue_pe.status is None
    assert s.dropped == ["issue_pe: sources disagree beyond 25% (a.com=40, b.in=60)"]


def test_same_domain_twice_is_one_source():
    """An aggregator echoed across two of its own pages is one source."""
    s = corroborate([_ext("https://a.com/1", issue_pe=40.0), _ext("https://www.a.com/2", issue_pe=40.0)],
                    min_sources=2, tolerance=0.25, caps=CAPS)
    assert s.issue_pe.value is None
    assert s.dropped == ["issue_pe: 1 source(s), need 2 — a.com said 40"]


def test_series_corroborate_per_fiscal_year():
    s = corroborate([
        _ext("https://a.com/1", revenue_cr=[("FY2023", 100.0), ("FY2024", 120.0), ("FY2025", 150.0)]),
        _ext("https://b.in/2", revenue_cr=[("FY2024", 121.0), ("FY2025", 149.0)]),
    ], min_sources=2, tolerance=0.25, caps=CAPS)
    assert [(r.as_of, r.value) for r in s.revenue_cr] == [("FY2024", 120.5), ("FY2025", 149.5)]
    assert s.dropped == ["revenue_cr[FY2023]: 1 source(s), need 2 — a.com said 100"]


def test_negative_pat_agrees_and_zero_versus_nonzero_never_does():
    s = corroborate([_ext("https://a.com/1", pat_cr=[("FY2025", -17.0)], issue_pe=0.0),
                     _ext("https://b.in/2", pat_cr=[("FY2025", -15.0)], issue_pe=30.0)],
                    min_sources=2, tolerance=0.25, caps=CAPS)
    assert s.pat_cr[0].value == -16.0
    assert s.issue_pe.value is None and "issue_pe: sources disagree" in s.dropped[0]


def test_two_exact_zeros_agree():
    assert mod._agree([0.0, 0.0], 0.25) is True


def test_min_sources_one_lets_a_single_domain_through():
    s = corroborate([_ext("https://a.com/1", issue_pe=40.0)], min_sources=1, tolerance=0.25, caps=CAPS)
    assert s.issue_pe.value == 40.0 and s.issue_pe.status == "corroborated"


def test_peers_are_keyed_by_name_case_insensitively_and_gated_each():
    s = corroborate([
        _ext("https://a.com/1", peer_pe=[("Kajaria Ceramics", 35.0), ("Somany", 25.0)]),
        _ext("https://b.in/2", peer_pe=[("kajaria ceramics", 36.0)]),
    ], min_sources=2, tolerance=0.25, caps=CAPS)
    assert [(p.label, p.value, p.status) for p in s.peer_pe] == [("Kajaria Ceramics", 35.5, "corroborated")]
    assert s.dropped == ["peer_pe[Somany]: 1 source(s), need 2 — a.com said 25"]


def test_reported_fields_need_one_source_prefer_the_matching_query_and_dedup():
    s = corroborate([
        _ext("https://fin.com/1", kind="financials", promoter="From the financials page",
             red_flags=["Litigation pending", "customer concentration"]),
        _ext("https://prom.com/2", kind="promoter", promoter="Named Promoter Ltd",
             anchor_names=["SBI MF"]),
        _ext("https://risk.com/3", kind="risks", red_flags=["LITIGATION PENDING", "Gas price exposure"]),
    ], min_sources=2, tolerance=0.25, caps=CAPS)
    assert s.promoter.value == "Named Promoter Ltd" and s.promoter.status == "reported"
    assert s.promoter.source_url == "https://prom.com/2"
    # risks page first, then the rest; case-insensitive dedup keeps the first spelling
    assert [f.value for f in s.red_flags] == ["LITIGATION PENDING", "Gas price exposure",
                                             "customer concentration"]
    assert s.red_flags[0].source_url == "https://risk.com/3"
    assert [a.value for a in s.anchor_names] == ["SBI MF"]
    assert all(f.status == "reported" for f in s.red_flags)


def test_reported_lists_respect_caps():
    s = corroborate([_ext("https://a.com/1", anchor_names=[f"F{i}" for i in range(8)]),
                     _ext("https://b.in/2", anchor_names=[f"G{i}" for i in range(8)])],
                    min_sources=2, tolerance=0.25, caps={**CAPS, "max_anchors": 3})
    assert len(s.anchor_names) == 3


def test_empty_input_yields_an_empty_substance_not_zeros():
    s = corroborate([], min_sources=2, tolerance=0.25, caps=CAPS)
    assert isinstance(s, IpoSubstance)
    assert s.revenue_cr == [] and s.pat_cr == [] and s.issue_pe.value is None
    assert s.ebitda_margin.value is None and s.docs_extracted == 0 and s.dropped == []


# ─────────────────────────── the LLM step ─────────────────────────────────

def test_extract_document_sends_json_mode_with_caps_in_the_prompt_and_fixed_max_tokens(monkeypatch):
    from core.config import settings
    monkeypatch.setattr(settings, "IPO_RESEARCH_EXTRACT_MAX_TOKENS", 777, raising=False)
    client = FakeClient(json.dumps({"issue_pe": 40}))
    e = extract_document(_doc(), "Test Co", "T", client=client, model="m", caps={**CAPS, "max_peers": 3})
    assert e.issue_pe == 40.0 and e.url == "https://www.a.com/x" and e.truncated is False
    kw = client.calls[0]
    assert kw["response_format"] == {"type": "json_object"} and kw["max_tokens"] == 777
    assert kw["extra_body"] == {"reasoning": {"enabled": False}} and kw["temperature"] == 0.0
    assert "3 entries" in kw["messages"][0]["content"]          # the caps travel in the prompt
    assert "Test Co (NSE symbol T)" in kw["messages"][1]["content"]
    assert "https://www.a.com/x" not in kw["messages"][1]["content"]   # the URL is never the model's to give


def test_truncated_response_degrades_to_partial_with_provenance_never_invented():
    raw = '{"revenue_cr": [{"as_of": "FY2025", "value": 100}], "pat_cr": [{"as_of": "FY2025", "val'
    client = FakeClient(raw, finish_reason="length")
    e = extract_document(_doc(), "Test Co", "T", client=client, model="m", caps=CAPS)
    assert e is not None and e.truncated is True
    assert e.revenue_cr == [("FY2025", 100.0)]       # what closed cleanly survives
    assert e.pat_cr == [] and e.issue_pe is None     # what was cut is absent, not zero


@pytest.mark.parametrize("raw,expected", [
    ('{"issue_pe": 40, "peer_pe": [{"name": "K", "value": 5', {"issue_pe": 40}),
    ('{"revenue_cr": [{"as_of": "FY25", "value": 1}], "promoter": "Mr', {"revenue_cr": [{"as_of": "FY25", "value": 1}]}),
    ('{"anchor_names": ["a", "b"], "red_flags": ["x"]', {"anchor_names": ["a", "b"], "red_flags": ["x"]}),
    ('{"promoter": "unterminated', {}),
    ('garbage', {}),
    ('', {}),
])
def test_salvage_partial_object_recovers_what_closed(raw, expected):
    assert mod.salvage_partial_object(raw) == expected


def test_malformed_json_that_cannot_be_salvaged_yields_an_empty_extraction():
    e = extract_document(_doc(), "Test Co", "T", client=FakeClient("not json at all"), model="m", caps=CAPS)
    assert e is not None and e.is_empty() and e.truncated is False


def test_client_failure_returns_none_and_never_raises():
    client = FakeClient("", raise_exc=RuntimeError("openrouter 502"))
    assert extract_document(_doc(), "Test Co", "T", client=client, model="m", caps=CAPS) is None


def test_extract_substance_skips_empty_documents_and_counts_reads():
    dossier = ResearchDossier(symbol="T", company="Test Co", docs=[
        _doc("https://a.com/1"), _doc("https://b.in/2"), _doc("https://c.org/3")])
    client = FakeClient(json.dumps({"issue_pe": 40}))
    s = extract_substance(dossier, client=client, model="m")
    assert s.docs_read == 3 and s.docs_extracted == 3 and len(client.calls) == 3
    assert s.issue_pe.value == 40.0 and len(s.issue_pe.sources) == 3


def test_extract_substance_over_an_empty_dossier_is_empty_and_makes_no_call():
    client = FakeClient("{}")
    s = extract_substance(ResearchDossier(symbol="T"), client=client, model="m")
    assert s.docs_read == 0 and client.calls == [] and s.issue_pe.value is None


# ─────────────────────────── replayed real captures ───────────────────────

def _assert_provenance(s: IpoSubstance, dossier: ResearchDossier):
    """Every value points at a document that was actually fetched."""
    urls = {d.url for d in dossier.docs}
    fields = [*s.revenue_cr, *s.pat_cr, s.ebitda_margin, s.issue_pe, *s.peer_pe, s.promoter,
              s.parent_track, *s.anchor_names, *s.use_of_proceeds, *s.red_flags]
    for f in fields:
        if f.value is not None:
            assert f.source_url in urls and set(f.sources) <= urls and f.status in ("corroborated", "reported")
        else:
            assert f.source_url is None and f.sources == [] and f.status is None


def test_varmora_replay_yields_three_year_series_and_a_named_promoter():
    d = _dossier("VARMORA_2026-09-24")
    s = extract_substance(d, client=ReplayClient("VARMORA"), model="m")
    _assert_provenance(s, d)
    assert s.docs_read == 14 and s.docs_truncated == 0
    assert [r.as_of for r in s.revenue_cr] == ["FY2024", "FY2025", "FY2026"]
    assert [r.as_of for r in s.pat_cr] == ["FY2024", "FY2025", "FY2026"]
    assert all(len(r.sources) >= 2 and r.status == "corroborated" for r in [*s.revenue_cr, *s.pat_cr])
    assert "Varmora" in str(s.promoter.value) and s.promoter.status == "reported"
    # a single blog's P/E and peer multiples are a rumour until a second domain agrees
    assert s.issue_pe.value is None and s.peer_pe == []
    assert any(x.startswith("issue_pe: 1 source(s)") for x in s.dropped)


def test_nse_replay_refuses_the_financials_the_web_disagrees_on():
    """'NSE' is ambiguous on the open web: sources quoted revenue of Rs 1,039cr
    against Rs 16,352cr for the same year. The gate must keep NONE of it, keep
    the reason, and still keep what did corroborate."""
    d = _dossier("NSE_2026-09-21")
    s = extract_substance(d, client=ReplayClient("NSE"), model="m")
    _assert_provenance(s, d)
    assert s.revenue_cr == [] and s.pat_cr == []
    assert any(x.startswith("revenue_cr[FY2025]: sources disagree") for x in s.dropped)
    assert any(x.startswith("pat_cr[FY2025]: sources disagree") for x in s.dropped)
    assert s.issue_pe.value == pytest.approx(35.4) and len(s.issue_pe.sources) >= 2
    assert len(s.anchor_names) >= 3 and all(a.status == "reported" for a in s.anchor_names)


def test_leap_replay_corroborates_a_margin_and_drops_a_lone_pe():
    d = _dossier("LEAP_nodate")
    s = extract_substance(d, client=ReplayClient("LEAP"), model="m")
    _assert_provenance(s, d)
    assert s.ebitda_margin.value == pytest.approx(51.31) and len(s.ebitda_margin.sources) >= 2
    assert [r.as_of for r in s.revenue_cr] == ["FY2024", "FY2025", "FY2026"]
    assert s.issue_pe.value is None and any(x.startswith("issue_pe: 1 source(s)") for x in s.dropped)
    assert "Sunu Mathew" in str(s.promoter.value)

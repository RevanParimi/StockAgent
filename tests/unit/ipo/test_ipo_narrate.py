"""IPO-4b — the narrator. Fully offline; no network, no model, no `data/`.

The narrator is the one place in this PI where prose reaches a reader, so
what is protected here is mostly what it may NOT say: nothing from the
verdict (which is never passed in), no number that is not in the facts, and
none of the advice vocabulary. A model that breaks either rule is rejected
and the deterministic template — which passes the same guards by
construction — is used instead.

The facts come from the recorded VARMORA dossier (captured 2026-09-21)
replayed through the extraction fixture, so the shapes under test are the
ones the real research produces, not invented ones.
"""
import json
from datetime import date
from pathlib import Path
from types import SimpleNamespace

import pytest

from core.ipo import narrate as mod
from core.ipo.extract import IpoSubstance, extract_substance
from core.ipo.hype import read_hype
from core.ipo.narrate import (
    FRAMING, IpoNarration, allowed_numbers, check_narration, compose, facts_digest,
    facts_urls, for_model, has_findings, narrate, narration_facts, render_template)
from core.ipo.research import ResearchDossier
from core.ipo.signals import IpoSignalSnapshot
from core.ipo.substance import read_substance
from core.ipo.verdict import decide_verdict
from core.ipo.verdicts import IpoVerdictStore
from tests.unit.ipo.test_ipo_extract import ReplayClient

FIX = Path("tests/fixtures/ipo_research")


@pytest.fixture(autouse=True)
def _no_telemetry(monkeypatch):
    import services.clients.llm_client as llm
    monkeypatch.setattr(llm, "record_llm_call", lambda *a, **k: None)
    monkeypatch.setattr(llm, "get_llm_client",
                        lambda: (_ for _ in ()).throw(AssertionError("real client")))


def _row(**extra):
    rec = {"symbol": "VARMORA", "company": "Varmora Granito Limited",
           "issue_start": "2026-09-22", "issue_end": "2026-09-24",
           "issue_price": 148.0, "issue_size_cr": 400.0}
    rec.update(extra)
    return rec


def _snap(state="open", **combined):
    return IpoSignalSnapshot(symbol="VARMORA", captured_at="2026-09-23T12:15:00+00:00",
                             state=state, issue_start="2026-09-22", issue_end="2026-09-24",
                             combined=combined or {"qib": 40.0, "total": 30.0, "retail": 9.0,
                                                   "nii": 20.0, "mutual_fund": 5.0},
                             cutoff_share=0.3)


@pytest.fixture(scope="module")
def research() -> IpoSubstance:
    dossier = ResearchDossier.model_validate(
        json.loads((FIX / "VARMORA_2026-09-24.json").read_text(encoding="utf-8")))
    import services.clients.llm_client as llm
    saved = llm.record_llm_call
    llm.record_llm_call = lambda *a, **k: None
    try:
        return extract_substance(dossier, client=ReplayClient("VARMORA"))
    finally:
        llm.record_llm_call = saved


@pytest.fixture
def facts(research):
    hype = read_hype([_snap()], _row(), symbol="VARMORA")
    substance = read_substance(research, [_snap()], _row(), symbol="VARMORA")
    return narration_facts(research, hype, substance, _row(),
                           symbol="VARMORA", close_date="2026-09-24", state="open")


class FakeClient:
    """Returns a fixed body, records the prompt it was given."""
    def __init__(self, body, finish_reason="stop"):
        self.body, self.finish_reason, self.calls, self.last = body, finish_reason, 0, None
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, **kw):
        self.calls += 1
        self.last = kw
        choice = SimpleNamespace(message=SimpleNamespace(content=self.body),
                                 finish_reason=self.finish_reason)
        return SimpleNamespace(choices=[choice],
                               usage=SimpleNamespace(prompt_tokens=10, completion_tokens=20))


class DeadClient:
    def __init__(self):
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, **kw):
        raise RuntimeError("model down")


# ─────────────────────────── the facts block ──────────────────────────────

def test_the_facts_carry_the_research_the_book_and_the_issue(facts):
    assert facts["company"] == "Varmora Granito Limited" and facts["symbol"] == "VARMORA"
    assert facts["issue"]["issue_price"] == 148.0 and facts["issue"]["source"] == "NSE"
    assert [s["fy"] for s in facts["pat_cr"]] == ["FY2024", "FY2025", "FY2026"]
    assert facts["pat_cr"][0]["status"] == "corroborated"
    assert facts["promoter"]["text"].startswith("Bhavesh")
    assert facts["subscription"]["qib_x"] == 40.0 and facts["subscription"]["source"] == "NSE"
    assert facts["subscription"]["status"].startswith("open")
    assert facts["red_flags"] and facts["use_of_proceeds"]


def test_no_verdict_field_can_reach_the_facts(research):
    """The prohibition that matters is structural: `narration_facts` takes no
    verdict, and nothing scored — index, component, feature, coverage — is
    copied out of either reading."""
    hype = read_hype([_snap()], _row(), symbol="VARMORA")
    substance = read_substance(research, [_snap()], _row(), symbol="VARMORA")
    verdict = decide_verdict(hype, substance, row=_row(), symbol="VARMORA",
                             close_date="2026-09-24", state="closed")
    assert verdict.short.lean is not None and verdict.demand is not None    # there IS a verdict
    facts = narration_facts(research, hype, substance, _row(),
                            symbol="VARMORA", close_date="2026-09-24", state="closed")

    def keys(node):
        if isinstance(node, dict):
            return set(node) | {k for v in node.values() for k in keys(v)}
        if isinstance(node, list):
            return {k for v in node for k in keys(v)}
        return set()
    forbidden = {"lean", "quadrant", "evidenced", "demand", "froth", "index", "hype",
                 "substance", "components", "features", "coverage", "band", "fitted",
                 "dark", "verdict", "short", "long"}
    assert not (keys(facts) & forbidden)
    numbers = {v for v in (verdict.demand, verdict.hype, verdict.substance) if v is not None}
    assert numbers and not (numbers & allowed_numbers(facts))


def test_the_book_status_says_whether_the_figures_were_final(research):
    for state, expect in (("open", "open"), ("closed", "closed"), ("listed", "closed")):
        f = narration_facts(research, read_hype([_snap(state=state)], _row()), None, _row(),
                            symbol="VARMORA", close_date="2026-09-24", state=state)
        assert f["subscription"]["status"].startswith(expect)


def test_the_model_never_sees_a_url_only_a_source_count(facts):
    blob = json.dumps(for_model(facts))
    assert "http" not in blob and "chittorgarh" not in blob
    assert for_model(facts)["pat_cr"][0]["sources"] == len(facts["pat_cr"][0]["sources"])
    assert facts_urls(facts)[0].startswith("http")           # the URLs still travel in code


def test_the_urls_are_every_source_once_in_first_appearance_order(facts):
    urls = facts_urls(facts)
    assert len(urls) == len(set(urls))
    assert "chittorgarh.com" in mod.domains_of(urls)


def test_an_empty_read_has_no_findings_and_narrates_nothing():
    facts = narration_facts(IpoSubstance(), None, None, _row(),
                            symbol="VARMORA", close_date="2026-09-24")
    assert has_findings(facts) is False                      # the issue row alone is not a note
    out = narrate(IpoSubstance(), None, None, _row(), symbol="VARMORA",
                  close_date="2026-09-24", client=DeadClient())
    assert out.text == "" and out.source == ""


def test_the_digest_moves_with_the_facts_and_not_with_the_wording(facts, research):
    same = narration_facts(research, read_hype([_snap()], _row(), symbol="VARMORA"),
                           read_substance(research, [_snap()], _row(), symbol="VARMORA"), _row(),
                           symbol="VARMORA", close_date="2026-09-24", state="open")
    assert facts_digest(same) == facts_digest(facts)
    moved = narration_facts(research, read_hype([_snap(qib=55.0, total=33.0)], _row()),
                            None, _row(), symbol="VARMORA", close_date="2026-09-24", state="open")
    assert facts_digest(moved) != facts_digest(facts)


# ─────────────────────────── the guards ───────────────────────────────────

def test_a_number_the_facts_do_not_state_is_rejected(facts):
    assert check_narration("Profit after tax was Rs 55.09 crore in FY2026.", facts) == ""
    assert "number not in facts" in check_narration(
        "Profit after tax grew 79.1% year on year.", facts)


def test_rounding_is_allowed_but_arithmetic_is_not(facts):
    assert check_narration("PAT of Rs 55.1 crore, revenue of Rs 1462 crore.", facts) == ""
    assert "number not in facts" in check_narration(
        "Revenue and PAT together came to Rs 1517 crore.", facts)


def test_a_share_may_be_written_as_a_percentage():
    facts = {"company": "X", "symbol": "X", "close_date": "2026-09-24",
             "subscription": {"retail_bids_at_cutoff_share": 0.46}}
    assert check_narration("46% of retail bids came at cut-off.", facts) == ""
    assert check_narration("0.46 of retail bids came at cut-off.", facts) == ""
    assert "number not in facts" in check_narration("54% of retail bids came at cut-off.", facts)


def test_a_loss_may_be_written_without_its_sign():
    facts = {"company": "X", "symbol": "X", "close_date": "2026-09-24",
             "pat_cr": [{"fy": "FY2025", "value": -12.5, "status": "corroborated", "sources": ["u"]}]}
    assert check_narration("A loss of Rs 12.5 crore in FY2025.", facts) == ""


def test_a_fiscal_year_may_be_written_short(facts):
    assert check_narration("Revenue rose between FY24 and FY26.", facts) == ""


@pytest.mark.parametrize("line", [
    "Investors should subscribe to the issue.",
    "The issue looks attractive at this valuation.",
    "A listing gain is likely.",
    "This reads as a quiet compounder.",
    "The hype index is elevated.",
    "We recommend applying.",
    "Profit after tax has nearly doubled since FY2024.",
    "Revenue is three times higher than at the start of the period.",
])
def test_the_advice_vocabulary_rejects_the_note(line, facts):
    assert "forbidden term" in check_narration(line, facts)


def test_arithmetic_stated_in_words_is_rejected_too(facts):
    """The number guard reads digits. "doubled" is a computation that emits
    none, and it is no more sourced for being spelled out."""
    assert "forbidden term" in check_narration("PAT doubled over the period.", facts)
    assert check_narration("PAT was Rs 55.09 crore in FY2026.", facts) == ""


def test_a_forbidden_word_the_documents_themselves_used_is_allowed():
    facts = {"company": "X", "symbol": "X", "close_date": "2026-09-24",
             "red_flags": [{"text": "Promoters may sell shares after the lock-in expires",
                            "sources": ["u"]}]}
    assert check_narration("The documents note promoters may sell after the lock-in.", facts) == ""


def test_the_guard_reads_the_model_facing_block_so_a_url_number_is_not_a_source(facts):
    """A URL slug carries digits (…rs-140-148-per-share-14031696). Those are
    not sourced claims, and quoting one must still be rejected."""
    assert "chittorgarh.com/ipo/varmora-granito-ipo/2563" in json.dumps(facts)
    assert "number not in facts" in check_narration("The price band was Rs 2563.", facts)


# ─────────────────────────── the template ─────────────────────────────────

def test_the_template_passes_its_own_guards(facts):
    """The fallback is only a fallback if it is admissible — otherwise a model
    outage would leave the row with nothing."""
    assert check_narration(render_template(facts), facts) == ""


def test_the_template_states_the_facts_it_was_given(facts):
    text = render_template(facts)
    assert "Varmora Granito Limited" in text and "VARMORA" in text
    assert "Rs 148" in text and "55.1" in text      # _fmt: one decimal above 10
    assert "Bhavesh" in text and "Promoters:" in text
    assert "Subscription (NSE" in text and "QIB 40x" in text and "book open" in text
    assert "Concerns raised in the documents read:" in text
    assert "30%" in text                                   # cut-off share as a percentage


def test_the_template_omits_what_is_absent_rather_than_naming_it():
    facts = narration_facts(IpoSubstance(), read_hype([_snap()], _row(), symbol="VARMORA"),
                            None, _row(), symbol="VARMORA", close_date="2026-09-24", state="open")
    text = render_template(facts)
    assert "P/E" not in text and "Promoters" not in text and "Concerns" not in text
    assert "QIB 40x" in text


def test_the_trailer_is_the_codes_and_never_the_models(facts):
    out = compose("Body text.", facts_urls(facts))
    assert out.startswith("Body text.")
    assert "Sources: chittorgarh.com" in out and out.endswith(FRAMING)
    assert "not advice" in FRAMING


def test_the_trailer_survives_a_note_with_no_sources():
    assert compose("Body.", []) == "Body.\n\n" + FRAMING


# ─────────────────────────── the model route ──────────────────────────────

def test_a_clean_model_note_is_used_and_gets_the_trailer(facts, research):
    body = ("Varmora Granito is promoted by Bhavesh Vallabhdas Varmora and others. "
            "Revenue from operations was Rs 1462 crore in FY2026 and profit after tax "
            "Rs 55.09 crore. The overall book was subscribed 30 times, with QIB at 40 times.")
    client = FakeClient(body)
    out = narrate(research, read_hype([_snap()], _row(), symbol="VARMORA"), None, _row(),
                  symbol="VARMORA", close_date="2026-09-24", state="open", client=client)
    assert out.source == "llm" and out.fallback_reason == ""
    assert out.text.startswith("Varmora Granito is promoted")
    assert "Sources:" in out.text and out.text.endswith(FRAMING)
    assert out.urls and out.facts_digest


def test_the_prompt_carries_the_facts_and_the_word_cap_and_no_url(facts, research):
    client = FakeClient("Rs 148 issue price.")
    narrate(research, read_hype([_snap()], _row(), symbol="VARMORA"), None, _row(),
            symbol="VARMORA", close_date="2026-09-24", state="open", client=client)
    system = client.last["messages"][0]["content"]
    user = client.last["messages"][-1]["content"]
    assert "220 words" in system and "research note" in system
    assert "VARMORA" in user and "pat_cr" in user
    assert "http" not in user
    assert client.last["temperature"] == 0.0
    assert "response_format" not in client.last            # prose out, not JSON


def test_a_model_that_invents_a_number_falls_back_to_the_template(research):
    client = FakeClient("Profit after tax grew 79.1% over the year.")
    out = narrate(research, read_hype([_snap()], _row(), symbol="VARMORA"), None, _row(),
                  symbol="VARMORA", close_date="2026-09-24", state="open", client=client)
    assert out.source == "template" and "number not in facts" in out.fallback_reason
    assert "79.1" not in out.text and "Varmora Granito Limited" in out.text


def test_a_model_that_states_a_lean_falls_back_to_the_template(research):
    client = FakeClient("A strong book; investors should subscribe.")
    out = narrate(research, read_hype([_snap()], _row(), symbol="VARMORA"), None, _row(),
                  symbol="VARMORA", close_date="2026-09-24", state="open", client=client)
    assert out.source == "template" and "forbidden term" in out.fallback_reason
    assert "subscribe" not in out.text.lower()


def test_a_dead_model_still_produces_a_note(research):
    out = narrate(research, read_hype([_snap()], _row(), symbol="VARMORA"), None, _row(),
                  symbol="VARMORA", close_date="2026-09-24", state="open", client=DeadClient())
    assert out.source == "template" and "llm error" in out.fallback_reason
    assert "Varmora Granito Limited" in out.text and out.text.endswith(FRAMING)


def test_an_empty_model_response_falls_back(research):
    out = narrate(research, read_hype([_snap()], _row(), symbol="VARMORA"), None, _row(),
                  symbol="VARMORA", close_date="2026-09-24", state="open",
                  client=FakeClient("   "))
    assert out.source == "template" and out.fallback_reason == "empty response"


def test_a_truncated_note_is_cut_back_to_its_last_whole_sentence(research):
    client = FakeClient("Rs 148 is the issue price. The book was subscribed 30 times overall. "
                        "Profit after tax in FY2026 was Rs 55", finish_reason="length")
    out = narrate(research, read_hype([_snap()], _row(), symbol="VARMORA"), None, _row(),
                  symbol="VARMORA", close_date="2026-09-24", state="open", client=client)
    assert out.source == "llm"
    assert out.text.split("\n\n")[0].endswith("subscribed 30 times overall.")


def test_a_truncation_with_no_whole_sentence_falls_back(research):
    out = narrate(research, read_hype([_snap()], _row(), symbol="VARMORA"), None, _row(),
                  symbol="VARMORA", close_date="2026-09-24", state="open",
                  client=FakeClient("Varmora Granito is a tile maker that", finish_reason="length"))
    assert out.source == "template" and out.fallback_reason == "empty response"


def test_the_kill_switch_uses_the_template_without_a_model(monkeypatch, research):
    from core.config import settings as s
    monkeypatch.setattr(s, "IPO_NARRATE_ENABLED", False, raising=True)
    client = FakeClient("never asked")
    out = narrate(research, read_hype([_snap()], _row(), symbol="VARMORA"), None, _row(),
                  symbol="VARMORA", close_date="2026-09-24", state="open", client=client)
    assert client.calls == 0 and out.source == "template"
    assert out.fallback_reason == "narration disabled"


def test_a_matching_previous_note_is_reused_without_a_model_call(research):
    hype = read_hype([_snap()], _row(), symbol="VARMORA")
    first = narrate(research, hype, None, _row(), symbol="VARMORA", close_date="2026-09-24",
                    state="open", client=FakeClient("Rs 148 issue price."))
    client = FakeClient("a second, different wording")
    again = narrate(research, hype, None, _row(), symbol="VARMORA", close_date="2026-09-24",
                    state="open", client=client, previous=first)
    assert client.calls == 0 and again.text == first.text


def test_a_moved_book_re_narrates(research):
    hype = read_hype([_snap()], _row(), symbol="VARMORA")
    first = narrate(research, hype, None, _row(), symbol="VARMORA", close_date="2026-09-24",
                    state="open", client=FakeClient("Rs 148 issue price."))
    client = FakeClient("Rs 148 issue price, book now closed.")
    moved = narrate(research, read_hype([_snap(state="closed", qib=55.0, total=33.0)], _row()),
                    None, _row(), symbol="VARMORA", close_date="2026-09-24", state="closed",
                    client=client, previous=first)
    assert client.calls == 1 and moved.facts_digest != first.facts_digest


def test_the_narrator_never_raises(monkeypatch, research):
    monkeypatch.setattr(mod, "narration_facts",
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))
    out = narrate(research, None, None, _row(), symbol="VARMORA", close_date="2026-09-24")
    assert out == IpoNarration()


# ─────────────────────────── the store ────────────────────────────────────

def test_the_narration_rides_on_the_row_and_is_outside_the_dedup_rule(tmp_path, research):
    store = IpoVerdictStore(base_dir=str(tmp_path))
    hype = read_hype([_snap()], _row(), symbol="VARMORA")
    substance = read_substance(research, [_snap()], _row(), symbol="VARMORA")
    verdict = decide_verdict(hype, substance, row=_row(), symbol="VARMORA",
                             close_date="2026-09-24", state="open")
    assert store.is_new(verdict, hype, substance) is True
    assert store.append(verdict, hype, substance, narration=IpoNarration(text="first")) is True

    # Same reading, different prose: not a new reading.
    assert store.is_new(verdict, hype, substance) is False
    assert store.append(verdict, hype, substance, narration=IpoNarration(text="re-worded")) is False
    rows = store.load_key("VARMORA", "2026-09-24")
    assert len(rows) == 1 and rows[0].narration.text == "first"

    # A moved reading is appended, and carries its own note.
    closed = decide_verdict(hype, substance, row=_row(), symbol="VARMORA",
                            close_date="2026-09-24", state="closed")
    assert store.is_new(closed, hype, substance) is True
    assert store.append(closed, hype, substance, narration=IpoNarration(text="second")) is True
    assert [r.narration.text for r in store.load_key("VARMORA", "2026-09-24")] == ["first", "second"]


def test_an_older_row_without_a_narration_still_reads(tmp_path):
    """Rows written before IPO-4b carry no `narration` key at all."""
    store = IpoVerdictStore(base_dir=str(tmp_path))
    store.path.write_text(json.dumps({
        "written_at": "2026-09-23T13:30:00+00:00",
        "verdict": {"symbol": "OLD", "close_date": "2026-09-22", "demand": 50.0},
    }) + "\n", encoding="utf-8")
    rows = store.load_all()
    assert len(rows) == 1 and rows[0].narration == IpoNarration()


# ─────────────────────────── the deep dive ────────────────────────────────

def test_the_deep_dive_narrates_the_row_it_writes(tmp_path, research, monkeypatch):
    from core.ipo import deep_dive as dd
    from core.ipo.signals import IpoSignalStore

    client = FakeClient("Rs 148 is the issue price; the overall book was 30 times subscribed.")
    monkeypatch.setattr(dd, "research_issue",
                        lambda *a, **k: ResearchDossier(symbol="VARMORA",
                                                        company="Varmora Granito Limited",
                                                        close_date="2026-09-24"))
    monkeypatch.setattr(dd, "_substance_for", lambda *a, **k: (research, True))
    signals = IpoSignalStore(base_dir=str(tmp_path / "signals"))
    signals.append(_snap())
    store = IpoVerdictStore(base_dir=str(tmp_path / "verdicts"))
    cand = dd.Candidate(symbol="VARMORA", close_date="2026-09-24", slot="t_minus_1",
                        state="open", row=_row())
    res = dd.analyse(cand, date(2026, 9, 23), research_dir=str(tmp_path / "research"),
                     signal_store=signals, verdict_store=store, client=client)
    assert res.error == "" and res.written is True
    assert res.narration.source == "llm" and client.calls == 1
    assert store.latest("VARMORA", "2026-09-24").narration.text == res.narration.text

    # A second evening with the same reading: deduped, and NOT narrated again.
    res2 = dd.analyse(cand, date(2026, 9, 24), research_dir=str(tmp_path / "research"),
                      signal_store=signals, verdict_store=store, client=client)
    assert res2.written is False and client.calls == 1
    assert len(store.load_key("VARMORA", "2026-09-24")) == 1


def test_the_post_close_re_read_narrates_once_then_stops(tmp_path, research, monkeypatch):
    """The note STATES whether the book was open or final, so the close is a
    fact that moved and the row earns fresh prose — once. The evenings after
    it change nothing, so the reading dedups and no further model is asked."""
    from core.ipo import deep_dive as dd
    from core.ipo.signals import IpoSignalStore

    client = FakeClient("Rs 148 is the issue price.")
    monkeypatch.setattr(dd, "research_issue",
                        lambda *a, **k: ResearchDossier(symbol="VARMORA",
                                                        company="Varmora Granito Limited",
                                                        close_date="2026-09-24"))
    monkeypatch.setattr(dd, "_substance_for", lambda *a, **k: (research, True))
    signals = IpoSignalStore(base_dir=str(tmp_path / "signals"))
    signals.append(_snap())
    store = IpoVerdictStore(base_dir=str(tmp_path / "verdicts"))
    kw = dict(research_dir=str(tmp_path / "research"), signal_store=signals,
              verdict_store=store, client=client)
    dd.analyse(dd.Candidate(symbol="VARMORA", close_date="2026-09-24", slot="t_minus_1",
                            state="open", row=_row()), date(2026, 9, 23), **kw)
    assert client.calls == 1
    post = dd.Candidate(symbol="VARMORA", close_date="2026-09-24", slot="post_close",
                        state="closed", row=_row())
    res = dd.analyse(post, date(2026, 9, 25), **kw)
    assert res.written is True and res.verdict.short.evidenced is True
    assert client.calls == 2                       # the book is now final: a new fact
    rows = store.load_key("VARMORA", "2026-09-24")
    assert len(rows) == 2 and all(r.narration.text for r in rows)

    # The next evening: same reading, same facts. Neither store nor model is asked.
    assert dd.analyse(post, date(2026, 9, 26), **kw).written is False
    assert client.calls == 2
    assert len(store.load_key("VARMORA", "2026-09-24")) == 2


def test_a_dark_row_is_never_narrated(tmp_path):
    """Nothing read means nothing stored (IPO-4a) — and no model call to
    write prose about a reading that was never taken."""
    from core.ipo import deep_dive as dd
    from core.ipo.signals import IpoSignalStore

    client = FakeClient("should never be asked")
    cand = dd.Candidate(symbol="VARMORA", close_date="2026-09-24", slot="t_minus_1",
                        state="open", row=_row())
    res = dd.analyse(cand, date(2026, 9, 23), research_dir=str(tmp_path / "research"),
                     signal_store=IpoSignalStore(base_dir=str(tmp_path / "signals")),
                     verdict_store=IpoVerdictStore(base_dir=str(tmp_path / "verdicts")),
                     search=lambda q, max_results=3: [], client=client)
    assert res.unread is True and client.calls == 0 and res.narration.text == ""

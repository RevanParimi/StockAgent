"""FIX-004: dossier knowledge is never dated after the day it was learned.

Independent invariants (REVIEW.md, issue-time information):
- a table of event dates against a pinned run date, whose expected stamps are
  written from the card's rule, not read from the implementation;
- every date that event ingestion writes is on or before the run date;
- the digest, with its clock pinned, never lists an observation or open
  guidance item dated after it.

The rule chosen (FIX-004): an event dated after the run date has not happened
and is skipped until it has; an event on or before the run date keeps its own
date, as before. NSE, Tavily and the LLM are replaced by fakes.
"""
import json
import re
from datetime import date, timedelta

import pytest

from backend.shared.schemas import dossier as dossier_mod
from backend.shared.schemas.dossier import (
    DossierObservation, GuidanceItem, OpenQuestion, ResponseSignature, TickerDossier,
)
from core.intelligence.rl.agents import event_ingestor as ei
from core.intelligence.rl.agents.event_ingestor import EventIngestor, find_qualifying_events
from core.intelligence.rl.stores import prediction_store as ps_mod
from core.intelligence.rl.stores.prediction_store import PredictionStore

TICKER, SECTOR = "TESTB", "banking_bfsi"
RUN = date(2026, 10, 10)        # a Saturday, the weekly scan's day
LOOKBACK = 8


def _rule(event_day: date, run_day: date = RUN, lookback: int = LOOKBACK) -> str | None:
    """The card's rule: the stored date, or None when the event is not digested."""
    if event_day > run_day:                                  # not happened yet
        return None
    if event_day < run_day - timedelta(days=lookback):       # outside the lookback (unchanged)
        return None
    return event_day.isoformat()                             # past or same day: its own date


# (event date, NSE section, expected stored date). The expected column is written
# by hand from the rule above; test_table_matches_the_rule checks the two agree.
EVENT_TABLE = [
    (date(2026, 10, 1), "announcements", None),              # 9 days back: outside the lookback
    (date(2026, 10, 2), "announcements", "2026-10-02"),      # the lookback's edge
    (date(2026, 10, 8), "announcements", "2026-10-08"),      # two days back
    (date(2026, 10, 9), "board_meetings", "2026-10-09"),     # a meeting held yesterday
    (date(2026, 10, 10), "board_meetings", "2026-10-10"),    # same day as the run
    (date(2026, 10, 11), "board_meetings", None),            # tomorrow
    (date(2026, 10, 24), "board_meetings", None),            # IDFCFIRSTB's measured case
    (date(2026, 10, 27), "board_meetings", None),            # STARHEALTH's measured case
]


def _subject(day: date, section: str) -> str:
    kind = "Board meeting to consider financial results" if section == "board_meetings" \
        else "Outcome of board meeting - financial results"
    return f"{kind} {day.isoformat()}"


def _nse_payload(rows):
    """prefetch_nse_data-shaped dict; rows are (date, section) pairs."""
    sections = {"announcements": [], "board_meetings": []}
    for day, section in rows:
        sections[section].append({"subj": _subject(day, section),
                                  "dt": day.strftime("%d-%b-%Y")})
    return {
        **sections,
        "actions": [],
        "key_mappings": {
            "announcements": {"desc": "subj", "date": "dt"},
            "board_meetings": {"desc": "subj", "date": "dt"},
            "actions": {},
        },
        "error": None,
    }


def _pin_clock(monkeypatch, day: date) -> None:
    """Pin 'today' for event ingestion, the store's save stamp and the digest."""
    class _Pinned(date):
        @classmethod
        def today(cls):
            return day
    monkeypatch.setattr(ei, "_date", _Pinned)
    monkeypatch.setattr(ps_mod, "date", _Pinned)
    monkeypatch.setattr(dossier_mod, "_date", _Pinned)


def _fake_llm(monkeypatch, calls: list) -> None:
    """Curator-shaped output that touches every field merge_curator_output dates."""
    def _call_llm(self, system, user):
        subject = re.search(r"^EVENT SUBJECT: (.+)$", user, re.M).group(1)
        calls.append(subject)
        return json.dumps({
            "event_tags_today": ["earnings_event"],
            "new_observations": [{"observation": f"obs | {subject}",
                                  "tags": ["earnings_event"], "materiality": 0.8}],
            "signature_updates": [
                {"action": "confirm", "signature_id": "RS001"},
                {"action": "create", "trigger_tags": ["earnings_event"],
                 "response": f"moves on | {subject}"},
            ],
            "guidance_updates": [{"action": "add", "guidance": f"guide | {subject}",
                                  "source": "event"}],
            "catalyst_updates": [],
            "thesis_update": f"thesis | {subject}",
            "flow_note": "",
            "open_question_updates": [
                {"action": "raise", "question": f"q | {subject}"},
                {"action": "resolve", "question": "Will margins hold", "answer": "yes"},
            ],
            "business_summary_update": "",
        })
    monkeypatch.setattr(EventIngestor, "_call_llm", _call_llm)
    monkeypatch.setattr(ei, "_build_bundle", lambda ticker, event: "bundle")


def _store(tmp_path, monkeypatch, seed: TickerDossier | None = None) -> PredictionStore:
    monkeypatch.setattr(ei.settings, "PREDICTION_DATA_DIR", str(tmp_path))
    store = PredictionStore(TICKER, sector=SECTOR, base_dir=tmp_path)
    if seed is not None:
        store.save_dossier(seed)
    return store


def _seed() -> TickerDossier:
    return TickerDossier(
        ticker=TICKER, sector=SECTOR, created_at="2026-09-01", last_updated="2026-09-01",
        response_signatures=[ResponseSignature(
            signature_id="RS001", trigger_tags=["earnings_event"], response="+2% on results",
            first_seen="2026-09-01", last_seen="2026-09-01", evidence_dates=["2026-09-01"])],
        open_questions=[OpenQuestion(question="Will margins hold?", raised_on="2026-09-01")],
    )


def _all_stored_dates(d: TickerDossier) -> list[str]:
    dates = [d.created_at, d.last_updated, d.thesis_since]
    dates += [o.date for o in d.observations]
    dates += [g.date for g in d.guidance]
    for s in d.response_signatures:
        dates += [s.first_seen, s.last_seen, *s.evidence_dates]
    for q in d.open_questions:
        dates += [q.raised_on, q.resolved_on]
    return [x for x in dates if x]


# ---------------------------------------------------------------------------
# Write time: event ingestion
# ---------------------------------------------------------------------------

def test_table_matches_the_rule():
    for day, _section, expected in EVENT_TABLE:
        assert _rule(day) == expected, day


def test_event_dates_against_the_run_date(tmp_path, monkeypatch):
    _pin_clock(monkeypatch, RUN)
    store = _store(tmp_path, monkeypatch, _seed())
    monkeypatch.setattr(ei.settings, "EVENT_INGEST_MAX_EVENTS_PER_SCAN", 50)
    monkeypatch.setattr(ei, "prefetch_nse_data",
                        lambda ticker: _nse_payload([(d, s) for d, s, _ in EVENT_TABLE]))
    calls: list[str] = []
    _fake_llm(monkeypatch, calls)

    digested = [(d, s, exp) for d, s, exp in EVENT_TABLE if exp is not None]
    skipped = [(d, s) for d, s, exp in EVENT_TABLE if exp is None]

    count = EventIngestor().run(TICKER, SECTOR, lookback_days=LOOKBACK)

    assert count == len(digested)
    out = store.load_dossier()
    # The LLM never saw an event outside the rule, so nothing was digested from it.
    assert sorted(calls) == sorted(_subject(d, s) for d, s, _ in digested)
    obs_by_subject = {o.observation.split(" | ", 1)[1]: o.date for o in out.observations}
    guid_by_subject = {g.guidance.split(" | ", 1)[1]: g.date for g in out.guidance}
    sig_by_subject = {s.response.split(" | ", 1)[1]: s for s in out.response_signatures
                      if " | " in s.response}
    q_by_subject = {q.question.split(" | ", 1)[1]: q.raised_on for q in out.open_questions
                    if " | " in q.question}
    for day, section, expected in digested:
        subj = _subject(day, section)
        assert obs_by_subject[subj] == expected
        assert guid_by_subject[subj] == expected
        assert sig_by_subject[subj].first_seen == sig_by_subject[subj].last_seen == expected
        assert sig_by_subject[subj].evidence_dates == [expected]
        assert q_by_subject[subj] == expected
    for day, section in skipped:
        assert _subject(day, section) not in obs_by_subject
    # RS001 was confirmed once per digested event, each time on that event's date.
    rs001 = next(s for s in out.response_signatures if s.signature_id == "RS001")
    assert sorted(rs001.evidence_dates) == sorted(["2026-09-01"] + [e for *_, e in digested])
    # Watermark key format "date|subject[:60]" is unchanged, and only digested events
    # are watermarked, so a skipped meeting is still eligible on a later scan.
    assert sorted(out.ingested_event_keys) == sorted(
        f"{e}|{_subject(d, s)[:60]}" for d, s, e in digested)
    # The invariant: no date written by the run is after the run date.
    run_iso = RUN.isoformat()
    late = [x for x in _all_stored_dates(out) if x > run_iso]
    assert late == []


def test_future_meetings_do_not_take_the_scan_cap(monkeypatch):
    future = [(RUN + timedelta(days=k), "board_meetings") for k in (3, 10, 17)]
    past = [(RUN - timedelta(days=k), "announcements") for k in (1, 2, 3)]
    monkeypatch.setattr(ei.settings, "EVENT_INGEST_MAX_EVENTS_PER_SCAN", 3)
    monkeypatch.setattr(ei, "prefetch_nse_data", lambda ticker: _nse_payload(future + past))

    events = find_qualifying_events(TICKER, LOOKBACK, today=RUN)

    # Newest first would have put the three future meetings first and filled the cap.
    assert [e["date"] for e in events] == [d.isoformat() for d, _ in past]


def test_find_defaults_to_the_current_date(monkeypatch):
    _pin_clock(monkeypatch, RUN)
    rows = [(RUN, "board_meetings"), (RUN + timedelta(days=1), "board_meetings")]
    monkeypatch.setattr(ei, "prefetch_nse_data", lambda ticker: _nse_payload(rows))

    assert [e["date"] for e in find_qualifying_events(TICKER, LOOKBACK)] == [RUN.isoformat()]


def test_one_board_meeting_from_scan_to_digest(tmp_path, monkeypatch):
    """STARHEALTH's shape: a meeting on Tue 27 Oct, weekly scans on Saturdays."""
    meeting = date(2026, 10, 27)
    subj = _subject(meeting, "board_meetings")
    store = _store(tmp_path, monkeypatch)
    monkeypatch.setattr(ei, "prefetch_nse_data",
                        lambda ticker: _nse_payload([(meeting, "board_meetings")]))
    calls: list[str] = []
    _fake_llm(monkeypatch, calls)

    for scan in (date(2026, 10, 10), date(2026, 10, 17), date(2026, 10, 24)):
        _pin_clock(monkeypatch, scan)
        assert EventIngestor().run(TICKER, SECTOR, lookback_days=LOOKBACK) == 0
        assert store.load_dossier() is None and calls == []

    _pin_clock(monkeypatch, date(2026, 10, 31))           # four days after the meeting
    assert EventIngestor().run(TICKER, SECTOR, lookback_days=LOOKBACK) == 1
    out = store.load_dossier()
    assert calls == [subj]
    assert [o.date for o in out.observations] == ["2026-10-27"]
    assert out.ingested_event_keys == [f"2026-10-27|{subj[:60]}"]

    # A digest dated before the meeting never lists its observation or guidance;
    # one dated on or after does. (The filter covers those two dated sections only:
    # the thesis and signatures this write set still render, see the receipt.)
    early = out.to_digest(10_000, as_of="2026-10-26")
    assert _section_dates(early, "Recent observations") == []
    assert _section_dates(early, "Open guidance") == []
    late = out.to_digest(10_000, as_of="2026-10-27")
    assert f"- 2026-10-27: obs | {subj}" in late
    assert f"- 2026-10-27 (event): guide | {subj}" in late
    # The next scan does not ingest it again.
    _pin_clock(monkeypatch, date(2026, 11, 3))
    assert EventIngestor().run(TICKER, SECTOR, lookback_days=LOOKBACK) == 0


# ---------------------------------------------------------------------------
# Read time: the digest
# ---------------------------------------------------------------------------

_PAST_OBS = ["2026-09-25", "2026-09-28", "2026-09-30", "2026-10-01",
             "2026-10-03", "2026-10-06", "2026-10-07"]
_FUTURE_OBS = ["2026-10-24", "2026-10-24", "2026-10-24"]


def _idfc_like() -> TickerDossier:
    """IDFCFIRSTB's measured shape: three observations dated 24 Oct among older ones,
    plus STARHEALTH's open guidance item dated 27 Oct."""
    obs = [DossierObservation(date=d, observation=f"note {i}")
           for i, d in enumerate(_PAST_OBS + _FUTURE_OBS)]
    return TickerDossier(
        ticker="TESTB", sector=SECTOR, created_at="2026-09-01", last_updated="2026-10-07",
        observations=obs,
        guidance=[GuidanceItem(date="2026-09-20", source="Q1 call", guidance="NIM 6%"),
                  GuidanceItem(date="2026-10-27", source="board meeting", guidance="Q2 results")],
    )


def _section_dates(digest: str, header: str) -> list[str]:
    m = re.search(rf"^## {header}\n((?:- .*\n?)+)", digest, re.M)
    if not m:
        return []
    return re.findall(r"^- (\d{4}-\d{2}-\d{2})", m.group(1), re.M)


def test_digest_with_pinned_clock_lists_no_row_dated_after_it(monkeypatch):
    _pin_clock(monkeypatch, date(2026, 10, 7))             # the probe's date

    digest = _idfc_like().to_digest(10_000)                # no as_of: the clock decides

    # The five newest rows on or before 7 Oct, where before FIX-004 three of the
    # five were the 24 Oct rows.
    assert _section_dates(digest, "Recent observations") == _PAST_OBS[-5:]
    assert _section_dates(digest, "Open guidance") == ["2026-09-20"]
    assert "2026-10-24" not in digest and "2026-10-27" not in digest


@pytest.mark.parametrize("offset", range(-20, 25))
def test_digest_never_lists_a_row_dated_after_its_date(offset):
    as_of = (date(2026, 10, 7) + timedelta(days=offset)).isoformat()
    d = _idfc_like()

    digest = d.to_digest(10_000, as_of=as_of)

    listed = _section_dates(digest, "Recent observations")
    guidance = _section_dates(digest, "Open guidance")
    assert all(x <= as_of for x in listed + guidance)
    # Rows dated on the digest date are known that day and stay listed.
    known = sorted(x for x in _PAST_OBS + _FUTURE_OBS if x <= as_of)
    assert listed == known[-5:]
    assert guidance == [g.date for g in d.guidance if g.date <= as_of]
    if not known:
        assert "## Recent observations" not in digest      # no empty section header


def test_explicit_as_of_overrides_the_clock(monkeypatch):
    _pin_clock(monkeypatch, date(2026, 10, 7))

    digest = _idfc_like().to_digest(10_000, as_of="2026-10-30")

    assert _section_dates(digest, "Recent observations")[-3:] == _FUTURE_OBS
    assert "2026-10-27" in _section_dates(digest, "Open guidance")


def test_stored_rows_are_not_rewritten_by_the_digest():
    d = _idfc_like()
    before = d.model_dump()

    d.to_digest(10_000, as_of="2026-10-07")

    assert d.model_dump() == before

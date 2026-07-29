import json
from datetime import date, timedelta

import pytest

from backend.shared.schemas.dossier import TickerDossier
from core.intelligence.rl.agents import event_ingestor as ei
from core.intelligence.rl.agents.event_ingestor import (
    EventIngestor, _build_bundle, _is_qualifying, find_qualifying_events,
)
from core.intelligence.rl.stores.prediction_store import PredictionStore


# ---------------------------------------------------------------------------
# _is_qualifying matrix
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("subject", [
    "Outcome of Board Meeting - Q4 Results",
    "Earnings Call Transcript",
    "Investor Presentation",
])
def test_is_qualifying_positive(subject):
    assert _is_qualifying(subject) is True


@pytest.mark.parametrize("subject", [
    "Change in Registrar",
    "Loss of share certificate",
])
def test_is_qualifying_negative(subject):
    assert _is_qualifying(subject) is False


def test_is_qualifying_empty_string():
    assert _is_qualifying("") is False


# ---------------------------------------------------------------------------
# find_qualifying_events — date window, cap, newest-first
# ---------------------------------------------------------------------------

def _nse_payload(items_with_dates):
    """Build a prefetch_nse_data-shaped dict. items_with_dates is a list of
    (date_str, subject) for announcements; key_mappings use plain field names."""
    announcements = [{"desc": subj, "an_dt": dt} for dt, subj in items_with_dates]
    return {
        "announcements": announcements,
        "board_meetings": [],
        "actions": [],
        "key_mappings": {
            "announcements": {"desc": "desc", "date": "an_dt"},
            "board_meetings": {},
            "actions": {},
        },
        "symbol_used": "TESTX",
        "fetched_at": "2026-06-12T00:00:00",
        "error": None,
    }


def _fmt(d: date) -> str:
    """Format a date as NSE's "DD-Mon-YYYY" string."""
    return d.strftime("%d-%b-%Y")


def test_find_qualifying_events_date_window_cap_and_order(monkeypatch):
    today = date.today()

    items = [
        (_fmt(today - timedelta(days=2)), "Outcome of Board Meeting - Q4 Results"),   # within window
        (_fmt(today - timedelta(days=7)), "Earnings Call Transcript"),                 # within window
        (_fmt(today - timedelta(days=8)), "Investor Presentation"),                    # within window (edge)
        (_fmt(today - timedelta(days=40)), "Outcome of Board Meeting - Q1 Results"),   # too old (>8 days)
        (_fmt(today - timedelta(days=1)), "Change in Registrar"),                      # not qualifying
    ]
    monkeypatch.setattr(ei, "prefetch_nse_data", lambda ticker: _nse_payload(items))

    events = find_qualifying_events("TESTX", lookback_days=8)

    # Cap at EVENT_INGEST_MAX_EVENTS_PER_SCAN (default 3), newest-first.
    assert len(events) == 3
    expected_dates = [
        (today - timedelta(days=2)).isoformat(),
        (today - timedelta(days=7)).isoformat(),
        (today - timedelta(days=8)).isoformat(),
    ]
    assert [e["date"] for e in events] == expected_dates
    assert all("key" in e and "subject" in e and "description" in e for e in events)


def test_find_qualifying_events_unparseable_date_skipped(monkeypatch):
    # The valid date must be relative to today, otherwise it drifts outside the
    # lookback window as the calendar advances (the fixed "10-Jun-2026" here was
    # a time-bomb that expired 30 days after 2026-06-10).
    items = [
        ("not-a-date", "Outcome of Board Meeting - Q4 Results"),
        (_fmt(date.today() - timedelta(days=10)), "Earnings Call Transcript"),
    ]
    monkeypatch.setattr(ei, "prefetch_nse_data", lambda ticker: _nse_payload(items))

    events = find_qualifying_events("TESTX", lookback_days=30)

    assert len(events) == 1
    assert events[0]["subject"] == "Earnings Call Transcript"


def test_find_qualifying_events_empty_when_prefetch_raises(monkeypatch):
    def boom(ticker):
        raise RuntimeError("network down")

    monkeypatch.setattr(ei, "prefetch_nse_data", boom)
    assert find_qualifying_events("TESTX", lookback_days=8) == []


# ---------------------------------------------------------------------------
# _build_bundle — truncation + Tavily absent path
# ---------------------------------------------------------------------------

def test_build_bundle_includes_subject_and_description(monkeypatch):
    def fake_fetch_tavily_context(*a, **k):
        return "No Tavily results for: query"

    monkeypatch.setattr(ei, "fetch_tavily_context", fake_fetch_tavily_context)

    event = {"date": "2026-06-10", "subject": "Q4 Results", "description": "Net profit up 12%",
             "key": "2026-06-10|Q4 Results"}
    bundle = _build_bundle("TESTX", event)

    assert "Q4 Results" in bundle
    assert "Net profit up 12%" in bundle
    assert "No Tavily" not in bundle  # absent-Tavily text not leaked into bundle


def test_build_bundle_includes_tavily_page_when_available(monkeypatch):
    def fake_fetch_tavily_context(queries, max_queries=1, max_results_per_query=1):
        return "--- Tavily (full content): some query ---\n• Title\n  Full article text here\n  Source: http://x"

    monkeypatch.setattr(ei, "fetch_tavily_context", fake_fetch_tavily_context)

    event = {"date": "2026-06-10", "subject": "Q4 Results", "description": "Net profit up 12%",
             "key": "2026-06-10|Q4 Results"}
    bundle = _build_bundle("TESTX", event)

    assert "Full article text here" in bundle


def test_build_bundle_truncated_to_max_chars(monkeypatch):
    long_text = "X" * 10000

    def fake_fetch_tavily_context(queries, max_queries=1, max_results_per_query=1):
        return long_text

    monkeypatch.setattr(ei, "fetch_tavily_context", fake_fetch_tavily_context)
    monkeypatch.setattr(ei.settings, "EVENT_INGEST_TEXT_MAX_CHARS", 100)

    event = {"date": "2026-06-10", "subject": "Q4 Results", "description": "desc",
             "key": "2026-06-10|Q4 Results"}
    bundle = _build_bundle("TESTX", event)

    assert len(bundle) == 100


def test_build_bundle_tavily_failure_skips_silently(monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("tavily down")

    monkeypatch.setattr(ei, "fetch_tavily_context", boom)

    event = {"date": "2026-06-10", "subject": "Q4 Results", "description": "Net profit up 12%",
             "key": "2026-06-10|Q4 Results"}
    bundle = _build_bundle("TESTX", event)

    assert "Q4 Results" in bundle
    assert "Net profit up 12%" in bundle


# ---------------------------------------------------------------------------
# EventIngestor.run — merge, business_summary, watermark, flag, garbage LLM
# ---------------------------------------------------------------------------

_PAYLOAD = {
    "event_tags_today": ["earnings_event"],
    "new_observations": [
        {"observation": "Q4 net profit up 12% YoY", "tags": ["earnings_event"], "materiality": 0.8},
    ],
    "signature_updates": [],
    "guidance_updates": [
        {"action": "add", "guidance": "FY27 volume growth guided at 8-10%",
         "source": "Q4 FY26 earnings call"},
    ],
    "catalyst_updates": [],
    "thesis_update": None,
    "flow_note": "",
    "open_question_updates": [],
    "business_summary_update": "Maruti Suzuki is India's largest passenger vehicle "
                                "manufacturer with a strong rural distribution network.",
}


def _setup_store(tmp_path, monkeypatch, ticker="TESTX", sector="automobile"):
    monkeypatch.setattr(ei.settings, "PREDICTION_DATA_DIR", str(tmp_path))
    store = PredictionStore(ticker, sector=sector, base_dir=tmp_path)
    return store


def _patch_common(monkeypatch, events, payload_or_payloads):
    monkeypatch.setattr(ei, "find_qualifying_events",
                         lambda ticker, days, exclude_keys=None: [
                             e for e in events if e["key"] not in (exclude_keys or set())])
    monkeypatch.setattr(ei, "_build_bundle", lambda ticker, event: "bundle text")

    if isinstance(payload_or_payloads, list):
        responses = iter(payload_or_payloads)

        def _call_llm(self, system, user):
            payload = next(responses)
            if isinstance(payload, str):
                return payload
            return json.dumps(payload)
    else:
        def _call_llm(self, system, user):
            return json.dumps(payload_or_payloads)

    monkeypatch.setattr(EventIngestor, "_call_llm", _call_llm)


def test_run_merges_guidance_and_business_summary(tmp_path, monkeypatch):
    store = _setup_store(tmp_path, monkeypatch)
    event = {"date": "2026-06-10", "subject": "Outcome of Board Meeting - Q4 Results",
             "description": "Net profit up 12%", "key": "2026-06-10|Outcome of Board Meeting - Q4 Results"}
    _patch_common(monkeypatch, [event], _PAYLOAD)

    count = EventIngestor().run("TESTX", "automobile")

    assert count == 1
    dossier = store.load_dossier()
    assert dossier is not None
    assert any("FY27 volume growth" in g.guidance for g in dossier.guidance)
    assert dossier.business_summary.startswith("Maruti Suzuki")
    assert any("Q4 net profit up 12%" in o.observation for o in dossier.observations)
    assert dossier.ingested_event_keys == [event["key"]]


def test_run_business_summary_capped(tmp_path, monkeypatch):
    store = _setup_store(tmp_path, monkeypatch)
    event = {"date": "2026-06-10", "subject": "Outcome of Board Meeting - Q4 Results",
             "description": "Net profit up 12%", "key": "2026-06-10|Outcome of Board Meeting - Q4 Results"}
    long_summary = "A" * 1000
    payload = dict(_PAYLOAD)
    payload["business_summary_update"] = long_summary
    _patch_common(monkeypatch, [event], payload)

    EventIngestor().run("TESTX", "automobile")

    dossier = store.load_dossier()
    assert len(dossier.business_summary) == 500


def test_run_watermark_prevents_double_ingest_and_caps_keys(tmp_path, monkeypatch):
    store = _setup_store(tmp_path, monkeypatch)
    event = {"date": "2026-06-10", "subject": "Outcome of Board Meeting - Q4 Results",
             "description": "Net profit up 12%", "key": "2026-06-10|Outcome of Board Meeting - Q4 Results"}
    _patch_common(monkeypatch, [event], _PAYLOAD)

    first = EventIngestor().run("TESTX", "automobile")
    assert first == 1

    # Second run: find_qualifying_events filters by exclude_keys via our fake,
    # so the same event must not be re-ingested.
    second = EventIngestor().run("TESTX", "automobile")
    assert second == 0

    dossier = store.load_dossier()
    assert dossier.ingested_event_keys == [event["key"]]


def test_run_ingested_event_keys_capped_at_40(tmp_path, monkeypatch):
    store = _setup_store(tmp_path, monkeypatch)

    # Pre-seed dossier with 40 watermark keys (already at cap).
    today_iso = date.today().isoformat()
    seeded = [f"old-{i:03d}|old event {i}" for i in range(1, 41)]
    dossier = TickerDossier(ticker="TESTX", sector="automobile",
                             created_at=today_iso, last_updated=today_iso,
                             ingested_event_keys=list(seeded))
    store.save_dossier(dossier)

    event = {"date": "2026-06-10", "subject": "Outcome of Board Meeting - Q4 Results",
             "description": "Net profit up 12%", "key": "2026-06-10|Outcome of Board Meeting - Q4 Results"}
    _patch_common(monkeypatch, [event], _PAYLOAD)

    count = EventIngestor().run("TESTX", "automobile")
    assert count == 1

    out = store.load_dossier()
    assert len(out.ingested_event_keys) == 40
    assert out.ingested_event_keys[-1] == event["key"]
    # Oldest key evicted to make room.
    assert seeded[0] not in out.ingested_event_keys
    assert seeded[1:] == out.ingested_event_keys[:-1]


def test_run_llm_garbage_skips_event_no_key_appended(tmp_path, monkeypatch):
    store = _setup_store(tmp_path, monkeypatch)
    event = {"date": "2026-06-10", "subject": "Outcome of Board Meeting - Q4 Results",
             "description": "Net profit up 12%", "key": "2026-06-10|Outcome of Board Meeting - Q4 Results"}
    _patch_common(monkeypatch, [event], "sorry, I can't help with that")

    count = EventIngestor().run("TESTX", "automobile")

    assert count == 0
    dossier = store.load_dossier()
    # Dossier was created (load_dossier returns None -> EventIngestor creates one
    # in-memory) but since nothing was ingested, nothing is saved.
    assert dossier is None


def test_run_does_not_raise_on_per_event_failure_and_continues(tmp_path, monkeypatch):
    store = _setup_store(tmp_path, monkeypatch)
    bad_event = {"date": "2026-06-09", "subject": "Earnings Call Transcript",
                  "description": "", "key": "2026-06-09|Earnings Call Transcript"}
    good_event = {"date": "2026-06-10", "subject": "Outcome of Board Meeting - Q4 Results",
                   "description": "Net profit up 12%", "key": "2026-06-10|Outcome of Board Meeting - Q4 Results"}
    _patch_common(monkeypatch, [bad_event, good_event], ["not json", json.dumps(_PAYLOAD)])

    count = EventIngestor().run("TESTX", "automobile")

    assert count == 1
    dossier = store.load_dossier()
    assert dossier.ingested_event_keys == [good_event["key"]]


def test_run_flag_off_returns_zero_and_store_untouched(tmp_path, monkeypatch):
    store = _setup_store(tmp_path, monkeypatch)
    monkeypatch.setattr(ei.settings, "RL_EVENT_INGEST_ENABLED", False)

    event = {"date": "2026-06-10", "subject": "Outcome of Board Meeting - Q4 Results",
             "description": "Net profit up 12%", "key": "2026-06-10|Outcome of Board Meeting - Q4 Results"}
    _patch_common(monkeypatch, [event], _PAYLOAD)

    count = EventIngestor().run("TESTX", "automobile")

    assert count == 0
    assert store.load_dossier() is None


def test_run_never_raises_on_unexpected_exception(tmp_path, monkeypatch):
    _setup_store(tmp_path, monkeypatch)

    def boom(ticker, days, exclude_keys=None):
        raise RuntimeError("boom")

    monkeypatch.setattr(ei, "find_qualifying_events", boom)

    count = EventIngestor().run("TESTX", "automobile")
    assert count == 0

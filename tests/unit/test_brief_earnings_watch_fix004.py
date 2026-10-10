"""FIX-004 change 1: the morning brief's earnings watch line never comes from
guidance the system had not learned by the time the brief goes out.

Independent invariants (REVIEW.md, issue-time information):
- a table of brief dates against stored guidance, whose expected watch lines
  are written by hand from the rule, not read from the implementation;
- a sweep of brief dates across a board meeting: the watch line is always an
  item dated before the brief's date, and the one the digest lists last;
- end to end, build_morning_brief and both renderers never show a pre-FIX-004
  row stamped with the meeting's date before the meeting.

The rule (FIX-004 change 1): the brief goes out at 08:50 IST, before any weekday
dossier writer runs (the curator at the 16:30 review; event ingestion and the
research loop on Saturdays). So it counts only open guidance dated before its
own date, and takes the latest stored of those. A row dated the brief's own day
can only be one that event ingestion stamped with a board meeting's future date
before FIX-004, as STARHEALTH's 27 Oct row (measured 7 Oct).
"""
from datetime import date, timedelta

import pytest

import core.delivery.brief as br
from backend.shared.schemas import dossier as dossier_mod
from backend.shared.schemas.dossier import GuidanceItem, TickerDossier
from core.intelligence.rl.stores import prediction_store as ps_mod
from core.intelligence.rl.stores.prediction_store import PredictionStore
from core.portfolio.store import PortfolioStore

SYMBOL, SECTOR = "TESTINS", "insurance"
MEETING = date(2026, 10, 27)                       # a Tuesday, as STARHEALTH's
FUTURE_TEXT = "Q2 results: gross premiums up 20%"  # written before the meeting

# Stored order (the order learned). Each: (date, guidance, status).
GUIDANCE = [
    ("2026-07-20", "Combined ratio under 100% by FY27", "open"),
    ("2026-08-05", "Retail health growth of 25%", "met"),
    ("2026-09-15", "Claims ratio to ease in H2", "open"),
    ("2026-10-27", FUTURE_TEXT, "open"),            # pre-FIX-004 row, the meeting's date
]


def _rule(guidance: list[tuple[str, str, str]], brief_day: date) -> str:
    """The rule: the latest stored open item dated before the brief's day, else ''."""
    known = [text for d, text, status in guidance
             if status == "open" and d < brief_day.isoformat()]
    return known[-1] if known else ""


# (brief date, expected watch line). Written by hand from the rule above;
# test_table_matches_the_rule checks the two agree.
WATCH_TABLE = [
    (date(2026, 7, 20), ""),                                    # the first item is dated that day
    (date(2026, 7, 21), "Combined ratio under 100% by FY27"),
    (date(2026, 8, 6), "Combined ratio under 100% by FY27"),    # the met item never counts
    (date(2026, 9, 15), "Combined ratio under 100% by FY27"),   # the claims item: same day, not yet
    (date(2026, 9, 16), "Claims ratio to ease in H2"),
    (date(2026, 10, 26), "Claims ratio to ease in H2"),         # Mon, the day before the meeting
    (date(2026, 10, 27), "Claims ratio to ease in H2"),         # Tue 08:50, the meeting's morning
    (date(2026, 10, 28), FUTURE_TEXT),                          # its date has passed
]


@pytest.fixture(autouse=True)
def _clock_after_every_date(monkeypatch):
    """The brief's and the dossier's clocks read 1 Dec, after every date here, so
    code that asks the clock instead of the brief's date shows the future row."""
    class _Pinned(date):
        @classmethod
        def today(cls):
            return date(2026, 12, 1)
    monkeypatch.setattr(br, "date", _Pinned)
    monkeypatch.setattr(dossier_mod, "_date", _Pinned)


def _dossier(guidance=GUIDANCE) -> TickerDossier:
    return TickerDossier(
        ticker=SYMBOL, sector=SECTOR, created_at="2026-07-01", last_updated="2026-10-09",
        guidance=[GuidanceItem(date=d, source="src", guidance=text, status=status)
                  for d, text, status in guidance])


def _serve(monkeypatch, dossier: TickerDossier | None) -> None:
    monkeypatch.setattr(br, "_resolve_sector", lambda t: SECTOR)
    monkeypatch.setattr(br, "_load_ticker_dossier", lambda t, s: dossier)


def test_table_matches_the_rule():
    for day, expected in WATCH_TABLE:
        assert _rule(GUIDANCE, day) == expected, day


@pytest.mark.parametrize("day, expected", WATCH_TABLE)
def test_watch_line_follows_the_table(monkeypatch, day, expected):
    _serve(monkeypatch, _dossier())

    assert br._earnings_watch(SYMBOL, day) == expected


def test_review_l1_future_guidance_is_never_the_watch_line(monkeypatch):
    """The fresh review's reproduction: on 23 Oct, open guidance dated 24 Oct."""
    _serve(monkeypatch, _dossier([("2026-10-24", "guide from 2026-10-24", "open")]))

    assert br._earnings_watch(SYMBOL, date(2026, 10, 23)) == ""
    assert br._earnings_watch(SYMBOL, date(2026, 10, 24)) == ""      # its own morning
    assert br._earnings_watch(SYMBOL, date(2026, 10, 25)) == "guide from 2026-10-24"


@pytest.mark.parametrize("offset", range(-26, 10))
def test_watch_line_is_known_before_the_brief_and_matches_the_digest(monkeypatch, offset):
    day = MEETING + timedelta(days=offset)
    d = _dossier()
    _serve(monkeypatch, d)

    watch = br._earnings_watch(SYMBOL, day)

    dated = {text: g_date for g_date, text, _ in GUIDANCE}
    if watch:
        assert dated[watch] < day.isoformat()
    if day <= MEETING:
        assert watch != FUTURE_TEXT
    # The watch line is the last open guidance line the digest showed the day before.
    digest = d.to_digest(10_000, as_of=(day - timedelta(days=1)).isoformat())
    section = digest.split("## Open guidance\n", 1)[1].split("\n\n", 1)[0] \
        if "## Open guidance\n" in digest else ""
    lines = [ln for ln in section.split("\n") if ln.startswith("- ")]
    assert watch == (lines[-1].split("): ", 1)[1] if lines else "")


def test_latest_stored_wins_over_latest_dated(monkeypatch):
    """The latest learned item, not the latest dated: the 10 Oct weekly scan appends
    a 6 Oct announcement after the curator's 8 Oct row. Unchanged behaviour."""
    _serve(monkeypatch, _dossier([("2026-10-08", "curator note", "open"),
                                  ("2026-10-06", "event note", "open")]))

    assert br._earnings_watch(SYMBOL, date(2026, 10, 12)) == "event note"


def test_watch_line_is_empty_without_a_dossier_or_on_a_failure(monkeypatch):
    _serve(monkeypatch, None)
    assert br._earnings_watch(SYMBOL, MEETING) == ""

    def _boom(t, s):
        raise RuntimeError("store unreadable")
    monkeypatch.setattr(br, "_load_ticker_dossier", _boom)
    assert br._earnings_watch(SYMBOL, MEETING) == ""


# ---------------------------------------------------------------------------
# End to end: build the brief from a stored dossier, render it both ways
# ---------------------------------------------------------------------------

def _brief_on(day: date, tmp_path, monkeypatch, guidance=GUIDANCE) -> dict:
    """build_morning_brief for a user holding SYMBOL, results on MEETING, the
    dossier read back from a real PredictionStore under tmp_path."""
    monkeypatch.setattr(ps_mod.settings, "PREDICTION_DATA_DIR", str(tmp_path / "predictions"))
    PredictionStore(SYMBOL, sector=SECTOR).save_dossier(_dossier(guidance))
    monkeypatch.setattr(br, "_resolve_sector", lambda t: SECTOR)
    monkeypatch.setattr(br, "load_events_calendar", lambda: {"events": {SYMBOL: [
        {"symbol": SYMBOL, "date": MEETING.isoformat(), "kind": "results",
         "desc": "Board meeting to consider financial results"}]}})
    monkeypatch.setattr(br, "_narrate_brief", lambda b: "Deterministic headline.")
    monkeypatch.setattr(br, "_read_regime", lambda: None)
    monkeypatch.setattr(br, "_overnight_items", lambda: [])
    monkeypatch.setattr(br, "_shelf_events_since", lambda since: [])
    monkeypatch.setattr(br, "_ipo_watch", lambda on=None: [])
    monkeypatch.setattr(br, "upcoming_lockin_alerts", lambda on, symbols=None: [])
    store = PortfolioStore(user_id="u1", base_dir=str(tmp_path / "portfolio"))
    store.save_digest({"date": (day - timedelta(days=1)).isoformat(), "user_id": "u1",
                       "portfolio_value": 100000.0, "cost_basis": 90000.0,
                       "total_pnl_pct": 11.1, "escalations": [],
                       "holdings": [{"symbol": SYMBOL, "verdict": "HOLD", "close": 1500.0,
                                     "pnl_pct": 11.1, "reason": "thesis intact",
                                     "notes": []}]})
    return br.build_morning_brief("u1", day, store=store)


@pytest.mark.parametrize("day", [date(2026, 10, 26), MEETING])
def test_brief_before_the_meeting_never_shows_the_future_row(tmp_path, monkeypatch, day):
    brief = _brief_on(day, tmp_path, monkeypatch)

    assert brief["earnings_soon"] == [{"symbol": SYMBOL, "date": MEETING.isoformat(),
                                       "watch": "Claims ratio to ease in H2"}]
    for rendered in (br.render_brief_text(brief), br.render_brief_html(brief)):
        assert FUTURE_TEXT not in rendered
        assert "Claims ratio to ease in H2" in rendered


def test_brief_falls_back_to_the_generic_line_when_only_future_guidance(tmp_path, monkeypatch):
    brief = _brief_on(MEETING, tmp_path, monkeypatch,
                      guidance=[("2026-10-27", FUTURE_TEXT, "open")])

    assert brief["earnings_soon"][0]["watch"] == ""
    text = br.render_brief_text(brief)
    assert FUTURE_TEXT not in text
    assert "results & guidance are the next catalyst." in text

"""
PR-009: the evidence exit rule's inputs, its shadow record and its switch gate.

The legacy exit rule sells on `thesis_break`. A daily price-path miss sends
the thesis reviewer one short LLM call with no new data; a "not intact" answer
with a falling remaining path sells. The evidence rule sells on `case_broken`
instead (core/portfolio/advisor.py): a high-materiality negative NSE filing or
rule-typed disclosure in the last 5 sessions, the latest actionable research
verdict a SELL (run after the buy, at most 22 sessions old), or the close at
the invalidation level, and only after `advisor.min_hold_sessions`. A news
article is a watch item, never a sale. The stops and every other rule are the
same code under both.

`advisor.exit_rule` picks the mode:

- `legacy`: the legacy rule decides; nothing is recorded here.
- `shadow` (the default): the legacy rule decides. Both verdicts are recorded
  in data/portfolio/<user>/exit_shadow.jsonl, one row per holding per review
  day, written once however often the pipeline re-runs.
- `evidence`: case_broken decides, and the legacy verdict is still recorded.

**Example.** Bought at ₹500 for its order book. Day 4: the market falls 2%,
the stock 4%, the review says "not intact" and the path ends at ₹478, so the
legacy rule EXITs at ₹480. The evidence rule finds no negative event, no SELL
verdict, ₹480 above the ₹455 invalidation level, and 4 sessions held: HOLD.
The row records both, and it is a disagreement.

**Decisions.** A holding (symbol and buy date) is one decision: its first
review day on which the two rules disagree. From that day the two rules no
longer hold the same position (one sold it), so its later disagreeing rows
stay in the file and are not counted again. A stock bought again later is a
new holding.

**Grading.** A decision is graded 10 and 30 sessions after the review day,
from the close both rules saw, against where the sale put the money. That
benchmark is fixed in the row on the decision day (`decision_benchmark`):
`cash` for a plain EXIT, whose proceeds wait in cash, graded on the stock's
own return; `nifty` for a SWITCH (the proceeds bought another stock) or once
the portfolio deploys its cash, graded on the excess over the Nifty from the
close's own session. With the auditor's rules (core/audit/rules.py) the
evidence rule was right when it sold and the stock then fell short of the
benchmark, or when it kept and the stock did not. Its result is that gap,
+gap when it kept the stock and -gap when it sold. **Example:** the stock
falls 3% and the Nifty 5%. After a plain EXIT, selling saved 3%: the evidence
rule that sold was right (result +3.0). After a SWITCH the money went into
the market, which lost 5%, so keeping was 2 points better: wrong (-2.0). A
SWITCH whose buy leg the executor would refuse (no close, the idea's entry
band) leaves the money in cash, so its row says cash. The weekly scorecard
grades the rows with its own price functions (the auditor's Nifty series); a
horizon that has not ended is pending, never scored.

The stock's return is in one price basis: the horizon close is put into the
basis of the decision's close with every bonus or split that went ex between
them, from the list NSE gives at grading (`horizon_in_basis`). **Example:**
sold at ₹190, a 1:1 bonus three sessions later, ₹95 at the horizon: ₹190 in
the old shares, a return of 0, not -50%. A demerger, a scheme, a
consolidation, a capital reduction or a rights issue NSE lists between the
two closes, or a new basis the instrument registry records, has no ratio to
apply. When that basis cannot be established the decision has no result
that week. A cause no later read can change sets the decision aside from
the gate, named and within a cap; any other never helps the evidence rule
(`gate_look`).

**The switch gate** is fixed here, before any result. It recommends the
switch; the owner makes it (`advisor.exit_rule: evidence`). Rollback: legacy.
A pass means "not worse" in count and money, not "better" (`gate_look`).

Information is the review day's: an event published after it, or another
symbol's, never counts, and neither does a research run after it, on or
before the buy day (the buyer could have seen it), or more than 22 sessions
before it. The invalidation level is set in the rupees of its deep dive; it
is compared in the review day's price basis, after every bonus and split
since the dive, or not at all (`level_in_basis`).
"""
from __future__ import annotations

import logging
from collections import Counter
from datetime import date, timedelta
from typing import Callable, Iterable

from backend.shared.data.fetchers.symbol_resolver import identity_break
from backend.shared.pipeline import decision_gate as dg
from backend.shared.schemas.portfolio import ExitShadowRow
from core.audit.rules import excess, is_correct, pct_change
from core.intelligence.rl.nse_calendar import trading_days_after, trading_days_ago
from core.portfolio.advisor import CASE_EVENT_SOURCES, ExitEvidence, case_broken_reasons
from core.portfolio.results import sessions_held
from core.portfolio.sizing import entry_check

logger = logging.getLogger(__name__)

MODES = ("legacy", "shadow", "evidence")
CASE_EVENT_SESSIONS = 5            # a negative event counts for this many sessions
RESEARCH_VERDICT_SESSIONS = 22     # a research verdict counts until it is this many sessions old
SELLS = ("EXIT", "SWITCH")         # the verdicts that sell the whole position
SHARE_COUNT_KINDS = ("bonus", "split")   # the corporate actions that change the price basis
BENCHMARKS = ("cash", "nifty")     # where a decision's sale put the money
# A close in its own bar's raw basis: NSE's, or Yahoo's within 1% of it
# (services/data/fetchers/close_verifier.py; NSE's wins a larger gap).
RAW_CLOSE_SOURCES = ("nse", "agree")

# -- The switch gate (fixed 24 Oct 2026, before any shadow row existed) --------
GRADE_HORIZONS_TD = (10, 30)
GATE_HORIZON_TD = 30               # a disagreement counts once 30 sessions have passed
GATE_MIN_MATURED = 15              # matured disagreements at 30 sessions
GATE_MIN_SPAN_DAYS = 56            # their review days span at least 8 weeks
GATE_MIN_RIGHT_PCT = 50.0          # the evidence rule right on at least this share, at 10 AND 30
GATE_MIN_MEAN_RESULT_PCT = 0.0     # and its mean result at least this, at 10 AND 30
GATE_MAX_STOCK_PCT = 30.0          # no stock more than this share of them
GATE_LOOKS = 2                     # the pass holds at this many consecutive weekly looks
BETTER_RIGHT_PCT = 70.0            # a pass is labelled "better" at this share with a positive mean
# A decision whose result can never be known is set aside, named (fixed 29 Oct 2026, before any
# shadow row existed); past either cap a pass becomes "cannot judge".
GATE_MAX_SET_ASIDE = 2             # decisions set aside
GATE_MAX_SET_ASIDE_PCT = 10.0      # of the decisions past 30 sessions

PASS, FAIL, NOT_ENOUGH, CANNOT_JUDGE = "pass", "fail", "not_enough", "cannot_judge"
# Why a grade has no result: a cause no later read can change, or one it may (`horizon_in_basis`).
LASTING, TEMPORARY = "lasting", "temporary"
_RESULT_UNITS = 10_000             # results are kept to 4 decimals; summed exactly in these units


def exit_rule_mode() -> str:
    """`advisor.exit_rule`, read per run. An unknown value reads as shadow:
    the same decisions as legacy, and the comparison keeps recording."""
    from backend.shared.config.settings.loader import cfg
    value = str(cfg("advisor.exit_rule", fallback="shadow") or "").strip().lower()
    if value in MODES:
        return value
    logger.warning("[exit_shadow] advisor.exit_rule %r is not one of %s; using shadow",
                   value, MODES)
    return "shadow"


def acting_rule(mode: str) -> str:
    """The rule whose verdict the autopilot executes in `mode`."""
    return "evidence" if mode == "evidence" else "legacy"


def sells(verdict: str) -> bool:
    return str(verdict or "").strip().upper() in SELLS


# -- Evidence, pure given its inputs ------------------------------------------------

def recent_negative_events(events: Iterable, symbol: str, on: date,
                           sessions: int = CASE_EVENT_SESSIONS) -> list:
    """High-materiality negative events about `symbol` published in the last
    `sessions` sessions up to `on`: after the IST day of the session before
    them, and on or before `on`. An event with no publication time, one
    published after `on`, or another symbol's never counts. Oldest first."""
    after = trading_days_ago(on, sessions).isoformat()
    last = on.isoformat()
    out = []
    for e in events:
        day = e.published_day()
        if e.symbol != symbol or day is None or not (after < day <= last):
            continue
        if e.direction == "negative" and e.materiality == "high":
            out.append(e)
    return sorted(out, key=lambda e: e.published_at or "")


def latest_actionable_verdict(records: Iterable[dict], symbol: str, on: date, bought: date,
                              sessions: int = RESEARCH_VERDICT_SESSIONS) -> dict | None:
    """The newest score-history record for `symbol` whose decision gate is
    actionable or degraded, run (IST) on a later day than the buy `bought`
    and at most `sessions` sessions before `on`: on or after the session
    `sessions` back, and on or before `on`. None when there is none.

    Never counted: an abstained run (in enforce, INSUFFICIENT DATA); a run
    on or before the buy day, which the buyer could have seen before buying;
    a run older than the window. Every held stock is managed, and the
    1st-of-month forecast re-analyses every managed stock, so a holding has a
    fresh verdict each month. Example: bought on 5 Oct over a 2 Oct SELL; that
    SELL never sells it. A SELL of 8 Oct sells it (after the minimum holding
    period) until it is 22 sessions old, unless a newer actionable run says
    otherwise."""
    from core.discovery.candidates import _gate_status, _ist_day
    since = trading_days_ago(on, sessions)
    best = None
    for r in records:
        if str(r.get("ticker") or "").strip().upper() != symbol:
            continue
        day = _ist_day(r.get("run_at"))
        if (day is None or day <= bought or day < since or day > on
                or not dg.is_actionable(_gate_status(r))):
            continue
        if best is None or str(r.get("run_at")) > str(best.get("run_at")):
            best = r
    return best


def invalidation_for(ideas: Iterable, symbol: str, on: date) -> tuple[float, str, date | None]:
    """(level, source, dive day) from `symbol`'s shelf idea whose latest deep
    dive is the newest on or before `on`, whatever its status (an idea the
    autopilot bought is promoted). The level is in the rupees of that dive's
    close. (0.0, "", None) when there is none or it set no level."""
    from core.discovery.shelf import last_dived
    best, best_day = None, None
    for idea in ideas:
        if str(getattr(idea, "symbol", "")).strip().upper() != symbol:
            continue
        dived = last_dived(idea)
        if dived is None or dived > on:
            continue
        if best_day is None or dived > best_day:
            best, best_day = idea, dived
    level = float(getattr(best, "invalidation_level", 0.0) or 0.0) if best is not None else 0.0
    if level <= 0:
        return 0.0, "", None
    return level, f"shelf idea dived {best_day.isoformat()}, {best.status}", best_day


def level_in_basis(level: float, dived: date, holding, on: date,
                   record=None) -> tuple[float, str, str]:
    """`level`, set in the rupees of a deep dive on `dived`, in the price
    basis of the close on `on`: divided by the ratio of every bonus or split
    that went ex after the dive and on or before `on`. Returns (level, note,
    gap). The note names each ratio applied. When the basis cannot be
    established the level is 0.0 and the gap says why: the invalidation test
    then does not run, because the price cannot be compared with the level.

    The ratios come from two records, each for its own days:
      - after the buy: the holding's applied actions, the record its cost
        basis and the stops rely on (the sync runs before any advisor rule);
      - from the dive day to the buy day: what NSE listed for the symbol this
        review day (`record`, a corp_actions.ActionRecord). The holding has no
        record before its buy, so this list must reach back to the dive day.
    Unknown: a bonus or split that went ex on the dive day itself (the dive's
    close may be on either side of it), or a split or bonus row NSE lists
    from the dive day on that could not be parsed.

    Example: dived at about ₹500 with the level ₹455; bought; a 1:1 bonus
    goes ex. The sync halves the cost basis, and the level is ₹227.50."""
    try:
        bought = date.fromisoformat(str(holding.buy_date)[:10])
    except (TypeError, ValueError):
        return 0.0, "", "the buy date is unreadable"
    dive, buy, last = dived.isoformat(), bought.isoformat(), on.isoformat()
    applied = [a for a in holding.applied_actions
               if a.kind in SHARE_COUNT_KINDS and a.ratio > 0 and buy < a.ex_date <= last]
    listed = [a for a in (record.actions if record is not None else ())
              if a.kind in SHARE_COUNT_KINDS and a.ratio > 0 and a.ex_date <= last]
    unread = sorted(d for d in (record.unparsed if record is not None else ())
                    if dive <= d <= last)
    if unread:
        return 0.0, "", (f"NSE lists a split or bonus on {unread[0]} that could not be "
                         "read, so its price basis is unknown")
    on_dive_day = [a for a in applied + listed if a.ex_date == dive]
    if on_dive_day:
        return 0.0, "", (f"a {on_dive_day[0].kind} went ex on the dive day, {dive}, so the "
                         "dive's close may be on either side of it")
    used: dict[str, object] = {}
    if dived <= bought:
        reach = record.covers_from if record is not None else ""
        if not reach or reach > dive:
            since = f"starts {reach}" if reach else "is empty or was not read"
            return 0.0, "", (f"a bonus or split between the dive ({dive}) and the buy "
                             f"({buy}) cannot be ruled out: NSE's list read today {since}")
        for a in listed:
            if dive < a.ex_date <= buy:
                used.setdefault(a.key, a)
    for a in applied:
        if a.ex_date > dive:
            used.setdefault(a.key, a)
    if not used:
        return level, "", ""
    steps = sorted(used.values(), key=lambda a: a.ex_date)
    factor = 1.0
    for a in steps:
        factor *= a.ratio
    note = (f"{level:.2f} at the dive, adjusted for "
            + ", ".join(f"the {a.kind} ex {a.ex_date} (÷{a.ratio:g})" for a in steps))
    return level / factor, note, ""


def exit_evidence(holding, on: date, *, events: Iterable = (), records: Iterable[dict] = (),
                  ideas: Iterable = (), actions=None, gaps: Iterable[str] = ()) -> ExitEvidence:
    """The evidence for one holding on review day `on`. Pure: the caller
    reads the stores (`EvidenceReader`) and names any it could not read.
    `actions` is the symbol's corp_actions.ActionRecord from this review
    day's sync, for the invalidation level's price basis."""
    symbol = holding.symbol.strip().upper()
    try:
        bought = date.fromisoformat(holding.buy_date[:10])
        held = sessions_held(bought, on)
    except (TypeError, ValueError):
        bought, held = None, None
    gaps = list(gaps)
    negative = recent_negative_events(events, symbol, on)
    selling = [e for e in negative if e.source in CASE_EVENT_SOURCES]
    watch = [e for e in negative if e.source not in CASE_EVENT_SOURCES]
    # An unreadable buy date: no verdict can be shown to postdate the buy.
    verdict = latest_actionable_verdict(records, symbol, on, bought) if bought else None
    at_dive, source, dived = invalidation_for(ideas, symbol, on)
    level = at_dive
    if at_dive > 0:
        level, note, gap = level_in_basis(at_dive, dived, holding, on, actions)
        if gap:
            gaps.append(f"invalidation level {at_dive:.2f} not used: {gap}")
        elif note:
            source = f"{source}; {note}"
    def brief(e) -> dict:
        return {"id": e.id, "published_at": e.published_at, "category": e.category,
                "what": e.what, "source": e.source}
    return ExitEvidence(
        sessions_held=held,
        negative_events=[brief(e) for e in selling],
        watch_events=[brief(e) for e in watch],
        research_verdict=str((verdict or {}).get("verdict") or "").strip().upper(),
        research_run_at=str((verdict or {}).get("run_at") or ""),
        invalidation_level=level,
        invalidation_level_at_dive=at_dive,
        invalidation_source=source if level > 0 else "",
        gaps=gaps,
    )


class EvidenceReader:
    """Reads one run's evidence sources: the event store and the score
    history per holding, the shelf once, and the corp-action sync's records
    (`corp_actions`: symbol -> ActionRecord, what this review day's sync
    fetched). A source that fails is named in the evidence's gaps, never read
    as "no evidence" silently."""

    def __init__(self, ideas: Iterable = (), event_store=None,
                 score_records: Callable[[str], list[dict]] | None = None,
                 corp_actions: dict | None = None) -> None:
        self._ideas = list(ideas)
        self._events = event_store
        self._records = score_records
        self._corp_actions = {str(k).strip().upper(): v for k, v in (corp_actions or {}).items()}

    def _event_store(self):
        if self._events is None:
            from core.events.store import EventStore
            self._events = EventStore()
        return self._events

    def _score_records(self, symbol: str) -> list[dict]:
        if self._records is None:
            from services.data.stores.score_store import ScoreStore
            self._records = ScoreStore().get_records
        return self._records(symbol)

    def read(self, holding, on: date) -> ExitEvidence:
        symbol = holding.symbol.strip().upper()
        gaps: list[str] = []
        events: list = []
        records: list[dict] = []
        try:
            events = self._event_store().load(symbol)
        except Exception as exc:
            gaps.append(f"company events unread: {exc}")
        try:
            records = self._score_records(symbol)
        except Exception as exc:
            gaps.append(f"research verdicts unread: {exc}")
        return exit_evidence(holding, on, events=events, records=records,
                             ideas=self._ideas, actions=self._corp_actions.get(symbol),
                             gaps=gaps)


def decision_benchmark(legacy_verdict: str, evidence_verdict: str, *,
                       deploys_cash: bool = False, switch_lands: bool = True) -> str:
    """Where the money of a disagreement's sale went, fixed on the decision
    day: "nifty" when the selling rule's verdict is a SWITCH whose buy leg
    lands (the proceeds bought another stock) or the portfolio deploys its
    cash into new ideas, else "cash" (a plain EXIT's proceeds, or a SWITCH's
    whose buy the executor refuses, wait in cash). "" when the two rules
    agree: there is no decision to grade.

    `deploys_cash` is false for every portfolio until SA-049 turns cash
    deployment on; from that day its decisions record "nifty". A stored row
    keeps the benchmark it was written with."""
    if sells(legacy_verdict) == sells(evidence_verdict):
        return ""
    selling = legacy_verdict if sells(legacy_verdict) else evidence_verdict
    if deploys_cash or (str(selling).strip().upper() == "SWITCH" and switch_lands):
        return "nifty"
    return "cash"


def switch_buy_lands(quote, session: date, idea, *, identity_issue: str = "",
                     enforcing: bool = False) -> bool:
    """Whether a SWITCH's buy leg passes the checks the executor makes before
    sizing it (core/portfolio/autopilot.py `_execute_buys`), at the
    destination's close `quote` (a pricing.SessionClose for `session`; None
    when it has none): a close; under the data gate's enforce, the session's
    own bar and a resolved identity (`identity_issue` empty); and a price
    inside its shelf idea's entry band (sizing.entry_check). Pure. False means
    the proceeds stay in cash.

    Not checked here: the executor's own re-fetch of the close, a buy of under
    one share after sizing, a buy already in the ledger."""
    close = getattr(quote, "close", None)
    if close is None or close <= 0:
        return False
    if enforcing and (not quote.fresh_for(session) or identity_issue):
        return False
    return entry_check(float(close), idea)[0]


def shadow_row(*, on: date, user_id: str, mode: str, close: float, legacy, evidence_rec,
               evidence: ExitEvidence | None, buy_date: str,
               price_bar_date: str = "", deploys_cash: bool = False,
               switch_lands: Callable[[str], bool] | None = None) -> ExitShadowRow:
    """The row comparing the two rules' records for one holding. `buy_date`
    names the holding; `price_bar_date` is the session `close` came from;
    `deploys_cash` and `switch_lands` feed the decision's benchmark
    (`decision_benchmark`). `switch_lands(symbol)` says whether a SWITCH's
    buy of `symbol` would land (`switch_buy_lands`); it is asked only for
    the selling rule's SWITCH. Without it, a SWITCH's buy counts as landing."""
    ev = evidence or ExitEvidence(gaps=["no evidence assembled"])
    disagree = sells(legacy.verdict) != sells(evidence_rec.verdict)
    lands = True
    selling = legacy if sells(legacy.verdict) else evidence_rec
    if disagree and switch_lands is not None and str(selling.verdict).upper() == "SWITCH":
        destination = str(selling.switch_candidate or "").strip().upper()
        lands = bool(destination) and switch_lands(destination)
    return ExitShadowRow(
        date=on.isoformat(), user_id=user_id, symbol=legacy.symbol, buy_date=str(buy_date),
        mode=mode, close=float(close), price_bar_date=str(price_bar_date or ""),
        legacy_verdict=legacy.verdict, legacy_triggers=list(legacy.triggers),
        evidence_verdict=evidence_rec.verdict, evidence_triggers=list(evidence_rec.triggers),
        disagree=disagree,
        benchmark=decision_benchmark(legacy.verdict, evidence_rec.verdict,
                                     deploys_cash=deploys_cash, switch_lands=lands),
        case_broken_reasons=case_broken_reasons(ev, float(close)),
        sessions_held=ev.sessions_held,
        evidence={
            "event_ids": [e.get("id") for e in ev.negative_events],
            "watch_event_ids": [e.get("id") for e in ev.watch_events],
            "research_verdict": ev.research_verdict,
            "research_run_at": ev.research_run_at,
            "invalidation_level": ev.invalidation_level,
            "invalidation_level_at_dive": ev.invalidation_level_at_dive,
            "invalidation_source": ev.invalidation_source,
            "gaps": list(ev.gaps),
        },
    )


# -- Grading and the gate, pure -------------------------------------------------------

def _day(value) -> date | None:
    try:
        return date.fromisoformat(str(value)[:10])
    except (TypeError, ValueError):
        return None


def first_disagreements(rows: Iterable[dict]) -> tuple[list[dict], int]:
    """The decisions among `rows`: each holding's (symbol and buy date) first
    disagreeing row, oldest first. That day one rule sold the holding and the
    other kept it, so from then on they no longer hold the same position, and
    the holding's later disagreeing rows are not new decisions, whichever
    rule they favour. Returns (decisions, the later rows left out)."""
    dated = sorted((r for r in rows if r.get("disagree") and _day(r.get("date"))),
                   key=lambda r: _day(r.get("date")))
    seen: set[tuple[str, str]] = set()
    decisions, later = [], 0
    for row in dated:
        holding = (str(row.get("symbol") or ""), str(row.get("buy_date") or ""))
        if holding in seen:
            later += 1
            continue
        seen.add(holding)
        decisions.append(row)
    return decisions, later


def horizon_in_basis(quote, record, start: date,
                     decided: date) -> tuple[float | None, str, str, str]:
    """The horizon close `quote` (a pricing.SessionClose) in the price basis
    of the decision's close: the raw close of its bar `start`, taken on the
    review day `decided`. A bonus or split cuts the raw price by its ratio
    and leaves the company's value alone, so the horizon close is multiplied
    by the ratio of every one that went ex after `start` and on or before the
    quote's bar (an ex day's close is already in the new shares). Returns
    (close, note, gap, kind); the note names each ratio applied.

    The ratios come from `record`, what NSE lists for the symbol read at
    grading (corp_actions.ActionRecord; None when it could not be read): a
    stock the acting rule sold has no holding, so no applied actions. When
    the basis cannot be established the close is None, the gap says why, and
    the kind says whether a later read could change it (TEMPORARY) or not
    (LASTING). Checked in this order, the first cause found decides:
      - temporary: the quote is undated or its bar is before `start`; the
        list was not read, or holds rows but none dated;
      - lasting: the list is empty (NSE lists nothing for the symbol) or
        starts after `start` (a bonus or split between could be missing);
      - lasting: a bonus or split went ex after `start` and on or before
        `decided`: the stored close was fetched on the review day and may be
        in either basis;
      - a split or bonus row from after `start` was not read as a ratio (it
        could not be parsed, names other securities or words the record does
        not know), lasting when it is ex on or before the quote's bar,
        temporary after it when the quote is Yahoo's alone (NSE's close did
        not answer): Yahoo's series is adjusted for every action up to the
        day it is read, and NSE's raw close would be graded;
      - NSE lists a change no ratio converts (a demerger, a scheme, a
        consolidation, a capital reduction, a rights issue, or a row of no
        known kind: the record's `basis_changes`) ex after `start`: lasting
        on or before the quote's bar or `decided`, temporary after them when
        the quote is Yahoo's alone;
      - temporary: the quote is Yahoo's alone with a bonus or split ex after
        its bar;
      - lasting: two rows give one day two ratios.

    Example: decided at ₹190 on 23 Oct; a 1:1 bonus (ratio 2) goes ex on
    28 Oct; the horizon's raw close is ₹95, which is ₹190 in the old shares.
    Had 40% of the company been demerged instead, ₹114 is not a fall of 40%,
    and no ratio in NSE's row says what the part that left is worth: no
    re-read changes that, so it is lasting."""
    bar = getattr(quote, "bar_date", None)
    since = start.isoformat()
    if bar is None:
        return None, "", "the horizon close is undated", TEMPORARY
    if bar < start:
        return None, "", (f"the horizon close is from {bar.isoformat()}, before the "
                          f"decision's close ({since})"), TEMPORARY
    if record is None:
        return None, "", ("NSE's list of its corporate actions could not be read, so one "
                          f"since {since} cannot be ruled out"), TEMPORARY
    if not record.covers_from:
        if record.rows:
            return None, "", ("NSE's list of its corporate actions holds no dated row, so "
                              f"one since {since} cannot be ruled out"), TEMPORARY
        return None, "", ("NSE's list of its corporate actions is empty, so one since "
                          f"{since} cannot be ruled out"), LASTING
    if record.covers_from > since:
        return None, "", (f"NSE's list of its corporate actions starts {record.covers_from}, "
                          f"after the decision's close ({since})"), LASTING
    after, review, last = since, decided.isoformat(), bar.isoformat()
    raw = str(getattr(quote, "source", "") or "") in RAW_CLOSE_SOURCES
    actions = [a for a in record.actions if a.kind in SHARE_COUNT_KINDS and a.ratio > 0]
    ex_days = sorted({a.ex_date for a in actions} | set(record.unparsed))
    stored = [d for d in ex_days if after < d <= review]
    if stored:
        return None, "", (f"a bonus or split went ex on {stored[0]}, after the close's bar "
                          f"({after}) and by the review day ({review}), so the stored close "
                          "may be on either side of it"), LASTING
    unread = [d for d in record.unparsed if after < d and (d <= last or not raw)]
    if unread:
        first = min(unread)
        return (None, "", f"NSE lists a split or bonus on {first} that could not be read",
                LASTING if first <= last else TEMPORARY)
    changed = sorted((d, kind) for d, kind in record.basis_changes
                     if after < d and (d <= last or d <= review or not raw))
    if changed:
        ex, kind = changed[0]
        return None, "", (f"NSE lists a {kind} ex {ex}, after the decision's close ({after}), "
                          "and no ratio puts the horizon close in the decision's price basis "
                          "across it"), LASTING if ex <= max(last, review) else TEMPORARY
    if not raw:
        later = [d for d in ex_days if d > last]
        if later:
            return None, "", (f"the horizon close is Yahoo's alone (NSE's did not answer), "
                              f"and Yahoo adjusts it for the bonus or split ex {later[0]}"
                              ), TEMPORARY
    used: dict[tuple[str, str], float] = {}
    for a in sorted(actions, key=lambda a: a.ex_date):
        if not after < a.ex_date <= last:
            continue
        ratio = used.setdefault((a.ex_date, a.kind), a.ratio)
        if abs(ratio - a.ratio) > 1e-9:
            return None, "", (f"NSE lists two {a.kind} ratios ex {a.ex_date} "
                              f"({ratio:g} and {a.ratio:g})"), LASTING
    factor = 1.0
    for ratio in used.values():
        factor *= ratio
    note = ", ".join(f"×{ratio:g} for the {kind} ex {ex}" for (ex, kind), ratio in used.items())
    return float(quote.close) * factor, note, "", ""


def grade_disagreements(rows: Iterable[dict], *, as_of: date,
                        stock_quote_on: Callable[[str, date], object] | None,
                        bench_close_on: Callable[[date], float],
                        corp_actions: Callable[[str], object] | None,
                        horizons: Iterable[int] = GRADE_HORIZONS_TD) -> list[dict]:
    """One grade per decision (`first_disagreements`) and horizon, for rows
    decided on or before `as_of`. Status "pending" while the horizon ends
    after `as_of` (no price is read); "ungraded" when the row names no
    benchmark (`decision_benchmark`), a close the benchmark needs is missing,
    or the horizon close's price basis cannot be established
    (`horizon_in_basis`, or `registry_break`; `no_basis` says why). An
    ungraded grade's `no_result` is LASTING when no later read can change
    its cause (`horizon_in_basis`'s kind, or a registry basis change), else
    TEMPORARY. Else "graded" with:

    - `return_pct`: the stock's own return, in one price basis
      (`horizon_in_basis`; `basis` names the ratios applied);
      `excess_pct`: over the Nifty (None when the Nifty is missing and the
      benchmark is cash);
    - `gap_pct`: against the row's benchmark (`return_pct` for cash,
      `excess_pct` for the Nifty), and `right`, whether the evidence rule was;
    - `result_pct`: the evidence rule's result, +gap when it kept the stock
      and -gap when it sold. `nifty_result_pct` is the same against the Nifty.

    Prices: the row's own close; the stock's close on the horizon's day, with
    its bar and source (`stock_quote_on(symbol, day)`, a pricing.SessionClose);
    the Nifty on the close's own session (`price_bar_date`, else the review
    day) and the horizon's day; nothing after the horizon's day.
    `corp_actions(symbol)` is the symbol's corp_actions.ActionRecord, read at
    grading. The benchmark is read from the row, never from today's
    configuration."""
    out: list[dict] = []
    decisions, _later = first_disagreements(
        r for r in rows if (_day(r.get("date")) or date.max) <= as_of)
    for row in decisions:
        decided = _day(row.get("date"))
        start = _day(row.get("price_bar_date"))
        if start is None or start > decided:
            start = decided
        symbol = str(row.get("symbol") or "")
        benchmark = str(row.get("benchmark") or "")
        evidence_sold = sells(row.get("evidence_verdict"))
        sign = -1 if evidence_sold else 1
        for horizon in horizons:
            matured = trading_days_after(decided, horizon)
            grade = {"date": decided.isoformat(), "symbol": symbol,
                     "buy_date": str(row.get("buy_date") or ""), "horizon_td": horizon,
                     "priced": start.isoformat(), "matures": matured.isoformat(),
                     "evidence_sold": evidence_sold, "benchmark": benchmark,
                     "status": "pending", "return_pct": None, "excess_pct": None,
                     "gap_pct": None, "result_pct": None, "nifty_result_pct": None,
                     "right": None, "basis": "", "no_basis": "", "no_result": ""}
            if matured > as_of:
                out.append(grade)
                continue
            try:
                if benchmark not in BENCHMARKS:
                    raise ValueError(f"the row names no benchmark ({benchmark!r})")
                if stock_quote_on is None:
                    raise ValueError("no stock price source")
                quote = stock_quote_on(symbol, matured)
                if getattr(quote, "close", None) is None:
                    raise ValueError("no close")
                horizon_close, grade["basis"], grade["no_basis"], kind = horizon_in_basis(
                    quote, _actions(corp_actions, symbol), start, decided)
                broken = "" if horizon_close is None else registry_break(symbol, start, matured)
                if broken:
                    horizon_close, grade["basis"], grade["no_basis"], kind = (
                        None, "", broken, LASTING)
                if horizon_close is None:
                    logger.info("[exit_shadow] %s %s @%dtd: no result (%s): %s", symbol, decided,
                                horizon, kind, grade["no_basis"])
                    grade.update(status="ungraded", no_result=kind)
                    out.append(grade)
                    continue
                ret = pct_change(float(row["close"]), horizon_close)
                try:
                    over = excess(ret, pct_change(float(bench_close_on(start)),
                                                  float(bench_close_on(matured))))
                except Exception:
                    if benchmark == "nifty":
                        raise
                    over = None
            except Exception as exc:
                logger.debug("[exit_shadow] %s %s @%dtd ungraded: %s", symbol, decided,
                             horizon, exc)
                grade.update(status="ungraded", no_result=TEMPORARY)
                out.append(grade)
                continue
            gap = ret if benchmark == "cash" else over
            grade.update(status="graded", return_pct=ret, excess_pct=over, gap_pct=gap,
                         result_pct=sign * gap,
                         nifty_result_pct=None if over is None else sign * over,
                         right=is_correct("EXIT" if evidence_sold else "HOLD", gap))
            out.append(grade)
    return out


def registry_break(symbol: str, start: date, until: date) -> str:
    """Why the instrument registry (config/instruments.yaml) puts closes of
    `symbol` from `start` and from `until` on two price bases ("" when it
    does not): a demerger or relisting it records between them
    (symbol_resolver.identity_break), which NSE's list may not show. Grading
    asks up to the horizon's day, the day its close is resolved for."""
    broken = identity_break(symbol, start, until)
    return f"the instrument registry says the {broken}" if broken else ""


def _actions(corp_actions: Callable[[str], object] | None, symbol: str):
    """The symbol's ActionRecord, or None when it could not be read (the
    basis is then unknown, never assumed)."""
    if corp_actions is None:
        return None
    try:
        return corp_actions(symbol)
    except Exception as exc:
        logger.warning("[exit_shadow] corporate actions unread for %s: %s", symbol, exc)
        return None


def _units(pct: float) -> int:
    return round(pct * _RESULT_UNITS)


def _mean(values: list[float]) -> float | None:
    return sum(_units(v) for v in values) / len(values) / _RESULT_UNITS if values else None


def tally(grades: Iterable[dict], horizon: int) -> dict:
    """Counts at one horizon: graded, right, ungraded and pending, with the
    graded decisions' mean result against their own benchmarks and, beside
    it, against the Nifty (over those the Nifty priced). `no_basis` counts
    the ungraded whose price basis is unknown (the rest had no price), and
    `no_basis_symbols` names their stocks."""
    rows = [g for g in grades if g["horizon_td"] == horizon]
    graded = [g for g in rows if g["status"] == "graded"]
    no_basis = [g for g in rows if g["status"] == "ungraded" and g.get("no_basis")]
    return {"horizon_td": horizon, "graded": len(graded),
            "right": sum(1 for g in graded if g["right"]),
            "ungraded": sum(1 for g in rows if g["status"] == "ungraded"),
            "no_basis": len(no_basis),
            "no_basis_symbols": sorted({g["symbol"] for g in no_basis}),
            "pending": sum(1 for g in rows if g["status"] == "pending"),
            "vs_cash": sum(1 for g in graded if g.get("benchmark") == "cash"),
            "vs_nifty": sum(1 for g in graded if g.get("benchmark") == "nifty"),
            "mean_result_pct": _mean([g["result_pct"] for g in graded]),
            "mean_nifty_result_pct": _mean([g["nifty_result_pct"] for g in graded
                                            if g.get("nifty_result_pct") is not None])}


def gate_look(grades: Iterable[dict]) -> dict:
    """This week's look at the switch gate. The decisions (one per holding)
    whose 30 sessions have ended are `matured`. One with a LASTING gap at 10
    sessions, at 30 or at both (`grade_disagreements`: its result can never
    be known) is set aside at both horizons and named in `set_aside` with
    its reason; the gate judges the rest. Any other missing grade never
    helps the evidence rule: it counts as not right, and it fails the money
    check at its horizon, because its result is unknown and no stand-in value
    could be guaranteed not to flatter the rule.

    - not_enough: fewer than GATE_MIN_MATURED judged, or their review days
      span less than GATE_MIN_SPAN_DAYS;
    - fail: at 10 or at 30 sessions, the evidence rule right on less than
      GATE_MIN_RIGHT_PCT, or its mean result (`grade_disagreements`) below
      GATE_MIN_MEAN_RESULT_PCT or unknown; or one stock more than
      GATE_MAX_STOCK_PCT of them;
    - cannot_judge: none of these, but more than GATE_MAX_SET_ASIDE set
      aside, or more than GATE_MAX_SET_ASIDE_PCT of `matured`. Only a pass
      becomes it, and it is never a pass (`recommends`);
    - pass: none of these. A pass means "not worse": at least as often right
      as the price-path rule, and no money lost against it. Half right is
      what a rule with no skill reaches about half the time, so a pass is
      not evidence that the rule is better. `better` is true when a pass is
      also right on at least BETTER_RIGHT_PCT at both horizons with a
      positive mean (11 of 15, unlikely by chance); it is a label only.

    Example: right on 8 of 15. The 8 saved 2% each, the 7 wrong ones cost
    10% each: (8 x 2 - 7 x 10) / 15 = -3.6% a decision. It fails. Add a
    16th, a sale of a stock that demerged three sessions later: it is set
    aside (1 of 16), and the 15 still fail."""
    by_key: dict[tuple[str, str], dict[int, dict]] = {}
    for g in grades:
        by_key.setdefault((g["date"], g["symbol"]), {})[g["horizon_td"]] = g
    matured = sorted(k for k, hs in by_key.items()
                     if GATE_HORIZON_TD in hs and hs[GATE_HORIZON_TD]["status"] != "pending")
    aside = [k for k in matured
             if any(by_key[k].get(h, {}).get("no_result") == LASTING for h in GRADE_HORIZONS_TD)]
    population = [k for k in matured if k not in aside]
    n = len(population)
    right = {h: sum(1 for k in population if by_key[k].get(h, {}).get("right") is True)
             for h in GRADE_HORIZONS_TD}
    # Money, exactly: the sum of the results in 1/10,000 of a point, and the
    # decisions with no result at that horizon.
    total, unknown = {}, {}
    for h in GRADE_HORIZONS_TD:
        got = [by_key[k].get(h) or {} for k in population]
        known = [g["result_pct"] for g in got
                 if g.get("status") == "graded" and g.get("result_pct") is not None]
        total[h] = sum(_units(v) for v in known)
        unknown[h] = n - len(known)
    days = [date.fromisoformat(d) for d, _ in population]
    span = (max(days) - min(days)).days if days else 0
    top_symbol, top_count = (Counter(s for _, s in population).most_common(1) or [("", 0)])[0]
    look = {"matured": len(matured), "judged": n,
            "set_aside": [{"date": d, "symbol": s, "reason": _lasting_reason(by_key[(d, s)])}
                          for d, s in aside],
            "right": {str(h): right[h] for h in GRADE_HORIZONS_TD},
            "mean_result_pct": {str(h): (None if unknown[h] or not n
                                         else total[h] / n / _RESULT_UNITS)
                                for h in GRADE_HORIZONS_TD},
            "unknown_result": {str(h): unknown[h] for h in GRADE_HORIZONS_TD},
            "span_days": span, "top_stock": top_symbol, "top_stock_count": top_count,
            "better": False, "reasons": []}
    if n < GATE_MIN_MATURED or span < GATE_MIN_SPAN_DAYS:
        if n < GATE_MIN_MATURED:
            look["reasons"].append(f"{n} of the {GATE_MIN_MATURED} decisions it needs "
                                   f"have reached {GATE_HORIZON_TD} sessions"
                                   + (f", not counting {len(aside)} set aside" if aside else ""))
        if span < GATE_MIN_SPAN_DAYS:
            look["reasons"].append(f"they span {span} days of the {GATE_MIN_SPAN_DAYS} "
                                   "(8 weeks) it needs")
        look["status"] = NOT_ENOUGH
        return look
    floor = _units(GATE_MIN_MEAN_RESULT_PCT) * n
    for h in GRADE_HORIZONS_TD:
        # Whole-number comparison: 8 of 16 is exactly 50%, which passes.
        if right[h] * 100 < GATE_MIN_RIGHT_PCT * n:
            look["reasons"].append(f"right on {right[h]} of {n} at {h} sessions "
                                   f"(needs {GATE_MIN_RIGHT_PCT:.0f}%)")
    for h in GRADE_HORIZONS_TD:
        if unknown[h]:
            look["reasons"].append(f"{_n(unknown[h], 'decision')} with no result at {h} "
                                   "sessions, so the money check cannot pass")
        elif total[h] < floor:
            look["reasons"].append(f"its mean result at {h} sessions is "
                                   f"{total[h] / n / _RESULT_UNITS:+.2f}% "
                                   f"(needs at least {GATE_MIN_MEAN_RESULT_PCT:+.2f}%)")
    if top_count * 100 > GATE_MAX_STOCK_PCT * n:
        look["reasons"].append(f"{top_symbol} is {top_count} of the {n} "
                               f"(more than {GATE_MAX_STOCK_PCT:.0f}%)")
    if look["reasons"]:
        look["status"] = FAIL
        return look
    # The cap, in whole numbers: 2 of 20 is exactly 10%, which it allows.
    if len(aside) > GATE_MAX_SET_ASIDE:
        look["reasons"].append(f"{len(aside)} of the {len(matured)} decisions are set aside "
                               f"(at most {GATE_MAX_SET_ASIDE} may be)")
    elif len(aside) * 100 > GATE_MAX_SET_ASIDE_PCT * len(matured):
        look["reasons"].append(f"{len(aside)} of the {len(matured)} decisions are set aside "
                               f"(more than {GATE_MAX_SET_ASIDE_PCT:.0f}%)")
    look["status"] = CANNOT_JUDGE if look["reasons"] else PASS
    look["better"] = look["status"] == PASS and all(
        right[h] * 100 >= BETTER_RIGHT_PCT * n and total[h] > 0 for h in GRADE_HORIZONS_TD)
    return look


def _lasting_reason(by_horizon: dict[int, dict]) -> str:
    """The reason of a set-aside decision's first lasting grade, by horizon."""
    return next(by_horizon[h].get("no_basis") or "" for h in GRADE_HORIZONS_TD
                if by_horizon.get(h, {}).get("no_result") == LASTING)


def recommends(look: dict, previous_look: dict | None) -> bool:
    """The switch is recommended when this week's look and the week before's
    both pass (GATE_LOOKS = 2). A week with no stored look breaks the run."""
    return (look.get("status") == PASS and isinstance(previous_look, dict)
            and previous_look.get("status") == PASS)


def scorecard_block(rows: Iterable[dict], *, as_of: date,
                    stock_quote_on: Callable[[str, date], object] | None,
                    bench_close_on: Callable[[date], float],
                    corp_actions: Callable[[str], object] | None,
                    previous_look: dict | None = None) -> dict:
    """The weekly scorecard's exit-rule block, from rows decided by `as_of`:
    `rows` holding-days reviewed, `decisions` (one per holding), and
    `repeat_days`, the later disagreeing days of the same holdings. The
    prices and corporate actions are `grade_disagreements`'s."""
    rows = [r for r in rows if (_day(r.get("date")) or date.max) <= as_of]
    decisions, later = first_disagreements(rows)
    grades = grade_disagreements(rows, as_of=as_of, stock_quote_on=stock_quote_on,
                                 bench_close_on=bench_close_on, corp_actions=corp_actions)
    look = gate_look(grades)
    return {"rows": len(rows), "decisions": len(decisions), "repeat_days": later,
            "tally": [tally(grades, h) for h in GRADE_HORIZONS_TD],
            "gate": look, "recommend": recommends(look, previous_look)}


def _n(count: int, word: str) -> str:
    return f"{count} {word}" + ("" if count == 1 else "s")


def scorecard_text(block: dict) -> str:
    """The block in plain words, for the scorecard line. Each horizon names
    the count right and the mean result against where the money went (cash
    or the Nifty, per decision), with the mean against the Nifty beside it."""
    bits = []
    for t in block["tally"]:
        if t["graded"]:
            bit = (f"at {t['horizon_td']} sessions it was right on {t['right']} of "
                   f"{t['graded']}, averaging {t['mean_result_pct']:+.2f}% a decision")
            if t.get("vs_cash"):
                bit += (f" against where the money went ({t['vs_cash']} against cash, "
                        f"{t.get('vs_nifty', 0)} against the Nifty")
                if t.get("mean_nifty_result_pct") is not None:
                    bit += f"; {t['mean_nifty_result_pct']:+.2f}% against the Nifty alone"
                bit += ")"
            else:
                bit += " against the Nifty"
            bits.append(bit)
        else:
            bits.append(f"at {t['horizon_td']} sessions none graded yet")
    text = (f"The price-path rule and the evidence rule disagreed on "
            f"{_n(block['decisions'], 'decision')} in {block['rows']} holding-days reviewed")
    if block.get("repeat_days"):
        text += (f" (a holding counts once, on the first day the rules differed; "
                 f"{_n(block['repeat_days'], 'later day')} of the same disagreements "
                 f"{'is' if block['repeat_days'] == 1 else 'are'} not counted)")
    text += "; " + "; ".join(bits) + "."
    pending = [f"{t['pending']} short of {t['horizon_td']} sessions"
               for t in block["tally"] if t["pending"]]
    missing = []
    for t in block["tally"]:
        no_price = t["ungraded"] - t.get("no_basis", 0)
        if no_price:
            missing.append(f"{no_price} with no price at {t['horizon_td']} sessions")
        if t.get("no_basis"):
            missing.append(f"{t['no_basis']} with no result at {t['horizon_td']} sessions, "
                           "as a corporate action could not be ruled out or allowed for "
                           f"({', '.join(t.get('no_basis_symbols') or [])})")
    if pending or missing:
        joined = "; ".join(pending + missing)
        text += " " + joined[0].upper() + joined[1:] + "."
    look = block["gate"]
    verdict = ("not worse than the price-path rule in count and money"
               + (f"; better: right on at least {BETTER_RIGHT_PCT:.0f}% with a positive mean"
                  if look.get("better") else ""))
    if block.get("recommend"):
        text += (f" Switch gate: passed two weeks running ({verdict}), so the evidence rule "
                 "may replace the price-path rule. The owner decides.")
    elif look["status"] == PASS:
        text += (f" Switch gate: passed this week ({verdict}); it must pass again "
                 "next week.")
    elif look["status"] == FAIL:
        text += " Switch gate: fails (" + "; ".join(look["reasons"]) + ")."
    elif look["status"] == CANNOT_JUDGE:
        text += " Switch gate: cannot judge (" + "; ".join(look["reasons"]) + ")."
    else:
        text += " Switch gate: not yet (" + "; ".join(look["reasons"]) + ")."
    aside = look.get("set_aside") or []
    if aside:
        text += (" Set aside, as " + ("its result" if len(aside) == 1 else "their results")
                 + " can never be known: "
                 + "; ".join(f"{a['symbol']}, decided {a['date']}: {a['reason']}" for a in aside)
                 + ".")
    return text


def previous_week_look(scorecards: Iterable[dict], week_monday: date) -> dict | None:
    """The gate look stored with the week before the one starting `week_monday`."""
    prev = (week_monday - timedelta(days=7)).isoformat()
    for row in scorecards:
        if row.get("week_start") == prev:
            return ((row.get("exit_rule") or {}).get("gate")
                    if isinstance(row.get("exit_rule"), dict) else None)
    return None

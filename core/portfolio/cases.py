"""
PR-005: an investment case for every position.

Every holding carries a short written case, recorded when it is bought: why
we own it (pillars, each citing its evidence), what we expect, what would
prove us wrong, and what we watch next. The explanations, the brief and the
evidence exit rule (core/portfolio/exit_shadow.py) read it.

**Written at purchase** by each buy path that opens a position: a SWITCH buy
leg and an idle-cash deployment buy (`execute_advice`, after its trades are
saved), and a manual add with an analysis (`POST /portfolio/holdings`).
Existing holdings get one from `backfill`, marked `after_purchase`, so nobody
mistakes it for the original reason. A case is never a reason to trade: a
failure to write one costs nothing but the case.

**Inputs** (`read_inputs`, pure `build_bundle`): the newest actionable
analysis (thesis, drivers, risks, price target, its fundamentals reading),
the shelf idea (band, invalidation level, conviction), the dossier's dated
guidance, and the company's events. Each was known before the case's `as_of`
(FIX-004): for a SWITCH or deployment buy, the 15:30 close of the buy's
session, the clock the buy was decided on (FIX-031); for a manual add or a
backfill, the time it is written.

**One reasoning-tier call** writes the pillars, the expectation's words, the
business conditions that would prove it wrong and what to watch. Code checks
every figure in the answer (`check_model_case`): a figure an evidence fact
cites must be a figure of that input, with the same unit; any other figure
must be one of the inputs'. "18%" is not "18.4%", and "1,200" is not
"1,200 crore". An answer that breaks a rule is not stored; the deterministic
case (`deterministic_case`) is, built from the shelf idea's own fields
copied word for word, and naming why.

**Code sets every price and date.** The invalidation price is the shelf
idea's level put into the buy day's price basis (`exit_shadow.level_in_basis`,
with RR-L1's refusals) and used only inside a window (`purchase_window`):
above the holding's stop price on the purchase day, where the stop already
covers it, and at least `advisor.case_noise_atr_mult` x ATR% below the
entry, where one ordinary day would fire it. **Example:** entry ₹500, ATR
2%, a stop of 12% (₹440, the mid-cap floor) and the noise line ₹485: a level
of ₹470 is used, ₹435 (below the stop) and ₹490 (noise) are not, and the
gap says which side. When the basis cannot be established the case has no
invalidation price and names the gap; it never stores the dive's raw level.
From then on only the holding's own applied bonuses and splits adjust it
(`level_after_buy`). A case written after the buy keeps the buy day's
rupees: its entry is the cost before the holding's bonuses and splits
(`buy_day_entry`), and a dive after the buy is put back into that basis
(`level_at_buy`). A price missing for a read that fell short (`read_gap`) is
worked again on later review days (`retry_invalidation`), a new version
when it settles. With `advisor.case_write` off (the rollback) the pipeline
neither reads cases for the evidence rule nor writes versions.

**Immutable history.** data/portfolio/<user>/cases/<SYMBOL>.jsonl holds every
version of every case of that symbol, one holding (its buy date) one case. A
change appends a version; nothing is edited. A buy path writes version 1
once: a second write for the same holding writes nothing.

**Pillar status** (`review_pillars`, each review day). A negative company
event of medium or high materiality published after the case's `as_of`, in a
category a pillar watches, marks that pillar `challenged`, citing the event.
A results event re-checks every pillar: negative, it challenges all of them;
otherwise each records the day it was checked. Each event is read once. A
challenged pillar is recorded beside the exit evidence, never a sale by
itself: only an NSE filing or a rule-typed disclosure makes `case_broken`
(advisor.CASE_EVENT_SOURCES), as before; a news article never does.
"""
from __future__ import annotations

import json
import logging
import re
import time
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Callable, Iterable

from filelock import FileLock

from core.config import settings
from backend.shared.schemas.cases import (
    CaseEvidence, CaseInput, Expectation, Invalidation, InvestmentCase, Pillar,
    PillarChallenge, WatchItem,
)
from backend.shared.schemas.events import CATEGORIES
from core.intelligence.rl.nse_calendar import IST, session_close_at

logger = logging.getLogger(__name__)

CALLER = "investment_case"
EVENT_LOOKBACK_DAYS = 60           # events older than this before as_of are not inputs
MAX_EVENTS = 10                    # the newest events, medium or high materiality
MAX_PILLARS = 4
TEXT_CHARS = 600                   # one input's text in the prompt
CHALLENGING = ("high", "medium")   # the materialities that can challenge a pillar
SYMBOL_RE = re.compile(r"^[A-Z0-9&_.-]{1,20}$")

# A figure and the unit written after it. "x" and "times" are dimensionless.
# Two-word units come first, so "1.5 lakh crore" is not read as "1.5 lakh".
_FIGURE_RE = re.compile(
    r"(?<![\d.,])(\d[\d,]*(?:\.\d+)?)\s*"
    r"(%|per\s*cent|percent|bps|(?:lakhs?|lacs?|thousand)\s*(?:crores?|cr\b)|"
    r"crores?|cr\b|lakhs?|lacs?|billion|bn\b|million|mn\b)?",
    re.IGNORECASE)
_UNITS = {"%": "%", "percent": "%", "bps": "bps", "crore": "cr", "crores": "cr", "cr": "cr",
          "lakh": "lakh", "lakhs": "lakh", "lac": "lakh", "lacs": "lakh",
          "billion": "bn", "bn": "bn", "million": "mn", "mn": "mn"}
_CRORE_OF = re.compile(r"^(lakh|lac|thousand)s?(?:crores?|cr)$")   # "lakhcrore" -> "lakh cr"


def _unit(written: str) -> str:
    unit = re.sub(r"\s+", "", (written or "").lower())
    two = _CRORE_OF.match(unit)
    if two:
        return f"{'lakh' if two.group(1) in ('lakh', 'lac') else 'thousand'} cr"
    return _UNITS.get(unit, unit)


# -- Figures ---------------------------------------------------------------------------------

def figures(text: str) -> list[tuple[float, str, str]]:
    """Every figure in `text` as (value, unit, as written). Commas are
    ignored ("1,20,000" is 120000); a figure inside a word counts ("FY27" has
    27, "Q3" has 3); the unit is the word after it, normalised ("crore",
    "Cr" -> "cr"; "per cent" -> "%"; "lakh crore", "lakh Cr" -> "lakh cr",
    and "thousand crore" -> "thousand cr", each its own unit), "" when none."""
    out = []
    for m in _FIGURE_RE.finditer(text or ""):
        token = m.group(1).rstrip(",")
        try:
            value = float(token.replace(",", ""))
        except ValueError:
            continue
        out.append((value, _unit(m.group(2)), m.group(0).strip()))
    return out


def ungrounded(text: str, source: str) -> list[str]:
    """The figures of `text` that are not figures of `source` with the same
    unit, as written. Exact: no rounding, no unit conversion."""
    have = {(v, u) for v, u, _ in figures(source)}
    return [shown for v, u, shown in figures(text) if (v, u) not in have]


# -- The store ---------------------------------------------------------------------------------

class CaseStore:
    """Append-only case history of one user, one JSONL file per symbol."""

    def __init__(self, user_id: str, base_dir: str | None = None) -> None:
        self.user_id = user_id
        self._dir = Path(base_dir or settings.PORTFOLIO_DATA_DIR) / user_id / "cases"

    def _path(self, symbol: str) -> Path:
        symbol = symbol.strip().upper()
        if not SYMBOL_RE.match(symbol):
            raise ValueError(f"not a symbol: {symbol!r}")
        return self._dir / f"{symbol}.jsonl"

    def versions(self, symbol: str, opened_on: str | None = None) -> list[InvestmentCase]:
        """Every stored version of `symbol`'s cases, oldest first; only the
        holding bought on `opened_on` when given. A line that cannot be read
        is skipped, loudly."""
        path = self._path(symbol)
        if not path.exists():
            return []
        out = []
        for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if not line.strip():
                continue
            try:
                case = InvestmentCase.model_validate_json(line)
            except ValueError as exc:
                logger.error("[cases] %s line %d unreadable: %s", path, n, exc)
                continue
            if opened_on is None or case.opened_on == opened_on:
                out.append(case)
        return out

    def latest(self, symbol: str, opened_on: str,
               before: datetime | None = None) -> InvestmentCase | None:
        """The newest version of the case of the holding bought on
        `opened_on`; only versions created before `before` when given."""
        best = None
        for case in self.versions(symbol, opened_on):
            if before is not None:
                at = _parse_time(case.created_at)
                if at is None or at >= before:
                    continue
            if best is None or case.version > best.version:
                best = case
        return best

    def append(self, case: InvestmentCase) -> bool:
        """Append `case` if it is the next version of its holding's case;
        False (nothing written) when that version exists already, so a
        re-run writes nothing."""
        path = self._path(case.symbol)
        self._dir.mkdir(parents=True, exist_ok=True)
        with FileLock(str(path) + ".lock", timeout=30):
            have = self.versions(case.symbol, case.opened_on)
            if len(have) + 1 != case.version:
                return False
            with path.open("a", encoding="utf-8", newline="\n") as fh:
                fh.write(case.model_dump_json() + "\n")
        return True

    def all_latest(self) -> list[InvestmentCase]:
        """The newest version of every case this user has, by symbol, then
        by buy date."""
        if not self._dir.exists():
            return []
        out = []
        for path in sorted(self._dir.glob("*.jsonl")):
            newest: dict[str, InvestmentCase] = {}
            for case in self.versions(path.stem):
                kept = newest.get(case.opened_on)
                if kept is None or case.version > kept.version:
                    newest[case.opened_on] = case
            out.extend(newest[k] for k in sorted(newest))
        return out


def _parse_time(stamp: str) -> datetime | None:
    try:
        at = datetime.fromisoformat(str(stamp))
    except ValueError:
        return None
    return at.replace(tzinfo=IST) if at.tzinfo is None else at.astimezone(IST)


def _now() -> datetime:
    return datetime.now(IST)


# -- The inputs ---------------------------------------------------------------------------------

@dataclass
class Bundle:
    """What a case may cite: each input's manifest entry and its text."""
    symbol: str
    as_of: datetime
    items: list[tuple[CaseInput, str]] = field(default_factory=list)
    analysis: dict | None = None           # the analysis record (A1), parsed
    idea: object | None = None             # the shelf idea (S1)
    gaps: list[str] = field(default_factory=list)

    def text(self, ref: str) -> str | None:
        return next((t for i, t in self.items if i.ref == ref), None)

    def input(self, ref: str) -> CaseInput | None:
        return next((i for i, _ in self.items if i.ref == ref), None)

    def all_text(self) -> str:
        return "\n".join(t for _, t in self.items)

    def prompt_lines(self) -> str:
        return "\n".join(f"[{i.ref}] {i.label}:\n{t[:TEXT_CHARS]}" for i, t in self.items)


def _jsonish(value) -> list:
    if isinstance(value, list):
        return value
    try:
        out = json.loads(value or "[]")
    except (TypeError, ValueError):
        return []
    return out if isinstance(out, list) else []


def _report(record: dict) -> dict:
    try:
        out = json.loads(record.get("report_json") or "{}")
    except (TypeError, ValueError):
        return {}
    return out if isinstance(out, dict) else {}


def _leaves(value, depth: int = 0) -> list[str]:
    """The text and number leaves of a nested reading, as "key: value"."""
    if depth > 3:
        return []
    out: list[str] = []
    if isinstance(value, dict):
        for k, v in value.items():
            if isinstance(v, (str, int, float)) and not isinstance(v, bool) and str(v).strip():
                out.append(f"{k}: {v}")
            else:
                out.extend(_leaves(v, depth + 1))
    elif isinstance(value, list):
        for v in value[:8]:
            out.extend(_leaves(v, depth + 1) if not isinstance(v, str) else [v])
    return out


def _analysis_before(records: Iterable[dict], symbol: str, as_of: datetime) -> dict | None:
    """The newest score-history record of `symbol` run before `as_of` whose
    decision gate lets it act (actionable or degraded)."""
    from backend.shared.pipeline import decision_gate as dg
    from core.discovery.candidates import _gate_status, _ist_time
    best, best_at = None, None
    for r in records:
        if str(r.get("ticker") or "").strip().upper() != symbol:
            continue
        at = _ist_time(r.get("run_at"))
        if at is None or at >= as_of or not dg.is_actionable(_gate_status(r)):
            continue
        if best_at is None or at > best_at:
            best, best_at = r, at
    return best


def _idea_before(ideas: Iterable, symbol: str, as_of: datetime):
    """`symbol`'s shelf idea whose latest deep dive is the newest decided
    before `as_of` (shelf.decision_time), whatever its status."""
    from core.discovery.shelf import decision_time, last_dived
    best, best_day = None, None
    for idea in ideas:
        if str(getattr(idea, "symbol", "")).strip().upper() != symbol:
            continue
        dived, decided = last_dived(idea), decision_time(idea)
        if dived is None or decided is None or decided[0] >= as_of:
            continue
        if best_day is None or dived > best_day:
            best, best_day = idea, dived
    return best


def build_bundle(symbol: str, as_of: datetime, *, records: Iterable[dict] = (),
                 ideas: Iterable = (), dossier=None, events: Iterable = ()) -> Bundle:
    """The inputs a case of `symbol` may cite, each known before `as_of`.
    Pure. A1 the analysis, F1 its fundamentals reading, S1 the shelf idea,
    D1.. the dossier's dated guidance (its undated parts only when the whole
    dossier was last updated before `as_of`'s day), E1.. the newest events."""
    from core.discovery.candidates import _ist_time
    from core.discovery.shelf import decision_time, last_dived
    from core.portfolio.exit_shadow import published_time
    symbol = symbol.strip().upper()
    b = Bundle(symbol=symbol, as_of=as_of)
    rec = _analysis_before(records, symbol, as_of)
    if rec is not None:
        report = _report(rec)
        at = _ist_time(rec.get("run_at"))
        b.analysis = dict(rec, report=report)
        lines = [f"verdict {rec.get('verdict', '')}, score {rec.get('final_score', '')}",
                 f"thesis: {rec.get('investment_thesis') or report.get('investment_thesis') or ''}"]
        lines += [f"driver: {d}" for d in _jsonish(rec.get("conviction_drivers"))[:5]]
        lines += [f"risk: {r}" for r in _jsonish(rec.get("top_risks"))[:5]]
        if report.get("price_target"):
            lines.append(f"price target: {report['price_target']}")
        if report.get("recovery_timeline_quarters"):
            lines.append(f"recovery timeline: {report['recovery_timeline_quarters']} quarters")
        b.items.append((CaseInput(ref="A1", kind="analysis", known_at=at.isoformat(),
                                  label=f"analysis run {at:%Y-%m-%d %H:%M} IST"),
                        "\n".join(lines)))
        reading = (report.get("agent_outputs") or {}).get("fundamentals")
        fund = _leaves(reading)
        if fund:
            b.items.append((CaseInput(ref="F1", kind="fundamentals", known_at=at.isoformat(),
                                      label="fundamentals read by that analysis"),
                            "\n".join(fund[:20])))
    else:
        b.gaps.append("no actionable analysis before the case")
    idea = _idea_before(ideas, symbol, as_of)
    if idea is not None:
        b.idea = idea
        decided = decision_time(idea)
        dived = last_dived(idea)
        lines = [f"deep dive of {dived.isoformat() if dived else ''}: conviction "
                 f"{getattr(idea, 'conviction', '')}, verdict {getattr(idea, 'verdict', '')}",
                 f"thesis: {getattr(idea, 'thesis', '') or '(none written)'}",
                 f"entry band: {getattr(idea, 'entry_low', '')} to {getattr(idea, 'entry_high', '')}",
                 f"invalidation level: {getattr(idea, 'invalidation_level', '')}"]
        b.items.append((CaseInput(ref="S1", kind="shelf_idea", known_at=decided[0].isoformat(),
                                  label=f"shelf idea, deep dive of {dived}"), "\n".join(lines)))
    else:
        b.gaps.append("no shelf idea decided before the case")
    if dossier is not None:
        day = as_of.date().isoformat()
        n = 0
        for g in getattr(dossier, "guidance", []) or []:
            if str(g.date)[:10] < day and str(g.status) == "open":
                n += 1
                b.items.append((CaseInput(ref=f"D{n}", kind="dossier",
                                          known_at=session_close_at(
                                              date.fromisoformat(str(g.date)[:10])).isoformat(),
                                          label=f"guidance of {g.date} ({g.source})"),
                                g.guidance))
        if str(getattr(dossier, "last_updated", "") or "9999")[:10] < day:
            for c in getattr(dossier, "recurring_catalysts", []) or []:
                n += 1
                b.items.append((CaseInput(
                    ref=f"D{n}", kind="dossier",
                    known_at=session_close_at(date.fromisoformat(
                        str(dossier.last_updated)[:10])).isoformat(),
                    label=f"recurring catalyst (dossier of {dossier.last_updated})"),
                    f"{c.name}: {c.typical_timing}; {c.expected_effect}"))
    since = as_of.date().toordinal() - EVENT_LOOKBACK_DAYS
    kept = []
    for e in events:
        at = published_time(e)
        if (str(getattr(e, "symbol", "")).upper() != symbol or at is None or at >= as_of
                or at.date().toordinal() < since or e.materiality not in CHALLENGING):
            continue
        kept.append((at, e))
    kept.sort(key=lambda p: p[0], reverse=True)
    for n, (at, e) in enumerate(kept[:MAX_EVENTS], start=1):
        b.items.append((CaseInput(ref=f"E{n}", kind="event", known_at=at.isoformat(),
                                  label=f"{e.source} {e.category} event of {at:%Y-%m-%d}, "
                                        f"{e.direction}"),
                        e.what))
    return b


def read_inputs(symbol: str, as_of: datetime, *, ideas: Iterable = (),
                sector: str = "") -> Bundle:
    """`build_bundle` over the stores: the score history, the dossier, the
    event store. A store that cannot be read is named in the bundle's gaps."""
    symbol = symbol.strip().upper()
    gaps: list[str] = []
    records: list[dict] = []
    events: list = []
    dossier = None
    try:
        from services.data.stores.score_store import ScoreStore
        records = ScoreStore().get_records(symbol)
    except Exception as exc:
        gaps.append(f"analyses unread: {exc}")
    try:
        from core.events.store import EventStore
        events = EventStore().load(symbol)
    except Exception as exc:
        gaps.append(f"company events unread: {exc}")
    try:
        from core.intelligence.rl.stores.prediction_store import PredictionStore
        dossier = PredictionStore(symbol, sector=sector or "generic").load_dossier()
    except Exception as exc:
        gaps.append(f"dossier unread: {exc}")
    b = build_bundle(symbol, as_of, records=records, ideas=ideas, dossier=dossier, events=events)
    b.gaps = gaps + b.gaps
    return b


# -- The model's case, checked ---------------------------------------------------------------

def _strip(raw: str) -> str:
    text = re.sub(r"<think>.*?</think>", "", raw or "", flags=re.DOTALL).strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text)
    return text


def check_model_case(raw: str, bundle: Bundle, header: str = "") -> tuple[dict | None, str]:
    """(the parts the model may write, "") when `raw` keeps every rule;
    (None, the first broken rule) otherwise. Rules: one JSON object; 1 to
    MAX_PILLARS pillars, each with a claim and at least one evidence fact;
    every reference an input of the bundle; every figure of an evidence fact
    a figure of the input it cites, with the same unit; every other figure a
    figure of the bundle (or of `header`, the stock and buy date it was
    told); watch categories from the event schema's."""
    try:
        data = json.loads(_strip(raw))
    except (TypeError, ValueError):
        return None, "the answer is not JSON"
    if not isinstance(data, dict):
        return None, "the answer is not a JSON object"
    pillars = data.get("pillars")
    if not isinstance(pillars, list) or not 1 <= len(pillars) <= MAX_PILLARS:
        return None, f"it gave {len(pillars) if isinstance(pillars, list) else 'no'} pillars"
    everything = bundle.all_text() + "\n" + header

    def free(text, where) -> str:
        if not isinstance(text, str):
            return f"{where} is not text"
        bad = ungrounded(text, everything)
        return f"{where} has a figure no input has: {bad[0]}" if bad else ""

    out_pillars = []
    for n, p in enumerate(pillars, start=1):
        if not isinstance(p, dict) or not str(p.get("claim") or "").strip():
            return None, f"pillar {n} has no claim"
        problem = free(p["claim"], f"pillar {n}'s claim")
        if problem:
            return None, problem
        evidence = p.get("evidence")
        if not isinstance(evidence, list) or not evidence:
            return None, f"pillar {n} cites no evidence"
        cited = []
        for ev in evidence:
            ref = str((ev or {}).get("ref") or "") if isinstance(ev, dict) else ""
            fact = (ev or {}).get("fact") if isinstance(ev, dict) else None
            source = bundle.text(ref)
            if source is None:
                return None, f"pillar {n} cites {ref or 'nothing'}, which is not an input"
            if not isinstance(fact, str) or not fact.strip():
                return None, f"pillar {n} cites {ref} with no fact"
            bad = ungrounded(fact, source)
            if bad:
                return None, f"pillar {n}'s fact from {ref} has a figure {ref} does not: {bad[0]}"
            cited.append({"fact": fact.strip(), "ref": ref})
        cats = p.get("watch_categories") or []
        if not isinstance(cats, list) or any(c not in CATEGORIES for c in cats):
            return None, f"pillar {n} watches a category that does not exist"
        out_pillars.append({"claim": p["claim"].strip(), "evidence": cited,
                            "watch_categories": sorted(set(cats))})
    expectation = data.get("expectation", "") or ""
    problem = free(expectation, "the expectation")
    if problem:
        return None, problem
    business = data.get("invalidation_business") or []
    if not isinstance(business, list):
        return None, "the business invalidation is not a list"
    for n, text in enumerate(business, start=1):
        problem = free(text, f"business invalidation {n}")
        if problem:
            return None, problem
    watch = []
    for n, w in enumerate(data.get("watch_next") or [], start=1):
        if not isinstance(w, dict):
            return None, f"watch item {n} is not an object"
        ref = str(w.get("ref") or "")
        if ref and bundle.text(ref) is None:
            return None, f"watch item {n} cites {ref}, which is not an input"
        problem = free(w.get("what", ""), f"watch item {n}")
        if problem:
            return None, problem
        watch.append({"what": str(w.get("what") or "").strip(), "ref": ref})
    one_line = data.get("one_line", "") or ""
    problem = free(one_line, "the one-line case")
    if problem:
        return None, problem
    return {"pillars": out_pillars, "expectation": expectation.strip(),
            "business": [b.strip() for b in business if b.strip()],
            "watch": [w for w in watch if w["what"]], "one_line": one_line.strip()}, ""


def _call_model(system: str, user: str) -> str:
    """One reasoning-tier JSON call, recorded like every other."""
    from services.clients.llm_client import JSON_MODE_EXTRA_BODY, get_llm_client, record_llm_call
    client = get_llm_client()
    model = settings.LLM_MODEL_REASONING
    t0 = time.time()
    try:
        resp = client.chat.completions.create(
            model=model, temperature=0.2, max_tokens=2000,
            response_format={"type": "json_object"}, extra_body=JSON_MODE_EXTRA_BODY,
            messages=[{"role": "system", "content": system}, {"role": "user", "content": user}])
    except Exception:
        record_llm_call(CALLER, model, 0, 0, int((time.time() - t0) * 1000), False)
        raise
    usage = getattr(resp, "usage", None)
    record_llm_call(CALLER, model, getattr(usage, "prompt_tokens", 0) or 0,
                    getattr(usage, "completion_tokens", 0) or 0,
                    int((time.time() - t0) * 1000), True)
    return resp.choices[0].message.content or ""


# -- The deterministic case ----------------------------------------------------------------

def _first_sentence(text: str, limit: int = 240) -> str:
    text = " ".join(str(text or "").split())
    m = re.match(r"(.+?[.!?])(\s|$)", text)
    out = m.group(1) if m else text
    return out if len(out) <= limit else out[:limit].rsplit(" ", 1)[0] + " …"


def deterministic_case(bundle: Bundle) -> dict | None:
    """The case from the inputs' own fields, copied word for word: the shelf
    idea's thesis (else the analysis's) as the pillar, its deep dive's
    conviction and verdict as the evidence, the analysis's drivers as more
    evidence and its risks as what would prove it wrong. An idea with no
    thesis says so; it never borrows words. None when there is neither an
    idea nor an analysis."""
    idea, rec = bundle.idea, bundle.analysis
    if idea is None and rec is None:
        return None
    pillars = []
    if idea is not None:
        thesis = str(getattr(idea, "thesis", "") or "").strip()
        claim = (_first_sentence(thesis) if thesis else
                 "No thesis was written; bought on its deep dive's conviction and verdict.")
        evidence = [{"fact": bundle.text("S1").splitlines()[0], "ref": "S1"}]
        pillars.append({"claim": claim, "evidence": evidence,
                        "watch_categories": ["guidance", "results"]})
    if rec is not None:
        thesis = str(rec.get("investment_thesis") or "").strip()
        drivers = [str(d) for d in _jsonish(rec.get("conviction_drivers")) if str(d).strip()]
        if not pillars:
            claim = (_first_sentence(thesis) if thesis else
                     "No thesis was written; bought on its analysis's verdict.")
            pillars.append({"claim": claim,
                            "evidence": [{"fact": bundle.text("A1").splitlines()[0],
                                          "ref": "A1"}],
                            "watch_categories": ["guidance", "results"]})
        pillars[0]["evidence"] += [{"fact": f"driver: {d}", "ref": "A1"} for d in drivers[:3]]
    risks = ([str(r) for r in _jsonish(rec.get("top_risks")) if str(r).strip()][:3]
             if rec is not None else [])
    return {"pillars": pillars, "expectation": "", "business": risks, "watch": [],
            "one_line": pillars[0]["claim"]}


# -- Prices and dates, set by code ---------------------------------------------------------

def purchase_window(entry: float, atr_pct: float, stop_pct: float,
                    mult: float | None = None) -> tuple[float, float]:
    """(stop price, noise line) on the purchase day: entry less the stop,
    and entry less `mult` x ATR% (`advisor.case_noise_atr_mult`)."""
    mult = settings.ADVISOR_CASE_NOISE_ATR_MULT if mult is None else mult
    return entry * (1 - stop_pct / 100.0), entry * (1 - mult * atr_pct / 100.0)


def buy_day_entry(holding) -> float:
    """The holding's cost in the buy day's rupees: its adjusted average
    price times the ratio of every bonus or split it applied after the buy
    (the sync divides the cost by each). Example: bought at ₹212, a 1:1 bonus
    ex later: the cost reads ₹106, and ₹212 on the buy day."""
    from core.portfolio.exit_shadow import SHARE_COUNT_KINDS
    buy = str(holding.buy_date)[:10]
    factor = 1.0
    for a in holding.applied_actions:
        if a.kind in SHARE_COUNT_KINDS and a.ratio > 0 and a.ex_date > buy:
            factor *= a.ratio
    return float(holding.adj_avg_price) * factor


def level_at_buy(level: float, dived: date, buy_day: date, symbol: str, record,
                 applied: Iterable = ()) -> tuple[float, str, str, bool]:
    """`level`, set in the rupees of a deep dive (or an analysis) on
    `dived`, in the price basis of the buy day's close. Returns (level, note,
    gap, unread); the level is 0.0 when the basis cannot be established, and
    `unread` is true when that is because NSE's list `record` did not reach
    back far enough (empty, a failed fetch, or a short list), not a refusal.

    - Dived on or before the buy day (every buy path): the dive-to-buy part
      of `exit_shadow.level_in_basis`, with RR-L1's refusals.
    - Dived after the buy (a backfill, or a manual add dated in the past):
      multiplied back by the ratio of every bonus or split that went ex after
      the buy and on or before the dive, in the holding's applied actions
      (`applied`) or NSE's list, so that `level_after_buy`, which divides by
      the holding's own, gives the dive's level again from the dive day on.
      Not established, as at purchase: NSE's list not reaching back to the
      buy day, a split or bonus row it could not read, a basis change with
      no ratio, a registry break, or a split or bonus ex on the dive day.

    Example: bought 23 Oct; a 1:1 bonus ex 2 Nov; re-dived 7 Nov with the
    level ₹100: ₹200 in the buy day's rupees, and ₹100 again from 2 Nov on."""
    from core.portfolio.exit_shadow import (BASIS_KINDS, SHARE_COUNT_KINDS, level_in_basis,
                                            registry_break)
    dive, buy = dived.isoformat(), buy_day.isoformat()
    reach = record.covers_from if record is not None else ""
    if dived <= buy_day:
        at_buy = SimpleNamespace(symbol=symbol, buy_date=buy, applied_actions=[])
        out, note, gap = level_in_basis(level, dived, at_buy, buy_day, record)
        return out, note, gap, bool(gap) and (not reach or reach > dive)
    if not reach or reach > buy:
        since = f"starts {reach}" if reach else "is empty or was not read"
        return 0.0, "", (f"a bonus or split between the buy ({buy}) and the dive ({dive}) "
                         f"cannot be ruled out: NSE's list read today {since}"), True
    applied = list(applied)
    unread = sorted(d for d in record.unparsed if buy < d <= dive)
    if unread:
        return 0.0, "", (f"NSE lists a split or bonus on {unread[0]} that could not be "
                         "read, so its price basis is unknown"), False
    changes = sorted((ex, kind) for ex, kind in record.basis_changes if buy < ex <= dive)
    changes += sorted((a.ex_date, a.kind) for a in applied
                      if a.kind in BASIS_KINDS and buy < a.ex_date <= dive)
    if changes:
        ex, kind = changes[0]
        return 0.0, "", (f"a {kind} went ex on {ex}, between the buy and the dive, and "
                         "gives no ratio, so the price basis is unknown"), False
    broken = registry_break(symbol, buy_day, dived)
    if broken:
        return 0.0, "", broken, False
    used: dict[str, object] = {}
    for a in [*applied, *record.actions]:
        if a.kind in SHARE_COUNT_KINDS and a.ratio > 0 and buy < a.ex_date <= dive:
            used.setdefault(a.key, a)
    on_dive_day = [a for a in used.values() if a.ex_date == dive]
    if on_dive_day:
        return 0.0, "", (f"a {on_dive_day[0].kind} went ex on the dive day, {dive}, so the "
                         "dive's close may be on either side of it"), False
    if not used:
        return level, "", "", False
    steps = sorted(used.values(), key=lambda a: a.ex_date)
    factor = 1.0
    for a in steps:
        factor *= a.ratio
    note = (f"{level:.2f} at the dive of {dive}, after the buy, put back into the buy day's "
            "rupees: " + ", ".join(f"the {a.kind} ex {a.ex_date} (×{a.ratio:g})"
                                   for a in steps))
    return level * factor, note, "", False


def purchase_invalidation(symbol: str, idea, buy_day: date, entry: float, record,
                          atr_pct: float, stop_pct: float, applied: Iterable = ()
                          ) -> Invalidation:
    """The case's invalidation price: the idea's level in the buy day's price
    basis (`level_at_buy`: NSE's list `record` read for the buy, and for a
    dive after the buy the holding's `applied` actions), used only when it
    lies above the stop price and at or below the noise line. Else no price,
    and the gap says why."""
    from core.discovery.shelf import last_dived
    at_dive = float(getattr(idea, "invalidation_level", 0.0) or 0.0) if idea is not None else 0.0
    if at_dive <= 0:
        return Invalidation(gap="the shelf idea set no invalidation level" if idea is not None
                            else "no shelf idea before the buy")
    return invalidation_from(symbol, at_dive, last_dived(idea), buy_day, entry, record,
                             atr_pct, stop_pct, applied)


def invalidation_from(symbol: str, at_dive: float, dived: date, buy_day: date, entry: float,
                      record, atr_pct: float, stop_pct: float, applied: Iterable = ()
                      ) -> Invalidation:
    """`purchase_invalidation` from the level `at_dive` of the deep dive on
    `dived`: what a retry recomputes from the case's own record. `entry` is
    in the buy day's rupees. A gap of a read that failed or fell short (NSE's
    list, or the ATR from the price history) is marked `read_gap`."""
    out = Invalidation(price_at_dive=at_dive, dived=dived.isoformat())
    stop = noise = None
    if atr_pct > 0 and stop_pct > 0:
        stop, noise = purchase_window(entry, atr_pct, stop_pct)
        out.stop_price, out.noise_line = round(stop, 2), round(noise, 2)
    level, note, gap, unread = level_at_buy(at_dive, dived, buy_day, symbol, record, applied)
    if gap:
        out.gap, out.read_gap = f"level {at_dive:.2f} not used: {gap}", unread
        return out
    if stop is None:
        out.gap = (f"level {level:.2f} not used: the ATR on the purchase day is unknown, so "
                   "neither side of the window can be set")
        out.read_gap = True
        return out
    if level <= stop:
        out.gap = (f"level {level:.2f} not used: at or below the stop price {stop:.2f}, "
                   "which already covers it")
        return out
    if level > noise:
        out.gap = (f"level {level:.2f} not used: above the noise line {noise:.2f} "
                   f"({settings.ADVISOR_CASE_NOISE_ATR_MULT:g} x ATR {atr_pct:.2f}% below "
                   f"the entry {entry:.2f}), where one ordinary day would fire it")
        return out
    out.price = round(level, 4)
    out.note = "; ".join(n for n in (
        note, f"inside the window: above the stop {stop:.2f}, at or below the noise line "
              f"{noise:.2f}") if n)
    return out


def _expectation(bundle: Bundle, buy_day: date, record, symbol: str,
                 applied: Iterable = ()) -> Expectation:
    """The analysis's price target in the buy day's rupees, by the same rule
    as the level (`level_at_buy`, an analysis after the buy included), and
    its recovery timeline in months."""
    rec = bundle.analysis
    if rec is None:
        return Expectation(gap="no analysis")
    report = rec.get("report") or {}
    target = report.get("price_target")
    quarters = report.get("recovery_timeline_quarters")
    out = Expectation(ref="A1",
                      horizon_months=int(quarters) * 3 if isinstance(quarters, int) and quarters > 0
                      else None)
    if not isinstance(target, (int, float)) or target <= 0:
        out.gap = "the analysis gave no price target"
        return out
    from core.discovery.candidates import _ist_day
    run_day = _ist_day(rec.get("run_at"))
    if run_day is None:
        out.gap = "the analysis's run time is unreadable"
        return out
    level, _note, gap, _unread = level_at_buy(float(target), run_day, buy_day, symbol, record,
                                              applied)
    if gap:
        out.gap = f"price target {float(target):.2f} not used: {gap}"
    else:
        out.target = round(level, 2)
    return out


def level_after_buy(case: InvestmentCase, holding, on: date, record=None
                    ) -> tuple[float, str, str]:
    """The case's invalidation price in the price basis of `on`'s close: its
    buy-day price divided by every bonus or split the holding's own record
    applied after the buy, never converted again from the dive. (0.0, "",
    gap) when the case has no price, or when after the buy NSE lists a
    basis change no ratio converts or a split or bonus it could not read,
    the holding's record holds a demerger or relisting, or the registry puts
    the buy day and `on` on two bases."""
    from core.portfolio.exit_shadow import BASIS_KINDS, SHARE_COUNT_KINDS, registry_break
    price = case.invalidation.price
    if not price:
        return 0.0, "", f"the investment case has no invalidation price: {case.invalidation.gap}"
    buy, last = case.opened_on, on.isoformat()
    unread = sorted(d for d in (record.unparsed if record is not None else ()) if buy < d <= last)
    if unread:
        return 0.0, "", (f"NSE lists a split or bonus on {unread[0]} that could not be read, "
                         "so its price basis is unknown")
    changes = sorted((ex, kind) for ex, kind in (record.basis_changes if record is not None
                                                 else ()) if buy < ex <= last)
    changes += sorted((a.ex_date, a.kind) for a in holding.applied_actions
                      if a.kind in BASIS_KINDS and buy < a.ex_date <= last)
    if changes:
        return 0.0, "", (f"a {changes[0][1]} went ex on {changes[0][0]}, after the buy, and "
                         "gives no ratio, so the price basis is unknown")
    broken = registry_break(case.symbol, date.fromisoformat(buy), on)
    if broken:
        return 0.0, "", broken
    steps = sorted((a for a in holding.applied_actions
                    if a.kind in SHARE_COUNT_KINDS and a.ratio > 0 and buy < a.ex_date <= last),
                   key=lambda a: a.ex_date)
    if not steps:
        return price, "", ""
    factor = 1.0
    for a in steps:
        factor *= a.ratio
    note = (f"{price:.2f} on the buy day, adjusted for "
            + ", ".join(f"the {a.kind} ex {a.ex_date} (÷{a.ratio:g})" for a in steps))
    return price / factor, note, ""


# -- Writing ------------------------------------------------------------------------------------

def _pillar_models(parts: dict, bundle: Bundle) -> list[Pillar]:
    out = []
    for p in parts["pillars"]:
        evidence = []
        for ev in p["evidence"]:
            src = bundle.input(ev["ref"])
            evidence.append(CaseEvidence(fact=ev["fact"], ref=ev["ref"], source=src.kind,
                                         date=src.known_at[:10]))
        out.append(Pillar(claim=p["claim"], evidence=evidence,
                          watch_categories=p["watch_categories"]))
    return out


def write_case(store: CaseStore, *, symbol: str, opened_on: date, entry_price: float,
               buy_path: str, bundle: Bundle, record=None, atr_pct: float = 0.0,
               stop_pct: float = 0.0, model: Callable[[str, str], str] | None = None,
               now: datetime | None = None, applied: Iterable = (),
               ) -> tuple[InvestmentCase | None, str]:
    """Write version 1 of the case of the holding of `symbol` bought on
    `opened_on`. Returns (the case, "") when written, (None, why) when not:
    one exists already (a re-run writes none), or nothing to build it from.

    `model` writes the words (default the reasoning tier when
    `advisor.case_model` is on); an answer that breaks a rule of
    `check_model_case`, or a call that fails, stores the deterministic case,
    naming why. `entry_price` is in the buy day's rupees; `applied` are the
    holding's applied actions, for a level or a target set after the buy."""
    symbol = symbol.strip().upper()
    if store.versions(symbol, opened_on.isoformat()):
        return None, "a case of this holding exists already"
    now = now or _now()
    written = ("at_purchase" if buy_path != "backfill" and now.date() == opened_on
               else "after_purchase")
    header = f"Stock: {symbol}. Bought on {opened_on.isoformat()}."
    parts, author, fallback = None, "model", ""
    if model is None and settings.ADVISOR_CASE_MODEL:
        model = _call_model
    if bundle.analysis is None and bundle.idea is None:
        return None, "no analysis or shelf idea before the buy to build a case from"
    if model is not None:
        from core.config.prompts.shared.investment_case import (
            INVESTMENT_CASE_SYSTEM_PROMPT, INVESTMENT_CASE_USER_TEMPLATE)
        try:
            raw = model(INVESTMENT_CASE_SYSTEM_PROMPT, INVESTMENT_CASE_USER_TEMPLATE.format(
                symbol=symbol, opened_on=opened_on.isoformat(), inputs=bundle.prompt_lines()))
            parts, fallback = check_model_case(raw, bundle, header)
        except Exception as exc:
            fallback = f"the model call failed: {type(exc).__name__}"
    else:
        fallback = "the model is off (advisor.case_model)"
    if parts is None:
        parts, author = deterministic_case(bundle), "deterministic"
    applied = list(applied)
    invalidation = purchase_invalidation(symbol, bundle.idea, opened_on, entry_price, record,
                                         atr_pct, stop_pct, applied)
    invalidation.business = parts["business"]
    expectation = _expectation(bundle, opened_on, record, symbol, applied)
    expectation.text = parts["expectation"]
    watch = [WatchItem(what=w["what"], ref=w["ref"]) for w in parts["watch"]]
    case = InvestmentCase(
        symbol=symbol, user_id=store.user_id, opened_on=opened_on.isoformat(),
        entry_price=round(float(entry_price), 4), pillars=_pillar_models(parts, bundle),
        expectation=expectation, invalidation=invalidation, watch_next=watch,
        one_line=parts["one_line"], written=written, author=author,
        fallback_reason=fallback if author == "deterministic" else "",
        buy_path=buy_path, created_at=now.isoformat(), as_of=bundle.as_of.isoformat(),
        inputs=[i for i, _ in bundle.items],
        source_run_id=str((bundle.analysis or {}).get("run_id")
                          or (bundle.analysis or {}).get("id") or ""),
        version=1, change="opened")
    if not store.append(case):
        return None, "a case of this holding exists already"
    return case, ""


# -- Pillar status -----------------------------------------------------------------------------

def review_pillars(store: CaseStore, holding, events: Iterable, on: date,
                   now: datetime | None = None) -> InvestmentCase | None:
    """Mark the pillars of `holding`'s case that `events` contradict, as a
    new version; None when nothing changed (or there is no case). Read once
    each: an event about the symbol, published after the case's `as_of` and
    before `on`'s 15:30 close (FIX-031). A negative event of medium or high
    materiality challenges every pillar watching its category; a results
    event re-checks every pillar, and challenges all of them when it is
    negative. A challenge is a record, never a sale."""
    from core.portfolio.exit_shadow import published_time
    symbol = holding.symbol.strip().upper()
    opened = str(holding.buy_date)[:10]
    case = store.latest(symbol, opened)
    if case is None:
        return None
    as_of, closed = _parse_time(case.as_of), session_close_at(on)
    read = set(case.events_read)
    new = []
    for e in events:
        at = published_time(e)
        if (str(getattr(e, "symbol", "")).upper() != symbol or at is None or e.id in read
                or as_of is None or not (as_of <= at < closed)):
            continue
        new.append((at, e))
    if not new:
        return None
    nxt = case.model_copy(deep=True)
    changes = []
    for at, e in sorted(new, key=lambda p: p[0]):
        nxt.events_read.append(e.id)
        bad = e.direction == "negative" and e.materiality in CHALLENGING
        for n, pillar in enumerate(nxt.pillars, start=1):
            why = ""
            if e.category == "results":
                pillar.last_checked = on.isoformat()
                if bad:
                    why = "negative results: every pillar is re-checked"
            elif bad and e.category in pillar.watch_categories:
                why = f"negative {e.category} event, a category this pillar watches"
            if why:
                pillar.status = "challenged"
                pillar.challenges.append(PillarChallenge(
                    event_id=e.id, published_at=e.published_at or "", source=e.source,
                    category=e.category, what=e.what, on=on.isoformat(), why=why))
                changes.append(f"pillar {n} challenged by {e.source} {e.category} of "
                               f"{at:%Y-%m-%d}")
        if e.category == "results" and not bad:
            changes.append(f"pillars re-checked on results of {at:%Y-%m-%d}")
    nxt.version = case.version + 1
    nxt.created_at = (now or _now()).isoformat()
    nxt.change = "; ".join(changes) or "events read; no pillar changed"
    return nxt if store.append(nxt) else None


def retry_invalidation(store: CaseStore, holding, record, on: date, *,
                       risk_profile: str = "balanced", history: Callable | None = None,
                       now: datetime | None = None) -> InvestmentCase | None:
    """A case whose invalidation price is missing for a read that failed or
    fell short (`read_gap`: NSE's list at the buy, or the price history) is
    worked again from this review day's reads, exactly as at purchase: the
    case's own level and dive day, its buy day and entry, the ATR to the buy
    day (`purchase_stop`), NSE's list `record` from today's sync. A result
    that settles, a price or a refusal (the window, RR-L1), is appended as a
    new version; another short read writes nothing. Nothing new is cited and
    no price after the buy day is read. Example: NSE's list unread at 16:45
    on the buy day; the next review day's sync reads it, and the case gets
    its price from the review day after (a version written after a close is
    read from the next one), well inside the minimum holding period."""
    symbol = holding.symbol.strip().upper()
    opened = str(holding.buy_date)[:10]
    case = store.latest(symbol, opened)
    if case is None or not case.invalidation.read_gap:
        return None
    old = case.invalidation
    if not old.price_at_dive or not old.dived:
        return None
    buy_day = date.fromisoformat(opened)
    atr, stop = purchase_stop(symbol, buy_day, risk_profile, history)
    inv = invalidation_from(symbol, float(old.price_at_dive), date.fromisoformat(old.dived),
                            buy_day, case.entry_price, record, atr, stop,
                            holding.applied_actions)
    if inv.read_gap:
        return None
    inv.business = list(old.business)
    nxt = case.model_copy(deep=True)
    nxt.invalidation = inv
    nxt.version = case.version + 1
    nxt.created_at = (now or _now()).isoformat()
    nxt.change = (f"invalidation price re-read on {on.isoformat()}: {inv.price:.2f} in the "
                  "buy day's rupees" if inv.price else
                  f"invalidation price re-read on {on.isoformat()}: {inv.gap}")
    return nxt if store.append(nxt) else None


def challenged_pillars(case: InvestmentCase | None) -> list[dict]:
    """The challenged pillars, for the exit evidence's record."""
    if case is None:
        return []
    return [{"claim": p.claim, "by": [c.event_id for c in p.challenges],
             "sources": sorted({c.source for c in p.challenges})}
            for p in case.pillars if p.status == "challenged"]


# -- The buy paths ------------------------------------------------------------------------------

def _price_history(symbol: str):
    from core.intelligence.algorithms.indicators.fetcher import get_price_history
    return get_price_history(symbol, years=1)


def _corp_record(symbol: str):
    from core.portfolio.corp_actions import action_record
    from services.data.fetchers.corporate_events import fetch_corp_actions
    return action_record(fetch_corp_actions(symbol), symbol)


def purchase_stop(symbol: str, buy_day: date, risk_profile: str,
                  history: Callable | None = None) -> tuple[float, float]:
    """(ATR %, stop %) on the purchase day, as the advisor computes them
    (`advisor.atr_pct` over `advisor.atr_period`, `compute_stop_pct` with
    the market-cap bucket the pipeline resolves, which reads no market cap):
    from the price history up to and including the buy day. (0.0, 0.0) when
    it cannot be read."""
    from core.portfolio.advisor import atr_pct, compute_stop_pct, resolve_cap_bucket
    try:
        df = (history or _price_history)(symbol)
        if df is None or len(df) == 0:
            return 0.0, 0.0
        df = df[[d.date() <= buy_day for d in df.index]]
        atr = atr_pct(df, settings.ADVISOR_ATR_PERIOD)
    except Exception as exc:
        logger.warning("[cases] no price history for %s: %s", symbol, exc)
        return 0.0, 0.0
    if atr <= 0:
        return 0.0, 0.0
    return atr, compute_stop_pct(atr, resolve_cap_bucket(None), risk_profile)


def write_for_buy(user_id: str, *, symbol: str, opened_on: date, entry_price: float,
                  buy_path: str, risk_profile: str = "balanced", ideas: Iterable = (),
                  sector: str = "", record=None, as_of: datetime | None = None, base_dir: str | None = None,
                  history: Callable | None = None, corp_record: Callable | None = None,
                  bundle_reader: Callable | None = None, model: Callable | None = None,
                  now: datetime | None = None, applied: Iterable = (),
                  ) -> tuple[InvestmentCase | None, str]:
    """Write the case of a buy that opened a position. Never raises: a case
    is never a reason a trade fails. `as_of` defaults to the time it is
    written; a SWITCH or deployment buy passes its session's 15:30 close.
    `entry_price` is in the buy day's rupees; `applied` are the holding's
    applied corporate actions (a backfill's, after the buy)."""
    try:
        if not settings.ADVISOR_CASE_WRITE:
            return None, "case writing is off (advisor.case_write)"
        store = CaseStore(user_id, base_dir)
        if store.versions(symbol, opened_on.isoformat()):
            return None, "a case of this holding exists already"
        now = now or _now()
        as_of = min(as_of or now, now)
        bundle = (bundle_reader or read_inputs)(symbol, as_of, ideas=ideas, sector=sector)
        if record is None:
            record = (corp_record or _corp_record)(symbol)
        atr, stop = purchase_stop(symbol, opened_on, risk_profile, history)
        return write_case(store, symbol=symbol, opened_on=opened_on, entry_price=entry_price,
                          buy_path=buy_path, bundle=bundle, record=record, atr_pct=atr,
                          stop_pct=stop, model=model, now=now, applied=applied)
    except Exception as exc:
        logger.error("[cases] case of %s/%s not written: %s", user_id, symbol, exc)
        return None, f"not written: {exc}"


def write_for_trades(user_id: str, portfolio, txns: Iterable, review_date: date, *,
                     ideas: Iterable = (), **kw) -> list[dict]:
    """After `execute_advice` saved its trades: one case for each SWITCH or
    deployment BUY that opened a position (the holding's buy date is the
    review day), from the inputs known at the review session's close."""
    held = {h.symbol: h for h in portfolio.holdings}
    out = []
    for t in txns:
        if t.side != "BUY" or t.verdict not in ("SWITCH", "DEPLOY"):
            continue
        h = held.get(t.symbol)
        if h is None or str(h.buy_date)[:10] != review_date.isoformat():
            continue
        case, why = write_for_buy(
            user_id, symbol=t.symbol, opened_on=review_date, entry_price=t.price,
            buy_path="switch" if t.verdict == "SWITCH" else "deploy",
            risk_profile=getattr(portfolio, "risk_profile", "balanced"), ideas=ideas,
            sector=h.sector, as_of=session_close_at(review_date), **kw)
        out.append({"symbol": t.symbol, "written": case is not None,
                    "author": case.author if case else "", "why": why})
    return out


def backfill(user_id: str, portfolio, *, ideas: Iterable = (), apply: bool = False,
             **kw) -> list[dict]:
    """A case for each holding without one, built from the latest inputs and
    marked `after_purchase`. A dry run (the default) writes nothing and says
    which holdings would get one. Run once, at the owner's word.

    Every price is in the buy day's rupees, as for a case written at
    purchase: the entry is the holding's cost before the bonuses and splits
    it applied since (`buy_day_entry`), and a deep dive or an analysis after
    the buy is put back into that basis (`level_at_buy`). Example: bought at
    ₹212 with the level ₹200, a 1:1 bonus since: the window is still set from
    ₹212, and the level stays ₹200 (₹100 in today's rupees)."""
    store = CaseStore(user_id, kw.get("base_dir"))
    out = []
    for h in portfolio.holdings:
        opened = str(h.buy_date)[:10]
        if store.versions(h.symbol, opened):
            out.append({"symbol": h.symbol, "opened_on": opened, "action": "has a case"})
            continue
        if not apply:
            out.append({"symbol": h.symbol, "opened_on": opened, "action": "would write"})
            continue
        case, why = write_for_buy(user_id, symbol=h.symbol, opened_on=date.fromisoformat(opened),
                                  entry_price=buy_day_entry(h), buy_path="backfill",
                                  risk_profile=getattr(portfolio, "risk_profile", "balanced"),
                                  ideas=ideas, sector=h.sector, applied=h.applied_actions,
                                  **kw)
        out.append({"symbol": h.symbol, "opened_on": opened,
                    "action": f"written ({case.author})" if case else f"not written: {why}"})
    return out

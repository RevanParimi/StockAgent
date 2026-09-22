"""PI Prospect P3 — the deep dive (plan 2026-09-21 / IPO-4a).

The first thing that wires Sprint 2 (research, extraction) and Sprint 3
(hype, substance, verdict, store) to the clock. One sweep a day at 19:00 IST,
after the 17:45 live refresh has captured the evening book, over the NSE
cache the refresh just wrote. Nothing here fetches from NSE, scores a
feature or decides anything: it ORCHESTRATES

    research_issue -> extract_substance -> read_hype / read_substance
                   -> decide_verdict -> IpoVerdictStore.append

and every stage keeps its own never-raise contract, so a dead Tavily or a
malformed ledger row degrades one reading rather than the run.

Why two slots and not one. `verdict.py` admits the spine hit-rate only when
the issue state is `closed` or `listed` (`short.evidenced`), and the
`ipo_verdicts_visible_gate` milestone counts ONLY those rows. A job that
fired purely at T-1 would write rows the gate can never count. So one cache
read yields two cohorts:

  t_minus_1   issue_end - today == ipo.deep_dive_lead_days. The expensive
              slot: Tavily research and per-document extraction. Writes the
              interim-book row, evidenced=False. Cannot be re-run tomorrow —
              tomorrow it is the close day.
  post_close  calendar state `closed` (past issue_end, no listing yet). The
              dossier and its extraction are cached, so this costs no network
              call; only the book and the calendar state have moved. Writes
              the evidenced row. Fires every evening until listing, and the
              verdict store's content-dedup rule makes the repeats free.

The extraction cache sits beside the dossier and is stamped with the
dossier's `fetched_at`: a re-fetched dossier gets a fresh extraction, a
matching one costs no LLM call, and an extraction that read nothing is never
cached (the same rule research.py applies to an empty dossier — an outage at
19:00 must not poison the window).

Why a daily sweep, not a per-issue scheduled job: close dates get extended. A
dynamically scheduled job rots silently; "who closes tomorrow?" asked every
evening cannot, and because the store key includes `close_date` an extension
re-fires a fresh analysis rather than being deduped away.

The LLM is nowhere in this file. It extracts inside extract.py and narrates
inside narrate.py; it never decides. The narration is written only for a row
that will actually be stored, and reuses the previous row's prose when the
facts digest has not moved — so an issue costs at most two notes: one at T-1
and one when the book turns final (which the note states), and the evenings
after that dedup to nothing at all.
"""
from __future__ import annotations

import json
import logging
from datetime import date, datetime
from pathlib import Path
from typing import Any, Callable
from zoneinfo import ZoneInfo

from pydantic import BaseModel, Field

from core.ipo.calendar import issue_state
from core.ipo.extract import IpoSubstance, extract_substance
from core.ipo.hype import HypeReading, read_hype
from core.ipo.narrate import IpoNarration, narrate
from core.ipo.research import ResearchDossier, _cache_path, research_issue
from core.ipo.signals import IpoSignalStore
from core.ipo.substance import SubstanceReading, read_substance
from core.ipo.verdict import IpoVerdict, decide_verdict
from core.ipo.verdicts import IpoVerdictStore

logger = logging.getLogger(__name__)

_IST = ZoneInfo("Asia/Kolkata")
_TAG = "ipo_deep_dive"

SLOTS: tuple[str, ...] = ("t_minus_1", "post_close")
_SLOT_RANK = {slot: i for i, slot in enumerate(SLOTS)}


class Candidate(BaseModel):
    symbol: str
    close_date: str
    slot: str                                   # one of SLOTS
    state: str                                  # calendar state on the sweep date
    row: dict[str, Any] = Field(default_factory=dict)


class DeepDiveResult(BaseModel):
    """What one analysis did, for the job log and the tests."""
    symbol: str
    close_date: str
    slot: str
    state: str = ""
    docs: int = 0                               # documents in the dossier
    research_cache_hit: bool = False
    research_degraded: bool = False
    docs_extracted: int = 0
    extraction_cache_hit: bool = False
    verdict: IpoVerdict = Field(default_factory=IpoVerdict)
    hype: HypeReading = Field(default_factory=HypeReading)
    substance: SubstanceReading = Field(default_factory=SubstanceReading)
    narration: IpoNarration = Field(default_factory=IpoNarration)
    written: bool = False                       # False also on the store's dedup
    unread: bool = False                        # every index dark: nothing to store
    error: str = ""


# ─────────────────────────── configuration ───────────────────────────────

def _settings() -> Any:
    from core.config import settings
    return settings


def _today_ist() -> date:
    return datetime.now(_IST).date()


# ─────────────────────────── candidate selection ─────────────────────────

def _iso(value: object) -> date | None:
    try:
        return date.fromisoformat(str(value or ""))
    except ValueError:
        return None


def _slot_of(rec: dict, on: date, lead_days: int) -> tuple[str | None, str]:
    """(slot or None, calendar state). None means this sweep has nothing to
    do for the row, and the state says why."""
    state = issue_state(rec, on)
    if state == "closed":
        return "post_close", state
    end = _iso(rec.get("issue_end"))
    if state == "open" and end is not None and (end - on).days == lead_days:
        return "t_minus_1", state
    return None, state


def _size(rec: dict) -> float:
    try:
        return float(rec.get("issue_size_cr") or 0.0)
    except (TypeError, ValueError):
        return 0.0


def candidates(cache: dict, on: date, lead_days: int | None = None,
               ) -> tuple[list[Candidate], dict[str, int]]:
    """The issues this evening's sweep should analyse, in the order the cap
    should cut them, plus a count of what was skipped and why.

    One row per symbol across every bucket — a closed-not-listed issue can sit
    in `current` or `past` depending on when NSE moved it, and `current` wins
    because it is the row the refresh enriched. Ordering: t_minus_1 first
    (it cannot be re-run tomorrow), then larger issues, then symbol, so the
    cap drops the smallest post-close re-read first.
    """
    lead = int(lead_days if lead_days is not None
               else getattr(_settings(), "IPO_DEEP_DIVE_LEAD_DAYS", 1))
    seen: dict[str, dict] = {}
    for bucket in ("current", "upcoming", "past"):
        for rec in cache.get(bucket, []) or []:
            if isinstance(rec, dict) and rec.get("symbol"):
                seen.setdefault(str(rec["symbol"]), rec)

    picked: list[Candidate] = []
    skipped: dict[str, int] = {}
    for symbol, rec in seen.items():
        if not rec.get("issue_end"):
            skipped["no_close_date"] = skipped.get("no_close_date", 0) + 1
            continue
        slot, state = _slot_of(rec, on, lead)
        if slot is None:
            skipped[state] = skipped.get(state, 0) + 1
            continue
        picked.append(Candidate(symbol=symbol, close_date=str(rec["issue_end"]),
                                slot=slot, state=state, row=rec))
    picked.sort(key=lambda c: (_SLOT_RANK[c.slot], -_size(c.row), c.symbol))
    return picked, skipped


# ─────────────────────────── extraction cache ────────────────────────────

def _substance_cache_path(research_dir: Path, symbol: str, close_date: str) -> Path:
    return _cache_path(research_dir, symbol, close_date).with_suffix(".substance.json")


def _load_cached_substance(path: Path, fetched_at: str) -> IpoSubstance | None:
    """The cached extraction, only while it belongs to the dossier in hand."""
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if str(data.get("dossier_fetched_at", "")) != fetched_at:
            return None                       # a re-fetched dossier deserves a fresh read
        out = IpoSubstance.model_validate(data.get("substance") or {})
    except Exception as exc:                  # corrupt cache is a miss, not a crash
        logger.warning("[%s] extraction cache unreadable at %s (non-fatal): %s", _TAG, path, exc)
        return None
    return out if out.docs_extracted > 0 else None


def _store_substance(path: Path, fetched_at: str, substance: IpoSubstance) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps({"dossier_fetched_at": fetched_at,
                                   "substance": substance.model_dump(mode="json")}, indent=1),
                       encoding="utf-8")
        tmp.replace(path)
    except OSError as exc:
        logger.warning("[%s] extraction cache write failed for %s (non-fatal): %s", _TAG, path, exc)


def _substance_for(dossier: ResearchDossier, research_dir: Path, *, client: Any,
                   ) -> tuple[IpoSubstance, bool]:
    """(IpoSubstance, cache_hit). Extracts only when the cache does not already
    hold a read of THIS dossier; caches only a read that found something."""
    path = _substance_cache_path(research_dir, dossier.symbol, dossier.close_date)
    cached = _load_cached_substance(path, dossier.fetched_at)
    if cached is not None:
        return cached, True
    if not dossier.docs:
        return IpoSubstance(symbol=dossier.symbol, company=dossier.company), False
    out = extract_substance(dossier, client=client)
    if out.docs_extracted > 0:
        _store_substance(path, dossier.fetched_at, out)
    return out, False


# ─────────────────────────── one issue ───────────────────────────────────

def analyse(cand: Candidate, on: date, *,
            research_dir: str | None = None,
            signal_store: IpoSignalStore | None = None,
            verdict_store: IpoVerdictStore | None = None,
            search: Callable[..., list[dict]] | None = None,
            client: Any = None) -> DeepDiveResult:
    """Research, extract, score, decide and store ONE issue. Never raises.

    The calendar state is passed to the verdict explicitly rather than read
    off the ledger: the last snapshot carrying a book was captured while the
    issue was still `open` (the capture ledger dedups identical re-reads), and
    only the calendar knows the book has since closed. That flip is exactly
    what makes the post_close row admissible evidence.
    """
    row = cand.row
    result = DeepDiveResult(symbol=cand.symbol, close_date=cand.close_date,
                            slot=cand.slot, state=cand.state)
    try:
        rdir = Path(research_dir or "data/ipo/research")
        dossier = research_issue(cand.symbol, str(row.get("company") or ""), cand.close_date,
                                 base_dir=str(rdir), search=search)
        result.docs = len(dossier.docs)
        result.research_cache_hit = dossier.cache_hit
        result.research_degraded = dossier.degraded

        research, hit = _substance_for(dossier, rdir, client=client)
        result.docs_extracted = research.docs_extracted
        result.extraction_cache_hit = hit

        snaps = (signal_store or IpoSignalStore()).load_symbol(cand.symbol)
        hype = read_hype(snaps, row, symbol=cand.symbol)
        substance = read_substance(research, snaps, row, symbol=cand.symbol)
        verdict = decide_verdict(hype, substance, row=row, symbol=cand.symbol,
                                 close_date=cand.close_date, state=cand.state)
        result.hype, result.substance, result.verdict = hype, substance, verdict
        # The capture ledger's rule, applied to verdicts: a row asserts a
        # reading was taken. No ledger snapshot and no research is "we never
        # read it", and storing that as a verdict would let a dark row pass
        # for a decision the day someone counts rows.
        if verdict.demand is None and verdict.hype is None and verdict.substance is None:
            result.unread = True
            return result
        store = verdict_store or IpoVerdictStore()
        # Narrate only what will be stored, and only what is not already
        # narrated: the dedup rule ignores the narration, so a note written
        # for a row that is then deduped is a model call spent on nothing,
        # and the post-close re-reads would otherwise pay it every evening.
        if store.is_new(verdict, hype, substance):
            previous = store.latest(cand.symbol, cand.close_date)
            result.narration = narrate(research, hype, substance, row,
                                       symbol=cand.symbol, close_date=cand.close_date,
                                       state=cand.state, client=client,
                                       previous=previous.narration if previous else None)
        result.written = store.append(verdict, hype, substance, narration=result.narration)
    except Exception as exc:
        result.error = str(exc)[:300]
        logger.warning("[%s] %s (%s) failed (non-fatal): %s", _TAG, cand.symbol, cand.slot, exc)
    return result


# ─────────────────────────── the sweep ───────────────────────────────────

def run_deep_dive_sweep(on: date | None = None, *,
                        cache_path: str | None = None,
                        research_dir: str | None = None,
                        signals_dir: str | None = None,
                        verdicts_dir: str | None = None,
                        search: Callable[..., list[dict]] | None = None,
                        client: Any = None,
                        max_issues: int | None = None) -> dict:
    """The job body. Never raises; returns a summary the scheduler logs.

    Every store and client is injectable so a test never touches `data/`.
    The cap counts ATTEMPTS, not successes — unlike the ladder budget, a run
    of failures here would spend Tavily calls on every retry, which is the
    budget the cap exists to protect.
    """
    from services.data.fetchers.ipo import load_ipo_cache

    on = on or _today_ist()
    s = _settings()
    summary: dict[str, Any] = {"on": on.isoformat(), "enabled": True, "candidates": 0,
                               "analysed": 0, "written": 0, "deduped": 0, "unread": 0, "errors": 0,
                               "over_cap": [], "skipped": {}, "pruned": 0, "issues": []}
    if not getattr(s, "IPO_DEEP_DIVE_ENABLED", True):
        summary["enabled"] = False
        return summary
    try:
        cache = load_ipo_cache(cache_path=cache_path)
        picked, skipped = candidates(cache, on)
        cap = int(max_issues if max_issues is not None
                  else getattr(s, "IPO_DEEP_DIVE_MAX_ISSUES", 5))
        summary["candidates"] = len(picked)
        summary["skipped"] = skipped
        summary["over_cap"] = [c.symbol for c in picked[cap:]]
        if summary["over_cap"]:
            logger.warning("[%s] %d candidate(s) over the per-sweep cap of %d, not analysed: %s",
                           _TAG, len(summary["over_cap"]), cap, ", ".join(summary["over_cap"]))

        signal_store = IpoSignalStore(base_dir=signals_dir)
        verdict_store = IpoVerdictStore(base_dir=verdicts_dir)
        for cand in picked[:cap]:
            res = analyse(cand, on, research_dir=research_dir, signal_store=signal_store,
                          verdict_store=verdict_store, search=search, client=client)
            summary["analysed"] += 1
            if res.error:
                summary["errors"] += 1
            elif res.written:
                summary["written"] += 1
            elif res.unread:
                summary["unread"] += 1
            else:
                summary["deduped"] += 1
            summary["issues"].append({
                "symbol": res.symbol, "close_date": res.close_date, "slot": res.slot,
                "state": res.state, "docs": res.docs, "docs_extracted": res.docs_extracted,
                "research_cache_hit": res.research_cache_hit,
                "extraction_cache_hit": res.extraction_cache_hit,
                "demand": res.verdict.demand, "hype": res.verdict.hype,
                "substance": res.verdict.substance, "lean": res.verdict.short.lean,
                "evidenced": res.verdict.short.evidenced, "written": res.written,
                "narration": res.narration.source, "unread": res.unread, "error": res.error,
            })
            logger.info("[%s] %s close=%s slot=%s docs=%d extracted=%d demand=%s substance=%s "
                        "lean=%s evidenced=%s narration=%s written=%s%s%s",
                        _TAG, res.symbol, res.close_date, res.slot, res.docs, res.docs_extracted,
                        res.verdict.demand, res.verdict.substance, res.verdict.short.lean,
                        res.verdict.short.evidenced, res.narration.source or "none", res.written,
                        " (unread: every index dark, not stored)" if res.unread else "",
                        f" error={res.error}" if res.error else "")

        try:
            summary["pruned"] = verdict_store.prune(
                older_than_days=int(getattr(s, "IPO_VERDICT_RETENTION_DAYS", 1200)))
        except Exception as exc:
            logger.warning("[%s] verdict prune failed (non-fatal): %s", _TAG, exc)
    except Exception as exc:
        summary["errors"] += 1
        summary["error"] = str(exc)[:300]
        logger.warning("[%s] sweep failed (non-fatal): %s", _TAG, exc)
    return summary

"""PI Prospect P3 — structured extraction + the corroboration gate
(plan 2026-09-21, IPO-2b / IPO-2c).

Two stages, kept separate on purpose:

  1. `extract_document` — one LLM call per fetched page, JSON in a fixed shape
     (core/config/prompts/shared/ipo_extract.py). The model reads; the code
     stamps the page's URL onto every claim it produced. A claim without a
     document behind it cannot exist here, so "a field without a source is
     discarded" is enforced by construction rather than by a check.

  2. `corroborate` — pure Python over those per-document observations. Every
     NUMBER must be stated by at least `ipo.research_min_sources` distinct
     domains within `ipo.research_agreement_tolerance`, or it is None with the
     reason recorded in `IpoSubstance.dropped`. This is ipo_gmp.py's "a lone
     number is a rumour" applied to scraped financials, which deserve at least
     the scepticism already applied to grey-market chatter. Non-numeric fields
     (promoter, anchors, flags) need one source and are labelled `reported`,
     never `corroborated`.

Dark-signal rule, with extra force for browsed figures: an unknown PAT is
None, not 0. Nothing in this module defaults a missing value to zero.

Never raises into a caller. A document the model cannot read, a truncated
response, a malformed JSON object — each degrades to "this document said
nothing", logged with the reason, and the gate runs over what remains.
"""
from __future__ import annotations

import json
import logging
import re
import time
from statistics import median
from typing import Any, Literal
from urllib.parse import urlparse

from pydantic import BaseModel, Field

from core.ipo.research import ResearchDoc, ResearchDossier

logger = logging.getLogger(__name__)

_CALLER = "ipo_extract"
Status = Literal["corroborated", "reported"]


# ─────────────────────────── output schema ────────────────────────────────

class Sourced(BaseModel):
    """One claim. `value` is None when the documents did not say (or did not
    agree). `source_url` is required whenever `value` is not None — the gate
    only ever builds a Sourced from a document, so this holds by construction;
    the validator is the tripwire for any future writer that forgets."""
    value: float | str | None = None
    source_url: str | None = None
    as_of: str | None = None            # fiscal-year label for series, else None
    label: str | None = None            # peer name for peer_pe, else None
    status: Status | None = None
    sources: list[str] = Field(default_factory=list)   # every agreeing URL

    def model_post_init(self, __context: Any) -> None:
        if self.value is not None and not self.source_url:
            raise ValueError("a Sourced value must carry a source_url")


class IpoSubstance(BaseModel):
    symbol: str = ""
    company: str = ""
    revenue_cr: list[Sourced] = Field(default_factory=list)     # oldest first, <=3
    pat_cr: list[Sourced] = Field(default_factory=list)         # same ordering
    ebitda_margin: Sourced = Field(default_factory=Sourced)
    issue_pe: Sourced = Field(default_factory=Sourced)
    peer_pe: list[Sourced] = Field(default_factory=list)
    promoter: Sourced = Field(default_factory=Sourced)
    parent_track: Sourced = Field(default_factory=Sourced)
    anchor_names: list[Sourced] = Field(default_factory=list)
    use_of_proceeds: list[Sourced] = Field(default_factory=list)
    red_flags: list[Sourced] = Field(default_factory=list)

    # Provenance of the read itself, so a thin result explains itself.
    docs_read: int = 0
    docs_extracted: int = 0             # documents that yielded a parseable object
    docs_truncated: int = 0             # finish_reason == "length" (salvaged, partial)
    dropped: list[str] = Field(default_factory=list)   # gate rejections, human-readable


class DocExtraction(BaseModel):
    """What ONE document said, after parsing and before the gate. The URL and
    domain are set by the caller from the ResearchDoc — never by the model."""
    url: str
    domain: str = ""
    kind: str = ""                      # the query kind that fetched the page
    revenue_cr: list[tuple[str, float]] = Field(default_factory=list)   # (FY label, value)
    pat_cr: list[tuple[str, float]] = Field(default_factory=list)
    ebitda_margin_pct: float | None = None
    issue_pe: float | None = None
    peer_pe: list[tuple[str, float]] = Field(default_factory=list)      # (peer name, value)
    promoter: str | None = None
    parent_track: str | None = None
    anchor_names: list[str] = Field(default_factory=list)
    use_of_proceeds: list[str] = Field(default_factory=list)
    red_flags: list[str] = Field(default_factory=list)
    truncated: bool = False

    def is_empty(self) -> bool:
        return not any((self.revenue_cr, self.pat_cr, self.peer_pe, self.anchor_names,
                        self.use_of_proceeds, self.red_flags, self.promoter, self.parent_track,
                        self.ebitda_margin_pct is not None, self.issue_pe is not None))


# ─────────────────────────── caps (config) ─────────────────────────────────

def _caps() -> dict[str, int]:
    from core.config import settings
    return {
        "max_peers": int(getattr(settings, "IPO_RESEARCH_MAX_PEERS", 5)),
        "max_anchors": int(getattr(settings, "IPO_RESEARCH_MAX_ANCHORS", 8)),
        "max_proceeds": int(getattr(settings, "IPO_RESEARCH_MAX_PROCEEDS", 5)),
        "max_flags": int(getattr(settings, "IPO_RESEARCH_MAX_FLAGS", 6)),
    }


# ─────────────────────────── parsing helpers ───────────────────────────────

_FY_RANGE = re.compile(r"(20\d{2})\s*[-–/]\s*(\d{2,4})")
_FY_SHORT = re.compile(r"FY\s*'?(\d{2,4})", re.IGNORECASE)
_YEAR = re.compile(r"(20\d{2})")


def normalise_fy(label: Any) -> str | None:
    """'FY25', 'FY2025', 'FY 2024-25', '2024-25', 'March 2025' -> 'FY2025'.
    None when no year can be read — an unlabelled figure cannot be placed in a
    series and is dropped rather than guessed."""
    s = str(label or "").strip()
    if not s:
        return None
    m = _FY_RANGE.search(s)
    if m:
        start, end = m.group(1), m.group(2)
        year = int(end) if len(end) == 4 else int(start[:2] + end)
        return f"FY{year}"
    m = _FY_SHORT.search(s)
    if m:
        y = m.group(1)
        year = int(y) if len(y) == 4 else 2000 + int(y)
        return f"FY{year}"
    m = _YEAR.search(s)
    if m:
        return f"FY{m.group(1)}"
    return None


def _num(x: Any) -> float | None:
    """A finite float or None. Strings with commas/units are NOT rescued — the
    prompt asks for plain numbers, and a model that ignored that is a model
    whose value we do not want to reinterpret."""
    if isinstance(x, bool) or x is None:
        return None
    if isinstance(x, (int, float)):
        f = float(x)
        return f if f == f and abs(f) != float("inf") else None
    return None


def _text(x: Any, limit: int) -> str | None:
    s = str(x).strip() if x is not None else ""
    return s[:limit] if s else None


def _series(raw: Any) -> list[tuple[str, float]]:
    out: dict[str, float] = {}
    for item in (raw if isinstance(raw, list) else []):
        if not isinstance(item, dict):
            continue
        fy, val = normalise_fy(item.get("as_of")), _num(item.get("value"))
        if fy and val is not None and fy not in out:
            out[fy] = val
    return sorted(out.items())[-3:]              # oldest first, latest three


def _peers(raw: Any, cap: int) -> list[tuple[str, float]]:
    out: list[tuple[str, float]] = []
    seen: set[str] = set()
    for item in (raw if isinstance(raw, list) else []):
        if not isinstance(item, dict):
            continue
        name, val = _text(item.get("name"), 80), _num(item.get("value"))
        if not name or val is None or name.lower() in seen:
            continue
        seen.add(name.lower())
        out.append((name, val))
        if len(out) >= cap:
            break
    return out


def _strings(raw: Any, cap: int, limit: int) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for item in (raw if isinstance(raw, list) else []):
        s = _text(item, limit)
        if not s or s.lower() in seen:
            continue
        seen.add(s.lower())
        out.append(s)
        if len(out) >= cap:
            break
    return out


def coerce(raw: dict, doc: ResearchDoc, caps: dict[str, int] | None = None,
           *, truncated: bool = False) -> DocExtraction:
    """Model JSON -> typed observation. Pure; re-applies every cap defensively
    so a model that ignored the prompt still cannot flood the gate."""
    caps = caps or _caps()
    raw = raw if isinstance(raw, dict) else {}
    return DocExtraction(
        url=doc.url, domain=doc.domain or _domain(doc.url), kind=doc.kind, truncated=truncated,
        revenue_cr=_series(raw.get("revenue_cr")),
        pat_cr=_series(raw.get("pat_cr")),
        ebitda_margin_pct=_num(raw.get("ebitda_margin_pct")),
        issue_pe=_num(raw.get("issue_pe")),
        peer_pe=_peers(raw.get("peer_pe"), caps["max_peers"]),
        promoter=_text(raw.get("promoter"), 200),
        parent_track=_text(raw.get("parent_track"), 200),
        anchor_names=_strings(raw.get("anchor_names"), caps["max_anchors"], 80),
        use_of_proceeds=_strings(raw.get("use_of_proceeds"), caps["max_proceeds"], 120),
        red_flags=_strings(raw.get("red_flags"), caps["max_flags"], 160),
    )


def _domain(url: str) -> str:
    try:
        host = urlparse(url).netloc.lower()
    except ValueError:
        return ""
    return host[4:] if host.startswith("www.") else host


def salvage_partial_object(raw: str) -> dict:
    """Recover what closed cleanly from a truncated top-level JSON object.

    The house `salvage_truncated_json` cuts at the last top-level key whose
    value is an OBJECT — right for the narrator/curator shapes, useless here,
    where every top-level value is a list or a scalar (a cut inside
    `"pat_cr": [...` salvaged zero keys in testing). This walks the same
    string/escape state but also accepts a closed `]` at depth 1 and a `,`
    at depth 1 (a completed scalar) as cut points. Returns {} when nothing
    can be recovered. Never raises.
    """
    if not raw:
        return {}
    depth, in_string, escape, cut = 0, False, False, None
    for i, ch in enumerate(raw):
        if in_string:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
        elif ch in "{[":
            depth += 1
        elif ch in "}]":
            depth -= 1
            if depth == 1:
                cut = i + 1                    # a top-level list/object value just closed
        elif ch == "," and depth == 1:
            cut = i                            # a top-level scalar value is complete
    if cut is None:
        return {}
    try:
        parsed = json.loads(raw[:cut].rstrip().rstrip(",") + "}")
    except (json.JSONDecodeError, ValueError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


# ─────────────────────────── stage 1: the LLM read ─────────────────────────

def extract_document(doc: ResearchDoc, company: str, symbol: str, *,
                     client: Any = None, model: str | None = None,
                     caps: dict[str, int] | None = None) -> DocExtraction | None:
    """One document -> DocExtraction, or None when nothing usable came back.

    Truncation (`finish_reason == "length"`) is logged distinctly from
    malformation and salvaged with the house `salvage_truncated_json`; what
    survives is partial-with-provenance, never invented.
    """
    from core.config import settings
    from core.config.prompts.shared.ipo_extract import (
        IPO_EXTRACT_SYSTEM_PROMPT, IPO_EXTRACT_USER_TEMPLATE)
    from services.clients.llm_client import (
        JSON_MODE_EXTRA_BODY, get_llm_client, record_llm_call, salvage_truncated_json)

    caps = caps or _caps()
    model = model or settings.LLM_MODEL_BULK
    max_tokens = int(getattr(settings, "IPO_RESEARCH_EXTRACT_MAX_TOKENS", 900))
    started = time.time()
    try:
        client = client or get_llm_client()
        resp = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": IPO_EXTRACT_SYSTEM_PROMPT.format(**caps)},
                {"role": "user", "content": IPO_EXTRACT_USER_TEMPLATE.format(
                    company=company, symbol=symbol, title=doc.title, content=doc.content)},
            ],
            temperature=0.0,            # extraction is a reading, not a sample
            max_tokens=max_tokens,
            response_format={"type": "json_object"},
            extra_body=JSON_MODE_EXTRA_BODY,
        )
        choice = resp.choices[0]
        raw = choice.message.content or ""
        truncated = getattr(choice, "finish_reason", None) == "length"
        try:
            data = json.loads(raw)
            parsed = True
        except (json.JSONDecodeError, ValueError):
            data = salvage_truncated_json(raw) or salvage_partial_object(raw)
            parsed = False
        if truncated:
            # Logged distinctly from malformation: a cap hit is a sizing bug
            # (the prompt's list caps are meant to make this unreachable), a
            # malformed object is a model bug. Both salvage to partial.
            logger.warning("[%s] response TRUNCATED at %d tokens for %s (%s) — %s",
                           _CALLER, max_tokens, symbol, doc.domain,
                           "JSON still parsed" if parsed else f"salvaged {len(data)} key(s)")
        elif not parsed:
            logger.warning("[%s] malformed JSON for %s (%s) — salvaged %d key(s)",
                           _CALLER, symbol, doc.domain, len(data))
        usage = getattr(resp, "usage", None)
        record_llm_call(_CALLER, model, getattr(usage, "prompt_tokens", 0) or 0,
                        getattr(usage, "completion_tokens", 0) or 0,
                        int((time.time() - started) * 1000), True)
        return coerce(data if isinstance(data, dict) else {}, doc, caps, truncated=truncated)
    except Exception as exc:
        logger.warning("[%s] extraction failed for %s (%s) (non-fatal): %s",
                       _CALLER, symbol, doc.domain, exc)
        try:
            record_llm_call(_CALLER, model, 0, 0, int((time.time() - started) * 1000), False)
        except Exception:
            pass
        return None


# ─────────────────────────── stage 2: the gate ─────────────────────────────

def _agree(values: list[float], tolerance: float) -> bool:
    """ipo_gmp's spread rule: relative to the smaller magnitude, so it holds
    for negative PAT; two exact zeros agree; a zero against a non-zero never
    does (there is no magnitude to measure the spread against)."""
    lo, hi = min(values), max(values)
    if lo == hi:
        return True
    reference = min(abs(lo), abs(hi))
    if reference == 0:
        return False
    return (hi - lo) / reference <= tolerance


def _gate_number(field: str, obs: list[tuple[str, str, float]], *,
                 min_sources: int, tolerance: float, dropped: list[str],
                 as_of: str | None = None, label: str | None = None) -> Sourced:
    """`obs` is (domain, url, value). One value per DOMAIN — an aggregator
    echoed across two of its own pages is one source, not two."""
    by_domain: dict[str, tuple[str, float]] = {}
    for domain, url, value in obs:
        if domain and domain not in by_domain:
            by_domain[domain] = (url, value)
    tag = field + (f"[{as_of}]" if as_of else "") + (f"[{label}]" if label else "")
    if not by_domain:
        return Sourced(as_of=as_of, label=label)
    if len(by_domain) < min_sources:
        dropped.append(f"{tag}: {len(by_domain)} source(s), need {min_sources} — "
                       f"{next(iter(by_domain))} said {next(iter(by_domain.values()))[1]:g}")
        return Sourced(as_of=as_of, label=label)
    values = [v for _u, v in by_domain.values()]
    if not _agree(values, tolerance):
        detail = ", ".join(f"{d}={v:g}" for d, (_u, v) in by_domain.items())
        dropped.append(f"{tag}: sources disagree beyond {tolerance:.0%} ({detail})")
        return Sourced(as_of=as_of, label=label)
    urls = [u for u, _v in by_domain.values()]
    return Sourced(value=float(median(values)), source_url=urls[0], as_of=as_of, label=label,
                   status="corroborated", sources=urls)


def _reported_one(obs: list[tuple[str, str]]) -> Sourced:
    """First non-empty text, labelled `reported`."""
    for url, text in obs:
        if text:
            return Sourced(value=text, source_url=url, status="reported", sources=[url])
    return Sourced()


def _reported_many(obs: list[tuple[str, str]], cap: int) -> list[Sourced]:
    out: list[Sourced] = []
    seen: set[str] = set()
    for url, text in obs:
        key = text.lower()
        if not text or key in seen:
            continue
        seen.add(key)
        out.append(Sourced(value=text, source_url=url, status="reported", sources=[url]))
        if len(out) >= cap:
            break
    return out


def corroborate(extractions: list[DocExtraction], *, symbol: str = "", company: str = "",
                min_sources: int | None = None, tolerance: float | None = None,
                caps: dict[str, int] | None = None) -> IpoSubstance:
    """Pure. Per-document observations -> one IpoSubstance with every number
    either corroborated or None-with-a-reason."""
    from core.config import settings
    min_sources = int(min_sources if min_sources is not None
                      else getattr(settings, "IPO_RESEARCH_MIN_SOURCES", 2))
    tolerance = float(tolerance if tolerance is not None
                      else getattr(settings, "IPO_RESEARCH_AGREEMENT_TOLERANCE", 0.25))
    caps = caps or _caps()
    out = IpoSubstance(symbol=symbol, company=company,
                       docs_extracted=len(extractions),
                       docs_truncated=sum(1 for e in extractions if e.truncated))
    gate = dict(min_sources=min_sources, tolerance=tolerance, dropped=out.dropped)

    # Series: corroborate per fiscal year, keep the latest three that survive.
    for field in ("revenue_cr", "pat_cr"):
        by_fy: dict[str, list[tuple[str, str, float]]] = {}
        for e in extractions:
            for fy, val in getattr(e, field):
                by_fy.setdefault(fy, []).append((e.domain, e.url, val))
        kept = [s for fy in sorted(by_fy)
                if (s := _gate_number(field, by_fy[fy], as_of=fy, **gate)).value is not None]
        setattr(out, field, kept[-3:])

    out.ebitda_margin = _gate_number(
        "ebitda_margin", [(e.domain, e.url, e.ebitda_margin_pct) for e in extractions
                          if e.ebitda_margin_pct is not None], **gate)
    out.issue_pe = _gate_number(
        "issue_pe", [(e.domain, e.url, e.issue_pe) for e in extractions
                     if e.issue_pe is not None], **gate)

    by_peer: dict[str, tuple[str, list[tuple[str, str, float]]]] = {}
    for e in extractions:
        for name, val in e.peer_pe:
            key = name.lower()
            by_peer.setdefault(key, (name, []))[1].append((e.domain, e.url, val))
    peers = [s for _k, (name, obs) in sorted(by_peer.items())
             if (s := _gate_number("peer_pe", obs, label=name, **gate)).value is not None]
    out.peer_pe = peers[:caps["max_peers"]]

    # Reported (non-numeric) fields take the first statement, so order matters:
    # the pages the matching query found come first, the rest keep dossier order.
    def _by_kind(kind: str) -> list[DocExtraction]:
        return sorted(extractions, key=lambda e: e.kind != kind)

    out.promoter = _reported_one([(e.url, e.promoter or "") for e in _by_kind("promoter")])
    out.parent_track = _reported_one([(e.url, e.parent_track or "") for e in _by_kind("promoter")])
    out.anchor_names = _reported_many(
        [(e.url, s) for e in _by_kind("anchor") for s in e.anchor_names], caps["max_anchors"])
    out.use_of_proceeds = _reported_many(
        [(e.url, s) for e in _by_kind("proceeds") for s in e.use_of_proceeds], caps["max_proceeds"])
    out.red_flags = _reported_many(
        [(e.url, s) for e in _by_kind("risks") for s in e.red_flags], caps["max_flags"])
    return out


# ─────────────────────────── the whole read ────────────────────────────────

def extract_substance(dossier: ResearchDossier, *, client: Any = None,
                      model: str | None = None) -> IpoSubstance:
    """Dossier -> IpoSubstance. Never raises; an empty dossier yields an empty
    (all-None) result whose `docs_read == 0` says why."""
    caps = _caps()
    extractions: list[DocExtraction] = []
    for doc in dossier.docs:
        try:
            got = extract_document(doc, dossier.company, dossier.symbol,
                                   client=client, model=model, caps=caps)
        except Exception as exc:                 # extract_document already catches; belt and braces
            logger.warning("[%s] unexpected failure on %s (non-fatal): %s", _CALLER, doc.url, exc)
            got = None
        if got is not None and not got.is_empty():
            extractions.append(got)
    try:
        out = corroborate(extractions, symbol=dossier.symbol, company=dossier.company, caps=caps)
    except Exception as exc:
        logger.warning("[%s] corroboration failed for %s (non-fatal): %s", _CALLER, dossier.symbol, exc)
        out = IpoSubstance(symbol=dossier.symbol, company=dossier.company)
    out.docs_read = len(dossier.docs)
    return out

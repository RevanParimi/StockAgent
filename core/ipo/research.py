"""PI Prospect P3 — the browsing layer (plan 2026-09-21, IPO-2a).

Gathers the open-web documents a Substance read needs for one issue: RHP
financials, valuation against peers, the promoter's record, the anchor book,
use of proceeds, and risks. This module FETCHES; it never interprets. What it
returns is a dossier of documents with URLs, and every later claim about the
issue must point back into it (extract.py stamps the document URL onto each
figure — the model is never asked for a URL it could invent).

Budget shape: this runs once per issue at T-1, not daily, which is what lets
it be far deeper than the pipeline's 2-call Tavily allowance. Six fetches for
fifteen issues a month is ~90 of the 1,000/month free tier.

Cache: one JSON per (symbol, close_date) under data/ipo/research/. A re-run
inside one window costs nothing. An EMPTY result is never cached — a Tavily
outage at 19:00 must not poison the whole window with "no documents".

Never raises into a caller: an unconfigured or dead Tavily yields a dossier
with no documents, and the caller renders nothing rather than something wrong.
"""
from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable
from urllib.parse import urlparse

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

# One query per kind, in priority order: when `research_max_fetches` is
# smaller than this list the tail is what gets dropped, so financials and
# valuation come first. The company name is the anchor; the symbol alone is
# ambiguous on the open web (NSE, SONA, LEAP ...).
QUERY_KINDS: tuple[tuple[str, str], ...] = (
    ("financials", "{company} IPO RHP revenue profit after tax FY23 FY24 FY25 financials"),
    ("valuation",  "{company} IPO valuation P/E versus listed peers price band"),
    ("promoter",   "{company} IPO promoter background parent company track record"),
    ("anchor",     "{company} IPO anchor investors allotment list"),
    ("proceeds",   "{company} IPO objects of the issue use of proceeds fresh issue OFS"),
    ("risks",      "{company} IPO risk factors litigation red flags analysts caution"),
)

_SAFE = re.compile(r"[^A-Za-z0-9_-]+")


class ResearchDoc(BaseModel):
    kind: str                       # which QUERY_KINDS entry found it
    title: str = ""
    url: str
    domain: str = ""
    content: str = ""
    published_date: str = ""
    score: float = 0.0


class ResearchDossier(BaseModel):
    symbol: str
    company: str = ""
    close_date: str = ""            # ISO; part of the cache key
    fetched_at: str = ""            # ISO-8601 UTC
    queries: list[str] = Field(default_factory=list)
    docs: list[ResearchDoc] = Field(default_factory=list)
    fetches_used: int = 0
    cache_hit: bool = False
    degraded: bool = False          # True when Tavily was unconfigured or every call failed

    @property
    def domains(self) -> set[str]:
        return {d.domain for d in self.docs if d.domain}


def query_plan(company: str, symbol: str, max_fetches: int | None = None) -> list[tuple[str, str]]:
    """(kind, query) pairs for one issue, capped at `max_fetches`.

    Strips the legal suffix so the query reads the way the press writes the
    name: "Varmora Granito IPO ..." finds more than "Varmora Granito Limited
    IPO ...". The symbol is appended only when it is a real word-like token,
    because a bare "NSE" would swamp the results with exchange pages.
    """
    from core.config import settings
    cap = int(max_fetches if max_fetches is not None
              else getattr(settings, "IPO_RESEARCH_MAX_FETCHES", 6))
    name = re.sub(r"\s+(limited|ltd\.?|private limited|pvt\.? ltd\.?)$", "", (company or "").strip(),
                  flags=re.IGNORECASE) or (symbol or "").strip()
    if not name:
        return []
    plan = [(kind, tmpl.format(company=name)) for kind, tmpl in QUERY_KINDS]
    return plan[:max(cap, 0)]


def _domain(url: str) -> str:
    try:
        host = urlparse(url).netloc.lower()
    except ValueError:
        return ""
    return host[4:] if host.startswith("www.") else host


def _cache_path(base_dir: Path, symbol: str, close_date: str) -> Path:
    stem = _SAFE.sub("_", f"{symbol}_{close_date or 'nodate'}")
    return base_dir / f"{stem}.json"


def _load_cached(path: Path) -> ResearchDossier | None:
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        dossier = ResearchDossier.model_validate(data)
    except Exception as exc:                      # corrupt cache is a miss, not a crash
        logger.warning("[ipo_research] cache unreadable at %s (non-fatal): %s", path, exc)
        return None
    if not dossier.docs:
        return None                               # never trust a cached empty result
    dossier.cache_hit = True
    return dossier


def _store(path: Path, dossier: ResearchDossier) -> None:
    """Rewrite via .tmp + replace (Windows/OneDrive rule)."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(dossier.model_dump_json(indent=1), encoding="utf-8")
        tmp.replace(path)
    except OSError as exc:
        logger.warning("[ipo_research] cache write failed for %s (non-fatal): %s", path, exc)


def research_issue(
    symbol: str,
    company: str,
    close_date: str = "",
    *,
    base_dir: str | None = None,
    search: Callable[..., list[dict]] | None = None,
    max_fetches: int | None = None,
) -> ResearchDossier:
    """The dossier for one issue. Cached per (symbol, close_date).

    `search` is injectable for tests and defaults to the shared Tavily client,
    which already records the call against the monthly counter and returns []
    on any failure. Documents are de-duplicated by URL across queries — the
    same RHP summary page answering two questions is one document, so a later
    corroboration count cannot be inflated by the query plan itself.
    """
    from core.config import settings

    dossier = ResearchDossier(symbol=symbol, company=company, close_date=close_date,
                              fetched_at=datetime.now(timezone.utc).isoformat(timespec="seconds"))
    if not getattr(settings, "IPO_RESEARCH_ENABLED", True):
        dossier.degraded = True
        return dossier

    cache_dir = Path(base_dir or "data/ipo/research")
    path = _cache_path(cache_dir, symbol, close_date)
    cached = _load_cached(path)
    if cached is not None:
        return cached

    if search is None:
        if not getattr(settings, "TAVILY_API_KEY", ""):
            logger.info("[ipo_research] TAVILY_API_KEY not set — %s gets no research documents", symbol)
            dossier.degraded = True
            return dossier
        from services.clients.tavily_fetcher import search_tavily
        search = search_tavily

    per_query = int(getattr(settings, "IPO_RESEARCH_RESULTS_PER_QUERY", 3))
    max_chars = int(getattr(settings, "IPO_RESEARCH_MAX_CONTENT_CHARS", 6000))
    seen: set[str] = set()
    failures = 0
    plan = query_plan(company, symbol, max_fetches)
    for kind, query in plan:
        dossier.queries.append(query)
        dossier.fetches_used += 1
        try:
            results = search(query, max_results=per_query) or []
        except Exception as exc:                  # the client swallows, but a test double may not
            logger.warning("[ipo_research] %s query failed for %s (non-fatal): %s", kind, symbol, exc)
            results = []
        if not results:
            failures += 1
            continue
        for item in results:
            url = str(item.get("url") or "").strip()
            content = str(item.get("content") or "").strip()
            if not url or not content or url in seen:
                continue
            seen.add(url)
            dossier.docs.append(ResearchDoc(
                kind=kind, title=str(item.get("title") or ""), url=url, domain=_domain(url),
                content=content[:max_chars], published_date=str(item.get("published_date") or ""),
                score=float(item.get("score") or 0.0),
            ))

    dossier.degraded = bool(plan) and failures == len(plan)
    if dossier.docs:
        _store(path, dossier)
    else:
        logger.warning("[ipo_research] no documents for %s (%d queries, %d failed) — not cached",
                       symbol, len(plan), failures)
    return dossier

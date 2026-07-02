"""
EventIngestor — event-driven dossier ingestion (RL Phase 3).

Scans NSE corporate announcements + board meetings for qualifying events
(results, concalls, guidance, investor presentations), enriches each with a
text bundle (announcement text + one Tavily page), digests it via the LLM into
the SAME JSON contract the daily DossierCurator emits, and applies it through
the SAME bounded merge (`merge_curator_output`). Weekly scan + on-demand CLI.

Contract: `EventIngestor.run` NEVER raises — any failure is logged and that
event (or the whole run) is skipped, returning the dossier unchanged.
"""
from __future__ import annotations

import json
import logging
from datetime import date as _date, timedelta

from backend.shared.schemas.dossier import TickerDossier
from backend.shared.schemas.feedback import EVENT_TAGS
from core.config import settings
from core.config.prompts.shared.event_ingestor import (
    EVENT_SYSTEM_PROMPT, EVENT_USER_TEMPLATE,
)
from core.intelligence.rl.agents.dossier_curator import (
    _strip_think, merge_curator_output,
)
from services.clients.tavily_fetcher import fetch_tavily_context
from services.data.fetchers.nse_announcements import prefetch_nse_data
from services.data.fetchers.nse_key_registry import resolve_field

logger = logging.getLogger(__name__)

# Cap on the rolling ingested_event_keys watermark (mirrors spec §3).
_MAX_INGESTED_EVENT_KEYS = 40

# Cap on business_summary_update length (same bound as DossierCurator/distill).
_BUSINESS_SUMMARY_MAX_CHARS = 500

# ---------------------------------------------------------------------------
# Component 1 — Event scan (pure, static)
# ---------------------------------------------------------------------------

QUALIFYING_KEYWORDS = (
    "result", "earnings", "concall", "conference call", "transcript", "guidance",
    "investor presentation", "investor meet", "analyst", "dividend",
    "board meeting outcome", "financial statement",
)


def _is_qualifying(subject: str) -> bool:
    """Case-insensitive substring match against QUALIFYING_KEYWORDS. Pure."""
    if not subject:
        return False
    s = subject.lower()
    return any(kw in s for kw in QUALIFYING_KEYWORDS)


def _parse_item_date(raw: str) -> _date | None:
    """Best-effort parse of an NSE date field. Returns None if unparseable."""
    if not raw:
        return None
    try:
        from dateutil import parser as _dp
        return _dp.parse(str(raw), dayfirst=True).date()
    except Exception:
        return None


def find_qualifying_events(ticker: str, lookback_days: int,
                            exclude_keys: set[str] | None = None) -> list[dict]:
    """Scan NSE announcements + board meetings for qualifying events.

    Returns at most settings.EVENT_INGEST_MAX_EVENTS_PER_SCAN normalized dicts
    with keys {"date", "subject", "description", "key"}, newest-first.
    Items already in `exclude_keys` (the dossier watermark) are skipped here
    as a convenience, but watermark filtering is primarily the caller's
    (run()) responsibility — this function stays store-free.

    Never raises: any prefetch/parsing failure yields an empty list.
    """
    exclude_keys = exclude_keys or set()
    cutoff = _date.today() - timedelta(days=lookback_days)

    try:
        nse_data = prefetch_nse_data(ticker)
    except Exception as exc:
        logger.warning("[EventIngestor] %s: prefetch_nse_data failed: %s", ticker, exc)
        return []

    key_mappings = nse_data.get("key_mappings", {}) or {}
    candidates: list[tuple[_date, dict]] = []

    for section, endpoint in (("announcements", "announcements"),
                               ("board_meetings", "board_meetings")):
        items = nse_data.get(section, []) or []
        mapping = key_mappings.get(endpoint, {}) or {}
        for item in items:
            if not isinstance(item, dict):
                continue
            desc = resolve_field(item, mapping, "desc", endpoint)
            dt_raw = resolve_field(item, mapping, "date", endpoint)
            if not desc:
                continue
            if not _is_qualifying(desc):
                continue
            item_date = _parse_item_date(dt_raw)
            if item_date is None:
                continue  # unparseable date — skip defensively
            if item_date < cutoff:
                continue

            date_iso = item_date.isoformat()
            description = ""
            attach = resolve_field(item, mapping, "attachment", endpoint) if endpoint == "announcements" else ""
            if attach and attach.lower() != desc.lower():
                description = attach

            key = f"{date_iso}|{desc[:60]}"
            if key in exclude_keys:
                continue

            candidates.append((item_date, {
                "date": date_iso,
                "subject": desc,
                "description": description,
                "key": key,
            }))

    candidates.sort(key=lambda pair: pair[0], reverse=True)
    cap = settings.EVENT_INGEST_MAX_EVENTS_PER_SCAN
    return [c[1] for c in candidates[:cap]]


# ---------------------------------------------------------------------------
# Component 2 — Enrichment
# ---------------------------------------------------------------------------

def _build_bundle(ticker: str, event: dict) -> str:
    """Build the text bundle for a qualifying event: subject + description +
    one Tavily full-page extraction. Truncated to EVENT_INGEST_TEXT_MAX_CHARS.

    Tavily failure or absence (no TAVILY_API_KEY) -> bundle without it.
    Never raises.
    """
    parts: list[str] = []
    subject = event.get("subject", "")
    description = event.get("description", "")
    if subject:
        parts.append(f"Subject: {subject}")
    if description:
        parts.append(f"Description: {description}")

    try:
        query = f"{ticker} {subject} earnings guidance"
        tavily_text = fetch_tavily_context([query], max_queries=1, max_results_per_query=1)
        if tavily_text and "No Tavily" not in tavily_text:
            parts.append(tavily_text)
    except Exception as exc:
        logger.debug("[EventIngestor] %s: Tavily enrichment skipped: %s", ticker, exc)

    bundle = "\n\n".join(parts)
    return bundle[: settings.EVENT_INGEST_TEXT_MAX_CHARS]


# ---------------------------------------------------------------------------
# Component 3 — Digestion (LLM) + merge reuse
# ---------------------------------------------------------------------------

class EventIngestor:
    """LLM client pattern mirrors DossierCurator (json_object, low temp, retry-free)."""

    def _call_llm(self, system_prompt: str, user_prompt: str) -> str:
        from services.clients.llm_client import JSON_MODE_EXTRA_BODY, get_llm_client
        client = get_llm_client()
        resp = client.chat.completions.create(
            model=settings.LLM_MODEL,
            temperature=0.2,
            max_tokens=900,
            response_format={"type": "json_object"},
            extra_body=JSON_MODE_EXTRA_BODY,
            messages=[{"role": "system", "content": system_prompt},
                      {"role": "user", "content": user_prompt}],
        )
        return resp.choices[0].message.content or ""

    # ------------------------------------------------------------------

    def run(self, ticker: str, sector: str, lookback_days: int | None = None) -> int:
        """Scan -> enrich -> digest -> merge -> save. Returns events ingested.

        NEVER raises. Flag off (RL_EVENT_INGEST_ENABLED=False) -> 0, no I/O.
        """
        from core.intelligence.rl.stores.prediction_store import PredictionStore

        if not getattr(settings, "RL_EVENT_INGEST_ENABLED", True):
            return 0

        try:
            days = lookback_days if lookback_days is not None else settings.EVENT_INGEST_LOOKBACK_DAYS
            store = PredictionStore(ticker, sector=sector)
            today_iso = _date.today().isoformat()

            dossier = store.load_dossier() or TickerDossier(
                ticker=ticker, sector=sector,
                created_at=today_iso, last_updated=today_iso)

            exclude_keys = set(dossier.ingested_event_keys)
            events = find_qualifying_events(ticker, days, exclude_keys=exclude_keys)
            events = [e for e in events if e["key"] not in exclude_keys]

            ingested = 0
            for event in events:
                try:
                    bundle = _build_bundle(ticker, event)
                    system = EVENT_SYSTEM_PROMPT.format(
                        ticker=ticker, sector=sector,
                        event_tags=", ".join(sorted(EVENT_TAGS)))
                    user = EVENT_USER_TEMPLATE.format(
                        ticker=ticker, sector=sector,
                        event_date=event["date"], event_subject=event["subject"],
                        bundle_text=bundle,
                    )
                    raw = self._call_llm(system, user)
                    data = json.loads(_strip_think(raw))

                    merge_curator_output(dossier, data, today=event["date"], outcome_link="")

                    summary_update = (data.get("business_summary_update") or "").strip()
                    if summary_update:
                        dossier.business_summary = summary_update[:_BUSINESS_SUMMARY_MAX_CHARS]

                    dossier.ingested_event_keys.append(event["key"])
                    if len(dossier.ingested_event_keys) > _MAX_INGESTED_EVENT_KEYS:
                        dossier.ingested_event_keys = dossier.ingested_event_keys[-_MAX_INGESTED_EVENT_KEYS:]

                    ingested += 1
                except Exception as exc:
                    logger.warning("[EventIngestor] %s: failed to ingest event %s: %s",
                                   ticker, event.get("key", "?"), exc)
                    continue

            if ingested:
                store.save_dossier(dossier)

            return ingested
        except Exception as exc:
            logger.warning("[EventIngestor] %s: non-fatal run failure: %s", ticker, exc)
            return 0

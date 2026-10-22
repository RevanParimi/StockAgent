"""
Type one company's new items with one bulk-tier call, and keep only what the
items support.

The model answers per item: is it about this company, what happened (one
sentence), and its category, direction and materiality. Everything else on
the stored event comes from the item the answer cites: the symbol (the one
the feed asked about), the publication time, the source and its URL or id.
So the model can neither date an event nor file it under another stock.

An answer is dropped and counted when it:

- cites no item it was given (`ungrounded`);
- states a figure its item does not contain, such as "profit up 15%" for an
  item that says 12%, or "Rs 35 billion" for "Rs 3,500 crore" (`ungrounded`).
  Figures of two or more digits are compared as numbers, commas ignored;
  "Q2" is not a figure;
- has an unknown category, direction or materiality, or no sentence
  (`invalid`);
- answers an item already answered in the same call (`duplicate`).

An item answered "not about this company" is `unrelated`: no event, and the
feed does not ask again. An item with no valid answer is asked again on the
next run. A failed call or output that is not the JSON contract (`failed`)
stores nothing.
"""
from __future__ import annotations

import json
import logging
import re
import time
from dataclasses import dataclass, field

from backend.shared.schemas.events import CATEGORIES, DIRECTIONS, MATERIALITIES, CompanyEvent
from core.config import settings
from core.config.prompts.shared.company_events import (
    COMPANY_EVENTS_SYSTEM_PROMPT, COMPANY_EVENTS_USER_TEMPLATE,
)
from core.events.sources import SourceItem

logger = logging.getLogger(__name__)

CALLER = "company_events"
MAX_WHAT_CHARS = 280
_ITEM_TEXT_CHARS = 600
_SOURCE_LABELS = {"nse_announcement": "NSE announcement", "nse_board_meeting": "NSE board meeting",
                  "news": "news"}
_NUMBER = re.compile(r"\d[\d,]*(?:\.\d+)?")


@dataclass
class Classified:
    events: list[CompanyEvent] = field(default_factory=list)
    unrelated: set[str] = field(default_factory=set)      # source ids judged not about it
    ungrounded: int = 0
    invalid: int = 0
    duplicate: int = 0
    failed: bool = False
    error: str = ""


def _value(token: str) -> float | None:
    try:
        return float(token.replace(",", "").rstrip("."))
    except ValueError:
        return None


def ungrounded_figures(what: str, source_text: str) -> list[str]:
    """The figures of two or more digits in `what` that are not figures of
    `source_text`, compared as numbers with commas ignored: "3,500" matches
    "3500.00", but "35" does not match "3500"."""
    have = {v for v in map(_value, _NUMBER.findall(source_text)) if v is not None}
    missing = []
    for token in _NUMBER.findall(what):
        if len(token.replace(",", "").replace(".", "").rstrip(".")) < 2:
            continue
        if _value(token) not in have:
            missing.append(token)
    return missing


def _item_lines(items: list[SourceItem]) -> str:
    lines = []
    for n, item in enumerate(items, start=1):
        label = _SOURCE_LABELS.get(item.source, item.source)
        if item.publisher:
            label = f"{label} ({item.publisher})"
        published = item.published_raw or "date not given"
        lines.append(f"[{n}] {label} | published {published} | {item.title}")
        if item.text:
            lines.append(f"    {item.text[:_ITEM_TEXT_CHARS]}")
    return "\n".join(lines)


def _call_llm(system: str, user: str) -> str:
    """One bulk-tier JSON call, recorded like every other (success or not)."""
    from services.clients.llm_client import JSON_MODE_EXTRA_BODY, get_llm_client, record_llm_call
    client = get_llm_client()
    t0 = time.time()
    try:
        resp = client.chat.completions.create(
            model=settings.LLM_MODEL_BULK,
            temperature=0.1,
            max_tokens=1800,
            response_format={"type": "json_object"},
            extra_body=JSON_MODE_EXTRA_BODY,
            messages=[{"role": "system", "content": system},
                      {"role": "user", "content": user}],
        )
    except Exception:
        record_llm_call(CALLER, settings.LLM_MODEL_BULK, 0, 0, int((time.time() - t0) * 1000), False)
        raise
    usage = getattr(resp, "usage", None)
    record_llm_call(CALLER, settings.LLM_MODEL_BULK,
                    getattr(usage, "prompt_tokens", 0) or 0,
                    getattr(usage, "completion_tokens", 0) or 0,
                    int((time.time() - t0) * 1000), True)
    return resp.choices[0].message.content or ""


def _entries(raw: str) -> list | None:
    """The answer list, or None when the output is not the contract."""
    text = re.sub(r"<think>.*?</think>", "", raw or "", flags=re.DOTALL).strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text)
    try:
        data = json.loads(text)
    except (TypeError, ValueError):
        return None
    entries = data.get("events") if isinstance(data, dict) else None
    return entries if isinstance(entries, list) else None


def _is_false(value) -> bool:
    return value is False or (isinstance(value, str) and value.strip().lower() == "false")


def classify_items(symbol: str, company: str, items: list[SourceItem], *,
                   fetched_at: str, call=None) -> Classified:
    """Events for `symbol` from `items`, each citing one of them. Never raises."""
    out = Classified()
    if not items:
        return out
    call = call or _call_llm
    user = COMPANY_EVENTS_USER_TEMPLATE.format(company=company or symbol, symbol=symbol,
                                               items=_item_lines(items))
    try:
        raw = call(COMPANY_EVENTS_SYSTEM_PROMPT, user)
    except Exception as exc:
        logger.warning("[events] %s: classifier call failed: %s", symbol, exc)
        out.failed, out.error = True, f"call: {exc}"[:200]
        return out
    entries = _entries(raw)
    if entries is None:
        logger.warning("[events] %s: classifier output is not the JSON contract (%d chars)",
                       symbol, len(raw or ""))
        out.failed, out.error = True, "malformed output"
        return out

    answered: set[str] = set()
    for entry in entries:
        if not isinstance(entry, dict):
            out.invalid += 1
            continue
        number = entry.get("item")
        if isinstance(number, str) and number.strip().isdigit():
            number = int(number.strip())
        if isinstance(number, bool) or not isinstance(number, int) or not 1 <= number <= len(items):
            out.ungrounded += 1
            continue
        item = items[number - 1]
        if item.source_id in answered:
            out.duplicate += 1
            continue
        if _is_false(entry.get("about_company")):
            answered.add(item.source_id)
            out.unrelated.add(item.source_id)
            continue
        category = str(entry.get("category") or "").strip().lower()
        direction = str(entry.get("direction") or "").strip().lower()
        materiality = str(entry.get("materiality") or "").strip().lower()
        what = " ".join(str(entry.get("what") or "").split())[:MAX_WHAT_CHARS]
        if (category not in CATEGORIES or direction not in DIRECTIONS
                or materiality not in MATERIALITIES or not what):
            out.invalid += 1
            continue
        if ungrounded_figures(what, f"{item.title} {item.text} {item.published_raw}"):
            out.ungrounded += 1
            continue
        answered.add(item.source_id)
        out.events.append(CompanyEvent(
            id=item.source_id, symbol=symbol, what=what, category=category,
            direction=direction, materiality=materiality, source=item.source,
            source_url=item.url, announcement_id=item.announcement_id, title=item.title,
            publisher=item.publisher, published_at=item.published_at,
            published_raw=item.published_raw, fetched_at=fetched_at,
            classifier=settings.LLM_MODEL_BULK))
    return out

"""Watchdog registry — loads and validates config/milestones.yaml.

A registry that cannot be parsed is a loud failure, never a silent skip:
the caller turns RegistryError into an `unknown`-state alert. A watchdog
that quietly watches nothing is worse than no watchdog at all.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Literal

import yaml

_WEEKDAYS = {"mon": 0, "tue": 1, "wed": 2, "thu": 3, "fri": 4, "sat": 5, "sun": 6}

_ALLOWED = {"id", "kind", "title", "check", "prep", "window", "deadline",
            "lead_days", "schedule", "action", "docs"}
_REQUIRED = {"id", "kind", "title", "check"}


class RegistryError(Exception):
    """config/milestones.yaml is malformed."""


@dataclass(frozen=True)
class Window:
    weekdays: tuple[int, ...]

    def is_open(self, on: date) -> bool:
        return not self.weekdays or on.weekday() in self.weekdays


@dataclass(frozen=True)
class Milestone:
    id: str
    kind: Literal["milestone", "invariant"]
    title: str
    check: str
    prep: str | None = None
    window: Window | None = None
    deadline: date | None = None
    lead_days: int = 3
    schedule: Literal["daily", "monthly"] = "daily"
    action: str = ""
    docs: str = ""


def _parse_window(raw, mid: str) -> Window | None:
    if raw is None:
        return None
    if not isinstance(raw, dict):
        raise RegistryError(f"{mid}: window must be a mapping")
    days = raw.get("weekdays") or []
    out = []
    for d in days:
        key = str(d).strip().lower()[:3]
        if key not in _WEEKDAYS:
            raise RegistryError(f"{mid}: unknown weekday {d!r}")
        out.append(_WEEKDAYS[key])
    return Window(weekdays=tuple(sorted(set(out))))


def _parse_entry(raw: dict, kind: str) -> Milestone:
    if not isinstance(raw, dict):
        raise RegistryError(
            f"{kind} entry must be a mapping, got {type(raw).__name__}")
    mid = str(raw.get("id") or "").strip()
    if not mid:
        raise RegistryError(f"{kind} entry missing 'id'")
    extra = set(raw) - _ALLOWED
    if extra:
        raise RegistryError(f"{mid}: unknown field(s) {sorted(extra)}")
    missing = _REQUIRED - set(raw)
    if missing:
        raise RegistryError(f"{mid}: missing required field(s) {sorted(missing)}")

    deadline = raw.get("deadline")
    if deadline is not None and not isinstance(deadline, date):
        raise RegistryError(f"{mid}: deadline must be an ISO date (YYYY-MM-DD)")
    schedule = str(raw.get("schedule", "daily"))
    if schedule not in ("daily", "monthly"):
        raise RegistryError(f"{mid}: schedule must be 'daily' or 'monthly'")

    return Milestone(
        id=mid,
        kind=raw["kind"],
        title=str(raw["title"]),
        check=str(raw["check"]),
        prep=(str(raw["prep"]) if raw.get("prep") else None),
        window=_parse_window(raw.get("window"), mid),
        deadline=deadline,
        lead_days=int(raw.get("lead_days", 3)),
        schedule=schedule,
        action=str(raw.get("action", "")).strip(),
        docs=str(raw.get("docs", "")),
    )


def load_registry(path: str | Path = "config/milestones.yaml") -> list[Milestone]:
    p = Path(path)
    if not p.exists():
        raise RegistryError(f"registry not found: {p}")
    try:
        doc = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        raise RegistryError(f"registry is not valid YAML: {exc}") from exc
    if not isinstance(doc, dict):
        raise RegistryError("registry root must be a mapping")

    entries: list[Milestone] = []
    for key in ("milestones", "invariants"):
        for raw in (doc.get(key) or []):
            entries.append(_parse_entry(raw, key))

    seen: set[str] = set()
    for e in entries:
        if e.id in seen:
            raise RegistryError(f"duplicate id: {e.id}")
        seen.add(e.id)
    return entries

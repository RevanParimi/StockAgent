"""Watchdog engine — the escalation ladder, as a pure function.

evaluate() performs no I/O and reads no clock: `now` and `prior_state` are
parameters. That is what makes the whole ladder table-testable without prod,
without a scheduler, and without waiting for a real Saturday.

Ladder (spec section 7):

    satisfied, previously not     -> resolved, once, then silent forever
    unknown                       -> warning, once per day
    past deadline, not satisfied  -> critical, every 7 days, indefinitely
    window open (or no window)    -> warning, once per day
    within lead of next window    -> info, once per approach
    otherwise                     -> silent

A lapsed deadline never goes quiet. That is the specific failure this exists
to prevent.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Literal

from core.ops.watchdog.checks import CheckResult
from core.ops.watchdog.registry import Milestone

Level = Literal["info", "warning", "critical", "resolved"]

_LAPSED_REPEAT_DAYS = 7


@dataclass(frozen=True)
class Notification:
    milestone_id: str
    level: Level
    title: str
    body: str
    # Presentation (2026-08-20): the same content as `body`, in parts, so the
    # Inbox can render a card instead of reflowing prose. `body` remains the
    # plain-text form push and email send.
    headline: str = ""
    status: str = ""
    next_step: str = ""
    docs: str = ""

    @property
    def severity(self) -> str:
        """AlertEvent.severity only accepts info|warning|critical."""
        return "info" if self.level == "resolved" else self.level


def _next_window_start(entry: Milestone, today: date) -> date | None:
    """First day on/after `today` on which the window is open."""
    if entry.window is None or not entry.window.weekdays:
        return today
    for offset in range(0, 14):
        cand = today + timedelta(days=offset)
        if cand.weekday() in entry.window.weekdays:
            return cand
    return None


def _compose(entry: Milestone, result: CheckResult, level: Level,
             headline: str) -> Notification:
    """Build one notification in both forms: parts for the Inbox card, and the
    plain-text `body` push and email send.

    `next_step` is dropped on `resolved`. The remediation text describes a
    problem that no longer exists, and reading it on a closing notice is
    actively misleading — on 2026-08-19 a satisfied IPO-ledger alert still
    warned that perishable window data "is being lost".
    """
    next_step = "" if level == "resolved" else entry.action.strip()
    # The title is printed ONCE, here. The headline deliberately does not
    # restate it (the card renders them as separate lines).
    lines = [f"[watchdog] {entry.title}", "", headline, "",
             f"Status: {result.detail}"]
    if next_step:
        lines += ["", "Next step:", next_step]
    if entry.docs:
        lines += ["", f"Docs: {entry.docs}"]
    return Notification(entry.id, level, entry.title, "\n".join(lines),
                        headline=headline, status=result.detail,
                        next_step=next_step, docs=entry.docs)


def evaluate(entries: list[Milestone],
             results: dict[str, CheckResult],
             now: datetime,
             prior_state: dict) -> tuple[list[Notification], dict]:
    """Return (notifications to send, new state). Pure."""
    today = now.date()
    prior_entries = (prior_state or {}).get("entries", {})
    new_entries: dict[str, dict] = {}
    notes: list[Notification] = []

    for entry in entries:
        result = results.get(entry.id) or CheckResult(
            "unknown", f"no result produced for {entry.id}")
        prior = prior_entries.get(entry.id, {})
        last_level = prior.get("last_level")
        last_state = prior.get("last_state")
        last_notified = prior.get("last_notified_date")
        record = {"last_level": last_level,
                  "last_notified_date": last_notified,
                  "last_state": result.state}

        def fire(level: Level, headline: str, _rec=record) -> None:
            notes.append(_compose(entry, result, level, headline))
            _rec["last_level"] = level
            _rec["last_notified_date"] = today.isoformat()

        notified_today = last_notified == today.isoformat()

        if result.state == "satisfied":
            if last_state is not None and last_state != "satisfied":
                fire("resolved", "Now satisfied — closing.")
            new_entries[entry.id] = record
            continue

        if result.state == "unknown":
            if not notified_today:
                fire("warning",
                     "The check could not answer. Treating as UNRESOLVED "
                     "rather than passing it.")
            new_entries[entry.id] = record
            continue

        # pending / blocked from here on.
        lapsed = entry.deadline is not None and today > entry.deadline
        if lapsed:
            due = (last_notified is None or
                   (today - date.fromisoformat(last_notified)).days
                   >= _LAPSED_REPEAT_DAYS)
            if due:
                fire("critical",
                     f"LAPSED — deadline {entry.deadline} passed and it is "
                     "still not done.")
            new_entries[entry.id] = record
            continue

        # What counts as "actionable today":
        #   recurring window  -> the window's own weekdays
        #   deadline only     -> the last `lead_days` before the deadline.
        #                        Treating this as always-open makes the entry
        #                        warn EVERY DAY until its deadline.
        #   neither           -> a standing invariant; broken means actionable.
        if entry.window is not None:
            window_open = entry.window.is_open(today)
        elif entry.deadline is not None:
            window_open = (entry.deadline - today).days <= entry.lead_days
        else:
            window_open = True

        if window_open:
            if entry.schedule == "monthly":
                same_month = (last_notified is not None and
                              last_notified[:7] == today.isoformat()[:7])
                if not same_month:
                    fire("warning", "Needs attention.")
            elif not notified_today:
                if result.state == "blocked":
                    fire("warning",
                         "BLOCKED — a precondition failed, so investigate "
                         "before acting.")
                else:
                    fire("warning", "Due now.")
            new_entries[entry.id] = record
            continue

        # The lead-in "comes due on <date>" notice only makes sense for a
        # recurring window. For a deadline-only entry the lead period IS the
        # actionable window, already handled above.
        if entry.window is None:
            new_entries[entry.id] = record
            continue

        nxt = _next_window_start(entry, today)
        if nxt is not None and (nxt - today).days <= entry.lead_days:
            already = (last_level == "info" and last_notified is not None and
                       date.fromisoformat(last_notified) >= today
                       - timedelta(days=entry.lead_days))
            if not already:
                fire("info",
                     f"Comes due on {nxt.isoformat()} "
                     f"({(nxt - today).days} day(s) away).")
        new_entries[entry.id] = record

    return notes, {"last_run_ts": now.timestamp(), "entries": new_entries}

"""Scheduled jobs, read from the scheduler's source (never by importing it).

For every `add_job(...)` call: the job id, its cron fields with the repository
defaults of any setting they read, the handler method, and the config switches
that gate the registration (the `if` tests around it). The two slot loops give
`ipo_refresh_am/pm` and `company_events_am/pm`, one job per loop item.

The reader follows plain assignments, `for` loops over a written-out tuple and
`int(...)`, `str(...).split(...)` and settings lookups. A gate is a plain check
of a switch: `if flag:`. A shape it does not know (a negated or combined gate,
an early return on a switch, a computed job id) stops it with the line, so a new
scheduler idiom is taught here and never silently dropped or read backwards.
"""
from __future__ import annotations

import ast
import re
from pathlib import Path
from typing import Any

from tools.architecture_map.model import sources, switches

SCHEDULER_FILE = "services/scheduler/python/scheduler.py"
SETTINGS_NAMES = ("settings", "_macro_cfg")   # the scheduler's two names for settings
CRON_FIELDS = ("year", "month", "day", "week", "day_of_week", "hour", "minute", "second")
# Some scheduler names end in the code of an old plan, "(M4)", "(BP4)" or "(P3, dark)",
# which reads like one of the map's module ids.
_PLAN_CODE = re.compile(r"\s*\((?:M|BP|P)\d+\b[^()]*\)\s*$")


def plain_name(name: str) -> str:
    """A job's name as the map shows it: without a closing bracket that holds an old
    plan's code. A name that is nothing else stays as it is."""
    return _PLAN_CODE.sub("", name).strip() or name


def shown(job: dict) -> dict:
    """The job with the map's name; the scheduler's own is kept where it differs."""
    name = plain_name(job["name"])
    kept = {"scheduler_name": job["name"]} if name != job["name"] else {}
    return {**job, "name": name, **kept}


class _Reader:
    def __init__(self, root: Path) -> None:
        self.settings = switches.declared_settings(root)
        self.config = switches.load_config(root)

    # -- values -----------------------------------------------------------

    def value(self, node: ast.AST, env: dict) -> Any:
        """The static value of an expression; raises SourceError if unknown."""
        if isinstance(node, ast.Constant):
            return node.value
        if isinstance(node, ast.Name) and node.id in env:
            bound = env[node.id]
            if bound[0] == "item":                      # one element of a sequence
                return list(self.value(bound[1], bound[3]))[bound[2]]
            return self.value(bound[1], bound[2])
        if (isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name)
                and node.value.id in SETTINGS_NAMES):
            return self.setting(node.attr)
        if isinstance(node, (ast.Tuple, ast.List)):
            return [self.value(e, env) for e in node.elts]
        if isinstance(node, ast.Subscript):
            return self.value(node.value, env)[self.value(node.slice, env)]
        if isinstance(node, ast.JoinedStr):
            return "".join(self._piece(p, env) for p in node.values)
        if isinstance(node, (ast.GeneratorExp, ast.ListComp)) and len(node.generators) == 1:
            loop = node.generators[0]
            if isinstance(loop.target, ast.Name) and not loop.ifs:
                items = self.value(loop.iter, env)
                return [self.value(node.elt,
                                   {**env, loop.target.id: ("expr", ast.Constant(item), env)})
                        for item in items]
        if isinstance(node, ast.Call):
            return self._call(node, env)
        raise sources.SourceError(f"line {getattr(node, 'lineno', '?')}: cannot read the "
                                  f"expression {ast.dump(node)[:120]}")

    def _piece(self, part: ast.AST, env: dict) -> str:
        if isinstance(part, ast.Constant):
            return str(part.value)
        if isinstance(part, ast.FormattedValue) and part.format_spec is None:
            return str(self.value(part.value, env))
        raise sources.SourceError(f"line {part.lineno}: cannot read an f-string part")

    def _call(self, node: ast.Call, env: dict) -> Any:
        func = node.func
        if isinstance(func, ast.Name) and func.id in ("int", "str", "bool") and len(node.args) == 1:
            return {"int": int, "str": str, "bool": bool}[func.id](self.value(node.args[0], env))
        if isinstance(func, ast.Name) and func.id == "cfg":
            call = switches.cfg_call(node)
            if call is not None:
                known, value = switches.default_of(self.config, call)
                if known:
                    return value
        if (isinstance(func, ast.Name) and func.id == "getattr" and len(node.args) >= 2
                and isinstance(node.args[0], ast.Name) and node.args[0].id in SETTINGS_NAMES):
            name = self.value(node.args[1], env)
            if name in self.settings or len(node.args) < 3:
                return self.setting(name)
            return self.value(node.args[2], env)
        if isinstance(func, ast.Attribute) and func.attr == "split":
            text = self.value(func.value, env)
            return text.split(*[self.value(a, env) for a in node.args])
        raise sources.SourceError(f"line {node.lineno}: cannot read the call "
                                  f"{ast.dump(node)[:120]}")

    def setting(self, name: str) -> Any:
        if name not in self.settings:
            raise sources.SourceError(f"setting {name} is not declared with cfg() in "
                                      f"{switches.SETTINGS_FILE}")
        known, value = switches.default_of(self.config, self.settings[name])
        if not known:
            raise sources.SourceError(f"setting {name} has no readable default")
        return value

    # -- gates ------------------------------------------------------------

    def switches_in(self, node: ast.AST, env: dict, seen: frozenset = frozenset()) -> list[str]:
        """The config keys of the boolean switches an `if` test reads."""
        keys: list[str] = []
        for sub in ast.walk(node):
            name = None
            if (isinstance(sub, ast.Attribute) and isinstance(sub.value, ast.Name)
                    and sub.value.id in SETTINGS_NAMES):
                name = sub.attr
            elif (isinstance(sub, ast.Call) and isinstance(sub.func, ast.Name)
                  and sub.func.id == "getattr" and len(sub.args) >= 2
                  and isinstance(sub.args[0], ast.Name) and sub.args[0].id in SETTINGS_NAMES
                  and isinstance(sub.args[1], ast.Constant)):
                name = sub.args[1].value
            elif isinstance(sub, ast.Name) and sub.id in env and sub.id not in seen:
                bound = env[sub.id]
                if bound[0] == "expr":
                    keys += self.switches_in(bound[1], bound[2], seen | {sub.id})
            elif isinstance(sub, ast.Call):
                call = switches.cfg_call(sub) if isinstance(sub.func, ast.Name) else None
                if call is not None:
                    known, value = switches.default_of(self.config, call)
                    if known and isinstance(value, bool):
                        keys.append(call["key"])
            if name is not None:
                if name not in self.settings:
                    raise sources.SourceError(
                        f"{SCHEDULER_FILE} line {sub.lineno}: setting {name} is not declared with "
                        f"cfg() in {switches.SETTINGS_FILE}")
                call = self.settings[name]
                known, value = switches.default_of(self.config, call)
                if known and isinstance(value, bool):
                    keys.append(call["key"])
        return keys

    def gate(self, node: ast.If, env: dict) -> list[str]:
        """The switches that gate an `if` body; [] when the test reads none.

        Only `if <switch>:` is read. `not`, `and`, `or`, a comparison or a
        `return` under a switch would be recorded wrongly, so each is refused."""
        found = self.switches_in(node.test, env)
        if not found:
            return []
        if not self.plain_switch(node.test, env):
            raise sources.SourceError(
                f"{SCHEDULER_FILE} line {node.lineno}: a gate that is not a plain check of one "
                "switch (not, and, or, a comparison)")
        if any(isinstance(sub, ast.Return)
               for statement in (*node.body, *node.orelse) for sub in ast.walk(statement)):
            raise sources.SourceError(
                f"{SCHEDULER_FILE} line {node.lineno}: a return under a switch gates the jobs "
                "after it")
        return found

    def plain_switch(self, node: ast.AST, env: dict) -> bool:
        if isinstance(node, ast.Name):
            bound = env.get(node.id)
            return bool(bound) and bound[0] == "expr" and self.plain_switch(bound[1], bound[2])
        if isinstance(node, ast.Attribute):
            return isinstance(node.value, ast.Name) and node.value.id in SETTINGS_NAMES
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            if node.func.id in ("getattr", "cfg"):
                return True
            return node.func.id == "bool" and len(node.args) == 1 and self.plain_switch(
                node.args[0], env)
        return False


def _bind(target: ast.AST, value: ast.AST, env: dict) -> None:
    """Record what a plain assignment or a loop target now names."""
    if isinstance(target, ast.Name):
        env[target.id] = ("expr", value, dict(env))
    elif isinstance(target, (ast.Tuple, ast.List)):
        snapshot = dict(env)
        for position, name in enumerate(target.elts):
            if isinstance(name, ast.Name):
                env[name.id] = ("item", value, position, snapshot)


def _add_job_calls(statement: ast.AST) -> list[ast.Call]:
    return [n for n in ast.walk(statement)
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
            and n.func.attr == "add_job"]


def _job(reader: _Reader, call: ast.Call, env: dict, gates: list[str]) -> dict:
    kw = {k.arg: k.value for k in call.keywords if k.arg}
    label = f"{SCHEDULER_FILE} line {call.lineno}"
    if "id" not in kw:
        raise sources.SourceError(f"{label}: add_job without an id")
    try:
        job_id = reader.value(kw["id"], env)
        trigger = kw.get("trigger", call.args[1] if len(call.args) > 1 else None)
        if not (isinstance(trigger, ast.Call) and getattr(trigger.func, "id", "") == "CronTrigger"):
            raise sources.SourceError("the trigger is not a CronTrigger(...)")
        cron, timezone = {}, "Asia/Kolkata"
        for keyword in trigger.keywords:
            if keyword.arg == "timezone":
                timezone = reader.value(keyword.value, env)
            elif keyword.arg in CRON_FIELDS:
                cron[keyword.arg] = str(reader.value(keyword.value, env))
            else:
                raise sources.SourceError(f"unknown CronTrigger argument {keyword.arg}")
        name = reader.value(kw["name"], env) if "name" in kw else job_id
    except (sources.SourceError, IndexError, KeyError, ValueError, TypeError) as exc:
        raise sources.SourceError(f"{label}: {exc}") from exc
    func = kw.get("func", call.args[0] if call.args else None)
    handler = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")
    return {"id": str(job_id), "name": str(name), "cron": cron, "timezone": timezone,
            "handler": handler, "gates": sorted(set(gates))}


def _walk(reader: _Reader, body: list[ast.stmt], env: dict, gates: list[str],
          jobs: list[dict]) -> None:
    for node in body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            if _add_job_calls(node):        # only code that registers jobs is read
                _walk(reader, node.body, {}, [], jobs)
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                _bind(target, node.value, env)
        elif isinstance(node, ast.AnnAssign) and node.value is not None:
            _bind(node.target, node.value, env)
        elif isinstance(node, ast.If):
            found = reader.gate(node, env)
            before = dict(env)                      # the else branch sees none of the body
            _walk(reader, node.body, env, gates + found, jobs)
            _walk(reader, node.orelse, before, gates + ["not " + k for k in found], jobs)
        elif isinstance(node, ast.Try):
            _walk(reader, node.body, env, gates, jobs)
            for handler in node.handlers:                 # a fallback must not override
                _walk(reader, handler.body, dict(env), gates, jobs)
            _walk(reader, node.orelse + node.finalbody, env, gates, jobs)
        elif isinstance(node, ast.For) and isinstance(node.iter, (ast.Tuple, ast.List)):
            for item in node.iter.elts:
                inner = dict(env)
                if isinstance(node.target, (ast.Tuple, ast.List)) and isinstance(
                        item, (ast.Tuple, ast.List)):
                    for name, value in zip(node.target.elts, item.elts):
                        _bind(name, value, inner)
                else:
                    _bind(node.target, item, inner)
                _walk(reader, node.body, inner, gates, jobs)
        elif isinstance(node, (ast.For, ast.While, ast.With)):
            if _add_job_calls(node):
                if isinstance(node, ast.For):
                    raise sources.SourceError(
                        f"{SCHEDULER_FILE} line {node.lineno}: a loop over something other than "
                        "a written-out tuple registers jobs")
            _walk(reader, node.body, dict(env), gates, jobs)
        else:
            for call in _add_job_calls(node):
                jobs.append(_job(reader, call, env, gates))


def scheduled_jobs(root: Path) -> list[dict]:
    """Every job the scheduler can register, sorted by id."""
    reader = _Reader(root)
    jobs: list[dict] = []
    _walk(reader, sources.parse(root, SCHEDULER_FILE).body, {}, [], jobs)
    seen: set[str] = set()
    for job in jobs:
        if job["id"] in seen:
            raise sources.SourceError(f"{SCHEDULER_FILE}: job id {job['id']} is registered twice")
        seen.add(job["id"])
    return sorted(jobs, key=lambda j: j["id"])


# -- words for a cron trigger ------------------------------------------------

_DAYS = {"mon-fri": "Mon–Fri", "mon": "Monday", "tue": "Tuesday", "wed": "Wednesday",
         "thu": "Thursday", "fri": "Friday", "sat": "Saturday", "sun": "Sunday", "*": ""}
_MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")
_WEEKDAY_ORDER = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")


def _number(text: str) -> int | None:
    return int(text) if text.isdigit() else None


def times_of(cron: dict) -> list[tuple[int, int]]:
    """(hour, minute) pairs, in order; empty when the fields are not plain numbers."""
    hours = [_number(h) for h in str(cron.get("hour", "0")).split(",")]
    minute = _number(str(cron.get("minute", "0")))
    if minute is None or any(h is None for h in hours):
        return []
    return sorted((h, minute) for h in hours)


def describe_schedule(cron: dict) -> dict:
    """{"group", "when", "time", "sort"}: the words of one cron trigger.

    `group` is "daily" (every day or Mon–Fri), "weekly" (one weekday) or
    "calendar" (a day of the month or a date of the year).
    """
    times = times_of(cron)
    clock = ", ".join(f"{h:02d}:{m:02d}" for h, m in times) or (
        f"{cron.get('hour', '*')}:{cron.get('minute', '*')}")
    day, month = cron.get("day", "*"), cron.get("month", "*")
    weekday = str(cron.get("day_of_week", "*")).lower()
    first = times[0] if times else (99, 99)
    if day != "*":
        if month != "*" and month.isdigit() and 1 <= int(month) <= 12:
            when = f"{_MONTHS[int(month) - 1]} {day}"
            sort = (2, int(month), int(day), *first)
        else:
            suffix = {"1": "st", "2": "nd", "3": "rd"}.get(day, "th")
            when = f"{day}{suffix} of the month" if day.isdigit() else f"day {day}"
            sort = (1, int(day) if day.isdigit() else 0, 0, *first)
        return {"group": "calendar", "when": when, "time": clock, "sort": list(sort)}
    if weekday in _WEEKDAY_ORDER:
        return {"group": "weekly", "when": _DAYS[weekday], "time": clock,
                "sort": [_WEEKDAY_ORDER.index(weekday), *first]}
    when = _DAYS.get(weekday, weekday) or "Daily"
    return {"group": "daily", "when": when, "time": clock, "sort": [*first]}

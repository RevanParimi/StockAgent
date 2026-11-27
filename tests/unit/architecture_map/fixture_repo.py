"""A small repository the architecture map's tests build, and break, in a temp folder.

It has one of each thing the generators read: settings declared with cfg(), a
config.yaml, a scheduler with constant ids, flags and both slot loops, a server
that mounts routers, imports of every shape, and a curated part describing it.
"""
from __future__ import annotations

from pathlib import Path

SETTINGS = '''
from .loader import cfg

FEEDBACK_CRON: str = cfg("scheduler.feedback_cron", env="FEEDBACK_CRON", fallback="30 16 * * mon-fri")
EVENTS_ON: bool = bool(cfg("events.enabled", env="EVENTS_ENABLED", fallback=False))
MORNING: str = str(cfg("events.morning", fallback="08:15"))
EVENING: str = str(cfg("events.evening", fallback="18:30"))
IPO_HOUR: int = int(cfg("ipo.refresh_hour", fallback=8))
IPO_HOUR_LIVE: int = int(cfg("ipo.refresh_hour_live", fallback=17))
IPO_MINUTE_LIVE: int = int(cfg("ipo.refresh_minute_live", fallback=45))
NOT_A_FLAG: int = int(cfg("scheduler.workers", fallback=1))
LEARNING: str = cfg("rl.learning_mode", env="RL_LEARNING_MODE", fallback="adapt")
'''

CONFIG = '''
scheduler:
  feedback_cron: "15 17 * * mon-fri"
events:
  enabled: true
  morning: "08:20"
ipo:
  enabled: true
audit:
  enabled: false
rl:
  learning_mode: observe
'''

SCHEDULER = '''
from backend.shared.config.settings.loader import cfg
from core.config import settings


class Host:
    def build(self):
        scheduler = object()
        parts = settings.FEEDBACK_CRON.split()
        if len(parts) == 5:
            minute_, hour_, day_, month_, dow_ = parts
            scheduler.add_job(func=self._review, trigger=CronTrigger(
                minute=minute_, hour=hour_, day=day_, month=month_, day_of_week=dow_,
                timezone="Asia/Kolkata"), id="daily_review", name="Daily review")
        try:
            from backend.shared.config import settings as _macro_cfg
            on = getattr(_macro_cfg, "EVENTS_ON", True)
        except Exception:
            on = True
        if on:
            scheduler.add_job(func=self._macro, trigger=CronTrigger(
                hour="9,12", minute=0, timezone="Asia/Kolkata"), id="macro")
        if getattr(settings, "EVENTS_ON", False):
            for slot, hhmm in (("am", settings.MORNING), ("pm", settings.EVENING)):
                try:
                    hour, minute = (int(p) for p in str(hhmm).split(":"))
                    scheduler.add_job(func=self._events, args=[slot], trigger=CronTrigger(
                        hour=hour, minute=minute, day_of_week="mon-fri",
                        timezone="Asia/Kolkata"),
                        id=f"events_{slot}", name=f"Events ({slot})")
                except ValueError:
                    pass
        if cfg("ipo.enabled", fallback=True):
            for slot, hour, minute in (("am", settings.IPO_HOUR, 0),
                                       ("pm", settings.IPO_HOUR_LIVE, settings.IPO_MINUTE_LIVE)):
                scheduler.add_job(func=self._ipo, trigger=CronTrigger(
                    hour=hour, minute=minute, timezone="Asia/Kolkata"), id=f"ipo_{slot}")
        if cfg("audit.enabled", fallback=True):
            scheduler.add_job(func=self._audit, trigger=CronTrigger(
                hour=int(cfg("audit.hour", fallback=23)), minute=45,
                timezone="Asia/Kolkata"), id="audit_nightly")
'''

SERVER = '''
from services.api.routes.items import router as items_router
from services.api.routes import socket

app = FastAPI()
app.include_router(items_router, tags=["Items"])
app.include_router(socket.router, prefix="/live")


@app.get("/health")
def health():
    return {}


if True:
    @app.get("/{full_path:path}", include_in_schema=False)
    def spa(full_path):
        return full_path
'''

ITEMS = '''
from fastapi import APIRouter
router = APIRouter(prefix="/items")


@router.get("", summary="list")
def listing():
    return []


@router.post("/{item_id}")
async def create(item_id):
    return item_id


@router.api_route("/both", methods=["PUT", "delete"])
def both():
    return None
'''

SOCKET = '''
from fastapi import APIRouter
router = APIRouter()


@router.websocket("/ws")
async def stream(websocket):
    return None
'''

ENGINE = '''"""Imports of every shape."""
import os
import core.store
from core import store, helper_name
from core.pkg import mod
from . import sibling
from ..portfolio import advisor
from backend.shared.thing import Thing


def later():
    from services.api import server
    return server, os, store, mod, sibling, advisor, Thing


class Engine:
    TUNING = 1

    def run(self):
        return later()
'''

FILES = {
    "config.yaml": CONFIG,
    "src/backend/shared/config/settings/base.py": SETTINGS,
    "src/backend/shared/thing.py": "class Thing:\n    pass\n",
    "services/scheduler/python/scheduler.py": SCHEDULER,
    "services/api/server.py": SERVER,
    "services/api/routes/__init__.py": "",
    "services/api/routes/items.py": ITEMS,
    "services/api/routes/socket.py": SOCKET,
    "services/api/__init__.py": "",
    "core/__init__.py": "helper_name = 1\n",
    "core/store.py": "x = 1\ny = 2\n",
    "core/pkg/__init__.py": "",
    "core/pkg/mod.py": "",
    "core/engine/__init__.py": "",
    "core/engine/main.py": ENGINE,
    "core/engine/sibling.py": "",
    "core/portfolio/__init__.py": "",
    "core/portfolio/advisor.py": "def decide():\n    return None\n",
    "scripts/tool.py": "from core.engine.main import Engine\n",
}

CURATED = {
    "overview.yaml": """
title: Fixture map
product: A fixture product
reading: Read it.
clock_note: A note.
externals:
  - {id: ext.user, name: A user}
code_map:
  - path: core/
    note: the core
    children:
      - {path: core/engine/, note: the engine}
  - {path: data/, note: state, runtime: true}
""",
    "modules/M01.yaml": """
id: M1
name: Platform
short: Platform
plane: base
column: 0
summary: runs things
submodules:
  - id: M1.1
    name: Scheduler
    summary: the clock
    files: [services/scheduler/python/scheduler.py, "src/backend/**/*.py", services/api/server.py]
    code: ["services/scheduler/python/scheduler.py::Host.build"]
    config: [events.enabled, rl.learning_mode]
    logic: |
      start
        jobs
        | continued
        more
""",
    "modules/M02.yaml": """
id: M2
name: Engine
short: Engine
plane: middle
column: 1
summary: does things
files: ["core/engine/*.py", "core/pkg/*.py", core/store.py]
submodules:
  - id: M2.1
    name: Routes
    summary: the API
    files: ["services/api/routes/*.py", services/api/__init__.py]
    code: ["core/engine/main.py::Engine.run", "core/engine/main.py::later"]
    logic: |
      ask ─► answer
  - id: M2.2
    name: Advisor
    summary: decides
    files: [core/portfolio/__init__.py, core/portfolio/advisor.py, scripts/tool.py]
    code: ["core/portfolio/advisor.py::decide"]
    logic: |
      decide
""",
    "shared.yaml": "files: [core/__init__.py]\n",
    "jobs.yaml": """
daily_review: {module: M1.1, does: reviews, lights: [M1.1, M2, S.items], flows: ["M1>M2"]}
macro: {module: M1.1, does: macro news, lights: [M1.1], flows: []}
events_am: {module: M1.1, does: events, lights: [M1], flows: []}
events_pm: {module: M1.1, does: events, lights: [M1.1], flows: []}
ipo_am: {module: M1.1, does: ipo, lights: [M1.1], flows: []}
ipo_pm: {module: M1.1, does: ipo, lights: [M1.1], flows: []}
audit_nightly: {module: M1.1, does: grades, lights: [M1.1], flows: []}
""",
    "routes.yaml": """
- {prefix: /health, module: M1.1}
- {prefix: "/{full_path:path}", module: M1.1}
- {prefix: /items, module: M2.1}
- {prefix: /live, module: M2.1}
""",
    "stores.yaml": """
- id: S.items
  name: Items
  path: data/items.json
  holds: items
  writers: [M2.1]
  readers: [M2.2]
  code: ["core/portfolio/advisor.py::decide"]
""",
    "flows.yaml": """
- {from: M1, to: M2, what: ticks}
- {from: M2.1, to: ext.user, what: pages}
""",
    "production.yaml": """
- key: rl.learning_mode
  value: observe
  source: KT section 1
  as_of: 2026-10-01
""",
    "trace.yaml": """
traces:
  - id: t1
    title: One thing's life
    steps:
      - {when: Monday, text: it starts, refs: [M1.1, daily_review, S.items]}
      - {when: Tuesday, text: it travels, refs: [M2.1, ext.user], flows: ["M2.1>ext.user"]}
      - {when: Friday, text: a job brings its part, refs: [daily_review, M2.2], flows: ["M1>M2"]}
tours:
  - id: tour1
    title: A tour
    steps:
      - {preset: focus, ref: M2.2, caption: look}
      - {preset: clock, ref: daily_review, caption: runs}
      - {preset: top, caption: whole}
""",
}

CURATED_DIR = "tools/architecture_map/model/curated"


def write(root: Path, rel: str, text: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(text.encode("utf-8"))


def make(root: Path) -> Path:
    """Write the fixture repository under `root` and return it."""
    for rel, text in FILES.items():
        write(root, rel, text)
    for name, text in CURATED.items():
        write(root, f"{CURATED_DIR}/{name}", text)
    return root


def edit(root: Path, rel: str, old: str, new: str) -> None:
    """Replace `old` with `new` in one file; the old text must be there once."""
    text = (root / rel).read_text(encoding="utf-8")
    assert text.count(old) == 1, f"{rel}: {old!r} found {text.count(old)} times"
    write(root, rel, text.replace(old, new))


def curated(root: Path, name: str, old: str, new: str) -> None:
    edit(root, f"{CURATED_DIR}/{name}", old, new)

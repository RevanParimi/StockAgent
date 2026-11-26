"""MAP-001: each generator reads small fixture sources as written."""
from __future__ import annotations

import pytest

from tests.unit.architecture_map import fixture_repo as fx
from tools.architecture_map.model import imports, jobs, routes, sources, switches, tree


@pytest.fixture
def repo(tmp_path):
    return fx.make(tmp_path / "repo")


# -- scheduled jobs ------------------------------------------------------------

def _by_id(found):
    return {job["id"]: job for job in found}


def test_every_registration_is_found_and_slot_loops_expand(repo):
    found = jobs.scheduled_jobs(repo)
    assert [j["id"] for j in found] == [
        "audit_nightly", "daily_review", "events_am", "events_pm", "ipo_am", "ipo_pm", "macro"]


def test_cron_fields_take_the_config_defaults(repo):
    found = _by_id(jobs.scheduled_jobs(repo))
    # FEEDBACK_CRON comes from config.yaml, not from the code's fallback.
    assert found["daily_review"]["cron"] == {
        "minute": "15", "hour": "17", "day": "*", "month": "*", "day_of_week": "mon-fri"}
    # config.yaml's events.morning wins; events.evening is only the code's fallback.
    assert found["events_am"]["cron"] == {"hour": "8", "minute": "20", "day_of_week": "mon-fri"}
    assert found["events_pm"]["cron"] == {"hour": "18", "minute": "30", "day_of_week": "mon-fri"}
    assert found["ipo_am"]["cron"] == {"hour": "8", "minute": "0"}
    assert found["ipo_pm"]["cron"] == {"hour": "17", "minute": "45"}
    assert found["audit_nightly"]["cron"] == {"hour": "23", "minute": "45"}
    assert found["macro"]["cron"] == {"hour": "9,12", "minute": "0"}


def test_names_handlers_and_gates(repo):
    found = _by_id(jobs.scheduled_jobs(repo))
    assert found["events_pm"]["name"] == "Events (pm)"
    assert found["macro"]["name"] == "macro"
    assert found["events_am"]["handler"] == "_events"
    # a length check is not a flag; a flag read through a local name is one
    assert found["daily_review"]["gates"] == []
    assert found["macro"]["gates"] == ["events.enabled"]
    assert found["events_am"]["gates"] == ["events.enabled"]
    assert found["ipo_pm"]["gates"] == ["ipo.enabled"]
    assert found["audit_nightly"]["gates"] == ["audit.enabled"]


def test_a_changed_default_changes_the_job(repo):
    fx.edit(repo, "config.yaml", 'morning: "08:20"', 'morning: "07:05"')
    assert _by_id(jobs.scheduled_jobs(repo))["events_am"]["cron"]["hour"] == "7"


@pytest.mark.parametrize("old,new,message", [
    ('id="macro"', 'id=make_id()', "cannot read the call"),
    ('hour="9,12"', 'hour=self.hour', "cannot read the expression"),
    ('id="macro"', 'name="x"', "without an id"),
    ('id="macro"', 'id="daily_review"', "registered twice"),
])
def test_an_unknown_shape_stops_the_reader(repo, old, new, message):
    fx.edit(repo, "services/scheduler/python/scheduler.py", old, new)
    with pytest.raises(sources.SourceError, match=message):
        jobs.scheduled_jobs(repo)


def test_a_loop_over_a_name_is_refused_not_skipped(repo):
    fx.edit(repo, "services/scheduler/python/scheduler.py",
            'for slot, hour, minute in (("am", settings.IPO_HOUR, 0),\n'
            '                                       ("pm", settings.IPO_HOUR_LIVE, '
            'settings.IPO_MINUTE_LIVE)):',
            "for slot, hour, minute in self.slots:")
    with pytest.raises(sources.SourceError, match="written-out tuple"):
        jobs.scheduled_jobs(repo)


@pytest.mark.parametrize("cron,group,when,time", [
    ({"hour": "6", "minute": "30"}, "daily", "Daily", "06:30"),
    ({"hour": "8", "minute": "5", "day_of_week": "mon-fri"}, "daily", "Mon–Fri", "08:05"),
    ({"hour": "9,12,15", "minute": "0", "day_of_week": "mon-fri"}, "daily", "Mon–Fri",
     "09:00, 12:00, 15:00"),
    ({"minute": "30", "hour": "16", "day": "*", "month": "*", "day_of_week": "mon-fri"},
     "daily", "Mon–Fri", "16:30"),
    ({"day_of_week": "sat", "hour": "10", "minute": "0"}, "weekly", "Saturday", "10:00"),
    ({"day": "1", "hour": "2", "minute": "0"}, "calendar", "1st of the month", "02:00"),
    ({"month": "12", "day": "31", "hour": "23", "minute": "0"}, "calendar", "Dec 31", "23:00"),
])
def test_a_cron_trigger_in_words(cron, group, when, time):
    words = jobs.describe_schedule(cron)
    assert (words["group"], words["when"], words["time"]) == (group, when, time)


def test_week_order_sorts_monday_before_sunday():
    monday = jobs.describe_schedule({"day_of_week": "mon", "hour": "3", "minute": "30"})
    sunday = jobs.describe_schedule({"day_of_week": "sun", "hour": "1", "minute": "0"})
    assert monday["sort"] < sunday["sort"]


# -- API routes ----------------------------------------------------------------

def test_routes_carry_prefixes_methods_files_and_mounting(repo):
    found = {(r["method"], r["path"]): r for r in routes.api_routes(repo)}
    assert sorted(found) == [
        ("DELETE", "/items/both"), ("GET", "/health"), ("GET", "/items"),
        ("GET", "/{full_path:path}"), ("POST", "/items/{item_id}"), ("PUT", "/items/both"),
        ("WS", "/live/ws")]
    assert found[("GET", "/items")]["file"] == "services/api/routes/items.py"
    assert found[("GET", "/items")]["handler"] == "listing"
    assert all(r["mounted"] for r in found.values())


def test_a_router_the_server_does_not_mount_is_listed_as_such(repo):
    fx.edit(repo, "services/api/server.py", 'app.include_router(socket.router, prefix="/live")\n', "")
    found = {r["path"]: r for r in routes.api_routes(repo)}
    assert found["/ws"]["mounted"] is False
    assert found["/items"]["mounted"] is True


@pytest.mark.parametrize("rel,old,new,message", [
    ("services/api/routes/items.py", '@router.get("", summary="list")', "@router.get(PATH)",
     "not a plain string"),
    ("services/api/routes/items.py", 'APIRouter(prefix="/items")', "APIRouter(prefix=PREFIX)",
     "not a plain string"),
    ("services/api/routes/items.py", "def both():\n    return None\n",
     "def both():\n    return None\n\n\nrouter.add_api_route('/x', both)\n", "add_api_route"),
    ("services/api/server.py", "app.include_router(items_router, tags=[\"Items\"])",
     "app.include_router(other_router)", "not imported"),
])
def test_a_registration_the_reader_cannot_read_stops_it(repo, rel, old, new, message):
    fx.edit(repo, rel, old, new)
    with pytest.raises(sources.SourceError, match=message):
        routes.api_routes(repo)


# -- imports -------------------------------------------------------------------

def test_imports_resolve_to_repository_files_only(repo):
    graph = {f["path"]: f for f in imports.import_graph(repo)}
    assert graph["core/engine/main.py"]["imports"] == [
        "core/__init__.py",               # `helper_name` is the package's attribute
        "core/engine/sibling.py",         # from . import sibling
        "core/pkg/mod.py",                # from package import module
        "core/portfolio/advisor.py",      # from ..portfolio import advisor
        "core/store.py",                  # import core.store, and from core import store
        "services/api/server.py",         # inside a function
        "src/backend/shared/thing.py",    # backend.x is src/backend/x
    ]
    assert graph["scripts/tool.py"]["imports"] == ["core/engine/main.py"]
    assert graph["core/store.py"]["imports"] == []


def test_a_file_never_imports_itself(repo):
    fx.write(repo, "core/engine/sibling.py", "from core.engine import sibling\n")
    graph = {f["path"]: f for f in imports.import_graph(repo)}
    assert graph["core/engine/sibling.py"]["imports"] == []


def test_line_counts_ignore_a_byte_order_mark_and_line_end_style(repo):
    (repo / "core/store.py").write_bytes(b"\xef\xbb\xbfx = 1\r\ny = 2\r\nz = 3")
    graph = {f["path"]: f for f in imports.import_graph(repo)}
    assert graph["core/store.py"]["lines"] == 3


def test_python_files_are_those_under_the_code_roots(repo):
    fx.write(repo, "tests/skipped.py", "")
    fx.write(repo, "core/__pycache__/skipped.py", "")
    found = sources.python_files(repo)
    assert "core/store.py" in found and not any("skipped" in p for p in found)


def test_a_source_that_does_not_parse_is_named(repo):
    fx.write(repo, "core/broken.py", "def (:\n")
    with pytest.raises(sources.SourceError, match="core/broken.py"):
        imports.import_graph(repo)


# -- config switches -----------------------------------------------------------

def test_switches_report_the_repository_default_and_its_source(repo):
    records, missing = switches.switch_records(
        repo, ["rl.learning_mode", "events.evening", "events.enabled", "nope.key"])
    by_key = {r["key"]: r for r in records}
    assert by_key["rl.learning_mode"] == {
        "key": "rl.learning_mode", "default": "observe", "default_source": "config.yaml",
        "env": "RL_LEARNING_MODE"}
    assert by_key["events.evening"]["default"] == "18:30"
    assert by_key["events.evening"]["default_source"] == "code fallback"
    assert by_key["events.enabled"]["env"] == "EVENTS_ENABLED"
    assert missing == ["nope.key"]


def test_a_key_only_config_yaml_holds_exists(repo):
    records, missing = switches.switch_records(repo, ["audit.enabled"])
    assert (records[0]["default"], records[0]["env"], missing) == (False, None, [])


# -- logic trees ---------------------------------------------------------------

def test_a_tree_is_parsed_and_drawn_back():
    parsed = tree.parse_tree("root\n  a\n  | more of a\n    a1\n\n  b\nsecond\n  c\n")
    assert [n["text"] for n in parsed] == ["root", "second"]
    assert parsed[0]["children"][0]["text"] == "a\nmore of a"
    assert tree.render_tree(parsed) == [
        "root",
        "├── a",
        "│   │   more of a",
        "│   └── a1",
        "└── b",
        "second",
        "└── c",
    ]


def test_a_continuation_of_a_leaf_keeps_the_guide_line_only_where_needed():
    drawn = tree.render_tree(tree.parse_tree("root\n  a\n  b\n  | and on\n"))
    assert drawn == ["root", "├── a", "└── b", "    and on"]


@pytest.mark.parametrize("text,message", [
    ("root\n   a", "not a multiple of 2"),
    ("root\n    a", "two levels deeper"),
    ("| orphan", "does not exist"),
    ("root\n\ta", "tab"),
])
def test_a_badly_written_tree_names_the_line(text, message):
    with pytest.raises(tree.TreeError, match=message):
        tree.parse_tree(text)


# -- the Opus check's cases: a shape the readers do not know stops them ----------

@pytest.mark.parametrize("old,new", [
    ('router = APIRouter(prefix="/items")', 'router: APIRouter = APIRouter(prefix="/items")'),
    ('router = APIRouter(prefix="/items")', 'router = fastapi.APIRouter(prefix="/items")'),
])
def test_a_router_declared_another_plain_way_is_still_read(repo, old, new):
    fx.edit(repo, "services/api/routes/items.py", old, new)
    assert ("GET", "/items") in {(r["method"], r["path"]) for r in routes.api_routes(repo)}


@pytest.mark.parametrize("old,new,message", [
    ('router = APIRouter(prefix="/items")', 'router = build_router()', "not a router"),
    ('router = APIRouter(prefix="/items")', 'routers = [APIRouter(prefix="/items")]',
     "not assigned to a plain name"),
    ("def both():\n    return None\n",
     "def both():\n    return None\n\n\nrouter.include_router(sub)\n", "include_router"),
    ('@router.api_route("/both", methods=["PUT", "delete"])',
     '@router.api_route("/both", methods=METHODS_)', "not written out"),
])
def test_a_router_shape_that_would_lose_routes_is_refused(repo, old, new, message):
    fx.edit(repo, "services/api/routes/items.py", old, new)
    with pytest.raises(sources.SourceError, match=message):
        routes.api_routes(repo)


@pytest.mark.parametrize("old,new,message", [
    ('if cfg("audit.enabled", fallback=True):', 'if not cfg("audit.enabled", fallback=True):',
     "not a plain check"),
    ('if on:', 'if on and cfg("ipo.enabled", fallback=True):', "not a plain check"),
    ('if on:', 'if on == True:', "not a plain check"),
    ('if on:', 'if getattr(settings, "NOT_DECLARED", True):', "NOT_DECLARED is not declared"),
    ('        if on:\n',
     '        if cfg("ipo.enabled", fallback=True):\n            return scheduler\n        if on:\n',
     "return under a switch"),
])
def test_a_gate_the_reader_would_record_wrongly_is_refused(repo, old, new, message):
    fx.edit(repo, "services/scheduler/python/scheduler.py", old, new)
    with pytest.raises(sources.SourceError, match=message):
        jobs.scheduled_jobs(repo)


def test_only_the_code_that_registers_jobs_is_read(repo):
    """A job handler may check a switch and return: it gates no registration."""
    fx.edit(repo, "services/scheduler/python/scheduler.py", "class Host:\n",
            "class Host:\n    def _job(self):\n        if not settings.EVENTS_ON:\n"
            "            return\n\n")
    assert len(jobs.scheduled_jobs(repo)) == 7


def test_the_else_branch_does_not_see_the_if_bodys_names(repo):
    fx.edit(repo, "services/scheduler/python/scheduler.py", '        if cfg("audit.enabled", fallback=True):\n',
            '        slot_hour = 5\n'
            '        if cfg("ipo.enabled", fallback=True):\n            slot_hour = 6\n'
            '        else:\n            scheduler.add_job(func=self._x, trigger=CronTrigger('
            'hour=slot_hour, minute=0), id="fallback")\n'
            '        if cfg("audit.enabled", fallback=True):\n')
    found = _by_id(jobs.scheduled_jobs(repo))
    assert found["fallback"]["cron"]["hour"] == "5"
    assert found["fallback"]["gates"] == ["not ipo.enabled"]


def test_a_setting_without_a_fallback_defaults_to_none_like_cfg_does(repo):
    fx.edit(repo, "src/backend/shared/config/settings/base.py",
            'LEARNING: str = cfg("rl.learning_mode"',
            'BARE: str = cfg("x.bare", env="BARE")\nPOSITIONAL = cfg("x.positional", "P", 7)\n'
            'LEARNING: str = cfg("rl.learning_mode"')
    records, missing = switches.switch_records(repo, ["x.bare", "x.positional"])
    assert missing == []
    assert [(r["key"], r["default"], r["env"]) for r in records] == [
        ("x.bare", None, "BARE"), ("x.positional", 7, "P")]


def test_a_whole_section_is_not_a_switch(repo):
    fx.edit(repo, "config.yaml", "events:\n  enabled: true\n",
            "events:\n  nested:\n    a: 1\n  enabled: true\n")
    records, missing = switches.switch_records(repo, ["events"])
    assert (records, missing) == ([], ["events"])

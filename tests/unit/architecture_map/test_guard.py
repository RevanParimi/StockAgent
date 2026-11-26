"""MAP-001: the model is deterministic, the guard names each drift with its fix,
and the real repository passes."""
from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from tests.unit.architecture_map import fixture_repo as fx
from tools.architecture_map.model import build, check, generate, validate

ROOT = Path(__file__).resolve().parents[3]
MODEL = build.MODEL_FILE
TREES = build.TREES_FILE
SCHEDULER = "services/scheduler/python/scheduler.py"


@pytest.fixture
def repo(tmp_path):
    root = fx.make(tmp_path / "repo")
    assert generate.write(root) == []
    return root


def _only(problems: list[str]) -> str:
    assert len(problems) == 1, problems
    assert "fix: " in problems[0], problems[0]
    assert "\n" not in problems[0]
    return problems[0]


def test_a_fresh_fixture_passes(repo):
    assert check.run(repo) == []


def test_two_runs_write_the_same_bytes(repo):
    first = ((repo / MODEL).read_bytes(), (repo / TREES).read_bytes())
    assert generate.write(repo) == []
    assert ((repo / MODEL).read_bytes(), (repo / TREES).read_bytes()) == first
    assert b"\r" not in first[0] + first[1]


def test_the_model_holds_the_curated_meaning_with_the_generated_facts(repo):
    model = json.loads((repo / MODEL).read_text(encoding="utf-8"))
    jobs = {j["id"]: j for j in model["jobs"]}
    assert (jobs["events_am"]["module"], jobs["events_am"]["does"]) == ("M1.1", "events")
    assert jobs["events_am"]["schedule"]["time"] == "08:20"
    routes = {(r["method"], r["path"]): r["module"] for r in model["routes"]}
    assert routes[("GET", "/items")] == "M2.1" and routes[("GET", "/health")] == "M1.1"
    files = {f["path"]: f["owner"] for f in model["files"]}
    assert files["core/store.py"] == "M2"                  # a module's own exact path
    assert files["core/engine/main.py"] == "M2"
    assert files["services/api/routes/items.py"] == "M2.1"
    assert files["core/__init__.py"] == "shared"
    assert model["modules"][0]["submodules"][0]["logic"][0]["children"][0]["text"] == (
        "jobs\ncontinued")
    assert {s["key"] for s in model["switches"]} >= {"events.enabled", "audit.enabled",
                                                     "rl.learning_mode"}


def test_trees_md_draws_the_clock_trees_and_production_values(repo):
    text = (repo / TREES).read_text(encoding="utf-8")
    assert "Code inspected: `unknown`" in text
    assert "ask ─► answer" in text
    assert "├── jobs\n│   continued\n└── more" in text
    assert "events_am (Mon–Fri)" in text and "[flag events.enabled]" in text
    assert "(also 12:00)" in text
    assert "production: `observe` (KT section 1, as of 2026-10-01)" in text
    assert "One thing's life" in text


# -- the generated part drifts -------------------------------------------------

def test_a_changed_file_makes_the_model_stale(repo):
    (repo / "core/store.py").write_text("x = 1\ny = 2\nz = 3\n", encoding="utf-8")
    problem = _only(check.run(repo))
    assert "model.json is stale" in problem and "core/store.py" in problem
    assert "recorded 2, found 3" in problem
    assert "python tools/architecture_map/model/generate.py" in problem


def test_a_changed_job_time_makes_the_model_stale(repo):
    fx.edit(repo, "config.yaml", 'morning: "08:20"', 'morning: "07:05"')
    problem = _only(check.run(repo))
    assert "stale" in problem and "events_am" in problem


def test_a_changed_import_makes_the_model_stale(repo):
    fx.edit(repo, "scripts/tool.py", "from core.engine.main import Engine\n",
            "from core import store\n")
    assert "scripts/tool.py" in _only(check.run(repo))


def test_a_changed_curated_tree_makes_the_model_stale(repo):
    fx.curated(repo, "modules/M02.yaml", "ask ─► answer", "ask ─► think ─► answer")
    assert "stale" in _only(check.run(repo))


def test_a_hand_edit_of_trees_md_is_caught(repo):
    with (repo / TREES).open("a", encoding="utf-8") as handle:
        handle.write("by hand\n")
    assert "TREES.md differs from the model" in _only(check.run(repo))


def test_a_reformatted_model_is_caught(repo):
    model = json.loads((repo / MODEL).read_text(encoding="utf-8"))
    (repo / MODEL).write_text(json.dumps(model), encoding="utf-8")
    assert "its bytes differ" in _only(check.run(repo))


@pytest.mark.parametrize("name", [MODEL, TREES])
def test_a_missing_output_is_named(repo, name):
    (repo / name).unlink()
    assert f"{name} is missing" in _only(check.run(repo))


@pytest.mark.parametrize("content", ["{not json", "[]", "{}"])
def test_an_unreadable_model_is_named(repo, content):
    (repo / MODEL).write_text(content, encoding="utf-8")
    assert "cannot be read" in _only(check.run(repo))


def test_a_later_commit_that_changes_no_code_still_passes(tmp_path):
    """The stamp records what was inspected; it is not compared."""
    root = fx.make(tmp_path / "repo")

    def git(*args):
        subprocess.run(["git", "-c", "user.email=t@example.invalid", "-c", "user.name=t", *args],
                       cwd=root, check=True, capture_output=True)

    git("init", "-q")
    git("add", "-A")
    git("commit", "-qm", "one")
    assert generate.write(root) == []
    stamp = json.loads((root / MODEL).read_text(encoding="utf-8"))["stamp"]
    assert re.fullmatch(r"[0-9a-f]{40}", stamp["commit"]) and stamp["uncommitted_code"] is False
    fx.write(root, "docs/note.md", "a note\n")
    git("add", "-A")
    git("commit", "-qm", "two")
    assert check.run(root) == []


def test_uncommitted_code_is_stamped_and_an_ignored_file_is_not_read(tmp_path):
    root = fx.make(tmp_path / "repo")

    def git(*args):
        subprocess.run(["git", "-c", "user.email=t@example.invalid", "-c", "user.name=t", *args],
                       cwd=root, check=True, capture_output=True)

    fx.write(root, ".gitignore", "scratch.py\n")
    git("init", "-q")
    git("add", "-A")
    git("commit", "-qm", "one")
    fx.write(root, "core/scratch.py", "x = 1\n")                  # ignored: not part of the code
    assert generate.write(root) == []
    assert "core/scratch.py" not in (root / MODEL).read_text(encoding="utf-8")
    fx.write(root, "core/store.py", "x = 1\n")
    assert generate.write(root) == []
    assert json.loads((root / MODEL).read_text(encoding="utf-8"))["stamp"][
        "uncommitted_code"] is True


# -- the curated part names what does not exist ----------------------------------

@pytest.mark.parametrize("name,old,new,expected", [
    ("modules/M02.yaml", "core/store.py", "core/gone.py", "core/gone.py does not exist"),
    ("modules/M02.yaml", '"core/engine/*.py"', '"core/engine/*.pyx"', "matches nothing"),
    ("modules/M02.yaml", "core/engine/main.py::later", "core/engine/main.py::missing",
     "defines no missing"),
    ("modules/M02.yaml", "core/engine/main.py::Engine.run", "core/engine/main.py::Engine.gone",
     "defines no Engine.gone"),
    ("stores.yaml", "core/portfolio/advisor.py::decide", "core/portfolio/gone.py::decide",
     "core/portfolio/gone.py does not exist"),
    ("modules/M01.yaml", "rl.learning_mode]", "rl.no_such_switch]",
     "config key rl.no_such_switch does not exist"),
    ("overview.yaml", "path: core/engine/", "path: core/vanished/",
     "core/vanished/ does not exist"),
])
def test_a_curated_path_function_or_key_that_does_not_exist(repo, name, old, new, expected):
    fx.curated(repo, name, old, new)
    problems = check.run(repo)
    assert any(expected in p and "fix: " in p for p in problems), problems


def test_a_function_renamed_in_the_code_is_caught(repo):
    fx.edit(repo, "core/portfolio/advisor.py", "def decide():", "def choose():")
    problems = check.run(repo)
    assert any("defines no decide" in p for p in problems), problems


# -- belongs to no module ------------------------------------------------------

def test_a_new_job_belongs_to_no_module(repo):
    fx.edit(repo, SCHEDULER, '        if cfg("audit.enabled", fallback=True):',
            '        scheduler.add_job(func=self._x, trigger=CronTrigger(hour=1, minute=0),\n'
            '                          id="brand_new")\n'
            '        if cfg("audit.enabled", fallback=True):')
    assert "job brand_new belongs to no module" in _only(check.run(repo))


def test_a_curated_job_the_scheduler_does_not_register(repo):
    fx.curated(repo, "jobs.yaml", "macro: {module: M1.1, does: macro news}",
               "macro: {module: M1.1, does: macro news}\ngone: {module: M1.1, does: x}")
    assert "does not register" in _only(check.run(repo))


def test_a_new_route_belongs_to_no_module(repo):
    fx.edit(repo, "services/api/server.py", '@app.get("/health")',
            '@app.get("/brand-new")\ndef brand_new():\n    return None\n\n\n@app.get("/health")')
    assert "route GET /brand-new (services/api/server.py) belongs to no module" in _only(
        check.run(repo))


def test_a_route_rule_that_matches_nothing_and_a_catch_all(repo):
    fx.curated(repo, "routes.yaml", "- {prefix: /live, module: M2.1}",
               "- {prefix: /live, module: M2.1}\n- {prefix: /old, module: M2.1}\n"
               "- {prefix: /, module: M1.1}")
    problems = check.run(repo)
    assert any("/old matches no route" in p for p in problems), problems
    assert any("catch-all" in p for p in problems), problems


def test_the_longest_route_prefix_wins():
    rules = [{"prefix": "/ui", "module": "M1"}, {"prefix": "/ui/chat", "module": "M2"}]
    assert validate.route_rule("/ui/chat/stream", rules)["module"] == "M2"
    assert validate.route_rule("/ui/chatter", rules)["module"] == "M1"
    assert validate.route_rule("/other", rules) is None


def test_a_new_python_file_belongs_to_no_module(repo):
    fx.write(repo, "core/new_part/thing.py", "x = 1\n")
    assert "core/new_part/thing.py belongs to no module" in _only(check.run(repo))


def test_a_file_two_modules_claim_is_refused(repo):
    fx.curated(repo, "modules/M01.yaml", "services/api/server.py]",
               'services/api/server.py, "core/portfolio/*.py"]')
    fx.curated(repo, "modules/M02.yaml", "core/portfolio/__init__.py, core/portfolio/advisor.py, ",
               '"core/portfolio/*.py", ')
    problems = check.run(repo)
    assert any("core/portfolio/advisor.py is claimed by M1.1 and M2.2" in p for p in problems), (
        problems)


def test_an_exact_path_beats_a_pattern_and_a_sub_module_beats_its_module():
    owners = [("M1", ["core/**/*.py"]), ("M1.1", ["core/a/*.py"]),
              ("M2.1", ["core/a/special.py"])]
    problems: list[str] = []
    result = validate.own_files(["core/a/x.py", "core/a/special.py", "core/b/y.py"], owners,
                                problems)
    assert problems == []
    assert result == {"core/a/x.py": "M1.1", "core/a/special.py": "M2.1", "core/b/y.py": "M1"}


@pytest.mark.parametrize("pattern,path,matches", [
    ("core/*.py", "core/a.py", True), ("core/*.py", "core/x/a.py", False),
    ("core/**/*.py", "core/a.py", True), ("core/**/*.py", "core/x/y/a.py", True),
    ("core/**", "core/x/a.py", True), ("core/?.py", "core/a.py", True),
    ("core/a.py", "core/aXpy", False),
])
def test_file_patterns(pattern, path, matches):
    assert bool(validate.glob_regex(pattern).match(path)) is matches


# -- references and production values --------------------------------------------

@pytest.mark.parametrize("name,old,new,expected", [
    ("flows.yaml", "to: M2, what: ticks", "to: M9, what: ticks", "M9, which the model lacks"),
    ("flows.yaml", "from: M2.1", "from: S.nothing", "S.nothing, which the model lacks"),
    ("stores.yaml", "writers: [M2.1]", "writers: [M2.7]", "M2.7, which the model lacks"),
    ("stores.yaml", "readers: [M2.2]", "readers: [S.items]", "S.items, which the model lacks"),
    ("trace.yaml", "daily_review, S.items]", "no_such_job, S.items]",
     "no_such_job, which the model lacks"),
    ("trace.yaml", "ref: M2.2", "ref: M4.4", "M4.4, which the model lacks"),
    ("jobs.yaml", "audit_nightly: {module: M1.1", "audit_nightly: {module: M3.1",
     "module M3.1 is not in the model"),
    ("routes.yaml", "prefix: /items, module: M2.1", "prefix: /items, module: M8",
     "module M8 is not in the model"),
])
def test_a_flow_store_trace_or_tour_naming_what_the_model_lacks(repo, name, old, new,
                                                                 expected):
    fx.curated(repo, name, old, new)
    problems = check.run(repo)
    assert any(expected in p and "fix: " in p for p in problems), problems


@pytest.mark.parametrize("old,new,expected", [
    ("source: KT section 1", "source: a hunch", "cites no source"),
    ("  source: KT section 1\n", "", "must have the keys"),
    ("as_of: 2026-10-01", "as_of: last week", "is not a date"),
    ("value: observe", 'value: ""', "has no value"),
    ("key: rl.learning_mode", "key: rl.gone", "config key rl.gone does not exist"),
    ("- key: rl.learning_mode\n", "- note: x\n", "needs a key or a name"),
])
def test_a_production_value_must_cite_its_source(repo, old, new, expected):
    fx.curated(repo, "production.yaml", old, new)
    problems = check.run(repo)
    assert any(expected in p for p in problems), problems


@pytest.mark.parametrize("name,old,new,expected", [
    ("modules/M02.yaml", "plane: middle", "plane: sideways", "plane 'sideways'"),
    ("modules/M02.yaml", "id: M2.1\n", "id: M1.1\n", "is not M2.<number>"),
    ("modules/M02.yaml", "      ask ─► answer\n", "      ask\n          too deep\n",
     "two levels deeper"),
    ("modules/M02.yaml", "summary: decides", "summary: decides\n    colour: red",
     "unknown keys"),
    ("flows.yaml", "- {from: M1, to: M2, what: ticks}", "- {from: M1, to: M2}",
     "must have the keys"),
    ("flows.yaml", "- {from: M1, to: M2, what: ticks}", "- [oops", "cannot be read"),
])
def test_a_badly_formed_curated_file_is_reported_not_raised(repo, name, old, new, expected):
    fx.curated(repo, name, old, new)
    problems = check.run(repo)
    assert any(expected in p and "fix: " in p for p in problems), problems


def test_a_missing_curated_file_is_reported(repo):
    shutil.rmtree(repo / fx.CURATED_DIR / "modules")
    assert any("holds no module file" in p for p in check.run(repo))


def test_an_unreadable_source_is_reported_not_raised(repo):
    fx.write(repo, "core/store.py", "def (:\n")
    assert "core/store.py" in _only(check.run(repo))


def test_generate_writes_nothing_when_the_curated_part_is_wrong(tmp_path):
    root = fx.make(tmp_path / "repo")
    fx.curated(root, "flows.yaml", "to: M2, what: ticks", "to: M9, what: ticks")
    assert generate.write(root)
    assert not (root / MODEL).exists() and not (root / TREES).exists()


def test_the_command_line_exit_codes(repo, capsys):
    assert check.main(["--root", str(repo)]) == 0
    assert "match the code" in capsys.readouterr().out
    fx.write(repo, "core/new_part/thing.py", "x = 1\n")
    assert check.main(["--root", str(repo)]) == 1
    assert "belongs to no module" in capsys.readouterr().out
    assert generate.main(["--root", str(repo)]) == 1
    assert "nothing written" in capsys.readouterr().out


def test_the_scripts_run_as_files_from_any_folder(repo):
    """`python tools/.../check.py` is how CI and the fix text run them."""
    script = ROOT / "tools/architecture_map/model/check.py"
    done = subprocess.run([__import__("sys").executable, str(script), "--root", str(repo)],
                          capture_output=True, text=True, cwd=repo.parent)
    assert done.returncode == 0, done.stdout + done.stderr
    assert "match the code" in done.stdout


# -- the real repository -------------------------------------------------------

@pytest.fixture(scope="module")
def real():
    model, problems = build.build_model(ROOT)
    assert problems == []
    return model


def test_the_real_repository_passes_the_guard():
    problems = check.run(ROOT)
    assert problems == [], "\n".join(problems)


def test_the_jobs_are_the_ones_kt_section_9_lists(real):
    kt = (ROOT / "docs/TECHNICAL_DESIGN.md").read_text(encoding="utf-8")
    clock = kt.split("## 9.", 1)[1].split("## 10.", 1)[0]
    documented = re.findall(r"^\| `([^`]+)` \|", clock, re.M)
    assert sorted(j["id"] for j in real["jobs"]) == sorted(documented)
    assert len(documented) == 25


def test_every_part_of_the_real_model_is_filled(real):
    assert [m["id"] for m in real["modules"]] == [f"M{n}" for n in range(1, 13)]
    assert all(s["logic"] for m in real["modules"] for s in m["submodules"])
    assert real["routes"] and all(r["module"] for r in real["routes"])
    owners = {f["owner"] for f in real["files"]}
    assert all(m["id"] in owners or any(s["id"] in owners for s in m["submodules"])
               for m in real["modules"])
    assert all(p["source"] == "KT section 1" for p in real["production"])
    assert real["traces"] and real["flows"] and real["stores"]


def test_the_seed_walkthrough_was_replaced_by_trees_md():
    folder = ROOT / "docs/architecture-map"
    assert not (folder / "seed-walkthrough-2026-11-22.md").exists()
    assert (folder / "walkthrough-2026-11-26.md").exists()


# -- the Opus check's cases: one line and a fix, never a traceback ---------------

@pytest.mark.parametrize("name,old,new", [
    ("stores.yaml", "writers: [M2.1]", "writers: 5"),
    ("stores.yaml", "writers: [M2.1]", "writers: [[M2.1]]"),
    ("stores.yaml", 'code: ["core/portfolio/advisor.py::decide"]', "code:"),
    ("stores.yaml", "name: Items", "name:"),
    ("flows.yaml", "from: M1,", "from: [M1],"),
    ("flows.yaml", "what: ticks", "what:"),
    ("routes.yaml", "{prefix: /items, module: M2.1}", "{prefix: /items, module: [M2.1]}"),
    ("jobs.yaml", "macro: {module: M1.1,", "macro: {module: [M1.1],"),
    ("jobs.yaml", "daily_review: {", "1: {"),
    ("production.yaml", "key: rl.learning_mode", "key: [a]"),
    ("trace.yaml", "refs: [M1.1, daily_review, S.items]", "refs: 3"),
    ("trace.yaml", "refs: [M1.1, daily_review, S.items]", "refs: [[M1.1]]"),
    ("trace.yaml", "tours:\n", "tours: 5\nextra:\n"),
    ("overview.yaml", "title: Fixture map\n", ""),
    ("overview.yaml", "externals:", "externals: {a: 1}\nxx:"),
    ("overview.yaml", "      - {path: core/engine/, note: the engine}", "      - 3"),
    ("overview.yaml", "path: core/\n", "path: /etc\n"),
    ("overview.yaml", "path: core/engine/", "path: ../"),
    ("shared.yaml", "files: [core/__init__.py]", "files: [core/__init__.py, null]"),
    ("shared.yaml", "files: [core/__init__.py]", 'files: [core/__init__.py, "/tmp/*"]'),
    ("modules/M01.yaml", "short: Platform", "short: 5"),
    ("modules/M01.yaml", "    name: Scheduler\n", "    name:\n"),
    ("modules/M01.yaml", "summary: runs things", "summary:"),
    ("modules/M01.yaml", "column: 0", "column: true"),
    ("modules/M01.yaml", "id: M1\n", "id: [1]\n"),
    ("modules/M02.yaml", 'code: ["core/portfolio/advisor.py::decide"]',
     'code: ["/etc/passwd::x"]'),
])
def test_a_wrong_type_or_path_gets_one_line_and_a_fix(repo, capsys, name, old, new):
    fx.curated(repo, name, old, new)
    assert check.main(["--root", str(repo)]) == 1
    printed = capsys.readouterr().out.strip().split("\n")
    assert all("fix: " in line for line in printed), printed
    assert not any("cannot check" in line for line in printed), printed
    assert generate.main(["--root", str(repo)]) == 1
    assert "cannot generate" not in capsys.readouterr().out


def test_an_unforeseen_error_still_prints_one_line_with_a_fix(repo, capsys, monkeypatch):
    def boom(*args, **kwargs):
        raise KeyError("surprise\nsecond line")

    monkeypatch.setattr(build, "build_model", boom)
    assert check.main(["--root", str(repo)]) == 1
    printed = capsys.readouterr().out.strip()
    assert "\n" not in printed and "cannot check (KeyError" in printed and "fix: " in printed
    assert generate.main(["--root", str(repo)]) == 1
    assert "cannot generate (KeyError" in capsys.readouterr().out


def test_a_stale_continuation_line_is_still_one_line(repo):
    fx.curated(repo, "modules/M01.yaml", "| continued", "| continued again")
    assert "stale" in _only(check.run(repo))


def test_a_stamp_that_names_no_commit_is_refused(repo):
    model = json.loads((repo / MODEL).read_text(encoding="utf-8"))
    model["stamp"] = "by hand"
    (repo / MODEL).write_text(json.dumps(model), encoding="utf-8")
    assert "its stamp names no commit" in _only(check.run(repo))


def test_a_curated_key_naming_a_whole_section_is_refused(repo):
    fx.edit(repo, "config.yaml", "events:\n  enabled: true\n",
            "events:\n  nested:\n    a: 1\n  enabled: true\n")
    fx.curated(repo, "modules/M01.yaml", "config: [events.enabled,", "config: [events,")
    problems = check.run(repo)
    assert any("events is a whole section" in p for p in problems), problems

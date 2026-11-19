"""PR-040: members see three screens and load no operator code.

Static invariants over the served folder (src/frontend/prototypes), read from
the files themselves rather than from the implementation's own lists:

- index.html's static script tags name no operator screen; every .jsx in the
  folder is either loaded by them or named in SA_OPERATOR_FILES, and that list
  holds exactly the files that define an operator screen;
- sw.js's precache list names no operator, removed or demo-only file, and every
  file it names exists;
- the Learn page, the Tweaks panel and the internal UI spec are not in the
  served folder.

The browser behaviour (navigation, the files each role requests, the first
open over the previous version's scripts) is in
tests/frontend/member_screens.test.mjs, run by the last test here.
"""
from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
PROTO = REPO / "src" / "frontend" / "prototypes"

# The components of the owner's screens (index.html's OPERATOR_SCREENS), and
# the helper module only the RL Monitor reads.
OPERATOR_COMPONENTS = {"AgentsPage", "AnalyticsPage", "LogsPage", "RLMonitorPage"}


def _html() -> str:
    return (PROTO / "index.html").read_text(encoding="utf-8")


def _static_babel_scripts() -> list[str]:
    return re.findall(r'<script type="text/babel" src="([^"]+)"></script>', _html())


def _operator_files() -> list[str]:
    m = re.search(r"window\.SA_OPERATOR_FILES = \[([^\]]*)\]", _html())
    assert m, "index.html names its operator files in SA_OPERATOR_FILES"
    return re.findall(r"'([^']+)'", m.group(1))


def _defines(name: str) -> set[str]:
    src = (PROTO / name).read_text(encoding="utf-8")
    return set(re.findall(r"^window\.(\w+)\s*=\s*\w+;", src, flags=re.M))


def test_operator_files_are_exactly_the_files_that_define_operator_screens():
    ops = _operator_files()
    defining = {p.name for p in PROTO.glob("*.jsx") if _defines(p.name) & OPERATOR_COMPONENTS}
    assert defining == {"agents-page.jsx", "analytics.jsx", "logs.jsx", "rl-monitor.jsx"}
    assert defining <= set(ops)
    # rl-data.jsx: the RL Monitor's data module, read by nothing a member loads
    assert set(ops) - defining == {"rl-data.jsx"}
    member_src = "\n".join((PROTO / f).read_text(encoding="utf-8") for f in _static_babel_scripts())
    assert "RL_TICKERS" not in member_src and "rlFetch" not in member_src


def test_index_html_loads_no_operator_file_and_every_screen_file_is_accounted_for():
    static = _static_babel_scripts()
    ops = _operator_files()
    assert static, "no static screen scripts found"
    assert not set(static) & set(ops), set(static) & set(ops)
    assert not re.search(r'src="(?:%s)"' % "|".join(map(re.escape, ops)), _html())
    every_jsx = {p.name for p in PROTO.glob("*.jsx")}
    assert every_jsx == set(static) | set(ops), every_jsx ^ (set(static) | set(ops))


def test_the_service_worker_precaches_member_files_only():
    sw = (PROTO / "sw.js").read_text(encoding="utf-8")
    block = sw[sw.index("const SHELL = ["):sw.index("];", sw.index("const SHELL = ["))]
    listed = [p.lstrip("/") for p in re.findall(r"'(/[^']*)'", block) if p != "/"]
    for name in _operator_files() + ["learn.jsx", "tweaks-panel.jsx", "prompt-lab.jsx", "demo-fixtures.js"]:
        assert name not in listed, name
    for name in listed:
        assert (PROTO / name).is_file(), name
    # every member screen script is precached, so the installed app opens offline
    assert set(_static_babel_scripts()) <= set(listed)


def test_removed_screens_and_the_spec_are_not_served():
    for gone in ("learn.jsx", "tweaks-panel.jsx", "UI_SPEC.md"):
        assert not (PROTO / gone).exists(), gone
    assert (REPO / "src" / "frontend" / "UI_SPEC.md").is_file()
    assert not list(PROTO.glob("*.md"))
    html = _html()
    for gone in ("LearnPage", "TweaksPanel", "useTweaks", "proto-nav"):
        assert gone not in html, gone


def test_member_browser_suite():
    """Runs the real-browser suite (needs node, `npm ci`, and Playwright's Chromium)."""
    node = shutil.which("node")
    if not node:
        pytest.skip("node is not on PATH")
    if not (REPO / "node_modules" / "playwright").exists():
        pytest.skip("node_modules missing: run `npm ci`")
    proc = subprocess.run([node, "--test", "tests/frontend/member_screens.test.mjs"], cwd=REPO,
                          capture_output=True, text=True, encoding="utf-8", timeout=900)
    out = proc.stdout + proc.stderr
    if "Executable doesn't exist" in out:
        pytest.skip("Chromium missing: run `npx playwright install chromium`")
    assert proc.returncode == 0, out[-4000:]

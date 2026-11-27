"""MAP-002 and MAP-003: the committed architecture map in a real browser.

The checks are in tests/frontend/architecture_map.test.mjs (the built page, opened from
disk with the network off: the world, the panel, the clock, the trace and the tour) and
architecture_map_logic.test.mjs (layout, flowcharts, what each step lights, colours, and
that the page was built from the committed viewer). This runs both in the full suite; CI's
browser job runs them through `npm run test:frontend`.
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]


def test_architecture_map_browser_suite():
    """Needs node, `npm ci` at the repository root, and Playwright's Chromium."""
    node = shutil.which("node")
    if not node:
        pytest.skip("node is not on PATH")
    if not (REPO / "node_modules" / "playwright").exists():
        pytest.skip("node_modules missing: run `npm ci`")
    proc = subprocess.run([node, "--test", "tests/frontend/architecture_map.test.mjs",
                           "tests/frontend/architecture_map_logic.test.mjs"], cwd=REPO,
                          # about 6 minutes in software rendering on a small box (MAP-003);
                          # the memory guard allows a browser test 960 s
                          capture_output=True, text=True, encoding="utf-8", timeout=900)
    out = proc.stdout + proc.stderr
    if "Executable doesn't exist" in out:
        pytest.skip("Chromium missing: run `npx playwright install chromium`")
    assert proc.returncode == 0, out[-4000:]

"""Atlas C2 / R1 guard — the intelligence plane never imports the user plane.

Learning Constitution R1 (docs/SCALING_BLUEPRINTS.md:231) prescribed an
import-boundary check but it was never implemented — R1 held only by
convention. This is that guard: it AST-walks every module under
core/intelligence/** and asserts none of them import the user-plane data
stores (the VerdictStore facade, atlas_store, user_store, the portfolio store,
or feedback_events). The one allowed arrow is user→intelligence
(VerdictStore imports PredictionStore); this test proves the reverse arrow
never appears.

The synthetic-negative test proves the checker actually detects a leak, so a
green walk is meaningful (not vacuously passing).
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

# Module paths the intelligence plane must never import (prefix match), plus
# substrings that flag a user-plane table module wherever it ends up living.
_FORBIDDEN_PREFIXES = (
    "services.data.verdict_store",
    "services.data.stores.atlas_store",
    "services.data.stores.user_store",
    "core.portfolio.store",
)
_FORBIDDEN_SUBSTRINGS = ("feedback_events",)

_REPO_ROOT = Path(__file__).resolve().parents[2]
_INTELLIGENCE = _REPO_ROOT / "core" / "intelligence"


def _imported_modules(source: str) -> set[str]:
    """All absolute import targets in `source` (both `import a.b` and
    `from a.b import c`, the latter also yielding `a.b.c`)."""
    out: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            for alias in node.names:
                out.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            base = node.module or ""            # level>0 relative → stays in-package
            if base:
                out.add(base)
                for alias in node.names:
                    out.add(f"{base}.{alias.name}")
    return out


def _forbidden_hits(source: str) -> set[str]:
    mods = _imported_modules(source)
    return {
        m for m in mods
        if any(m == p or m.startswith(p + ".") for p in _FORBIDDEN_PREFIXES)
        or any(s in m for s in _FORBIDDEN_SUBSTRINGS)
    }


def test_intelligence_plane_imports_no_user_plane():
    assert _INTELLIGENCE.is_dir(), f"missing {_INTELLIGENCE}"
    violations: dict[str, set[str]] = {}
    for py in _INTELLIGENCE.rglob("*.py"):
        try:
            src = py.read_text(encoding="utf-8-sig")   # tolerate a leading BOM
        except OSError:
            continue
        hits = _forbidden_hits(src)
        if hits:
            violations[str(py.relative_to(_REPO_ROOT))] = hits
    assert not violations, (
        "R1 breach — intelligence plane imports user-plane data stores:\n"
        + "\n".join(f"  {f}: {sorted(h)}" for f, h in violations.items())
    )


@pytest.mark.parametrize("leak", [
    "from services.data.verdict_store import VerdictStore",
    "import services.data.stores.atlas_store",
    "from services.data.stores.user_store import get_user",
    "from core.portfolio.store import PortfolioStore",
    "from services.data.stores.feedback_events import record",
])
def test_checker_flags_a_real_leak(leak):
    # The checker must catch each forbidden import — otherwise a green walk
    # above would be meaningless.
    assert _forbidden_hits(leak + "\nimport os\n")


def test_checker_ignores_the_allowed_arrow():
    # user→intelligence (importing PredictionStore) is fine and must NOT flag.
    ok = "from core.intelligence.rl.stores.prediction_store import PredictionStore\n"
    assert _forbidden_hits(ok) == set()

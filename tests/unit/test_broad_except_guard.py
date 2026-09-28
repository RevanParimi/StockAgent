"""SA-005: the CI guard against new unlogged broad exception swallowing.

Each snippet's expected verdict is written by hand from the rule in the
script's docstring, not read back from the scanner.
"""
from __future__ import annotations

import importlib.util
import textwrap
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location(
    "check_broad_except", _ROOT / "scripts" / "ci" / "check_broad_except.py")
guard = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(guard)


def _flags(src: str) -> list[int]:
    """Line numbers the scanner reports for a snippet, pragma'd ones excluded."""
    found = guard.scan_source("pkg/mod.py", textwrap.dedent(src))
    return [line for _key, line, pragma, _text in found if not pragma]


@pytest.mark.parametrize("src, line", [
    ("try:\n    f()\nexcept Exception:\n    pass\n", 3),
    ("try:\n    f()\nexcept:\n    return_value = None\n", 3),
    ("try:\n    f()\nexcept BaseException:\n    x = 1\n", 3),
    ("try:\n    f()\nexcept (ValueError, Exception):\n    y = None\n", 3),
    ("try:\n    f()\nexcept builtins.Exception:\n    pass\n", 3),
    ("def g():\n    try:\n        f()\n    except Exception as exc:\n        return None\n", 4),
    ("def g():\n    for i in x:\n        try:\n            f()\n        except Exception:\n"
     "            continue\n", 5),
])
def test_silent_broad_handlers_are_flagged(src, line):
    assert _flags(src) == [line]


@pytest.mark.parametrize("src", [
    "try:\n    f()\nexcept ValueError:\n    pass\n",                       # narrow
    "try:\n    f()\nexcept (KeyError, OSError):\n    pass\n",               # narrow tuple
    "try:\n    f()\nexcept Exception:\n    logger.warning('x')\n",          # logged
    "try:\n    f()\nexcept Exception:\n    log.debug('x')\n",               # logged, any level
    "try:\n    f()\nexcept Exception:\n    logging.exception('x')\n",
    "try:\n    f()\nexcept Exception:\n    traceback.print_exc()\n",
    "try:\n    f()\nexcept Exception:\n    cleanup()\n    raise\n",            # re-raised
    "try:\n    f()\nexcept Exception as exc:\n    raise Wrapped() from exc\n",
    "try:\n    f()\nexcept Exception as exc:\n    return {'error': str(exc)}\n",  # carried on
    "try:\n    f()\nexcept Exception as exc:\n    rec.error = repr(exc)\n",
])
def test_handled_or_narrow_handlers_pass(src):
    assert _flags(src) == []


def test_broad_suppress_is_a_swallow_but_narrow_suppress_is_not():
    src = """\
    import contextlib
    with contextlib.suppress(Exception):
        f()
    with suppress(KeyError):
        g()
    with open(p), suppress(OSError, BaseException):
        h()
    """
    assert _flags(src) == [2, 6]


def test_pragma_needs_a_reason():
    src = """\
    try:
        f()
    except Exception:  # swallow-ok: best-effort warm-up; a miss is harmless
        pass
    try:
        g()
    except Exception:  # swallow-ok:
        pass
    """
    assert _flags(src) == [7]


def test_keys_follow_function_and_ordinal_not_line():
    src_a = """\
    class Store:
        def load(self):
            try:
                f()
            except Exception:
                pass
    """
    src_b = "\n\n\n# moved down\n" + textwrap.dedent(src_a)
    key_a = [k for k, *_ in guard.scan_source("m.py", textwrap.dedent(src_a))]
    key_b = [k for k, *_ in guard.scan_source("m.py", src_b)]
    assert key_a == key_b == ["m.py | Store.load | #0"]


def _repo(tmp_path: Path, files: dict[str, str]) -> Path:
    for rel, src in files.items():
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(textwrap.dedent(src), encoding="utf-8")
    return tmp_path


_ONE = """\
def load():
    try:
        f()
    except Exception:
        pass
"""


def test_check_passes_on_baseline_and_fails_on_a_new_swallow(tmp_path, monkeypatch):
    monkeypatch.setattr(guard, "_python_files", lambda root: sorted(
        p.relative_to(root).as_posix() for p in root.rglob("*.py")))
    root = _repo(tmp_path, {"core/a.py": _ONE, "tests/test_x.py": _ONE})
    baseline = tmp_path / "baseline.txt"
    guard.write_baseline({"core/a.py | load | #0", "tests/test_x.py | load | #0"}, baseline)
    assert guard.check(root, baseline) == ([], [])

    # A second silent handler in the same function is new, even though the
    # file already has an allowlisted one.
    (root / "core/a.py").write_text(textwrap.dedent(_ONE) + textwrap.dedent("""\
    def save():
        try:
            g()
        except:
            return None
    """), encoding="utf-8")
    new, stale = guard.check(root, baseline)
    assert len(new) == 1 and "core/a.py:9" in new[0] and "save | #0" in new[0]
    assert stale == []


def test_fixing_a_swallow_makes_its_entry_stale(tmp_path, monkeypatch):
    monkeypatch.setattr(guard, "_python_files", lambda root: sorted(
        p.relative_to(root).as_posix() for p in root.rglob("*.py")))
    root = _repo(tmp_path, {"core/a.py": _ONE.replace("pass", "logger.warning('x')")})
    baseline = tmp_path / "baseline.txt"
    guard.write_baseline({"core/a.py | load | #0"}, baseline)
    assert guard.check(root, baseline) == ([], ["core/a.py | load | #0"])


def test_real_tree_matches_its_baseline():
    """The committed baseline is exact for the committed tree: no new silent
    broad handler has been added and every grandfathered one still exists."""
    new, stale = guard.check()
    assert new == [], "\n".join(new)
    assert stale == [], "\n".join(stale)

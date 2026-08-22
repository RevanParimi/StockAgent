"""Shared isolation for the watchdog tests.

The watchdog resolves the atlas flag against the LIVE config.yaml, so every
test whose premise is "the C11 cutover has not happened yet" was really
asserting "...and config.yaml still says false". That held right up until the
cutover flipped it, at which point 14 tests went red without a single line of
watchdog code changing. The tests were reading the repo's deploy state.

`delenv("ATLAS_ENABLED")` does not isolate this on its own: the flag resolves
as cfg("atlas.enabled", env="ATLAS_ENABLED", fallback=False), so clearing the
env override merely falls through to yaml. Pin the yaml layer as well, and a
test states its own premise instead of inheriting one.

This only sets the DEFAULT. Tests that need the flag on still win, whether
they set the env var (which overrides yaml) or set this same yaml key True in
the test body (which runs after this fixture) - and the two tests that prove a
yaml-only flip closes the milestone keep doing exactly that.
"""
import pytest


@pytest.fixture(autouse=True)
def _atlas_flag_off_unless_a_test_says_otherwise(monkeypatch):
    import backend.shared.config.settings.loader as loader_mod
    atlas = loader_mod._YAML.get("atlas")
    if isinstance(atlas, dict):
        monkeypatch.setitem(atlas, "enabled", False)

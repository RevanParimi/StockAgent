"""
config/settings/loader.py
=========================
Loads repo-root config.yaml once at import and resolves individual settings
with precedence:  environment variable  >  config.yaml  >  hardcoded fallback.

base.py is the only intended consumer (via `from .loader import cfg`); the
40+ modules that read `settings.<NAME>` are untouched by this layer.

File resolution order:
  1. CONFIG_FILE env var (explicit path; if it doesn't exist, warn and fall
     back to defaults rather than guessing another location)
  2. Path.cwd()/config.yaml   (repo root locally, /app in the Docker image)
  3. walk upward from this file's directory (handles the src/ layout when
     cwd differs, e.g. IDE test runners)

Missing file  → warn once, return {} (all fallbacks apply — identical to the
                pre-YAML behavior).
Malformed file → RuntimeError at import (fail loud, never run on a silently
                broken config).
"""
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)

_TRUE_STRINGS = {"true", "1", "yes", "on"}
_FALSE_STRINGS = {"false", "0", "no", "off"}
_MISSING = object()


def _find_config_file() -> Path | None:
    env_path = os.getenv("CONFIG_FILE")
    if env_path:
        p = Path(env_path)
        if p.is_file():
            return p
        logger.warning("[config] CONFIG_FILE=%s does not exist — using fallbacks", env_path)
        return None
    cwd_candidate = Path.cwd() / "config.yaml"
    if cwd_candidate.is_file():
        return cwd_candidate
    for parent in Path(__file__).resolve().parents:
        candidate = parent / "config.yaml"
        if candidate.is_file():
            return candidate
    return None


def load_yaml() -> dict:
    path = _find_config_file()
    if path is None:
        logger.warning("[config] no config.yaml found — running on hardcoded defaults")
        return {}
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise RuntimeError(f"Malformed config.yaml at {path}: {exc}") from exc
    if data is None:
        return {}
    if not isinstance(data, dict):
        raise RuntimeError(
            f"config.yaml at {path} must be a top-level mapping, got {type(data).__name__}"
        )
    logger.info("[config] loaded %s", path)
    return data


_YAML: dict = load_yaml()


def _dig(dotted: str) -> Any:
    node: Any = _YAML
    for part in dotted.split("."):
        if not isinstance(node, dict) or part not in node:
            return _MISSING
        node = node[part]
    return node


def _coerce(raw: str, target: Any, key: str) -> Any:
    """Coerce an env-var string to the type of `target` (YAML value or fallback)."""
    if isinstance(target, bool):
        low = raw.strip().lower()
        if low in _TRUE_STRINGS:
            return True
        if low in _FALSE_STRINGS:
            return False
        raise ValueError(f"Config key {key}: cannot parse bool from {raw!r}")
    if isinstance(target, int) and not isinstance(target, bool):
        try:
            return int(raw)
        except ValueError as exc:
            raise ValueError(f"Config key {key}: expected int, got {raw!r}") from exc
    if isinstance(target, float):
        try:
            return float(raw)
        except ValueError as exc:
            raise ValueError(f"Config key {key}: expected float, got {raw!r}") from exc
    if isinstance(target, (list, tuple)):
        return [item.strip() for item in raw.split(",") if item.strip()]
    return raw


def cfg(path: str, env: str | None = None, fallback: Any = None) -> Any:
    """Resolve one setting: env (coerced) > config.yaml > fallback."""
    yaml_val = _dig(path)
    if env:
        raw = os.getenv(env)
        if raw is not None and raw != "":
            target = yaml_val if yaml_val is not _MISSING else fallback
            if target is None or isinstance(target, str):
                return raw
            return _coerce(raw, target, env)
    if yaml_val is not _MISSING:
        return yaml_val
    return fallback

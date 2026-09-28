"""Loader for config.yaml: precedence (env > yaml > fallback) and coercion."""
import textwrap
from pathlib import Path

import pytest


def _fresh_loader(monkeypatch, tmp_path, yaml_text: str | None):
    """Import a fresh loader module bound to a throwaway config.yaml."""
    import importlib
    import backend.shared.config.settings.loader as loader_mod

    if yaml_text is None:
        monkeypatch.setenv("CONFIG_FILE", str(tmp_path / "does-not-exist.yaml"))
    else:
        cfg_file = tmp_path / "config.yaml"
        cfg_file.write_text(textwrap.dedent(yaml_text), encoding="utf-8")
        monkeypatch.setenv("CONFIG_FILE", str(cfg_file))
    return importlib.reload(loader_mod)


def _reload_real_loader(monkeypatch):
    """Put the shared loader back on the real config.yaml: undo the test's
    CONFIG_FILE first, then reload in place."""
    import importlib
    import backend.shared.config.settings.loader as loader_mod

    monkeypatch.undo()
    return importlib.reload(loader_mod)


@pytest.fixture(autouse=True)
def _restore_loader(monkeypatch):
    """_fresh_loader reloads the one shared loader module in place, so without
    this every later cfg() read in the run (base.py's included) kept seeing the
    last throwaway YAML, and a test reading a shipped default passed or failed
    by collection order (SA-005)."""
    yield
    _reload_real_loader(monkeypatch)


def test_reload_is_undone_for_the_rest_of_the_run(monkeypatch, tmp_path):
    import yaml
    from backend.shared.config.settings import base

    root = Path(__file__).resolve().parents[3]
    shipped = yaml.safe_load((root / "config.yaml").read_text(encoding="utf-8"))
    _fresh_loader(monkeypatch, tmp_path, "decision_gate: {mode: enforce}")
    # The leak mechanism: base.py's own cfg reads the reloaded module's YAML.
    assert base.cfg("decision_gate.mode", fallback=None) == "enforce"

    _reload_real_loader(monkeypatch)
    assert base.cfg("decision_gate.mode", fallback=None) == shipped["decision_gate"]["mode"]
    assert base.cfg("rl.learning_mode", fallback=None) == shipped["rl"]["learning_mode"]


YAML = """
    llm:
      model_bulk: "deepseek/deepseek-v4-flash"
      temperature: 0.2
      max_tokens: 2048
    scheduler:
      enabled: true
      tickers: ["MARUTI", "TATAMOTORS"]
    regime_multipliers:
      MACRO_CRISIS: {risk_macro: 1.40, fundamentals: 0.80}
    score_thresholds:
      strong_buy: [0.75, 1.00]
"""


def test_yaml_beats_fallback(monkeypatch, tmp_path):
    loader = _fresh_loader(monkeypatch, tmp_path, YAML)
    assert loader.cfg("llm.model_bulk", fallback="wrong") == "deepseek/deepseek-v4-flash"
    assert loader.cfg("llm.temperature", fallback=9.9) == 0.2


def test_env_beats_yaml(monkeypatch, tmp_path):
    loader = _fresh_loader(monkeypatch, tmp_path, YAML)
    monkeypatch.setenv("LLM_MODEL_BULK", "override/model")
    assert loader.cfg("llm.model_bulk", env="LLM_MODEL_BULK",
                      fallback="x") == "override/model"


def test_fallback_when_missing_everywhere(monkeypatch, tmp_path):
    loader = _fresh_loader(monkeypatch, tmp_path, YAML)
    assert loader.cfg("llm.nonexistent", env="NOPE_NOT_SET", fallback=42) == 42


def test_missing_yaml_file_uses_fallbacks(monkeypatch, tmp_path):
    loader = _fresh_loader(monkeypatch, tmp_path, None)
    assert loader.cfg("llm.model_bulk", fallback="fb") == "fb"


def test_malformed_yaml_raises(monkeypatch, tmp_path):
    with pytest.raises(RuntimeError):
        _fresh_loader(monkeypatch, tmp_path, "llm: [unclosed")


def test_env_bool_coercion(monkeypatch, tmp_path):
    loader = _fresh_loader(monkeypatch, tmp_path, YAML)
    monkeypatch.setenv("SCHED_ON", "false")
    assert loader.cfg("scheduler.enabled", env="SCHED_ON", fallback=True) is False
    monkeypatch.setenv("SCHED_ON", "YES")
    assert loader.cfg("scheduler.enabled", env="SCHED_ON", fallback=False) is True


def test_env_int_float_coercion(monkeypatch, tmp_path):
    loader = _fresh_loader(monkeypatch, tmp_path, YAML)
    monkeypatch.setenv("MAXTOK", "4096")
    assert loader.cfg("llm.max_tokens", env="MAXTOK", fallback=0) == 4096
    monkeypatch.setenv("TEMP", "0.7")
    assert loader.cfg("llm.temperature", env="TEMP", fallback=0.0) == 0.7


def test_env_bad_int_raises_with_key_name(monkeypatch, tmp_path):
    loader = _fresh_loader(monkeypatch, tmp_path, YAML)
    monkeypatch.setenv("MAXTOK", "not-a-number")
    with pytest.raises(ValueError, match="MAXTOK"):
        loader.cfg("llm.max_tokens", env="MAXTOK", fallback=0)


def test_env_csv_list_coercion(monkeypatch, tmp_path):
    loader = _fresh_loader(monkeypatch, tmp_path, YAML)
    monkeypatch.setenv("TICKS", "A, B ,C")
    assert loader.cfg("scheduler.tickers", env="TICKS",
                      fallback=[]) == ["A", "B", "C"]


def test_nested_table_from_yaml(monkeypatch, tmp_path):
    loader = _fresh_loader(monkeypatch, tmp_path, YAML)
    table = loader.cfg("regime_multipliers", fallback={})
    assert table["MACRO_CRISIS"]["risk_macro"] == 1.40


def test_tuple_wrapping_pattern(monkeypatch, tmp_path):
    """The assignment-site pattern base.py uses for SCORE_THRESHOLDS."""
    loader = _fresh_loader(monkeypatch, tmp_path, YAML)
    raw = loader.cfg("score_thresholds", fallback={"strong_buy": (0.75, 1.00)})
    wrapped = {k: tuple(v) for k, v in raw.items()}
    assert wrapped["strong_buy"] == (0.75, 1.00)

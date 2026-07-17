"""tests/unit/test_atomic_io.py — AUD-057 shared atomic writer."""
import json
import os

import pytest

from core.utils.atomic_io import atomic_write_json, atomic_write_text


def test_atomic_write_text_roundtrip(tmp_path):
    p = tmp_path / "sub" / "out.txt"          # parent does not exist yet
    atomic_write_text(p, "hello\n")
    assert p.read_text(encoding="utf-8") == "hello\n"


def test_atomic_write_text_overwrites(tmp_path):
    p = tmp_path / "out.txt"
    atomic_write_text(p, "one")
    atomic_write_text(p, "two")
    assert p.read_text(encoding="utf-8") == "two"


def test_atomic_write_leaves_no_temp_files(tmp_path):
    p = tmp_path / "out.json"
    atomic_write_json(p, {"a": 1})
    assert [f.name for f in tmp_path.iterdir()] == ["out.json"]


def test_atomic_write_json_kwargs(tmp_path):
    p = tmp_path / "out.json"
    atomic_write_json(p, {"b": 2, "a": 1}, indent=None, sort_keys=True)
    assert p.read_text(encoding="utf-8") == '{"a": 1, "b": 2}'
    assert json.loads(p.read_text(encoding="utf-8")) == {"a": 1, "b": 2}


def test_atomic_write_failure_cleans_tmp(tmp_path, monkeypatch):
    p = tmp_path / "out.txt"
    def boom(src, dst):
        raise OSError("simulated replace failure")
    monkeypatch.setattr(os, "replace", boom)
    with pytest.raises(OSError):
        atomic_write_text(p, "x")
    assert list(tmp_path.iterdir()) == []     # tmp file removed, target absent

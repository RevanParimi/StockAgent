"""scripts/docs/archive_done_tasks.py moves a done story's notes out of STATE.json word for word."""

import importlib.util
import json
import sys
from pathlib import Path

_PATH = Path(__file__).resolve().parents[2] / "scripts/docs/archive_done_tasks.py"
_spec = importlib.util.spec_from_file_location("archive_done_tasks", _PATH)
archive_done_tasks = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(archive_done_tasks)

STATE_TEXT = """{
  "pi": "PI-TEST",
  "tasks": [
    {"id": "A-1", "title": "Done one", "status": "done", "depends_on": [], "review": {"verdict": "accepted", "note": "long ₹ text"}, "production_verification": {"status": "pending_observation"}, "implementation_receipt": "evidence/A-1.md", "routed_from": "B-0 review"},
    {
      "id": "A-2",
      "title": "Still todo",
      "status": "todo",
      "depends_on": ["A-1"],
      "sequencing_note": "kept: not done"
    }
  ],
  "history": [{"date": "2026-11-19", "event": "x"}]
}
"""


def _run(tmp_path, monkeypatch, *argv):
    state, archive = tmp_path / "STATE.json", tmp_path / "STATE-tasks-archive.json"
    monkeypatch.setattr(archive_done_tasks, "STATE", state)
    monkeypatch.setattr(archive_done_tasks, "ARCHIVE", archive)
    monkeypatch.setattr(sys, "argv", ["archive_done_tasks.py", *argv])
    return archive_done_tasks.main(), state, archive


def test_done_task_keeps_its_card_and_moves_the_rest_word_for_word(tmp_path, monkeypatch):
    (tmp_path / "STATE.json").write_text(STATE_TEXT, encoding="utf-8")
    before = json.loads(STATE_TEXT)

    code, state, archive = _run(tmp_path, monkeypatch)

    assert code == 0
    after = json.loads(state.read_text(encoding="utf-8"))
    card = after["tasks"][0]
    assert card["status"] == "done" and card["depends_on"] == []
    assert card["production_verification"] == {"status": "pending_observation"}
    assert card["implementation_receipt"] == "evidence/A-1.md"
    assert card["routed_from"] == "B-0 review"
    assert "review" not in card
    assert card["archived_detail"] == archive_done_tasks.ARCHIVE_REF
    entry = json.loads(archive.read_text(encoding="utf-8"))["tasks"][0]
    assert entry["id"] == "A-1" and entry["fields"] == {"review": before["tasks"][0]["review"]}
    rebuilt = {k: v for k, v in card.items() if k != "archived_detail"} | entry["fields"]
    assert rebuilt == before["tasks"][0]
    assert after["tasks"][1] == before["tasks"][1]
    assert after["history"] == before["history"]
    assert state.read_text(encoding="utf-8").split('"A-2"')[1] == STATE_TEXT.split('"A-2"')[1]


def test_check_writes_nothing_and_a_second_run_moves_nothing(tmp_path, monkeypatch):
    (tmp_path / "STATE.json").write_text(STATE_TEXT, encoding="utf-8")

    code, state, archive = _run(tmp_path, monkeypatch, "--check")
    assert code == 0 and state.read_text(encoding="utf-8") == STATE_TEXT and not archive.exists()

    _run(tmp_path, monkeypatch)
    once = state.read_text(encoding="utf-8"), archive.read_text(encoding="utf-8")
    code, state, archive = _run(tmp_path, monkeypatch)
    assert code == 0
    assert (state.read_text(encoding="utf-8"), archive.read_text(encoding="utf-8")) == once

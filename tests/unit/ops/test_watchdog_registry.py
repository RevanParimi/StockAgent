"""Watchdog registry — loading and strict validation of config/milestones.yaml."""
import pytest
from datetime import date

from core.ops.watchdog.registry import RegistryError, load_registry


def _write(tmp_path, text):
    p = tmp_path / "milestones.yaml"
    p.write_text(text, encoding="utf-8")
    return p


def test_loads_milestone_and_invariant(tmp_path):
    p = _write(tmp_path, """
milestones:
  - id: atlas_c11_cutover
    kind: milestone
    title: "Atlas C11 live cutover"
    check: atlas_cutover_pending
    prep: atlas_cutover_prep
    window: {weekdays: [sat, sun]}
    deadline: 2026-08-15
    lead_days: 3
    action: "Set ATLAS_ENABLED=true and redeploy."
    docs: docs/plan.md
invariants:
  - id: serper_month_rollover
    kind: invariant
    title: "Serper counter rolled over"
    check: serper_counter_current_month
    schedule: monthly
""")
    entries = load_registry(p)
    assert [e.id for e in entries] == ["atlas_c11_cutover", "serper_month_rollover"]
    m = entries[0]
    assert m.window.weekdays == (5, 6)          # sat, sun
    assert m.deadline == date(2026, 8, 15)
    assert m.lead_days == 3
    assert entries[1].schedule == "monthly"
    assert entries[1].window is None


def test_defaults_applied(tmp_path):
    p = _write(tmp_path, """
milestones:
  - id: m1
    kind: milestone
    title: T
    check: c
""")
    m = load_registry(p)[0]
    assert m.lead_days == 3 and m.schedule == "daily"
    assert m.prep is None and m.deadline is None and m.window is None


def test_duplicate_id_rejected(tmp_path):
    p = _write(tmp_path, """
milestones:
  - {id: dup, kind: milestone, title: A, check: c}
  - {id: dup, kind: milestone, title: B, check: c}
""")
    with pytest.raises(RegistryError, match="duplicate"):
        load_registry(p)


def test_unknown_field_rejected(tmp_path):
    p = _write(tmp_path, """
milestones:
  - {id: m1, kind: milestone, title: T, check: c, wat: 1}
""")
    with pytest.raises(RegistryError, match="unknown field"):
        load_registry(p)


def test_bad_weekday_rejected(tmp_path):
    p = _write(tmp_path, """
milestones:
  - {id: m1, kind: milestone, title: T, check: c, window: {weekdays: [funday]}}
""")
    with pytest.raises(RegistryError, match="weekday"):
        load_registry(p)


def test_missing_required_field_rejected(tmp_path):
    p = _write(tmp_path, "milestones:\n  - {id: m1, kind: milestone, title: T}\n")
    with pytest.raises(RegistryError, match="check"):
        load_registry(p)


def test_missing_file_is_registry_error(tmp_path):
    with pytest.raises(RegistryError, match="not found"):
        load_registry(tmp_path / "nope.yaml")

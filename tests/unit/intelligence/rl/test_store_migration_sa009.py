"""
SA-009: plan, apply and roll back the prediction-store quarantine.

Invariants, against store_tree_sa009 (expected results from its design):
  * the plan moves only stores of managed tickers that are not the owner's
    store; it holds everything that needs a decision and merges nothing;
  * plan (the dry run) and a rerun give the same plan and change no byte;
  * apply moves exact bytes, keeps them readable, and re-checks each store
    immediately before its move; a migration directory is never reused;
  * rollback restores the same readable tree byte for byte, never merges into
    a live store that reappeared, and recovers after a crash mid-apply.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from core.intelligence.rl.stores import store_inventory as inv
from core.intelligence.rl.stores import store_migration as sm
from core.intelligence.rl.stores.prediction_store import PredictionStore
from tests.unit.intelligence.rl import store_tree_sa009 as fx

NOW = datetime(2026, 9, 30, 1, 0, 0, tzinfo=timezone.utc)


@pytest.fixture
def tree(tmp_path):
    base, managed = fx.build_tree(tmp_path)
    return base, managed, tmp_path / "prediction_quarantine"


def _plan(base, managed):
    return sm.make_plan(base, managed, **fx.inventory_kwargs())


def _apply(plan, base, managed, qroot, **kw):
    return sm.apply_plan(plan, plan["digest"], base, managed, qroot,
                         now=kw.pop("now", NOW), **fx.inventory_kwargs(), **kw)


def _readable(base):
    """What the store class reads from each moved store, before any move."""
    return {
        "SUZLON": PredictionStore("SUZLON", sector="automobile", base_dir=str(base))
        .load_envelope("SUZLON_2026-07").model_dump(),
        "RBLBANK": PredictionStore("RBLBANK", sector="bfsi", base_dir=str(base))
        .load_feedback_log("RBLBANK_2026-07").model_dump(),
        "MARUTI": PredictionStore("MARUTI", base_dir=str(base))
        .load_envelope("MARUTI_2026-06").model_dump(),
    }


MOVED = ["MARUTI", "automobile/SUZLON", "bfsi/RBLBANK"]


def test_plan_moves_only_stray_stores_of_managed_tickers(tree):
    base, managed, _ = tree
    plan = _plan(base, managed)
    assert sorted(i["store_id"] for i in plan["items"]) == MOVED
    by_id = {i["store_id"]: i for i in plan["items"]}
    assert by_id["MARUTI"]["reason"] == "legacy_flat"
    assert by_id["automobile/SUZLON"]["owner_store"] == "renewable_energy/SUZLON"
    assert by_id["automobile/SUZLON"]["evidence"]["roster_vs_owner"] == "wrong_roster"
    assert [f["path"] for f in by_id["automobile/SUZLON"]["files"]] == [
        "SUZLON_2026-07_daily_feedback_log.json", "SUZLON_2026-07_prediction_envelope.json",
        "SUZLON_agent_weight_memory.json", "archived_envelopes/2026-07_v1.json"]
    assert {(h["ticker"], h["reason"]) for h in plan["holds"]} == {
        ("ACME", "unmanaged_duplicate"), ("INOXWIND", "owner_registry_conflict")}
    assert [(f["store"], f["reason"]) for f in plan["flags"]] == [
        ("it_sector/TCS", "canonical_roster_wrong_roster")]


def test_two_owner_stores_differing_in_case_are_held(tree):
    """A case-sensitive volume could hold automobile/MARUTI and automobile/maruti
    (Windows cannot, so the manifest is edited instead of the tree)."""
    base, managed, _ = tree
    manifest = inv.build_inventory(base, managed, **fx.inventory_kwargs())
    twin = json.loads(json.dumps(next(s for s in manifest["stores"]
                                      if s["store_id"] == "automobile/MARUTI")))
    twin["store_id"] = "automobile/maruti"
    manifest["stores"].append(twin)
    files = {s["store_id"]: [] for s in manifest["stores"]}
    plan = sm.build_plan(manifest, files)
    assert ("MARUTI", "several_owner_stores") in {(h["ticker"], h["reason"])
                                                  for h in plan["holds"]}
    assert not any(i["ticker"] == "MARUTI" for i in plan["items"])


def test_dry_run_and_rerun_give_the_same_plan_and_change_nothing(tree, tmp_path):
    base, managed, _ = tree
    before = fx.tree_state(tmp_path)
    a, b = _plan(base, managed), _plan(base, managed)
    assert a == b
    assert fx.tree_state(tmp_path) == before
    other_base, other_managed = fx.build_tree(tmp_path / "copy")
    assert _plan(other_base, other_managed)["digest"] == a["digest"]
    text = json.dumps(a)
    for secret in fx.SECRETS:
        assert secret not in text
    assert str(tmp_path) not in text


def test_apply_moves_exact_bytes_and_they_stay_readable(tree):
    base, managed, qroot = tree
    readable = _readable(base)
    plan = _plan(base, managed)
    kept = {sid: inv.list_store_files(base / sid)
            for sid in ("renewable_energy/SUZLON", "banking_bfsi/RBLBANK", "automobile/MARUTI",
                        "automobile/ACME", "generic/ACME", "automobile/INOXWIND",
                        "renewable_energy/INOXWIND", "it_sector/TCS", "generic/NEWCO")}
    lineage = _apply(plan, base, managed, qroot)
    assert lineage["status"] == "applied"
    mig = qroot / lineage["migration_id"]
    for item in plan["items"]:
        assert not (base / item["store_id"]).exists()
        assert inv.list_store_files(mig / "stores" / item["store_id"]) == item["files"]
    assert {i["status"] for i in lineage["items"]} == {"moved"}
    # Everything else, holds included, is untouched.
    for sid, files in kept.items():
        assert inv.list_store_files(base / sid) == files, sid
    # The quarantine is a predictions root of its own: the store class reads it.
    assert _readable(mig / "stores") == readable
    # Rerun: nothing left to move; the holds and the flag remain.
    again = _plan(base, managed)
    assert again["items"] == []
    assert len(again["holds"]) == 2 and len(again["flags"]) == 1
    after = inv.build_inventory(base, managed, **fx.inventory_kwargs())
    assert [d["ticker"] for d in after["duplicates"]["tickers"]] == ["ACME", "INOXWIND"]
    events = (qroot / "migrations.jsonl").read_text(encoding="utf-8").splitlines()
    assert json.loads(events[-1])["moved"] == 3


def test_rollback_restores_the_same_readable_tree(tree, tmp_path):
    base, managed, qroot = tree
    before = fx.tree_state(base)
    readable = _readable(base)
    lineage = _apply(_plan(base, managed), base, managed, qroot)
    assert fx.tree_state(base) != before
    back = sm.rollback(qroot / lineage["migration_id"])
    assert back["status"] == "rolled_back"
    assert {i["status"] for i in back["items"]} == {"rolled_back"}
    assert fx.tree_state(base) == before
    assert _readable(base) == readable
    # A second rollback has nothing to move and changes nothing.
    sm.rollback(qroot / lineage["migration_id"])
    assert fx.tree_state(base) == before


def test_apply_refuses_an_unapproved_or_stale_plan(tree):
    base, managed, qroot = tree
    plan = _plan(base, managed)
    with pytest.raises(sm.MigrationRefused):
        sm.apply_plan(plan, "0" * 64, base, managed, qroot, **fx.inventory_kwargs())
    before = fx.tree_state(base)
    f = base / "automobile" / "SUZLON" / "SUZLON_agent_weight_memory.json"
    f.write_bytes(f.read_bytes() + b"\n")
    with pytest.raises(sm.MigrationRefused, match="changed since the plan"):
        _apply(plan, base, managed, qroot)
    assert not qroot.exists()
    f.write_bytes(f.read_bytes()[:-1])
    managed.write_bytes(managed.read_bytes() + b"\n")
    with pytest.raises(sm.MigrationRefused, match="changed since the plan"):
        _apply(plan, base, managed, qroot)
    assert fx.tree_state(base) == before


def test_apply_rechecks_each_store_immediately_before_moving_it(tree, monkeypatch):
    """A write that lands after apply's fresh-plan check (a job starting mid
    apply) stops the migration at that store; nothing is sized or moved from
    stale figures, and the store keeps the new write."""
    base, managed, qroot = tree
    plan = _plan(base, managed)
    monkeypatch.setattr(sm, "make_plan", lambda *a, **k: plan)
    # Items run in ticker order: MARUTI, RBLBANK, SUZLON.
    late = base / "bfsi" / "RBLBANK" / "RBLBANK_2026-07_daily_feedback_log.json"
    late.write_bytes(late.read_bytes().replace(b"1240.0", b"1241.0"))
    lineage = _apply(plan, base, managed, qroot)
    assert lineage["status"] == "stopped"
    status = {i["store_id"]: i["status"] for i in lineage["items"]}
    assert status == {"MARUTI": "moved", "bfsi/RBLBANK": "refused_changed",
                      "automobile/SUZLON": "not_attempted"}
    refused = next(i for i in lineage["items"] if i["store_id"] == "bfsi/RBLBANK")
    assert refused["diff"] == {"added": [], "removed": [],
                               "changed": ["RBLBANK_2026-07_daily_feedback_log.json"]}
    assert b"1241.0" in late.read_bytes()
    assert (base / "automobile" / "SUZLON").is_dir()
    back = sm.rollback(qroot / lineage["migration_id"])
    assert back["status"] == "rolled_back"
    assert (base / "MARUTI" / "MARUTI_2026-06_prediction_envelope.json").exists()


def test_rollback_never_merges_into_a_live_store_that_reappeared(tree):
    base, managed, qroot = tree
    lineage = _apply(_plan(base, managed), base, managed, qroot)
    # A writer recreates automobile/SUZLON after the move.
    fresh = PredictionStore("SUZLON", sector="automobile", base_dir=str(base))
    fresh._write_json(fresh._dir / "SUZLON_2026-09_prediction_envelope.json", {"new": 1})
    back = sm.rollback(qroot / lineage["migration_id"])
    assert back["status"] == "partial"
    status = {i["store_id"]: i["status"] for i in back["items"]}
    assert status == {"MARUTI": "rolled_back", "automobile/SUZLON": "refused_live_path_exists",
                      "bfsi/RBLBANK": "rolled_back"}
    assert sorted(p.name for p in (base / "automobile" / "SUZLON").iterdir()) == [
        "SUZLON_2026-09_prediction_envelope.json"]
    held = qroot / lineage["migration_id"] / "stores" / "automobile" / "SUZLON"
    item = next(i for i in lineage["items"] if i["store_id"] == "automobile/SUZLON")
    assert inv.list_store_files(held) == item["files"]


def test_rollback_refuses_a_quarantined_store_whose_bytes_changed(tree):
    base, managed, qroot = tree
    lineage = _apply(_plan(base, managed), base, managed, qroot)
    held = qroot / lineage["migration_id"] / "stores" / "automobile" / "SUZLON"
    w = held / "SUZLON_agent_weight_memory.json"
    w.write_bytes(w.read_bytes() + b"\n")
    back = sm.rollback(qroot / lineage["migration_id"])
    assert back["status"] == "partial"
    item = next(i for i in back["items"] if i["store_id"] == "automobile/SUZLON")
    assert item["status"] == "refused_quarantine_changed"
    assert item["rollback_diff"]["changed"] == ["SUZLON_agent_weight_memory.json"]
    assert not (base / "automobile" / "SUZLON").exists()
    assert (base / "bfsi" / "RBLBANK").is_dir() and (base / "MARUTI").is_dir()


def test_rollback_removes_an_empty_live_directory_a_read_recreated(tree):
    """Change 1 (review L2): after the apply, any read through PredictionStore's
    constructor recreates an empty automobile/SUZLON. It holds nothing, so
    rollback removes it and restores the store."""
    base, managed, qroot = tree
    before = fx.tree_state(base)
    readable = _readable(base)
    lineage = _apply(_plan(base, managed), base, managed, qroot)
    PredictionStore("SUZLON", sector="automobile", base_dir=str(base))
    assert list((base / "automobile" / "SUZLON").iterdir()) == []
    back = sm.rollback(qroot / lineage["migration_id"])
    assert back["status"] == "rolled_back"
    item = next(i for i in back["items"] if i["store_id"] == "automobile/SUZLON")
    assert item["status"] == "rolled_back"
    assert item["removed_empty_live_dir"] is True
    assert fx.tree_state(base) == before
    assert _readable(base) == readable


def test_a_refused_store_is_retried_and_the_status_never_overstates(tree):
    """Change 1 (review L1): a quarantined file changes, so rollback refuses
    that store. Retries before the repair stay partial (the CLI exits 1);
    once the operator restores the bytes, a retry brings the store back."""
    base, managed, qroot = tree
    before = fx.tree_state(base)
    lineage = _apply(_plan(base, managed), base, managed, qroot)
    mig = qroot / lineage["migration_id"]
    w = mig / "stores" / "automobile" / "SUZLON" / "SUZLON_agent_weight_memory.json"
    original = w.read_bytes()
    w.write_bytes(original + b"\n")
    assert sm.rollback(mig)["status"] == "partial"
    assert sm.rollback(mig)["status"] == "partial"
    assert sm.main(["rollback", "--migration", str(mig)]) == 1
    assert not (base / "automobile" / "SUZLON").exists()
    w.write_bytes(original)
    fixed = sm.rollback(mig)
    assert fixed["status"] == "rolled_back"
    item = next(i for i in fixed["items"] if i["store_id"] == "automobile/SUZLON")
    assert item["status"] == "rolled_back"
    assert "rollback_diff" not in item
    assert fx.tree_state(base) == before


def test_a_store_already_back_counts_only_with_its_recorded_bytes(tree):
    """The operator moved automobile/SUZLON back by hand. With other bytes it
    is refused; with the recorded bytes it counts as restored."""
    base, managed, qroot = tree
    before = fx.tree_state(base)
    lineage = _apply(_plan(base, managed), base, managed, qroot)
    mig = qroot / lineage["migration_id"]
    live = base / "automobile" / "SUZLON"
    (mig / "stores" / "automobile" / "SUZLON").rename(live)
    w = live / "SUZLON_agent_weight_memory.json"
    original = w.read_bytes()
    w.write_bytes(original + b"\n")
    back = sm.rollback(mig)
    assert back["status"] == "partial"
    status = {i["store_id"]: i["status"] for i in back["items"]}
    assert status["automobile/SUZLON"] == "refused_quarantine_missing"
    w.write_bytes(original)
    back = sm.rollback(mig)
    assert back["status"] == "rolled_back"
    assert {i["store_id"]: i["status"] for i in back["items"]} == {
        "MARUTI": "rolled_back", "automobile/SUZLON": "found_live", "bfsi/RBLBANK": "rolled_back"}
    assert fx.tree_state(base) == before


def test_apply_moves_the_fresh_plans_items_not_the_files(tree):
    """The plan file is operator input: an item added to it, with its digest
    left as it was, is never moved (review L3)."""
    base, managed, qroot = tree
    plan = _plan(base, managed)
    edited = json.loads(json.dumps(plan))
    edited["items"].append({**edited["items"][0], "store_id": "renewable_energy/SUZLON",
                            "files": inv.list_store_files(base / "renewable_energy" / "SUZLON")})
    lineage = _apply(edited, base, managed, qroot)
    assert sorted(i["store_id"] for i in lineage["items"]) == MOVED
    assert (base / "renewable_energy" / "SUZLON").is_dir()


@pytest.mark.parametrize("suzlon", [
    {"sym": "SUZLON", "enabled": True},
    {"sym": "SUZLON", "sector": "", "enabled": True},
    {"sym": "SUZLON", "sector": "   ", "enabled": True},
], ids=["absent", "empty", "blank"])
def test_a_managed_entry_without_a_sector_is_held_never_defaulted(tree, suzlon):
    """The scheduler would default such an entry to automobile. The plan acts
    on no default, whether the ticker has two stores or one (review L3)."""
    base, managed, _ = tree
    roster = [e for e in fx.MANAGED if e["sym"] not in ("SUZLON", "TCS")]
    managed.write_bytes(json.dumps(
        roster + [suzlon, {"sym": "TCS", "enabled": False}]).encode("utf-8"))
    plan = _plan(base, managed)
    holds = {(h["ticker"], h["reason"]) for h in plan["holds"]}
    assert ("SUZLON", "managed_without_sector_duplicate") in holds
    assert ("TCS", "managed_without_sector") in holds
    assert not any(i["ticker"] in ("SUZLON", "TCS") for i in plan["items"])
    manifest = inv.build_inventory(base, managed, **fx.inventory_kwargs())
    assert {s["ownership"]["owner_sector"] for s in manifest["stores"]
            if s["ticker"] in ("SUZLON", "TCS")} == {None}


def test_conflicting_managed_entries_are_held(tree):
    """Two entries for SUZLON disagree (the second differs only in spelling):
    which store is the owner's is a decision, not a rule (review L3)."""
    base, managed, _ = tree
    managed.write_bytes(json.dumps(
        fx.MANAGED + [{"sym": "suzlon ", "sector": "automobile", "enabled": False}]
    ).encode("utf-8"))
    plan = _plan(base, managed)
    assert ("SUZLON", "managed_conflict_duplicate") in {(h["ticker"], h["reason"])
                                                        for h in plan["holds"]}
    assert not any(i["ticker"] == "SUZLON" for i in plan["items"])


def test_a_migration_directory_is_never_reused(tree):
    base, managed, qroot = tree
    plan = _plan(base, managed)
    taken = qroot / f"{NOW:%Y%m%dT%H%M%SZ}-{plan['digest'][:12]}"
    taken.mkdir(parents=True)
    (taken / "lineage.json").write_text("{}", encoding="utf-8")
    before = fx.tree_state(base)
    with pytest.raises(sm.MigrationRefused, match="already exists"):
        _apply(plan, base, managed, qroot)
    assert fx.tree_state(base) == before
    assert (taken / "lineage.json").read_text(encoding="utf-8") == "{}"


def test_rollback_recovers_a_crash_between_a_move_and_its_record(tree, monkeypatch):
    base, managed, qroot = tree
    before = fx.tree_state(base)
    real = sm._write_lineage
    calls = []

    def crash_after_first_move(path, lineage):
        calls.append(1)
        if len(calls) == 2:          # 1 = initial record, 2 = after the first move
            raise KeyboardInterrupt("simulated crash")
        real(path, lineage)

    monkeypatch.setattr(sm, "_write_lineage", crash_after_first_move)
    with pytest.raises(KeyboardInterrupt):
        _apply(_plan(base, managed), base, managed, qroot)
    monkeypatch.setattr(sm, "_write_lineage", real)
    (mig,) = [p for p in qroot.iterdir() if p.is_dir()]
    recorded = json.loads((mig / "lineage.json").read_text(encoding="utf-8"))
    assert {i["status"] for i in recorded["items"]} == {"pending"}
    assert not (base / "MARUTI").exists()          # moved, but not recorded
    back = sm.rollback(mig)
    assert {i["store_id"]: i["status"] for i in back["items"]} == {
        "MARUTI": "rolled_back", "automobile/SUZLON": "not_moved", "bfsi/RBLBANK": "not_moved"}
    assert fx.tree_state(base) == before


def test_quarantine_root_must_be_outside_the_predictions_root(tree):
    base, managed, _ = tree
    plan = _plan(base, managed)
    with pytest.raises(sm.MigrationRefused, match="overlaps"):
        _apply(plan, base, managed, base / "_quarantine")


def test_default_quarantine_root_sits_beside_the_predictions_root(tmp_path):
    assert sm.default_quarantine_root(tmp_path / "data" / "predictions") == (
        tmp_path / "data" / "prediction_quarantine").resolve()


def test_cli_round_trip(tree, tmp_path, monkeypatch):
    base, managed, qroot = tree
    before = fx.tree_state(base)
    kwargs = fx.inventory_kwargs()
    real_build = inv.build_inventory
    monkeypatch.setattr(inv, "build_inventory",
                        lambda b, m=inv.DEFAULT_MANAGED_PATH, **k: real_build(b, m, **kwargs))
    plan_path = tmp_path / "plan.json"
    assert sm.main(["plan", "--base-dir", str(base), "--managed", str(managed),
                    "--out", str(plan_path)]) == 0
    digest = json.loads(plan_path.read_text(encoding="utf-8"))["digest"]
    assert sm.main(["apply", "--plan", str(plan_path), "--approve", "f" * 64,
                    "--base-dir", str(base), "--managed", str(managed),
                    "--quarantine-root", str(qroot)]) == 2
    assert sm.main(["apply", "--plan", str(plan_path), "--approve", digest,
                    "--base-dir", str(base), "--managed", str(managed),
                    "--quarantine-root", str(qroot)]) == 0
    (mig,) = [p for p in qroot.iterdir() if p.is_dir()]
    assert sm.main(["rollback", "--migration", str(mig)]) == 0
    assert fx.tree_state(base) == before

"""
SA-009: the read-only prediction-store manifest.

Invariants, each against tests/unit/intelligence/rl/store_tree_sa009.py,
whose expected results are written from the fixture's design:
  * missing metadata is told apart from a confirmed sector, and a directory
    name alone never confirms one;
  * a store whose rows carry another graph's dimensions is identified, both
    against its own directory and against the ticker's owner;
  * duplicate forecast identities are found and marked identical or
    conflicting, across stores and inside one store;
  * the inventory writes nothing, creates no directory, is deterministic and
    repeats none of the stores' content.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from core.intelligence.rl.stores import store_inventory as inv
from tests.unit.intelligence.rl import store_tree_sa009 as fx


@pytest.fixture
def tree(tmp_path):
    base, managed = fx.build_tree(tmp_path)
    return base, managed


def _manifest(tree):
    base, managed = tree
    return inv.build_inventory(base, managed, **fx.inventory_kwargs())


def _stores(manifest):
    return {s["store_id"]: s for s in manifest["stores"]}


def test_missing_metadata_is_distinguished_from_a_confirmed_sector(tree):
    stores = _stores(_manifest(tree))
    status = {k: v["sector_evidence"]["status"] for k, v in stores.items()}
    assert status == {
        "renewable_energy/SUZLON": "confirmed",   # renewable roster in its own graph's dir
        "automobile/SUZLON": "confirmed",         # the automobile graph did produce it
        "banking_bfsi/RBLBANK": "confirmed",
        "bfsi/RBLBANK": "conflicting",            # unknown dir; files declare banking_bfsi
        "automobile/MARUTI": "confirmed",
        "MARUTI": "roster_only",                  # flat: no directory sector, roster known
        "LEGACYCO": "missing",                    # flat, no roster: nothing to go on
        "it_sector/TCS": "conflicting",           # automobile roster under it_sector
        "generic/NEWCO": "directory_only",        # the directory name alone
        "generic/SUNPHARMA": "empty",
        "automobile/ACME": "confirmed",
        "generic/ACME": "confirmed",
        "automobile/INOXWIND": "confirmed",
        "renewable_energy/INOXWIND": "confirmed",
    }


def test_default_sector_fields_are_reported_but_never_evidence(tree):
    s = _stores(_manifest(tree))["renewable_energy/SUZLON"]
    # The feedback log and weights say "automobile" (the pre-SA-009 schema
    # default in a renewable store). They are reported, and the store is
    # still confirmed from its dimensions.
    assert s["declared_sectors"]["feedback_log"] == {"automobile": 1}
    assert s["declared_sectors"]["weight_memory"] == {"automobile": 1}
    assert s["declared_sectors"]["envelope"] == {"renewable_energy": 1}
    assert s["sector_evidence"]["status"] == "confirmed"


def test_wrong_dimension_roster_is_identified_against_directory_and_owner(tree):
    stores = _stores(_manifest(tree))
    copy = stores["automobile/SUZLON"]
    assert copy["files_by_roster"] == {"automobile": [
        "SUZLON_2026-07_daily_feedback_log.json", "SUZLON_2026-07_prediction_envelope.json",
        "SUZLON_agent_weight_memory.json", "archived_envelopes/2026-07_v1.json"]}
    assert copy["ownership"] == {
        "owner_sector": "renewable_energy", "owner_source": "managed",
        "owner_graph": "renewable_energy", "role": "non_canonical",
        "roster_vs_owner": "wrong_roster", "registry_agrees": True}
    tcs = stores["it_sector/TCS"]
    assert tcs["ownership"]["role"] == "canonical"
    assert tcs["ownership"]["roster_vs_owner"] == "wrong_roster"
    assert stores["renewable_energy/SUZLON"]["ownership"]["roster_vs_owner"] == "match"
    # Owned by the managed entry (automobile), so the renewable copy is the stray.
    assert stores["renewable_energy/INOXWIND"]["ownership"]["roster_vs_owner"] == "wrong_roster"
    assert stores["renewable_energy/INOXWIND"]["ownership"]["registry_agrees"] is False


def test_ownership_needs_a_managed_entry_and_never_guesses(tree):
    stores = _stores(_manifest(tree))
    for sid in ("generic/NEWCO", "automobile/ACME", "generic/ACME", "LEGACYCO",
                "generic/SUNPHARMA"):
        assert stores[sid]["ownership"]["role"] == "unowned", sid
        assert stores[sid]["ownership"]["owner_sector"] is None
    assert stores["MARUTI"]["ownership"]["role"] == "non_canonical"
    assert stores["automobile/MARUTI"]["ownership"]["role"] == "canonical"


def test_duplicate_forecast_ids_are_marked_identical_or_conflicting(tree):
    m = _manifest(tree)
    envs = {d["id"]: d for d in m["duplicates"]["envelopes"]}
    assert {k: v["status"] for k, v in envs.items()} == {
        "ACME_2026-07": "conflicting",
        "RBLBANK_2026-07": "identical",
        "SUZLON_2026-07": "conflicting",
    }
    assert [o["store"] for o in envs["SUZLON_2026-07"]["occurrences"]] == [
        "automobile/SUZLON", "renewable_energy/SUZLON"]
    days = {d["id"]: d for d in m["duplicates"]["graded_days"]}
    assert {k: v["status"] for k, v in days.items()} == {
        "RBLBANK:2026-07-03": "identical",
        "SUZLON:2026-07-01": "conflicting",
        "TCS:2026-07-31": "conflicting",      # graded in two logs of one store
    }
    assert {o["store"] for o in days["TCS:2026-07-31"]["occurrences"]} == {"it_sector/TCS"}
    assert [d["ticker"] for d in m["duplicates"]["tickers"]] == [
        "ACME", "INOXWIND", "MARUTI", "RBLBANK", "SUZLON"]


def test_consumers_follow_each_lookup_rule(tree):
    stores = _stores(_manifest(tree))
    assert stores["automobile/SUZLON"]["consumers"] == ["discovery", "automobile_default"]
    assert stores["renewable_energy/SUZLON"]["consumers"] == [
        "discovery", "managed", "analysis_graph"]
    assert stores["MARUTI"]["consumers"] == ["discovery_misread", "flat_cli"]
    assert stores["generic/NEWCO"]["consumers"] == ["discovery", "analysis_graph"]


def test_summary_and_unknown_sector_dirs(tree):
    s = _manifest(tree)["summary"]
    assert s["stores"] == 14
    assert s["empty_stores"] == 1
    assert s["legacy_flat_stores"] == 2
    assert s["unknown_sector_dirs"] == ["bfsi"]
    assert s["duplicate_tickers"] == 5
    assert s["wrong_roster_stores"] == 3      # automobile/SUZLON, it_sector/TCS, renewable INOXWIND
    assert s["roles"] == {"canonical": 5, "non_canonical": 4, "unowned": 4}


def test_inventory_writes_nothing_and_creates_no_directory(tree, tmp_path):
    base, managed = tree
    before = fx.tree_state(tmp_path)
    inv.build_inventory(base, managed, **fx.inventory_kwargs())
    inv.build_inventory(base, tmp_path / "absent.json", **fx.inventory_kwargs())
    assert fx.tree_state(tmp_path) == before


def test_missing_managed_roster_is_not_bootstrapped_and_owns_nothing(tree, tmp_path):
    base, _ = tree
    absent = tmp_path / "absent.json"
    m = inv.build_inventory(base, absent, **fx.inventory_kwargs())
    assert not absent.exists()
    assert m["managed"]["status"] == "missing"
    assert {s["ownership"]["role"] for s in m["stores"]} == {"unowned"}


def test_manifest_is_deterministic_and_tracks_every_byte(tree, tmp_path):
    base, managed = tree
    a = inv.build_inventory(base, managed, **fx.inventory_kwargs())
    b = inv.build_inventory(base, managed, **fx.inventory_kwargs())
    assert a["digest"] == b["digest"]
    assert inv.manifest_body(a) == inv.manifest_body(b)
    # The same tree built elsewhere has the same digest (no absolute paths).
    other_base, other_managed = fx.build_tree(tmp_path / "copy")
    c = inv.build_inventory(other_base, other_managed, **fx.inventory_kwargs())
    assert c["digest"] == a["digest"]
    f = base / "generic" / "NEWCO" / "NEWCO_dossier.json"
    f.write_bytes(f.read_bytes() + b" ")
    assert inv.build_inventory(base, managed, **fx.inventory_kwargs())["digest"] != a["digest"]


def test_manifest_repeats_no_store_content_or_local_path(tree, tmp_path):
    text = json.dumps(_manifest(tree))
    for secret in fx.SECRETS:
        assert secret not in text
    assert str(tmp_path) not in text
    assert tmp_path.name not in text


def test_malformed_files_are_reported_not_fatal(tmp_path):
    """A file that is not JSON, not an object, or has the wrong inner types
    is counted and carries no evidence; the inventory still completes."""
    d = tmp_path / "predictions" / "banking_bfsi" / "ODDBANK"
    d.mkdir(parents=True)
    (d / "ODDBANK_2026-07_prediction_envelope.json").write_text(
        json.dumps({"sector": "banking_bfsi", "daily_forecasts": "oops"}), encoding="utf-8")
    (d / "ODDBANK_2026-07_daily_feedback_log.json").write_text(
        json.dumps({"entries": [1, "x", {"date": "2026-07-01",
                                         "predicted_agent_scores": ["not", "a", "dict"]}]}),
        encoding="utf-8")
    (d / "ODDBANK_agent_weight_memory.json").write_text("[1, 2]", encoding="utf-8")
    (d / "ODDBANK_2026-08_prediction_envelope.json").write_text("{not json", encoding="utf-8")
    (s,) = inv.build_inventory(tmp_path / "predictions", None, **fx.inventory_kwargs())["stores"]
    assert s["files"] == 4
    assert s["unreadable_files"] == ["ODDBANK_2026-08_prediction_envelope.json",
                                     "ODDBANK_agent_weight_memory.json"]
    assert s["files_by_roster"] == {}
    assert s["sector_evidence"]["status"] == "directory_only"
    assert s["schema"]["feedback_entries"] == 1


def test_real_rosters_recognise_a_store_written_by_prediction_store(tmp_path):
    """The default wiring (the sector settings' own AGENT_WEIGHTS) confirms a
    banking store the store class wrote, and SA-009's store stamp shows in it."""
    from backend.sectors.banking_bfsi.config import settings as banking
    from core.intelligence.rl.stores.prediction_store import PredictionStore
    from core.schemas.feedback import DailyForecast, FeedbackEntry, PredictionEnvelope

    base = tmp_path / "predictions"
    dims = sorted(banking.AGENT_WEIGHTS)
    store = PredictionStore("HDFCBANK", sector="banking_bfsi", base_dir=str(base))
    store.save_envelope(PredictionEnvelope(
        ticker="HDFCBANK", sector="banking_bfsi", cycle_id="HDFCBANK_2026-07",
        generated_at="2026-07-01", base_close=100.0,
        daily_forecasts=[DailyForecast(day=1, date="2026-07-01", predicted_close=100.0,
                                       predicted_verdict="BUY",
                                       predicted_agent_scores={d: 0.6 for d in dims})]))
    store.append_feedback_entry(FeedbackEntry(
        day=1, date="2026-07-01", predicted_close=100.0, actual_close=101.0,
        price_error_pct=1.0, predicted_verdict="BUY", actual_direction="UP",
        direction_correct=True, predicted_agent_scores={d: 0.6 for d in dims}),
        cycle_id="HDFCBANK_2026-07")
    m = inv.build_inventory(base, None)
    (s,) = m["stores"]
    assert s["sector_evidence"]["status"] == "confirmed"
    assert set(s["files_by_roster"]) == {"banking_bfsi"}
    assert s["declared_sectors"]["feedback_log"] == {"banking_bfsi": 1}
    assert m["rosters"]["banking_bfsi"] == dims


def test_cli_writes_the_manifest(tree, tmp_path, capsys):
    base, managed = tree
    out = tmp_path / "manifest.json"
    assert inv.main(["--base-dir", str(base), "--managed", str(managed),
                     "--out", str(out)]) == 0
    written = json.loads(out.read_text(encoding="utf-8"))
    assert written["schema"] == inv.SCHEMA
    assert json.loads(capsys.readouterr().err)["digest"] == written["digest"]

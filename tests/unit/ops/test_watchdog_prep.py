"""Watchdog prep — idempotent auto-preparation that never takes the final step."""
import os

import pytest

from core.ops.watchdog import prep as P


@pytest.fixture(autouse=True)
def _isolate_data_dir(tmp_path, monkeypatch):
    """Prep writes a marker under the data dir. Without this every prep test
    would write the REAL data/atlas_prep_done.json, polluting the tree and
    leaking state into the next test (a stale marker makes prep skip the ETL)."""
    from core.ops.watchdog import checks as C
    monkeypatch.setattr(C, "_DATA_DIR", tmp_path)
    return tmp_path


def test_run_prep_unknown_name_is_not_ok():
    r = P.run_prep("nope")
    assert r.ok is False and "not registered" in r.transcript[0]


def test_run_prep_swallows_exception():
    @P.prep("boom_prep_test")
    def _b():
        raise RuntimeError("kaboom")
    try:
        r = P.run_prep("boom_prep_test")
        assert r.ok is False and any("kaboom" in t for t in r.transcript)
    finally:
        P.PREPS.pop("boom_prep_test", None)


def test_duplicate_prep_name_rejected():
    @P.prep("dupe_prep_test")
    def _a():
        return P.PrepResult(True, [])
    try:
        with pytest.raises(ValueError, match="already registered"):
            @P.prep("dupe_prep_test")
            def _b():
                return P.PrepResult(True, [])
    finally:
        P.PREPS.pop("dupe_prep_test", None)


class TestAtlasPrep:
    def test_dry_run_then_real_etl_reported(self, monkeypatch):
        calls = []

        def fake_run_etl(**kw):
            calls.append(kw)
            return {"users": 1, "instruments": 12, "verdicts": 1191}

        monkeypatch.setattr(P, "_run_etl", fake_run_etl)
        r = P.run_prep("atlas_cutover_prep")
        assert r.ok is True
        assert calls[0]["dry_run"] is True and calls[1]["dry_run"] is False
        assert any("1191" in line for line in r.transcript)

    def test_aborts_before_real_etl_when_dry_run_fails(self, monkeypatch):
        def fake_run_etl(**kw):
            if kw.get("dry_run"):
                raise RuntimeError("source db unreadable")
            pytest.fail("must not run the real ETL after a failed dry run")

        monkeypatch.setattr(P, "_run_etl", fake_run_etl)
        r = P.run_prep("atlas_cutover_prep")
        assert r.ok is False
        assert any("unreadable" in line for line in r.transcript)

    def test_never_sets_the_flag(self, monkeypatch):
        monkeypatch.setattr(P, "_run_etl", lambda **kw: {"users": 1})
        monkeypatch.delenv("ATLAS_ENABLED", raising=False)
        P.run_prep("atlas_cutover_prep")
        assert os.getenv("ATLAS_ENABLED") is None


class TestPrepGating:
    """Prep must run only when it is both safe and useful."""

    def _entry(self, **kw):
        from core.ops.watchdog.registry import Milestone, Window
        base = dict(id="atlas", kind="milestone", title="Atlas",
                    check="c", prep="atlas_cutover_prep",
                    window=Window(weekdays=(5, 6)))
        base.update(kw)
        return Milestone(**base)

    def _results(self, state):
        from core.ops.watchdog.checks import CheckResult
        return {"atlas": CheckResult(state, "detail")}

    def test_runs_when_pending_and_window_open(self, monkeypatch):
        from core.ops.watchdog import runner as R
        monkeypatch.setattr(P, "_run_etl", lambda **kw: {"ok": 1})
        from datetime import date
        out = R._run_preps([self._entry()], self._results("pending"),
                           date(2026, 8, 15))          # Saturday
        assert "atlas" in out

    def test_skipped_when_blocked(self, monkeypatch):
        from core.ops.watchdog import runner as R
        monkeypatch.setattr(P, "_run_etl",
                            lambda **kw: pytest.fail("must not prep a blocked entry"))
        from datetime import date
        out = R._run_preps([self._entry()], self._results("blocked"),
                           date(2026, 8, 15))
        assert out == {}

    def test_skipped_when_window_closed(self, monkeypatch):
        from core.ops.watchdog import runner as R
        monkeypatch.setattr(P, "_run_etl",
                            lambda **kw: pytest.fail("must not prep outside the window"))
        from datetime import date
        out = R._run_preps([self._entry()], self._results("pending"),
                           date(2026, 8, 12))          # Wednesday
        assert out == {}

    def test_skipped_when_disabled_by_config(self, monkeypatch):
        from core.ops.watchdog import runner as R
        monkeypatch.setattr(R, "_prep_enabled", lambda: False)
        monkeypatch.setattr(P, "_run_etl",
                            lambda **kw: pytest.fail("prep_enabled=false must disarm prep"))
        from datetime import date
        out = R._run_preps([self._entry()], self._results("pending"),
                           date(2026, 8, 15))
        assert out == {}


def test_transcript_appears_in_the_alert(tmp_path, monkeypatch):
    """The point of prep: the alert says 'done and verified', not 'go check'."""
    from core.ops.watchdog import checks as C
    from core.ops.watchdog import runner as R
    from datetime import datetime
    from zoneinfo import ZoneInfo

    reg = tmp_path / "milestones.yaml"
    reg.write_text("""
milestones:
  - id: atlas_c11_cutover
    kind: milestone
    title: "Atlas C11"
    check: atlas_cutover_pending
    prep: atlas_cutover_prep
    window: {weekdays: [sat, sun]}
    deadline: 2026-08-16
    action: "Set ATLAS_ENABLED=true."
""", encoding="utf-8")
    monkeypatch.setattr(R, "_REGISTRY_PATH", reg)
    monkeypatch.setattr(R, "_STATE_PATH", tmp_path / "state.json")
    monkeypatch.setattr(C, "_DATA_DIR", tmp_path)
    monkeypatch.delenv("ATLAS_ENABLED", raising=False)
    (tmp_path / "portfolio").mkdir()
    (tmp_path / "portfolio" / "primary").mkdir()
    monkeypatch.setattr(P, "_run_etl", lambda **kw: {"verdicts": 1191})

    sent = []
    monkeypatch.setattr(R, "_broadcast", lambda events, title: sent.extend(events))
    R.run_watchdog(now=datetime(2026, 8, 15, 6, 30, tzinfo=ZoneInfo("Asia/Kolkata")))

    assert sent
    assert "Automatic prep" in sent[0].message
    assert "1191" in sent[0].message


class TestPrepIsIdempotentAndVisibleToTheCheck:
    """Saturday's prep creates atlas.db. Without a marker, Sunday's check reads
    that as 'pre-flight DIRTY, investigate' — a false alarm caused by our own
    prep, on the LAST day of the window, which would talk the user out of the
    cutover entirely."""

    def _wire(self, monkeypatch, tmp_path):
        from core.ops.watchdog import checks as C
        monkeypatch.setattr(C, "_DATA_DIR", tmp_path)
        monkeypatch.delenv("ATLAS_ENABLED", raising=False)
        (tmp_path / "portfolio").mkdir(exist_ok=True)
        (tmp_path / "portfolio" / "primary").mkdir(exist_ok=True)

    def test_check_reads_ready_to_flip_after_prep_ran(self, monkeypatch, tmp_path):
        from core.ops.watchdog import checks as C
        self._wire(monkeypatch, tmp_path)
        calls = []

        def fake_etl(**kw):
            calls.append(kw)
            if not kw.get("dry_run"):
                (tmp_path / "atlas.db").write_text("etl output")  # as the real one does
            return {"verdicts": 1191}

        monkeypatch.setattr(P, "_run_etl", fake_etl)

        assert C.run_check("atlas_cutover_pending").state == "pending"
        P.run_prep("atlas_cutover_prep")                 # Saturday
        assert (tmp_path / "atlas.db").exists()
        r = C.run_check("atlas_cutover_pending")         # Sunday
        assert r.state == "pending", "must not read as blocked after our own prep"
        assert "already run" in r.detail.lower()

    def test_unexplained_atlas_db_is_still_blocked(self, monkeypatch, tmp_path):
        """A db with no prep marker is genuinely unexpected — keep warning."""
        from core.ops.watchdog import checks as C
        self._wire(monkeypatch, tmp_path)
        (tmp_path / "atlas.db").write_text("from somewhere else")
        r = C.run_check("atlas_cutover_pending")
        assert r.state == "blocked" and "atlas.db" in r.detail

    def test_second_prep_does_not_rerun_the_etl(self, monkeypatch, tmp_path):
        self._wire(monkeypatch, tmp_path)
        calls = []
        monkeypatch.setattr(P, "_run_etl",
                            lambda **kw: calls.append(kw) or {"verdicts": 1191})
        P.run_prep("atlas_cutover_prep")
        first = len(calls)
        second = P.run_prep("atlas_cutover_prep")
        assert len(calls) == first, "re-running the ETL is wasteful and can error"
        assert second.ok is True
        assert any("already prepared" in l.lower() for l in second.transcript)

    def test_prep_writes_a_marker_recording_what_it_did(self, monkeypatch, tmp_path):
        import json
        from core.ops.watchdog import checks as C
        self._wire(monkeypatch, tmp_path)
        monkeypatch.setattr(P, "_run_etl", lambda **kw: {"verdicts": 1191})
        P.run_prep("atlas_cutover_prep")
        marker = json.loads(C._atlas_prep_marker().read_text(encoding="utf-8"))
        assert "at" in marker and marker["result"]["verdicts"] == 1191

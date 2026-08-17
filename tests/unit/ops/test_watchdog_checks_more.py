"""Watchdog standing invariants — deploy drift, quota rollover, scorecard,
audit grading, user mirroring."""
import json
from datetime import date

from core.ops.watchdog import checks as C


class TestRegistryIsCurrent:
    """Compares the registry FILE, not the commit SHA: holding unrelated
    commits back is normal here, so a SHA check would warn every day."""

    def test_satisfied_when_identical(self, monkeypatch):
        monkeypatch.setattr(C, "_local_registry_text", lambda: "milestones: []\n")
        monkeypatch.setattr(C, "_github_registry_text", lambda: "milestones: []\n")
        assert C.run_check("registry_is_current").state == "satisfied"

    def test_satisfied_despite_line_ending_and_trailing_space_noise(self, monkeypatch):
        monkeypatch.setattr(C, "_local_registry_text", lambda: "milestones: []   \r\n")
        monkeypatch.setattr(C, "_github_registry_text", lambda: "milestones: []\n\n")
        assert C.run_check("registry_is_current").state == "satisfied"

    def test_pending_when_origin_has_a_new_milestone(self, monkeypatch):
        monkeypatch.setattr(C, "_local_registry_text", lambda: "milestones: []\n")
        monkeypatch.setattr(C, "_github_registry_text",
                            lambda: "milestones:\n  - {id: new}\n")
        r = C.run_check("registry_is_current")
        assert r.state == "pending" and "not deployed" in r.detail

    def test_unknown_when_github_unreachable(self, monkeypatch):
        monkeypatch.setattr(C, "_local_registry_text", lambda: "milestones: []\n")
        monkeypatch.setattr(C, "_github_registry_text", lambda: None)
        assert C.run_check("registry_is_current").state == "unknown"

    def test_unknown_when_local_unreadable(self, monkeypatch):
        monkeypatch.setattr(C, "_local_registry_text", lambda: None)
        monkeypatch.setattr(C, "_github_registry_text", lambda: "x")
        assert C.run_check("registry_is_current").state == "unknown"

    def test_network_failure_becomes_unknown_not_a_crash(self, monkeypatch):
        def boom():
            raise OSError("dns failure")
        monkeypatch.setattr(C, "_local_registry_text", lambda: "x")
        monkeypatch.setattr(C, "_github_registry_text", boom)
        assert C.run_check("registry_is_current").state == "unknown"


class TestSerperRollover:
    def test_satisfied_when_month_current(self, monkeypatch):
        monkeypatch.setattr(C, "_today", lambda: date(2026, 8, 10))
        monkeypatch.setattr(C, "_api_usage", lambda: {"month": "2026-08"})
        assert C.run_check("serper_counter_current_month").state == "satisfied"

    def test_pending_when_month_stale(self, monkeypatch):
        monkeypatch.setattr(C, "_today", lambda: date(2026, 8, 10))
        monkeypatch.setattr(C, "_api_usage", lambda: {"month": "2026-07"})
        r = C.run_check("serper_counter_current_month")
        assert r.state == "pending" and "2026-07" in r.detail


class TestScorecardWritten:
    def test_satisfied_when_previous_month_file_exists(self, monkeypatch, tmp_path):
        monkeypatch.setattr(C, "_scorecard_dir", lambda: tmp_path)
        monkeypatch.setattr(C, "_today", lambda: date(2026, 9, 3))
        (tmp_path / "2026-08_scorecard.json").write_text("{}")
        assert C.run_check("monthly_scorecard_written").state == "satisfied"

    def test_pending_when_missing(self, monkeypatch, tmp_path):
        monkeypatch.setattr(C, "_scorecard_dir", lambda: tmp_path)
        monkeypatch.setattr(C, "_today", lambda: date(2026, 9, 3))
        r = C.run_check("monthly_scorecard_written")
        assert r.state == "pending" and "2026-08" in r.detail

    def test_january_looks_back_to_previous_december(self, monkeypatch, tmp_path):
        monkeypatch.setattr(C, "_scorecard_dir", lambda: tmp_path)
        monkeypatch.setattr(C, "_today", lambda: date(2027, 1, 5))
        r = C.run_check("monthly_scorecard_written")
        assert "2026-12" in r.detail


class TestAuditGradedWhenDue:
    def _write(self, tmp_path, monkeypatch, payload, today=date(2026, 8, 10)):
        p = tmp_path / "audit_last_run.json"
        p.write_text(json.dumps(payload), encoding="utf-8")
        monkeypatch.setattr(C, "_AUDIT_RUN_PATH", p)
        monkeypatch.setattr(C, "_today", lambda: today)

    def test_pending_when_rows_exist_but_none_graded(self, tmp_path, monkeypatch):
        """The 2026-08-07 0/119 signature."""
        self._write(tmp_path, monkeypatch, {
            "date": "2026-08-10", "graded": 0, "already_present": 0,
            "skipped_unpriceable": 0, "pending_rows": 119})
        r = C.run_check("audit_graded_when_due")
        assert r.state == "pending" and "119" in r.detail

    def test_satisfied_when_carried_forward(self, tmp_path, monkeypatch):
        self._write(tmp_path, monkeypatch, {
            "date": "2026-08-10", "graded": 0, "already_present": 119,
            "pending_rows": 119})
        assert C.run_check("audit_graded_when_due").state == "satisfied"

    def test_satisfied_when_nothing_to_do(self, tmp_path, monkeypatch):
        self._write(tmp_path, monkeypatch, {
            "date": "2026-08-10", "graded": 0, "already_present": 0,
            "pending_rows": 0})
        assert C.run_check("audit_graded_when_due").state == "satisfied"

    def test_pending_when_nightly_has_gone_stale(self, tmp_path, monkeypatch):
        self._write(tmp_path, monkeypatch, {
            "date": "2026-01-01", "graded": 5, "already_present": 0,
            "pending_rows": 5})
        r = C.run_check("audit_graded_when_due")
        assert r.state == "pending" and "stopped running" in r.detail

    def test_pending_when_no_summary_file_yet(self, tmp_path, monkeypatch):
        monkeypatch.setattr(C, "_AUDIT_RUN_PATH", tmp_path / "absent.json")
        r = C.run_check("audit_graded_when_due")
        assert r.state == "pending" and "not completed" in r.detail


class TestUsersMirrored:
    """Signup writes users.db; the fan-out set reads atlas.db. The mirror that
    joins them is written non-fatally, and unlike the user_instruments index
    there is no nightly rebuild to repair it — so an undetected failure is a
    person who silently receives nothing. This check is that detection."""

    def _counts(self, monkeypatch, *, enabled=True, users=0, atlas=0):
        monkeypatch.setattr(C, "_atlas_enabled", lambda: enabled)
        monkeypatch.setattr(C, "_identity_counts", lambda: (users, atlas))

    def test_satisfied_and_silent_while_atlas_is_off(self, monkeypatch):
        """Pre-cutover users.db IS the identity store, so a divergence is
        meaningless — the check must not nag until the flip makes it real."""
        self._counts(monkeypatch, enabled=False, users=3, atlas=0)
        assert C.run_check("users_mirrored").state == "satisfied"

    def test_satisfied_when_counts_match(self, monkeypatch):
        self._counts(monkeypatch, users=2, atlas=2)
        r = C.run_check("users_mirrored")
        assert r.state == "satisfied" and "2" in r.detail

    def test_pending_when_atlas_is_short(self, monkeypatch):
        self._counts(monkeypatch, users=3, atlas=1)
        r = C.run_check("users_mirrored")
        assert r.state == "pending"
        assert "2" in r.detail and "atlas_etl" in r.detail

    def test_pending_when_atlas_is_ahead(self, monkeypatch):
        """The other direction: a delete cascade that half-failed."""
        self._counts(monkeypatch, users=1, atlas=4)
        r = C.run_check("users_mirrored")
        assert r.state == "pending" and "3" in r.detail

    def test_unreadable_store_becomes_unknown_not_a_crash(self, monkeypatch):
        monkeypatch.setattr(C, "_atlas_enabled", lambda: True)

        def boom():
            raise OSError("database is locked")

        monkeypatch.setattr(C, "_identity_counts", boom)
        assert C.run_check("users_mirrored").state == "unknown"

    def test_disabled_flag_never_touches_atlas_db(self, monkeypatch, tmp_path):
        """Reading user_ids() would CREATE atlas.db and block the C11 cutover,
        so the flag check has to come before any store call — the same landmine
        as atlas_store.mirror_user."""
        import services.data.stores.atlas_store as atlas_store
        monkeypatch.setattr(atlas_store, "_DB_PATH", tmp_path / "atlas.db")
        monkeypatch.setattr(atlas_store, "_conn_holder", {"conn": None})
        monkeypatch.delenv("ATLAS_ENABLED", raising=False)
        atlas_store._reset_for_tests()
        try:
            assert C.run_check("users_mirrored").state == "satisfied"
            assert not (tmp_path / "atlas.db").exists()
        finally:
            atlas_store._reset_for_tests()


def test_manual_confirmation_stays_pending():
    r = C.run_check("manual_confirmation")
    assert r.state == "pending"


def test_every_registry_check_name_is_registered():
    """A milestones.yaml entry naming a check that does not exist would only
    surface at 06:30 as an 'unknown' alert. Catch it at test time instead."""
    from core.ops.watchdog.registry import load_registry
    for entry in load_registry():
        assert entry.check in C.CHECKS, f"{entry.id}: unregistered check {entry.check}"


def test_every_registry_prep_name_is_registered():
    from core.ops.watchdog.prep import PREPS
    from core.ops.watchdog.registry import load_registry
    for entry in load_registry():
        if entry.prep:
            assert entry.prep in PREPS, f"{entry.id}: unregistered prep {entry.prep}"


def test_signals_accruing_is_satisfied_when_no_window_was_open(tmp_path, monkeypatch):
    """A quiet IPO month is not a fault. This check must not cry wolf."""
    import core.ops.watchdog.checks as checks
    monkeypatch.setattr(checks, "_data_dir", lambda: tmp_path)
    (tmp_path / "market_cache").mkdir(parents=True)
    (tmp_path / "market_cache" / "ipo.json").write_text(
        '{"fetched_at": "2026-08-13T08:00:00+00:00", "current": [], '
        '"upcoming": [], "past": []}', encoding="utf-8")
    assert checks.ipo_signals_accruing().state == "satisfied"


def test_signals_accruing_is_pending_when_an_open_issue_has_no_snapshot(tmp_path, monkeypatch):
    import core.ops.watchdog.checks as checks
    monkeypatch.setattr(checks, "_data_dir", lambda: tmp_path)
    (tmp_path / "market_cache").mkdir(parents=True)
    (tmp_path / "market_cache" / "ipo.json").write_text(
        '{"fetched_at": "2026-08-13T08:00:00+00:00", "current": ['
        '{"symbol": "MOLBIO", "issue_start": "2026-08-10", '
        '"issue_end": "2099-01-01", "listing_date": ""}], '
        '"upcoming": [], "past": []}', encoding="utf-8")
    (tmp_path / "ipo").mkdir(parents=True)
    result = checks.ipo_signals_accruing()
    assert result.state == "pending"
    assert "MOLBIO" in result.detail


def test_signals_accruing_is_satisfied_with_only_upcoming_issues(tmp_path, monkeypatch):
    """An issue that hasn't opened yet has nothing to capture yet — not a fault."""
    import core.ops.watchdog.checks as checks
    monkeypatch.setattr(checks, "_data_dir", lambda: tmp_path)
    (tmp_path / "market_cache").mkdir(parents=True)
    (tmp_path / "market_cache" / "ipo.json").write_text(json.dumps({
        "fetched_at": "2026-08-13T08:00:00+00:00",
        "current": [],
        "upcoming": [{"symbol": "FUTURE", "issue_start": "2099-01-01",
                       "issue_end": "2099-01-05", "listing_date": ""}],
        "past": []}), encoding="utf-8")
    assert checks.ipo_signals_accruing().state == "satisfied"


def test_signals_accruing_is_satisfied_with_only_closed_issues(tmp_path, monkeypatch):
    """Closed-but-not-listed issues linger in the NSE feed for days; a closed
    window is no longer open, so there is nothing new to capture."""
    import core.ops.watchdog.checks as checks
    monkeypatch.setattr(checks, "_data_dir", lambda: tmp_path)
    (tmp_path / "market_cache").mkdir(parents=True)
    (tmp_path / "market_cache" / "ipo.json").write_text(json.dumps({
        "fetched_at": "2026-08-13T08:00:00+00:00",
        "current": [{"symbol": "OLDISSUE", "issue_start": "2020-01-01",
                      "issue_end": "2020-01-10", "listing_date": ""}],
        "upcoming": [],
        "past": []}), encoding="utf-8")
    assert checks.ipo_signals_accruing().state == "satisfied"


def test_signals_accruing_is_satisfied_with_only_listed_issues(tmp_path, monkeypatch):
    """`listed` outranks open/closed — once the tape exists the window is
    history, so this must not be mistaken for a currently-open issue."""
    import core.ops.watchdog.checks as checks
    monkeypatch.setattr(checks, "_data_dir", lambda: tmp_path)
    (tmp_path / "market_cache").mkdir(parents=True)
    (tmp_path / "market_cache" / "ipo.json").write_text(json.dumps({
        "fetched_at": "2026-08-13T08:00:00+00:00",
        "current": [{"symbol": "TAPED", "issue_start": "2020-01-01",
                      "issue_end": "2020-01-10", "listing_date": "2020-01-15"}],
        "upcoming": [],
        "past": []}), encoding="utf-8")
    assert checks.ipo_signals_accruing().state == "satisfied"


def test_signals_accruing_names_only_the_missing_symbol_when_mixed(tmp_path, monkeypatch):
    """Two open issues, one already captured and one not — pending must name
    only the one actually missing, not the one already accruing."""
    import core.ops.watchdog.checks as checks
    from core.ipo.signals import IpoSignalSnapshot, IpoSignalStore
    monkeypatch.setattr(checks, "_data_dir", lambda: tmp_path)
    (tmp_path / "market_cache").mkdir(parents=True)
    (tmp_path / "market_cache" / "ipo.json").write_text(json.dumps({
        "fetched_at": "2026-08-13T08:00:00+00:00",
        "current": [
            {"symbol": "CAPTURED", "issue_start": "2026-08-10",
             "issue_end": "2099-01-01", "listing_date": ""},
            {"symbol": "MISSING", "issue_start": "2026-08-10",
             "issue_end": "2099-01-01", "listing_date": ""},
        ],
        "upcoming": [], "past": []}), encoding="utf-8")
    store = IpoSignalStore(base_dir=str(tmp_path / "ipo"))
    store.append(IpoSignalSnapshot(symbol="CAPTURED",
                                    captured_at="2026-08-13T08:00:00+00:00"))
    result = checks.ipo_signals_accruing()
    assert result.state == "pending"
    assert "MISSING" in result.detail
    assert "CAPTURED" not in result.detail
    assert result.evidence["missing"] == ["MISSING"]


def test_signals_accruing_ignores_a_malformed_row_without_raising(tmp_path, monkeypatch):
    """A non-dict row inside `current` must not crash the 06:30 job."""
    import core.ops.watchdog.checks as checks
    monkeypatch.setattr(checks, "_data_dir", lambda: tmp_path)
    (tmp_path / "market_cache").mkdir(parents=True)
    (tmp_path / "market_cache" / "ipo.json").write_text(json.dumps({
        "fetched_at": "2026-08-13T08:00:00+00:00",
        "current": ["not-a-dict", 42, None],
        "upcoming": [], "past": []}), encoding="utf-8")
    result = checks.ipo_signals_accruing()
    assert result.state == "satisfied"


def test_signals_accruing_survives_an_unreadable_ledger(tmp_path, monkeypatch):
    """If the ledger itself cannot be read — a permission error in prod, and
    here a path collision that forces the same failure — the check must
    return a verdict, not raise and rely on run_check's outer net."""
    import core.ops.watchdog.checks as checks
    monkeypatch.setattr(checks, "_data_dir", lambda: tmp_path)
    (tmp_path / "market_cache").mkdir(parents=True)
    (tmp_path / "market_cache" / "ipo.json").write_text(json.dumps({
        "fetched_at": "2026-08-13T08:00:00+00:00",
        "current": [{"symbol": "MOLBIO", "issue_start": "2026-08-10",
                      "issue_end": "2099-01-01", "listing_date": ""}],
        "upcoming": [], "past": []}), encoding="utf-8")
    # A file where the store expects a directory makes IpoSignalStore's own
    # mkdir(parents=True, exist_ok=True) raise FileExistsError.
    (tmp_path / "ipo").write_text("not a directory", encoding="utf-8")
    result = checks.ipo_signals_accruing()
    assert result.state == "pending"
    assert "MOLBIO" in result.detail

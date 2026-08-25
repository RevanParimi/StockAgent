"""
tests/unit/shared/test_data_health_record.py
=============================================
Three Loops PI — task B2: emit the data-health record.

Prod evidence (2026-08-24, spec §2.3): a SUZLON run lost 3 of its 6
dimensions, shipped a BUY, and logged `real_data=True`. `has_real_data` is
`live >= 3` of 10 sections and its only consumer is a log line, so a run that
kept 3 sections and a run that kept all 10 left the same trace. These tests
pin the record that tells them apart, and pin that producing it can never
cost the run.
"""
from __future__ import annotations

import importlib
import json
import os
from pathlib import Path
from unittest import mock
from unittest.mock import MagicMock, patch

import pytest

import services.data.stores.data_health as dh
import services.data.stores.log_store as log_store
from backend.shared.pipeline import base_orchestrator as bo_mod
from backend.shared.pipeline.base_orchestrator import BaseSectorOrchestrator
from backend.shared.pipeline.unified_analyst import DIMENSIONS
from core.schemas.pipeline import AgentOutput, StockQuery
from services.data.context import bundle_builder as bb


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def health_log(tmp_path):
    """Re-execute data_health with LOGS_DIR pinned to a throwaway directory."""
    target = tmp_path / "logs"
    clean = {k: v for k, v in os.environ.items() if k != "LOGS_DIR"}
    clean["LOGS_DIR"] = str(target)
    with mock.patch.dict(os.environ, clean, clear=True):
        importlib.reload(dh)
        yield target / "data_health.jsonl"
    importlib.reload(dh)


@pytest.fixture()
def fresh_db(tmp_path, monkeypatch):
    """Point the telemetry store at a throwaway DB, reset its cached conn."""
    db_path = tmp_path / "telemetry.db"
    monkeypatch.setattr(log_store.settings, "TELEMETRY_DB_PATH", str(db_path), raising=False)
    monkeypatch.setattr(log_store, "_conn", None)
    yield db_path
    if log_store._conn is not None:
        log_store._conn.close()
        log_store._conn = None


def _rows(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def _all_ok_status() -> dict[str, str]:
    return {name: bb.STATUS_OK for name in bb.SECTION_ORDER}


def _record(module, **overrides):
    kwargs = dict(
        run_id="r1",
        ticker="SUZLON",
        sector="renewable_energy",
        section_status=_all_ok_status(),
        api_calls={"serper": 3, "tavily": 1},
        dimensions_expected=list(DIMENSIONS["renewable_energy"]),
        dimensions_missing=[],
    )
    kwargs.update(overrides)
    return module.record_data_health(**kwargs)


# ---------------------------------------------------------------------------
# 1. The bundle records an outcome per section, not just a string
# ---------------------------------------------------------------------------

class TestSectionStatus:
    """`empty` must be distinguishable from `failed` and from `n/a` — that is
    the whole point of the field. A fetcher that returns "" without raising is
    the state nothing catches today."""

    def _build(self, sector="renewable_energy", **fetchers):
        query = StockQuery(ticker="SUZLON", company_name="Suzlon Energy Ltd", nse_data={})
        defaults = {name: "live text" for name in bb.SECTION_ORDER}
        defaults.update(fetchers)
        patchers = []
        for name, value in defaults.items():
            kw = {"side_effect": value} if isinstance(value, Exception) else {"return_value": value}
            patchers.append(patch.object(bb, f"_fetch_{name}", **kw))
        for p in patchers:
            p.start()
        try:
            return bb.build_sector_bundle(query, sector)
        finally:
            for p in patchers:
                p.stop()

    def test_healthy_sections_are_ok(self):
        bundle = self._build()
        assert set(bundle.section_status) == set(bb.SECTION_ORDER)
        assert set(bundle.section_status.values()) == {bb.STATUS_OK}

    def test_empty_string_is_empty_not_ok(self):
        """Acceptance: `_fetch_flows_sentiment` returning "" records `empty`."""
        bundle = self._build(flows_sentiment="")
        assert bundle.section_status["flows_sentiment"] == bb.STATUS_EMPTY
        assert bundle.section_status["company_news"] == bb.STATUS_OK

    def test_whitespace_only_is_also_empty(self):
        bundle = self._build(flows_sentiment="   \n  ")
        assert bundle.section_status["flows_sentiment"] == bb.STATUS_EMPTY

    def test_raised_exception_is_failed_with_the_type(self):
        bundle = self._build(technicals=RuntimeError("boom"))
        assert bundle.section_status["technicals"] == "failed:RuntimeError"
        assert bundle.sections["technicals"] == bb.UNAVAILABLE

    def test_failed_is_not_empty(self):
        bundle = self._build(technicals=RuntimeError("boom"), flows_sentiment="")
        assert bundle.section_status["technicals"] != bundle.section_status["flows_sentiment"]

    def test_deliberate_skip_is_not_applicable(self):
        """`commodities` outside automobile is skipped by design, not broken."""
        bundle = self._build(commodities=bb.NOT_APPLICABLE)
        assert bundle.section_status["commodities"] == bb.STATUS_NOT_APPLICABLE

    def test_macro_cache_hit_is_recorded_by_the_branch_that_knows(self):
        """A cache hit looks like any other populated section from the outside,
        so `_fetch_macro_context` records it where the branch is taken."""
        query = StockQuery(ticker="SUZLON", company_name="Suzlon Energy Ltd", nse_data={})
        status: dict[str, str] = {}
        with patch("services.data.fetchers.macro.get_macro_context", return_value="macro"), \
             patch("services.data.cache.macro_cache.get_macro_cache", return_value="cached news"):
            text = bb._fetch_macro_context("renewable_energy", "fake-key", status)

        assert status["macro_context"] == bb.STATUS_CACHE_HIT
        assert "cached news" in text

    def test_macro_miss_leaves_the_status_to_the_classifier(self):
        query = StockQuery(ticker="SUZLON", company_name="Suzlon Energy Ltd", nse_data={})
        status: dict[str, str] = {}
        with patch("services.data.fetchers.macro.get_macro_context", return_value="macro"), \
             patch("services.data.cache.macro_cache.get_macro_cache", return_value=""), \
             patch("services.data.fetchers.news.fetch_news_context", return_value="fresh news"):
            bb._fetch_macro_context("renewable_energy", "fake-key", status)

        assert "macro_context" not in status

    def test_has_real_data_is_unchanged_by_b2(self):
        """B2 is additive. `has_real_data` keeps its old meaning — including
        counting an `n/a` section as live, which the health record does not."""
        bundle = self._build(sector="renewable_energy", commodities=bb.NOT_APPLICABLE)
        assert bundle.has_real_data is True
        assert bundle.section_status["commodities"] == bb.STATUS_NOT_APPLICABLE

    def test_all_sections_dead_means_no_real_data(self):
        bundle = self._build(**{name: "" for name in bb.SECTION_ORDER})
        assert bundle.has_real_data is False


# ---------------------------------------------------------------------------
# 2. The record itself
# ---------------------------------------------------------------------------

class TestBuildRecord:
    def test_counts_split_live_failed_empty_and_na(self):
        status = _all_ok_status()
        status["macro_context"] = bb.STATUS_CACHE_HIT
        status["flows_sentiment"] = bb.STATUS_EMPTY
        status["commodities"] = bb.STATUS_NOT_APPLICABLE
        status["technicals"] = "failed:RuntimeError"

        rec = dh.build_record(
            run_id="r1", ticker="SUZLON", sector="renewable_energy",
            section_status=status, api_calls={"serper": 2},
            dimensions_expected=list(DIMENSIONS["renewable_energy"]),
            dimensions_missing=[],
        )

        assert rec["live"] == 7          # 6 ok + 1 cache_hit
        assert rec["degraded"] == 1
        assert rec["empty"] == 1
        assert rec["not_applicable"] == 1
        assert rec["live"] + rec["degraded"] + rec["empty"] + rec["not_applicable"] == 10

    def test_a_section_the_builder_never_reached_is_named_not_dropped(self):
        rec = dh.build_record(
            run_id="r1", ticker="SUZLON", sector="renewable_energy",
            section_status={"company_news": bb.STATUS_OK}, api_calls=None,
            dimensions_expected=list(DIMENSIONS["renewable_energy"]),
            dimensions_missing=[],
        )
        assert set(rec["sections"]) == set(bb.SECTION_ORDER)
        assert rec["sections"]["dossier"] == "failed:NotReached"
        assert rec["live"] == 1

    def test_health_ok_when_every_dimension_scored(self):
        rec = dh.build_record(
            run_id="r1", ticker="SUZLON", sector="renewable_energy",
            section_status=_all_ok_status(), api_calls=None,
            dimensions_expected=list(DIMENSIONS["renewable_energy"]),
            dimensions_missing=[],
        )
        assert rec["health"] == dh.HEALTH_OK

    def test_health_degraded_when_a_dimension_is_missing(self):
        rec = dh.build_record(
            run_id="r1", ticker="SUZLON", sector="renewable_energy",
            section_status=_all_ok_status(), api_calls=None,
            dimensions_expected=list(DIMENSIONS["renewable_energy"]),
            dimensions_missing=["technical"],
        )
        assert rec["health"] == dh.HEALTH_DEGRADED

    def test_health_hollow_when_nothing_scored(self):
        rec = dh.build_record(
            run_id="r1", ticker="SUZLON", sector="renewable_energy",
            section_status=_all_ok_status(), api_calls=None,
            dimensions_expected=list(DIMENSIONS["renewable_energy"]),
            dimensions_missing=list(DIMENSIONS["renewable_energy"]),
        )
        assert rec["health"] == dh.HEALTH_HOLLOW
        assert rec["dimensions_scored"] == 0

    def test_health_hollow_when_no_section_came_back_live(self):
        rec = dh.build_record(
            run_id="r1", ticker="SUZLON", sector="renewable_energy",
            section_status={n: bb.STATUS_EMPTY for n in bb.SECTION_ORDER}, api_calls=None,
            dimensions_expected=list(DIMENSIONS["renewable_energy"]),
            dimensions_missing=[],
        )
        assert rec["health"] == dh.HEALTH_HOLLOW

    def test_the_suzlon_case_reproduces(self):
        """Acceptance: 3 of 6 dimensions, the three missing ones named."""
        rec = dh.build_record(
            run_id="186c7ad4", ticker="SUZLON", sector="renewable_energy",
            section_status=_all_ok_status(), api_calls={"serper": 3, "tavily": 1},
            dimensions_expected=list(DIMENSIONS["renewable_energy"]),
            dimensions_missing=["sentiment_policy", "technical", "risk"],
        )

        assert rec["dimensions_expected"] == 6
        assert rec["dimensions_scored"] == 3
        assert rec["dimensions_missing"] == ["sentiment_policy", "technical", "risk"]
        assert rec["health"] == dh.HEALTH_DEGRADED


# ---------------------------------------------------------------------------
# 3. Persistence — JSONL + telemetry.db
# ---------------------------------------------------------------------------

class TestPersistence:
    def test_row_written_to_jsonl(self, health_log, fresh_db):
        mod = importlib.import_module("services.data.stores.data_health")
        _record(mod)

        rows = _rows(health_log)
        assert len(rows) == 1
        assert rows[0]["ticker"] == "SUZLON"
        assert rows[0]["sector"] == "renewable_energy"
        assert rows[0]["health"] == dh.HEALTH_OK

    def test_row_mirrored_to_telemetry_db(self, health_log, fresh_db):
        mod = importlib.import_module("services.data.stores.data_health")
        _record(mod)

        assert log_store.data_health_count() == 1
        assert log_store.data_health_count(health=dh.HEALTH_OK) == 1
        assert log_store.data_health_count(health=dh.HEALTH_HOLLOW) == 0

    def test_default_log_path_is_the_volume(self):
        """B1's rule: one LOGS_DIR default, and it is the Railway volume."""
        clean = {k: v for k, v in os.environ.items() if k != "LOGS_DIR"}
        try:
            with mock.patch.dict(os.environ, clean, clear=True):
                mod = importlib.reload(dh)
                assert not mod.DATA_HEALTH_LOG.is_absolute()
                assert mod.DATA_HEALTH_LOG == Path("data") / "logs" / "data_health.jsonl"
        finally:
            importlib.reload(dh)

    def test_flag_off_writes_nothing(self, health_log, fresh_db, monkeypatch):
        """Rollback line: `observability.data_health_enabled: false`."""
        mod = importlib.import_module("services.data.stores.data_health")
        monkeypatch.setattr(mod, "data_health_enabled", lambda: False)

        assert _record(mod) is None
        assert _rows(health_log) == []
        assert log_store.data_health_count() == 0


# ---------------------------------------------------------------------------
# 4. It can never cost the run
# ---------------------------------------------------------------------------

class TestNeverRaises:
    """Acceptance: force each writer to throw and assert the caller survives."""

    def test_jsonl_writer_throwing_still_returns_the_record(self, health_log, fresh_db, monkeypatch):
        mod = importlib.import_module("services.data.stores.data_health")
        monkeypatch.setattr(mod, "_append", MagicMock(side_effect=OSError("disk full")))

        rec = _record(mod)

        assert rec is not None                       # the run still gets its record
        assert log_store.data_health_count() == 1    # and the durable mirror still has it

    def test_telemetry_mirror_throwing_still_writes_the_jsonl(self, health_log, fresh_db, monkeypatch):
        monkeypatch.setattr(
            log_store, "log_data_health", MagicMock(side_effect=RuntimeError("db locked"))
        )
        mod = importlib.import_module("services.data.stores.data_health")

        rec = _record(mod)

        assert rec is not None
        assert len(_rows(health_log)) == 1

    def test_both_writers_throwing_still_returns_the_record(self, health_log, fresh_db, monkeypatch):
        mod = importlib.import_module("services.data.stores.data_health")
        monkeypatch.setattr(mod, "_append", MagicMock(side_effect=OSError("disk full")))
        monkeypatch.setattr(
            log_store, "log_data_health", MagicMock(side_effect=RuntimeError("db locked"))
        )

        assert _record(mod) is not None

    def test_a_broken_record_builder_returns_none_instead_of_raising(self, health_log, monkeypatch):
        mod = importlib.import_module("services.data.stores.data_health")
        monkeypatch.setattr(mod, "build_record", MagicMock(side_effect=ValueError("nope")))

        assert _record(mod) is None

    def test_a_broken_flag_read_returns_none_instead_of_raising(self, health_log, monkeypatch):
        mod = importlib.import_module("services.data.stores.data_health")
        monkeypatch.setattr(
            mod, "data_health_enabled", MagicMock(side_effect=RuntimeError("bad yaml"))
        )

        assert _record(mod) is None


# ---------------------------------------------------------------------------
# 5. The orchestrator wiring
# ---------------------------------------------------------------------------

class _DummyAgent:
    def run(self, query, run_id):  # pragma: no cover - graph is never invoked
        return AgentOutput(agent="dummy", ticker=query.ticker, overall_score=0.5)


class _RenewableTestOrchestrator(BaseSectorOrchestrator):
    SECTOR_NAME = "renewable_energy"

    def __init__(self) -> None:
        self._sub_agents = {"dummy": _DummyAgent()}
        super().__init__()


@pytest.fixture()
def orchestrator():
    with patch(
        "backend.shared.pipeline.base_orchestrator.get_llm_client", return_value=MagicMock()
    ):
        orch = _RenewableTestOrchestrator()
    orch._aggregator = MagicMock()
    return orch


def _suzlon_outputs(missing: list[str]) -> dict[str, AgentOutput]:
    outputs = {}
    for dim in DIMENSIONS["renewable_energy"]:
        outputs[dim] = AgentOutput(
            agent=dim, ticker="SUZLON", overall_score=0.5,
            error="missing_in_unified_response" if dim in missing else None,
        )
    return outputs


class TestOrchestratorWiring:
    def _run(self, orchestrator, outputs, *, section_status=None):
        bundle = bb.SectorDataBundle(
            sections={n: "live text" for n in bb.SECTION_ORDER},
            has_real_data=True,
            api_calls_made={"serper": 3, "tavily": 1},
            section_status=section_status or _all_ok_status(),
        )
        query = StockQuery(ticker="SUZLON", company_name="Suzlon Energy Ltd")
        analyst = MagicMock()
        analyst.run.return_value = outputs
        analyst._last_prompt_tokens = 0
        analyst._last_completion_tokens = 0
        with patch("services.data.context.bundle_builder.build_sector_bundle", return_value=bundle), \
             patch("backend.shared.pipeline.unified_analyst.UnifiedAnalyst", return_value=analyst):
            orchestrator._run_unified(query, run_id="186c7ad4")
        return orchestrator._last_data_health

    def test_the_suzlon_run_records_three_of_six(self, orchestrator, health_log, fresh_db):
        """Acceptance, end to end: the errored dimensions are the missing ones,
        and they are exactly what SignalAggregator excludes from the composite."""
        missing = ["sentiment_policy", "technical", "risk"]

        rec = self._run(orchestrator, _suzlon_outputs(missing))

        assert rec is not None
        assert rec["dimensions_expected"] == 6
        assert rec["dimensions_scored"] == 3
        assert sorted(rec["dimensions_missing"]) == sorted(missing)
        assert rec["health"] == dh.HEALTH_DEGRADED
        assert len(_rows(health_log)) == 1

    def test_a_clean_run_records_ok(self, orchestrator, health_log, fresh_db):
        rec = self._run(orchestrator, _suzlon_outputs([]))

        assert rec["dimensions_scored"] == 6
        assert rec["health"] == dh.HEALTH_OK

    def test_a_failed_run_still_writes_a_row(self, orchestrator, health_log, fresh_db):
        """Acceptance: a row for every run, including the total failure — the
        case most worth having, and the one an `if outputs:` guard would drop."""
        rec = self._run(orchestrator, {})

        assert rec is not None
        assert rec["dimensions_expected"] == 6
        assert rec["dimensions_scored"] == 0
        assert sorted(rec["dimensions_missing"]) == sorted(DIMENSIONS["renewable_energy"])
        assert rec["health"] == dh.HEALTH_HOLLOW
        assert len(_rows(health_log)) == 1

    def test_recording_failure_does_not_break_the_run(self, orchestrator, health_log, fresh_db):
        """The whole point of the isolation: bookkeeping must not cost a verdict."""
        outputs = _suzlon_outputs([])
        bundle = bb.SectorDataBundle(
            sections={n: "live text" for n in bb.SECTION_ORDER},
            has_real_data=True,
            api_calls_made={},
            section_status=_all_ok_status(),
        )
        query = StockQuery(ticker="SUZLON", company_name="Suzlon Energy Ltd")
        analyst = MagicMock()
        analyst.run.return_value = outputs
        analyst._last_prompt_tokens = 0
        analyst._last_completion_tokens = 0
        with patch("services.data.context.bundle_builder.build_sector_bundle", return_value=bundle), \
             patch("backend.shared.pipeline.unified_analyst.UnifiedAnalyst", return_value=analyst), \
             patch("services.data.stores.data_health.record_data_health",
                   side_effect=RuntimeError("store exploded")):
            result = orchestrator._run_unified(query, run_id="r1")

        assert result == outputs                       # the verdict survives
        assert orchestrator._last_data_health is None  # only the record is lost

    def test_legacy_fallback_keeps_the_row_but_drops_it_from_the_report(
        self, orchestrator, health_log, fresh_db, monkeypatch
    ):
        """The hollow unified attempt is real and stays on disk — that is the
        degradation nothing used to record. But the verdict comes from the
        legacy pool, so `dimensions_scored: 0` must not ride along on it."""
        monkeypatch.setattr(bo_mod.settings, "UNIFIED_ANALYST_SECTORS", "renewable_energy")
        monkeypatch.setattr(bo_mod.settings, "UNIFIED_ANALYST_FALLBACK_LEGACY", True)
        legacy_outputs = _suzlon_outputs([])
        bundle = bb.SectorDataBundle(
            sections={n: "live text" for n in bb.SECTION_ORDER},
            has_real_data=True, api_calls_made={}, section_status=_all_ok_status(),
        )
        analyst = MagicMock()
        analyst.run.return_value = {}          # total unified failure
        query = StockQuery(ticker="SUZLON", company_name="Suzlon Energy Ltd")

        with patch("services.data.context.bundle_builder.build_sector_bundle", return_value=bundle), \
             patch("backend.shared.pipeline.unified_analyst.UnifiedAnalyst", return_value=analyst), \
             patch.object(orchestrator, "_run_via_graph", return_value=legacy_outputs):
            result = orchestrator._run_agents(query, run_id="r1")

        assert result == legacy_outputs
        assert orchestrator._last_data_health is None      # not attached to the report
        rows = _rows(health_log)
        assert len(rows) == 1                              # but recorded all the same
        assert rows[0]["health"] == dh.HEALTH_HOLLOW

    def test_the_record_is_reset_between_runs(self, orchestrator, health_log, fresh_db):
        """An orchestrator instance is long-lived; a stale record on the next
        report would be a lie about a run that never happened."""
        self._run(orchestrator, _suzlon_outputs([]))
        assert orchestrator._last_data_health is not None

        with patch("services.data.stores.data_health.record_data_health", return_value=None):
            self._run(orchestrator, _suzlon_outputs([]))

        assert orchestrator._last_data_health is None


def test_final_report_carries_the_health_record():
    """B5 reads the record off the report, so the field has to exist and
    default to None for the legacy path that builds no bundle."""
    from core.schemas.pipeline import FinalReport

    report = FinalReport(
        ticker="SUZLON", company_name="Suzlon Energy Ltd",
        final_score=0.61, verdict="BUY", weighted_agent_scores={},
    )
    assert report.data_health is None

    report.data_health = {"health": dh.HEALTH_DEGRADED, "dimensions_scored": 3}
    assert report.model_dump()["data_health"]["health"] == dh.HEALTH_DEGRADED

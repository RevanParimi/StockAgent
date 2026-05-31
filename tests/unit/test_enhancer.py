"""
tests/unit/test_enhancer.py
============================
Unit tests for P4 — PromptEnhancer: miss_counter → Search Queries.

Coverage:
  - PromptEnhancer.enhance(): empty miss_counter returns {}
  - enhance(): top_n factors ranked by count
  - enhance(): unknown factor has no template → skipped silently
  - enhance(): placeholder substitution ({ticker}, {date}, {month}, {year})
  - enhance(): multiple factors accumulate queries per agent
  - enhance(): top_n=1 limits to one factor
  - PromptEnhancer.save_enhancements(): file created with correct schema
  - save_enhancements(): based_on_miss_counter snapshot is accurate
  - PredictionStore.load_enhancements(): returns {} when file missing
  - PredictionStore.load_enhancements(): returns agent_enhancements dict
  - PredictionStore._enhancements_path(): correct path construction
  - Backward compatibility: old PredictionStore JSON loads without error
"""

import json
import tempfile
from datetime import date
from pathlib import Path

import pytest

from core.intelligence.prompt_enhancer.enhancer import (
    MISS_FACTOR_TO_QUERY_TEMPLATE,
    PromptEnhancer,
)
from core.intelligence.rl.stores.prediction_store import PredictionStore
from core.schemas.feedback import LearningLedger


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_ledger(miss_counter: dict[str, int], ticker: str = "MARUTI") -> LearningLedger:
    return LearningLedger(
        ticker=ticker,
        sector="automobile",
        last_updated=date.today().isoformat(),
        miss_counter=miss_counter,
    )


# ---------------------------------------------------------------------------
# PromptEnhancer.enhance()
# ---------------------------------------------------------------------------

class TestPromptEnhancerEnhance:
    def test_empty_miss_counter_returns_empty(self):
        ledger = _make_ledger({})
        result = PromptEnhancer().enhance("MARUTI", ledger)
        assert result == {}

    def test_top_n_ranking_by_count(self):
        miss = {
            "FII_outflow_spike":         5,
            "crude_oil_spot_price":      4,
            "RBI_policy_surprise":       3,
            "month_end_inventory_flush": 1,
        }
        ledger = _make_ledger(miss)
        result = PromptEnhancer().enhance("MARUTI", ledger, top_n=2)
        # Should use only the top 2: FII_outflow_spike, crude_oil_spot_price
        for agent_queries in result.values():
            for q in agent_queries:
                assert any(
                    kw in q.lower()
                    for kw in ["fii", "crude", "brent", "dii"]
                ), f"Unexpected query from non-top factor: {q}"

    def test_top_n_default_three(self):
        miss = {
            "FII_outflow_spike":         5,
            "crude_oil_spot_price":      4,
            "RBI_policy_surprise":       3,
            "month_end_inventory_flush": 1,
        }
        ledger = _make_ledger(miss)
        result = PromptEnhancer().enhance("MARUTI", ledger, top_n=3)
        # All agents that appear for the top-3 factors should be in result
        assert len(result) >= 1

    def test_unknown_factor_skipped_silently(self):
        from unittest.mock import patch
        miss = {"completely_unknown_factor_xyz": 99}
        ledger = _make_ledger(miss)
        # LLM generation is the fallback for unknown factors; mock it to return []
        # so the test confirms that when no template AND LLM fails, result is empty.
        with patch.object(PromptEnhancer, "_generate_queries_llm", return_value=[]):
            result = PromptEnhancer().enhance("MARUTI", ledger)
        assert result == {}

    @pytest.mark.parametrize("ticker", ["MARUTI", "TATAMOTORS", "HDFCBANK"])
    def test_ticker_placeholder_substituted(self, ticker):
        miss = {"FII_outflow_spike": 3}
        ledger = _make_ledger(miss, ticker=ticker)
        result = PromptEnhancer().enhance(ticker, ledger, top_n=1)
        # risk_macro query contains the ticker
        assert "risk_macro" in result
        assert ticker in result["risk_macro"][0]

    def test_date_placeholder_substituted(self):
        miss = {"FII_outflow_spike": 3}
        ledger = _make_ledger(miss)
        result = PromptEnhancer().enhance("MARUTI", ledger, top_n=1)
        today_str = date.today().isoformat()
        assert "risk_macro" in result
        assert today_str in result["risk_macro"][0]

    def test_month_year_placeholder_substituted(self):
        miss = {"crude_oil_spot_price": 3}
        ledger = _make_ledger(miss)
        result = PromptEnhancer().enhance("MARUTI", ledger, top_n=1)
        today = date.today()
        # raw_materials query contains month; risk_macro query contains month
        all_queries = [q for qs in result.values() for q in qs]
        assert any(today.strftime("%B") in q or str(today.year) in q for q in all_queries)

    def test_multiple_factors_accumulate_per_agent(self):
        # FII_outflow_spike → risk_macro gets a query
        # crude_oil_spot_price → risk_macro gets another query
        miss = {"FII_outflow_spike": 5, "crude_oil_spot_price": 4}
        ledger = _make_ledger(miss)
        result = PromptEnhancer().enhance("MARUTI", ledger, top_n=2)
        assert "risk_macro" in result
        assert len(result["risk_macro"]) >= 2

    def test_top_n_one_limits_to_single_factor(self):
        miss = {"FII_outflow_spike": 5, "crude_oil_spot_price": 4}
        ledger = _make_ledger(miss)
        result = PromptEnhancer().enhance("MARUTI", ledger, top_n=1)
        # Only FII_outflow_spike (top 1) contributes → only risk_macro + sentiment
        expected_agents = set(MISS_FACTOR_TO_QUERY_TEMPLATE["FII_outflow_spike"].keys())
        assert set(result.keys()) == expected_agents

    def test_all_five_known_factors_produce_output(self):
        factors = {
            "FII_outflow_spike":         5,
            "crude_oil_spot_price":      4,
            "RBI_policy_surprise":       3,
            "INR_depreciation":          2,
            "month_end_inventory_flush": 1,
        }
        ledger = _make_ledger(factors)
        result = PromptEnhancer().enhance("MARUTI", ledger, top_n=5)
        assert len(result) >= 1
        all_queries = [q for qs in result.values() for q in qs]
        assert len(all_queries) >= 5   # at least one query per factor


# ---------------------------------------------------------------------------
# PromptEnhancer.save_enhancements()
# ---------------------------------------------------------------------------

class TestPromptEnhancerSave:
    def test_file_created_with_correct_schema(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            "core.config.settings.PREDICTION_DATA_DIR", str(tmp_path)
        )
        import core.intelligence.prompt_enhancer.enhancer as enhancer_mod
        monkeypatch.setattr(enhancer_mod.settings, "PREDICTION_DATA_DIR", str(tmp_path))

        miss = {"FII_outflow_spike": 3}
        ledger = _make_ledger(miss)
        enhancements = PromptEnhancer().enhance("MARUTI", ledger, top_n=1)
        cycle_id = "MARUTI_2026-04"

        PromptEnhancer().save_enhancements("MARUTI", "automobile", enhancements, cycle_id, ledger)

        saved_path = tmp_path / "automobile" / "MARUTI" / f"{cycle_id}_prompt_enhancements.json"
        assert saved_path.exists(), "Enhancement file not created"

        data = json.loads(saved_path.read_text(encoding="utf-8"))
        assert data["ticker"] == "MARUTI"
        assert data["cycle_id"] == cycle_id
        assert "generated_at" in data
        assert "based_on_miss_counter" in data
        assert "agent_enhancements" in data

    def test_miss_counter_snapshot_saved(self, tmp_path, monkeypatch):
        import core.intelligence.prompt_enhancer.enhancer as enhancer_mod
        monkeypatch.setattr(enhancer_mod.settings, "PREDICTION_DATA_DIR", str(tmp_path))

        miss = {"FII_outflow_spike": 5, "crude_oil_spot_price": 3}
        ledger = _make_ledger(miss)
        enhancements = PromptEnhancer().enhance("MARUTI", ledger, top_n=2)
        PromptEnhancer().save_enhancements("MARUTI", "automobile", enhancements, "MARUTI_2026-04", ledger)

        saved_path = tmp_path / "automobile" / "MARUTI" / "MARUTI_2026-04_prompt_enhancements.json"
        data = json.loads(saved_path.read_text(encoding="utf-8"))
        assert data["based_on_miss_counter"]["FII_outflow_spike"] == 5
        assert data["based_on_miss_counter"]["crude_oil_spot_price"] == 3

    def test_empty_enhancements_saves_cleanly(self, tmp_path, monkeypatch):
        import core.intelligence.prompt_enhancer.enhancer as enhancer_mod
        monkeypatch.setattr(enhancer_mod.settings, "PREDICTION_DATA_DIR", str(tmp_path))

        ledger = _make_ledger({})
        enhancements = {}
        PromptEnhancer().save_enhancements("MARUTI", "automobile", enhancements, "MARUTI_2026-04", ledger)

        saved_path = tmp_path / "automobile" / "MARUTI" / "MARUTI_2026-04_prompt_enhancements.json"
        assert saved_path.exists()
        data = json.loads(saved_path.read_text(encoding="utf-8"))
        assert data["agent_enhancements"] == {}

    def test_ticker_normalised_to_uppercase(self, tmp_path, monkeypatch):
        import core.intelligence.prompt_enhancer.enhancer as enhancer_mod
        monkeypatch.setattr(enhancer_mod.settings, "PREDICTION_DATA_DIR", str(tmp_path))

        PromptEnhancer().save_enhancements("maruti", "automobile", {}, "maruti_2026-04", None)
        saved_path = tmp_path / "automobile" / "MARUTI" / "maruti_2026-04_prompt_enhancements.json"
        assert saved_path.exists()


# ---------------------------------------------------------------------------
# PredictionStore.load_enhancements() + _enhancements_path()
# ---------------------------------------------------------------------------

class TestPredictionStoreEnhancements:
    def test_load_enhancements_missing_file_returns_empty(self, tmp_path):
        store = PredictionStore("MARUTI", sector="automobile", base_dir=str(tmp_path))
        result = store.load_enhancements("MARUTI_2026-04")
        assert result == {}

    def test_load_enhancements_reads_agent_enhancements(self, tmp_path):
        store = PredictionStore("MARUTI", sector="automobile", base_dir=str(tmp_path))
        cycle_id = "MARUTI_2026-04"
        path = store._enhancements_path(cycle_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "ticker": "MARUTI",
            "cycle_id": cycle_id,
            "generated_at": "2026-04-01",
            "based_on_miss_counter": {"FII_outflow_spike": 5},
            "agent_enhancements": {
                "risk_macro": ["MARUTI FII DII net flows 2026-04-01"],
                "sentiment":  ["FII selling India equity April 2026"],
            },
        }
        path.write_text(json.dumps(payload), encoding="utf-8")

        result = store.load_enhancements(cycle_id)
        assert "risk_macro" in result
        assert len(result["risk_macro"]) == 1
        assert "MARUTI FII DII" in result["risk_macro"][0]

    def test_enhancements_path_includes_cycle_id(self, tmp_path):
        store = PredictionStore("MARUTI", sector="automobile", base_dir=str(tmp_path))
        path = store._enhancements_path("MARUTI_2026-04")
        assert "MARUTI_2026-04" in str(path)
        assert path.name.endswith("_prompt_enhancements.json")

    def test_load_enhancements_uses_current_cycle_when_none(self, tmp_path):
        store = PredictionStore("MARUTI", sector="automobile", base_dir=str(tmp_path))
        # No file → returns {}
        result = store.load_enhancements(None)
        assert result == {}

    def test_load_enhancements_corrupt_file_returns_empty(self, tmp_path):
        store = PredictionStore("MARUTI", sector="automobile", base_dir=str(tmp_path))
        path = store._enhancements_path("MARUTI_2026-04")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("NOT JSON", encoding="utf-8")
        result = store.load_enhancements("MARUTI_2026-04")
        assert result == {}

    def test_load_enhancements_missing_key_returns_empty(self, tmp_path):
        # File exists but has no "agent_enhancements" key
        store = PredictionStore("MARUTI", sector="automobile", base_dir=str(tmp_path))
        path = store._enhancements_path("MARUTI_2026-04")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"ticker": "MARUTI"}), encoding="utf-8")
        result = store.load_enhancements("MARUTI_2026-04")
        assert result == {}


# ---------------------------------------------------------------------------
# Template map sanity checks
# ---------------------------------------------------------------------------

class TestMissFactorTemplateMap:
    @pytest.mark.parametrize("factor", [
        "FII_outflow_spike",
        "crude_oil_spot_price",
        "RBI_policy_surprise",
        "INR_depreciation",
        "month_end_inventory_flush",
    ])
    def test_all_required_factors_present(self, factor):
        assert factor in MISS_FACTOR_TO_QUERY_TEMPLATE

    @pytest.mark.parametrize("factor", [
        "FII_outflow_spike",
        "crude_oil_spot_price",
        "RBI_policy_surprise",
        "INR_depreciation",
        "month_end_inventory_flush",
    ])
    def test_each_factor_has_at_least_one_agent(self, factor):
        templates = MISS_FACTOR_TO_QUERY_TEMPLATE[factor]
        assert isinstance(templates, dict)
        assert len(templates) >= 1

    def test_templates_contain_supported_placeholders(self):
        supported = {"{ticker}", "{date}", "{month}", "{year}"}
        for factor, agent_map in MISS_FACTOR_TO_QUERY_TEMPLATE.items():
            for agent, template in agent_map.items():
                # Collect placeholders used in this template
                import re
                used = set(re.findall(r"\{[^}]+\}", template))
                unknown = used - supported
                assert not unknown, (
                    f"Factor '{factor}', agent '{agent}': "
                    f"unsupported placeholders {unknown}"
                )

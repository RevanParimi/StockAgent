"""tests/unit/intelligence/rl/test_factor_regime_stale.py — AUD-073."""
import inspect

from core.intelligence.rl.algorithms.factor_regime import (
    format_factor_regime_context,
    get_regime_penalty_scale,
    _vintage_is_stale,
)


def _regime(stale: bool):
    return {"regime": "REVERSAL", "strength": "STRONG", "z_score": -2.0,
            "avg_wml_pct": -1.5, "last_wml_pct": -3.0, "size_tilt": "SMALL_CAP",
            "style_tilt": "VALUE", "market_factor_avg": 0.1,
            "lookback_months": 12, "data_vintage": "2023-03",
            "fetched_at": "2026-07-17", "data_stale": stale}


def test_stale_regime_never_scales_penalties():
    assert get_regime_penalty_scale("pattern_analysis", _regime(stale=True)) == 1.0


def test_fresh_regime_still_scales():
    assert get_regime_penalty_scale("pattern_analysis", _regime(stale=False)) == 0.80


def test_missing_stale_key_behaves_as_fresh():
    r = _regime(stale=False)
    del r["data_stale"]
    assert get_regime_penalty_scale("pattern_analysis", r) == 0.80


def test_vintage_staleness_detection():
    assert _vintage_is_stale("2023-03") is True     # 3+ years old
    assert _vintage_is_stale("garbage") is True     # unparseable -> stale (safe)


def test_context_labels_stale_data():
    ctx = format_factor_regime_context(_regime(stale=True))
    assert "STALE" in ctx
    assert "2023-03" in ctx


def test_no_verify_false_in_module():
    import core.intelligence.rl.algorithms.factor_regime as fr
    assert "verify=False" not in inspect.getsource(fr)

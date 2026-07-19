"""tests/unit/shared/test_verdict_shadow.py — AUD-077 shadow lane."""
import json

import backend.shared.pipeline.verdict_shadow as vs


def test_verdict_from_composite_bands():
    assert vs.verdict_from_composite(0.90) == "STRONG BUY"
    assert vs.verdict_from_composite(0.75) == "STRONG BUY"   # lo-inclusive
    assert vs.verdict_from_composite(0.60) == "BUY"
    assert vs.verdict_from_composite(0.50) == "NEUTRAL"
    assert vs.verdict_from_composite(0.30) == "SELL"
    assert vs.verdict_from_composite(0.05) == "STRONG SELL"
    assert vs.verdict_from_composite(0.0) == "STRONG SELL"
    assert vs.verdict_from_composite(1.0) == "STRONG BUY"


def test_log_verdict_shadow_appends_record(tmp_path):
    log = tmp_path / "shadow.jsonl"
    rec = vs.log_verdict_shadow(
        ticker="MARUTI", composite=0.62, llm_verdict="NEUTRAL",
        llm_final_score=0.55, learned_weights_used=True,
        shadow_log=str(log),
    )
    assert rec["threshold_verdict"] == "BUY"
    assert rec["diverged"] is True
    on_disk = json.loads(log.read_text(encoding="utf-8").splitlines()[-1])
    assert on_disk["ticker"] == "MARUTI"
    assert on_disk["composite"] == 0.62
    assert on_disk["learned_weights_used"] is True
    assert on_disk["ts"]


def test_log_verdict_shadow_agreement_not_diverged(tmp_path):
    log = tmp_path / "shadow.jsonl"
    rec = vs.log_verdict_shadow(
        ticker="TCS", composite=0.50, llm_verdict="neutral",
        llm_final_score=0.5, learned_weights_used=False,
        shadow_log=str(log),
    )
    assert rec["diverged"] is False        # case-insensitive comparison


def test_log_verdict_shadow_never_raises(tmp_path):
    # a directory as the log path forces the write to fail
    rec = vs.log_verdict_shadow(
        ticker="X", composite=0.5, llm_verdict="NEUTRAL",
        llm_final_score=0.5, learned_weights_used=False,
        shadow_log=str(tmp_path),
    )
    assert rec is None


def test_aggregator_calls_shadow_logger():
    import inspect
    from backend.shared.pipeline.signal_aggregator import SignalAggregator
    assert "log_verdict_shadow" in inspect.getsource(SignalAggregator.run)


def test_log_verdict_shadow_records_sector(tmp_path):
    log = tmp_path / "shadow.jsonl"
    rec = vs.log_verdict_shadow(
        ticker="MARUTI", composite=0.62, llm_verdict="BUY",
        llm_final_score=0.6, learned_weights_used=True,
        sector="automobile", shadow_log=str(log),
    )
    assert rec["sector"] == "automobile"
    on_disk = json.loads(log.read_text(encoding="utf-8").splitlines()[-1])
    assert on_disk["sector"] == "automobile"


def test_log_verdict_shadow_sector_defaults_empty(tmp_path):
    log = tmp_path / "shadow.jsonl"
    rec = vs.log_verdict_shadow(
        ticker="TCS", composite=0.5, llm_verdict="NEUTRAL",
        llm_final_score=0.5, learned_weights_used=False,
        shadow_log=str(log),
    )
    assert rec["sector"] == ""

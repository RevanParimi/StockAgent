"""AUD-087: run summaries report real summed usage, not hardcoded zeros."""
from types import SimpleNamespace

from backend.shared.pipeline.base_orchestrator import sum_run_usage
from backend.shared.schemas.pipeline import AgentOutput


def _out(agent, pt, ct, cost):
    o = AgentOutput(agent=agent, ticker="MARUTI", overall_score=0.5)
    o.prompt_tokens = pt
    o.completion_tokens = ct
    o.cost_usd = cost
    return o


def test_sums_agents_resolve_and_aggregator():
    outputs = {"a": _out("a", 100, 50, 0.001), "b": _out("b", 200, 70, 0.002)}
    agg = SimpleNamespace(_last_prompt_tokens=30, _last_completion_tokens=10)
    pt, ct, cost = sum_run_usage(outputs, (5, 2), agg)
    assert pt == 335 and ct == 132
    assert cost > 0.003  # agent costs + priced resolve/aggregator tokens


def test_defaults_are_zero_and_excluded_from_reports():
    o = AgentOutput(agent="a", ticker="T", overall_score=0.5)
    assert o.prompt_tokens == 0 and o.completion_tokens == 0 and o.cost_usd == 0.0
    dumped = o.model_dump()
    assert "prompt_tokens" not in dumped and "cost_usd" not in dumped


def test_aggregator_without_usage_attrs_is_safe():
    pt, ct, cost = sum_run_usage({}, (0, 0), object())
    assert (pt, ct, cost) == (0, 0, 0.0)

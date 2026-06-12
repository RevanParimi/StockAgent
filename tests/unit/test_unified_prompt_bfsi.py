"""Tests for the banking_bfsi Unified Sector Analyst prompt module (sector rollout, 2026-06-13)."""

from backend.sectors.banking_bfsi.prompts import unified


DIMENSIONS = [
    "fundamentals", "risk", "macro_policy", "institutional",
    "pattern_analysis", "universe_setup",
]


def test_prompt_contains_all_six_dimensions():
    for dim in DIMENSIONS:
        assert dim in unified.ANALYSIS_PROMPT


def test_prompt_lists_subscore_names():
    # One sub_score name per dimension model (spot-check >= 5)
    for sub in [
        "asset_quality",       # fundamentals
        "concentration_risk",  # risk
        "rbi_rate_cycle",       # macro_policy
        "fii_dii_flow",         # institutional
        "breakout_zones",       # pattern_analysis
        "index_weight",         # universe_setup
    ]:
        assert sub in unified.ANALYSIS_PROMPT, f"missing sub-score field: {sub}"


def test_prompt_lists_all_subscores_for_all_dimensions():
    all_sub_scores = [
        # fundamentals
        "asset_quality", "net_interest", "capital_adequacy", "profitability", "loan_mix",
        # risk
        "asset_quality_trend", "concentration_risk", "deposit_stability",
        "regulatory_risk", "cyber_fraud_risk",
        # macro_policy
        "rbi_rate_cycle", "system_credit", "liquidity_conditions",
        "regulatory_actions", "fiscal_policy",
        # institutional
        "fii_dii_flow", "promoter_holding", "insider_trades",
        "amfi_mf_flow", "bulk_block_deals",
        # pattern_analysis
        "price_cycle", "momentum", "breakout_zones",
        "relative_strength", "volume_pattern",
        # universe_setup
        "index_weight", "peer_positioning", "market_cap_tier",
        "corporate_actions", "rebalancing_risk",
    ]
    for sub in all_sub_scores:
        assert sub in unified.ANALYSIS_PROMPT, f"missing sub-score field: {sub}"


def test_prompt_has_format_slots():
    assert "{ticker}" in unified.ANALYSIS_PROMPT
    assert "{company_name}" in unified.ANALYSIS_PROMPT
    assert "{bundle}" in unified.ANALYSIS_PROMPT
    assert "{report_date}" in unified.ANALYSIS_PROMPT


def test_prompt_formats_without_error():
    formatted = unified.ANALYSIS_PROMPT.format(
        ticker="X", company_name="Y", report_date="Z", bundle="B"
    )
    assert "X" in formatted
    assert "Y" in formatted
    assert "Z" in formatted
    assert "B" in formatted


def test_system_prompt_has_grounding_rules():
    assert "JSON" in unified.SYSTEM_PROMPT
    assert "training" in unified.SYSTEM_PROMPT.lower() or "fabricat" in unified.SYSTEM_PROMPT.lower()


def test_prompt_has_output_shape_keys():
    for key in ["score", "confidence", "summary", "key_positives", "key_risks",
                 "sub_scores", "ticker_vs_peers", "bull_case_if", "bear_case_if",
                 "what_changed"]:
        assert f'"{key}"' in unified.ANALYSIS_PROMPT


def test_no_valuation_extras():
    # banking_bfsi has no valuation extras per the rollout spec.
    for field in ["price_target", "recovery_timeline_quarters", "discount_reason",
                   "recovery_catalysts", "fair_value_estimate", "current_discount_pct"]:
        assert field not in unified.ANALYSIS_PROMPT

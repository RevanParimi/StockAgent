"""Tests for the it_sector Unified Sector Analyst prompt module (sector rollout, 2026-06-13)."""

from backend.sectors.it_sector.prompts import unified


DIMENSIONS = [
    "fundamentals", "global_macro", "risk_macro", "peer_benchmark",
    "pattern_analysis", "sentiment", "transcript_nlp", "insider_smart_money",
]


def test_prompt_contains_all_eight_dimensions():
    for dim in DIMENSIONS:
        assert dim in unified.ANALYSIS_PROMPT


def test_prompt_lists_subscore_names():
    # One sub_score name per dimension model (spot-check >= 5)
    for sub in [
        "revenue_growth",       # fundamentals
        "us_tech_spend",         # global_macro
        "visa_risk",             # risk_macro
        "valuation_gap",         # peer_benchmark
        "nifty_it_beta",         # pattern_analysis
        "ai_narrative",          # sentiment
        "guidance_delta",        # transcript_nlp
        "promoter_activity",     # insider_smart_money
    ]:
        assert sub in unified.ANALYSIS_PROMPT, f"missing sub-score field: {sub}"


def test_prompt_lists_all_subscores_for_all_dimensions():
    all_sub_scores = [
        # fundamentals
        "revenue_growth", "ebit_margins", "deal_wins", "attrition", "valuation",
        # global_macro
        "us_tech_spend", "fed_rate_impact", "usd_inr", "geopolitical", "ma_activity",
        # risk_macro
        "visa_risk", "ai_disruption", "client_concentration", "fx_hedge", "talent_risk",
        # peer_benchmark
        "revenue_growth_rank", "margin_rank", "deal_momentum_rank",
        "attrition_rank", "valuation_gap",
        # pattern_analysis
        "price_cycle", "momentum", "breakout_levels", "nifty_it_beta", "volume_quality",
        # sentiment
        "ai_narrative", "layoff_signals", "management_tone", "sector_narrative", "news_volume",
        # transcript_nlp
        "guidance_delta", "vertical_mix", "geography_colour", "ai_deal_count", "analyst_pushback",
        # insider_smart_money
        "promoter_activity", "director_trades", "amfi_mf_flow", "fii_futures", "block_deals",
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


def test_transcript_nlp_grounds_in_policy_deep_dive():
    # The bundle's policy_deep_dive section carries earnings-call transcript
    # content for IT — the transcript_nlp dimension must reference it.
    assert "policy_deep_dive" in unified.ANALYSIS_PROMPT


def test_no_valuation_extras():
    for field in ["price_target", "recovery_timeline_quarters", "discount_reason",
                   "recovery_catalysts", "fair_value_estimate", "current_discount_pct"]:
        assert field not in unified.ANALYSIS_PROMPT

"""Tests for the automobile Unified Sector Analyst prompt module (Task 3, 2026-06-12)."""

from backend.sectors.automobile.prompts import unified


def test_prompt_contains_all_nine_dimensions():
    for dim in ["sales_demand", "raw_materials", "fundamentals", "pattern_analysis",
                "sentiment", "policy_regulatory", "competitive_intel", "risk_macro",
                "valuation_catalyst"]:
        assert dim in unified.ANALYSIS_PROMPT


def test_prompt_lists_subscore_names():
    for sub in ["fada_siam_dispatch", "rsi_macd_bb", "pe_discount_vs_peers",
                "fame_ev_subsidy", "ev_market_share"]:
        assert sub in unified.ANALYSIS_PROMPT


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
    # Data-only / no-fabrication rule
    assert "training" in unified.SYSTEM_PROMPT.lower() or "fabricat" in unified.SYSTEM_PROMPT.lower()


def test_prompt_lists_all_subscores_for_all_dimensions():
    all_sub_scores = [
        # sales_demand
        "fada_siam_dispatch", "ev_segment_vahan", "dealer_inventory", "export_import",
        "used_car_price_index",
        # raw_materials
        "steel_aluminium", "platinum_palladium", "crude_oil_polymer", "power_tariff",
        "commodities_trend",
        # fundamentals
        "revenue_ebitda_delta", "margin_vs_peers", "order_book_pipeline",
        "attrition_headcount", "promoter_fii_dii_flow",
        # pattern_analysis
        "price_cycle_position", "seasonal_pattern", "rsi_macd_bb",
        "breakout_support_zone", "peer_correlation",
        # sentiment
        "news_nlp", "management_tone", "twitter_reddit_sentiment",
        "youtube_view_spikes", "dealer_consumer_feedback",
        # policy_regulatory
        "fame_ev_subsidy", "emission_norms", "union_budget_duties",
        "pli_scheme", "state_ev_incentives",
        # competitive_intel
        "ev_market_share", "new_model_pipeline", "jv_acquisitions",
        "adas_safety_ratings", "competitive_position",
        # risk_macro
        "inr_usd_crude_exposure", "commodity_prices", "rbi_repo_emi_impact",
        "emission_policy_risk", "global_geopolitical_risk",
        # valuation_catalyst (exact pydantic sub-score field names)
        "pe_discount_vs_peers", "technical_trend", "mean_reversion_potential",
        "support_zone_strength", "recovery_signal_confidence",
    ]
    for sub in all_sub_scores:
        assert sub in unified.ANALYSIS_PROMPT, f"missing sub-score field: {sub}"


def test_prompt_has_valuation_catalyst_extra_fields():
    for field in ["price_target", "recovery_timeline_quarters", "discount_reason",
                   "recovery_catalysts", "fair_value_estimate", "current_discount_pct"]:
        assert field in unified.ANALYSIS_PROMPT


def test_prompt_has_output_shape_keys():
    for key in ["score", "confidence", "summary", "key_positives", "key_risks",
                 "sub_scores", "ticker_vs_peers", "bull_case_if", "bear_case_if",
                 "what_changed"]:
        assert f'"{key}"' in unified.ANALYSIS_PROMPT

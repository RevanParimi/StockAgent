"""Tests for the renewable_energy Unified Sector Analyst prompt module (sector rollout, 2026-06-13)."""

from backend.sectors.renewable_energy.prompts import unified


DIMENSIONS = [
    "fundamentals", "business", "valuation", "sentiment_policy", "technical", "risk",
]


def test_prompt_contains_all_six_dimensions():
    for dim in DIMENSIONS:
        assert dim in unified.ANALYSIS_PROMPT


def test_prompt_lists_subscore_names():
    # One sub_score name per dimension model (spot-check >= 5)
    for sub in [
        "capacity_utilisation",  # fundamentals
        "ppa_quality",            # business
        "ev_per_mw",              # valuation
        "mnre_auction_health",    # sentiment_policy
        "moving_averages",        # technical
        "discom_credit",          # risk
    ]:
        assert sub in unified.ANALYSIS_PROMPT, f"missing sub-score field: {sub}"


def test_prompt_lists_all_subscores_for_all_dimensions():
    all_sub_scores = [
        # fundamentals
        "capacity_utilisation", "ebitda_quality", "debt_serviceability", "receivables", "leverage",
        # business
        "subsector_mix", "ppa_quality", "pipeline_cred", "customer_divers", "geography_spread",
        # valuation
        "ev_per_mw", "ev_ebitda", "tariff_vs_auction", "pipeline_dcf", "implied_irr",
        # sentiment_policy
        "mnre_auction_health", "budget_allocation", "policy_tailwinds",
        "rbi_rate_impact", "module_price",
        # technical
        "moving_averages", "rsi_signal", "macd_weekly", "volume_catalyst", "accumulation_zone",
        # risk
        "discom_credit", "curtailment_risk", "ppa_protection", "execution_risk", "promoter_pledge",
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


def test_sentiment_policy_grounds_in_policy_deep_dive():
    # The bundle's policy_deep_dive section carries MNRE auction/policy content.
    assert "policy_deep_dive" in unified.ANALYSIS_PROMPT


def test_commodities_not_applicable_handled():
    # commodities section reads "not_applicable" for RE; module-price signal
    # should come from news sections instead.
    assert "not_applicable" in unified.ANALYSIS_PROMPT or "commodities" in unified.ANALYSIS_PROMPT


def test_no_valuation_extras():
    # renewable_energy's "valuation" dimension is scores+summary only, same
    # shape as other dimensions -- no price_target etc.
    for field in ["price_target", "recovery_timeline_quarters", "discount_reason",
                   "recovery_catalysts", "fair_value_estimate", "current_discount_pct"]:
        assert field not in unified.ANALYSIS_PROMPT

"""
eval/gen_test_data.py
=====================
Generates realistic synthetic prediction data so the evaluator has
something to measure before real pipeline runs have accumulated.

Creates under data/predictions/{sector}/{TICKER}/:
  {TICKER}_{YYYY-MM}_prediction_envelope.json
  {TICKER}_{YYYY-MM}_daily_feedback_log.json
  {TICKER}_agent_weight_memory.json

Usage
-----
  python eval/gen_test_data.py                       # all sectors, 30 days
  python eval/gen_test_data.py --seed 42             # reproducible
  python eval/gen_test_data.py --days 60             # more history
  python eval/gen_test_data.py --sector automobile   # one sector only
  python eval/gen_test_data.py --tickers MARUTI,TCS  # specific tickers
"""
from __future__ import annotations

import argparse
import json
import math
import os
import random
import sys
from datetime import date, timedelta
from pathlib import Path

# ─────────────────────────────────────────────────────────────────────────────
# Sector catalogue  (mirrors settings.py files exactly)
# ─────────────────────────────────────────────────────────────────────────────

SECTORS: dict[str, dict] = {
    "automobile": {
        "agents": {
            "sales_demand": 0.15, "raw_materials": 0.09, "fundamentals": 0.18,
            "pattern_analysis": 0.11, "sentiment": 0.04, "policy_regulatory": 0.09,
            "competitive_intel": 0.09, "risk_macro": 0.13, "valuation_catalyst": 0.12,
        },
        "tickers": {
            "MARUTI": 12500, "TATAMOTORS": 700, "M&M": 2900,
            "HEROMOTOCO": 4200, "BAJAJ-AUTO": 8500, "EICHERMOT": 4800,
        },
        "sub_scores": {
            "sales_demand":       ["fada_siam_dispatch","ev_segment_vahan","dealer_inventory","export_import","used_car_price_index","waiting_period_booking"],
            "raw_materials":      ["steel_aluminium","platinum_palladium","crude_oil_polymer","power_tariff","commodities_trend","pricing_power_passthrough"],
            "fundamentals":       ["revenue_ebitda_delta","margin_vs_peers","order_book_pipeline","attrition_headcount","promoter_fii_dii_flow","cash_flow_balance_sheet"],
            "pattern_analysis":   ["multi_timeframe_trend","seasonal_pattern","rsi_macd_bb","breakout_support_zone","peer_correlation","volume_confirmation"],
            "sentiment":          ["news_nlp","management_tone","twitter_reddit_sentiment","youtube_view_spikes","dealer_consumer_feedback","institutional_sentiment"],
            "policy_regulatory":  ["fame_ev_subsidy","emission_norms","union_budget_duties","pli_scheme","state_ev_incentives","localisation_readiness"],
            "competitive_intel":  ["ev_market_share","new_model_pipeline","jv_acquisitions","adas_safety_ratings","competitive_position","future_readiness"],
            "risk_macro":         ["inr_usd_crude_exposure","commodity_prices","rbi_repo_emi_impact","emission_policy_risk","global_geopolitical_risk","consumer_demand_sensitivity"],
            "valuation_catalyst": ["pe_discount_vs_peers","risk_adjusted_return_potential","mean_reversion_potential","catalyst_timing","recovery_signal_confidence","sector_rotation_momentum","valuation_trap_risk"],
        },
    },
    "banking_bfsi": {
        "agents": {
            "fundamentals": 0.25, "risk": 0.20, "macro_policy": 0.20,
            "institutional": 0.15, "pattern_analysis": 0.15, "universe_setup": 0.05,
        },
        "tickers": {
            "HDFCBANK": 1800, "ICICIBANK": 1300, "SBIN": 800,
            "KOTAKBANK": 1950, "AXISBANK": 1150, "INDUSINDBK": 950,
        },
        "sub_scores": {
            "fundamentals":    ["asset_quality","net_interest","capital_adequacy","profitability","loan_mix"],
            "risk":            ["asset_quality_trend","concentration_risk","deposit_stability","regulatory_risk","cyber_fraud_risk"],
            "macro_policy":    ["rbi_rate_cycle","system_credit","liquidity_conditions","regulatory_actions","fiscal_policy"],
            "institutional":   ["fii_dii_flow","promoter_holding","insider_trades","amfi_mf_flow","bulk_block_deals"],
            "pattern_analysis":["price_cycle","momentum","breakout_zones","relative_strength","volume_pattern"],
            "universe_setup":  ["index_weight","peer_positioning","market_cap_tier","corporate_actions","rebalancing_risk"],
        },
    },
    "it_sector": {
        "agents": {
            "fundamentals": 0.25, "global_macro": 0.20, "risk_macro": 0.15,
            "peer_benchmark": 0.15, "pattern_analysis": 0.10, "sentiment": 0.08,
            "transcript_nlp": 0.04, "insider_smart_money": 0.03,
        },
        "tickers": {
            "TCS": 3800, "INFY": 1800, "WIPRO": 280,
            "HCLTECH": 1650, "TECHM": 1400, "LTIM": 5200,
        },
        "sub_scores": {
            "fundamentals":       ["revenue_growth","ebit_margins","deal_wins","attrition","valuation"],
            "global_macro":       ["us_tech_spend","fed_rate_impact","usd_inr","geopolitical","ma_activity"],
            "risk_macro":         ["visa_risk","ai_disruption","client_concentration","fx_hedge","talent_risk"],
            "peer_benchmark":     ["revenue_growth_rank","margin_rank","deal_momentum_rank","attrition_rank","valuation_gap"],
            "pattern_analysis":   ["price_cycle","momentum","breakout_levels","nifty_it_beta","volume_quality"],
            "sentiment":          ["ai_narrative","layoff_signals","management_tone","sector_narrative","news_volume"],
            "transcript_nlp":     ["guidance_delta","vertical_mix","geography_colour","ai_deal_count","analyst_pushback"],
            "insider_smart_money":["promoter_activity","director_trades","amfi_mf_flow","fii_futures","block_deals"],
        },
    },
    "renewable_energy": {
        "agents": {
            "fundamentals": 0.30, "business": 0.25, "valuation": 0.20,
            "sentiment_policy": 0.15, "technical": 0.10, "risk": 0.00,
        },
        "tickers": {
            "ADANIGREEN": 1800, "TATAPOWER": 430, "TORNTPOWER": 1600,
            "CESC": 180, "SJVN": 115, "NHPC": 90,
        },
        "sub_scores": {
            "fundamentals":    ["capacity_utilisation","ebitda_quality","debt_serviceability","receivables","leverage"],
            "business":        ["subsector_mix","ppa_quality","pipeline_cred","customer_divers","geography_spread"],
            "valuation":       ["ev_per_mw","ev_ebitda","tariff_vs_auction","pipeline_dcf","implied_irr"],
            "sentiment_policy":["mnre_auction_health","budget_allocation","policy_tailwinds","rbi_rate_impact","module_price"],
            "technical":       ["moving_averages","rsi_signal","macd_weekly","volume_catalyst","accumulation_zone"],
            "risk":            ["discom_credit","curtailment_risk","ppa_protection","execution_risk","promoter_pledge"],
        },
    },
}

VERDICTS        = ["STRONG BUY", "BUY", "NEUTRAL", "SELL", "STRONG SELL"]
VERDICT_WEIGHTS = [0.12,         0.38, 0.25,      0.18,   0.07]
MISS_TYPES      = ["model_bias", "direction_flip", "timing", "magnitude", "data_gap", "external_shock"]
MISS_WEIGHTS    = [0.30,         0.30,              0.20,     0.10,        0.05,        0.05]
REGIMES         = ["NORMAL", "NORMAL", "NORMAL", "NORMAL", "RISK_OFF", "RISK_ON", "MACRO_CRISIS"]


def _clamp(v: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, v))


def _rng_score(rng: random.Random, center: float, spread: float = 0.12) -> float:
    return round(_clamp(rng.gauss(center, spread)), 4)


def _verdict_direction(verdict: str) -> str:
    """Expected actual direction for a correct prediction."""
    if verdict in ("STRONG BUY", "BUY"):
        return "UP"
    if verdict in ("STRONG SELL", "SELL"):
        return "DOWN"
    return "FLAT"


def _actual_direction(verdict: str, is_correct: bool, rng: random.Random) -> str:
    if is_correct:
        return _verdict_direction(verdict)
    wrong_pool = [d for d in ("UP", "DOWN", "FLAT") if d != _verdict_direction(verdict)]
    return rng.choice(wrong_pool)


def _agent_score_center(verdict: str) -> float:
    """Mean agent score associated with a given verdict."""
    return {"STRONG BUY": 0.78, "BUY": 0.65, "NEUTRAL": 0.50, "SELL": 0.38, "STRONG SELL": 0.24}.get(verdict, 0.50)


# ─────────────────────────────────────────────────────────────────────────────
# Core generators
# ─────────────────────────────────────────────────────────────────────────────

def _gen_day(
    rng: random.Random,
    day_idx: int,
    ref_date: date,
    base_close: float,
    sector: str,
    ticker: str,
    agents: dict[str, float],
    sub_scores_map: dict[str, list[str]],
    hit_rate: float,
) -> tuple[dict, dict]:
    """Return (DailyForecast dict, FeedbackEntry dict) for one trading day."""
    target_date = ref_date + timedelta(days=day_idx)
    # Skip weekends naively (keep it simple — real data has them too sometimes)

    # Pick verdict
    verdict = rng.choices(VERDICTS, weights=VERDICT_WEIGHTS, k=1)[0]
    # Decide correctness
    is_correct = rng.random() < hit_rate

    actual_dir = _actual_direction(verdict, is_correct, rng)

    # Agent scores — all agents score consistently with the verdict
    score_center = _agent_score_center(verdict)
    agent_scores: dict[str, float] = {}
    agent_sub_scores: dict[str, dict[str, float]] = {}

    for agent in agents:
        agent_score = _rng_score(rng, score_center, spread=0.10)
        agent_scores[agent] = agent_score
        # Sub-scores cluster around the agent score
        dims = sub_scores_map.get(agent, [])
        agent_sub_scores[agent] = {
            dim: _rng_score(rng, agent_score, spread=0.08) for dim in dims
        }

    # Final composite score
    total_w = sum(agents.values())
    final_score = round(sum(agent_scores[a] * w for a, w in agents.items()) / total_w, 4) if total_w else 0.5

    # Predicted close  (small random walk from base)
    daily_drift = rng.gauss(0.001, 0.015)  # ~1.5% daily vol
    predicted_close = round(base_close * (1 + daily_drift * (day_idx + 1) * 0.3), 2)
    actual_pct_delta = rng.gauss(0.0, 0.018) if actual_dir == "FLAT" else (
        abs(rng.gauss(0.015, 0.012)) if actual_dir == "UP" else -abs(rng.gauss(0.015, 0.012))
    )
    actual_close = round(predicted_close * (1 + actual_pct_delta), 2)
    price_error = round((actual_close - predicted_close) / predicted_close * 100, 4)

    regime = rng.choices(REGIMES, k=1)[0]

    # Forecast row
    forecast = {
        "day": day_idx + 1,
        "date": target_date.isoformat(),
        "predicted_close": predicted_close,
        "predicted_change_pct": round(daily_drift * 100, 4),
        "predicted_verdict": verdict,
        "predicted_agent_scores": agent_scores,
        "predicted_agent_subscores": agent_sub_scores,
        "confidence": round(_clamp(rng.gauss(0.62, 0.10)), 4),
        "key_assumptions": [
            rng.choice(["RBI holds repo rate", "crude below $90", "USD/INR stable",
                        "sector demand resilient", "no major earnings miss",
                        "FII flows positive", "monsoon normal"]),
        ],
        "revised": False,
        "revision_count": 0,
    }

    # Miss analysis (only populated when wrong)
    miss_analysis = None
    if not is_correct:
        primary_miss = rng.choices(list(agents.keys()), k=1)[0]
        miss_type = rng.choices(MISS_TYPES, weights=MISS_WEIGHTS, k=1)[0]
        drift = {a: round(rng.gauss(0, 0.08), 4) for a in rng.sample(list(agents.keys()), k=min(3, len(agents)))}
        miss_analysis = {
            "primary_miss_agent": primary_miss,
            "miss_type": miss_type,
            "missed_factors": [rng.choice(["crude spike", "RBI surprise", "FII outflow", "earnings miss", "INR depreciation", "global selloff"])],
            "over_weighted_factors": [rng.choice(["domestic demand", "order book", "EV growth", "margin resilience"])],
            "agent_score_drift": drift,
            "predicted_subscores_significant": {},
            "actual_subscores_significant": {},
        }

    feedback = {
        "day": day_idx + 1,
        "date": target_date.isoformat(),
        "predicted_close": predicted_close,
        "actual_close": actual_close,
        "price_error_pct": price_error,
        "predicted_verdict": verdict,
        "actual_direction": actual_dir,
        "direction_correct": is_correct,
        "regime_label": regime,
        "volume_vs_20d_avg": round(rng.lognormvariate(0, 0.4), 3),
        "miss_analysis": miss_analysis,
        "timing": None,
        "revised_context": None,
        "thesis_review": None,
        "lessons_generated": [],
        "weight_adjustment_applied": f"v{rng.randint(1,5)}" if not is_correct else "",
    }

    return forecast, feedback


def _gen_weight_memory(
    rng: random.Random,
    ticker: str,
    sector: str,
    agents: dict[str, float],
    entries: list[dict],
    today: date,
) -> dict:
    """Build a WeightMemory JSON from scratch using the feedback entries."""
    # Per-agent accuracy from entries
    agent_acc: dict[str, dict] = {}
    for agent in agents:
        hits = sum(1 for e in entries if e["direction_correct"])
        total = len(entries)
        # Each agent has slightly different accuracy
        agent_hits = max(0, min(total, int(hits + rng.randint(-3, 3))))
        agent_acc[agent] = {
            "direction_hits": agent_hits,
            "total": total,
            "avg_error": round(abs(rng.gauss(0, 0.05)), 4),
            "monthly_snapshot_history": [
                {
                    "month": (today - timedelta(days=30)).strftime("%Y-%m"),
                    "hit_rate": round(_clamp(rng.gauss(0.61, 0.05)), 4),
                    "total": max(1, total // 2),
                    "dominant_regime": "NORMAL",
                }
            ],
        }

    # RL-drifted weights: ±0.01-0.04 from base
    current_weights = {}
    for agent, base_w in agents.items():
        drift = rng.uniform(-0.04, 0.04)
        current_weights[agent] = round(_clamp(base_w + drift, 0.01, 0.35), 4)
    # Re-normalise to sum = 1.0 (roughly)
    total_cw = sum(current_weights.values())
    if total_cw > 0:
        current_weights = {a: round(v / total_cw, 4) for a, v in current_weights.items()}

    # Regime accuracy
    regime_accuracy = {}
    for regime in ["NORMAL", "RISK_OFF", "MACRO_CRISIS"]:
        regime_accuracy[regime] = {}
        for agent in agents:
            base_hr = 0.64 if regime == "NORMAL" else (0.54 if regime == "RISK_OFF" else 0.42)
            h = max(0, int(rng.gauss(base_hr * 20, 2)))
            t = 20
            regime_accuracy[regime][agent] = {
                "direction_hits": min(h, t),
                "total": t,
                "avg_error": round(abs(rng.gauss(0, 0.04)), 4),
                "monthly_snapshot_history": [],
            }

    return {
        "ticker": ticker,
        "sector": sector,
        "last_updated": today.isoformat(),
        "weight_version": rng.randint(3, 8),
        "current_weights": current_weights,
        "base_weights": dict(agents),
        "adjustment_bounds": {"max_single_step": 0.05, "max_total_drift_from_base": 0.15},
        "agent_accuracy": agent_acc,
        "weight_history": [
            {
                "version": 1,
                "date": (today - timedelta(days=45)).isoformat(),
                "weights": dict(agents),
                "reason": "Initial base weights loaded.",
                "deltas": {},
                "accuracy_snapshot": {},
                "regime_at_update": "NORMAL",
            }
        ],
        "regime_accuracy": regime_accuracy,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Top-level generation
# ─────────────────────────────────────────────────────────────────────────────

def generate(
    sector: str,
    ticker: str,
    base_close: float,
    days: int,
    hit_rate: float,
    rng: random.Random,
    out_dir: Path,
    today: date,
) -> None:
    cfg        = SECTORS[sector]
    agents     = cfg["agents"]
    sub_map    = cfg["sub_scores"]
    ym         = today.strftime("%Y-%m")
    cycle_id   = f"{ticker}_{ym}"
    start_date = today - timedelta(days=days - 1)

    forecasts: list[dict] = []
    feedback_entries: list[dict] = []

    for i in range(days):
        fc, fb = _gen_day(rng, i, start_date, base_close, sector, ticker, agents, sub_map, hit_rate)
        forecasts.append(fc)
        feedback_entries.append(fb)

    envelope = {
        "ticker": ticker,
        "sector": sector,
        "cycle_id": cycle_id,
        "generated_at": today.isoformat() + "T09:15:00",
        "base_close": base_close,
        "weight_version_used": 1,
        "forecast_profile_shape": "linear",
        "forecast_profile_monthly_pct": round(rng.gauss(2.0, 3.0), 2),
        "forecast_profile_source": "static",
        "daily_forecasts": forecasts,
        "conviction_streak": {
            "current_verdict": forecasts[-1]["predicted_verdict"] if forecasts else "NEUTRAL",
            "streak_days": rng.randint(1, 5),
            "streak_start_date": (today - timedelta(days=rng.randint(1, 5))).isoformat(),
            "max_streak_seen": rng.randint(5, 12),
            "reversion_prior": round(rng.uniform(0, 0.15), 4),
        },
    }

    feedback_log = {
        "ticker": ticker,
        "sector": sector,
        "cycle_id": cycle_id,
        "entries": feedback_entries,
    }

    wm = _gen_weight_memory(rng, ticker, sector, agents, feedback_entries, today)

    ticker_dir = out_dir / sector / ticker
    ticker_dir.mkdir(parents=True, exist_ok=True)

    def _save(obj: dict, name: str) -> None:
        path = ticker_dir / name
        with open(path, "w", encoding="utf-8") as f:
            json.dump(obj, f, indent=2, ensure_ascii=False)

    _save(envelope,     f"{ticker}_{ym}_prediction_envelope.json")
    _save(feedback_log, f"{ticker}_{ym}_daily_feedback_log.json")
    _save(wm,           f"{ticker}_agent_weight_memory.json")


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate synthetic prediction data for the StockAgent evaluator",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python eval/gen_test_data.py
  python eval/gen_test_data.py --seed 42
  python eval/gen_test_data.py --days 60
  python eval/gen_test_data.py --sector automobile
  python eval/gen_test_data.py --tickers MARUTI,TCS
""",
    )
    parser.add_argument("--seed",     type=int,   default=None, help="Random seed for reproducibility")
    parser.add_argument("--days",     type=int,   default=30,   help="Trading days to generate per ticker (default 30)")
    parser.add_argument("--hit-rate", type=float, default=0.62, help="Overall direction hit rate (default 0.62)")
    parser.add_argument("--sector",   default=None, help="Generate for one sector only")
    parser.add_argument("--tickers",  default=None, help="Comma-separated ticker list (overrides sector defaults)")
    args = parser.parse_args()

    rng     = random.Random(args.seed)
    today   = date.today()
    root    = Path(__file__).parent.parent
    out_dir = root / "data" / "predictions"

    sectors_to_run = [args.sector] if args.sector else list(SECTORS.keys())
    for s in sectors_to_run:
        if s not in SECTORS:
            print(f"Unknown sector: {s}  (valid: {', '.join(SECTORS)})")
            sys.exit(1)

    ticker_filter = set(t.strip().upper() for t in args.tickers.split(",")) if args.tickers else None

    total_files = 0
    for sector in sectors_to_run:
        tickers = SECTORS[sector]["tickers"]
        for ticker, base_close in tickers.items():
            if ticker_filter and ticker not in ticker_filter:
                continue
            # Vary hit rate slightly per ticker (+/- 5pp) for realism
            ticker_hit = _clamp(args.hit_rate + rng.uniform(-0.05, 0.05))
            generate(sector, ticker, base_close, args.days, ticker_hit, rng, out_dir, today)
            total_files += 3
            print(f"  [{sector}] {ticker:<15}  {args.days} days  hit_rate={ticker_hit:.0%}")

    print(f"\nDone. {total_files} files written under data/predictions/")
    print("Run:  python eval/evaluate.py")


if __name__ == "__main__":
    main()

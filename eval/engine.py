"""
eval/engine.py
==============
Data collection and metric computation for the evaluation framework.

Data sources (in priority order):
  1. data/predictions/{sector}/{TICKER}/*_daily_feedback_log.json
     → direction accuracy, miss analysis, verdict accuracy
  2. data/predictions/{sector}/{TICKER}/*_agent_weight_memory.json
     → per-agent hit rates, weight drift, regime breakdown
  3. data/predictions/{sector}/{TICKER}/*_prediction_envelope.json
     → predicted_agent_subscores for sub-score calibration
  4. outputs/**/*.json
     → FinalReport JSON files (score distributions, conflict rates)
"""
from __future__ import annotations

import json
import math
import os
import re
from pathlib import Path
from typing import Any

from eval.schemas import (
    AgentEvalResult,
    EvalReport,
    OverallSummary,
    ScoreCalibrationBucket,
    SectorEvalResult,
    SubScoreAccuracy,
    TickerStats,
    VerdictAccuracy,
)

# ─────────────────────────────────────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────────────────────────────────────

SECTORS = ["automobile", "banking_bfsi", "it_sector", "renewable_energy"]

# Base weights per sector (matches settings.py files)
BASE_WEIGHTS: dict[str, dict[str, float]] = {
    "automobile": {
        "sales_demand": 0.15,
        "raw_materials": 0.09,
        "fundamentals": 0.18,
        "pattern_analysis": 0.11,
        "sentiment": 0.04,
        "policy_regulatory": 0.09,
        "competitive_intel": 0.09,
        "risk_macro": 0.13,
        "valuation_catalyst": 0.12,
    },
    "banking_bfsi": {
        "fundamentals": 0.25,
        "risk": 0.20,
        "macro_policy": 0.20,
        "institutional": 0.15,
        "pattern_analysis": 0.15,
        "universe_setup": 0.05,
    },
    "it_sector": {
        "fundamentals": 0.25,
        "global_macro": 0.20,
        "risk_macro": 0.15,
        "peer_benchmark": 0.15,
        "pattern_analysis": 0.10,
        "sentiment": 0.08,
        "transcript_nlp": 0.04,
        "insider_smart_money": 0.03,
    },
    "renewable_energy": {
        "fundamentals": 0.30,
        "business": 0.25,
        "valuation": 0.20,
        "sentiment_policy": 0.15,
        "technical": 0.10,
        "risk": 0.00,
    },
}

# Sub-score dimensions per agent (used for labelling when no data is found)
AGENT_SUB_SCORES: dict[str, list[str]] = {
    # automobile
    "sales_demand":        ["fada_siam_dispatch", "ev_segment_vahan", "dealer_inventory", "export_import", "used_car_price_index", "waiting_period_booking"],
    "fundamentals":        ["revenue_ebitda_delta", "margin_vs_peers", "order_book_pipeline", "attrition_headcount", "promoter_fii_dii_flow", "cash_flow_balance_sheet"],
    "pattern_analysis":    ["multi_timeframe_trend", "seasonal_pattern", "rsi_macd_bb", "breakout_support_zone", "peer_correlation", "volume_confirmation"],
    "sentiment":           ["news_nlp", "management_tone", "twitter_reddit_sentiment", "youtube_view_spikes", "dealer_consumer_feedback", "institutional_sentiment"],
    "risk_macro":          ["inr_usd_crude_exposure", "commodity_prices", "rbi_repo_emi_impact", "emission_policy_risk", "global_geopolitical_risk", "consumer_demand_sensitivity"],
    "raw_materials":       ["steel_aluminium", "platinum_palladium", "crude_oil_polymer", "power_tariff", "commodities_trend", "pricing_power_passthrough"],
    "policy_regulatory":   ["fame_ev_subsidy", "emission_norms", "union_budget_duties", "pli_scheme", "state_ev_incentives", "localisation_readiness"],
    "competitive_intel":   ["ev_market_share", "new_model_pipeline", "jv_acquisitions", "adas_safety_ratings", "competitive_position", "future_readiness"],
    "valuation_catalyst":  ["pe_discount_vs_peers", "risk_adjusted_return_potential", "mean_reversion_potential", "catalyst_timing", "recovery_signal_confidence", "sector_rotation_momentum", "valuation_trap_risk"],
    # banking_bfsi
    "risk":                ["asset_quality_trend", "concentration_risk", "deposit_stability", "regulatory_risk", "cyber_fraud_risk"],
    "macro_policy":        ["rbi_rate_cycle", "system_credit", "liquidity_conditions", "regulatory_actions", "fiscal_policy"],
    "institutional":       ["fii_dii_flow", "promoter_holding", "insider_trades", "amfi_mf_flow", "bulk_block_deals"],
    "universe_setup":      ["index_weight", "peer_positioning", "market_cap_tier", "corporate_actions", "rebalancing_risk"],
    # it_sector
    "global_macro":        ["us_tech_spend", "fed_rate_impact", "usd_inr", "geopolitical", "ma_activity"],
    "peer_benchmark":      ["revenue_growth_rank", "margin_rank", "deal_momentum_rank", "attrition_rank", "valuation_gap"],
    "transcript_nlp":      ["guidance_delta", "vertical_mix", "geography_colour", "ai_deal_count", "analyst_pushback"],
    "insider_smart_money": ["promoter_activity", "director_trades", "amfi_mf_flow", "fii_futures", "block_deals"],
    # renewable_energy
    "business":            ["subsector_mix", "ppa_quality", "pipeline_cred", "customer_divers", "geography_spread"],
    "valuation":           ["ev_per_mw", "ev_ebitda", "tariff_vs_auction", "pipeline_dcf", "implied_irr"],
    "sentiment_policy":    ["mnre_auction_health", "budget_allocation", "policy_tailwinds", "rbi_rate_impact", "module_price"],
    "technical":           ["moving_averages", "rsi_signal", "macd_weekly", "volume_catalyst", "accumulation_zone"],
}

# Verdict → expected direction mapping
VERDICT_BULLISH = {"STRONG BUY", "BUY"}
VERDICT_BEARISH = {"STRONG SELL", "SELL"}


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _load_json(path: Path) -> dict | None:
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def _grade(hit_rate: float, total: int) -> str:
    """A/B/C/D/F based on direction hit rate. N/A when sample is too small."""
    if total < 5:
        return "N/A"
    if hit_rate >= 0.65:
        return "A"
    if hit_rate >= 0.58:
        return "B"
    if hit_rate >= 0.52:
        return "C"
    if hit_rate >= 0.46:
        return "D"
    return "F"


def _pearson(xs: list[float], ys: list[float]) -> float | None:
    """Pearson correlation coefficient. Returns None if insufficient data."""
    n = len(xs)
    if n < 5:
        return None
    mx = sum(xs) / n
    my = sum(ys) / n
    num = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    dx = math.sqrt(sum((x - mx) ** 2 for x in xs))
    dy = math.sqrt(sum((y - my) ** 2 for y in ys))
    if dx == 0 or dy == 0:
        return None
    return round(num / (dx * dy), 4)


def _calibration_buckets(scores: list[float], outcomes: list[bool]) -> list[ScoreCalibrationBucket]:
    """
    Group (score, correct) pairs into five 0.2-wide buckets.
    Returns calibration error per bucket.
    """
    bands = [
        ("0.00–0.20", 0.00, 0.20, 0.10),
        ("0.20–0.40", 0.20, 0.40, 0.30),
        ("0.40–0.60", 0.40, 0.60, 0.50),
        ("0.60–0.80", 0.60, 0.80, 0.70),
        ("0.80–1.00", 0.80, 1.00, 0.90),
    ]
    buckets: list[ScoreCalibrationBucket] = []
    for label, lo, hi, ideal in bands:
        idxs = [i for i, s in enumerate(scores) if lo <= s < hi]
        if not idxs:
            continue
        hits = sum(1 for i in idxs if outcomes[i])
        hr = hits / len(idxs)
        buckets.append(ScoreCalibrationBucket(
            bucket=label, score_min=lo, score_max=hi,
            sample_count=len(idxs),
            direction_hit_rate=round(hr, 4),
            ideal_hit_rate=ideal,
            calibration_error=round(abs(hr - ideal), 4),
        ))
    return buckets


def _std(vals: list[float]) -> float:
    if len(vals) < 2:
        return 0.0
    m = sum(vals) / len(vals)
    return round(math.sqrt(sum((v - m) ** 2 for v in vals) / len(vals)), 4)


def _safe_mean(vals: list[float]) -> float:
    return round(sum(vals) / len(vals), 4) if vals else 0.0


def _verdict_is_correct(verdict: str, actual_direction: str) -> bool:
    """
    Verdict correct when bullish verdict + UP direction, or
    bearish verdict + DOWN direction, or NEUTRAL + FLAT.
    """
    if verdict in VERDICT_BULLISH:
        return actual_direction == "UP"
    if verdict in VERDICT_BEARISH:
        return actual_direction == "DOWN"
    if verdict == "NEUTRAL":
        return actual_direction == "FLAT"
    return False


# ─────────────────────────────────────────────────────────────────────────────
# Data collection
# ─────────────────────────────────────────────────────────────────────────────

class _RawEntry:
    """Flattened, sector-agnostic row from one FeedbackEntry."""
    __slots__ = (
        "sector", "ticker", "date", "predicted_verdict", "actual_direction",
        "direction_correct", "price_error_pct", "regime_label",
        "primary_miss_agent", "miss_type", "agent_score_drift",
        "predicted_agent_scores", "predicted_agent_subscores",
        "final_score",
    )

    def __init__(self, **kw: Any):
        for k, v in kw.items():
            setattr(self, k, v)


def _collect_sector(sector_path: Path, sector: str) -> tuple[list[_RawEntry], dict[str, Any], list[str]]:
    """
    Walk one sector directory and return:
      entries     — list of _RawEntry (one per feedback log row)
      weight_data — dict[ticker] → raw WeightMemory JSON
      sources     — list of file paths read
    """
    entries: list[_RawEntry] = []
    weight_data: dict[str, Any] = {}
    sources: list[str] = []

    if not sector_path.exists():
        return entries, weight_data, sources

    for ticker_dir in sorted(sector_path.iterdir()):
        if not ticker_dir.is_dir():
            continue
        ticker = ticker_dir.name

        # ── Feedback logs ──────────────────────────────────────────────────
        for log_file in sorted(ticker_dir.glob("*_daily_feedback_log.json")):
            raw = _load_json(log_file)
            if not raw:
                continue
            sources.append(str(log_file))

            for fe in raw.get("entries", []):
                ma = fe.get("miss_analysis") or {}
                predicted_scores = fe.get("predicted_agent_scores", {})
                # predicted_agent_subscores lives on DailyForecast; we'll join via date
                entries.append(_RawEntry(
                    sector=sector,
                    ticker=ticker,
                    date=fe.get("date", ""),
                    predicted_verdict=fe.get("predicted_verdict", ""),
                    actual_direction=fe.get("actual_direction", ""),
                    direction_correct=bool(fe.get("direction_correct", False)),
                    price_error_pct=float(fe.get("price_error_pct", 0.0)),
                    regime_label=fe.get("regime_label", "NORMAL"),
                    primary_miss_agent=ma.get("primary_miss_agent", ""),
                    miss_type=ma.get("miss_type", ""),
                    agent_score_drift=ma.get("agent_score_drift", {}),
                    predicted_agent_scores=predicted_scores,
                    predicted_agent_subscores={},   # filled below
                    final_score=predicted_scores.get("__final__", None),
                ))

        # ── Prediction envelopes (sub-scores) ─────────────────────────────
        date_to_subscores: dict[str, dict[str, dict[str, float]]] = {}
        date_to_final: dict[str, float] = {}
        for env_file in sorted(ticker_dir.glob("*_prediction_envelope.json")):
            raw = _load_json(env_file)
            if not raw:
                continue
            sources.append(str(env_file))
            for df in raw.get("daily_forecasts", []):
                d = df.get("date", "")
                date_to_subscores[d] = df.get("predicted_agent_subscores", {})
                # Store the predicted composite if available
                verdict_str = df.get("predicted_verdict", "")
                agent_scores = df.get("predicted_agent_scores", {})
                # best proxy for final_score: mean of agent scores
                if agent_scores:
                    date_to_final[d] = round(sum(agent_scores.values()) / len(agent_scores), 4)

        # Back-fill sub-scores and final_score into matching entries
        for e in entries:
            if e.ticker == ticker and e.date in date_to_subscores:
                e.predicted_agent_subscores = date_to_subscores[e.date]
            if e.ticker == ticker and e.date in date_to_final and e.final_score is None:
                e.final_score = date_to_final[e.date]

        # ── Weight memory ──────────────────────────────────────────────────
        for wm_file in sorted(ticker_dir.glob("*_agent_weight_memory.json")):
            raw = _load_json(wm_file)
            if not raw:
                continue
            sources.append(str(wm_file))
            weight_data[ticker] = raw

    return entries, weight_data, sources


def _collect_final_reports(outputs_path: Path) -> tuple[list[dict], list[str]]:
    """Collect any FinalReport JSON files saved to outputs/."""
    reports: list[dict] = []
    sources: list[str] = []
    if not outputs_path.exists():
        return reports, sources
    for f in sorted(outputs_path.rglob("*.json")):
        raw = _load_json(f)
        if raw and "final_score" in raw and "verdict" in raw:
            reports.append(raw)
            sources.append(str(f))
    return reports, sources


# ─────────────────────────────────────────────────────────────────────────────
# Scorers
# ─────────────────────────────────────────────────────────────────────────────

def _score_agents(
    entries: list[_RawEntry],
    weight_data: dict[str, Any],
    sector: str,
) -> dict[str, AgentEvalResult]:
    """Build AgentEvalResult for every agent in this sector."""
    base_w = BASE_WEIGHTS.get(sector, {})
    all_agents = set(base_w.keys())

    # Also pick up any agents mentioned in entries
    for e in entries:
        all_agents.update(e.predicted_agent_scores.keys())
        if e.primary_miss_agent:
            all_agents.add(e.primary_miss_agent)
    all_agents.discard("")

    # Aggregate WeightMemory across all tickers (combine hit counts)
    combined_wm: dict[str, dict[str, Any]] = {}
    for wm in weight_data.values():
        for agent, acc in (wm.get("agent_accuracy") or {}).items():
            if agent not in combined_wm:
                combined_wm[agent] = {"direction_hits": 0, "total": 0, "avg_error": []}
            combined_wm[agent]["direction_hits"] += acc.get("direction_hits", 0)
            combined_wm[agent]["total"]          += acc.get("total", 0)
            combined_wm[agent]["avg_error"].append(acc.get("avg_error", 0.0))

    # Regime accuracy: merge across tickers
    regime_hits: dict[str, dict[str, list]] = {}  # agent → regime → [bool outcomes]
    for wm in weight_data.values():
        for regime, agents in (wm.get("regime_accuracy") or {}).items():
            for agent, acc in agents.items():
                regime_hits.setdefault(agent, {}).setdefault(regime, [])
                h, t = acc.get("direction_hits", 0), acc.get("total", 0)
                if t > 0:
                    regime_hits[agent][regime].extend([True] * h + [False] * (t - h))

    # Current weights: take max-version WeightMemory per sector (most recent)
    latest_wm: dict | None = None
    best_ver = -1
    for wm in weight_data.values():
        ver = wm.get("weight_version", 0)
        if ver > best_ver:
            best_ver = ver
            latest_wm = wm
    current_weights = (latest_wm or {}).get("current_weights", {})

    # Per-agent: score distribution from feedback entries
    agent_scores_by_entry: dict[str, list[float]] = {}
    agent_directions: dict[str, list[bool]] = {}
    agent_miss_types: dict[str, list[str]] = {}
    primary_miss_counts: dict[str, int] = {}

    for e in entries:
        for agent, score in e.predicted_agent_scores.items():
            if agent == "__final__":
                continue
            agent_scores_by_entry.setdefault(agent, []).append(float(score))
            agent_directions.setdefault(agent, []).append(e.direction_correct)
        if e.primary_miss_agent:
            primary_miss_counts[e.primary_miss_agent] = primary_miss_counts.get(e.primary_miss_agent, 0) + 1
        if e.miss_type:
            agent_miss_types.setdefault(e.primary_miss_agent, []).append(e.miss_type)

    results: dict[str, AgentEvalResult] = {}
    for agent in sorted(all_agents):
        wm_acc = combined_wm.get(agent, {})
        d_hits = wm_acc.get("direction_hits", 0)
        d_total = wm_acc.get("total", 0)

        # Fall back to counting entries directly if WeightMemory is sparse
        if d_total == 0 and agent in agent_directions:
            directions = agent_directions[agent]
            d_total = len(directions)
            d_hits = sum(1 for x in directions if x)

        hit_rate = round(d_hits / d_total, 4) if d_total > 0 else 0.0

        scores = agent_scores_by_entry.get(agent, [])
        miss_type_raw = agent_miss_types.get(agent, [])
        miss_breakdown: dict[str, int] = {}
        for mt in miss_type_raw:
            miss_breakdown[mt] = miss_breakdown.get(mt, 0) + 1

        # Regime hit rates
        regime_hr: dict[str, float] = {}
        for regime, outcomes in regime_hits.get(agent, {}).items():
            if outcomes:
                regime_hr[regime] = round(sum(outcomes) / len(outcomes), 4)

        # Sub-score accuracy
        sub_scores_result = _score_sub_scores(agent, sector, entries)

        bw = base_w.get(agent, 0.0)
        cw = current_weights.get(agent, bw)

        results[agent] = AgentEvalResult(
            agent=agent,
            sector=sector,
            weight_base=bw,
            weight_current=cw,
            weight_drift=round(cw - bw, 4),
            direction_hits=d_hits,
            total_evaluated=d_total,
            direction_hit_rate=hit_rate,
            avg_score=_safe_mean(scores),
            score_std=_std(scores),
            primary_miss_count=primary_miss_counts.get(agent, 0),
            miss_type_breakdown=miss_breakdown,
            regime_hit_rates=regime_hr,
            sub_scores=sub_scores_result,
            grade=_grade(hit_rate, d_total),
        )

    return results


def _score_sub_scores(
    agent: str,
    sector: str,
    entries: list[_RawEntry],
) -> dict[str, SubScoreAccuracy]:
    """
    For one agent, compute SubScoreAccuracy for each of its sub-dimensions.
    Uses predicted_agent_subscores from prediction envelopes joined to direction_correct.
    """
    # Collect (sub_dim → list of (score_value, direction_correct))
    dim_data: dict[str, tuple[list[float], list[bool]]] = {}

    for e in entries:
        agent_ss = e.predicted_agent_subscores.get(agent, {})
        for dim, val in agent_ss.items():
            dim_data.setdefault(dim, ([], []))
            dim_data[dim][0].append(float(val))
            dim_data[dim][1].append(e.direction_correct)

    # For known sub-score dims, add placeholder if no data recorded
    known_dims = AGENT_SUB_SCORES.get(agent, [])
    for dim in known_dims:
        dim_data.setdefault(dim, ([], []))

    result: dict[str, SubScoreAccuracy] = {}
    for dim, (scores, outcomes) in dim_data.items():
        n = len(scores)
        corr = _pearson(scores, [1.0 if o else 0.0 for o in outcomes]) if n >= 5 else None
        buckets = _calibration_buckets(scores, outcomes) if n >= 5 else []

        # Sub-score grade: based on correlation when available
        if corr is not None:
            if corr >= 0.40:   sg = "A"
            elif corr >= 0.25: sg = "B"
            elif corr >= 0.10: sg = "C"
            elif corr >= 0.0:  sg = "D"
            else:              sg = "F"  # negative correlation is a model issue
        else:
            sg = "N/A"

        result[dim] = SubScoreAccuracy(
            sub_score_name=dim,
            agent=agent,
            sector=sector,
            sample_count=n,
            avg=_safe_mean(scores),
            std=_std(scores),
            min_val=min(scores, default=0.0),
            max_val=max(scores, default=0.0),
            correlation_with_direction=corr,
            calibration_buckets=buckets,
            grade=sg,
        )
    return result


def _score_verdicts(entries: list[_RawEntry]) -> dict[str, VerdictAccuracy]:
    """Compute precision per verdict tier."""
    tally: dict[str, dict] = {}
    for e in entries:
        v = e.predicted_verdict or "UNKNOWN"
        if v not in tally:
            tally[v] = {"total": 0, "correct": 0, "actual": {}}
        tally[v]["total"] += 1
        if e.direction_correct:
            tally[v]["correct"] += 1
        ad = e.actual_direction or "UNKNOWN"
        tally[v]["actual"][ad] = tally[v]["actual"].get(ad, 0) + 1

    result: dict[str, VerdictAccuracy] = {}
    for v, d in tally.items():
        t, c = d["total"], d["correct"]
        result[v] = VerdictAccuracy(
            verdict=v,
            total_calls=t,
            correct_calls=c,
            precision=round(c / t, 4) if t > 0 else 0.0,
            actual_distribution=d["actual"],
        )
    return result


def _score_tickers(entries: list[_RawEntry]) -> dict[str, TickerStats]:
    """Per-ticker accuracy stats."""
    tally: dict[str, dict] = {}
    for e in entries:
        t = e.ticker
        if t not in tally:
            tally[t] = {"hits": 0, "total": 0, "errors": [], "miss_types": {}, "blamed": {}}
        tally[t]["total"] += 1
        if e.direction_correct:
            tally[t]["hits"] += 1
        tally[t]["errors"].append(abs(e.price_error_pct))
        if e.miss_type:
            tally[t]["miss_types"][e.miss_type] = tally[t]["miss_types"].get(e.miss_type, 0) + 1
        if e.primary_miss_agent:
            tally[t]["blamed"][e.primary_miss_agent] = tally[t]["blamed"].get(e.primary_miss_agent, 0) + 1

    result: dict[str, TickerStats] = {}
    for ticker, d in tally.items():
        most_blamed = max(d["blamed"], key=d["blamed"].get) if d["blamed"] else ""
        result[ticker] = TickerStats(
            ticker=ticker,
            total_days=d["total"],
            direction_hits=d["hits"],
            direction_hit_rate=round(d["hits"] / d["total"], 4) if d["total"] else 0.0,
            avg_price_error_pct=round(_safe_mean(d["errors"]), 4),
            miss_type_distribution=d["miss_types"],
            most_blamed_agent=most_blamed,
        )
    return result


def _score_sector(
    sector: str,
    entries: list[_RawEntry],
    weight_data: dict[str, Any],
    final_reports: list[dict],
) -> SectorEvalResult:
    """Build a complete SectorEvalResult."""
    total = len(entries)
    if total == 0:
        return SectorEvalResult(
            sector=sector,
            total_predictions=0,
            direction_hit_rate=0.0,
            avg_price_error_pct=0.0,
            conflict_rate=0.0,
            grade="N/A",
        )

    hits = sum(1 for e in entries if e.direction_correct)
    hit_rate = round(hits / total, 4)
    avg_err = round(_safe_mean([abs(e.price_error_pct) for e in entries]), 4)

    # Conflict rate from FinalReport JSONs (sector-filtered)
    sector_reports = [r for r in final_reports if r.get("sector") == sector or sector in str(r.get("ticker", ""))]
    if sector_reports:
        with_conflicts = sum(1 for r in sector_reports if r.get("conflicts_resolved"))
        conflict_rate = round(with_conflicts / len(sector_reports), 4)
    else:
        conflict_rate = 0.0

    agents = _score_agents(entries, weight_data, sector)
    verdict_acc = _score_verdicts(entries)
    tickers = _score_tickers(entries)

    # Final score calibration (from FinalReport JSONs + feedback final_score)
    final_scores: list[float] = []
    final_outcomes: list[bool] = []
    for e in entries:
        if e.final_score is not None:
            final_scores.append(e.final_score)
            final_outcomes.append(e.direction_correct)
    for r in sector_reports:
        fs = r.get("final_score")
        if fs is not None:
            # We don't have outcome for fresh reports — skip for calibration
            pass
    calib = _calibration_buckets(final_scores, final_outcomes) if len(final_scores) >= 5 else []

    # Best / worst agent
    ranked = sorted(
        [(a, r.direction_hit_rate, r.total_evaluated) for a, r in agents.items() if r.total_evaluated >= 5],
        key=lambda x: x[1],
    )
    best_agent = ranked[-1][0] if ranked else ""
    worst_agent = ranked[0][0] if ranked else ""

    return SectorEvalResult(
        sector=sector,
        total_predictions=total,
        direction_hit_rate=hit_rate,
        avg_price_error_pct=avg_err,
        conflict_rate=conflict_rate,
        verdict_accuracy=verdict_acc,
        agents=agents,
        tickers=tickers,
        best_agent=best_agent,
        worst_agent=worst_agent,
        grade=_grade(hit_rate, total),
        final_score_calibration=calib,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Top-level entry point
# ─────────────────────────────────────────────────────────────────────────────

def build_eval_report(
    base_dir: Path,
    target_sectors: list[str] | None = None,
) -> EvalReport:
    """
    Scan base_dir for prediction data and outputs, compute all metrics,
    and return a fully-populated EvalReport.

    Args:
        base_dir: Root of the StockAgent project (c:/StartUp/StockAgent).
        target_sectors: If provided, evaluate only these sectors.
    """
    from datetime import date

    sectors_to_eval = target_sectors or SECTORS
    predictions_root = base_dir / "data" / "predictions"
    outputs_root = base_dir / "outputs"

    all_sources: list[str] = []
    warnings: list[str] = []

    # Collect final reports (sector-agnostic)
    final_reports, fr_sources = _collect_final_reports(outputs_root)
    all_sources.extend(fr_sources)

    sector_results: dict[str, SectorEvalResult] = {}

    for sector in sectors_to_eval:
        sector_path = predictions_root / sector
        entries, weight_data, sources = _collect_sector(sector_path, sector)
        all_sources.extend(sources)

        if not entries:
            warnings.append(
                f"{sector}: no feedback log data found in {sector_path}. "
                "Run the pipeline and daily_review.py first to generate prediction data."
            )

        sector_results[sector] = _score_sector(sector, entries, weight_data, final_reports)

    # Overall summary
    all_entries_total = sum(s.total_predictions for s in sector_results.values())
    all_entries_hits = sum(
        round(s.direction_hit_rate * s.total_predictions)
        for s in sector_results.values()
    )
    overall_hr = round(all_entries_hits / all_entries_total, 4) if all_entries_total > 0 else 0.0
    overall_err = _safe_mean([
        s.avg_price_error_pct for s in sector_results.values() if s.total_predictions > 0
    ])

    # Best/worst sector
    ranked_sectors = sorted(
        [(s, r.direction_hit_rate, r.total_predictions) for s, r in sector_results.items() if r.total_predictions > 0],
        key=lambda x: x[1],
    )
    best_sector  = ranked_sectors[-1][0] if ranked_sectors else ""
    worst_sector = ranked_sectors[0][0]  if ranked_sectors else ""

    # Best/worst agent globally
    all_agents_flat = [
        (f"{a} ({s})", r.direction_hit_rate, r.total_evaluated)
        for s, sr in sector_results.items()
        for a, r in sr.agents.items()
        if r.total_evaluated >= 5
    ]
    all_agents_flat.sort(key=lambda x: x[1])
    best_agent_global  = all_agents_flat[-1][0] if all_agents_flat else ""
    worst_agent_global = all_agents_flat[0][0]  if all_agents_flat else ""

    # Most / least reliable sub-score (by correlation)
    sub_corrs: list[tuple[str, float]] = [
        (f"{dim} ({agent} / {sector})", r.correlation_with_direction)
        for sector, sr in sector_results.items()
        for agent, ar in sr.agents.items()
        for dim, r in ar.sub_scores.items()
        if r.correlation_with_direction is not None
    ]
    sub_corrs.sort(key=lambda x: x[1])
    best_sub  = sub_corrs[-1][0] if sub_corrs else ""
    worst_sub = sub_corrs[0][0]  if sub_corrs else ""

    overall = OverallSummary(
        total_predictions=all_entries_total,
        overall_direction_hit_rate=overall_hr,
        overall_avg_price_error_pct=overall_err,
        best_sector=best_sector,
        worst_sector=worst_sector,
        best_agent_global=best_agent_global,
        worst_agent_global=worst_agent_global,
        most_reliable_sub_score=best_sub,
        least_reliable_sub_score=worst_sub,
    )

    return EvalReport(
        eval_date=date.today().isoformat(),
        data_sources=all_sources,
        sectors=sector_results,
        overall=overall,
        warnings=warnings,
    )

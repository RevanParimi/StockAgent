"""
services/api/routes/analytics.py
=================================
RL Analytics API — export, analysis views, and Power BI OData feed.

Endpoints
---------
GET /analytics/rl-export?format=csv|json   — full RL performance rows (Item 14)
GET /analytics/agent-accuracy              — per-agent hit rates + avg error (Item 15a)
GET /analytics/weight-drift                — agent weight history time-series (Item 15b)
GET /analytics/miss-breakdown              — miss type counts by ticker (Item 15c)
GET /analytics/conviction-outcomes         — streak length bucketed vs accuracy (Item 15d)
GET /analytics/sector-comparison           — cross-sector score/verdict comparison (Item 15e)
GET /analytics/powerbi-feed                — OData v4 JSON for Power BI Web connector (Item 17)
GET /analytics/powerbi-feed/$metadata      — EDMX XML schema for Power BI OData connector (Item 17)

Data sources
------------
- core.intelligence.rl.stores.prediction_store.PredictionStore
    → DailyFeedbackLog (per ticker/cycle): FeedbackEntry fields
    → WeightMemory: weight_history, agent_accuracy
    → PredictionEnvelope: conviction_streak, daily_forecasts
- services.data.stores.score_store.ScoreStore
    → score_history table: final_score, verdict, run_at per ticker

All endpoints degrade gracefully to empty result sets if no RL data exists.
"""

from __future__ import annotations

import csv
import io
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Query
from fastapi.responses import StreamingResponse, Response

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/analytics", tags=["Analytics"])

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_MISS_COLORS: dict[str, str] = {
    "direction_flip":  "#ef4444",
    "model_bias":      "#f97316",
    "timing":          "#f59e0b",
    "magnitude":       "#84cc16",
    "data_gap":        "#94a3b8",
    "data_stale":      "#94a3b8",
    "external_shock":  "#64748b",
    "":                "#cbd5e1",
}

_AGENT_COLORS: list[str] = [
    "#6366f1", "#22d3ee", "#4ade80", "#fb923c",
    "#f472b6", "#a78bfa", "#34d399", "#fbbf24", "#e879f9",
]

# ---------------------------------------------------------------------------
# Data-loading helpers
# ---------------------------------------------------------------------------

def _list_rl_tickers() -> list[tuple[str, str]]:
    """Return [(ticker, sector)] for all directories under data/predictions/."""
    base = Path("data/predictions")
    results: list[tuple[str, str]] = []
    if not base.exists():
        return results
    for sector_dir in base.iterdir():
        if not sector_dir.is_dir() or sector_dir.name.startswith("_"):
            continue
        for ticker_dir in sector_dir.iterdir():
            if ticker_dir.is_dir():
                results.append((ticker_dir.name, sector_dir.name))
    return results


def _try_import_prediction_store():
    try:
        from core.intelligence.rl.stores.prediction_store import PredictionStore
        return PredictionStore
    except ImportError:
        return None


def _try_import_score_store():
    try:
        from services.data.stores.score_store import ScoreStore
        return ScoreStore()
    except Exception:
        return None


def _build_score_index() -> dict[str, list[dict]]:
    """
    Load all score history from ScoreStore, indexed by ticker.
    Returns {ticker: [row, ...]} sorted by run_at descending.
    """
    store = _try_import_score_store()
    if store is None:
        return {}
    try:
        rows = store.get_all_latest() or []
        index: dict[str, list[dict]] = {}
        for row in rows:
            ticker = row.get("ticker", "")
            if ticker:
                index.setdefault(ticker, []).append(row)
        # Also pull full history for each ticker
        full_index: dict[str, list[dict]] = {}
        seen = set(index.keys())
        for ticker in seen:
            try:
                history = store.get_history(ticker, limit=90)
                full_index[ticker] = history or []
            except Exception:
                full_index[ticker] = index.get(ticker, [])
        return full_index
    except Exception as exc:
        logger.debug("[analytics] ScoreStore load failed: %s", exc)
        return {}


def _nearest_score(score_rows: list[dict], target_date: str) -> float | None:
    """Find the score row with run_at nearest to target_date."""
    if not score_rows:
        return None
    best = None
    best_delta = None
    for row in score_rows:
        run_at = (row.get("run_at") or "")[:10]
        if not run_at:
            continue
        try:
            delta = abs(
                datetime.fromisoformat(run_at) - datetime.fromisoformat(target_date)
            ).days
        except ValueError:
            continue
        if best_delta is None or delta < best_delta:
            best_delta = delta
            best = float(row["final_score"])
    return best


def _load_feedback_rows(
    score_index: dict[str, list[dict]],
) -> list[dict]:
    """
    Assemble one row per FeedbackEntry across all tickers with RL data.
    Returns list of dicts matching the export schema.
    """
    PredictionStore = _try_import_prediction_store()
    if PredictionStore is None:
        return []

    rows: list[dict] = []
    tickers = _list_rl_tickers()

    for ticker, sector in tickers:
        try:
            store = PredictionStore(ticker=ticker, sector=sector)
            wm = store.load_weight_memory()

            # Overall hit rate for this ticker across all reviewed days
            all_entries: list[Any] = []
            for cycle_id in store.list_cycles():
                fb_log = store.load_feedback_log(cycle_id)
                if fb_log and fb_log.entries:
                    all_entries.extend(fb_log.entries)

            total_entries = len(all_entries)
            total_correct = sum(1 for e in all_entries if e.direction_correct)
            ticker_hit_rate = round(total_correct / total_entries, 4) if total_entries else 0.0

            current_weights: dict[str, float] = {}
            if wm:
                current_weights = dict(wm.current_weights or {})

            # Per-cycle, per-day rows
            streak = 0
            for cycle_id in store.list_cycles():
                fb_log = store.load_feedback_log(cycle_id)
                if not fb_log or not fb_log.entries:
                    continue

                sorted_entries = sorted(fb_log.entries, key=lambda e: e.date)
                for entry in sorted_entries:
                    # Update running conviction streak
                    if entry.direction_correct:
                        streak += 1
                    else:
                        streak = 0

                    miss_type = ""
                    primary_miss_agent = ""
                    if entry.miss_analysis:
                        mt = entry.miss_analysis.miss_type
                        miss_type = str(mt) if mt else ""
                        primary_miss_agent = entry.miss_analysis.primary_miss_agent or ""

                    final_score = _nearest_score(
                        score_index.get(ticker, []), entry.date
                    )

                    rows.append({
                        "ticker":             ticker,
                        "sector":             sector,
                        "date":               entry.date,
                        "actual_direction":   str(entry.actual_direction),
                        "direction_correct":  entry.direction_correct,
                        "price_error_pct":    round(entry.price_error_pct, 4),
                        "miss_type":          miss_type,
                        "primary_miss_agent": primary_miss_agent,
                        "conviction_streak":  streak,
                        "regime_label":       "",
                        "agent_weights":      current_weights,
                        "hit_rate":           ticker_hit_rate,
                        "final_score":        final_score,
                    })

        except Exception as exc:
            logger.debug("[analytics] Error loading %s/%s: %s", sector, ticker, exc)

    rows.sort(key=lambda r: (r["ticker"], r["date"]))
    return rows


# ---------------------------------------------------------------------------
# Item 14 — GET /analytics/rl-export
# ---------------------------------------------------------------------------

@router.get("/rl-export", summary="Export full RL performance data as JSON or CSV")
async def rl_export(format: str = Query(default="json", pattern="^(json|csv)$")):
    """
    Returns one row per reviewed trading day per ticker.

    Columns: ticker · sector · date · final_score · actual_direction ·
             direction_correct · price_error_pct · miss_type · primary_miss_agent ·
             conviction_streak · regime_label · agent_weights (JSON) · hit_rate

    format=csv  — downloads a .csv file
    format=json — returns a JSON array
    """
    score_index = _build_score_index()
    rows = _load_feedback_rows(score_index)

    if format == "csv":
        buf = io.StringIO()
        fieldnames = [
            "ticker", "sector", "date", "final_score", "actual_direction",
            "direction_correct", "price_error_pct", "miss_type", "primary_miss_agent",
            "conviction_streak", "regime_label", "hit_rate", "agent_weights",
        ]
        writer = csv.DictWriter(buf, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            flat = {**row, "agent_weights": json.dumps(row.get("agent_weights", {}))}
            writer.writerow(flat)
        buf.seek(0)
        return StreamingResponse(
            io.BytesIO(buf.read().encode("utf-8")),
            media_type="text/csv",
            headers={"Content-Disposition": 'attachment; filename="rl_export.csv"'},
        )

    return {
        "count":      len(rows),
        "columns":    [
            "ticker", "sector", "date", "final_score", "actual_direction",
            "direction_correct", "price_error_pct", "miss_type", "primary_miss_agent",
            "conviction_streak", "regime_label", "hit_rate", "agent_weights",
        ],
        "rows":       rows,
        "exported_at": datetime.now(timezone.utc).isoformat(),
    }


# ---------------------------------------------------------------------------
# Item 15a — GET /analytics/agent-accuracy
# ---------------------------------------------------------------------------

@router.get("/agent-accuracy", summary="Per-agent direction hit rate and average price error")
async def agent_accuracy():
    """
    For each ticker: per-agent hit rate and average |price_error_pct| sourced
    from WeightMemory.agent_accuracy. Aggregated across tickers too.
    """
    PredictionStore = _try_import_prediction_store()
    if PredictionStore is None:
        return {"tickers": [], "aggregate": []}

    tickers_data: list[dict] = []
    aggregate: dict[str, dict] = {}

    for ticker, sector in _list_rl_tickers():
        try:
            store = PredictionStore(ticker=ticker, sector=sector)
            wm = store.load_weight_memory()
            if not wm or not wm.agent_accuracy:
                continue

            per_agent = []
            for agent_name, acc in wm.agent_accuracy.items():
                hit = float(acc.hit_rate()) if hasattr(acc, "hit_rate") else (
                    acc.direction_hits / acc.total if acc.total > 0 else 0.0
                )
                per_agent.append({
                    "agent":          agent_name,
                    "hit_rate":       round(hit, 4),
                    "direction_hits": acc.direction_hits,
                    "total":          acc.total,
                    "avg_error_pct":  round(acc.avg_error, 4),
                })
                agg = aggregate.setdefault(agent_name, {"hits": 0, "total": 0, "errors": []})
                agg["hits"]   += acc.direction_hits
                agg["total"]  += acc.total
                agg["errors"].append(acc.avg_error)

            per_agent.sort(key=lambda x: x["hit_rate"], reverse=True)
            tickers_data.append({
                "ticker":     ticker,
                "sector":     sector,
                "per_agent":  per_agent,
                "overall_hit_rate": round(
                    sum(a["hit_rate"] for a in per_agent) / len(per_agent), 4
                ) if per_agent else 0.0,
            })
        except Exception as exc:
            logger.debug("[analytics/agent-accuracy] %s: %s", ticker, exc)

    agg_list = []
    for agent_name, d in aggregate.items():
        agg_list.append({
            "agent":         agent_name,
            "hit_rate":      round(d["hits"] / d["total"], 4) if d["total"] else 0.0,
            "direction_hits": d["hits"],
            "total":         d["total"],
            "avg_error_pct": round(sum(d["errors"]) / len(d["errors"]), 4) if d["errors"] else 0.0,
        })
    agg_list.sort(key=lambda x: x["hit_rate"], reverse=True)

    return {
        "tickers":   tickers_data,
        "aggregate": agg_list,
    }


# ---------------------------------------------------------------------------
# Item 15b — GET /analytics/weight-drift
# ---------------------------------------------------------------------------

@router.get("/weight-drift", summary="Agent weight history time-series per ticker")
async def weight_drift():
    """
    Returns the full WeightMemory.weight_history for each ticker —
    versioned snapshots of learned agent weights plus the reason for each change.

    Useful for: plotting how each agent's influence has evolved and detecting
    weight over-correction.
    """
    PredictionStore = _try_import_prediction_store()
    if PredictionStore is None:
        return {"tickers": []}

    result: list[dict] = []
    all_agents: set[str] = set()

    for ticker, sector in _list_rl_tickers():
        try:
            store = PredictionStore(ticker=ticker, sector=sector)
            wm = store.load_weight_memory()
            if not wm:
                continue

            history = [
                {
                    "version": h.version,
                    "date":    h.date,
                    "weights": dict(h.weights),
                    "reason":  h.reason,
                }
                for h in (wm.weight_history or [])
            ]
            history.sort(key=lambda h: h["date"])
            all_agents.update(wm.current_weights.keys() if wm.current_weights else [])

            result.append({
                "ticker":          ticker,
                "sector":          sector,
                "current_weights": dict(wm.current_weights or {}),
                "base_weights":    dict(wm.base_weights or {}),
                "weight_history":  history,
                "weight_version":  wm.weight_version,
                "last_updated":    wm.last_updated,
            })
        except Exception as exc:
            logger.debug("[analytics/weight-drift] %s: %s", ticker, exc)

    # Assign a stable colour per agent for frontend charts
    agent_colors = {
        agent: _AGENT_COLORS[i % len(_AGENT_COLORS)]
        for i, agent in enumerate(sorted(all_agents))
    }

    return {"tickers": result, "agent_colors": agent_colors}


# ---------------------------------------------------------------------------
# Item 15c — GET /analytics/miss-breakdown
# ---------------------------------------------------------------------------

@router.get("/miss-breakdown", summary="Miss type distribution per ticker and aggregated")
async def miss_breakdown():
    """
    Counts every MissType across all FeedbackEntry records.

    Returns:
      aggregate — {miss_type: count} across all tickers
      tickers   — [{ticker, miss_counts: {type: n}, top_miss_agent: str}]
      colors    — {miss_type: hex_color} for chart rendering
    """
    PredictionStore = _try_import_prediction_store()
    if PredictionStore is None:
        return {"aggregate": {}, "tickers": [], "colors": _MISS_COLORS}

    aggregate: dict[str, int] = {}
    tickers_data: list[dict] = []

    for ticker, sector in _list_rl_tickers():
        try:
            store = PredictionStore(ticker=ticker, sector=sector)
            miss_counts: dict[str, int] = {}
            agent_miss_counts: dict[str, int] = {}

            for cycle_id in store.list_cycles():
                fb_log = store.load_feedback_log(cycle_id)
                if not fb_log or not fb_log.entries:
                    continue
                for entry in fb_log.entries:
                    if entry.miss_analysis:
                        mt = str(entry.miss_analysis.miss_type or "")
                        miss_counts[mt] = miss_counts.get(mt, 0) + 1
                        aggregate[mt]   = aggregate.get(mt, 0) + 1
                        agent = entry.miss_analysis.primary_miss_agent or ""
                        if agent:
                            agent_miss_counts[agent] = agent_miss_counts.get(agent, 0) + 1
                    else:
                        miss_counts[""] = miss_counts.get("", 0) + 1
                        aggregate[""]   = aggregate.get("", 0) + 1

            top_agent = max(agent_miss_counts, key=agent_miss_counts.get) if agent_miss_counts else ""
            tickers_data.append({
                "ticker":         ticker,
                "sector":         sector,
                "miss_counts":    miss_counts,
                "top_miss_agent": top_agent,
                "agent_miss_counts": agent_miss_counts,
            })
        except Exception as exc:
            logger.debug("[analytics/miss-breakdown] %s: %s", ticker, exc)

    return {
        "aggregate": aggregate,
        "tickers":   tickers_data,
        "colors":    _MISS_COLORS,
    }


# ---------------------------------------------------------------------------
# Item 15d — GET /analytics/conviction-outcomes
# ---------------------------------------------------------------------------

@router.get("/conviction-outcomes", summary="Conviction streak length bucketed against direction accuracy")
async def conviction_outcomes():
    """
    Groups FeedbackEntry rows by conviction streak bucket (0, 1-2, 3-5, 6-10, 11+)
    and computes direction accuracy and mean |price_error_pct| per bucket.

    Also returns raw (streak_days, direction_correct, price_error_pct) scatter points
    for plotting a scatter chart.
    """
    PredictionStore = _try_import_prediction_store()
    if PredictionStore is None:
        return {"buckets": [], "scatter": []}

    _BUCKETS = [(0, 0), (1, 2), (3, 5), (6, 10), (11, 999)]
    _BUCKET_LABELS = ["0", "1–2", "3–5", "6–10", "11+"]

    bucket_hits:   dict[int, int]   = {i: 0 for i in range(len(_BUCKETS))}
    bucket_total:  dict[int, int]   = {i: 0 for i in range(len(_BUCKETS))}
    bucket_errors: dict[int, list[float]] = {i: [] for i in range(len(_BUCKETS))}
    scatter: list[dict] = []

    for ticker, sector in _list_rl_tickers():
        try:
            store = PredictionStore(ticker=ticker, sector=sector)
            streak = 0
            for cycle_id in store.list_cycles():
                fb_log = store.load_feedback_log(cycle_id)
                if not fb_log or not fb_log.entries:
                    continue
                for entry in sorted(fb_log.entries, key=lambda e: e.date):
                    # Streak at start of this day
                    bucket_idx = next(
                        (i for i, (lo, hi) in enumerate(_BUCKETS) if lo <= streak <= hi),
                        len(_BUCKETS) - 1,
                    )
                    bucket_total[bucket_idx] += 1
                    bucket_errors[bucket_idx].append(abs(entry.price_error_pct))
                    if entry.direction_correct:
                        bucket_hits[bucket_idx] += 1
                        streak += 1
                    else:
                        streak = 0

                    scatter.append({
                        "ticker":            ticker,
                        "date":              entry.date,
                        "streak":            streak,
                        "direction_correct": entry.direction_correct,
                        "price_error_pct":   round(entry.price_error_pct, 3),
                    })
        except Exception as exc:
            logger.debug("[analytics/conviction-outcomes] %s: %s", ticker, exc)

    buckets = []
    for i, label in enumerate(_BUCKET_LABELS):
        n = bucket_total[i]
        hits = bucket_hits[i]
        errs = bucket_errors[i]
        buckets.append({
            "label":            label,
            "total":            n,
            "hits":             hits,
            "accuracy":         round(hits / n, 4) if n else 0.0,
            "avg_error_pct":    round(sum(errs) / len(errs), 3) if errs else 0.0,
        })

    return {"buckets": buckets, "scatter": scatter}


# ---------------------------------------------------------------------------
# Item 15e — GET /analytics/sector-comparison
# ---------------------------------------------------------------------------

@router.get("/sector-comparison", summary="Cross-sector verdict and score comparison")
async def sector_comparison():
    """
    Groups the latest ScoreStore row per ticker by sector and computes:
      - avg_score, score_stddev
      - verdict distribution (STRONG BUY / BUY / NEUTRAL / SELL / STRONG SELL)
      - best/worst ticker in each sector

    Also includes RL direction accuracy per sector (from WeightMemory).
    """
    store = _try_import_score_store()
    rows = store.get_all_latest() if store else []

    # Group scores by sector using detect_sector
    sector_scores: dict[str, list[dict]] = {}
    try:
        from backend.sectors import detect_sector
        for row in rows:
            ticker  = row.get("ticker", "")
            sector  = detect_sector(ticker)
            sector_scores.setdefault(sector, []).append(row)
    except ImportError:
        for row in rows:
            sector_scores.setdefault("unknown", []).append(row)

    # RL accuracy per sector (from WM)
    rl_sector_accuracy: dict[str, dict] = {}
    PredictionStore = _try_import_prediction_store()
    if PredictionStore:
        for ticker, sector in _list_rl_tickers():
            try:
                ps = PredictionStore(ticker=ticker, sector=sector)
                wm = ps.load_weight_memory()
                if wm and wm.agent_accuracy:
                    hits  = sum(a.direction_hits for a in wm.agent_accuracy.values())
                    total = sum(a.total          for a in wm.agent_accuracy.values())
                    rate  = hits / total if total else 0.0
                    acc   = rl_sector_accuracy.setdefault(sector, {"hits": 0, "total": 0})
                    acc["hits"]  += hits
                    acc["total"] += total
            except Exception:
                pass

    verdicts = ["STRONG BUY", "BUY", "NEUTRAL", "SELL", "STRONG SELL"]
    result = []
    for sector, sector_rows in sector_scores.items():
        scores = [float(r["final_score"]) for r in sector_rows if r.get("final_score") is not None]
        avg    = round(sum(scores) / len(scores), 4) if scores else 0.0
        stddev = 0.0
        if len(scores) > 1:
            mean = sum(scores) / len(scores)
            stddev = round((sum((s - mean) ** 2 for s in scores) / len(scores)) ** 0.5, 4)

        verdict_dist = {v: 0 for v in verdicts}
        for row in sector_rows:
            v = row.get("verdict", "NEUTRAL")
            if v in verdict_dist:
                verdict_dist[v] += 1

        best  = max(sector_rows, key=lambda r: float(r.get("final_score", 0)))
        worst = min(sector_rows, key=lambda r: float(r.get("final_score", 1)))

        rl_acc = rl_sector_accuracy.get(sector, {})
        rl_rate = round(rl_acc["hits"] / rl_acc["total"], 4) if rl_acc.get("total", 0) > 0 else None

        result.append({
            "sector":            sector,
            "ticker_count":      len(sector_rows),
            "avg_score":         avg,
            "score_stddev":      stddev,
            "verdict_dist":      verdict_dist,
            "best_ticker":       {"ticker": best.get("ticker"), "score": float(best.get("final_score", 0)), "verdict": best.get("verdict")},
            "worst_ticker":      {"ticker": worst.get("ticker"), "score": float(worst.get("final_score", 0)), "verdict": worst.get("verdict")},
            "rl_direction_accuracy": rl_rate,
        })

    result.sort(key=lambda x: x["avg_score"], reverse=True)
    return {
        "sectors":    result,
        "as_of":      datetime.now(timezone.utc).isoformat(),
        "total_tickers": len(rows),
    }


# ---------------------------------------------------------------------------
# Item 17 — GET /analytics/powerbi-feed  (OData v4)
# ---------------------------------------------------------------------------

_ODATA_CONTEXT_URL = "/analytics/powerbi-feed/$metadata#rlMetrics"

@router.get("/powerbi-feed", summary="OData v4 JSON feed for Power BI Web connector")
async def powerbi_feed():
    """
    Returns RL performance rows in OData v4 format.

    **How to connect in Power BI Desktop:**
    1. Home → Get Data → Web → Basic
    2. URL: https://stockagent-ai.up.railway.app/analytics/powerbi-feed
    3. Power BI auto-detects the OData 'value' array
    4. Expand 'agent_weights' as a Record → extract individual agent columns
    5. Schedule refresh: File → Options → Data Source Settings → Set credentials
       (Anonymous — no auth needed), then publish to Power BI Service and set
       Gateway refresh schedule (min 30 min interval for free tier).

    Alternatively use the OData connector:
    1. Home → Get Data → OData Feed
    2. URL: https://stockagent-ai.up.railway.app/analytics/powerbi-feed
    3. This auto-reads $metadata to type columns correctly.
    """
    score_index = _build_score_index()
    rows = _load_feedback_rows(score_index)

    # OData expects string-only leaf values (no nested dicts in v4 simple properties)
    # Flatten agent_weights as a JSON string; Power BI can parse it with JSON.Document()
    odata_rows = []
    for row in rows:
        odata_rows.append({
            "ticker":             row["ticker"],
            "sector":             row["sector"],
            "date":               row["date"],
            "actual_direction":   row["actual_direction"],
            "direction_correct":  row["direction_correct"],
            "price_error_pct":    row["price_error_pct"],
            "miss_type":          row["miss_type"],
            "primary_miss_agent": row["primary_miss_agent"],
            "conviction_streak":  row["conviction_streak"],
            "regime_label":       row["regime_label"],
            "hit_rate":           row["hit_rate"],
            "final_score":        row["final_score"],
            "agent_weights_json": json.dumps(row["agent_weights"]),
        })

    return {
        "@odata.context":  _ODATA_CONTEXT_URL,
        "@odata.count":    len(odata_rows),
        "value":           odata_rows,
    }


# ---------------------------------------------------------------------------
# Item 17 — GET /analytics/powerbi-feed/$metadata  (EDMX XML)
# ---------------------------------------------------------------------------

_EDMX_TEMPLATE = """\
<?xml version="1.0" encoding="utf-8"?>
<edmx:Edmx Version="4.0" xmlns:edmx="http://docs.oasis-open.org/odata/ns/edmx">
  <edmx:DataServices>
    <Schema Namespace="StockAgent" xmlns="http://docs.oasis-open.org/odata/ns/edm">
      <EntityType Name="RlMetric">
        <Key><PropertyRef Name="ticker"/><PropertyRef Name="date"/></Key>
        <Property Name="ticker"              Type="Edm.String"  Nullable="false"/>
        <Property Name="sector"              Type="Edm.String"  Nullable="false"/>
        <Property Name="date"                Type="Edm.Date"    Nullable="false"/>
        <Property Name="actual_direction"    Type="Edm.String"/>
        <Property Name="direction_correct"   Type="Edm.Boolean"/>
        <Property Name="price_error_pct"     Type="Edm.Double"/>
        <Property Name="miss_type"           Type="Edm.String"/>
        <Property Name="primary_miss_agent"  Type="Edm.String"/>
        <Property Name="conviction_streak"   Type="Edm.Int32"/>
        <Property Name="regime_label"        Type="Edm.String"/>
        <Property Name="hit_rate"            Type="Edm.Double"/>
        <Property Name="final_score"         Type="Edm.Double"/>
        <Property Name="agent_weights_json"  Type="Edm.String"/>
      </EntityType>
      <EntityContainer Name="Default">
        <EntitySet Name="rlMetrics" EntityType="StockAgent.RlMetric"/>
      </EntityContainer>
    </Schema>
  </edmx:DataServices>
</edmx:Edmx>"""


@router.get(
    "/powerbi-feed/$metadata",
    summary="EDMX metadata for OData connector type inference",
    include_in_schema=False,
)
async def powerbi_metadata():
    return Response(content=_EDMX_TEMPLATE, media_type="application/xml")

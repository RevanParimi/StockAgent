"""
services/data/stores/analysis_logger.py
========================================
Two human-oriented log outputs written after every completed analysis run.

  logs/analysis_rich.jsonl    — one JSON line per run; all facts in one place.
                                 Consumed by the UI and Python scripts.

  logs/analysis_readable.log  — plain-text block per run; open in any editor.
                                 Designed for human review, not parsing.

Public API
----------
log_analysis(report, run_id, duration_seconds, model, agent_outputs)
"""

from __future__ import annotations

import json
import logging
import textwrap
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from config import settings
from core.schemas.pipeline import FinalReport

logger = logging.getLogger(__name__)

LOGS_DIR = Path(settings.__dict__.get("LOGS_DIR", "logs"))
RICH_LOG    = LOGS_DIR / "analysis_rich.jsonl"
READABLE_LOG = LOGS_DIR / "analysis_readable.log"

_WIDTH = 80   # terminal width for readable log


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _signal(score: float) -> str:
    if score >= 0.75: return "STRONG"
    if score >= 0.60: return "POSITIVE"
    if score >= 0.50: return "NEUTRAL"
    if score >= 0.40: return "CAUTION"
    return "WEAK"


def _bar(score: float, width: int = 10) -> str:
    filled = round(score * width)
    return "\u2588" * filled + "\u2591" * (width - filled)


def _append(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with open(path, "a", encoding="utf-8") as f:
            f.write(text)
    except Exception as exc:
        logger.warning("[analysis_logger] Write failed %s: %s", path.name, exc)


def _get_vc_field(agent_outputs: dict, field: str):
    """Extract a field from the valuation_catalyst agent output dict."""
    vc = agent_outputs.get("valuation_catalyst", {})
    if hasattr(vc, "model_dump"):
        vc = vc.model_dump()
    return vc.get(field) if isinstance(vc, dict) else None


def _fetch_price(ticker: str) -> dict:
    """Best-effort current price from yfinance. Returns empty dict on failure."""
    try:
        import yfinance as yf
        suffix = settings.YFINANCE_SUFFIX
        yf_ticker = ticker if ticker.endswith(suffix) else f"{ticker}{suffix}"
        info = yf.Ticker(yf_ticker).fast_info
        return {
            "current":          round(float(info.last_price or 0), 2),
            "52w_high":         round(float(info.year_high or 0), 2),
            "52w_low":          round(float(info.year_low or 0), 2),
        }
    except Exception:
        return {}


# ---------------------------------------------------------------------------
# Rich structured log (JSONL — one line per run)
# ---------------------------------------------------------------------------

def _build_rich_record(
    report: FinalReport,
    run_id: str,
    duration_seconds: float,
    model: str,
    agent_outputs: dict[str, Any],
    price: dict,
    ts: str,
) -> dict:
    agent_breakdown = []
    for name, ws in report.weighted_agent_scores.items():
        ao = agent_outputs.get(name, {})
        # ao may be an AgentOutput object or dict depending on caller
        if hasattr(ao, "model_dump"):
            ao = ao.model_dump()
        agent_breakdown.append({
            "agent":         name,
            "score":         ws.raw,
            "weight":        ws.weight,
            "weighted":      round(ws.weighted, 4),
            "signal":        _signal(ws.raw),
            "summary":       ao.get("summary", ""),
            "key_positives": ao.get("key_positives", []),
            "key_risks":     ao.get("key_risks", []),
            "sub_scores":    ao.get("sub_scores"),
            "error":         ao.get("error"),
        })

    # sort by weighted contribution descending
    agent_breakdown.sort(key=lambda x: x["weighted"], reverse=True)

    return {
        "ts":              ts,
        "run_id":          run_id,
        "date":            report.report_date,
        "ticker":          report.ticker,
        "company_name":    report.company_name,
        "sector":          "automobile",
        "price":           price,
        "verdict":         report.verdict,
        "final_score":     report.final_score,
        "investment_thesis":   report.investment_thesis,
        "conviction_drivers":  report.conviction_drivers,
        "top_risks":           report.top_risks,
        "conflicts_resolved":  report.conflicts_resolved,
        "agent_breakdown":     agent_breakdown,
        "valuation": {
            "fair_value_estimate":       _get_vc_field(agent_outputs, "fair_value_estimate"),
            "price_target":              report.price_target,
            "undervalued_by_pct":        report.undervalued_by_pct,
            "recovery_timeline_quarters": report.recovery_timeline_quarters,
            "discount_reason":           report.discount_reason,
            "recovery_catalysts":        report.recovery_catalysts,
        },
        "run_meta": {
            "duration_seconds": duration_seconds,
            "model":            model,
        },
    }


# ---------------------------------------------------------------------------
# Human-readable log (plain text)
# ---------------------------------------------------------------------------

def _build_readable_block(record: dict) -> str:
    sep  = "=" * _WIDTH + "\n"
    thin = "-" * _WIDTH + "\n"
    lines: list[str] = ["\n", sep]

    # Header
    ticker_line = f"{record['ticker']} | {record['company_name']}"
    date_str    = f"{record['date']}  run:{record['run_id']}"
    lines.append(f"{ticker_line:<50}{date_str:>30}\n")
    lines.append(f"Model: {record['run_meta']['model']}  |  {record['run_meta']['duration_seconds']:.1f}s\n")
    lines.append(sep)

    # Verdict
    score_str = f"Score: {record['final_score']:.3f} / 1.00"
    verdict_str = f"VERDICT: {record['verdict']}"
    lines.append(f"{verdict_str:<40}{score_str:>40}\n\n")

    # Price block
    p = record.get("price", {})
    if p.get("current"):
        current   = p["current"]
        hi, lo    = p.get("52w_high", 0), p.get("52w_low", 0)
        hi_pct    = f"{(current - hi) / hi * 100:+.1f}%" if hi else "N/A"
        lo_pct    = f"{(current - lo) / lo * 100:+.1f}%" if lo else "N/A"
        lines.append(f"Price: \u20b9{current:,.2f}  |  52W High: \u20b9{hi:,.2f} ({hi_pct})  |  52W Low: \u20b9{lo:,.2f} ({lo_pct})\n\n")

    # Thesis
    thesis = record.get("investment_thesis", "")
    if thesis and "failed" not in thesis.lower():
        lines.append("INVESTMENT THESIS\n")
        for ln in textwrap.wrap(thesis, width=_WIDTH - 2):
            lines.append(f"  {ln}\n")
        lines.append("\n")

    # Conviction drivers
    drivers = record.get("conviction_drivers", [])
    if drivers:
        lines.append("CONVICTION DRIVERS\n")
        for d in drivers:
            for ln in textwrap.wrap(d, width=_WIDTH - 4):
                lines.append(f"  + {ln}\n")
        lines.append("\n")

    # Top risks
    risks = record.get("top_risks", [])
    if risks:
        lines.append("TOP RISKS\n")
        for r in risks:
            for ln in textwrap.wrap(r, width=_WIDTH - 4):
                lines.append(f"  ! {ln}\n")
        lines.append("\n")

    # Valuation section
    val = record.get("valuation", {})
    fv  = val.get("fair_value_estimate")
    pt  = val.get("price_target")
    disc = val.get("undervalued_by_pct")
    rq  = val.get("recovery_timeline_quarters")
    dr  = val.get("discount_reason")
    cats = val.get("recovery_catalysts", [])
    if any(x is not None for x in (fv, pt, disc)):
        lines.append("VALUATION\n")
        fv_str   = f"\u20b9{fv:,.0f}" if fv is not None else "N/A"
        pt_str   = f"\u20b9{pt:,.0f}" if pt is not None else "N/A"
        disc_str = f"{disc:+.1f}%" if disc is not None else "N/A"
        rq_str   = f"{rq}Q" if rq is not None else "N/A"
        dr_str   = dr or "N/A"
        lines.append(f"  Fair Value: {fv_str}  |  Current Discount: {disc_str}  |  Price Target: {pt_str}\n")
        lines.append(f"  Recovery: {rq_str}  |  Reason: {dr_str}\n")
        if cats:
            lines.append("  Catalysts:\n")
            for cat in cats[:3]:
                lines.append(f"    - {cat}\n")
        lines.append("\n")

    # Agent breakdown table
    lines.append("AGENT BREAKDOWN  (sorted by weighted contribution)\n")
    lines.append(f"  {'Agent':<20} {'Score':>5}  {'Bar':<12} {'Signal':<8} {'Wt':>4}  {'Contrib':>7}\n")
    lines.append("  " + "-" * (_WIDTH - 2) + "\n")
    for ab in record["agent_breakdown"]:
        lines.append(
            f"  {ab['agent']:<20} {ab['score']:>5.2f}  {_bar(ab['score']):<12} "
            f"{ab['signal']:<8} {ab['weight']*100:>3.0f}%  {ab['weighted']:>7.4f}\n"
        )
        # Key positives (first one only for brevity)
        if ab.get("key_positives"):
            snippet = ab["key_positives"][0][:60]
            lines.append(f"    {'':20}  + {snippet}\n")
        if ab.get("key_risks"):
            snippet = ab["key_risks"][0][:60]
            lines.append(f"    {'':20}  ! {snippet}\n")
    lines.append("\n")

    # Conflicts resolved
    conflicts = record.get("conflicts_resolved", [])
    if conflicts:
        lines.append("CONFLICTS RESOLVED\n")
        for c in conflicts:
            lines.append(f"  . {c}\n")
        lines.append("\n")

    lines.append(sep)
    return "".join(lines)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def log_analysis(
    report: FinalReport,
    run_id: str,
    duration_seconds: float,
    model: str,
    agent_outputs: dict[str, Any],
) -> None:
    """
    Write one entry to analysis_rich.jsonl and analysis_readable.log.

    Parameters
    ----------
    report           : FinalReport from the orchestrator
    run_id           : 8-char run identifier
    duration_seconds : wall-clock time for the full run
    model            : LLM model string used for this run
    agent_outputs    : dict of agent_name → AgentOutput (or dict)
    """
    ts    = datetime.now(timezone.utc).isoformat()
    price = _fetch_price(report.ticker)

    record = _build_rich_record(
        report, run_id, duration_seconds, model, agent_outputs, price, ts
    )

    # 1. Structured JSONL
    _append(RICH_LOG, json.dumps(record, default=str) + "\n")

    # 2. Human-readable plain text
    _append(READABLE_LOG, _build_readable_block(record))

    logger.info(
        "[analysis_logger] Logged run %s → %s & %s",
        run_id, RICH_LOG.name, READABLE_LOG.name,
    )

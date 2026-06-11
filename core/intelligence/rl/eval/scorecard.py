"""
core/intelligence/rl/eval/scorecard.py
=======================================
Monthly Scorecard + Baseline Duel — builder + table renderer (Phase 1,
spec 2026-06-12, section 5).

`build_scorecard(month)` is READ-ONLY over feedback logs, control logs, and
dossiers (auto-discovers tickers from `data/predictions/` like
`EvalHarness._load_real_pairs`). It reuses `eval/metrics.py` and
`eval/baselines.py` for every accuracy/brier/coverage formula — this module
adds no new math, only joins, lane bookkeeping, and rendering.

`save_scorecard(sc)` writes (and `build_scorecard` itself does not write —
callers decide when to persist) `{SCORECARD_DIR}/{YYYY-MM}_scorecard.json`,
the permanent improvement time series. `render_table(sc)` prints the
human-readable table from spec section 5.2.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path

from core.config import settings
from core.intelligence.rl.eval.baselines import (
    always_up_accuracy,
    persistence_accuracy,
)
from core.intelligence.rl.eval.harness import EvalHarness
from core.intelligence.rl.eval.metrics import (
    MatchedRecord,
    band_coverage,
    brier_score,
    direction_accuracy,
    mae_pct,
)
from core.intelligence.rl.stores.prediction_store import PredictionStore
from core.schemas.feedback import FeedbackEntry
from backend.shared.schemas.scorecard import LaneScore, MonthlyScorecard, TickerScorecard

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Ticker discovery — mirrors EvalHarness._load_real_pairs
# ---------------------------------------------------------------------------

def _discover_tickers(base_dir: Path) -> list[tuple[str, str]]:
    """Return [(ticker, sector), ...] for every ticker directory under base_dir."""
    found: list[tuple[str, str]] = []
    if not base_dir.exists():
        return found
    for sector_dir in sorted(p for p in base_dir.iterdir() if p.is_dir()):
        sector = sector_dir.name
        for ticker_dir in sorted(p for p in sector_dir.iterdir() if p.is_dir()):
            found.append((ticker_dir.name, sector))
    return found


# ---------------------------------------------------------------------------
# Per-ticker lane computation
# ---------------------------------------------------------------------------

def _agent_lane(
    entries: list[FeedbackEntry], records: list[MatchedRecord]
) -> LaneScore:
    if not entries:
        return LaneScore(n=0)
    return LaneScore(
        n=len(entries),
        direction_accuracy=direction_accuracy(entries),
        brier_score=brier_score(records) if records else None,
    )


def _control_lane(control_entries: list) -> LaneScore:
    """control_entries: list[ControlPrediction] already filtered to scored
    (correct is not None) entries."""
    if not control_entries:
        return LaneScore(n=0)
    n = len(control_entries)
    accuracy = sum(1 for e in control_entries if e.correct) / n
    brier = sum(
        (e.confidence - (1.0 if e.correct else 0.0)) ** 2 for e in control_entries
    ) / n
    return LaneScore(n=n, direction_accuracy=accuracy, brier_score=brier)


def _baseline_lane(entries: list[FeedbackEntry], fn) -> LaneScore:
    acc = fn(entries)
    if acc is None:
        return LaneScore(n=len(entries))
    return LaneScore(n=len(entries), direction_accuracy=acc)


def _edge(a: float | None, b: float | None) -> float | None:
    if a is None or b is None:
        return None
    return a - b


def _claim_split(entries: list[FeedbackEntry]) -> tuple[int, float | None, float | None]:
    claim_entries = [e for e in entries if e.claims_fired]
    other_entries = [e for e in entries if not e.claims_fired]
    claim_days = len(claim_entries)
    acc_claim = direction_accuracy(claim_entries) if claim_entries else None
    acc_other = direction_accuracy(other_entries) if other_entries else None
    return claim_days, acc_claim, acc_other


def _build_ticker_scorecard(
    ticker: str,
    sector: str,
    entries: list[FeedbackEntry],
    records: list[MatchedRecord],
    control_scored: list,
) -> TickerScorecard:
    agent = _agent_lane(entries, records)
    control = _control_lane(control_scored)
    persistence = _baseline_lane(entries, persistence_accuracy)
    always_up = _baseline_lane(entries, always_up_accuracy)

    claim_days, acc_claim, acc_other = _claim_split(entries)

    return TickerScorecard(
        ticker=ticker,
        sector=sector,
        agent=agent,
        control=control,
        persistence=persistence,
        always_up=always_up,
        band_coverage=band_coverage(records) if records else None,
        mae_pct=mae_pct(entries) if entries else None,
        edge_vs_control=_edge(agent.direction_accuracy, control.direction_accuracy),
        edge_vs_persistence=_edge(agent.direction_accuracy, persistence.direction_accuracy),
        claim_days=claim_days,
        accuracy_on_claim_days=acc_claim,
        accuracy_on_other_days=acc_other,
    )


# ---------------------------------------------------------------------------
# Builder
# ---------------------------------------------------------------------------

def build_scorecard(month: str, tickers: list[str] | None = None) -> MonthlyScorecard:
    """
    Build the monthly scorecard for `month` ("YYYY-MM").

    Read-only over `data/predictions/` (feedback logs, control logs,
    dossiers). Auto-discovers tickers like `EvalHarness._load_real_pairs`
    unless `tickers` is given (case-insensitive match against discovered
    tickers — sector is still resolved from the directory layout).

    Per-ticker failures are logged and the ticker is skipped; this function
    never raises.
    """
    base_dir = Path(settings.PREDICTION_DATA_DIR)

    discovered = _discover_tickers(base_dir)
    if tickers:
        wanted = {t.upper() for t in tickers}
        discovered = [(t, s) for t, s in discovered if t.upper() in wanted]

    sc = MonthlyScorecard(month=month, generated_at=datetime.now().isoformat())

    all_entries: list[FeedbackEntry] = []
    all_records: list[MatchedRecord] = []
    all_control_scored: list = []

    for ticker, sector in discovered:
        try:
            cycle_id = f"{ticker}_{month}"
            store = PredictionStore(ticker, sector=sector, base_dir=str(base_dir))

            feedback_log = store.load_feedback_log(cycle_id)
            entries = feedback_log.entries
            if not entries:
                continue

            envelope = store.load_envelope(cycle_id)
            records: list[MatchedRecord] = []
            if envelope is not None:
                records = EvalHarness._match_records(envelope, feedback_log)

            control_log = store.load_control_log(cycle_id)
            control_scored = [e for e in control_log.entries if e.correct is not None]

            ts = _build_ticker_scorecard(ticker, sector, entries, records, control_scored)

            # Dossier health snapshot.
            dossier = store.load_dossier()
            if dossier is not None:
                ts.dossier_version = dossier.version
                ts.dossier_observations = len(dossier.observations)
                ts.live_signatures = sum(
                    1 for s in dossier.response_signatures if s.is_alive
                )

            sc.tickers[ticker] = ts

            all_entries.extend(entries)
            all_records.extend(records)
            all_control_scored.extend(control_scored)
        except Exception as exc:
            logger.warning(
                "[scorecard] %s: failed to build ticker scorecard for %s (skipped): %s",
                ticker, month, exc,
            )
            continue

    # Aggregate — pooled across all tickers.
    aggregate = _build_ticker_scorecard("ALL", "all", all_entries, all_records, all_control_scored)
    if sc.tickers:
        total_obs = sum(
            t.dossier_observations for t in sc.tickers.values()
            if t.dossier_observations is not None
        )
        total_live = sum(
            t.live_signatures for t in sc.tickers.values()
            if t.live_signatures is not None
        )
        any_dossier = any(t.dossier_observations is not None for t in sc.tickers.values())
        if any_dossier:
            aggregate.dossier_observations = total_obs
            aggregate.live_signatures = total_live
    sc.aggregate = aggregate

    sc.deltas_vs_previous = _compute_deltas(sc, base_dir=base_dir)

    return sc


# ---------------------------------------------------------------------------
# Deltas vs previous month
# ---------------------------------------------------------------------------

_DELTA_METRICS: list[tuple[str, str]] = [
    ("agent", "direction_accuracy"),
    ("agent", "brier_score"),
    (None, "band_coverage"),
    (None, "mae_pct"),
    (None, "edge_vs_control"),
]


def _previous_month(month: str) -> str:
    year, mon = (int(p) for p in month.split("-"))
    if mon == 1:
        return f"{year - 1}-12"
    return f"{year}-{mon - 1:02d}"


def _scorecard_path(month: str) -> Path:
    return Path(settings.SCORECARD_DIR) / f"{month}_scorecard.json"


def _get_metric(ts: TickerScorecard | None, lane: str | None, metric: str) -> float | None:
    if ts is None:
        return None
    if lane is None:
        return getattr(ts, metric, None)
    lane_obj = getattr(ts, lane, None)
    if lane_obj is None:
        return None
    return getattr(lane_obj, metric, None)


def _compute_deltas(sc: MonthlyScorecard, base_dir: Path) -> dict[str, float]:
    prev_path = _scorecard_path(_previous_month(sc.month))
    if not prev_path.exists():
        return {}

    try:
        prev_data = json.loads(prev_path.read_text(encoding="utf-8"))
        prev_sc = MonthlyScorecard(**prev_data)
    except Exception as exc:
        logger.warning("[scorecard] failed to load previous scorecard %s: %s", prev_path, exc)
        return {}

    deltas: dict[str, float] = {}
    for lane, metric in _DELTA_METRICS:
        this_val = _get_metric(sc.aggregate, lane, metric)
        prev_val = _get_metric(prev_sc.aggregate, lane, metric)
        if this_val is None or prev_val is None:
            continue
        key = f"{lane}.{metric}" if lane else metric
        deltas[key] = this_val - prev_val

    return deltas


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------

def save_scorecard(sc: MonthlyScorecard) -> Path:
    """Write {SCORECARD_DIR}/{month}_scorecard.json atomically. Returns the path."""
    out_dir = Path(settings.SCORECARD_DIR)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{sc.month}_scorecard.json"
    tmp = path.with_suffix(".tmp")
    tmp.write_text(
        json.dumps(sc.model_dump(), indent=2, ensure_ascii=False), encoding="utf-8"
    )
    tmp.replace(path)
    return path


# ---------------------------------------------------------------------------
# Table renderer
# ---------------------------------------------------------------------------

def _fmt_pct(value: float | None) -> str:
    return f"{value * 100:.1f}%" if value is not None else "—"


def _fmt_brier(value: float | None) -> str:
    return f"{value:.3f}" if value is not None else "—"


def _fmt_pp(value: float) -> str:
    return f"{value * 100:+.1f}pp"


def render_table(sc: MonthlyScorecard) -> str:
    """Render the human-readable table from spec section 5.2."""
    lines: list[str] = []

    header = f"SCORECARD {sc.month}"
    if sc.deltas_vs_previous:
        header += f" (vs {_previous_month(sc.month)})"
    lines.append(header)

    agg = sc.aggregate
    lines.append(f"{'lane':<12} {'accuracy':>9} {'brier':>8}    n")

    def _lane_line(name: str, lane: LaneScore, edge: float | None = None,
                    delta_key: str | None = None) -> str:
        line = (
            f"{name:<12} {_fmt_pct(lane.direction_accuracy):>9} "
            f"{_fmt_brier(lane.brier_score):>8} {lane.n:>4}"
        )
        annotations = []
        if delta_key is not None and delta_key in sc.deltas_vs_previous:
            annotations.append(f"({_fmt_pp(sc.deltas_vs_previous[delta_key])} vs prev month)")
        if edge is not None:
            annotations.append(f"-> edge {_fmt_pp(edge)}")
        if annotations:
            line += "   " + " ".join(annotations)
        return line

    if agg is not None:
        lines.append(_lane_line("agent", agg.agent, delta_key="agent.direction_accuracy"))
        lines.append(_lane_line("control LLM", agg.control, edge=agg.edge_vs_control))
        lines.append(_lane_line("persistence", agg.persistence, edge=agg.edge_vs_persistence))
        lines.append(_lane_line("always-up", agg.always_up))

        if agg.claim_days:
            claim_acc = _fmt_pct(agg.accuracy_on_claim_days)
            other_acc = _fmt_pct(agg.accuracy_on_other_days)
            lines.append(
                f"claims: fired on {agg.claim_days} days — "
                f"{claim_acc} on claim days vs {other_acc} other days"
            )
        else:
            lines.append("claims: fired on 0 days")

        if agg.dossier_observations is not None:
            version_str = f"v{agg.dossier_version}, " if agg.dossier_version is not None else ""
            lines.append(
                f"dossier: {version_str}{agg.dossier_observations} observations, "
                f"{agg.live_signatures} live signatures"
            )

    return "\n".join(lines)

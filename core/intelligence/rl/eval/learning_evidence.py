"""
core/intelligence/rl/eval/learning_evidence.py
===============================================
Learning Evidence Report -- the self-ablation experiment (design doc
docs/superpowers/specs/2026-07-19-learning-evidence-design.md; scientific
motivation in docs/audit/ADAPTIVE_LEARNING_REVIEW.md).

Answers, with sample sizes and significance, the question the scorecard
never asks: *does the adaptive layer beat the same system with learning
switched off?* Five sections:

  1. Counterfactual weight replay -- every logged day's frozen
     `predicted_agent_scores` re-decided under ADAPTED (weights active
     strictly before that date) vs BASE (engineered priors) vs UNIFORM
     weights, through the same deterministic verdict map the shadow lane
     uses. Divergence rate + paired lift + exact sign-test p-value.
  2. Signal health -- credit-degeneracy index (how often the hit-credit
     rule hands every agent identical credit -> zero learning signal) and
     weight-entropy / poverty-trap diagnostics per ticker.
  3. Lesson efficacy -- per-lesson fired-day vs non-fired-day accuracy.
  4. Calibration -- Brier decomposition (reliability − resolution +
     uncertainty) over stated-confidence records.
  5. Actuation coupling -- LLM verdict vs threshold verdict divergence
     from the AUD-077 shadow lane.

READ-ONLY over data/predictions and data/rl. No LLM calls -- fully
deterministic and retroactively computable. Caveat embedded in every
report: production verdicts are LLM-emitted; the replay isolates the
weight loop's effect through the deterministic decision channel (the
hard-bind candidate), not through the LLM's attention.

CLI:
    python -m core.intelligence.rl.eval.learning_evidence --month 2026-06
    python -m core.intelligence.rl.eval.learning_evidence --month 2026-06 --months-back 3 --email
"""
from __future__ import annotations

import json
import logging
import math
from datetime import datetime
from pathlib import Path

from core.config import settings
from core.intelligence.rl.eval.metrics import MatchedRecord
from core.intelligence.rl.stores.prediction_store import PredictionStore
from core.schemas.feedback import FeedbackEntry, WeightMemory

logger = logging.getLogger(__name__)

# Minimum replayed days before any verdict at all.
MIN_REPLAYED_DAYS = 10
# Minimum divergent days before any directional claim about the learning loop.
MIN_DIVERGENT_DAYS = 10
# Below this divergence rate the weight loop is not influencing decisions.
INERT_DIVERGENCE_RATE = 0.02
# Two-sided sign-test significance level for the beneficial/harmful call.
SIGNIFICANCE_LEVEL = 0.10
# Minimum fired/unfired days before a lesson's lift is trusted.
LESSON_MIN_N = 5


# ---------------------------------------------------------------------------
# Statistics helpers (pure, stdlib only)
# ---------------------------------------------------------------------------

def wilson_interval(hits: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """Wilson score 95% interval for a binomial proportion. (0,1) when n=0."""
    if n <= 0:
        return (0.0, 1.0)
    p = hits / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    margin = (z / denom) * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return (max(0.0, centre - margin), min(1.0, centre + margin))


def sign_test_p(k: int, n: int) -> float:
    """Exact two-sided sign test (binomial, p=0.5) over n discordant pairs.

    `k` is the count of the rarer outcome. Returns 1.0 when n == 0 (no
    evidence either way).
    """
    if n <= 0:
        return 1.0
    k = min(k, n - k)
    tail = sum(math.comb(n, i) for i in range(k + 1)) * 0.5 ** n
    return min(1.0, 2 * tail)


def brier_decomposition(records: list[MatchedRecord]) -> dict:
    """Murphy decomposition over confidence deciles: brier = REL − RES + UNC.

    Exact when within-bin confidence is constant; with decile bins the
    small within-bin variance residual is folded into reliability, which is
    the standard practical treatment.
    """
    from core.intelligence.rl.eval.metrics import _decile_bucket

    n = len(records)
    if n == 0:
        return {"n": 0, "brier": None, "reliability": None,
                "resolution": None, "uncertainty": None}

    bins: dict[str, list[MatchedRecord]] = {}
    for r in records:
        bins.setdefault(_decile_bucket(r.confidence), []).append(r)

    base_rate = sum(1.0 for r in records if r.direction_correct) / n
    reliability = 0.0
    resolution = 0.0
    for recs in bins.values():
        nk = len(recs)
        conf_k = sum(r.confidence for r in recs) / nk
        hit_k = sum(1.0 for r in recs if r.direction_correct) / nk
        reliability += nk * (conf_k - hit_k) ** 2
        resolution += nk * (hit_k - base_rate) ** 2
    reliability /= n
    resolution /= n
    uncertainty = base_rate * (1 - base_rate)
    return {
        "n": n,
        "brier": round(reliability - resolution + uncertainty, 6),
        "reliability": round(reliability, 6),
        "resolution": round(resolution, 6),
        "uncertainty": round(uncertainty, 6),
    }


# ---------------------------------------------------------------------------
# Weight reconstruction + composite
# ---------------------------------------------------------------------------

def weights_before(history: list, base_weights: dict, date_str: str) -> dict:
    """Weights active strictly before `date_str`.

    The forecast reviewed on day D was produced before D's review updated
    the weights, so the causally-correct lane uses the last
    WeightHistoryEntry dated strictly before D; with none, the base
    weights.
    """
    chosen = base_weights
    for entry in history:
        if entry.date < date_str:
            chosen = entry.weights
        else:
            break
    return chosen


def composite_for(scores: dict, weights: dict) -> float:
    """Weighted mean of agent scores, renormalised over agents present.

    Mirrors SignalAggregator's composite (weighted sum / weight total over
    scored agents). Zero weight overlap falls back to the simple mean --
    the same neutral treatment the aggregator gives an all-errored day.
    """
    total_w = 0.0
    total = 0.0
    for agent, score in scores.items():
        w = weights.get(agent, 0.0)
        total += score * w
        total_w += w
    if total_w <= 0:
        return sum(scores.values()) / len(scores) if scores else 0.5
    return max(0.0, min(1.0, total / total_w))


# ---------------------------------------------------------------------------
# Section 1 -- counterfactual weight replay
# ---------------------------------------------------------------------------

def _lane_correct(composite: float, actual_direction: str) -> bool:
    from backend.shared.pipeline.verdict_shadow import verdict_from_composite
    from core.intelligence.rl.agents.feedback_agent import is_direction_correct

    return is_direction_correct(verdict_from_composite(composite), actual_direction)


def replay_ticker(entries: list[FeedbackEntry], wm: WeightMemory | None) -> dict:
    """Replay one ticker's entries under ADAPTED / BASE / UNIFORM weights.

    Entries without stored `predicted_agent_scores` cannot be replayed and
    are counted in `n_skipped`. A ticker without weight memory has no
    learning state: both ADAPTED and BASE collapse to settings.AGENT_WEIGHTS
    (zero divergence -- which is the honest reading).
    """
    lanes = {name: {"n": 0, "hits": 0} for name in ("adapted", "base", "uniform")}
    out = {
        "n_replayed": 0,
        "n_skipped": 0,
        "lanes": lanes,
        "divergent_vs_base": 0,
        "adapted_wins_vs_base": 0,
        "base_wins_vs_adapted": 0,
        "divergent_vs_uniform": 0,
        "adapted_wins_vs_uniform": 0,
        "uniform_wins_vs_adapted": 0,
    }

    base_w = wm.base_weights if wm is not None else dict(settings.AGENT_WEIGHTS)
    history = wm.weight_history if wm is not None else []

    for entry in entries:
        scores = entry.predicted_agent_scores
        if not scores:
            out["n_skipped"] += 1
            continue

        adapted_w = weights_before(history, base_w, entry.date)
        uniform_w = {a: 1.0 / len(scores) for a in scores}

        results = {}
        for name, w in (("adapted", adapted_w), ("base", base_w), ("uniform", uniform_w)):
            correct = _lane_correct(composite_for(scores, w), entry.actual_direction)
            lanes[name]["n"] += 1
            lanes[name]["hits"] += 1 if correct else 0
            results[name] = correct

        out["n_replayed"] += 1
        if results["adapted"] != results["base"]:
            out["divergent_vs_base"] += 1
            if results["adapted"]:
                out["adapted_wins_vs_base"] += 1
            else:
                out["base_wins_vs_adapted"] += 1
        if results["adapted"] != results["uniform"]:
            out["divergent_vs_uniform"] += 1
            if results["adapted"]:
                out["adapted_wins_vs_uniform"] += 1
            else:
                out["uniform_wins_vs_adapted"] += 1

    return out


def _merge_replays(replays: list[dict]) -> dict:
    merged = {
        "n_replayed": 0,
        "n_skipped": 0,
        "lanes": {name: {"n": 0, "hits": 0} for name in ("adapted", "base", "uniform")},
    }
    keys = [
        "divergent_vs_base", "adapted_wins_vs_base", "base_wins_vs_adapted",
        "divergent_vs_uniform", "adapted_wins_vs_uniform", "uniform_wins_vs_adapted",
    ]
    for k in keys:
        merged[k] = 0
    for r in replays:
        merged["n_replayed"] += r["n_replayed"]
        merged["n_skipped"] += r["n_skipped"]
        for name in merged["lanes"]:
            merged["lanes"][name]["n"] += r["lanes"][name]["n"]
            merged["lanes"][name]["hits"] += r["lanes"][name]["hits"]
        for k in keys:
            merged[k] += r[k]

    for name, lane in merged["lanes"].items():
        n, hits = lane["n"], lane["hits"]
        lane["accuracy"] = round(hits / n, 4) if n else None
        lo, hi = wilson_interval(hits, n)
        lane["wilson_95"] = [round(lo, 4), round(hi, 4)]

    def _pair(n_div, wins, losses):
        return {
            "n_divergent": n_div,
            "adapted_wins": wins,
            "base_wins": losses,
            "lift_pp": round((wins - losses) / n_div * 100, 2) if n_div else None,
            "p_value": round(sign_test_p(min(wins, losses), wins + losses), 6),
        }

    merged["adapted_vs_base"] = _pair(
        merged["divergent_vs_base"],
        merged["adapted_wins_vs_base"],
        merged["base_wins_vs_adapted"],
    )
    merged["adapted_vs_uniform"] = _pair(
        merged["divergent_vs_uniform"],
        merged["adapted_wins_vs_uniform"],
        merged["uniform_wins_vs_adapted"],
    )
    return merged


# ---------------------------------------------------------------------------
# Section 2 -- learning-signal health
# ---------------------------------------------------------------------------

def credit_degeneracy_index(entries: list[FeedbackEntry]) -> float:
    """Fraction of multi-agent days where hit-credit is identical for every
    agent -- days on which the weight loop's update signal carries zero
    inter-agent information (review doc G2)."""
    from core.intelligence.rl.agents.weight_adapter import agent_hit_credit

    eligible = 0
    degenerate = 0
    for entry in entries:
        agents = list(entry.predicted_agent_scores)
        if len(agents) < 2:
            continue
        eligible += 1
        credits = {agent_hit_credit(entry, a) for a in agents}
        if len(credits) == 1:
            degenerate += 1
    return round(degenerate / eligible, 4) if eligible else 0.0


def _norm_entropy(weights: dict) -> float:
    vals = [w for w in weights.values() if w > 0]
    total = sum(vals)
    if total <= 0 or len(weights) < 2:
        return 0.0
    h = -sum((w / total) * math.log(w / total) for w in vals)
    return round(h / math.log(len(weights)), 6)


def _uniform_distance(weights: dict) -> float:
    n = len(weights)
    if n == 0:
        return 0.0
    total = sum(weights.values()) or 1.0
    u = 1.0 / n
    return round(0.5 * sum(abs(w / total - u) for w in weights.values()), 6)


def weight_health(wm: WeightMemory) -> dict:
    """Entropy / uniformity diagnostics for one ticker's weight state.

    `poverty_trapped`: agents below half the uniform share -- under the
    prop_scale floor they receive quarter-sized boosts and cannot recover
    (review doc G3).
    """
    n = max(1, len(wm.current_weights))
    uniform = 1.0 / n
    trapped = sorted(
        a for a, w in wm.current_weights.items() if w < 0.5 * uniform
    )
    return {
        "entropy_base": _norm_entropy(wm.base_weights),
        "entropy_current": _norm_entropy(wm.current_weights),
        "uniform_distance_base": _uniform_distance(wm.base_weights),
        "uniform_distance_current": _uniform_distance(wm.current_weights),
        "n_weight_versions": wm.weight_version,
        "poverty_trapped": trapped,
    }


# ---------------------------------------------------------------------------
# Section 3 -- lesson efficacy
# ---------------------------------------------------------------------------

def lesson_efficacy(entries: list[FeedbackEntry]) -> dict:
    """Per-lesson fired-day vs non-fired-day accuracy over one ticker's
    entries. Uses the recorded `direction_correct` (the production reward
    signal -- inherits its pre-2026-07-17 NEUTRAL inflation for old months).
    """
    lesson_ids: set[str] = set()
    for e in entries:
        lesson_ids.update(e.claims_fired)

    table: dict[str, dict] = {}
    for lid in sorted(lesson_ids):
        fired = [e for e in entries if lid in e.claims_fired]
        unfired = [e for e in entries if lid not in e.claims_fired]
        fired_n, unfired_n = len(fired), len(unfired)
        fired_acc = sum(1 for e in fired if e.direction_correct) / fired_n if fired_n else None
        unfired_acc = (
            sum(1 for e in unfired if e.direction_correct) / unfired_n if unfired_n else None
        )
        lift_pp = (
            round((fired_acc - unfired_acc) * 100, 2)
            if fired_acc is not None and unfired_acc is not None
            else None
        )
        sufficient = fired_n >= LESSON_MIN_N and unfired_n >= LESSON_MIN_N
        table[lid] = {
            "fired_n": fired_n,
            "fired_accuracy": round(fired_acc, 4) if fired_acc is not None else None,
            "unfired_n": unfired_n,
            "unfired_accuracy": round(unfired_acc, 4) if unfired_acc is not None else None,
            "lift_pp": lift_pp,
            "sufficient": sufficient,
            "harmful": bool(sufficient and lift_pp is not None and lift_pp < 0),
        }
    return table


# ---------------------------------------------------------------------------
# Section 5 -- actuation coupling (shadow lane)
# ---------------------------------------------------------------------------

def actuation_stats(path: Path | str | None = None, months: list[str] | None = None) -> dict:
    """Divergence stats from data/rl/verdict_shadow.jsonl. Tolerates a
    missing/corrupt file (returns zeros) -- the lane only exists since
    2026-07-17."""
    p = Path(path) if path else Path("data") / "rl" / "verdict_shadow.jsonl"
    rows: list[dict] = []
    if p.exists():
        for line in p.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            if months and rec.get("ts", "")[:7] not in months:
                continue
            rows.append(rec)

    n = len(rows)
    diverged = sum(1 for r in rows if r.get("diverged"))
    learned = sum(1 for r in rows if r.get("learned_weights_used"))
    return {
        "shadow_rows": n,
        "divergence_rate": round(diverged / n, 4) if n else None,
        "learned_weight_rows": learned,
    }


# ---------------------------------------------------------------------------
# Verdict
# ---------------------------------------------------------------------------

def decide_verdict(replay: dict) -> tuple[str, str]:
    """Map the pooled replay section onto the four-way learning verdict."""
    avb = replay.get("adapted_vs_base", {})
    n_div = avb.get("n_divergent", 0)
    n_replayed = replay.get("n_replayed", 0)

    if n_replayed < MIN_REPLAYED_DAYS:
        return (
            "INSUFFICIENT_DATA",
            f"only {n_replayed} replayed days (need {MIN_REPLAYED_DAYS}) "
            "-- no claim possible yet",
        )
    if n_div / n_replayed < INERT_DIVERGENCE_RATE:
        return (
            "LEARNING_INERT",
            f"adapted weights changed the decision on only {n_div}/{n_replayed} days "
            f"(<{INERT_DIVERGENCE_RATE:.0%}) -- the weight loop is not influencing decisions",
        )
    if n_div < MIN_DIVERGENT_DAYS:
        return (
            "INSUFFICIENT_DATA",
            f"only {n_div} divergent days (need {MIN_DIVERGENT_DAYS}) "
            f"over {n_replayed} replayed days -- no win/loss claim possible yet",
        )
    p = avb.get("p_value", 1.0)
    wins, losses = avb.get("adapted_wins", 0), avb.get("base_wins", 0)
    if p < SIGNIFICANCE_LEVEL and wins > losses:
        return (
            "LEARNING_ACTIVE_BENEFICIAL",
            f"adapted beat frozen-base on divergent days {wins}-{losses} (p={p:.4f})",
        )
    if p < SIGNIFICANCE_LEVEL and losses > wins:
        return (
            "LEARNING_ACTIVE_HARMFUL",
            f"frozen-base beat adapted on divergent days {losses}-{wins} (p={p:.4f}) "
            "-- the learning loop is destroying value; freeze or fix it",
        )
    return (
        "LEARNING_ACTIVE_UNPROVEN",
        f"decisions diverge ({n_div} days) but the split {wins}-{losses} "
        f"is not distinguishable from chance (p={p:.4f})",
    )


# ---------------------------------------------------------------------------
# Builder
# ---------------------------------------------------------------------------

def _discover_tickers(base_dir: Path) -> list[tuple[str, str]]:
    found: list[tuple[str, str]] = []
    if not base_dir.exists():
        return found
    for sector_dir in sorted(p for p in base_dir.iterdir() if p.is_dir()):
        for ticker_dir in sorted(p for p in sector_dir.iterdir() if p.is_dir()):
            found.append((ticker_dir.name, sector_dir.name))
    return found


def build_learning_evidence(
    months: list[str], base_dir: Path | str | None = None
) -> dict:
    """Build the Learning Evidence Report over `months` (["YYYY-MM", ...]).

    Read-only. Per-ticker failures are logged and skipped; never raises.
    """
    base = Path(base_dir) if base_dir else Path(settings.PREDICTION_DATA_DIR)
    months = sorted(months)

    replays: list[dict] = []
    all_entries: list[FeedbackEntry] = []
    all_records: list[MatchedRecord] = []
    ticker_health: dict[str, dict] = {}
    lessons: dict[str, dict] = {}

    for ticker, sector in _discover_tickers(base):
        try:
            store = PredictionStore(ticker, sector=sector, base_dir=str(base))
            wm = store.load_weight_memory()
            ticker_entries: list[FeedbackEntry] = []

            for month in months:
                cycle_id = f"{ticker}_{month}"
                log = store.load_feedback_log(cycle_id)
                if not log.entries:
                    continue
                ticker_entries.extend(log.entries)

                envelope = store.load_envelope(cycle_id)
                if envelope is not None:
                    from core.intelligence.rl.eval.harness import EvalHarness
                    all_records.extend(EvalHarness._match_records(envelope, log))

            if not ticker_entries:
                continue

            replays.append(replay_ticker(ticker_entries, wm))
            all_entries.extend(ticker_entries)

            if wm is not None:
                ticker_health[ticker] = weight_health(wm)

            for lid, row in lesson_efficacy(ticker_entries).items():
                key = lid if lid not in lessons else f"{lid}@{ticker}"
                lessons[key] = {**row, "ticker": ticker}
        except Exception as exc:
            logger.warning(
                "[learning_evidence] %s: skipped (failed to load/replay): %s", ticker, exc
            )
            continue

    replay = _merge_replays(replays)
    verdict, reason = decide_verdict(replay)

    return {
        "months": months,
        "generated_at": datetime.now().isoformat(),
        "caveat": (
            "Production verdicts are LLM-emitted; this replay isolates the weight "
            "loop's effect through the deterministic composite->threshold decision "
            "channel (the hard-bind candidate), not through the LLM's attention. "
            "direction_correct for months before 2026-07-17 carries the NEUTRAL "
            "auto-hit inflation (AUD-060)."
        ),
        "replay": replay,
        "signal_health": {
            "credit_degeneracy_index": credit_degeneracy_index(all_entries),
            "tickers": ticker_health,
        },
        "lesson_efficacy": {
            "lessons": lessons,
            "n_lessons_scored": len(lessons),
            "n_harmful": sum(1 for r in lessons.values() if r["harmful"]),
        },
        "calibration": brier_decomposition(all_records),
        "actuation": actuation_stats(months=months),
        "verdict": verdict,
        "verdict_reason": reason,
    }


# ---------------------------------------------------------------------------
# Persistence + renderer
# ---------------------------------------------------------------------------

def save_report(report: dict) -> tuple[Path, Path]:
    """Write {LEARNING_EVIDENCE_DIR}/{last-month}_evidence.{json,txt}
    atomically. Returns (json_path, txt_path)."""
    out_dir = Path(getattr(settings, "LEARNING_EVIDENCE_DIR", "data/eval/learning_evidence"))
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = f"{report['months'][-1]}_evidence"

    json_path = out_dir / f"{stem}.json"
    tmp = json_path.with_suffix(".tmp")
    tmp.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(json_path)

    txt_path = out_dir / f"{stem}.txt"
    tmp = txt_path.with_suffix(".txt.tmp")
    tmp.write_text(render_report(report), encoding="utf-8")
    tmp.replace(txt_path)
    return json_path, txt_path


def _fmt_pct(v) -> str:
    return f"{v * 100:.1f}%" if v is not None else "--"


def render_report(report: dict) -> str:
    """Human-readable report -- the text that lands in the monthly email."""
    lines: list[str] = []
    months = report["months"]
    lines.append(f"LEARNING EVIDENCE -- {months[0]}..{months[-1]}" if len(months) > 1
                 else f"LEARNING EVIDENCE -- {months[0]}")
    lines.append("")
    lines.append(f"VERDICT: {report['verdict']}")
    lines.append(f"  {report['verdict_reason']}")
    lines.append("")

    r = report["replay"]
    lines.append(f"1. Counterfactual weight replay ({r['n_replayed']} days replayed, "
                 f"{r['n_skipped']} skipped -- no stored agent scores)")
    for name in ("adapted", "base", "uniform"):
        lane = r["lanes"][name]
        ci = lane.get("wilson_95") or [None, None]
        ci_str = f" [{_fmt_pct(ci[0])},{_fmt_pct(ci[1])}]" if lane["n"] else ""
        lines.append(f"   {name:<8} {_fmt_pct(lane.get('accuracy'))}{ci_str}  n={lane['n']}")
    for label, key in (("vs frozen base", "adapted_vs_base"),
                       ("vs uniform", "adapted_vs_uniform")):
        pair = r[key]
        lines.append(
            f"   {label}: diverged {pair['n_divergent']} days, "
            f"adapted {pair['adapted_wins']}-{pair['base_wins']}, "
            f"lift {pair['lift_pp']}pp, p={pair['p_value']}"
        )
    lines.append("")

    sh = report["signal_health"]
    lines.append(f"2. Signal health -- credit-degeneracy index "
                 f"{_fmt_pct(sh['credit_degeneracy_index'])} of days carry zero "
                 "inter-agent learning signal")
    for ticker, h in sorted(sh["tickers"].items()):
        trap = f" TRAPPED: {','.join(h['poverty_trapped'])}" if h["poverty_trapped"] else ""
        lines.append(
            f"   {ticker:<12} entropy {h['entropy_base']:.3f}->{h['entropy_current']:.3f} "
            f"(1.0=uniform/no information), v{h['n_weight_versions']}{trap}"
        )
    lines.append("")

    lef = report["lesson_efficacy"]
    lines.append(f"3. Lesson efficacy -- {lef['n_lessons_scored']} lessons scored, "
                 f"{lef['n_harmful']} harmful")
    ranked = sorted(
        (item for item in lef["lessons"].items() if item[1]["lift_pp"] is not None),
        key=lambda kv: kv[1]["lift_pp"],
    )
    for lid, row in ranked[:10]:
        flag = " HARMFUL" if row["harmful"] else ("" if row["sufficient"] else " (low n)")
        lines.append(
            f"   {lid:<14} ({row['ticker']}) fired {row['fired_n']}d "
            f"{_fmt_pct(row['fired_accuracy'])} vs unfired "
            f"{_fmt_pct(row['unfired_accuracy'])} -> lift {row['lift_pp']}pp{flag}"
        )
    lines.append("")

    cal = report["calibration"]
    if cal["n"]:
        lines.append(
            f"4. Calibration (n={cal['n']}) -- brier {cal['brier']} = reliability "
            f"{cal['reliability']} - resolution {cal['resolution']} + uncertainty "
            f"{cal['uncertainty']}  (resolution ~0 means stated confidence does not "
            "distinguish outcomes)"
        )
    else:
        lines.append("4. Calibration -- no matched confidence records this period")

    act = report["actuation"]
    if act["shadow_rows"]:
        lines.append(
            f"5. Actuation (shadow lane) -- {act['shadow_rows']} rows, LLM diverged from "
            f"threshold verdict on {_fmt_pct(act['divergence_rate'])} "
            f"({act['learned_weight_rows']} rows used learned weights)"
        )
    else:
        lines.append("5. Actuation -- no shadow-lane rows in this period")

    lines.append("")
    lines.append(f"Caveat: {report['caveat']}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _previous_month(today=None) -> str:
    from datetime import date

    d = today or date.today()
    year, month = (d.year, d.month - 1) if d.month > 1 else (d.year - 1, 12)
    return f"{year}-{month:02d}"


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Build the Learning Evidence Report")
    parser.add_argument("--month", default=_previous_month(),
                        help="Last month to include, YYYY-MM (default: previous month)")
    parser.add_argument("--months-back", type=int, default=1,
                        help="How many months ending at --month (default 1)")
    parser.add_argument("--data-dir", default=None,
                        help="Override predictions dir (default settings.PREDICTION_DATA_DIR)")
    parser.add_argument("--email", action="store_true",
                        help="Email the rendered report via the delivery channel")
    args = parser.parse_args(argv)

    year, mon = (int(p) for p in args.month.split("-"))
    months = []
    for _ in range(max(1, args.months_back)):
        months.append(f"{year}-{mon:02d}")
        year, mon = (year, mon - 1) if mon > 1 else (year - 1, 12)
    months.reverse()

    report = build_learning_evidence(months, base_dir=args.data_dir)
    json_path, txt_path = save_report(report)
    text = render_report(report)
    print(text)
    print(f"\nSaved: {json_path} / {txt_path}")

    if args.email:
        from core.delivery.channels import send_email

        sent = send_email(
            subject=f"[StockAgent] Learning Evidence {months[-1]}: {report['verdict']}",
            body=text,
        )
        print(f"Email sent: {sent}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

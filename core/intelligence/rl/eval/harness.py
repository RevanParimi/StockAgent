"""
core/intelligence/rl/eval/harness.py
=====================================
EvalHarness — load -> replay -> aggregate -> EvalReport.

This module is the only piece of Component 1 that touches I/O, and it is
**read-only**: real data is loaded via `PredictionStore.load_envelope` /
`load_feedback_log`, never written back. Synthetic data comes from
`SyntheticLogGenerator` and lives only in memory.

After loading, real and synthetic data share one code path: both become
lists of `(PredictionEnvelope, DailyFeedbackLog)` pairs, which are joined
into `MatchedRecord`s and `FeedbackEntry` lists and fed to the pure functions
in `metrics.py`.

Ablation
--------
`ABLATION_REGISTRY` maps an ablation key to the settings attribute name that
(eventually) controls it. Components 2/3 haven't landed yet, so
`getattr(settings, name, True)` is used everywhere the flag value matters —
the registry works today and keeps working once the real settings exist.

Per the coordinator decision (design spec Component 1 / ablation):
  - **Synthetic** runs: the generator re-simulates the same seed with the
    flag conceptually "off" (see `synthetic.py`'s ablation model) and the
    harness reports the delta in `direction_accuracy` and `brier_score`
    (baseline-with-feature minus ablated-without-feature).
  - **Real** recorded logs: ablation is a no-op. Recorded history cannot be
    re-run with a different flag, so the harness logs a warning and omits
    `ablation_deltas` for that key.
"""
from __future__ import annotations

import logging
from datetime import date, datetime
from pathlib import Path

from pydantic import BaseModel, Field

from core.config import settings
from core.schemas.feedback import DailyFeedbackLog, FeedbackEntry, PredictionEnvelope
from core.intelligence.rl.eval.metrics import (
    MatchedRecord,
    band_coverage,
    brier_score,
    direction_accuracy,
    mae_pct,
    reliability_table,
)
from core.intelligence.rl.eval.synthetic import SyntheticLogGenerator
from core.intelligence.rl.stores.prediction_store import PredictionStore

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Ablation registry — see module docstring.
# ---------------------------------------------------------------------------
ABLATION_REGISTRY: dict[str, str] = {
    "calibration_reward": "RL_CALIBRATION_REWARD_ENABLED",
    "forgetting": "RL_FORGETTING_ENABLED",
    "executable_claims": "RL_CLAIMS_ENABLED",
}


# ---------------------------------------------------------------------------
# EvalReport
# ---------------------------------------------------------------------------

class EvalReport(BaseModel):
    """
    Output of `EvalHarness.run_eval()`.

    `aggregate`, `per_ticker`, and `per_sector` all hold the same metric
    dict shape: {direction_accuracy, brier_score, reliability_table,
    band_coverage, mae_pct, n_entries}.
    """
    generated_at: str = Field(default_factory=lambda: datetime.now().isoformat())
    source: str                                    # "synthetic" | "real"
    n_entries: int = 0
    aggregate: dict = Field(default_factory=dict)
    per_ticker: dict[str, dict] = Field(default_factory=dict)
    per_sector: dict[str, dict] = Field(default_factory=dict)
    ablations_run: list[str] = Field(default_factory=list)
    # ablation_key -> {"direction_accuracy_delta": float, "brier_score_delta": float}
    # Absent / None entry for keys where ablation is a no-op (real data).
    ablation_deltas: dict[str, dict | None] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# EvalHarness
# ---------------------------------------------------------------------------

class EvalHarness:
    """
    Replays prediction + feedback history and emits hard metrics.

    Read-only: never writes to `data/predictions` and never mutates
    settings. `base_dir` overrides the predictions root (defaults to
    `settings.PREDICTION_DATA_DIR`), useful for pointing tests at a fixture
    directory.
    """

    def __init__(self, base_dir: str | None = None) -> None:
        self._base_dir = Path(base_dir or settings.PREDICTION_DATA_DIR)

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    def run_eval(
        self,
        synthetic: bool = False,
        ablate: list[str] | None = None,
        n_tickers: int = 4,
        n_cycles: int = 1,
        accuracy_rate: float = 0.6,
        vol: float = 1.0,
        seed: int = 42,
    ) -> EvalReport:
        """
        Run the evaluation harness.

        Parameters
        ----------
        synthetic : bool
            If True, fabricate data via `SyntheticLogGenerator(seed)`.
            If False, auto-discover real data under `data/predictions/`.
        ablate : list[str] | None
            Ablation keys (see `ABLATION_REGISTRY`). Synthetic runs report
            a delta per key; real runs log a warning and report no delta.
        n_tickers, n_cycles, accuracy_rate, vol, seed : synthetic-only knobs,
            forwarded to `SyntheticLogGenerator.generate()`.
        """
        ablate = ablate or []

        if synthetic:
            pairs = SyntheticLogGenerator(seed=seed).generate(
                n_tickers=n_tickers, n_cycles=n_cycles,
                accuracy_rate=accuracy_rate, vol=vol,
            )
            source = "synthetic"
        else:
            pairs = self._load_real_pairs()
            source = "real"

        report = self._build_report(pairs, source=source)

        for key in ablate:
            report.ablations_run.append(key)
            settings_attr = ABLATION_REGISTRY.get(key)
            if settings_attr is not None:
                # Touch the (possibly not-yet-existent) settings attr so the
                # registry is exercised end-to-end, per spec instructions.
                getattr(settings, settings_attr, True)

            if not synthetic:
                logger.warning(
                    "[EvalHarness] Ablation '%s' is a no-op for real recorded "
                    "history — recorded logs cannot be re-run. Reporting no delta.",
                    key,
                )
                report.ablation_deltas[key] = None
                continue

            report.ablation_deltas[key] = self._synthetic_ablation_delta(
                key=key,
                baseline_aggregate=report.aggregate,
                n_tickers=n_tickers,
                n_cycles=n_cycles,
                accuracy_rate=accuracy_rate,
                vol=vol,
                seed=seed,
            )

        return report

    # ------------------------------------------------------------------
    # Real data discovery (read-only)
    # ------------------------------------------------------------------

    def _load_real_pairs(self) -> list[tuple[PredictionEnvelope, DailyFeedbackLog]]:
        """
        Auto-discover `data/predictions/{sector}/{ticker}/*_daily_feedback_log.json`
        and the matching `*_prediction_envelope.json`, loaded via
        `PredictionStore` (read-only).
        """
        pairs: list[tuple[PredictionEnvelope, DailyFeedbackLog]] = []

        if not self._base_dir.exists():
            return pairs

        for sector_dir in sorted(p for p in self._base_dir.iterdir() if p.is_dir()):
            sector = sector_dir.name
            for ticker_dir in sorted(p for p in sector_dir.iterdir() if p.is_dir()):
                ticker = ticker_dir.name
                for feedback_path in sorted(ticker_dir.glob(f"{ticker}_*_daily_feedback_log.json")):
                    cycle_id = feedback_path.stem.replace("_daily_feedback_log", "")
                    store = PredictionStore(ticker, sector=sector, base_dir=str(self._base_dir))
                    feedback_log = store.load_feedback_log(cycle_id)
                    if not feedback_log.entries:
                        continue
                    envelope = store.load_envelope(cycle_id)
                    if envelope is None:
                        # Feedback log without a matching envelope: build a
                        # minimal empty envelope so the join step still works
                        # (band_coverage / brier_score simply see no match).
                        envelope = PredictionEnvelope(
                            ticker=ticker,
                            sector=sector,
                            cycle_id=cycle_id,
                            generated_at="",
                            base_close=0.0,
                        )
                    pairs.append((envelope, feedback_log))

        return pairs

    # ------------------------------------------------------------------
    # Aggregation
    # ------------------------------------------------------------------

    def _build_report(
        self,
        pairs: list[tuple[PredictionEnvelope, DailyFeedbackLog]],
        source: str,
    ) -> EvalReport:
        all_entries: list[FeedbackEntry] = []
        all_records: list[MatchedRecord] = []

        per_ticker_entries: dict[str, list[FeedbackEntry]] = {}
        per_ticker_records: dict[str, list[MatchedRecord]] = {}
        per_sector_entries: dict[str, list[FeedbackEntry]] = {}
        per_sector_records: dict[str, list[MatchedRecord]] = {}

        for envelope, feedback_log in pairs:
            entries = feedback_log.entries
            records = self._match_records(envelope, feedback_log)

            all_entries.extend(entries)
            all_records.extend(records)

            ticker = feedback_log.ticker
            sector = feedback_log.sector

            per_ticker_entries.setdefault(ticker, []).extend(entries)
            per_ticker_records.setdefault(ticker, []).extend(records)
            per_sector_entries.setdefault(sector, []).extend(entries)
            per_sector_records.setdefault(sector, []).extend(records)

        report = EvalReport(
            source=source,
            n_entries=len(all_entries),
            aggregate=self._compute_metrics(all_entries, all_records),
            per_ticker={
                t: self._compute_metrics(per_ticker_entries[t], per_ticker_records[t])
                for t in per_ticker_entries
            },
            per_sector={
                s: self._compute_metrics(per_sector_entries[s], per_sector_records[s])
                for s in per_sector_entries
            },
        )
        return report

    @staticmethod
    def _match_records(
        envelope: PredictionEnvelope, feedback_log: DailyFeedbackLog
    ) -> list[MatchedRecord]:
        """Join FeedbackEntry (actuals) with DailyForecast (confidence + band) by date."""
        forecasts_by_date = {f.date: f for f in envelope.daily_forecasts}
        records: list[MatchedRecord] = []
        for entry in feedback_log.entries:
            forecast = forecasts_by_date.get(entry.date)
            if forecast is None:
                continue
            records.append(
                MatchedRecord(
                    date=entry.date,
                    confidence=forecast.confidence,
                    direction_correct=entry.direction_correct,
                    actual_close=entry.actual_close,
                    price_lower=forecast.price_lower,
                    price_upper=forecast.price_upper,
                )
            )
        return records

    @staticmethod
    def _compute_metrics(
        entries: list[FeedbackEntry], records: list[MatchedRecord]
    ) -> dict:
        return {
            "n_entries": len(entries),
            "direction_accuracy": direction_accuracy(entries),
            "brier_score": brier_score(records),
            "reliability_table": reliability_table(records),
            "band_coverage": band_coverage(records),
            "mae_pct": mae_pct(entries),
        }

    # ------------------------------------------------------------------
    # Synthetic ablation delta
    # ------------------------------------------------------------------

    def _synthetic_ablation_delta(
        self,
        key: str,
        baseline_aggregate: dict,
        n_tickers: int,
        n_cycles: int,
        accuracy_rate: float,
        vol: float,
        seed: int,
    ) -> dict:
        """
        Re-simulate the same seed with `key` ablated and report the delta
        (baseline-with-feature minus ablated-without-feature) in
        `direction_accuracy` and `brier_score`.
        """
        ablated_pairs = SyntheticLogGenerator(seed=seed).generate(
            n_tickers=n_tickers, n_cycles=n_cycles,
            accuracy_rate=accuracy_rate, vol=vol,
            ablate={key},
        )
        ablated_report = self._build_report(ablated_pairs, source="synthetic")

        return {
            "direction_accuracy_delta": (
                baseline_aggregate["direction_accuracy"]
                - ablated_report.aggregate["direction_accuracy"]
            ),
            "brier_score_delta": (
                baseline_aggregate["brier_score"]
                - ablated_report.aggregate["brier_score"]
            ),
        }

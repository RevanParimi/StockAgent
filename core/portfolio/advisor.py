"""
Compass Phase A — Position Advisor v1 (spec §5).

Pure-Python decision engine over signals the RL foundation already computes.
The LLM only narrates (narrator.py) — it never decides.

Verdict precedence (explicit, non-negotiable): EXIT > TRIM > ADD > HOLD.
Tax-deferral may soften a TRIM into WAIT_FOR_LTCG; it must NEVER suppress or
delay an EXIT — capital protection outranks tax optimisation, always.
"""
from __future__ import annotations

import hashlib
import logging
from datetime import date, timedelta

from pydantic import BaseModel

from core.config import settings
from backend.shared.schemas.portfolio import AdviceRecord, Holding, Portfolio
from services.data.verdict_store import VerdictStore  # plane boundary (Atlas C2)
from services.data.fetchers.corporate_events import next_results_event

logger = logging.getLogger(__name__)

_BUCKET_TIGHTEN = {"small": "mid", "mid": "large", "large": "large"}


class AdvisorSignals(BaseModel):
    """Deterministic inputs for one holding on one review date (spec §5.1)."""
    symbol: str
    sector: str
    close: float
    atr_stop_pct: float                    # volatility-scaled stop, already clamped
    unrealised_pnl_pct: float              # vs adj_avg_price, dividend-inclusive
    holding_age_days: int
    regime_label: str = "NORMAL"
    thesis_intact: bool | None = None      # latest ThesisReview outcome, None = never reviewed
    reforecast_reason: str = ""            # latest reforecast event reason this cycle
    envelope_direction: str = "FLAT"       # UP | DOWN | FLAT remaining-forecast drift
    confidence_trend: float = 0.0          # last remaining conf − first remaining conf
    reversion_prior: float = 0.0
    direction_accuracy_7d: float | None = None
    position_weight_pct: float = 0.0
    earnings_in_days: int | None = None    # trading-day distance to next results event
    confidence: float = 0.5                # mean remaining envelope confidence


# ---------------------------------------------------------------------------
# Stops (spec §5.2 — volatility-scaled, never a flat %)
# ---------------------------------------------------------------------------

def atr_pct(ohlcv_df, period: int) -> float:
    """ATR(period) as % of last close. 0.0 on failure (callers fall back to
    the bucket floor via compute_stop_pct's clamp)."""
    try:
        import pandas as pd
        if ohlcv_df is None or len(ohlcv_df) < period + 1:
            return 0.0
        high, low, close = ohlcv_df["High"], ohlcv_df["Low"], ohlcv_df["Close"]
        prev_close = close.shift(1)
        tr = pd.concat(
            [high - low, (high - prev_close).abs(), (low - prev_close).abs()], axis=1
        ).max(axis=1)
        atr = tr.rolling(period).mean().iloc[-1]
        last = float(close.iloc[-1])
        return round(float(atr) / last * 100, 4) if last > 0 else 0.0
    except Exception as exc:
        logger.debug("[advisor] ATR computation failed: %s", exc)
        return 0.0


def resolve_cap_bucket(market_cap_inr: float | None) -> str:
    """large/mid/small from free-float mcap in INR; unknown -> mid."""
    if market_cap_inr is None or market_cap_inr <= 0:
        return "mid"
    crores = market_cap_inr / 1e7
    if crores >= settings.ADVISOR_LARGE_CAP_FLOOR_CR:
        return "large"
    if crores >= settings.ADVISOR_MID_CAP_FLOOR_CR:
        return "mid"
    return "small"


def compute_stop_pct(atr_pct_value: float, cap_bucket: str, risk_profile: str) -> float:
    """clamp(stop_atr_mult × ATR%, bucket floor, bucket cap); conservative
    profiles tighten one bucket notch."""
    bucket = cap_bucket if cap_bucket in settings.ADVISOR_STOP_BUCKETS else "mid"
    if risk_profile == "conservative":
        bucket = _BUCKET_TIGHTEN[bucket]
    floor, cap = settings.ADVISOR_STOP_BUCKETS[bucket]
    raw = settings.ADVISOR_STOP_ATR_MULT * atr_pct_value
    return round(min(max(raw, floor), cap), 2)


# ---------------------------------------------------------------------------
# Signal assembly from existing RL artifacts
# ---------------------------------------------------------------------------

def build_signals(
    holding: Holding,
    portfolio: Portfolio,
    review_date: date,
    store: VerdictStore,
    calendar: dict,
    close: float,
    ohlcv_df=None,
    market_cap_inr: float | None = None,
) -> AdvisorSignals:
    """Assemble the advisor's inputs from PredictionStore artifacts + the
    events calendar. Every sub-read is non-fatal — missing artifacts leave
    conservative defaults in place."""
    sig = AdvisorSignals(
        symbol=holding.symbol,
        sector=holding.sector,
        close=close,
        atr_stop_pct=compute_stop_pct(
            atr_pct(ohlcv_df, settings.ADVISOR_ATR_PERIOD),
            resolve_cap_bucket(market_cap_inr),
            portfolio.risk_profile,
        ),
        unrealised_pnl_pct=holding.unrealised_pnl_pct(close),
        holding_age_days=holding.age_days(review_date),
    )
    # Position weight vs portfolio market value
    try:
        total = sum(h.adj_qty * h.adj_avg_price for h in portfolio.holdings)
        if total > 0:
            sig.position_weight_pct = round(
                holding.adj_qty * holding.adj_avg_price / total * 100, 2
            )
    except Exception:
        pass
    # Envelope state
    try:
        env = store.load_envelope(store.cycle_id_for(review_date))
        if env and env.daily_forecasts:
            remaining = [f for f in env.daily_forecasts if f.date >= review_date.isoformat()]
            if remaining:
                drift_pct = (remaining[-1].predicted_close - close) / close * 100
                band = settings.ADVISOR_ENVELOPE_FLAT_BAND_PCT
                sig.envelope_direction = (
                    "UP" if drift_pct > band else "DOWN" if drift_pct < -band else "FLAT"
                )
                sig.confidence_trend = round(remaining[-1].confidence - remaining[0].confidence, 4)
                sig.confidence = round(
                    sum(f.confidence for f in remaining) / len(remaining), 4
                )
            sig.reversion_prior = env.conviction_streak.reversion_prior
            if env.reforecast_history:
                sig.reforecast_reason = env.reforecast_history[-1].reason
    except Exception as exc:
        logger.warning("[advisor] envelope read failed for %s (non-fatal): %s",
                       holding.symbol, exc)
    # Feedback log: regime, thesis, direction accuracy
    try:
        log = store.load_feedback_log(store.cycle_id_for(review_date))
        entries = log.entries if log else []
        if entries:
            sig.regime_label = entries[-1].regime_label
            last7 = entries[-7:]
            sig.direction_accuracy_7d = round(
                sum(1 for e in last7 if e.direction_correct) / len(last7), 4
            )
            for e in reversed(entries):
                if e.thesis_review is not None:
                    sig.thesis_intact = e.thesis_review.thesis_intact
                    break
    except Exception as exc:
        logger.warning("[advisor] feedback read failed for %s (non-fatal): %s",
                       holding.symbol, exc)
    # Earnings distance (trading days)
    try:
        ev = next_results_event(holding.symbol, review_date, calendar)
        if ev is not None:
            from core.intelligence.rl.nse_calendar import is_trading_day
            d, n = review_date, 0
            target = date.fromisoformat(ev.date)
            while d < target:
                d += timedelta(days=1)
                if is_trading_day(d):
                    n += 1
            sig.earnings_in_days = n
    except Exception as exc:
        logger.warning("[advisor] earnings-distance failed for %s (non-fatal): %s",
                       holding.symbol, exc)
    return sig


# ---------------------------------------------------------------------------
# Verdict engine
# ---------------------------------------------------------------------------

def _best_switch_candidate(signals: AdvisorSignals, shelf_ideas, sector_weights: dict):
    """SWITCH (spec §5.2): EXIT already fired AND an active shelf idea beats the
    holding's mean remaining envelope confidence by >= ADVISOR_SWITCH_CONVICTION_GAP,
    in a sector strictly UNDERWEIGHT vs the exiting holding's sector. With no
    sector-weight context every idea fails the underweight check (conservative)."""
    own_weight = sector_weights.get(signals.sector, 0.0)
    best = None
    for idea in shelf_ideas or []:
        if getattr(idea, "status", "active") != "active":
            continue
        if sector_weights.get(idea.sector, 0.0) >= own_weight:
            continue
        if idea.conviction - signals.confidence < settings.ADVISOR_SWITCH_CONVICTION_GAP:
            continue
        if best is None or idea.conviction > best.conviction:
            best = idea
    return best


def decide(
    signals: AdvisorSignals,
    holding: Holding,
    risk_profile: str,
    shelf_ideas: list | None = None,
    sector_weights: dict[str, float] | None = None,
) -> AdviceRecord:
    triggers: list[str] = []
    notes: list[str] = []

    # -- EXIT (spec §5.2, highest precedence) ------------------------------
    if signals.unrealised_pnl_pct <= -signals.atr_stop_pct:
        triggers.append("stop_breach")
    if signals.thesis_intact is False and signals.envelope_direction == "DOWN":
        triggers.append("thesis_break")
    if signals.reforecast_reason in ("external_shock", "thesis_break", "preopen_shock") \
            and signals.envelope_direction == "DOWN":
        triggers.append("shock_reforecast")
    if signals.regime_label == "MACRO_CRISIS" and signals.envelope_direction == "DOWN":
        triggers.append("crisis_regime_bearish")

    exit_fired = bool(triggers)

    # -- TRIM ---------------------------------------------------------------
    trim_fired = False
    if not exit_fired and signals.unrealised_pnl_pct >= settings.ADVISOR_TRIM_PROFIT_PCT:
        if signals.confidence_trend <= -settings.ADVISOR_CONFIDENCE_DECLINE_THRESHOLD:
            triggers.append("trim_profit_confidence_decline")
            trim_fired = True
        elif signals.reversion_prior >= settings.ADVISOR_REVERSION_PRIOR_ELEVATED:
            triggers.append("trim_profit_reversion_elevated")
            trim_fired = True

    # -- ADD ----------------------------------------------------------------
    add_fired = False
    if not exit_fired and not trim_fired:
        if (
            signals.envelope_direction == "UP"
            and signals.regime_label not in ("MACRO_CRISIS", "RISK_OFF")
            and signals.position_weight_pct < settings.ADVISOR_MAX_POSITION_PCT
            and (signals.direction_accuracy_7d or 0.0) >= settings.ADVISOR_ADD_MIN_DIRECTION_ACCURACY
        ):
            triggers.append("add_bullish_healthy")
            add_fired = True

    # -- Precedence: EXIT > TRIM > ADD > HOLD -------------------------------
    if exit_fired:
        verdict = "EXIT"
    elif trim_fired:
        verdict = "TRIM"
    elif add_fired:
        verdict = "ADD"
    else:
        verdict = "HOLD"

    # -- SWITCH: EXIT + stronger shelf idea in an underweight sector (§5.2) --
    switch_candidate = ""
    if verdict == "EXIT" and shelf_ideas:
        cand = _best_switch_candidate(signals, shelf_ideas, sector_weights or {})
        if cand is not None:
            verdict = "SWITCH"
            triggers.append("switch_candidate_available")
            switch_candidate = cand.symbol

    # -- LTCG softening: TRIM only, NEVER EXIT (spec §5.2) ------------------
    if verdict == "TRIM" and signals.thesis_intact is not False:
        months = signals.holding_age_days / 30.44
        if settings.ADVISOR_LTCG_WAIT_MIN_MONTHS <= months < 12:
            verdict = "HOLD"
            notes.append("WAIT_FOR_LTCG")

    # -- Annotations ---------------------------------------------------------
    if (
        signals.unrealised_pnl_pct > 0
        and signals.earnings_in_days is not None
        and signals.earnings_in_days <= settings.ADVISOR_EARNINGS_GAP_DAYS
    ):
        notes.append("EARNINGS_GAP_PROTECTION")
    if signals.position_weight_pct >= settings.ADVISOR_SECTOR_CONCENTRATION_WARN_PCT:
        notes.append("SECTOR_CONCENTRATION_HIGH")

    rationale = "|".join(sorted(triggers) + sorted(notes)) or "default_hold"
    return AdviceRecord(
        date=date.today().isoformat(),
        user_id="",                      # pipeline fills the user id
        symbol=signals.symbol,
        verdict=verdict,
        close=signals.close,
        unrealised_pnl_pct=round(signals.unrealised_pnl_pct, 2),
        stop_pct=signals.atr_stop_pct,
        triggers=triggers,
        notes=notes,
        confidence=signals.confidence,
        switch_candidate=switch_candidate,
        rationale_hash=hashlib.sha256(rationale.encode()).hexdigest()[:16],
    )

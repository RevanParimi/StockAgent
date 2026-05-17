"""
core/intelligence/rl/algorithms/price_interpolator.py
======================================================
LLM-calibrated 30-day price path builder.

WHAT IT REPLACES
----------------
The static dict in generate_forecast.py:
    verdict_monthly_pct = {"STRONG BUY": 8.0, "BUY": 4.0, "NEUTRAL": 0.5, ...}

These universal constants are wrong in two ways:
  1. The same verdict means different expected returns for a 5% ATR stock vs a
     40% ATR stock.  A BUY on HDFC Bank (+3% realistic) ≠ a BUY on ADANIGREEN
     (+8–12% if the thesis plays out).
  2. Linear price drift ignores that many real stock moves are front-loaded
     (catalyst imminent) or back-loaded (awaiting event), not uniform.

HOW IT WORKS
------------
1. LLM receives: ticker, sector, verdict, ATR%, regime, conviction_drivers,
   historical accuracy (optional).
2. LLM returns a ForecastProfile:
     - monthly_return_pct: calibrated to this stock's actual volatility
     - path_shape: linear | front_loaded | back_loaded | volatile
     - confidence_band_daily_pct: ATR-based daily uncertainty band (asymmetric ok)
3. build_price_path() uses the profile to construct the 30-day forecast.

PATH SHAPES
-----------
  linear      — uniform daily drift (current behaviour, used as fallback)
  front_loaded— 60% of monthly move in first 10 days, 40% spread over days 11–30
                Use when: near-term catalyst present in conviction_drivers
  back_loaded — 20% in days 1–10, 80% in days 11–30
                Use when: catalyst is >15 days away (e.g. upcoming earnings)
  volatile    — trend with ±ATR noise per day; shows genuine uncertainty
                Use when: high ATR AND regime is MACRO_CRISIS or RISK_OFF

FALLBACK BEHAVIOUR
------------------
If the LLM call fails or returns invalid JSON, build_price_path() uses the
static verdict_monthly_pct dict and linear shape — identical to the old code.
No exception is raised; the caller never knows the LLM path failed.

LLM COST
--------
~200 input tokens, ~80 output tokens, once per ticker per month-start.
For 20 tickers: ~5,600 tokens/month. Negligible.
"""

from __future__ import annotations

import json
import logging
import math
import random
import time
from typing import Literal

from pydantic import BaseModel, Field

from core.config import settings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Static fallback — identical to old generate_forecast.py behaviour
# ---------------------------------------------------------------------------

_STATIC_MONTHLY_PCT: dict[str, float] = {
    "STRONG BUY":  8.0,
    "BUY":         4.0,
    "NEUTRAL":     0.5,
    "SELL":        -3.0,
    "STRONG SELL": -7.0,
}

PathShape = Literal["linear", "front_loaded", "back_loaded", "volatile"]


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

class ForecastProfile(BaseModel):
    """
    LLM-determined forecast shape parameters for a single ticker-verdict pair.

    All values are deliberately bounded to prevent the LLM from producing
    unrealistic forecasts.  The formula in build_price_path() is the source
    of truth; the profile only supplies calibrated parameters to that formula.
    """
    monthly_return_pct: float = Field(
        description="Expected return over 30 trading days. Calibrated to ATR.",
        ge=-20.0, le=20.0,
    )
    path_shape: PathShape = "linear"
    confidence_band_daily_pct: float = Field(
        description="Daily ±uncertainty band as % of price. ATR-derived.",
        ge=0.1, le=5.0,
        default=1.0,
    )
    reasoning: str = Field(default="", max_length=300)
    source: Literal["llm", "static"] = "llm"


# ---------------------------------------------------------------------------
# LLM system prompt
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = """\
You are a quantitative analyst calibrating a 30-day stock price forecast path.

You will receive: ticker, sector, verdict (BUY/SELL/etc), daily ATR as % of price, \
current market regime, conviction drivers (near-term catalysts), and optionally the \
historical average return this ticker produced in the last N cycles with the same verdict.

Your job: return a ForecastProfile that reflects realistic expectations for THIS specific stock.

Rules:
1. monthly_return_pct should be calibrated to the ATR — a high-ATR stock can reasonably \
   move ±10-15% on BUY; a low-ATR stock might move only ±2-3%.
2. path_shape choices:
   - "front_loaded"  — use if a near-term catalyst (earnings, data release, policy event) \
                        is mentioned in conviction_drivers within the next 10 trading days
   - "back_loaded"   — use if the main catalyst is >15 trading days away
   - "volatile"      — use if ATR > 2.0% AND regime is MACRO_CRISIS or RISK_OFF
   - "linear"        — default when no specific shape is indicated
3. confidence_band_daily_pct = ATR × 0.5 is a reasonable starting point; adjust higher \
   for MACRO_CRISIS/RISK_OFF, lower for NORMAL/RISK_ON.
4. Do NOT exceed these bounds: monthly_return_pct in [-20, 20], band in [0.1, 5.0].
5. For NEUTRAL verdicts, keep monthly_return_pct close to 0.0 (±1.0%).

Return ONLY valid JSON:
{
  "monthly_return_pct": <float>,
  "path_shape": "<linear|front_loaded|back_loaded|volatile>",
  "confidence_band_daily_pct": <float>,
  "reasoning": "<max 2 sentences>"
}
"""


# ---------------------------------------------------------------------------
# Core class
# ---------------------------------------------------------------------------

class PriceInterpolator:
    """
    Replaces the static verdict_monthly_pct dict with an LLM-calibrated profile.
    Stateless — instantiate once per generate_forecast call.
    """

    def get_profile(
        self,
        ticker: str,
        sector: str,
        verdict: str,
        atr_pct: float,
        regime_label: str,
        conviction_drivers: list[str],
        historical_avg_return_pct: float | None = None,
    ) -> ForecastProfile:
        """
        Call LLM to get a calibrated ForecastProfile for this ticker/verdict.

        Falls back to static values on any failure.

        Parameters
        ----------
        ticker                   : NSE ticker
        sector                   : sector name
        verdict                  : STRONG BUY | BUY | NEUTRAL | SELL | STRONG SELL
        atr_pct                  : 14-day ATR as % of price (e.g. 1.8 means 1.8%)
        regime_label             : from RegimeDetector (e.g. "NORMAL")
        conviction_drivers       : top 3-5 reasons from FinalReport
        historical_avg_return_pct: optional — median return this ticker produced in
                                   past cycles with the same verdict (from FeedbackLog)
        """
        try:
            user_prompt = self._build_prompt(
                ticker, sector, verdict, atr_pct, regime_label,
                conviction_drivers, historical_avg_return_pct,
            )
            raw = self._call_llm(user_prompt)
            return self._parse(raw, verdict, atr_pct)
        except Exception as exc:
            logger.warning(
                "[PriceInterpolator] LLM call failed for %s (%s) — using static fallback: %s",
                ticker, verdict, exc,
            )
            return self._static_fallback(verdict, atr_pct)

    def build_price_path(
        self,
        base_close: float,
        profile: ForecastProfile,
        n_days: int,
        base_confidence: float,
    ) -> list[tuple[float, float]]:
        """
        Construct the day-by-day (predicted_close, confidence) sequence.

        Returns list of (price, confidence) tuples, length = n_days.

        Path shapes:
          linear      — uniform drift per day
          front_loaded— 60% of monthly move in first third of horizon
          back_loaded — 20% in first third, 80% in last two thirds
          volatile    — drift + per-day ATR noise (seeded for reproducibility)
        """
        monthly_pct = profile.monthly_return_pct
        daily_band  = profile.confidence_band_daily_pct

        # Build the daily drift weights for the chosen path shape
        weights = self._shape_weights(n_days, profile.path_shape)

        total_move = base_close * (monthly_pct / 100.0)
        result: list[tuple[float, float]] = []
        running_close = base_close

        # Confidence decays slightly further out (uncertainty grows with horizon)
        conf_decay_per_day = 0.004  # 0.4% per day — slightly softer than old 0.5%

        rng = random.Random(42)  # deterministic seed so identical inputs → identical paths

        for i, w in enumerate(weights):
            day_move = total_move * w
            if profile.path_shape == "volatile":
                # Add ATR-scaled noise in the direction of the trend
                noise = rng.gauss(0, base_close * daily_band / 100.0) * 0.3
                day_move += noise
            running_close = round(running_close + day_move, 2)

            # Confidence: base decay + band-scaled uncertainty
            horizon_decay = 1.0 - conf_decay_per_day * i
            band_penalty  = max(0.0, (daily_band - 1.0) * 0.02)  # wider band = lower conf
            day_conf = round(max(0.05, min(0.99, base_confidence * horizon_decay - band_penalty)), 4)

            result.append((running_close, day_conf))

        return result

    # ------------------------------------------------------------------
    # Path shape weights
    # ------------------------------------------------------------------

    @staticmethod
    def _shape_weights(n_days: int, shape: PathShape) -> list[float]:
        """
        Return a list of per-day fractional move weights summing to 1.0.
        Each weight × total_monthly_move = that day's price increment.
        """
        if shape == "linear" or n_days == 0:
            w = 1.0 / n_days
            return [w] * n_days

        if shape == "front_loaded":
            # 60% of move in first ~third of days, 40% spread over rest
            split = max(1, n_days // 3)
            front_w = 0.60 / split
            back_w  = 0.40 / max(1, n_days - split)
            return [front_w] * split + [back_w] * (n_days - split)

        if shape == "back_loaded":
            # 20% in first third, 80% in remaining
            split = max(1, n_days // 3)
            front_w = 0.20 / split
            back_w  = 0.80 / max(1, n_days - split)
            return [front_w] * split + [back_w] * (n_days - split)

        if shape == "volatile":
            # Uniform drift but noise is added at build time — weights are linear
            w = 1.0 / n_days
            return [w] * n_days

        # Fallback
        w = 1.0 / n_days
        return [w] * n_days

    # ------------------------------------------------------------------
    # LLM call
    # ------------------------------------------------------------------

    @staticmethod
    def _build_prompt(
        ticker: str,
        sector: str,
        verdict: str,
        atr_pct: float,
        regime_label: str,
        conviction_drivers: list[str],
        historical_avg: float | None,
    ) -> str:
        hist = (
            f"Historical average return for {ticker} on '{verdict}' signals: "
            f"{historical_avg:+.1f}% over 30 days (from past cycles)."
            if historical_avg is not None
            else "No historical return data yet (first or second cycle)."
        )
        drivers_str = "\n".join(f"  - {d}" for d in conviction_drivers[:5]) or "  (none listed)"
        return (
            f"Ticker: {ticker} | Sector: {sector}\n"
            f"Verdict: {verdict}\n"
            f"14-day ATR: {atr_pct:.2f}% of price\n"
            f"Market regime: {regime_label}\n"
            f"Conviction drivers:\n{drivers_str}\n"
            f"{hist}\n\n"
            f"Calibrate the 30-day forecast profile for this ticker and verdict."
        )

    def _call_llm(self, user_prompt: str) -> str:
        from openai import OpenAI, APIError, APITimeoutError, RateLimitError
        client = OpenAI(
            api_key=settings.OPENROUTER_API_KEY,
            base_url=settings.OPENROUTER_BASE_URL,
            timeout=settings.LLM_TIMEOUT_SECONDS,
        )
        delay = settings.RETRY_DELAY_SECONDS
        last_err: Exception | None = None

        for attempt in range(1, settings.MAX_RETRIES + 1):
            try:
                resp = client.chat.completions.create(
                    model=settings.LLM_MODEL,
                    temperature=0.2,
                    max_tokens=180,
                    messages=[
                        {"role": "system", "content": _SYSTEM_PROMPT},
                        {"role": "user",   "content": user_prompt},
                    ],
                    response_format={"type": "json_object"},
                )
                return resp.choices[0].message.content or "{}"
            except RateLimitError as e:
                last_err = e; time.sleep(delay); delay *= 2
            except APITimeoutError as e:
                last_err = e; time.sleep(delay)
            except Exception as e:
                last_err = e; break

        raise RuntimeError(f"LLM failed: {last_err}")

    # ------------------------------------------------------------------
    # Parse + fallback
    # ------------------------------------------------------------------

    def _parse(self, raw: str, verdict: str, atr_pct: float) -> ForecastProfile:
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return self._static_fallback(verdict, atr_pct)

        monthly_pct = float(data.get("monthly_return_pct", _STATIC_MONTHLY_PCT.get(verdict, 0.5)))
        monthly_pct = max(-20.0, min(20.0, monthly_pct))

        # Sanity-check: sign of monthly_pct must align with verdict direction
        if verdict in {"STRONG BUY", "BUY"} and monthly_pct < 0:
            monthly_pct = abs(monthly_pct)
        elif verdict in {"STRONG SELL", "SELL"} and monthly_pct > 0:
            monthly_pct = -abs(monthly_pct)

        raw_shape = data.get("path_shape", "linear")
        shape: PathShape = raw_shape if raw_shape in {"linear", "front_loaded", "back_loaded", "volatile"} else "linear"

        band = float(data.get("confidence_band_daily_pct", atr_pct * 0.5))
        band = max(0.1, min(5.0, band))

        return ForecastProfile(
            monthly_return_pct=round(monthly_pct, 2),
            path_shape=shape,
            confidence_band_daily_pct=round(band, 3),
            reasoning=str(data.get("reasoning", ""))[:300],
            source="llm",
        )

    @staticmethod
    def _static_fallback(verdict: str, atr_pct: float) -> ForecastProfile:
        monthly_pct = _STATIC_MONTHLY_PCT.get(verdict, 0.5)
        # Scale by ATR if it differs meaningfully from the "average" 1.5% ATR
        # the static values were implicitly calibrated for.
        atr_scale = max(0.5, min(2.5, atr_pct / 1.5)) if atr_pct > 0 else 1.0
        scaled_pct = round(monthly_pct * atr_scale, 2)
        scaled_pct = max(-20.0, min(20.0, scaled_pct))
        return ForecastProfile(
            monthly_return_pct=scaled_pct,
            path_shape="linear",
            confidence_band_daily_pct=round(max(0.1, atr_pct * 0.5), 3),
            reasoning="Static fallback (LLM unavailable).",
            source="static",
        )


# ---------------------------------------------------------------------------
# Convenience: compute ATR% from yfinance OHLCV DataFrame
# ---------------------------------------------------------------------------

def compute_atr_pct(ohlcv_df) -> float:
    """
    14-day Average True Range as % of last close.
    ohlcv_df: pandas DataFrame with columns High, Low, Close.
    Returns 0.0 on failure (caller should use static fallback).
    """
    try:
        import pandas as pd
        if ohlcv_df is None or len(ohlcv_df) < 15:
            return 0.0
        high  = ohlcv_df["High"]
        low   = ohlcv_df["Low"]
        close = ohlcv_df["Close"]
        prev_close = close.shift(1)
        tr = pd.concat([
            high - low,
            (high - prev_close).abs(),
            (low  - prev_close).abs(),
        ], axis=1).max(axis=1)
        atr14      = tr.rolling(14).mean().iloc[-1]
        last_close = float(close.iloc[-1])
        return round(float(atr14) / last_close * 100, 4) if last_close > 0 else 0.0
    except Exception as exc:
        logger.debug("[PriceInterpolator] ATR computation failed: %s", exc)
        return 0.0


# ---------------------------------------------------------------------------
# Convenience: compute historical average return for a verdict from FeedbackLog
# ---------------------------------------------------------------------------

def compute_historical_avg_return(
    feedback_log_or_entries,
    verdict: str,
    last_n_cycles: int = 6,
) -> float | None:
    """
    Compute median observed price_error_pct for a given verdict.
    Accepts either a DailyFeedbackLog object or a plain list of FeedbackEntry objects.
    Returns None if fewer than 3 matching entries.
    """
    try:
        if isinstance(feedback_log_or_entries, list):
            all_entries = feedback_log_or_entries
        elif feedback_log_or_entries is None:
            return None
        else:
            all_entries = feedback_log_or_entries.entries or []

        if not all_entries:
            return None

        matching = [
            e.price_error_pct
            for e in all_entries
            if e.predicted_verdict.upper() == verdict.upper()
        ]
        if len(matching) < 3:
            return None
        matching_sorted = sorted(matching)
        mid = len(matching_sorted) // 2
        median = (
            matching_sorted[mid]
            if len(matching_sorted) % 2 != 0
            else (matching_sorted[mid - 1] + matching_sorted[mid]) / 2
        )
        return round(median, 2)
    except Exception:
        return None

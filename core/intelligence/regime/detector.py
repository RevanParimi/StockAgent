"""
core/intelligence/regime/detector.py
=====================================
P5 — Context-Conditional Regime Multiplier

RegimeDetector reads three cheap signals from yfinance (no LLM call) and
classifies the current market into one of six regime labels. The resulting
per-agent multipliers are applied on top of learned WeightMemory weights
inside daily_review.py — they are ephemeral and NOT written to
weight_memory.json.

Regime Labels (priority order checked in detect()):
  MACRO_CRISIS       VIX > 22 AND fii_proxy < -1.0%
  RISK_OFF           VIX > 22 OR (14≤VIX≤22 AND fii_proxy < -1.0%)
  MOMENTUM_EXTENDED  VIX < 14 AND fii_proxy > +1.0% AND sector_rsi > 70
  RISK_ON            VIX < 22 AND fii_proxy > +1.0% AND sector_rsi < 70
  OVERSOLD           sector_rsi < 30  (regardless of VIX / FII)
  NORMAL             everything else

FII proxy:
  Nifty 50 (^NSEI) 5-day price momentum.
  Positive 5-day return → inflow proxy; negative → outflow proxy.
  Threshold ±1.0% over 5 days.

RSI:
  Wilder smoothing (EWM alpha=1/14) on sector index closing prices.
  No ta-lib — pure pandas.

All errors fall back to safe defaults so a network failure never breaks
the core feedback loop.
"""

from __future__ import annotations

import logging
from datetime import date

import pandas as pd

from core.config import settings
from core.schemas.feedback import RegimeSnapshot

logger = logging.getLogger(__name__)

_RSI_PERIOD = 14


def _compute_rsi(prices: pd.Series, period: int = _RSI_PERIOD) -> float:
    """
    Wilder RSI(period) using pandas EWM.
    Returns the most recent RSI value, or 50.0 on failure.
    """
    if len(prices) < period + 1:
        return settings.RSI_FALLBACK
    delta = prices.diff().dropna()
    gain  = delta.clip(lower=0)
    loss  = (-delta).clip(lower=0)
    avg_gain = gain.ewm(alpha=1.0 / period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1.0 / period, adjust=False).mean()
    last_loss = avg_loss.iloc[-1]
    if last_loss == 0:
        return 100.0
    rs  = avg_gain.iloc[-1] / last_loss
    rsi = 100.0 - (100.0 / (1.0 + rs))
    return round(float(rsi), 2)


class RegimeDetector:
    """
    Lightweight market regime classifier.  No LLM call. Reads yfinance only.
    All public methods are synchronous.
    """

    def detect(self, as_of_date: date, sector: str) -> RegimeSnapshot:
        """
        Detect the current market regime for a given date and sector.

        Parameters
        ----------
        as_of_date : date
            The trading date to classify (typically today).
        sector : str
            Sector name used to pick the sector RSI ticker.

        Returns
        -------
        RegimeSnapshot with regime_label, raw signal values, per-agent
        multipliers from settings.REGIME_MULTIPLIERS, and a narrative string.
        """
        vix        = self._get_vix(as_of_date)
        fii_proxy  = self._get_fii_proxy(as_of_date)
        sector_rsi = self._get_sector_rsi(sector, as_of_date)

        label = self._classify(vix, fii_proxy, sector_rsi)
        multipliers = dict(settings.REGIME_MULTIPLIERS.get(label, settings.REGIME_MULTIPLIERS["NORMAL"]))
        narrative   = self._build_narrative(label, vix, fii_proxy, sector_rsi)

        snap = RegimeSnapshot(
            regime_label      = label,
            vix_value         = vix,
            fii_proxy_5d_pct  = fii_proxy,
            sector_rsi        = sector_rsi,
            multipliers       = multipliers,
            narrative         = narrative,
            as_of_date        = as_of_date.isoformat(),
        )
        logger.info(
            "[RegimeDetector] %s | VIX=%.1f | FII_proxy=%.2f%% | RSI=%.1f → %s",
            as_of_date, vix, fii_proxy, sector_rsi, label,
        )
        return snap

    # ------------------------------------------------------------------
    # Signal fetchers
    # ------------------------------------------------------------------

    def _get_vix(self, as_of_date: date) -> float:
        """
        India VIX from yfinance ^INDIAVIX.
        Falls back to VIX_FALLBACK (17.0 — NORMAL regime midpoint) on error.
        """
        try:
            import yfinance as yf
            df = yf.Ticker(settings.REGIME_VIX_TICKER).history(period="1mo")
            if df.empty:
                return settings.VIX_FALLBACK
            return round(float(df["Close"].iloc[-1]), 2)
        except Exception as exc:
            logger.warning("[RegimeDetector] VIX fetch failed (fallback %.1f): %s",
                           settings.VIX_FALLBACK, exc)
            return settings.VIX_FALLBACK

    def _get_fii_proxy(self, as_of_date: date) -> float:
        """
        Nifty 50 (^NSEI) 5-day momentum as proxy for FII net flow direction.
        Returns (close[-1] - close[-6]) / close[-6] * 100.
        Falls back to FII_PROXY_FALLBACK (0.0 — neutral) on error.
        """
        try:
            import yfinance as yf
            df = yf.Ticker(settings.REGIME_FII_PROXY_TICKER).history(period="1mo")
            if df.empty or len(df) < 6:
                return settings.FII_PROXY_FALLBACK
            close = df["Close"]
            pct   = (close.iloc[-1] - close.iloc[-6]) / close.iloc[-6] * 100.0
            return round(float(pct), 4)
        except Exception as exc:
            logger.warning("[RegimeDetector] FII proxy fetch failed (fallback 0.0): %s", exc)
            return settings.FII_PROXY_FALLBACK

    def _get_sector_rsi(self, sector: str, as_of_date: date) -> float:
        """
        RSI(14) of the sector index using Wilder smoothing (pure pandas, no ta-lib).
        Sector index tickers from settings.REGIME_SECTOR_TICKERS; falls back to ^NSEI.
        Falls back to RSI_FALLBACK (50.0) on error.
        """
        ticker_sym = settings.REGIME_SECTOR_TICKERS.get(
            sector, settings.REGIME_SECTOR_FALLBACK_TICKER
        )
        try:
            import yfinance as yf
            df = yf.Ticker(ticker_sym).history(period="3mo")
            if df.empty or len(df) < _RSI_PERIOD + 1:
                # Try fallback ticker if sector ticker gave insufficient data
                if ticker_sym != settings.REGIME_SECTOR_FALLBACK_TICKER:
                    df = yf.Ticker(settings.REGIME_SECTOR_FALLBACK_TICKER).history(period="3mo")
                if df.empty or len(df) < _RSI_PERIOD + 1:
                    return settings.RSI_FALLBACK
            return _compute_rsi(df["Close"])
        except Exception as exc:
            logger.warning(
                "[RegimeDetector] Sector RSI fetch failed for %s (fallback 50.0): %s",
                ticker_sym, exc,
            )
            return settings.RSI_FALLBACK

    # ------------------------------------------------------------------
    # Classification
    # ------------------------------------------------------------------

    @staticmethod
    def _classify(vix: float, fii_proxy: float, sector_rsi: float) -> str:
        """
        Evaluate regime conditions in priority order.
        Returns one of the six regime label strings.
        """
        threshold = settings.FII_PROXY_THRESHOLD_PCT
        vix_hi    = settings.VIX_VOLATILE_THRESHOLD
        vix_lo    = settings.VIX_LOW_VOL_THRESHOLD

        # MACRO_CRISIS: worst of both worlds — volatile VIX AND selling pressure
        if vix > vix_hi and fii_proxy < -threshold:
            return "MACRO_CRISIS"

        # RISK_OFF: elevated VIX (even without FII outflow) OR selling + mid-VIX
        if vix > vix_hi or (vix_lo <= vix <= vix_hi and fii_proxy < -threshold):
            return "RISK_OFF"

        # MOMENTUM_EXTENDED: low vol + inflow + overbought → mean-reversion risk
        if vix < vix_lo and fii_proxy > threshold and sector_rsi > settings.RSI_OVERBOUGHT:
            return "MOMENTUM_EXTENDED"

        # RISK_ON: calm market + inflow + sector not overbought
        if vix < vix_hi and fii_proxy > threshold and sector_rsi < settings.RSI_OVERBOUGHT:
            return "RISK_ON"

        # OVERSOLD: sector RSI below oversold threshold regardless of macro
        if sector_rsi < settings.RSI_OVERSOLD:
            return "OVERSOLD"

        return "NORMAL"

    @staticmethod
    def _build_narrative(
        label: str, vix: float, fii_proxy: float, sector_rsi: float
    ) -> str:
        narratives = {
            "MACRO_CRISIS": (
                f"MACRO CRISIS regime detected: India VIX {vix:.1f} (above 22) with "
                f"Nifty 5-day return {fii_proxy:+.2f}% indicating FII outflow pressure; "
                "risk_macro weight elevated, growth signals discounted."
            ),
            "RISK_OFF": (
                f"RISK-OFF regime: elevated VIX ({vix:.1f}) or FII outflow proxy "
                f"({fii_proxy:+.2f}% 5-day Nifty); risk_macro carries higher weight today."
            ),
            "RISK_ON": (
                f"RISK-ON regime: VIX {vix:.1f} (calm), Nifty 5-day {fii_proxy:+.2f}% "
                "(FII inflow proxy), sector RSI {:.1f}; fundamentals and sentiment elevated.".format(sector_rsi)
            ),
            "MOMENTUM_EXTENDED": (
                f"MOMENTUM EXTENDED: VIX {vix:.1f} low, Nifty {fii_proxy:+.2f}% inflow, "
                f"sector RSI {sector_rsi:.1f} (overbought > 70); "
                "pattern_analysis elevated for mean-reversion detection."
            ),
            "OVERSOLD": (
                f"OVERSOLD regime: sector RSI {sector_rsi:.1f} (below 30); "
                "pattern_analysis weight elevated for mean-reversion opportunity detection."
            ),
            "NORMAL": (
                f"NORMAL regime: VIX {vix:.1f}, Nifty 5-day {fii_proxy:+.2f}%, "
                f"sector RSI {sector_rsi:.1f}; base learned weights apply."
            ),
        }
        return narratives.get(label, f"Regime: {label}")


def apply_regime_multipliers(
    learned_weights: dict[str, float],
    multipliers: dict[str, float],
) -> dict[str, float]:
    """
    Apply regime multipliers to learned weights and renormalise to sum=1.0.

    Parameters
    ----------
    learned_weights : per-agent learned weights (sum ≈ 1.0)
    multipliers     : per-agent regime multipliers (from RegimeSnapshot.multipliers)

    Returns
    -------
    Renormalised effective weights dict. Agents not in multipliers get 1.0×.
    """
    raw: dict[str, float] = {}
    for agent, weight in learned_weights.items():
        mult = multipliers.get(agent, 1.0)
        raw[agent] = weight * mult

    total = sum(raw.values())
    if total == 0:
        return dict(learned_weights)
    return {agent: round(w / total, 6) for agent, w in raw.items()}

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

The session read (FIX-023). `detect(as_of_date)` describes the market at the
close of `as_of_date`: the India VIX, the Nifty and the sector index are read
from bars on or before it; Brent, USD/INR and the S&P 500 from bars before
it, because their bar for that date closes after the Indian session (the S&P
500's at 02:30 IST the next day). So the 16:30 job on Tuesday, reviewing
Monday, reads Monday's VIX and Nifty and Friday's S&P 500 session, not
Tuesday's. An input with no close in the 7 days up to its cut has not
answered.

A missing input has no value (FIX-023). Its snapshot value is None and its
name is in `dark_inputs`; a missing global input never fires. A failed fetch
never breaks the feedback loop: the learning loop's label is classified with
the neutral values (VIX 17.0, Nifty 0%, RSI 50) in place of the missing ones,
as before. But that label is trusted as the day's regime only when its
severity is **established**: the inputs that answered give the same severity
whatever the missing ones are (each read at its mildest, then its severest).
Otherwise `unavailable` says why ("India VIX did not answer") and
`floor_label` is the mildest label they allow. The sticky layer
(regime/state.py) then records the day without a label. Example: Nifty -3%
in 5 sessions with India VIX missing could be NORMAL (VIX 12) or
MACRO_CRISIS (VIX 30): unavailable. With VIX 30 and Nifty -3% answering and
Brent missing, the label is MACRO_CRISIS whatever Brent did: established.
"""

from __future__ import annotations

import logging
import math
from datetime import date, timedelta

import pandas as pd

from core.config import settings
from core.intelligence.regime.state import severity
from core.schemas.feedback import RegimeSnapshot

logger = logging.getLogger(__name__)

# FIX-023: an input with no close in this many days up to its cut has not answered.
_MAX_INPUT_AGE_DAYS = 7


def _num(value: float | None, spec: str) -> str:
    return "n/a" if value is None else format(value, spec)


def _names(missing: list[str]) -> str:
    """'India VIX', 'India VIX and Nifty 50', 'India VIX, Nifty 50 and S&P 500'."""
    return missing[0] if len(missing) == 1 else ", ".join(missing[:-1]) + " and " + missing[-1]


def _compute_rsi(prices: pd.Series, period: int = settings.RSI_PERIOD) -> float:
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
            The session to classify: the review session for the daily
            review, today for the monthly forecast. No bar after it is read.
        sector : str
            Sector name used to pick the sector RSI ticker.

        Returns
        -------
        RegimeSnapshot with regime_label, raw signal values (None for an input
        that did not answer), per-agent multipliers from
        settings.REGIME_MULTIPLIERS, a narrative string, and whether the
        label's severity is established (`unavailable` empty).
        """
        vix        = self._get_vix(as_of_date)
        fii_proxy  = self._get_fii_proxy(as_of_date)
        sector_rsi = self._get_sector_rsi(sector, as_of_date)
        brent = self._get_5d_pct(settings.REGIME_BRENT_TICKER, as_of_date)
        usdinr = self._get_5d_pct(settings.REGIME_USDINR_TICKER, as_of_date)
        spx = self._get_last_session_pct(settings.REGIME_SPX_TICKER, as_of_date)

        label = self._classify(
            settings.VIX_FALLBACK if vix is None else vix,
            settings.FII_PROXY_FALLBACK if fii_proxy is None else fii_proxy,
            settings.RSI_FALLBACK if sector_rsi is None else sector_rsi)
        stress = self._global_stress_signals(brent, usdinr, spx)
        escalated = self._escalate_label(label, len(stress))
        if escalated != label:
            logger.info("[RegimeDetector] global stress %s escalated %s -> %s",
                        stress, label, escalated)
        label = escalated

        missing = [name for name, value in (
            ("India VIX", vix), ("Nifty 50", fii_proxy), ("sector index", sector_rsi),
            ("Brent crude", brent), ("USD/INR", usdinr), ("S&P 500", spx)) if value is None]
        mildest, severest = self._label_bounds(
            vix, fii_proxy, len(stress),
            sum(value is None for value in (brent, usdinr, spx)))
        unavailable = ""
        if severity(mildest) != severity(severest):
            unavailable = f"{_names(missing)} did not answer"
            logger.warning("[RegimeDetector] %s: %s; the label lies between %s and %s",
                           as_of_date, unavailable, mildest, severest)

        multipliers = dict(settings.REGIME_MULTIPLIERS.get(
            label, settings.REGIME_MULTIPLIERS["NORMAL"]))
        narrative = self._build_narrative(label, vix, fii_proxy, sector_rsi)
        if missing:
            narrative += f" Not answered: {_names(missing)}."
        if stress:
            parts = []
            if brent is not None:
                parts.append(f"Brent 5d {brent:+.1f}%")
            if usdinr is not None:
                parts.append(f"USDINR 5d {usdinr:+.2f}%")
            if spx is not None:
                parts.append(f"S&P last {spx:+.1f}%")
            narrative += (f" Global stress [{', '.join(stress)}]: "
                          + ", ".join(parts) + ".")

        snap = RegimeSnapshot(
            regime_label      = label,
            vix_value         = vix,
            fii_proxy_5d_pct  = fii_proxy,
            sector_rsi        = sector_rsi,
            multipliers       = multipliers,
            narrative         = narrative,
            as_of_date        = as_of_date.isoformat(),
            brent_5d_pct      = brent,
            usdinr_5d_pct     = usdinr,
            spx_last_pct      = spx,
            global_stress_signals = stress,
            dark_inputs       = missing,
            unavailable       = unavailable,
            floor_label       = mildest if unavailable else "",
        )
        logger.info(
            "[RegimeDetector] %s | VIX=%s | FII_proxy=%s%% | RSI=%s → %s",
            as_of_date, _num(vix, ".1f"), _num(fii_proxy, ".2f"), _num(sector_rsi, ".1f"),
            label,
        )
        return snap

    # ------------------------------------------------------------------
    # Signal fetchers
    # ------------------------------------------------------------------

    def _closes(self, ticker: str, period: str, last_day: date) -> pd.Series | None:
        """`ticker`'s daily closes from Yahoo up to and including `last_day`
        (each bar's own exchange date), oldest first; None when Yahoo errs,
        returns no dated close, or none in the _MAX_INPUT_AGE_DAYS up to
        `last_day`. A close that is not a number is dropped."""
        try:
            import yfinance as yf
            df = yf.Ticker(ticker).history(period=period)
        except Exception as exc:
            logger.warning("[RegimeDetector] %s fetch failed: %s", ticker, exc)
            return None
        if df is None or df.empty or "Close" not in df or not isinstance(
                df.index, pd.DatetimeIndex):
            logger.warning("[RegimeDetector] %s: no dated closes", ticker)
            return None
        close = pd.to_numeric(df["Close"], errors="coerce")
        close = close[[math.isfinite(v) for v in close]]
        close = close[[ts.date() <= last_day for ts in close.index]]
        if close.empty or (last_day - close.index[-1].date()).days > _MAX_INPUT_AGE_DAYS:
            logger.warning("[RegimeDetector] %s: no close in the %d days up to %s",
                           ticker, _MAX_INPUT_AGE_DAYS, last_day)
            return None
        return close

    def _get_vix(self, as_of_date: date) -> float | None:
        """
        India VIX (^INDIAVIX) at the close of `as_of_date`, or the newest
        session before it. None when it did not answer: never a midpoint.
        """
        close = self._closes(settings.REGIME_VIX_TICKER, "1mo", as_of_date)
        return None if close is None else round(float(close.iloc[-1]), 2)

    def _get_fii_proxy(self, as_of_date: date) -> float | None:
        """
        Nifty 50 (^NSEI) 5-day momentum as proxy for FII net flow direction,
        to the close of `as_of_date`: (close[-1] - close[-6]) / close[-6] * 100.
        None when it did not answer (fewer than 6 closes).
        """
        close = self._closes(settings.REGIME_FII_PROXY_TICKER, "1mo", as_of_date)
        if close is None or len(close) < 6:
            return None
        pct = (close.iloc[-1] - close.iloc[-6]) / close.iloc[-6] * 100.0
        return round(float(pct), 4)

    def _get_sector_rsi(self, sector: str, as_of_date: date) -> float | None:
        """
        RSI(14) of the sector index using Wilder smoothing (pure pandas, no ta-lib),
        to the close of `as_of_date`. Sector index tickers from
        settings.REGIME_SECTOR_TICKERS; falls back to ^NSEI. None when neither
        has enough closes.
        """
        ticker_sym = settings.REGIME_SECTOR_TICKERS.get(
            sector, settings.REGIME_SECTOR_FALLBACK_TICKER
        )
        close = self._closes(ticker_sym, "3mo", as_of_date)
        if (close is None or len(close) < settings.RSI_PERIOD + 1) and \
                ticker_sym != settings.REGIME_SECTOR_FALLBACK_TICKER:
            # Try fallback ticker if sector ticker gave insufficient data
            close = self._closes(settings.REGIME_SECTOR_FALLBACK_TICKER, "3mo", as_of_date)
        if close is None or len(close) < settings.RSI_PERIOD + 1:
            return None
        return _compute_rsi(close)

    def _get_5d_pct(self, ticker: str, as_of_date: date) -> float | None:
        """5-session % change for a global ticker, over the sessions before
        `as_of_date`. None when it did not answer."""
        close = self._closes(ticker, "1mo", as_of_date - timedelta(days=1))
        if close is None or len(close) < 6:
            return None
        return round(float((close.iloc[-1] - close.iloc[-6]) / close.iloc[-6] * 100.0), 4)

    def _get_last_session_pct(self, ticker: str, as_of_date: date) -> float | None:
        """% move of the last session completed before `as_of_date`. None when
        it did not answer."""
        close = self._closes(ticker, "1mo", as_of_date - timedelta(days=1))
        if close is None or len(close) < 2:
            return None
        return round(float((close.iloc[-1] - close.iloc[-2]) / close.iloc[-2] * 100.0), 4)

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

    @classmethod
    def _label_bounds(cls, vix: float | None, fii_proxy: float | None,
                      n_stress: int, n_dark_global: int) -> tuple[str, str]:
        """(mildest, severest) label the inputs that answered allow (FIX-023):
        a missing VIX read as 0 then as unbounded, a missing Nifty move as
        unbounded rise then fall, each missing global input as not firing then
        firing. The sector RSI never changes a label's severity."""
        rsi = settings.RSI_FALLBACK
        mildest = cls._escalate_label(cls._classify(
            0.0 if vix is None else vix,
            math.inf if fii_proxy is None else fii_proxy, rsi), n_stress)
        severest = cls._escalate_label(cls._classify(
            math.inf if vix is None else vix,
            -math.inf if fii_proxy is None else fii_proxy, rsi), n_stress + n_dark_global)
        return mildest, severest

    @staticmethod
    def _global_stress_signals(
        brent_5d_pct: float | None,
        usdinr_5d_pct: float | None,
        spx_last_pct: float | None,
    ) -> list[str]:
        """Which global-stress conditions fired. None (fetch failed) never
        counts — a network outage must degrade to today's behavior."""
        fired: list[str] = []
        if brent_5d_pct is not None and brent_5d_pct >= settings.REGIME_BRENT_SHOCK_PCT:
            fired.append("brent_shock")
        if usdinr_5d_pct is not None and usdinr_5d_pct >= settings.REGIME_USDINR_STRESS_PCT:
            fired.append("usdinr_stress")
        if spx_last_pct is not None and spx_last_pct <= settings.REGIME_SPX_DROP_PCT:
            fired.append("spx_drop")
        return fired

    @staticmethod
    def _escalate_label(label: str, n_stress: int) -> str:
        """One severity notch when enough independent global signals agree.
        A single noisy signal never escalates on its own."""
        if n_stress < settings.REGIME_GLOBAL_STRESS_MIN_SIGNALS:
            return label
        if label == "RISK_OFF":
            return "MACRO_CRISIS"
        if label == "MACRO_CRISIS":
            return label
        return "RISK_OFF"

    @staticmethod
    def _build_narrative(
        label: str, vix: float | None, fii_proxy: float | None, sector_rsi: float | None
    ) -> str:
        """A missing value reads "n/a"."""
        v, f, r = _num(vix, ".1f"), _num(fii_proxy, "+.2f"), _num(sector_rsi, ".1f")
        narratives = {
            "MACRO_CRISIS": (
                f"MACRO CRISIS regime detected: India VIX {v} (above 22) with "
                f"Nifty 5-day return {f}% indicating FII outflow pressure; "
                "risk_macro weight elevated, growth signals discounted."
            ),
            "RISK_OFF": (
                f"RISK-OFF regime: elevated VIX ({v}) or FII outflow proxy "
                f"({f}% 5-day Nifty); risk_macro carries higher weight today."
            ),
            "RISK_ON": (
                f"RISK-ON regime: VIX {v} (calm), Nifty 5-day {f}% "
                f"(FII inflow proxy), sector RSI {r}; fundamentals and sentiment elevated."
            ),
            "MOMENTUM_EXTENDED": (
                f"MOMENTUM EXTENDED: VIX {v} low, Nifty {f}% inflow, "
                f"sector RSI {r} (overbought > 70); "
                "pattern_analysis elevated for mean-reversion detection."
            ),
            "OVERSOLD": (
                f"OVERSOLD regime: sector RSI {r} (below 30); "
                "pattern_analysis weight elevated for mean-reversion opportunity detection."
            ),
            "NORMAL": (
                f"NORMAL regime: VIX {v}, Nifty 5-day {f}%, "
                f"sector RSI {r}; base learned weights apply."
            ),
        }
        return narratives.get(label, f"Regime: {label}")


def apply_regime_multipliers(
    learned_weights: dict[str, float],
    multipliers: dict[str, float],
    sector: str = "automobile",
) -> dict[str, float]:
    """
    Apply regime multipliers to learned weights and renormalise to sum=1.0.

    Parameters
    ----------
    learned_weights : per-agent learned weights (sum ≈ 1.0)
    multipliers     : per-agent regime multipliers (from RegimeSnapshot.multipliers)
    sector          : used to look up SECTOR_AGENT_REGIME_ROLE for non-automobile sectors

    For non-automobile sectors, each agent is mapped to its canonical automobile role
    via SECTOR_AGENT_REGIME_ROLE before the multiplier lookup.  Agents with no mapping
    entry default to 1.0× (pass-through).

    Returns
    -------
    Renormalised effective weights dict. Agents not in multipliers get 1.0×.
    """
    from core.config import settings as _s
    role_map: dict[str, str] = getattr(_s, "SECTOR_AGENT_REGIME_ROLE", {}).get(sector, {})

    raw: dict[str, float] = {}
    for agent, weight in learned_weights.items():
        canonical_role = role_map.get(agent, agent)  # fall back to own name
        mult = multipliers.get(canonical_role, 1.0)
        raw[agent] = weight * mult

    total = sum(raw.values())
    if total == 0:
        return dict(learned_weights)
    return {agent: round(w / total, 6) for agent, w in raw.items()}

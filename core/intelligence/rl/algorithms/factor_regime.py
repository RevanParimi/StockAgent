"""
core/intelligence/rl/algorithms/factor_regime.py
=================================================
IIMA India Fama-French 4-Factor regime signal.

Source:  www.iimahd.ernet.in/~iffm/Indian-Fama-French-Momentum/
Vintage: 2023-03 (last available as of May 2026)
Factors: SMB (size), HML (value), WML (momentum), MF (market), RF (risk-free)
Coverage: October 1993 onwards — monthly frequency.

NOTE: Data ends March 2023.  Use as a long-run structural prior, NOT a live
      signal.  For live regime, use core/intelligence/regime/detector.py.
      The two complement each other: RegimeDetector = short-run (VIX/FII/RSI),
      factor_regime = long-run structural background (size/style/momentum tilt).

Signal value
------------
WML (Winners Minus Losers): the momentum factor.
  Positive average WML → momentum regime: past winners keep outperforming.
  Negative average WML → reversal regime: sector rotation / mean-reversion.

WeightAdapter integration
--------------------------
get_regime_penalty_scale(agent_name, regime) returns a multiplier in [0.5, 1.0]
for the bias penalty in WeightAdapter._compute_deltas():
  REVERSAL + pattern_analysis/competitive_intel → 0.80 (momentum agents suffer in reversals)
  MOMENTUM + fundamentals/risk_macro            → 0.85 (value agents lag in momentum markets)
  All other cases                               → 1.0 (no change)
  Data stale (>18 months old, AUD-073)          → 1.0 always — a frozen
  dataset stays in prompts as a labeled structural prior but never tilts
  live weight penalties.

Caching
-------
Daily in-process cache + 30-day CSV file cache (mirrors iima_ff_factors.py pattern).
On failure silently returns None — all callers handle None gracefully.
"""

from __future__ import annotations

import io
import logging
from datetime import date
from pathlib import Path
from typing import Literal

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

_IIMA_BASE  = "https://www.iimahd.ernet.in/~iffm/Indian-Fama-French-Momentum"
_INDEX_URL  = f"{_IIMA_BASE}/"
_CACHE_DIR  = Path(__file__).parent.parent.parent.parent / "data" / "cache" / "iima_ff"
_TIMEOUT    = 30
_STALE_AFTER_MONTHS = 18   # newest factor row older than this => background-only

# ---------------------------------------------------------------------------
# In-process daily cache
# ---------------------------------------------------------------------------

_PROCESS_CACHE: dict[str, dict | None] = {}   # { "YYYY-MM-DD": regime_dict | None }


def _today_key() -> str:
    return date.today().isoformat()


# ---------------------------------------------------------------------------
# IIMA download helpers (mirrors scripts/api_exploration/iima_ff_factors.py)
# ---------------------------------------------------------------------------

def _get(url: str):
    import requests
    return requests.get(url, timeout=_TIMEOUT)


def _discover_latest_vintage() -> str:
    import re
    resp = _get(_INDEX_URL)
    resp.raise_for_status()
    prefixes = sorted(set(
        m.group(1)
        for m in re.finditer(r'DATA/(\d{4}-\d{2})_', resp.text)
    ))
    if not prefixes:
        raise RuntimeError("IIMA: no data vintage found on index page")
    return prefixes[-1]


def _download_csv(vintage: str | None = None) -> "pd.DataFrame":
    """Download (or read from cache) the 4-factor monthly CSV."""
    import pandas as pd

    _CACHE_DIR.mkdir(parents=True, exist_ok=True)

    if vintage is None:
        vintage = _discover_latest_vintage()

    filename   = (
        f"{vintage}_FourFactors_and_Market_Returns_Monthly_SurvivorshipBiasAdjusted.csv"
    )
    cache_path = _CACHE_DIR / filename

    if cache_path.exists():
        age_days = (date.today() - date.fromtimestamp(cache_path.stat().st_mtime)).days
        if age_days < 30:
            logger.debug("[factor_regime] Using cached IIMA CSV (%d days old)", age_days)
            return pd.read_csv(cache_path)

    url  = f"{_IIMA_BASE}/DATA/{filename}"
    logger.info("[factor_regime] Downloading IIMA 4-factor CSV: %s", url)
    resp = _get(url)
    resp.raise_for_status()

    df = pd.read_csv(io.StringIO(resp.text))
    df.to_csv(cache_path, index=False)
    return df


# ---------------------------------------------------------------------------
# Regime computation
# ---------------------------------------------------------------------------

def _vintage_is_stale(vintage) -> bool:
    """True when the newest factor row is older than _STALE_AFTER_MONTHS.
    Unparseable vintages count as stale — never grant live influence to data
    we can't date (AUD-073)."""
    import pandas as pd
    try:
        last = pd.to_datetime(str(vintage), errors="coerce")
        if pd.isna(last):
            return True
        return (pd.Timestamp.today() - last).days > _STALE_AFTER_MONTHS * 31
    except Exception:
        return True


def _compute_regime(lookback_months: int = 12) -> dict:
    """Download IIMA CSV and compute momentum + style regime."""
    import pandas as pd

    df = _download_csv()

    recent  = df.tail(lookback_months).copy()
    wml     = recent["WML"].dropna()
    smb     = recent["SMB"].dropna()
    hml     = recent["HML"].dropna()
    mf      = recent["MF"].dropna()

    avg_wml  = float(wml.mean())
    std_wml  = float(wml.std()) or 1.0
    last_wml = float(wml.iloc[-1]) if not wml.empty else 0.0
    z_score  = round((last_wml - avg_wml) / std_wml, 2)

    regime   = "MOMENTUM" if avg_wml > 0 else "REVERSAL"
    strength = "STRONG" if abs(z_score) > 1.5 else ("MODERATE" if abs(z_score) > 0.5 else "WEAK")

    vintage = str(df["Date"].iloc[-1]) if not df.empty else "unknown"
    return {
        "regime":           regime,
        "strength":         strength,
        "z_score":          z_score,
        "avg_wml_pct":      round(avg_wml,        3),
        "last_wml_pct":     round(last_wml,       3),
        "size_tilt":        "SMALL_CAP" if float(smb.mean()) > 0 else "LARGE_CAP",
        "style_tilt":       "VALUE"     if float(hml.mean()) > 0 else "GROWTH",
        "market_factor_avg": round(float(mf.mean()), 3),
        "lookback_months":  lookback_months,
        "data_vintage":     vintage,
        "data_stale":       _vintage_is_stale(vintage),   # AUD-073
        "fetched_at":       _today_key(),
    }


# ---------------------------------------------------------------------------
# Public API — cached daily
# ---------------------------------------------------------------------------

def get_factor_regime(lookback_months: int = 12, force_refresh: bool = False) -> dict | None:
    """
    Return the IIMA 4-factor regime signal, cached daily.

    Returns None on any failure (network, CSV parse, etc.) — callers treat
    None as "no regime data available" and skip the adjustment gracefully.
    """
    key = _today_key()
    if not force_refresh and key in _PROCESS_CACHE:
        return _PROCESS_CACHE[key]

    try:
        regime = _compute_regime(lookback_months=lookback_months)
        logger.info(
            "[factor_regime] Regime: %s %s | WML avg=%.3f%% z=%.2f | %s / %s",
            regime["strength"], regime["regime"],
            regime["avg_wml_pct"], regime["z_score"],
            regime["size_tilt"], regime["style_tilt"],
        )
        _PROCESS_CACHE[key] = regime
        return regime
    except Exception as exc:
        logger.warning("[factor_regime] Failed to compute regime (non-fatal): %s", exc)
        _PROCESS_CACHE[key] = None
        return None


# ---------------------------------------------------------------------------
# Context formatter
# ---------------------------------------------------------------------------

def format_factor_regime_context(regime: dict | None) -> str:
    """
    Format IIMA factor regime for agent prompt injection.

    Returns "" when regime is None or missing (agents ignore it silently).
    """
    if not regime:
        return ""

    stale_tag = " — STALE, background prior only" if regime.get("data_stale") else ""
    lines = [
        f"[IIMA FACTOR REGIME — long-run prior, data through "
        f"{regime.get('data_vintage', 'unknown')}{stale_tag}]",
        f"  Momentum regime: {regime['strength']} {regime['regime']} "
        f"(WML avg={regime['avg_wml_pct']:+.3f}%, z={regime['z_score']:+.2f})",
        f"  Market tilt: {regime['size_tilt']} / {regime['style_tilt']}",
    ]

    if regime["regime"] == "REVERSAL":
        lines.append(
            "  Note: Reversal regime — sector rotation in play; "
            "past winners may lag, laggards may catch up."
        )
    else:
        lines.append(
            "  Note: Momentum regime — recent sector winners likely to keep outperforming."
        )

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# WeightAdapter integration — penalty scaling
# ---------------------------------------------------------------------------

# Agents whose bias penalties are scaled down in each regime.
# Scale < 1.0 means "be more lenient on this agent's misses in this regime —
# the model is structurally disadvantaged, not just wrong."
_REVERSAL_LENIENT_AGENTS = {"pattern_analysis", "competitive_intel", "sales_demand"}
_MOMENTUM_LENIENT_AGENTS = {"fundamentals", "risk_macro"}

_REVERSAL_SCALE = 0.80   # 20% leniency in reversal regime for momentum agents
_MOMENTUM_SCALE = 0.85   # 15% leniency in momentum regime for value/fundamental agents


def get_regime_penalty_scale(agent_name: str, regime: dict | None) -> float:
    """
    Return the bias-penalty multiplier for the given agent under the current regime.

    Used by WeightAdapter._compute_deltas() to apply regime-aware leniency:
      - In REVERSAL regime, pattern-momentum agents are penalised less (regime headwind)
      - In MOMENTUM regime, fundamental/value agents are penalised less (regime headwind)

    Returns 1.0 (no change) when regime is None, WEAK, or agent doesn't match.
    """
    if not regime:
        return 1.0

    # AUD-073: the IIMA series is frozen at 2023-03. A regime read from stale
    # data stays in the prompt as a labeled structural prior, but must never
    # tilt live weight penalties.
    if regime.get("data_stale"):
        return 1.0

    r_type     = regime.get("regime", "")
    r_strength = regime.get("strength", "WEAK")

    # Only apply leniency for MODERATE or STRONG regimes (WEAK = noisy, not structural)
    if r_strength == "WEAK":
        return 1.0

    if r_type == "REVERSAL" and agent_name in _REVERSAL_LENIENT_AGENTS:
        return _REVERSAL_SCALE
    if r_type == "MOMENTUM" and agent_name in _MOMENTUM_LENIENT_AGENTS:
        return _MOMENTUM_SCALE

    return 1.0

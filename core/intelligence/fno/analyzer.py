"""
core/intelligence/fno/analyzer.py
==================================
FnO signal computation from NSE options chain data.

Three signals computed:
  PCR (Put-Call Ratio):  total_put_OI / total_call_OI
    <0.7  → bullish (more calls written, market expects upside)
    >1.5  → bearish (more puts written, market expects downside)
    0.7-1.5 → neutral

  Max Pain: strike where total value of all options (calls + puts) expiring
    worthless is maximised from the option WRITER's perspective.
    = argmin_K [ Σ_calls max(0, K-strike)×OI + Σ_puts max(0, strike-K)×OI ]
    Theory: market makers who wrote options profit maximally at max pain strike.
    Statistical tendency for price to gravitate toward max pain near expiry.

  OI Buildup Direction: net call vs put OI at ATM ±3% range
    call_OI_atm > put_OI_atm × 1.3 → LONG (call writing implies bullish positioning)
    put_OI_atm > call_OI_atm × 1.3 → SHORT (put writing implies bearish)
    else → NEUTRAL
"""
from __future__ import annotations
import logging
from core.schemas.feedback import FnOSnapshot

logger = logging.getLogger(__name__)


class FnOAnalyzer:
    PCR_BULLISH_THRESHOLD = 0.70
    PCR_BEARISH_THRESHOLD = 1.50
    ATM_RANGE_PCT = 0.03         # ±3% of current price = near-ATM zone

    def analyze(
        self,
        chain_data: list[dict],
        current_price: float,
        ticker: str,
        date_str: str,
        near_month_expiry: str | None = None,
    ) -> FnOSnapshot:
        snap = FnOSnapshot(
            date=date_str, ticker=ticker, current_price=current_price,
            near_month_expiry=near_month_expiry,
        )
        if not chain_data:
            return snap
        try:
            snap.pcr = self._compute_pcr(chain_data)
            snap.total_call_oi = sum(
                int(r.get("CE", {}).get("openInterest", 0) or 0) for r in chain_data
            )
            snap.total_put_oi = sum(
                int(r.get("PE", {}).get("openInterest", 0) or 0) for r in chain_data
            )
            snap.max_pain_price = self._compute_max_pain(chain_data)
            snap.oi_buildup_direction = self._compute_oi_buildup(chain_data, current_price)
            snap.atm_strike = self._find_atm_strike(chain_data, current_price)
            if snap.max_pain_price and current_price > 0:
                snap.max_pain_deviation_pct = round(
                    (current_price - snap.max_pain_price) / current_price * 100, 2
                )
        except Exception as exc:
            logger.warning("[FnOAnalyzer] Analysis failed: %s", exc)
        return snap

    def _compute_pcr(self, chain_data: list[dict]) -> float | None:
        total_put = sum(
            int(r.get("PE", {}).get("openInterest", 0) or 0) for r in chain_data
        )
        total_call = sum(
            int(r.get("CE", {}).get("openInterest", 0) or 0) for r in chain_data
        )
        if total_call == 0:
            return None
        return round(total_put / total_call, 3)

    def _compute_max_pain(self, chain_data: list[dict]) -> float | None:
        strikes = [r["strikePrice"] for r in chain_data if "strikePrice" in r]
        if not strikes:
            return None
        min_pain, max_pain_strike = float("inf"), None
        for K in strikes:
            pain = sum(
                max(0.0, K - r["strikePrice"])
                * int(r.get("CE", {}).get("openInterest", 0) or 0)
                + max(0.0, r["strikePrice"] - K)
                * int(r.get("PE", {}).get("openInterest", 0) or 0)
                for r in chain_data
                if "strikePrice" in r
            )
            if pain < min_pain:
                min_pain, max_pain_strike = pain, K
        return float(max_pain_strike) if max_pain_strike is not None else None

    def _compute_oi_buildup(self, chain_data: list[dict], current_price: float) -> str:
        near_atm = [
            r for r in chain_data
            if abs(r.get("strikePrice", 0) - current_price) / max(current_price, 1)
            <= self.ATM_RANGE_PCT
        ]
        call_oi = sum(
            int(r.get("CE", {}).get("openInterest", 0) or 0) for r in near_atm
        )
        put_oi = sum(
            int(r.get("PE", {}).get("openInterest", 0) or 0) for r in near_atm
        )
        if call_oi == 0 and put_oi == 0:
            return "NEUTRAL"
        if put_oi == 0 or (call_oi / max(put_oi, 1)) > 1.3:
            return "LONG"
        if call_oi == 0 or (put_oi / max(call_oi, 1)) > 1.3:
            return "SHORT"
        return "NEUTRAL"

    def _find_atm_strike(self, chain_data: list[dict], current_price: float) -> float | None:
        strikes = [r["strikePrice"] for r in chain_data if "strikePrice" in r]
        if not strikes:
            return None
        return float(min(strikes, key=lambda s: abs(s - current_price)))

"""
core/intelligence/fno/fetcher.py
================================
Fetches NSE options chain for a given stock symbol using the `nse` package.

NSE option chain response structure (relevant fields):
  response["records"]["data"] → list of dicts:
    {"strikePrice": 1000, "expiryDate": "28-May-2026",
     "CE": {"openInterest": 1234, "lastPrice": 45.2, ...},
     "PE": {"openInterest": 5678, "lastPrice": 12.3, ...}}
  response["records"]["underlyingValue"] → current spot price

Only near-month (closest expiry) contracts are extracted to avoid far-month noise.
"""
from __future__ import annotations
import logging
import pathlib
import tempfile
from datetime import datetime

logger = logging.getLogger(__name__)


class FnOFetcher:
    def __init__(self) -> None:
        self.near_month_expiry: str | None = None
        try:
            from services.data.fetchers.nse_client import make_nse, track_for_cleanup
            self._nse = make_nse()               # private temp dir (AUD-086)
            track_for_cleanup(self, self._nse)   # rmtree on GC (AUD-017)
        except Exception as exc:
            logger.warning("[FnOFetcher] nse package unavailable: %s", exc)
            self._nse = None

    def close(self) -> None:
        """Release the NSE session and its temp dir (AUD-017)."""
        from services.data.fetchers.nse_client import close_nse
        close_nse(self._nse)
        self._nse = None

    def fetch_option_chain(self, ticker: str) -> list[dict] | None:
        """
        Fetch near-month options chain for ticker.
        Returns list of chain rows (each with strikePrice, CE, PE dicts), or None on failure.
        Sets self.near_month_expiry to the near-month expiry date string on success.
        """
        if self._nse is None:
            return None
        try:
            raw = self._nse.optionChain(ticker)
        except Exception as exc:
            logger.warning("[FnOFetcher] optionChain(%s) failed: %s", ticker, exc)
            return None
        try:
            records = raw.get("records", {})
            all_rows = records.get("data", [])
            if not all_rows:
                return None
            # Sort chronologically (NSE format: "28-May-2026")
            raw_expiries = {r["expiryDate"] for r in all_rows if "expiryDate" in r}
            expiry_dates = sorted(
                raw_expiries,
                key=lambda s: datetime.strptime(s, "%d-%b-%Y"),
            )
            if not expiry_dates:
                return all_rows
            near_month_expiry = expiry_dates[0]
            self.near_month_expiry = near_month_expiry
            return [r for r in all_rows if r.get("expiryDate") == near_month_expiry]
        except Exception as exc:
            logger.warning("[FnOFetcher] parsing optionChain for %s failed: %s", ticker, exc)
            return None

    def get_underlying_price(self, ticker: str) -> float | None:
        if self._nse is None:
            return None
        try:
            raw = self._nse.optionChain(ticker)
            return float(raw.get("records", {}).get("underlyingValue", 0) or 0) or None
        except Exception:
            return None

"""
core/intelligence/rl/stores/offmarket_fetcher.py
================================================
Off-market signal fetcher — block deals, bulk deals, pre-open auction.

Architecture: next-day leading signal.
  - Fetched at END of daily_review for day T (non-fatal).
  - Injected at START of daily_review for day T+1 into market_context_today.

Why: Block/bulk deals and pre-open price gaps are institutional positioning signals
that occur during the trading session. By 4:30pm close they are already reflected in
price — but they tell us WHY the price moved, which helps FeedbackAgent attribute the
miss more accurately the next day.
"""
from __future__ import annotations
import logging
from core.schemas.feedback import OffMarketSignals, BlockDeal, BulkDeal

logger = logging.getLogger(__name__)


class OffMarketFetcher:
    def __init__(self) -> None:
        try:
            from nse import NSE
            self._nse = NSE()
        except Exception as exc:
            logger.warning("[OffMarketFetcher] nse package unavailable: %s", exc)
            self._nse = None

    def fetch_all(self, ticker: str, date_str: str) -> OffMarketSignals:
        signals = OffMarketSignals(date=date_str, ticker=ticker)
        if self._nse is None:
            return signals
        try:
            signals.block_deals = self._fetch_block_deals(ticker)
        except Exception as exc:
            logger.debug("[OffMarketFetcher] block deals failed: %s", exc)
        try:
            signals.bulk_deals = self._fetch_bulk_deals(ticker)
        except Exception as exc:
            logger.debug("[OffMarketFetcher] bulk deals failed: %s", exc)
        try:
            self._enrich_pre_open(signals, ticker)
        except Exception as exc:
            logger.debug("[OffMarketFetcher] pre-open failed: %s", exc)
        signals = self._compute_summary(signals)
        return signals

    def _fetch_block_deals(self, ticker: str) -> list[BlockDeal]:
        raw = self._nse.blockDeals()
        if not raw:
            return []
        return [
            BlockDeal(
                symbol=r.get("symbol", ""),
                client_name=r.get("clientName", ""),
                trade_type="BUY" if r.get("buySell", "").upper() == "BUY" else "SELL",
                quantity=int(r.get("quantity", 0) or 0),
                price=float(r.get("price", 0) or 0),
                trade_value_cr=round(
                    int(r.get("quantity", 0) or 0) * float(r.get("price", 0) or 0) / 1e7, 2
                ),
            )
            for r in raw
            if r.get("symbol", "").upper() == ticker.upper()
        ]

    def _fetch_bulk_deals(self, ticker: str) -> list[BulkDeal]:
        raw = self._nse.bulkDeals()
        if not raw:
            return []
        return [
            BulkDeal(
                symbol=r.get("symbol", ""),
                client_name=r.get("clientName", ""),
                trade_type="BUY" if r.get("buySell", "").upper() == "BUY" else "SELL",
                quantity=int(r.get("quantity", 0) or 0),
                price=float(r.get("price", 0) or 0),
                trade_value_cr=round(
                    int(r.get("quantity", 0) or 0) * float(r.get("price", 0) or 0) / 1e7, 2
                ),
            )
            for r in raw
            if r.get("symbol", "").upper() == ticker.upper()
        ]

    def _enrich_pre_open(self, signals: OffMarketSignals, ticker: str) -> None:
        q = self._nse.quote(ticker)
        if not q:
            return
        po = q.get("preOpenMarket", {})
        if not po:
            return
        signals.pre_open_price = float(po.get("IEP", 0) or 0) or None
        prev_close = float(q.get("priceInfo", {}).get("previousClose", 0) or 0)
        if signals.pre_open_price and prev_close:
            signals.pre_open_vs_prev_close_pct = round(
                (signals.pre_open_price - prev_close) / prev_close * 100, 3
            )
        signals.pre_open_volume = int(po.get("totalTradedVolume", 0) or 0) or None

    def _compute_summary(self, signals: OffMarketSignals) -> OffMarketSignals:
        all_deals = signals.block_deals + signals.bulk_deals
        parts = []
        if all_deals:
            buy_val = sum(d.trade_value_cr for d in all_deals if d.trade_type == "BUY")
            sell_val = sum(d.trade_value_cr for d in all_deals if d.trade_type == "SELL")
            signals.total_trade_value_cr = round(buy_val + sell_val, 2)
            if buy_val > sell_val * 1.5:
                signals.net_institutional_direction = "BUY"
            elif sell_val > buy_val * 1.5:
                signals.net_institutional_direction = "SELL"
            elif buy_val > 0 or sell_val > 0:
                signals.net_institutional_direction = "MIXED"
            if signals.block_deals:
                parts.append(
                    f"{len(signals.block_deals)} block deal(s) "
                    f"[net {signals.net_institutional_direction}, "
                    f"₹{signals.total_trade_value_cr:.1f}Cr]"
                )
            if signals.bulk_deals:
                parts.append(f"{len(signals.bulk_deals)} bulk deal(s)")
        if signals.pre_open_vs_prev_close_pct is not None:
            sign = "+" if signals.pre_open_vs_prev_close_pct > 0 else ""
            parts.append(f"pre-open gap {sign}{signals.pre_open_vs_prev_close_pct:.2f}%")
        signals.summary = "; ".join(parts)
        return signals

    @staticmethod
    def build_context_string(signals: OffMarketSignals) -> str:
        """Format signals into an LLM-readable context string for injection."""
        if not signals.summary:
            return ""
        lines = [f"[OFF-MARKET SIGNALS from {signals.date}]"]
        lines.append(
            f"  Institutional activity: {signals.net_institutional_direction} "
            f"(₹{signals.total_trade_value_cr:.1f}Cr total)"
        )
        for d in signals.block_deals:
            lines.append(
                f"  Block deal: {d.client_name} {d.trade_type} {d.quantity:,} "
                f"shares @ ₹{d.price:.1f} (₹{d.trade_value_cr:.1f}Cr)"
            )
        for d in signals.bulk_deals:
            lines.append(
                f"  Bulk deal: {d.client_name} {d.trade_type} {d.quantity:,} "
                f"shares @ ₹{d.price:.1f} (₹{d.trade_value_cr:.1f}Cr)"
            )
        if signals.pre_open_vs_prev_close_pct is not None:
            sign = "+" if signals.pre_open_vs_prev_close_pct > 0 else ""
            lines.append(
                f"  Pre-open gap: {sign}{signals.pre_open_vs_prev_close_pct:.2f}% "
                f"(IEP ₹{signals.pre_open_price:.1f})"
            )
        return "\n".join(lines)

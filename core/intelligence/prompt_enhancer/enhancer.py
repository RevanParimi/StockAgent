"""
core/intelligence/prompt_enhancer/enhancer.py
=============================================
P4 — PromptEnhancer: miss_counter → Search Queries

Reads the miss_counter from a ticker's LearningLedger and produces
additional context search queries for each agent, targeting the top-N
factors the system has historically missed.

Called once per month-start (generate_forecast.py). Output is cached in
a per-ticker JSON file for the cycle and loaded lazily by each agent at
run() time via PredictionStore.

Self-regulating behaviour
--------------------------
Enhancements are regenerated each month-start from the CURRENT miss_counter.
If a previously-missed factor stops appearing (queries found the data), its
count stays flat → it falls out of top_n → deprioritised automatically.
No special code needed; the ranking handles it.
"""

from __future__ import annotations

import json
import logging
from datetime import date
from pathlib import Path
from typing import TYPE_CHECKING

from core.config import settings

if TYPE_CHECKING:
    from core.schemas.feedback import LearningLedger

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Template map: miss factor → {agent_name: query_template}
# Placeholders: {ticker}, {date}, {month}, {year}
# ---------------------------------------------------------------------------

MISS_FACTOR_TO_QUERY_TEMPLATE: dict[str, dict[str, str]] = {
    "FII_outflow_spike": {
        "risk_macro": "{ticker} FII DII net flows provisional {date}",
        "sentiment":  "FII selling India equity {month} {year}",
    },
    "crude_oil_spot_price": {
        "raw_materials": "Brent crude spot price today {date}",
        "risk_macro":    "crude oil impact Indian automobile sector {month}",
    },
    "RBI_policy_surprise": {
        "risk_macro":   "RBI MPC meeting upcoming schedule {year}",
        "fundamentals": "RBI repo rate decision impact auto loan rates",
    },
    "INR_depreciation": {
        "risk_macro":    "USD INR exchange rate {date}",
        "raw_materials": "INR depreciation impact import cost automobile {year}",
    },
    "month_end_inventory_flush": {
        "sales_demand": "{ticker} dealer inventory days channel check {month}",
    },
}


class PromptEnhancer:
    """
    Stateless utility: reads miss_counter and generates extra search queries.

    Parameters
    ----------
    (none — stateless)
    """

    MISS_FACTOR_TO_QUERY_TEMPLATE = MISS_FACTOR_TO_QUERY_TEMPLATE

    def enhance(
        self,
        ticker: str,
        learning_ledger: "LearningLedger",
        top_n: int = 3,
    ) -> dict[str, list[str]]:
        """
        Build extra search queries from the top-N missed factors.

        Returns
        -------
        {agent_name: [extra_query_1, extra_query_2, ...]}

        Returns {} when miss_counter is empty (first cycle — no history yet).
        Substitutes {ticker}, {date}, {month}, {year} with today's values.
        """
        miss_counter = learning_ledger.miss_counter
        if not miss_counter:
            return {}

        # Take the top_n factors by count
        sorted_factors = sorted(miss_counter.items(), key=lambda kv: kv[1], reverse=True)
        top_factors = [factor for factor, _ in sorted_factors[:top_n]]

        today = date.today()
        fmt = {
            "ticker": ticker,
            "date":   today.isoformat(),
            "month":  today.strftime("%B"),
            "year":   str(today.year),
        }

        # Accumulate queries per agent
        agent_queries: dict[str, list[str]] = {}
        for factor in top_factors:
            agent_templates = self.MISS_FACTOR_TO_QUERY_TEMPLATE.get(factor)
            if not agent_templates:
                logger.debug(
                    "[PromptEnhancer] No template for miss factor '%s' — skipped", factor
                )
                continue
            for agent_name, template in agent_templates.items():
                try:
                    query = template.format(**fmt)
                except KeyError as exc:
                    logger.warning(
                        "[PromptEnhancer] Template placeholder error for '%s': %s", factor, exc
                    )
                    query = template  # use raw template as fallback
                agent_queries.setdefault(agent_name, []).append(query)

        logger.info(
            "[PromptEnhancer] Enhanced queries for %s from top-%d miss factors %s: %s agents",
            ticker, top_n, top_factors[:top_n],
            len(agent_queries),
        )
        return agent_queries

    def save_enhancements(
        self,
        ticker: str,
        sector: str,
        enhancements: dict[str, list[str]],
        cycle_id: str,
        learning_ledger: "LearningLedger | None" = None,
    ) -> None:
        """
        Persist enhancements to:
          data/predictions/{sector}/{ticker}/{cycle_id}_prompt_enhancements.json

        Parameters
        ----------
        ticker        : NSE ticker symbol
        sector        : sector name (e.g. "automobile")
        enhancements  : output of enhance()
        cycle_id      : e.g. "MARUTI_2026-04"
        learning_ledger : used to capture the miss_counter snapshot for audit
        """
        base_dir = Path(settings.PREDICTION_DATA_DIR)
        target_dir = base_dir / sector / ticker.upper()
        target_dir.mkdir(parents=True, exist_ok=True)

        path = target_dir / f"{cycle_id}_prompt_enhancements.json"
        tmp  = path.with_suffix(".tmp")

        miss_snapshot: dict[str, int] = {}
        if learning_ledger is not None:
            miss_snapshot = dict(learning_ledger.miss_counter)

        payload = {
            "ticker":               ticker.upper(),
            "cycle_id":             cycle_id,
            "generated_at":         date.today().isoformat(),
            "based_on_miss_counter": miss_snapshot,
            "agent_enhancements":   enhancements,
        }
        tmp.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        tmp.replace(path)
        logger.info(
            "[PromptEnhancer] Saved enhancements for %s cycle %s (%d agents enhanced)",
            ticker, cycle_id, len(enhancements),
        )

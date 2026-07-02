"""
core/intelligence/rl/workflows/preopen_check.py
================================================
Living Envelope (RL Phase 2.5), Component 3 — pre-open sanity check.

Market-level overnight shock check, run once per trading day before the
09:15 IST open (scheduler job `preopen_shock_check`, 08:45 IST). NEVER
raises — any failure degrades to a neutral/no-op result.

Cost contract: exactly 1 Serper search + 1 FAST-tier LLM call PER
INVOCATION, regardless of how many tickers are checked.

Flow
----
1. Gate on RL_PREOPEN_CHECK_ENABLED — off means zero side effects.
2. One Serper search for overnight India-market / GIFT-Nifty / global macro
   headlines (via services.data.fetchers.news.fetch_news_context,
   max_queries=1).
3. One LLM_MODEL_FAST call (json_object) rating overall overnight shock
   severity/direction. Parsed defensively — garbage JSON degrades to
   severity 0.0 / direction "neutral".
4. severity < RL_PREOPEN_SHOCK_SEVERITY -> log + return (no per-ticker work).
5. severity >= threshold -> for each (ticker, sector), load today's envelope
   forecast direction via PredictionStore. A contradiction (predicted UP in
   risk_off, or predicted DOWN in risk_on) is flagged and triggers
   regenerate_envelope(trigger="preopen_shock"). Per-ticker failures are
   isolated — the loop continues.

See docs/superpowers/specs/2026-06-13-living-envelope-design.md section 5.
"""

from __future__ import annotations

import json
import logging
import re
from datetime import date

from core.config import settings
from core.config.prompts.shared.preopen_check import (
    PREOPEN_SYSTEM_PROMPT, PREOPEN_USER_TEMPLATE,
)

logger = logging.getLogger(__name__)

_VALID_DIRECTIONS = {"risk_off", "risk_on", "neutral"}

_NEUTRAL_RESULT = {
    "severity": 0.0,
    "direction": "neutral",
    "flagged": [],
    "reforecasts": [],
}


def _strip_think(raw: str) -> str:
    return re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL).strip()


def _call_llm(system_prompt: str, user_prompt: str) -> tuple[str, str]:
    """LLM client pattern mirrors control_lane._call_llm. May raise — caller handles."""
    from services.clients.llm_client import JSON_MODE_EXTRA_BODY, get_llm_client

    client = get_llm_client()
    model = settings.LLM_MODEL_FAST
    resp = client.chat.completions.create(
        model=model,
        temperature=0.2,
        max_tokens=300,
        response_format={"type": "json_object"},
        extra_body=JSON_MODE_EXTRA_BODY,
        messages=[{"role": "system", "content": system_prompt},
                  {"role": "user", "content": user_prompt}],
    )
    return resp.choices[0].message.content or "", model


def _fetch_overnight_context(today: date) -> str:
    """One Serper search for overnight India-market / global macro headlines.

    Serper/NewsAPI failure -> fetch_news_context returns a "[No results...]"
    placeholder string, not an exception. Non-fatal either way.
    """
    from services.data.fetchers.news import fetch_news_context

    query = (
        f"India stock market GIFT Nifty global overnight macro news "
        f"{today.isoformat()}"
    )
    try:
        return fetch_news_context([query], max_queries=1)
    except Exception as exc:
        logger.warning("[preopen_check] News fetch failed (non-fatal): %s", exc)
        return ""


def _rate_overnight_shock(today: date, news_context: str) -> dict:
    """One LLM_MODEL_FAST call rating overnight shock severity/direction.

    NEVER raises — any failure (LLM down, garbage JSON, etc.) returns the
    neutral default {"severity": 0.0, "direction": "neutral", "headline": ""}.
    """
    try:
        system = PREOPEN_SYSTEM_PROMPT.format()
        user = PREOPEN_USER_TEMPLATE.format(
            date=today.isoformat(), news_context=(news_context or "")[:3000],
        )
        raw, _model = _call_llm(system, user)
        data = json.loads(_strip_think(raw))

        severity = float(data.get("severity", 0.0))
        severity = max(0.0, min(1.0, severity))

        direction = str(data.get("direction", "neutral")).strip().lower()
        if direction not in _VALID_DIRECTIONS:
            direction = "neutral"

        headline = str(data.get("headline", ""))[:120]

        return {"severity": severity, "direction": direction, "headline": headline}
    except Exception as exc:
        logger.warning(
            "[preopen_check] LLM shock rating failed (non-fatal, treating as "
            "neutral/no-shock): %s", exc,
        )
        return {"severity": 0.0, "direction": "neutral", "headline": ""}


def _default_tickers() -> list[tuple[str, str]]:
    """All managed tickers across the four sector configs.

    Reads backend.sectors.<sector>.config.settings.TICKERS for each of the
    four known sectors. Non-fatal: a sector module that fails to import
    contributes no tickers.
    """
    _SECTORS = ["automobile", "banking_bfsi", "it_sector", "renewable_energy"]
    out: list[tuple[str, str]] = []
    for sector in _SECTORS:
        try:
            mod = __import__(
                f"backend.sectors.{sector}.config.settings", fromlist=["TICKERS"],
            )
            for ticker in getattr(mod, "TICKERS", []):
                out.append((ticker, sector))
        except Exception as exc:
            logger.warning(
                "[preopen_check] Could not load tickers for sector %s (non-fatal): %s",
                sector, exc,
            )
    return out


def _predicted_direction(ticker: str, sector: str, date_str: str) -> str | None:
    """Today's predicted direction ("UP" | "DOWN" | "FLAT") from the current
    envelope, or None if there is no envelope / no forecast row for today.

    Mirrors the daily_review access pattern: store.load_envelope(cycle_id)
    -> envelope.get_forecast(date_str) -> predicted_verdict.
    """
    from core.intelligence.rl.stores.prediction_store import PredictionStore

    store = PredictionStore(ticker, sector=sector)
    cycle_id = store.current_cycle_id()
    envelope = store.load_envelope(cycle_id)
    if envelope is None:
        return None

    today_forecast = envelope.get_forecast(date_str)
    if today_forecast is None:
        return None

    verdict = (today_forecast.predicted_verdict or "").upper()
    if verdict in {"BUY", "STRONG BUY"}:
        return "UP"
    if verdict in {"SELL", "STRONG SELL"}:
        return "DOWN"
    return "FLAT"


def _contradicts(predicted_direction: str, shock_direction: str) -> bool:
    """predicted UP in risk_off, or predicted DOWN in risk_on."""
    if predicted_direction == "UP" and shock_direction == "risk_off":
        return True
    if predicted_direction == "DOWN" and shock_direction == "risk_on":
        return True
    return False


def run_preopen_check(tickers: list[tuple[str, str]] | None = None) -> dict:
    """Market-level overnight shock check.

    Parameters
    ----------
    tickers : list of (ticker, sector) pairs, or None to check all managed
        tickers across the four sectors.

    Returns
    -------
    dict with keys: severity, direction, flagged, reforecasts (+ optional
    "skipped" reason). NEVER raises.
    """
    if not getattr(settings, "RL_PREOPEN_CHECK_ENABLED", True):
        return {**_NEUTRAL_RESULT, "skipped": "disabled"}

    today = date.today()

    # --- 1 Serper call -------------------------------------------------- #
    news_context = _fetch_overnight_context(today)

    # --- 1 LLM call ------------------------------------------------------- #
    rating = _rate_overnight_shock(today, news_context)
    severity = rating["severity"]
    direction = rating["direction"]
    headline = rating["headline"]

    threshold = getattr(settings, "RL_PREOPEN_SHOCK_SEVERITY", 0.7)

    if severity < threshold:
        logger.info(
            "[preopen_check] severity=%.2f direction=%s below threshold %.2f — "
            "no per-ticker action. headline=%r",
            severity, direction, threshold, headline,
        )
        return {
            "severity": severity, "direction": direction,
            "flagged": [], "reforecasts": [], "headline": headline,
        }

    logger.warning(
        "[preopen_check] SHOCK DETECTED severity=%.2f direction=%s headline=%r — "
        "scanning managed tickers for contradictions",
        severity, direction, headline,
    )

    if tickers is None:
        tickers = _default_tickers()

    date_str = today.isoformat()
    flagged: list[str] = []
    reforecasts: list[str] = []

    for ticker, sector in tickers:
        try:
            predicted_direction = _predicted_direction(ticker, sector, date_str)
            if predicted_direction is None:
                continue

            if not _contradicts(predicted_direction, direction):
                continue

            flagged.append(ticker)
            logger.warning(
                "[preopen_check] %s: predicted=%s contradicts overnight "
                "direction=%s — triggering re-forecast",
                ticker, predicted_direction, direction,
            )

            from core.intelligence.rl.workflows.generate_forecast import regenerate_envelope

            envelope = regenerate_envelope(
                ticker, sector,
                reason=f"pre-open shock: {headline}",
                trigger="preopen_shock",
            )
            if envelope is not None:
                reforecasts.append(ticker)
        except Exception as exc:
            logger.warning(
                "[preopen_check] %s: per-ticker check failed (non-fatal): %s",
                ticker, exc,
            )

    return {
        "severity": severity, "direction": direction,
        "flagged": flagged, "reforecasts": reforecasts, "headline": headline,
    }

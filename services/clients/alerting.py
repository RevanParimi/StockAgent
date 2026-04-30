"""
tools/alerting.py
=================
Notification system for score and verdict changes.

Supported channels (configured via ALERT_CHANNELS in .env):
  console  — print to stdout (always works, no setup)
  file     — append to ALERT_LOG_FILE
  webhook  — HTTP POST to ALERT_WEBHOOK_URL (Slack/Discord/custom)

Public API
----------
AlertManager().check_and_alert(report, store) → list[Alert]
AlertManager().send(alert)
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import requests

from core.config import settings
from core.schemas.pipeline import FinalReport

logger = logging.getLogger(__name__)


@dataclass
class Alert:
    """A single alert event."""
    ticker: str
    alert_type: str          # "score_change" | "verdict_change" | "new_ticker"
    message: str
    severity: str            # "info" | "warning" | "critical"
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    details: dict = field(default_factory=dict)

    def to_slack_payload(self) -> dict:
        emoji = {"info": "ℹ️", "warning": "⚠️", "critical": "🚨"}.get(self.severity, "📊")
        return {
            "text": f"{emoji} *Automobile Agent Alert* — {self.ticker}",
            "blocks": [
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": (
                            f"{emoji} *{self.ticker}* — {self.alert_type.replace('_', ' ').title()}\n"
                            f"{self.message}\n"
                            f"_Triggered at {self.timestamp}_"
                        ),
                    },
                }
            ],
        }

    def to_log_line(self) -> str:
        return (
            f"[{self.timestamp}] [{self.severity.upper()}] "
            f"{self.ticker} | {self.alert_type} | {self.message}"
        )


class AlertManager:
    """
    Detects changes between the latest pipeline run and the previous one,
    then dispatches alerts to configured channels.
    """

    def check_and_alert(
        self,
        report: FinalReport,
        store,                  # ScoreStore instance (avoids circular import)
    ) -> list[Alert]:
        """
        Compare new report against stored history and fire alerts where needed.

        Returns list of Alert objects that were fired.
        """
        alerts: list[Alert] = []
        ticker = report.ticker

        delta = store.get_score_delta(ticker)
        verdict_changed = store.get_verdict_changed(ticker)
        previous = store.get_previous(ticker)

        # First-time ticker — just inform
        if previous is None:
            alert = Alert(
                ticker=ticker,
                alert_type="new_ticker",
                message=(
                    f"First run recorded. Score={report.final_score:.3f} "
                    f"Verdict={report.verdict}"
                ),
                severity="info",
                details={"final_score": report.final_score, "verdict": report.verdict},
            )
            alerts.append(alert)

        else:
            # Score change alert
            if delta is not None and abs(delta) >= settings.ALERT_SCORE_CHANGE_THRESHOLD:
                direction = "▲" if delta > 0 else "▼"
                severity = "warning" if abs(delta) < 0.20 else "critical"
                alert = Alert(
                    ticker=ticker,
                    alert_type="score_change",
                    message=(
                        f"Score changed {direction}{abs(delta):.3f} "
                        f"({previous['final_score']:.3f} → {report.final_score:.3f})"
                    ),
                    severity=severity,
                    details={
                        "previous_score": previous["final_score"],
                        "new_score": report.final_score,
                        "delta": delta,
                    },
                )
                alerts.append(alert)

            # Verdict change alert
            if settings.ALERT_ON_VERDICT_CHANGE and verdict_changed:
                severity = "critical" if (
                    "STRONG" in report.verdict or "STRONG" in previous["verdict"]
                ) else "warning"
                alert = Alert(
                    ticker=ticker,
                    alert_type="verdict_change",
                    message=(
                        f"Verdict changed: {previous['verdict']} → {report.verdict}"
                    ),
                    severity=severity,
                    details={
                        "previous_verdict": previous["verdict"],
                        "new_verdict": report.verdict,
                    },
                )
                alerts.append(alert)

        for alert in alerts:
            self.send(alert)

        return alerts

    def send(self, alert: Alert) -> None:
        """Dispatch an alert to all configured channels."""
        for channel in settings.ALERT_CHANNELS:
            try:
                if channel == "console":
                    self._send_console(alert)
                elif channel == "file":
                    self._send_file(alert)
                elif channel == "webhook":
                    self._send_webhook(alert)
                else:
                    logger.warning("[Alerting] Unknown channel: %s", channel)
            except Exception as exc:
                logger.error(
                    "[Alerting] Failed to send via channel=%s: %s", channel, exc
                )

    # ------------------------------------------------------------------
    # Channel implementations
    # ------------------------------------------------------------------

    def _send_console(self, alert: Alert) -> None:
        prefix = {"info": "[ INFO ]", "warning": "[  WARN ]", "critical": "[ ALERT ]"}.get(
            alert.severity, "[ INFO ]"
        )
        print(f"\n{prefix} {alert.to_log_line()}")

    def _send_file(self, alert: Alert) -> None:
        log_path = Path(settings.ALERT_LOG_FILE)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open("a", encoding="utf-8") as f:
            f.write(alert.to_log_line() + "\n")
        logger.debug("[Alerting] Alert written to %s", log_path)

    def _send_webhook(self, alert: Alert) -> None:
        if not settings.ALERT_WEBHOOK_URL:
            logger.debug("[Alerting] ALERT_WEBHOOK_URL not set — skipping webhook")
            return
        payload = alert.to_slack_payload()
        resp = requests.post(
            settings.ALERT_WEBHOOK_URL,
            json=payload,
            timeout=10,
        )
        resp.raise_for_status()
        logger.info("[Alerting] Webhook sent for %s (%s)", alert.ticker, alert.alert_type)

"""Append-only JSONL store for graded outcome rows.

Deliberately separate from advice_ledger.jsonl. The ledger is the audit
authority for what the system told the user and its append-only property is
enforced by test_advice_ledger_append_only; a nightly grading job must not be
in the business of rewriting it.
"""
from __future__ import annotations

import json
import logging
import re
from pathlib import Path

from backend.shared.schemas.audit import AuditOutcome
from core.config import settings

logger = logging.getLogger(__name__)

_USER_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


class AuditOutcomeStore:
    """One file per user: data/portfolio/<user_id>/advice_outcomes.jsonl."""

    def __init__(self, user_id: str | None = None, base_dir: str | None = None) -> None:
        self.user_id = (user_id or settings.PORTFOLIO_DEFAULT_USER_ID).strip()
        if not _USER_ID_RE.fullmatch(self.user_id):
            raise ValueError(
                f"invalid user_id {self.user_id!r} — allowed: [A-Za-z0-9_-], max 64 chars"
            )
        self._dir = Path(base_dir or settings.PORTFOLIO_DATA_DIR) / self.user_id
        self._dir.mkdir(parents=True, exist_ok=True)

    @property
    def path(self) -> Path:
        return self._dir / "advice_outcomes.jsonl"

    def append(self, row: AuditOutcome) -> None:
        with open(self.path, "a", encoding="utf-8") as fh:
            fh.write(row.model_dump_json() + "\n")

    def load_all(self) -> list[AuditOutcome]:
        path = self.path
        if not path.exists():
            return []
        out: list[AuditOutcome] = []
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                out.append(AuditOutcome(**json.loads(line)))
            except Exception:
                continue     # a corrupt line must never break the report
        return out

    def existing_keys(self) -> set[tuple[str, int]]:
        """Every (ref, horizon_td) already graded — the idempotency guard."""
        return {row.key() for row in self.load_all()}

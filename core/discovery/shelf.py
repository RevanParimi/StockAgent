"""Compass Phase B — Discovery Shelf store. Full implementation in Task 11."""
from __future__ import annotations

from backend.shared.schemas.discovery import Shelf


class ShelfStore:
    def load(self) -> Shelf:
        return Shelf()

"""
tests/unit/test_ticker_registry_drift.py
=========================================
Drift guard between each active sector's managed `TICKERS` list
(backend.sectors.<sector>.config.settings.TICKERS) and the global
`TICKER_SECTOR` routing map (backend.sectors.registry.TICKER_SECTOR).

Direction 1 (managed -> routing): every ticker a sector actively manages
must be present in TICKER_SECTOR and route back to that same sector. If a
managed ticker is missing or mismapped, sector-routing for that ticker is
silently wrong.

Direction 2 (routing -> managed) is intentionally NOT an equality check:
TICKER_SECTOR legitimately covers MORE tickers than any sector's managed
TICKERS list (e.g. NTPC/POWERGRID are routed to renewable_energy for
sector-detection purposes but are not in the scheduled/managed set). Instead
we assert structural invariants: no ticker is double-booked across two
active sectors' TICKERS lists, and every TICKERS entry is a clean
uppercase/no-whitespace symbol.
"""
from __future__ import annotations

import importlib

import pytest

from backend.sectors import registry

ACTIVE_SECTORS: list[str] = [
    "automobile",
    "banking_bfsi",
    "it_sector",
    "renewable_energy",
]


def _managed_tickers(sector: str) -> list[str]:
    mod = importlib.import_module(f"backend.sectors.{sector}.config.settings")
    return list(getattr(mod, "TICKERS", []))


# ---------------------------------------------------------------------------
# Direction 1: managed TICKERS -> TICKER_SECTOR
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("sector", ACTIVE_SECTORS)
def test_managed_tickers_present_and_correctly_mapped(sector: str) -> None:
    missing: list[str] = []
    mismatched: list[tuple[str, str]] = []

    for ticker in _managed_tickers(sector):
        mapped = registry.TICKER_SECTOR.get(ticker)
        if mapped is None:
            missing.append(ticker)
        elif mapped != sector:
            mismatched.append((ticker, mapped))

    assert not missing, (
        f"[{sector}] managed ticker(s) missing from registry.TICKER_SECTOR: {missing}. "
        f"Add them to TICKER_SECTOR mapped to '{sector}'."
    )
    assert not mismatched, (
        f"[{sector}] managed ticker(s) mapped to the WRONG sector in "
        f"registry.TICKER_SECTOR: {mismatched} (expected '{sector}')."
    )


# ---------------------------------------------------------------------------
# Direction 2: structural invariants on the managed TICKERS lists themselves
# ---------------------------------------------------------------------------

def test_no_ticker_double_booked_across_active_sectors() -> None:
    seen: dict[str, str] = {}
    duplicates: list[tuple[str, str, str]] = []

    for sector in ACTIVE_SECTORS:
        for ticker in _managed_tickers(sector):
            if ticker in seen and seen[ticker] != sector:
                duplicates.append((ticker, seen[ticker], sector))
            else:
                seen[ticker] = sector

    assert not duplicates, (
        f"Ticker(s) appear in more than one active sector's TICKERS list: {duplicates}"
    )


@pytest.mark.parametrize("sector", ACTIVE_SECTORS)
def test_managed_tickers_are_clean_uppercase_symbols(sector: str) -> None:
    bad: list[str] = []
    for ticker in _managed_tickers(sector):
        if ticker != ticker.strip() or ticker != ticker.upper() or not ticker:
            bad.append(ticker)

    assert not bad, f"[{sector}] TICKERS entries are not clean uppercase/no-whitespace: {bad}"

"""
Three Loops PI — task A1: one router, `generic` fallback.

Before A1 there were two independent resolution paths and they disagreed on
every disabled sector (spec §2.1):

    ticker      API path (SectorRegistry)     RL path (sector_router)
    SUNPHARMA   AutomobileAgentOrchestrator   GenericSectorOrchestrator
    TITAN       AutomobileAgentOrchestrator   AutomobileAgentOrchestrator

That divergence is what minted the duplicate prediction stores (13 tickers
holding a never-learned `automobile` stub beside their real-sector store).

These tests pin the equivalence itself, not just the current answers: both
entry points must return the *identical class* for a table of tickers
spanning enabled, disabled, unknown and alias cases.
"""
import ast
import pathlib

import pytest

from backend.sectors import detect_sector, get_orchestrator
from backend.sectors import registry
from core.intelligence.rl.workflows import sector_router as sr


# The acceptance table from the A1 card: enabled sectors, disabled sectors,
# the DLF duplicate-key case, an unmapped real ticker (TITAN) and a string
# that is not a ticker at all.
ACCEPTANCE_TICKERS = [
    "SUNPHARMA",    # pharma       — disabled
    "RELIANCE",     # oilgas       — disabled
    "TATASTEEL",    # metals       — disabled
    "ITC",          # fmcg         — disabled
    "LT",           # capgoods     — disabled
    "BHARTIARTL",   # telecom      — disabled
    "DLF",          # realestate   — disabled, duplicate literal key
    "TITAN",        # unmapped     — jewellery, no entry
    "ZOMATO",       # retail       — disabled
    "SOMETHINGNEW", # unknown      — not a ticker
]


def _automobile_cls():
    from backend.sectors.automobile.pipeline.orchestrator import AutomobileAgentOrchestrator
    return AutomobileAgentOrchestrator


def _generic_cls():
    from backend.sectors.generic.pipeline.orchestrator import GenericSectorOrchestrator
    return GenericSectorOrchestrator


# ── the equivalence itself ────────────────────────────────────────────────

@pytest.mark.parametrize("ticker", ACCEPTANCE_TICKERS)
def test_api_and_rl_paths_return_the_same_class(ticker):
    """§2.1's routing table must print zero DIVERGE rows."""
    sector = detect_sector(ticker)
    api_cls = get_orchestrator(sector)
    rl_cls = sr.get_orchestrator_class(sector)
    assert api_cls is rl_cls, (
        f"DIVERGE {ticker} (sector={sector}): "
        f"API={api_cls.__name__} RL={rl_cls.__name__}"
    )


@pytest.mark.parametrize("ticker", ACCEPTANCE_TICKERS)
def test_no_automobile_graph_for_a_non_automobile_ticker(ticker):
    """The rule that stops the duplicate-store bleed."""
    sector = detect_sector(ticker)
    assert sector != "automobile", f"{ticker} should not resolve to automobile"
    assert get_orchestrator(sector) is not _automobile_cls()
    assert sr.get_orchestrator_class(sector) is not _automobile_cls()


# ── fallbacks land on generic, not automobile ─────────────────────────────

def test_unknown_ticker_resolves_to_generic():
    assert detect_sector("SOMETHINGNEW") == "generic"
    assert detect_sector("TITAN") == "generic"


def test_disabled_sector_routes_to_the_generic_graph():
    assert get_orchestrator("pharma") is _generic_cls()
    assert sr.get_orchestrator_class("pharma") is _generic_cls()


def test_generic_sector_routes_to_the_generic_graph():
    """`generic` itself used to diverge: the RL path gave the generic graph,
    the API path degraded it to automobile because `generic` has no toggle
    entry. It is a routing target, not a toggleable sector."""
    assert get_orchestrator("generic") is _generic_cls()
    assert sr.get_orchestrator_class("generic") is _generic_cls()


def test_enabled_native_sectors_still_route_natively():
    from backend.sectors.banking_bfsi.pipeline.orchestrator import BankingAgentOrchestrator
    from backend.sectors.it_sector.pipeline.orchestrator import ITAgentOrchestrator
    from backend.sectors.renewable_energy.pipeline.orchestrator import RenewableAgentOrchestrator

    expected = {
        "automobile": _automobile_cls(),
        "banking_bfsi": BankingAgentOrchestrator,
        "it_sector": ITAgentOrchestrator,
        "renewable_energy": RenewableAgentOrchestrator,
    }
    for sector, cls in expected.items():
        assert get_orchestrator(sector) is cls
        assert sr.get_orchestrator_class(sector) is cls


def test_generic_orchestrator_is_instantiable_from_the_rl_entry_point():
    orch = sr.get_orchestrator("pharma")
    assert type(orch).__name__ == "GenericSectorOrchestrator"
    assert orch.SECTOR_NAME == "generic"


# ── the rollback line ─────────────────────────────────────────────────────

def test_flag_off_restores_automobile_degradation(monkeypatch):
    """`sectors.generic_fallback_enabled: false` is the named rollback.

    It restores the pre-A1 fallback TARGET on both paths — the paths stay
    unified, they just degrade to automobile again.
    """
    monkeypatch.setattr(registry, "_generic_fallback_enabled", lambda: False)

    assert detect_sector("SOMETHINGNEW") == "automobile"
    assert get_orchestrator("pharma") is _automobile_cls()
    assert sr.get_orchestrator_class("pharma") is _automobile_cls()

    # still unified — the rollback must not resurrect the divergence
    for ticker in ACCEPTANCE_TICKERS:
        sector = detect_sector(ticker)
        assert get_orchestrator(sector) is sr.get_orchestrator_class(sector)


def test_flag_defaults_to_true():
    assert registry._generic_fallback_enabled() is True


# ── the ticker map itself ─────────────────────────────────────────────────

def _ticker_sector_literal_keys() -> list[str]:
    """Literal keys of the TICKER_SECTOR dict, read via AST.

    A regex over the source miscounts (the map is two entries per line and
    the values are quoted too), which is how the earlier draft concluded
    there was one duplicate when there are two.
    """
    tree = ast.parse(pathlib.Path(registry.__file__).read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        target = getattr(node, "target", None)
        if isinstance(node, ast.AnnAssign) and getattr(target, "id", "") == "TICKER_SECTOR":
            return [k.value for k in node.value.keys]
    raise AssertionError("TICKER_SECTOR literal not found in registry.py")


def test_ticker_sector_has_no_duplicate_literal_keys():
    """A duplicate key is silent in Python — the last one wins. `DLF` was
    mapped to `infra` and then to `realestate` for months. This fails CI the
    next time one is added."""
    keys = _ticker_sector_literal_keys()
    duplicates = sorted({k for k in keys if keys.count(k) > 1})
    assert not duplicates, f"duplicate TICKER_SECTOR keys: {duplicates}"
    assert len(keys) == len(registry.TICKER_SECTOR)


def test_dlf_resolves_to_realestate():
    """The conflict is settled in favour of realestate — which is also what
    the duplicate silently produced, so no mapping changes."""
    assert detect_sector("DLF") == "realestate"


# ── one source for the native-sector set ──────────────────────────────────

def test_native_sectors_agrees_everywhere():
    from core.portfolio import promotion

    assert sr.NATIVE_SECTORS == registry.NATIVE_SECTORS
    assert promotion.NATIVE_SECTORS == registry.NATIVE_SECTORS
    assert promotion.SUPPORTED_SECTORS == registry.NATIVE_SECTORS
    assert registry.NATIVE_SECTORS == frozenset(
        {"automobile", "banking_bfsi", "it_sector", "renewable_energy"}
    )


@pytest.mark.parametrize("module", ["core.intelligence.rl.workflows.sector_router",
                                    "core.portfolio.promotion"])
def test_native_sectors_is_imported_not_redeclared(module):
    """Equality alone would pass on three hand-kept copies that happen to
    agree today — which is exactly the state A1 found. Assert the *source*
    only imports the name."""
    import importlib

    mod = importlib.import_module(module)
    tree = ast.parse(pathlib.Path(mod.__file__).read_text(encoding="utf-8"))

    imported = any(
        isinstance(node, ast.ImportFrom)
        and any(a.name == "NATIVE_SECTORS" for a in node.names)
        for node in ast.walk(tree)
    )
    assigned = [
        node for node in ast.walk(tree)
        if isinstance(node, (ast.Assign, ast.AnnAssign))
        and any(
            getattr(t, "id", None) == "NATIVE_SECTORS"
            for t in (node.targets if isinstance(node, ast.Assign) else [node.target])
        )
    ]
    assert imported, f"{module} should import NATIVE_SECTORS from the registry"
    assert not assigned, f"{module} re-declares NATIVE_SECTORS — that is the A1 bug"

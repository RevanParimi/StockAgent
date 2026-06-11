"""Task 15: chat get_ticker_dossier tool + RL insight bug fixes.

Covers docs/superpowers/plans/2026-06-11-ticker-dossier.md Task 15:
- _chat_tool_ticker_dossier(ticker) renders the ticker dossier digest.
- _dispatch_chat_tool routes "get_ticker_dossier" to it.
- _sector_for_ticker resolves sector via managed tickers, then directory scan,
  falling back to "automobile".

Also covers a drift guard: every tool name handled by _dispatch_chat_tool must
have a matching schema entry in _CHAT_TOOLS, otherwise the LLM can never call it.
"""
import ast
import asyncio
import inspect
import json


def test_dossier_tool_reads_digest(tmp_path, monkeypatch):
    import services.api.routes.ui_data as ui
    sector_dir = tmp_path / "automobile" / "MARUTI"
    sector_dir.mkdir(parents=True)
    dossier = {"ticker": "MARUTI", "sector": "automobile",
               "created_at": "2026-06-01", "last_updated": "2026-06-11",
               "current_thesis": "BUY on rural recovery"}
    (sector_dir / "MARUTI_dossier.json").write_text(json.dumps(dossier), encoding="utf-8")
    monkeypatch.setattr(ui, "_PREDICTIONS_DIR", tmp_path)
    out = asyncio.run(ui._chat_tool_ticker_dossier("maruti"))
    assert "MARUTI dossier" in out
    assert "rural recovery" in out


def test_dossier_tool_empty_when_missing(tmp_path, monkeypatch):
    import services.api.routes.ui_data as ui
    monkeypatch.setattr(ui, "_PREDICTIONS_DIR", tmp_path)
    assert asyncio.run(ui._chat_tool_ticker_dossier("GHOST")) == ""


def test_dispatch_routes_dossier_tool(monkeypatch):
    import services.api.routes.ui_data as ui

    async def fake(t):
        return f"DOSSIER:{t}"

    monkeypatch.setattr(ui, "_chat_tool_ticker_dossier", fake)
    out = asyncio.run(ui._dispatch_chat_tool("get_ticker_dossier", {"ticker": "TCS"}))
    assert out == "DOSSIER:TCS"


def test_sector_resolution_helper(monkeypatch, tmp_path):
    import services.api.routes.ui_data as ui
    (tmp_path / "banking_bfsi" / "HDFCBANK").mkdir(parents=True)
    monkeypatch.setattr(ui, "_PREDICTIONS_DIR", tmp_path)
    monkeypatch.setattr(ui, "_load_mt", lambda: [])  # force directory-scan fallback
    assert ui._sector_for_ticker("HDFCBANK") == "banking_bfsi"
    assert ui._sector_for_ticker("UNKNOWN") == "automobile"


def test_sector_resolution_uses_managed_tickers(monkeypatch, tmp_path):
    import services.api.routes.ui_data as ui
    monkeypatch.setattr(ui, "_PREDICTIONS_DIR", tmp_path)
    monkeypatch.setattr(ui, "_load_mt", lambda: [{"sym": "MARUTI", "sector": "automobile"}])
    assert ui._sector_for_ticker("maruti") == "automobile"


def _dispatched_tool_names() -> set[str]:
    """
    Statically extract every literal tool name compared in
    `_dispatch_chat_tool`'s `if name == "..."` branches, by parsing its source.
    """
    import services.api.routes.ui_data as ui

    source = inspect.getsource(ui._dispatch_chat_tool)
    tree = ast.parse(source)
    names: set[str] = set()

    class Visitor(ast.NodeVisitor):
        def visit_Compare(self, node: ast.Compare) -> None:
            if (
                isinstance(node.left, ast.Name)
                and node.left.id == "name"
                and len(node.ops) == 1
                and isinstance(node.ops[0], ast.Eq)
                and len(node.comparators) == 1
                and isinstance(node.comparators[0], ast.Constant)
                and isinstance(node.comparators[0].value, str)
            ):
                names.add(node.comparators[0].value)
            self.generic_visit(node)

    Visitor().visit(tree)
    return names


def test_every_dispatched_tool_has_a_schema_entry():
    """
    Drift guard: every tool name handled by _dispatch_chat_tool must have a
    matching entry in _CHAT_TOOLS, otherwise the LLM has no way to call it.
    """
    import services.api.routes.ui_data as ui

    dispatched = _dispatched_tool_names()
    schema_names = {t["function"]["name"] for t in ui._CHAT_TOOLS}

    missing = dispatched - schema_names
    assert not missing, f"Tools dispatched but missing _CHAT_TOOLS schema: {missing}"

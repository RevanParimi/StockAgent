"""AUD-099b: prompt-file writer must emit UNBREAKABLE string literals.

The old _safe_triple_quote escaped only embedded triple-quotes; a payload
ending in a single backslash escaped the closing delimiter and broke out
of the string in a file that gets importlib-imported (code injection).
"""
import ast

import pytest

PAYLOADS = [
    'ends with a backslash \\',
    'embedded """ triple quotes',
    'both \\""" and a trailing backslash \\',
    '"""\nimport os\nos.system("pwned")\nX = """',
    'plain multi\nline\nprompt with unicode ₹ and "quotes"',
]


@pytest.mark.parametrize("payload", PAYLOADS)
def test_written_file_is_safe_and_round_trips(tmp_path, payload):
    from services.api.routes.prompts import _write_prompt_file
    f = tmp_path / "prompt_mod.py"
    _write_prompt_file(f, '"""doc"""', payload, "analysis", ["q1"])
    src = f.read_text(encoding="utf-8")

    tree = ast.parse(src)  # must be valid Python
    # SAFETY: only a docstring + the three expected assignments — nothing injected
    for node in tree.body:
        assert isinstance(node, (ast.Expr, ast.Assign)), f"injected node: {ast.dump(node)[:80]}"
    names = [t.id for n in tree.body if isinstance(n, ast.Assign) for t in n.targets]
    assert names == ["SYSTEM_PROMPT", "ANALYSIS_PROMPT", "CONTEXT_SEARCH_QUERIES"]

    ns: dict = {}
    exec(compile(src, "<prompt>", "exec"), ns)   # noqa: S102 — test-only
    assert ns["SYSTEM_PROMPT"] == payload         # exact round-trip
    assert ns["ANALYSIS_PROMPT"] == "analysis"
    assert ns["CONTEXT_SEARCH_QUERIES"] == ["q1"]

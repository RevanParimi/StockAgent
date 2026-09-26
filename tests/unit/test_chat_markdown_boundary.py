"""SA-001: guards for the chat Markdown rendering boundary.

The browser behaviour itself is tested in tests/frontend/chat_markdown.test.mjs
(real Chromium, real ChatOverlay sink); the last test here runs that suite.
The static tests keep the boundary from quietly growing: no new HTML sink in
the prototype client, and every CDN script pinned to exact bytes.
"""
from __future__ import annotations

import base64
import hashlib
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
PROTO = REPO / "src" / "frontend" / "prototypes"
INDEX = PROTO / "index.html"

# Ways to turn a string into live markup or code in a browser.
_SINK = re.compile(
    r"dangerouslySetInnerHTML|\.innerHTML\b|\.outerHTML\b|insertAdjacentHTML|document\.write"
    r"|srcdoc|srcDoc|createContextualFragment|parseFromString|new Function\b|\beval\s*\("
)


# Uses of the Markdown parser itself (portfolio.jsx has an unrelated `marked` array).
_PARSER = re.compile(r"window\.marked\b|saMarkedLib|\bmarked\.(?:parse|parseInline|lexer|use|setOptions|Marked)\b")


def _code_files():
    return sorted(p for p in PROTO.rglob("*") if p.suffix in {".js", ".jsx", ".html"})


def _code_lines(path: Path):
    """Lines that are not whole-line comments (the boundary's own comments name the sink)."""
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip().startswith(("//", "*", "/*")):
            yield line


def test_the_chat_bubble_is_the_only_html_sink_in_the_client():
    found = []
    for path in _code_files():
        for line in _code_lines(path):
            for m in _SINK.finditer(line):
                found.append((path.name, m.group(0), line.strip()))
    assert [(f, s) for f, s, _ in found] == [("sphere.jsx", "dangerouslySetInnerHTML")], found
    assert found[0][2] == "dangerouslySetInnerHTML={{ __html: bubbleHtml }}/>"


# Ways to navigate to a string. React 18 does not block a javascript: URL in
# href={...}, so a model- or tool-supplied URL here would be an equivalent sink.
_URL_SINK = re.compile(
    r"href=\{|src=\{|window\.open\(|openWindow\(|location\.(?:href|assign|replace)\s*[=(]"
    r"|setAttribute\(\s*['\"](?:href|src|action|formaction)"
)


def test_no_dynamic_url_sink_takes_model_or_tool_text():
    found = [(path.name, m.group(0)) for path in _code_files()
             for line in _code_lines(path) for m in _URL_SINK.finditer(line)]
    # sw.js opens the push payload's url, which core/delivery builds server-side
    # ('/#/inbox/<tab>'); no model or tool text reaches it.
    assert found == [("sw.js", "openWindow(")], found


def test_the_bubble_sink_only_receives_rendered_markdown_or_constants():
    src = (PROTO / "sphere.jsx").read_text(encoding="utf-8")
    assignments = re.findall(r"bubbleHtml\s*(\+?=)\s*([^;]+);", src)
    allowed = {("=", "'…'"), ("=", "renderMd(m.text || '')"),
               ("+=", "'<span class=\"chat-cursor\">▌</span>'")}
    assert assignments and set(assignments) <= allowed, assignments
    render_md = re.search(r"function renderMd\(text\) \{(.*?)\n\}", src, re.S).group(1)
    assert "marked" not in render_md, "renderMd must not call the raw Markdown parser"


def test_only_the_boundary_module_touches_the_markdown_parser():
    users = sorted({p.name for p in _code_files()
                    if any(_PARSER.search(line) for line in _code_lines(p))})
    assert users == ["chat-markdown.js", "index.html"], users


def _script_tags(html: str):
    return re.findall(r"<script\b([^>]*)>", html)


def test_every_cdn_script_is_pinned_to_exact_bytes():
    html = INDEX.read_text(encoding="utf-8")
    external = [attrs for attrs in _script_tags(html) if 'src="https://' in attrs]
    assert len(external) == 5, external   # react, react-dom, babel, marked, dompurify
    for attrs in external:
        src = re.search(r'src="([^"]+)"', attrs).group(1)
        assert re.search(r"@\d+\.\d+\.\d+/", src), f"not an exact version: {src}"
        assert re.search(r'integrity="sha384-[A-Za-z0-9+/=]{64}"', attrs), f"no SRI: {src}"
        assert 'crossorigin="anonymous"' in attrs, f"SRI needs CORS: {src}"


def test_the_boundary_loads_in_order_before_any_app_code():
    html = INDEX.read_text(encoding="utf-8")
    pos = {name: html.find(needle) for name, needle in {
        "marked": "npm/marked@",
        "handoff": "delete window.marked;",
        "dompurify": "npm/dompurify@",
        "boundary": '<script src="chat-markdown.js"></script>',
        "app": 'type="text/babel"',
    }.items()}
    assert all(v >= 0 for v in pos.values()), pos
    assert pos["marked"] < pos["handoff"] < pos["dompurify"] < pos["boundary"] < pos["app"], pos


def test_the_service_worker_shell_includes_the_boundary_module():
    sw = (PROTO / "sw.js").read_text(encoding="utf-8")
    assert "'/chat-markdown.js'" in sw


def test_browser_harness_libraries_match_the_production_pins():
    """package.json must pin the exact versions index.html loads, so the browser
    suite serves the same bytes; when node_modules exists, check the hashes too."""
    html = INDEX.read_text(encoding="utf-8")
    dev = json.loads((REPO / "package.json").read_text(encoding="utf-8"))["devDependencies"]
    files = {"react": "umd/react.development.js", "react-dom": "umd/react-dom.development.js",
             "@babel/standalone": "babel.min.js", "marked": "marked.min.js",
             "dompurify": "dist/purify.min.js"}
    for pkg, rel in files.items():
        m = re.search(rf'src="https://[^"]*/{re.escape(pkg)}@(\d+\.\d+\.\d+)/{re.escape(rel)}"'
                      rf'\s+integrity="(sha384-[^"]+)"', html)
        assert m, f"{pkg} not loaded from index.html as expected"
        version, integrity = m.groups()
        assert dev.get(pkg) == version, f"package.json pins {pkg}@{dev.get(pkg)}, index.html loads {version}"
        local = REPO / "node_modules" / pkg / rel
        if local.exists():
            digest = "sha384-" + base64.b64encode(hashlib.sha384(local.read_bytes()).digest()).decode()
            assert digest == integrity, f"node_modules/{pkg}/{rel} does not match index.html's SRI"


def test_chat_markdown_browser_suite():
    """Runs the real-browser suite (needs node, `npm ci`, and Playwright's Chromium)."""
    node = shutil.which("node")
    if not node:
        pytest.skip("node is not on PATH")
    if not (REPO / "node_modules" / "playwright").exists():
        pytest.skip("node_modules missing: run `npm ci`")
    proc = subprocess.run([node, "--test", "tests/frontend/chat_markdown.test.mjs"], cwd=REPO,
                          capture_output=True, text=True, encoding="utf-8", timeout=600)
    out = proc.stdout + proc.stderr
    if "Executable doesn't exist" in out:
        pytest.skip("Chromium missing: run `npx playwright install chromium`")
    assert proc.returncode == 0, out[-4000:]

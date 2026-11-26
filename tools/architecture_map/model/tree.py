"""Logic trees: the walkthrough's branching logic as data.

In the curated YAML a tree is a block of text, one node a line, two spaces of
indentation per level. A line starting with `| ` continues the node above it.
Blank lines are ignored. Example:

    What did stock X close at on session D?
      both closes present
        within tolerance ─► the first value
        | ("agree")
      neither ─► None

The model keeps it as nested {text, children} (what the viewer draws), and
TREES.md draws it back with ├── and └──.
"""
from __future__ import annotations

INDENT = "  "
MORE = "| "


class TreeError(ValueError):
    """A tree the curator wrote that cannot be read; the message names the line."""


def parse_tree(text: str) -> list[dict]:
    """The roots of a tree; raises TreeError naming the bad line."""
    roots: list[dict] = []
    stack: list[dict] = []           # stack[d] is the last node at depth d
    for number, raw in enumerate(text.split("\n"), start=1):
        line = raw.rstrip()
        if not line.strip():
            continue
        if line.startswith("\t") or "\t" in line[:len(line) - len(line.lstrip())]:
            raise TreeError(f"line {number}: indented with a tab")
        spaces = len(line) - len(line.lstrip(" "))
        body = line[spaces:]
        if body.startswith(MORE) or body == MORE.strip():
            if not stack:
                raise TreeError(f"line {number}: continues a node that does not exist")
            stack[-1]["text"] += "\n" + body[len(MORE):]
            continue
        if spaces % len(INDENT):
            raise TreeError(f"line {number}: indented by {spaces} spaces, not a multiple of 2")
        depth = spaces // len(INDENT)
        if depth > len(stack):
            raise TreeError(f"line {number}: indented two levels deeper than the line above")
        node = {"text": body, "children": []}
        if depth == 0:
            roots.append(node)
        else:
            stack[depth - 1]["children"].append(node)
        del stack[depth:]
        stack.append(node)
    return roots


def render_tree(roots: list[dict]) -> list[str]:
    """The tree drawn with branch characters, one string per line."""
    lines: list[str] = []
    for root in roots:
        first, *more = root["text"].split("\n")
        lines.append(first)
        lines += [("│   " if root["children"] else "    ") + part for part in more]
        _render(root["children"], "", lines)
    return lines


def _render(children: list[dict], prefix: str, lines: list[str]) -> None:
    for position, node in enumerate(children):
        last = position == len(children) - 1
        first, *more = node["text"].split("\n")
        lines.append(prefix + ("└── " if last else "├── ") + first)
        below = prefix + ("    " if last else "│   ")
        lines += [below + ("│   " if node["children"] else "") + part for part in more]
        _render(node["children"], below, lines)

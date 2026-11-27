"""Logic trees: the walkthrough's branching logic as data.

In the curated YAML a tree is a block of text, one node a line, two spaces of
indentation per level. A line starting with `| ` continues the node above it.
Blank lines are ignored. Example:

    What did stock X close at on session D?
      both closes present
        within tolerance ─► the first value
        | ("agree")
      neither ─► None

A node may start with flow marks, each followed by a space (MAP-002). They say
how the viewer draws the flowchart; TREES.md shows the text without them.

    > text           "then": it follows the node above it at the same level,
                     instead of being one of the parent's parts
    ? text           a decision (a diamond)
    ?! cond ─► text  a decision whose `─►` result ends that path
    ! text           an end (an outcome)

`>` comes first (`> ? text`). A text that starts with one of these characters
without a space after it is plain text.

The model keeps it as nested {text, children, and `kind`, `ends`, `then` only
where marked} (what the viewer draws), and TREES.md draws it back with ├── and
└──.
"""
from __future__ import annotations

INDENT = "  "
MORE = "| "
ARROW = "─►"
KINDS = {"?": {"kind": "decision"}, "?!": {"kind": "decision", "ends": True},
         "!": {"kind": "end"}}


class TreeError(ValueError):
    """A tree the curator wrote that cannot be read; the message names the line."""


def _marks(body: str, number: int) -> dict:
    """The node's text and its flow marks."""
    node: dict = {}
    seen: list[str] = []
    while True:
        mark, space, rest = body.partition(" ")
        if not space or mark not in (">", *KINDS):
            break
        if mark == ">" and ">" in seen:
            raise TreeError(f"line {number}: > is written once")
        if mark == ">" and seen:
            raise TreeError(f"line {number}: > comes before the other marks")
        if mark in KINDS and any(s in KINDS for s in seen):
            raise TreeError(f"line {number}: a node is a decision or an end, not both")
        seen.append(mark)
        body = rest.lstrip(" ")
        if mark == ">":
            node["then"] = True
        else:
            node.update(KINDS[mark])
    if body.strip() in ("", ">", *KINDS):
        raise TreeError(f"line {number}: a mark with no text")
    return {"text": body, "children": [], **node}


def parse_tree(text: str) -> list[dict]:
    """The roots of a tree; raises TreeError naming the bad line."""
    roots: list[dict] = []
    stack: list[dict] = []           # stack[d] is the last node at depth d
    lines_of: dict[int, int] = {}    # id(node) -> the line it starts on
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
        node = _marks(body, number)
        lines_of[id(node)] = number
        if depth == 0:
            if node.get("then"):
                raise TreeError(f"line {number}: > has nothing to follow: a first-level line "
                                "starts its own tree")
            roots.append(node)
        else:
            siblings = stack[depth - 1]["children"]
            if node.get("then"):
                if not siblings:
                    raise TreeError(f"line {number}: > has nothing above it to follow")
                if siblings[-1].get("kind") == "end":
                    raise TreeError(f"line {number}: nothing follows an end")
            siblings.append(node)
        del stack[depth:]
        stack.append(node)
    _check(roots, lines_of)
    return roots


def _check(nodes: list[dict], lines_of: dict[int, int]) -> None:
    """The rules that need a node's whole text and children."""
    for node in nodes:
        number = lines_of[id(node)]
        if node.get("ends") and ARROW not in node["text"]:
            raise TreeError(f"line {number}: ?! needs a {ARROW} result to end with")
        if node.get("kind") == "end" and node["children"]:
            raise TreeError(f"line {number}: an end has no children")
        _check(node["children"], lines_of)


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

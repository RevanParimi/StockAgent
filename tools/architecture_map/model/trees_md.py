"""TREES.md: the walkthrough's trees, drawn from the model so they cannot drift."""
from __future__ import annotations

from tools.architecture_map.model.tree import render_tree

KT_SECTION_1 = "../TECHNICAL_DESIGN.md#1-reading-the-evidence"


def _leaf(text: str, children: list[dict] | None = None) -> dict:
    return {"text": text, "children": children or []}


def _block(roots: list[dict]) -> list[str]:
    return ["```", *render_tree(roots), "```", ""]


def _dotted(label: str, width: int) -> str:
    return f"{label} {'.' * max(2, width - len(label))}"


def _number(module_id: str) -> str:
    """"M1.2" -> "1.2", the sub-module number the walkthrough shows."""
    return module_id[1:]


def _names(model: dict) -> dict[str, str]:
    names = {m["id"]: f"{m['id']} {m['short']}" for m in model["modules"]}
    names |= {s["id"]: f"{s['id']} {s['name']}" for m in model["modules"] for s in m["submodules"]}
    names |= {s["id"]: s["name"] for s in model["stores"]}
    names |= {e["id"]: e["name"] for e in model["externals"]}
    return names


def _product_tree(model: dict) -> list[dict]:
    width = max(len(m["short"]) for m in model["modules"]) + 4
    return [_leaf(model["product"], [
        _leaf(f"{m['id']:<4} {_dotted(m['short'], width)} {m['summary']}")
        for m in model["modules"]])]


def _flow_tree(model: dict) -> list[dict]:
    names = _names(model)
    grouped: dict[str, list[dict]] = {}
    for flow in model["flows"]:
        grouped.setdefault(flow["from"], []).append(
            _leaf(f"─► {names[flow['to']]}: {flow['what']}"))
    return [_leaf("What travels between the parts (from ─► to)",
                  [_leaf(names[source], children) for source, children in grouped.items()])]


def _code_tree(entries: list[dict], parent: str = "") -> list[dict]:
    """The code map, a child's path shown below its parent's."""
    out = []
    for entry in entries:
        path = entry["path"]
        label = path[len(parent):] if parent and path.startswith(parent) else path
        out.append(_leaf(f"{label:<24} {entry['note']}",
                         _code_tree(entry.get("children") or [], path)))
    return out


def _clock_line(job: dict, width: int) -> str:
    schedule = job["schedule"]
    first, *later = schedule["time"].split(", ")
    also = f" (also {', '.join(later)})" if later else ""
    gate = f"  [flag {', '.join(job['gates'])}]" if job["gates"] else ""
    label = job["id"]
    if schedule["group"] == "daily":
        label += f" ({'every day' if schedule['when'] == 'Daily' else schedule['when']})"
    return f"{first:<6} {_dotted(label, width)} {job['module']:<6} {job['does']}{also}{gate}"


def _clock(model: dict) -> list[dict]:
    jobs = model["jobs"]
    width = max(len(f"{j['id']} (every day)") for j in jobs) + 2
    groups = (("Daily (every day, or Monday to Friday)", "daily"), ("Weekly", "weekly"),
              ("Monthly and yearly", "calendar"))
    roots = []
    for title, group in groups:
        chosen = sorted((j for j in jobs if j["schedule"]["group"] == group),
                        key=lambda j: (j["schedule"]["sort"], j["id"]))
        column = max((len(j["schedule"]["when"]) for j in chosen), default=0)
        lines = []
        for job in chosen:
            when = "" if group == "daily" else f"{job['schedule']['when']:<{column}}  "
            lines.append(_leaf(when + _clock_line(job, width)))
        roots.append(_leaf(title, lines))
    return roots


def _production_by_key(model: dict) -> dict[str, dict]:
    return {p["key"]: p for p in model["production"] if p.get("key")}


def _value(value) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, dict):
        return ", ".join(f"{k}: {_value(v)}" for k, v in value.items())
    if isinstance(value, list):
        return "[" + ", ".join(_value(v) for v in value) + "]"
    return str(value)


def _facts(model: dict, sub: dict) -> list[str]:
    """The bullet list under a sub-module's tree: files, functions, switches, stores, jobs."""
    out = []
    switches = {s["key"]: s for s in model["switches"]}
    production = _production_by_key(model)
    if sub["python_files"]:
        out.append("- Files: " + ", ".join(f"`{f}`" for f in sub["python_files"]))
    other = [f for f in sub["files"] if not f.endswith(".py")]
    if other:
        out.append("- Also: " + ", ".join(f"`{f}`" for f in other))
    if sub["code"]:
        out.append("- Functions: " + ", ".join(f"`{c.partition('::')[2]}`" for c in sub["code"]))
    for key in sub["config"]:
        record = switches[key]
        line = f"- `{key}` = `{_value(record['default'])}` ({record['default_source']})"
        if key in production:
            entry = production[key]
            line += (f"; production: `{_value(entry['value'])}` ({entry['source']}, "
                     f"as of {entry['as_of']})")
        out.append(line)
    writes = [s["name"] for s in model["stores"] if sub["id"] in s["writers"]]
    reads = [s["name"] for s in model["stores"] if sub["id"] in s["readers"]]
    if writes:
        out.append("- Writes: " + ", ".join(writes))
    if reads:
        out.append("- Reads: " + ", ".join(reads))
    jobs = [j["id"] for j in model["jobs"] if j["module"] == sub["id"]]
    if jobs:
        out.append("- Jobs: " + ", ".join(f"`{j}`" for j in jobs))
    routes = [r for r in model["routes"] if r["module"] == sub["id"]]
    if routes:
        out.append(f"- Routes: {len(routes)} (listed in `model.json`)")
    return out


def _module_section(model: dict, module: dict) -> list[str]:
    width = max(len(s["name"]) for s in module["submodules"]) + 4
    out = [f"## {module['id']}: {module['name']}", "",
           *_block([_leaf(f"{module['id']} {module['short']}", [
               _leaf(f"{_number(s['id'])} {_dotted(s['name'], width)} {s['summary']}")
               for s in module["submodules"]])])]
    for sub in module["submodules"]:
        out += [f"### {_number(sub['id'])} {sub['name']}", ""]
        out += _block(sub["logic"])
        facts = _facts(model, sub)
        if facts:
            out += [*facts, ""]
    return out


def _stores_section(model: dict) -> list[str]:
    names = _names(model)
    out = ["## Stores: where state lives", "",
           "| Store | Path | Holds | Written by | Read by |", "|---|---|---|---|---|"]
    for store in model["stores"]:
        out.append("| " + " | ".join([
            store["name"], f"`{store['path']}`", store["holds"],
            ", ".join(names[w] if w in names else w for w in store["writers"]),
            ", ".join(names[r] if r in names else r for r in store["readers"])]) + " |")
    return out + [""]


def _production_section(model: dict) -> list[str]:
    switches = {s["key"]: s for s in model["switches"]}
    out = ["## Production values", "",
           f"Cited to [KT section 1]({KT_SECTION_1}), not read from production. Each is the value "
           "as of its date.", "", "| Setting | Repository default | Production | As of | Note |",
           "|---|---|---|---|---|"]
    for entry in model["production"]:
        key = entry.get("key")
        label = f"`{key}`" if key else entry["name"]
        default = f"`{_value(switches[key]['default'])}`" if key else "—"
        out.append(f"| {label} | {default} | `{_value(entry['value'])}` | {entry['as_of']} | "
                   f"{entry.get('note', '')} |")
    return out + [""]


def _trace_section(model: dict) -> list[str]:
    out = []
    for trace in model["traces"]:
        steps = [_leaf(f"{s['when']:<12} {s['text']}  ({', '.join(s['refs'])})")
                 for s in trace["steps"]]
        out += [f"## {trace['title']}", "", *_block([_leaf(trace["title"], steps)])]
    return out


def _stop(step: dict) -> str:
    """Where a tour stop looks: its view and, if it has one, its target."""
    view = "close up" if step["preset"] == "focus" else f"{step['preset']} view"
    return f"{view}: {step['ref']}" if step.get("ref") else view


def _tour_section(model: dict) -> list[str]:
    out = []
    for tour in model["tours"]:
        stops = [_leaf(f"{n}  {s['caption']}  ({_stop(s)})")
                 for n, s in enumerate(tour["steps"], start=1)]
        out += [f"## {tour['title']}", "", *_block([_leaf(tour["title"], stops)])]
    return out


def render(model: dict) -> str:
    stamp = model["stamp"]
    inspected = f"`{stamp['commit']}`"
    if stamp.get("uncommitted_code"):
        inspected += " (with uncommitted changes to the code)"
    out = ["# StockAgent architecture, as trees", "",
           "Generated by `python tools/architecture_map/model/generate.py` from the code and from "
           "`tools/architecture_map/model/curated/`. Do not edit it by hand: change the curated "
           f"files and run the generator. Code inspected: {inspected}.", "",
           model["reading"].strip(), "", "## Part 0: Start here", "",
           "### 0.1 The product in one tree", "", *_block(_product_tree(model)),
           "### 0.2 How the modules feed each other", "", *_block(_flow_tree(model)),
           "### 0.3 Where the code lives", "",
           *_block([_leaf("StockAgent/", _code_tree(model["code_map"]))]),
           "### 0.4 One day on the clock (IST)", "", *_block(_clock(model)),
           model["clock_note"].strip(), ""]
    for module in model["modules"]:
        out += _module_section(model, module)
    out += _stores_section(model)
    out += _production_section(model)
    out += _trace_section(model)
    out += _tour_section(model)
    return "\n".join(out).rstrip("\n") + "\n"

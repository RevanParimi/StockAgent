# The architecture map

Developer documentation: nothing here ships in the app, and the app reads none of it.

| File | What it is |
|---|---|
| [index.html](index.html) | The map in 3D: one self-contained file. Open it by double click. It works offline and asks for nothing from the network. Generated; never edit it. |
| [TREES.md](TREES.md) | The same content as text trees (generated). |
| `model.json` | The model both are drawn from (generated). |
| [DESIGN.md](DESIGN.md) | The map's own design rules. A new visual element goes here first. |
| [UI-CHECKLIST.md](UI-CHECKLIST.md) | The interface checklist each map story passes. |
| [walkthrough-2026-11-26.md](walkthrough-2026-11-26.md) | A dated reading copy of the walkthrough. |

## Open it

Open `docs/architecture-map/index.html` in a browser that draws WebGL (any current Chrome,
Firefox, Edge or Safari). Without WebGL it says so, and the legend, search and the panel still show
every module (a flat 2D view is MAP-005's).

What you see: the three heights are what people see, the product flowing left to right, and storage;
the platform is the frame under the product; measurement and operations sit on a ring outside it.
Moving dots show which way each flow runs. Click a module (or choose it in the legend on the left):
it opens into its parts, and the panel on the right shows how a part decides as a flowchart
(diamond: a decision; pill: a start or an outcome; dashed box: a list of details).

**Manager** shows the logic, stores, jobs and flows in plain words. **Developer** adds files,
functions, routes and settings, each with the repository default and, where
[KT section 1](../TECHNICAL_DESIGN.md#1-reading-the-evidence) states one, the production value
with its source and date. The header says which commit the map was read from.

## Keys

| Key | What it does |
|---|---|
| `1` `2` `3` `4` | Front, top, side and below views (see DESIGN.md for what each answers) |
| `R` | Reset the view |
| `/` | Search modules, parts, stores, jobs, settings, functions and files |
| `P` | Pause or resume motion |
| `← → ↑ ↓` and `+ −` | Turn and zoom the 3D view, once it has the focus (Tab to it) |
| `Shift` + arrows | Move the 3D view sideways, once it has the focus |
| `Esc` | Close the dialog, then the panel |
| `?` | The list of keys |

A part has its own address, so a document or a chat can point into the map: `index.html#m=M5.2`
opens the advisor's flowchart; add `&v=dev` for the developer view.

## Keep it true

The model is generated from the code and from the curated files in
`tools/architecture_map/model/curated/`. After a code change run

```text
python tools/architecture_map/model/generate.py
```

and commit what it writes; the CI guard (`check.py`) fails otherwise. In a tree, a line may start
with `>` (follows the line above), `?` (a decision), `?!` (a decision whose result ends the path)
or `!` (an outcome): `tools/architecture_map/model/tree.py` describes them. TREES.md shows the text
without the marks.

## Rebuild the page

The page holds a copy of the model, taken when it was built. After a change to the model or to the
viewer (`tools/architecture_map/viewer/`):

```text
cd tools/architecture_map/viewer
npm ci          # pinned versions; install scripts are not run (.npmrc)
npm run build   # writes docs/architecture-map/index.html
```

A test fails when the committed page was not built from the committed viewer source, and when its
copy of the model's modules, logic, flows, stores, jobs, settings or production values differs from
`model.json`: rebuild after such a change. File lists, line counts, routes and the commit shown in
the header (`Code inspected`) are only as new as the last rebuild.

## Tests

`npm run test:frontend` at the repository root runs `tests/frontend/architecture_map.test.mjs`
(the built page in Chromium with software WebGL, opened from disk with the network off) and
`architecture_map_logic.test.mjs` (layout, flowchart rules, colours and contrast, the rebuild
check). Neither needs the viewer's own packages.

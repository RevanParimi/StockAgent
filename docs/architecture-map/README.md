# The architecture map

Developer documentation: nothing here ships in the app, and the app reads none of it.

| File | What it is |
|---|---|
| [index.html](index.html) | The map (3D, or flat on a phone and without WebGL): one self-contained file. Open it by double click. It works offline and asks for nothing from the network. Generated; never edit it. |
| [TREES.md](TREES.md) | The same content as text trees (generated). |
| `model.json` | The model both are drawn from (generated). |
| [DESIGN.md](DESIGN.md) | The map's own design rules. A new visual element goes here first. |
| [UI-CHECKLIST.md](UI-CHECKLIST.md) | The interface checklist each map story passes. |
| [walkthrough-2026-11-26.md](walkthrough-2026-11-26.md) | A dated reading copy of the walkthrough. |

## Open it

Open `docs/architecture-map/index.html` in any current Chrome, Firefox, Edge or Safari. A browser
that draws WebGL shows the 3D map. Without WebGL, if the 3D view fails, or on a window 760 px wide
or less (a phone), it shows the [flat map](#the-flat-map-and-phones) of the same model.

What you see: the three heights are what people see, the product flowing left to right, and storage;
the platform is the frame under the product; measurement and operations sit on a ring outside it.
Moving dots show which way each flow runs. Click a module (or choose it in the legend on the left):
it opens into its parts, and the panel on the right shows how a part decides as a flowchart
(diamond: a decision; pill: a start or an outcome; dashed box: a list of details).

**Manager** shows the logic, stores, jobs and flows in plain words. **Developer** adds files,
functions, routes and settings, each with the repository default and, where
[KT section 1](../TECHNICAL_DESIGN.md#1-reading-the-evidence) states one, the production value
with its source and date. The header says which commit the map was read from.

## Watch it work

Three things play step by step in a bar under the world, with Back, Next, Play or Pause, a speed
(1×, 2×, 4×) and Close (`Esc`):

- **The clock** (`5`): a ring of the day around the product, with a bead for every time a scheduled
  job runs: daily on the inner ring, weekly in the middle, monthly and yearly outside. At each time
  the job's parts light up and dots run along the flows it drives. The panel names the job, its
  trigger and the switches that gate it, and lists the whole day. The slider jumps to a time.
  What lights up is what a run can reach; a quiet day or a switch inside the job can stop earlier.
  Shared plumbing (the model client, config) is not lit, and only the flows the map draws can run:
  a job that sends alerts lights Delivery even where no flow leads there.
- **Trace a stock**: one stock's life, from Saturday's deep dive to the Sunday scorecard, with
  each step's path lit.
- **Tour**: eight stops through the product. A manager who opens the map without a link to a part
  starts here; `Esc` leaves it. Autoplay never starts by itself.

Their addresses can be shared: `index.html#p=clock&s=16`, `#p=trace&s=6`, `#p=tour&s=1`.

## The flat map and phones

One drawing of the same model: the planes as bands from top to bottom, each module at its column,
the outside parties beside them, the stores under them. It has the same legend, panel, search,
player and deep links as the 3D map, and nothing in it moves.

- Choose a card (or a module in the legend) to open it. What it touches stays bright, the rest
  fades, its flows brighten, and its parts are listed under the drawing.
- `1` to `4` change what stands out: flows, flows without storage, planes, or storage. `5`, Trace a
  stock and the Tour light each step on the drawing.
- `+` and `−`, or the buttons above the drawing, change its size; a wider drawing scrolls.
- In the code galaxy each card counts its module's files; a card holds the shared files.
- On a phone the player stands above the map, and opening something moves to its panel.

## The code galaxy

In the **Developer** view, **Code galaxy** (`G`) shows the code as it is: one dot for each Python
file under `core/`, `services/`, `src/backend/` and `scripts/`, and a line for each import between
two of them. A dot's size grows with the file's lines and its colour is its module's. Each module's
files gather in a ball that stands where the module stands in the world; files that belong to no one
module have a ball of their own. A file that many modules import sits on the side facing them, and
one imported by six or more other modules has a ring and its name.

- Choose a module in the legend (or **Shared files**) to light its files; the panel counts what they
  import from outside and what imports them, and lists them, largest first.
- Click a dot, a name or a listed file, or search a file by its name (`/`), for its panel: path,
  lines, the part it belongs to, what it imports and what imports it, each a link.
- The galaxy and the world share what is chosen: **Show in the world** opens the file's part, and
  in the developer view a part's panel links to its code. The world's panel lists each part's files
  as links into the galaxy.
- Views `1` to `4` and `R` frame the galaxy; `5` leaves it for the clock; `Esc` closes the panel,
  then the galaxy. Without WebGL the panels still list every file.

Imports are read from `import` statements. A file loaded by name at run time, and a script someone
runs, may show as imported by nothing. The galaxy holds the files and line counts of the page's last
rebuild (the header's `Code inspected`).

Addresses: `index.html#g` is the galaxy, `#g&m=M5` lights a module's files and
`#g&f=core/portfolio/advisor.py` opens a file.

## Keys

| Key | What it does |
|---|---|
| `1` `2` `3` `4` | Front, top, side and below views (see DESIGN.md for what each answers) |
| `5` | The clock |
| `G` | The code galaxy (developer view) |
| `R` | Reset the view |
| `/` | Search modules, parts, stores, jobs, settings, functions and files |
| `P` | Pause or resume motion (3D view; the flat map does not move) |
| `← → ↑ ↓` and `+ −` | Turn and zoom the 3D view, once it has the focus (Tab to it); on the flat map `+ −` change its size and the arrows scroll it |
| `Shift` + arrows | Move the 3D view sideways, once it has the focus |
| `Esc` | Close the dialog, then the clock, trace or tour, then the panel, then the galaxy |
| `?` | The list of keys |

A part has its own address, so a document or a chat can point into the map: `index.html#m=M5.2`
opens the advisor's flowchart; add `&v=dev` for the developer view.

## Keep it true

The model is generated from the code and from the curated files in
`tools/architecture_map/model/curated/`. After a code change run

```text
python tools/architecture_map/model/generate.py
```

and commit what it writes; the CI guard (`check.py`) fails otherwise. What the clock lights for
each job is `lights` and `flows` in `curated/jobs.yaml`; the trace and the tour are
`curated/trace.yaml`. The guard fails on a job without them and on a step that names something the
map lacks; whether a job really drives those flows is checked by reading its code.

In a tree, a line may start with `>` (follows the line above), `?` (a decision), `?!` (a decision
whose result ends the path) or `!` (an outcome): `tools/architecture_map/model/tree.py` describes
them. TREES.md shows the text without the marks.

## Rebuild the page

The page holds a copy of the model, taken when it was built. After a change to the model or to the
viewer (`tools/architecture_map/viewer/`):

```text
cd tools/architecture_map/viewer
npm ci          # pinned versions; install scripts are not run (.npmrc)
npm run build   # writes docs/architecture-map/index.html
```

A test fails when the committed page was not built from the committed viewer source, and when its
copy of the model's modules, logic, flows, stores, jobs, settings, production values, trace or
tour differs from `model.json`: rebuild after such a change. File lists, line counts, routes and
the commit shown in the header (`Code inspected`) are only as new as the last rebuild.

## Tests

`npm run test:frontend` at the repository root runs `tests/frontend/architecture_map.test.mjs`
(the built page in Chromium with software WebGL, opened from disk with the network off),
`architecture_map_galaxy.test.mjs` (the code galaxy, the same way),
`architecture_map_flat.test.mjs` (the flat map without WebGL and on a phone, every part's panel)
and `architecture_map_logic.test.mjs` (layout, flowchart rules, what each step and choice lights,
the clock ring, the galaxy's balls and dots, the flat map's places and states, colours and
contrast, the rebuild check). None needs the viewer's own packages.

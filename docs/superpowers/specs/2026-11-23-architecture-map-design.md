# Architecture map — a 3D world for the flow, a flat panel for the logic

Status: **adopted as the plan** on 2026-11-23 (the owner, about 00:10 IST: "take it like phases
that we do and complete all phases of this plan using our autopilot"). Nothing here is
implemented yet. Author: Claude + Revan. Date: 2026-11-23. Stories:
[MAP-001](../../planning/PI-2026-09/stories/MAP-001.md) to
[MAP-005](../../planning/PI-2026-09/stories/MAP-005.md).

## Why

On 22 Nov 2026 the owner asked to understand the core architecture "in ascii tree way": prose
documents do not show the flow. The walkthrough that followed (12 modules, their sub-modules, the
logic of each as branching trees, the daily clock, one stock's life) is kept as the map's seed:
[seed walkthrough](../../architecture-map/seed-walkthrough-2026-11-22.md). The owner then asked
for the same understanding as something "visually stunning and detailed", in 3D, that "will long
last for any developer or techno manager"; effort is not a constraint.

## What was weighed

| Need | 3D (Three.js) | 2D interactive HTML |
|---|---|---|
| First impression, showcase | best | good |
| Many relationships at once (flow, layers, storage, time) | best: each axis carries a meaning | limited to one plane |
| Looking from several directions | yes: each direction answers a question | no |
| Reading branching logic and exact order | weak: labels tilt, shrink and hide | best |
| Laptops, phones, screenshots | needs a GPU | everywhere |
| Lasting | both drift unless driven by the code | same |

Mermaid, D2, hand-drawn tools and hosted architecture tools were set aside by the owner.

**Decision: a hybrid.** A 3D world for where things are and how they connect, and a flat detail
panel for what the logic says. Pure 3D would look as good and lose the depth of detail asked for.

## The world

Every axis means something; nothing is placed at random.

```
                     ┌──────────── TOP PLANE: what people see ────────────┐
                    /  [M10 Screens]     [M10 Chat]     [M9 Brief · Alerts] /
                   └────────────────────────────────────────────────────────┘
                          ▲ reads              ▲ delivers
          ┌──────────── MIDDLE PLANE: the product, flowing left ─► right ──────────┐
         /  [M2 Data] ══► [M3 Research] ══► [M4 Learning] ══► [M5 Portfolio]       /
        /        ▲               ▲                                  ▲              /
       /   [M7 Events]     [M6 Discovery] ══════════════════════════╝   [M8 IPO]  /
      └──────────────────────────────────────────────────────────────────────────┘
               │ writes             │ writes                 │ writes
         ┌──────────── BOTTOM PLANE: storage (the data/ volume) ─────────┐
        /  predictions/    portfolio/<user>/    discovery/    SQLite ×5  /
       └──────────────────────────────────────────────────────────────┘

   Outer ring: M11 Measurement and M12 Operations, dotted beams to what they watch
   Base frame: M1 Platform, a clock ring carrying the scheduled jobs at their times
   ══► glowing tubes with moving particles = data flowing
```

Layout is computed from the model (a module's plane and its column in the flow), never from
hand-placed coordinates, so a new module or flow lands in a sensible place by itself.

### Camera presets

| Key | Camera | Question it answers |
|---|---|---|
| 1 | Front | How does a stock become a verdict, then a trade? |
| 2 | Top | What are the modules and their neighbours? |
| 3 | Side | What does a person see, what decides, what is stored? |
| 4 | Below | Which module writes which file? |
| 5 | Clock | What runs when? (the day player, MAP-003) |

`R` resets the view, `/` searches, `Esc` closes the panel, `?` shows the keys. Orbit is limited
so the world cannot be turned upside down; a click flies the camera to the thing clicked.

### Interaction

- **Click a module:** everything unrelated fades; the module unfolds into its sub-modules in
  place; the detail panel opens.
- **Hover a flow tube:** what travels on it ("verdict + gate status").
- **Deep links:** `#m=M5.2` opens that sub-module, so a document or a chat can point into the map.
- **Audience toggle:** *manager* (story, plain words, the guided tour by default) and *developer*
  (file paths, functions, config keys, stores read and written, the code galaxy).

### The detail panel (flat, always readable)

For each sub-module:
- its logic as a flowchart of connected boxes, laid out by ELK from the model's logic tree (the
  seed's trees), decisions as diamonds, outcomes as ends;
- files and functions, as repository paths;
- config keys, each with its repository default and, where production differs, the production
  value with its source and date (KT section 1 only);
- stores it reads and writes; jobs that run it; flows in and out.

Labels in the 3D world are HTML overlays that always face the camera; long text never renders in
3D.

### Later modes

- **Day player** (MAP-003): a clock slider 06:30 → 23:45 plus the weekly and monthly jobs; each
  job lights up at its time and particles run along the flows it drives.
- **Trace a stock** (MAP-003): the seed's finale path (dive, shelf, buy, daily reviews, exit,
  Sunday scorecard), step by step.
- **Guided tour** (MAP-003): about 8 scripted stops with one-line captions.
- **Code galaxy** (MAP-004): a force graph of the Python files and their imports, coloured by
  module, sized by lines; selecting a module in the world lights its files, and back.
- **2D fallback** (MAP-005): the same model as a flat map when WebGL is missing or the screen is
  small.

## Look and usability (added 2026-11-23; see "Decisions taken")

Five sessions build the map. Two files keep one look and one standard across them:

- **`docs/architecture-map/DESIGN.md`**, the map's own design rules: a colour per module and per
  plane, type, glow and bloom limits, panel and flowchart styles, motion, and contrast. It follows
  the DESIGN.md format collected in VoltAgent's awesome-design-md, but it is our own and copies no
  brand. MAP-002 writes it before drawing anything. A later card that adds a visual element adds
  it to DESIGN.md first.
- **`docs/architecture-map/UI-CHECKLIST.md`**, an interface checklist in our own words, taken from
  Vercel's Web Interface Guidelines (vercel-labs/web-interface-guidelines) at a recorded commit:
  keyboard, visible focus, labels, contrast, reduced motion, touch targets, and so on. It is read
  once and kept in the repository, never fetched at build or test time, so the map stays offline
  and the check stays repeatable. Each card passes it for what it adds, and its receipt lists each
  item as passed or not applicable. MAP-005 passes it over the whole map.

## The model: what keeps it true

```
architecture model
├── GENERATED from the code (always true)
│   ├── scheduled jobs: id, trigger, gate flag ..... from scheduler.py (AST)
│   ├── API routes: method, path, router ........... from services/api routers (AST)
│   ├── imports between Python files .............. from core/, services/, src/backend/, scripts/
│   ├── config switches and their defaults ........ from config.yaml (keys the curated part names)
│   └── file sizes in lines
├── CURATED (meaning, checked against the code when written)
│   ├── modules, sub-modules, flows (from, to, what travels)
│   ├── stores (path, writers, readers)
│   ├── logic trees per sub-module (seeded from the walkthrough)
│   ├── job → modules and flows it drives; route → module
│   ├── trace and tour scripts
│   └── production values {value, source: "KT section 1", as_of}
└── GUARD (CI): fails when the code and the model disagree
    ├── the generated part differs from a fresh run ─► "run the generator"
    ├── a curated file path, function or config key does not exist
    ├── a job or route belongs to no module
    ├── a flow, store or trace step names something the model lacks
    └── a production value cites no source
Every view shows "code inspected: <commit>".
```

`TREES.md` is generated from the model (the walkthrough's trees, kept current), and replaces the
seed once the model holds its content.

## Technology

| Part | Choice |
|---|---|
| Generators and guard | `tools/architecture_map/model/`: Python 3.11, standard library + PyYAML (already required); hermetic unit tests; the guard runs in CI's guards job without Node |
| Viewer | `tools/architecture_map/viewer/`: its own `package.json` and lockfile; Vite, React 18, three, @react-three/fiber, @react-three/drei, @react-three/postprocessing (bloom), elkjs, a single-file plugin |
| Output | `docs/architecture-map/index.html`, one self-contained file committed to the repository: opens by double click, offline, no server, no network request; `docs/architecture-map/model.json`; `docs/architecture-map/TREES.md` |
| Viewer tests | a Playwright smoke test of the built file (loads from `file://`, no console errors, canvas present, a click opens the panel), Chromium with software WebGL |
| Screenshots | at device scale factor 2 for the owner, kept under ignored `analysis_data/architecture_map/` |

npm was reachable on 23 Nov (three 0.187.0, @react-three/fiber 9.8.2, elkjs 0.12.1); MAP-002 pins
what it installs.

**Nothing ships or runs in the app.** The Dockerfile copies neither `tools/` nor `docs/`; nothing
in the app imports them; no route, job, store or setting changes. Commits that touch only these
folders still redeploy the app when pushed, so they wait for the push windows like any other.

## Safety and privacy

The model holds code structure and configuration switch values only: no secrets, tokens,
hostnames, Railway identifiers, user data or production logs. It is safe to show outside, for the
showcase the owner has in mind. Production values are cited to KT section 1, never read from
production.

## Phases

| Story | Outcome |
|---|---|
| [MAP-001](../../planning/PI-2026-09/stories/MAP-001.md) | The model, its generators and the guard; the seed's content in the model; `TREES.md` generated |
| [MAP-002](../../planning/PI-2026-09/stories/MAP-002.md) | The 3D world, camera presets, click-to-focus and the detail panel, with the money path's logic (M3, M4.2, M5.2, M5.3, M6) |
| [MAP-003](../../planning/PI-2026-09/stories/MAP-003.md) | The day player, "trace a stock" and the guided tour |
| [MAP-004](../../planning/PI-2026-09/stories/MAP-004.md) | The code galaxy, linked to the world |
| [MAP-005](../../planning/PI-2026-09/stories/MAP-005.md) | Every module's logic, the 2D fallback, polish, and the map as a living document |

Each is a light story: implemented, tested and accepted in its own conversation on the full suite
and the guards. The owner sees screenshots at the end of each.

## Decisions taken on 2026-11-23

- **Hybrid over pure 3D**, for readable logic (the owner's direction: 3D, depth of detail).
- **In the repository from MAP-001.** The 22 Nov suggestion was to build outside it first. The
  autopilot works from the repository in fresh sessions, and work outside git would have no
  history, no backup and no way to continue on another device.
- **One self-contained HTML file** over a hosted page: it lasts without a server.
- **Order in the queue:** after FIX-033 (P0) and PR-047 (the buy rule decided on 21 Nov), which
  protect money, and PR-017's pending fresh review; ahead of PR-007 and the rest. PR-015's switch
  keeps its push window. The owner may move the map first.
- **DESIGN.md and UI-CHECKLIST.md**, added by Claude in a manual session at about 08:15 IST under
  CLAUDE.md section 2 (story content is delegated). The owner had shared two videos of design
  tools; the session found two of them fit the map, and the owner asked whether they had been
  added to the stories. Two others were set aside: image-to-code, because the map is drawn from the
  model and has no mockups, and a second Playwright, because one is already planned and
  installed. The owner may drop either file.

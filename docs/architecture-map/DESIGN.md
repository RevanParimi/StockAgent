# Architecture map — design rules

The one look of the map (`docs/architecture-map/index.html`). Five stories build it (MAP-002 to
MAP-005); this file keeps them consistent. A story that adds a visual element adds it here first.
The format follows the DESIGN.md sections collected in VoltAgent's awesome-design-md; the content
is our own and copies no brand. The colour values below are the ones the code uses
(`tools/architecture_map/viewer/src/theme.js`); a test fails when the two disagree.

## 1. Theme and atmosphere

A quiet night-sky model of a machine: dark, spacious, calm. Light is information: what glows is
data that moves or the thing you are looking at. Everything else stays dim so the flow reads from
across a room. Dense detail lives in the flat panel, never in 3D.

- Two audiences: **manager** (plain words) and **developer** (paths, functions, settings).
- Dark only. There is no light theme.

## 2. Colour and roles

### Surfaces and ink

| Token | Value | Role |
|---|---|---|
| bg | `#0b1020` | page and scene background |
| panel | `#121a2e` | side panel, top bar, legend |
| raised | `#1b2540` | dialogs, hovered rows, tooltips |
| node | `#18213a` | flowchart box fill |
| line | `#33415f` | borders and dividers (decorative) |
| edge | `#8f9bba` | flowchart arrows and outlines that carry meaning |
| ink | `#e9eefb` | primary text |
| ink2 | `#b4bfd9` | secondary text |
| muted | `#8f9bba` | small labels, stamps |
| link | `#8ecbff` | links and deep-link targets |
| focus | `#ffd166` | keyboard focus ring, selection outline |
| yes | `#7ee2a8` | the "yes" label on a decision edge (always with the word) |

### Planes (what kind of thing)

| Token | Value | Plane |
|---|---|---|
| planeTop | `#7d6cf0` | what people see |
| planeMiddle | `#3a7bd5` | the product, flowing left to right |
| planeBase | `#6b7690` | the base frame the product rests on |
| planeStores | `#b4832f` | storage |
| planeRing | `#8a99b3` | the watchers' ring |

### Modules

Twelve colours, checked with the data-visualisation validator on the map's background: all pairs
that meet on screen (joined by a flow, in neighbouring columns of one plane, or next to each other
in the legend) differ by at least 17.9 for full colour vision and 10.1 under colour-blindness
simulation (floors: 15 and 8); every colour is at least 3:1 against the background and the panel.
Twelve colours cannot all differ from each other, so **colour never carries identity alone**:
every module also shows its ID and short name.

| Token | Value | Module |
|---|---|---|
| M1 | `#53b029` | Platform |
| M2 | `#5e7dfa` | Data |
| M3 | `#1ab2a6` | Research |
| M4 | `#236fd8` | Learning |
| M5 | `#c43d73` | Portfolio |
| M6 | `#667900` | Discovery |
| M7 | `#cc8c45` | Events |
| M8 | `#a985e5` | IPO |
| M9 | `#96a022` | Delivery |
| M10 | `#c66167` | Interface |
| M11 | `#935ede` | Measurement |
| M12 | `#ad620e` | Operations |

A module the model gains later takes `planeMiddle` until it has a token here; add one (and re-run
the validator) in the same change. In the code galaxy a file that belongs to no one module
(“shared”) takes `edge`, and every ball of files is labelled, so colour still carries nothing
alone.

## 3. Type

- Text: the system's own sans (`ui-sans-serif, system-ui, "Segoe UI", Roboto, sans-serif`). Code
  (paths, function names, setting keys): `ui-monospace, SFMono-Regular, Menlo, Consolas,
  monospace`. No web fonts: the page works offline.
- Sizes: 12 px stamps and edge labels, 13 px body of panel and flowchart, 14 px controls and
  legend, 16 px section headings, 20 px panel title. Line height 1.45.
- Headings in sentence case. Numbers in tables use tabular figures. Use `…`, not three dots.
- Code names are marked `translate="no"` so a browser translator leaves them alone.
- No long text in 3D: labels hold an ID and a short name (stores: the store's name).

## 4. Components

| Component | Look | States |
|---|---|---|
| Module block (3D) | rounded box in the module colour, edges a third of the way to white so they glow | rest: body glow 0.45; hover: 0.75; selected: 1 and a `focus` outline; unrelated to the selection: opacity 0.12 |
| Sub-module block (3D) | small box in the module colour above its module, two abreast, only while the module is selected | the selected sub-module is outlined in `focus` |
| Store block (3D) | flat `planeStores` slab | rest 0.5 opacity (Top view 0.14, Below view 0.7); touched by the selection: 0.95; unrelated: 0.12 |
| Flow tube (3D) | thin tube in the source module's colour, a cone arrowhead near the target, moving dots along it | hover or related to selection: brighter and thicker; unrelated: 0.08; flows to or from the ring: dashed |
| Storage pipe (3D) | thinner line from writer to store in the writer's colour | rest 0.32 (Top view 0.06, Below view 0.85); related to the selection: 0.85; unrelated: 0.05 |
| Planes (3D) | large translucent slabs with a name label | never highlighted |
| Flowchart box | one height (56% of the window, 240 to 640 px, resizable by its corner), the same before and after drawing; a wider chart scrolls | opens centred on its start |
| Label (HTML over 3D) | `panel` pill, 12-14 px, a 4 px bar in the module colour, ID then short name | hover: `raised`; selected: `focus` outline; unrelated: 0.25 opacity |
| Tooltip (flow) | `raised`, "from → to" then what travels | appears on hover, never the only place the fact is shown (the panel lists flows) |
| Top bar | `panel`, title and stamp left, view buttons, search, audience, motion, help right | a pressed toggle is filled `raised` with a `focus` underline and `aria-pressed` |
| Legend | the modules as links (`#m=<id>`): colour swatch, ID, short name | the selected one is marked by outline and `aria-current` |
| Panel | `panel`, 16 px padding, sections with 16 px headings; scrolls on its own | closed: the world takes the width |
| Flowchart start | pill, 2 px border in the module colour | |
| Flowchart step | rounded rectangle, 6 px radius, `node` fill, 1 px `edge` border | |
| Flowchart decision | elongated diamond (pointed left and right ends), `node` fill, 1.5 px `edge` border: a true diamond would be unreadable with a sentence inside | |
| Flowchart end | pill, 1.5 px `edge` border, filled `raised` | |
| Flowchart list | rounded rectangle with a dashed `edge` border, one bulleted line each: two or more details of one box | |
| Flowchart edges | "then": solid 1.5 px arrow; "part of": 1 px, no emphasis; edge labels ("yes", "no" or the branch's words) in 12 px on the line | |
| Dialog (search, help) | `raised`, centred, dimmed backdrop; native dialog, focus stays inside, `Esc` closes | |
| Player (the clock, trace a stock, guided tour) | a `panel` bar under the world, never over it: mode name and “n of N” (tabular), the caption, then Back, Play or Pause, Next (on the last step of a trace or tour: Finish), speed (1×, 2×, 4×) and Close ✕ | the playing button reads Pause and is pressed; Back on the first step and Next on the clock's last time are marked disabled (`aria-disabled`, so the focus stays on them) |
| Time slider (clock) | native range input, one notch for each time a job runs, labelled with the time, the day it runs on and the job's name; the first and last time at its ends | focus ring on the input; arrows, Home, End and Page keys move it |
| Lit (3D) | what the step names: module blocks at body glow 1 with their lit edges, stores and outside parties full, flows bright with dots, pipes between a lit module and a lit store | everything else: opacity 0.12 (flows 0.08); a step that names nothing dims nothing |
| Lit label | `raised`, `focus` outline; a module whose lit parts are named reads “M4 Learning · M4.2”, more than two “M5 Portfolio · 4 parts” | others 0.25 opacity; on the clock view only lit things are named |
| Clock ring (3D) | three flat circles around the product, in the base frame's plane: daily (inner), weekly (middle), monthly and yearly (outer); 00:00 at the back, running clockwise seen from above; a tick each hour, figures at 00, 06, 12 and 18; a one-line key in the view's lower left names the rings | `planeBase` lines; drawn only on the clock view |
| Job marker (3D) | a bead on its ring at its time, in its module's colour; a job that runs three times has three beads; beads at one time on one ring stand one outside the other | the current time: larger, with a `focus` ring and a radial `focus` hand across the three rings; one label, the job's time and name |
| Job panel (clock) | the panel names the job, its trigger, its gate switches (with the repository default and, where KT section 1 states it, the production value), what it does, what it lights and what flows; below, every time of the day as a list of buttons, the current one marked `aria-current` | |

### The code galaxy (MAP-004)

| Component | Look | States |
|---|---|---|
| Code galaxy button | a toggle in the top bar, developer view only (`aria-pressed`, key `G`) | pressed while the galaxy shows; the manager view has no galaxy, so changing to it returns to the world |
| File dot (3D) | one dot for each Python file in the model, in its module's colour (shared files `edge`); its area grows with its lines, with a smallest size so an empty file can still be pointed at | rest: the colour; lit: a step towards white, so it glows; unrelated: mixed towards `bg` (the look of opacity 0.12) |
| Chosen file ring (3D) | a `focus` ring facing the viewer around the chosen file's dot, drawn over the dots so it is found even behind others | one at a time |
| Bridge ring (3D) | a thin `ink2` ring facing the viewer around a file that files of six or more other modules import | gone when its file is unrelated |
| Import lines (3D) | one thin line for each import, shading from the importer's colour to the imported file's, added light so lines never hide a dot | rest: faint, fainter across modules; a lit module: lines inside it bright, lines to or from another module fainter (under half), others all but gone; a chosen file: all but gone, its own lines drawn as below |
| Chosen file's lines (3D) | solid `ink` lines to the files it imports, dashed `link` lines from the files that import it | the view's key says which is which, and the panel lists both |
| Galaxy labels | a label above each ball: the module's ID and short name, or “Shared files”; file names (with the folder for an `__init__.py`) for the bridge files, up to six of the largest files of a lit module, or, with a file chosen, that file and up to six of its largest neighbours only | as Label; a file label is smaller, in a `code` face, and opens its file |
| Galaxy key | one line in the view's lower left: what a dot, its size, a ring, a line and a colour mean; with a chosen file, what solid and dashed mean | |
| File tooltip | `raised`: the path, then its lines and module | on hover only; the panel holds the same facts |
| Code panel | for a lit module, part or the shared files: how many files and lines, what they import from other modules and what other modules import from them, then the files, largest first, as links | a part without a Python file says so |
| File panel | the file's name and path, its lines and owner, “Imports” and “Imported by” as lists of links, “Show in the world” | an empty list says so in words |

Shape carries meaning beside colour: pill = start or end, diamond = decision, rectangle = step,
dashed rectangle = a list of details.

## 5. Layout

- Screen: top bar across; legend on the left; the world fills the middle; the panel opens on the
  right (about 40% of the width, wider with "Wider panel"). In a mode the player takes a row under
  the world; the clock also opens its job panel on the right, the trace and the tour do not.
- World: every position is computed from the model. Height = plane (top: what people see; middle:
  the product; just under it: the base frame; far below: storage). Left to right = the module's
  column in the flow. Modules sharing a plane and column step apart front to back. The top plane
  stands behind the product plane, so it does not cover the flow seen from above. Ring modules sit
  on an ellipse around the product plane. A store sits under the columns of the modules that write
  it. No hand-placed coordinates.
- A selected module is framed from the front, a little above (40° lens), with its parts.
- Camera presets, each framing the whole world for the window:
  - 1 Front (40° lens, raised): how a stock becomes a verdict, then a trade.
  - 2 Top (40°, from above): the modules and their neighbours; storage and pipes fade.
  - 3 Side (13°, almost level, from far away so the heights stay apart): the planes are labelled
    with who stands on them; module labels are hidden.
  - 4 Below (40°, from below and in front, so a module sits above the stores its pipes reach):
    stores are named, flows and the top plane fade.
  - 5 Clock (40°, high and in front): the product inside the clock ring; plane, store and unlit
    names are hidden.
- A tour stop chooses a view (front, top, side, below, clock) or flies to one module (“focus”),
  which then unfolds into its parts; a trace step is shown from the front.
- Code galaxy (MAP-004): each module's files gather in one ball. A ball stands where its module
  stands in the world (the same left to right order and height, drawn further apart) and is then
  pushed apart from the others until none touches; the shared files have a ball of their own under
  the base frame. Inside a ball, files that import each other draw together, and a file that other
  modules import is pulled to the side that faces them, so it reads as a bridge. Every position
  comes from a seeded calculation: the same on every load. The legend lists “Shared files” too.
  Keys `1` to `4` and `R` frame the galaxy from the same four sides as the world (its front view
  looks down more steeply, so that balls behind one another come apart); `5` leaves it for the
  clock. Choosing a module or a file moves no camera. `Esc` closes the panel, then the galaxy.

## 6. Glow and depth

- Bloom is the only post-processing: intensity at most 0.7, threshold at least 0.55, so only
  emissive edges, dots and the selection glow.
- Text is never drawn in the 3D scene, so bloom never blurs it.
- Panels have one flat border and a soft shadow; no gradients on text.

## 7. Motion

- Camera flights: 700 ms, ease in and out, stop as soon as the user drags or presses a preset.
- The code galaxy has no motion of its own; only a change of view flies the camera.
- Autoplay: one step every 6 s (trace, tour) or 2.4 s (clock) at 1×, divided by the speed. It
  never starts by itself (the guided tour opens at its first stop and waits), stops at the last
  step, and is stopped by Back, Next, the slider, Pause or **Pause motion**.
- Dots along flows: steady speed, never faster than one flow length in four seconds.
- Anything that moves can be stopped: the **Pause motion** button (key `P`), and with the system's
  "reduce motion" setting the dots stop and the camera jumps instead of flying.
- Hover and focus changes are instant or at most 120 ms, on `opacity`, `background-color` and
  `border-color` only; never `transition: all`.

## 8. Contrast and access

- Text is at least 4.5:1 on its surface (`ink`, `ink2`, `muted`, `link`, `yes` pass on `bg`,
  `panel`, `raised` and `node`). Text is never set in a module colour or on a module-colour fill.
- Meaningful lines and borders are at least 3:1 (`edge`, `focus`, module colours).
- Keyboard focus is a 2 px `focus` outline with 2 px offset (`:focus-visible`).
- Each step's words are announced politely. The clock ring has its text equivalent in the job
  panel's list; the slider's value is read as time, day and job.
- Every action in the 3D world also exists as a button or key: modules from the legend, views from
  the top bar, turning and zooming with the arrow keys and `+`/`−`, moving with Shift and the
  arrows, once the view has the focus (it shows the focus ring inside its edge), flows listed in
  the panel.
- In the code galaxy every file is reached without pointing at a dot: a module in the legend opens
  its code panel, which lists its files; search finds a file by its name. The panels are the
  galaxy's text equivalent, with or without a 3D view.

## 9. Do and don't

- Do let the model decide what is drawn; do keep one meaning per axis.
- Don't hand-place a block, add a decorative animation, or put a paragraph in 3D.
- Don't use colour alone, a light surface, or a downloaded font, image or script.

## 10. Phones and small screens

Not designed yet: MAP-005 adds the phone layout and the flat 2D fallback. Until then a narrow
window stacks the panel under the world.

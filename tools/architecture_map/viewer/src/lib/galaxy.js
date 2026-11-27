// The code galaxy (MAP-004): the Python files and their imports, where each file stands, what
// a choice lights and what the panels say about it. Pure functions over the model and the
// world, so tests run them without a browser.

import { SHARED, SURFACE, moduleColour, moduleOf } from '../theme.js';
import { findPart } from './select.js';
import { boundsOf, layoutWorld } from './world.js';

// A file that files of this many other modules import is marked as a bridge.
export const BRIDGE_MODULES = 6;
// A dot's area grows with the file's lines; an empty file keeps a dot to point at.
export const DOT = { smallest: 0.3, perRootLine: 0.04 };
export const GAP = 2.5; // the least room between two balls of files
const SEED = 20261123;
// How much further apart than in the world the modules stand, so their balls have room.
const SPREAD = [1.4, 2.4, 2.2];
// The galaxy's front view looks down more than the world's, so that balls standing behind
// one another come apart.
export const FRONT = [0, 0.8, 1];
// Room left round the galaxy, so that the key in the lower left covers no ball.
export const MARGIN = 1.15;
// A ball's volume for each unit of dot volume in it: room to see the single files.
const ROOM = 34;
const PART_LABELS = 6; // file names shown beside a lit module or a chosen file

export const clusterOf = (owner) => (owner === SHARED ? SHARED : moduleOf(owner));
export const clusterColour = (cluster) => (cluster === SHARED ? SURFACE.edge
  : moduleColour(cluster));
export const dotRadius = (lines) => Math.max(DOT.smallest, DOT.perRootLine * Math.sqrt(lines));

const byText = (a, b) => (a < b ? -1 : a > b ? 1 : 0);
// M1, M2 … M12 in number order, the shared files last.
const rank = (cluster) => (cluster === SHARED ? Infinity : Number(cluster.slice(1)));
const byCluster = (a, b) => rank(a) - rank(b) || byText(a, b);
const bySize = (a, b) => b.lines - a.lines || byText(a.path, b.path);

/** A file's name for a label: `advisor.py`; a package's own file carries its folder. */
export function fileLabel(path) {
  const parts = path.split('/');
  const name = parts.at(-1);
  return name === '__init__.py' && parts.length > 1 ? `${parts.at(-2)}/${name}` : name;
}

/** A module's or the shared files' name. */
export function clusterName(model, cluster) {
  if (cluster === SHARED) return 'Shared files';
  const module = model.modules.find((m) => m.id === cluster);
  return module ? `${module.id} ${module.short}` : cluster;
}

/** A part's or a module's name, or the shared files'. */
export function ownerName(model, owner) {
  const part = findPart(model, owner);
  if (!part) return clusterName(model, owner);
  return part.sub ? `${part.sub.id} ${part.sub.name}` : clusterName(model, owner);
}

/** The files and their imports, each file knowing who imports it. */
export function codeGraph(model) {
  const files = [...model.files].sort((a, b) => byText(a.path, b.path)).map((f) => ({
    path: f.path, lines: f.lines, owner: f.owner, cluster: clusterOf(f.owner), imports: [],
    importedBy: [],
  }));
  const byPath = new Map(files.map((f) => [f.path, f]));
  for (const record of model.files) {
    const from = byPath.get(record.path);
    for (const to of record.imports) {
      const target = byPath.get(to);
      if (!target || target === from) continue;
      from.imports.push(to);
      target.importedBy.push(from.path);
    }
  }
  for (const file of files) {
    file.imports.sort(byText);
    file.importedBy.sort(byText);
  }
  const edges = files.flatMap((f) => f.imports.map((to) => ({ from: f.path, to })));
  return { files, byPath, edges };
}

/** The other modules with a file that imports this one. The shared files are no module. */
export function importingModules(graph, path) {
  const file = graph.byPath.get(path);
  const found = new Set(file.importedBy.map((from) => graph.byPath.get(from).cluster));
  found.delete(file.cluster);
  found.delete(SHARED);
  return [...found].sort(byCluster);
}

export const isBridge = (graph, path) => importingModules(graph, path).length >= BRIDGE_MODULES;

/** Whether a file's owner lies in a module, a part or the shared files. */
function owns(owner, id) {
  if (id === SHARED) return owner === SHARED;
  return id.includes('.') ? owner === id : clusterOf(owner) === id;
}

export const filesOf = (graph, id) => graph.files.filter((f) => owns(f.owner, id));

/** What the map selects when a file is chosen: its part, its module or the shared files. */
export const pickOf = (graph, path) => graph.byPath.get(path)?.owner ?? null;

// -- what a choice lights ---------------------------------------------------------------

/** A chosen file lights itself and its neighbours; a module, a part or the shared files
 *  light their files. Null, so everything rests, when nothing is chosen, and also when
 *  the choice has no Python file: a choice that names nothing dims nothing. */
export function galaxyLights(graph, { selected, file }) {
  const chosen = file ? graph.byPath.get(file) : null;
  if (chosen) {
    return { file: chosen.path,
      files: new Set([chosen.path, ...chosen.imports, ...chosen.importedBy]) };
  }
  if (!selected) return null;
  const files = filesOf(graph, selected);
  return files.length ? { file: null, files: new Set(files.map((f) => f.path)) } : null;
}

export function dotState(lights, path) {
  if (!lights) return 'rest';
  if (lights.file === path) return 'chosen';
  return lights.files.has(path) ? 'lit' : 'faded';
}

/** `near` and `far` at rest (inside a module, or between two); `own` for a chosen file's
 *  lines; `inside` and `bridge` for a lit module's; else `faded`. */
export function edgeState(graph, lights, edge) {
  if (!lights) {
    return graph.byPath.get(edge.from).cluster === graph.byPath.get(edge.to).cluster
      ? 'near' : 'far';
  }
  if (lights.file) {
    return edge.from === lights.file || edge.to === lights.file ? 'own' : 'faded';
  }
  const ends = Number(lights.files.has(edge.from)) + Number(lights.files.has(edge.to));
  return ends === 2 ? 'inside' : ends === 1 ? 'bridge' : 'faded';
}

/** The code panel's facts: the files, largest first, and what crosses their border. */
export function codeSummary(graph, id) {
  const files = filesOf(graph, id).sort(bySize);
  const mine = new Set(files.map((f) => f.path));
  const tally = (side) => {
    const count = new Map();
    for (const file of files) {
      for (const other of file[side]) {
        if (mine.has(other)) continue;
        const cluster = graph.byPath.get(other).cluster;
        count.set(cluster, (count.get(cluster) ?? 0) + 1);
      }
    }
    return [...count].sort((a, b) => b[1] - a[1] || byCluster(a[0], b[0]));
  };
  return { files, lines: files.reduce((sum, f) => sum + f.lines, 0),
    imports: tally('imports'), importedBy: tally('importedBy') };
}

// -- where each file stands -------------------------------------------------------------

/** A seeded source of numbers from 0 to 1 (mulberry32): no run differs from another. */
function seeded(seed) {
  let state = seed >>> 0;
  return () => {
    state = (state + 0x6d2b79f5) >>> 0;
    let t = state;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

const numberOf = (text) => [...text].reduce(
  (n, c) => (Math.imul(n, 31) + c.charCodeAt(0)) >>> 0, 7);

const add = (a, b) => [a[0] + b[0], a[1] + b[1], a[2] + b[2]];
const sub = (a, b) => [a[0] - b[0], a[1] - b[1], a[2] - b[2]];
const times = (a, s) => [a[0] * s, a[1] * s, a[2] * s];
const length = (a) => Math.hypot(a[0], a[1], a[2]);
// Two points in one place part along x: any fixed direction keeps runs alike.
const away = (a) => { const n = length(a); return n > 1e-6 ? times(a, 1 / n) : [1, 0, 0]; };

/** A ball for each module with files, and one for the shared files, none touching. Each
 *  stands where its module stands in the world, drawn further apart. */
function placeBalls(graph, world) {
  const placed = world.modules.map((m) => ({
    id: m.id, anchor: m.pos.map((v, i) => v * SPREAD[i]),
  }));
  // the shared files lie under the base frame, in front of it
  const base = world.modules.filter((m) => m.plane === 'base');
  const middle = (axis) => (base.length
    ? base.reduce((sum, m) => sum + m.pos[axis], 0) / base.length : 0);
  placed.push({ id: SHARED,
    anchor: [middle(0) * SPREAD[0], (middle(1) - 5) * SPREAD[1], (middle(2) + 7) * SPREAD[2]] });
  const balls = placed.map((ball) => {
    const files = graph.files.filter((f) => f.cluster === ball.id);
    const volume = files.reduce((sum, f) => sum + dotRadius(f.lines) ** 3, 0);
    const largest = Math.max(0, ...files.map((f) => dotRadius(f.lines)));
    return { ...ball, count: files.length, centre: [...ball.anchor],
      radius: Math.max(2.5, Math.cbrt(volume * ROOM), largest * 2) };
  }).filter((ball) => ball.count);
  for (let pass = 0; pass < 2000; pass += 1) {
    // a pull back to its own place first, then only pushing apart until none touches
    const pull = pass < 300 ? 0.02 : 0;
    for (const ball of balls) {
      ball.centre = add(ball.centre, times(sub(ball.anchor, ball.centre), pull));
    }
    let touching = false;
    for (let i = 0; i < balls.length; i += 1) {
      for (let j = i + 1; j < balls.length; j += 1) {
        const [a, b] = [balls[i], balls[j]];
        const between = sub(b.centre, a.centre);
        const wanted = a.radius + b.radius + GAP;
        const gap = length(between);
        if (gap >= wanted) continue;
        // a hair more than needed, so the pushing ends
        const step = times(away(between), (wanted - gap) / 2 + 0.01);
        a.centre = sub(a.centre, step);
        b.centre = add(b.centre, step);
        touching = true;
      }
    }
    if (!pull && !touching) break;
  }
  return balls;
}

/** Where a file is drawn to inside its ball: the side facing the modules that use it
 *  (and, more weakly, those it uses). Null for a file that crosses no border. */
function bridgePull(graph, file, balls) {
  const own = balls.get(file.cluster);
  let towards = [0, 0, 0];
  let weight = 0;
  for (const [others, much] of [[file.importedBy, 1], [file.imports, 0.25]]) {
    for (const path of others) {
      const cluster = graph.byPath.get(path).cluster;
      if (cluster === file.cluster) continue;
      towards = add(towards, times(away(sub(balls.get(cluster).centre, own.centre)), much));
      weight += much;
    }
  }
  if (!weight || length(towards) < 1e-6) return null;
  const reach = (own.radius - dotRadius(file.lines)) * Math.min(1, 0.4 + weight / 5);
  return { target: add(own.centre, times(away(towards), reach)), strength: Math.min(1, weight / 4) };
}

/** The files of one ball: drawn together where they import each other, pushed apart,
 *  bridges drawn to the side, and never outside the ball. */
function placeDots(graph, ball, balls) {
  const random = seeded(SEED ^ numberOf(ball.id));
  const dots = graph.files.filter((f) => f.cluster === ball.id).map((file) => {
    let at;
    do at = [random() * 2 - 1, random() * 2 - 1, random() * 2 - 1];
    while (length(at) > 1);
    return { file, radius: dotRadius(file.lines), pos: add(ball.centre, times(at, ball.radius * 0.7)),
      pull: bridgePull(graph, file, balls) };
  });
  const byPath = new Map(dots.map((d) => [d.file.path, d]));
  const links = dots.flatMap((d) => d.file.imports.filter((to) => byPath.has(to))
    .map((to) => [d, byPath.get(to)]));
  const keepIn = (dot) => {
    const out = sub(dot.pos, ball.centre);
    const room = ball.radius - dot.radius;
    if (length(out) > room) dot.pos = add(ball.centre, times(away(out), room));
  };
  /** Push apart every pair closer than `spacing` allows; true when any pair was. */
  const part = (spacing, share) => {
    let close = false;
    for (let i = 0; i < dots.length; i += 1) {
      for (let j = i + 1; j < dots.length; j += 1) {
        const [a, b] = [dots[i], dots[j]];
        const between = sub(b.pos, a.pos);
        const wanted = spacing(a, b);
        const gap = length(between);
        if (gap >= wanted) continue;
        const step = times(away(between), (wanted - gap) * share);
        a.pos = sub(a.pos, step);
        b.pos = add(b.pos, step);
        close = true;
      }
    }
    return close;
  };
  for (let pass = 0; pass < 200; pass += 1) {
    const heat = 1 - (pass / 200) * 0.8;
    part((a, b) => (a.radius + b.radius) * 1.6 + 1.2, 0.12 * heat);
    for (const [a, b] of links) {
      const between = sub(b.pos, a.pos);
      const stretch = length(between) - (a.radius + b.radius + 1);
      const step = times(away(between), stretch * 0.012 * heat);
      a.pos = add(a.pos, step);
      b.pos = sub(b.pos, step);
    }
    for (const dot of dots) {
      dot.pos = add(dot.pos, times(sub(ball.centre, dot.pos), 0.004 * heat));
      if (dot.pull) {
        dot.pos = add(dot.pos, times(sub(dot.pull.target, dot.pos), 0.08 * dot.pull.strength));
      }
      keepIn(dot);
    }
  }
  for (let pass = 0; pass < 300; pass += 1) {
    const close = part((a, b) => a.radius + b.radius + 0.12, 0.51);
    dots.forEach(keepIn);
    if (!close) break;
  }
  return dots.map((d) => ({ path: d.file.path, cluster: ball.id, radius: d.radius, pos: d.pos }));
}

/** The whole galaxy. `nodes` are in the graph's file order, one for each file. */
export function layoutGalaxy(model, world = layoutWorld(model)) {
  const graph = codeGraph(model);
  const balls = placeBalls(graph, world);
  const byId = new Map(balls.map((b) => [b.id, b]));
  const placed = new Map(balls.flatMap((ball) => placeDots(graph, ball, byId))
    .map((node) => [node.path, node]));
  const nodes = graph.files.map((f) => placed.get(f.path));
  // the views frame every dot, not an empty box around them
  const points = nodes.flatMap((n) => [-1, 1].flatMap((x) => [-1, 1].flatMap((y) => [-1, 1].map(
    (z) => [n.pos[0] + x * n.radius, n.pos[1] + y * n.radius, n.pos[2] + z * n.radius]))));
  const bounds = { ...boundsOf(points), points };
  return {
    graph, bounds, nodes, byPath: placed,
    balls: balls.map(({ id, centre, radius, count }) => ({
      id, centre, radius, count,
      // the height of the ball's highest dot, where its name goes
      top: Math.max(...nodes.filter((n) => n.cluster === id).map((n) => n.pos[1] + n.radius)),
    })),
    bridges: graph.files.filter((f) => isBridge(graph, f.path)).map((f) => f.path),
  };
}

// -- pointing and names -----------------------------------------------------------------

/** The dot under a point of the screen. `dots` are as seen: `{path, x, y, radius, depth}`
 *  in pixels. A dot whose disc holds the point wins, the nearest to the viewer first;
 *  else the closest dot within `reach` pixels, so a small dot is a 24 px target. */
export function dotAt(dots, x, y, reach = 12) {
  let over = null;
  let near = null;
  for (const dot of dots) {
    const gap = Math.hypot(dot.x - x, dot.y - y);
    if (gap <= dot.radius) {
      if (!over || dot.depth < over.depth) over = dot;
    } else if (gap <= reach && (!near || gap < near.gap)) near = { dot, gap };
  }
  return over ?? near?.dot ?? null;
}

/** The names in the galaxy: one over each ball, and the files worth naming. */
export function galaxyLabels(model, galaxy, { selected, file }) {
  const { graph } = galaxy;
  const lights = galaxyLights(graph, { selected, file });
  const mine = file ? graph.byPath.get(file)?.cluster : selected && clusterOf(selected);
  const touched = new Set(lights ? [...lights.files].map((p) => graph.byPath.get(p).cluster) : []);
  const items = galaxy.balls.map((ball) => {
    const state = !lights ? 'rest' : ball.id === mine ? 'selected'
      : file && touched.has(ball.id) ? 'rest' : 'faded';
    const module = model.modules.find((m) => m.id === ball.id);
    return { key: `ball-${ball.id}`, kind: 'module', id: module?.id ?? null,
      text: module ? module.short : 'Shared files', select: ball.id,
      colour: clusterColour(ball.id), state, priority: state === 'selected' ? 0 : 2, hidden: false,
      pos: [ball.centre[0], ball.top + 0.6, ball.centre[2]] };
  });
  const named = new Map();
  const name = (path, state, priority) => {
    if (!named.has(path)) named.set(path, { state, priority });
  };
  if (lights?.file) name(lights.file, 'selected', -1);
  if (lights) {
    [...lights.files].filter((p) => p !== lights.file).map((p) => graph.byPath.get(p))
      .sort(bySize).slice(0, PART_LABELS).forEach((f) => name(f.path, 'rest', 3));
  }
  // a chosen file's picture holds enough names without the bridges'
  for (const path of lights?.file ? [] : galaxy.bridges) {
    if (!lights || lights.files.has(path)) name(path, 'rest', 4);
  }
  for (const [path, { state, priority }] of named) {
    const node = galaxy.byPath.get(path);
    items.push({ key: `file:${path}`, kind: 'file', id: null, text: fileLabel(path), file: path,
      select: path, colour: clusterColour(node.cluster), state, priority, hidden: false,
      pos: [node.pos[0], node.pos[1] + node.radius + 0.2, node.pos[2]] });
  }
  return items;
}

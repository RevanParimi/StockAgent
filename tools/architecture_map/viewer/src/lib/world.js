// Where everything stands in the 3D world, computed from the model only: height is the
// plane, left to right is the column in the flow, and nothing is placed by hand.
// Pure functions (no three.js), so tests run them without a browser.

import { moduleOf, nodeOf } from '../theme.js';

export const LEVEL = { externals: 13, top: 8, middle: 0, base: -2.8, stores: -10 };
export const SIZE = { module: [4.6, 1.5, 3.4], sub: [2.3, 0.7, 1.4], store: [5.2, 0.55, 2.6] };
const COLUMN_STEP = 11;
const PAIR_STEP = 5; // two modules sharing a plane and column sit side by side, a step apart
const PAIR_DEPTH = 7.6; // and apart front to back, so neither hides the other from the front
const ROW_STEP = 4.8;
// The top plane sits behind the flow, so that it does not cover it in the view from above.
const TOP_BACK = -12;

const add = (a, b) => [a[0] + b[0], a[1] + b[1], a[2] + b[2]];
const sub = (a, b) => [a[0] - b[0], a[1] - b[1], a[2] - b[2]];
const scale = (a, s) => [a[0] * s, a[1] * s, a[2] * s];
const length = (a) => Math.hypot(a[0], a[1], a[2]);
const unit = (a) => { const n = length(a) || 1; return scale(a, 1 / n); };
const mean = (values) => values.reduce((s, v) => s + v, 0) / (values.length || 1);

function gridColumns(modules) {
  const flat = modules.filter((m) => m.plane !== 'ring').map((m) => m.column);
  const columns = flat.length ? flat : modules.map((m) => m.column);
  return (Math.min(...columns) + Math.max(...columns)) / 2;
}

function placeModules(modules) {
  const middle = gridColumns(modules);
  const groups = new Map();
  for (const m of modules) {
    if (m.plane === 'ring') continue;
    const key = `${m.plane}:${m.column}`;
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key).push(m);
  }
  const placed = [];
  for (const group of groups.values()) {
    const rows = Math.ceil(group.length / 2);
    group.forEach((m, i) => {
      const row = Math.floor(i / 2);
      const alone = group.length - row * 2 === 1;
      const side = alone ? 0 : (i % 2 === 0 ? -0.5 : 0.5);
      const depth = group.length === 2
        ? (i === 0 ? 0.5 : -0.5) * PAIR_DEPTH
        : ((rows - 1) / 2 - row) * ROW_STEP;
      placed.push({
        ...pick(m),
        pos: [(m.column - middle) * COLUMN_STEP + side * PAIR_STEP,
          LEVEL[m.plane] ?? LEVEL.middle,
          (m.plane === 'top' ? TOP_BACK : 0) + depth],
        size: SIZE.module,
      });
    });
  }
  return placed;
}

const pick = (m) => ({ id: m.id, name: m.name, short: m.short, plane: m.plane, column: m.column });

// The ring runs around the product plane; its modules sit on the right-hand side of it,
// in column order from front to back.
function placeRing(modules, others) {
  const ring = modules.filter((m) => m.plane === 'ring').sort((a, b) => a.column - b.column);
  const flat = others.filter((m) => m.plane !== 'top');
  const xs = flat.map((m) => Math.abs(m.pos[0]));
  const zs = flat.map((m) => Math.abs(m.pos[2]));
  const rx = (xs.length ? Math.max(...xs) : 10) + 11;
  const rz = Math.max(14, (zs.length ? Math.max(...zs) : 0) + 9);
  const spread = Math.min(Math.PI * 0.75, Math.max(0, ring.length - 1) * 0.85);
  const placed = ring.map((m, i) => {
    const angle = ring.length === 1 ? 0 : spread / 2 - (spread * i) / (ring.length - 1);
    return {
      ...pick(m),
      pos: [rx * Math.cos(angle), LEVEL.middle, rz * Math.sin(angle)],
      size: SIZE.module,
    };
  });
  return { placed, rx, rz };
}

// A store sits under the modules that write it; stores keep that left-to-right order in
// a grid three deep, so none overlaps another.
function placeStores(model, byId, extent) {
  const list = model.stores.map((s) => {
    const writers = [...new Set(s.writers.map(moduleOf))].filter((id) => byId.has(id));
    const readers = [...new Set(s.readers.map(moduleOf))].filter((id) => byId.has(id));
    const anchors = (writers.length ? writers : readers).map((id) => byId.get(id).pos[0]);
    return { id: s.id, name: s.name, path: s.path, writers, readers, anchor: mean(anchors) };
  });
  list.sort((a, b) => a.anchor - b.anchor || a.id.localeCompare(b.id, 'en'));
  const depth = 3;
  const columns = Math.max(1, Math.ceil(list.length / depth));
  const width = Math.max(extent[1] - extent[0], (columns - 1) * (SIZE.store[0] + 1));
  const start = mean(extent) - width / 2;
  return list.map(({ anchor, ...store }, i) => {
    const column = Math.floor(i / depth);
    const row = i % depth;
    const x = columns === 1 ? mean(extent) : start + (column * width) / (columns - 1);
    return { ...store, pos: [x, LEVEL.stores, (row - (depth - 1) / 2) * 5.6], size: SIZE.store };
  });
}

function placeExternals(model, byId) {
  const externals = (model.externals ?? []).map((e) => {
    const sources = model.flows
      .filter((f) => f.to === e.id)
      .map((f) => byId.get(nodeOf(f.from))?.pos[0])
      .filter((x) => x !== undefined);
    return { id: e.id, name: e.name, x: sources.length ? mean(sources) : 0 };
  });
  externals.sort((a, b) => a.x - b.x || a.id.localeCompare(b.id, 'en'));
  let last = -Infinity;
  return externals.map(({ x, ...e }) => {
    const placed = Math.max(x, last + 9);
    last = placed;
    return { ...e, pos: [placed, LEVEL.externals, TOP_BACK] };
  });
}

/** A point on the quadratic curve through three control points. */
export function curvePoint([a, b, c], t) {
  const u = 1 - t;
  return [0, 1, 2].map((i) => u * u * a[i] + 2 * u * t * b[i] + t * t * c[i]);
}

function flowCurve(from, to, index) {
  const direction = unit(sub(to.pos, from.pos));
  const trim = Math.min(2.7, length(sub(to.pos, from.pos)) * 0.3);
  const start = add(from.pos, scale(direction, trim));
  const end = sub(to.pos, scale(direction, trim));
  const middle = scale(add(start, end), 0.5);
  const distance = length(sub(end, start));
  const level = Math.abs(to.pos[1] - from.pos[1]) < 1;
  // Tubes on one plane arc upwards, those between planes bow towards the front. The side
  // step keeps A to B apart from B to A, and neighbouring tubes apart from each other.
  const forward = to.pos[0] >= from.pos[0] ? 1 : -1;
  const lift = level
    ? [0, 1.4 + distance * 0.07 + (index % 3) * 0.35, forward * (1 + (index % 2) * 0.9)]
    : [forward * 0.6, 0, 2 + (index % 3) * 0.9];
  return [start, add(middle, lift), end];
}

export function flowKey(flow) {
  return `${flow.from}>${flow.to}`;
}

/** Every position in the world. */
export function layoutWorld(model) {
  const flat = placeModules(model.modules);
  const ring = placeRing(model.modules, flat);
  const modules = [...flat, ...ring.placed]
    .sort((a, b) => Number(a.id.slice(1)) - Number(b.id.slice(1)));
  const byId = new Map(modules.map((m) => [m.id, m]));
  const xs = flat.map((m) => m.pos[0]);
  const extent = [Math.min(...xs, 0), Math.max(...xs, 0)];
  const stores = placeStores(model, byId, extent);
  const externals = placeExternals(model, byId);
  const anchors = new Map([...byId, ...externals.map((e) => [e.id, e])]);

  const flows = [];
  model.flows.forEach((f, index) => {
    const from = anchors.get(nodeOf(f.from));
    const to = anchors.get(nodeOf(f.to));
    if (!from || !to || from === to) return;
    flows.push({
      key: flowKey(f), from: f.from, to: f.to, what: f.what,
      ring: from.plane === 'ring' || to.plane === 'ring',
      points: flowCurve(from, to, index),
    });
  });

  const pipes = [];
  for (const store of stores) {
    for (const writer of store.writers) {
      const m = byId.get(writer);
      const top = add(m.pos, [0, -m.size[1] / 2, 0]);
      const end = add(store.pos, [0, store.size[1] / 2, 0]);
      const bend = [(top[0] + end[0]) / 2, (top[1] + end[1]) / 2 - 1, (top[2] + end[2]) / 2];
      pipes.push({ store: store.id, module: writer, points: [top, bend, end] });
    }
  }

  const planes = planeSlabs(modules, stores, externals);
  const bounds = boundsOf([
    ...modules.flatMap((m) => corners(m.pos, m.size)),
    ...stores.flatMap((s) => corners(s.pos, s.size)),
    ...externals.map((e) => e.pos),
  ]);
  return { modules, stores, externals, flows, pipes, planes, ring: { rx: ring.rx, rz: ring.rz },
    bounds };
}

function corners(pos, size) {
  const out = [];
  for (const dx of [-0.5, 0.5]) {
    for (const dy of [-0.5, 0.5]) {
      for (const dz of [-0.5, 0.5]) {
        out.push([pos[0] + dx * size[0], pos[1] + dy * size[1], pos[2] + dz * size[2]]);
      }
    }
  }
  return out;
}

export function boundsOf(points) {
  const min = [0, 1, 2].map((i) => Math.min(...points.map((p) => p[i])));
  const max = [0, 1, 2].map((i) => Math.max(...points.map((p) => p[i])));
  return { min, max, centre: scale(add(min, max), 0.5) };
}

const PLANE_NAMES = {
  top: 'What people see', middle: 'The product, flowing left to right',
  base: 'The base frame', stores: 'Storage (the data volume)',
};

function planeSlabs(modules, stores, externals) {
  const groups = {
    top: modules.filter((m) => m.plane === 'top'),
    middle: modules.filter((m) => m.plane === 'middle'),
    base: modules.filter((m) => m.plane === 'base'),
    stores,
  };
  const wide = groups.middle.concat(groups.base);
  const out = [];
  for (const [id, items] of Object.entries(groups)) {
    if (!items.length) continue;
    // the base frame lies under the product plane, so it spans it
    const span = id === 'base' ? wide : id === 'top' ? items.concat(externals) : items;
    const xs = span.map((i) => i.pos[0]);
    const zs = span.map((i) => i.pos[2]);
    const width = Math.max(...xs) - Math.min(...xs) + 8;
    const depth = Math.max(12, Math.max(...zs) - Math.min(...zs) + 8);
    const y = (id === 'stores' ? LEVEL.stores : LEVEL[id]) - 1.05;
    out.push({
      id, name: PLANE_NAMES[id],
      centre: [(Math.max(...xs) + Math.min(...xs)) / 2, y,
        (Math.max(...zs) + Math.min(...zs)) / 2],
      size: [width, depth],
    });
  }
  return out;
}

/** The small blocks a selected module unfolds into: two abreast above it, wide apart so
 *  their names do not run into each other. */
export function layoutSubmodules(moduleBlock, submodules) {
  const perRow = 2;
  const step = [8.2, 1.35];
  return submodules.map((s, i) => {
    const row = Math.floor(i / perRow);
    const inRow = Math.min(perRow, submodules.length - row * perRow);
    const column = i % perRow;
    return {
      id: s.id, name: s.name,
      pos: [moduleBlock.pos[0] + (column - (inRow - 1) / 2) * step[0],
        moduleBlock.pos[1] + 2.3 + row * step[1],
        moduleBlock.pos[2]],
      size: SIZE.sub,
    };
  });
}

// The four views. Each is the direction from the target to the camera.
export const PRESETS = {
  front: { key: '1', label: 'Front', dir: [0, 0.42, 1], fov: 40,
    asks: 'How does a stock become a verdict, then a trade?' },
  top: { key: '2', label: 'Top', dir: [0, 1, 0.03], fov: 40,
    asks: 'What are the modules and their neighbours?' },
  // A narrow lens from far away keeps the three heights apart.
  side: { key: '3', label: 'Side', dir: [1, 0.07, 0.02], fov: 13,
    asks: 'What does a person see, what decides, what is stored?' },
  // From below and in front, so a module sits above the stores its pipes reach.
  below: { key: '4', label: 'Below', dir: [0, -1, 0.8], fov: 40,
    asks: 'Which module writes which file?' },
};

const cross = (a, b) => [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2],
  a[0] * b[1] - a[1] * b[0]];
const dot = (a, b) => a[0] * b[0] + a[1] * b[1] + a[2] * b[2];

/** The camera position that frames the whole box from `dir`, for this field of view and
 *  shape of window: every corner lands inside the frustum. */
export function fitCamera(bounds, dir, fovDegrees, aspect, margin = 1.08) {
  const toCamera = unit(dir);
  const forward = scale(toCamera, -1);
  let right = cross(forward, [0, 1, 0]);
  if (length(right) < 1e-6) right = [1, 0, 0];
  right = unit(right);
  const up = cross(right, forward);
  const tanV = Math.tan((fovDegrees * Math.PI) / 360);
  const tanH = tanV * aspect;
  let distance = 1;
  const { min, max, centre } = bounds;
  for (const x of [min[0], max[0]]) {
    for (const y of [min[1], max[1]]) {
      for (const z of [min[2], max[2]]) {
        const c = sub([x, y, z], centre);
        const depth = dot(c, forward);
        distance = Math.max(distance, Math.abs(dot(c, right)) / tanH - depth,
          Math.abs(dot(c, up)) / tanV - depth);
      }
    }
  }
  return { position: add(centre, scale(toCamera, distance * margin)), target: [...centre] };
}

/** The view of one module and its unfolded parts: from the front, a little above. */
export const FOCUS = { dir: [0.12, 0.36, 1], fov: 40 };

export function focusCamera(moduleBlock, subBlocks, aspect) {
  const bounds = boundsOf([
    ...corners(moduleBlock.pos, [14, 4, 7]),
    ...subBlocks.flatMap((s) => corners(s.pos, [SIZE.sub[0] + 3, 2, SIZE.sub[2]])),
  ]);
  return { ...fitCamera(bounds, FOCUS.dir, FOCUS.fov, aspect, 1.18), fov: FOCUS.fov };
}

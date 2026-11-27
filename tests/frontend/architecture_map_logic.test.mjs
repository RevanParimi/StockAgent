/**
 * MAP-002: the architecture map's pure logic, and the committed page against its source.
 * No browser, no viewer packages: Node alone, so CI runs it after a root `npm ci`.
 *
 *   node --test tests/frontend/architecture_map_logic.test.mjs
 *
 * The checks state what must hold, in their own arithmetic, rather than repeating the
 * viewer's code: nothing overlaps, no logic is lost between the tree and its chart, a
 * view frames everything, text can be read.
 */
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

import {
  FOCUS, LEVEL, PRESETS, fitCamera, focusCamera, layoutSubmodules, layoutWorld,
} from '../../tools/architecture_map/viewer/src/lib/world.js';
import { buildFlow } from '../../tools/architecture_map/viewer/src/lib/flow.js';
import {
  cardLabel, flatCodeStates, flatLayout, flatStates, wrapWords,
} from '../../tools/architecture_map/viewer/src/lib/flat.js';
import {
  findPart, formatHash, parseHash, related, search, searchIndex, settingsFor,
} from '../../tools/architecture_map/viewer/src/lib/select.js';
import {
  BEAD, TOUR_PRESETS, TRACKS, beads, captionOf, clockBounds, clockRing, highlighted, jobLights,
  moments, openingPlay, ringPoint, stepsOf, stopView, traceLights, viewOf,
} from '../../tools/architecture_map/viewer/src/lib/play.js';
import {
  BRIDGE_MODULES, FRONT, MARGIN, codeGraph, codeSummary, dotAt, edgeState, fileLabel, galaxyLabels,
  galaxyLights, importingModules, layoutGalaxy, pickOf,
} from '../../tools/architecture_map/viewer/src/lib/galaxy.js';
import { MODULE, PLANE, SURFACE } from '../../tools/architecture_map/viewer/src/theme.js';
import { sourceHash } from '../../tools/architecture_map/viewer/scripts/source-hash.mjs';

const REPO = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..', '..');
const read = (...p) => readFileSync(path.join(REPO, ...p), 'utf8').replace(/\r\n/g, '\n');
const MODEL = JSON.parse(read('docs', 'architecture-map', 'model.json'));
const MONEY_PATH = ['M3.1', 'M3.2', 'M3.3', 'M3.4', 'M3.5', 'M4.2', 'M5.2', 'M5.3',
  'M6.1', 'M6.2', 'M6.3', 'M6.4', 'M6.5'];
const logicOf = (id) => findPart(MODEL, id).sub.logic;

// -- the world --------------------------------------------------------------------------

const box = (item) => item.pos.map((v, i) => [v - item.size[i] / 2, v + item.size[i] / 2]);
const overlap = (a, b) => box(a).every((range, i) => {
  const other = box(b)[i];
  return range[0] < other[1] && other[0] < range[1];
});
const assertApart = (items, what) => {
  for (let i = 0; i < items.length; i += 1) {
    for (let j = i + 1; j < items.length; j += 1) {
      assert.ok(!overlap(items[i], items[j]), `${what}: ${items[i].id} overlaps ${items[j].id}`);
    }
  }
};

test('the same model always gives the same world', () => {
  assert.deepEqual(layoutWorld(MODEL), layoutWorld(structuredClone(MODEL)));
});

test('every module, store and outside party has its own place', () => {
  const world = layoutWorld(MODEL);
  assert.deepEqual(world.modules.map((m) => m.id), MODEL.modules.map((m) => m.id));
  assert.deepEqual(world.stores.map((s) => s.id).sort(), MODEL.stores.map((s) => s.id).sort());
  assert.deepEqual(world.externals.map((e) => e.id).sort(),
    MODEL.externals.map((e) => e.id).sort());
  assertApart(world.modules, 'modules');
  assertApart(world.stores, 'stores');
  assertApart([...world.modules, ...world.stores], 'modules and stores');
});

test('height is the plane and left to right is the column in the flow', () => {
  const world = layoutWorld(MODEL);
  const plane = (name) => world.modules.filter((m) => m.plane === name).map((m) => m.pos[1]);
  const lowest = (name) => Math.min(...plane(name));
  const highest = (name) => Math.max(...plane(name));
  assert.ok(Math.min(...world.externals.map((e) => e.pos[1])) > highest('top'));
  assert.ok(lowest('top') > highest('middle'));
  assert.ok(lowest('middle') > highest('base'));
  assert.ok(lowest('base') > Math.max(...world.stores.map((s) => s.pos[1])));
  const flat = world.modules.filter((m) => m.plane !== 'ring');
  for (const a of flat) {
    for (const b of flat) {
      if (a.column < b.column) assert.ok(a.pos[0] < b.pos[0], `${a.id} left of ${b.id}`);
    }
  }
  // the watchers stand outside the product plane
  const reach = Math.max(...flat.map((m) => m.pos[0]));
  for (const m of world.modules.filter((x) => x.plane === 'ring')) assert.ok(m.pos[0] > reach);
});

test('a store sits between the columns of the modules that write it, in their order', () => {
  const world = layoutWorld(MODEL);
  const x = new Map(world.modules.map((m) => [m.id, m.pos[0]]));
  const anchor = (s) => s.writers.reduce((sum, w) => sum + x.get(w), 0) / s.writers.length;
  const written = world.stores.filter((s) => s.writers.length);
  for (const a of written) {
    for (const b of written) {
      if (anchor(a) + 0.01 < anchor(b)) {
        assert.ok(a.pos[0] <= b.pos[0], `${a.id} not right of ${b.id}`);
      }
    }
  }
});

test('every flow of the model is drawn once, from its source towards its target', () => {
  const world = layoutWorld(MODEL);
  assert.equal(world.flows.length, MODEL.flows.length);
  const places = new Map([...world.modules, ...world.externals].map((m) => [m.id, m.pos]));
  const key = (who) => (who.startsWith('ext.') ? who : who.split('.')[0]);
  const far = (a, b) => Math.hypot(...a.map((v, i) => v - b[i]));
  for (const flow of world.flows) {
    const [start, , end] = flow.points;
    const from = places.get(key(flow.from));
    const to = places.get(key(flow.to));
    assert.ok(far(start, from) < far(start, to), `${flow.key} starts at its source`);
    assert.ok(far(end, to) < far(end, from), `${flow.key} ends at its target`);
    const ring = [flow.from, flow.to].some((w) => world.modules
      .find((m) => m.id === key(w))?.plane === 'ring');
    assert.equal(flow.ring, ring, `${flow.key} dotted only when it touches a watcher`);
  }
});

test('one pipe for each module that writes a store', () => {
  const world = layoutWorld(MODEL);
  const wanted = new Set(MODEL.stores.flatMap((s) => s.writers
    .filter((w) => !w.startsWith('ext.')).map((w) => `${w.split('.')[0]}>${s.id}`)));
  assert.deepEqual(new Set(world.pipes.map((p) => `${p.module}>${p.store}`)), wanted);
  assert.equal(world.pipes.length, wanted.size);
});

test('modules and stores added to the model land without overlapping anything', () => {
  const grown = structuredClone(MODEL);
  const copy = (id, plane, column) => ({ ...structuredClone(grown.modules[1]), id,
    short: id, plane, column,
    submodules: [{ ...grown.modules[1].submodules[0], id: `${id}.1` }] });
  grown.modules.push(copy('M13', 'middle', 3), copy('M14', 'middle', 3), copy('M15', 'middle', 3),
    copy('M16', 'top', 2), copy('M17', 'ring', 7), copy('M18', 'middle', 9));
  grown.stores.push({ id: 'S.new', name: 'New', path: 'data/new', holds: 'x', writers: ['M18.1'],
    readers: [], code: [] });
  const world = layoutWorld(grown);
  assert.equal(world.modules.length, MODEL.modules.length + 6);
  assertApart(world.modules, 'modules');
  assertApart(world.stores, 'stores');
});

test('a selected module unfolds into all its parts, apart and under the plane above', () => {
  const world = layoutWorld(MODEL);
  for (const data of MODEL.modules) {
    const block = world.modules.find((m) => m.id === data.id);
    const parts = layoutSubmodules(block, data.submodules);
    assert.deepEqual(parts.map((p) => p.id), data.submodules.map((s) => s.id));
    assertApart([block, ...parts], data.id);
    if (block.plane === 'middle') {
      for (const p of parts) assert.ok(p.pos[1] + p.size[1] / 2 < LEVEL.top - 0.5, p.id);
    }
  }
});

// The test's own camera: is every corner inside the picture, and is the picture filled?
function inside(camera, fov, aspect, corners) {
  const sub = (a, b) => a.map((v, i) => v - b[i]);
  const dot = (a, b) => a[0] * b[0] + a[1] * b[1] + a[2] * b[2];
  const unit = (a) => a.map((v) => v / Math.hypot(...a));
  const cross = (a, b) => [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2],
    a[0] * b[1] - a[1] * b[0]];
  const forward = unit(sub(camera.target, camera.position));
  const right = unit(cross(forward, [0, 1, 0]));
  const up = cross(right, forward);
  const tan = Math.tan((fov * Math.PI) / 360);
  return corners.map((c) => {
    const rel = sub(c, camera.position);
    const depth = dot(rel, forward);
    assert.ok(depth > 0.5, 'in front of the camera');
    return Math.max(Math.abs(dot(rel, right)) / (depth * tan * aspect),
      Math.abs(dot(rel, up)) / (depth * tan));
  });
}

const cornersOf = (items) => items.flatMap((item) => {
  const [x, y, z] = box(item);
  return x.flatMap((a) => y.flatMap((b) => z.map((c) => [a, b, c])));
});

test('every view frames the whole world in any window, without wasting it', () => {
  const world = layoutWorld(MODEL);
  const corners = cornersOf([...world.modules, ...world.stores]);
  for (const [name, preset] of Object.entries(PRESETS)) {
    for (const aspect of [0.7, 1, 1.6, 2.4]) {
      const camera = fitCamera(world.bounds, preset.dir, preset.fov, aspect);
      const reach = inside(camera, preset.fov, aspect, corners);
      assert.ok(Math.max(...reach) <= 1.0001, `${name} at ${aspect} cuts something off`);
      assert.ok(Math.max(...reach) > 0.45, `${name} at ${aspect} leaves the world tiny`);
    }
  }
});

test('the four views look from four different sides, and the clock from above', () => {
  const world = layoutWorld(MODEL);
  const at = Object.values(PRESETS).map((p) => fitCamera(world.bounds, p.dir, p.fov, 1.6).position);
  assert.deepEqual(Object.values(PRESETS).map((p) => p.key), ['1', '2', '3', '4', '5']);
  assert.ok(at[4][1] > at[0][1] && at[4][2] > world.bounds.centre[2], 'Clock: high, in front');
  const dy = (i) => at[i][1] - world.bounds.centre[1];
  assert.ok(dy(1) > 0 && dy(1) > dy(0), 'Top is above');
  assert.ok(dy(3) < 0, 'Below is underneath');
  assert.ok(at[2][0] - world.bounds.centre[0] > 3 * Math.abs(at[2][2]), 'Side is along the flow');
});

test('a selected module and its parts are all in view', () => {
  const world = layoutWorld(MODEL);
  for (const data of MODEL.modules) {
    const block = world.modules.find((m) => m.id === data.id);
    const parts = layoutSubmodules(block, data.submodules);
    const camera = focusCamera(block, parts, 1.2);
    assert.equal(camera.fov, FOCUS.fov);
    assert.ok(Math.max(...inside(camera, camera.fov, 1.2, cornersOf([block, ...parts]))) <= 1,
      data.id);
  }
});

// A block as the picture shows it: the rectangle its corners cover, in screen units from
// the middle (x to the right, y up), by the test's own camera.
function rectangle(camera, fov, aspect, item) {
  const sub = (a, b) => a.map((v, i) => v - b[i]);
  const dot = (a, b) => a[0] * b[0] + a[1] * b[1] + a[2] * b[2];
  const unit = (a) => a.map((v) => v / Math.hypot(...a));
  const cross = (a, b) => [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2],
    a[0] * b[1] - a[1] * b[0]];
  const forward = unit(sub(camera.target, camera.position));
  const right = unit(cross(forward, [0, 1, 0]));
  const up = cross(right, forward);
  const tan = Math.tan((fov * Math.PI) / 360);
  const points = cornersOf([item]).map((c) => {
    const rel = sub(c, camera.position);
    const depth = dot(rel, forward);
    return [dot(rel, right) / (depth * tan * aspect), dot(rel, up) / (depth * tan)];
  });
  const xs = points.map((p) => p[0]);
  const ys = points.map((p) => p[1]);
  return { x: [Math.min(...xs), Math.max(...xs)], y: [Math.min(...ys), Math.max(...ys)] };
}
const area = (r) => (r.x[1] - r.x[0]) * (r.y[1] - r.y[0]);
const shared = (a, b) => Math.max(0, Math.min(a.x[1], b.x[1]) - Math.max(a.x[0], b.x[0]))
  * Math.max(0, Math.min(a.y[1], b.y[1]) - Math.max(a.y[0], b.y[0]));

const seen = (preset, aspect = 1.6) => {
  const world = layoutWorld(MODEL);
  const { dir, fov } = PRESETS[preset];
  const camera = fitCamera(world.bounds, dir, fov, aspect);
  return world.modules.map((m) => ({ ...m, rect: rectangle(camera, fov, aspect, m) }));
};

test('from the front no module hides more than a fifth of another', () => {
  const modules = seen('front');
  for (const a of modules) {
    for (const b of modules) {
      if (a.id >= b.id) continue;
      const hidden = shared(a.rect, b.rect) / Math.min(area(a.rect), area(b.rect));
      assert.ok(hidden < 0.2, `${a.id} and ${b.id}: ${hidden.toFixed(2)}`);
    }
  }
});

test('from above no screen module covers a module of the product', () => {
  const modules = seen('top');
  for (const top of modules.filter((m) => m.plane === 'top')) {
    for (const below of modules.filter((m) => m.plane === 'middle')) {
      assert.equal(shared(top.rect, below.rect), 0, `${top.id} covers ${below.id}`);
    }
  }
});

test('a selected module stays large in the picture, with its parts above it', () => {
  const world = layoutWorld(MODEL);
  for (const data of MODEL.modules) {
    const block = world.modules.find((m) => m.id === data.id);
    const parts = layoutSubmodules(block, data.submodules);
    const camera = focusCamera(block, parts, 1.2);
    const own = rectangle(camera, camera.fov, 1.2, block);
    assert.ok((own.x[1] - own.x[0]) / 2 > 0.14, `${data.id} is small: ${own.x}`);
    for (const p of parts) {
      assert.ok(rectangle(camera, camera.fov, 1.2, p).y[0] > own.y[0], `${p.id} above`);
    }
  }
});

// -- flowcharts -------------------------------------------------------------------------

const tree = (text, extra = {}, children = []) => ({ text, children, ...extra });
const kinds = (graph) => graph.nodes.map((n) => n.kind);
const edge = (graph, from, to) => graph.edges.find((e) => nodeText(graph, e.from).includes(from)
  && nodeText(graph, e.to).includes(to));
const nodeText = (graph, id) => graph.nodes.find((n) => n.id === id).text;

test('a decision that ends a path says yes to the end and no to what follows', () => {
  const [g] = buildFlow([tree('run', {}, [
    tree('empty ─► stop here', { kind: 'decision', ends: true }),
    tree('carry on', { then: true }),
  ])]);
  assert.deepEqual(kinds(g), ['start', 'decision', 'end', 'step']);
  assert.equal(edge(g, 'empty', 'stop here').label, 'yes');
  assert.equal(edge(g, 'empty', 'carry on').label, 'no');
  assert.equal(edge(g, 'empty', 'carry on').type, 'then');
});

test('a decision whose paths join again does not call the continuation no', () => {
  const [g] = buildFlow([tree('run', {}, [
    tree('big miss ─► review the thesis', { kind: 'decision' }),
    tree('carry on', { then: true }),
  ])]);
  assert.deepEqual(kinds(g), ['start', 'decision', 'step', 'step']);
  assert.equal(edge(g, 'big miss', 'review').label, 'yes');
  assert.equal(edge(g, 'big miss', 'carry on').label, '');
});

test('an "else" check is the no path of the check before it', () => {
  const [g] = buildFlow([tree('decide', {}, [
    tree('sell if any', { kind: 'decision' }),
    tree('else trim if', { kind: 'decision', then: true }),
    tree('else hold', { kind: 'end', then: true }),
  ])]);
  assert.equal(edge(g, 'sell', 'trim').label, 'no');
  assert.equal(edge(g, 'trim', 'hold').label, 'no');
});

test('a short condition under a decision becomes the arrow, a long one stays in its box', () => {
  const [g] = buildFlow([tree('by mode', { kind: 'decision' }, [
    tree('record ─► log only'),
    tree('direction right and the error under half a percent ─► reuse'),
  ])]);
  assert.equal(edge(g, 'by mode', 'log only').label, 'record');
  const long = g.nodes.find((n) => n.text.includes('half a percent'));
  assert.ok(long.text.includes('reuse'));
});

test('lines of detail share one box, unless the flow goes on from one of them', () => {
  const [g] = buildFlow([tree('check', {}, [tree('a'), tree('b'), tree('c'),
    tree('d'), tree('e', { then: true })])]);
  const list = g.nodes.find((n) => n.kind === 'list');
  assert.deepEqual(list.items, ['a', 'b', 'c']);
  assert.deepEqual(g.nodes.filter((n) => n.kind === 'step').map((n) => n.text), ['d', 'e']);
  assert.equal(edge(g, 'd', 'e').type, 'then');
});

test('wrapped lines are joined, dot leaders made a dash and ellipses kept', () => {
  const texts = ['automobile (9) ....... sales,\nraw materials', 'renewable (6) . business',
    'stop_breach .. below', 'metals ... 18 in all'];
  assert.deepEqual(buildFlow(texts.map((t) => tree(t))).map((g) => g.nodes[0].text),
    ['automobile (9) — sales, raw materials', 'renewable (6) — business', 'stop_breach — below',
      'metals … 18 in all']);
});

test('under a decision even one line of detail is not drawn as a branch', () => {
  const [g] = buildFlow([tree('wait', { kind: 'decision' }, [tree('only a note')])]);
  assert.deepEqual(kinds(g), ['decision', 'list']);
});

test('from a decision every arrow to a box says what leads there', () => {
  for (const module of MODEL.modules) {
    for (const part of module.submodules) {
      for (const g of buildFlow(part.logic)) {
        const kind = new Map(g.nodes.map((n) => [n.id, n.kind]));
        for (const e of g.edges) {
          if (e.type === 'part' && kind.get(e.from) === 'decision' && kind.get(e.to) !== 'list') {
            assert.ok(e.label, `${part.id}: unlabelled arrow to “${nodeText(g, e.to).slice(0, 60)}”`);
          }
        }
      }
    }
  }
});

// Every word of the tree is in the chart, once: nothing lost, nothing invented. The
// arrows and the dot leaders are drawn, not written; "yes" and "no" are the chart's.
function words(text) {
  return text.split(/\s+/).map((w) => w.trim()).filter((w) => w && !['─►', '—', '…'].includes(w)
    && !/^\.+$/.test(w));
}
const treeWords = (nodes) => nodes.flatMap((n) => [...words(n.text.replace(/─►/g, ' ─► ')),
  ...treeWords(n.children)]);

test('every part of the model draws a chart that holds all of its words', () => {
  for (const module of MODEL.modules) {
    for (const part of module.submodules) {
      const graphs = buildFlow(part.logic);
      const drawn = graphs.flatMap((g) => [
        ...g.nodes.flatMap((n) => words((n.items ?? [n.text]).join(' ').replace(/─►/g, ' ─► '))),
        // a "no" on a "then" arrow is the chart's own; every other label is the tree's
        // (or the chart's "yes", left out below)
        ...g.edges.filter((e) => e.type !== 'then').flatMap((e) => words(e.label)),
      ]);
      const wanted = treeWords(part.logic).filter((w) => w !== 'yes');
      assert.deepEqual(drawn.filter((w) => w !== 'yes').sort(), wanted.sort(), part.id);
    }
  }
});

test('every chart is one connected drawing per tree, and nothing leaves an end', () => {
  for (const module of MODEL.modules) {
    for (const part of module.submodules) {
      const graphs = buildFlow(part.logic);
      assert.equal(graphs.length, part.logic.length, part.id);
      for (const g of graphs) {
        const ids = new Set(g.nodes.map((n) => n.id));
        assert.equal(ids.size, g.nodes.length, `${part.id}: one id each`);
        const reached = new Set([g.nodes[0].id]);
        for (let grew = true; grew;) {
          grew = false;
          for (const e of g.edges) {
            assert.ok(ids.has(e.from) && ids.has(e.to), `${part.id}: ${e.id}`);
            if (reached.has(e.from) && !reached.has(e.to)) { reached.add(e.to); grew = true; }
          }
        }
        assert.equal(reached.size, ids.size, `${part.id}: every box is reached`);
        assert.equal(g.edges.length, ids.size - 1, `${part.id}: one way into each box`);
        for (const n of g.nodes.filter((x) => x.kind === 'end')) {
          assert.ok(!g.edges.some((e) => e.from === n.id), `${part.id}: ${n.text} is an end`);
        }
      }
    }
  }
});

test('every money-path part is drawn with decisions or an order, not as a bare list', () => {
  const plain = MONEY_PATH.filter((id) => {
    const graphs = buildFlow(logicOf(id));
    return !graphs.some((g) => g.sequential || g.nodes.some((n) => n.kind === 'decision'));
  });
  assert.deepEqual(plain, []);
});

// The order along the "then" arrows, from the first box that holds `from`.
function along(id, from) {
  for (const g of buildFlow(logicOf(id))) {
    let node = g.nodes.find((n) => n.text.includes(from));
    if (!node) continue;
    const seen = [node.text];
    for (;;) {
      const next = g.edges.find((e) => e.from === node.id && e.type === 'then');
      if (!next) return seen;
      node = g.nodes.find((n) => n.id === next.to);
      seen.push(node.text);
    }
  }
  return [];
}
const inOrder = (texts, expected, what) => {
  assert.equal(texts.length, expected.length, `${what}: ${texts.join(' | ')}`);
  expected.forEach((part, i) => assert.ok(texts[i].includes(part), `${what}: ${texts[i]}`));
};

test('the advisor chart checks identity, then exit, trim and add, and holds otherwise', () => {
  inOrder(along('M5.2', 'identity changed'),
    ['identity changed', 'EXIT if any', 'else TRIM', 'else ADD', 'else HOLD'], 'M5.2');
});

test('the daily review chart gates in the order the code returns', () => {
  inOrder(along('M4.2', 'no envelope'),
    ['no envelope', 'no row for D', 'non-actionable', 'identity or price basis'], 'M4.2 step 1');
  inOrder(along('M4.2', 'Step 0').slice(0, 4),
    ['Step 0', 'Step 1', 'Step 2', 'Step 3'], 'M4.2 steps');
});

test('the analysis chart stops an unscored run before the aggregator', () => {
  const [g] = buildFlow(logicOf('M3.1'));
  assert.equal(edge(g, 'no dimension scored', 'AnalysisUnavailable').label, 'yes');
  assert.equal(edge(g, 'no dimension scored', '6 aggregator').label, 'no');
});

test('a buy that fails a check is skipped; the costs are paid on every trade', () => {
  const [g] = buildFlow(logicOf('M5.3'));
  assert.equal(edge(g, 'any check fails', 'skipped').label, 'yes');
  // sells pay them too, so the costs do not hang on the buy checks
  assert.equal(edge(g, 'execute_advice', 'pays its costs').type, 'part');
});

test('the advisor chart names the verdict each check ends in, and adjusts it afterwards', () => {
  const [decide, after] = buildFlow(logicOf('M5.2'));
  for (const [check, verdict] of [['EXIT if any', 'verdict EXIT'], ['else TRIM', 'verdict TRIM'],
    ['else ADD', 'verdict ADD']]) {
    assert.equal(edge(decide, check, verdict).label, 'yes');
  }
  assert.ok(!decide.nodes.some((n) => n.text.includes('SWITCH')),
    'switching comes after the checks, in a drawing of its own');
  assert.ok(after.nodes.some((n) => (n.items ?? [n.text]).some((t) => t.includes('SWITCH'))));
});

test('the daily review re-runs only after a miss, and asks why in both cases', () => {
  const [g] = buildFlow(logicOf('M4.2'));
  assert.equal(edge(g, 'direction right', 'reuse').label, 'yes');
  assert.equal(edge(g, 'direction right', 're-run today').label, 'no');
  const why = edge(g, 'direction right', 'FeedbackAgent');
  assert.deepEqual([why.type, why.label], ['then', '']);
});

test('the weekly funnel dives its re-dives first, as the code calls them', () => {
  const order = along('M6.1', 're-dives first');
  inOrder(order, ['re-dives first', 'then the IPO candidates', 'then the screen', 'leftover'],
    'M6.1 dives');
});

// -- selection, settings and search -----------------------------------------------------

test('the address holds the part and the audience, and refuses what is not on the map', () => {
  const none = { id: null, audience: null, play: null, unknown: null };
  assert.deepEqual(parseHash('#m=M5.2&v=dev', MODEL),
    { ...none, id: 'M5.2', audience: 'developer' });
  assert.deepEqual(parseHash('#m=M5', MODEL), { ...none, id: 'M5' });
  assert.deepEqual(parseHash('', MODEL), none);
  for (const bad of ['M99', 'M5.99', '<img src=x>', 'M5.2.1']) {
    const got = parseHash(`#m=${encodeURIComponent(bad)}`, MODEL);
    assert.equal(got.id, null, bad);
    assert.equal(got.unknown, bad);
  }
  for (const state of [{ id: 'M3', audience: 'manager' }, { id: 'M6.4', audience: 'developer' }]) {
    const back = parseHash(formatHash(state), MODEL);
    assert.equal(back.id, state.id);
    assert.equal(back.audience ?? 'manager', state.audience);
  }
});

test('a selection keeps what it touches and nothing else', () => {
  const touched = related(MODEL, 'M5');
  const base = (who) => (who.startsWith('ext.') ? who : who.split('.')[0]);
  const neighbours = new Set(['M5', ...MODEL.flows.flatMap((f) => [base(f.from), base(f.to)]
    .includes('M5') ? [base(f.from), base(f.to)] : [])]);
  assert.deepEqual(touched.modules, neighbours);
  assert.ok(!touched.modules.has('M12'));
  const stores = MODEL.stores.filter((s) => [...s.writers, ...s.readers]
    .some((w) => base(w) === 'M5')).map((s) => s.id);
  assert.deepEqual([...touched.stores].sort(), stores.sort());
  // a part keeps only its own stores
  const advisor = related(MODEL, 'M5.2').stores;
  assert.deepEqual([...advisor].sort(), MODEL.stores.filter((s) => [...s.writers, ...s.readers]
    .includes('M5.2')).map((s) => s.id).sort());
  assert.equal(related(MODEL, null), null);
});

test('a setting shows the repository default and the cited production value', () => {
  const [mode] = settingsFor(MODEL, findPart(MODEL, 'M3.4').sub)
    .filter((s) => s.key === 'decision_gate.mode');
  const cited = MODEL.production.find((p) => p.key === 'decision_gate.mode');
  assert.equal(mode.production.value, cited.value);
  assert.equal(mode.production.source, 'KT section 1');
  assert.ok(mode.production.as_of);
  assert.equal(mode.value, String(MODEL.switches.find((s) => s.key === mode.key).default));
  const uncited = settingsFor(MODEL, findPart(MODEL, 'M3.3').sub);
  assert.ok(uncited.every((s) => s.production === null));
});

test('search finds parts, files and settings, needs every word, and says nothing for nothing', () => {
  const index = searchIndex(MODEL);
  assert.equal(search(index, 'advisor')[0].id, 'M5.2');
  assert.equal(search(index, 'M3.4')[0].id, 'M3.4');
  assert.ok(search(index, 'advisor.py').some((r) => r.kind === 'file' && r.id === 'M5.2'));
  assert.ok(search(index, 'decision_gate.mode').some((r) => r.id === 'M3.4'));
  assert.deepEqual(search(index, ''), []);
  assert.deepEqual(search(index, 'advisor zzzz'), []);
  assert.ok(search(index, 'a', 5).length <= 5);
  for (const item of search(index, 'shelf')) assert.ok(findPart(MODEL, item.id), item.title);
});

// -- the clock, the trace and the tour (MAP-003) ---------------------------------------

const jobById = (id) => MODEL.jobs.find((j) => j.id === id);
const drawnFlows = () => new Set(layoutWorld(MODEL).flows.map((f) => f.key));
const base = (who) => (who.startsWith('ext.') || who.startsWith('S.') ? who : who.split('.')[0]);

test('the day holds every job at each of its times, in clock order', () => {
  const day = moments(MODEL);
  const wanted = MODEL.jobs.flatMap((j) => j.schedule.time.split(', ').map((t) => `${j.id}@${t}`));
  assert.deepEqual(day.map((m) => m.key).sort(), wanted.sort());
  assert.ok(day.every((m) => /^\d\d:\d\d$/.test(m.time)), 'every job has a time of day');
  for (let i = 1; i < day.length; i += 1) assert.ok(day[i - 1].time <= day[i].time, day[i].key);
  assert.deepEqual(day.filter((m) => m.job.id === 'macro_market_news').map((m) => m.time),
    ['09:00', '12:00', '15:00']);
  // at the same time the daily job comes before the monthly one
  const nine = day.filter((m) => m.time === '09:00').map((m) => m.job.schedule.group);
  assert.deepEqual(nine, ['daily', 'calendar']);
  // by the kind of job, not by its name
  const renamed = structuredClone(MODEL);
  renamed.jobs.find((j) => j.id === 'rl_monthly_forecast').id = 'aaa_forecast';
  assert.deepEqual(moments(renamed).filter((m) => m.time === '09:00').map((m) => m.job.id),
    ['macro_market_news', 'aaa_forecast']);
});

test('every job lights its own part, and only flows the world draws between lit things', () => {
  const drawnKeys = drawnFlows();
  const ids = new Set([...MODEL.modules.flatMap((m) => [m.id, ...m.submodules.map((s) => s.id)]),
    ...MODEL.stores.map((s) => s.id), ...MODEL.externals.map((e) => e.id)]);
  for (const job of MODEL.jobs) {
    const lit = jobLights(job);
    assert.ok(job.lights.every((name) => ids.has(name)), job.id);
    assert.ok(lit.modules.has(job.module.split('.')[0]), `${job.id} lights its module`);
    for (const key of lit.flows) {
      assert.ok(drawnKeys.has(key), `${job.id}: ${key} is not drawn`);
      for (const end of key.split('>')) {
        assert.ok(lit.modules.has(base(end)) || lit.externals.has(end), `${job.id}: ${end} dark`);
      }
    }
  }
});

test('the daily review lights the money path: data to portfolio to the account holder', () => {
  const lit = jobLights(jobById('rl_daily_review'));
  for (const id of ['M4.2', 'M5.1', 'M5.2', 'M5.3', 'M6.4']) assert.ok(lit.parts.has(id), id);
  for (const key of ['M4>M5', 'M5>M9', 'M9>ext.user']) assert.ok(lit.flows.has(key), key);
  assert.ok(lit.stores.has('S.portfolio') && lit.externals.has('ext.user'));
});

test('every trace step lights what it names; a job stands for its part', () => {
  const drawnKeys = drawnFlows();
  const steps = stepsOf(MODEL, 'trace');
  assert.equal(steps.length, MODEL.traces[0].steps.length);
  for (const step of steps) {
    const lit = traceLights(MODEL, step);
    assert.ok(lit.modules.size > 0, step.text);
    for (const name of step.refs) {
      const job = jobById(name);
      if (job) assert.ok(lit.parts.has(job.module), `${name} lights ${job.module}`);
    }
    for (const key of lit.flows) assert.ok(drawnKeys.has(key), key);
    assert.equal(lit.flows.size, (step.flows ?? []).length, step.text);
  }
});

test('each tour stop shows its view: a part opened up, a job on the clock, or what it names', () => {
  const stops = stepsOf(MODEL, 'tour');
  assert.deepEqual(TOUR_PRESETS, ['front', 'top', 'side', 'below', 'clock', 'focus']);
  for (const stop of stops) {
    assert.ok(TOUR_PRESETS.includes(stop.preset), stop.preset);
    const shown = viewOf(MODEL, 'tour', stop);
    assert.ok(Object.keys(PRESETS).includes(shown.preset), `${stop.preset} -> ${shown.preset}`);
    if (stop.preset === 'focus') assert.equal(shown.selected, stop.ref);
    else assert.equal(shown.selected, null);
    if (stop.preset === 'clock') assert.equal(shown.job.id, stop.ref);
    if (!stop.ref) assert.equal(shown.lit, null, 'nothing named, nothing dimmed');
  }
  const top = stopView(MODEL, { preset: 'top', ref: 'M11', caption: 'x' });
  assert.ok(top.lit.modules.has('M11') && top.lit.modules.has('M3'));
  assert.ok(!top.lit.modules.has('M8'), 'a module it does not touch stays dim');
  assert.deepEqual([...top.lit.flows].sort(), MODEL.flows
    .filter((f) => [f.from, f.to].some((w) => base(w) === 'M11'))
    .map((f) => `${f.from}>${f.to}`).sort());
  const ledger = stopView(MODEL, { preset: 'below', ref: 'S.portfolio', caption: 'x' });
  assert.deepEqual([...ledger.lit.stores], ['S.portfolio']);
  const writers = new Set(MODEL.stores.find((s) => s.id === 'S.portfolio').writers.map(base));
  assert.deepEqual(ledger.lit.modules, writers);
});

test('the clock and the trace view their steps from the clock and the front', () => {
  const day = stepsOf(MODEL, 'clock');
  const shown = viewOf(MODEL, 'clock', day[0]);
  assert.equal(shown.preset, 'clock');
  assert.equal(shown.job.id, day[0].job.id);
  assert.equal(viewOf(MODEL, 'trace', MODEL.traces[0].steps[0]).preset, 'front');
});

test('what a step highlights is also said in words', () => {
  const said = (mode, step) => highlighted(MODEL, viewOf(MODEL, mode, step));
  const buy = MODEL.traces[0].steps.find((s) => s.text.includes('XYZ joins the managed list'));
  const words = said('trace', buy);
  for (const name of buy.refs) {
    const module = MODEL.modules.find((m) => m.id === name);
    const part = MODEL.modules.flatMap((m) => m.submodules).find((s) => s.id === name);
    const store = MODEL.stores.find((s) => s.id === name);
    const wanted = module ? `${name} ${module.short}` : part ? `${name} ${part.name}` : store.name;
    assert.ok(words.includes(wanted), `${wanted} in ${words}`);
  }
  assert.equal(words.length, buy.refs.length);
  // a stop that flies to a module names it; one without a target says nothing
  assert.deepEqual(said('tour', { preset: 'focus', ref: 'M5', caption: 'x' }), ['M5 Portfolio']);
  assert.deepEqual(said('tour', { preset: 'front', caption: 'x' }), []);
});

test('captions are the model’s words, arrows drawn as arrows', () => {
  const day = moments(MODEL);
  const review = day.find((m) => m.job.id === 'rl_daily_review');
  const said = captionOf('clock', review);
  assert.equal(said.lead, '16:30 · Monday to Friday');
  assert.equal(said.name, review.job.name);
  assert.ok(said.text.startsWith('grades the previous session'));
  const step = MODEL.traces[0].steps[0];
  assert.equal(captionOf('trace', step).lead, 'Saturday');
  assert.ok(!captionOf('trace', step).text.includes('─►'));
  assert.ok(captionOf('trace', step).text.includes('→'));
  assert.equal(captionOf('tour', MODEL.tours[0].steps[0]).text, MODEL.tours[0].steps[0].caption);
});

test('a manager who asked for nothing starts on the tour; anyone else gets what they asked', () => {
  const open = (hash, audience = 'manager') => openingPlay(MODEL, parseHash(hash, MODEL), audience);
  assert.deepEqual(open(''), { mode: 'tour', step: 0 });
  assert.deepEqual(open('#v=mgr'), { mode: 'tour', step: 0 });
  assert.equal(open('', 'developer'), null);
  assert.equal(open('#m=M5.2'), null);
  assert.equal(open('#m=M99'), null);
  assert.equal(open('#p=disco'), null);
  assert.deepEqual(open('#p=clock&s=4', 'developer'), { mode: 'clock', step: 3 });
  assert.equal(openingPlay({ ...MODEL, tours: [] }, parseHash('', MODEL), 'manager'), null);
});

test('the address holds the mode and the step, kept inside the steps', () => {
  const count = stepsOf(MODEL, 'tour').length;
  const at = (hash) => parseHash(hash, MODEL);
  assert.deepEqual(at('#p=tour&s=3').play, { mode: 'tour', step: 2 });
  for (const [s, step] of [['99', count - 1], ['0', 0], ['-4', 0], ['abc', 0], ['2.7', 1]]) {
    assert.equal(at(`#p=tour&s=${s}`).play.step, step, s);
  }
  assert.equal(at('#p=trace').play.step, 0);
  assert.equal(at('#p=clock&s=999').play.step, moments(MODEL).length - 1);
  // a mode wins over a part, and a mode the map does not have is named
  assert.equal(at('#p=tour&m=M5').id, null);
  assert.deepEqual([at('#p=disco').play, at('#p=disco').unknown], [null, 'p=disco']);
  // names every JavaScript object carries are no modes either
  for (const name of ['constructor', 'toString', '__proto__', 'hasOwnProperty', 'valueOf', '']) {
    assert.equal(at(`#p=${name}`).play, null, `#p=${name}`);
  }
  for (const play of [{ mode: 'clock', step: 5 }, { mode: 'trace', step: 0 }]) {
    const back = parseHash(formatHash({ id: null, audience: 'developer', play }), MODEL);
    assert.deepEqual([back.play, back.audience], [play, 'developer']);
  }
});

const flat = (a, b) => Math.hypot(a[0] - b[0], a[2] - b[2]);

test('the clock ring holds the whole product and runs like a clock', () => {
  const world = layoutWorld(MODEL);
  const ring = clockRing(world);
  for (const item of [...world.modules, ...world.stores]) {
    for (const [dx, dz] of [[-1, -1], [-1, 1], [1, -1], [1, 1]]) {
      const corner = [item.pos[0] + (dx * item.size[0]) / 2, 0,
        item.pos[2] + (dz * item.size[2]) / 2];
      assert.ok(flat(corner, ring.centre) < ring.radius - 1, `${item.id} inside the ring`);
    }
  }
  const [cx, , cz] = ring.centre;
  const at = (hour) => ringPoint(ring, hour * 60, 'daily');
  const near = (p, x, z) => Math.abs(p[0] - x) < 1e-6 && Math.abs(p[2] - z) < 1e-6;
  const r = ring.radius;
  assert.ok(near(at(0), cx, cz - r), '00:00 at the back');
  assert.ok(near(at(6), cx + r, cz), '06:00 to the right');
  assert.ok(near(at(12), cx, cz + r), '12:00 in front');
  assert.ok(near(at(18), cx - r, cz), '18:00 to the left');
  const radii = ['daily', 'weekly', 'calendar'].map((g) => flat(ringPoint(ring, 0, g), ring.centre));
  assert.ok(radii[0] < radii[1] && radii[1] < radii[2], 'daily inside weekly inside monthly');
  assert.deepEqual(Object.keys(TRACKS), ['daily', 'weekly', 'calendar']);
});

test('one bead per time, on its job’s ring, none touching another', () => {
  const ring = clockRing(layoutWorld(MODEL));
  const day = moments(MODEL);
  const placed = beads(ring, day);
  assert.equal(placed.length, day.length);
  const radius = (group) => flat(ringPoint(ring, 0, group), ring.centre);
  placed.forEach((bead, i) => {
    // its own time, as an angle: it stays on the ray of that time
    const [hours, minutes] = bead.time.split(':').map(Number);
    const angle = ((hours * 60 + minutes) / 1440) * Math.PI * 2;
    const bearing = Math.atan2(bead.pos[0] - ring.centre[0], ring.centre[2] - bead.pos[2]);
    assert.ok(Math.abs(Math.atan2(Math.sin(bearing - angle), Math.cos(bearing - angle))) < 1e-6,
      `${bead.key} at its time`);
    // on its track, or stepped outwards only to clear a bead placed before it
    const out = flat(bead.pos, ring.centre) - radius(bead.job.schedule.group);
    assert.ok(out > -1e-6 && out < 2.5, `${bead.key} on its ring (${out})`);
    if (out > 1e-6) {
      const onLine = ringPoint(ring, hours * 60 + minutes, bead.job.schedule.group);
      assert.ok(placed.slice(0, i).some((other) => flat(onLine, other.pos) < BEAD * 2.2),
        `${bead.key} left its line for nothing`);
    }
  });
  for (let i = 0; i < placed.length; i += 1) {
    for (let j = i + 1; j < placed.length; j += 1) {
      const gap = Math.hypot(...placed[i].pos.map((v, k) => v - placed[j].pos[k]));
      assert.ok(gap >= BEAD * 2, `${placed[i].key} and ${placed[j].key} touch (${gap})`);
    }
  }
});

test('the clock view frames the whole ring in any window', () => {
  const world = layoutWorld(MODEL);
  const ring = clockRing(world);
  const bounds = clockBounds(world, ring);
  const { dir, fov } = PRESETS.clock;
  const rim = Array.from({ length: 96 }, (_, i) => ringPoint(ring, i * 15, 'calendar'));
  for (const aspect of [0.7, 1, 1.6, 2.4]) {
    const camera = fitCamera(bounds, dir, fov, aspect);
    const reach = Math.max(...inside(camera, fov, aspect, rim));
    assert.ok(reach <= 1.0001, `ring cut off at ${aspect}`);
    assert.ok(reach > 0.55, `ring tiny at ${aspect}: ${reach}`);
  }
});

// -- the code galaxy (MAP-004) ---------------------------------------------------------

// Worked out here from the model's own words, so the viewer's helpers are not the proof.
const ballOf = (file) => (file.owner === 'shared' ? 'shared' : file.owner.split('.')[0]);
const fileAt = new Map(MODEL.files.map((f) => [f.path, f]));
const importersOf = (path) => MODEL.files.filter((f) => f.imports.includes(path)).map((f) => f.path);
const apart = (a, b) => Math.hypot(...a.map((v, i) => v - b[i]));
const GALAXY = layoutGalaxy(MODEL);
const ball = (id) => GALAXY.balls.find((b) => b.id === id);

test('the galaxy holds every file of the model once, each in its module’s ball', () => {
  assert.deepEqual(GALAXY.nodes.map((n) => n.path).sort(), MODEL.files.map((f) => f.path).sort());
  for (const node of GALAXY.nodes) assert.equal(node.cluster, ballOf(fileAt.get(node.path)), node.path);
  const wanted = new Map();
  for (const f of MODEL.files) wanted.set(ballOf(f), (wanted.get(ballOf(f)) ?? 0) + 1);
  assert.deepEqual(new Map(GALAXY.balls.map((b) => [b.id, b.count])), wanted);
  // one line for each import between two files of the model
  const imports = MODEL.files.flatMap((f) => f.imports
    .filter((to) => to !== f.path && fileAt.has(to)).map((to) => `${f.path}>${to}`));
  assert.deepEqual(GALAXY.graph.edges.map((e) => `${e.from}>${e.to}`).sort(), imports.sort());
  for (const f of GALAXY.graph.files) {
    assert.deepEqual(f.importedBy, importersOf(f.path).filter((p) => p !== f.path).sort(), f.path);
  }
});

test('the same model gives the same galaxy, in whatever order it lists the files', () => {
  const shuffled = structuredClone(MODEL);
  shuffled.files.reverse();
  for (const f of shuffled.files) f.imports.reverse();
  const again = layoutGalaxy(shuffled);
  assert.deepEqual(again.nodes, GALAXY.nodes);
  assert.deepEqual(again.balls, GALAXY.balls);
});

test('balls touch nothing, every dot stays in its own ball, and no two dots overlap', () => {
  for (let i = 0; i < GALAXY.balls.length; i += 1) {
    for (let j = i + 1; j < GALAXY.balls.length; j += 1) {
      const [a, b] = [GALAXY.balls[i], GALAXY.balls[j]];
      assert.ok(apart(a.centre, b.centre) > a.radius + b.radius, `${a.id} and ${b.id} touch`);
    }
  }
  for (const node of GALAXY.nodes) {
    const own = ball(node.cluster);
    assert.ok(apart(node.pos, own.centre) + node.radius <= own.radius + 1e-6, `${node.path} outside`);
    // so each module's files gather: a file is nearer its own ball than any other
    for (const other of GALAXY.balls.filter((b) => b !== own)) {
      assert.ok(apart(node.pos, own.centre) < apart(node.pos, other.centre), node.path);
    }
  }
  for (let i = 0; i < GALAXY.nodes.length; i += 1) {
    for (let j = i + 1; j < GALAXY.nodes.length; j += 1) {
      const [a, b] = [GALAXY.nodes[i], GALAXY.nodes[j]];
      assert.ok(apart(a.pos, b.pos) >= a.radius + b.radius, `${a.path} overlaps ${b.path}`);
    }
  }
});

test('balls keep the world’s order: columns left to right, planes top to bottom', () => {
  const flat = MODEL.modules.filter((m) => m.plane !== 'ring' && ball(m.id));
  for (const a of flat) {
    for (const b of flat) {
      if (a.column < b.column) {
        assert.ok(ball(a.id).centre[0] < ball(b.id).centre[0], `${a.id} left of ${b.id}`);
      }
    }
  }
  const height = (plane) => flat.filter((m) => m.plane === plane).map((m) => ball(m.id).centre[1]);
  assert.ok(Math.min(...height('top')) > Math.max(...height('middle')));
  assert.ok(Math.min(...height('middle')) > Math.max(...height('base')));
  assert.ok(ball('shared').centre[1] < Math.min(...height('base')));
});

test('a dot’s area grows with its file’s lines, and the smallest can still be seen', () => {
  const size = new Map(GALAXY.nodes.map((n) => [n.path, n.radius]));
  const byLines = [...MODEL.files].sort((a, b) => a.lines - b.lines);
  for (let i = 1; i < byLines.length; i += 1) {
    assert.ok(size.get(byLines[i - 1].path) <= size.get(byLines[i].path), byLines[i].path);
  }
  assert.ok(size.get(byLines[0].path) > 0.2, 'an empty file has a dot');
  const [mid, big] = [byLines.at(-30), byLines.at(-1)];
  const ratio = (size.get(big.path) / size.get(mid.path)) ** 2;
  assert.ok(Math.abs(ratio - big.lines / mid.lines) < 0.01, 'area in proportion to lines');
});

test('a file many modules import is a bridge on the side that faces them', () => {
  const users = (f) => new Set(importersOf(f.path).map((p) => ballOf(fileAt.get(p)))
    .filter((id) => id !== ballOf(f) && id !== 'shared'));
  const bridges = MODEL.files.filter((f) => users(f).size >= BRIDGE_MODULES);
  assert.ok(bridges.length >= 3, 'the model has files imported across many modules');
  assert.deepEqual([...GALAXY.bridges].sort(), bridges.map((f) => f.path).sort());
  // “other modules” for every file: not its own
  for (const f of MODEL.files) {
    assert.deepEqual(importingModules(GALAXY.graph, f.path), [...users(f)]
      .sort((a, b) => Number(a.slice(1)) - Number(b.slice(1))), f.path);
  }
  // and the shared files are no module, even when one of them imports it
  const probed = 'core/portfolio/advisor.py';
  const odd = structuredClone(MODEL);
  odd.files.push({ path: 'scripts/zz_probe.py', lines: 1, owner: 'shared', imports: [probed] });
  assert.deepEqual(importingModules(codeGraph(odd), probed),
    importingModules(GALAXY.graph, probed));
  for (const f of bridges) {
    const own = ball(ballOf(f));
    const out = GALAXY.byPath.get(f.path).pos.map((v, i) => v - own.centre[i]);
    const centres = importersOf(f.path).map((p) => ballOf(fileAt.get(p)))
      .filter((id) => id !== own.id).map((id) => ball(id).centre);
    const towards = [0, 1, 2].map(
      (i) => centres.reduce((sum, c) => sum + c[i], 0) / centres.length - own.centre[i]);
    const cos = out.reduce((s, v, i) => s + v * towards[i], 0)
      / (Math.hypot(...out) * Math.hypot(...towards));
    assert.ok(cos > 0.8, `${f.path} faces away from its users (${cos.toFixed(2)})`);
    assert.ok(Math.hypot(...out) > own.radius * 0.5, `${f.path} is not at its ball's side`);
  }
});

test('a choice lights its files: a module, a part, the shared files or one file', () => {
  const graph = codeGraph(MODEL);
  const lit = (choice) => [...(galaxyLights(graph, choice)?.files ?? [])].sort();
  const owned = (test_) => MODEL.files.filter((f) => test_(f.owner)).map((f) => f.path).sort();
  assert.equal(galaxyLights(graph, { selected: null, file: null }), null);
  assert.deepEqual(lit({ selected: 'M5' }), owned((o) => o === 'M5' || o.startsWith('M5.')));
  // M1 is not M10, M11 or M12
  assert.deepEqual(lit({ selected: 'M1' }), owned((o) => o === 'M1' || o.startsWith('M1.')));
  assert.deepEqual(lit({ selected: 'M5.2' }), owned((o) => o === 'M5.2'));
  assert.deepEqual(lit({ selected: 'shared' }), owned((o) => o === 'shared'));
  const file = 'core/portfolio/advisor.py';
  const wanted = [...new Set([file, ...fileAt.get(file).imports, ...importersOf(file)])].sort();
  const chosen = galaxyLights(graph, { selected: 'M5.2', file });
  assert.deepEqual([...chosen.files].sort(), wanted, 'a file wins over its part');
  assert.equal(chosen.file, file);
  // a part without a Python file dims nothing
  const bare = MODEL.modules.flatMap((m) => m.submodules).find((s) => !s.python_files.length);
  if (bare) assert.equal(galaxyLights(graph, { selected: bare.id }), null);
  assert.equal(pickOf(graph, file), fileAt.get(file).owner);
  assert.equal(pickOf(graph, 'no/such.py'), null);
});

test('an import’s line says whether it lies inside the lit files or bridges out of them', () => {
  const graph = codeGraph(MODEL);
  const within = (e) => ballOf(fileAt.get(e.from)) === ballOf(fileAt.get(e.to));
  for (const edge of graph.edges) {
    assert.equal(edgeState(graph, null, edge), within(edge) ? 'near' : 'far');
  }
  const m5 = galaxyLights(graph, { selected: 'M5' });
  const inM5 = (p) => ballOf(fileAt.get(p)) === 'M5';
  const seen = new Set();
  for (const edge of graph.edges) {
    const ends = Number(inM5(edge.from)) + Number(inM5(edge.to));
    assert.equal(edgeState(graph, m5, edge), ['faded', 'bridge', 'inside'][ends]);
    seen.add(ends);
  }
  assert.equal(seen.size, 3);
  const file = 'core/portfolio/advisor.py';
  const one = galaxyLights(graph, { file });
  for (const edge of graph.edges) {
    const own = edge.from === file || edge.to === file;
    assert.equal(edgeState(graph, one, edge), own ? 'own' : 'faded');
  }
});

test('the code panel counts its files, lines and what crosses its border', () => {
  const graph = codeGraph(MODEL);
  for (const id of ['M5', 'M5.2', 'shared']) {
    const mine = MODEL.files.filter((f) => (id.includes('.') || id === 'shared'
      ? f.owner === id : ballOf(f) === id));
    const paths = new Set(mine.map((f) => f.path));
    const got = codeSummary(graph, id);
    assert.deepEqual(got.files.map((f) => f.path).sort(), [...paths].sort(), id);
    assert.equal(got.lines, mine.reduce((s, f) => s + f.lines, 0), id);
    for (let i = 1; i < got.files.length; i += 1) {
      assert.ok(got.files[i - 1].lines >= got.files[i].lines, `${id}: largest first`);
    }
    const count = (pairs) => {
      const by = {};
      for (const other of pairs) {
        if (!paths.has(other)) by[ballOf(fileAt.get(other))] = (by[ballOf(fileAt.get(other))] ?? 0) + 1;
      }
      return by;
    };
    assert.deepEqual(Object.fromEntries(got.imports), count(mine.flatMap((f) => f.imports)), id);
    assert.deepEqual(Object.fromEntries(got.importedBy),
      count(mine.flatMap((f) => importersOf(f.path))), id);
  }
});

test('the galaxy’s address holds a part, the shared files or a file, and refuses the rest', () => {
  const none = { id: null, audience: null, play: null, unknown: null, code: true, file: null };
  assert.deepEqual(parseHash('#g', MODEL), none);
  assert.deepEqual(parseHash('#g&m=M5.2&v=dev', MODEL),
    { ...none, id: 'M5.2', audience: 'developer' });
  assert.deepEqual(parseHash('#g&m=shared', MODEL), { ...none, id: 'shared' });
  assert.deepEqual(parseHash('#g&f=core/portfolio/advisor.py', MODEL),
    { ...none, file: 'core/portfolio/advisor.py' });
  assert.deepEqual(parseHash('#g&m=M2&f=core/portfolio/advisor.py', MODEL),
    { ...none, file: 'core/portfolio/advisor.py' }, 'a file wins over a part');
  for (const bad of ['core/nothing.py', 'constructor', '<img src=x>']) {
    const got = parseHash(`#g&f=${encodeURIComponent(bad)}`, MODEL);
    assert.deepEqual([got.code, got.file, got.unknown], [true, null, bad]);
  }
  assert.deepEqual(parseHash('#g&m=M99', MODEL), { ...none, unknown: 'M99' });
  // the world has no shared part
  assert.equal(parseHash('#m=shared', MODEL).unknown, 'shared');
  assert.equal(formatHash({ code: true, file: 'core/portfolio/advisor.py', id: 'M5.2',
    audience: 'developer' }), '#g&f=core/portfolio/advisor.py&v=dev');
  assert.equal(formatHash({ code: true, audience: 'developer' }), '#g&v=dev');
  for (const state of [{ id: 'M3', file: null }, { id: 'shared', file: null },
    { id: null, file: 'services/api/server.py' }]) {
    const back = parseHash(formatHash({ ...state, code: true, audience: 'developer' }), MODEL);
    assert.deepEqual([back.id, back.file, back.code], [state.id, state.file, true]);
  }
  // a path with characters an address would read otherwise survives the round trip
  const odd = { ...MODEL, files: [...MODEL.files, { path: 'core/a&b #1.py', lines: 1,
    owner: 'shared', imports: [] }] };
  assert.equal(parseHash(formatHash({ code: true, file: 'core/a&b #1.py' }), odd).file,
    'core/a&b #1.py');
  // an address into the galaxy starts no tour
  assert.equal(openingPlay(MODEL, parseHash('#g', MODEL), 'manager'), null);
});

test('search finds every Python file by its name, the exact name first', () => {
  const index = searchIndex(MODEL);
  for (const f of MODEL.files) {
    const hits = search(index, f.path, 50).filter((r) => r.kind === 'file' && r.file === f.path);
    assert.equal(hits.length, 1, f.path);
  }
  const first = search(index, 'advisor.py')[0];
  assert.deepEqual([first.kind, first.file], ['file', 'core/portfolio/advisor.py']);
  const shared = MODEL.files.find((f) => f.owner === 'shared');
  assert.equal(search(index, shared.path)[0].id, 'shared');
  // a function that lives in a Python file can open it
  const fn = search(index, 'assess_analysis').find((r) => r.kind === 'function');
  assert.ok(fileAt.has(fn.file));
});

test('pointing finds the dot under the cursor, the nearer one first, within a 24 px target', () => {
  const dot = (path, x, radius, depth) => ({ path, x, y: 100, radius, depth });
  const dots = [dot('far', 100, 20, 50), dot('near', 110, 15, 20), dot('small', 200, 2, 10),
    dot('other', 218, 2, 10)];
  const at = (x, y = 100) => dotAt(dots, x, y)?.path ?? null;
  assert.equal(at(105), 'near', 'both discs hold it: the nearer to the viewer');
  assert.equal(at(82), 'far', 'only the far disc holds it');
  assert.equal(at(190), 'small', '10 px from a 2 px dot is still on its target');
  assert.equal(at(212), 'other', 'between two small dots, the closer');
  assert.equal(at(200, 111), 'small');
  assert.equal(at(200, 113), null, 'beyond 12 px, nothing');
  assert.equal(at(160), null);
});

test('the galaxy names every ball, its bridges, and the files a choice is about', () => {
  const items = (choice) => galaxyLabels(MODEL, GALAXY, choice);
  const files = (list) => list.filter((i) => i.kind === 'file');
  const rest = items({ selected: null, file: null });
  assert.deepEqual(rest.filter((i) => i.kind === 'module').map((i) => i.select).sort(),
    GALAXY.balls.map((b) => b.id).sort());
  assert.deepEqual(files(rest).map((i) => i.file).sort(), [...GALAXY.bridges].sort());
  assert.ok(rest.every((i) => i.state === 'rest' && !i.hidden));
  assert.equal(new Set(rest.map((i) => i.key)).size, rest.length, 'one element for each name');
  const m5 = items({ selected: 'M5', file: null });
  assert.equal(m5.find((i) => i.select === 'M5').state, 'selected');
  assert.equal(m5.find((i) => i.select === 'M2').state, 'faded');
  const largest = MODEL.files.filter((f) => ballOf(f) === 'M5').sort((a, b) => b.lines - a.lines);
  for (const f of largest.slice(0, 6)) assert.ok(m5.some((i) => i.file === f.path), f.path);
  assert.ok(!m5.some((i) => i.file === largest[8].path));
  // names of files that are not lit are not shown
  assert.ok(files(m5).every((i) => ballOf(fileAt.get(i.file)) === 'M5'));
  const file = 'core/portfolio/advisor.py';
  const one = items({ selected: 'M5.2', file });
  const chosen = one.find((i) => i.file === file);
  assert.equal(chosen.state, 'selected');
  assert.ok(chosen.priority < Math.min(...one.filter((i) => i !== chosen).map((i) => i.priority)));
  const near = new Set([...fileAt.get(file).imports, ...importersOf(file)]);
  assert.ok(files(one).every((i) => i.file === file || near.has(i.file)));
  // the chosen file and six neighbours at most, even where many neighbours are bridges
  assert.equal(files(one).length, 1 + Math.min(6, near.size));
  const hub = 'core/config/settings/__init__.py';
  assert.equal(files(items({ selected: pickOf(GALAXY.graph, hub), file: hub })).length, 7);
  assert.equal(fileLabel('core/config/settings/__init__.py'), 'settings/__init__.py');
  assert.equal(fileLabel(file), 'advisor.py');
});

test('every view of the galaxy holds every dot, in any window, without wasting it', () => {
  const corners = GALAXY.nodes.flatMap((n) => [-1, 1].flatMap((x) => [-1, 1].flatMap((y) => [-1, 1]
    .map((z) => [n.pos[0] + x * n.radius, n.pos[1] + y * n.radius, n.pos[2] + z * n.radius]))));
  for (const [name, preset] of Object.entries(PRESETS).filter(([id]) => id !== 'clock')) {
    for (const aspect of [0.7, 1, 1.6, 2.4]) {
      const dir = name === 'front' ? FRONT : preset.dir;
      const camera = fitCamera(GALAXY.bounds, dir, preset.fov, aspect, MARGIN);
      const reach = Math.max(...inside(camera, preset.fov, aspect, corners));
      assert.ok(reach <= 0.9, `${name} at ${aspect} leaves no room round the galaxy (${reach})`);
      assert.ok(reach > 0.6, `${name} at ${aspect} leaves it tiny (${reach})`);
    }
  }
});

// -- the look ---------------------------------------------------------------------------

const DESIGN = read('docs', 'architecture-map', 'DESIGN.md');
const rows = new Map([...DESIGN.matchAll(/^\| (\S+) \| `(#[0-9a-f]{6})` \|/gm)]
  .map((m) => [m[1], m[2]]));

test('DESIGN.md and the code state the same colours', () => {
  const code = { ...SURFACE, ...PLANE, ...MODULE };
  assert.deepEqual(Object.fromEntries([...rows].sort()),
    Object.fromEntries(Object.entries(code).sort()));
  for (const m of MODEL.modules) assert.ok(MODULE[m.id], `${m.id} has a colour in DESIGN.md`);
  const css = read('tools', 'architecture_map', 'viewer', 'src', 'styles.css');
  for (const [name, value] of Object.entries(SURFACE)) {
    assert.ok(css.includes(`--${name}: ${value};`), `styles.css --${name}`);
  }
});

function luminance(hex) {
  const [r, g, b] = [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16) / 255)
    .map((c) => (c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4));
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}
const contrast = (a, b) => {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x);
  return (hi + 0.05) / (lo + 0.05);
};

test('text is readable and meaningful lines can be seen', () => {
  assert.ok(Math.abs(contrast('#000000', '#ffffff') - 21) < 0.01);
  for (const surface of ['bg', 'panel', 'raised', 'node']) {
    for (const ink of ['ink', 'ink2', 'muted', 'link', 'yes']) {
      assert.ok(contrast(SURFACE[ink], SURFACE[surface]) >= 4.5, `${ink} on ${surface}`);
    }
    for (const mark of ['edge', 'focus']) {
      assert.ok(contrast(SURFACE[mark], SURFACE[surface]) >= 3, `${mark} on ${surface}`);
    }
  }
  for (const [id, colour] of Object.entries(MODULE)) {
    for (const surface of ['bg', 'panel', 'node']) {
      assert.ok(contrast(colour, SURFACE[surface]) >= 3, `${id} on ${surface}`);
    }
  }
});

// -- every module’s logic (MAP-005) ------------------------------------------------------

// The parts that are lists of things, not an order of events or a choice.
const LISTS = ['M1.4', 'M1.5', 'M2.4', 'M5.7', 'M10.1', 'M10.3', 'M11.3', 'M11.4', 'M12.3', 'M12.5'];

test('every part that is a process is drawn with an order or a decision', () => {
  const every = MODEL.modules.flatMap((m) => m.submodules.map((s) => s.id));
  const plain = every.filter((id) => !buildFlow(logicOf(id))
    .some((g) => g.sequential || g.nodes.some((n) => n.kind === 'decision')));
  assert.deepEqual(plain.sort(), [...LISTS].sort());
});

test('the regime chart tries each label in the detector’s order and ends in one', () => {
  inOrder(along('M4.5', 'VIX > 22 and FII'), ['VIX > 22 and FII', 'else VIX > 22', 'VIX < 14',
    'VIX < 22', 'RSI < 30', 'NORMAL'], 'M4.5');
  const [g] = buildFlow(logicOf('M4.5'));
  assert.equal(edge(g, 'VIX > 22 and FII', 'MACRO_CRISIS').label, 'yes');
});

test('the sign-in chart answers a token first, then the switch, then refuses', () => {
  inOrder(along('M10.2', 'valid bearer token'), ['valid bearer token', 'invalid or expired',
    'auth.required off', 'else 401'], 'M10.2');
});

test('the watchdog chart climbs its ladder in the engine’s order', () => {
  inOrder(along('M12.1', 'satisfied'), ['satisfied', 'unknown', 'past its deadline',
    'window open', 'window near', 'silent'], 'M12.1');
});

test('no job’s name on the map ends in an old plan’s code', () => {
  assert.deepEqual(MODEL.jobs.map((j) => j.name).filter((n) => /\((M|BP|P)\d/.test(n)), []);
});

// -- the flat map (MAP-005) --------------------------------------------------------------

const GRAPH = codeGraph(MODEL);
const WORLD = layoutWorld(MODEL);
const WIDE = flatLayout(MODEL, WORLD);
const NARROW = flatLayout(MODEL, WORLD, { narrow: true });
const cardsOf = (layout) => new Map(layout.cards.map((c) => [c.id, c]));
const cardsApart = (layout, what) => {
  const { cards } = layout;
  for (let i = 0; i < cards.length; i += 1) {
    const a = cards[i];
    assert.ok(a.x >= 0 && a.y >= 0 && a.x + a.w <= layout.width && a.y + a.h <= layout.height,
      `${what}: ${a.id} is inside the drawing`);
    for (const b of cards.slice(i + 1)) {
      assert.ok(a.x + a.w <= b.x || b.x + b.w <= a.x || a.y + a.h <= b.y || b.y + b.h <= a.y,
        `${what}: ${a.id} overlaps ${b.id}`);
    }
  }
};
const lowest = (layout, ids) => Math.max(...ids.map((id) => cardsOf(layout).get(id).y));
const highest = (layout, ids) => Math.min(...ids.map((id) => cardsOf(layout).get(id).y));
const inPlane = (plane) => MODEL.modules.filter((m) => m.plane === plane).map((m) => m.id);

test('the flat map has one card for every module, outside party and store, apart', () => {
  for (const [layout, what] of [[WIDE, 'wide'], [NARROW, 'narrow']]) {
    const wanted = [...MODEL.modules, ...MODEL.externals, ...MODEL.stores].map((x) => x.id);
    assert.deepEqual(layout.cards.map((c) => c.id).sort(), wanted.sort(), what);
    cardsApart(layout, what);
  }
  assert.equal(NARROW.width, 360, 'a narrow map is a phone wide');
  const widths = (layout, ids) => new Set(ids.map((id) => cardsOf(layout).get(id).x)).size;
  assert.equal(widths(NARROW, MODEL.modules.map((m) => m.id)), 2, 'modules two abreast');
  assert.equal(widths(NARROW, MODEL.stores.map((s) => s.id)), 3, 'stores three abreast');
});

test('on the flat map the planes run top to bottom and columns left to right', () => {
  const stores = MODEL.stores.map((s) => s.id);
  const wide = [inPlane('top'), inPlane('middle'), inPlane('base'), stores];
  const narrow = [inPlane('top'), inPlane('middle'), inPlane('base'), inPlane('ring'), stores];
  for (const [layout, order] of [[WIDE, wide], [NARROW, narrow]]) {
    for (let i = 1; i < order.length; i += 1) {
      assert.ok(lowest(layout, order[i - 1]) < highest(layout, order[i]), `band ${i}`);
    }
  }
  const at = cardsOf(WIDE);
  const modules = MODEL.modules.filter((m) => m.plane !== 'ring');
  for (const a of modules) {
    for (const b of modules.filter((x) => x.plane === a.plane && x.column > a.column)) {
      assert.ok(at.get(a.id).x < at.get(b.id).x, `${a.id} stands left of ${b.id}`);
    }
  }
  // the watchers stand beside the product, to its right, inside one frame
  const frame = WIDE.bands.find((b) => b.frame);
  for (const id of inPlane('ring')) {
    const card = at.get(id);
    assert.ok(inPlane('middle').every((m) => at.get(m).x < card.x), `${id} is to the right`);
    assert.ok(card.x >= frame.x && card.x + card.w <= frame.x + frame.w
      && card.y >= frame.y && card.y + card.h <= frame.y + frame.h, `${id} is framed`);
  }
});

// How far a point is from a card's outline.
const offEdge = ([x, y], c) => {
  const inX = x >= c.x - 0.1 && x <= c.x + c.w + 0.1;
  const inY = y >= c.y - 0.1 && y <= c.y + c.h + 0.1;
  const sides = [inY ? Math.abs(x - c.x) : Infinity, inY ? Math.abs(x - c.x - c.w) : Infinity,
    inX ? Math.abs(y - c.y) : Infinity, inX ? Math.abs(y - c.y - c.h) : Infinity];
  return Math.min(...sides);
};

test('every flow is one arrow from its source card to its target card; every writer a line', () => {
  for (const layout of [WIDE, NARROW]) {
    const at = cardsOf(layout);
    assert.deepEqual(layout.arrows.map((a) => a.key).sort(),
      MODEL.flows.map((f) => `${f.from}>${f.to}`).sort());
    for (const arrow of layout.arrows) {
      const flow = MODEL.flows.find((f) => `${f.from}>${f.to}` === arrow.key);
      assert.equal(arrow.what, flow.what);
      assert.ok(offEdge(arrow.start, at.get(flow.from)) < 0.2, `${arrow.key} leaves its source`);
      assert.ok(offEdge(arrow.end, at.get(flow.to)) < 0.2, `${arrow.key} reaches its target`);
      assert.match(arrow.d, /^M[\d.]+,[\d.]+ C/, arrow.key);
    }
    const writers = new Set(MODEL.stores.flatMap((s) => s.writers
      .map((w) => `${w.split('.')[0]}>${s.id}`)));
    assert.deepEqual(layout.pipes.map((p) => `${p.module}>${p.store}`).sort(), [...writers].sort());
  }
});

const statesOf = (options) => flatStates(MODEL, WIDE, options);
const choose = (id) => statesOf({ shown: id, touched: related(MODEL, id) });

test('on the flat map a choice lights what it touches and fades the rest', () => {
  const rest = statesOf({});
  assert.ok([...rest.cards.values()].every((s) => s === 'rest'));
  assert.ok([...rest.arrows.values()].every((s) => s === 'rest'));
  assert.ok([...rest.pipes.values()].every((s) => s === 'off'));
  const { cards, arrows, pipes } = choose('M5.2');
  const near = new Set(MODEL.flows.filter((f) => [f.from, f.to].includes('M5'))
    .flatMap((f) => [f.from, f.to]));
  for (const m of MODEL.modules) {
    assert.equal(cards.get(m.id), m.id === 'M5' ? 'selected' : near.has(m.id) ? 'rest' : 'faded',
      m.id);
  }
  for (const f of MODEL.flows) {
    assert.equal(arrows.get(`${f.from}>${f.to}`),
      [f.from, f.to].includes('M5') ? 'bright' : 'faded', `${f.from}>${f.to}`);
  }
  // M5.2 reads and writes few stores: those stand out, its module's own lines only
  const mine = new Set(MODEL.stores.filter((s) => [...s.writers, ...s.readers].includes('M5.2'))
    .map((s) => s.id));
  assert.ok(mine.size > 0);
  for (const s of MODEL.stores) {
    assert.equal(cards.get(s.id), mine.has(s.id) ? 'near' : 'faded', s.id);
  }
  for (const [key, level] of pipes) {
    const [module, store] = key.split('>');
    assert.equal(level, module === 'M5' && mine.has(store) ? 'bright' : 'off', key);
  }
});

test('on the flat map a playing step lights only what it names', () => {
  const job = MODEL.jobs.find((j) => j.id === 'rl_daily_review');
  const lit = jobLights(job);
  const { cards, arrows, pipes } = statesOf({ lit, preset: 'clock' });
  const named = new Set(job.lights.map((id) => (id.startsWith('M') ? id.split('.')[0] : id)));
  for (const [id, state] of cards) assert.equal(state, named.has(id) ? 'lit' : 'faded', id);
  const running = new Set(job.flows);
  for (const [key, level] of arrows) assert.equal(level, running.has(key) ? 'bright' : 'faded', key);
  for (const [key, level] of pipes) {
    const [module, store] = key.split('>');
    assert.equal(level, named.has(module) && named.has(store) ? 'bright' : 'off', key);
  }
});

test('the four views change what stands out on the flat map, not where it stands', () => {
  const view = (preset) => statesOf({ preset });
  assert.ok([...view('below').arrows.values()].every((s) => s === 'dim'));
  assert.ok([...view('below').pipes.values()].every((s) => s === 'show'));
  assert.ok(MODEL.stores.every((s) => view('below').cards.get(s.id) === 'near'));
  assert.ok([...view('side').arrows.values()].every((s) => s === 'dim'));
  assert.ok(MODEL.stores.every((s) => view('top').cards.get(s.id) === 'faded'));
  assert.ok(MODEL.modules.every((m) => view('top').cards.get(m.id) === 'rest'));
});

test('the flat galaxy shows each module’s files and the shared ones, and no flows', () => {
  for (const narrow of [false, true]) {
    const layout = flatLayout(MODEL, WORLD, { narrow, code: GRAPH });
    assert.deepEqual(layout.cards.map((c) => c.id).sort(),
      [...MODEL.modules.map((m) => m.id), 'shared'].sort());
    assert.equal(layout.arrows.length + layout.pipes.length, 0);
    cardsApart(layout, 'code');
    for (const card of layout.cards) {
      const files = MODEL.files.filter((f) => f.owner.split('.')[0] === card.id).length;
      assert.equal(card.lines.at(-1), `${files} file${files === 1 ? '' : 's'}`, card.id);
    }
    const states = flatCodeStates(layout, 'M5.2').cards;
    assert.equal(states.get('M5'), 'selected');
    assert.equal(states.get('shared'), 'faded');
    assert.equal(flatCodeStates(layout, 'shared').cards.get('shared'), 'selected');
    assert.ok([...flatCodeStates(layout, null).cards.values()].every((s) => s === 'rest'));
  }
});

test('a card’s words wrap within its lines, and say so when they do not fit', () => {
  assert.deepEqual(wrapWords('Value history, digests and results', 14),
    ['Value history,', 'digests and', 'results']);
  assert.deepEqual(wrapWords('one two three four five six', 9, 2), ['one two', 'three…']);
  assert.deepEqual(wrapWords('averyveryverylongword x', 8), ['averyveryverylongword', 'x']);
  for (const layout of [WIDE, NARROW]) {
    for (const store of MODEL.stores) {
      const card = cardsOf(layout).get(store.id);
      // whole, in at most three lines: the browser test measures that they fit
      assert.equal(card.lines.join(' '), store.name, `${store.id} shows its whole name`);
      assert.ok(card.lines.length <= 3, store.id);
    }
  }
});

test('a card says what it is to those who cannot see it', () => {
  const at = cardsOf(WIDE);
  const m5 = MODEL.modules.find((m) => m.id === 'M5');
  assert.equal(cardLabel(MODEL, at.get('M5')), `M5 Portfolio: ${m5.summary}`);
  assert.match(cardLabel(MODEL, at.get('S.cases')), /^Store Investment cases: opens the part/);
  assert.equal(cardLabel(MODEL, at.get('ext.owner')), 'The owner');
});

// -- the committed page ------------------------------------------------------------------

const PAGE = read('docs', 'architecture-map', 'index.html');

test('the committed page was built from the committed viewer', () => {
  const stated = /<meta name="viewer-source" content="(sha256:[0-9a-f]{64})"/.exec(PAGE)?.[1];
  assert.equal(stated, sourceHash(path.join(REPO, 'tools', 'architecture_map', 'viewer')),
    'rebuild it: cd tools/architecture_map/viewer && npm ci && npm run build');
});

const embedded = () => JSON.parse(
  /<script type="application\/json" id="model">([\s\S]*?)<\/script>/.exec(PAGE)?.[1]);

// What the page says that a person wrote, or that a setting or the clock states. File
// lists, line counts, routes and the commit stamp are left to the next rebuild.
const meaning = (m) => ({
  product: m.product, externals: m.externals, flows: m.flows, stores: m.stores, jobs: m.jobs,
  switches: m.switches, production: m.production, traces: m.traces, tours: m.tours,
  modules: m.modules.map(({ python_files: _f, submodules, ...module }) => ({
    ...module, submodules: submodules.map(({ python_files: _p, ...part }) => part) })),
});

test('the page shows the model as it is now', () => {
  assert.deepEqual(meaning(embedded()), meaning(MODEL),
    'rebuild it: cd tools/architecture_map/viewer && npm ci && npm run build');
});

test('the committed page is one file that asks for nothing', () => {
  assert.ok(!/<script[^>]*\ssrc=/i.test(PAGE), 'no outside script');
  assert.ok(!/<link[^>]*\shref=/i.test(PAGE), 'no outside stylesheet');
  assert.match(PAGE, /connect-src 'none'/);
  const model = embedded();
  assert.equal(model.schema, 1);
  assert.match(model.stamp.commit, /^[0-9a-f]{40}$/);
  assert.equal(model.modules.length >= 12, true);
});

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
  findPart, formatHash, parseHash, related, search, searchIndex, settingsFor,
} from '../../tools/architecture_map/viewer/src/lib/select.js';
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

test('the four views look from four different sides', () => {
  const world = layoutWorld(MODEL);
  const at = Object.values(PRESETS).map((p) => fitCamera(world.bounds, p.dir, p.fov, 1.6).position);
  assert.deepEqual(Object.values(PRESETS).map((p) => p.key), ['1', '2', '3', '4']);
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
  assert.deepEqual(parseHash('#m=M5.2&v=dev', MODEL),
    { id: 'M5.2', audience: 'developer', unknown: null });
  assert.deepEqual(parseHash('#m=M5', MODEL), { id: 'M5', audience: null, unknown: null });
  assert.deepEqual(parseHash('', MODEL), { id: null, audience: null, unknown: null });
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
  switches: m.switches, production: m.production,
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

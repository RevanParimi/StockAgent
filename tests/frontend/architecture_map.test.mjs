/**
 * MAP-002: the committed architecture map in a real browser, opened from disk with the
 * network off and software WebGL, as someone double-clicking the file would.
 *
 *   node --test tests/frontend/architecture_map.test.mjs
 *
 * Every page records its console errors and every request it makes; a test that leaves
 * either behind fails. What is on the map is read from the model inside the page, so a
 * regenerated model needs no change here.
 */
import { test, before, after } from 'node:test';
import assert from 'node:assert/strict';
import path from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { chromium } from 'playwright';

import {
  PRESETS, curvePoint, fitCamera, layoutWorld,
} from '../../tools/architecture_map/viewer/src/lib/world.js';
import {
  beads, clockBounds, clockRing, moments,
} from '../../tools/architecture_map/viewer/src/lib/play.js';

const REPO = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..', '..');
const PAGE = pathToFileURL(path.join(REPO, 'docs', 'architecture-map', 'index.html')).href;
const MONEY_PATH = ['M3.1', 'M3.2', 'M3.3', 'M3.4', 'M3.5', 'M4.2', 'M5.2', 'M5.3',
  'M6.1', 'M6.2', 'M6.3', 'M6.4', 'M6.5'];
const SLOW = { timeout: 180_000 };

let browser;
before(async () => {
  browser = await chromium.launch({
    args: ['--use-angle=swiftshader', '--enable-unsafe-swiftshader', '--ignore-gpu-blocklist'],
  });
});
after(async () => { await browser?.close(); });

/** A page on the map, and what went wrong on it. Reduced motion unless a test says. A
 *  page opened with no address starts on the guided tour; unless a test wants it, Esc
 *  leaves it first and the test begins on the map. A test that opens several pages in
 *  turn calls `close` on each: drawn in software, every open one holds much memory. */
async function open(t, { hash = '', motion = false, size = [1280, 800], tour = false } = {}) {
  const context = await browser.newContext({
    viewport: { width: size[0], height: size[1] }, offline: true,
    reducedMotion: motion ? 'no-preference' : 'reduce',
  });
  const page = await context.newPage();
  const wrong = [];
  const asked = [];
  page.on('console', (m) => { if (m.type() === 'error') wrong.push(m.text().slice(0, 500)); });
  page.on('pageerror', (e) => wrong.push(`page error: ${e.message}`));
  page.on('request', (r) => asked.push(r.url()));
  t.after(async () => { await context.close(); });
  await page.goto(PAGE + hash);
  await page.waitForSelector('[data-app][data-ready="true"]', { timeout: 90_000 });
  if (!hash && !tour) {
    await page.keyboard.press('Escape');
    await page.waitForSelector('[data-app][data-mode=""]');
    await page.waitForTimeout(300);
    await still(page);
  }
  const clean = () => {
    assert.deepEqual(wrong, [], 'console errors');
    assert.deepEqual(asked.filter((u) => u.split('#')[0] !== PAGE), [],
      'the page asks for nothing but itself');
  };
  return { page, clean, close: () => context.close() };
}

const data = (page, name) => page.getAttribute('[data-app]', `data-${name}`);
const model = (page) => page.evaluate(() => JSON.parse(document.getElementById('model').textContent));
const still = (page) => page.waitForFunction(
  () => document.querySelector('[data-app]').dataset.moving === 'false', null, { timeout: 60_000 });
async function settled(page, since) {
  // the camera has left where it was and stopped
  await page.waitForFunction((from) => {
    const app = document.querySelector('[data-app]');
    return app.dataset.camera !== from && app.dataset.moving === 'false';
  }, since, { timeout: 60_000 });
  return data(page, 'camera');
}
const drawn = (page, id) => page.waitForSelector(
  `.flowchart[data-flowchart="${id}"][data-ready="true"]`, { timeout: 90_000 });

test('it opens from disk, offline, with a 3D view and no error', SLOW, async (t) => {
  const { page, clean } = await open(t);
  assert.equal(await page.locator('canvas').count(), 1);
  assert.ok(await page.evaluate(() => Boolean(document.querySelector('canvas')
    .getContext('webgl2'))), 'a WebGL context');
  assert.equal(await page.title(), 'StockAgent architecture');
  const inside = await model(page);
  assert.match(await page.locator('.stamp').textContent(),
    new RegExp(`Code inspected: ${inside.stamp.commit.slice(0, 7)}`));
  // the legend and the world name every module
  assert.equal(await page.locator('.legend a[data-module]').count(), inside.modules.length);
  for (const m of inside.modules) {
    assert.equal(await page.locator(`.label-anchor[data-label="${m.id}"]`).count(), 1, m.id);
  }
  clean();
});

test('each preset key moves the camera, and R brings it home', SLOW, async (t) => {
  const { page, clean } = await open(t);
  await still(page);
  const home = await data(page, 'camera');
  const seen = [home];
  for (const [key, preset] of [['2', 'top'], ['3', 'side'], ['4', 'below'], ['1', 'front']]) {
    const before_ = await data(page, 'camera');
    await page.keyboard.press(key);
    seen.push(await settled(page, before_));
    assert.equal(await data(page, 'preset'), preset);
  }
  assert.equal(new Set(seen.slice(0, 4)).size, 4, 'four different views');
  assert.equal(seen.at(-1), home, 'key 1 is where the page began');
  await page.keyboard.press('2');
  await settled(page, home);
  await page.keyboard.press('r');
  assert.equal(await settled(page, seen[1]), home);
  clean();
});

/** Two looks at the 3D view a moment apart. */
async function twice(page) {
  const view = page.locator('canvas');
  const first = await view.screenshot();
  await page.waitForTimeout(900);
  return [first, await view.screenshot()];
}

test('with motion the camera flies, and motion can be paused', SLOW, async (t) => {
  const { page, clean } = await open(t, { motion: true, size: [900, 600] });
  await still(page);
  assert.equal(await data(page, 'motion'), 'on');
  const [now, later] = await twice(page);
  assert.ok(!now.equals(later), 'the dots travel');
  // record the places the camera passes through on the way to the view from above
  await page.evaluate(() => {
    window.seen = [];
    const app = document.querySelector('[data-app]');
    new MutationObserver(() => window.seen.push([app.dataset.camera, app.dataset.moving]))
      .observe(app, { attributes: true, attributeFilter: ['data-camera', 'data-moving'] });
  });
  const start = await data(page, 'camera');
  await page.keyboard.press('2');
  const end = await settled(page, start);
  const path_ = await page.evaluate(() => window.seen);
  assert.ok(path_.some(([, moving]) => moving === 'true'), 'it flies');
  assert.ok(path_.some(([camera]) => camera !== start && camera !== end),
    'it passes between the two views');
  await page.keyboard.press('p');
  assert.equal(await data(page, 'motion'), 'off');
  await page.waitForTimeout(500);
  const [paused, stillPaused] = await twice(page);
  assert.ok(paused.equals(stillPaused), 'paused, nothing moves');
  await page.getByRole('button', { name: 'Pause motion' }).click();
  assert.equal(await data(page, 'motion'), 'on');
  clean();
});

test('with reduced motion asked for, nothing moves by itself', SLOW, async (t) => {
  const { page, clean } = await open(t);
  await still(page);
  await page.waitForTimeout(500);
  const [now, later] = await twice(page);
  assert.ok(now.equals(later), 'the dots stand still');
  // and a view change is a jump: the camera is never on its way
  await page.evaluate(() => {
    window.flew = false;
    const app = document.querySelector('[data-app]');
    new MutationObserver(() => { window.flew ||= app.dataset.moving === 'true'; })
      .observe(app, { attributes: true, attributeFilter: ['data-moving'] });
  });
  const start = await data(page, 'camera');
  await page.keyboard.press('2');
  await settled(page, start);
  assert.equal(await page.evaluate(() => window.flew), false);
  assert.equal(await data(page, 'motion'), 'off');
  assert.ok(await page.getByRole('button', { name: 'Pause motion' }).isDisabled());
  await page.keyboard.press('p');
  assert.equal(await data(page, 'motion'), 'off');
  clean();
});

test('clicking M5 opens its panel with all its parts and flies to it', SLOW, async (t) => {
  const { page, clean } = await open(t);
  await still(page);
  const home = await data(page, 'camera');
  await page.locator('.label-anchor[data-label="M5"] button').click();
  await page.waitForSelector('[data-panel="M5"]');
  assert.notEqual(await settled(page, home), home);
  const inside = await model(page);
  const parts = inside.modules.find((m) => m.id === 'M5').submodules;
  const listed = await page.locator('.panel nav[aria-label="Parts"] li').allTextContents();
  assert.equal(listed.length, parts.length);
  parts.forEach((s, i) => assert.ok(listed[i].includes(`${s.id} ${s.name}`), listed[i]));
  // what has no flow or store in common with M5 fades; its neighbours do not
  const faded = (id) => page.locator(`.label-anchor[data-label="${id}"] .label`)
    .evaluate((el) => el.classList.contains('faded'));
  const touching = new Set(inside.flows.flatMap((f) => [f.from, f.to]
    .some((w) => w.split('.')[0] === 'M5') ? [f.from.split('.')[0], f.to.split('.')[0]] : []));
  for (const m of inside.modules) {
    assert.equal(await faded(m.id), m.id !== 'M5' && !touching.has(m.id), m.id);
  }
  // the module unfolds in the world too
  for (const s of parts) {
    assert.equal(await page.locator(`.label-anchor[data-label="${s.id}"]`).count(), 1, s.id);
  }
  assert.equal(new URL(page.url()).hash, '#m=M5');
  assert.match(await page.title(), /^M5 /);
  clean();
});

test('opening the panel mid-flight frames the module for the narrower view', SLOW, async (t) => {
  // Where the camera ends up must not depend on whether it flew there: the panel narrows
  // the view while the flight is under way.
  const size = [1100, 650];
  const arrive = async (motion) => {
    const { page, clean, close } = await open(t, { motion, size });
    await still(page);
    const home = await data(page, 'camera');
    const wide = (await page.locator('canvas').boundingBox()).width;
    await page.locator('.legend [data-module="M5"]').click();
    await page.waitForFunction((w) => document.querySelector('canvas').clientWidth < w - 100, wide);
    await settled(page, home);
    await page.waitForTimeout(600);
    await still(page);
    clean();
    const at = await data(page, 'camera');
    await close();
    return at;
  };
  const jumped = await arrive(false);
  const flown = await arrive(true);
  assert.equal(flown, jumped);
});

test('clicking a block itself, not its name, selects it', SLOW, async (t) => {
  const { page, clean } = await open(t);
  await still(page);
  const name = await page.locator('.label-anchor[data-label="M5"] button').boundingBox();
  // the block stands just under its name
  await page.mouse.click(name.x + name.width / 2, name.y + name.height + 22);
  await page.waitForSelector('[data-panel="M5"]', { timeout: 30_000 });
  clean();
});

/** Where a point of the world lands on the 3D view: the camera's own geometry. */
function onScreen(camera, fov, view, point) {
  const sub = (a, b) => a.map((v, i) => v - b[i]);
  const dot = (a, b) => a[0] * b[0] + a[1] * b[1] + a[2] * b[2];
  const unit = (a) => a.map((v) => v / Math.hypot(...a));
  const cross = (a, b) => [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2],
    a[0] * b[1] - a[1] * b[0]];
  const forward = unit(sub(camera.target, camera.position));
  const right = unit(cross(forward, [0, 1, 0]));
  const up = cross(right, forward);
  const rel = sub(point, camera.position);
  const tan = Math.tan((fov * Math.PI) / 360);
  const depth = dot(rel, forward);
  return {
    x: view.x + ((dot(rel, right) / (depth * tan * (view.width / view.height)) + 1) / 2) * view.width,
    y: view.y + ((1 - dot(rel, up) / (depth * tan)) / 2) * view.height,
  };
}

test('pointing at a flow says what travels on it', SLOW, async (t) => {
  const { page, clean } = await open(t);
  await still(page);
  const view = await page.locator('canvas').boundingBox();
  const inside = await model(page);
  const world = layoutWorld(inside);
  const { dir, fov } = PRESETS.front;
  const camera = fitCamera(world.bounds, dir, fov, view.width / view.height);
  const tip = page.locator('.tooltip');
  const told = new Set();
  for (const flow of world.flows) {
    for (const along of [0.4, 0.6]) {
      const at = onScreen(camera, fov, view, curvePoint(flow.points, along));
      await page.mouse.move(at.x, at.y);
      if (!(await tip.count())) continue;
      const text = await tip.textContent();
      assert.ok(inside.flows.some((f) => text.endsWith(f.what) && text.includes('→')), text);
      if (text.endsWith(flow.what)) told.add(flow.key);
    }
  }
  // some flows pass behind a label or another flow; most answer for themselves
  assert.ok(told.size > world.flows.length / 2, `${told.size} of ${world.flows.length}`);
  await page.mouse.move(view.x + 4, view.y + 4);
  assert.equal(await tip.count(), 0, 'pointing at nothing says nothing');
  clean();
});

test('#m=M5.2 opens the advisor’s flowchart', SLOW, async (t) => {
  const { page, clean } = await open(t, { hash: '#m=M5.2' });
  await page.waitForSelector('[data-panel="M5.2"]');
  await drawn(page, 'M5.2');
  const chart = page.locator('.flowchart[data-flowchart="M5.2"]');
  assert.ok(await chart.locator('g.node[data-kind="decision"]').count() >= 4);
  assert.ok(await chart.locator('g.node[data-kind="end"]').count() >= 2);
  const titles = await chart.locator('g.node > title').allTextContents();
  for (const words of ['identity changed', 'EXIT if any trigger fires', 'else TRIM',
    'else ADD', 'else HOLD', 'stop_breach']) {
    assert.ok(titles.some((x) => x.includes(words)), words);
  }
  // every box has its own space: no two drawn boxes overlap
  const boxes = await chart.locator('svg[data-graph="0"] g.node').evaluateAll(
    (nodes) => nodes.map((n) => {
      const r = n.getBoundingClientRect();
      return { x: r.x, y: r.y, r: r.right, b: r.bottom };
    }));
  for (let i = 0; i < boxes.length; i += 1) {
    for (let j = i + 1; j < boxes.length; j += 1) {
      const [a, b] = [boxes[i], boxes[j]];
      assert.ok(a.r <= b.x + 1 || b.r <= a.x + 1 || a.b <= b.y + 1 || b.b <= a.y + 1,
        `boxes ${i} and ${j} overlap`);
    }
  }
  clean();
});

test('every money-path part draws its flowchart, with its own outline as text', SLOW, async (t) => {
  const { page, clean } = await open(t);
  const inside = await model(page);
  const subs = new Map(inside.modules.flatMap((m) => m.submodules).map((s) => [s.id, s]));
  for (const id of MONEY_PATH) {
    await page.evaluate((hash) => { window.location.hash = hash; }, `#m=${id}`);
    await drawn(page, id);
    const chart = page.locator(`.flowchart[data-flowchart="${id}"]`);
    assert.equal(await chart.locator('svg').count(), subs.get(id).logic.length, id);
    assert.ok(await chart.locator('g.node').count() >= 3, id);
    assert.equal(await chart.locator('.notice').count(), 0, id);
    const first = subs.get(id).logic[0].text.split('\n')[0].replace(/\s{2,}/g, ' ');
    assert.ok((await chart.locator('details.outline li').first().textContent())
      .startsWith(first.slice(0, 30)), id);
  }
  clean();
});

test('the developer view adds paths, functions and settings with their sources', SLOW, async (t) => {
  const { page, clean } = await open(t, { hash: '#m=M3.4' });
  await page.waitForSelector('[data-panel="M3.4"]');
  const panel = page.locator('.panel');
  assert.equal(await panel.getByRole('heading', { name: 'Where it lives' }).count(), 0);
  assert.ok(!(await panel.textContent()).includes('decision_gate.py'));
  await page.getByRole('button', { name: 'Developer' }).click();
  const text = await panel.textContent();
  assert.ok(text.includes('src/backend/shared/pipeline/decision_gate.py'));
  assert.ok(text.includes('assess_analysis'));
  const inside = await model(page);
  const cited = inside.production.find((p) => p.key === 'decision_gate.mode');
  const row = panel.locator('tr', { hasText: 'decision_gate.mode' });
  assert.ok((await row.textContent()).includes(`${cited.source}, as of ${cited.as_of}`));
  assert.equal(new URL(page.url()).hash, '#m=M3.4&v=dev');
  await page.reload();
  await page.waitForSelector('[data-app][data-ready="true"][data-audience="developer"]');
  clean();
});

test('an unknown address says so, and Back returns to what was open', SLOW, async (t) => {
  const { page, clean } = await open(t, { hash: '#m=M99' });
  assert.match(await page.locator('.world .notice').textContent(), /M99/);
  assert.equal(await page.locator('.panel').count(), 0);
  await page.locator('.legend [data-module="M2"]').click();
  await page.waitForSelector('[data-panel="M2"]');
  await page.locator('.legend [data-module="M7"]').click();
  await page.waitForSelector('[data-panel="M7"]');
  await page.goBack();
  await page.waitForSelector('[data-panel="M2"]');
  await page.goForward();
  await page.waitForSelector('[data-panel="M7"]');
  // the audience travels with the address too
  await page.getByRole('button', { name: 'Developer' }).click();
  await page.locator('.legend [data-module="M3"]').click();
  await page.waitForSelector('[data-panel="M3"]');
  await page.goBack();
  await page.waitForSelector('[data-panel="M7"]');
  assert.equal(await data(page, 'audience'), 'developer');
  await page.goBack();
  await page.waitForSelector('[data-panel="M2"]');
  assert.equal(new URL(page.url()).hash, '#m=M2');
  assert.equal(await data(page, 'audience'), 'manager');
  clean();
});

test('the skip link moves to the modules and leaves what is open', SLOW, async (t) => {
  const { page, clean } = await open(t, { hash: '#m=M5.2' });
  await page.waitForSelector('[data-panel="M5.2"]');
  await page.keyboard.press('Tab');
  assert.match((await focus(page)).text, /^Skip to the list of modules/);
  await page.keyboard.press('Enter');
  assert.equal((await focus(page)).module, 'M1');
  assert.equal(await page.locator('[data-panel="M5.2"]').count(), 1);
  assert.equal(new URL(page.url()).hash, '#m=M5.2');
  clean();
});

/** The focused element, and whether a person can see that it is focused. */
const focus = (page) => page.evaluate(() => {
  const el = document.activeElement;
  const style = getComputedStyle(el);
  return {
    tag: el.tagName, text: el.textContent.trim().slice(0, 60), module: el.dataset.module ?? '',
    inDialog: Boolean(el.closest('dialog')), id: el.id,
    ring: style.outlineStyle !== 'none' && parseFloat(style.outlineWidth) >= 2,
  };
});

test('views, search, the panel and help work from the keyboard, focus always seen', SLOW, async (t) => {
  const { page, clean } = await open(t);
  await still(page);
  await page.keyboard.press('Tab');
  assert.match((await focus(page)).text, /^Skip to the list of modules/);
  // Tab to the legend entry of M5, every stop on the way showing its focus
  let at = await focus(page);
  for (let i = 0; i < 40 && at.module !== 'M5'; i += 1) {
    assert.ok(at.ring, `no focus ring on ${at.tag} ${at.text}`);
    await page.keyboard.press('Tab');
    at = await focus(page);
  }
  assert.equal(at.module, 'M5');
  assert.ok(at.ring);
  await page.keyboard.press('Enter');
  await page.waitForSelector('[data-panel="M5"]');
  // Esc closes the panel and gives focus back
  await page.keyboard.press('Escape');
  await page.waitForSelector('.panel', { state: 'detached' });
  assert.equal((await focus(page)).module, 'M5');
  // the 3D view itself turns and zooms from the keyboard
  for (let i = 0; i < 40 && (await focus(page)).tag !== 'MAIN'; i += 1) await page.keyboard.press('Tab');
  assert.equal((await focus(page)).tag, 'MAIN');
  assert.ok((await focus(page)).ring);
  for (const key of ['ArrowLeft', 'ArrowDown', '+', '-', 'ArrowRight']) {
    const was = await data(page, 'camera');
    await page.keyboard.press(key);
    await settled(page, was);
  }
  // Shift and the arrows slide the view: away and back ends where it began
  const here = await data(page, 'camera');
  await page.keyboard.press('Shift+ArrowLeft');
  assert.notEqual(await settled(page, here), here);
  const moved = await data(page, 'camera');
  await page.keyboard.press('Shift+ArrowRight');
  const back = (await settled(page, moved)).split(',').map(Number);
  here.split(',').map(Number).forEach((v, i) => assert.ok(Math.abs(v - back[i]) <= 0.2, here));
  // a view key
  const before_ = await data(page, 'camera');
  await page.keyboard.press('4');
  await settled(page, before_);
  assert.equal(await data(page, 'preset'), 'below');
  // search: digits typed there are text, not view keys
  await page.keyboard.press('/');
  await page.waitForSelector('dialog.search[open]');
  assert.equal((await focus(page)).id, 'search-input');
  await page.keyboard.type('2');
  assert.equal(await data(page, 'preset'), 'below');
  await page.keyboard.press('Backspace');
  await page.keyboard.type('advisor');
  assert.match(await page.locator('#result-0').textContent(), /M5\.2 Advisor/);
  await page.keyboard.press('ArrowDown');
  assert.equal(await page.locator('#result-1').getAttribute('aria-selected'), 'true');
  await page.keyboard.press('ArrowUp');
  await page.keyboard.press('Enter');
  await page.waitForSelector('[data-panel="M5.2"]');
  await page.waitForSelector('dialog.search', { state: 'hidden' });
  at = await focus(page);
  assert.equal(at.tag, 'H2', 'focus moves into what was opened');
  assert.match(at.text, /^M5\.2/);
  assert.ok(at.ring);
  // Esc in search closes only the search
  await page.keyboard.press('/');
  await page.waitForSelector('dialog.search[open]');
  await page.keyboard.press('Escape');
  await page.waitForSelector('dialog.search', { state: 'hidden' });
  assert.equal(await page.locator('[data-panel="M5.2"]').count(), 1);
  // help keeps the focus inside, closes on Esc, and gives it back
  await page.keyboard.press('Shift+Slash');
  await page.waitForSelector('dialog.help[open]');
  for (let i = 0; i < 4; i += 1) {
    await page.keyboard.press('Tab');
    const inside = await focus(page);
    assert.ok(inside.inDialog || inside.tag === 'BODY', `focus left the dialog: ${inside.text}`);
  }
  await page.keyboard.press('Escape');
  await page.waitForSelector('dialog.help', { state: 'hidden' });
  assert.equal(await page.locator('[data-panel="M5.2"]').count(), 1);
  await page.keyboard.press('Escape');
  await page.waitForSelector('.panel', { state: 'detached' });
  clean();
});

test('without WebGL it says so, and the legend and panel still work', SLOW, async (t) => {
  const context = await browser.newContext({ viewport: { width: 1280, height: 800 },
    offline: true, reducedMotion: 'reduce' });
  t.after(async () => { await context.close(); });
  await context.addInitScript(() => {
    const real = HTMLCanvasElement.prototype.getContext;
    HTMLCanvasElement.prototype.getContext = function getContext(kind, ...rest) {
      return String(kind).startsWith('webgl') ? null : real.call(this, kind, ...rest);
    };
  });
  const page = await context.newPage();
  const wrong = [];
  page.on('console', (m) => { if (m.type() === 'error') wrong.push(m.text()); });
  page.on('pageerror', (e) => wrong.push(e.message));
  await page.goto(PAGE);
  assert.match(await page.getByRole('alert').textContent(), /needs WebGL/);
  assert.equal(await page.locator('canvas').count(), 0);
  // the tour a manager starts on plays without the 3D view too, and says what it lights
  await page.locator('.player').getByRole('button', { name: 'Next →' }).click();
  await page.waitForSelector('[data-app][data-step="2"]');
  const lights = page.locator('.player-lights');
  assert.match(await lights.textContent(), /Highlighted on the map: M6 Discovery/);
  assert.ok((await lights.boundingBox()).height > 10, 'in sight');
  for (const name of ['constructor', 'toString', '__proto__']) {
    await page.evaluate((hash) => { window.location.hash = hash; }, `#p=${name}`);
    await page.waitForSelector('.world .notice');
    assert.equal(await page.locator('.legend [data-module]').count() > 0, true, name);
  }
  await page.keyboard.press('5');
  await page.waitForSelector('[data-panel="clock"] [data-moment]');
  await page.locator('.legend [data-module="M5"]').click();
  await page.locator('.panel a', { hasText: 'Advisor' }).click();
  await drawn(page, 'M5.2');
  assert.deepEqual(wrong, []);
});

test('a laptop and a wide screen need no page scrolling', SLOW, async (t) => {
  for (const size of [[1280, 720], [2200, 1200]]) {
    const { page, clean, close } = await open(t, { hash: '#m=M6.1', size });
    await drawn(page, 'M6.1');
    const scroll = await page.evaluate(() => [
      document.documentElement.scrollWidth - window.innerWidth,
      document.documentElement.scrollHeight - window.innerHeight]);
    assert.deepEqual(scroll, [0, 0], `${size}`);
    clean();
    await close();
  }
});

// -- the clock, the trace and the tour (MAP-003) -------------------------------------------

const playerCount = (page) => page.locator('.player .count').textContent();
const onStep = (page, step) => page.waitForSelector(`[data-app][data-step="${step}"]`,
  { timeout: 60_000 });

/** Note every value an attribute of the app takes from now on. */
const record = (page, name) => page.evaluate((attribute) => {
  const app = document.querySelector('[data-app]');
  window.visited = [app.getAttribute(attribute)];
  new MutationObserver(() => window.visited.push(app.getAttribute(attribute)))
    .observe(app, { attributes: true, attributeFilter: [attribute] });
}, name);
const visited = (page) => page.evaluate(() => window.visited);

const press = (page, name) => page.locator('.player').getByRole('button', { name, exact: true })
  .click();
const button = (page, name) => page.locator('.player').getByRole('button', { name, exact: true });

test('a manager starts on the guided tour, steps to its end and leaves it', SLOW, async (t) => {
  const { page, clean } = await open(t, { tour: true });
  const inside = await model(page);
  const stops = inside.tours[0].steps;
  assert.equal(await data(page, 'mode'), 'tour');
  assert.equal(new URL(page.url()).hash, '#p=tour&s=1');
  assert.equal(await page.title(), `Guided tour, 1 of ${stops.length} · StockAgent architecture`);
  assert.equal(await data(page, 'playing'), 'false', 'it waits to be played');
  assert.equal(await button(page, '← Back').getAttribute('aria-disabled'), 'true');
  await button(page, '← Back').click({ force: true });
  assert.equal(await data(page, 'step'), '1', 'there is nothing before the first stop');
  const cameras = new Set();
  for (const [i, stop] of stops.entries()) {
    await onStep(page, i + 1);
    await still(page);
    await page.waitForTimeout(200);
    cameras.add(await data(page, 'camera'));
    assert.equal(await playerCount(page), `${i + 1} of ${stops.length}`);
    assert.ok((await page.locator('.player-caption').textContent()).includes(stop.caption), stop.caption);
    assert.equal(await data(page, 'preset'), stop.preset === 'focus' ? 'front' : stop.preset);
    assert.equal(await data(page, 'job'), stop.preset === 'clock' ? stop.ref ?? '' : '');
    if (stop.preset === 'clock' && stop.ref) {
      // the clock's hand is on that job's time
      const job = inside.jobs.find((j) => j.id === stop.ref);
      assert.equal((await page.locator('.label-anchor[data-label="job-now"]').textContent())
        .trim(), `${job.schedule.time.split(', ')[0]} ${job.name}`);
    }
    assert.equal(await page.locator('.panel').count(), 0, 'the tour has no panel');
    if (stop.preset === 'focus') {
      // the part it is about opens up in the world, and the legend marks it
      const parts = inside.modules.find((m) => m.id === stop.ref.split('.')[0]).submodules;
      for (const s of parts) {
        assert.equal(await page.locator(`.label-anchor[data-label="${s.id}"]`).count(), 1, s.id);
      }
      assert.equal(await page.locator('.legend [aria-current="true"]').getAttribute('data-module'),
        stop.ref.split('.')[0]);
    }
    if (i < stops.length - 1) await press(page, 'Next →');
  }
  assert.ok(cameras.size >= 5, `the camera moves with the tour: ${cameras.size} places`);
  await press(page, 'Finish');
  await page.waitForSelector('.player', { state: 'detached' });
  assert.equal(await data(page, 'mode'), '');
  assert.equal(new URL(page.url()).hash, '');
  assert.equal(await page.title(), 'StockAgent architecture');
  assert.equal(await page.evaluate(() => document.activeElement.dataset.story), 'tour',
    'the focus is not lost with the button that had it');
  clean();
});

test('a developer, a deep link and Esc: no tour', SLOW, async (t) => {
  for (const hash of ['#v=dev', '#m=M5']) {
    const { page, clean, close } = await open(t, { hash });
    assert.equal(await data(page, 'mode'), '', hash);
    assert.equal(await page.locator('.player').count(), 0, hash);
    clean();
    await close();
  }
  const { page, clean } = await open(t, { tour: true });
  const height = () => page.locator('canvas').evaluate((c) => c.clientHeight);
  const was = await height();
  await page.keyboard.press('Escape');
  await page.waitForSelector('.player', { state: 'detached' });
  assert.equal(new URL(page.url()).hash, '');
  assert.equal(await page.evaluate(() => document.activeElement.tagName), 'BODY');
  await page.waitForFunction((h) => document.querySelector('canvas').clientHeight > h + 50, was);
  clean();
});

test('autoplay runs the tour and the trace to their ends and stops there', SLOW, async (t) => {
  const { page, clean } = await open(t);
  const inside = await model(page);
  for (const [name, steps, title] of [
    ['Tour', inside.tours[0].steps, 'Guided tour'],
    ['Trace a stock', inside.traces[0].steps, 'One stock’s life']]) {
    await page.locator('.topbar').getByRole('button', { name, exact: true }).click();
    await page.waitForSelector(`.player[aria-label="${title}"]`);
    assert.equal(await data(page, 'step'), '1', 'a mode opens at its first step');
    await press(page, '4×');
    await record(page, 'data-step');
    await press(page, 'Play');
    assert.equal(await data(page, 'playing'), 'true');
    await page.waitForSelector(`[data-app][data-step="${steps.length}"][data-playing="false"]`,
      { timeout: 90_000 });
    assert.deepEqual([...new Set(await visited(page))],
      steps.map((_, i) => String(i + 1)), `${name} visits every step in order`);
    // it stays on the last step; Play starts again from the first
    await page.waitForTimeout(2000);
    assert.equal(await data(page, 'step'), String(steps.length));
    await press(page, 'Play');
    await onStep(page, 1);
    await press(page, 'Pause');
    // a slow machine may have moved on before the click landed: where it stopped, it stays
    const stopped = await data(page, 'step');
    assert.ok(Number(stopped) <= 2, 'Play on the last step starts again');
    await page.waitForTimeout(2000);
    assert.equal(await data(page, 'step'), stopped, 'paused, it stays');
    await page.getByRole('button', { name: `Close ${title}` }).click();
    await page.waitForSelector('.player', { state: 'detached' });
  }
  clean();
});

test('the trace says each step and names what it lights', SLOW, async (t) => {
  const { page, clean } = await open(t, { hash: '#p=trace&s=1' });
  const inside = await model(page);
  const steps = inside.traces[0].steps;
  const modules = new Set(inside.modules.map((m) => m.id));
  const jobs = new Map(inside.jobs.map((j) => [j.id, j]));
  for (const [i, step] of steps.entries()) {
    await onStep(page, i + 1);
    const said = await page.locator('.player-caption').textContent();
    assert.ok(said.startsWith(step.when), said);
    assert.match(await page.locator('.player .sr-only').textContent(), /^Highlighted on the map: /);
    assert.ok(said.includes(step.text.split('─►')[0].trim()), said);
    // the modules it names are lit, every other one is dimmed
    const named = new Set(step.refs.map((r) => (jobs.get(r)?.module ?? r).split('.')[0])
      .filter((r) => modules.has(r)));
    for (const id of modules) {
      const classes = await page.locator(`.label-anchor[data-label="${id}"] .label`)
        .getAttribute('class');
      assert.equal(classes.includes(' lit'), named.has(id), `step ${i + 1}: ${id}`);
      assert.equal(classes.includes(' faded'), !named.has(id), `step ${i + 1}: ${id}`);
    }
    if (i < steps.length - 1) await press(page, 'Next →');
  }
  await press(page, '← Back');
  await onStep(page, steps.length - 1);
  assert.equal(new URL(page.url()).hash, `#p=trace&s=${steps.length - 1}`);
  clean();
});

test('playing the day visits every job, and the panel names it, its trigger and its gate',
  SLOW, async (t) => {
    const { page, clean } = await open(t);
    const inside = await model(page);
    await page.keyboard.press('5');
    await page.waitForSelector('[data-panel="clock"]');
    assert.equal(await data(page, 'preset'), 'clock');
    const rows = page.locator('[data-panel="clock"] [data-moment]');
    const times = inside.jobs.reduce((n, j) => n + j.schedule.time.split(', ').length, 0);
    assert.equal(await rows.count(), times);
    // the world names the job under the hand, and the list keeps it in sight
    const named = () => page.locator('.label-anchor[data-label="job-now"]').textContent();
    const first = inside.jobs.find((j) => j.id === 'scorecard_monthly');
    assert.equal((await named()).trim(), `02:00 ${first.name}`);
    const inSight = () => page.evaluate(() => {
      const row = document.querySelector('.day [aria-current="true"]').getBoundingClientRect();
      const box = document.querySelector('.day').getBoundingClientRect();
      return row.top >= box.top - 1 && row.bottom <= box.bottom + 1;
    });
    for (let step = 2; step <= times; step += 1) {
      await press(page, 'Next →');
      await onStep(page, step);
      await page.waitForFunction((s) => document.querySelector('.day [aria-current="true"]')
        .parentElement === document.querySelectorAll('.day li')[s - 1], step);
      assert.ok(await inSight(), `time ${step} is out of the list's sight`);
    }
    await press(page, '← Back');
    await page.locator('.player input[type="range"]').fill('0');
    await onStep(page, 1);
    assert.ok(await inSight(), 'and back at the top');
    // a bead in the world takes the clock to its time
    await still(page);
    const view = await page.locator('canvas').boundingBox();
    const world = layoutWorld(inside);
    const ring = clockRing(world);
    const { dir, fov } = PRESETS.clock;
    const camera = fitCamera(clockBounds(world, ring), dir, fov, view.width / view.height);
    const bead = beads(ring, moments(inside)).find((b) => b.key === 'rl_daily_review@16:30');
    const at = onScreen(camera, fov, view, bead.pos);
    await page.mouse.click(at.x, at.y);
    await page.waitForSelector('[data-app][data-job="rl_daily_review"]');
    const clicked = inside.jobs.find((j) => j.id === 'rl_daily_review');
    await page.waitForFunction((words) => document
      .querySelector('.label-anchor[data-label="job-now"]')?.textContent.trim() === words,
    `16:30 ${clicked.name}`);
    await page.locator('.player input[type="range"]').fill('0');
    await onStep(page, 1);
    await record(page, 'data-job');
    await press(page, '4×');
    await press(page, 'Play');
    await page.waitForSelector(`[data-app][data-step="${times}"][data-playing="false"]`,
      { timeout: 120_000 });
    assert.deepEqual([...new Set(await visited(page))].sort(),
      inside.jobs.map((j) => j.id).sort(), 'every job marker');
    assert.equal(await button(page, 'Next →').getAttribute('aria-disabled'), 'true');
    // the panel at 16:30, and at a gated job
    const panel = page.locator('[data-panel="clock"]');
    await panel.locator('[data-moment="rl_daily_review@16:30"]').click();
    await page.waitForSelector('[data-app][data-job="rl_daily_review"]');
    const review = inside.jobs.find((j) => j.id === 'rl_daily_review');
    assert.equal(await panel.locator('h2').textContent(), `16:30 · ${review.name}`);
    assert.ok((await panel.textContent()).includes('Monday to Friday at 16:30 IST'));
    assert.ok((await panel.textContent()).includes('No switch gates it'));
    assert.equal(await panel.locator('[aria-current="true"]').getAttribute('data-moment'),
      'rl_daily_review@16:30');
    assert.equal(await page.title(), 'Clock, 16:30 · StockAgent architecture');
    await panel.locator('[data-moment="audit_nightly@23:45"]').click();
    await page.waitForSelector('[data-app][data-job="audit_nightly"]');
    const setting = inside.switches.find((s) => s.key === 'audit.enabled');
    assert.match(await panel.locator('.gates').textContent(),
      new RegExp(`audit\\.enabled.*Repository default ${setting.default}`));
    assert.ok(!(await panel.textContent()).includes('_audit_nightly_job'), 'not for a manager');
    await page.getByRole('button', { name: 'Developer' }).click();
    assert.ok((await panel.textContent()).includes('_audit_nightly_job'));
    assert.equal(new URL(page.url()).hash.endsWith('&v=dev'), true);
    clean();
  });

test('the clock, trace and tour work from the keyboard, focus always seen', SLOW, async (t) => {
  const { page, clean } = await open(t);
  // the Clock button opens the clock and hands the focus to Play
  for (let i = 0; i < 30; i += 1) {
    await page.keyboard.press('Tab');
    if (await page.evaluate(() => document.activeElement.dataset.view === 'clock')) break;
  }
  await page.keyboard.press('Enter');
  await page.waitForSelector('.player');
  assert.equal((await focus(page)).text, 'Play');
  assert.ok((await focus(page)).ring);
  // the slider is a Tab stop before the buttons; arrows, Home and End move it
  await page.keyboard.press('Shift+Tab');
  await page.keyboard.press('Shift+Tab');
  const at = await page.evaluate(() => document.activeElement.type);
  assert.equal(at, 'range');
  assert.ok((await focus(page)).ring, 'the slider shows its focus');
  const times = Number((await playerCount(page)).split(' of ')[1]);
  await page.keyboard.press('ArrowRight');
  await onStep(page, 2);
  await page.keyboard.press('End');
  await onStep(page, times);
  await page.keyboard.press('Home');
  await onStep(page, 1);
  const spoken = () => page.getAttribute('.player input[type="range"]', 'aria-valuetext');
  const inside = await model(page);
  const first = inside.jobs.find((j) => j.id === 'scorecard_monthly');
  assert.equal(await spoken(), `02:00, 1st of the month, ${first.name}`);
  // Play, Next and the speed from the keyboard; a person's move ends autoplay
  for (let i = 0; i < 4 && (await focus(page)).text !== 'Play'; i += 1) {
    await page.keyboard.press('Tab');
  }
  await page.keyboard.press('Space');
  await page.waitForSelector('[data-app][data-playing="true"]');
  await page.keyboard.press('Tab');
  assert.match((await focus(page)).text, /^Next/);
  assert.ok((await focus(page)).ring);
  await page.keyboard.press('Enter');
  assert.equal(await data(page, 'playing'), 'false');
  assert.ok(Number(await data(page, 'step')) >= 2);
  // pausing motion stops autoplay too (motion is already off here, so P does nothing)
  await page.keyboard.press('Shift+Tab');
  await page.keyboard.press('Shift+Tab');
  assert.match((await focus(page)).text, /^← Back/);
  for (let i = 0; i < 12; i += 1) await page.keyboard.press('Enter');
  await onStep(page, 1);
  assert.match((await focus(page)).text, /^← Back/, 'a disabled Back keeps the focus');
  // Esc from the slider leaves the clock and gives the focus back to its button
  await page.keyboard.press('Shift+Tab');
  assert.equal(await page.evaluate(() => document.activeElement.type), 'range');
  await page.keyboard.press('Escape');
  await page.waitForSelector('.player', { state: 'detached' });
  assert.equal(await page.evaluate(() => document.activeElement.dataset.view), 'clock');
  assert.equal(await data(page, 'preset'), 'front');
  // a story button opens it with the focus on Next; Esc returns to the button
  await page.locator('[data-story="trace"]').focus();
  await page.keyboard.press('Enter');
  await page.waitForSelector('.player');
  assert.match((await focus(page)).text, /^Next/);
  assert.ok((await focus(page)).ring);
  await page.keyboard.press('Enter');
  await onStep(page, 2);
  await page.keyboard.press('Escape');
  await page.waitForSelector('.player', { state: 'detached' });
  assert.equal(await page.evaluate(() => document.activeElement.dataset.story), 'trace');
  clean();
});

test('pausing motion stops autoplay, and Play starts it again', SLOW, async (t) => {
  const { page, clean } = await open(t, { motion: true, size: [900, 600] });
  await page.keyboard.press('5');
  await page.waitForSelector('.player');
  await press(page, '4×');
  await press(page, 'Play');
  await onStep(page, 3);
  await page.keyboard.press('p');
  assert.deepEqual([await data(page, 'motion'), await data(page, 'playing')], ['off', 'false']);
  const step = await data(page, 'step');
  await page.waitForTimeout(2000);
  assert.equal(await data(page, 'step'), step);
  await press(page, 'Play');
  await onStep(page, Number(step) + 1);
  assert.equal(await data(page, 'motion'), 'off', 'Play does not start the dots');
  clean();
});

test('a mode is in the address: Back leaves it, Forward returns, a reload keeps the step',
  SLOW, async (t) => {
    const { page, clean } = await open(t);
    await page.locator('.legend [data-module="M5"]').click();
    await page.waitForSelector('[data-panel="M5"]');
    await page.locator('[data-view="clock"]').click();
    await page.waitForSelector('[data-panel="clock"]');
    assert.equal(await data(page, 'selected'), '');
    await press(page, 'Next →');
    await press(page, 'Next →');
    await onStep(page, 3);
    assert.equal(new URL(page.url()).hash, '#p=clock&s=3');
    await page.goBack();
    await page.waitForSelector('[data-panel="M5"]');
    assert.equal(await data(page, 'mode'), '');
    assert.equal(await page.locator('.player').count(), 0);
    assert.equal(await page.evaluate(() => document.activeElement.dataset.view), 'clock',
      'Back from a mode does not drop the focus that stood in its player');
    await page.goForward();
    await page.waitForSelector('[data-app][data-mode="clock"][data-step="3"]');
    await page.reload();
    await page.waitForSelector('[data-app][data-ready="true"][data-mode="clock"][data-step="3"]');
    // a part opened from the clock's panel leaves the clock
    await page.locator('[data-panel="clock"] .lights a').first().click();
    await page.waitForSelector('.player', { state: 'detached' });
    assert.match(await data(page, 'selected'), /^M\d+/);
    assert.equal(await page.locator('[data-panel="clock"]').count(), 0);
    // a view key leaves a mode for that view; the address of an unknown mode says so
    await page.keyboard.press('5');
    await page.waitForSelector('.player');
    await page.keyboard.press('2');
    await page.waitForSelector('.player', { state: 'detached' });
    assert.equal(await data(page, 'preset'), 'top');
    await page.evaluate(() => { window.location.hash = '#p=disco'; });
    await page.waitForSelector('.world .notice');
    assert.match(await page.locator('.world .notice').textContent(), /disco/);
    clean();
  });

test('the modes need no page scrolling, on a laptop and a wide screen', SLOW, async (t) => {
  for (const size of [[1280, 720], [2200, 1200]]) {
    // one page a size, taken from mode to mode
    const { page, clean, close } = await open(t, { hash: '#p=clock&s=16', size });
    for (const [mode, hash] of [['clock', '#p=clock&s=16'], ['trace', '#p=trace&s=7'],
      ['tour', '#p=tour&s=3']]) {
      await page.evaluate((to) => { window.location.hash = to; }, hash);
      await page.waitForSelector(`[data-app][data-mode="${mode}"] .player`);
      const scroll = await page.evaluate(() => [
        document.documentElement.scrollWidth - window.innerWidth,
        document.documentElement.scrollHeight - window.innerHeight]);
      assert.deepEqual(scroll, [0, 0], `${size} ${hash}`);
      const world = await page.locator('.world').boundingBox();
      assert.ok(world.height > 250 && world.width > 250, `${size} ${hash}: ${world.height}`);
    }
    clean();
    await close();
  }
});

/**
 * MAP-004: the code galaxy of the committed architecture map, in a real browser.
 *
 *   node --test tests/frontend/architecture_map_galaxy.test.mjs
 *
 * Its logic (layout, what a choice lights, addresses, search) is in
 * architecture_map_logic.test.mjs. What is expected is worked out here from the model
 * inside the page.
 */
import { test } from 'node:test';
import assert from 'node:assert/strict';

import {
  PAGE, SLOW, data, focus, model, onScreen, open, settled, still, useBrowser,
} from './architecture_map_harness.mjs';
import {
  FRONT, MARGIN, layoutGalaxy,
} from '../../tools/architecture_map/viewer/src/lib/galaxy.js';
import { PRESETS, fitCamera } from '../../tools/architecture_map/viewer/src/lib/world.js';

const theBrowser = useBrowser();
const ADVISOR = 'core/portfolio/advisor.py';

const ballOf = (file) => (file.owner === 'shared' ? 'shared' : file.owner.split('.')[0]);
const importersOf = (inside, path) => inside.files.filter((f) => f.imports.includes(path))
  .map((f) => f.path);
const fileOf = (inside, path) => inside.files.find((f) => f.path === path);

/** Waits until the galaxy shows this many dots lit. */
const lit = (page, n) => page.waitForSelector(`[data-app][data-lit="${n}"]`, { timeout: 60_000 });
const drawnDots = (page) => page.waitForSelector('[data-app][data-dots]', { timeout: 90_000 });
const panelFiles = (page) => page.locator('.panel .files li');
const section = (page, title) => page.locator('.panel section', {
  has: page.getByRole('heading', { name: title }) });

/** Where each dot stands on the screen, by the page's own geometry worked out again. */
async function dotsOnScreen(page) {
  // the 3D view has taken the width its place now has
  await page.waitForFunction(() => Math.abs(document.querySelector('canvas').clientWidth
    - document.querySelector('main.world').clientWidth) <= 1);
  const view = await page.locator('canvas').boundingBox();
  const inside = await model(page);
  const galaxy = layoutGalaxy(inside);
  const { fov } = PRESETS.front;
  const camera = fitCamera(galaxy.bounds, FRONT, fov, view.width / view.height, MARGIN);
  // and the page looks from where the arithmetic says
  const from = camera.position.map((v) => v.toFixed(1)).join(',');
  await page.waitForFunction((want) => {
    const app = document.querySelector('[data-app]');
    return app.dataset.camera === want && app.dataset.moving === 'false';
  }, from);
  await page.waitForTimeout(300);
  const tan = Math.tan((fov * Math.PI) / 360);
  const depthOf = (p) => {
    const forward = camera.target.map((v, i) => v - camera.position[i]);
    const n = Math.hypot(...forward);
    return p.reduce((s, v, i) => s + (v - camera.position[i]) * (forward[i] / n), 0);
  };
  return galaxy.nodes.map((node) => ({
    ...node, ...onScreen(camera, fov, view, node.pos), depth: depthOf(node.pos),
    onScreen: (node.radius / (depthOf(node.pos) * tan)) * (view.height / 2),
  }));
}

/** No name or panel stands on this point of the view. */
const onView = (page, { x, y }) => page.evaluate(
  ([px, py]) => document.elementFromPoint(px, py)?.tagName === 'CANVAS', [x, y]);

/** Of these dots, large ones that nothing covers, the largest first. `room` is how far, in
 *  pixels, every other dot's edge must stay from the centre; 0 asks only that no nearer dot
 *  covers it. */
async function clearOf(page, dots, among, room = 13) {
  const free = [];
  for (const dot of among.filter((d) => d.onScreen > 4).sort((a, b) => b.onScreen - a.onScreen)) {
    const crowded = dots.some((o) => o.path !== dot.path && (room || o.depth < dot.depth)
      && Math.hypot(o.x - dot.x, o.y - dot.y) < o.onScreen + (room || 3));
    if (!crowded && await onView(page, dot)) free.push(dot);
  }
  return free;
}

/** How bright the view is at a point: the mean of a small square. */
async function brightness(page, { x, y }) {
  const shot = await page.screenshot({ clip: { x: x - 2, y: y - 2, width: 4, height: 4 } });
  return page.evaluate(async (base64) => {
    // an image from a data address is allowed by the page's own policy
    const image = new Image();
    image.src = `data:image/png;base64,${base64}`;
    await image.decode();
    const canvas = document.createElement('canvas');
    canvas.width = image.width;
    canvas.height = image.height;
    const pen = canvas.getContext('2d');
    pen.drawImage(image, 0, 0);
    const pixels = pen.getImageData(0, 0, image.width, image.height).data;
    let sum = 0;
    for (let i = 0; i < pixels.length; i += 4) sum += pixels[i] + pixels[i + 1] + pixels[i + 2];
    return sum / (pixels.length / 4) / 3;
  }, shot.toString('base64'));
}

test('the galaxy opens from the developer view: a dot for every file', SLOW, async (t) => {
  const { page, clean } = await open(t);
  const button = page.locator('[data-galaxy]');
  assert.equal(await button.count(), 0, 'a manager has no galaxy');
  await page.keyboard.press('g');
  assert.equal(await data(page, 'tab'), 'world');
  await page.getByRole('button', { name: 'Developer' }).click();
  await button.click();
  await drawnDots(page);
  const inside = await model(page);
  assert.equal(Number(await data(page, 'dots')), inside.files.length);
  assert.equal(await data(page, 'lit'), '0');
  assert.equal(await data(page, 'tab'), 'code');
  assert.equal(await button.getAttribute('aria-pressed'), 'true');
  assert.equal(new URL(page.url()).hash, '#g&v=dev');
  assert.equal(await page.title(), 'Code galaxy · StockAgent architecture');
  assert.equal(await page.locator('.panel').count(), 0);
  const balls = [...new Set(inside.files.map(ballOf))];
  for (const id of balls) {
    assert.equal(await page.locator(`.label-anchor[data-label="ball-${id}"]`).count(), 1, id);
  }
  // the world's names are gone, and the legend gains the shared files
  assert.equal(await page.locator('.label-anchor[data-label="S.paper"]').count(), 0);
  assert.equal(await page.locator('.legend a[data-module]').count(), inside.modules.length + 1);
  assert.match(await page.locator('.code-key').textContent(),
    new RegExp(`^${inside.files.length} Python files`));
  // G leaves and comes back; the world is as it was
  await page.keyboard.press('g');
  await page.waitForSelector('[data-app][data-tab="world"]:not([data-dots])');
  assert.equal(await page.locator('.label-anchor[data-label="M5"]').count(), 1);
  assert.equal(new URL(page.url()).hash, '#v=dev');
  await page.keyboard.press('G');
  await drawnDots(page);
  clean();
});

test('selecting M5 lights its files, in the galaxy and back in the world', SLOW, async (t) => {
  // a wide window, so single dots can still be looked at beside the panel
  const { page, clean } = await open(t, { hash: '#g', size: [1800, 1100] });
  await drawnDots(page);
  assert.equal(await data(page, 'audience'), 'developer');
  assert.equal(new URL(page.url()).hash, '#g&v=dev', 'the address says which view');
  const inside = await model(page);
  const mine = inside.files.filter((f) => ballOf(f) === 'M5').map((f) => f.path);
  const dots = await dotsOnScreen(page);
  // measured where nothing else stands, before and after
  const others = (await clearOf(page, dots, dots.filter((d) => d.cluster !== 'M5'), 6)).slice(0, 20);
  const was = new Map();
  for (const dot of others) was.set(dot.path, await brightness(page, dot));
  assert.ok(others.length >= 4 && [...was.values()].every((v) => v > 60), `dots, not the sky: ${[...was.values()]}`);
  await page.locator('.legend [data-module="M5"]').click();
  await page.waitForSelector('[data-panel="code"][data-code="M5"]');
  await lit(page, mine.length);
  assert.equal(new URL(page.url()).hash, '#g&m=M5&v=dev');
  assert.equal(await panelFiles(page).count(), mine.length);
  assert.match(await page.locator('.panel .summary').textContent(),
    new RegExp(`^${mine.length} Python files, `));
  assert.match(await page.locator('.label-anchor[data-label="ball-M5"] .label')
    .getAttribute('class'), /selected/);
  assert.match(await page.locator('.label-anchor[data-label="ball-M11"] .label')
    .getAttribute('class'), /faded/);
  // in the narrower view: the same dots are dim now, and a dot of M5 is bright
  const after = await dotsOnScreen(page);
  const dimmed = await clearOf(page, after, after.filter((d) => was.has(d.path)), 6);
  assert.ok(dimmed.length >= 2, 'dots of other modules to look at again');
  // M5's dots stand close and carry names: the brightest of those in sight
  let high = 0;
  for (const dot of after.filter((d) => d.cluster === 'M5')) {
    if (await onView(page, dot)) high = Math.max(high, await brightness(page, dot));
  }
  for (const dot of dimmed) {
    const low = await brightness(page, dot);
    assert.ok(low < was.get(dot.path) * 0.6, `${dot.path} fades (${was.get(dot.path)} to ${low})`);
    assert.ok(high > low * 2, `M5's dots stand out (${high} against ${low})`);
  }
  // to the world: M5 is selected there, and G brings its files back
  await page.getByRole('button', { name: 'Show M5 in the world' }).click();
  await page.waitForSelector('[data-panel="M5"]');
  assert.equal(await data(page, 'tab'), 'world');
  assert.equal(new URL(page.url()).hash, '#m=M5&v=dev');
  assert.match((await focus(page)).text, /^M5 /, 'focus moves into what was opened');
  await page.keyboard.press('g');
  await lit(page, mine.length);
  await page.waitForSelector('[data-panel="code"][data-code="M5"]');
  // from a module's list to a file and back: the focus follows from panel to panel
  await panelFiles(page).locator('a').first().focus();
  await page.keyboard.press('Enter');
  await page.waitForSelector('[data-panel="file"]');
  await page.waitForFunction(() => document.activeElement.tagName === 'H2');
  await page.goBack();
  await page.waitForSelector('[data-panel="code"][data-code="M5"]');
  await page.waitForFunction(() => document.activeElement.textContent === 'M5 Portfolio: its code',
    null, { timeout: 5000 });
  // a module's panel leads to its neighbours' code
  const first = section(page, 'What imports it from outside').locator('li a').first();
  const name = await first.textContent();
  await first.click();
  await page.waitForSelector(`[data-panel="code"][data-code="${name.split(' ')[0]}"]`);
  clean();
});

test('searching advisor.py opens its panel; its imports lead on and back', SLOW, async (t) => {
  const { page, clean } = await open(t, { hash: '#g' });
  await drawnDots(page);
  const inside = await model(page);
  const advisor = fileOf(inside, ADVISOR);
  const users = importersOf(inside, ADVISOR);
  await page.keyboard.press('/');
  await page.waitForSelector('dialog.search[open]');
  await page.keyboard.type('advisor.py');
  await page.keyboard.press('Enter');
  await page.waitForSelector(`[data-panel="file"][data-file="${ADVISOR}"]`);
  await lit(page, new Set([ADVISOR, ...advisor.imports, ...users]).size);
  const panel = page.locator('.panel');
  assert.equal(await panel.locator('h2').textContent(), 'advisor.py');
  const at = await focus(page);
  assert.deepEqual([at.tag, at.text, at.ring], ['H2', 'advisor.py', true]);
  assert.equal(await page.title(), 'advisor.py · Code galaxy · StockAgent architecture');
  assert.equal(new URL(page.url()).hash, `#g&f=${ADVISOR}&v=dev`);
  const text = await panel.textContent();
  assert.ok(text.includes(`${advisor.lines.toLocaleString('en-US')} lines. Part of M5.2 Advisor.`));
  const listed = async (title) => (await section(page, title).locator('li code').allTextContents())
    .sort();
  assert.deepEqual(await listed(`Imports (${advisor.imports.length})`), [...advisor.imports].sort());
  assert.deepEqual(await listed(`Imported by (${users.length})`), [...users].sort());
  assert.match(await page.locator('.code-key').textContent(), /Solid lines.*Dashed/);
  // the chosen file is named in the galaxy, and the legend marks its module
  assert.match(await page.locator(`.label-anchor[data-label="file:${ADVISOR}"] .label`)
    .getAttribute('class'), /selected/);
  assert.equal(await page.locator('.legend [data-module="M5"]').getAttribute('aria-current'), 'true');
  // follow the first import, from the keyboard
  const next = advisor.imports.slice().sort()[0];
  await section(page, `Imports (${advisor.imports.length})`).locator('li a').first().focus();
  await page.keyboard.press('Enter');
  await page.waitForSelector(`[data-panel="file"][data-file="${next}"]`);
  assert.equal((await focus(page)).tag, 'H2');
  assert.ok(await section(page, `Imported by (${importersOf(inside, next).length})`)
    .locator('li code', { hasText: ADVISOR }).count());
  await page.goBack();
  await page.waitForSelector(`[data-panel="file"][data-file="${ADVISOR}"]`);
  await page.waitForFunction(() => document.activeElement.tagName === 'H2'
    && document.activeElement.textContent === 'advisor.py', null, { timeout: 5000 });
  await page.goForward();
  await page.waitForSelector(`[data-panel="file"][data-file="${next}"]`);
  await page.reload();
  await page.waitForSelector(`[data-panel="file"][data-file="${next}"]`);
  await drawnDots(page);
  // the file shows its module in the world
  await page.goto(`${page.url().split('#')[0]}#g&f=${ADVISOR}`);
  await page.waitForSelector(`[data-panel="file"][data-file="${ADVISOR}"]`);
  await page.getByRole('button', { name: 'Show M5.2 in the world' }).click();
  await page.waitForSelector('[data-panel="M5.2"]');
  assert.equal(await data(page, 'selected'), 'M5.2');
  clean();
});

test('pointing at a dot names it, a click opens it, and a drag chooses nothing', SLOW, async (t) => {
  const { page, clean } = await open(t, { hash: '#g' });
  await drawnDots(page);
  const dots = await dotsOnScreen(page);
  // the rightmost of the clear dots: out of the picture if the view were not framed again
  const target = (await clearOf(page, dots, dots)).sort((a, b) => b.x - a.x)[0];
  assert.ok(target, 'a dot nothing covers');
  await page.mouse.move(target.x, target.y);
  await page.waitForSelector('.tooltip');
  assert.ok((await page.locator('.tooltip').textContent()).startsWith(target.path));
  assert.ok(await page.locator('.world.pointing').count());
  // a small dot is a 24 px target: just outside its disc still names it, where no other dot
  // is as near
  const beside = (d) => ({ x: d.x + d.onScreen + 2.5, y: d.y });
  let small = null;
  for (const d of dots.filter((o) => o.onScreen < 9)) {
    const at = beside(d);
    const alone = dots.every((o) => o.path === d.path
      || Math.hypot(o.x - at.x, o.y - at.y) > Math.max(o.onScreen, 12) + 2);
    if (alone && await onView(page, at)) { small = d; break; }
  }
  assert.ok(small, 'a small dot with room beside it');
  await page.mouse.move(beside(small).x, beside(small).y);
  await page.waitForFunction((path) => document.querySelector('.tooltip strong')?.textContent
    === path, small.path);
  await page.mouse.move(target.x, target.y);
  await page.waitForFunction((path) => document.querySelector('.tooltip strong')?.textContent
    === path, target.path);
  const inside = await model(page);
  // a drag from the dot turns the view and chooses nothing
  const was = await data(page, 'camera');
  await page.mouse.down();
  await page.mouse.move(target.x + 120, target.y + 30, { steps: 6 });
  await page.mouse.up();
  await settled(page, was);
  assert.equal(await page.locator('.panel').count(), 0);
  assert.equal(await data(page, 'file'), '');
  await page.keyboard.press('r');
  await page.waitForFunction((camera) => document.querySelector('[data-app]').dataset.camera
    === camera, was);
  // a drag out and back ends on the same dot, and still chooses nothing
  await page.mouse.move(target.x, target.y);
  await page.mouse.down();
  await page.mouse.move(target.x - 90, target.y, { steps: 5 });
  await page.mouse.move(target.x, target.y, { steps: 5 });
  await page.mouse.up();
  await page.waitForTimeout(400);
  assert.equal(await data(page, 'file'), '', 'a drag is no click');
  await page.keyboard.press('r');
  await page.waitForFunction((camera) => document.querySelector('[data-app]').dataset.camera
    === camera, was);
  await page.mouse.click(target.x, target.y);
  await page.waitForSelector(`[data-panel="file"][data-file="${target.path}"]`);
  // the panel narrowed the view, and the galaxy is framed for it: a click is no drag
  const narrowed = (await dotsOnScreen(page)).find((d) => d.path === target.path);
  const room = await page.locator('canvas').boundingBox();
  assert.ok(narrowed.x > room.x && narrowed.x < room.x + room.width, 'the chosen file is in view');
  assert.equal(await page.locator('.panel .summary').textContent(), target.path);
  assert.equal(await data(page, 'selected'), fileOf(inside, target.path).owner);
  assert.equal(await page.locator('.tooltip').count(), 0);
  // empty space chooses nothing and keeps what is chosen
  const view = await page.locator('canvas').boundingBox();
  await page.mouse.click(view.x + 5, view.y + 5);
  await page.waitForTimeout(300);
  assert.equal(await data(page, 'file'), target.path);
  // a view the person turned is theirs: choosing and closing move no camera
  await page.mouse.move(view.x + 30, view.y + 30);
  await page.mouse.down();
  await page.mouse.move(view.x + 90, view.y + 50, { steps: 4 });
  await page.mouse.up();
  await still(page);
  const turned = await data(page, 'camera');
  await page.keyboard.press('Escape');
  await page.waitForSelector('.panel', { state: 'detached' });
  await page.waitForFunction(() => Math.abs(document.querySelector('canvas').clientWidth
    - document.querySelector('main.world').clientWidth) <= 1);
  await page.waitForTimeout(600);
  assert.equal(await data(page, 'camera'), turned);
  await page.keyboard.press('r');
  await still(page);
  // a file's name in the galaxy opens it too
  const label = page.locator('.label-anchor[data-label^="file:"] button:visible').filter({
    hasNotText: target.path.split('/').at(-1) }).first();
  const named = await label.getAttribute('data-target');
  await label.click();
  await page.waitForSelector(`[data-panel="file"][data-file="${named}"]`);
  clean();
});

test('the developer panel of the world leads to its files in the galaxy', SLOW, async (t) => {
  const { page, clean } = await open(t, { hash: '#m=M5.2&v=dev' });
  await page.waitForSelector('[data-panel="M5.2"]');
  const inside = await model(page);
  const mine = inside.files.filter((f) => f.owner === 'M5.2');
  await page.getByRole('link', { name: 'Show its code in the galaxy' }).click();
  await page.waitForSelector('[data-panel="code"][data-code="M5.2"]');
  await lit(page, mine.length);
  assert.equal(await panelFiles(page).count(), mine.length);
  await page.goBack();
  await page.waitForSelector('[data-panel="M5.2"]');
  assert.equal(await data(page, 'tab'), 'world');
  await section(page, 'Where it lives').locator('a', { hasText: ADVISOR }).click();
  await page.waitForSelector(`[data-panel="file"][data-file="${ADVISOR}"]`);
  await drawnDots(page);
  // the manager view has no galaxy: changing to it shows the module in the world
  await page.getByRole('button', { name: 'Manager' }).click();
  await page.waitForSelector('[data-panel="M5.2"]');
  assert.equal(await data(page, 'tab'), 'world');
  assert.equal(await page.getByRole('link', { name: 'Show its code in the galaxy' }).count(), 0);
  await page.goBack();
  await page.waitForSelector(`[data-panel="file"][data-file="${ADVISOR}"]`);
  assert.equal(await data(page, 'audience'), 'developer');
  clean();
});

test('the world and the galaxy pass the focus and a search on', SLOW, async (t) => {
  const { page, clean } = await open(t, { hash: '#m=M5.2&v=dev' });
  await page.waitForSelector('[data-panel="M5.2"]');
  const inside = await model(page);
  // G from inside the world's panel: the focus follows into the galaxy's panel
  await page.getByRole('button', { name: 'Wider panel' }).focus();
  await page.keyboard.press('g');
  await page.waitForSelector('[data-panel="code"][data-code="M5.2"]');
  await page.waitForFunction(() => document.activeElement.tagName === 'H2');
  // and from a mode's player to the galaxy's button
  await page.keyboard.press('5');
  await page.waitForSelector('.player');
  await page.locator('.player').getByRole('button', { name: 'Play' }).focus();
  await page.keyboard.press('g');
  await page.waitForSelector('[data-app][data-tab="code"]');
  await page.waitForFunction(() => document.activeElement.hasAttribute('data-galaxy'));
  // a developer's search for a module's own file, which no world panel lists, opens the galaxy
  await page.keyboard.press('g');
  await page.waitForSelector('[data-app][data-tab="world"]');
  const own = inside.files.find((f) => /^M\d+$/.test(f.owner));
  const find = async (path) => {
    // the last search is shut: a key pressed while it is still open is ignored
    await page.waitForSelector('dialog.search', { state: 'hidden' });
    await page.keyboard.press('/');
    await page.waitForSelector('dialog.search[open]');
    assert.equal(await page.locator('#search-input').inputValue(), '', 'it opens empty');
    await page.keyboard.type(path);
    await page.keyboard.press('Enter');
  };
  await find(own.path);
  await page.waitForSelector(`[data-panel="file"][data-file="${own.path}"]`);
  // a "closed" event left over from an earlier search does not shut the one now open
  await page.waitForSelector('dialog.search', { state: 'hidden' });
  await page.keyboard.press('/');
  await page.waitForSelector('dialog.search[open]');
  await page.evaluate(() => document.querySelector('dialog.search')
    .dispatchEvent(new Event('close')));
  await page.waitForTimeout(300);
  assert.equal(await page.locator('dialog.search[open]').count(), 1);
  await page.keyboard.press('Escape');
  await page.waitForSelector('dialog.search', { state: 'hidden' });
  // a part's file stays in the world, which lists it
  await page.keyboard.press('Escape');
  await page.keyboard.press('Escape');
  await page.waitForSelector('[data-app][data-tab="world"]');
  await find(ADVISOR);
  await page.waitForSelector('[data-panel="M5.2"]');
  assert.equal(await data(page, 'tab'), 'world');
  // a manager's search stays in the world for a module's file; a shared file lives only in the galaxy
  await page.getByRole('button', { name: 'Manager' }).click();
  await find(own.path);
  await page.waitForSelector(`[data-panel="${own.owner}"]`);
  assert.equal(await data(page, 'audience'), 'manager');
  const shared = inside.files.find((f) => f.owner === 'shared');
  await find(shared.path);
  await page.waitForSelector(`[data-panel="file"][data-file="${shared.path}"]`);
  assert.equal(await data(page, 'audience'), 'developer');
  clean();
});

test('the galaxy works from the keyboard: legend, views, Esc, the clock and addresses', SLOW,
  async (t) => {
    const { page, clean } = await open(t, { hash: '#g' });
    await drawnDots(page);
    const inside = await model(page);
    let at = await focus(page);
    for (let i = 0; i < 40 && at.module !== 'shared'; i += 1) {
      await page.keyboard.press('Tab');
      at = await focus(page);
    }
    assert.equal(at.module, 'shared');
    assert.ok(at.ring);
    await page.keyboard.press('Enter');
    await page.waitForSelector('[data-panel="code"][data-code="shared"]');
    const shared = inside.files.filter((f) => f.owner === 'shared');
    await lit(page, shared.length);
    assert.equal(await panelFiles(page).count(), shared.length);
    assert.equal(await page.locator('.panel .to-world').count(), 0, 'no block in the world');
    // Esc closes the panel and gives the focus back; a view key stays in the galaxy
    await page.keyboard.press('Escape');
    await page.waitForSelector('.panel', { state: 'detached' });
    assert.equal((await focus(page)).module, 'shared');
    assert.equal(await data(page, 'tab'), 'code');
    await lit(page, 0);
    // the view has its full width again
    await page.waitForTimeout(600);
    await still(page);
    const front = await data(page, 'camera');
    for (const [key, preset] of [['2', 'top'], ['3', 'side'], ['4', 'below']]) {
      const before = await data(page, 'camera');
      await page.keyboard.press(key);
      await settled(page, before);
      assert.deepEqual([await data(page, 'tab'), await data(page, 'preset')], ['code', preset]);
    }
    await page.keyboard.press('r');
    await page.waitForFunction((camera) => document.querySelector('[data-app]').dataset.camera
      === camera, front);
    // choosing flies nowhere: from one panel to another the camera stays
    await page.locator('.legend [data-module="M3"]').focus();
    await page.keyboard.press('Enter');
    await page.waitForSelector('[data-panel="code"][data-code="M3"]');
    await page.waitForTimeout(600);
    await still(page);
    const there = await data(page, 'camera');
    await page.locator('.legend [data-module="M9"]').click();
    await page.waitForSelector('[data-panel="code"][data-code="M9"]');
    await page.waitForTimeout(600);
    assert.equal(await data(page, 'camera'), there);
    // a second Esc, with nothing chosen, goes back to the world
    await page.keyboard.press('Escape');
    await page.waitForSelector('.panel', { state: 'detached' });
    await page.keyboard.press('Escape');
    await page.waitForSelector('[data-app][data-tab="world"]');
    assert.equal(await page.locator('.panel').count(), 0);
    // 5 leaves the galaxy for the clock, and a story button does too
    await page.keyboard.press('g');
    await drawnDots(page);
    await page.keyboard.press('5');
    await page.waitForSelector('[data-app][data-tab="world"][data-mode="clock"]');
    await page.locator('[data-galaxy]').click();
    await drawnDots(page);
    assert.equal(await data(page, 'mode'), '');
    assert.equal(await page.locator('.player').count(), 0);
    await page.locator('[data-story="trace"]').click();
    await page.waitForSelector('[data-app][data-tab="world"][data-mode="trace"]');
    await page.goBack();
    await page.waitForSelector('[data-app][data-tab="code"]');
    // the 3D view turns from the keyboard
    await page.locator('.world').focus();
    const before = await data(page, 'camera');
    await page.keyboard.press('ArrowLeft');
    await settled(page, before);
    // an unknown file says so and still shows the galaxy
    await page.evaluate(() => { window.location.hash = '#g&f=core/no_such.py'; });
    await page.waitForSelector('.world .notice');
    assert.match(await page.locator('.world .notice').textContent(), /core\/no_such\.py/);
    assert.equal(await data(page, 'tab'), 'code');
    assert.equal(await page.locator('.panel').count(), 0);
    // no page scrolling, with a panel open too
    for (const size of [[1280, 720], [2200, 1200]]) {
      await page.setViewportSize({ width: size[0], height: size[1] });
      await page.evaluate((path) => { window.location.hash = `#g&f=${path}`; }, ADVISOR);
      await page.waitForSelector('[data-panel="file"]');
      const scroll = await page.evaluate(() => [
        document.documentElement.scrollWidth - window.innerWidth,
        document.documentElement.scrollHeight - window.innerHeight]);
      assert.deepEqual(scroll, [0, 0], `${size}`);
      const key = await page.locator('.code-key').boundingBox();
      const world = await page.locator('.world').boundingBox();
      assert.ok(key.x >= world.x && key.x + key.width <= world.x + world.width + 0.5, `${size}`);
    }
    clean();
  });

test('without WebGL the galaxy’s panels still list every file', SLOW, async (t) => {
  const context = await theBrowser().newContext({ viewport: { width: 1280, height: 800 },
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
  await page.goto(`${PAGE}#g`);
  assert.match(await page.getByRole('alert').textContent(), /needs WebGL.*every file/);
  assert.equal(await page.locator('canvas').count(), 0);
  assert.equal(await page.locator('.code-key').count(), 0);
  const inside = await model(page);
  const seen = new Set();
  for (const id of [...new Set(inside.files.map(ballOf))]) {
    await page.locator(`.legend [data-module="${id}"]`).click();
    await page.waitForSelector(`[data-panel="code"][data-code="${id}"]`);
    for (const path of await panelFiles(page).locator('code').allTextContents()) seen.add(path);
  }
  assert.deepEqual([...seen].sort(), inside.files.map((f) => f.path).sort());
  await panelFiles(page).locator('a').first().click();
  await page.waitForSelector('[data-panel="file"]');
  assert.deepEqual(wrong, []);
});

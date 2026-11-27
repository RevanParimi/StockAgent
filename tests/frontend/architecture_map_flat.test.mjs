/**
 * MAP-005: the committed map without a 3D view, and on a phone. Opened from disk with the
 * network off, as someone double-clicking the file would. Nothing here draws in 3D but one
 * test, so it is light.
 *
 *   node --test tests/frontend/architecture_map_flat.test.mjs
 *
 * Every page records its console errors and every request it makes; a test that leaves
 * either behind fails. What is on the map is read from the model inside the page.
 */
import { test } from 'node:test';
import assert from 'node:assert/strict';

import { SLOW, data, focus, model, open, useBrowser } from './architecture_map_harness.mjs';
import { moments } from '../../tools/architecture_map/viewer/src/lib/play.js';

useBrowser();

const PHONE = [390, 844];
const flat = (t, options = {}) => open(t, { webgl: false, ...options });
const drawn = (page, id) => page.waitForSelector(
  `.flowchart[data-flowchart="${id}"][data-ready="true"]`, { timeout: 90_000 });
const card = (page, id) => page.locator(`.flat a[data-card="${id}"], .flat g[data-card="${id}"]`);
const states = (page) => page.locator('.flat [data-card]').evaluateAll((all) => Object.fromEntries(
  all.map((el) => [el.dataset.card, el.dataset.state])));
const levels = (page) => page.locator('.flat [data-flow]').evaluateAll((all) => Object.fromEntries(
  all.map((el) => [el.dataset.flow, el.dataset.level])));
const scale = (page) => page.locator('.flat-scroll svg').getAttribute('data-scale').then(Number);
/** Waits until the map's size follows the box it stands in now. The map hears of a new
 *  width on the next frame and draws it after that, and shows the old size until then:
 *  two frames pass first, so that nothing is still on its way. The limits of the fit are
 *  FlatMap.jsx's (a change there shows as this wait timing out); the size is written to
 *  two decimals, hence the margin. */
const measured = async (page) => {
  await page.evaluate(() => new Promise((done) => {
    requestAnimationFrame(() => requestAnimationFrame(() => setTimeout(done, 0)));
  }));
  await page.waitForFunction(() => {
    const box = document.querySelector('.flat-scroll');
    const svg = box.querySelector('svg');
    const fit = Math.min(1.4, Math.max(0.75, box.clientWidth / svg.viewBox.baseVal.width));
    return Math.abs(Number(svg.dataset.scale) - fit) <= 0.01;
  });
};
const sideways = (page) => page.evaluate(
  () => document.documentElement.scrollWidth - window.innerWidth);
/** No card's words reach past its box. */
const wordsFit = async (page, where) => {
  const over = await page.locator('.flat [data-card]').evaluateAll((all) => all.flatMap((el) => {
    const box = el.querySelector('.flat-box').getBBox();
    const words = el.querySelector('text').getBBox();
    return words.x < box.x - 0.5 || words.x + words.width > box.x + box.width + 0.5
      || words.y < box.y - 0.5 || words.y + words.height > box.y + box.height + 0.5
      ? [`${el.dataset.card}: ${Math.round(words.x + words.width)} of ${box.width}`] : [];
  }));
  assert.deepEqual(over, [], where);
};
const stampSeen = async (page, inside, where) => {
  const stamp = page.locator('.stamp');
  assert.ok((await stamp.textContent())
    .includes(`Code inspected: ${inside.stamp.commit.slice(0, 7)}`), where);
  assert.ok(await stamp.isVisible(), where);
};

test('without WebGL the flat map holds the whole model and says why it is flat', SLOW,
  async (t) => {
    const { page, clean } = await flat(t);
    const inside = await model(page);
    assert.equal(await page.locator('canvas').count(), 0);
    assert.equal(await data(page, 'view-kind'), 'flat');
    assert.match(await page.getByRole('alert').textContent(), /needs WebGL.*flat map/);
    for (const item of [...inside.modules, ...inside.externals, ...inside.stores]) {
      assert.equal(await card(page, item.id).count(), 1, item.id);
    }
    assert.equal(await page.locator('.flat [data-flow]').count(), inside.flows.length);
    // a module and a store are links; an outside party is not
    assert.equal(await card(page, 'M5').getAttribute('href'), '#m=M5');
    assert.equal(await card(page, 'ext.owner').evaluate((el) => el.tagName), 'g');
    // no 3D-only control, and the page's stamp is there
    assert.equal(await page.getByRole('button', { name: 'Pause motion' }).count(), 0);
    await stampSeen(page, inside, 'flat');
    // pointing at a flow says what travels on it
    const first = inside.flows[0];
    assert.ok((await page.locator(`.flat [data-flow="${first.from}>${first.to}"] title`)
      .textContent()).endsWith(first.what));
    // a laptop and a wide screen need no page scrolling, up and down or sideways
    for (const [width, height] of [[1280, 720], [2200, 1200]]) {
      await page.setViewportSize({ width, height });
      assert.deepEqual(await page.evaluate(() => [
        document.documentElement.scrollWidth - window.innerWidth,
        document.documentElement.scrollHeight - window.innerHeight]), [0, 0], `${width}`);
    }
    await wordsFit(page, 'wide');
    clean();
  });

test('every part’s panel opens with its flowchart and no console error', { timeout: 600_000 },
  async (t) => {
    const { page, clean } = await flat(t, { hash: '#m=M1' });
    const inside = await model(page);
    const parts = inside.modules.flatMap((m) => m.submodules);
    assert.ok(parts.length >= 51, `${parts.length} parts`);
    for (const part of parts) {
      await page.evaluate((hash) => { window.location.hash = hash; }, `#m=${part.id}`);
      await page.waitForSelector(`[data-panel="${part.id}"]`);
      await drawn(page, part.id);
      const chart = page.locator(`.flowchart[data-flowchart="${part.id}"]`);
      assert.equal(await chart.locator('svg').count(), part.logic.length, part.id);
      assert.equal(await chart.locator('.notice').count(), 0, part.id);
      // the card of its module is chosen on the map
      assert.equal(await card(page, part.id.split('.')[0]).getAttribute('data-state'),
        'selected', part.id);
    }
    // and every module's own panel
    for (const module of inside.modules) {
      await page.evaluate((hash) => { window.location.hash = hash; }, `#m=${module.id}&v=dev`);
      await page.waitForSelector(`[data-panel="${module.id}"]`);
    }
    clean();
  });

test('choosing a card opens its panel, lights what it touches and lists its parts', SLOW,
  async (t) => {
    const { page, clean } = await flat(t);
    const inside = await model(page);
    await card(page, 'M5').click();
    await page.waitForSelector('[data-panel="M5"]');
    assert.equal(new URL(page.url()).hash, '#m=M5');
    const shown = await states(page);
    assert.equal(shown.M5, 'selected');
    // M8 and M5 share no flow; M3 flows into M5
    assert.equal(shown.M8, 'faded');
    assert.equal(shown.M3, 'rest');
    assert.equal(shown['S.advice'], 'near');
    assert.equal(shown['S.chat'], 'faded');
    const flows = await levels(page);
    for (const flow of inside.flows) {
      const touches = [flow.from, flow.to].includes('M5');
      assert.equal(flows[`${flow.from}>${flow.to}`], touches ? 'bright' : 'faded',
        `${flow.from}>${flow.to}`);
    }
    assert.equal(await page.locator('.flat [data-pipe="M5>S.advice"].bright').count(), 1);
    assert.equal(await page.locator('.flat [data-pipe="M10>S.chat"].off').count(), 1);
    const parts = inside.modules.find((m) => m.id === 'M5').submodules;
    assert.deepEqual(await page.locator('.flat-parts a').evaluateAll(
      (all) => all.map((a) => a.dataset.flatPart)), parts.map((s) => s.id));
    await page.locator('.flat-parts a[data-flat-part="M5.2"]').click();
    await drawn(page, 'M5.2');
    assert.equal(await page.locator('.flat-parts a[aria-current="true"]').getAttribute('data-flat-part'),
      'M5.2');
    // a store card opens the part that writes it; Back returns
    await card(page, 'S.cases').click();
    await page.waitForSelector('[data-panel="M5.5"]');
    await page.goBack();
    await page.waitForSelector('[data-panel="M5.2"]');
    // a deep link opens the same thing
    await page.reload();
    await page.waitForSelector('[data-panel="M5.2"]');
    assert.equal((await states(page)).M5, 'selected');
    clean();
  });

test('the flat map works from the keyboard alone, focus always seen', SLOW, async (t) => {
  const { page, clean } = await flat(t);
  await page.keyboard.press('Tab');
  assert.match((await focus(page)).text, /^Skip to the list of modules/);
  // Tab to the card of M5, every stop on the way showing its focus
  const at = () => page.evaluate(() => document.activeElement.dataset.card ?? '');
  for (let i = 0; i < 60 && (await at()) !== 'M5'; i += 1) {
    assert.ok((await focus(page)).ring, `no focus ring on ${(await focus(page)).text}`);
    await page.keyboard.press('Tab');
  }
  assert.equal(await at(), 'M5');
  assert.ok((await focus(page)).ring);
  await page.keyboard.press('Enter');
  await page.waitForSelector('[data-panel="M5"]');
  await page.keyboard.press('Escape');
  await page.waitForSelector('.panel', { state: 'detached' });
  assert.equal(await at(), 'M5', 'Esc gives the focus back to the card');
  // + and − change the size, from the map
  await measured(page);
  const before = await scale(page);
  await page.keyboard.press('+');
  await page.waitForFunction((was) => Number(document.querySelector('.flat-scroll svg')
    .dataset.scale) > was, before);
  const bigger = await scale(page);
  await page.keyboard.press('-');
  await page.waitForFunction((was) => Number(document.querySelector('.flat-scroll svg')
    .dataset.scale) < was, bigger);
  await page.getByRole('button', { name: 'Fit' }).click();
  assert.equal(await scale(page), before);
  // the views change what stands out, and nothing moves
  const places = () => page.locator('.flat [data-card]').evaluateAll(
    (all) => all.map((el) => el.getAttribute('transform')));
  const front = await places();
  await page.keyboard.press('4');
  await page.waitForSelector('[data-app][data-preset="below"]');
  assert.ok(Object.values(await levels(page)).every((level) => level === 'dim'));
  assert.ok(await page.locator('.flat [data-pipe].show').count() > 10);
  assert.equal((await states(page))['S.advice'], 'near');
  await page.keyboard.press('2');
  await page.waitForSelector('[data-app][data-preset="top"]');
  assert.equal((await states(page))['S.advice'], 'faded');
  await page.keyboard.press('r');
  await page.waitForSelector('[data-app][data-preset="front"]');
  assert.deepEqual(await places(), front);
  // search and help work the same
  await page.keyboard.press('/');
  await page.waitForSelector('dialog.search[open]');
  await page.keyboard.type('advisor');
  await page.keyboard.press('Enter');
  await page.waitForSelector('[data-panel="M5.2"]');
  await page.waitForSelector('dialog.search', { state: 'hidden' });
  assert.equal((await focus(page)).tag, 'H2');
  await page.keyboard.press('Shift+Slash');
  await page.waitForSelector('dialog.help[open]');
  assert.match(await page.locator('dialog.help').textContent(), /the map is flat/);
  await page.keyboard.press('Escape');
  await page.waitForSelector('dialog.help', { state: 'hidden' });
  clean();
});

test('a dialog asked for again before the browser has caught up still opens', SLOW,
  async (t) => {
    const { page, clean } = await flat(t, { hash: '#v=dev' });
    // Esc shuts a dialog at once, but the page hears of it only on the next frame. Here it
    // is shut and asked for again in one go, so that no frame can come between.
    const shutAndAsk = (kind, ask) => page.evaluate(([name, how]) => {
      document.querySelector(`dialog.${name}`).close();
      if (how === 'button') {
        [...document.querySelectorAll('.topbar button[aria-haspopup="dialog"]')]
          .find((b) => b.textContent.trim().toLowerCase().startsWith(name)).click();
      } else {
        document.body.dispatchEvent(new KeyboardEvent('keydown', { key: how, bubbles: true }));
      }
    }, [kind, ask]);
    const staysOpen = async (kind) => {
      await page.waitForSelector(`dialog.${kind}[open]`);
      // the late report of the old closing must not shut the new one
      await page.waitForTimeout(300);
      assert.equal(await page.locator(`dialog.${kind}[open]`).count(), 1, kind);
    };
    await page.keyboard.press('/');
    await page.waitForSelector('dialog.search[open]');
    await page.keyboard.type('advisor');
    await shutAndAsk('search', '/');
    await staysOpen('search');
    assert.equal(await page.locator('#search-input').inputValue(), '', 'it opens empty');
    await shutAndAsk('search', 'button');
    await staysOpen('search');
    await page.keyboard.press('Escape');
    await page.waitForSelector('dialog.search', { state: 'hidden' });
    await page.keyboard.press('Shift+Slash');
    await page.waitForSelector('dialog.help[open]');
    await shutAndAsk('help', '?');
    await staysOpen('help');
    await shutAndAsk('help', 'button');
    await staysOpen('help');
    clean();
  });

test('keys pressed right after Esc are the page’s, not typing in the shut dialog', SLOW,
  async (t) => {
    const { page, clean } = await flat(t, { hash: '#v=dev' });
    // A search opened with nothing focused has nowhere to give the focus back to: the
    // shut dialog's field keeps it until the next frame. Real keys, one after another.
    const openThenEsc = async () => {
      await page.evaluate(() => document.activeElement?.blur());
      await page.keyboard.press('/');
      await page.waitForSelector('dialog.search[open]');
      await page.waitForTimeout(300);
      await page.keyboard.press('Escape');
    };
    await openThenEsc();
    await page.keyboard.press('/');
    await page.waitForSelector('dialog.search[open]');
    assert.equal(await page.locator('#search-input').inputValue(), '',
      'the "/" that opens it is not typed into it');
    await page.keyboard.press('Escape');
    await page.waitForSelector('dialog.search', { state: 'hidden' });
    // a view key does its work, and the search stays empty
    await openThenEsc();
    await page.keyboard.press('2');
    await page.waitForSelector('[data-app][data-preset="top"]');
    assert.equal(await page.locator('#search-input').inputValue(), '');
    // the same with no frame at all between the closing and the key: the focus is still
    // in the shut field
    await openThenEsc();
    await page.waitForSelector('dialog.search', { state: 'hidden' });
    await page.keyboard.press('/');
    await page.waitForSelector('dialog.search[open]');
    await page.evaluate(() => {
      const field = document.getElementById('search-input');
      field.focus();
      document.querySelector('dialog.search').close();
      if (document.activeElement !== field) throw new Error('the field gave the focus up');
      field.dispatchEvent(new KeyboardEvent('keydown', { key: '/', bubbles: true }));
    });
    await page.waitForSelector('dialog.search[open]');
    clean();
  });

test('the clock, the trace and the tour light the flat map step by step', SLOW, async (t) => {
  const { page, clean } = await flat(t, { hash: '#p=clock&s=1' });
  const inside = await model(page);
  const day = moments(inside);
  for (const [index, moment] of day.entries()) {
    await page.evaluate((hash) => { window.location.hash = hash; }, `#p=clock&s=${index + 1}`);
    await page.waitForSelector(`[data-app][data-step="${index + 1}"]`);
    const shown = await states(page);
    const wanted = new Set(moment.job.lights.map((id) => (id.startsWith('M')
      ? id.split('.')[0] : id)));
    for (const [id, state] of Object.entries(shown)) {
      assert.equal(state, wanted.has(id) ? 'lit' : 'faded', `${moment.key} ${id}`);
    }
  }
  assert.equal(await page.locator('[data-panel="clock"] [data-moment]').count(), day.length);
  await stampSeen(page, inside, 'clock');
  for (const mode of ['trace', 'tour']) {
    const steps = (mode === 'trace' ? inside.traces : inside.tours)[0].steps.length;
    await page.evaluate((hash) => { window.location.hash = hash; }, `#p=${mode}&s=1`);
    await page.waitForSelector(`[data-app][data-mode="${mode}"][data-step="1"]`);
    for (let step = 2; step <= steps; step += 1) {
      await page.locator('.player').getByRole('button', { name: 'Next →' }).click();
      await page.waitForSelector(`[data-app][data-step="${step}"]`);
    }
    await page.locator('.player').getByRole('button', { name: 'Finish' }).click();
    await page.waitForSelector('[data-app][data-mode=""]');
  }
  clean();
});

test('P belongs to the 3D view: on the flat map it neither stops autoplay nor pauses motion',
  SLOW, async (t) => {
    // with motion allowed: with it reduced, P does nothing anywhere
    const { page, clean } = await flat(t, { hash: '#p=trace&s=1', motion: true });
    await page.locator('.player').getByRole('button', { name: 'Play' }).click();
    await page.waitForSelector('[data-app][data-playing="true"][data-motion="on"]');
    await page.keyboard.press('p');
    await page.waitForTimeout(500);
    assert.equal(await data(page, 'playing'), 'true');
    assert.equal(await data(page, 'motion'), 'on');
    await page.locator('.player').getByRole('button', { name: 'Pause' }).click();
    await page.waitForSelector('[data-app][data-playing="false"]');
    clean();
  });

test('the flat code galaxy counts every module’s files and opens their panels', SLOW,
  async (t) => {
    const { page, clean } = await flat(t, { hash: '#g&v=dev' });
    const inside = await model(page);
    assert.match(await page.getByRole('alert').textContent(), /every file/);
    let total = 0;
    for (const id of [...inside.modules.map((m) => m.id), 'shared']) {
      const words = await card(page, id).textContent();
      const count = Number(/(\d+) files?/.exec(words)[1]);
      const files = inside.files.filter((f) => f.owner.split('.')[0] === id).length;
      assert.equal(count, files, id);
      total += count;
    }
    assert.equal(total, inside.files.length);
    assert.equal(await page.locator('.flat [data-flow]').count(), 0);
    await wordsFit(page, 'code');
    await card(page, 'M5').click();
    await page.waitForSelector('[data-panel="code"][data-code="M5"]');
    assert.equal((await states(page)).M5, 'selected');
    assert.equal((await states(page)).M3, 'faded');
    await card(page, 'shared').click();
    await page.waitForSelector('[data-code="shared"]');
    await stampSeen(page, inside, 'galaxy');
    clean();
  });

test('on a phone the map is flat, fits the width and moves to what opens', SLOW, async (t) => {
  const { page, clean } = await open(t, { size: PHONE, tour: true });
  const inside = await model(page);
  assert.equal(await page.locator('canvas').count(), 0, 'nothing is drawn in 3D');
  assert.equal(await page.locator('.flat').getAttribute('data-flat'), 'narrow');
  assert.equal(await page.getByRole('status').filter({ hasText: 'narrow window' }).count(), 1);
  // the tour a manager starts on: its player stands above the map, and the page is not moved
  const box = async (what) => page.locator(what).boundingBox();
  assert.ok((await box('.player')).y < (await box('main.world')).y);
  assert.equal(await page.evaluate(() => window.scrollY), 0);
  assert.equal(await sideways(page), 0, 'tour');
  await page.keyboard.press('Escape');
  await page.waitForSelector('[data-app][data-mode=""]');
  await wordsFit(page, 'narrow');
  // targets are at least 24 px
  const small = await page.locator('button:visible, a:visible').evaluateAll((all) => all
    .map((el) => [el.textContent.trim().slice(0, 30), el.getBoundingClientRect()])
    .filter(([, r]) => r.height < 24 || r.width < 24).map(([name]) => name));
  assert.deepEqual(small, []);
  await stampSeen(page, inside, 'phone');
  // opening a card moves to its panel, closing moves back
  await card(page, 'M5').click();
  await page.waitForSelector('[data-panel="M5"]');
  await page.waitForFunction(() => {
    const top = document.querySelector('.panel').getBoundingClientRect().top;
    return top < 100 && top > -400;
  });
  assert.equal(await sideways(page), 0, 'a module');
  await page.locator('.panel a', { hasText: 'Advisor' }).first().click();
  await drawn(page, 'M5.2');
  assert.equal(await sideways(page), 0, 'a flowchart');
  await page.getByRole('button', { name: 'Close the panel' }).click();
  await page.waitForSelector('.panel', { state: 'detached' });
  assert.ok((await box('.flat [data-card="M5"]')) !== null);
  // developer view, the clock and the galaxy keep to the width too
  await page.getByRole('button', { name: 'Developer' }).click();
  await page.evaluate(() => { window.location.hash = '#m=M3.4&v=dev'; });
  await drawn(page, 'M3.4');
  assert.equal(await sideways(page), 0, 'settings and paths');
  await page.getByRole('button', { name: /^Clock/ }).click();
  await page.waitForSelector('[data-panel="clock"]');
  assert.equal(await sideways(page), 0, 'clock');
  assert.ok((await box('.player')).y < 300, 'a mode someone starts is moved to');
  await page.evaluate(() => { window.location.hash = '#g&m=M5&v=dev'; });
  await page.waitForSelector('[data-code="M5"]');
  assert.equal(await sideways(page), 0, 'galaxy');
  await page.locator('.topbar').getByRole('button', { name: /^Search/ }).click();
  await page.waitForSelector('dialog.search[open]');
  await page.keyboard.type('advisor');
  const dialog = await box('dialog.search');
  assert.ok(dialog.x >= 0 && dialog.x + dialog.width <= PHONE[0], 'the dialog fits');
  clean();
});

test('a window made narrow turns flat, and wide again shows the 3D view', SLOW, async (t) => {
  const { page, clean } = await open(t, { hash: '#p=trace&s=2' });
  await page.waitForSelector('canvas');
  // the player moves above the map and back, and whoever stands on a button stays there
  const next = page.locator('.player').getByRole('button', { name: 'Next →' });
  const focused = () => page.evaluate(() => document.activeElement.textContent.trim());
  const above = async () => (await page.locator('.player').boundingBox()).y
    < (await page.locator('main.world').boundingBox()).y;
  // what the screen shows first, a keyboard reaches first
  const readFirst = () => page.evaluate(() => Boolean(document.querySelector('.player')
    .compareDocumentPosition(document.querySelector('main.world'))
    & Node.DOCUMENT_POSITION_FOLLOWING));
  await next.focus();
  await page.setViewportSize({ width: 600, height: 800 });
  await page.waitForSelector('.flat');
  assert.equal(await focused(), 'Next →', 'narrow');
  assert.ok(await above());
  assert.ok(await readFirst());
  await page.setViewportSize({ width: 1280, height: 800 });
  await page.waitForSelector('[data-app][data-ready="true"] canvas');
  assert.equal(await focused(), 'Next →', 'wide again');
  assert.ok(!(await above()));
  assert.ok(!(await readFirst()));
  await page.keyboard.press('Escape');
  await page.evaluate(() => { window.location.hash = '#m=M5.2'; });
  await page.waitForSelector('[data-panel="M5.2"]');
  await page.setViewportSize({ width: 600, height: 800 });
  await page.waitForSelector('.flat');
  assert.equal(await page.locator('canvas').count(), 0);
  assert.equal(await page.locator('[data-panel="M5.2"]').count(), 1);
  await page.setViewportSize({ width: 1280, height: 800 });
  await page.waitForSelector('canvas');
  assert.equal(await page.locator('.flat').count(), 0);
  assert.equal(await data(page, 'view-kind'), '3d');
  assert.equal(await page.locator('[data-panel="M5.2"]').count(), 1);
  clean();
});

test('a 3D view that fails is replaced by the flat map, which says so', SLOW, async (t) => {
  // the first ask (is there WebGL?) is answered, the 3D view's own is not
  const { page } = await open(t, { webgl: true, hash: '#m=M2' });
  await page.context().addInitScript(() => {
    const real = HTMLCanvasElement.prototype.getContext;
    let asked = 0;
    HTMLCanvasElement.prototype.getContext = function getContext(kind, ...rest) {
      if (!String(kind).startsWith('webgl')) return real.call(this, kind, ...rest);
      asked += 1;
      return asked === 1 ? real.call(this, kind, ...rest) : null;
    };
  });
  const wrong = [];
  page.on('console', (m) => { if (m.type() === 'error') wrong.push(m.text()); });
  page.on('pageerror', (e) => wrong.push(e.message));
  await page.reload();
  await page.waitForSelector('.flat', { timeout: 90_000 });
  assert.match(await page.getByRole('alert').textContent(), /3D view failed.*flat map/);
  assert.ok(wrong.length > 0, 'the failure is said in the console');
  assert.deepEqual(wrong.filter((m) => !/webgl|context|error boundary/i.test(m)), [],
    'nothing else went wrong');
  assert.equal(await page.locator('[data-panel="M2"]').count(), 1);
  await page.locator('.flat a[data-card="M5"]').click();
  await page.waitForSelector('[data-panel="M5"]');
});

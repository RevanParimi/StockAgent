/**
 * What the architecture map's browser tests share: the committed page opened from disk
 * with the network off and software WebGL, as someone double-clicking the file would.
 *
 * Every page records its console errors and every request it makes; a test that leaves
 * either behind fails.
 */
import { before, after } from 'node:test';
import assert from 'node:assert/strict';
import path from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { chromium } from 'playwright';

const REPO = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..', '..');
export const PAGE = pathToFileURL(path.join(REPO, 'docs', 'architecture-map', 'index.html')).href;
export const SLOW = { timeout: 180_000 };

let browser;
/** Starts a browser for the file's tests and closes it after them. */
export function useBrowser() {
  before(async () => {
    browser = await chromium.launch({
      args: ['--use-angle=swiftshader', '--enable-unsafe-swiftshader', '--ignore-gpu-blocklist'],
    });
  });
  after(async () => { await browser?.close(); });
  return () => browser;
}

/** A page on the map, and what went wrong on it. Reduced motion unless a test says. A
 *  page opened with no address starts on the guided tour; unless a test wants it, Esc
 *  leaves it first and the test begins on the map. A test that opens several pages in
 *  turn calls `close` on each: drawn in software, every open one holds much memory. */
export async function open(t, { hash = '', motion = false, size = [1280, 800], tour = false } = {}) {
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

export const data = (page, name) => page.getAttribute('[data-app]', `data-${name}`);
export const model = (page) => page.evaluate(() => JSON.parse(document.getElementById('model').textContent));
export const still = (page) => page.waitForFunction(
  () => document.querySelector('[data-app]').dataset.moving === 'false', null, { timeout: 60_000 });
export async function settled(page, since) {
  // the camera has left where it was and stopped
  await page.waitForFunction((from) => {
    const app = document.querySelector('[data-app]');
    return app.dataset.camera !== from && app.dataset.moving === 'false';
  }, since, { timeout: 60_000 });
  return data(page, 'camera');
}

/** Where a point of the world lands on the 3D view: the camera's own geometry. */
export function onScreen(camera, fov, view, point) {
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

/** The focused element, and whether a person can see that it is focused. */
export const focus = (page) => page.evaluate(() => {
  const el = document.activeElement;
  const style = getComputedStyle(el);
  return {
    tag: el.tagName, text: el.textContent.trim().slice(0, 60), module: el.dataset.module ?? '',
    inDialog: Boolean(el.closest('dialog')), id: el.id,
    ring: style.outlineStyle !== 'none' && parseFloat(style.outlineWidth) >= 2,
  };
});

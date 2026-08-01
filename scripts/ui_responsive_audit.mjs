/**
 * Responsive audit — spec 2026-07-31 §6.
 *
 * Asserts no screen overflows its viewport horizontally, at four widths, and
 * writes screenshots for the human pass. The assertion is necessary but not
 * sufficient: it cannot catch a container that grows while its contents stay
 * fixed-width (that distributes badly without overflowing), so the 1280px
 * screenshots still need eyes.
 *
 * Tab traversal (Task 11): a SCREENS entry can be `{ name, tabs }` instead of
 * a bare string. `tabs` is a list of inner-tab button labels (the button's
 * accessible name — usually its visible text) to click, one at a time, after
 * landing on the screen; the same overflow assertion runs again after each
 * click and failures are reported as `screen/tab @ width`. This exists
 * because rl-monitor's "Agent weight drift" tab held a 474px-wide grid that
 * never showed up in any failure list — activeTab defaults to a different
 * tab, so the screen-level check alone never rendered it.
 *
 * Usage:
 *   python scripts/seed_fixture_ui.py --data-dir .uidev-data
 *   PORTFOLIO_DATA_DIR=.uidev-data python -m uvicorn services.api.server:app --port 8001
 *   node scripts/ui_responsive_audit.mjs --out .uidev-data/shots
 *
 * Auth note: the SPA login gate is client-side on a stored bearer token
 * (index.html's saGetToken/saSetToken), independent of AUTH_REQUIRED. To
 * reach the authenticated screens this script logs in against the dev owner
 * account (data/users.db, seeded by earlier tasks: dev-verify@example.com /
 * testpass123) and seeds the returned token into localStorage via
 * context.addInitScript before the app boots in each browser context.
 */
import { chromium } from 'playwright';
import { mkdirSync } from 'node:fs';
import path from 'node:path';

const arg = (k, d) => {
  const i = process.argv.indexOf(k);
  return i !== -1 && process.argv[i + 1] ? process.argv[i + 1] : d;
};
const BASE = arg('--base', 'http://localhost:8001');
const OUT = arg('--out', '.uidev-data/shots');

const WIDTHS = [360, 390, 768, 1280];
// A screen entry is either a bare name, or { name, tabs } where `tabs` is the
// list of inner-tab button labels (visible accessible-name text) to click
// and re-assert. Task 9's screen-level harness never clicked into a
// non-default inner tab, so rl-monitor's "Agent weight drift" tab (474px
// grid, 496px measured overflow) went unasserted for two tasks. Every
// activeTab-driven screen gets a tabs list here so that class of bug cannot
// hide behind a tab again.
const SCREENS = ['home', 'agents', 'portfolio', 'inbox', 'learn',
                 { name: 'rl-monitor', tabs: ['Predictions vs actual', 'Direction calendar',
                                               'Miss attribution', 'Agent weight drift'] },
                 { name: 'analytics', tabs: ['overview', 'weights', 'sector'] },
                 'logs', 'prompt-lab', 'settings'];
// Normalize to { name, tabs } so the loop below doesn't need to branch on shape.
const NORMALIZED_SCREENS = SCREENS.map(s => typeof s === 'string' ? { name: s, tabs: [] } : s);

const slugify = s => s.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '');

mkdirSync(OUT, { recursive: true });

// Log in as the dev owner account so the SPA's client-side token gate
// doesn't strand every screenshot on the login screen. AUTH_REQUIRED=false
// makes the *server* treat anonymous requests as owner-passthrough, but the
// React app decides which screen to show purely from a stored bearer token.
async function getDevToken() {
  const res = await fetch(`${BASE}/auth/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email: 'dev-verify@example.com', password: 'testpass123' }),
  });
  if (!res.ok) {
    throw new Error(`/auth/login failed (${res.status}) — is the dev owner account `
      + `seeded in data/users.db? See task-4/6/7/8 reports for how it was created.`);
  }
  const body = await res.json();
  return body.token;
}

const token = await getDevToken();

const browser = await chromium.launch();
const failures = [];

for (const width of WIDTHS) {
  const ctx = await browser.newContext({
    viewport: { width, height: 900 }, deviceScaleFactor: 1 });
  // Seed the bearer token before any page script runs, so App() sees
  // hasToken===true on first render and skips the login screen.
  await ctx.addInitScript(tok => {
    localStorage.setItem('sa_auth_token', tok);
  }, token);
  const page = await ctx.newPage();

  // Shared assertion: same scrollWidth <= innerWidth check the screen-level
  // loop always used, parameterized by the failure label so tab checks can
  // report `screen/tab @ width` instead of just `screen @ width`.
  const checkOverflow = async (label) => {
    const overflow = await page.evaluate(() => ({
      scrollWidth: document.documentElement.scrollWidth,
      innerWidth: window.innerWidth,
    }));
    const ok = overflow.scrollWidth <= overflow.innerWidth;
    if (!ok) {
      failures.push(`${label} @ ${width}px — scrollWidth ${overflow.scrollWidth} > ${overflow.innerWidth}`);
    }
    return ok;
  };

  for (const { name: screen, tabs } of NORMALIZED_SCREENS) {
    await page.goto(BASE, { waitUntil: 'networkidle' });
    // The prototype does no URL routing — drive it through the Tweaks quick-jump
    // by calling the app's own nav via a synthetic hash the App() reads, falling
    // back to clicking the nav entry.
    const navigated = await page.evaluate(s => {
      if (typeof window.__auditNav !== 'function') return false;
      window.__auditNav(s);
      return true;
    }, screen);
    if (!navigated) {
      console.error(`FATAL: window.__auditNav missing — cannot navigate to "${screen}". ` +
                    'Every screenshot would be the same screen and results would be meaningless.');
      await browser.close();
      process.exit(2);
    }
    await page.waitForTimeout(600);

    const ok = await checkOverflow(screen);
    await page.screenshot({
      path: path.join(OUT, `${screen}-${width}${ok ? '' : '-FAIL'}.png`),
      fullPage: true });

    // Click into each inner tab and re-assert. Same instrument-broken vs
    // app-overflows distinction as the missing-nav-seam guard above: if a
    // tab button can't be found/clicked, the harness itself is unreliable
    // for this screen, so it's exit 2, not a scored failure.
    for (const tabLabel of tabs) {
      const tabButton = page.getByRole('button', { name: tabLabel }).first();
      try {
        await tabButton.click({ timeout: 5000 });
      } catch (e) {
        console.error(`FATAL: could not click tab "${tabLabel}" on screen "${screen}" — ` +
                      `tab traversal is unreliable, results would be meaningless. (${e.message})`);
        await browser.close();
        process.exit(2);
      }
      await page.waitForTimeout(300);

      const tabLabelPath = `${screen}/${tabLabel}`;
      const tabOk = await checkOverflow(tabLabelPath);
      await page.screenshot({
        path: path.join(OUT, `${screen}-${slugify(tabLabel)}-${width}${tabOk ? '' : '-FAIL'}.png`),
        fullPage: true });
    }
  }
  await ctx.close();
}

await browser.close();

if (failures.length) {
  console.error(`\n✗ ${failures.length} overflow failure(s):`);
  for (const f of failures) console.error('  ' + f);
  console.error(`\nScreenshots in ${OUT}`);
  process.exit(1);
}
const totalTabs = NORMALIZED_SCREENS.reduce((n, s) => n + s.tabs.length, 0);
console.log(`✓ no horizontal overflow across ${SCREENS.length} screens `
  + `(+ ${totalTabs} inner tabs) × ${WIDTHS.length} widths`);
console.log(`Screenshots in ${OUT} — eyeball the 1280px set for under-distribution.`);
process.exit(0);

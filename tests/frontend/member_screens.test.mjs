/**
 * PR-040: members see three screens and load no operator code — in the real
 * browser, through the real app.
 *
 *   node --test tests/frontend/member_screens.test.mjs
 *
 * Serves src/frontend/prototypes/index.html from a fake origin, as
 * no_invented_figures.test.mjs does: CDN scripts from node_modules, every API
 * path a test does not plan answered 503, everything else outside aborted.
 * Every same-origin file the page requests is recorded, so a test can say
 * which files a browser downloaded.
 *
 * The invariants do not mirror the implementation:
 *  - a member's navigation, at desktop and phone width, names exactly Today,
 *    Portfolio and Ask, with Settings and Sign out in the account menu, and
 *    no operator screen, Learn or Inbox anywhere;
 *  - from sign-in through every member screen, a member's browser requests
 *    none of the operator files (and no removed or demo-only file); the
 *    owner's browser requests every one, and each operator screen opens;
 *  - the service worker's list holds no operator file, and the new index.html
 *    still renders over the scripts of the version before it (scripts come
 *    from the service worker's cache first);
 *  - the removed sections stay removed even when the server sends their data;
 *    the analysis drawer's agent breakdown and conflicts are the owner's;
 *  - every member screen says "unavailable" when its API fails.
 */
import { test, before, after } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync, existsSync } from 'node:fs';
import { execFileSync } from 'node:child_process';
import path from 'node:path';
import { launch, stopAnimations, ORIGIN, REPO, FRONTEND, CDN_FILES, CONTENT_TYPES } from './chat_harness.mjs';

const OPERATOR_FILES = ['agents-page.jsx', 'analytics.jsx', 'logs.jsx', 'rl-data.jsx', 'rl-monitor.jsx'];
const REMOVED_FILES = ['learn.jsx', 'tweaks-panel.jsx', 'prompt-lab.jsx'];
const OPERATOR_LABELS = ['Operator', 'Agents', 'Analytics', 'Logs', 'RL Monitor'];
const API_PREFIXES = ['/ui/', '/auth/', '/portfolio', '/history/', '/delivery/', '/discovery/',
                      '/analyse', '/ws/', '/ops/', '/scheduler', '/analytics', '/prompts', '/health'];

const MEMBER = { user_id: 'u-ravi', email: 'ravi@example.test', display_name: 'Ravi Kumar', role: 'member' };
const OWNER = { user_id: 'primary', email: 'owner@example.test', display_name: 'Meera Rao', role: 'owner' };

function json(body, status = 200) {
  return { status, contentType: 'application/json', body: JSON.stringify(body) };
}

const QWATCH = { sym: 'QWATCHX', name: 'Qwatch Industries', price: 1234.5, change: 2.51, score: 0.61,
                 verdict: 'BUY', trend: 'up', hasData: true };
const AGENT = { key: 'fundamentals', name: 'Fundamentals', icon: '📈', weight: 0.2, enabled: true,
                desc: 'Revenue and margins.', beginner: 'Whether the company makes more money.' };

function liveApi(overrides = {}) {
  return {
    '/ui/bootstrap': json({
      AGENTS: [AGENT], TICKERS: [QWATCH], WATCHLIST: ['QWATCHX'],
      MARKET_TODAY: { pulse: 'Mixed signals', oneLiner: 'Qwatch guided higher.', autoChange: 0.37,
                      drivers: [], sectorChange: [], freshness: { label: 'Updated 2h ago', runAt: null, isStale: false } },
      MARKET_MONTH: { pulse: 'Mixed signals', oneLiner: 'Quiet month.', drivers: [],
                      agentVotes: [{ n: 'Fundamentals', v: 0.71, k: 'good' }],
                      freshness: { label: 'No data yet', runAt: null, isStale: true } },
      NIFTY50: null, NIFTY_AUTO_HISTORY: [], TRENDING: [],
      // Sections removed by PR-040: sent by the server, never drawn.
      SUGGESTIONS: [{ sym: 'QSUGGEST', name: 'Qsuggest Ltd', reason: 'You watch autos.', score: 0.7,
                      verdict: 'BUY', price: 100, change: 1 }],
      CATEGORIES: [{ key: 'qcat', name: 'Qcategory', icon: '🚗', count: 3, tickers: ['QWATCHX'] }],
      CHAT_SEEDS: ['How is my portfolio doing?'], AGENT_TASK_FLAGS: {},
      _fetchedAt: '2026-10-13T03:30:00+00:00', _liveData: true,
    }),
    '/ui/watchlist': json({ watchlist: ['QWATCHX'], tickers: [QWATCH] }),
    '/ui/learnings': json({ items: [] }),
    '/ui/agents': json({ agents: [AGENT] }),
    ...overrides,
  };
}

const fromCheckout = (name) => {
  const file = path.join(FRONTEND, name);
  return existsSync(file) ? readFileSync(file) : null;
};

/**
 * Open the app. plan.api maps an API path (no query) to a response or a
 * function; plan.user is the account (/auth/me and /auth/login answer it);
 * plan.staticFile(name) supplies every file but index.html (default: the
 * checkout), so a test can serve the previous version's scripts.
 */
async function openApp(browser, plan = {}) {
  const context = await browser.newContext({
    serviceWorkers: 'block',
    viewport: plan.viewport || { width: 1280, height: 900 },
    timezoneId: 'Asia/Kolkata',
  });
  await stopAnimations(context);
  const requests = [];
  const calls = [];
  const user = plan.user || MEMBER;
  const staticFile = plan.staticFile || fromCheckout;
  const api = { '/auth/me': json({ user }), '/auth/login': json({ token: 'test-session', user }),
                '/auth/logout': json({ ok: true }), ...(plan.api || {}) };
  await context.route('**/*', async (route) => {
    const url = route.request().url();
    if (url.startsWith(ORIGIN + '/')) {
      const u = new URL(url);
      if (u.pathname === '/' || u.pathname === '/index.html') {
        return route.fulfill({ status: 200, contentType: 'text/html',
                               body: readFileSync(path.join(FRONTEND, 'index.html')) });
      }
      const isStatic = /\.(jsx?|html|css|json|png|svg|ico)$/.test(u.pathname);
      if (!isStatic && API_PREFIXES.some(p => u.pathname.startsWith(p))) {
        calls.push(route.request().method() + ' ' + u.pathname);
        const answer = api[u.pathname];
        if (answer === undefined) return route.fulfill(json({ detail: 'not in this test plan' }, 503));
        return route.fulfill(typeof answer === 'function' ? await answer(u, route.request()) : answer);
      }
      const name = decodeURIComponent(u.pathname.slice(1));
      requests.push(name);
      const body = name && !name.includes('..') ? staticFile(name) : null;
      if (!body) return route.fulfill({ status: 404, body: 'not found' });
      return route.fulfill({ status: 200, body,
                             contentType: CONTENT_TYPES[path.extname(name)] || 'application/octet-stream' });
    }
    for (const [pattern, rel] of CDN_FILES) {
      if (pattern.test(url)) {
        return route.fulfill({ status: 200, body: readFileSync(path.join(REPO, 'node_modules', rel)),
                               contentType: 'text/javascript',
                               headers: { 'Access-Control-Allow-Origin': '*' } });
      }
    }
    return route.abort('blockedbyclient');
  });
  if (!plan.signedOut) {
    await context.addInitScript(() => { localStorage.setItem('sa_auth_token', 'test-session'); });
  }
  const page = await context.newPage();
  const errors = [];
  page.on('pageerror', (e) => errors.push(String(e)));
  page.on('dialog', (d) => d.dismiss());
  await page.goto(`${ORIGIN}/${plan.query || ''}`);
  if (plan.signedOut) await page.getByPlaceholder('you@example.com').waitFor({ timeout: 30000 });
  else await page.locator('h1').first().waitFor({ timeout: 30000 });
  return { context, page, requests, calls, errors };
}

async function signIn(page) {
  await page.getByPlaceholder('you@example.com').fill('someone@example.test');
  await page.locator('input[type="password"]').fill('a-password');
  await page.locator('button[type="submit"]').click();
  await page.locator('h1').first().waitFor({ timeout: 30000 });
}

async function settled(page) {
  await page.waitForFunction(() => window.__apiState && window.__apiState !== 'loading' && window.saUser,
                             null, { timeout: 8000 }).catch(() => {});
  await page.waitForTimeout(500);
}

async function operatorLoaded(page) {
  await page.waitForFunction(() => window.saOperatorState === 'ready', null, { timeout: 30000 });
  await page.waitForTimeout(200);
}

async function goTo(page, screen) {
  await page.evaluate((s) => window.__auditNav(s), screen);
  await page.waitForTimeout(600);
}

const text = (page) => page.evaluate(() => document.body.innerText);

// The page's text matches within the bound, else the assertion fails with the
// text it did show. A screen drawn late on a loaded box is not a missing one
// (BACKLOG B-36, OPS-003).
async function shown(page, pattern, timeout = 10000) {
  await page.waitForFunction(([src, flags]) => new RegExp(src, flags).test(document.body.innerText),
                             [pattern.source, pattern.flags], { timeout }).catch(() => {});
  assert.match(await text(page), pattern);
}

const labels = async (locator) => (await locator.allInnerTexts()).map(t => t.replace(/\s+/g, ' ').trim())
  .filter(t => t && t !== '☾' && t !== '☀');                        // the theme toggle is not a screen

let browser;
before(async () => { browser = await launch(); });
after(async () => { await browser?.close(); });

// -- Navigation ----------------------------------------------------------------

test("a member's navigation offers exactly Today, Portfolio and Ask, and the account menu", async () => {
  const desk = await openApp(browser, { user: MEMBER, api: liveApi() });
  try {
    await settled(desk.page);
    assert.deepEqual(await labels(desk.page.locator('.nav-top-pill button')), ['Today', 'Portfolio', 'Ask']);
    assert.equal(await desk.page.locator('.sa-operator-menu').count(), 0);
    await desk.page.getByRole('button', { name: 'Account' }).click();
    assert.deepEqual(await labels(desk.page.locator('.sa-account-menu button')), ['Settings', 'Sign out']);
    // the floating operator chips and the Tweaks panel are gone
    assert.equal(await desk.page.locator('.proto-nav').count(), 0);
    await desk.page.evaluate(() => window.postMessage({ type: '__activate_edit_mode' }, '*'));
    await desk.page.waitForTimeout(300);
    assert.equal(await desk.page.locator('.twk-panel').count(), 0);
    // Ask is the chat
    await desk.page.keyboard.press('Escape');
    await desk.page.locator('.nav-top-pill').getByRole('button', { name: 'Ask' }).click();
    await desk.page.getByPlaceholder('Ask about a stock or sector…').waitFor({ timeout: 5000 });
    const all = await text(desk.page);
    for (const gone of ['Learn', 'Inbox', ...OPERATOR_LABELS]) {
      assert.ok(!new RegExp(`(^|\\n)\\s*${gone}\\s*(\\n|$)`).test(all), `"${gone}" offered: ${all.slice(0, 400)}`);
    }
    assert.deepEqual(desk.errors, []);
  } finally { await desk.context.close(); }

  const phone = await openApp(browser, { user: MEMBER, api: liveApi(), viewport: { width: 390, height: 860 } });
  try {
    await settled(phone.page);
    assert.deepEqual(await labels(phone.page.locator('.mobile-bottom-nav button')), ['Today', 'Portfolio', 'Ask']);
    await phone.page.locator('.nav-hamburger button').last().click();
    const menu = await labels(phone.page.locator('.mobile-menu button'));
    assert.deepEqual(menu, ['Today', 'Portfolio', 'Ask', 'Settings', 'Sign out'], menu.join(' | '));
    const menuText = await phone.page.locator('.mobile-menu').innerText();
    for (const gone of ['Learn', 'Inbox', ...OPERATOR_LABELS]) assert.ok(!menuText.includes(gone), `menu: ${gone}`);
    assert.deepEqual(phone.errors, []);
  } finally { await phone.context.close(); }
});

test('the owner also has the Operator menu, and every operator screen opens from it', async () => {
  const headings = { Agents: 'Your AI agents', Analytics: 'RL Analytics', Logs: 'Server Logs',
                     'RL Monitor': 'Reinforcement Learning Monitor' };
  const app = await openApp(browser, { user: OWNER, api: liveApi() });
  try {
    await settled(app.page);
    await operatorLoaded(app.page);
    assert.deepEqual(await labels(app.page.locator('.nav-top-pill > button')), ['Today', 'Portfolio', 'Ask']);
    for (const [label, heading] of Object.entries(headings)) {
      await app.page.locator('.sa-operator-menu').getByRole('button', { name: /Operator/ }).click();
      const items = await labels(app.page.locator('.sa-operator-menu [aria-label="Operator"] button'));
      assert.deepEqual(items, ['Agents', 'Analytics', 'Logs', 'RL Monitor']);
      await app.page.locator('.sa-operator-menu [aria-label="Operator"]').getByRole('button', { name: label }).click();
      await app.page.getByText(heading).first().waitFor({ timeout: 10000 });
      assert.equal(await app.page.getByRole('button', { name: "Today's market" }).count(), 0, `${label}: not Today`);
    }
    assert.deepEqual(app.errors, []);
  } finally { await app.context.close(); }

  const phone = await openApp(browser, { user: OWNER, api: liveApi(), viewport: { width: 390, height: 860 } });
  try {
    await settled(phone.page);
    assert.deepEqual(await labels(phone.page.locator('.mobile-bottom-nav button')), ['Today', 'Portfolio', 'Ask']);
    await phone.page.locator('.nav-hamburger button').last().click();
    const menu = await labels(phone.page.locator('.mobile-menu button'));
    assert.deepEqual(menu, ['Today', 'Portfolio', 'Ask', 'Settings', 'Agents', 'Analytics', 'Logs',
                                     'RL Monitor', 'Sign out'], menu.join(' | '));
    assert.match(await phone.page.locator('.mobile-menu').innerText(), /Operator/i);   // an eyebrow: CSS capitals
  } finally { await phone.context.close(); }
});

// -- What each browser downloads ---------------------------------------------

async function walkMemberScreens(page) {
  for (const tab of ['Brief', 'Digest', 'Weekly', 'Alerts']) {
    await page.getByRole('button', { name: tab, exact: true }).click();
    await page.waitForTimeout(300);
  }
  for (const tab of ["Today's market", 'This month', 'Watchlist', 'Trending']) {
    await page.getByRole('button', { name: tab }).first().click();
    await page.waitForTimeout(300);
  }
  await goTo(page, 'portfolio');
  await goTo(page, 'settings');
  await goTo(page, 'home');
  await goTo(page, 'ask');
  await page.keyboard.press('Escape');
}

test('a member requests no operator file from sign-in through every screen; the owner requests each', async () => {
  const member = await openApp(browser, { user: MEMBER, api: liveApi(), signedOut: true });
  try {
    await signIn(member.page);
    await settled(member.page);
    await walkMemberScreens(member.page);
    for (const s of ['agents', 'analytics', 'logs', 'rl-monitor', 'learn', 'inbox']) await goTo(member.page, s);
    await member.page.waitForTimeout(800);
    assert.ok(member.requests.includes('home.jsx') && member.requests.includes('inbox.jsx'), member.requests.join(','));
    const fetched = member.requests.filter(r => OPERATOR_FILES.includes(r) || REMOVED_FILES.includes(r)
                                                || r === 'demo-fixtures.js' || r === 'UI_SPEC.md');
    assert.deepEqual(fetched, []);
    assert.equal(await member.page.evaluate(() => window.saOperatorState), 'none');
    assert.equal(await member.page.evaluate(() => typeof window.AgentsPage), 'undefined');
    assert.deepEqual(member.errors, []);
  } finally { await member.context.close(); }

  const owner = await openApp(browser, { user: OWNER, api: liveApi(), signedOut: true });
  try {
    await signIn(owner.page);
    await operatorLoaded(owner.page);
    for (const f of OPERATOR_FILES) assert.ok(owner.requests.includes(f), `${f}: ${owner.requests.join(',')}`);
    assert.deepEqual(owner.requests.filter(r => REMOVED_FILES.includes(r)), []);
    assert.deepEqual(owner.errors, []);
  } finally { await owner.context.close(); }
});

test("the service worker's list holds no operator, removed or demo-only file, and names real files", () => {
  const sw = readFileSync(path.join(FRONTEND, 'sw.js'), 'utf8');
  const block = sw.slice(sw.indexOf('const SHELL = ['), sw.indexOf('];', sw.indexOf('const SHELL = [')));
  const listed = [...block.matchAll(/'\/([^']*)'/g)].map(m => m[1]).filter(Boolean);
  assert.ok(listed.includes('home.jsx') && listed.includes('inbox.jsx'), listed.join(','));
  for (const f of [...OPERATOR_FILES, ...REMOVED_FILES, 'demo-fixtures.js']) {
    assert.ok(!listed.includes(f), `sw.js lists ${f}`);
  }
  for (const f of listed) assert.ok(existsSync(path.join(FRONTEND, f)), `sw.js lists a missing file: ${f}`);
});

// -- The first open after an update ------------------------------------------

// The scripts a browser may still hold when the new index.html arrives: the
// version in production before this change (origin/main at its writing) and
// the commit it was built on.
const PREVIOUS = { 'production before PR-040': '3f26ae5', 'the base of PR-040': '4fd3396' };

function hasRevision(rev) {
  try {
    execFileSync('git', ['cat-file', '-e', `${rev}^{commit}`], { cwd: REPO, stdio: 'ignore' });
    return true;
  } catch { return false; }
}

const filesAt = (rev) => (name) => {
  try {
    return execFileSync('git', ['show', `${rev}:src/frontend/prototypes/${name}`],
                        { cwd: REPO, stdio: ['ignore', 'pipe', 'ignore'], maxBuffer: 16 << 20 });
  } catch { return null; }
};

for (const [label, rev] of Object.entries(PREVIOUS)) {
  test(`the new index.html renders over the scripts of ${label} (${rev})`, async (t) => {
    if (!hasRevision(rev)) { t.skip(`revision ${rev} is not in this clone`); return; }
    const member = await openApp(browser, { user: MEMBER, api: liveApi(), staticFile: filesAt(rev) });
    try {
      await settled(member.page);
      assert.match(await member.page.locator('h1').first().innerText(), /Ravi/);
      for (const s of ['inbox', 'learn', 'agents', 'logs', 'portfolio', 'settings', 'home']) {
        await goTo(member.page, s);
        assert.ok((await text(member.page)).trim().length > 0, `${s}: blank`);
      }
      assert.equal(await member.page.locator('h1').count() > 0, true);
      assert.deepEqual(member.requests.filter(r => OPERATOR_FILES.includes(r)), []);
      assert.deepEqual(member.errors, []);
    } finally { await member.context.close(); }

    const owner = await openApp(browser, { user: OWNER, api: liveApi(), staticFile: filesAt(rev) });
    try {
      await settled(owner.page);
      await operatorLoaded(owner.page);
      await goTo(owner.page, 'agents');
      await owner.page.getByText('Your AI agents').first().waitFor({ timeout: 10000 });
      assert.deepEqual(owner.errors, []);
    } finally { await owner.context.close(); }
  });
}

// -- What stays removed ------------------------------------------------------

const REPORT = {
  ticker: 'QWATCHX', company_name: 'Qwatch Industries', verdict: 'BUY', final_score: 0.66,
  executive_summary: 'Orders are ahead of plan.', investment_thesis: 'Demand is recovering.',
  conviction_drivers: ['Order book'], top_risks: ['Input costs'],
  weighted_agent_scores: { fundamentals: 0.7 }, conflicts_resolved: ['Valuation against momentum'],
};

async function analyse(page) {
  await page.getByRole('button', { name: 'Watchlist' }).first().click();
  await page.getByRole('button', { name: 'Analyze' }).first().click();
  await page.getByText('Investment thesis').waitFor({ timeout: 15000 });
  return page.locator('aside.drawer-panel').innerText();
}

test('removed sections stay removed; the agent breakdown and conflicts are the owner’s', async () => {
  const api = liveApi({ '/analyse': json(REPORT) });
  const member = await openApp(browser, { user: MEMBER, api });
  try {
    await settled(member.page);
    let all = await text(member.page);
    for (const gone of ['Browse by category', 'Suggested for you', 'Qcategory', 'QSUGGEST']) {
      assert.ok(!all.includes(gone), gone);
    }
    await member.page.getByRole('button', { name: 'This month' }).first().click();
    await member.page.waitForTimeout(300);
    assert.ok(!(await text(member.page)).includes('How agents are voting'));
    const drawer = await analyse(member.page);
    assert.match(drawer, /Demand is recovering/);
    assert.ok(!/Agent breakdown/i.test(drawer), drawer);
    assert.ok(!/Conflicts resolved/i.test(drawer), drawer);
    assert.deepEqual(member.errors, []);
  } finally { await member.context.close(); }

  const owner = await openApp(browser, { user: OWNER, api });
  try {
    await settled(owner.page);
    await owner.page.getByRole('button', { name: 'This month' }).first().click();
    await owner.page.waitForTimeout(300);
    assert.ok(!(await text(owner.page)).includes('How agents are voting'));
    const drawer = await analyse(owner.page);
    assert.match(drawer, /Agent breakdown/i);
    assert.match(drawer, /Conflicts resolved/i);
    assert.match(drawer, /Valuation against momentum/);
  } finally { await owner.context.close(); }
});

// -- Unavailable states --------------------------------------------------------

test('every member screen says unavailable when its API fails', async () => {
  const app = await openApp(browser, { user: MEMBER, api: { '/ui/bootstrap': json({ detail: 'down' }, 500) } });
  try {
    await settled(app.page);
    await shown(app.page, /Market data unavailable/);
    for (const tab of ['Brief', 'Digest', 'Weekly', 'Alerts']) {
      await app.page.getByRole('button', { name: tab, exact: true }).click();
      await app.page.waitForTimeout(400);           // the previous tab's message must not count
      await app.page.locator('.sa-inbox-panel .sa-unavailable').waitFor({ timeout: 5000 });
      assert.match(await app.page.locator('.sa-inbox-panel').innerText(), /Couldn't load this/, tab);
      assert.equal(await app.page.locator('.sa-inbox-panel [aria-pressed="true"]').innerText(), tab);
    }
    await app.page.getByRole('button', { name: 'Watchlist' }).first().click();
    await shown(app.page, /Your watchlist is unavailable right now/);
    await goTo(app.page, 'portfolio');
    await shown(app.page, /Your portfolio is unavailable right now/);
    assert.deepEqual(app.errors, []);
  } finally { await app.context.close(); }
});

test('the Agents page shows the learning mode beside the weight controls', async () => {
  const api = liveApi({
    '/ui/rl/tickers': json({ tickers: [{ sym: 'QWATCHX', name: 'Qwatch Industries' }] }),
    '/ui/rl/weights/QWATCHX': json({ available: true, ticker: 'QWATCHX', learning_mode: 'observe',
                                     learning_mode_reason: 'rl.learning_mode=observe' }),
  });
  const app = await openApp(browser, { user: OWNER, api });
  try {
    await settled(app.page);
    await operatorLoaded(app.page);
    await goTo(app.page, 'agents');
    const note = app.page.locator('.sa-learning-mode');
    await note.getByText(/Learning mode: observe/).waitFor({ timeout: 10000 });
    assert.match(await note.innerText(), /configured weights/);
    assert.match(await note.innerText(), /no analysis reads them yet/);
  } finally { await app.context.close(); }

  const down = await openApp(browser, { user: OWNER, api: { '/ui/bootstrap': json({}, 500) } });
  try {
    await settled(down.page);
    await operatorLoaded(down.page);
    await goTo(down.page, 'agents');
    await down.page.locator('.sa-learning-mode').getByText(/unavailable right now/).waitFor({ timeout: 10000 });
    assert.match(await text(down.page), /The agents are unavailable right now/);
    assert.deepEqual(down.errors, []);
  } finally { await down.context.close(); }
});

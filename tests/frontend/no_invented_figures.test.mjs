/**
 * PR-001: real figures only, and operator tools for the owner only — in the
 * real browser, through the real app.
 *
 *   node --test tests/frontend/no_invented_figures.test.mjs
 *
 * Serves src/frontend/prototypes/index.html itself (every screen, the global
 * fetch wrapper, demo-fixtures.js) from a fake origin. Each test answers the
 * API from its own plan; any API path the plan does not name gets a 503, so a
 * screen that silently invents data instead of asking (or after a failed ask)
 * is caught. Same no-network rules as chat_harness.mjs: CDN scripts come from
 * node_modules, every other outside request is aborted.
 *
 * The invariants do not mirror the implementation:
 *  - with every market API failing, the visible text holds no percentage, no
 *    rupee figure, no index level, no ticker or company from the sample set
 *    (read from demo-fixtures.js itself) and no "Aditi";
 *  - with the APIs answering, every percentage and rupee figure on screen is
 *    one the API sent, formatted the way any reader would;
 *  - the greeting follows the IST clock even on a device in another zone;
 *  - the verdict-changes heading states the number of change cards it lists,
 *    and Learn claims nothing about the member's progress;
 *  - the weekly review opens with its results scorecard (PR-002): red flags,
 *    then what could not be checked, then the lines, every figure one the row
 *    sent, and never the scoreboard it replaced.
 */
import { test, before, after } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync, existsSync } from 'node:fs';
import path from 'node:path';
import { launch, ORIGIN, REPO, FRONTEND, CDN_FILES, CONTENT_TYPES } from './chat_harness.mjs';

const API_PREFIXES = ['/ui/', '/auth/', '/portfolio', '/history/', '/delivery/', '/discovery/',
                      '/analyse', '/ws/', '/ops/', '/scheduler', '/analytics', '/prompts', '/health'];

// The sample tickers and company names, read from the repository's fixture
// module (not SA_FRONTEND_ROOT's) so the test cannot drift from what demo mode
// shows, and an older copy of the screens is checked against the same set.
const FIXTURE_SRC = readFileSync(path.join(REPO, 'src', 'frontend', 'prototypes', 'demo-fixtures.js'), 'utf8');
const SAMPLE_SYMS = [...new Set([...FIXTURE_SRC.matchAll(/sym:'([A-Z&-]+)'/g)].map(m => m[1]))];
const SAMPLE_NAMES = [...new Set([...FIXTURE_SRC.matchAll(/name:'([^']+)'/g)].map(m => m[1]))]
  .filter(n => /\s/.test(n));   // company names ("Tata Motors"), not single words

const PCT = /[+\-−]?\d[\d,]*(?:\.\d+)?\s?%/g;
const RUPEE = /₹\s?\d[\d,]*(?:\.\d+)?/g;
const INDEX_LEVEL = /\b\d{1,2},\d{3}(?:\.\d+)?\b/g;   // 22,847 · 24,850.10

function json(body, status = 200) {
  return { status, contentType: 'application/json', body: JSON.stringify(body) };
}

const MEMBER = { user_id: 'u-ravi', email: 'ravi@example.test', display_name: 'Ravi Kumar', role: 'member' };
const OWNER = { user_id: 'primary', email: 'owner@example.test', display_name: 'Meera Rao', role: 'owner' };

/**
 * Open the app. plan.api maps an API path (no query) to a response object or
 * a function (url) -> response; plan.user is /auth/me's user; plan.query is
 * the page's query string; plan.time / plan.timezoneId fix the clock.
 */
async function openApp(browser, plan = {}) {
  const context = await browser.newContext({
    serviceWorkers: 'block',
    viewport: plan.viewport || { width: 1280, height: 900 },
    timezoneId: plan.timezoneId || 'Asia/Kolkata',
  });
  if (plan.time) await context.clock.setFixedTime(new Date(plan.time));
  const calls = [];
  const unplanned = [];
  const api = { '/auth/me': json({ user: plan.user || MEMBER }), ...(plan.api || {}) };
  await context.route('**/*', async (route) => {
    const url = route.request().url();
    if (url.startsWith(ORIGIN + '/')) {
      const u = new URL(url);
      if (u.pathname === '/' || u.pathname === '/index.html') {
        return route.fulfill({ status: 200, contentType: 'text/html',
                               body: readFileSync(path.join(FRONTEND, 'index.html')) });
      }
      const isStatic = /\.(jsx?|html|css|json|png|svg|ico)$/.test(u.pathname);   // portfolio.jsx is not /portfolio
      if (!isStatic && API_PREFIXES.some(p => u.pathname.startsWith(p))) {
        calls.push(u.pathname + u.search);
        const answer = api[u.pathname];
        if (answer === undefined) {
          unplanned.push(u.pathname);
          return route.fulfill(json({ detail: 'not in this test plan' }, 503));
        }
        return route.fulfill(typeof answer === 'function' ? await answer(u, route.request()) : answer);
      }
      const name = decodeURIComponent(u.pathname.slice(1));
      const file = path.join(FRONTEND, name);
      if (!name || name.includes('..') || !existsSync(file)) return route.fulfill({ status: 404, body: 'not found' });
      return route.fulfill({ status: 200, body: readFileSync(file),
                             contentType: CONTENT_TYPES[path.extname(file)] || 'application/octet-stream' });
    }
    for (const [pattern, rel] of CDN_FILES) {
      if (pattern.test(url)) {
        return route.fulfill({ status: 200, body: readFileSync(path.join(REPO, 'node_modules', rel)),
                               contentType: 'text/javascript',
                               headers: { 'Access-Control-Allow-Origin': '*' } });
      }
    }
    return route.abort('blockedbyclient');   // fonts and anything else outside
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
  else await page.locator('h1').first().waitFor({ timeout: 30000 });   // the hero: React and Babel are up
  return { context, page, calls, unplanned, errors };
}

// Wait until bootstrap settled (either way) and the user is known. Bounded
// and not itself an assertion, so an older copy of the screens (which has
// neither flag) still reaches the checks that matter.
async function settled(page) {
  await page.waitForFunction(() => window.__apiState && window.__apiState !== 'loading' && window.saUser,
                             null, { timeout: 8000 }).catch(() => {});
  await page.waitForTimeout(600);
}

async function greeting(page) {
  return (await page.locator('h1').first().innerText()).split('\n')[0].trim();
}

async function visibleText(page) {
  return page.evaluate(() => document.body.innerText);
}

async function goTo(page, screen) {
  await page.evaluate((s) => window.__auditNav(s), screen);
  await page.waitForTimeout(700);
}

// Every view a member can reach from Home, with the text each one shows.
async function memberViews(page) {
  const views = {};
  for (const tab of ["Today's market", 'This month', 'Watchlist', 'Trending']) {
    await page.getByRole('button', { name: tab }).first().click();
    await page.waitForTimeout(600);
    views[`home/${tab}`] = await visibleText(page);
  }
  await page.getByRole('button', { name: 'Open assistant' }).click();
  await page.waitForTimeout(400);
  views['home/chat'] = await visibleText(page);
  await page.keyboard.press('Escape');
  for (const screen of ['portfolio', 'agents', 'inbox', 'settings', 'learn']) {
    await goTo(page, 'home');
    await goTo(page, screen);
    views[screen] = await visibleText(page);
  }
  return views;
}

let browser;
before(async () => { browser = await launch(); });
after(async () => { await browser?.close(); });

test('the fixture module is read: the invariants below have sample values to look for', () => {
  assert.ok(SAMPLE_SYMS.length >= 8, SAMPLE_SYMS.join(','));
  assert.ok(SAMPLE_SYMS.includes('MARUTI'));
  assert.ok(SAMPLE_NAMES.includes('Tata Motors'), SAMPLE_NAMES.join(','));
});

test('with every market API failing, no figure, ticker, company or invented name is shown', async () => {
  const { context, page, errors } = await openApp(browser, {
    user: MEMBER,
    api: { '/ui/bootstrap': json({ detail: 'down' }, 500) },   // every other market API: 503
  });
  try {
    await settled(page);
    const home = await visibleText(page);
    const views = await memberViews(page);
    views.home = home;
    for (const [view, text] of Object.entries(views)) {
      assert.deepEqual(text.match(PCT) || [], [], `${view}: a percentage no API sent`);
      assert.deepEqual(text.match(RUPEE) || [], [], `${view}: a rupee figure no API sent`);
      assert.deepEqual(text.match(INDEX_LEVEL) || [], [], `${view}: an index level no API sent`);
      for (const sym of SAMPLE_SYMS) {
        assert.ok(!new RegExp(`(^|[^A-Z])${sym.replace(/[-&]/g, '\\$&')}([^A-Z]|$)`).test(text),
                  `${view}: sample ticker ${sym}`);
      }
      for (const name of SAMPLE_NAMES) assert.ok(!text.includes(name), `${view}: sample company ${name}`);
      assert.ok(!/Aditi/.test(text), `${view}: Aditi`);
    }
    // ...and each screen says so instead of going blank.
    assert.match(home, /Market data unavailable/);
    assert.match(views["home/Today's market"], /Today's market is unavailable right now/);
    assert.match(views["home/Today's market"], /Nifty 50\s+Unavailable right now/i);
    assert.match(views['home/This month'], /This month's market is unavailable right now/);
    assert.match(views['home/Watchlist'], /Your watchlist is unavailable right now/);
    assert.match(views['home/Trending'], /Trending is unavailable right now/);
    assert.match(views.portfolio, /Your portfolio is unavailable right now/);
    assert.match(views.agents, /The agents are unavailable right now/);
    assert.ok(!/\d+ agents ·/.test(views.agents), 'no agent count while the agents are unknown');
    // Learn says nothing about the member that nothing records (no progress is kept)
    assert.match(views.learn, /Learning paths/);
    for (const claim of [/you finished/i, /left off/i, /Recommended next/i, /Run a demo analysis/i]) {
      assert.ok(!claim.test(views.learn), `learn: ${claim}`);
    }
    assert.deepEqual(errors, []);
  } finally { await context.close(); }
});

// A day of real-looking API answers, each value distinct so the page's
// figures can be traced back to one.
const N50 = { name: 'Nifty 50', value: 25123.45, changePct: -0.42, asOf: '2026-10-12' };
const RANGE_1M = { index: 'Nifty 50', range: '1M', label: '1 month', points: [24210.5, 24660.25, 25123.45],
                   change: 3.77, value: 25123.45, asOf: '2026-10-12', from: '2026-09-12' };
const QWATCH = { sym: 'QWATCHX', name: 'Qwatch Industries', price: 1234.5, change: 2.51, score: 0.61,
                 verdict: 'BUY', trend: 'up', hasData: true };
const QUNPRICED = { sym: 'QNOPRICE', name: 'Qnoprice Ltd', price: 0.0, change: 0.0, score: 0.5,
                    verdict: 'NEUTRAL', trend: 'flat', hasData: false };
const AGENT = { key: 'fundamentals', name: 'Fundamentals', icon: '📈', weight: 0.2, enabled: true,
                desc: 'Revenue and margins.', beginner: 'Whether the company makes more money.' };

function liveApi(overrides = {}) {
  return {
    '/ui/bootstrap': json({
      AGENTS: [AGENT], TICKERS: [QWATCH, QUNPRICED], WATCHLIST: ['QWATCHX', 'QNOPRICE'],
      MARKET_TODAY: { pulse: 'Mixed signals', oneLiner: 'Qwatch guided higher.', autoChange: 0.37,
                      drivers: [], sectorChange: [{ name: 'Auto', pct: 0.37 }],
                      freshness: { label: 'Updated 2h ago', runAt: null, isStale: false } },
      MARKET_MONTH: { pulse: 'Mixed signals', oneLiner: 'No analyses this month yet.', drivers: [],
                      agentVotes: [], freshness: { label: 'No data yet', runAt: null, isStale: true } },
      NIFTY50: N50, NIFTY_AUTO_HISTORY: [], TRENDING: [], SUGGESTIONS: [], CATEGORIES: [],
      CHAT_SEEDS: ['How is my portfolio doing?'], AGENT_TASK_FLAGS: {},
      _fetchedAt: '2026-10-13T03:30:00+00:00', _liveData: true,
    }),
    '/ui/nifty-ranges': json(RANGE_1M),
    '/ui/watchlist': json({ watchlist: ['QWATCHX', 'QNOPRICE'], tickers: [QWATCH, QUNPRICED] }),
    '/ui/trending': json({ trending: [], all: [] }),
    '/ui/learnings': json({ items: [] }),
    '/ui/agents': json({ agents: [AGENT] }),
    ...overrides,
  };
}

test('with the APIs answering, every figure on screen is one an API sent', async () => {
  // ...including a sector index whose fetch failed (pct null since PR-001)
  const boot = JSON.parse(liveApi()['/ui/bootstrap'].body);
  boot.MARKET_TODAY.sectorChange.push({ name: 'IT', pct: null });
  const { context, page, errors } = await openApp(browser, {
    user: MEMBER, api: liveApi({ '/ui/bootstrap': json(boot) }) });
  try {
    await settled(page);
    const allowed = await page.evaluate(({ n50, range, q, agent }) => {
      const pct = (v) => (v >= 0 ? '+' : '') + v.toFixed(2) + '%';
      return {
        // the sector move, and the agent's weight as the Agents page states it
        pct: [pct(n50.changePct), pct(range.change), pct(q.change), pct(0.37),
              (agent.weight * 100).toFixed(0) + '%'],
        rupee: ['₹' + q.price.toLocaleString('en-IN', { minimumFractionDigits: 2 })],
        level: [range.value.toLocaleString('en-IN', { maximumFractionDigits: 2 }),
                q.price.toLocaleString('en-IN', { minimumFractionDigits: 2 })],
      };
    }, { n50: N50, range: RANGE_1M, q: QWATCH, agent: AGENT });
    const views = await memberViews(page);
    const seen = new Set();
    for (const [view, text] of Object.entries(views)) {
      for (const m of text.match(PCT) || []) {
        assert.ok(allowed.pct.includes(m.replace('−', '-').replace(/\s/g, '')), `${view}: ${m} was not sent`);
        seen.add(m);
      }
      for (const m of text.match(RUPEE) || []) assert.ok(allowed.rupee.includes(m), `${view}: ${m} was not sent`);
      for (const m of text.match(INDEX_LEVEL) || []) assert.ok(allowed.level.includes(m), `${view}: ${m} was not sent`);
      assert.ok(!/Aditi/.test(text), view);
    }
    // the screens did render the API's figures (the check above is not vacuous)
    assert.ok(seen.has('-0.42%') && seen.has('+3.77%') && seen.has('+2.51%'), [...seen].join(' '));
    // the hero's market line names its date; the index box its level and date
    const home = views["home/Today's market"];
    assert.match(home, /Nifty 50 -0\.42% on 12 Oct\./);
    assert.match(home, /25,123\.45/);
    assert.match(home, /as of 12 Oct/);
    // a stock whose price fetch failed and that was never analysed shows dashes
    const watch = views['home/Watchlist'];
    const row = watch.split('\n').findIndex(l => l.includes('QNOPRICE'));
    assert.ok(row >= 0, watch);
    assert.ok(!/0\.50/.test(watch), 'no default 0.50 score for an unanalysed stock');
    assert.match(watch, /Not analysed/);
    assert.deepEqual(errors, []);
  } finally { await context.close(); }
});

test('a bootstrap that lands after the watchlist opens still fills it; a missing section is unavailable', async () => {
  // /ui/watchlist fails, and bootstrap answers 4 s late, after the tab is open.
  // Bootstrap also leaves out MARKET_MONTH: that pane says unavailable, not "Loading".
  const boot = JSON.parse(liveApi()['/ui/bootstrap'].body);
  delete boot.MARKET_MONTH;
  const { context, page, errors } = await openApp(browser, {
    user: MEMBER,
    api: liveApi({
      '/ui/bootstrap': async () => { await new Promise(r => setTimeout(r, 4000)); return json(boot); },
      '/ui/watchlist': json({ detail: 'down' }, 503),
    }),
  });
  try {
    await page.getByRole('button', { name: 'Watchlist' }).first().click();
    await page.waitForFunction(() => window.__apiState === 'ready', null, { timeout: 15000 });
    await page.waitForTimeout(800);
    const watch = await visibleText(page);
    assert.match(watch, /QWATCHX/, 'the watchlist shows bootstrap\'s stocks once it lands');
    assert.match(watch, /₹1,234\.50/);
    await page.getByRole('button', { name: 'This month' }).first().click();
    await page.waitForTimeout(500);
    const month = await visibleText(page);
    assert.match(month, /This month's market is unavailable right now/);
    assert.ok(!/Loading this month/.test(month), month);
    assert.deepEqual(errors, []);
  } finally { await context.close(); }
});

test('the greeting uses the signed-in name and the IST clock, never "Aditi"', async () => {
  for (const [time, zone, expected] of [
    ['2026-10-13T09:00:00+05:30', 'America/New_York', 'Good morning, Ravi.'],      // 23:30 there
    ['2026-10-13T13:00:00+05:30', 'America/Los_Angeles', 'Good afternoon, Ravi.'], // 00:30 there
    ['2026-10-13T19:30:00+05:30', 'Asia/Tokyo', 'Good evening, Ravi.'],
  ]) {
    const { context, page, errors } = await openApp(browser, { user: MEMBER, api: liveApi(), time, timezoneId: zone });
    try {
      await settled(page);
      assert.equal(await greeting(page), expected, `${time} in ${zone}`);
      assert.ok(!(await visibleText(page)).includes('Aditi'));
      assert.equal((await page.locator('.nav-avatar').textContent()).trim(), 'RK');
      assert.deepEqual(errors, []);
    } finally { await context.close(); }
  }
  const { context, page } = await openApp(browser, {
    user: { ...MEMBER, display_name: '' }, api: liveApi(), time: '2026-10-13T09:00:00+05:30' });
  try {
    await settled(page);
    assert.equal(await greeting(page), 'Good morning.');
  } finally { await context.close(); }
});

const OPERATOR = ['Prompt Lab', 'Analytics', 'Logs', 'RL Monitor'];

async function operatorSurface(page) {
  const out = {};
  out.chips = await page.locator('.proto-nav button').allTextContents();
  out.topNav = await page.locator('.nav-top-pill button').allTextContents();
  // the Tweaks panel opens when a host page sends this message
  await page.evaluate(() => window.postMessage({ type: '__activate_edit_mode' }, '*'));
  await page.waitForTimeout(300);
  out.tweaks = await page.locator('.twk-panel').count();
  await goTo(page, 'agents');
  out.cardControls = await page.locator('.sa-tune-control').count();
  await page.locator('.card', { hasText: 'Fundamentals' }).first().click();
  await page.waitForTimeout(400);
  // controls any version of the drawer has: the weight slider and the plug button
  out.slider = await page.locator('aside input[type="range"]').count();
  out.plugButton = await page.getByRole('button', { name: /^(Unplug|Plug in)$/ }).count();
  out.drawerControls = await page.locator('aside .sa-tune-control').count();
  await goTo(page, 'logs');
  // Home's tab bar is on screen only when the app fell back to Home
  out.screenAfterLogs = await page.getByRole('button', { name: "Today's market" }).count();
  return out;
}

test('a member sees no operator chip, menu entry, tuning control or Tweaks', async () => {
  const { context, page, errors } = await openApp(browser, { user: MEMBER, api: liveApi() });
  try {
    await settled(page);
    const s = await operatorSurface(page);
    for (const label of OPERATOR) {
      assert.ok(!s.chips.some(t => t.includes(label)), `chip ${label}: ${s.chips}`);
      assert.ok(!s.topNav.some(t => t.includes(label)), `nav ${label}: ${s.topNav}`);
    }
    assert.deepEqual(s.chips.map(t => t.trim()), ['Sign out']);
    assert.equal(s.tweaks, 0);
    assert.equal(s.slider, 0, 'weight slider');
    assert.equal(s.plugButton, 0, 'plug button');
    assert.equal(s.cardControls, 0, 'plug toggles on the cards');
    assert.equal(s.drawerControls, 0, 'task toggles in the drawer');
    assert.equal(s.screenAfterLogs, 1, 'navigating a member to logs lands on Home');
    assert.deepEqual(errors, []);
  } finally { await context.close(); }
  // the phone menu, where the operator entries used to be listed
  const phone = await openApp(browser, { user: MEMBER, api: liveApi(), viewport: { width: 390, height: 860 } });
  try {
    await settled(phone.page);
    await phone.page.locator('.nav-hamburger button').last().click();
    const menu = await phone.page.locator('.mobile-menu').innerText();
    for (const label of OPERATOR) assert.ok(!menu.includes(label), `menu ${label}`);
    assert.match(menu, /Settings/);
    const bottom = await phone.page.locator('.mobile-bottom-nav').innerText();
    assert.ok(!bottom.includes('RL Monitor'), bottom);
  } finally { await phone.context.close(); }
});

test('the owner sees the operator chips, menu entries, tuning controls and Tweaks', async () => {
  const { context, page, errors } = await openApp(browser, {
    user: OWNER, api: liveApi({ '/ui/logs/stream': json({ detail: 'Owner only.' }, 403) }) });
  try {
    await settled(page);
    const s = await operatorSurface(page);
    for (const label of OPERATOR) assert.ok(s.chips.some(t => t.includes(label)), `chip ${label}: ${s.chips}`);
    assert.ok(s.topNav.some(t => t.includes('RL Monitor')), s.topNav);
    assert.equal(s.tweaks, 1);
    assert.equal(s.slider, 1, 'weight slider');
    assert.equal(s.plugButton, 1, 'plug button');
    assert.equal(s.screenAfterLogs, 0, 'the owner reaches the logs screen');
    assert.deepEqual(errors, []);
  } finally { await context.close(); }
  const phone = await openApp(browser, { user: OWNER, api: liveApi(), viewport: { width: 390, height: 860 } });
  try {
    await settled(phone.page);
    await phone.page.locator('.nav-hamburger button').last().click();
    const menu = await phone.page.locator('.mobile-menu').innerText();
    for (const label of ['Prompt Lab', 'Analytics', 'Logs', 'RL Monitor']) assert.ok(menu.includes(label), `menu ${label}`);
  } finally { await phone.context.close(); }
});

test('the learnings section shows dated verdict changes and no money figure, even from an old server', async () => {
  const legacy = {
    // what /ui/learnings sent before PR-001: a server not yet redeployed
    summary: { missedGain: 18420, avoidedLoss: 6180, realizedLoss: 0, accuracyVsAgent: 0.62, actionsReviewed: 2 },
    patterns: [{ id: 'p1', label: 'Correct verdict calls this period', rate: 0.5, kind: 'good', detail: '1 of 2' }],
    items: [{ id: 'turned-bullish-qwatchx', kind: 'turned-bullish', severity: 'low', sym: 'QWATCHX',
              title: 'QWATCHX: SELL → BUY', when: '2026-10-10', what: 'Orders picked up.',
              detail: 'Score moved +0.21 → now BUY', cost: 'Score moved +0.21 → now BUY', costValue: 2100,
              lesson: 'When score crosses 0.70+, QWATCHX has shown sustained upside. Watch agent weights.',
              action: 'Review agent details', agentSnapshot: [{ n: 'Fundamentals', v: 0.72 }] }],
  };
  const { context, page, errors } = await openApp(browser, {
    user: MEMBER, api: liveApi({ '/ui/learnings': json(legacy),
                                 '/portfolio': json({ holdings: [] }) }) });
  try {
    await settled(page);
    await page.waitForFunction(() => window.__learningsLive === true);
    await goTo(page, 'portfolio');
    const text = await visibleText(page);       // innerText applies CSS capitals
    assert.match(text, /Recent verdict changes/i);
    assert.match(text, /QWATCHX: SELL → BUY/);
    assert.match(text, /2026-10-10/);
    for (const gone of ['Missed gain', 'Avoided loss', 'Realized loss', 'agent agreement', 'Your patterns',
                        'Watch agent weights', 'Review agent details', '18,420', '6,180', '62%']) {
      assert.ok(!text.toLowerCase().includes(gone.toLowerCase()), gone);
    }
    // the only rupee figures are the empty portfolio's own zeros from /portfolio
    assert.deepEqual((text.match(RUPEE) || []).filter(m => m !== '₹0'), []);
    assert.deepEqual(errors, []);
  } finally { await context.close(); }
});

// The section's heading counts verdict changes only: its number is the change
// cards shown, a full list (the server's cap) is called the most recent, and a
// forecast miss is listed under its own heading and never counted.
const vChange = (sym, prev, cur, when, kind) => ({
  id: `${kind}-${sym.toLowerCase()}-${when}`, kind, severity: 'low', sym, title: `${sym}: ${prev} → ${cur}`,
  when, what: 'Orders picked up.', detail: `Score moved +0.10 → now ${cur}`, agentSnapshot: [] });
const fMiss = (sym, when) => ({
  id: `rl-${sym.toLowerCase()}-${when}`, kind: 'forecast-miss', severity: 'high', sym,
  title: `RL flag: model bias on ${sym}`, when, what: 'Agent fundamentals flagged as primary miss.',
  detail: 'Miss type: model_bias', agentSnapshot: [] });
const QSYMS = ['QALPHA', 'QBRAVO', 'QCHARLIE', 'QDELTA', 'QECHO', 'QFOXTROT', 'QGOLF', 'QHOTEL', 'QINDIA', 'QJULIET'];

async function learningsSection(items, since = null) {
  const { context, page, errors } = await openApp(browser, {
    user: MEMBER, api: liveApi({ '/ui/learnings': json({ items, since }), '/portfolio': json({ holdings: [] }) }) });
  try {
    await settled(page);
    await page.waitForFunction(() => window.__learningsLive === true);
    await goTo(page, 'portfolio');
    const text = await page.locator('.sa-learnings').innerText();   // CSS capitals on the eyebrows
    const [before, after = ''] = text.split(/latest forecast misses/i);
    const titles = (s) => s.split('\n').map(l => l.trim()).filter(l => /^Q[A-Z]+: [A-Z ]+ → [A-Z ]+$/.test(l));
    const flags = (s) => s.split('\n').filter(l => /^RL flag: /.test(l.trim()));
    return { text, changeCards: titles(before), missesBefore: flags(before), missCards: flags(after),
             missHeading: text.length !== before.length, errors };
  } finally { await context.close(); }
}

test('the verdict-changes heading counts the change cards it lists, never a forecast miss', async () => {
  const mixed = await learningsSection([
    vChange('QALPHA', 'NEUTRAL', 'BUY', '2026-10-13', 'bullish'),
    vChange('QBRAVO', 'BUY', 'SELL', '2026-10-10', 'turned-bearish'),
    vChange('QCHARLIE', 'SELL', 'BUY', '2026-10-09', 'turned-bullish'),
    fMiss('QDELTA', '2026-10-11'), fMiss('QECHO', '2026-10-08')]);
  const stated = Number(mixed.text.match(/(\d+) changes? in the analysed stocks/)?.[1]);
  assert.equal(stated, mixed.changeCards.length, mixed.text);
  assert.equal(stated, 3);
  assert.deepEqual(mixed.missesBefore, [], 'no forecast miss among the changes');
  assert.equal(mixed.missCards.length, 2);
  assert.deepEqual(mixed.errors, []);

  const full = await learningsSection(QSYMS.map((s, i) =>
    vChange(s, 'NEUTRAL', 'BUY', `2026-10-${String(13 - i).padStart(2, '0')}`, 'bullish')));
  assert.match(full.text, /The 10 most recent changes in the analysed stocks/);
  assert.ok(!/^10 changes/m.test(full.text), 'a full list is the newest ten, not all of them');
  assert.equal(full.changeCards.length, 10);
  assert.equal(full.missHeading, false);

  const one = await learningsSection([vChange('QALPHA', 'BUY', 'NEUTRAL', '2026-10-13', 'neutral')]);
  assert.match(one.text, /1 change in the analysed stocks/);
  assert.equal(one.changeCards.length, 1);

  // With no change the heading says since when the analyses have been looking (FIX-010)
  const missesOnly = await learningsSection([fMiss('QDELTA', '2026-10-11'), fMiss('QECHO', '2026-10-08')],
                                            '2026-09-16');
  assert.match(missesOnly.text, /No verdict changes since 16 Sept?/);
  assert.ok(!/in the analysed stocks/.test(missesOnly.text), 'no bare claim about every analysed stock');
  assert.equal(missesOnly.changeCards.length, 0);
  assert.equal(missesOnly.missCards.length, 2);
  const noHistory = await learningsSection([fMiss('QDELTA', '2026-10-11')]);
  assert.match(noHistory.text, /No verdict changes recorded yet/);
});

// The verdict changes depend on the viewer (FIX-010): signed out, the page
// loads the shared stocks' changes; signing in fetches them again as the
// member, whose own holding then appears without a reload.
test('signing in fetches the verdict changes again as the new viewer', async () => {
  const shared = vChange('QSHARED', 'SELL', 'BUY', '2026-10-12', 'turned-bullish');
  const own = vChange('QMYOWN', 'BUY', 'SELL', '2026-10-13', 'turned-bearish');
  const asked = [];
  const { context, page, errors } = await openApp(browser, { user: MEMBER, signedOut: true, api: liveApi({
    '/auth/login': json({ token: 'fresh-session', user: MEMBER }),
    '/portfolio': json({ holdings: [] }),
    '/ui/learnings': (_u, req) => {
      const signedIn = /^Bearer fresh-session$/.test(req.headers()['authorization'] || '');
      asked.push(signedIn);
      return json({ items: signedIn ? [own, shared] : [shared], since: '2026-09-16' });
    } }) });
  try {
    await page.getByPlaceholder('you@example.com').fill(MEMBER.email);
    await page.locator('input[type=password]').first().fill('pw-for-the-test');
    await page.locator('form button[type=submit]').first().click();
    await page.locator('h1').first().waitFor({ timeout: 30000 });
    await settled(page);
    await page.waitForFunction(() => (window.PORTFOLIO_LEARNINGS?.items || []).length === 2, null,
                               { timeout: 8000 });
    await goTo(page, 'portfolio');
    const text = await page.locator('.sa-learnings').innerText();
    assert.match(text, /QMYOWN: BUY → SELL/, 'the member\'s own change, after sign-in');
    assert.match(text, /2 changes in the analysed stocks/);
    assert.deepEqual(asked, [false, true], 'once signed out at load, once as the member');
    assert.deepEqual(errors, []);
  } finally { await context.close(); }
});

// The verdict changes name the viewer's own holdings (FIX-010), so they never
// outlive the viewer on a shared tab: not after sign-out, not when the next
// account's own fetch fails, not when the previous viewer's answer comes late.
const SECOND = { user_id: 'u-second', email: 'second@example.test', display_name: 'Second Member', role: 'member' };

async function signOutThenIn(page, user) {
  await page.getByRole('button', { name: 'Sign out' }).first().click();
  await page.getByPlaceholder('you@example.com').waitFor({ timeout: 30000 });
  const atLogin = await page.evaluate(() => window.PORTFOLIO_LEARNINGS);
  await page.getByPlaceholder('you@example.com').fill(user.email);
  await page.locator('input[type=password]').first().fill('pw-for-the-test');
  await page.locator('form button[type=submit]').first().click();
  await page.locator('h1').first().waitFor({ timeout: 30000 });
  return atLogin;
}

test('signing out drops the verdict changes; a failed fetch for the next account shows none', async () => {
  const own = vChange('QMYOWN', 'BUY', 'SELL', '2026-10-13', 'turned-bearish');
  const asked = [];
  const { context, page, errors } = await openApp(browser, { user: MEMBER, api: liveApi({
    '/auth/logout': json({ ok: true }),
    '/auth/login': json({ token: 'second-session', user: SECOND }),
    '/portfolio': json({ holdings: [] }),
    '/ui/learnings': (_u, req) => {
      const first = (req.headers()['authorization'] || '') === 'Bearer test-session';
      asked.push(first ? 'first viewer' : 'next viewer');
      return first ? json({ items: [own], since: '2026-09-16' }) : json({ detail: 'unavailable' }, 503);
    } }) });
  try {
    await settled(page);
    await page.waitForFunction(() => window.__learningsLive === true);
    await goTo(page, 'portfolio');
    assert.match(await page.locator('.sa-learnings').innerText(), /QMYOWN: BUY → SELL/);
    const atLogin = await signOutThenIn(page, SECOND);
    assert.equal(atLogin, null, 'the list is dropped at sign-out');
    for (let i = 0; i < 40 && asked.length < 2; i++) await page.waitForTimeout(100);
    await page.waitForTimeout(400);
    await goTo(page, 'portfolio');
    assert.ok(!(await visibleText(page)).includes('QMYOWN'), 'the previous viewer\'s holding is not shown');
    assert.equal(await page.locator('.sa-learnings').count(), 0);
    assert.deepEqual(asked, ['first viewer', 'next viewer']);
    assert.deepEqual(errors, []);
  } finally { await context.close(); }
});

test('an answer for the previous viewer that arrives after the next sign-in is discarded', async () => {
  const own = vChange('QMYOWN', 'BUY', 'SELL', '2026-10-13', 'turned-bearish');
  let lateAnswerSent = false;
  const { context, page, errors } = await openApp(browser, { user: MEMBER, api: liveApi({
    '/auth/logout': json({ ok: true }),
    '/auth/login': json({ token: 'second-session', user: SECOND }),
    '/portfolio': json({ holdings: [] }),
    '/ui/learnings': async (_u, req) => {
      if ((req.headers()['authorization'] || '') !== 'Bearer test-session') {
        return json({ detail: 'unavailable' }, 503);
      }
      await new Promise(r => setTimeout(r, 4000));   // still in flight at sign-out and sign-in
      lateAnswerSent = true;
      return json({ items: [own], since: '2026-09-16' });
    } }) });
  try {
    await settled(page);
    await signOutThenIn(page, SECOND);
    for (let i = 0; i < 80 && !lateAnswerSent; i++) await page.waitForTimeout(100);
    assert.ok(lateAnswerSent, 'the slow answer was delivered during the test');
    await page.waitForTimeout(800);
    await goTo(page, 'portfolio');
    assert.equal(await page.evaluate(() => window.PORTFOLIO_LEARNINGS), null);
    assert.ok(!(await visibleText(page)).includes('QMYOWN'), 'the previous viewer\'s holding is not shown');
    assert.deepEqual(errors, []);
  } finally { await context.close(); }
});

test('demo mode is explicit: ?demo=1 shows the samples under a banner and asks no market API', async () => {
  const { context, page, calls, errors } = await openApp(browser, { user: MEMBER, query: '?demo=1' });
  try {
    await settled(page);
    assert.equal(await page.evaluate(() => window.__apiState), 'demo');
    const text = await visibleText(page);
    assert.match(text, /Sample data — the market figures and portfolio here are not live/);
    assert.match(text, /24,850/);                       // the fixture's Nifty 50 level
    for (const p of ['/ui/bootstrap', '/ui/nifty-ranges', '/ui/learnings']) {
      assert.ok(!calls.some(c => c.startsWith(p)), `${p} called in demo mode`);
    }
    assert.deepEqual(errors, []);
  } finally { await context.close(); }
  // ...and without the switch the samples are not even defined
  const plain = await openApp(browser, { user: MEMBER, api: { '/ui/bootstrap': json({}, 500) } });
  try {
    await settled(plain.page);
    assert.equal(await plain.page.evaluate(() => window.saDemoFixtures), undefined);
    assert.equal(await plain.page.locator('.sa-demo-banner').count(), 0);
  } finally { await plain.context.close(); }
});

// -- PR-002: the weekly review opens with the results scorecard ------------------

// A real row's sessions and sentences, printed by the Python builder
// (core/portfolio/results.py) for idle cash in a rising Nifty, ten sales of
// which three have no grade, and one sale this week; one line of each kind.
const SCORECARD = {
  week: '2026-W10', sessions: { count: 5, first: '2026-03-02', last: '2026-03-06' },
  lines: [
    { kind: 'red_flag', text: 'Behind the Nifty: over the last 4 weeks the portfolio made +0.0% against +10.0% for the same money in the Nifty (10.0 points behind; red line 3).' },
    { kind: 'unchecked', text: 'Selling too early: could not check. 3 of 10 sales have no 30-session grade; the share is between 40% and 70% (red line 60%).' },
    { kind: 'line', label: 'Closed trades', text: 'This week: 1 trade · 1 won (100%) · average win +12.0% · expectancy +12.0% per trade, before costs.' },
    { kind: 'check', status: 'clear', text: 'Holding period: positions closed this week were held a median of 12 sessions (red line: under 10).' },
  ],
};
const WEEKLY = {
  date: '2026-03-08', kind: 'weekly_review', headline: 'Idle cash cost ten points against the Nifty.',
  allocation: [], concentration_flags: [], laggards: [], switch_candidates: [], switch_suggestions: [],
  scoreboard: { counts: { EXIT: 2 }, checked: 9, correct: 7 },   // the replaced scoreboard: never shown
  scorecard: SCORECARD,
};

async function openWeekly(review) {
  const app = await openApp(browser, { user: MEMBER,
                                       api: { '/delivery/weekly/latest': json(review) } });
  await settled(app.page);
  await goTo(app.page, 'inbox');
  await app.page.getByRole('button', { name: 'Weekly', exact: true }).click();
  await app.page.getByText(review.headline).waitFor({ timeout: 10000 });
  return app;
}

test('the weekly review opens with its scorecard: red flags, then what could not be checked', async () => {
  const { context, page, errors } = await openWeekly(WEEKLY);
  try {
    const text = await visibleText(page);
    const at = (s) => { const i = text.indexOf(s); assert.ok(i >= 0, `missing "${s}" in:\n${text}`); return i; };
    assert.ok(at('Red flag · Behind the Nifty') < at('Could not check · Selling too early'));
    assert.ok(at('Could not check · Selling too early') < at('This week: 1 trade'));
    assert.ok(at('This week: 1 trade') < at(WEEKLY.headline), 'the results come before the headline');
    assert.ok(at('red line: under 10') > at('This week: 1 trade'), 'clear checks come last');
    assert.ok(!/judged calls right|7\/9/.test(text), 'the old scoreboard is not shown');
    const sent = JSON.stringify(SCORECARD);
    for (const m of text.match(PCT) || []) assert.ok(sent.includes(m), `${m} was not sent`);
    assert.deepEqual(errors, []);
  } finally { await context.close(); }
});

test('a weekly review whose scorecard failed says so; one stored before it shows none', async () => {
  let app = await openWeekly({ ...WEEKLY, scorecard: null });
  try {
    assert.match(await visibleText(app.page), /Results could not be computed this week\./);
  } finally { await app.context.close(); }
  const before = { ...WEEKLY };
  delete before.scorecard;
  app = await openWeekly(before);
  try {
    const text = await visibleText(app.page);
    assert.ok(!/results ·|could not be computed|judged calls right/i.test(text), text);
    assert.deepEqual(app.errors, []);
  } finally { await app.context.close(); }
});

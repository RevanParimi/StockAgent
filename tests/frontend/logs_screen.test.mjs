/**
 * FIX-007: the Logs screen against owner-only log routes, in the real browser.
 *
 *   node --test tests/frontend/logs_screen.test.mjs
 *
 * Mounts the real LogsPage (logs.jsx) under index.html's own <head>, so the
 * global fetch wrapper that signs requests and prompts for the API key on a
 * 403 runs as in production. Only /ui/logs/stream is replaced in the page,
 * underneath that wrapper: it records what the wrapper sent and answers 401,
 * 403, or an open event stream. Same no-network rules as chat_harness.mjs.
 */
import { test, before, after } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync, existsSync } from 'node:fs';
import path from 'node:path';
import { launch, ORIGIN, REPO, FRONTEND, CDN_FILES, CONTENT_TYPES } from './chat_harness.mjs';

const PAGE = `${ORIGIN}/logs-harness.html`;
const MARKER = 'FIX007-BROWSER-u_7f3a9c21';

function harnessHtml() {
  const index = readFileSync(path.join(FRONTEND, 'index.html'), 'utf8');
  return index.slice(0, index.indexOf('<body>')) + `<body><div id="root"></div>
<script type="text/babel" src="icons.jsx"></script>
<script type="text/babel">function TopNav() { return null; }</script>
<script type="text/babel" src="logs.jsx"></script>
<script type="text/babel">
ReactDOM.createRoot(document.getElementById('root')).render(<LogsPage onNav={() => {}}/>);
</script>
</body></html>`;
}

// Runs before any page script, so index.html's wrapper wraps this stub.
function pageInit(plan) {
  if (plan.token) localStorage.setItem('sa_auth_token', plan.token);
  window.__logsCalls = [];
  const originalFetch = window.fetch.bind(window);
  window.fetch = async (input, init) => {
    const url = typeof input === 'string' ? input : ((input && input.url) || '');
    if (!url.startsWith('/ui/logs/stream')) return originalFetch(input, init);
    window.__logsCalls.push({ url, headers: Object.assign({}, (init && init.headers) || {}) });
    if (plan.status !== 200) {
      return new Response(JSON.stringify({ detail: plan.status === 403 ? 'Owner only.' : 'Login required.' }),
                          { status: plan.status, headers: { 'Content-Type': 'application/json' } });
    }
    const enc = new TextEncoder();
    const body = new ReadableStream({
      start(ctrl) {
        ctrl.enqueue(enc.encode(': keepalive\n\n'));
        for (const e of plan.entries) ctrl.enqueue(enc.encode('data: ' + JSON.stringify(e) + '\n\n'));
        // left open, as the server's stream is
      },
    });
    return new Response(body, { status: 200, headers: { 'Content-Type': 'text/event-stream' } });
  };
}

async function openLogs(browser, plan) {
  const context = await browser.newContext({ serviceWorkers: 'block' });
  const blocked = [];
  await context.route('**/*', async (route) => {
    const url = route.request().url();
    if (url === PAGE) return route.fulfill({ status: 200, contentType: 'text/html', body: harnessHtml() });
    if (url.startsWith(ORIGIN + '/')) {
      const name = decodeURIComponent(new URL(url).pathname.slice(1));
      const file = path.join(FRONTEND, name);
      if (!name || name.includes('..') || !existsSync(file)) {
        blocked.push(url);
        return route.fulfill({ status: 404, body: 'not found' });
      }
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
    blocked.push(url);
    return route.abort('blockedbyclient');
  });
  await context.addInitScript(pageInit, { status: 200, entries: [], token: '', ...plan });
  const page = await context.newPage();
  const dialogs = [];
  page.on('dialog', async (d) => { dialogs.push(d.message()); await d.dismiss(); });
  await page.goto(PAGE);
  return { context, page, dialogs, blocked };
}

let browser;
before(async () => { browser = await launch(); });
after(async () => { await browser?.close(); });

const entry = (msg) => ({ ts: '2026-10-12 09:00:00 IST', level: 'WARNING', name: 'brief', msg });

test('a member is told the logs are owner-only, is not asked for a key, and the screen stops asking', async () => {
  const { context, page, dialogs } = await openLogs(browser, { status: 403, token: 'member-tok' });
  try {
    const note = page.locator('.logs-refusal');
    await note.waitFor();
    assert.equal(await note.textContent(), 'Server logs are visible to the owner account only.');
    await page.waitForTimeout(6000);                  // longer than the 5 s reconnect delay
    const calls = await page.evaluate(() => window.__logsCalls);
    assert.equal(calls.length, 1, 'a refusal is final: no reconnect');
    assert.equal(calls[0].headers.Authorization, 'Bearer member-tok');
    assert.deepEqual(dialogs, [], 'no API-key prompt for a member');
    assert.equal(await page.getByText('refused', { exact: true }).count(), 1);
  } finally { await context.close(); }
});

test('a signed-out visitor is asked to sign in as the owner', async () => {
  const { context, page, dialogs } = await openLogs(browser, { status: 401 });
  try {
    const note = page.locator('.logs-refusal');
    await note.waitFor();
    assert.equal(await note.textContent(), 'Sign in with the owner account to see server logs.');
    const calls = await page.evaluate(() => window.__logsCalls);
    assert.equal(calls.length, 1);
    assert.equal(calls[0].headers.Authorization, undefined);
    assert.deepEqual(dialogs, []);
  } finally { await context.close(); }
});

test("the owner's session is sent and the stream's lines are shown live", async () => {
  const { context, page, dialogs, blocked } = await openLogs(browser, {
    token: 'owner-tok', entries: [entry(`[brief] build failed for ${MARKER}`)],
  });
  try {
    await page.getByText(`[brief] build failed for ${MARKER}`).waitFor();
    await page.getByText('live', { exact: true }).waitFor();
    const calls = await page.evaluate(() => window.__logsCalls);
    assert.equal(calls.length, 1);
    assert.equal(calls[0].headers.Authorization, 'Bearer owner-tok');
    assert.equal(await page.locator('.logs-refusal').count(), 0);
    assert.deepEqual(dialogs, []);
    assert.deepEqual(blocked.filter((u) => u.includes('/ui/logs')), [], 'no EventSource request');
  } finally { await context.close(); }
});

/**
 * Browser harness for the chat Markdown boundary (SA-001).
 *
 * Serves src/frontend/prototypes/ from a fake origin and mounts the real
 * ChatOverlay (sphere.jsx) under index.html's own <head>, so the same pinned
 * CDN scripts, SRI hashes and chat-markdown.js run as in production. CDN URLs
 * are answered from node_modules copies; the browser still enforces the SRI
 * hashes, so a byte mismatch fails the test instead of passing silently.
 * Every other request is aborted and recorded: no real network.
 *
 * The chat transport is replaced in the page: /ui/chat/stream becomes a
 * ReadableStream that emits the planned SSE token events with a gap between
 * them, so each partial text reaches the sink as its own React render.
 *
 * SA_FRONTEND_ROOT=<dir> points the harness at another copy of the prototype
 * files (used to show the fixtures execute on the pre-fix revision).
 */
import { chromium } from 'playwright';
import { readFileSync, existsSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const REPO = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..', '..');
const FRONTEND = process.env.SA_FRONTEND_ROOT || path.join(REPO, 'src', 'frontend', 'prototypes');
export const ORIGIN = 'http://sa.test';
export const PAGE_URL = `${ORIGIN}/harness.html`;
export const LINK_ORIGIN = 'https://example.test';

// CDN script URL -> node_modules file. Version-agnostic on purpose: the SRI
// hash in index.html, not this table, decides whether the bytes are right.
const CDN_FILES = [
  [/^https:\/\/unpkg\.com\/react@[^/]+\/umd\/react\.development\.js$/, 'react/umd/react.development.js'],
  [/^https:\/\/unpkg\.com\/react-dom@[^/]+\/umd\/react-dom\.development\.js$/, 'react-dom/umd/react-dom.development.js'],
  [/^https:\/\/unpkg\.com\/@babel\/standalone@[^/]+\/babel\.min\.js$/, '@babel/standalone/babel.min.js'],
  [/^https:\/\/cdn\.jsdelivr\.net\/npm\/marked@[^/]+\/marked\.min\.js$/, 'marked/marked.min.js'],
  [/^https:\/\/cdn\.jsdelivr\.net\/npm\/dompurify@[^/]+\/dist\/purify\.min\.js$/, 'dompurify/dist/purify.min.js'],
];

const CONTENT_TYPES = { '.js': 'text/javascript', '.jsx': 'text/babel', '.css': 'text/css',
                        '.html': 'text/html', '.json': 'application/json' };

function harnessHtml() {
  const index = readFileSync(path.join(FRONTEND, 'index.html'), 'utf8');
  const head = index.slice(0, index.indexOf('<body>'));
  return head + `<body><div id="root"></div>
<script type="text/babel" src="icons.jsx"></script>
<script type="text/babel" src="sphere.jsx"></script>
<script type="text/babel">
ReactDOM.createRoot(document.getElementById('root')).render(<ChatOverlay open={true} onClose={() => {}}/>);
</script>
</body></html>`;
}

// Runs in every page before any page script.
function pageInit() {
  window.__xssHits = [];
  window.__xss = (id) => { window.__xssHits.push(String(id)); };
  window.__chatPlan = { tokens: [], gapMs: 20, streamFails: false, reply: '' };
  window.__chatDone = false;

  const originalFetch = window.fetch.bind(window);
  const sse = (obj) => new TextEncoder().encode('data: ' + JSON.stringify(obj) + '\n\n');
  window.fetch = async (input, init) => {
    const url = typeof input === 'string' ? input : ((input && input.url) || '');
    const plan = window.__chatPlan;
    if (url === '/ui/chat/stream') {
      if (plan.streamFails) throw new TypeError('stream unavailable (test)');
      const body = new ReadableStream({
        async start(ctrl) {
          ctrl.enqueue(sse({ event: 'intent', session_id: 's-test', tier: 'active', query: 'q' }));
          for (const text of plan.tokens) {
            await new Promise((r) => setTimeout(r, plan.gapMs));
            ctrl.enqueue(sse({ event: 'token', text }));
          }
          ctrl.enqueue(sse({ event: 'done' }));
          ctrl.close();
          window.__chatDone = true;
        },
      });
      return new Response(body, { status: 200, headers: { 'Content-Type': 'text/event-stream' } });
    }
    if (url === '/ui/chat') {
      window.__chatDone = true;
      return new Response(JSON.stringify({ reply: plan.reply, session_id: 's-test' }),
                          { status: 200, headers: { 'Content-Type': 'application/json' } });
    }
    return originalFetch(input, init);
  };

  // Safety invariants for rendered chat HTML. Deliberately independent of the
  // sanitizer's configuration: they state what must never reach the page.
  const MARKDOWN_TAGS = new Set(['P', 'BR', 'HR', 'STRONG', 'EM', 'DEL', 'CODE', 'PRE',
    'BLOCKQUOTE', 'UL', 'OL', 'LI', 'A', 'H1', 'H2', 'H3', 'H4', 'H5', 'H6',
    'TABLE', 'THEAD', 'TBODY', 'TR', 'TH', 'TD']);
  const PLAIN_ATTRS = new Set(['href', 'title', 'align', 'start', 'target', 'rel']);
  window.__inspect = (root, { allowCursor = false } = {}) => {
    const out = [];
    for (const el of root.querySelectorAll('*')) {
      const tag = el.tagName.toUpperCase();
      const isCursor = allowCursor && tag === 'SPAN' && el.getAttribute('class') === 'chat-cursor';
      if (!MARKDOWN_TAGS.has(tag) && !isCursor) out.push(`element <${tag.toLowerCase()}>`);
      for (const attr of el.attributes) {
        const name = attr.name.toLowerCase();
        if (name.startsWith('on')) out.push(`event attribute ${name}`);
        else if (!PLAIN_ATTRS.has(name) && !(isCursor && name === 'class')) out.push(`attribute ${name}`);
      }
      if (el.hasAttribute('href')) {
        let protocol = null;
        try { protocol = new URL(el.getAttribute('href'), document.baseURI).protocol; } catch (e) {}
        if (protocol !== 'http:' && protocol !== 'https:') out.push(`href protocol ${protocol}`);
        if (tag === 'A') {
          const rel = (el.getAttribute('rel') || '').split(/\s+/);
          if (el.getAttribute('target') !== '_blank') out.push('link target is not _blank');
          if (!rel.includes('noopener') || !rel.includes('noreferrer')) out.push('link rel lacks noopener noreferrer');
        }
      }
    }
    return out;
  };
}

/**
 * Open the harness in a fresh browser context.
 * options.cdn: { [packageName]: 'missing' | 'tampered' } breaks one library.
 * options.missing: same-origin file names to answer with 404.
 */
export async function openChat(browser, options = {}) {
  const context = await browser.newContext({ serviceWorkers: 'block' });
  const blocked = [];
  await context.route('**/*', async (route) => {
    const url = route.request().url();
    if (url === PAGE_URL) {
      return route.fulfill({ status: 200, contentType: 'text/html', body: harnessHtml() });
    }
    if (url.startsWith(ORIGIN + '/')) {
      const name = decodeURIComponent(new URL(url).pathname.slice(1));
      const file = path.join(FRONTEND, name);
      if ((options.missing || []).includes(name) || !name || name.includes('..') || !existsSync(file)) {
        return route.fulfill({ status: 404, body: 'not found' });
      }
      return route.fulfill({ status: 200, body: readFileSync(file),
                             contentType: CONTENT_TYPES[path.extname(file)] || 'application/octet-stream' });
    }
    for (const [pattern, rel] of CDN_FILES) {
      if (!pattern.test(url)) continue;
      const pkg = rel.split('/')[0] === '@babel' ? '@babel/standalone' : rel.split('/')[0];
      const mode = (options.cdn || {})[pkg];
      if (mode === 'missing') return route.fulfill({ status: 404, body: 'not found' });
      let body = readFileSync(path.join(REPO, 'node_modules', rel));
      if (mode === 'tampered') body = Buffer.concat([body, Buffer.from('\n/* tampered */\n')]);
      return route.fulfill({ status: 200, body, contentType: 'text/javascript',
                             headers: { 'Access-Control-Allow-Origin': '*' } });
    }
    if (url.startsWith(LINK_ORIGIN + '/')) {
      return route.fulfill({ status: 200, contentType: 'text/html',
                             body: '<!doctype html><title>landing</title><p>landing</p>' });
    }
    blocked.push(url);
    return route.abort('blockedbyclient');
  });
  await context.addInitScript(pageInit);

  const page = await context.newPage();
  const dialogs = [];
  page.on('dialog', async (d) => { dialogs.push(d.message()); await d.dismiss(); });
  await page.goto(PAGE_URL);
  await page.waitForSelector('.chat-md');   // greeting bubble: React + Babel are up

  // Record every committed state of every bot bubble, not only the final one.
  await page.evaluate(() => {
    window.__sinkRenders = 0;
    window.__sinkViolations = [];
    const seen = new Set();
    const check = () => {
      window.__sinkRenders += 1;
      for (const el of document.querySelectorAll('.chat-md')) {
        for (const v of window.__inspect(el, { allowCursor: true })) {
          if (!seen.has(v)) { seen.add(v); window.__sinkViolations.push(v); }
        }
      }
    };
    new MutationObserver(check).observe(document.getElementById('root'),
      { subtree: true, childList: true, characterData: true, attributes: true });
  });
  return { context, page, blocked, dialogs };
}

/** Split text the way the server's _chunk_for_stream does (3-word groups). */
export function serverChunks(text) {
  const words = text.split(' ');
  const out = [];
  for (let i = 0; i < words.length; i += 3) {
    const piece = words.slice(i, i + 3).join(' ');
    out.push(i + 3 >= words.length ? piece : piece + ' ');
  }
  return out;
}

/**
 * Send one user message through the real ChatOverlay form and wait until the
 * bot reply is complete. plan: { tokens } for the stream, or
 * { streamFails: true, reply } for the blocking /ui/chat fallback.
 * Returns the last bot bubble's element handle.
 */
export async function sendChat(page, plan, settleMs = 1200) {
  await page.evaluate((p) => {
    window.__chatDone = false;
    Object.assign(window.__chatPlan, { gapMs: 20, streamFails: false, tokens: [], reply: '' }, p);
  }, plan);
  const before = await page.locator('.chat-md').count();
  await page.fill('input[placeholder^="Ask"]', 'test question');
  await page.press('input[placeholder^="Ask"]', 'Enter');
  await page.waitForFunction(() => window.__chatDone === true);
  await page.waitForFunction((n) => {
    const bubbles = document.querySelectorAll('.chat-md');
    return bubbles.length > n && !document.querySelector('.chat-cursor')
      && bubbles[bubbles.length - 1].textContent !== '…';
  }, before);
  await page.waitForTimeout(settleMs);   // let async handlers (onerror, onbegin, ontoggle) fire
  return page.locator('.chat-md').last();
}

export async function launch() {
  return chromium.launch({ headless: true });
}

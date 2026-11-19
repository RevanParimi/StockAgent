// The data the member screens read. Market data comes only from the API (see
// "Market data" below); sample values for demo mode live in demo-fixtures.js.
// The agents' task catalogue is the owner's Agents page's own (agents-page.jsx,
// PR-040), and the Learn course went with the Learn page.

// ─── Market data ───────────────────────────────────────────────────────────
// Every market global starts empty. /ui/bootstrap fills them; until it
// answers a screen shows "Loading…", and if it fails the screen says the data
// is unavailable. Nothing falls back to sample values (PR-001). Demo mode
// (?demo=1, index.html) is the one exception: it installs demo-fixtures.js's
// sample values instead and makes no market API call.
//
// window.__apiState: 'loading' | 'ready' | 'failed' | 'demo'. App() re-renders
// through window.__onApiReady when it settles either way.
Object.assign(window, {
  AGENTS: [], TICKERS: [], WATCHLIST: [], TRENDING: [], SUGGESTIONS: [], CATEGORIES: [],
  MARKET_TODAY: null, MARKET_MONTH: null, NIFTY50: null, NIFTY_AUTO_HISTORY: [],
  PORTFOLIO_LEARNINGS: null, AGENT_TASK_FLAGS: {},
  // Questions only, never a claim about a stock (same list as the server's).
  CHAT_SEEDS: [
    'How is my portfolio doing?',
    'What moved the market today?',
    'What should I watch in my holdings this week?',
    'Explain the latest verdict on one of my stocks',
  ],
});
window.__apiReady = false;
window.__apiState = 'loading';

function saApiSettled(state) {
  window.__apiState = state;
  window.__apiReady = state === 'ready' || state === 'demo';
  if (typeof window.__onApiReady === 'function') window.__onApiReady();
}

function saApplyDemoFixtures() {
  Object.assign(window, window.saDemoFixtures || {});
  window.__learningsLive = false;
  saApiSettled('demo');
}

if (window.saDemoMode) {
  // index.html requests demo-fixtures.js only in demo mode, without blocking
  // the page: apply it now if it has run, else when it has (PR-040).
  if (window.saDemoFixtures) saApplyDemoFixtures();
  else window.addEventListener('sa-demo-fixtures', saApplyDemoFixtures, { once: true });
} else {
  (async function loadFromAPI() {
    try {
      const res = await fetch('/ui/bootstrap');
      if (!res.ok) throw new Error('bootstrap HTTP ' + res.status);
      const d = await res.json();

      if (Array.isArray(d.AGENTS))      window.AGENTS      = d.AGENTS;
      if (Array.isArray(d.TICKERS))     window.TICKERS     = d.TICKERS;
      if (Array.isArray(d.WATCHLIST))   window.WATCHLIST   = d.WATCHLIST;
      if (Array.isArray(d.TRENDING))    window.TRENDING    = d.TRENDING;
      if (Array.isArray(d.SUGGESTIONS)) window.SUGGESTIONS = d.SUGGESTIONS;
      if (Array.isArray(d.CATEGORIES))  window.CATEGORIES  = d.CATEGORIES;
      if (d.MARKET_TODAY)               window.MARKET_TODAY = d.MARKET_TODAY;
      if (d.MARKET_MONTH)               window.MARKET_MONTH = d.MARKET_MONTH;
      window.NIFTY50 = d.NIFTY50 || null;
      if (Array.isArray(d.NIFTY_AUTO_HISTORY)) window.NIFTY_AUTO_HISTORY = d.NIFTY_AUTO_HISTORY;
      if (d.CHAT_SEEDS?.length)         window.CHAT_SEEDS  = d.CHAT_SEEDS;

      // T2.2 — the persisted agent task flags; the owner's Agents page applies
      // them to its catalogue (agents-page.jsx).
      window.AGENT_TASK_FLAGS = (d.AGENT_TASK_FLAGS && typeof d.AGENT_TASK_FLAGS === 'object')
        ? d.AGENT_TASK_FLAGS : {};

      window.__apiLive      = d._liveData ?? false;
      window.__apiFetchedAt = d._fetchedAt;
      saApiSettled('ready');
    } catch (e) {
      console.warn('[StockAgent] Bootstrap API unavailable — market data shown as unavailable.', e);
      saApiSettled('failed');
    }

    await saLoadLearnings();
  })();
}

// T2.5 — recent verdict changes, fetched separately (not in bootstrap to keep it
// fast). They depend on the viewer: the viewer's own stocks join the shared ones
// (FIX-010). So a sign-in after this page loaded fetches them again
// (window.saSetToken in index.html calls this).
//
// The list names the viewer's own holdings, so it never outlives its viewer:
// every change of account passes through sign-out (window.saClearToken: the
// button, an expired session, a deleted account), which drops it, so the next
// account's failed fetch shows no list; and an answer that arrives after a
// sign-out is discarded.
let saLearningsViewer = 0;
function saForgetLearnings() {
  if (window.saDemoMode) return;
  saLearningsViewer += 1;
  window.PORTFOLIO_LEARNINGS = null;
  window.__learningsLive = false;
  if (typeof window.__onApiReady === 'function') window.__onApiReady();
}
async function saLoadLearnings() {
  if (window.saDemoMode) return;
  const viewer = saLearningsViewer;
  try {
    const lr = await fetch('/ui/learnings');
    if (!lr.ok) return;
    const learnings = await lr.json();
    if (viewer !== saLearningsViewer) return;   // signed out meanwhile
    const live = (learnings.items?.length || 0) > 0;
    window.PORTFOLIO_LEARNINGS = live ? learnings : null;
    window.__learningsLive = live;
    if (typeof window.__onApiReady === 'function') window.__onApiReady();
  } catch {
    // no section: there is nothing real to show
  }
}
window.saLoadLearnings = saLoadLearnings;
window.saForgetLearnings = saForgetLearnings;

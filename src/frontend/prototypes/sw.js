/* StockAgent service worker
 * Goals: make the app installable (PWA/TWA) and work offline as a shell,
 * WITHOUT ever serving stale live market data.
 *   - API / streaming paths  -> network only (not intercepted, never cached)
 *   - navigations            -> network-first, fall back to cached shell
 *   - same-origin static GET -> stale-while-revalidate
 *   - cross-origin CDN libs  -> cache-first
 */
const VERSION = 'v6';
const SHELL_CACHE = `sa-shell-${VERSION}`;
const RUNTIME_CACHE = `sa-runtime-${VERSION}`;

const SHELL = [
  '/', '/index.html', '/styles.css', '/manifest.json',
  '/data.jsx', '/icons.jsx', '/sphere.jsx', '/auth.jsx', '/home.jsx',
  '/agents-page.jsx', '/portfolio.jsx', '/learn.jsx', '/tweaks-panel.jsx',
  '/prompt-lab.jsx', '/analytics.jsx', '/logs.jsx', '/rl-data.jsx', '/rl-monitor.jsx',
  '/inbox.jsx',
  '/icons/pwa-192x192.png', '/icons/pwa-512x512.png', '/icons/pwa-maskable-512x512.png',
  '/icons/apple-touch-icon.png', '/icons/favicon-32x32.png',
];

// Always hit the network for these (live data / docs) — never cache.
const API_PREFIXES = [
  '/api', '/ui', '/analyse', '/history', '/health', '/tickers',
  '/scheduler', '/prompts', '/analytics', '/ws', '/docs', '/redoc', '/openapi.json',
  '/delivery', '/portfolio', '/discovery',
];

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(SHELL_CACHE)
      .then((cache) => cache.addAll(SHELL))
      .then(() => self.skipWaiting())
      .catch(() => self.skipWaiting()) // don't block install if an asset 404s
  );
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(
        keys.filter((k) => k !== SHELL_CACHE && k !== RUNTIME_CACHE).map((k) => caches.delete(k))
      ))
      .catch(() => {}) // a broken CacheStorage must never block activation
      .then(() => self.clients.claim())
  );
});

// CacheStorage can fail wholesale at runtime (Android storage corruption /
// eviction: "UnknownError: Unexpected internal error"). Every cache op below
// therefore degrades to plain network instead of rejecting respondWith() —
// otherwise ONE broken cache blanks the whole app even when the network is
// fine (reproduced 2026-07-24: notification tap → blank page).
function safeOpen(name) {
  return caches.open(name).catch(() => null);
}

function isApi(pathname) {
  return API_PREFIXES.some((p) => pathname === p || pathname.startsWith(p + '/'));
}

self.addEventListener('fetch', (event) => {
  const req = event.request;
  if (req.method !== 'GET') return; // POST etc. (API) -> default network
  const url = new URL(req.url);

  if (url.origin !== self.location.origin) {
    event.respondWith(cacheFirst(req));
    return;
  }
  if (isApi(url.pathname)) return; // live data -> default network, never cached

  if (req.mode === 'navigate') {
    event.respondWith(
      fetch(req).catch(() =>
        caches.match('/index.html')
          .catch(() => undefined)
          .then((cached) => cached || Response.error())
      )
    );
    return;
  }
  event.respondWith(staleWhileRevalidate(req));
});

function cacheFirst(req) {
  return safeOpen(RUNTIME_CACHE).then((cache) => {
    if (!cache) return fetch(req);
    return cache.match(req)
      .catch(() => undefined)
      .then((cached) =>
        cached || fetch(req).then((res) => {
          if (res && res.status === 200) {
            const copy = res.clone();
            cache.put(req, copy).catch(() => {});
          }
          return res;
        })
      );
  });
}

function staleWhileRevalidate(req) {
  return safeOpen(RUNTIME_CACHE).then((cache) => {
    if (!cache) return fetch(req);
    return cache.match(req)
      .catch(() => undefined)
      .then((cached) => {
        const network = fetch(req)
          .then((res) => {
            if (res && res.status === 200) {
              const copy = res.clone();
              cache.put(req, copy).catch(() => {});
            }
            return res;
          })
          .catch(() => cached);
        return cached || network;
      });
  });
}

/* Compass Phase C — web-push (M4 proactive delivery).
 * Payload: {"title": ..., "body": ..., "url": ...} from core/delivery/channels.py */
self.addEventListener('push', (event) => {
  let data = {};
  try { data = event.data ? event.data.json() : {}; }
  catch (e) { data = { body: event.data ? event.data.text() : '' }; }
  event.waitUntil(self.registration.showNotification(data.title || 'StockAgent', {
    body: data.body || '',
    icon: '/icons/pwa-192x192.png',
    badge: '/icons/pwa-192x192.png',
    data: { url: data.url || '/' },
  }));
});

self.addEventListener('notificationclick', (event) => {
  event.notification.close();
  const url = (event.notification.data && event.notification.data.url) || '/';
  event.waitUntil(
    clients.matchAll({ type: 'window', includeUncontrolled: true }).then((wins) => {
      for (const w of wins) {
        if ('focus' in w) {
          // Warm tap: tell the open app where to go, then bring it forward.
          w.postMessage({ type: 'sa-open', url });
          return w.focus();
        }
      }
      return clients.openWindow(url);
    })
  );
});

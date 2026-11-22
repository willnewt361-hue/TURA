/* TURA service worker — app shell cache for offline-first */
const CACHE_PREFIX = 'tura-shell-';
const CACHE = `${CACHE_PREFIX}v13`;
const SHELL = [
  '/app/',
  '/manifest.webmanifest',
  '/css/map.css',
  '/css/tura.css',
  '/js/api.js',
  '/js/store.js',
  '/js/ws.js',
  '/js/i18n.js',
  '/js/tour.js',
  '/js/theme.js',
  '/js/map.js',
  '/js/app.js',
  '/assets/logo.svg',
  '/assets/uganda-coach.svg',
  '/assets/pwa-icon-180.png',
  '/assets/pwa-icon-192.png',
  '/assets/pwa-icon-512.png',
];

self.addEventListener('install', (event) => {
  event.waitUntil(caches.open(CACHE).then((c) => c.addAll(SHELL)).then(() => self.skipWaiting()));
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(
        keys
          .filter((key) => key.startsWith(CACHE_PREFIX) && key !== CACHE)
          .map((key) => caches.delete(key))
      )
    ).then(() => self.clients.claim())
  );
});

// The page can ask a waiting worker to activate immediately after an update.
self.addEventListener('message', (event) => {
  if (event.data && event.data.type === 'SKIP_WAITING') self.skipWaiting();
});

self.addEventListener('fetch', (event) => {
  const url = new URL(event.request.url);
  if (event.request.method !== 'GET' || url.origin !== self.location.origin) return;
  if (url.pathname.startsWith('/api/') || url.pathname.startsWith('/ws')) return;

  event.respondWith((async () => {
    const cache = await caches.open(CACHE);
    const cacheKey = event.request.mode === 'navigate'
      ? new Request(`${url.origin}${url.pathname}`)
      : event.request;
    const cached = await cache.match(cacheKey);

    try {
      const response = await fetch(event.request);
      if (response.ok) await cache.put(cacheKey, response.clone());
      return response;
    } catch {
      if (cached) return cached;
      if (event.request.mode === 'navigate') {
        return (await cache.match('/app/'))
          || new Response('TURA is offline. Reconnect and open the app once to save it for offline use.', {
            status: 503,
            headers: { 'Content-Type': 'text/plain; charset=utf-8' },
          });
      }
      return new Response('This page is not available offline.', {
        status: 503,
        headers: { 'Content-Type': 'text/plain; charset=utf-8' },
      });
    }
  })());
});

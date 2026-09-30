/* TURA service worker — app shell cache for offline-first */
const CACHE = 'tura-shell-v9';
const SHELL = [
  '/',
  '/app/',
  '/pages/index.html',
  '/pages/login.html',
  '/pages/map-interface.html',
  '/pages/tracking.html',
  '/css/demo.css',
  '/css/map.css',
  '/js/demo.js',
  '/js/map.js',
  '/js/theme.js',
  '/css/tura.css',
  '/js/api.js',
  '/js/store.js',
  '/js/ws.js',
  '/js/i18n.js',
  '/js/tour.js',
  '/js/app.js',
  '/assets/logo.svg',
  '/assets/uganda-coach.svg',
  '/manifest.webmanifest',
];

self.addEventListener('install', (event) => {
  event.waitUntil(caches.open(CACHE).then((c) => c.addAll(SHELL)).then(() => self.skipWaiting()));
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k)))
    ).then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', (event) => {
  const url = new URL(event.request.url);
  if (event.request.method !== 'GET') return;
  if (url.pathname.startsWith('/api/') || url.pathname.startsWith('/ws')) return;

  event.respondWith(
    caches.match(event.request).then((cached) => {
      const fetchPromise = fetch(event.request)
        .then((res) => {
          if (res && res.ok && url.origin === location.origin) {
            const copy = res.clone();
            caches.open(CACHE).then((c) => c.put(event.request, copy));
          }
          return res;
        })
        .catch(() => cached);
      return cached || fetchPromise;
    })
  );
});

// Shree Daksha Academy Service Worker - Offline Ticket Pass Cache
const CACHE_NAME = 'sda-ticket-pass-v1';
const STATIC_ASSETS = [
  '/static/css/lenis.css',
  '/static/favicon.svg'
];

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => {
      return cache.addAll(STATIC_ASSETS).catch(() => {});
    }).then(() => self.skipWaiting())
  );
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) => {
      return Promise.all(
        keys.map((key) => {
          if (key !== CACHE_NAME) {
            return caches.delete(key);
          }
        })
      );
    }).then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', (event) => {
  const request = event.request;
  if (request.method !== 'GET') return;

  const url = new URL(request.url);

  // SEC-12: Clear cached passes on logout and never intercept authenticated or API endpoints
  if (url.pathname === '/logout') {
    caches.open(CACHE_NAME).then((cache) => {
      cache.keys().then((requests) => {
        requests.forEach((req) => {
          if (new URL(req.url).pathname.startsWith('/payment-status/')) {
            cache.delete(req);
          }
        });
      });
    });
    return;
  }

  if (
    url.pathname.startsWith('/admin') ||
    url.pathname.startsWith('/member') ||
    url.pathname.startsWith('/api/') ||
    url.pathname.startsWith('/login') ||
    url.pathname.startsWith('/scanner') ||
    url.pathname.startsWith('/payment-proofs/') ||
    url.pathname.startsWith('/static/uploads/payment_proofs/')
  ) {
    return;
  }

  // Network-first for payment status ticket passes, caching only the latest 3 passes for offline gate access
  if (url.pathname.startsWith('/payment-status/')) {
    event.respondWith(
      fetch(request)
        .then((response) => {
          if (response && response.status === 200) {
            const responseClone = response.clone();
            caches.open(CACHE_NAME).then((cache) => {
              cache.put(request, responseClone);
            });
          }
          return response;
        })
        .catch(() => {
          return caches.match(request).then((cachedResponse) => {
            if (cachedResponse) {
              return cachedResponse;
            }
            return new Response(
              '<!DOCTYPE html><html><head><meta charset="utf-8"><title>Offline Pass</title><meta name="viewport" content="width=device-width, initial-scale=1"></head><body style="font-family:system-ui,-apple-system,sans-serif;padding:32px 16px;text-align:center;background:#0b1220;color:#f8fafc;"><div style="max-width:400px;margin:40px auto;background:#1e293b;padding:24px;border-radius:12px;border:1px solid #334155;"><h2>📶 Offline</h2><p style="color:#94a3b8;font-size:14px;line-height:1.5;">This ticket pass has not been cached on this device yet. Please reconnect to the internet once to save it offline.</p></div></body></html>',
              { headers: { 'Content-Type': 'text/html' } }
            );
          });
        })
    );
    return;
  }

  // Static assets: cache-first with network fallback
  if (url.pathname.startsWith('/static/')) {
    event.respondWith(
      caches.match(request).then((cached) => {
        return cached || fetch(request).then((response) => {
          if (response && response.status === 200) {
            const responseClone = response.clone();
            caches.open(CACHE_NAME).then((cache) => {
              cache.put(request, responseClone);
            });
          }
          return response;
        });
      })
    );
    return;
  }
});

// Margo Service Worker v1.0 — Orbiby
const CACHE_NAME = 'margo-v1';
const ASSETS = [
  '/margo/',
  '/margo/index.html',
  '/margo/manifest.json',
  '/margo/icons/icon-192.png',
  '/margo/icons/icon-512.png',
];

// Instala e faz cache dos assets principais
self.addEventListener('install', event => {
  event.waitUntil(
    caches.open(CACHE_NAME).then(cache => cache.addAll(ASSETS))
  );
  self.skipWaiting();
});

// Ativa e limpa caches antigos
self.addEventListener('activate', event => {
  event.waitUntil(
    caches.keys().then(keys =>
      Promise.all(keys.filter(k => k !== CACHE_NAME).map(k => caches.delete(k)))
    )
  );
  self.clients.claim();
});

// Estratégia: Network first, cache como fallback
// — garante que o app sempre tenta buscar versão mais recente
self.addEventListener('fetch', event => {
  // Ignora requests ao backend Railway (sempre online)
  if (event.request.url.includes('railway.app')) return;
  // Ignora requests não-GET
  if (event.request.method !== 'GET') return;

  event.respondWith(
    fetch(event.request)
      .then(response => {
        // Atualiza cache com resposta mais recente
        const clone = response.clone();
        caches.open(CACHE_NAME).then(cache => cache.put(event.request, clone));
        return response;
      })
      .catch(() => {
        // Sem internet — serve do cache
        return caches.match(event.request).then(cached => {
          if (cached) return cached;
          // Fallback para index.html se não achou no cache
          return caches.match('/margo/index.html');
        });
      })
  );
});

// Push notifications — base para lembretes futuros
self.addEventListener('push', event => {
  if (!event.data) return;
  const data = event.data.json();
  self.registration.showNotification(data.title || 'Margo', {
    body:    data.body || '',
    icon:    '/margo/icons/icon-192.png',
    badge:   '/margo/icons/icon-96.png',
    vibrate: [200, 100, 200],
    data:    { url: data.url || '/margo/' }
  });
});

// Clique na notificação — abre o app
self.addEventListener('notificationclick', event => {
  event.notification.close();
  event.waitUntil(
    clients.openWindow(event.notification.data.url || '/margo/')
  );
});

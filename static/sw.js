const CACHE = "brain-v2";
const SHELL = [
  "/app",
  "/static/style.css",
  "/static/app.js",
];

self.addEventListener("install", e => {
  e.waitUntil(caches.open(CACHE).then(c => c.addAll(SHELL)));
  self.skipWaiting();
});

self.addEventListener("activate", e => {
  e.waitUntil(
    caches.keys().then(keys =>
      Promise.all(keys.filter(k => k !== CACHE).map(k => caches.delete(k)))
    )
  );
  self.clients.claim();
});

self.addEventListener("fetch", e => {
  const url = new URL(e.request.url);

  // API requests: always network
  if (url.pathname.startsWith("/api/") || url.pathname.startsWith("/trigger/")) {
    e.respondWith(fetch(e.request));
    return;
  }

  // Shell files: network first, fall back to cache (so updates always come through)
  e.respondWith(
    fetch(e.request)
      .then(res => {
        const clone = res.clone();
        caches.open(CACHE).then(c => c.put(e.request, clone));
        return res;
      })
      .catch(() => caches.match(e.request))
  );
});

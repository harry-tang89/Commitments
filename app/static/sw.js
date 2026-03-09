const CACHE_NAME = "ac-v6";
// Cache only non-sensitive static assets.
const STATIC_ASSETS = [
  "/manifest.webmanifest",
  "/static/manifest.webmanifest",
  "/static/styles/main.css",
  "/static/icons/icon-192.png",
  "/static/icons/icon-512.png"
];

self.addEventListener("install", (event) => {
  // Pre-cache core assets on install so the app can open offline.
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => cache.addAll(STATIC_ASSETS))
  );
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  // Remove stale cache versions to prevent serving outdated files forever.
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(
        keys
          .filter((key) => key !== CACHE_NAME)
          .map((key) => caches.delete(key))
      )
    )
  );
  self.clients.claim();
});

self.addEventListener("fetch", (event) => {
  if (event.request.method !== "GET") return;

  const requestUrl = new URL(event.request.url);
  if (requestUrl.origin !== self.location.origin) return;

  const isStaticAssetRequest =
    requestUrl.pathname.startsWith("/static/") ||
    requestUrl.pathname === "/manifest.webmanifest";

  if (event.request.mode === "navigate") {
    // Avoid caching authenticated pages; return network-only for navigations.
    event.respondWith(
      fetch(event.request).catch(
        () =>
          new Response("Offline. Please reconnect to continue.", {
            status: 503,
            headers: { "Content-Type": "text/plain; charset=utf-8" }
          })
      )
    );
    return;
  }

  if (!isStaticAssetRequest) return;

  event.respondWith(
    fetch(event.request)
      .then((response) => {
        if (response && response.status === 200 && response.type === "basic") {
          // Runtime cache for same-origin static resources.
          const responseClone = response.clone();
          caches.open(CACHE_NAME).then((cache) => cache.put(event.request, responseClone));
        }
        return response;
      })
      .catch(() => caches.match(event.request))
  );
});

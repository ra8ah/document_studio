/* Static-assets-only service worker. Never caches API responses, HTML or anything authenticated. */
const CACHE = "studio-static-v1";
const STATIC = /^\/(static\/|fonts\/|icon-[\w-]+\.png$|manifest\.json$)/;

self.addEventListener("install", () => self.skipWaiting());
self.addEventListener("activate", (e) => {
  e.waitUntil(caches.keys().then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))))
    .then(() => self.clients.claim()));
});
self.addEventListener("fetch", (e) => {
  const req = e.request;
  if (req.method !== "GET") return;
  const url = new URL(req.url);
  // same-origin static files only; /api/*, /print/*, /share/* and navigations go straight to the network
  if (url.origin !== self.location.origin || !STATIC.test(url.pathname) || req.headers.has("authorization")) return;
  e.respondWith(caches.open(CACHE).then(async (c) => {
    const hit = await c.match(req);
    if (hit) return hit;
    const res = await fetch(req);
    if (res.ok && res.type === "basic") c.put(req, res.clone());
    return res;
  }));
});

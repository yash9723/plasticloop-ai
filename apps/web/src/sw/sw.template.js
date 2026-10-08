/* PlasticLoop AI service worker — generated into public/sw.js by scripts/build-sw.mjs. */
/* Caching strategy:
 *   - /api/*            network only (the app keeps operational data in IndexedDB, never in HTTP caches)
 *   - /_next/static/*   cache-first (content-hashed, immutable)
 *   - navigations, RSC  network-first, falling back to the last cached copy, then /offline
 * Old caches are deleted on activate, keyed by the build-stamped VERSION.
 */
const VERSION = "__SW_VERSION__";
const STATIC_CACHE = `pl-static-${VERSION}`;
const PAGE_CACHE = `pl-pages-${VERSION}`;
const SHELL = ["/collector", "/collector/offline-queue", "/offline", "/manifest.webmanifest", "/icons/icon-192.png"];

/** Caches the hashed JS/CSS a page needs, so a page cached as HTML can also run offline. */
async function cacheAssetsFrom(response) {
  try {
    const html = await response.clone().text();
    const urls = [...new Set(html.match(/\/_next\/static\/[^"'\s)\\]+/g) || [])];
    const cache = await caches.open(STATIC_CACHE);
    await Promise.allSettled(urls.map(async (u) => (await cache.match(u)) || cache.add(u)));
  } catch {
    /* best effort: the page itself is still cached */
  }
}

async function precache(url) {
  const cache = await caches.open(PAGE_CACHE);
  const response = await fetch(new Request(url, { credentials: "same-origin" }));
  if (!response.ok) return;
  await cache.put(url, response.clone());
  if ((response.headers.get("content-type") || "").includes("text/html")) await cacheAssetsFrom(response);
}

self.addEventListener("install", (event) => {
  event.waitUntil(Promise.allSettled(SHELL.map(precache)).then(() => self.skipWaiting()));
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((keys) => Promise.all(keys.filter((k) => k.startsWith("pl-") && !k.endsWith(VERSION)).map((k) => caches.delete(k))))
      .then(() => self.clients.claim()),
  );
});

const isStatic = (url) =>
  url.pathname.startsWith("/_next/static/") || url.pathname.startsWith("/icons/") || /\.(woff2?|ttf|svg|png|ico)$/.test(url.pathname);

async function cacheFirst(request) {
  const cached = await caches.match(request);
  if (cached) return cached;
  const response = await fetch(request);
  if (response.ok) (await caches.open(STATIC_CACHE)).put(request, response.clone());
  return response;
}

async function networkFirst(request, fallbackUrl) {
  const cache = await caches.open(PAGE_CACHE);
  try {
    const response = await fetch(request);
    if (response.ok && response.type === "basic") {
      cache.put(request, response.clone());
      if (request.mode === "navigate") cacheAssetsFrom(response);
    }
    return response;
  } catch (err) {
    const cached = (await cache.match(request, { ignoreVary: true })) || (await cache.match(request, { ignoreSearch: true, ignoreVary: true }));
    if (cached) return cached;
    if (fallbackUrl) {
      const fallback = await cache.match(fallbackUrl);
      if (fallback) return fallback;
    }
    throw err;
  }
}

self.addEventListener("fetch", (event) => {
  const { request } = event;
  if (request.method !== "GET") return;
  const url = new URL(request.url);
  if (url.origin !== self.location.origin) return;
  if (url.pathname.startsWith("/api/")) return;
  if (isStatic(url)) {
    event.respondWith(cacheFirst(request));
    return;
  }
  if (request.mode === "navigate") {
    event.respondWith(networkFirst(request, "/offline"));
    return;
  }
  if (request.headers.get("RSC") === "1" || url.searchParams.has("_rsc")) {
    event.respondWith(networkFirst(request));
  }
});

self.addEventListener("message", (event) => {
  if (event.data === "SKIP_WAITING") self.skipWaiting();
});

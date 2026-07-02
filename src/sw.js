/**
 * Service worker — offline cache for the app shell and map tiles.
 *
 * TEMPLATE: build.js replaces the __PLACEHOLDER__ constants below and writes
 * the result to dist/sw.js (this file is never served as-is, and is NOT part
 * of the concatenated app bundle — only js/… script tags are).
 *
 * Responsibilities are split three ways so nothing is cached twice:
 * - This SW owns the app shell (precache) and the protomaps tile/TileJSON
 *   runtime cache, plus a small runtime cache for lazy same-origin static
 *   assets (Noto emoji font, images).
 * - Event/location/tag data (data/*.json) is deliberately PASSED THROUGH
 *   untouched — the page manages those in IndexedDB (js/data/dataCache.js)
 *   because it must know whether it rendered from cache and must receive
 *   fresh bytes to merge (script.js _backgroundRefresh).
 * - Map style JSONs are the exception: MapLibre fetches them itself, so they
 *   are precached + stale-while-revalidated here.
 *
 * Kill-switch: building with the SW disabled emits this same file with
 * SW_DISABLED=true — an installed copy then wipes every cache and unregisters
 * itself on its next activation (browsers re-fetch sw.js on navigation, and
 * .htaccess serves it no-cache). IndexedDB data is untouched.
 */
/* eslint-env serviceworker */
'use strict';

const SW_VERSION = '__SW_VERSION__';
const SW_DISABLED = __SW_DISABLED__;
// Hashed/versioned URLs — immutable, may be filled from the browser HTTP cache.
const PRECACHE_IMMUTABLE = __PRECACHE_IMMUTABLE__;
// Unversioned URLs — fetched with {cache:'reload'} so a stale HTTP-cache copy
// can never be pinned into the precache.
const PRECACHE_REVALIDATE = __PRECACHE_REVALIDATE__;

const PRECACHE = `precache-${SW_VERSION}`;
const RUNTIME_STATIC = 'runtime-static-v1';
const RUNTIME_STYLES = 'runtime-styles-v1';
const RUNTIME_TILES = 'runtime-tiles-v1';
const CACHE_ALLOWLIST = [PRECACHE, RUNTIME_STATIC, RUNTIME_STYLES, RUNTIME_TILES];

const TILE_ORIGIN = 'https://api.protomaps.com';
// ~400 vector tiles ≈ 16–30 MB — covers a typical metro browsing footprint.
const TILE_CACHE_MAX_ENTRIES = 400;
// Refresh tiles older than this so basemap updates eventually propagate.
const TILE_MAX_AGE_MS = 30 * 24 * 60 * 60 * 1000;

// Path of the SW's own directory ('/' in prod, '/fomo/dist/' under XAMPP) —
// same-origin routing below is relative to this.
const BASE_PATH = new URL('.', self.location).pathname;

self.addEventListener('install', (event) => {
    if (SW_DISABLED) {
        self.skipWaiting();
        return;
    }
    event.waitUntil((async () => {
        const cache = await caches.open(PRECACHE);
        await cache.addAll(PRECACHE_IMMUTABLE);
        await Promise.all(PRECACHE_REVALIDATE.map(async (url) => {
            const response = await fetch(new Request(url, { cache: 'reload' }));
            if (!response.ok) throw new Error(`Precache failed: ${url} (${response.status})`);
            await cache.put(url, response);
        }));
        // A fresh shell shouldn't wait behind an old SW — HTML is network-first
        // and bundles are content-hashed, so activating immediately is safe.
        await self.skipWaiting();
    })());
});

self.addEventListener('activate', (event) => {
    event.waitUntil((async () => {
        if (SW_DISABLED) {
            // Rescue mode: erase every cache this origin owns and bow out.
            const names = await caches.keys();
            await Promise.all(names.map((name) => caches.delete(name)));
            await self.registration.unregister();
            return;
        }
        const names = await caches.keys();
        await Promise.all(names
            .filter((name) => !CACHE_ALLOWLIST.includes(name))
            .map((name) => caches.delete(name)));
        await self.clients.claim();
    })());
});

self.addEventListener('fetch', (event) => {
    if (SW_DISABLED) return;
    const request = event.request;
    if (request.method !== 'GET') return;

    const url = new URL(request.url);

    // Protomaps: TileJSON revalidates in the background; tiles are cache-first
    // with a capped FIFO so previously-viewed areas render offline.
    if (url.origin === TILE_ORIGIN) {
        if (url.pathname.endsWith('.json')) {
            event.respondWith(staleWhileRevalidate(event, RUNTIME_TILES, request));
        } else {
            event.respondWith(tileCacheFirst(request));
        }
        return;
    }

    // Any other cross-origin resource: pass through.
    if (url.origin !== self.location.origin) return;

    // Page navigations: always prefer the network (HTML is served no-cache, so
    // online users can never be pinned to a stale app); cached shell offline.
    if (request.mode === 'navigate') {
        event.respondWith(navigationNetworkFirst(request));
        return;
    }

    if (!url.pathname.startsWith(BASE_PATH)) return;
    const rel = url.pathname.slice(BASE_PATH.length);

    if (rel.startsWith('data/')) {
        // Map styles: MapLibre fetches these itself → serve cached, refresh in
        // the background. Everything else under data/ (events/locations/tags
        // JSON) is owned by the page's IndexedDB layer — pass through.
        if (rel.startsWith('data/map-style-')) {
            event.respondWith(staleWhileRevalidate(event, RUNTIME_STYLES, request, { ignoreSearch: true }));
        }
        return;
    }

    // Never cache dynamic endpoints.
    if (rel.startsWith('api/') || rel.startsWith('admin/')) return;

    // App shell + lazy static assets (Noto emoji font, images, old hashed
    // bundles a not-yet-reloaded page may still request): cache-first.
    event.respondWith(cacheFirstStatic(request));
});

/**
 * Serve from cache, refreshing the cached copy in the background.
 */
async function staleWhileRevalidate(event, cacheName, request, matchOptions) {
    const cache = await caches.open(cacheName);
    const cached = await cache.match(request, matchOptions);
    const refresh = fetch(request)
        .then((response) => {
            if (response && response.ok) cache.put(request, response.clone());
            return response;
        })
        .catch(() => null);
    if (cached) {
        event.waitUntil(refresh);
        return cached;
    }
    const response = await refresh;
    if (response) return response;
    return Response.error();
}

let tilePutCount = 0;

async function tileCacheFirst(request) {
    const cache = await caches.open(RUNTIME_TILES);
    const cached = await cache.match(request);
    if (cached && !isStale(cached, TILE_MAX_AGE_MS)) return cached;
    try {
        const response = await fetch(request);
        if (response && response.ok) {
            await cache.put(request, response.clone());
            evictExcessTiles(cache);
        }
        return response;
    } catch (error) {
        // Offline: an expired tile beats a blank one.
        if (cached) return cached;
        throw error;
    }
}

function isStale(response, maxAgeMs) {
    const dateHeader = response.headers.get('date');
    if (!dateHeader) return false;
    const age = Date.now() - new Date(dateHeader).getTime();
    return Number.isFinite(age) && age > maxAgeMs;
}

/**
 * Cap the tile cache. Cache API keys are insertion-ordered, so deleting from
 * the front is FIFO eviction — good enough (a re-visited area simply re-enters
 * after eviction). keys() is O(entries), so only run it every ~20 puts.
 */
function evictExcessTiles(cache) {
    if (++tilePutCount % 20 !== 0) return;
    cache.keys().then((keys) => {
        const excess = keys.length - TILE_CACHE_MAX_ENTRIES;
        if (excess <= 0) return;
        return Promise.all(keys.slice(0, excess).map((key) => cache.delete(key)));
    }).catch(() => {});
}

async function navigationNetworkFirst(request) {
    try {
        return await fetch(request);
    } catch (error) {
        const cache = await caches.open(PRECACHE);
        // Exact page first (about.html), then the app shell.
        const cached = await cache.match(request, { ignoreSearch: true });
        if (cached) return cached;
        const shell = await cache.match('index.html');
        if (shell) return shell;
        throw error;
    }
}

async function cacheFirstStatic(request) {
    const precache = await caches.open(PRECACHE);
    // ignoreSearch: the page requests vendor/maplibre-gl.js?v=… and
    // data/map-style-*.json?v=… with version queries that must hit their
    // precached entries regardless of how they were stored.
    const precached = await precache.match(request, { ignoreSearch: true });
    if (precached) return precached;

    const runtime = await caches.open(RUNTIME_STATIC);
    const cached = await runtime.match(request);
    if (cached) return cached;

    const response = await fetch(request);
    if (response && response.ok) {
        runtime.put(request, response.clone()).catch(() => {});
    }
    return response;
}

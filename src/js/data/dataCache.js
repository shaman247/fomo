/**
 * DataCache Module
 *
 * IndexedDB-backed on-device cache for the event/location/tag data files.
 * Enables instant startup from a previously-stored snapshot (and full offline
 * operation) while fresh data revalidates in the background — see
 * App._backgroundRefresh in script.js.
 *
 * Storage layout (DB "fomo-data-cache"):
 * - `files` store: one record per data file, keyed by its fetch path
 *   (e.g. "data/events.day0.json") → { url, data (parsed JSON), hash, savedAt }
 * - `meta` store: a single "snapshot" record describing the cached generation:
 *   { schemaVersion, complete, manifestDays, savedAt, hashes: {url: hash} }
 *
 * `complete` is only set once EVERY file of one export generation has been
 * stored (verified against the DB), so a cached session never renders a
 * mixed-generation snapshot. `hashes` mirrors the per-file content hashes so
 * the background refresh can cheaply skip identical re-downloads without
 * deserializing the ~20 MB of file records.
 *
 * Failure policy: any IndexedDB error flips an internal `broken` flag and the
 * module becomes a silent no-op — the app degrades to plain network loading.
 *
 * @module DataCache
 */
const DataCache = (() => {
    const DB_NAME = 'fomo-data-cache';
    const DB_VERSION = 1;
    const FILES_STORE = 'files';
    const META_STORE = 'meta';
    const META_KEY = 'snapshot';

    // Bump when the exported data format or the required file set changes in a
    // way old cached snapshots can't satisfy — mismatched snapshots are wiped.
    const SCHEMA_VERSION = 1;

    // A snapshot older than this is ignored (its 90-day event window has
    // drifted too far; better to eat one slow network start than show it).
    const MAX_SNAPSHOT_AGE_MS = 14 * 24 * 60 * 60 * 1000;

    let db = null;
    let broken = false;
    let meta = null; // in-memory copy of the snapshot meta record

    /**
     * FNV-1a 32-bit hash of a string, as 8 hex chars. Fast enough for the
     * ~2 MB Phase-1 payload (~10 ms) and collision-safe enough for a
     * "did this file change since we cached it?" check.
     * @param {string} text
     * @returns {string}
     */
    function hashString(text) {
        let h = 0x811c9dc5;
        for (let i = 0; i < text.length; i++) {
            h ^= text.charCodeAt(i);
            // h *= 16777619 (FNV prime), in 32-bit space without overflow
            h = (h + ((h << 1) + (h << 4) + (h << 7) + (h << 8) + (h << 24))) >>> 0;
        }
        return h.toString(16).padStart(8, '0');
    }

    /** Promise wrapper for an IDBRequest. */
    function _req(request) {
        return new Promise((resolve, reject) => {
            request.onsuccess = () => resolve(request.result);
            request.onerror = () => reject(request.error);
        });
    }

    /** Promise that settles when a transaction completes/aborts. */
    function _txDone(tx) {
        return new Promise((resolve, reject) => {
            tx.oncomplete = () => resolve();
            tx.onabort = () => reject(tx.error || new Error('IndexedDB transaction aborted'));
            tx.onerror = () => reject(tx.error);
        });
    }

    function _markBroken(error) {
        if (!broken) console.warn('DataCache disabled:', error);
        broken = true;
        meta = null;
    }

    /**
     * Open the database and load the snapshot meta record. Safe to call when
     * IndexedDB is unavailable (private browsing, quota lockout) — the module
     * just marks itself broken. Also requests persistent storage (best-effort;
     * reduces eviction pressure on iOS/Android WebViews).
     * @returns {Promise<void>}
     */
    async function init() {
        if (typeof indexedDB === 'undefined') {
            broken = true;
            return;
        }
        try {
            const openReq = indexedDB.open(DB_NAME, DB_VERSION);
            openReq.onupgradeneeded = () => {
                const d = openReq.result;
                if (!d.objectStoreNames.contains(FILES_STORE)) {
                    d.createObjectStore(FILES_STORE, { keyPath: 'url' });
                }
                if (!d.objectStoreNames.contains(META_STORE)) {
                    d.createObjectStore(META_STORE);
                }
            };
            db = await _req(openReq);
            db.onversionchange = () => { try { db.close(); } catch (e) {} broken = true; };

            meta = (await _req(
                db.transaction(META_STORE).objectStore(META_STORE).get(META_KEY)
            )) || null;

            // A snapshot written by an incompatible app version is useless —
            // wipe it so it can't linger and shadow fresh writes.
            if (meta && meta.schemaVersion !== SCHEMA_VERSION) {
                await clearAll();
            }

            if (navigator.storage && navigator.storage.persist) {
                navigator.storage.persist().catch(() => {});
            }
        } catch (error) {
            _markBroken(error);
        }
    }

    /**
     * Whether a complete, current-schema, fresh-enough snapshot exists — i.e.
     * whether the app can render this session entirely from cache.
     * @returns {boolean}
     */
    function isUsable() {
        return !broken && !!db && !!meta &&
            meta.complete === true &&
            meta.schemaVersion === SCHEMA_VERSION &&
            typeof meta.savedAt === 'number' &&
            (Date.now() - meta.savedAt) < MAX_SNAPSHOT_AGE_MS;
    }

    /** @returns {?Object} the in-memory snapshot meta (null if none/broken) */
    function getMeta() {
        return broken ? null : meta;
    }

    /**
     * Read one cached file record.
     * @param {string} url
     * @returns {Promise<?{url: string, data: *, hash: string, savedAt: number}>}
     */
    async function get(url) {
        if (broken || !db) return null;
        try {
            return (await _req(
                db.transaction(FILES_STORE).objectStore(FILES_STORE).get(url)
            )) || null;
        } catch (error) {
            _markBroken(error);
            return null;
        }
    }

    /**
     * Read several cached file records in one transaction.
     * @param {string[]} urls
     * @returns {Promise<Map<string, Object>>} url → record (missing urls omitted)
     */
    async function getMany(urls) {
        const result = new Map();
        if (broken || !db) return result;
        try {
            const store = db.transaction(FILES_STORE).objectStore(FILES_STORE);
            const records = await Promise.all(urls.map(u => _req(store.get(u))));
            records.forEach((rec, i) => { if (rec) result.set(urls[i], rec); });
        } catch (error) {
            _markBroken(error);
            result.clear();
        }
        return result;
    }

    /**
     * Which of the given urls exist in the files store. Uses getKey() so the
     * (potentially multi-MB) values are never deserialized.
     * @param {string[]} urls
     * @returns {Promise<Set<string>>}
     */
    async function hasKeys(urls) {
        const present = new Set();
        if (broken || !db) return present;
        try {
            const store = db.transaction(FILES_STORE).objectStore(FILES_STORE);
            const keys = await Promise.all(urls.map(u => _req(store.getKey(u))));
            keys.forEach((k, i) => { if (k !== undefined) present.add(urls[i]); });
        } catch (error) {
            _markBroken(error);
            present.clear();
        }
        return present;
    }

    /**
     * Store one fetched file. Callers treat this as fire-and-forget; the
     * returned promise resolves false (never rejects) on failure.
     * @param {string} url
     * @param {*} data - parsed JSON
     * @param {string} hash - content hash of the raw response text
     * @returns {Promise<boolean>}
     */
    function put(url, data, hash) {
        return putMany([{ url, data, hash }]);
    }

    /**
     * Store several fetched files in one transaction.
     * @param {Array<{url: string, data: *, hash: string}>} entries
     * @returns {Promise<boolean>} false (never rejects) on failure
     */
    async function putMany(entries) {
        if (broken || !db || !entries.length) return false;
        try {
            const tx = db.transaction(FILES_STORE, 'readwrite');
            const store = tx.objectStore(FILES_STORE);
            const savedAt = Date.now();
            for (const { url, data, hash } of entries) {
                store.put({ url, data, hash, savedAt });
            }
            await _txDone(tx);
            return true;
        } catch (error) {
            // Out of quota: drop the whole cache (a partial snapshot is
            // useless) and disable for this session rather than thrash.
            if (error && error.name === 'QuotaExceededError') {
                try { await clearAll(); } catch (e) {}
            }
            _markBroken(error);
            return false;
        }
    }

    /**
     * Replace the snapshot meta record. schemaVersion is stamped here so
     * callers can't accidentally persist a mismatched one.
     * @param {Object} newMeta - {complete, manifestDays, savedAt, hashes}
     * @returns {Promise<boolean>} false (never rejects) on failure
     */
    async function setMeta(newMeta) {
        if (broken || !db) return false;
        try {
            const record = { ...newMeta, schemaVersion: SCHEMA_VERSION };
            const tx = db.transaction(META_STORE, 'readwrite');
            tx.objectStore(META_STORE).put(record, META_KEY);
            await _txDone(tx);
            meta = record;
            return true;
        } catch (error) {
            _markBroken(error);
            return false;
        }
    }

    /**
     * Wipe both stores (files + meta). Used on schema mismatch and quota
     * exhaustion. Leaves the DB itself in place.
     * @returns {Promise<void>}
     */
    async function clearAll() {
        if (!db) return;
        const tx = db.transaction([FILES_STORE, META_STORE], 'readwrite');
        tx.objectStore(FILES_STORE).clear();
        tx.objectStore(META_STORE).clear();
        await _txDone(tx);
        meta = null;
    }

    return {
        init,
        isUsable,
        getMeta,
        get,
        getMany,
        hasKeys,
        put,
        putMany,
        setMeta,
        clearAll,
        hashString
    };
})();

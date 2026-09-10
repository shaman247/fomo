/** Shared artwork renderer. Saved IDs and exact legacy Unicode aliases only. */
const IconManager = (() => {
    const decoded = new Map(), rendered = new Map(), accents = new Map();
    const mounted = new WeakMap(), visible = new WeakSet();
    const MAX_VARIANTS = 128;
    const packLoads = new Map(), packJobs = [];
    const pendingPackChoices = new Map();
    let activePacks = 0;
    let tagIcons = {}, tagEmojis = {}, observing = false, visibilityObserver;
    const own = (object, key) => Object.prototype.hasOwnProperty.call(object, key);
    const canonical = value => (typeof value === 'string' ? value : '').trim().replace(/[\uFE0E\uFE0F]/g, '');
    function resolve(record = {}) {
        record ||= {};
        const emoji = canonical(record?.emoji);
        const id = own(IconCatalog.icons, record.icon_id) ? record.icon_id
            : own(IconCatalog.emoji, emoji) ? IconCatalog.emoji[emoji] : IconCatalog.fallbackId;
        return IconCatalog.icons[id];
    }
    function setTagIcons(map, emojis = {}) { tagIcons = map || {}; tagEmojis = emojis; }
    const tagRecord = (tag, emoji) => ({ icon_id: own(tagIcons, tag) ? tagIcons[tag] : null, emoji: emoji || tagEmojis[tag] });
    const cacheKey = record => `${IconCatalog.revision}:${resolve(record).id}`;
    const tagCacheKey = tag => cacheKey(tagRecord(tag));
    const accentKey = (record, theme) => `${resolve(record).id}|${theme}`;
    function getColor(record, theme = Utils.getCurrentTheme()) {
        return accents.get(accentKey(record, theme)) || '#8899aa';
    }
    // Bound simultaneous downloads when a long list of icons enters view.
    const jobs = [];
    let active = 0;
    function pump() {
        while (active < 6 && jobs.length) {
            active++;
            const { url, done, fail } = jobs.shift();
            const img = new Image();
            const finish = callback => { active--; callback(); pump(); };
            img.onload = () => finish(() => done(img));
            img.onerror = () => finish(() => fail(new Error('Icon image unavailable')));
            img.src = url;
        }
    }
    function load(url) {
        if (!decoded.has(url)) {
            const promise = new Promise((done, fail) => { jobs.push({ url, done, fail }); pump(); });
            decoded.set(url, promise);
            if (decoded.size > 256) decoded.delete(decoded.keys().next().value);
            promise.catch(() => { if (decoded.get(url) === promise) decoded.delete(url); });
        }
        return decoded.get(url);
    }
    function pumpPacks() {
        while (activePacks < 3 && packJobs.length) {
            const { pack, done } = packJobs.shift();
            activePacks++;
            const controller = new AbortController();
            const timeout = setTimeout(() => controller.abort(), 8000);
            // Include body consumption in the deadline, not just the headers.
            Promise.resolve().then(async () => {
                const response = await fetch(pack.url, { signal: controller.signal });
                if (!response.ok) throw Error('Icon pack unavailable');
                const data = await response.json();
                if (data?.schemaVersion !== 1 || !data.icons || typeof data.icons !== 'object') {
                    throw Error('Invalid icon pack');
                }
                return data.icons;
            }).catch(() => null).then(done).finally(() => {
                clearTimeout(timeout);
                activePacks--;
                pumpPacks();
            });
        }
    }
    function loadPack(id) {
        const pack = IconCatalog.packs?.[id];
        if (!pack || typeof fetch !== 'function') return Promise.resolve(null);
        if (!packLoads.has(pack.url)) {
            // Keep failure results too: one missing pack must not trigger a
            // failed HTTP request for every chip. Individual SVGs still work.
            packLoads.set(pack.url, new Promise(done => { packJobs.push({ pack, done }); pumpPacks(); }));
        }
        return packLoads.get(pack.url);
    }
    function loadPackedArtwork(descriptor) {
        return loadPack(descriptor.pack).then(icons => {
            const entry = icons && own(icons, descriptor.id) && icons[descriptor.id];
            if (!entry || entry.revision !== descriptor.revision || typeof entry.svg !== 'string') {
                return load(descriptor.url);
            }
            // Data URLs use the existing Image/canvas path and preserve SVG
            // gradients and palette extraction. Only requested
            // icons are decoded; the rest of the pack remains plain text.
            const url = `data:image/svg+xml;charset=utf-8,${encodeURIComponent(entry.svg)}`;
            return load(url).catch(() => load(descriptor.url));
        });
    }
    function loadArtwork(descriptor) {
        if (decoded.has(descriptor.url)) return load(descriptor.url);
        const pack = IconCatalog.packs?.[descriptor.pack];
        if (!pack || typeof fetch !== 'function') return load(descriptor.url);
        if (descriptor.pack === 'startup' || packLoads.has(pack.url)) return loadPackedArtwork(descriptor);
        // Coalesce requests from one render batch. A lone rare icon should not
        // download its whole group. Use a secondary pack only when it saves
        // requests and requested artwork covers at least 60% of its gzip size.
        return new Promise((done, fail) => {
            if (!pendingPackChoices.has(pack.url)) {
                const requests = [];
                pendingPackChoices.set(pack.url, requests);
                queueMicrotask(() => {
                    pendingPackChoices.delete(pack.url);
                    const unique = new Map(requests.map(r => [r.descriptor.id, r.descriptor]));
                    const requestedBytes = [...unique.values()].reduce((sum, icon) => sum + (icon.gzipBytes || 0), 0);
                    const usePack = unique.size > 1 && requestedBytes >= pack.gzipBytes * 0.6;
                    for (const request of requests) {
                        (usePack ? loadPackedArtwork(request.descriptor) : load(request.descriptor.url))
                            .then(request.done, request.fail);
                    }
                });
            }
            pendingPackChoices.get(pack.url).push({ descriptor, done, fail });
        });
    }
    function prepare(descriptor, theme = Utils.getCurrentTheme(), mapSprite = false) {
        const dpr = Math.min(window.devicePixelRatio || 1, 2);
        const key = [descriptor.id, descriptor.revision, theme, dpr, mapSprite].join('|');
        if (rendered.has(key)) return rendered.get(key);
        const promise = loadArtwork(descriptor).catch(() => load(IconCatalog.fallbackUrl)).then(img => {
            const size = 64 * dpr;
            const canvas = document.createElement('canvas');
            canvas.width = canvas.height = size;
            const ctx = canvas.getContext('2d', { willReadFrequently: true });
            // Map sprites reserve the same left-biased collision box as before.
            if (mapSprite) ctx.drawImage(img, 17 * dpr, 9 * dpr, 46 * dpr, 46 * dpr);
            else ctx.drawImage(img, 4 * dpr, 4 * dpr, 56 * dpr, 56 * dpr);
            const pixels = ctx.getImageData(0, 0, size, size);
            const accent = TagColorManager.extractColorFromPixels(pixels);
            accents.set(`${descriptor.id}|${theme}`, accent);
            return { url: img.src, accent, pixels, pixelRatio: dpr };
        });
        rendered.set(key, promise);
        if (rendered.size > MAX_VARIANTS) rendered.delete(rendered.keys().next().value);
        promise.catch(() => { if (rendered.get(key) === promise) rendered.delete(key); });
        return promise;
    }
    function createElement(record, { onAccent = () => {}, onPendingAccent = onAccent,
        className = 'popup-event-emoji event-icon', resolveRecord = null } = {}) {
        const span = document.createElement('span');
        span.className = className;
        span.classList.add('event-icon');
        span.setAttribute('aria-hidden', 'true');
        span.style.cssText = 'display:inline-flex;width:1em;height:1em;flex:none;align-items:center;justify-content:center;';
        let generation = 0;
        const paint = () => {
            const descriptor = resolve(resolveRecord ? resolveRecord() : record);
            const current = ++generation;
            const theme = Utils.getCurrentTheme();
            const stillCurrent = () => current === generation && Utils.getCurrentTheme() === theme;
            span.dataset.iconId = descriptor.id;
            onPendingAccent(getColor({ icon_id: descriptor.id }, theme));
            prepare(descriptor, theme).then(result => {
                if (!stillCurrent()) return;
                const img = document.createElement('img');
                img.alt = '';
                img.width = img.height = 24;
                img.style.cssText = 'width:100%;height:100%;object-fit:contain;box-sizing:border-box;';
                img.style.padding = '6.25%';
                img.onload = () => {
                    if (!stillCurrent()) return;
                    span.replaceChildren(img);
                    onAccent(result.accent);
                };
                img.onerror = () => {
                    if (stillCurrent() && img.src !== IconCatalog.fallbackUrl) img.src = IconCatalog.fallbackUrl;
                };
                img.src = result.url;
            }).catch(() => {}); // A reserved empty slot is preferable to platform glyphs.
        };
        mounted.set(span, paint);
        if (typeof IntersectionObserver !== 'undefined') {
            visibilityObserver ||= new IntersectionObserver(entries => entries.forEach(entry => {
                if (entry.isIntersecting) { visible.add(entry.target); mounted.get(entry.target)?.(); }
                else visible.delete(entry.target);
            }), { rootMargin: '100px' });
            visibilityObserver.observe(span);
        } else { visible.add(span); paint(); }
        return span;
    }
    function createTagElement(tag, emoji, options = {}) {
        return createElement(tagRecord(tag, emoji), { className: 'chip-emoji event-icon',
            ...options, onPendingAccent: () => {}, resolveRecord: () => tagRecord(tag, emoji) });
    }
    function refresh() {
        document.querySelectorAll('.event-icon').forEach(span => {
            if (visible.has(span)) mounted.get(span)?.();
        });
    }
    // Convert inline UI/text emoji too; never rewrite inputs, scripts or our own
    // image slots. Unicode stays in data/accessibility labels, not rendered glyphs.
    const pictograph = /[\p{Extended_Pictographic}\p{Regional_Indicator}\u20e3]/u;
    const segmenter = new Intl.Segmenter(undefined, { granularity: 'grapheme' });
    function hydrate(root) {
        const nodes = [];
        const visit = node => {
            if (node.nodeType === 3) { if (pictograph.test(node.textContent)) nodes.push(node); return; }
            if (node.nodeType !== 1) return;
            if (node.matches('.event-icon')) { visibilityObserver?.observe(node); return; }
            if (node.matches('script,style,textarea,input,select,svg,canvas,[contenteditable]')) return;
            for (const child of node.childNodes) visit(child);
        };
        visit(root);
        for (const node of nodes) {
            if (!node.parentElement || node.parentElement.closest('.event-icon,script,style,textarea,[contenteditable]')) continue;
            const fragment = document.createDocumentFragment();
            let text = '';
            const flush = () => {
                if (text) fragment.appendChild(document.createTextNode(text));
                text = '';
            };
            for (const { segment } of segmenter.segment(node.textContent)) {
                if (pictograph.test(segment)) {
                    flush();
                    fragment.appendChild(createElement({ emoji: segment }, { className: 'inline-icon event-icon' }));
                } else text += segment;
            }
            flush();
            node.replaceWith(fragment);
        }
    }
    function init() {
        if (observing) return;
        observing = true;
        loadPack('startup');
        hydrate(document.body);
        new MutationObserver(records => {
            for (const record of records) {
                if (record.type === 'attributes') { refresh(); continue; }
                if (record.target.parentElement?.closest('.event-icon')) continue;
                if (record.type === 'characterData') hydrate(record.target);
                else record.addedNodes.forEach(hydrate);
                record.removedNodes.forEach(node => {
                    if (node.nodeType !== 1 || node.isConnected) return;
                    if (node.matches('.event-icon')) visibilityObserver?.unobserve(node);
                    node.querySelectorAll('.event-icon').forEach(el => visibilityObserver?.unobserve(el));
                });
            }
        }).observe(document.body, { childList: true, characterData: true, subtree: true });
        new MutationObserver(refresh).observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] });
    }
    return { init, resolve, createElement, prepare, getColor, cacheKey, refresh, setTagIcons, tagCacheKey, createTagElement };
})();

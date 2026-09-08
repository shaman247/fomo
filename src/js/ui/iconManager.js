/** Shared artwork renderer. Saved IDs and exact legacy Unicode aliases only. */
const IconManager = (() => {
    const decoded = new Map(), rendered = new Map(), accents = new Map();
    const mounted = new WeakMap(), visible = new WeakSet();
    const MAX_VARIANTS = 128;
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
        return accents.get(accentKey(record, theme)) || Themes.resolve(theme).achromaticFallback || '#8899aa';
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
    function prepare(descriptor, theme = Utils.getCurrentTheme(), mapSprite = false) {
        const dpr = Math.min(window.devicePixelRatio || 1, 2);
        const key = [descriptor.id, descriptor.revision, theme, dpr, mapSprite].join('|');
        if (rendered.has(key)) return rendered.get(key);
        const promise = load(descriptor.url).catch(() => load(IconCatalog.fallbackUrl)).then(img => {
            const size = 64 * dpr;
            const canvas = document.createElement('canvas');
            canvas.width = canvas.height = size;
            const ctx = canvas.getContext('2d', { willReadFrequently: true });
            // Map sprites reserve the same left-biased collision box as before.
            if (mapSprite) ctx.drawImage(img, 17 * dpr, 9 * dpr, 46 * dpr, 46 * dpr);
            else ctx.drawImage(img, 4 * dpr, 4 * dpr, 56 * dpr, 56 * dpr);
            let pixels = ctx.getImageData(0, 0, size, size);
            const definition = Themes.resolve(theme);
            if (definition.emojiTransform) pixels = EmojiTransforms.apply(pixels, definition.emojiTransform, dpr);
            ctx.putImageData(pixels, 0, 0);
            const accent = TagColorManager.extractColorFromPixels(pixels, definition);
            accents.set(`${descriptor.id}|${theme}`, accent);
            return { url: definition.emojiTransform ? canvas.toDataURL('image/png') : img.src,
                transformed: !!definition.emojiTransform, accent, pixels, pixelRatio: dpr };
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
                if (!result.transformed) img.style.padding = '6.25%';
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

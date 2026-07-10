/**
 * ProtoFlags Module
 *
 * URL/localStorage-backed feature flags for the UX prototype experiments
 * (alternate layouts + the prototype picker itself). Everything defaults to
 * the production behavior; flags exist so prototypes can be toggled live
 * without affecting normal visitors.
 *
 * Resolution order (evaluated immediately at load, before App.init strips
 * query params): URL param > stored value > default. URL-provided values are
 * persisted so they survive the address-bar cleanup and later reloads.
 *
 * URL params handled here:
 *   ?proto=1 / ?proto=0  — show/hide the prototype picker (0 also resets all
 *                          flags and reverts a prototype theme to its base)
 *   ?theme=<name>        — persist a theme (validated against Themes registry;
 *                          handled here so it lands in storage before
 *                          ThemeManager.initTheme() reads it → single style load)
 *   ?layout=docked / ?popups=panel / ?chips=minimal — layout experiment flags
 *
 * @module ProtoFlags
 */
const ProtoFlags = (() => {
    const STORAGE_KEY = 'protoFlags';

    /**
     * Flag definitions. First value is the production default.
     * requiresReload: the flag is read during load-time wiring (visible-center
     * math, sheet initial state, history baseline) — live toggling is not safe.
     */
    const DEFS = {
        layout: { values: ['default', 'docked'], requiresReload: true },
        popups: { values: ['float', 'panel'], requiresReload: false },
        chips: { values: ['full', 'minimal'], requiresReload: false }
    };

    const state = {
        flags: {},      // stored (raw) non-default flag values
        proto: false    // prototype picker visibility
    };

    // ========================================
    // STORAGE
    // ========================================

    function _load() {
        try {
            const raw = Utils.SafeStorage.getItem(STORAGE_KEY);
            if (!raw) return;
            const parsed = JSON.parse(raw);
            if (parsed && typeof parsed === 'object') {
                state.proto = parsed.proto === '1';
                for (const name of Object.keys(DEFS)) {
                    if (DEFS[name].values.includes(parsed[name])) {
                        state.flags[name] = parsed[name];
                    }
                }
            }
        } catch (e) {
            // Corrupt JSON — start clean
            state.flags = {};
            state.proto = false;
        }
    }

    function _persist() {
        const out = {};
        if (state.proto) out.proto = '1';
        for (const [name, value] of Object.entries(state.flags)) {
            if (value !== DEFS[name].values[0]) out[name] = value;
        }
        if (Object.keys(out).length > 0) {
            Utils.SafeStorage.setItem(STORAGE_KEY, JSON.stringify(out));
        } else {
            Utils.SafeStorage.removeItem(STORAGE_KEY);
        }
    }

    // ========================================
    // QUERY API
    // ========================================

    /** Raw stored/URL value, without cross-flag derivations. */
    function getRaw(name) {
        const def = DEFS[name];
        if (!def) return undefined;
        return state.flags[name] || def.values[0];
    }

    /**
     * Effective value. Derivation: layout=docked forces popups=panel —
     * a floating popup over the docked half-map re-introduces the clutter
     * docked exists to remove, and its dismiss/fit dance has no home there.
     */
    function get(name) {
        if (name === 'popups' && getRaw('layout') === 'docked' && !Utils.isMobileLayout()) {
            return 'panel';
        }
        return getRaw(name);
    }

    function isOn(name, value) {
        return get(name) === value;
    }

    function pickerRequested() {
        return state.proto;
    }

    /** Picker contract: every flag with its current value and UI hints. */
    function list() {
        return Object.keys(DEFS).map(name => ({
            name,
            values: DEFS[name].values,
            value: get(name),
            requiresReload: DEFS[name].requiresReload,
            locked: name === 'popups' && getRaw('layout') === 'docked'
        }));
    }

    // ========================================
    // MUTATION API
    // ========================================

    function _syncBodyClasses() {
        const body = document.body;
        if (!body) return;
        body.classList.toggle('proto-layout-docked', get('layout') === 'docked');
        body.classList.toggle('proto-popups-panel', get('popups') === 'panel');
        body.classList.toggle('proto-chips-minimal', get('chips') === 'minimal');
    }

    function set(name, value) {
        if (name === 'proto') {
            state.proto = !!value && value !== '0';
            _persist();
            document.dispatchEvent(new CustomEvent('protoflagschange', { detail: { name, value: state.proto } }));
            return;
        }
        const def = DEFS[name];
        if (!def || !def.values.includes(value)) return;
        if (state.flags[name] === value || (!state.flags[name] && value === def.values[0])) return;
        state.flags[name] = value;
        _persist();
        _syncBodyClasses();
        document.dispatchEvent(new CustomEvent('protoflagschange', { detail: { name, value: get(name) } }));
    }

    function resetAll() {
        state.flags = {};
        state.proto = false;
        _persist();
        _syncBodyClasses();
    }

    // ========================================
    // EVAL-TIME URL RESOLUTION
    // ========================================

    (function _resolveFromUrl() {
        _load();

        let params;
        try {
            params = new URLSearchParams(window.location.search);
        } catch (e) {
            _syncBodyClasses();
            return;
        }

        const proto = params.get('proto');
        if (proto === '1') {
            state.proto = true;
        } else if (proto === '0') {
            // Full opt-out: clear flags and revert a prototype theme to its base
            state.flags = {};
            state.proto = false;
            if (typeof Themes !== 'undefined') {
                const stored = Utils.SafeStorage.getItem('theme');
                if (stored && Themes.isKnown(stored) && Themes.resolve(stored).proto) {
                    Utils.SafeStorage.setItem('theme', Themes.baseOf(stored));
                }
            }
        }

        // ?theme= is persisted here (pre-init) so ThemeManager.initTheme()
        // reads it and the map constructs with the right style — one style load.
        const theme = params.get('theme');
        if (theme && /^[a-z0-9-]{1,32}$/.test(theme)
            && typeof Themes !== 'undefined' && Themes.isKnown(theme)) {
            Utils.SafeStorage.setItem('theme', theme);
        }

        for (const name of Object.keys(DEFS)) {
            const v = params.get(name);
            if (v && DEFS[name].values.includes(v)) {
                state.flags[name] = v;
            }
        }

        _persist();
        _syncBodyClasses();
    })();

    // ========================================
    // EXPORTS
    // ========================================

    return {
        get,
        getRaw,
        set,
        isOn,
        list,
        pickerRequested,
        resetAll
    };
})();

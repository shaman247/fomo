/**
 * ProtoPanel Module
 *
 * The hidden prototype picker: a floating 🎨 button that expands into a
 * panel listing every registry theme and the layout experiment flags.
 * Only initialized when ProtoFlags.pickerRequested() (?proto=1, persisted).
 * Production visitors never see it.
 *
 * @module ProtoPanel
 */
const ProtoPanel = (() => {
    const state = {
        callbacks: null,   // { onThemeSelect(name) }
        root: null,        // container element
        open: false,
        needsReload: false
    };

    function _el(tag, className, text) {
        const el = document.createElement(tag);
        if (className) el.className = className;
        if (text !== undefined) el.textContent = text;
        return el;
    }

    function _renderThemes(section) {
        section.textContent = '';
        section.appendChild(_el('div', 'proto-panel-heading', 'Theme'));
        const current = Utils.getCurrentTheme();
        Themes.list().forEach(def => {
            const btn = _el('button', 'proto-theme-btn', def.label);
            btn.type = 'button';
            btn.setAttribute('aria-pressed', String(def.name === current));
            const badge = _el('span', 'proto-theme-badge', def.proto ? 'proto' : def.base);
            btn.appendChild(badge);
            btn.addEventListener('click', () => {
                if (state.callbacks && state.callbacks.onThemeSelect) {
                    state.callbacks.onThemeSelect(def.name);
                }
                // applyThemeChange is async; re-render highlight on next tick
                setTimeout(_rerender, 50);
            });
            section.appendChild(btn);
        });
    }

    function _renderFlags(section) {
        section.textContent = '';
        section.appendChild(_el('div', 'proto-panel-heading', 'Layout experiments'));
        ProtoFlags.list().forEach(flag => {
            const row = _el('div', 'proto-flag-row');
            const label = _el('span', 'proto-flag-name', flag.name);
            if (flag.locked) label.title = 'Forced by docked layout';
            row.appendChild(label);
            const group = _el('div', 'proto-flag-values');
            flag.values.forEach(value => {
                const btn = _el('button', 'proto-flag-btn', value);
                btn.type = 'button';
                btn.setAttribute('aria-pressed', String(flag.value === value));
                if (flag.locked) btn.disabled = true;
                btn.addEventListener('click', () => {
                    ProtoFlags.set(flag.name, value);
                    if (flag.requiresReload) {
                        state.needsReload = true;
                    }
                    _rerender();
                });
                group.appendChild(btn);
            });
            row.appendChild(group);
            section.appendChild(row);
        });

        if (state.needsReload) {
            const reload = _el('button', 'proto-reload-btn', '↻ Reload to apply layout');
            reload.type = 'button';
            reload.addEventListener('click', () => window.location.reload());
            section.appendChild(reload);
        }
    }

    function _rerender() {
        if (!state.root) return;
        _renderThemes(state.root.querySelector('.proto-panel-themes'));
        _renderFlags(state.root.querySelector('.proto-panel-flags'));
    }

    function _buildPanel() {
        const root = _el('div', 'proto-panel-root');
        root.id = 'proto-panel-root';

        const toggle = _el('button', 'proto-panel-toggle', '🎨');
        toggle.type = 'button';
        toggle.title = 'Prototype themes & layouts';
        toggle.setAttribute('aria-label', 'Prototype themes and layouts');

        const panel = _el('div', 'proto-panel');
        panel.appendChild(_el('div', 'proto-panel-title', 'Prototypes'));
        panel.appendChild(_el('div', 'proto-panel-themes'));
        panel.appendChild(_el('div', 'proto-panel-flags'));

        const hide = _el('button', 'proto-hide-btn', 'Hide prototype tools');
        hide.type = 'button';
        hide.addEventListener('click', () => {
            // Full opt-out: back to production behavior
            const current = Utils.getCurrentTheme();
            if (Themes.resolve(current).proto && state.callbacks && state.callbacks.onThemeSelect) {
                state.callbacks.onThemeSelect(Themes.baseOf(current));
            }
            ProtoFlags.resetAll();
            destroy();
        });
        panel.appendChild(hide);

        toggle.addEventListener('click', () => {
            state.open = !state.open;
            root.classList.toggle('proto-panel-open', state.open);
            if (state.open) _rerender();
        });

        root.appendChild(panel);
        root.appendChild(toggle);
        return root;
    }

    /**
     * Initializes the picker (call only when ProtoFlags.pickerRequested()).
     * @param {Object} callbacks
     * @param {Function} callbacks.onThemeSelect - Applies a theme by name
     */
    function init(callbacks) {
        if (state.root) return;
        state.callbacks = callbacks || {};
        state.root = _buildPanel();
        document.body.appendChild(state.root);
        document.addEventListener('protoflagschange', _rerender);
    }

    function destroy() {
        if (!state.root) return;
        document.removeEventListener('protoflagschange', _rerender);
        state.root.remove();
        state.root = null;
        state.open = false;
    }

    return { init, destroy };
})();

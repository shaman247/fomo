/** Venue membership is explicit city data; the Venue subtree also supports new exports. */
const VenueTags = (() => {
    let names = new Set();
    function configure(childrenOf, options = globalThis.__CITY__?.venueSelector || {}) {
        const scoped = Object.keys(childrenOf).some(name => name.startsWith('venue:'));
        names = new Set(scoped ? [] : (options.tags || []));
        function visit(name) {
            if (visited.has(name)) return;
            visited.add(name);
            names.add(name);
            for (const child of childrenOf[name] || []) visit(child);
        }
        const visited = new Set();
        visit('Venue');
    }
    return { configure, has: name => name.startsWith('venue:') || names.has(name) };
})();

/** Shared hierarchical navigation, with independently scoped labels and resets. */
function createTagSelector({ id, noun, searchLabel, includes }) {
    let names = [], children = {}, roots = [], branches = new Map();
    let panel, button, onChange, counts = {}, search = '', lastState = '';
    const expanded = new Set(), searchCollapsed = new Set();
    const activeEntries = () => Object.entries(TagStateManager.getTagStates())
        .filter(([name, state]) => includes(name) && state !== 'unselected');
    const active = name => TagStateManager.getTagState(name) !== 'unselected';
    const displayName = name => id === 'venue' ? Utils.getTagDisplayName(name) : name;
    const compareNames = (a, b) => displayName(a).localeCompare(displayName(b));

    function configure(childrenOf, availableNames) {
        VenueTags.configure(childrenOf);
        // Build navigation from the complete graph, not just currently assigned
        // tags. A missing/zero-count parent must never promote its child to a root.
        const candidates = new Set([...availableNames, ...Object.keys(childrenOf),
            ...Object.values(childrenOf).flat()].filter(includes));
        const configuredRoots = globalThis.__CITY__?.filterRoots?.[id] || [];
        const scoped = [...candidates].some(name => name.startsWith('venue:'));
        roots = configuredRoots.map(name => id === 'venue' && scoped ? `venue:${name}` : name)
            .filter(name => candidates.has(name)).sort(compareNames);
        children = {};
        for (const name of candidates) {
            children[name] = [...new Set(childrenOf[name] || [])]
                .filter(child => candidates.has(child) && child !== name).sort(compareNames);
        }
        function descend(name, seen = new Set()) {
            if (seen.has(name)) return seen;
            seen.add(name);
            for (const child of children[name] || []) descend(child, seen);
            return seen;
        }
        const reachable = new Set(roots.flatMap(name => [...descend(name)]));
        names = [...reachable].sort(compareNames);
        branches = new Map(names.map(name => [name, descend(name)]));
        // Unapproved/disconnected components stay out of navigation, including
        // cycles. Active legacy selections remain removable in the active list.
        if (panel) render();
    }
    function count(name) { return counts[name] || 0; }
    function updateCounts(events, locations = {}) {
        const next = {}, seen = new Set();
        for (const event of events) {
            const id = event.id ?? event;
            if (seen.has(id)) continue;
            seen.add(id);
            for (const tag of Utils.eventFilterTags(event, locations[event.locationKey])) {
                next[tag] = (next[tag] || 0) + 1;
            }
        }
        const changed = names.some(name => count(name) !== (next[name] || 0));
        counts = next;
        if (changed && panel) render();
        else refresh();
    }
    function setSearch(value) { search = value; searchCollapsed.clear(); }
    function visibleNames() {
        const query = Utils.normalizeForSearch(search.trim());
        const direct = new Set(names.filter(name => query
            ? [name, displayName(name)].some(term => Utils.normalizeForSearch(term).includes(query))
            : active(name) || count(name) > 0));
        return names.filter(name => [...branches.get(name)].some(child => direct.has(child)));
    }
    function groupState(name) {
        const state = TagStateManager.getTagState(name);
        return { checked: state === 'selected' || state === 'required',
            indeterminate: state === 'forbidden' || (state === 'unselected'
                && [...(branches.get(name) || [])].some(child => child !== name && active(child))) };
    }
    function setTagSelection(name, checked) {
        // Each checkbox represents a real tag, preserving the existing OR/required/
        // excluded semantics. Choosing a parent uses its exported inherited membership.
        TagStateManager.setTagState(name, checked ? 'selected' : 'unselected');
        commit();
    }
    function clear() {
        for (const [name] of activeEntries()) TagStateManager.setTagState(name, 'unselected');
        commit();
    }
    function commit() {
        refresh();
        TagStateManager.updateAllTagVisuals();
        onChange?.();
    }
    function label() {
        const entries = activeEntries();
        if (!entries.length) return `All ${noun}`;
        if (entries.length > 1) return `${entries.length} ${noun}`;
        const [name, state] = entries[0];
        return state === 'forbidden' ? `Exclude ${displayName(name)}` : displayName(name);
    }
    function sync() {
        if (!button || !panel) return;
        button.querySelector('span').textContent = label();
        button.setAttribute('aria-label', `${noun}: ${label()}`);
        panel.querySelectorAll('[data-topic]').forEach(input => Object.assign(input, groupState(input.dataset.topic)));
        const all = panel.querySelector('[data-all-tags]');
        all.checked = activeEntries().length === 0;
        all.indeterminate = !all.checked;
    }
    function refresh() {
        if (!panel) return;
        const signature = JSON.stringify(activeEntries());
        if (signature !== lastState) render();
        else sync();
    }
    function checkbox(name, focusKey = name || 'all') {
        const row = document.createElement('label');
        const input = document.createElement('input');
        input.type = 'checkbox';
        input.dataset.focusKey = focusKey;
        if (name) input.dataset.topic = name;
        else input.dataset.allTags = '';
        row.append(input, document.createTextNode(name ? displayName(name) : `All ${noun}`));
        const state = name && TagStateManager.getTagState(name);
        if (state === 'required' || state === 'forbidden') {
            const badge = document.createElement('span');
            badge.className = 'tag-selector-state';
            badge.textContent = state === 'required' ? 'Required' : 'Excluded';
            row.append(badge);
        }
        input.addEventListener('change', () => name ? setTagSelection(name, !active(name)) : clear());
        if (name) row.addEventListener('contextmenu', event => {
            event.preventDefault();
            const cycle = ['unselected', 'selected', 'required', 'forbidden'];
            TagStateManager.setTagState(name, cycle[(cycle.indexOf(TagStateManager.getTagState(name)) + 1) % cycle.length]);
            commit();
        });
        return row;
    }
    function render() {
        const focused = panel.contains(document.activeElement) ? document.activeElement : null;
        const focusKey = focused?.dataset.focusKey;
        const focusDisclosure = focused?.dataset.disclosure !== undefined;
        const focusSearch = focused?.type === 'search';
        const caret = focusSearch ? focused.selectionStart : null;
        const scrollTop = panel.scrollTop;
        const searchInput = document.createElement('input');
        searchInput.type = 'search';
        searchInput.className = 'neighborhood-search';
        searchInput.placeholder = searchLabel;
        searchInput.setAttribute('aria-label', searchLabel);
        searchInput.value = search;
        const tree = document.createElement('div');
        panel.replaceChildren(searchInput, checkbox());
        // Active filters remain removable even if a date/format change gives them
        // zero matches, or an organizer is selected outside the curated hierarchy.
        const entries = activeEntries();
        if (entries.length) {
            const selected = document.createElement('div');
            selected.className = 'tag-selector-active';
            selected.setAttribute('role', 'group');
            selected.setAttribute('aria-label', `Active ${id} filters`);
            entries.forEach(([name]) => selected.append(checkbox(name, `active:${name}`)));
            panel.append(selected);
        }
        panel.append(tree);
        let index = 0, visible;
        function node(name, path = new Set()) {
            const group = document.createElement('div');
            const heading = document.createElement('div');
            heading.className = 'format-selector-group-heading';
            const nodeKey = JSON.stringify([...path, name]);
            heading.append(checkbox(name, nodeKey));
            group.append(heading);
            const nextPath = new Set([...path, name]);
            const descendants = children[name].filter(child => !nextPath.has(child) && visible.has(child));
            if (descendants.length) {
                const list = document.createElement('div');
                list.className = 'format-selector-children';
                list.id = `${id}-group-${index++}`;
                list.setAttribute('role', 'group');
                list.setAttribute('aria-label', `${displayName(name)} tags`);
                const disclosure = document.createElement('button');
                disclosure.type = 'button';
                disclosure.className = 'format-selector-disclosure';
                disclosure.dataset.disclosure = name;
                disclosure.dataset.focusKey = nodeKey;
                disclosure.setAttribute('aria-controls', list.id);
                const arrow = document.createElement('span');
                arrow.textContent = '›';
                arrow.setAttribute('aria-hidden', 'true');
                disclosure.append(arrow);
                const syncExpanded = () => {
                    const open = search.trim() ? !searchCollapsed.has(name) : expanded.has(name);
                    list.hidden = !open;
                    disclosure.setAttribute('aria-expanded', String(open));
                    disclosure.setAttribute('aria-label', `${open ? 'Collapse' : 'Expand'} ${displayName(name)}`);
                    // Build branches only when opened: the exported graph has thousands
                    // of nodes and multiple parents, so eager rendering duplicates work.
                    if (open && !list.childElementCount) descendants.forEach(child => list.append(node(child, nextPath)));
                };
                disclosure.addEventListener('click', () => {
                    const toggles = search.trim() ? searchCollapsed : expanded;
                    if (toggles.has(name)) toggles.delete(name); else toggles.add(name);
                    syncExpanded();
                    sync();
                });
                syncExpanded();
                heading.append(disclosure);
                group.append(list);
            }
            return group;
        }
        function drawTree() {
            visible = new Set(visibleNames());
            index = 0;
            tree.replaceChildren(...roots.filter(name => visible.has(name)).map(name => node(name)));
            if (!tree.childElementCount) {
                const empty = document.createElement('p');
                empty.className = 'selector-empty-message';
                empty.textContent = search.trim() ? `No matching ${noun.toLowerCase()}` : 'No matching events';
                tree.append(empty);
            }
            sync();
        }
        searchInput.addEventListener('input', () => { setSearch(searchInput.value); drawTree(); });
        drawTree();
        lastState = JSON.stringify(activeEntries());
        if (focused) {
            const replacement = focusSearch ? searchInput : [...panel.querySelectorAll(focusDisclosure ? 'button' : 'input')]
                .find(el => el.dataset.focusKey === focusKey);
            (replacement || searchInput).focus({ preventScroll: true });
            if (focusSearch) searchInput.setSelectionRange(caret, caret);
        }
        panel.scrollTop = scrollTop;
    }
    function position() {
        const rect = button.getBoundingClientRect();
        const width = Math.min(350, window.innerWidth - 16);
        panel.style.width = `${width}px`;
        panel.style.left = `${Math.max(8, Math.min(rect.right - width, window.innerWidth - width - 8))}px`;
        panel.style.top = `${rect.bottom + 6}px`;
        panel.style.maxHeight = `${Math.max(100, window.innerHeight - rect.bottom - 22)}px`;
    }
    function init(config) {
        button = document.getElementById(`${id}-selector-button`);
        panel = document.getElementById(`${id}-selector-panel`);
        onChange = config.onChange;
        configure(config.childrenOf, config.names);
        panel.addEventListener('beforetoggle', event => {
            button.setAttribute('aria-expanded', String(event.newState === 'open'));
            if (event.newState === 'open') { refresh(); position(); }
        });
        window.addEventListener('resize', () => { if (panel.matches(':popover-open')) position(); });
    }
    return { init, configure, updateCounts, count, setSearch, visibleNames, groupState, setTagSelection, clear, label, refresh };
}

const TagSelector = createTagSelector({ id: 'tag', noun: 'Tags', searchLabel: 'Find a tag',
    includes: name => !VenueTags.has(name) });
const VenueSelector = createTagSelector({ id: 'venue', noun: 'Venues', searchLabel: 'Find a venue type',
    includes: name => VenueTags.has(name) });

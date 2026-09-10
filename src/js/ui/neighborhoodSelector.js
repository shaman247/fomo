/** Geographic OR filter, independent of event formats and topic tags. */
const NeighborhoodSelector = (() => {
    const areaName = name => name.startsWith('venue:') ? name.slice(6) : name;
    let children = {}, roots = [], names = [], branches = new Map();
    let selected = null; // null = all checked; [] = none checked. Both show all areas.
    let panel, button, onChange;
    const expanded = new Set();
    const searchCollapsed = new Set();
    let configured = false;
    let eventCounts = {}, totalCount = 0, search = '';
    let ancestors = new Map();

    function count(name) { return eventCounts[name] || 0; }
    function isEmpty(name) { return count(name) === 0; }
    function updateCounts(events, locations = {}) {
        const counts = {}, seen = new Set();
        for (const event of events) {
            const id = event.id ?? event;
            if (seen.has(id)) continue;
            seen.add(id);
            const matched = new Set();
            for (const tag of [...(event.tags || []), ...(locations[event.locationKey]?.tags || [])]) {
                for (const name of ancestors.get(areaName(tag)) || []) matched.add(name);
            }
            for (const name of matched) counts[name] = (counts[name] || 0) + 1;
        }
        const changed = totalCount !== seen.size || names.some(name => count(name) !== (counts[name] || 0));
        eventCounts = counts;
        totalCount = seen.size;
        if (changed && panel) render();
    }
    function visibleNames() {
        const query = search.trim().toLocaleLowerCase();
        const direct = new Set(names.filter(name => query
            ? name.toLocaleLowerCase().includes(query) : !isEmpty(name)));
        // Include the ancestor path so even an empty matching area is reachable.
        return names.filter(name => direct.has(name)
            || [...(branches.get(name) || [])].some(child => direct.has(child)));
    }
    function setSearch(value) { search = value; searchCollapsed.clear(); }


    function configure(childrenOf, geographicTags, options = globalThis.__CITY__?.neighborhoodSelector || {}) {
        childrenOf = Object.fromEntries(Object.entries(childrenOf || {}).map(([name, children]) => [areaName(name), children.map(areaName)]));
        const allowed = new Set([...(geographicTags || [])].map(areaName));
        allowed.delete('Neighborhood');
        const configuredGroups = options.groups || {};
        for (const name of Object.keys(configuredGroups)) allowed.add(name);
        const groupParents = new Map();
        for (const [parent, members] of Object.entries(configuredGroups)) {
            for (const child of members) groupParents.set(child, parent);
        }
        const order = preferred => (a, b) => {
            const rank = name => { const index = preferred.indexOf(name); return index < 0 ? Infinity : index; };
            return (rank(a) - rank(b)) || a.localeCompare(b);
        };
        if (!configured) {
            (options.expanded || []).forEach(name => expanded.add(name));
            configured = true;
        }
        names = [...allowed].sort((a, b) => a.localeCompare(b));
        children = {};
        const nested = new Set();
        for (const name of names) {
            children[name] = [...new Set([...(childrenOf?.[name] || []), ...(configuredGroups[name] || [])])]
                .filter(child => allowed.has(child) && child !== name
                    && (!groupParents.has(child) || groupParents.get(child) === name))
                .sort(order(configuredGroups[name] || []));
            children[name].forEach(child => nested.add(child));
        }
        roots = names.filter(name => !nested.has(name));
        branches = new Map();
        function descend(name, seen = new Set()) {
            if (seen.has(name)) return;
            seen.add(name);
            for (const child of children[name] || []) descend(child, seen);
            return seen;
        }
        for (const name of names) branches.set(name, descend(name));
        ancestors = new Map();
        for (const [parent, branch] of branches) {
            for (const child of branch) {
                if (!ancestors.has(child)) ancestors.set(child, []);
                ancestors.get(child).push(parent);
            }
        }
        // Keep malformed cyclic components reachable without recursing forever.
        const reachable = new Set(roots.flatMap(name => [...branches.get(name)]));
        for (const name of names) if (!reachable.has(name)) {
            roots.push(name);
            branches.get(name).forEach(child => reachable.add(child));
        }
        roots.sort(order(options.order || []));
        if (selected !== null) selected = new Set([...selected].filter(name => allowed.has(name)));
        normalize();
        if (panel) render();
    }
    function normalize() { if (selected?.size === names.length && names.length) selected = null; }
    function selection() { return selected === null ? null : names.filter(name => selected.has(name)); }
    function setSelection(values) {
        selected = values == null ? null : new Set(values.filter(name => branches.has(name)));
        normalize();
        sync();
    }
    function fromLegacyTags(values) {
        values = values.map(areaName);
        if (values.includes('Neighborhood')) return null;
        return [...new Set(values.flatMap(name => [...(branches.get(name) || [])]))];
    }
    function groupState(name) {
        const branch = branches.get(name) || new Set();
        const count = [...branch].filter(n => selected === null || selected.has(n)).length;
        return { checked: count > 0 && count === branch.size, indeterminate: count > 0 && count < branch.size };
    }
    function setGroupSelection(name, checked) {
        const next = new Set(selection() || names);
        for (const child of branches.get(name) || []) {
            if (checked) next.add(child); else next.delete(child);
        }
        setSelection([...next]);
        onChange?.();
    }
    function matches(event, location) {
        if (selected === null || selected.size === 0) return true;
        const tags = new Set([...(event.tags || []), ...(location?.tags || [])].map(areaName));
        const geographic = [...tags].filter(name => branches.has(name));
        // Ignore inherited borough/region tags when a more specific area is known.
        // Otherwise excluding one neighborhood would still match its checked borough.
        return geographic.some(name => selected.has(name)
            && !geographic.some(other => other !== name && branches.get(name).has(other)));
    }
    function label() {
        if (selected === null || selected.size === 0) return 'Everywhere';
        // Summarize completely selected branches by their highest checked heading.
        const complete = names.filter(name => groupState(name).checked);
        const top = complete.filter(name => !complete.some(parent => parent !== name && branches.get(parent).has(name)));
        if (top.length === 1 && branches.get(top[0]).size === selected.size) return top[0];
        return `${top.length || selected.size} Areas`;
    }
    function sync() {
        if (!panel || !button) return;
        button.querySelector('span').textContent = label();
        button.setAttribute('aria-label', `Neighborhoods: ${label()}`);
        const all = panel.querySelector('[data-all-neighborhoods]');
        all.checked = selected === null;
        all.indeterminate = selected !== null && selected.size > 0;
        panel.querySelectorAll('[data-neighborhood]').forEach(input => Object.assign(input, groupState(input.dataset.neighborhood)));
    }
    function checkbox(name) {
        const row = document.createElement('label');
        const input = document.createElement('input');
        input.type = 'checkbox';
        if (name) input.dataset.neighborhood = name;
        else input.dataset.allNeighborhoods = '';
        row.append(input, document.createTextNode(name || 'Everywhere'));
        input.addEventListener('change', () => {
            if (name) setGroupSelection(name, input.checked);
            else { setSelection(input.checked ? null : []); onChange?.(); }
        });
        return row;
    }
    function render() {
        const focused = panel.contains(document.activeElement) ? document.activeElement : null;
        const focusArea = focused?.dataset.neighborhood;
        const focusAll = focused?.hasAttribute('data-all-neighborhoods');
        const focusSearch = focused?.type === 'search';
        const caret = focusSearch ? focused.selectionStart : null;
        const scrollTop = panel.scrollTop;
        const searchInput = document.createElement('input');
        searchInput.type = 'search';
        searchInput.className = 'neighborhood-search';
        searchInput.placeholder = 'Find an area';
        searchInput.setAttribute('aria-label', 'Find a neighborhood or region');
        searchInput.value = search;
        const tree = document.createElement('div');
        panel.replaceChildren(searchInput, checkbox(), tree);
        let index = 0, visible;
        searchInput.addEventListener('input', () => { setSearch(searchInput.value); drawTree(); });
        function node(name, path = new Set()) {
            const group = document.createElement('div');
            const heading = document.createElement('div');
            heading.className = 'format-selector-group-heading';
            heading.append(checkbox(name));
            group.append(heading);
            const nextPath = new Set([...path, name]);
            const descendants = children[name].filter(child => !nextPath.has(child) && visible.has(child));
            if (descendants.length) {
                const list = document.createElement('div');
                list.className = 'format-selector-children';
                list.id = `neighborhood-group-${index++}`;
                list.setAttribute('role', 'group');
                list.setAttribute('aria-label', `${name} neighborhoods`);
                const disclosure = document.createElement('button');
                disclosure.type = 'button';
                disclosure.className = 'format-selector-disclosure';
                disclosure.setAttribute('aria-controls', list.id);
                const arrow = document.createElement('span');
                arrow.textContent = '›'; arrow.setAttribute('aria-hidden', 'true');
                disclosure.append(arrow);
                const syncExpanded = () => {
                    const open = search.trim() ? !searchCollapsed.has(name) : expanded.has(name);
                    list.hidden = !open;
                    disclosure.setAttribute('aria-expanded', String(open));
                    disclosure.setAttribute('aria-label', `${open ? 'Collapse' : 'Expand'} ${name}`);
                };
                disclosure.addEventListener('click', () => {
                    if (search.trim()) {
                        if (searchCollapsed.has(name)) searchCollapsed.delete(name); else searchCollapsed.add(name);
                    } else {
                        if (expanded.has(name)) expanded.delete(name); else expanded.add(name);
                    }
                    syncExpanded();
                });
                descendants.forEach(child => list.append(node(child, nextPath)));
                syncExpanded(); heading.append(disclosure); group.append(list);
            }
            return group;
        }
        function drawTree() {
            visible = new Set(visibleNames());
            index = 0;
            tree.replaceChildren(...roots.filter(name => visible.has(name)).map(name => node(name)));
            if (!tree.childElementCount) {
                const empty = document.createElement('p');
                empty.className = 'neighborhood-empty-message';
                empty.textContent = search.trim() ? 'No matching areas' : 'No matching events';
                tree.append(empty);
            }
            sync();
        }
        drawTree();
        if (focusSearch) {
            searchInput.focus({ preventScroll: true });
            searchInput.setSelectionRange(caret, caret);
        } else if (focused) {
            const replacement = [...panel.querySelectorAll('input')].find(input =>
                focusAll ? input.hasAttribute('data-all-neighborhoods') : focusArea && input.dataset.neighborhood === focusArea);
            (replacement || searchInput).focus({ preventScroll: true });
        }
        panel.scrollTop = scrollTop;
    }
    function position() {
        const rect = button.getBoundingClientRect();
        const width = Math.min(330, window.innerWidth - 16);
        panel.style.width = `${width}px`;
        panel.style.left = `${Math.max(8, Math.min(rect.right - width, window.innerWidth - width - 8))}px`;
        panel.style.top = `${rect.bottom + 6}px`;
        panel.style.maxHeight = `${Math.max(100, window.innerHeight - rect.bottom - 22)}px`;
    }
    function init(childrenOf, geographicTags, values, callback) {
        button = document.getElementById('neighborhood-selector-button');
        panel = document.getElementById('neighborhood-selector-panel');
        onChange = callback;
        configure(childrenOf, geographicTags);
        setSelection(values);
        panel.addEventListener('beforetoggle', event => {
            button.setAttribute('aria-expanded', String(event.newState === 'open'));
            if (event.newState === 'open') position();
        });
        window.addEventListener('resize', () => { if (panel.matches(':popover-open')) position(); });
    }
    return { init, configure, updateCounts, count, setSearch, visibleNames, isEmpty, selection, setSelection, fromLegacyTags, matches, groupState, setGroupSelection, label };
})();

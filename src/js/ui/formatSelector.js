/** Event formats are an independent OR filter, intersected with dates and topics. */
const FormatSelector = (() => {
    let groups = {};
    let types = [];
    let selected = null; // null = all checked; empty Set = none checked. Both show all events.
    const expandedGroups = new Set();
    let button, panel, onChange;
    let eventCounts = {}, totalCount = 0;

    function count(type) { return eventCounts[type] || 0; }
    function categoryCount(category) {
        return [...new Set(groups[category] || [])].reduce((sum, type) => sum + count(type), 0);
    }
    function visibleTypes() { return types.filter(type => count(type) > 0); }
    function updateCounts(events) {
        const counts = {}, seen = new Set();
        for (const event of events) {
            const id = event.id ?? event;
            if (seen.has(id)) continue;
            seen.add(id);
            const type = types.includes(event.event_type) ? event.event_type : 'Other';
            counts[type] = (counts[type] || 0) + 1;
        }
        const changed = totalCount !== seen.size || types.some(type => count(type) !== (counts[type] || 0));
        eventCounts = counts;
        totalCount = seen.size;
        if (changed && panel) {
            render();
            if (panel.matches(':popover-open')) position();
        }
    }
    function countedLabel(text, format, category) {
        return `${text} (${category ? categoryCount(category) : format ? count(format) : totalCount})`;
    }

    function configure(categories) {
        groups = { ...(categories || {}), 'Other': ['Other'] };
        types = [...new Set(Object.values(groups).flat())];
        for (const category of expandedGroups) if (!groups[category]) expandedGroups.delete(category);
        if (selected !== null) selected = new Set([...selected].filter(t => types.includes(t)));
        normalizeSelection();
        if (panel) render();
    }
    function selection() { return selected === null ? null : types.filter(t => selected.has(t)); }
    function setSelection(values) {
        selected = values == null ? null : new Set(values.filter(t => types.includes(t)));
        normalizeSelection();
        sync();
    }
    function normalizeSelection() {
        if (selected?.size === types.length) selected = null;
    }
    function groupState(category) {
        const formats = groups[category] || [];
        const count = formats.filter(type => selected === null || selected.has(type)).length;
        return { checked: formats.length > 0 && count === formats.length,
            indeterminate: count > 0 && count < formats.length };
    }
    function setGroupSelection(category, checked) {
        const next = new Set(selection() || types);
        for (const type of groups[category] || []) {
            if (checked) next.add(type); else next.delete(type);
        }
        commit([...next]);
    }
    function fromLegacyTags(names) {
        if (names.includes('Format')) return null;
        return [...new Set(names.flatMap(name => groups[name === 'Outings' ? 'Outing' : name] || (types.includes(name) ? [name] : [])))];
    }
    function matches(event) {
        return selected === null || selected.size === 0 || selected.has(types.includes(event.event_type) ? event.event_type : 'Other');
    }
    function label() {
        const values = selection();
        return values === null || values.length === 0 ? 'All Events' : values.length === 1 ? values[0] : `${values.length} Formats`;
    }
    function sync() {
        if (!button || !panel) return;
        button.querySelector('span').textContent = label();
        button.setAttribute('aria-label', `Event formats: ${label()}`);
        const all = panel.querySelector('[data-all-formats]');
        all.checked = selected === null;
        all.indeterminate = selected !== null && selected.size > 0;
        panel.querySelectorAll('[data-format]').forEach(input => {
            input.checked = selected === null || selected.has(input.dataset.format);
        });
        panel.querySelectorAll('[data-category]').forEach(input => {
            Object.assign(input, groupState(input.dataset.category));
        });
    }
    function commit(values) {
        setSelection(values);
        onChange?.();
    }
    function checkbox(text, format, category) {
        const row = document.createElement('label');
        const input = document.createElement('input');
        input.type = 'checkbox';
        if (category) input.dataset.category = category;
        else if (format) input.dataset.format = format;
        else input.dataset.allFormats = '';
        row.append(input, document.createTextNode(countedLabel(text, format, category)));
        input.addEventListener('change', () => {
            if (category) setGroupSelection(category, input.checked);
            else if (!format) commit(input.checked ? null : []);
            else {
                const next = new Set(selection() || types);
                if (input.checked) next.add(format); else next.delete(format);
                commit([...next]);
            }
        });
        return row;
    }
    function render() {
        const focused = panel.contains(document.activeElement) ? document.activeElement : null;
        const focusFormat = focused?.dataset.format;
        const focusCategory = focused?.dataset.category;
        const focusAll = focused?.hasAttribute('data-all-formats');
        const scrollTop = panel.scrollTop;
        panel.replaceChildren();
        const header = document.createElement('div');
        header.className = 'format-selector-group-heading';
        header.append(checkbox('All Events'));
        panel.append(header);
        for (const [category, formats] of Object.entries(groups)) {
            if (categoryCount(category) === 0) continue;
            const group = document.createElement('div');
            group.className = 'format-selector-group';
            if (formats.length === 1 && formats[0] === category) {
                group.classList.add('format-selector-group-heading');
                group.append(checkbox(category, category));
            } else {
                const heading = document.createElement('div');
                heading.className = 'format-selector-group-heading';
                heading.append(checkbox(category, null, category));
                const children = document.createElement('div');
                children.className = 'format-selector-children';
                children.id = `format-group-${panel.children.length}`;
                children.setAttribute('role', 'group');
                children.setAttribute('aria-label', `${category} formats`);
                formats.filter(type => count(type) > 0).forEach(type => children.append(checkbox(type, type)));
                const disclosure = document.createElement('button');
                disclosure.type = 'button';
                disclosure.className = 'format-selector-disclosure';
                disclosure.setAttribute('aria-controls', children.id);
                const chevron = document.createElement('span');
                chevron.textContent = '›';
                chevron.setAttribute('aria-hidden', 'true');
                disclosure.append(chevron);
                const syncExpanded = () => {
                    const expanded = expandedGroups.has(category);
                    children.hidden = !expanded;
                    disclosure.setAttribute('aria-expanded', String(expanded));
                    disclosure.setAttribute('aria-label', `${expanded ? 'Collapse' : 'Expand'} ${category}`);
                };
                disclosure.addEventListener('click', () => {
                    if (expandedGroups.has(category)) expandedGroups.delete(category);
                    else expandedGroups.add(category);
                    syncExpanded();
                });
                syncExpanded();
                heading.append(disclosure);
                group.append(heading, children);
            }
            panel.append(group);
        }
        if (!totalCount) {
            const empty = document.createElement('p');
            empty.className = 'selector-empty-message';
            empty.textContent = 'No matching events';
            panel.append(empty);
        }
        sync();
        if (focused) {
            const replacement = [...panel.querySelectorAll('input')].find(input =>
                focusAll ? input.hasAttribute('data-all-formats') :
                    (focusFormat && input.dataset.format === focusFormat) ||
                    (focusCategory && input.dataset.category === focusCategory));
            (replacement || panel.querySelector('[data-all-formats]')).focus({ preventScroll: true });
        }
        panel.scrollTop = scrollTop;
    }
    function position() {
        const rect = button.getBoundingClientRect();
        // Size against every leaf even when its category is collapsed.
        const style = getComputedStyle(panel.querySelector('label'));
        const context = document.createElement('canvas').getContext('2d');
        context.font = `${style.fontWeight} ${style.fontSize} ${style.fontFamily}`;
        const textWidth = text => context.measureText(text).width
            + Math.max(0, text.length - 1) * (parseFloat(style.letterSpacing) || 0);
        const px = (element, property) => element ? parseFloat(getComputedStyle(element)[property]) || 0 : 0;
        const rowChrome = parseFloat(style.paddingLeft) + parseFloat(style.paddingRight)
            + px(panel.querySelector('input'), 'width') + parseFloat(style.columnGap);
        const indent = px(panel.querySelector('.format-selector-children'), 'paddingLeft');
        const disclosureWidth = px(panel.querySelector('.format-selector-disclosure'), 'width');
        const contentWidth = Math.max(
            ...types.map(type => textWidth(countedLabel(type, type)) + indent),
            ...Object.keys(groups).map(category => textWidth(countedLabel(category, null, category)) + disclosureWidth),
            textWidth(countedLabel('All Events'))
        );
        const width = Math.min(Math.ceil(contentWidth + rowChrome
            + px(panel, 'borderLeftWidth') + px(panel, 'borderRightWidth')), window.innerWidth - 16);
        panel.style.width = `${width}px`;
        panel.style.left = `${Math.max(8, Math.min(rect.right - width, window.innerWidth - width - 8))}px`;
        panel.style.top = `${rect.bottom + 6}px`;
        panel.style.maxHeight = `${Math.max(100, window.innerHeight - rect.bottom - 22)}px`;
    }
    function init(categories, values, callback) {
        button = document.getElementById('format-selector-button');
        panel = document.getElementById('format-selector-panel');
        onChange = callback;
        configure(categories);
        setSelection(values);
        panel.addEventListener('beforetoggle', event => {
            button.setAttribute('aria-expanded', String(event.newState === 'open'));
            if (event.newState === 'open') position();
        });
        window.addEventListener('resize', () => {
            if (panel.matches(':popover-open')) position();
        });
    }
    return { init, configure, updateCounts, count, categoryCount, visibleTypes, fromLegacyTags, selection, setSelection, groupState, setGroupSelection, matches, label };
})();

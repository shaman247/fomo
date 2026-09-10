(() => {
    const $ = id => document.getElementById(id);
    const types = { place: 'Place', event: 'Event', tag: 'Tag', keyword: 'Keyword' };
    let selected = '', searchVersion = 0, resultVersion = 0, offset = 0, timer;
    let examples = [], searchAbort, resultAbort;
    const filters = ['limit', 'events', 'tags', 'precision', 'minimum'];
    const element = (tag, text, className) => {
        const node = document.createElement(tag);
        if (text !== undefined) node.textContent = text;
        if (className) node.className = className;
        return node;
    };
    const subtype = item => types[item.subtype === 'keyword' ? 'keyword' : item.type];
    const context = item => [subtype(item), `#${item.id}`, item.context,
        item.type === 'event' ? (item.active ? 'Active in export' : 'Outside active export') : '',
        !item.hasVector ? 'No learned vector' : ''].filter(Boolean).join(' · ');
    async function getJSON(path, params = {}, signal) {
        const response = await fetch(`${path}?${new URLSearchParams(params)}`, { signal });
        const data = await response.json();
        if (!response.ok) throw Error(data.error || 'Request failed');
        return data;
    }

    function searchButton(item) {
        const button = element('button', undefined, 'search-result');
        button.type = 'button'; button.dataset.entity = item.key;
        button.setAttribute('aria-current', String(item.key === selected));
        button.append(element('strong', `${item.emoji} ${item.name}`), element('small', context(item)));
        button.addEventListener('click', () => choose(item.key));
        return button;
    }

    async function search(more = false) {
        const version = ++searchVersion;
        searchAbort?.abort(); searchAbort = new AbortController();
        const query = $('search').value.trim();
        if (!more) { offset = 0; $('search-results').replaceChildren(); }
        $('more-search').hidden = true;
        if (!query) {
            $('search-status').textContent = 'Or choose a starting point below.';
            $('search-results').replaceChildren(...examples.map(searchButton));
            return;
        }
        $('search-status').textContent = 'Searching…';
        try {
            const data = await getJSON('/api/search', { q: query, type: $('search-type').value, offset }, searchAbort.signal);
            if (version !== searchVersion) return;
            $('search-results').append(...data.items.map(searchButton));
            offset += data.items.length;
            $('search-status').textContent = `${offset.toLocaleString()} of ${data.total.toLocaleString()} matches`;
            $('more-search').hidden = offset >= data.total;
        } catch (error) {
            if (error.name !== 'AbortError' && version === searchVersion) $('search-status').textContent = error.message;
        }
    }

    function renderSelection(seed) {
        const section = $('selection'); section.replaceChildren();
        section.append(element('span', context(seed), 'eyebrow'), element('h2', `${seed.emoji} ${seed.name}`));
        if (seed.description) section.append(element('p', seed.description, 'description'));
        if (!seed.hasVector) section.append(element('p', 'This entity has no learned vector. It may be an excluded geographic tag or have no supporting training records.', 'error'));
        if (seed.tags.length) {
            const list = element('div', undefined, 'entity-tags');
            for (const tag of seed.tags) {
                const chip = element('button', tag.name); chip.type = 'button';
                chip.addEventListener('click', () => choose(tag.key)); list.appendChild(chip);
            }
            section.appendChild(list);
        }
    }

    function renderNeighbors(data) {
        $('neighbors').replaceChildren();
        for (const [kind, title] of [['place', 'Places'], ['event', 'Events'], ['tag', 'Tags & keywords']]) {
            const group = data.groups[kind];
            const section = element('section', undefined, 'neighbor-column');
            const header = element('div', undefined, 'column-heading');
            header.append(element('h2', title), element('p', `${group.items.length} shown · ${group.total.toLocaleString()} eligible`, 'muted'));
            const list = element('ol', undefined, 'neighbor-list');
            group.items.forEach((item, index) => {
                const li = element('li');
                const button = element('button', undefined, 'neighbor'); button.type = 'button';
                button.title = `Explore ${item.name}`;
                const label = element('span');
                label.append(element('span', `${item.emoji} ${item.name}`, 'neighbor-name'), element('small', context(item)));
                button.append(element('span', String(index + 1), 'rank'), label,
                    element('span', item.score.toFixed(3), 'score'));
                button.addEventListener('click', () => choose(item.key));
                li.appendChild(button); list.appendChild(li);
            });
            if (!group.items.length) list.appendChild(element('li', 'No neighbors match these filters.', 'empty'));
            section.append(header, list); $('neighbors').appendChild(section);
        }
    }

    async function refresh() {
        if (!selected || !$('filters').reportValidity()) return;
        const version = ++resultVersion;
        resultAbort?.abort(); resultAbort = new AbortController();
        $('result-status').classList.remove('error');
        $('result-status').textContent = 'Comparing with the full model…';
        $('neighbors').replaceChildren();
        try {
            const params = Object.fromEntries(filters.map(id => [id, $(id).value]));
            const data = await getJSON('/api/neighbors', { entity: selected, ...params }, resultAbort.signal);
            if (version !== resultVersion) return;
            renderSelection(data.seed); renderNeighbors(data);
            $('result-status').textContent = `${data.precision === 'browser' ? 'Browser int8' : 'Full precision'} constituent similarity · highest first · click a result to explore`;
        } catch (error) {
            if (error.name !== 'AbortError' && version === resultVersion) {
                $('selection').replaceChildren(element('h2', 'Unable to load entity'));
                $('result-status').textContent = error.message;
                $('result-status').classList.add('error');
            }
        }
    }

    function saveURL(replace = false) {
        const params = new URLSearchParams({ entity: selected, ...Object.fromEntries(filters.map(id => [id, $(id).value])) });
        history[replace ? 'replaceState' : 'pushState']({}, '', `?${params}`);
    }
    function choose(key) {
        selected = key; saveURL();
        $('selection').replaceChildren(element('p', 'Loading selected entity…'));
        document.querySelectorAll('[data-entity]').forEach(button => button.setAttribute('aria-current', String(button.dataset.entity === key)));
        refresh();
    }
    function restoreURL() {
        const params = new URLSearchParams(location.search);
        selected = params.get('entity') || '';
        for (const id of filters) if (params.has(id)) {
            if ($(id).tagName === 'SELECT' && ![...$(id).options].some(option => option.value === params.get(id))) continue;
            $(id).value = params.get(id);
        }
        if (selected) refresh();
        else {
            resultVersion++; resultAbort?.abort();
            $('selection').replaceChildren(element('h2', 'What’s similar?'), element('p', 'Choose an entity to explore.'));
            $('neighbors').replaceChildren(); $('result-status').textContent = '';
        }
    }
    $('search').addEventListener('input', () => {
        clearTimeout(timer); searchVersion++; searchAbort?.abort();
        $('search-results').replaceChildren(); $('more-search').hidden = true;
        timer = setTimeout(() => search(), 150);
    });
    $('search-type').addEventListener('change', () => { clearTimeout(timer); search(); });
    $('more-search').addEventListener('click', () => search(true));
    $('filters').addEventListener('submit', event => event.preventDefault());
    $('filters').addEventListener('change', () => { if (selected) { saveURL(true); refresh(); } });
    window.addEventListener('popstate', restoreURL);
    getJSON('/api/meta').then(data => {
        $('model-info').textContent = `${data.entities.toLocaleString()} entities · ${data.dimensions} dimensions · model ${data.generation}`;
        examples = data.examples; search(); restoreURL();
    }).catch(error => { $('model-info').textContent = `Unable to load model: ${error.message}`; });
})();

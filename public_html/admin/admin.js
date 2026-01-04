/**
 * FOMO Admin Dashboard JavaScript
 * Client-side data handling with preloaded data
 */

// ============================================================================
// STATE
// ============================================================================

const AdminData = {
    websites: null,
    locations: null,
    events: null,
    tags: null,
    meta: {}  // columns, filters, etc.
};

const State = {
    currentTab: 'websites',
    selectedId: null,
    sort: { key: null, dir: 'asc' },
    activeFilter: null,
    searchQuery: '',
    visibleCount: 200,
    rowsPerPage: 200
};

// Detail panel history
const detailHistory = [];
let detailHistoryIndex = -1;


// ============================================================================
// INITIALIZATION
// ============================================================================

document.addEventListener('DOMContentLoaded', async () => {
    State.currentTab = window.initialTab || 'websites';

    // Load initial tab data
    await loadTabData(State.currentTab);

    // Prefetch other tabs in background
    setTimeout(prefetchOtherTabs, 100);
});

async function prefetchOtherTabs() {
    const tabs = ['websites', 'locations', 'events', 'tags'];
    for (const tab of tabs) {
        if (tab !== State.currentTab && !AdminData[tab]) {
            try {
                await loadTabData(tab, true);
            } catch (e) {
                // Silently ignore prefetch errors
            }
            await sleep(100);
        }
    }
}

function sleep(ms) {
    return new Promise(resolve => setTimeout(resolve, ms));
}

// ============================================================================
// DATA LOADING
// ============================================================================

async function loadTabData(tab, silent = false) {
    if (!silent) {
        document.getElementById('toolbar').innerHTML = '<span class="muted">Loading...</span>';
        document.querySelector('.table-wrap').innerHTML = '<p class="muted" style="padding:20px">Loading...</p>';
    }

    console.log(`[Admin] Loading ${tab} data...`);
    const startTime = performance.now();

    try {
        const response = await fetch(`api.php?type=${tab}`);
        console.log(`[Admin] Fetch completed in ${Math.round(performance.now() - startTime)}ms, status: ${response.status}`);
        const data = await response.json();
        console.log(`[Admin] Parsed JSON, got ${data.data?.length || 0} rows`);

        if (!data.success) {
            throw new Error(data.error || 'Failed to load data');
        }

        AdminData[tab] = data.data;
        AdminData.meta[tab] = {
            columns: data.columns,
            filters: data.filters,
            defaultSort: data.defaultSort,
            idField: data.idField,
            nameField: data.nameField,
            detailEndpoint: data.detailEndpoint
        };

        // Update tab counts
        if (data.counts) {
            updateTabCounts(data.counts);
        }

        if (!silent) {
            // Set default sort and filter
            State.sort = { ...data.defaultSort };
            State.activeFilter = data.filters.find(f => f.default)?.value || null;
            State.searchQuery = '';
            State.page = 1;

            renderTab(tab);
        }
    } catch (error) {
        if (!silent) {
            document.getElementById('toolbar').innerHTML = `<span class="error">Error: ${error.message}</span>`;
            document.querySelector('.table-wrap').innerHTML = '';
        }
    }
}

function updateTabCounts(counts) {
    for (const [tab, count] of Object.entries(counts)) {
        const el = document.getElementById(`count-${tab}`);
        if (el) {
            el.textContent = count.toLocaleString();
        }
    }
}

// ============================================================================
// RENDERING
// ============================================================================

function renderTab(tab) {
    const data = AdminData[tab];
    const meta = AdminData.meta[tab];

    if (!data || !meta) return;

    // Apply filters, search, and sort
    let rows = [...data];
    rows = applyFilter(rows, meta.filters);
    rows = applySearch(rows, meta.columns);
    rows = applySort(rows);

    // Render toolbar
    renderToolbar(rows.length, data.length, meta.filters);

    // Slice to visible count
    const visibleRows = rows.slice(0, State.visibleCount);
    const hasMore = rows.length > State.visibleCount;

    // Render table
    renderTable(visibleRows, meta.columns, meta.idField, meta.nameField, hasMore, rows.length);
}

function renderToolbar(filteredCount, totalCount, filters) {
    const toolbar = document.getElementById('toolbar');
    let html = '<div class="stats">';

    for (const f of filters) {
        if (f.static) {
            html += `<div class="stat static"><span class="num">${f.count.toLocaleString()}</span> ${f.label}</div>`;
        } else {
            const isActive = State.activeFilter === f.value;
            const cls = [f.class || '', isActive ? 'active' : ''].filter(Boolean).join(' ');
            html += `<a href="javascript:void(0)" onclick="setFilter('${f.value}')" class="stat ${cls}">
                <span class="num">${f.count.toLocaleString()}</span> ${f.label}
            </a>`;
        }
    }

    html += '</div>';
    html += `<input type="text" class="search" id="search" placeholder="Search..." value="${escapeHtml(State.searchQuery)}" oninput="onSearch(this.value)">`;

    toolbar.innerHTML = html;
}

function renderTable(rows, columns, idField, nameField, hasMore = false, totalCount = 0) {
    const tableWrap = document.querySelector('.table-wrap');

    let html = '<table id="data-table"><thead><tr>';

    // Header
    for (const col of columns) {
        const cls = col.class || '';
        if (col.sortable) {
            let arrow = '';
            if (State.sort.key === col.key) {
                arrow = State.sort.dir === 'asc' ? ' ↑' : ' ↓';
            }
            html += `<th class="${cls}"><a href="javascript:void(0)" onclick="setSort('${col.key}')">${escapeHtml(col.label)}${arrow}</a></th>`;
        } else {
            html += `<th class="${cls}">${escapeHtml(col.label)}</th>`;
        }
    }

    html += '</tr></thead><tbody>';

    // Rows
    for (const row of rows) {
        const rowId = idField === 'tag' ? row.tag : row[idField];
        const rowName = (row[nameField] || '').toLowerCase();
        const escapedId = escapeHtml(String(rowId)).replace(/'/g, "\\'");

        html += `<tr data-id="${escapeHtml(String(rowId))}" data-name="${escapeHtml(rowName)}" onclick="selectRow('${escapedId}')">`;

        for (const col of columns) {
            const style = col.maxWidth ? `max-width:${col.maxWidth}` : '';
            const title = col.maxWidth ? `title="${escapeHtml(String(row[col.key] || ''))}"` : '';
            html += `<td class="${col.class || ''}" style="${style}" ${title}>${renderValue(row, col)}</td>`;
        }

        html += '</tr>';
    }

    html += '</tbody></table>';

    // Show more button
    if (hasMore) {
        const remaining = totalCount - rows.length;
        const nextBatch = Math.min(remaining, State.rowsPerPage);
        html += `<div class="show-more-container">
            <button class="show-more-btn" onclick="showMore()">Show ${nextBatch} more (${remaining.toLocaleString()} remaining)</button>
        </div>`;
    }

    tableWrap.innerHTML = html;
}

function renderValue(row, col) {
    const key = col.key;
    let value = row[key];

    // Handle fallback
    if ((value === null || value === undefined || value === '') && col.fallback) {
        value = row[col.fallback];
    }

    // Handle empty
    if ((value === null || value === undefined || value === '') && col.empty) {
        return `<span class="muted">${col.empty}</span>`;
    }

    const type = col.type || 'text';

    switch (type) {
        case 'badge': {
            const badges = {
                'ok': ['ok', 'OK'], 'due': ['due', 'Due'], 'never': ['never', 'Never'],
                'failed': ['failed', 'Fail'], 'disabled': ['disabled', 'Off'],
                'processed': ['processed', 'Processed'], 'crawled': ['crawled', 'Crawled'],
                'extracted': ['extracted', 'Extracted'],
            };
            if (badges[value]) {
                return `<span class="badge badge-${badges[value][0]}">${badges[value][1]}</span>`;
            }
            return escapeHtml(String(value || ''));
        }

        case 'days_ago': {
            if (!value) return '<span class="muted">-</span>';
            const d = daysAgo(value);
            if (d === 0) return 'Today';
            if (d === 1) return 'Yesterday';
            return `${d}d ago`;
        }

        case 'friendly_date': {
            if (!value) return '-';
            return formatFriendlyDate(value);
        }

        case 'short_date': {
            if (!value) return '';
            return formatShortDate(value);
        }

        case 'coords': {
            if (row.lat && row.lng) {
                return `${row.lat.toFixed(4)}, ${row.lng.toFixed(4)}`;
            }
            return '-';
        }

        case 'tags_linked': {
            if (!value) return '<span class="muted">-</span>';
            const tags = value.split(', ').slice(0, 3);
            return tags.map(t => {
                const escaped = escapeHtml(t).replace(/'/g, "\\'");
                return `<a href="javascript:void(0)" onclick="event.stopPropagation();openDetail('tags', '${escaped}', '${escaped}')" class="tag" style="text-decoration:none;color:inherit">${escapeHtml(t)}</a>`;
            }).join('');
        }

        case 'tag_badge':
            return `<span class="tag-badge">${escapeHtml(String(value || ''))}</span>`;

        case 'location_link': {
            const id = row[col.idKey];
            if (!id) return escapeHtml(String(value || ''));
            const escaped = escapeHtml(String(value || '')).replace(/'/g, "\\'");
            return `<a href="javascript:void(0)" onclick="event.stopPropagation();openDetail('locations', ${id}, '${escaped}')" class="entity-link">${escapeHtml(String(value || ''))}</a>`;
        }

        case 'website_link': {
            const id = row[col.idKey];
            if (!id) return escapeHtml(String(value || ''));
            const escaped = escapeHtml(String(value || '')).replace(/'/g, "\\'");
            return `<a href="javascript:void(0)" onclick="event.stopPropagation();openDetail('websites', ${id}, '${escaped}')" class="entity-link">${escapeHtml(String(value || ''))}</a>`;
        }

        case 'count_if_gt1':
            return value > 1 ? String(value) : '<span class="muted">-</span>';

        case 'number':
            return value != null ? String(value) : '';

        default:
            return escapeHtml(String(value || ''));
    }
}

// ============================================================================
// FILTERING, SORTING, SEARCHING
// ============================================================================

function applyFilter(rows, filters) {
    if (!State.activeFilter) return rows;

    const filter = filters.find(f => f.value === State.activeFilter);
    if (!filter || !filter.match) return rows;

    const { field, op, value } = filter.match;

    return rows.filter(row => {
        const rowVal = row[field];
        switch (op) {
            case '=':
                return rowVal === value;
            case '!=':
                return rowVal !== value;
            case 'in':
                return Array.isArray(value) && value.includes(rowVal);
            case 'not_in':
                return Array.isArray(value) && !value.includes(rowVal);
            default:
                return true;
        }
    });
}

function applySearch(rows, columns) {
    if (!State.searchQuery) return rows;

    const query = State.searchQuery.toLowerCase();
    const searchableKeys = columns
        .filter(c => c.key === 'name' || c.key === 'tag' || c.key === 'address' || c.key === 'locations')
        .map(c => c.key);

    // Always search in name field
    if (!searchableKeys.includes('name')) searchableKeys.push('name');

    return rows.filter(row => {
        for (const key of searchableKeys) {
            const val = row[key];
            if (val && String(val).toLowerCase().includes(query)) {
                return true;
            }
        }
        return false;
    });
}

function applySort(rows) {
    if (!State.sort.key) return rows;

    const key = State.sort.key;
    const dir = State.sort.dir === 'asc' ? 1 : -1;

    return rows.sort((a, b) => {
        let valA = a[key];
        let valB = b[key];

        // Handle nulls
        if (valA == null && valB == null) return 0;
        if (valA == null) return 1;
        if (valB == null) return -1;

        // Numeric comparison
        if (typeof valA === 'number' && typeof valB === 'number') {
            return (valA - valB) * dir;
        }

        // String comparison
        return String(valA).localeCompare(String(valB)) * dir;
    });
}

// ============================================================================
// USER INTERACTIONS
// ============================================================================

function switchTab(tab) {
    if (tab === State.currentTab) return;

    // Update active tab styling
    document.querySelectorAll('#tabs .tab').forEach(t => {
        t.classList.toggle('active', t.dataset.tab === tab);
    });

    State.currentTab = tab;
    State.selectedId = null;
    State.visibleCount = State.rowsPerPage;

    // Clear row selection
    document.querySelectorAll('tr.selected').forEach(tr => tr.classList.remove('selected'));

    if (AdminData[tab]) {
        // Data already loaded, reset state and render
        const meta = AdminData.meta[tab];
        State.sort = { ...meta.defaultSort };
        State.activeFilter = meta.filters.find(f => f.default)?.value || null;
        State.searchQuery = '';
        renderTab(tab);
    } else {
        // Load data
        loadTabData(tab);
    }
}

function setFilter(value) {
    State.activeFilter = value;
    State.visibleCount = State.rowsPerPage;
    renderTab(State.currentTab);
}

function setSort(key) {
    if (State.sort.key === key) {
        State.sort.dir = State.sort.dir === 'asc' ? 'desc' : 'asc';
    } else {
        State.sort.key = key;
        State.sort.dir = 'asc';
    }
    renderTab(State.currentTab);
}

function onSearch(value) {
    State.searchQuery = value;
    State.visibleCount = State.rowsPerPage;
    renderTabPreservingSearch();
}

function renderTabPreservingSearch() {
    const searchInput = document.getElementById('search');
    const hadFocus = document.activeElement === searchInput;
    const cursorPos = searchInput ? searchInput.selectionStart : 0;

    renderTab(State.currentTab);

    // Restore focus and cursor position
    if (hadFocus) {
        const newSearchInput = document.getElementById('search');
        if (newSearchInput) {
            newSearchInput.focus();
            newSearchInput.setSelectionRange(cursorPos, cursorPos);
        }
    }
}

function showMore() {
    State.visibleCount += State.rowsPerPage;
    renderTab(State.currentTab);
}

function selectRow(id) {
    document.querySelectorAll('tr.selected').forEach(tr => tr.classList.remove('selected'));
    document.querySelector(`tr[data-id="${id}"]`)?.classList.add('selected');
    State.selectedId = id;

    const meta = AdminData.meta[State.currentTab];
    const data = AdminData[State.currentTab];
    const row = data.find(r => {
        const rowId = meta.idField === 'tag' ? r.tag : r[meta.idField];
        return String(rowId) === String(id);
    });

    if (!row) return;

    const name = row[meta.nameField];
    loadDetail(State.currentTab, id, name, true);
}

// ============================================================================
// DETAIL PANEL
// ============================================================================

function closeDetail() {
    document.getElementById('detail-panel').classList.remove('open');
    document.querySelectorAll('tr.selected').forEach(tr => tr.classList.remove('selected'));
    State.selectedId = null;
}

function openDetail(type, id, name) {
    document.querySelectorAll('tr.selected').forEach(tr => tr.classList.remove('selected'));
    State.selectedId = null;
    loadDetail(type, id, name, true);
}

function loadDetail(type, id, name, addToHistory) {
    const endpoints = {
        websites: 'websites_detail.php',
        locations: 'locations_detail.php',
        events: 'events_detail.php',
        tags: 'tags_detail.php'
    };

    const endpoint = endpoints[type];
    if (!endpoint) return;

    if (addToHistory) {
        if (detailHistoryIndex < detailHistory.length - 1) {
            detailHistory.splice(detailHistoryIndex + 1);
        }
        detailHistory.push({ type, id, name });
        detailHistoryIndex = detailHistory.length - 1;
    }

    document.getElementById('detail-title').textContent = name;
    document.getElementById('detail-panel').classList.add('open');
    document.getElementById('detail-content').innerHTML = '<p class="muted">Loading...</p>';
    updateDetailNavButtons();

    const param = type === 'tags' ? 'tag=' + encodeURIComponent(id) : 'id=' + id;
    fetch(endpoint + '?' + param)
        .then(r => r.text())
        .then(html => {
            document.getElementById('detail-content').innerHTML = html;
        });
}

function updateDetailNavButtons() {
    const backBtn = document.getElementById('detail-back');
    const fwdBtn = document.getElementById('detail-forward');

    if (backBtn) {
        backBtn.classList.toggle('disabled', detailHistoryIndex <= 0);
    }
    if (fwdBtn) {
        fwdBtn.classList.toggle('disabled', detailHistoryIndex >= detailHistory.length - 1);
    }
}

function detailGoBack() {
    if (detailHistoryIndex > 0) {
        detailHistoryIndex--;
        const entry = detailHistory[detailHistoryIndex];
        loadDetail(entry.type, entry.id, entry.name, false);
    }
}

function detailGoForward() {
    if (detailHistoryIndex < detailHistory.length - 1) {
        detailHistoryIndex++;
        const entry = detailHistory[detailHistoryIndex];
        loadDetail(entry.type, entry.id, entry.name, false);
    }
}

// ============================================================================
// UTILITIES
// ============================================================================

function escapeHtml(str) {
    if (str == null) return '';
    return String(str)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#039;');
}

function daysAgo(dateStr) {
    if (!dateStr) return null;
    const then = new Date(dateStr);
    then.setHours(0, 0, 0, 0);
    const now = new Date();
    now.setHours(0, 0, 0, 0);
    return Math.round((now - then) / (1000 * 60 * 60 * 24));
}

function formatFriendlyDate(dateStr) {
    // Parse as local date (not UTC) by using year/month/day components
    const [year, month, day] = dateStr.split('-').map(Number);
    const dt = new Date(year, month - 1, day);
    const today = new Date();
    today.setHours(0, 0, 0, 0);

    const diffDays = Math.round((dt - today) / (1000 * 60 * 60 * 24));

    if (diffDays === 0) return 'Today';
    if (diffDays === 1) return 'Tomorrow';
    if (diffDays > 0 && diffDays <= 6) {
        return dt.toLocaleDateString('en-US', { weekday: 'short' });
    }
    return dt.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
}

function formatShortDate(dateStr) {
    // Parse as local date (not UTC) by using year/month/day components
    const [year, month, day] = dateStr.split('-').map(Number);
    const dt = new Date(year, month - 1, day);
    return dt.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
}

// ============================================================================
// KEYBOARD SHORTCUTS
// ============================================================================

document.addEventListener('keydown', e => {
    if (e.key === 'Escape') closeDetail();

    const panelOpen = document.getElementById('detail-panel')?.classList.contains('open');
    if (panelOpen) {
        if ((e.altKey && e.key === 'ArrowLeft') || (e.metaKey && e.key === '[')) {
            e.preventDefault();
            detailGoBack();
        } else if ((e.altKey && e.key === 'ArrowRight') || (e.metaKey && e.key === ']')) {
            e.preventDefault();
            detailGoForward();
        }
    }
});

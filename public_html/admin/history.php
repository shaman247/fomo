<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Edit History - fomo.nyc Admin</title>
    <link rel="stylesheet" href="admin.css">
    <style>
        .history-container {
            max-width: 1400px;
            margin: 0 auto;
            padding: 20px;
        }

        .history-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 20px;
        }

        .filters {
            display: flex;
            gap: 15px;
            margin-bottom: 20px;
            flex-wrap: wrap;
        }

        .filter-group {
            display: flex;
            align-items: center;
            gap: 8px;
        }

        .filter-group label {
            color: var(--text-secondary);
            font-size: 0.9rem;
        }

        .filter-group select {
            padding: 6px 12px;
            border: 1px solid var(--border);
            border-radius: 6px;
            background: var(--bg-secondary);
            color: var(--text-primary);
        }

        .stats-bar {
            display: flex;
            gap: 20px;
            margin-bottom: 20px;
            padding: 15px;
            background: var(--bg-secondary);
            border-radius: 8px;
        }

        .stat-item {
            text-align: center;
        }

        .stat-item .value {
            font-size: 1.5rem;
            font-weight: bold;
            color: var(--accent);
        }

        .stat-item .label {
            font-size: 0.8rem;
            color: var(--text-secondary);
        }

        .history-list {
            display: flex;
            flex-direction: column;
            gap: 10px;
        }

        .edit-card {
            background: var(--bg-secondary);
            border-radius: 8px;
            padding: 15px;
            display: grid;
            grid-template-columns: auto 1fr auto;
            gap: 15px;
            align-items: start;
        }

        .edit-action {
            width: 80px;
            text-align: center;
        }

        .action-badge {
            display: inline-block;
            padding: 4px 10px;
            border-radius: 4px;
            font-size: 0.8rem;
            font-weight: 500;
            text-transform: uppercase;
        }

        .action-badge.INSERT {
            background: #10b981;
            color: white;
        }

        .action-badge.UPDATE {
            background: #3b82f6;
            color: white;
        }

        .action-badge.DELETE {
            background: #ef4444;
            color: white;
        }

        .source-badge {
            display: inline-block;
            padding: 2px 8px;
            border-radius: 4px;
            font-size: 0.75rem;
            margin-top: 5px;
        }

        .source-badge.local {
            background: #8b5cf6;
            color: white;
        }

        .source-badge.website {
            background: #10b981;
            color: white;
        }

        .source-badge.crawl {
            background: #f59e0b;
            color: white;
        }

        .edit-details {
            min-width: 0;
        }

        .edit-target {
            font-size: 0.9rem;
            margin-bottom: 5px;
        }

        .edit-target .table-name {
            font-family: var(--font-mono);
            background: var(--accent);
            padding: 2px 6px;
            border-radius: 4px;
            font-size: 0.8rem;
        }

        .edit-target .record-name {
            color: var(--text-primary);
            font-weight: 500;
        }

        .edit-target .field-name {
            color: var(--text-secondary);
        }

        .edit-change {
            font-size: 0.85rem;
            display: flex;
            gap: 10px;
            align-items: flex-start;
            margin-top: 8px;
        }

        .change-old, .change-new {
            flex: 1;
            padding: 8px;
            border-radius: 4px;
            font-family: var(--font-mono);
            white-space: pre-wrap;
            word-break: break-word;
            max-height: 100px;
            overflow-y: auto;
        }

        .change-old {
            background: rgba(239, 68, 68, 0.1);
            border: 1px solid rgba(239, 68, 68, 0.3);
        }

        .change-new {
            background: rgba(16, 185, 129, 0.1);
            border: 1px solid rgba(16, 185, 129, 0.3);
        }

        .change-arrow {
            color: var(--text-secondary);
            padding-top: 8px;
        }

        .edit-meta {
            text-align: right;
            font-size: 0.8rem;
            color: var(--text-secondary);
            min-width: 150px;
        }

        .edit-meta .time {
            margin-bottom: 3px;
        }

        .edit-meta .user {
            color: var(--accent);
        }

        .btn {
            padding: 6px 12px;
            border-radius: 6px;
            border: none;
            cursor: pointer;
            font-size: 0.85rem;
        }

        .btn-revert {
            background: #f59e0b;
            color: white;
            margin-top: 5px;
        }

        .btn-revert:hover {
            background: #d97706;
        }

        .empty-state {
            text-align: center;
            padding: 60px 20px;
            color: var(--text-secondary);
        }

        .record-history-header {
            background: var(--bg-secondary);
            padding: 15px;
            border-radius: 8px;
            margin-bottom: 20px;
        }

        .record-history-header h2 {
            margin: 0;
            font-size: 1.2rem;
        }

        .record-history-header .back-link {
            color: var(--accent);
            text-decoration: none;
            font-size: 0.9rem;
        }
    </style>
</head>
<body>
    <div class="history-container">
        <div class="history-header">
            <h1>Edit History</h1>
        </div>

        <div id="recordHeader" style="display: none;" class="record-history-header">
            <a href="history.php" class="back-link">&larr; All History</a>
            <h2 id="recordTitle"></h2>
        </div>

        <div class="filters" id="filters">
            <div class="filter-group">
                <label>Source:</label>
                <select id="filterSource" onchange="loadHistory()">
                    <option value="">All</option>
                    <option value="local">Local</option>
                    <option value="website">Website</option>
                    <option value="crawl">Crawl</option>
                </select>
            </div>
            <div class="filter-group">
                <label>Table:</label>
                <select id="filterTable" onchange="loadHistory()">
                    <option value="">All</option>
                </select>
            </div>
        </div>

        <div class="stats-bar" id="statsBar"></div>

        <div class="history-list" id="historyList">
            <div class="empty-state">Loading...</div>
        </div>
    </div>

    <script>
        // Check for record-specific history
        const urlParams = new URLSearchParams(window.location.search);
        const recordTable = urlParams.get('table');
        const recordId = urlParams.get('id');

        async function loadHistory() {
            const source = document.getElementById('filterSource').value;
            const table = document.getElementById('filterTable').value;

            let url;
            if (recordTable && recordId) {
                url = `history_api.php?table=${recordTable}&id=${recordId}`;
                document.getElementById('filters').style.display = 'none';
            } else {
                url = `history_api.php?recent=1&limit=100`;
                if (source) url += `&source=${source}`;
                if (table) url += `&filter_table=${table}`;
            }

            try {
                const response = await fetch(url);
                const data = await response.json();

                if (data.success) {
                    if (recordTable && recordId) {
                        renderRecordHistory(data);
                    } else {
                        renderRecentHistory(data);
                    }
                }
            } catch (error) {
                console.error('Error loading history:', error);
            }
        }

        function renderRecentHistory(data) {
            const { edits, stats, table_counts } = data;

            // Render stats
            const statsBar = document.getElementById('statsBar');
            const total = Object.values(stats).reduce((a, b) => a + b, 0);
            statsBar.innerHTML = `
                <div class="stat-item">
                    <div class="value">${total}</div>
                    <div class="label">Total Edits</div>
                </div>
                <div class="stat-item">
                    <div class="value">${stats.local || 0}</div>
                    <div class="label">Local</div>
                </div>
                <div class="stat-item">
                    <div class="value">${stats.website || 0}</div>
                    <div class="label">Website</div>
                </div>
                <div class="stat-item">
                    <div class="value">${stats.crawl || 0}</div>
                    <div class="label">Crawl</div>
                </div>
            `;

            // Populate table filter
            const tableSelect = document.getElementById('filterTable');
            const currentValue = tableSelect.value;
            tableSelect.innerHTML = '<option value="">All</option>';
            for (const [table, count] of Object.entries(table_counts)) {
                tableSelect.innerHTML += `<option value="${table}">${table} (${count})</option>`;
            }
            tableSelect.value = currentValue;

            renderEditList(edits);
        }

        function renderRecordHistory(data) {
            const { history, current_record, table, record_id } = data;

            // Show record header
            document.getElementById('recordHeader').style.display = 'block';
            document.getElementById('recordTitle').textContent =
                `${table} #${record_id}` + (current_record?.name ? `: ${current_record.name}` : '');

            // Hide stats
            document.getElementById('statsBar').style.display = 'none';

            renderEditList(history);
        }

        function renderEditList(edits) {
            const list = document.getElementById('historyList');

            if (edits.length === 0) {
                list.innerHTML = `
                    <div class="empty-state">
                        <h2>No edits found</h2>
                        <p>Edit history will appear here when changes are made.</p>
                    </div>
                `;
                return;
            }

            list.innerHTML = edits.map(edit => `
                <div class="edit-card">
                    <div class="edit-action">
                        <span class="action-badge ${edit.action}">${edit.action}</span>
                        <div class="source-badge ${edit.source}">${edit.source}</div>
                    </div>
                    <div class="edit-details">
                        <div class="edit-target">
                            <span class="table-name">${edit.table_name}</span>
                            <span class="record-name">${edit.record_name || '#' + edit.record_id}</span>
                            ${edit.field_name ? `<span class="field-name">.${edit.field_name}</span>` : ''}
                        </div>
                        ${edit.action === 'UPDATE' ? `
                            <div class="edit-change">
                                <div class="change-old">${escapeHtml(truncate(edit.old_value, 200)) || '<em>null</em>'}</div>
                                <div class="change-arrow">&rarr;</div>
                                <div class="change-new">${escapeHtml(truncate(edit.new_value, 200)) || '<em>null</em>'}</div>
                            </div>
                        ` : edit.action === 'INSERT' ? `
                            <div class="edit-change">
                                <div class="change-new" style="flex: 1;">${formatInsertValue(edit.new_value)}</div>
                            </div>
                        ` : `
                            <div class="edit-change">
                                <div class="change-old" style="flex: 1;">${formatInsertValue(edit.old_value)}</div>
                            </div>
                        `}
                    </div>
                    <div class="edit-meta">
                        <div class="time">${formatDate(edit.created_at)}</div>
                        ${edit.user_name ? `<div class="user">${edit.user_name}</div>` : ''}
                        ${edit.editor_info ? `<div>${edit.editor_info}</div>` : ''}
                        ${edit.action === 'UPDATE' ? `
                            <button class="btn btn-revert" onclick="revertEdit(${edit.id})">Revert</button>
                        ` : ''}
                    </div>
                </div>
            `).join('');
        }

        async function revertEdit(editId) {
            if (!confirm('Revert this edit? This will restore the previous value.')) {
                return;
            }

            try {
                const response = await fetch('history_api.php?action=revert', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ edit_id: editId })
                });
                const data = await response.json();

                if (data.success) {
                    alert('Edit reverted successfully');
                    loadHistory();
                } else {
                    alert('Error: ' + data.error);
                }
            } catch (error) {
                console.error('Error reverting:', error);
                alert('Error reverting edit');
            }
        }

        function formatDate(dateStr) {
            if (!dateStr) return '';
            const date = new Date(dateStr);
            const now = new Date();
            const diff = now - date;

            if (diff < 60000) return 'just now';
            if (diff < 3600000) return Math.floor(diff / 60000) + 'm ago';
            if (diff < 86400000) return Math.floor(diff / 3600000) + 'h ago';
            if (diff < 604800000) return Math.floor(diff / 86400000) + 'd ago';

            return date.toLocaleDateString();
        }

        function escapeHtml(str) {
            if (!str) return '';
            return String(str).replace(/&/g, '&amp;')
                              .replace(/</g, '&lt;')
                              .replace(/>/g, '&gt;');
        }

        function truncate(str, max) {
            if (!str) return '';
            str = String(str);
            return str.length > max ? str.substring(0, max) + '...' : str;
        }

        function formatInsertValue(value) {
            if (!value) return '<em>empty</em>';
            try {
                const obj = JSON.parse(value);
                return '<pre>' + escapeHtml(JSON.stringify(obj, null, 2).substring(0, 500)) + '</pre>';
            } catch {
                return escapeHtml(truncate(value, 300));
            }
        }

        // Load on page load
        loadHistory();
    </script>
</body>
</html>

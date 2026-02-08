<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Conflicts - fomo.nyc Admin</title>
    <link rel="stylesheet" href="admin.css">
    <style>
        .conflicts-container {
            max-width: 1400px;
            margin: 0 auto;
            padding: 20px;
        }

        .conflict-stats {
            display: flex;
            gap: 20px;
            margin-bottom: 20px;
        }

        .stat-card {
            background: var(--bg-secondary);
            border-radius: 8px;
            padding: 15px 25px;
            text-align: center;
        }

        .stat-card .count {
            font-size: 2rem;
            font-weight: bold;
            color: var(--accent);
        }

        .stat-card .label {
            color: var(--text-secondary);
            font-size: 0.9rem;
        }

        .stat-card.pending .count {
            color: #f59e0b;
        }

        .conflict-list {
            display: flex;
            flex-direction: column;
            gap: 15px;
        }

        .conflict-card {
            background: var(--bg-secondary);
            border-radius: 8px;
            padding: 20px;
            border-left: 4px solid #f59e0b;
        }

        .conflict-card.resolved {
            border-left-color: #10b981;
            opacity: 0.7;
        }

        .conflict-header {
            display: flex;
            justify-content: space-between;
            align-items: flex-start;
            margin-bottom: 15px;
        }

        .conflict-meta {
            font-size: 0.85rem;
            color: var(--text-secondary);
        }

        .conflict-table {
            font-family: var(--font-mono);
            background: var(--accent);
            padding: 2px 8px;
            border-radius: 4px;
            font-size: 0.85rem;
        }

        .conflict-field {
            color: var(--text-primary);
            font-weight: 500;
        }

        .conflict-values {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 15px;
            margin-bottom: 15px;
        }

        .value-box {
            background: var(--bg-primary);
            border-radius: 6px;
            padding: 15px;
        }

        .value-box h4 {
            font-size: 0.8rem;
            text-transform: uppercase;
            color: var(--text-secondary);
            margin-bottom: 8px;
        }

        .value-box.local h4 {
            color: #3b82f6;
        }

        .value-box.website h4 {
            color: #10b981;
        }

        .value-content {
            font-family: var(--font-mono);
            font-size: 0.9rem;
            white-space: pre-wrap;
            word-break: break-word;
            max-height: 150px;
            overflow-y: auto;
        }

        .conflict-actions {
            display: flex;
            gap: 10px;
            flex-wrap: wrap;
        }

        .btn {
            padding: 8px 16px;
            border-radius: 6px;
            border: none;
            cursor: pointer;
            font-size: 0.9rem;
            transition: background 0.2s;
        }

        .btn-local {
            background: #3b82f6;
            color: white;
        }

        .btn-local:hover {
            background: #2563eb;
        }

        .btn-website {
            background: #10b981;
            color: white;
        }

        .btn-website:hover {
            background: #059669;
        }

        .btn-merge {
            background: #8b5cf6;
            color: white;
        }

        .btn-merge:hover {
            background: #7c3aed;
        }

        .btn-secondary {
            background: var(--bg-primary);
            color: var(--text-primary);
            border: 1px solid var(--border);
        }

        .btn-secondary:hover {
            background: var(--border);
        }

        .batch-actions {
            display: flex;
            gap: 10px;
            align-items: center;
            margin-bottom: 20px;
            padding: 15px;
            background: var(--bg-secondary);
            border-radius: 8px;
        }

        .batch-actions label {
            display: flex;
            align-items: center;
            gap: 8px;
            cursor: pointer;
        }

        .checkbox-wrapper {
            width: 20px;
            height: 20px;
        }

        .merge-editor {
            margin-top: 10px;
            display: none;
        }

        .merge-editor.visible {
            display: block;
        }

        .merge-editor textarea {
            width: 100%;
            min-height: 100px;
            padding: 10px;
            border: 1px solid var(--border);
            border-radius: 6px;
            background: var(--bg-primary);
            color: var(--text-primary);
            font-family: var(--font-mono);
            resize: vertical;
        }

        .merge-editor .btn-group {
            margin-top: 10px;
            display: flex;
            gap: 10px;
        }

        .empty-state {
            text-align: center;
            padding: 60px 20px;
            color: var(--text-secondary);
        }

        .empty-state h2 {
            color: var(--text-primary);
            margin-bottom: 10px;
        }

        .status-tabs {
            display: flex;
            gap: 5px;
            margin-bottom: 20px;
        }

        .status-tab {
            padding: 8px 16px;
            border-radius: 6px;
            background: var(--bg-secondary);
            color: var(--text-secondary);
            cursor: pointer;
            border: none;
            transition: all 0.2s;
        }

        .status-tab.active {
            background: var(--accent);
            color: var(--bg-primary);
        }

        .status-tab:hover:not(.active) {
            background: var(--border);
        }
    </style>
</head>
<body>
    <div class="conflicts-container">
        <h1>Sync Conflicts</h1>

        <div class="conflict-stats" id="stats"></div>

        <div class="status-tabs" id="statusTabs"></div>

        <div class="batch-actions" id="batchActions" style="display: none;">
            <label>
                <input type="checkbox" id="selectAll">
                Select All
            </label>
            <span id="selectedCount">0 selected</span>
            <button class="btn btn-local" onclick="batchResolve('local')">Keep All Local</button>
            <button class="btn btn-website" onclick="batchResolve('website')">Keep All Website</button>
        </div>

        <div class="conflict-list" id="conflictList">
            <div class="empty-state">
                <h2>Loading...</h2>
            </div>
        </div>
    </div>

    <script>
        let conflicts = [];
        let selectedIds = new Set();
        let currentStatus = 'pending';

        async function loadConflicts(status = 'pending') {
            currentStatus = status;
            try {
                const response = await fetch(`conflicts_api.php?action=list&status=${status}`);
                const data = await response.json();

                if (data.success) {
                    conflicts = data.conflicts;
                    renderStats(data.counts);
                    renderTabs(data.counts);
                    renderConflicts();
                }
            } catch (error) {
                console.error('Error loading conflicts:', error);
            }
        }

        function renderStats(counts) {
            const stats = document.getElementById('stats');
            const total = Object.values(counts).reduce((a, b) => a + b, 0);
            const pending = counts.pending || 0;
            const resolved = total - pending;

            stats.innerHTML = `
                <div class="stat-card pending">
                    <div class="count">${pending}</div>
                    <div class="label">Pending</div>
                </div>
                <div class="stat-card">
                    <div class="count">${resolved}</div>
                    <div class="label">Resolved</div>
                </div>
                <div class="stat-card">
                    <div class="count">${total}</div>
                    <div class="label">Total</div>
                </div>
            `;
        }

        function renderTabs(counts) {
            const tabs = document.getElementById('statusTabs');
            const statuses = ['pending', 'resolved_local', 'resolved_website', 'resolved_merged'];

            tabs.innerHTML = statuses.map(status => {
                const count = counts[status] || 0;
                const label = status === 'pending' ? 'Pending' :
                              status === 'resolved_local' ? 'Kept Local' :
                              status === 'resolved_website' ? 'Kept Website' : 'Merged';
                return `
                    <button class="status-tab ${status === currentStatus ? 'active' : ''}"
                            onclick="loadConflicts('${status}')">
                        ${label} (${count})
                    </button>
                `;
            }).join('');
        }

        function renderConflicts() {
            const list = document.getElementById('conflictList');
            const batchActions = document.getElementById('batchActions');

            if (conflicts.length === 0) {
                list.innerHTML = `
                    <div class="empty-state">
                        <h2>No conflicts</h2>
                        <p>${currentStatus === 'pending' ? 'All sync conflicts have been resolved!' : 'No conflicts with this status.'}</p>
                    </div>
                `;
                batchActions.style.display = 'none';
                return;
            }

            batchActions.style.display = currentStatus === 'pending' ? 'flex' : 'none';

            list.innerHTML = conflicts.map(conflict => `
                <div class="conflict-card ${conflict.status !== 'pending' ? 'resolved' : ''}" data-id="${conflict.id}">
                    <div class="conflict-header">
                        <div>
                            ${currentStatus === 'pending' ? `
                                <label style="margin-right: 10px;">
                                    <input type="checkbox" class="conflict-checkbox"
                                           data-id="${conflict.id}"
                                           ${selectedIds.has(conflict.id) ? 'checked' : ''}>
                                </label>
                            ` : ''}
                            <span class="conflict-table">${conflict.table_name}</span>
                            <span class="conflict-field">${conflict.field_name || 'record'}</span>
                            <span class="conflict-meta">on ${conflict.record_name}</span>
                        </div>
                        <div class="conflict-meta">
                            ${formatDate(conflict.created_at)}
                        </div>
                    </div>

                    <div class="conflict-values">
                        <div class="value-box local">
                            <h4>Local Value</h4>
                            <div class="value-content">${escapeHtml(conflict.local_value) || '<em>null</em>'}</div>
                        </div>
                        <div class="value-box website">
                            <h4>Website Value</h4>
                            <div class="value-content">${escapeHtml(conflict.website_value) || '<em>null</em>'}</div>
                        </div>
                    </div>

                    ${conflict.status === 'pending' ? `
                        <div class="conflict-actions">
                            <button class="btn btn-local" onclick="resolveConflict(${conflict.id}, 'local')">
                                Keep Local
                            </button>
                            <button class="btn btn-website" onclick="resolveConflict(${conflict.id}, 'website')">
                                Keep Website
                            </button>
                            <button class="btn btn-merge" onclick="showMergeEditor(${conflict.id})">
                                Custom Merge
                            </button>
                        </div>
                        <div class="merge-editor" id="merge-${conflict.id}">
                            <textarea id="merge-value-${conflict.id}"
                                      placeholder="Enter merged value...">${escapeHtml(conflict.local_value) || ''}</textarea>
                            <div class="btn-group">
                                <button class="btn btn-merge" onclick="resolveConflict(${conflict.id}, 'merged')">
                                    Apply Merged Value
                                </button>
                                <button class="btn btn-secondary" onclick="hideMergeEditor(${conflict.id})">
                                    Cancel
                                </button>
                            </div>
                        </div>
                    ` : `
                        <div class="conflict-meta">
                            Resolved: ${conflict.status.replace('resolved_', '')}
                            ${conflict.resolved_by_name ? `by ${conflict.resolved_by_name}` : ''}
                            ${conflict.resolved_at ? `at ${formatDate(conflict.resolved_at)}` : ''}
                        </div>
                    `}
                </div>
            `).join('');

            // Add checkbox event listeners
            document.querySelectorAll('.conflict-checkbox').forEach(cb => {
                cb.addEventListener('change', updateSelection);
            });
        }

        function updateSelection() {
            selectedIds.clear();
            document.querySelectorAll('.conflict-checkbox:checked').forEach(cb => {
                selectedIds.add(parseInt(cb.dataset.id));
            });
            document.getElementById('selectedCount').textContent = `${selectedIds.size} selected`;
        }

        document.getElementById('selectAll').addEventListener('change', function() {
            document.querySelectorAll('.conflict-checkbox').forEach(cb => {
                cb.checked = this.checked;
            });
            updateSelection();
        });

        function showMergeEditor(id) {
            document.getElementById(`merge-${id}`).classList.add('visible');
        }

        function hideMergeEditor(id) {
            document.getElementById(`merge-${id}`).classList.remove('visible');
        }

        async function resolveConflict(id, resolution) {
            const body = { id, resolution };

            if (resolution === 'merged') {
                body.merged_value = document.getElementById(`merge-value-${id}`).value;
            }

            try {
                const response = await fetch('conflicts_api.php?action=resolve', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(body)
                });
                const data = await response.json();

                if (data.success) {
                    loadConflicts(currentStatus);
                } else {
                    alert('Error: ' + data.error);
                }
            } catch (error) {
                console.error('Error resolving conflict:', error);
                alert('Error resolving conflict');
            }
        }

        async function batchResolve(resolution) {
            if (selectedIds.size === 0) {
                alert('No conflicts selected');
                return;
            }

            if (!confirm(`Resolve ${selectedIds.size} conflicts with "${resolution}" value?`)) {
                return;
            }

            try {
                const response = await fetch('conflicts_api.php?action=batch_resolve', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        ids: Array.from(selectedIds),
                        resolution
                    })
                });
                const data = await response.json();

                if (data.success) {
                    alert(`Resolved ${data.resolved} conflicts`);
                    selectedIds.clear();
                    loadConflicts(currentStatus);
                } else {
                    alert('Error: ' + data.error);
                }
            } catch (error) {
                console.error('Error batch resolving:', error);
                alert('Error batch resolving conflicts');
            }
        }

        function formatDate(dateStr) {
            if (!dateStr) return '';
            const date = new Date(dateStr);
            return date.toLocaleDateString() + ' ' + date.toLocaleTimeString();
        }

        function escapeHtml(str) {
            if (!str) return '';
            return str.replace(/&/g, '&amp;')
                      .replace(/</g, '&lt;')
                      .replace(/>/g, '&gt;')
                      .replace(/"/g, '&quot;');
        }

        // Load on page load
        loadConflicts();
    </script>
</body>
</html>

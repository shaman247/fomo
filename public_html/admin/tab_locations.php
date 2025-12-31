<?php
/**
 * Locations Tab
 *
 * Displays all locations with associated website and event counts.
 */

require_once 'db_config.php';

// Get filter/sort parameters
$sort_by = $_GET['sort'] ?? 'name';
$sort_dir = $_GET['dir'] ?? 'asc';
$filter_type = $_GET['type'] ?? 'all';
$current_page = max(1, intval($_GET['page'] ?? 1));

// Build query
$query = "
    SELECT
        l.id,
        l.name,
        l.lat,
        l.lng,
        l.address,
        l.emoji,
        l.created_at,
        (SELECT COUNT(*) FROM website_locations wl WHERE wl.location_id = l.id) as website_count,
        (SELECT COUNT(DISTINCT ce.id)
         FROM crawl_events ce
         JOIN crawl_results cr ON ce.crawl_result_id = cr.id
         JOIN website_locations wl ON cr.website_id = wl.website_id
         WHERE wl.location_id = l.id
         AND cr.status = 'processed') as event_count,
        (SELECT COUNT(DISTINCT ce.id)
         FROM crawl_events ce
         JOIN crawl_results cr ON ce.crawl_result_id = cr.id
         JOIN website_locations wl ON cr.website_id = wl.website_id
         JOIN crawl_runs crun ON cr.crawl_run_id = crun.id
         WHERE wl.location_id = l.id
         AND cr.status = 'processed'
         AND crun.run_date >= DATE_SUB(CURDATE(), INTERVAL 7 DAY)) as events_7d
    FROM locations l
    WHERE 1=1
";

if ($filter_type === 'with_coords') {
    $query .= " AND l.lat IS NOT NULL AND l.lng IS NOT NULL";
} elseif ($filter_type === 'no_coords') {
    $query .= " AND (l.lat IS NULL OR l.lng IS NULL)";
}

// Sort
$valid_sorts = ['id', 'name', 'website_count', 'event_count', 'events_7d', 'created_at'];
$sort_column = in_array($sort_by, $valid_sorts) ? $sort_by : 'name';
$sort_direction = strtoupper($sort_dir) === 'DESC' ? 'DESC' : 'ASC';

// Get total count for pagination
$count_where = "";
if ($filter_type === 'with_coords') {
    $count_where = " WHERE lat IS NOT NULL AND lng IS NOT NULL";
} elseif ($filter_type === 'no_coords') {
    $count_where = " WHERE (lat IS NULL OR lng IS NULL)";
}
$total_count = $pdo->query("SELECT COUNT(*) FROM locations" . $count_where)->fetchColumn();
$pagination = getPagination($total_count, $current_page);

$query .= " ORDER BY $sort_column $sort_direction";
$query .= " LIMIT " . $pagination['limit'] . " OFFSET " . $pagination['offset'];

$locations = $pdo->query($query)->fetchAll(PDO::FETCH_ASSOC);

// Get stats
$stats = $pdo->query("
    SELECT
        COUNT(*) as total,
        SUM(CASE WHEN lat IS NOT NULL AND lng IS NOT NULL THEN 1 ELSE 0 END) as with_coords,
        SUM(CASE WHEN lat IS NULL OR lng IS NULL THEN 1 ELSE 0 END) as no_coords
    FROM locations
")->fetch(PDO::FETCH_ASSOC);

// Create lookup for JSON
$locations_json = [];
foreach ($locations as $l) {
    $locations_json[$l['id']] = $l;
}

// Sort link helper
function sortLink($column, $label, $current_sort, $current_dir) {
    $new_dir = ($current_sort === $column && $current_dir === 'asc') ? 'desc' : 'asc';
    $arrow = '';
    if ($current_sort === $column) {
        $arrow = $current_dir === 'asc' ? ' ↑' : ' ↓';
    }
    $params = $_GET;
    $params['sort'] = $column;
    $params['dir'] = $new_dir;
    return '<a href="?' . http_build_query($params) . '">' . htmlspecialchars($label) . $arrow . '</a>';
}
?>
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&display=swap" rel="stylesheet">
    <style>
        :root {
            --primary-bg: #171717;
            --secondary-bg: #222;
            --tertiary-bg: #373737;
            --tertiary-hover-bg: #444;
            --primary-text: #ddd;
            --secondary-text: #999;
            --accent-color: #74b3a5;
            --accent-hover: #bcf4e8;
            --border-color: #444;
            --success: #74b3a5;
            --warning: #f1c160;
            --danger: #c8535b;
            --info: #6b9bd1;
        }

        * { box-sizing: border-box; margin: 0; padding: 0; }

        body {
            font-family: 'Inter', -apple-system, sans-serif;
            background: var(--primary-bg);
            color: var(--primary-text);
            font-size: 13px;
            line-height: 1.4;
        }

        .layout { display: flex; height: 100vh; }
        .main { flex: 1; display: flex; flex-direction: column; overflow: hidden; }

        .toolbar {
            background: var(--secondary-bg);
            padding: 8px 16px;
            border-bottom: 1px solid var(--border-color);
            display: flex;
            align-items: center;
            gap: 12px;
            flex-shrink: 0;
        }

        .stats { display: flex; gap: 8px; }

        .stat {
            display: flex;
            align-items: center;
            gap: 6px;
            padding: 4px 10px;
            background: var(--tertiary-bg);
            border-radius: 4px;
            font-size: 12px;
            cursor: pointer;
            text-decoration: none;
            color: inherit;
            transition: background 0.15s;
        }

        .stat:hover { background: var(--tertiary-hover-bg); }
        .stat.active { background: var(--accent-color); color: #000; }
        .stat .num { font-weight: 600; }

        .search {
            background: var(--tertiary-bg);
            border: 1px solid var(--border-color);
            border-radius: 4px;
            padding: 6px 10px;
            color: var(--primary-text);
            font-size: 12px;
            width: 180px;
        }

        .search:focus { outline: none; border-color: var(--accent-color); }

        .muted { color: var(--secondary-text); }
        .table-wrap { flex: 1; overflow: auto; }

        table { width: 100%; border-collapse: collapse; }

        th, td {
            padding: 6px 10px;
            text-align: left;
            border-bottom: 1px solid var(--border-color);
            white-space: nowrap;
        }

        th {
            background: var(--secondary-bg);
            font-weight: 500;
            color: var(--secondary-text);
            font-size: 11px;
            text-transform: uppercase;
            letter-spacing: 0.5px;
            position: sticky;
            top: 0;
            z-index: 10;
        }

        th a { color: inherit; text-decoration: none; }
        th a:hover { color: var(--accent-color); }

        tr { cursor: pointer; transition: background 0.1s; }
        tr:hover { background: var(--tertiary-bg); }
        tr.selected { background: #2a3a35; }

        .name { font-weight: 500; }
        .right { text-align: right; }
        .coords { font-family: monospace; font-size: 11px; }

        .detail-panel {
            width: 400px;
            background: var(--secondary-bg);
            border-left: 1px solid var(--border-color);
            display: none;
            flex-direction: column;
            overflow: hidden;
        }

        .detail-panel.open { display: flex; }

        .detail-header {
            padding: 12px 16px;
            border-bottom: 1px solid var(--border-color);
            display: flex;
            align-items: center;
            justify-content: space-between;
        }

        .detail-header h2 { font-size: 14px; font-weight: 600; }

        .close-btn {
            background: none;
            border: none;
            color: var(--secondary-text);
            font-size: 18px;
            cursor: pointer;
            padding: 4px 8px;
        }

        .close-btn:hover { color: var(--primary-text); }

        .detail-content { flex: 1; overflow-y: auto; padding: 16px; }
        .detail-section { margin-bottom: 20px; }

        .detail-section h3 {
            font-size: 11px;
            text-transform: uppercase;
            color: var(--secondary-text);
            margin-bottom: 8px;
            letter-spacing: 0.5px;
        }

        .detail-grid {
            display: grid;
            grid-template-columns: 100px 1fr;
            gap: 6px 12px;
            font-size: 12px;
        }

        .detail-grid dt { color: var(--secondary-text); }
        .detail-grid dd { color: var(--primary-text); word-break: break-word; }

        .item-list { list-style: none; font-size: 12px; }
        .item-list li { padding: 4px 0; border-bottom: 1px solid var(--border-color); }
        .item-list a { color: var(--accent-color); text-decoration: none; }
        .item-list a:hover { color: var(--accent-hover); }

        .pagination {
            display: flex;
            align-items: center;
            gap: 8px;
            font-size: 12px;
        }

        .page-link {
            color: var(--accent-color);
            text-decoration: none;
            padding: 4px 8px;
            background: var(--tertiary-bg);
            border-radius: 3px;
        }

        .page-link:hover {
            background: var(--tertiary-hover-bg);
            color: var(--accent-hover);
        }

        .page-info {
            color: var(--secondary-text);
        }
    </style>
</head>
<body>
    <div class="layout">
        <div class="main">
            <div class="toolbar">
                <div class="stats">
                    <a href="?tab=locations&type=all" class="stat <?= $filter_type === 'all' ? 'active' : '' ?>">
                        <span class="num"><?= $stats['total'] ?></span> total
                    </a>
                    <a href="?tab=locations&type=with_coords" class="stat <?= $filter_type === 'with_coords' ? 'active' : '' ?>">
                        <span class="num"><?= $stats['with_coords'] ?></span> mapped
                    </a>
                    <a href="?tab=locations&type=no_coords" class="stat <?= $filter_type === 'no_coords' ? 'active' : '' ?>">
                        <span class="num"><?= $stats['no_coords'] ?></span> unmapped
                    </a>
                </div>
                <input type="text" class="search" id="search" placeholder="Search..." onkeyup="filterTable()">
                <?= renderPagination($pagination, count($locations)) ?>
            </div>

            <div class="table-wrap">
                <table id="locations-table">
                    <thead>
                        <tr>
                            <th><?= sortLink('id', '#', $sort_by, $sort_dir) ?></th>
                            <th></th>
                            <th><?= sortLink('name', 'Name', $sort_by, $sort_dir) ?></th>
                            <th>Address</th>
                            <th>Coordinates</th>
                            <th class="right"><?= sortLink('website_count', 'Sites', $sort_by, $sort_dir) ?></th>
                            <th class="right"><?= sortLink('event_count', 'Events', $sort_by, $sort_dir) ?></th>
                            <th class="right"><?= sortLink('events_7d', '7d', $sort_by, $sort_dir) ?></th>
                        </tr>
                    </thead>
                    <tbody>
                        <?php foreach ($locations as $l): ?>
                        <tr data-id="<?= $l['id'] ?>" data-name="<?= strtolower(h($l['name'])) ?>" onclick="selectLocation(<?= $l['id'] ?>)">
                            <td class="muted"><?= $l['id'] ?></td>
                            <td><?= $l['emoji'] ?? '' ?></td>
                            <td class="name"><?= h($l['name']) ?></td>
                            <td class="muted" style="max-width:200px;overflow:hidden;text-overflow:ellipsis;" title="<?= h($l['address'] ?? '') ?>"><?= h($l['address'] ?? '-') ?></td>
                            <td class="coords muted">
                                <?php if ($l['lat'] && $l['lng']): ?>
                                    <?= round($l['lat'], 4) ?>, <?= round($l['lng'], 4) ?>
                                <?php else: ?>
                                    -
                                <?php endif; ?>
                            </td>
                            <td class="right"><?= $l['website_count'] ?: '-' ?></td>
                            <td class="right"><?= $l['event_count'] ?: '-' ?></td>
                            <td class="right muted"><?= $l['events_7d'] ?: '-' ?></td>
                        </tr>
                        <?php endforeach; ?>
                    </tbody>
                </table>
            </div>
        </div>

        <div class="detail-panel" id="detail-panel">
            <div class="detail-header">
                <h2 id="detail-name">-</h2>
                <button class="close-btn" onclick="closePanel()">&times;</button>
            </div>
            <div class="detail-content" id="detail-content"></div>
        </div>
    </div>

    <script>
        const locationsData = <?= json_encode($locations_json, JSON_HEX_TAG | JSON_HEX_AMP) ?>;
        let selectedId = null;

        function selectLocation(id) {
            document.querySelectorAll('tr.selected').forEach(tr => tr.classList.remove('selected'));
            document.querySelector(`tr[data-id="${id}"]`)?.classList.add('selected');
            selectedId = id;

            const l = locationsData[id];
            if (!l) return;

            document.getElementById('detail-name').textContent = l.name;
            document.getElementById('detail-panel').classList.add('open');

            fetch(`locations_detail.php?id=${id}`)
                .then(r => r.text())
                .then(html => {
                    document.getElementById('detail-content').innerHTML = html;
                });
        }

        function closePanel() {
            document.getElementById('detail-panel').classList.remove('open');
            document.querySelectorAll('tr.selected').forEach(tr => tr.classList.remove('selected'));
            selectedId = null;
        }

        function filterTable() {
            const searchText = document.getElementById('search').value.toLowerCase();
            document.querySelectorAll('#locations-table tbody tr').forEach(row => {
                const name = row.getAttribute('data-name');
                row.style.display = name.includes(searchText) ? '' : 'none';
            });
        }

        document.addEventListener('keydown', e => {
            if (e.key === 'Escape') closePanel();
        });
    </script>
</body>
</html>

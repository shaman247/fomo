<?php
/**
 * Events Tab
 *
 * Displays final processed events with filtering by date, location, and tags.
 */

require_once 'db_config.php';

// Get filter/sort parameters
$sort_by = $_GET['sort'] ?? 'start_date';
$sort_dir = $_GET['dir'] ?? 'desc';
$filter_period = $_GET['period'] ?? 'upcoming';
$filter_location = $_GET['location'] ?? '';
$current_page = max(1, intval($_GET['page'] ?? 1));

// Build query - join with event_occurrences for dates, get first matching occurrence per event
$query = "
    SELECT
        e.id,
        e.name,
        e.short_name,
        e.description,
        e.emoji,
        e.location_id,
        e.location_name as event_location_name,
        e.sublocation,
        e.website_id,
        MIN(eo.start_date) as start_date,
        MIN(eo.end_date) as end_date,
        MIN(eo.start_time) as start_time,
        MIN(eo.end_time) as end_time,
        w.name as website_name,
        l.name as location_name,
        (SELECT GROUP_CONCAT(t.name SEPARATOR ', ')
         FROM event_tags et
         JOIN tags t ON et.tag_id = t.id
         WHERE et.event_id = e.id) as tags,
        (SELECT COUNT(*) FROM event_sources es WHERE es.event_id = e.id) as source_count,
        (SELECT COUNT(*) FROM event_occurrences eo2 WHERE eo2.event_id = e.id) as occurrence_count
    FROM events e
    LEFT JOIN event_occurrences eo ON e.id = eo.event_id
    LEFT JOIN websites w ON e.website_id = w.id
    LEFT JOIN locations l ON e.location_id = l.id
    WHERE 1=1
";

// Period filter
if ($filter_period === 'upcoming') {
    $query .= " AND eo.start_date >= CURDATE()";
} elseif ($filter_period === 'past') {
    $query .= " AND eo.start_date < CURDATE()";
} elseif ($filter_period === 'today') {
    $query .= " AND eo.start_date = CURDATE()";
} elseif ($filter_period === 'week') {
    $query .= " AND eo.start_date BETWEEN CURDATE() AND DATE_ADD(CURDATE(), INTERVAL 7 DAY)";
}

// Location filter
if ($filter_location && is_numeric($filter_location)) {
    $query .= " AND e.location_id = " . intval($filter_location);
}

// Group by event to avoid duplicates from multiple occurrences
$query .= " GROUP BY e.id, e.name, e.short_name, e.description, e.emoji, e.location_id, e.location_name, e.sublocation, e.website_id, w.name, l.name";

// Sort
$valid_sorts = ['id', 'name', 'start_date', 'location_name', 'website_name', 'source_count', 'occurrence_count'];
$sort_column = in_array($sort_by, $valid_sorts) ? $sort_by : 'start_date';
// For grouped queries, use MIN(eo.start_date) alias
if ($sort_column === 'start_date') $sort_column = 'start_date';
if ($sort_column === 'location_name') $sort_column = 'l.name';
if ($sort_column === 'website_name') $sort_column = 'w.name';
$sort_direction = strtoupper($sort_dir) === 'DESC' ? 'DESC' : 'ASC';

// Build count query for pagination - count distinct events, not occurrences
$count_query = "
    SELECT COUNT(DISTINCT e.id)
    FROM events e
    LEFT JOIN event_occurrences eo ON e.id = eo.event_id
    WHERE 1=1
";
if ($filter_period === 'upcoming') {
    $count_query .= " AND eo.start_date >= CURDATE()";
} elseif ($filter_period === 'past') {
    $count_query .= " AND eo.start_date < CURDATE()";
} elseif ($filter_period === 'today') {
    $count_query .= " AND eo.start_date = CURDATE()";
} elseif ($filter_period === 'week') {
    $count_query .= " AND eo.start_date BETWEEN CURDATE() AND DATE_ADD(CURDATE(), INTERVAL 7 DAY)";
}
if ($filter_location && is_numeric($filter_location)) {
    $count_query .= " AND e.location_id = " . intval($filter_location);
}
$total_count = $pdo->query($count_query)->fetchColumn();
$pagination = getPagination($total_count, $current_page);

$query .= " ORDER BY $sort_column $sort_direction";
$query .= " LIMIT " . $pagination['limit'] . " OFFSET " . $pagination['offset'];

$events = $pdo->query($query)->fetchAll(PDO::FETCH_ASSOC);

// Get stats - count distinct events, not occurrences
$stats = $pdo->query("
    SELECT
        (SELECT COUNT(*) FROM events) as total,
        (SELECT COUNT(DISTINCT e.id) FROM events e JOIN event_occurrences eo ON e.id = eo.event_id WHERE eo.start_date >= CURDATE()) as upcoming,
        (SELECT COUNT(DISTINCT e.id) FROM events e JOIN event_occurrences eo ON e.id = eo.event_id WHERE eo.start_date = CURDATE()) as today,
        (SELECT COUNT(DISTINCT e.id) FROM events e JOIN event_occurrences eo ON e.id = eo.event_id WHERE eo.start_date BETWEEN CURDATE() AND DATE_ADD(CURDATE(), INTERVAL 7 DAY)) as week
")->fetch(PDO::FETCH_ASSOC);

// Get locations for dropdown
$locations_list = $pdo->query("
    SELECT l.id, l.name, COUNT(DISTINCT e.id) as event_count
    FROM locations l
    JOIN events e ON l.id = e.location_id
    GROUP BY l.id, l.name
    ORDER BY l.name
")->fetchAll(PDO::FETCH_ASSOC);

// Create lookup for JSON
$events_json = [];
foreach ($events as $e) {
    $events_json[$e['id']] = $e;
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

function formatDate($date) {
    if (!$date) return '-';
    $dt = new DateTime($date);
    $today = new DateTime('today');
    $diff = $today->diff($dt)->days;
    if ($dt->format('Y-m-d') === $today->format('Y-m-d')) return 'Today';
    if ($diff === 1 && $dt > $today) return 'Tomorrow';
    if ($diff <= 6 && $dt > $today) return $dt->format('D');
    return $dt->format('M j');
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

        select {
            background: var(--tertiary-bg);
            border: 1px solid var(--border-color);
            border-radius: 4px;
            padding: 6px 8px;
            color: var(--primary-text);
            font-size: 12px;
        }

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

        .name { font-weight: 500; max-width: 300px; overflow: hidden; text-overflow: ellipsis; }
        .right { text-align: right; }

        .tag {
            display: inline-block;
            padding: 1px 5px;
            background: var(--tertiary-bg);
            border-radius: 3px;
            font-size: 10px;
            margin-right: 3px;
        }

        .badge-free {
            background: rgba(116,179,165,0.2);
            color: var(--success);
        }

        .detail-panel {
            width: 450px;
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

        .event-link {
            color: var(--accent-color);
            text-decoration: none;
        }

        .event-link:hover { color: var(--accent-hover); }

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
                    <a href="?tab=events&period=upcoming" class="stat <?= $filter_period === 'upcoming' ? 'active' : '' ?>">
                        <span class="num"><?= number_format($stats['upcoming'] ?? 0) ?></span> upcoming
                    </a>
                    <a href="?tab=events&period=today" class="stat <?= $filter_period === 'today' ? 'active' : '' ?>">
                        <span class="num"><?= $stats['today'] ?? 0 ?></span> today
                    </a>
                    <a href="?tab=events&period=week" class="stat <?= $filter_period === 'week' ? 'active' : '' ?>">
                        <span class="num"><?= $stats['week'] ?? 0 ?></span> this week
                    </a>
                    <a href="?tab=events&period=all" class="stat <?= $filter_period === 'all' ? 'active' : '' ?>">
                        <span class="num"><?= number_format($stats['total'] ?? 0) ?></span> all
                    </a>
                </div>
                <input type="text" class="search" id="search" placeholder="Search..." onkeyup="filterTable()">
                <select id="location-filter" onchange="applyFilters()">
                    <option value="">All Locations</option>
                    <?php foreach ($locations_list as $loc): ?>
                    <option value="<?= $loc['id'] ?>" <?= $filter_location == $loc['id'] ? 'selected' : '' ?>>
                        <?= h($loc['name']) ?> (<?= $loc['event_count'] ?>)
                    </option>
                    <?php endforeach; ?>
                </select>
                <?= renderPagination($pagination, count($events)) ?>
            </div>

            <div class="table-wrap">
                <table id="events-table">
                    <thead>
                        <tr>
                            <th><?= sortLink('id', '#', $sort_by, $sort_dir) ?></th>
                            <th></th>
                            <th><?= sortLink('name', 'Event', $sort_by, $sort_dir) ?></th>
                            <th><?= sortLink('start_date', 'Date', $sort_by, $sort_dir) ?></th>
                            <th>Time</th>
                            <th><?= sortLink('location_name', 'Location', $sort_by, $sort_dir) ?></th>
                            <th><?= sortLink('website_name', 'Source', $sort_by, $sort_dir) ?></th>
                            <th class="right"><?= sortLink('occurrence_count', 'Dates', $sort_by, $sort_dir) ?></th>
                            <th>Tags</th>
                        </tr>
                    </thead>
                    <tbody>
                        <?php foreach ($events as $e): ?>
                        <tr data-id="<?= $e['id'] ?>" data-name="<?= strtolower(h($e['name'])) ?>" onclick="selectEvent(<?= $e['id'] ?>)">
                            <td class="muted"><?= $e['id'] ?></td>
                            <td><?= $e['emoji'] ?? '' ?></td>
                            <td class="name" title="<?= h($e['name']) ?>"><?= h($e['name']) ?></td>
                            <td><?= formatDate($e['start_date']) ?></td>
                            <td class="muted"><?= $e['start_time'] ? h($e['start_time']) : '-' ?></td>
                            <td><?= h($e['location_name'] ?? $e['event_location_name'] ?? '-') ?></td>
                            <td class="muted"><?= h($e['website_name'] ?? '-') ?></td>
                            <td class="right muted"><?= $e['occurrence_count'] > 1 ? $e['occurrence_count'] : '-' ?></td>
                            <td>
                                <?php if ($e['tags']): ?>
                                    <?php foreach (array_slice(explode(', ', $e['tags']), 0, 3) as $tag): ?>
                                        <span class="tag"><?= h($tag) ?></span>
                                    <?php endforeach; ?>
                                <?php else: ?>
                                    <span class="muted">-</span>
                                <?php endif; ?>
                            </td>
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
        const eventsData = <?= json_encode($events_json, JSON_HEX_TAG | JSON_HEX_AMP) ?>;
        let selectedId = null;

        function selectEvent(id) {
            document.querySelectorAll('tr.selected').forEach(tr => tr.classList.remove('selected'));
            document.querySelector(`tr[data-id="${id}"]`)?.classList.add('selected');
            selectedId = id;

            const e = eventsData[id];
            if (!e) return;

            document.getElementById('detail-name').textContent = e.name;
            document.getElementById('detail-panel').classList.add('open');

            fetch(`events_detail.php?id=${id}`)
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
            document.querySelectorAll('#events-table tbody tr').forEach(row => {
                const name = row.getAttribute('data-name');
                row.style.display = name.includes(searchText) ? '' : 'none';
            });
        }

        function applyFilters() {
            const location = document.getElementById('location-filter').value;
            const params = new URLSearchParams(window.location.search);
            if (location) {
                params.set('location', location);
            } else {
                params.delete('location');
            }
            window.location.search = params.toString();
        }

        document.addEventListener('keydown', e => {
            if (e.key === 'Escape') closePanel();
        });
    </script>
</body>
</html>

<?php
/**
 * Tags Tab
 *
 * Displays all unique tags with event counts and usage statistics.
 */

require_once 'db_config.php';

// Get filter/sort parameters
$sort_by = $_GET['sort'] ?? 'event_count';
$sort_dir = $_GET['dir'] ?? 'desc';
$filter_min = $_GET['min'] ?? '1';
$current_page = max(1, intval($_GET['page'] ?? 1));

// Build query
$query = "
    SELECT
        cet.tag,
        COUNT(DISTINCT cet.crawl_event_id) as event_count,
        COUNT(DISTINCT ce.crawl_result_id) as website_count,
        MIN(ceo.start_date) as first_event,
        MAX(ceo.start_date) as last_event,
        SUM(CASE WHEN ceo.start_date >= CURDATE() THEN 1 ELSE 0 END) as upcoming_count,
        (SELECT GROUP_CONCAT(DISTINCT l.name SEPARATOR ', ')
         FROM crawl_event_tags cet2
         JOIN crawl_events ce2 ON cet2.crawl_event_id = ce2.id
         JOIN crawl_results cr2 ON ce2.crawl_result_id = cr2.id
         JOIN website_locations wl2 ON cr2.website_id = wl2.website_id
         JOIN locations l ON wl2.location_id = l.id
         WHERE cet2.tag = cet.tag
         LIMIT 5) as locations
    FROM crawl_event_tags cet
    JOIN crawl_events ce ON cet.crawl_event_id = ce.id
    JOIN crawl_results cr ON ce.crawl_result_id = cr.id
    LEFT JOIN crawl_event_occurrences ceo ON ce.id = ceo.crawl_event_id
    WHERE cr.status = 'processed'
    GROUP BY cet.tag
";

// Min events filter
if (is_numeric($filter_min) && $filter_min > 1) {
    $query .= " HAVING event_count >= " . intval($filter_min);
}

// Sort
$valid_sorts = ['tag', 'event_count', 'upcoming_count', 'website_count', 'first_event', 'last_event'];
$sort_column = in_array($sort_by, $valid_sorts) ? $sort_by : 'event_count';
$sort_direction = strtoupper($sort_dir) === 'DESC' ? 'DESC' : 'ASC';

// Get total count for pagination
$count_query = "
    SELECT COUNT(DISTINCT cet.tag)
    FROM crawl_event_tags cet
    JOIN crawl_events ce ON cet.crawl_event_id = ce.id
    JOIN crawl_results cr ON ce.crawl_result_id = cr.id
    WHERE cr.status = 'processed'
";
$total_count = $pdo->query($count_query)->fetchColumn();
$pagination = getPagination($total_count, $current_page);

$query .= " ORDER BY $sort_column $sort_direction";
$query .= " LIMIT " . $pagination['limit'] . " OFFSET " . $pagination['offset'];

$tags = $pdo->query($query)->fetchAll(PDO::FETCH_ASSOC);

// Get stats
$stats = $pdo->query("
    SELECT
        COUNT(DISTINCT tag) as total_tags,
        COUNT(*) as total_uses,
        (SELECT COUNT(DISTINCT cet.tag)
         FROM crawl_event_tags cet
         JOIN crawl_events ce ON cet.crawl_event_id = ce.id
         JOIN crawl_event_occurrences ceo ON ce.id = ceo.crawl_event_id
         WHERE ceo.start_date >= CURDATE()) as active_tags
    FROM crawl_event_tags
")->fetch(PDO::FETCH_ASSOC);

// Create lookup for JSON
$tags_json = [];
foreach ($tags as $t) {
    $tags_json[$t['tag']] = $t;
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
        }

        .stat .num { font-weight: 600; color: var(--accent-color); }

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

        .name { font-weight: 500; }
        .right { text-align: right; }

        .tag-badge {
            display: inline-block;
            padding: 2px 8px;
            background: var(--tertiary-bg);
            border-radius: 3px;
            font-size: 12px;
        }

        .bar {
            height: 6px;
            background: var(--tertiary-bg);
            border-radius: 3px;
            width: 80px;
            display: inline-block;
            overflow: hidden;
        }

        .bar-fill {
            height: 100%;
            background: var(--accent-color);
        }

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

        .event-list { list-style: none; font-size: 12px; }
        .event-list li { padding: 6px 0; border-bottom: 1px solid var(--border-color); }
        .event-list .date { color: var(--secondary-text); font-size: 11px; }

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
                    <div class="stat">
                        <span class="num"><?= number_format($stats['total_tags']) ?></span> unique tags
                    </div>
                    <div class="stat">
                        <span class="num"><?= number_format($stats['active_tags']) ?></span> active
                    </div>
                    <div class="stat">
                        <span class="num"><?= number_format($stats['total_uses']) ?></span> total uses
                    </div>
                </div>
                <input type="text" class="search" id="search" placeholder="Search tags..." onkeyup="filterTable()">
                <select id="min-filter" onchange="applyFilters()">
                    <option value="1" <?= $filter_min == '1' ? 'selected' : '' ?>>Min 1 event</option>
                    <option value="5" <?= $filter_min == '5' ? 'selected' : '' ?>>Min 5 events</option>
                    <option value="10" <?= $filter_min == '10' ? 'selected' : '' ?>>Min 10 events</option>
                    <option value="25" <?= $filter_min == '25' ? 'selected' : '' ?>>Min 25 events</option>
                </select>
                <?= renderPagination($pagination, count($tags)) ?>
            </div>

            <div class="table-wrap">
                <table id="tags-table">
                    <thead>
                        <tr>
                            <th><?= sortLink('tag', 'Tag', $sort_by, $sort_dir) ?></th>
                            <th class="right"><?= sortLink('event_count', 'Events', $sort_by, $sort_dir) ?></th>
                            <th class="right"><?= sortLink('upcoming_count', 'Upcoming', $sort_by, $sort_dir) ?></th>
                            <th class="right"><?= sortLink('website_count', 'Sources', $sort_by, $sort_dir) ?></th>
                            <th>Usage</th>
                            <th><?= sortLink('first_event', 'First', $sort_by, $sort_dir) ?></th>
                            <th><?= sortLink('last_event', 'Last', $sort_by, $sort_dir) ?></th>
                            <th>Locations</th>
                        </tr>
                    </thead>
                    <tbody>
                        <?php
                        $max_events = max(array_column($tags, 'event_count') ?: [1]);
                        foreach ($tags as $t):
                            $pct = ($t['event_count'] / $max_events) * 100;
                        ?>
                        <tr data-tag="<?= strtolower(h($t['tag'])) ?>" onclick="selectTag('<?= h(addslashes($t['tag'])) ?>')">
                            <td><span class="tag-badge"><?= h($t['tag']) ?></span></td>
                            <td class="right"><?= number_format($t['event_count']) ?></td>
                            <td class="right"><?= $t['upcoming_count'] ?: '-' ?></td>
                            <td class="right muted"><?= $t['website_count'] ?></td>
                            <td>
                                <div class="bar">
                                    <div class="bar-fill" style="width: <?= $pct ?>%"></div>
                                </div>
                            </td>
                            <td class="muted"><?= $t['first_event'] ? date('M j, Y', strtotime($t['first_event'])) : '-' ?></td>
                            <td class="muted"><?= $t['last_event'] ? date('M j, Y', strtotime($t['last_event'])) : '-' ?></td>
                            <td class="muted" style="max-width:150px;overflow:hidden;text-overflow:ellipsis;" title="<?= h($t['locations'] ?? '') ?>">
                                <?= h($t['locations'] ?? '-') ?>
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
        const tagsData = <?= json_encode($tags_json, JSON_HEX_TAG | JSON_HEX_AMP) ?>;
        let selectedTag = null;

        function selectTag(tag) {
            document.querySelectorAll('tr.selected').forEach(tr => tr.classList.remove('selected'));
            document.querySelector(`tr[data-tag="${tag.toLowerCase()}"]`)?.classList.add('selected');
            selectedTag = tag;

            document.getElementById('detail-name').textContent = tag;
            document.getElementById('detail-panel').classList.add('open');

            fetch(`tags_detail.php?tag=${encodeURIComponent(tag)}`)
                .then(r => r.text())
                .then(html => {
                    document.getElementById('detail-content').innerHTML = html;
                });
        }

        function closePanel() {
            document.getElementById('detail-panel').classList.remove('open');
            document.querySelectorAll('tr.selected').forEach(tr => tr.classList.remove('selected'));
            selectedTag = null;
        }

        function filterTable() {
            const searchText = document.getElementById('search').value.toLowerCase();
            document.querySelectorAll('#tags-table tbody tr').forEach(row => {
                const tag = row.getAttribute('data-tag');
                row.style.display = tag.includes(searchText) ? '' : 'none';
            });
        }

        function applyFilters() {
            const min = document.getElementById('min-filter').value;
            const params = new URLSearchParams(window.location.search);
            params.set('min', min);
            window.location.search = params.toString();
        }

        document.addEventListener('keydown', e => {
            if (e.key === 'Escape') closePanel();
        });
    </script>
</body>
</html>

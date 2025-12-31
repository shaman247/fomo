<?php
/**
 * Websites Tab
 *
 * Displays all websites with crawl status information.
 */

require_once 'db_config.php';

// Get filter parameters
$filter_status = $_GET['status'] ?? 'all';
$filter_disabled = $_GET['disabled'] ?? 'no';
$sort_by = $_GET['sort'] ?? 'name';
$sort_dir = $_GET['dir'] ?? 'asc';
$current_page = max(1, intval($_GET['page'] ?? 1));

// Build main query
$query = "
    SELECT
        w.id,
        w.name,
        w.crawl_frequency,
        w.disabled,
        w.last_crawled_at,
        w.created_at,
        w.selector,
        w.num_clicks,
        w.keywords,
        w.max_pages,
        w.notes,
        (SELECT COUNT(*) FROM website_urls wu WHERE wu.website_id = w.id) as url_count,
        (SELECT GROUP_CONCAT(l.name SEPARATOR ', ')
         FROM website_locations wl
         JOIN locations l ON wl.location_id = l.id
         WHERE wl.website_id = w.id) as locations,
        cr_latest.id as latest_crawl_id,
        cr_latest.status as latest_crawl_status,
        cr_latest.event_count as latest_event_count,
        cr_latest.error_message as latest_error,
        crun_latest.run_date as latest_run_date,
        (SELECT COUNT(*) FROM crawl_results cr2
         JOIN crawl_runs crun2 ON cr2.crawl_run_id = crun2.id
         WHERE cr2.website_id = w.id
         AND crun2.run_date >= DATE_SUB(CURDATE(), INTERVAL 7 DAY)) as crawls_7d,
        (SELECT COUNT(*) FROM crawl_results cr3
         JOIN crawl_runs crun3 ON cr3.crawl_run_id = crun3.id
         WHERE cr3.website_id = w.id
         AND cr3.status = 'failed'
         AND crun3.run_date >= DATE_SUB(CURDATE(), INTERVAL 7 DAY)) as fails_7d,
        (SELECT SUM(cr4.event_count) FROM crawl_results cr4
         JOIN crawl_runs crun4 ON cr4.crawl_run_id = crun4.id
         WHERE cr4.website_id = w.id
         AND crun4.run_date >= DATE_SUB(CURDATE(), INTERVAL 7 DAY)) as events_7d,
        CASE
            WHEN w.disabled = 1 THEN 'disabled'
            WHEN w.last_crawled_at IS NULL THEN 'never'
            WHEN cr_latest.status = 'failed' THEN 'failed'
            WHEN DATEDIFF(NOW(), w.last_crawled_at) > COALESCE(w.crawl_frequency, 7) THEN 'due'
            ELSE 'ok'
        END as crawl_status
    FROM websites w
    LEFT JOIN crawl_results cr_latest ON cr_latest.id = (
        SELECT cr.id FROM crawl_results cr
        JOIN crawl_runs crun ON cr.crawl_run_id = crun.id
        WHERE cr.website_id = w.id
        ORDER BY crun.run_date DESC
        LIMIT 1
    )
    LEFT JOIN crawl_runs crun_latest ON cr_latest.crawl_run_id = crun_latest.id
    WHERE 1=1
";

$params = [];

if ($filter_disabled === 'yes') {
    $query .= " AND w.disabled = 1";
} elseif ($filter_disabled === 'no') {
    $query .= " AND w.disabled = 0";
}

if ($filter_status === 'due') {
    $query .= " AND w.disabled = 0 AND (w.last_crawled_at IS NULL OR DATEDIFF(NOW(), w.last_crawled_at) > COALESCE(w.crawl_frequency, 7))";
} elseif ($filter_status === 'failed') {
    $query .= " AND cr_latest.status = 'failed'";
} elseif ($filter_status === 'never') {
    $query .= " AND w.last_crawled_at IS NULL";
} elseif ($filter_status === 'ok') {
    $query .= " AND w.disabled = 0 AND w.last_crawled_at IS NOT NULL AND DATEDIFF(NOW(), w.last_crawled_at) <= COALESCE(w.crawl_frequency, 7)";
}

// Sort
$valid_sorts = ['id', 'name', 'last_crawled_at', 'crawl_frequency', 'latest_event_count', 'crawl_status', 'events_7d'];
$sort_column = in_array($sort_by, $valid_sorts) ? $sort_by : 'name';
$sort_direction = strtoupper($sort_dir) === 'DESC' ? 'DESC' : 'ASC';

// Get total count for pagination
$count_query = preg_replace('/SELECT.*?FROM/s', 'SELECT COUNT(*) FROM', $query);
$count_query = preg_replace('/LEFT JOIN crawl_results.*?LEFT JOIN crawl_runs.*?WHERE/s', 'WHERE', $count_query);
$total_count = $pdo->query("SELECT COUNT(*) FROM websites w WHERE 1=1" .
    ($filter_disabled === 'yes' ? " AND w.disabled = 1" : ($filter_disabled === 'no' ? " AND w.disabled = 0" : ""))
)->fetchColumn();

$pagination = getPagination($total_count, $current_page);

$query .= " ORDER BY $sort_column $sort_direction";
$query .= " LIMIT " . $pagination['limit'] . " OFFSET " . $pagination['offset'];

$stmt = $pdo->prepare($query);
$stmt->execute($params);
$websites = $stmt->fetchAll(PDO::FETCH_ASSOC);

// Create websites lookup for JSON
$websites_json = [];
foreach ($websites as $w) {
    $websites_json[$w['id']] = $w;
}

// Get summary stats
$stats_query = "
    SELECT
        COUNT(*) as total,
        SUM(CASE WHEN disabled = 1 THEN 1 ELSE 0 END) as disabled,
        SUM(CASE WHEN disabled = 0 AND last_crawled_at IS NULL THEN 1 ELSE 0 END) as never,
        SUM(CASE WHEN disabled = 0 AND last_crawled_at IS NOT NULL
            AND DATEDIFF(NOW(), last_crawled_at) > COALESCE(crawl_frequency, 7) THEN 1 ELSE 0 END) as due,
        SUM(CASE WHEN disabled = 0 AND last_crawled_at IS NOT NULL
            AND DATEDIFF(NOW(), last_crawled_at) <= COALESCE(crawl_frequency, 7) THEN 1 ELSE 0 END) as ok
    FROM websites
";
$stats = $pdo->query($stats_query)->fetch(PDO::FETCH_ASSOC);

// Count failed
$failed_count = $pdo->query("
    SELECT COUNT(DISTINCT w.id) FROM websites w
    JOIN crawl_results cr ON cr.website_id = w.id
    JOIN crawl_runs crun ON cr.crawl_run_id = crun.id
    WHERE w.disabled = 0
    AND cr.status = 'failed'
    AND cr.id = (SELECT cr2.id FROM crawl_results cr2 JOIN crawl_runs crun2 ON cr2.crawl_run_id = crun2.id WHERE cr2.website_id = w.id ORDER BY crun2.run_date DESC LIMIT 1)
")->fetchColumn();

// Get recent crawl run stats
$recent_runs = $pdo->query("
    SELECT crun.run_date,
           COUNT(cr.id) as total,
           SUM(CASE WHEN cr.status = 'processed' THEN 1 ELSE 0 END) as ok,
           SUM(CASE WHEN cr.status = 'failed' THEN 1 ELSE 0 END) as failed,
           SUM(cr.event_count) as events
    FROM crawl_runs crun
    LEFT JOIN crawl_results cr ON crun.id = cr.crawl_run_id
    WHERE crun.run_date >= DATE_SUB(CURDATE(), INTERVAL 14 DAY)
    GROUP BY crun.run_date
    ORDER BY crun.run_date DESC
")->fetchAll(PDO::FETCH_ASSOC);

// Helper function
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

        .layout {
            display: flex;
            height: 100vh;
        }

        .main {
            flex: 1;
            display: flex;
            flex-direction: column;
            overflow: hidden;
        }

        .toolbar {
            background: var(--secondary-bg);
            padding: 8px 16px;
            border-bottom: 1px solid var(--border-color);
            display: flex;
            align-items: center;
            gap: 12px;
            flex-shrink: 0;
        }

        .stats {
            display: flex;
            gap: 8px;
        }

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
        .stat.ok .num { color: var(--success); }
        .stat.due .num { color: var(--warning); }
        .stat.failed .num { color: var(--danger); }
        .stat.active .num { color: inherit; }

        .search {
            background: var(--tertiary-bg);
            border: 1px solid var(--border-color);
            border-radius: 4px;
            padding: 6px 10px;
            color: var(--primary-text);
            font-size: 12px;
            width: 180px;
        }

        .search:focus {
            outline: none;
            border-color: var(--accent-color);
        }

        select {
            background: var(--tertiary-bg);
            border: 1px solid var(--border-color);
            border-radius: 4px;
            padding: 6px 8px;
            color: var(--primary-text);
            font-size: 12px;
        }

        .muted { color: var(--secondary-text); }

        .runs {
            display: flex;
            gap: 4px;
            margin-left: auto;
        }

        .run {
            text-align: center;
            padding: 4px 8px;
            background: var(--tertiary-bg);
            border-radius: 3px;
            min-width: 50px;
        }

        .run .date { font-size: 10px; color: var(--secondary-text); }
        .run .events { font-size: 13px; font-weight: 600; color: var(--accent-color); }
        .run .meta { font-size: 9px; color: var(--secondary-text); }
        .run .meta .fail { color: var(--danger); }

        .table-wrap {
            flex: 1;
            overflow: auto;
        }

        table {
            width: 100%;
            border-collapse: collapse;
        }

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

        .badge {
            display: inline-block;
            padding: 2px 6px;
            border-radius: 3px;
            font-size: 10px;
            font-weight: 600;
            text-transform: uppercase;
        }

        .badge-ok { background: rgba(116,179,165,0.2); color: var(--success); }
        .badge-due { background: rgba(241,193,96,0.2); color: var(--warning); }
        .badge-never { background: rgba(150,150,150,0.2); color: var(--secondary-text); }
        .badge-failed { background: rgba(200,83,91,0.2); color: var(--danger); }
        .badge-disabled { background: rgba(100,100,100,0.2); color: #777; }
        .badge-processed { background: rgba(116,179,165,0.2); color: var(--success); }
        .badge-crawled { background: rgba(107,155,209,0.2); color: var(--info); }
        .badge-extracted { background: rgba(180,130,200,0.2); color: #b482c8; }

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

        .detail-header h2 {
            font-size: 14px;
            font-weight: 600;
            overflow: hidden;
            text-overflow: ellipsis;
        }

        .close-btn {
            background: none;
            border: none;
            color: var(--secondary-text);
            font-size: 18px;
            cursor: pointer;
            padding: 4px 8px;
        }

        .close-btn:hover { color: var(--primary-text); }

        .detail-content {
            flex: 1;
            overflow-y: auto;
            padding: 16px;
        }

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

        .url-list { list-style: none; font-size: 12px; }
        .url-list li { padding: 4px 0; border-bottom: 1px solid var(--border-color); }
        .url-list a { color: var(--accent-color); text-decoration: none; word-break: break-all; }
        .url-list a:hover { color: var(--accent-hover); }

        .crawl-history { font-size: 12px; }

        .crawl-item {
            display: flex;
            align-items: center;
            gap: 10px;
            padding: 8px 0;
            border-bottom: 1px solid var(--border-color);
        }

        .crawl-item .date { color: var(--secondary-text); min-width: 70px; }
        .crawl-item .events { min-width: 50px; text-align: right; }

        .error-msg {
            background: rgba(200,83,91,0.1);
            border: 1px solid rgba(200,83,91,0.3);
            border-radius: 4px;
            padding: 8px;
            font-size: 11px;
            color: var(--danger);
            word-break: break-word;
        }

        .config-value {
            font-family: monospace;
            background: var(--tertiary-bg);
            padding: 2px 6px;
            border-radius: 3px;
            font-size: 11px;
        }

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
                    <a href="?tab=websites&status=all&disabled=no" class="stat <?= $filter_status === 'all' && $filter_disabled === 'no' ? 'active' : '' ?>">
                        <span class="num"><?= $stats['total'] - $stats['disabled'] ?></span> active
                    </a>
                    <a href="?tab=websites&status=ok&disabled=no" class="stat ok <?= $filter_status === 'ok' ? 'active' : '' ?>">
                        <span class="num"><?= $stats['ok'] ?></span> ok
                    </a>
                    <a href="?tab=websites&status=due&disabled=no" class="stat due <?= $filter_status === 'due' ? 'active' : '' ?>">
                        <span class="num"><?= $stats['due'] + $stats['never'] ?></span> due
                    </a>
                    <a href="?tab=websites&status=failed&disabled=no" class="stat failed <?= $filter_status === 'failed' ? 'active' : '' ?>">
                        <span class="num"><?= $failed_count ?></span> failed
                    </a>
                </div>
                <input type="text" class="search" id="search" placeholder="Search..." onkeyup="filterTable()">
                <select id="disabled-filter" onchange="applyFilters()">
                    <option value="no" <?= $filter_disabled === 'no' ? 'selected' : '' ?>>Active</option>
                    <option value="all" <?= $filter_disabled === 'all' ? 'selected' : '' ?>>All</option>
                    <option value="yes" <?= $filter_disabled === 'yes' ? 'selected' : '' ?>>Disabled</option>
                </select>
                <?= renderPagination($pagination, count($websites)) ?>

                <?php if (!empty($recent_runs)): ?>
                <div class="runs">
                    <?php foreach (array_slice($recent_runs, 0, 7) as $run): ?>
                    <div class="run">
                        <div class="date"><?= date('M j', strtotime($run['run_date'])) ?></div>
                        <div class="events"><?= $run['events'] ?? 0 ?></div>
                        <div class="meta">
                            <?= $run['ok'] ?>
                            <?php if ($run['failed'] > 0): ?>/<span class="fail"><?= $run['failed'] ?></span><?php endif; ?>
                        </div>
                    </div>
                    <?php endforeach; ?>
                </div>
                <?php endif; ?>
            </div>

            <div class="table-wrap">
                <table id="websites-table">
                    <thead>
                        <tr>
                            <th><?= sortLink('id', '#', $sort_by, $sort_dir) ?></th>
                            <th><?= sortLink('name', 'Name', $sort_by, $sort_dir) ?></th>
                            <th>Location</th>
                            <th class="right">URLs</th>
                            <th><?= sortLink('crawl_status', 'Status', $sort_by, $sort_dir) ?></th>
                            <th><?= sortLink('last_crawled_at', 'Last Crawl', $sort_by, $sort_dir) ?></th>
                            <th>Result</th>
                            <th class="right"><?= sortLink('latest_event_count', 'Events', $sort_by, $sort_dir) ?></th>
                            <th class="right"><?= sortLink('events_7d', '7d', $sort_by, $sort_dir) ?></th>
                        </tr>
                    </thead>
                    <tbody>
                        <?php foreach ($websites as $w): ?>
                        <tr data-id="<?= $w['id'] ?>" data-name="<?= strtolower(h($w['name'])) ?>" onclick="selectWebsite(<?= $w['id'] ?>)">
                            <td class="muted"><?= $w['id'] ?></td>
                            <td class="name"><?= h($w['name']) ?></td>
                            <td class="muted" style="max-width:150px;overflow:hidden;text-overflow:ellipsis;" title="<?= h($w['locations'] ?? '') ?>"><?= h($w['locations'] ?? '-') ?></td>
                            <td class="right"><?= $w['url_count'] ?: '-' ?></td>
                            <td>
                                <?php
                                $sc = ['ok'=>'ok','due'=>'due','never'=>'never','failed'=>'failed','disabled'=>'disabled'][$w['crawl_status']] ?? 'never';
                                $sl = ['ok'=>'OK','due'=>'Due','never'=>'Never','failed'=>'Fail','disabled'=>'Off'][$w['crawl_status']] ?? $w['crawl_status'];
                                ?>
                                <span class="badge badge-<?= $sc ?>"><?= $sl ?></span>
                            </td>
                            <td>
                                <?php if ($w['last_crawled_at']): ?>
                                    <?php $d = daysAgo($w['last_crawled_at']); ?>
                                    <?= $d === 0 ? 'Today' : ($d === 1 ? 'Yesterday' : $d . 'd ago') ?>
                                <?php else: ?>
                                    <span class="muted">-</span>
                                <?php endif; ?>
                            </td>
                            <td>
                                <?php if ($w['latest_crawl_status']): ?>
                                    <?php $rc = ['processed'=>'processed','failed'=>'failed','crawled'=>'crawled','extracted'=>'extracted'][$w['latest_crawl_status']] ?? 'never'; ?>
                                    <span class="badge badge-<?= $rc ?>"><?= ucfirst($w['latest_crawl_status']) ?></span>
                                <?php else: ?>
                                    <span class="muted">-</span>
                                <?php endif; ?>
                            </td>
                            <td class="right"><?= $w['latest_event_count'] !== null ? $w['latest_event_count'] : '-' ?></td>
                            <td class="right muted"><?= $w['events_7d'] ?: '-' ?></td>
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
        const websitesData = <?= json_encode($websites_json, JSON_HEX_TAG | JSON_HEX_AMP) ?>;
        let selectedId = null;

        function selectWebsite(id) {
            document.querySelectorAll('tr.selected').forEach(tr => tr.classList.remove('selected'));
            document.querySelector(`tr[data-id="${id}"]`)?.classList.add('selected');
            selectedId = id;

            const w = websitesData[id];
            if (!w) return;

            document.getElementById('detail-name').textContent = w.name;
            document.getElementById('detail-panel').classList.add('open');

            fetch(`websites_detail.php?id=${id}`)
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
            document.querySelectorAll('#websites-table tbody tr').forEach(row => {
                const name = row.getAttribute('data-name');
                row.style.display = name.includes(searchText) ? '' : 'none';
            });
        }

        function applyFilters() {
            const disabled = document.getElementById('disabled-filter').value;
            const params = new URLSearchParams(window.location.search);
            params.set('disabled', disabled);
            window.location.search = params.toString();
        }

        document.addEventListener('keydown', e => {
            if (e.key === 'Escape') closePanel();
        });
    </script>
</body>
</html>

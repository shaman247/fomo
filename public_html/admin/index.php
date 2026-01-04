<?php
/**
 * FOMO Admin Dashboard - Single Page Application
 *
 * Shell page that loads data client-side via api.php
 */

require_once 'db_config.php';

$tab = $_GET['tab'] ?? 'websites';
$valid_tabs = ['websites', 'locations', 'events', 'tags'];
if (!in_array($tab, $valid_tabs)) {
    $tab = 'websites';
}

// Get initial tab counts for header
$counts = [
    'websites' => $pdo->query("SELECT COUNT(*) FROM websites WHERE disabled = 0")->fetchColumn(),
    'locations' => $pdo->query("SELECT COUNT(*) FROM locations")->fetchColumn(),
    'events' => $pdo->query("SELECT COUNT(*) FROM events")->fetchColumn(),
    'tags' => $pdo->query("SELECT COUNT(*) FROM tags t WHERE EXISTS (SELECT 1 FROM event_tags et WHERE et.tag_id = t.id)")->fetchColumn(),
];
?>
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>fomo.nyc Admin Tool</title>
    <link rel="icon" type="image/svg+xml" href="../images/torch.svg">
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&display=swap" rel="stylesheet">
    <link rel="stylesheet" href="admin.css">
</head>
<body>
    <div class="layout">
        <div class="top-bar">
            <div class="logo">fomo</div>
            <div class="tabs" id="tabs">
                <?php foreach ($valid_tabs as $t): ?>
                <a href="javascript:void(0)" onclick="switchTab('<?= $t ?>')" class="tab <?= $tab === $t ? 'active' : '' ?>" data-tab="<?= $t ?>">
                    <?= ucfirst($t) ?> <span class="count" id="count-<?= $t ?>"><?= number_format($counts[$t]) ?></span>
                </a>
                <?php endforeach; ?>
            </div>
        </div>

        <div class="content">
            <div class="main">
                <div class="toolbar" id="toolbar">
                    <span class="muted">Loading...</span>
                </div>

                <div class="table-wrap">
                    <p class="muted" style="padding:20px">Loading...</p>
                </div>
            </div>

            <div class="detail-panel" id="detail-panel">
                <div class="detail-header">
                    <button class="nav-btn disabled" id="detail-back" onclick="detailGoBack()" title="Back (Alt+←)">&lsaquo;</button>
                    <h2 id="detail-title">-</h2>
                    <button class="nav-btn disabled" id="detail-forward" onclick="detailGoForward()" title="Forward (Alt+→)">&rsaquo;</button>
                    <button class="close-btn" onclick="closeDetail()">&times;</button>
                </div>
                <div class="detail-content" id="detail-content">
                    <p class="muted">Select an item to view details</p>
                </div>
            </div>
        </div>
    </div>

    <script>
        window.initialTab = <?= json_encode($tab) ?>;
    </script>
    <script src="admin.js"></script>
</body>
</html>

<?php
/**
 * FOMO Admin Dashboard
 *
 * Tabbed interface for managing websites, locations, events, and tags.
 */

require_once 'db_config.php';

$tab = $_GET['tab'] ?? 'websites';
$valid_tabs = ['websites', 'locations', 'events', 'tags'];
if (!in_array($tab, $valid_tabs)) {
    $tab = 'websites';
}

// Get counts for tabs
$counts = [
    'websites' => $pdo->query("SELECT COUNT(*) FROM websites WHERE disabled = 0")->fetchColumn(),
    'locations' => $pdo->query("SELECT COUNT(*) FROM locations")->fetchColumn(),
    'events' => $pdo->query("SELECT COUNT(*) FROM events")->fetchColumn(),
    'tags' => $pdo->query("SELECT COUNT(DISTINCT tag) FROM crawl_event_tags")->fetchColumn(),
];
?>
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>FOMO Admin</title>
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
            flex-direction: column;
        }

        .top-bar {
            background: var(--secondary-bg);
            padding: 0 16px;
            border-bottom: 1px solid var(--border-color);
            display: flex;
            align-items: center;
            height: 48px;
            flex-shrink: 0;
        }

        .logo {
            font-size: 16px;
            font-weight: 600;
            color: var(--accent-color);
            margin-right: 32px;
        }

        .tabs {
            display: flex;
            gap: 4px;
            height: 100%;
        }

        .tab {
            display: flex;
            align-items: center;
            gap: 6px;
            padding: 0 16px;
            color: var(--secondary-text);
            text-decoration: none;
            border-bottom: 2px solid transparent;
            transition: all 0.15s;
        }

        .tab:hover {
            color: var(--primary-text);
            background: var(--tertiary-bg);
        }

        .tab.active {
            color: var(--accent-color);
            border-bottom-color: var(--accent-color);
        }

        .tab .count {
            background: var(--tertiary-bg);
            padding: 2px 6px;
            border-radius: 10px;
            font-size: 11px;
        }

        .tab.active .count {
            background: rgba(116,179,165,0.2);
        }

        .content {
            flex: 1;
            overflow: hidden;
        }

        .content iframe {
            width: 100%;
            height: 100%;
            border: none;
        }
    </style>
</head>
<body>
    <div class="layout">
        <div class="top-bar">
            <div class="logo">FOMO Admin</div>
            <div class="tabs">
                <a href="?tab=websites" class="tab <?= $tab === 'websites' ? 'active' : '' ?>">
                    Websites <span class="count"><?= number_format($counts['websites']) ?></span>
                </a>
                <a href="?tab=locations" class="tab <?= $tab === 'locations' ? 'active' : '' ?>">
                    Locations <span class="count"><?= number_format($counts['locations']) ?></span>
                </a>
                <a href="?tab=events" class="tab <?= $tab === 'events' ? 'active' : '' ?>">
                    Events <span class="count"><?= number_format($counts['events']) ?></span>
                </a>
                <a href="?tab=tags" class="tab <?= $tab === 'tags' ? 'active' : '' ?>">
                    Tags <span class="count"><?= number_format($counts['tags']) ?></span>
                </a>
            </div>
        </div>
        <div class="content">
            <iframe src="tab_<?= $tab ?>.php?<?= http_build_query($_GET) ?>" id="content-frame"></iframe>
        </div>
    </div>
</body>
</html>

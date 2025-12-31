<?php
/**
 * Database Configuration
 *
 * Shared database connection for all admin pages.
 */

$env = getenv('FOMO_ENV') ?: 'local';

$db_configs = [
    'local' => [
        'host' => 'localhost',
        'database' => 'fomo',
        'user' => 'root',
        'password' => ''
    ],
    'production' => [
        'host' => 'localhost',
        'database' => 'fomoowsq_fomo',
        'user' => 'fomoowsq_root',
        'password' => 'REDACTED_DB_PASSWORD'
    ]
];

$config = $db_configs[$env] ?? $db_configs['local'];

try {
    $pdo = new PDO(
        "mysql:host={$config['host']};dbname={$config['database']};charset=utf8mb4",
        $config['user'],
        $config['password'],
        [PDO::ATTR_ERRMODE => PDO::ERRMODE_EXCEPTION]
    );
} catch (PDOException $e) {
    die("Database connection failed: " . $e->getMessage());
}

// Common helper functions
function h($str) {
    return htmlspecialchars($str ?? '', ENT_QUOTES, 'UTF-8');
}

function daysAgo($date) {
    if (!$date) return null;
    return (new DateTime($date))->diff(new DateTime())->days;
}

function formatBytes($bytes) {
    if (!$bytes) return '-';
    if ($bytes < 1024) return $bytes . ' B';
    if ($bytes < 1048576) return round($bytes / 1024, 1) . ' KB';
    return round($bytes / 1048576, 1) . ' MB';
}

// Pagination constants
define('ROWS_PER_PAGE', 200);

function getPagination($total, $current_page) {
    $total_pages = max(1, ceil($total / ROWS_PER_PAGE));
    $current_page = max(1, min($current_page, $total_pages));
    $offset = ($current_page - 1) * ROWS_PER_PAGE;
    return [
        'total' => $total,
        'total_pages' => $total_pages,
        'current_page' => $current_page,
        'offset' => $offset,
        'limit' => ROWS_PER_PAGE,
        'has_prev' => $current_page > 1,
        'has_next' => $current_page < $total_pages
    ];
}

function renderPagination($pagination, $shown_count) {
    if ($pagination['total_pages'] <= 1) {
        return '<span class="muted">' . number_format($shown_count) . ' shown</span>';
    }

    $params = $_GET;
    $html = '<div class="pagination">';
    $html .= '<span class="muted">' . number_format($shown_count) . ' of ' . number_format($pagination['total']) . '</span>';

    if ($pagination['has_prev']) {
        $params['page'] = $pagination['current_page'] - 1;
        $html .= ' <a href="?' . http_build_query($params) . '" class="page-link">&laquo; Prev</a>';
    }

    $html .= ' <span class="page-info">Page ' . $pagination['current_page'] . ' of ' . $pagination['total_pages'] . '</span>';

    if ($pagination['has_next']) {
        $params['page'] = $pagination['current_page'] + 1;
        $html .= ' <a href="?' . http_build_query($params) . '" class="page-link">Next &raquo;</a>';
    }

    $html .= '</div>';
    return $html;
}

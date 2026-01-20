<?php
/**
 * Database Configuration
 *
 * Shared database connection for all admin pages.
 */

// Auto-detect environment by hostname
$isLocal = in_array($_SERVER['HTTP_HOST'] ?? '', ['localhost', '127.0.0.1'])
        || strpos($_SERVER['HTTP_HOST'] ?? '', 'localhost:') === 0;

if ($isLocal) {
    $config = [
        'host' => 'localhost',
        'database' => 'fomo',
        'user' => 'root',
        'password' => ''
    ];
} else {
    $config = [
        'host' => 'localhost',
        'database' => 'fomoowsq_fomo',
        'user' => 'fomoowsq_root',
        'password' => 'REDACTED_DB_PASSWORD'
    ];
}

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
    // Compare calendar dates, not datetimes, to avoid timezone/time-of-day issues
    $then = (new DateTime($date))->setTime(0, 0, 0);
    $now = (new DateTime())->setTime(0, 0, 0);
    return $then->diff($now)->days;
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

    $html = '<div class="pagination">';
    $html .= '<span class="muted">' . number_format($shown_count) . ' of ' . number_format($pagination['total']) . '</span>';

    if ($pagination['has_prev']) {
        $prev_page = $pagination['current_page'] - 1;
        $html .= ' <a href="javascript:void(0)" onclick="goToPage(' . $prev_page . ')" class="page-link">&laquo; Prev</a>';
    }

    $html .= ' <span class="page-info">Page ' . $pagination['current_page'] . ' of ' . $pagination['total_pages'] . '</span>';

    if ($pagination['has_next']) {
        $next_page = $pagination['current_page'] + 1;
        $html .= ' <a href="javascript:void(0)" onclick="goToPage(' . $next_page . ')" class="page-link">Next &raquo;</a>';
    }

    $html .= '</div>';
    return $html;
}

// Detail page helper functions

function formatShortDate($date) {
    return $date ? date('M j, Y', strtotime($date)) : '-';
}

function formatDateOnly($date) {
    return $date ? date('M j', strtotime($date)) : '-';
}

function formatTime($time) {
    return $time ? date('g:ia', strtotime($time)) : '';
}

function detailLink($type, $id, $name, $text = null, $class = '') {
    $escapedName = h(addslashes($name));
    $displayText = $text ?? h($name);
    $classAttr = $class ? " class=\"$class\"" : '';
    return "<a href=\"javascript:void(0)\" onclick=\"openDetail('$type', " . (is_numeric($id) ? $id : "'$id'") . ", '$escapedName')\"$classAttr>$displayText</a>";
}

function formatOccurrences($occurrencesStr) {
    $occurrences = explode(';;', $occurrencesStr);
    $texts = [];
    foreach ($occurrences as $occ) {
        list($date, $time) = explode('|', $occ);
        $text = formatDateOnly($date);
        if ($time) {
            $text .= ' ' . formatTime($time);
        }
        $texts[] = $text;
    }
    return implode(', ', $texts);
}

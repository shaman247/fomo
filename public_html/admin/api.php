<?php
/**
 * FOMO Admin API - Returns all data for client-side handling
 *
 * Endpoints:
 *   GET api.php?type=websites
 *   GET api.php?type=locations
 *   GET api.php?type=events
 *   GET api.php?type=tags
 */

// Ensure we always return JSON, even on errors
header('Content-Type: application/json');

// Set up error handling to return JSON errors
set_error_handler(function($severity, $message, $file, $line) {
    throw new ErrorException($message, 0, $severity, $file, $line);
});

set_exception_handler(function($e) {
    http_response_code(500);
    echo json_encode([
        'success' => false,
        'error' => $e->getMessage(),
        'file' => $e->getFile(),
        'line' => $e->getLine()
    ]);
    exit;
});

require_once 'db_config.php';

// ============================================================================
// DATA FETCH FUNCTIONS
// ============================================================================

function getWebsites($pdo) {
    $query = "
        SELECT
            w.id, w.name, w.crawl_frequency, w.disabled, w.last_crawled_at,
            (SELECT COUNT(*) FROM website_urls wu WHERE wu.website_id = w.id) as url_count,
            (SELECT GROUP_CONCAT(l.name SEPARATOR ', ')
             FROM website_locations wl JOIN locations l ON wl.location_id = l.id
             WHERE wl.website_id = w.id) as locations,
            cr_latest.status as latest_crawl_status,
            cr_latest.event_count as latest_event_count,
            crun_latest.run_date as latest_run_date,
            (SELECT SUM(cr4.event_count) FROM crawl_results cr4
             JOIN crawl_runs crun4 ON cr4.crawl_run_id = crun4.id
             WHERE cr4.website_id = w.id AND crun4.run_date >= DATE_SUB(CURDATE(), INTERVAL 7 DAY)) as events_7d,
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
            WHERE cr.website_id = w.id ORDER BY crun.run_date DESC LIMIT 1
        )
        LEFT JOIN crawl_runs crun_latest ON cr_latest.crawl_run_id = crun_latest.id
        ORDER BY w.name ASC
    ";

    $rows = $pdo->query($query)->fetchAll(PDO::FETCH_ASSOC);

    // Convert numeric fields
    foreach ($rows as &$row) {
        $row['id'] = (int)$row['id'];
        $row['url_count'] = $row['url_count'] ? (int)$row['url_count'] : null;
        $row['latest_event_count'] = $row['latest_event_count'] ? (int)$row['latest_event_count'] : null;
        $row['events_7d'] = $row['events_7d'] ? (int)$row['events_7d'] : null;
        $row['disabled'] = (bool)$row['disabled'];
    }

    return $rows;
}

function getWebsiteFilters($pdo) {
    $stats = $pdo->query("
        SELECT
            COUNT(*) as total,
            SUM(CASE WHEN disabled = 0 THEN 1 ELSE 0 END) as active,
            SUM(CASE WHEN disabled = 0 AND last_crawled_at IS NOT NULL AND DATEDIFF(NOW(), last_crawled_at) <= COALESCE(crawl_frequency, 7) THEN 1 ELSE 0 END) as ok,
            SUM(CASE WHEN disabled = 0 AND (last_crawled_at IS NULL OR DATEDIFF(NOW(), last_crawled_at) > COALESCE(crawl_frequency, 7)) THEN 1 ELSE 0 END) as due
        FROM websites
    ")->fetch(PDO::FETCH_ASSOC);

    $failed_count = $pdo->query("
        SELECT COUNT(DISTINCT w.id) FROM websites w
        JOIN crawl_results cr ON cr.website_id = w.id
        WHERE w.disabled = 0 AND cr.status = 'failed'
        AND cr.id = (SELECT cr2.id FROM crawl_results cr2 JOIN crawl_runs crun2 ON cr2.crawl_run_id = crun2.id WHERE cr2.website_id = w.id ORDER BY crun2.run_date DESC LIMIT 1)
    ")->fetchColumn();

    return [
        ['key' => 'status', 'value' => 'active', 'label' => 'active', 'count' => (int)$stats['active'], 'default' => true,
         'match' => ['field' => 'disabled', 'op' => '=', 'value' => false]],
        ['key' => 'status', 'value' => 'ok', 'label' => 'ok', 'count' => (int)$stats['ok'], 'class' => 'ok',
         'match' => ['field' => 'crawl_status', 'op' => '=', 'value' => 'ok']],
        ['key' => 'status', 'value' => 'due', 'label' => 'due', 'count' => (int)$stats['due'], 'class' => 'due',
         'match' => ['field' => 'crawl_status', 'op' => 'in', 'value' => ['due', 'never']]],
        ['key' => 'status', 'value' => 'failed', 'label' => 'failed', 'count' => (int)$failed_count, 'class' => 'failed',
         'match' => ['field' => 'crawl_status', 'op' => '=', 'value' => 'failed']],
        ['key' => 'status', 'value' => 'disabled', 'label' => 'disabled', 'count' => (int)$stats['total'] - (int)$stats['active'],
         'match' => ['field' => 'disabled', 'op' => '=', 'value' => true]],
    ];
}

function getLocations($pdo) {
    $query = "
        SELECT
            l.id, l.name, l.lat, l.lng, l.address, l.emoji, l.created_at,
            (SELECT COUNT(*) FROM website_locations wl WHERE wl.location_id = l.id) as website_count,
            (SELECT COUNT(DISTINCT e.id) FROM events e WHERE e.location_id = l.id) as event_count,
            (SELECT COUNT(DISTINCT e.id) FROM events e
             JOIN event_occurrences eo ON e.id = eo.event_id
             WHERE e.location_id = l.id AND eo.start_date >= CURDATE()
             AND eo.start_date <= DATE_ADD(CURDATE(), INTERVAL 7 DAY)) as events_7d
        FROM locations l
        ORDER BY l.name ASC
    ";

    $rows = $pdo->query($query)->fetchAll(PDO::FETCH_ASSOC);

    foreach ($rows as &$row) {
        $row['id'] = (int)$row['id'];
        $row['lat'] = $row['lat'] ? (float)$row['lat'] : null;
        $row['lng'] = $row['lng'] ? (float)$row['lng'] : null;
        $row['website_count'] = (int)$row['website_count'];
        $row['event_count'] = (int)$row['event_count'];
        $row['events_7d'] = (int)$row['events_7d'];
        $row['has_coords'] = $row['lat'] !== null && $row['lng'] !== null;
    }

    return $rows;
}

function getLocationFilters($pdo) {
    $stats = $pdo->query("
        SELECT COUNT(*) as total,
            SUM(CASE WHEN lat IS NOT NULL AND lng IS NOT NULL THEN 1 ELSE 0 END) as with_coords,
            SUM(CASE WHEN lat IS NULL OR lng IS NULL THEN 1 ELSE 0 END) as no_coords
        FROM locations
    ")->fetch(PDO::FETCH_ASSOC);

    return [
        ['key' => 'type', 'value' => 'all', 'label' => 'total', 'count' => (int)$stats['total'], 'default' => true,
         'match' => null],
        ['key' => 'type', 'value' => 'with_coords', 'label' => 'mapped', 'count' => (int)$stats['with_coords'],
         'match' => ['field' => 'has_coords', 'op' => '=', 'value' => true]],
        ['key' => 'type', 'value' => 'no_coords', 'label' => 'unmapped', 'count' => (int)$stats['no_coords'],
         'match' => ['field' => 'has_coords', 'op' => '=', 'value' => false]],
    ];
}

function getEvents($pdo) {
    $query = "
        SELECT
            e.id, e.name, e.emoji, e.location_id, e.location_name as event_location_name,
            e.website_id,
            MIN(CASE WHEN eo.start_date >= CURDATE() THEN eo.start_date END) as next_date,
            MIN(eo.start_date) as start_date,
            (SELECT eo3.start_time FROM event_occurrences eo3 WHERE eo3.event_id = e.id AND eo3.start_date = MIN(CASE WHEN eo.start_date >= CURDATE() THEN eo.start_date END) LIMIT 1) as start_time,
            w.name as website_name, l.name as location_name,
            (SELECT GROUP_CONCAT(t.name SEPARATOR ', ') FROM event_tags et JOIN tags t ON et.tag_id = t.id WHERE et.event_id = e.id) as tags,
            (SELECT COUNT(*) FROM event_occurrences eo2 WHERE eo2.event_id = e.id) as occurrence_count
        FROM events e
        LEFT JOIN event_occurrences eo ON e.id = eo.event_id
        LEFT JOIN websites w ON e.website_id = w.id
        LEFT JOIN locations l ON e.location_id = l.id
        GROUP BY e.id, e.name, e.emoji, e.location_id, e.location_name, e.website_id, w.name, l.name
        ORDER BY MIN(CASE WHEN eo.start_date >= CURDATE() THEN eo.start_date END) ASC, MIN(eo.start_date) ASC
    ";

    $rows = $pdo->query($query)->fetchAll(PDO::FETCH_ASSOC);

    // Categorize events by time period
    $today = date('Y-m-d');
    $weekEnd = date('Y-m-d', strtotime('+7 days'));

    foreach ($rows as &$row) {
        $row['id'] = (int)$row['id'];
        $row['location_id'] = $row['location_id'] ? (int)$row['location_id'] : null;
        $row['website_id'] = $row['website_id'] ? (int)$row['website_id'] : null;
        $row['occurrence_count'] = (int)$row['occurrence_count'];

        // Use next_date for display and filtering (next occurrence from today onward)
        // Fall back to start_date for past events
        $displayDate = $row['next_date'] ?? $row['start_date'];
        $row['start_date'] = $displayDate;

        // Add period classification for filtering based on next upcoming occurrence
        if ($row['next_date']) {
            // Has a future occurrence
            if ($row['next_date'] === $today) {
                $row['period'] = 'today';
            } elseif ($row['next_date'] <= $weekEnd) {
                $row['period'] = 'week';
            } else {
                $row['period'] = 'upcoming';
            }
        } else {
            // No future occurrences - it's in the past
            $row['period'] = 'past';
        }
        unset($row['next_date']);
    }

    return $rows;
}

function getEventFilters($pdo) {
    $stats = $pdo->query("
        SELECT
            (SELECT COUNT(*) FROM events) as total,
            (SELECT COUNT(DISTINCT e.id) FROM events e JOIN event_occurrences eo ON e.id = eo.event_id WHERE eo.start_date >= CURDATE()) as upcoming,
            (SELECT COUNT(DISTINCT e.id) FROM events e JOIN event_occurrences eo ON e.id = eo.event_id WHERE eo.start_date = CURDATE()) as today,
            (SELECT COUNT(DISTINCT e.id) FROM events e JOIN event_occurrences eo ON e.id = eo.event_id WHERE eo.start_date BETWEEN CURDATE() AND DATE_ADD(CURDATE(), INTERVAL 7 DAY)) as week
    ")->fetch(PDO::FETCH_ASSOC);

    return [
        ['key' => 'period', 'value' => 'upcoming', 'label' => 'upcoming', 'count' => (int)$stats['upcoming'], 'default' => true,
         'match' => ['field' => 'period', 'op' => 'in', 'value' => ['today', 'week', 'upcoming']]],
        ['key' => 'period', 'value' => 'today', 'label' => 'today', 'count' => (int)$stats['today'],
         'match' => ['field' => 'period', 'op' => '=', 'value' => 'today']],
        ['key' => 'period', 'value' => 'week', 'label' => 'this week', 'count' => (int)$stats['week'],
         'match' => ['field' => 'period', 'op' => 'in', 'value' => ['today', 'week']]],
        ['key' => 'period', 'value' => 'all', 'label' => 'all', 'count' => (int)$stats['total'],
         'match' => null],
    ];
}

function getTags($pdo) {
    $query = "
        SELECT
            t.id as tag_id, t.name as tag,
            COUNT(DISTINCT et.event_id) as event_count,
            COUNT(DISTINCT e.website_id) as website_count,
            MIN(eo.start_date) as first_event,
            MAX(eo.start_date) as last_event,
            COUNT(DISTINCT CASE WHEN eo.start_date >= CURDATE() THEN et.event_id END) as upcoming_count
        FROM tags t
        JOIN event_tags et ON t.id = et.tag_id
        JOIN events e ON et.event_id = e.id
        LEFT JOIN event_occurrences eo ON e.id = eo.event_id
        GROUP BY t.id, t.name
        ORDER BY COUNT(DISTINCT et.event_id) DESC
    ";

    $rows = $pdo->query($query)->fetchAll(PDO::FETCH_ASSOC);

    // Fetch locations for all tags in one query
    $tag_ids = array_column($rows, 'tag_id');
    $locations_map = [];

    if (!empty($tag_ids)) {
        $placeholders = implode(',', array_fill(0, count($tag_ids), '?'));
        $loc_stmt = $pdo->prepare("
            SELECT et.tag_id, GROUP_CONCAT(DISTINCT l.name ORDER BY l.name SEPARATOR ', ') as locations
            FROM event_tags et
            JOIN events e ON et.event_id = e.id
            JOIN locations l ON e.location_id = l.id
            WHERE et.tag_id IN ($placeholders)
            GROUP BY et.tag_id
        ");
        $loc_stmt->execute($tag_ids);
        $locations_map = $loc_stmt->fetchAll(PDO::FETCH_KEY_PAIR);
    }

    foreach ($rows as &$row) {
        $row['tag_id'] = (int)$row['tag_id'];
        $row['event_count'] = (int)$row['event_count'];
        $row['website_count'] = (int)$row['website_count'];
        $row['upcoming_count'] = (int)$row['upcoming_count'];
        $row['locations'] = $locations_map[$row['tag_id']] ?? null;
    }

    return $rows;
}

function getTagFilters($pdo) {
    $stats = $pdo->query("
        SELECT
            (SELECT COUNT(*) FROM tags t WHERE EXISTS (SELECT 1 FROM event_tags et WHERE et.tag_id = t.id)) as total_tags,
            (SELECT COUNT(*) FROM event_tags) as total_uses,
            (SELECT COUNT(DISTINCT et.tag_id) FROM event_tags et
             WHERE EXISTS (SELECT 1 FROM event_occurrences eo WHERE eo.event_id = et.event_id AND eo.start_date >= CURDATE())) as active_tags
    ")->fetch(PDO::FETCH_ASSOC);

    return [
        ['label' => 'unique tags', 'count' => (int)$stats['total_tags'], 'static' => true],
        ['label' => 'active', 'count' => (int)$stats['active_tags'], 'static' => true],
        ['label' => 'total uses', 'count' => (int)$stats['total_uses'], 'static' => true],
    ];
}

// ============================================================================
// MAIN API LOGIC
// ============================================================================

$type = $_GET['type'] ?? '';

$response = [
    'success' => true,
    'data' => [],
    'columns' => [],
    'filters' => [],
    'stats' => [],
    'counts' => []
];

// Get tab counts for header
$response['counts'] = [
    'websites' => (int)$pdo->query("SELECT COUNT(*) FROM websites WHERE disabled = 0")->fetchColumn(),
    'locations' => (int)$pdo->query("SELECT COUNT(*) FROM locations")->fetchColumn(),
    'events' => (int)$pdo->query("SELECT COUNT(*) FROM events")->fetchColumn(),
    'tags' => (int)$pdo->query("SELECT COUNT(*) FROM tags t WHERE EXISTS (SELECT 1 FROM event_tags et WHERE et.tag_id = t.id)")->fetchColumn(),
];

switch ($type) {
    case 'websites':
        $response['data'] = getWebsites($pdo);
        $response['columns'] = [
            ['key' => 'id', 'label' => '#', 'class' => 'muted', 'sortable' => true],
            ['key' => 'name', 'label' => 'Name', 'class' => 'name', 'sortable' => true],
            ['key' => 'locations', 'label' => 'Location', 'class' => 'muted truncate', 'maxWidth' => '150px'],
            ['key' => 'url_count', 'label' => 'URLs', 'class' => 'right', 'empty' => '-', 'sortable' => true, 'type' => 'number'],
            ['key' => 'crawl_status', 'label' => 'Status', 'type' => 'badge', 'sortable' => true],
            ['key' => 'last_crawled_at', 'label' => 'Last Crawl', 'type' => 'days_ago', 'sortable' => true],
            ['key' => 'latest_crawl_status', 'label' => 'Result', 'type' => 'badge'],
            ['key' => 'latest_event_count', 'label' => 'Events', 'class' => 'right', 'empty' => '-', 'sortable' => true, 'type' => 'number'],
            ['key' => 'events_7d', 'label' => '7d', 'class' => 'right muted', 'empty' => '-', 'sortable' => true, 'type' => 'number'],
        ];
        $response['filters'] = getWebsiteFilters($pdo);
        $response['defaultSort'] = ['key' => 'name', 'dir' => 'asc'];
        $response['idField'] = 'id';
        $response['nameField'] = 'name';
        $response['detailEndpoint'] = 'websites_detail.php';
        break;

    case 'locations':
        $response['data'] = getLocations($pdo);
        $response['columns'] = [
            ['key' => 'id', 'label' => '#', 'class' => 'muted', 'sortable' => true],
            ['key' => 'emoji', 'label' => ''],
            ['key' => 'name', 'label' => 'Name', 'class' => 'name', 'sortable' => true],
            ['key' => 'address', 'label' => 'Address', 'class' => 'muted truncate', 'maxWidth' => '200px', 'empty' => '-'],
            ['key' => 'coords', 'label' => 'Coordinates', 'class' => 'muted coords', 'type' => 'coords'],
            ['key' => 'website_count', 'label' => 'Sites', 'class' => 'right', 'empty' => '-', 'sortable' => true, 'type' => 'number'],
            ['key' => 'event_count', 'label' => 'Events', 'class' => 'right', 'empty' => '-', 'sortable' => true, 'type' => 'number'],
            ['key' => 'events_7d', 'label' => '7d', 'class' => 'right muted', 'empty' => '-', 'sortable' => true, 'type' => 'number'],
        ];
        $response['filters'] = getLocationFilters($pdo);
        $response['defaultSort'] = ['key' => 'name', 'dir' => 'asc'];
        $response['idField'] = 'id';
        $response['nameField'] = 'name';
        $response['detailEndpoint'] = 'locations_detail.php';
        break;

    case 'events':
        $response['data'] = getEvents($pdo);
        $response['columns'] = [
            ['key' => 'id', 'label' => '#', 'class' => 'muted', 'sortable' => true],
            ['key' => 'emoji', 'label' => ''],
            ['key' => 'name', 'label' => 'Event', 'class' => 'name truncate', 'maxWidth' => '300px', 'sortable' => true],
            ['key' => 'start_date', 'label' => 'Date', 'type' => 'friendly_date', 'sortable' => true],
            ['key' => 'start_time', 'label' => 'Time', 'class' => 'muted', 'empty' => '-'],
            ['key' => 'location_name', 'label' => 'Location', 'fallback' => 'event_location_name', 'empty' => '-', 'type' => 'location_link', 'idKey' => 'location_id', 'sortable' => true],
            ['key' => 'website_name', 'label' => 'Source', 'class' => 'muted', 'empty' => '-', 'type' => 'website_link', 'idKey' => 'website_id', 'sortable' => true],
            ['key' => 'occurrence_count', 'label' => 'Dates', 'class' => 'right muted', 'type' => 'count_if_gt1', 'sortable' => true],
            ['key' => 'tags', 'label' => 'Tags', 'type' => 'tags_linked'],
        ];
        $response['filters'] = getEventFilters($pdo);
        $response['defaultSort'] = ['key' => 'start_date', 'dir' => 'asc'];
        $response['idField'] = 'id';
        $response['nameField'] = 'name';
        $response['detailEndpoint'] = 'events_detail.php';
        break;

    case 'tags':
        $response['data'] = getTags($pdo);
        $response['columns'] = [
            ['key' => 'tag', 'label' => 'Tag', 'type' => 'tag_badge', 'sortable' => true],
            ['key' => 'event_count', 'label' => 'Events', 'class' => 'right', 'sortable' => true, 'type' => 'number'],
            ['key' => 'upcoming_count', 'label' => 'Upcoming', 'class' => 'right', 'empty' => '-', 'sortable' => true, 'type' => 'number'],
            ['key' => 'website_count', 'label' => 'Sources', 'class' => 'right muted', 'sortable' => true, 'type' => 'number'],
            ['key' => 'first_event', 'label' => 'First', 'class' => 'muted', 'type' => 'short_date', 'empty' => '-', 'sortable' => true],
            ['key' => 'last_event', 'label' => 'Last', 'class' => 'muted', 'type' => 'short_date', 'empty' => '-', 'sortable' => true],
            ['key' => 'locations', 'label' => 'Locations', 'class' => 'muted truncate', 'maxWidth' => '150px', 'empty' => '-'],
        ];
        $response['filters'] = getTagFilters($pdo);
        $response['defaultSort'] = ['key' => 'event_count', 'dir' => 'desc'];
        $response['idField'] = 'tag';
        $response['nameField'] = 'tag';
        $response['detailEndpoint'] = 'tags_detail.php';
        break;

    default:
        $response['success'] = false;
        $response['error'] = 'Invalid type. Use: websites, locations, events, or tags';
}

echo json_encode($response, JSON_UNESCAPED_UNICODE);

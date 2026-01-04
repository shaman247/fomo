<?php
/**
 * Events CRUD API
 *
 * Endpoints:
 *   GET    /api/events.php           - List events (with filters)
 *   GET    /api/events.php?id=123    - Get single event
 *   POST   /api/events.php           - Create event
 *   PUT    /api/events.php?id=123    - Update event
 *   DELETE /api/events.php?id=123    - Delete event
 *   GET    /api/events.php?id=123&history=1 - Get edit history
 */

require_once __DIR__ . '/config.php';
require_once __DIR__ . '/edit_logger.php';

header('Access-Control-Allow-Origin: *');
header('Access-Control-Allow-Methods: GET, POST, PUT, DELETE, OPTIONS');
header('Access-Control-Allow-Headers: Content-Type');
header('Content-Type: application/json');

if ($_SERVER['REQUEST_METHOD'] === 'OPTIONS') {
    http_response_code(204);
    exit;
}

session_start();

try {
    $pdo = new PDO(
        "mysql:host=" . DB_HOST . ";dbname=" . DB_NAME . ";charset=utf8mb4",
        DB_USER,
        DB_PASS,
        [PDO::ATTR_ERRMODE => PDO::ERRMODE_EXCEPTION]
    );
} catch (PDOException $e) {
    jsonError('Database connection failed', 500);
}

$logger = new EditLogger($pdo, 'website', 'api');
$logger->setUserContextFromRequest();

$method = $_SERVER['REQUEST_METHOD'];
$id = isset($_GET['id']) ? (int)$_GET['id'] : null;

switch ($method) {
    case 'GET':
        if ($id) {
            if (isset($_GET['history'])) {
                getEventHistory($pdo, $logger, $id);
            } else {
                getEvent($pdo, $id);
            }
        } else {
            listEvents($pdo);
        }
        break;
    case 'POST':
        createEvent($pdo, $logger);
        break;
    case 'PUT':
        if (!$id) jsonError('ID required', 400);
        updateEvent($pdo, $logger, $id);
        break;
    case 'DELETE':
        if (!$id) jsonError('ID required', 400);
        deleteEvent($pdo, $logger, $id);
        break;
    default:
        jsonError('Method not allowed', 405);
}

function listEvents(PDO $pdo): void {
    $limit = min((int)($_GET['limit'] ?? 100), 1000);
    $offset = (int)($_GET['offset'] ?? 0);

    $where = ["1=1"];
    $params = [];

    // Filter by upcoming
    if (isset($_GET['upcoming']) && $_GET['upcoming']) {
        $where[] = "EXISTS (SELECT 1 FROM event_occurrences eo WHERE eo.event_id = e.id AND eo.start_date >= CURDATE())";
    }

    // Filter by location
    if (isset($_GET['location_id'])) {
        $where[] = "e.location_id = ?";
        $params[] = (int)$_GET['location_id'];
    }

    // Filter by website
    if (isset($_GET['website_id'])) {
        $where[] = "e.website_id = ?";
        $params[] = (int)$_GET['website_id'];
    }

    $whereClause = implode(' AND ', $where);

    $sql = "
        SELECT e.id, e.name, e.short_name, e.emoji, e.location_id, e.location_name,
               e.lat, e.lng, e.website_id, e.created_at, e.updated_at,
               l.name as location_display_name,
               w.name as website_name,
               (SELECT MIN(eo.start_date) FROM event_occurrences eo
                WHERE eo.event_id = e.id AND eo.start_date >= CURDATE()) as next_date
        FROM events e
        LEFT JOIN locations l ON e.location_id = l.id
        LEFT JOIN websites w ON e.website_id = w.id
        WHERE $whereClause
        ORDER BY next_date ASC, e.name ASC
        LIMIT ? OFFSET ?
    ";

    $params[] = $limit;
    $params[] = $offset;

    $stmt = $pdo->prepare($sql);
    $stmt->execute($params);
    $events = $stmt->fetchAll(PDO::FETCH_ASSOC);

    foreach ($events as &$e) {
        $e['id'] = (int)$e['id'];
        $e['location_id'] = $e['location_id'] ? (int)$e['location_id'] : null;
        $e['website_id'] = $e['website_id'] ? (int)$e['website_id'] : null;
        $e['lat'] = $e['lat'] ? (float)$e['lat'] : null;
        $e['lng'] = $e['lng'] ? (float)$e['lng'] : null;
    }

    jsonSuccess(['events' => $events, 'limit' => $limit, 'offset' => $offset]);
}

function getEvent(PDO $pdo, int $id): void {
    $stmt = $pdo->prepare("
        SELECT e.*, l.name as location_display_name, w.name as website_name
        FROM events e
        LEFT JOIN locations l ON e.location_id = l.id
        LEFT JOIN websites w ON e.website_id = w.id
        WHERE e.id = ?
    ");
    $stmt->execute([$id]);
    $event = $stmt->fetch(PDO::FETCH_ASSOC);

    if (!$event) {
        jsonError('Event not found', 404);
    }

    $event['id'] = (int)$event['id'];
    $event['location_id'] = $event['location_id'] ? (int)$event['location_id'] : null;
    $event['website_id'] = $event['website_id'] ? (int)$event['website_id'] : null;
    $event['lat'] = $event['lat'] ? (float)$event['lat'] : null;
    $event['lng'] = $event['lng'] ? (float)$event['lng'] : null;

    // Get occurrences
    $stmt = $pdo->prepare("
        SELECT id, start_date, start_time, end_date, end_time, sort_order
        FROM event_occurrences WHERE event_id = ? ORDER BY start_date, sort_order
    ");
    $stmt->execute([$id]);
    $event['occurrences'] = $stmt->fetchAll(PDO::FETCH_ASSOC);

    // Get URLs
    $stmt = $pdo->prepare("SELECT id, url, sort_order FROM event_urls WHERE event_id = ? ORDER BY sort_order");
    $stmt->execute([$id]);
    $event['urls'] = $stmt->fetchAll(PDO::FETCH_ASSOC);

    // Get tags
    $stmt = $pdo->prepare("
        SELECT t.id, t.name FROM tags t
        JOIN event_tags et ON t.id = et.tag_id
        WHERE et.event_id = ? ORDER BY t.name
    ");
    $stmt->execute([$id]);
    $event['tags'] = $stmt->fetchAll(PDO::FETCH_ASSOC);

    jsonSuccess(['event' => $event]);
}

function getEventHistory(PDO $pdo, EditLogger $logger, int $id): void {
    $stmt = $pdo->prepare("SELECT id FROM events WHERE id = ?");
    $stmt->execute([$id]);
    if (!$stmt->fetch()) {
        jsonError('Event not found', 404);
    }

    $history = $logger->getRecordHistory('events', $id);
    jsonSuccess(['history' => $history]);
}

function createEvent(PDO $pdo, EditLogger $logger): void {
    $input = getJsonInput();

    $name = trim($input['name'] ?? '');
    if (empty($name)) {
        jsonError('Name is required', 400);
    }

    $data = [
        'name' => substr($name, 0, 500),
        'short_name' => isset($input['short_name']) ? substr(trim($input['short_name']), 0, 255) : null,
        'description' => isset($input['description']) ? trim($input['description']) : null,
        'emoji' => isset($input['emoji']) ? substr(trim($input['emoji']), 0, 10) : null,
        'location_id' => isset($input['location_id']) ? (int)$input['location_id'] : null,
        'location_name' => isset($input['location_name']) ? substr(trim($input['location_name']), 0, 255) : null,
        'sublocation' => isset($input['sublocation']) ? substr(trim($input['sublocation']), 0, 255) : null,
        'lat' => isset($input['lat']) ? (float)$input['lat'] : null,
        'lng' => isset($input['lng']) ? (float)$input['lng'] : null,
        'website_id' => isset($input['website_id']) ? (int)$input['website_id'] : null,
    ];

    // Validate coordinates
    if ($data['lat'] !== null && ($data['lat'] < -90 || $data['lat'] > 90)) {
        jsonError('Invalid latitude', 400);
    }
    if ($data['lng'] !== null && ($data['lng'] < -180 || $data['lng'] > 180)) {
        jsonError('Invalid longitude', 400);
    }

    // If location_id provided, copy coords from location
    if ($data['location_id']) {
        $stmt = $pdo->prepare("SELECT lat, lng FROM locations WHERE id = ?");
        $stmt->execute([$data['location_id']]);
        $loc = $stmt->fetch(PDO::FETCH_ASSOC);
        if ($loc) {
            $data['lat'] = $loc['lat'] ? (float)$loc['lat'] : $data['lat'];
            $data['lng'] = $loc['lng'] ? (float)$loc['lng'] : $data['lng'];
        }
    }

    $stmt = $pdo->prepare("
        INSERT INTO events (name, short_name, description, emoji, location_id, location_name,
                           sublocation, lat, lng, website_id)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ");
    $stmt->execute([
        $data['name'], $data['short_name'], $data['description'], $data['emoji'],
        $data['location_id'], $data['location_name'], $data['sublocation'],
        $data['lat'], $data['lng'], $data['website_id']
    ]);

    $id = (int)$pdo->lastInsertId();
    $logger->logInsert('events', $id, $data);

    // Handle occurrences
    if (!empty($input['occurrences']) && is_array($input['occurrences'])) {
        $stmtOcc = $pdo->prepare("
            INSERT INTO event_occurrences (event_id, start_date, start_time, end_date, end_time, sort_order)
            VALUES (?, ?, ?, ?, ?, ?)
        ");
        foreach ($input['occurrences'] as $i => $occ) {
            if (empty($occ['start_date'])) continue;
            $stmtOcc->execute([
                $id,
                $occ['start_date'],
                isset($occ['start_time']) ? substr(trim($occ['start_time']), 0, 20) : null,
                $occ['end_date'] ?? null,
                isset($occ['end_time']) ? substr(trim($occ['end_time']), 0, 20) : null,
                $i
            ]);
        }
    }

    // Handle URLs
    if (!empty($input['urls']) && is_array($input['urls'])) {
        $stmtUrl = $pdo->prepare("INSERT INTO event_urls (event_id, url, sort_order) VALUES (?, ?, ?)");
        foreach ($input['urls'] as $i => $url) {
            $url = trim($url);
            if (!empty($url)) {
                $stmtUrl->execute([$id, substr($url, 0, 2000), $i]);
            }
        }
    }

    // Handle tags
    if (!empty($input['tags']) && is_array($input['tags'])) {
        foreach ($input['tags'] as $tagName) {
            $tagName = trim($tagName);
            if (!empty($tagName)) {
                $tagId = getOrCreateTag($pdo, $tagName);
                $pdo->prepare("INSERT IGNORE INTO event_tags (event_id, tag_id) VALUES (?, ?)")
                    ->execute([$id, $tagId]);
            }
        }
    }

    jsonSuccess(['id' => $id, 'message' => 'Event created'], 201);
}

function updateEvent(PDO $pdo, EditLogger $logger, int $id): void {
    $stmt = $pdo->prepare("SELECT * FROM events WHERE id = ?");
    $stmt->execute([$id]);
    $oldRecord = $stmt->fetch(PDO::FETCH_ASSOC);

    if (!$oldRecord) {
        jsonError('Event not found', 404);
    }

    $input = getJsonInput();
    $updates = [];
    $params = [];

    $stringFields = [
        'name' => 500, 'short_name' => 255, 'location_name' => 255,
        'sublocation' => 255, 'emoji' => 10
    ];
    foreach ($stringFields as $field => $max) {
        if (array_key_exists($field, $input)) {
            $value = $input[$field] !== null ? substr(trim($input[$field]), 0, $max) : null;
            $updates[] = "$field = ?";
            $params[] = $value ?: null;
        }
    }

    if (array_key_exists('description', $input)) {
        $updates[] = "description = ?";
        $params[] = $input['description'] !== null ? trim($input['description']) : null;
    }

    $intFields = ['location_id', 'website_id'];
    foreach ($intFields as $field) {
        if (array_key_exists($field, $input)) {
            $updates[] = "$field = ?";
            $params[] = $input[$field] !== null ? (int)$input[$field] : null;
        }
    }

    if (array_key_exists('lat', $input)) {
        $lat = $input['lat'] !== null ? (float)$input['lat'] : null;
        if ($lat !== null && ($lat < -90 || $lat > 90)) jsonError('Invalid latitude', 400);
        $updates[] = "lat = ?";
        $params[] = $lat;
    }

    if (array_key_exists('lng', $input)) {
        $lng = $input['lng'] !== null ? (float)$input['lng'] : null;
        if ($lng !== null && ($lng < -180 || $lng > 180)) jsonError('Invalid longitude', 400);
        $updates[] = "lng = ?";
        $params[] = $lng;
    }

    if (!empty($updates)) {
        $params[] = $id;
        $pdo->prepare("UPDATE events SET " . implode(', ', $updates) . " WHERE id = ?")->execute($params);

        $stmt = $pdo->prepare("SELECT * FROM events WHERE id = ?");
        $stmt->execute([$id]);
        $newRecord = $stmt->fetch(PDO::FETCH_ASSOC);

        $logger->logUpdates('events', $id, $oldRecord, $newRecord);
    }

    // Handle occurrences
    if (array_key_exists('occurrences', $input)) {
        $pdo->prepare("DELETE FROM event_occurrences WHERE event_id = ?")->execute([$id]);
        if (!empty($input['occurrences']) && is_array($input['occurrences'])) {
            $stmtOcc = $pdo->prepare("
                INSERT INTO event_occurrences (event_id, start_date, start_time, end_date, end_time, sort_order)
                VALUES (?, ?, ?, ?, ?, ?)
            ");
            foreach ($input['occurrences'] as $i => $occ) {
                if (empty($occ['start_date'])) continue;
                $stmtOcc->execute([
                    $id,
                    $occ['start_date'],
                    isset($occ['start_time']) ? substr(trim($occ['start_time']), 0, 20) : null,
                    $occ['end_date'] ?? null,
                    isset($occ['end_time']) ? substr(trim($occ['end_time']), 0, 20) : null,
                    $i
                ]);
            }
        }
    }

    // Handle URLs
    if (array_key_exists('urls', $input)) {
        $pdo->prepare("DELETE FROM event_urls WHERE event_id = ?")->execute([$id]);
        if (!empty($input['urls']) && is_array($input['urls'])) {
            $stmtUrl = $pdo->prepare("INSERT INTO event_urls (event_id, url, sort_order) VALUES (?, ?, ?)");
            foreach ($input['urls'] as $i => $url) {
                $url = trim($url);
                if (!empty($url)) {
                    $stmtUrl->execute([$id, substr($url, 0, 2000), $i]);
                }
            }
        }
    }

    // Handle tags
    if (array_key_exists('tags', $input)) {
        $pdo->prepare("DELETE FROM event_tags WHERE event_id = ?")->execute([$id]);
        if (!empty($input['tags']) && is_array($input['tags'])) {
            foreach ($input['tags'] as $tagName) {
                $tagName = trim($tagName);
                if (!empty($tagName)) {
                    $tagId = getOrCreateTag($pdo, $tagName);
                    $pdo->prepare("INSERT IGNORE INTO event_tags (event_id, tag_id) VALUES (?, ?)")
                        ->execute([$id, $tagId]);
                }
            }
        }
    }

    jsonSuccess(['message' => 'Event updated']);
}

function deleteEvent(PDO $pdo, EditLogger $logger, int $id): void {
    $stmt = $pdo->prepare("SELECT * FROM events WHERE id = ?");
    $stmt->execute([$id]);
    $record = $stmt->fetch(PDO::FETCH_ASSOC);

    if (!$record) {
        jsonError('Event not found', 404);
    }

    $logger->logDelete('events', $id, $record);
    $pdo->prepare("DELETE FROM events WHERE id = ?")->execute([$id]);

    jsonSuccess(['message' => 'Event deleted']);
}

function getOrCreateTag(PDO $pdo, string $name): int {
    $name = substr(trim($name), 0, 100);
    $stmt = $pdo->prepare("SELECT id FROM tags WHERE name = ?");
    $stmt->execute([$name]);
    $row = $stmt->fetch(PDO::FETCH_ASSOC);
    if ($row) return (int)$row['id'];

    $pdo->prepare("INSERT INTO tags (name) VALUES (?)")->execute([$name]);
    return (int)$pdo->lastInsertId();
}

function getJsonInput(): array {
    $raw = file_get_contents('php://input');
    if (empty($raw)) return [];
    $data = json_decode($raw, true);
    if (json_last_error() !== JSON_ERROR_NONE) jsonError('Invalid JSON', 400);
    return $data ?? [];
}

function jsonSuccess(array $data, int $code = 200): void {
    http_response_code($code);
    echo json_encode(array_merge(['success' => true], $data));
    exit;
}

function jsonError(string $msg, int $code = 400): void {
    http_response_code($code);
    echo json_encode(['success' => false, 'error' => $msg]);
    exit;
}

<?php
/**
 * Websites CRUD API
 *
 * Endpoints:
 *   GET    /api/websites.php           - List all websites
 *   GET    /api/websites.php?id=123    - Get single website
 *   POST   /api/websites.php           - Create website
 *   PUT    /api/websites.php?id=123    - Update website
 *   DELETE /api/websites.php?id=123    - Delete website
 *   GET    /api/websites.php?id=123&history=1 - Get edit history
 */

require_once __DIR__ . '/config.php';
require_once __DIR__ . '/edit_logger.php';

// CORS headers
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
                getWebsiteHistory($pdo, $logger, $id);
            } else {
                getWebsite($pdo, $id);
            }
        } else {
            listWebsites($pdo);
        }
        break;
    case 'POST':
        createWebsite($pdo, $logger);
        break;
    case 'PUT':
        if (!$id) jsonError('ID required', 400);
        updateWebsite($pdo, $logger, $id);
        break;
    case 'DELETE':
        if (!$id) jsonError('ID required', 400);
        deleteWebsite($pdo, $logger, $id);
        break;
    default:
        jsonError('Method not allowed', 405);
}

function listWebsites(PDO $pdo): void {
    $stmt = $pdo->query("
        SELECT w.id, w.name, w.base_url, w.crawl_frequency, w.disabled,
               w.last_crawled_at, w.created_at, w.updated_at,
               (SELECT COUNT(*) FROM events e WHERE e.website_id = w.id) as event_count
        FROM websites w
        ORDER BY w.name
    ");

    $websites = $stmt->fetchAll(PDO::FETCH_ASSOC);

    foreach ($websites as &$w) {
        $w['id'] = (int)$w['id'];
        $w['crawl_frequency'] = $w['crawl_frequency'] ? (int)$w['crawl_frequency'] : null;
        $w['disabled'] = (bool)$w['disabled'];
        $w['event_count'] = (int)$w['event_count'];
    }

    jsonSuccess(['websites' => $websites]);
}

function getWebsite(PDO $pdo, int $id): void {
    $stmt = $pdo->prepare("
        SELECT id, name, base_url, crawl_frequency, selector, num_clicks,
               keywords, max_pages, notes, disabled, last_crawled_at,
               created_at, updated_at
        FROM websites WHERE id = ?
    ");
    $stmt->execute([$id]);
    $website = $stmt->fetch(PDO::FETCH_ASSOC);

    if (!$website) {
        jsonError('Website not found', 404);
    }

    $website['id'] = (int)$website['id'];
    $website['crawl_frequency'] = $website['crawl_frequency'] ? (int)$website['crawl_frequency'] : null;
    $website['num_clicks'] = $website['num_clicks'] ? (int)$website['num_clicks'] : null;
    $website['max_pages'] = $website['max_pages'] ? (int)$website['max_pages'] : null;
    $website['disabled'] = (bool)$website['disabled'];

    // Get URLs
    $stmt = $pdo->prepare("SELECT id, url, sort_order FROM website_urls WHERE website_id = ? ORDER BY sort_order");
    $stmt->execute([$id]);
    $website['urls'] = $stmt->fetchAll(PDO::FETCH_ASSOC);

    // Get linked locations
    $stmt = $pdo->prepare("
        SELECT l.id, l.name FROM locations l
        JOIN website_locations wl ON l.id = wl.location_id
        WHERE wl.website_id = ? ORDER BY l.name
    ");
    $stmt->execute([$id]);
    $website['locations'] = $stmt->fetchAll(PDO::FETCH_ASSOC);

    // Get tags
    $stmt = $pdo->prepare("SELECT id, tag FROM website_tags WHERE website_id = ? ORDER BY tag");
    $stmt->execute([$id]);
    $website['tags'] = $stmt->fetchAll(PDO::FETCH_ASSOC);

    jsonSuccess(['website' => $website]);
}

function getWebsiteHistory(PDO $pdo, EditLogger $logger, int $id): void {
    $stmt = $pdo->prepare("SELECT id FROM websites WHERE id = ?");
    $stmt->execute([$id]);
    if (!$stmt->fetch()) {
        jsonError('Website not found', 404);
    }

    $history = $logger->getRecordHistory('websites', $id);
    jsonSuccess(['history' => $history]);
}

function createWebsite(PDO $pdo, EditLogger $logger): void {
    $input = getJsonInput();

    $name = trim($input['name'] ?? '');
    if (empty($name)) {
        jsonError('Name is required', 400);
    }

    $data = [
        'name' => substr($name, 0, 255),
        'base_url' => isset($input['base_url']) ? substr(trim($input['base_url']), 0, 500) : null,
        'crawl_frequency' => isset($input['crawl_frequency']) ? (int)$input['crawl_frequency'] : null,
        'selector' => isset($input['selector']) ? substr(trim($input['selector']), 0, 500) : null,
        'num_clicks' => isset($input['num_clicks']) ? (int)$input['num_clicks'] : null,
        'keywords' => isset($input['keywords']) ? substr(trim($input['keywords']), 0, 255) : null,
        'max_pages' => isset($input['max_pages']) ? (int)$input['max_pages'] : 30,
        'notes' => isset($input['notes']) ? trim($input['notes']) : null,
        'disabled' => isset($input['disabled']) ? (bool)$input['disabled'] : false,
    ];

    $stmt = $pdo->prepare("
        INSERT INTO websites (name, base_url, crawl_frequency, selector, num_clicks, keywords, max_pages, notes, disabled)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    ");
    $stmt->execute([
        $data['name'], $data['base_url'], $data['crawl_frequency'],
        $data['selector'], $data['num_clicks'], $data['keywords'],
        $data['max_pages'], $data['notes'], $data['disabled'] ? 1 : 0
    ]);

    $id = (int)$pdo->lastInsertId();
    $logger->logInsert('websites', $id, $data);

    // Handle URLs
    if (!empty($input['urls']) && is_array($input['urls'])) {
        $stmtUrl = $pdo->prepare("INSERT INTO website_urls (website_id, url, sort_order) VALUES (?, ?, ?)");
        foreach ($input['urls'] as $i => $url) {
            $url = trim($url);
            if (!empty($url)) {
                $stmtUrl->execute([$id, substr($url, 0, 2000), $i]);
            }
        }
    }

    // Handle location links
    if (!empty($input['location_ids']) && is_array($input['location_ids'])) {
        $stmtLoc = $pdo->prepare("INSERT IGNORE INTO website_locations (website_id, location_id) VALUES (?, ?)");
        foreach ($input['location_ids'] as $locId) {
            $stmtLoc->execute([$id, (int)$locId]);
        }
    }

    // Handle tags
    if (!empty($input['tags']) && is_array($input['tags'])) {
        $stmtTag = $pdo->prepare("INSERT IGNORE INTO website_tags (website_id, tag) VALUES (?, ?)");
        foreach ($input['tags'] as $tag) {
            $tag = trim($tag);
            if (!empty($tag)) {
                $stmtTag->execute([$id, substr($tag, 0, 100)]);
            }
        }
    }

    jsonSuccess(['id' => $id, 'message' => 'Website created'], 201);
}

function updateWebsite(PDO $pdo, EditLogger $logger, int $id): void {
    $stmt = $pdo->prepare("SELECT * FROM websites WHERE id = ?");
    $stmt->execute([$id]);
    $oldRecord = $stmt->fetch(PDO::FETCH_ASSOC);

    if (!$oldRecord) {
        jsonError('Website not found', 404);
    }

    $input = getJsonInput();
    $updates = [];
    $params = [];

    $stringFields = ['name' => 255, 'base_url' => 500, 'selector' => 500, 'keywords' => 255];
    foreach ($stringFields as $field => $max) {
        if (array_key_exists($field, $input)) {
            $value = $input[$field] !== null ? substr(trim($input[$field]), 0, $max) : null;
            $updates[] = "$field = ?";
            $params[] = $value ?: null;
        }
    }

    $intFields = ['crawl_frequency', 'num_clicks', 'max_pages'];
    foreach ($intFields as $field) {
        if (array_key_exists($field, $input)) {
            $updates[] = "$field = ?";
            $params[] = $input[$field] !== null ? (int)$input[$field] : null;
        }
    }

    if (array_key_exists('notes', $input)) {
        $updates[] = "notes = ?";
        $params[] = $input['notes'] !== null ? trim($input['notes']) : null;
    }

    if (array_key_exists('disabled', $input)) {
        $updates[] = "disabled = ?";
        $params[] = (bool)$input['disabled'] ? 1 : 0;
    }

    if (!empty($updates)) {
        $params[] = $id;
        $pdo->prepare("UPDATE websites SET " . implode(', ', $updates) . " WHERE id = ?")->execute($params);

        $stmt = $pdo->prepare("SELECT * FROM websites WHERE id = ?");
        $stmt->execute([$id]);
        $newRecord = $stmt->fetch(PDO::FETCH_ASSOC);

        $logger->logUpdates('websites', $id, $oldRecord, $newRecord);
    }

    // Handle URLs
    if (array_key_exists('urls', $input)) {
        $pdo->prepare("DELETE FROM website_urls WHERE website_id = ?")->execute([$id]);
        if (!empty($input['urls']) && is_array($input['urls'])) {
            $stmtUrl = $pdo->prepare("INSERT INTO website_urls (website_id, url, sort_order) VALUES (?, ?, ?)");
            foreach ($input['urls'] as $i => $url) {
                $url = trim($url);
                if (!empty($url)) {
                    $stmtUrl->execute([$id, substr($url, 0, 2000), $i]);
                }
            }
        }
    }

    // Handle location links
    if (array_key_exists('location_ids', $input)) {
        $pdo->prepare("DELETE FROM website_locations WHERE website_id = ?")->execute([$id]);
        if (!empty($input['location_ids']) && is_array($input['location_ids'])) {
            $stmtLoc = $pdo->prepare("INSERT IGNORE INTO website_locations (website_id, location_id) VALUES (?, ?)");
            foreach ($input['location_ids'] as $locId) {
                $stmtLoc->execute([$id, (int)$locId]);
            }
        }
    }

    // Handle tags
    if (array_key_exists('tags', $input)) {
        $pdo->prepare("DELETE FROM website_tags WHERE website_id = ?")->execute([$id]);
        if (!empty($input['tags']) && is_array($input['tags'])) {
            $stmtTag = $pdo->prepare("INSERT IGNORE INTO website_tags (website_id, tag) VALUES (?, ?)");
            foreach ($input['tags'] as $tag) {
                $tag = trim($tag);
                if (!empty($tag)) {
                    $stmtTag->execute([$id, substr($tag, 0, 100)]);
                }
            }
        }
    }

    jsonSuccess(['message' => 'Website updated']);
}

function deleteWebsite(PDO $pdo, EditLogger $logger, int $id): void {
    $stmt = $pdo->prepare("SELECT * FROM websites WHERE id = ?");
    $stmt->execute([$id]);
    $record = $stmt->fetch(PDO::FETCH_ASSOC);

    if (!$record) {
        jsonError('Website not found', 404);
    }

    $stmt = $pdo->prepare("SELECT COUNT(*) FROM events WHERE website_id = ?");
    $stmt->execute([$id]);
    $eventCount = (int)$stmt->fetchColumn();

    if ($eventCount > 0) {
        jsonError("Cannot delete: website has $eventCount event(s)", 409);
    }

    $logger->logDelete('websites', $id, $record);
    $pdo->prepare("DELETE FROM websites WHERE id = ?")->execute([$id]);

    jsonSuccess(['message' => 'Website deleted']);
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

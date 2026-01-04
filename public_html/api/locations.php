<?php
/**
 * Locations CRUD API
 *
 * Endpoints:
 *   GET    /api/locations.php           - List all locations
 *   GET    /api/locations.php?id=123    - Get single location
 *   POST   /api/locations.php           - Create location
 *   PUT    /api/locations.php?id=123    - Update location
 *   DELETE /api/locations.php?id=123    - Delete location
 *   GET    /api/locations.php?id=123&history=1 - Get edit history
 */

require_once __DIR__ . '/config.php';
require_once __DIR__ . '/edit_logger.php';

// CORS headers
header('Access-Control-Allow-Origin: *');
header('Access-Control-Allow-Methods: GET, POST, PUT, DELETE, OPTIONS');
header('Access-Control-Allow-Headers: Content-Type');
header('Content-Type: application/json');

// Handle preflight
if ($_SERVER['REQUEST_METHOD'] === 'OPTIONS') {
    http_response_code(204);
    exit;
}

// Start session for auth
session_start();

// Database connection
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

// Create edit logger
$logger = new EditLogger($pdo, 'website', 'api');
$logger->setUserContextFromRequest();

$method = $_SERVER['REQUEST_METHOD'];
$id = isset($_GET['id']) ? (int)$_GET['id'] : null;

switch ($method) {
    case 'GET':
        if ($id) {
            if (isset($_GET['history'])) {
                getLocationHistory($pdo, $logger, $id);
            } else {
                getLocation($pdo, $id);
            }
        } else {
            listLocations($pdo);
        }
        break;
    case 'POST':
        createLocation($pdo, $logger);
        break;
    case 'PUT':
        if (!$id) jsonError('ID required', 400);
        updateLocation($pdo, $logger, $id);
        break;
    case 'DELETE':
        if (!$id) jsonError('ID required', 400);
        deleteLocation($pdo, $logger, $id);
        break;
    default:
        jsonError('Method not allowed', 405);
}

/**
 * List all locations.
 */
function listLocations(PDO $pdo): void {
    $stmt = $pdo->query("
        SELECT l.id, l.name, l.short_name, l.very_short_name, l.address,
               l.lat, l.lng, l.emoji, l.alt_emoji, l.created_at, l.updated_at,
               (SELECT COUNT(*) FROM events e WHERE e.location_id = l.id) as event_count
        FROM locations l
        ORDER BY l.name
    ");

    $locations = $stmt->fetchAll(PDO::FETCH_ASSOC);

    // Convert types
    foreach ($locations as &$loc) {
        $loc['id'] = (int)$loc['id'];
        $loc['lat'] = $loc['lat'] ? (float)$loc['lat'] : null;
        $loc['lng'] = $loc['lng'] ? (float)$loc['lng'] : null;
        $loc['event_count'] = (int)$loc['event_count'];
    }

    jsonSuccess(['locations' => $locations]);
}

/**
 * Get single location with related data.
 */
function getLocation(PDO $pdo, int $id): void {
    // Get location
    $stmt = $pdo->prepare("
        SELECT id, name, short_name, very_short_name, address,
               lat, lng, emoji, alt_emoji, created_at, updated_at
        FROM locations WHERE id = ?
    ");
    $stmt->execute([$id]);
    $location = $stmt->fetch(PDO::FETCH_ASSOC);

    if (!$location) {
        jsonError('Location not found', 404);
    }

    // Convert types
    $location['id'] = (int)$location['id'];
    $location['lat'] = $location['lat'] ? (float)$location['lat'] : null;
    $location['lng'] = $location['lng'] ? (float)$location['lng'] : null;

    // Get alternate names
    $stmt = $pdo->prepare("
        SELECT id, alternate_name FROM location_alternate_names
        WHERE location_id = ? ORDER BY id
    ");
    $stmt->execute([$id]);
    $location['alternate_names'] = $stmt->fetchAll(PDO::FETCH_ASSOC);

    // Get tags
    $stmt = $pdo->prepare("
        SELECT t.id, t.name FROM tags t
        JOIN location_tags lt ON t.id = lt.tag_id
        WHERE lt.location_id = ? ORDER BY t.name
    ");
    $stmt->execute([$id]);
    $location['tags'] = $stmt->fetchAll(PDO::FETCH_ASSOC);

    // Get linked websites
    $stmt = $pdo->prepare("
        SELECT w.id, w.name FROM websites w
        JOIN website_locations wl ON w.id = wl.website_id
        WHERE wl.location_id = ? ORDER BY w.name
    ");
    $stmt->execute([$id]);
    $location['websites'] = $stmt->fetchAll(PDO::FETCH_ASSOC);

    jsonSuccess(['location' => $location]);
}

/**
 * Get edit history for a location.
 */
function getLocationHistory(PDO $pdo, EditLogger $logger, int $id): void {
    // Verify location exists
    $stmt = $pdo->prepare("SELECT id FROM locations WHERE id = ?");
    $stmt->execute([$id]);
    if (!$stmt->fetch()) {
        jsonError('Location not found', 404);
    }

    $history = $logger->getRecordHistory('locations', $id);

    jsonSuccess(['history' => $history]);
}

/**
 * Create a new location.
 */
function createLocation(PDO $pdo, EditLogger $logger): void {
    $input = getJsonInput();

    // Validate required fields
    $name = trim($input['name'] ?? '');
    if (empty($name)) {
        jsonError('Name is required', 400);
    }

    // Prepare data
    $data = [
        'name' => substr($name, 0, 255),
        'short_name' => isset($input['short_name']) ? substr(trim($input['short_name']), 0, 100) : null,
        'very_short_name' => isset($input['very_short_name']) ? substr(trim($input['very_short_name']), 0, 50) : null,
        'address' => isset($input['address']) ? substr(trim($input['address']), 0, 500) : null,
        'lat' => isset($input['lat']) ? (float)$input['lat'] : null,
        'lng' => isset($input['lng']) ? (float)$input['lng'] : null,
        'emoji' => isset($input['emoji']) ? substr(trim($input['emoji']), 0, 10) : null,
        'alt_emoji' => isset($input['alt_emoji']) ? substr(trim($input['alt_emoji']), 0, 10) : null,
    ];

    // Validate coordinates
    if ($data['lat'] !== null && ($data['lat'] < -90 || $data['lat'] > 90)) {
        jsonError('Invalid latitude', 400);
    }
    if ($data['lng'] !== null && ($data['lng'] < -180 || $data['lng'] > 180)) {
        jsonError('Invalid longitude', 400);
    }

    // Insert location
    $stmt = $pdo->prepare("
        INSERT INTO locations (name, short_name, very_short_name, address, lat, lng, emoji, alt_emoji)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    ");
    $stmt->execute([
        $data['name'],
        $data['short_name'],
        $data['very_short_name'],
        $data['address'],
        $data['lat'],
        $data['lng'],
        $data['emoji'],
        $data['alt_emoji']
    ]);

    $id = (int)$pdo->lastInsertId();

    // Log the insert
    $logger->logInsert('locations', $id, $data);

    // Handle alternate names
    if (!empty($input['alternate_names']) && is_array($input['alternate_names'])) {
        $stmtAlt = $pdo->prepare("INSERT INTO location_alternate_names (location_id, alternate_name) VALUES (?, ?)");
        foreach ($input['alternate_names'] as $altName) {
            $altName = trim($altName);
            if (!empty($altName)) {
                $stmtAlt->execute([$id, substr($altName, 0, 255)]);
            }
        }
    }

    // Handle tags
    if (!empty($input['tags']) && is_array($input['tags'])) {
        foreach ($input['tags'] as $tagName) {
            $tagName = trim($tagName);
            if (!empty($tagName)) {
                $tagId = getOrCreateTag($pdo, $tagName);
                $pdo->prepare("INSERT IGNORE INTO location_tags (location_id, tag_id) VALUES (?, ?)")
                    ->execute([$id, $tagId]);
            }
        }
    }

    jsonSuccess([
        'id' => $id,
        'message' => 'Location created'
    ], 201);
}

/**
 * Update an existing location.
 */
function updateLocation(PDO $pdo, EditLogger $logger, int $id): void {
    // Get current record
    $stmt = $pdo->prepare("SELECT * FROM locations WHERE id = ?");
    $stmt->execute([$id]);
    $oldRecord = $stmt->fetch(PDO::FETCH_ASSOC);

    if (!$oldRecord) {
        jsonError('Location not found', 404);
    }

    $input = getJsonInput();

    // Build update data (only include fields that were provided)
    $updates = [];
    $params = [];

    $fields = [
        'name' => 255,
        'short_name' => 100,
        'very_short_name' => 50,
        'address' => 500,
        'emoji' => 10,
        'alt_emoji' => 10
    ];

    foreach ($fields as $field => $maxLength) {
        if (array_key_exists($field, $input)) {
            $value = $input[$field];
            if ($value !== null) {
                $value = substr(trim($value), 0, $maxLength);
            }
            $updates[] = "$field = ?";
            $params[] = $value ?: null;
        }
    }

    // Handle lat/lng
    if (array_key_exists('lat', $input)) {
        $lat = $input['lat'] !== null ? (float)$input['lat'] : null;
        if ($lat !== null && ($lat < -90 || $lat > 90)) {
            jsonError('Invalid latitude', 400);
        }
        $updates[] = "lat = ?";
        $params[] = $lat;
    }

    if (array_key_exists('lng', $input)) {
        $lng = $input['lng'] !== null ? (float)$input['lng'] : null;
        if ($lng !== null && ($lng < -180 || $lng > 180)) {
            jsonError('Invalid longitude', 400);
        }
        $updates[] = "lng = ?";
        $params[] = $lng;
    }

    if (empty($updates)) {
        jsonError('No fields to update', 400);
    }

    // Execute update
    $params[] = $id;
    $sql = "UPDATE locations SET " . implode(', ', $updates) . " WHERE id = ?";
    $pdo->prepare($sql)->execute($params);

    // Get new record for logging
    $stmt = $pdo->prepare("SELECT * FROM locations WHERE id = ?");
    $stmt->execute([$id]);
    $newRecord = $stmt->fetch(PDO::FETCH_ASSOC);

    // Log changes
    $logger->logUpdates('locations', $id, $oldRecord, $newRecord);

    // Handle alternate names if provided
    if (array_key_exists('alternate_names', $input)) {
        // Clear existing
        $pdo->prepare("DELETE FROM location_alternate_names WHERE location_id = ?")->execute([$id]);

        // Add new
        if (!empty($input['alternate_names']) && is_array($input['alternate_names'])) {
            $stmtAlt = $pdo->prepare("INSERT INTO location_alternate_names (location_id, alternate_name) VALUES (?, ?)");
            foreach ($input['alternate_names'] as $altName) {
                $altName = trim($altName);
                if (!empty($altName)) {
                    $stmtAlt->execute([$id, substr($altName, 0, 255)]);
                }
            }
        }
    }

    // Handle tags if provided
    if (array_key_exists('tags', $input)) {
        // Clear existing
        $pdo->prepare("DELETE FROM location_tags WHERE location_id = ?")->execute([$id]);

        // Add new
        if (!empty($input['tags']) && is_array($input['tags'])) {
            foreach ($input['tags'] as $tagName) {
                $tagName = trim($tagName);
                if (!empty($tagName)) {
                    $tagId = getOrCreateTag($pdo, $tagName);
                    $pdo->prepare("INSERT IGNORE INTO location_tags (location_id, tag_id) VALUES (?, ?)")
                        ->execute([$id, $tagId]);
                }
            }
        }
    }

    jsonSuccess(['message' => 'Location updated']);
}

/**
 * Delete a location.
 */
function deleteLocation(PDO $pdo, EditLogger $logger, int $id): void {
    // Get current record for logging
    $stmt = $pdo->prepare("SELECT * FROM locations WHERE id = ?");
    $stmt->execute([$id]);
    $record = $stmt->fetch(PDO::FETCH_ASSOC);

    if (!$record) {
        jsonError('Location not found', 404);
    }

    // Check if location is in use
    $stmt = $pdo->prepare("SELECT COUNT(*) FROM events WHERE location_id = ?");
    $stmt->execute([$id]);
    $eventCount = (int)$stmt->fetchColumn();

    if ($eventCount > 0) {
        jsonError("Cannot delete: location is used by $eventCount event(s)", 409);
    }

    // Log deletion before deleting
    $logger->logDelete('locations', $id, $record);

    // Delete (cascades to alternate_names, tags via FK)
    $pdo->prepare("DELETE FROM locations WHERE id = ?")->execute([$id]);

    jsonSuccess(['message' => 'Location deleted']);
}

/**
 * Get or create a tag by name.
 */
function getOrCreateTag(PDO $pdo, string $name): int {
    $name = substr(trim($name), 0, 100);

    $stmt = $pdo->prepare("SELECT id FROM tags WHERE name = ?");
    $stmt->execute([$name]);
    $row = $stmt->fetch(PDO::FETCH_ASSOC);

    if ($row) {
        return (int)$row['id'];
    }

    $pdo->prepare("INSERT INTO tags (name) VALUES (?)")->execute([$name]);
    return (int)$pdo->lastInsertId();
}

/**
 * Get JSON input from request body.
 */
function getJsonInput(): array {
    $rawInput = file_get_contents('php://input');
    if (empty($rawInput)) {
        return [];
    }

    $data = json_decode($rawInput, true);
    if (json_last_error() !== JSON_ERROR_NONE) {
        jsonError('Invalid JSON', 400);
    }

    return $data ?? [];
}

/**
 * Return JSON success response.
 */
function jsonSuccess(array $data, int $statusCode = 200): void {
    http_response_code($statusCode);
    echo json_encode(array_merge(['success' => true], $data));
    exit;
}

/**
 * Return JSON error response.
 */
function jsonError(string $message, int $statusCode = 400): void {
    http_response_code($statusCode);
    echo json_encode([
        'success' => false,
        'error' => $message
    ]);
    exit;
}

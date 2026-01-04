<?php
/**
 * Sync API
 *
 * Exposes edits for syncing between local and production databases.
 *
 * Endpoints:
 *   GET  /api/sync.php?since=123           - Get edits since ID 123
 *   GET  /api/sync.php?since=123&source=website - Filter by source
 *   POST /api/sync.php                     - Receive edits from local
 *   GET  /api/sync.php?action=status       - Get sync status
 */

require_once __DIR__ . '/config.php';
require_once __DIR__ . '/edit_logger.php';

header('Access-Control-Allow-Origin: *');
header('Access-Control-Allow-Methods: GET, POST, OPTIONS');
header('Access-Control-Allow-Headers: Content-Type, X-Sync-Key');
header('Content-Type: application/json');

if ($_SERVER['REQUEST_METHOD'] === 'OPTIONS') {
    http_response_code(204);
    exit;
}

// Simple API key authentication for sync operations
// In production, use a more secure method
$expectedSyncKey = getenv('SYNC_API_KEY') ?: 'fomo-sync-key-change-in-production';
$providedKey = $_SERVER['HTTP_X_SYNC_KEY'] ?? '';

if ($_SERVER['REQUEST_METHOD'] === 'POST' && $providedKey !== $expectedSyncKey) {
    jsonError('Invalid sync key', 401);
}

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

$logger = new EditLogger($pdo, 'website', 'sync');

$method = $_SERVER['REQUEST_METHOD'];
$action = $_GET['action'] ?? '';

switch ($method) {
    case 'GET':
        if ($action === 'status') {
            getSyncStatus($pdo, $logger);
        } else {
            getEdits($pdo, $logger);
        }
        break;
    case 'POST':
        receiveEdits($pdo, $logger);
        break;
    default:
        jsonError('Method not allowed', 405);
}

/**
 * Get edits since a given ID.
 */
function getEdits(PDO $pdo, EditLogger $logger): void {
    $sinceId = (int)($_GET['since'] ?? 0);
    $source = $_GET['source'] ?? null;
    $limit = min((int)($_GET['limit'] ?? 1000), 5000);

    // Validate source
    if ($source !== null && !in_array($source, ['local', 'website', 'crawl'])) {
        jsonError('Invalid source', 400);
    }

    $edits = $logger->getEditsSince($sinceId, $source, $limit);

    // Get the max ID for pagination
    $maxId = 0;
    if (!empty($edits)) {
        $maxId = max(array_column($edits, 'id'));
    }

    jsonSuccess([
        'edits' => $edits,
        'count' => count($edits),
        'since_id' => $sinceId,
        'max_id' => $maxId,
        'has_more' => count($edits) === $limit
    ]);
}

/**
 * Receive edits from local database.
 */
function receiveEdits(PDO $pdo, EditLogger $logger): void {
    $input = getJsonInput();

    if (!isset($input['edits']) || !is_array($input['edits'])) {
        jsonError('edits array required', 400);
    }

    $edits = $input['edits'];
    $applied = 0;
    $skipped = 0;
    $conflicts = [];

    $pdo->beginTransaction();

    try {
        foreach ($edits as $edit) {
            // Check if this edit UUID already exists
            $stmt = $pdo->prepare("SELECT id FROM edits WHERE edit_uuid = ?");
            $stmt->execute([$edit['edit_uuid']]);

            if ($stmt->fetch()) {
                $skipped++;
                continue;
            }

            // Check for conflicts - same record+field edited in both places
            if ($edit['action'] === 'UPDATE') {
                $conflict = checkForConflict($pdo, $edit);
                if ($conflict) {
                    $conflicts[] = $conflict;
                    continue;
                }
            }

            // Apply the edit
            $success = applyEdit($pdo, $edit);
            if ($success) {
                $applied++;
            } else {
                $skipped++;
            }
        }

        // Update sync state
        if (!empty($edits)) {
            $maxId = max(array_column($edits, 'id'));
            $logger->updateLastSyncedEditId('local', $maxId);
        }

        $pdo->commit();

        jsonSuccess([
            'applied' => $applied,
            'skipped' => $skipped,
            'conflicts' => count($conflicts),
            'conflict_details' => $conflicts
        ]);

    } catch (Exception $e) {
        $pdo->rollBack();
        jsonError('Sync failed: ' . $e->getMessage(), 500);
    }
}

/**
 * Check if an incoming edit conflicts with a local edit.
 */
function checkForConflict(PDO $pdo, array $incomingEdit): ?array {
    // Look for local edits to the same record+field since last sync
    $stmt = $pdo->prepare("
        SELECT e.*, ss.last_synced_edit_id
        FROM edits e
        LEFT JOIN sync_state ss ON ss.source = 'local'
        WHERE e.table_name = ?
          AND e.record_id = ?
          AND e.field_name = ?
          AND e.source = 'website'
          AND e.id > COALESCE(ss.last_synced_edit_id, 0)
        ORDER BY e.id DESC
        LIMIT 1
    ");

    $stmt->execute([
        $incomingEdit['table_name'],
        $incomingEdit['record_id'],
        $incomingEdit['field_name']
    ]);

    $localEdit = $stmt->fetch(PDO::FETCH_ASSOC);

    if (!$localEdit) {
        return null;
    }

    // Conflict exists - values differ
    if ($localEdit['new_value'] !== $incomingEdit['new_value']) {
        // Record the conflict
        $stmt = $pdo->prepare("
            INSERT INTO conflicts (
                local_edit_id, website_edit_id, table_name, record_id, field_name,
                local_value, website_value, status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, 'pending')
        ");

        // First insert the incoming edit to get its ID
        $stmt2 = $pdo->prepare("
            INSERT INTO edits (
                edit_uuid, table_name, record_id, field_name, action,
                old_value, new_value, source, editor_info
            ) VALUES (?, ?, ?, ?, ?, ?, ?, 'local', 'synced')
        ");
        $stmt2->execute([
            $incomingEdit['edit_uuid'],
            $incomingEdit['table_name'],
            $incomingEdit['record_id'],
            $incomingEdit['field_name'],
            $incomingEdit['action'],
            $incomingEdit['old_value'],
            $incomingEdit['new_value']
        ]);
        $incomingEditId = $pdo->lastInsertId();

        $stmt->execute([
            $incomingEditId,
            $localEdit['id'],
            $incomingEdit['table_name'],
            $incomingEdit['record_id'],
            $incomingEdit['field_name'],
            $incomingEdit['new_value'],
            $localEdit['new_value']
        ]);

        return [
            'table' => $incomingEdit['table_name'],
            'record_id' => $incomingEdit['record_id'],
            'field' => $incomingEdit['field_name'],
            'local_value' => $incomingEdit['new_value'],
            'website_value' => $localEdit['new_value']
        ];
    }

    return null;
}

/**
 * Apply an edit to the database.
 */
function applyEdit(PDO $pdo, array $edit): bool {
    $tableName = $edit['table_name'];
    $recordId = $edit['record_id'];
    $action = $edit['action'];

    // Validate table name (prevent SQL injection)
    $validTables = [
        'locations', 'location_alternate_names', 'location_tags',
        'websites', 'website_urls', 'website_locations', 'website_tags',
        'events', 'event_occurrences', 'event_urls', 'event_tags',
        'tags', 'tag_rules'
    ];

    if (!in_array($tableName, $validTables)) {
        return false;
    }

    try {
        if ($action === 'UPDATE') {
            $fieldName = $edit['field_name'];
            $newValue = $edit['new_value'];

            // Validate field name (alphanumeric and underscore only)
            if (!preg_match('/^[a-zA-Z_][a-zA-Z0-9_]*$/', $fieldName)) {
                return false;
            }

            $stmt = $pdo->prepare("UPDATE `$tableName` SET `$fieldName` = ? WHERE id = ?");
            $stmt->execute([$newValue, $recordId]);

        } elseif ($action === 'DELETE') {
            $stmt = $pdo->prepare("DELETE FROM `$tableName` WHERE id = ?");
            $stmt->execute([$recordId]);

        } elseif ($action === 'INSERT') {
            // INSERT is complex - skip for now, handle separately
            return false;
        }

        // Record that we received this edit
        $stmt = $pdo->prepare("
            INSERT INTO edits (
                edit_uuid, table_name, record_id, field_name, action,
                old_value, new_value, source, editor_info, applied_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, 'local', 'synced', NOW())
            ON DUPLICATE KEY UPDATE applied_at = NOW()
        ");
        $stmt->execute([
            $edit['edit_uuid'],
            $tableName,
            $recordId,
            $edit['field_name'] ?? null,
            $action,
            $edit['old_value'] ?? null,
            $edit['new_value'] ?? null
        ]);

        return true;

    } catch (PDOException $e) {
        error_log("Apply edit failed: " . $e->getMessage());
        return false;
    }
}

/**
 * Get sync status.
 */
function getSyncStatus(PDO $pdo, EditLogger $logger): void {
    // Get last synced IDs
    $stmt = $pdo->query("SELECT source, last_synced_edit_id, last_sync_at FROM sync_state");
    $syncState = [];
    while ($row = $stmt->fetch(PDO::FETCH_ASSOC)) {
        $syncState[$row['source']] = [
            'last_edit_id' => (int)$row['last_synced_edit_id'],
            'last_sync_at' => $row['last_sync_at']
        ];
    }

    // Get edit counts by source
    $stmt = $pdo->query("
        SELECT source, COUNT(*) as count, MAX(id) as max_id
        FROM edits GROUP BY source
    ");
    $editCounts = [];
    while ($row = $stmt->fetch(PDO::FETCH_ASSOC)) {
        $editCounts[$row['source']] = [
            'count' => (int)$row['count'],
            'max_id' => (int)$row['max_id']
        ];
    }

    // Get pending conflicts
    $stmt = $pdo->query("SELECT COUNT(*) FROM conflicts WHERE status = 'pending'");
    $pendingConflicts = (int)$stmt->fetchColumn();

    jsonSuccess([
        'sync_state' => $syncState,
        'edit_counts' => $editCounts,
        'pending_conflicts' => $pendingConflicts
    ]);
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

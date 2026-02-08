<?php
/**
 * Conflicts API
 *
 * Handles conflict resolution for the admin dashboard.
 *
 * Endpoints:
 *   GET  ?action=list              - List pending conflicts
 *   GET  ?action=get&id=123        - Get single conflict details
 *   POST ?action=resolve           - Resolve a conflict
 *   POST ?action=batch_resolve     - Resolve multiple conflicts
 */

require_once __DIR__ . '/db_config.php';

header('Content-Type: application/json');

session_start();

$action = $_GET['action'] ?? '';

switch ($action) {
    case 'list':
        listConflicts($pdo);
        break;
    case 'get':
        getConflict($pdo, (int)($_GET['id'] ?? 0));
        break;
    case 'resolve':
        resolveConflict($pdo);
        break;
    case 'batch_resolve':
        batchResolve($pdo);
        break;
    default:
        jsonError('Invalid action');
}

function listConflicts(PDO $pdo): void {
    $status = $_GET['status'] ?? 'pending';

    $stmt = $pdo->prepare("
        SELECT c.id, c.table_name, c.record_id, c.field_name,
               c.local_value, c.website_value, c.status,
               c.resolved_value, c.resolved_at, c.created_at,
               u.display_name as resolved_by_name,
               le.created_at as local_edit_at,
               we.created_at as website_edit_at
        FROM conflicts c
        LEFT JOIN users u ON c.resolved_by = u.id
        LEFT JOIN edits le ON c.local_edit_id = le.id
        LEFT JOIN edits we ON c.website_edit_id = we.id
        WHERE c.status = ?
        ORDER BY c.created_at DESC
        LIMIT 100
    ");
    $stmt->execute([$status]);
    $conflicts = $stmt->fetchAll(PDO::FETCH_ASSOC);

    // Get record names for context
    foreach ($conflicts as &$conflict) {
        $conflict['id'] = (int)$conflict['id'];
        $conflict['record_id'] = (int)$conflict['record_id'];

        // Get the record name
        $conflict['record_name'] = getRecordName($pdo, $conflict['table_name'], $conflict['record_id']);
    }

    // Get counts by status
    $stmt = $pdo->query("
        SELECT status, COUNT(*) as count FROM conflicts GROUP BY status
    ");
    $counts = [];
    while ($row = $stmt->fetch(PDO::FETCH_ASSOC)) {
        $counts[$row['status']] = (int)$row['count'];
    }

    jsonSuccess([
        'conflicts' => $conflicts,
        'counts' => $counts
    ]);
}

function getConflict(PDO $pdo, int $id): void {
    if (!$id) {
        jsonError('ID required');
    }

    $stmt = $pdo->prepare("
        SELECT c.*, u.display_name as resolved_by_name
        FROM conflicts c
        LEFT JOIN users u ON c.resolved_by = u.id
        WHERE c.id = ?
    ");
    $stmt->execute([$id]);
    $conflict = $stmt->fetch(PDO::FETCH_ASSOC);

    if (!$conflict) {
        jsonError('Conflict not found', 404);
    }

    $conflict['id'] = (int)$conflict['id'];
    $conflict['record_id'] = (int)$conflict['record_id'];

    // Get the current record value
    $tableName = $conflict['table_name'];
    $recordId = $conflict['record_id'];
    $fieldName = $conflict['field_name'];

    if ($fieldName) {
        $stmt = $pdo->prepare("SELECT `$fieldName` FROM `$tableName` WHERE id = ?");
        $stmt->execute([$recordId]);
        $row = $stmt->fetch(PDO::FETCH_ASSOC);
        $conflict['current_value'] = $row ? $row[$fieldName] : null;
    }

    // Get the full record for context
    $stmt = $pdo->prepare("SELECT * FROM `$tableName` WHERE id = ?");
    $stmt->execute([$recordId]);
    $conflict['current_record'] = $stmt->fetch(PDO::FETCH_ASSOC);

    jsonSuccess(['conflict' => $conflict]);
}

function resolveConflict(PDO $pdo): void {
    if ($_SERVER['REQUEST_METHOD'] !== 'POST') {
        jsonError('POST required', 405);
    }

    $input = getJsonInput();

    $id = (int)($input['id'] ?? 0);
    $resolution = $input['resolution'] ?? ''; // 'local', 'website', or 'merged'
    $mergedValue = $input['merged_value'] ?? null;

    if (!$id) {
        jsonError('Conflict ID required');
    }

    if (!in_array($resolution, ['local', 'website', 'merged'])) {
        jsonError('Invalid resolution. Use: local, website, or merged');
    }

    if ($resolution === 'merged' && $mergedValue === null) {
        jsonError('Merged value required for merged resolution');
    }

    // Get the conflict
    $stmt = $pdo->prepare("SELECT * FROM conflicts WHERE id = ? AND status = 'pending'");
    $stmt->execute([$id]);
    $conflict = $stmt->fetch(PDO::FETCH_ASSOC);

    if (!$conflict) {
        jsonError('Conflict not found or already resolved', 404);
    }

    $tableName = $conflict['table_name'];
    $recordId = $conflict['record_id'];
    $fieldName = $conflict['field_name'];

    // Determine the value to apply
    $newValue = match($resolution) {
        'local' => $conflict['local_value'],
        'website' => $conflict['website_value'],
        'merged' => $mergedValue
    };

    $status = match($resolution) {
        'local' => 'resolved_local',
        'website' => 'resolved_website',
        'merged' => 'resolved_merged'
    };

    $pdo->beginTransaction();

    try {
        // Apply the resolution if it's not 'website' (website value is already current)
        if ($resolution !== 'website' && $fieldName) {
            $stmt = $pdo->prepare("UPDATE `$tableName` SET `$fieldName` = ? WHERE id = ?");
            $stmt->execute([$newValue, $recordId]);
        }

        // Update the conflict record
        $userId = $_SESSION['user_id'] ?? null;
        $stmt = $pdo->prepare("
            UPDATE conflicts SET
                status = ?,
                resolved_value = ?,
                resolved_by = ?,
                resolved_at = NOW()
            WHERE id = ?
        ");
        $stmt->execute([$status, $newValue, $userId, $id]);

        $pdo->commit();

        jsonSuccess(['message' => 'Conflict resolved']);

    } catch (Exception $e) {
        $pdo->rollBack();
        jsonError('Resolution failed: ' . $e->getMessage(), 500);
    }
}

function batchResolve(PDO $pdo): void {
    if ($_SERVER['REQUEST_METHOD'] !== 'POST') {
        jsonError('POST required', 405);
    }

    $input = getJsonInput();

    $ids = $input['ids'] ?? [];
    $resolution = $input['resolution'] ?? ''; // 'local' or 'website'

    if (empty($ids) || !is_array($ids)) {
        jsonError('IDs array required');
    }

    if (!in_array($resolution, ['local', 'website'])) {
        jsonError('Invalid resolution for batch. Use: local or website');
    }

    $resolved = 0;
    $failed = 0;

    foreach ($ids as $id) {
        $id = (int)$id;
        if (!$id) continue;

        // Get the conflict
        $stmt = $pdo->prepare("SELECT * FROM conflicts WHERE id = ? AND status = 'pending'");
        $stmt->execute([$id]);
        $conflict = $stmt->fetch(PDO::FETCH_ASSOC);

        if (!$conflict) {
            $failed++;
            continue;
        }

        $tableName = $conflict['table_name'];
        $recordId = $conflict['record_id'];
        $fieldName = $conflict['field_name'];

        $newValue = $resolution === 'local' ? $conflict['local_value'] : $conflict['website_value'];
        $status = $resolution === 'local' ? 'resolved_local' : 'resolved_website';

        try {
            // Apply resolution
            if ($resolution === 'local' && $fieldName) {
                $stmt = $pdo->prepare("UPDATE `$tableName` SET `$fieldName` = ? WHERE id = ?");
                $stmt->execute([$newValue, $recordId]);
            }

            // Update conflict
            $userId = $_SESSION['user_id'] ?? null;
            $stmt = $pdo->prepare("
                UPDATE conflicts SET status = ?, resolved_value = ?, resolved_by = ?, resolved_at = NOW()
                WHERE id = ?
            ");
            $stmt->execute([$status, $newValue, $userId, $id]);

            $resolved++;
        } catch (Exception $e) {
            $failed++;
        }
    }

    jsonSuccess([
        'resolved' => $resolved,
        'failed' => $failed
    ]);
}

function getRecordName(PDO $pdo, string $table, int $id): ?string {
    try {
        $nameField = match($table) {
            'locations', 'websites', 'events', 'tags' => 'name',
            default => null
        };

        if (!$nameField) {
            return "#$id";
        }

        $stmt = $pdo->prepare("SELECT `$nameField` FROM `$table` WHERE id = ?");
        $stmt->execute([$id]);
        $row = $stmt->fetch(PDO::FETCH_ASSOC);
        return $row ? $row[$nameField] : "#$id";
    } catch (Exception $e) {
        return "#$id";
    }
}

function getJsonInput(): array {
    $raw = file_get_contents('php://input');
    if (empty($raw)) return [];
    $data = json_decode($raw, true);
    if (json_last_error() !== JSON_ERROR_NONE) jsonError('Invalid JSON', 400);
    return $data ?? [];
}

function jsonSuccess(array $data): void {
    echo json_encode(array_merge(['success' => true], $data));
    exit;
}

function jsonError(string $msg, int $code = 400): void {
    http_response_code($code);
    echo json_encode(['success' => false, 'error' => $msg]);
    exit;
}

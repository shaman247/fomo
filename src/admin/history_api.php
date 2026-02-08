<?php
/**
 * Edit History API
 *
 * Provides edit history for records.
 *
 * Endpoints:
 *   GET ?table=locations&id=123  - Get history for a specific record
 *   GET ?recent=1                - Get recent edits across all tables
 *   POST ?action=revert          - Revert to a previous edit
 */

require_once __DIR__ . '/db_config.php';

header('Content-Type: application/json');

session_start();

$action = $_GET['action'] ?? '';

if ($action === 'revert') {
    revertEdit($pdo);
} elseif (isset($_GET['recent'])) {
    getRecentEdits($pdo);
} elseif (isset($_GET['table']) && isset($_GET['id'])) {
    getRecordHistory($pdo, $_GET['table'], (int)$_GET['id']);
} else {
    jsonError('Invalid request. Use: ?table=X&id=Y or ?recent=1');
}

function getRecordHistory(PDO $pdo, string $tableName, int $recordId): void {
    // Validate table name
    $validTables = [
        'locations', 'websites', 'events', 'tags',
        'location_alternate_names', 'location_tags',
        'website_urls', 'website_locations', 'website_tags',
        'event_occurrences', 'event_urls', 'event_tags',
        'tag_rules'
    ];

    if (!in_array($tableName, $validTables)) {
        jsonError('Invalid table name');
    }

    $stmt = $pdo->prepare("
        SELECT e.id, e.edit_uuid, e.field_name, e.action,
               e.old_value, e.new_value, e.source, e.editor_info,
               e.editor_ip, e.created_at, e.applied_at,
               u.display_name as user_name, u.email as user_email
        FROM edits e
        LEFT JOIN users u ON e.user_id = u.id
        WHERE e.table_name = ? AND e.record_id = ?
        ORDER BY e.created_at DESC
        LIMIT 100
    ");
    $stmt->execute([$tableName, $recordId]);
    $history = $stmt->fetchAll(PDO::FETCH_ASSOC);

    // Get current record for context
    $currentRecord = null;
    try {
        $stmt = $pdo->prepare("SELECT * FROM `$tableName` WHERE id = ?");
        $stmt->execute([$recordId]);
        $currentRecord = $stmt->fetch(PDO::FETCH_ASSOC);
    } catch (Exception $e) {
        // Record might be deleted
    }

    jsonSuccess([
        'history' => $history,
        'current_record' => $currentRecord,
        'table' => $tableName,
        'record_id' => $recordId
    ]);
}

function getRecentEdits(PDO $pdo): void {
    $limit = min((int)($_GET['limit'] ?? 50), 200);
    $source = $_GET['source'] ?? null;
    $table = $_GET['filter_table'] ?? null;

    $sql = "
        SELECT e.id, e.table_name, e.record_id, e.field_name, e.action,
               e.old_value, e.new_value, e.source, e.editor_info,
               e.created_at, u.display_name as user_name
        FROM edits e
        LEFT JOIN users u ON e.user_id = u.id
        WHERE 1=1
    ";
    $params = [];

    if ($source) {
        $sql .= " AND e.source = ?";
        $params[] = $source;
    }

    if ($table) {
        $sql .= " AND e.table_name = ?";
        $params[] = $table;
    }

    // LIMIT value is already sanitized as int, so interpolate directly
    $sql .= " ORDER BY e.created_at DESC LIMIT " . $limit;

    $stmt = $pdo->prepare($sql);
    $stmt->execute($params);
    $edits = $stmt->fetchAll(PDO::FETCH_ASSOC);

    // Get record names for display
    foreach ($edits as &$edit) {
        $edit['record_name'] = getRecordName($pdo, $edit['table_name'], $edit['record_id']);
    }

    // Get stats
    $stmt = $pdo->query("
        SELECT source, COUNT(*) as count FROM edits
        GROUP BY source
    ");
    $stats = [];
    while ($row = $stmt->fetch(PDO::FETCH_ASSOC)) {
        $stats[$row['source']] = (int)$row['count'];
    }

    // Get table counts
    $stmt = $pdo->query("
        SELECT table_name, COUNT(*) as count FROM edits
        GROUP BY table_name
        ORDER BY count DESC
    ");
    $tableCounts = [];
    while ($row = $stmt->fetch(PDO::FETCH_ASSOC)) {
        $tableCounts[$row['table_name']] = (int)$row['count'];
    }

    jsonSuccess([
        'edits' => $edits,
        'stats' => $stats,
        'table_counts' => $tableCounts
    ]);
}

function revertEdit(PDO $pdo): void {
    if ($_SERVER['REQUEST_METHOD'] !== 'POST') {
        jsonError('POST required', 405);
    }

    $input = getJsonInput();
    $editId = (int)($input['edit_id'] ?? 0);

    if (!$editId) {
        jsonError('edit_id required');
    }

    // Get the edit
    $stmt = $pdo->prepare("SELECT * FROM edits WHERE id = ?");
    $stmt->execute([$editId]);
    $edit = $stmt->fetch(PDO::FETCH_ASSOC);

    if (!$edit) {
        jsonError('Edit not found', 404);
    }

    $tableName = $edit['table_name'];
    $recordId = $edit['record_id'];
    $action = $edit['action'];

    // Validate table name
    $validTables = [
        'locations', 'websites', 'events', 'tags',
        'location_alternate_names', 'location_tags',
        'website_urls', 'website_locations', 'website_tags',
        'event_occurrences', 'event_urls', 'event_tags',
        'tag_rules'
    ];

    if (!in_array($tableName, $validTables)) {
        jsonError('Cannot revert edits to this table');
    }

    $pdo->beginTransaction();

    try {
        // Load edit logger only when needed
        require_once __DIR__ . '/../api/edit_logger.php';
        $logger = new EditLogger($pdo, 'website', 'revert');
        $logger->setUserContextFromRequest();

        if ($action === 'UPDATE') {
            // Revert UPDATE: set field back to old value
            $fieldName = $edit['field_name'];
            $oldValue = $edit['old_value'];

            if (!$fieldName || !preg_match('/^[a-zA-Z_][a-zA-Z0-9_]*$/', $fieldName)) {
                throw new Exception('Invalid field name');
            }

            // Get current value
            $stmt = $pdo->prepare("SELECT `$fieldName` FROM `$tableName` WHERE id = ?");
            $stmt->execute([$recordId]);
            $current = $stmt->fetch(PDO::FETCH_ASSOC);

            if (!$current) {
                throw new Exception('Record not found');
            }

            $currentValue = $current[$fieldName];

            // Apply revert
            $stmt = $pdo->prepare("UPDATE `$tableName` SET `$fieldName` = ? WHERE id = ?");
            $stmt->execute([$oldValue, $recordId]);

            // Log the revert
            $logger->logUpdate($tableName, $recordId, $fieldName, $currentValue, $oldValue);

        } elseif ($action === 'DELETE') {
            // Can't easily revert DELETE without full record data
            jsonError('Cannot revert DELETE operations');

        } elseif ($action === 'INSERT') {
            // Revert INSERT: delete the record
            $stmt = $pdo->prepare("SELECT * FROM `$tableName` WHERE id = ?");
            $stmt->execute([$recordId]);
            $record = $stmt->fetch(PDO::FETCH_ASSOC);

            if ($record) {
                $logger->logDelete($tableName, $recordId, $record);
                $pdo->prepare("DELETE FROM `$tableName` WHERE id = ?")->execute([$recordId]);
            }
        }

        $pdo->commit();
        jsonSuccess(['message' => 'Edit reverted']);

    } catch (Exception $e) {
        $pdo->rollBack();
        jsonError('Revert failed: ' . $e->getMessage(), 500);
    }
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
        return $row ? $row[$nameField] : "#$id (deleted)";
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

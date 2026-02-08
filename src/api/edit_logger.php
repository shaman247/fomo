<?php
/**
 * Edit Logger
 *
 * Logs all changes to core tables for sync and audit purposes.
 * Each edit is stored as an immutable log entry with a UUID for global uniqueness.
 */

require_once __DIR__ . '/config.php';

class EditLogger {
    private $pdo;
    private $source;
    private $editorInfo;
    private $userId;
    private $editorIp;
    private $editorUserAgent;

    // Tables that should have edits logged
    private const TRACKED_TABLES = [
        'locations', 'location_alternate_names', 'location_tags',
        'websites', 'website_urls', 'website_locations', 'website_tags',
        'events', 'event_occurrences', 'event_urls', 'event_tags',
        'tags', 'tag_rules'
    ];

    /**
     * Initialize the edit logger.
     *
     * @param PDO $pdo Database connection
     * @param string $source Origin of edits ('local', 'website', or 'crawl')
     * @param string|null $editorInfo Additional context (e.g., 'admin', 'api')
     */
    public function __construct(PDO $pdo, string $source = 'website', ?string $editorInfo = null) {
        $this->pdo = $pdo;
        $this->source = $source;
        $this->editorInfo = $editorInfo;
        $this->userId = null;
        $this->editorIp = null;
        $this->editorUserAgent = null;
    }

    /**
     * Set user context for attribution.
     */
    public function setUserContext(?int $userId = null, ?string $ip = null, ?string $userAgent = null): void {
        $this->userId = $userId;
        $this->editorIp = $ip;
        $this->editorUserAgent = $userAgent;
    }

    /**
     * Auto-detect user context from request.
     */
    public function setUserContextFromRequest(): void {
        $this->editorIp = $_SERVER['REMOTE_ADDR'] ?? null;
        $this->editorUserAgent = $_SERVER['HTTP_USER_AGENT'] ?? null;

        // Check for logged-in user in session
        if (session_status() === PHP_SESSION_ACTIVE && isset($_SESSION['user_id'])) {
            $this->userId = $_SESSION['user_id'];
        }
    }

    /**
     * Generate a UUID v4.
     */
    private function generateUuid(): string {
        $data = random_bytes(16);
        $data[6] = chr(ord($data[6]) & 0x0f | 0x40);
        $data[8] = chr(ord($data[8]) & 0x3f | 0x80);
        return vsprintf('%s%s-%s-%s-%s-%s%s%s', str_split(bin2hex($data), 4));
    }

    /**
     * Serialize a value for storage.
     */
    private function serializeValue($value): ?string {
        if ($value === null) {
            return null;
        }
        if (is_array($value) || is_object($value)) {
            return json_encode($value);
        }
        if ($value instanceof DateTime) {
            return $value->format('c');
        }
        return (string)$value;
    }

    /**
     * Check if a table is tracked.
     */
    private function isTrackedTable(string $tableName): bool {
        return in_array($tableName, self::TRACKED_TABLES);
    }

    /**
     * Insert an edit record.
     */
    private function insertEdit(
        string $tableName,
        int $recordId,
        ?string $fieldName,
        string $action,
        $oldValue,
        $newValue
    ): ?int {
        $editUuid = $this->generateUuid();

        $stmt = $this->pdo->prepare("
            INSERT INTO edits (
                edit_uuid, table_name, record_id, field_name, action,
                old_value, new_value, source, user_id, editor_ip,
                editor_user_agent, editor_info, applied_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NOW())
        ");

        $stmt->execute([
            $editUuid,
            $tableName,
            $recordId,
            $fieldName,
            $action,
            $this->serializeValue($oldValue),
            $this->serializeValue($newValue),
            $this->source,
            $this->userId,
            $this->editorIp,
            $this->editorUserAgent ? substr($this->editorUserAgent, 0, 500) : null,
            $this->editorInfo
        ]);

        return (int)$this->pdo->lastInsertId();
    }

    /**
     * Log an INSERT operation.
     *
     * @param string $tableName Name of the table
     * @param int $recordId ID of the inserted record
     * @param array $recordData Associative array of field values
     * @return int|null Edit ID
     */
    public function logInsert(string $tableName, int $recordId, array $recordData): ?int {
        if (!$this->isTrackedTable($tableName)) {
            return null;
        }

        return $this->insertEdit(
            $tableName,
            $recordId,
            null,
            'INSERT',
            null,
            $recordData
        );
    }

    /**
     * Log an UPDATE operation for a single field.
     *
     * @param string $tableName Name of the table
     * @param int $recordId ID of the updated record
     * @param string $fieldName Name of the field that changed
     * @param mixed $oldValue Previous value
     * @param mixed $newValue New value
     * @return int|null Edit ID
     */
    public function logUpdate(
        string $tableName,
        int $recordId,
        string $fieldName,
        $oldValue,
        $newValue
    ): ?int {
        if (!$this->isTrackedTable($tableName)) {
            return null;
        }

        // Don't log if value didn't actually change
        if ($this->serializeValue($oldValue) === $this->serializeValue($newValue)) {
            return null;
        }

        return $this->insertEdit(
            $tableName,
            $recordId,
            $fieldName,
            'UPDATE',
            $oldValue,
            $newValue
        );
    }

    /**
     * Log UPDATE operations for multiple fields by comparing old and new records.
     *
     * @param string $tableName Name of the table
     * @param int $recordId ID of the updated record
     * @param array $oldRecord Old field values
     * @param array $newRecord New field values
     * @return array List of edit IDs
     */
    public function logUpdates(
        string $tableName,
        int $recordId,
        array $oldRecord,
        array $newRecord
    ): array {
        $editIds = [];

        foreach ($newRecord as $fieldName => $newValue) {
            $oldValue = $oldRecord[$fieldName] ?? null;
            $editId = $this->logUpdate($tableName, $recordId, $fieldName, $oldValue, $newValue);
            if ($editId !== null) {
                $editIds[] = $editId;
            }
        }

        return $editIds;
    }

    /**
     * Log a DELETE operation.
     *
     * @param string $tableName Name of the table
     * @param int $recordId ID of the deleted record
     * @param array $recordData Snapshot of record before deletion
     * @return int|null Edit ID
     */
    public function logDelete(string $tableName, int $recordId, array $recordData): ?int {
        if (!$this->isTrackedTable($tableName)) {
            return null;
        }

        return $this->insertEdit(
            $tableName,
            $recordId,
            null,
            'DELETE',
            $recordData,
            null
        );
    }

    /**
     * Get edits since a given edit ID.
     *
     * @param int $sinceId Return edits with ID > sinceId
     * @param string|null $source Filter by source
     * @param int $limit Maximum number of edits
     * @return array List of edit records
     */
    public function getEditsSince(int $sinceId = 0, ?string $source = null, int $limit = 1000): array {
        $sql = "
            SELECT id, edit_uuid, table_name, record_id, field_name, action,
                   old_value, new_value, source, user_id, editor_ip,
                   editor_user_agent, editor_info, created_at, applied_at
            FROM edits
            WHERE id > ?
        ";
        $params = [$sinceId];

        if ($source !== null) {
            $sql .= " AND source = ?";
            $params[] = $source;
        }

        // LIMIT value is already sanitized as int, so interpolate directly
        // (PDO emulation mode can't bind integers for LIMIT)
        $sql .= " ORDER BY id ASC LIMIT " . $limit;

        $stmt = $this->pdo->prepare($sql);
        $stmt->execute($params);

        return $stmt->fetchAll(PDO::FETCH_ASSOC);
    }

    /**
     * Get edit history for a specific record.
     *
     * @param string $tableName Name of the table
     * @param int $recordId ID of the record
     * @return array List of edit records, newest first
     */
    public function getRecordHistory(string $tableName, int $recordId): array {
        $stmt = $this->pdo->prepare("
            SELECT e.id, e.edit_uuid, e.field_name, e.action,
                   e.old_value, e.new_value, e.source, e.editor_info,
                   e.created_at, u.display_name as user_name, u.email as user_email
            FROM edits e
            LEFT JOIN users u ON e.user_id = u.id
            WHERE e.table_name = ? AND e.record_id = ?
            ORDER BY e.created_at DESC
        ");

        $stmt->execute([$tableName, $recordId]);
        return $stmt->fetchAll(PDO::FETCH_ASSOC);
    }

    /**
     * Get the last synced edit ID for a source.
     *
     * @param string $source 'local' or 'website'
     * @return int|null Last synced edit ID
     */
    public function getLastSyncedEditId(string $source): ?int {
        $stmt = $this->pdo->prepare("
            SELECT last_synced_edit_id FROM sync_state WHERE source = ?
        ");
        $stmt->execute([$source]);
        $row = $stmt->fetch(PDO::FETCH_ASSOC);
        return $row ? (int)$row['last_synced_edit_id'] : null;
    }

    /**
     * Update the last synced edit ID for a source.
     *
     * @param string $source 'local' or 'website'
     * @param int $editId Last synced edit ID
     */
    public function updateLastSyncedEditId(string $source, int $editId): void {
        $stmt = $this->pdo->prepare("
            INSERT INTO sync_state (source, last_synced_edit_id, last_sync_at)
            VALUES (?, ?, NOW())
            ON DUPLICATE KEY UPDATE last_synced_edit_id = ?, last_sync_at = NOW()
        ");
        $stmt->execute([$source, $editId, $editId]);
    }
}

/**
 * Create an EditLogger instance with database connection.
 *
 * @param string $source Origin of edits ('local', 'website', or 'crawl')
 * @param string|null $editorInfo Additional context
 * @return EditLogger
 */
function getEditLogger(string $source = 'website', ?string $editorInfo = null): EditLogger {
    $pdo = new PDO(
        "mysql:host=" . DB_HOST . ";dbname=" . DB_NAME . ";charset=utf8mb4",
        DB_USER,
        DB_PASS,
        [PDO::ATTR_ERRMODE => PDO::ERRMODE_EXCEPTION]
    );

    $logger = new EditLogger($pdo, $source, $editorInfo);
    $logger->setUserContextFromRequest();

    return $logger;
}

-- Reviewed duplicate identities, bounded to source names/URLs/venues/slots.
CREATE TABLE IF NOT EXISTS event_merge_redirects (
    duplicate_id INT UNSIGNED NOT NULL PRIMARY KEY,
    survivor_id INT UNSIGNED NOT NULL,
    survivor_name VARCHAR(500) NOT NULL,
    source_identities JSON NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    CHECK (duplicate_id <> survivor_id),
    INDEX idx_survivor (survivor_id),
    FOREIGN KEY (duplicate_id) REFERENCES events(id) ON DELETE CASCADE,
    FOREIGN KEY (survivor_id) REFERENCES events(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

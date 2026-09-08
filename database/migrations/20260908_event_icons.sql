CREATE TABLE IF NOT EXISTS event_icon_assignments (
    event_id INT UNSIGNED NOT NULL PRIMARY KEY,
    icon_id VARCHAR(64) CHARACTER SET ascii COLLATE ascii_bin DEFAULT NULL,
    origin ENUM('rule','manual') NOT NULL,
    rule_version VARCHAR(64) DEFAULT NULL,
    input_hash CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    review_required TINYINT(1) NOT NULL DEFAULT 0,
    reason TEXT NOT NULL,
    evidence_json JSON NOT NULL,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    CONSTRAINT fk_event_icon_event FOREIGN KEY (event_id) REFERENCES events(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

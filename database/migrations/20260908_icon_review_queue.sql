CREATE TABLE IF NOT EXISTS icon_review_queue (
    emoji_hash CHAR(64) CHARACTER SET ascii COLLATE ascii_bin PRIMARY KEY,
    emoji VARCHAR(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL,
    source_kind VARCHAR(32) NOT NULL,
    source_id INT DEFAULT NULL,
    source_name VARCHAR(500) DEFAULT NULL,
    observations INT UNSIGNED NOT NULL DEFAULT 1,
    first_seen TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_seen TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    status ENUM('pending','resolved','dismissed') NOT NULL DEFAULT 'pending',
    review_note TEXT DEFAULT NULL,
    INDEX idx_icon_review_status (status,last_seen)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

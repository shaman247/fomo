-- Apply before running the BL03 canonical URL replay guard.
-- Historical crawl_events/raw_data/cache URLs are deliberately preserved.
CREATE TABLE IF NOT EXISTS event_url_exclusions (
    id INT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
    event_id INT UNSIGNED NOT NULL,
    url_hash CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    url VARCHAR(2000) NOT NULL,
    replacement_url VARCHAR(2000) NOT NULL,
    event_snapshot LONGTEXT NOT NULL COMMENT 'Exact reviewed name, venue and all sessions',
    evidence TEXT NOT NULL,
    reviewed_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_event_url_exclusion (event_id,url_hash),
    FOREIGN KEY (event_id) REFERENCES events(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

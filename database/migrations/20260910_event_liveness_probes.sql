-- Liveness probe verdicts (pipeline/liveness_probe.py), one row per (event, url) fetch.
-- Read back to rate-limit re-probes and to explain a fast-path archival in triage.
CREATE TABLE IF NOT EXISTS event_liveness_probes (
    id INT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
    event_id INT UNSIGNED NOT NULL,
    website_id INT DEFAULT NULL COMMENT 'Source website whose latest crawl dropped the event; its browser settings were used',
    url VARCHAR(2000) NOT NULL,
    verdict VARCHAR(16) NOT NULL COMMENT 'dead, alive, unknown',
    http_status INT DEFAULT NULL,
    page_title VARCHAR(500) DEFAULT NULL,
    reason VARCHAR(200) DEFAULT NULL,
    archived TINYINT(1) NOT NULL DEFAULT 0 COMMENT '1 when this probe archived the event',
    probed_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

    INDEX idx_probe_event (event_id, probed_at),
    INDEX idx_probe_time (probed_at),
    FOREIGN KEY (event_id) REFERENCES events(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Explicit positive source ownership; not a duplicate merge or suppression.
CREATE TABLE IF NOT EXISTS event_source_identities (
    event_id INT UNSIGNED NOT NULL,
    crawl_event_id INT UNSIGNED NOT NULL,
    identity JSON NOT NULL,
    review_reason TEXT NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (event_id, crawl_event_id),
    FOREIGN KEY (event_id) REFERENCES events(id) ON DELETE CASCADE,
    FOREIGN KEY (crawl_event_id) REFERENCES crawl_events(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

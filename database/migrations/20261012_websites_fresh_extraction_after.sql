-- BL28: per-site fingerprint invalidation (extractor.fingerprint_invalidated).
ALTER TABLE websites
    ADD COLUMN IF NOT EXISTS fresh_extraction_after DATETIME DEFAULT NULL
    COMMENT 'A content-fingerprint match never copies an extraction older than this; set it to NOW() (extractor.mark_fresh_extraction_needed) when un-archiving an event the cached extraction missed, so the next crawl re-extracts. Self-clearing: the fresh extraction is newer, so later matches reuse it.'
    AFTER blocked_location_names;

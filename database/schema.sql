-- fomo.nyc Database Schema
-- Event venues, websites, and events data

-- Create database if not exists (for local development)
CREATE DATABASE IF NOT EXISTS fomo CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

USE fomo;

-- Tables are not declared in strict dependency order (some FOREIGN KEYs reference
-- tables defined later), so defer FK validation until every table exists. Re-enabled
-- at the end of the file.
SET FOREIGN_KEY_CHECKS = 0;

-- ============================================================================
-- LOCATIONS
-- ============================================================================

-- Locations table - stores venue/location information
CREATE TABLE IF NOT EXISTS locations (
    id INT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    short_name VARCHAR(100) DEFAULT NULL COMMENT 'Display name for map labels and buttons',
    very_short_name VARCHAR(50) DEFAULT NULL COMMENT 'Abbreviated name when space is limited',
    address VARCHAR(500),
    description TEXT DEFAULT NULL,
    lat DECIMAL(10, 6),
    lng DECIMAL(10, 6),
    emoji VARCHAR(10),
    alt_emoji VARCHAR(10) COMMENT 'Fallback shown on Windows when emoji is a country flag (the system emoji font has no flag glyphs)',
    generic_location TINYINT(1) NOT NULL DEFAULT 0 COMMENT 'If true, a broad area/neighborhood rather than a specific venue (always uses pushpin emoji)',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

    INDEX idx_name (name),
    INDEX idx_short_name (short_name),
    INDEX idx_coords (lat, lng)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Location alternate names
CREATE TABLE IF NOT EXISTS location_alternate_names (
    id INT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
    location_id INT UNSIGNED NOT NULL,
    alternate_name VARCHAR(255) NOT NULL,
    website_id INT UNSIGNED DEFAULT NULL COMMENT 'Scope to specific website (NULL = global)',

    INDEX idx_location (location_id),
    INDEX idx_alt_name (alternate_name),
    INDEX idx_website_id (website_id),
    FOREIGN KEY (location_id) REFERENCES locations(id) ON DELETE CASCADE,
    FOREIGN KEY (website_id) REFERENCES websites(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ============================================================================
-- WEBSITES
-- ============================================================================

-- Websites table - stores event source websites for crawling
CREATE TABLE IF NOT EXISTS websites (
    id INT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    description TEXT DEFAULT NULL,
    base_url VARCHAR(500) DEFAULT NULL COMMENT 'Main website URL (informational, not crawled)',
    crawl_frequency INT UNSIGNED DEFAULT NULL COMMENT 'Days between crawls',
    selector VARCHAR(500) DEFAULT NULL COMMENT 'CSS selector for click-to-load',
    num_clicks INT UNSIGNED DEFAULT NULL COMMENT 'Number of clicks for pagination',
    js_code TEXT DEFAULT NULL COMMENT 'JavaScript code to execute before crawling',
    keywords VARCHAR(255) DEFAULT NULL COMMENT 'URL filter keywords',
    max_pages INT UNSIGNED DEFAULT 30 COMMENT 'Max pages for deep crawl',
    notes TEXT DEFAULT NULL,
    disabled BOOLEAN DEFAULT FALSE COMMENT 'If true, skip this website during crawling',
    crawl_after DATE DEFAULT NULL COMMENT 'Do not crawl until this date (for seasonal events)',
    force_crawl BOOLEAN DEFAULT FALSE COMMENT 'If true, crawl this website on next run regardless of frequency',
    last_crawled_at TIMESTAMP NULL COMMENT 'When this website was last crawled',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    delay_before_return_html INT UNSIGNED DEFAULT NULL COMMENT 'Seconds to wait for JS to render (default: 5)',
    content_filter_threshold DECIMAL(3,2) DEFAULT NULL COMMENT 'Pruning filter threshold 0-1 (NULL disables filter)',
    scan_full_page TINYINT(1) DEFAULT NULL COMMENT 'Scroll full page before capture (default: true)',
    remove_overlay_elements TINYINT(1) DEFAULT NULL COMMENT 'Remove popup/overlay elements (default: true)',
    javascript_enabled TINYINT(1) DEFAULT NULL COMMENT 'Enable JavaScript execution (default: true)',
    text_mode TINYINT(1) DEFAULT NULL COMMENT 'Disable images for text-only crawl (default: false)',
    light_mode TINYINT(1) DEFAULT NULL COMMENT 'Use minimal browser features (default: true)',
    use_stealth TINYINT(1) DEFAULT NULL COMMENT 'Use stealth mode to avoid detection',
    headed TINYINT(1) DEFAULT NULL COMMENT 'Run browser in headed (visible window) mode (default: false). Stealth always runs headed regardless.',
    scroll_delay DECIMAL(3,2) DEFAULT NULL COMMENT 'Seconds to pause between scroll steps (default: 0.2)',
    crawl_timeout INT UNSIGNED DEFAULT NULL COMMENT 'Timeout in seconds for entire crawl operation (default: 120)',
    crawl_frequency_locked BOOLEAN DEFAULT FALSE COMMENT 'If true, auto-frequency adjustment is disabled',
    strict_name_match TINYINT(1) NOT NULL DEFAULT 0 COMMENT 'If true, merger only fuses a crawl_event into an existing event on an EXACT name match, or a fuzzy match confirmed by a shared occurrence slot (prevents different recurring programs at a shared generic venue from collapsing; e.g. daily.nyc run clubs)',
    max_batches INT DEFAULT NULL COMMENT 'Override default per-website extraction batch limit (default 3 = 90 events)',
    source_type ENUM('primary','aggregator') NOT NULL DEFAULT 'primary' COMMENT 'aggregator sites are cross-referenced manually, not crawled on a regular schedule',
    process_images TINYINT(1) DEFAULT NULL COMMENT 'Run image/vision extraction for this site (e.g. Instagram)',
    user_agent VARCHAR(500) DEFAULT NULL COMMENT 'Per-site User-Agent override (default: constants.get_user_agent())',
    emoji VARCHAR(8) DEFAULT NULL COMMENT 'Organizer emoji shown in event popups',
    skip_reenrichment TINYINT(1) NOT NULL DEFAULT 0 COMMENT 'Skip detail-crawl re-enrichment (sites whose event URLs consistently fail, e.g. bot-protected ticketing)',
    blocked_location_names TEXT DEFAULT NULL COMMENT 'List of location names to drop (e.g. non-NYC venues from a multi-city feed)',

    INDEX idx_name (name),
    INDEX idx_last_crawled (last_crawled_at),
    INDEX idx_disabled (disabled)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Website URLs (one website can have multiple URLs to crawl)
CREATE TABLE IF NOT EXISTS website_urls (
    id INT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
    website_id INT UNSIGNED NOT NULL,
    url VARCHAR(2000) NOT NULL,
    js_code TEXT DEFAULT NULL COMMENT 'JavaScript code to execute for this specific URL',
    sort_order INT UNSIGNED DEFAULT 0,

    INDEX idx_website (website_id),
    FOREIGN KEY (website_id) REFERENCES websites(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Website-Location relationship (many-to-many)
CREATE TABLE IF NOT EXISTS website_locations (
    id INT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
    website_id INT UNSIGNED NOT NULL,
    location_id INT UNSIGNED NOT NULL,
    is_primary TINYINT(1) NOT NULL DEFAULT 0 COMMENT 'Primary venue for this website (default location when the extractor emits the org name)',
    url VARCHAR(500) DEFAULT NULL COMMENT 'Optional per-link URL for this website-location pairing',

    UNIQUE KEY unique_website_location (website_id, location_id),
    INDEX idx_website (website_id),
    INDEX idx_location (location_id),
    FOREIGN KEY (website_id) REFERENCES websites(id) ON DELETE CASCADE,
    FOREIGN KEY (location_id) REFERENCES locations(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Website extra tags (tags to apply to all events from this website)
CREATE TABLE IF NOT EXISTS website_tags (
    id INT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
    website_id INT UNSIGNED NOT NULL,
    tag VARCHAR(100) NOT NULL,

    UNIQUE KEY unique_website_tag (website_id, tag),
    INDEX idx_website (website_id),
    FOREIGN KEY (website_id) REFERENCES websites(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ============================================================================
-- INSTAGRAM
-- ============================================================================

-- Instagram accounts - stores Instagram handles for locations and websites
CREATE TABLE IF NOT EXISTS instagram_accounts (
    id INT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
    handle VARCHAR(100) NOT NULL,
    name VARCHAR(255) DEFAULT NULL,
    description VARCHAR(500) DEFAULT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

    UNIQUE KEY unique_handle (handle)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Location-Instagram relationship (many-to-many)
CREATE TABLE IF NOT EXISTS location_instagram (
    location_id INT UNSIGNED NOT NULL,
    instagram_id INT UNSIGNED NOT NULL,

    PRIMARY KEY (location_id, instagram_id),
    FOREIGN KEY (location_id) REFERENCES locations(id) ON DELETE CASCADE,
    FOREIGN KEY (instagram_id) REFERENCES instagram_accounts(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Website-Instagram relationship (many-to-many)
CREATE TABLE IF NOT EXISTS website_instagram (
    website_id INT UNSIGNED NOT NULL,
    instagram_id INT UNSIGNED NOT NULL,

    PRIMARY KEY (website_id, instagram_id),
    FOREIGN KEY (website_id) REFERENCES websites(id) ON DELETE CASCADE,
    FOREIGN KEY (instagram_id) REFERENCES instagram_accounts(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ============================================================================
-- EVENTS
-- ============================================================================

-- Events table - stores individual events
CREATE TABLE IF NOT EXISTS events (
    id INT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(500) NOT NULL,
    short_name VARCHAR(255) DEFAULT NULL,
    description TEXT,
    emoji VARCHAR(10),
    location_id INT UNSIGNED DEFAULT NULL,
    location_name VARCHAR(255) DEFAULT NULL COMMENT 'Original location name from source',
    sublocation VARCHAR(255) DEFAULT NULL COMMENT 'Room, floor, etc.',
    website_id INT UNSIGNED DEFAULT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    archived TINYINT(1) DEFAULT 0 COMMENT 'If true, event is archived (no future occurrences)',
    suppressed TINYINT(1) DEFAULT 0 COMMENT 'If true, event is hidden from display',
    reviewed TINYINT(1) DEFAULT 0 COMMENT 'If true, event has been reviewed for suppression',
    section VARCHAR(50) DEFAULT NULL COMMENT 'Display section grouping for the frontend (single-occasion vs ongoing, etc.)',
    event_type VARCHAR(40) DEFAULT NULL COMMENT 'Classified event_type (see pipeline/event_types.py); drives the Format tag family',

    INDEX idx_name (name(255)),
    INDEX idx_location (location_id),
    INDEX idx_website (website_id),
    INDEX idx_archived (archived),
    INDEX idx_reviewed (reviewed),
    FOREIGN KEY (location_id) REFERENCES locations(id) ON DELETE SET NULL,
    FOREIGN KEY (website_id) REFERENCES websites(id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Event occurrences (one event can have multiple dates/times)
CREATE TABLE IF NOT EXISTS event_occurrences (
    id INT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
    event_id INT UNSIGNED NOT NULL,
    start_date DATE NOT NULL,
    start_time VARCHAR(20) DEFAULT NULL COMMENT 'Time string (e.g., "7pm", "11am")',
    end_date DATE DEFAULT NULL,
    end_time VARCHAR(20) DEFAULT NULL,
    sort_order INT UNSIGNED DEFAULT 0,

    INDEX idx_event (event_id),
    INDEX idx_start_date (start_date),
    INDEX idx_date_range (start_date, end_date),
    FOREIGN KEY (event_id) REFERENCES events(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Event URLs (one event can have multiple source URLs)
CREATE TABLE IF NOT EXISTS event_urls (
    id INT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
    event_id INT UNSIGNED NOT NULL,
    url VARCHAR(2000) NOT NULL,
    sort_order INT UNSIGNED DEFAULT 0,

    INDEX idx_event (event_id),
    FOREIGN KEY (event_id) REFERENCES events(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Event scores - per-event quality scores from the (optional) event scorer.
-- event_id has no FK (scorer rows may outlive an event); composite_score is generated.
CREATE TABLE IF NOT EXISTS event_scores (
    id INT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
    event_id INT NOT NULL,
    scorer_run_id VARCHAR(50) NOT NULL,
    scorer_model VARCHAR(100) NOT NULL,
    scored_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    specificity DECIMAL(3,1) NOT NULL DEFAULT 0.0,
    novelty DECIMAL(3,1) NOT NULL DEFAULT 0.0,
    openness DECIMAL(3,1) NOT NULL DEFAULT 0.0,
    prominence DECIMAL(3,1) NOT NULL DEFAULT 0.0,
    connection DECIMAL(3,1) NOT NULL DEFAULT 0.0,
    substance DECIMAL(3,1) NOT NULL DEFAULT 0.0,
    specificity_reason TEXT DEFAULT NULL,
    novelty_reason TEXT DEFAULT NULL,
    openness_reason TEXT DEFAULT NULL,
    prominence_reason TEXT DEFAULT NULL,
    connection_reason TEXT DEFAULT NULL,
    substance_reason TEXT DEFAULT NULL,
    composite_score DECIMAL(5,2) GENERATED ALWAYS AS (specificity + novelty + openness + prominence + connection + substance) STORED,

    UNIQUE KEY uq_event_run (event_id, scorer_run_id),
    INDEX idx_event_id (event_id),
    INDEX idx_composite (composite_score)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- Dedupe dismissed pairs - event pairs a human reviewer marked as NOT duplicates (so they won't re-surface)
CREATE TABLE IF NOT EXISTS dedupe_dismissed_pairs (
    id INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
    event_id_a INT NOT NULL,
    event_id_b INT NOT NULL,
    reason VARCHAR(500) DEFAULT NULL,
    dismissed_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

    UNIQUE KEY unique_pair (event_id_a, event_id_b),
    INDEX idx_a (event_id_a),
    INDEX idx_b (event_id_b),
    CONSTRAINT chk_order CHECK (event_id_a < event_id_b)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ============================================================================
-- TAGS (Generic - used by locations and events)
-- ============================================================================

-- Tags table - stores unique tag values
CREATE TABLE IF NOT EXISTS tags (
    id INT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    emoji VARCHAR(10) DEFAULT NULL,
    alt_emoji VARCHAR(10) DEFAULT NULL COMMENT 'Fallback shown on Windows when emoji is a country flag (the system emoji font has no flag glyphs)',
    is_quick_filter TINYINT(1) NOT NULL DEFAULT 0,
    display_order INT DEFAULT NULL,
    type ENUM('tag','keyword') NOT NULL DEFAULT 'keyword' COMMENT 'tag=curated (in hierarchy/filters), keyword=search-only. New AI tags default to keyword; promote via populate_tag_hierarchy.py',

    UNIQUE KEY unique_tag_name (name),
    INDEX idx_name (name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Location tags (many-to-many)
CREATE TABLE IF NOT EXISTS location_tags (
    id INT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
    location_id INT UNSIGNED NOT NULL,
    tag_id INT UNSIGNED NOT NULL,

    UNIQUE KEY unique_location_tag (location_id, tag_id),
    INDEX idx_location (location_id),
    INDEX idx_tag (tag_id),
    FOREIGN KEY (location_id) REFERENCES locations(id) ON DELETE CASCADE,
    FOREIGN KEY (tag_id) REFERENCES tags(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Event tags (many-to-many)
CREATE TABLE IF NOT EXISTS event_tags (
    id INT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
    event_id INT UNSIGNED NOT NULL,
    tag_id INT UNSIGNED NOT NULL,

    UNIQUE KEY unique_event_tag (event_id, tag_id),
    INDEX idx_event (event_id),
    INDEX idx_tag (tag_id),
    FOREIGN KEY (event_id) REFERENCES events(id) ON DELETE CASCADE,
    FOREIGN KEY (tag_id) REFERENCES tags(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Tag hierarchy - DAG edges between curated tags (a tag may have multiple parents)
CREATE TABLE IF NOT EXISTS tag_hierarchy (
    parent_tag_id INT UNSIGNED NOT NULL,
    child_tag_id INT UNSIGNED NOT NULL,

    PRIMARY KEY (parent_tag_id, child_tag_id),
    INDEX idx_child (child_tag_id),
    FOREIGN KEY (parent_tag_id) REFERENCES tags(id) ON DELETE CASCADE,
    FOREIGN KEY (child_tag_id) REFERENCES tags(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Tag aliases - maps keyword/synonym aliases to a canonical curated tag (semantic equivalence)
CREATE TABLE IF NOT EXISTS tag_aliases (
    tag_id INT UNSIGNED NOT NULL,
    alias VARCHAR(100) NOT NULL,

    PRIMARY KEY (alias),
    INDEX idx_tag (tag_id),
    FOREIGN KEY (tag_id) REFERENCES tags(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Tag disambiguations - context rules picking the right homonym variant (e.g. Drama / Film)
CREATE TABLE IF NOT EXISTS tag_disambiguations (
    id INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
    ambiguous_alias VARCHAR(100) NOT NULL COMMENT 'Normalized AI-emitted tag (e.g. drama)',
    context_tag_id INT UNSIGNED DEFAULT NULL COMMENT 'Rule fires if this tag (or a descendant) is a co-tag; NULL = unconditional fallback',
    target_tag_id INT UNSIGNED NOT NULL COMMENT 'Variant to use when the rule matches',
    priority INT NOT NULL DEFAULT 0 COMMENT 'Higher priority evaluated first; first match wins',

    INDEX idx_alias (ambiguous_alias),
    INDEX fk_dis_ctx (context_tag_id),
    INDEX fk_dis_tgt (target_tag_id),
    FOREIGN KEY (context_tag_id) REFERENCES tags(id) ON DELETE CASCADE,
    FOREIGN KEY (target_tag_id) REFERENCES tags(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ============================================================================
-- CRAWL DATA (Pipeline tracking)
-- ============================================================================

-- Crawl runs - represents a daily crawl batch (e.g., 20251203)
CREATE TABLE IF NOT EXISTS crawl_runs (
    id INT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
    run_date DATE NOT NULL COMMENT 'The date of the crawl run (YYYYMMDD folder)',
    status ENUM('running', 'completed', 'failed') DEFAULT 'running',
    started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP NULL,
    notes TEXT DEFAULT NULL,

    UNIQUE KEY unique_run_date (run_date),
    INDEX idx_status (status),
    INDEX idx_run_date (run_date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Crawl results - per-website crawl output within a run
CREATE TABLE IF NOT EXISTS crawl_results (
    id INT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
    crawl_run_id INT UNSIGNED NOT NULL,
    website_id INT UNSIGNED DEFAULT NULL COMMENT 'Matched website, if identified',
    filename VARCHAR(255) NOT NULL COMMENT 'Original filename (e.g., cocusocial.json)',
    event_count INT UNSIGNED DEFAULT 0 COMMENT 'Number of events extracted',
    status ENUM('pending', 'crawled', 'extracted', 'processed', 'failed') DEFAULT 'pending',
    crawled_content LONGTEXT DEFAULT NULL COMMENT 'Raw markdown from crawler',
    extracted_content LONGTEXT DEFAULT NULL COMMENT 'Markdown table from Gemini extraction',
    batch_job_name VARCHAR(255) DEFAULT NULL COMMENT 'Gemini batch job name, if extracted via the batch API',
    content_hash CHAR(64) DEFAULT NULL COMMENT 'Hash of crawled_content to detect unchanged pages',
    crawled_at TIMESTAMP NULL,
    extracted_at TIMESTAMP NULL,
    processed_at TIMESTAMP NULL,
    error_message TEXT DEFAULT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    UNIQUE KEY unique_run_file (crawl_run_id, filename),
    INDEX idx_crawl_run (crawl_run_id),
    INDEX idx_website (website_id),
    INDEX idx_status (status),
    FOREIGN KEY (crawl_run_id) REFERENCES crawl_runs(id) ON DELETE CASCADE,
    FOREIGN KEY (website_id) REFERENCES websites(id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Crawl events - individual events extracted from a crawl result (raw data)
CREATE TABLE IF NOT EXISTS crawl_events (
    id INT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
    crawl_result_id INT UNSIGNED NOT NULL,
    name VARCHAR(500) NOT NULL,
    short_name VARCHAR(255) DEFAULT NULL,
    description TEXT,
    emoji VARCHAR(10),
    location_name VARCHAR(255) DEFAULT NULL COMMENT 'Raw location name from crawl',
    sublocation VARCHAR(255) DEFAULT NULL,
    location_id INT UNSIGNED DEFAULT NULL COMMENT 'Matched location from database',
    url VARCHAR(2000) DEFAULT NULL COMMENT 'Primary event URL',
    raw_data JSON DEFAULT NULL COMMENT 'Full JSON object from crawl',
    content_hash CHAR(64) DEFAULT NULL COMMENT 'SHA-256 hash for deduplication',
    detail_crawl_attempts TINYINT UNSIGNED NOT NULL DEFAULT 0 COMMENT 'Number of detail-crawl re-enrichment attempts on this event URL',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    INDEX idx_crawl_result (crawl_result_id),
    INDEX idx_name (name(255)),
    INDEX idx_content_hash (content_hash),
    INDEX idx_location_name (location_name),
    INDEX idx_location_id (location_id),
    FOREIGN KEY (crawl_result_id) REFERENCES crawl_results(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Crawl event occurrences - dates/times for crawl events
CREATE TABLE IF NOT EXISTS crawl_event_occurrences (
    id INT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
    crawl_event_id INT UNSIGNED NOT NULL,
    start_date DATE NOT NULL,
    start_time VARCHAR(20) DEFAULT NULL,
    end_date DATE DEFAULT NULL,
    end_time VARCHAR(20) DEFAULT NULL,
    sort_order INT UNSIGNED DEFAULT 0,

    INDEX idx_crawl_event (crawl_event_id),
    INDEX idx_start_date (start_date),
    FOREIGN KEY (crawl_event_id) REFERENCES crawl_events(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Crawl event tags - tags for crawl events
CREATE TABLE IF NOT EXISTS crawl_event_tags (
    id INT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
    crawl_event_id INT UNSIGNED NOT NULL,
    tag VARCHAR(100) NOT NULL COMMENT 'Raw tag string from crawl',

    INDEX idx_crawl_event (crawl_event_id),
    INDEX idx_tag (tag),
    FOREIGN KEY (crawl_event_id) REFERENCES crawl_events(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Event sources - links final events to the crawl events that contributed to them
CREATE TABLE IF NOT EXISTS event_sources (
    id INT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
    event_id INT UNSIGNED NOT NULL,
    crawl_event_id INT UNSIGNED NOT NULL,
    is_primary BOOLEAN DEFAULT FALSE COMMENT 'Is this the primary/first source for this event',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    UNIQUE KEY unique_event_source (event_id, crawl_event_id),
    INDEX idx_event (event_id),
    INDEX idx_crawl_event (crawl_event_id),
    FOREIGN KEY (event_id) REFERENCES events(id) ON DELETE CASCADE,
    FOREIGN KEY (crawl_event_id) REFERENCES crawl_events(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Extraction rejections - audit trail of events dropped during extraction/processing
-- (e.g. out-of-window dates, non-events). No FKs so rows survive crawl_result cleanup.
CREATE TABLE IF NOT EXISTS extraction_rejections (
    id INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
    crawl_result_id INT DEFAULT NULL,
    website_id INT DEFAULT NULL,
    rejection_type VARCHAR(50) NOT NULL COMMENT 'e.g. start_too_future, non_event, no_date',
    stage VARCHAR(32) NOT NULL COMMENT 'Pipeline stage that rejected the event',
    event_name VARCHAR(500) DEFAULT NULL,
    event_url VARCHAR(2000) DEFAULT NULL,
    extracted_start_date DATE DEFAULT NULL,
    extracted_end_date DATE DEFAULT NULL,
    details TEXT DEFAULT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

    INDEX idx_crawl_result (crawl_result_id),
    INDEX idx_created (created_at),
    INDEX idx_type (rejection_type)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ============================================================================
-- TAG RULES
-- ============================================================================

-- Rules for processing tags extracted from events
CREATE TABLE IF NOT EXISTS tag_rules (
    id INT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
    rule_type ENUM('rewrite', 'exclude', 'remove') NOT NULL COMMENT 'rewrite=map to new tag, exclude=filter out, remove=skip entire event',
    pattern VARCHAR(100) NOT NULL COMMENT 'Tag pattern to match (lowercase)',
    replacement VARCHAR(100) DEFAULT NULL COMMENT 'Replacement tag (only for rewrite rules)',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    UNIQUE KEY unique_rule (rule_type, pattern),
    INDEX idx_rule_type (rule_type),
    INDEX idx_pattern (pattern)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ============================================================================
-- USER FEEDBACK
-- ============================================================================

-- Feedback submitted by users via the website
CREATE TABLE IF NOT EXISTS feedback (
    id INT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
    message TEXT NOT NULL,
    user_agent VARCHAR(500) DEFAULT NULL,
    page_url VARCHAR(500) DEFAULT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    INDEX idx_created_at (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ============================================================================
-- USER ACCOUNTS (Optional authentication)
-- ============================================================================

-- Users table - optional accounts for tracking edits
CREATE TABLE IF NOT EXISTS users (
    id INT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
    email VARCHAR(255) NOT NULL,
    display_name VARCHAR(100) DEFAULT NULL,
    password_hash VARCHAR(255) NOT NULL,
    is_admin BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_login_at TIMESTAMP NULL,

    UNIQUE KEY unique_email (email),
    INDEX idx_email (email)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ============================================================================
-- EDIT HISTORY & SYNC
-- ============================================================================

-- Immutable edit log - tracks all changes to core tables
CREATE TABLE IF NOT EXISTS edits (
    id INT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
    edit_uuid CHAR(36) NOT NULL COMMENT 'UUID for global uniqueness across databases',
    table_name VARCHAR(50) NOT NULL COMMENT 'Table that was edited',
    record_id INT UNSIGNED NOT NULL COMMENT 'ID of the edited record',
    field_name VARCHAR(100) DEFAULT NULL COMMENT 'NULL for INSERT/DELETE, field name for UPDATE',
    action ENUM('INSERT', 'UPDATE', 'DELETE') NOT NULL,
    old_value TEXT DEFAULT NULL COMMENT 'Previous value (NULL for INSERT)',
    new_value TEXT DEFAULT NULL COMMENT 'New value (NULL for DELETE)',
    source ENUM('local', 'website', 'crawl') NOT NULL COMMENT 'Where edit originated',
    user_id INT UNSIGNED DEFAULT NULL COMMENT 'User who made the edit (NULL if anonymous)',
    editor_ip VARCHAR(45) DEFAULT NULL COMMENT 'IP address for anonymous edits',
    editor_user_agent VARCHAR(500) DEFAULT NULL COMMENT 'Browser user agent',
    editor_info VARCHAR(500) DEFAULT NULL COMMENT 'Additional context (e.g., crawl_run:123)',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    applied_at TIMESTAMP NULL COMMENT 'When edit was applied (NULL if pending)',

    UNIQUE KEY unique_edit_uuid (edit_uuid),
    INDEX idx_table_record (table_name, record_id),
    INDEX idx_source (source),
    INDEX idx_created (created_at),
    INDEX idx_user (user_id),
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Sync state - tracks sync progress between local and production
CREATE TABLE IF NOT EXISTS sync_state (
    id INT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
    source ENUM('local', 'website') NOT NULL COMMENT 'Which database this tracks',
    last_synced_edit_id INT UNSIGNED DEFAULT NULL COMMENT 'Last edit ID synced FROM this source',
    last_sync_at TIMESTAMP NULL,

    UNIQUE KEY unique_source (source)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Conflicts - pending conflicts for manual review
CREATE TABLE IF NOT EXISTS conflicts (
    id INT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
    local_edit_id INT UNSIGNED NOT NULL,
    website_edit_id INT UNSIGNED NOT NULL,
    table_name VARCHAR(50) NOT NULL,
    record_id INT UNSIGNED NOT NULL,
    field_name VARCHAR(100) DEFAULT NULL,
    local_value TEXT DEFAULT NULL,
    website_value TEXT DEFAULT NULL,
    status ENUM('pending', 'resolved_local', 'resolved_website', 'resolved_merged') DEFAULT 'pending',
    resolved_value TEXT DEFAULT NULL,
    resolved_by INT UNSIGNED DEFAULT NULL COMMENT 'User who resolved the conflict',
    resolved_at TIMESTAMP NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    INDEX idx_status (status),
    INDEX idx_table_record (table_name, record_id),
    INDEX idx_created (created_at),
    FOREIGN KEY (local_edit_id) REFERENCES edits(id) ON DELETE CASCADE,
    FOREIGN KEY (website_edit_id) REFERENCES edits(id) ON DELETE CASCADE,
    FOREIGN KEY (resolved_by) REFERENCES users(id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ============================================================================
-- GRANTEES (NYSCA Grant Recipients)
-- ============================================================================

-- Grantees table - NYSCA grant recipients for potential website additions
CREATE TABLE IF NOT EXISTS grantees (
    id INT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(255) NOT NULL COMMENT 'Organization name from NYSCA grant list',
    area VARCHAR(100) DEFAULT NULL COMMENT 'NY region (e.g., New York City, Long Island)',
    website_id INT UNSIGNED DEFAULT NULL COMMENT 'Linked website if added to our database',
    exclusion_reason VARCHAR(500) DEFAULT NULL COMMENT 'Why website was not added (if applicable)',
    notes TEXT DEFAULT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

    UNIQUE KEY unique_name (name),
    INDEX idx_area (area),
    INDEX idx_website (website_id),
    FOREIGN KEY (website_id) REFERENCES websites(id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ============================================================================
-- INFRASTRUCTURE
-- ============================================================================

-- Advisory write-lock holder - serializes bulk DB writes across git worktrees
-- (connection-scoped MySQL advisory lock; see pipeline/dblock.py).
CREATE TABLE IF NOT EXISTS db_write_lock_holder (
    lock_name VARCHAR(64) NOT NULL,
    holder VARCHAR(128) DEFAULT NULL COMMENT 'Identifier of the session currently holding the lock',
    taken_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

    PRIMARY KEY (lock_name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

SET FOREIGN_KEY_CHECKS = 1;

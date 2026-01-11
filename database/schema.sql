-- fomo.nyc Database Schema
-- Event venues, websites, and events data

-- Create database if not exists (for local development)
CREATE DATABASE IF NOT EXISTS fomo CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

USE fomo;

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
    lat DECIMAL(10, 6),
    lng DECIMAL(10, 6),
    emoji VARCHAR(10),
    alt_emoji VARCHAR(10),
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

    INDEX idx_location (location_id),
    INDEX idx_alt_name (alternate_name),
    FOREIGN KEY (location_id) REFERENCES locations(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ============================================================================
-- WEBSITES
-- ============================================================================

-- Websites table - stores event source websites for crawling
CREATE TABLE IF NOT EXISTS websites (
    id INT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    base_url VARCHAR(500) DEFAULT NULL COMMENT 'Main website URL (informational, not crawled)',
    crawl_frequency INT UNSIGNED DEFAULT NULL COMMENT 'Days between crawls',
    selector VARCHAR(500) DEFAULT NULL COMMENT 'CSS selector for click-to-load',
    num_clicks INT UNSIGNED DEFAULT NULL COMMENT 'Number of clicks for pagination',
    keywords VARCHAR(255) DEFAULT NULL COMMENT 'URL filter keywords',
    max_pages INT UNSIGNED DEFAULT 30 COMMENT 'Max pages for deep crawl',
    delay_before_return_html INT UNSIGNED DEFAULT NULL COMMENT 'Seconds to wait for JS to render (default: 5)',
    content_filter_threshold DECIMAL(3,2) DEFAULT NULL COMMENT 'Pruning filter threshold 0-1 (NULL disables filter)',
    scan_full_page TINYINT(1) DEFAULT NULL COMMENT 'Scroll full page before capture (default: true)',
    remove_overlay_elements TINYINT(1) DEFAULT NULL COMMENT 'Remove popup/overlay elements (default: true)',
    javascript_enabled TINYINT(1) DEFAULT NULL COMMENT 'Enable JavaScript execution (default: true)',
    text_mode TINYINT(1) DEFAULT NULL COMMENT 'Disable images for text-only crawl (default: true)',
    light_mode TINYINT(1) DEFAULT NULL COMMENT 'Use minimal browser features (default: true)',
    scroll_delay DECIMAL(3,2) DEFAULT NULL COMMENT 'Seconds to pause between scroll steps (default: 0.2)',
    crawl_timeout INT UNSIGNED DEFAULT NULL COMMENT 'Timeout in seconds for entire crawl operation (default: 120)',
    notes TEXT DEFAULT NULL,
    disabled BOOLEAN DEFAULT FALSE COMMENT 'If true, skip this website during crawling',
    force_crawl BOOLEAN DEFAULT FALSE COMMENT 'If true, crawl this website on next run regardless of frequency',
    last_crawled_at TIMESTAMP NULL COMMENT 'When this website was last crawled',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

    INDEX idx_name (name),
    INDEX idx_last_crawled (last_crawled_at),
    INDEX idx_disabled (disabled)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Website URLs (one website can have multiple URLs to crawl)
CREATE TABLE IF NOT EXISTS website_urls (
    id INT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
    website_id INT UNSIGNED NOT NULL,
    url VARCHAR(2000) NOT NULL,
    sort_order INT UNSIGNED DEFAULT 0,

    INDEX idx_website (website_id),
    FOREIGN KEY (website_id) REFERENCES websites(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Website-Location relationship (many-to-many)
CREATE TABLE IF NOT EXISTS website_locations (
    id INT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
    website_id INT UNSIGNED NOT NULL,
    location_id INT UNSIGNED NOT NULL,

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
    lat DECIMAL(10, 6),
    lng DECIMAL(10, 6),
    website_id INT UNSIGNED DEFAULT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

    INDEX idx_name (name(255)),
    INDEX idx_location (location_id),
    INDEX idx_website (website_id),
    INDEX idx_coords (lat, lng),
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

-- ============================================================================
-- TAGS (Generic - used by locations and events)
-- ============================================================================

-- Tags table - stores unique tag values
CREATE TABLE IF NOT EXISTS tags (
    id INT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(100) NOT NULL,

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
    lat DECIMAL(10, 6),
    lng DECIMAL(10, 6),
    url VARCHAR(2000) DEFAULT NULL COMMENT 'Primary event URL',
    raw_data JSON DEFAULT NULL COMMENT 'Full JSON object from crawl',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    INDEX idx_crawl_result (crawl_result_id),
    INDEX idx_name (name(255)),
    INDEX idx_location_name (location_name),
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

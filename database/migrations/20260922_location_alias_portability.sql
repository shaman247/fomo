-- Run before deploying the accompanying db.py / processor.py changes.
-- No city-specific decisions: existing aliases retain their current behavior.
ALTER TABLE location_alternate_names
    ADD COLUMN IF NOT EXISTS portable TINYINT(1) NOT NULL DEFAULT 1
    COMMENT 'Allow exact fallback from other websites; disable for branch-specific shorthand';

CREATE TABLE IF NOT EXISTS location_match_policies (
    location_id INT UNSIGNED NOT NULL PRIMARY KEY,
    ambiguous_bare_names JSON NOT NULL COMMENT 'Reviewed source spellings that must not prefix/fuzzy match a branch',
    FOREIGN KEY (location_id) REFERENCES locations(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

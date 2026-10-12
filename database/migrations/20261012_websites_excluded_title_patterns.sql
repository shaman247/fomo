-- BL37: per-site title exclusions applied before chunking (extractor.drop_excluded_records).
ALTER TABLE websites
    ADD COLUMN IF NOT EXISTS excluded_title_patterns TEXT DEFAULT NULL
    COMMENT 'One case-insensitive regex per line. Before chunking, the extractor drops every markdown heading record (heading to next heading) whose title matches, so cards the site always lists but never as events (recurring food/drink specials) never reach a packet. Anchor patterns (^...$) so a real event sharing a word survives. Rationale: database/extraction_settings_rationale.md'
    AFTER blocked_location_names;

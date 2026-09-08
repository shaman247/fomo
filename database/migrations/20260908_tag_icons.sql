ALTER TABLE tags ADD COLUMN IF NOT EXISTS icon_id VARCHAR(64) CHARACTER SET ascii COLLATE ascii_bin DEFAULT NULL COMMENT 'Optional custom icon catalog ID; emoji remains the Unicode fallback';

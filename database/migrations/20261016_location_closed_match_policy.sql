-- Run before deploying the accompanying db.py / processor.py changes.
-- A closed venue (description "Permanently closed <Month YYYY>. Formerly ...")
-- keeps its row for history, but must stop capturing NEW crawl_events by its
-- street address or its global names: the address usually has a successor
-- tenant, and the old name only appears in stale listings. Website-scoped
-- aliases, website links and reviewed event_venue_overrides still resolve.
-- No city-specific decisions here; mark venues with
--   INSERT INTO location_match_policies (location_id, ambiguous_bare_names, closed)
--   VALUES (<id>, '[]', 1) ON DUPLICATE KEY UPDATE closed = 1;
ALTER TABLE location_match_policies
    ADD COLUMN IF NOT EXISTS closed TINYINT(1) NOT NULL DEFAULT 0
    COMMENT 'Venue permanently closed: new crawl_events never resolve to it by address, name, alias, short name, prefix or fuzzy match. Website-scoped alternate names, website links and event_venue_overrides still apply';

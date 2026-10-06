-- Source/title/URL/date-bounded venue reviews may explicitly preserve TBD.
ALTER TABLE event_venue_overrides MODIFY location_id INT UNSIGNED DEFAULT NULL
    COMMENT 'NULL explicitly preserves a reviewed unknown venue';

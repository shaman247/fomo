-- Agent reviews are distinct from protected human/editorial manual choices.
ALTER TABLE event_icon_assignments MODIFY COLUMN origin ENUM('rule','manual','agent') NOT NULL;

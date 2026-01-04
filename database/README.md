# fomo.nyc Database

MariaDB/MySQL database for storing locations, websites, and events data.

## Prerequisites

- **XAMPP** (local development) or MariaDB/MySQL server
- **Python 3.8+** with `mysql-connector-python`

Install the Python MySQL connector:

```bash
pip install mysql-connector-python
```

## Database Configuration

The database uses the same credentials as the PHP API (`public_html/api/config.php`):

| Environment | Database | User | Host |
|-------------|----------|------|------|
| Local (XAMPP) | `fomo` | `root` | `localhost` |
| Production | `fomoowsq_fomo` | `fomoowsq_root` | `localhost` |

Set the `FOMO_ENV` environment variable to switch environments:
- `local` (default) - Uses XAMPP credentials
- `production` - Uses production credentials

## Schema Overview

### Core Data Model
```
┌─────────────┐     ┌─────────────────┐     ┌──────────────┐
│  locations  │────<│ website_locations│>────│   websites   │
└─────────────┘     └─────────────────┘     └──────────────┘
       │                                            │
       │ 1:N                                   1:N  │ 1:N
       ▼                                            ▼
┌─────────────────────┐                    ┌──────────────┐
│location_alternate_  │                    │ website_urls │
│      names          │                    ├──────────────┤
└─────────────────────┘                    │ website_tags │
                                           └──────────────┘
       │
       │                    ┌──────────┐
       │                    │  events  │───────────────────┐
       │                    └──────────┘                   │
       │                         │                         │
       │                    1:N  │  1:N                    │
       │                         ▼                         ▼
       │              ┌──────────────────┐       ┌────────────┐
       │              │event_occurrences │       │ event_urls │
       │              └──────────────────┘       └────────────┘
       │
       ▼
┌────────────────┐          ┌──────┐          ┌─────────────┐
│ location_tags  │─────────>│ tags │<─────────│ event_tags  │
└────────────────┘          └──────┘          └─────────────┘
```

### Crawl Pipeline Data Model
```
┌─────────────┐
│ crawl_runs  │  (daily crawl batch, e.g., 20251203)
└─────────────┘
       │
       │ 1:N
       ▼
┌───────────────┐
│ crawl_results │  (per-website output, e.g., cocusocial.json)
└───────────────┘
       │
       │ 1:N
       ▼
┌──────────────┐──────────────┬──────────────────────┐
│ crawl_events │              │                      │
└──────────────┘              │                      │
       │                      │ 1:N                  │ 1:N
       │                      ▼                      ▼
       │         ┌────────────────────────┐  ┌─────────────────┐
       │         │ crawl_event_occurrences│  │ crawl_event_tags│
       │         └────────────────────────┘  └─────────────────┘
       │
       │ N:M (via event_sources)
       ▼
┌──────────┐
│  events  │  (deduplicated final events)
└──────────┘
```

The crawl pipeline stores raw extracted events in `crawl_events`, then deduplicates
and merges them into the final `events` table. The `event_sources` junction table
tracks which crawl events contributed to each final event.

## Tables

### `locations`
Venue/location information for events.

| Column | Type | Description |
|--------|------|-------------|
| `id` | INT UNSIGNED | Primary key (matches JSON id) |
| `name` | VARCHAR(255) | Location name |
| `address` | VARCHAR(500) | Full address |
| `lat` | DECIMAL(10,6) | Latitude |
| `lng` | DECIMAL(10,6) | Longitude |
| `emoji` | VARCHAR(10) | Primary emoji |
| `alt_emoji` | VARCHAR(10) | Alternative emoji |
| `created_at` | TIMESTAMP | Record creation time |
| `updated_at` | TIMESTAMP | Last update time |

### `location_alternate_names`
Alternative names for locations.

| Column | Type | Description |
|--------|------|-------------|
| `id` | INT UNSIGNED | Auto-increment primary key |
| `location_id` | INT UNSIGNED | Foreign key to locations |
| `alternate_name` | VARCHAR(255) | Alternative name |

### `websites`
Event source websites for crawling.

| Column | Type | Description |
|--------|------|-------------|
| `id` | INT UNSIGNED | Primary key (matches JSON id) |
| `name` | VARCHAR(255) | Website name |
| `crawl_frequency` | INT UNSIGNED | Days between crawls |
| `selector` | VARCHAR(500) | CSS selector for click-to-load |
| `num_clicks` | INT UNSIGNED | Number of pagination clicks |
| `keywords` | VARCHAR(255) | URL filter keywords |
| `notes` | TEXT | Internal notes |
| `created_at` | TIMESTAMP | Record creation time |
| `updated_at` | TIMESTAMP | Last update time |

### `website_urls`
URLs to crawl for each website.

| Column | Type | Description |
|--------|------|-------------|
| `id` | INT UNSIGNED | Auto-increment primary key |
| `website_id` | INT UNSIGNED | Foreign key to websites |
| `url` | VARCHAR(2000) | URL to crawl |
| `sort_order` | INT UNSIGNED | Order of URLs |

### `website_locations`
Many-to-many relationship between websites and locations.

| Column | Type | Description |
|--------|------|-------------|
| `id` | INT UNSIGNED | Auto-increment primary key |
| `website_id` | INT UNSIGNED | Foreign key to websites |
| `location_id` | INT UNSIGNED | Foreign key to locations |

### `website_tags`
Extra tags to apply to all events from a website (e.g., Community Board tags).

| Column | Type | Description |
|--------|------|-------------|
| `id` | INT UNSIGNED | Auto-increment primary key |
| `website_id` | INT UNSIGNED | Foreign key to websites |
| `tag` | VARCHAR(100) | Tag to apply to events |

These tags are automatically added to every event extracted from the website during processing.

### `events`
Individual events.

| Column | Type | Description |
|--------|------|-------------|
| `id` | INT UNSIGNED | Auto-increment primary key |
| `name` | VARCHAR(500) | Event name |
| `short_name` | VARCHAR(255) | Short display name |
| `description` | TEXT | Event description |
| `emoji` | VARCHAR(10) | Event emoji |
| `location_id` | INT UNSIGNED | Foreign key to locations (nullable) |
| `location_name` | VARCHAR(255) | Original location name from source |
| `sublocation` | VARCHAR(255) | Room, floor, etc. |
| `lat` | DECIMAL(10,6) | Latitude |
| `lng` | DECIMAL(10,6) | Longitude |
| `website_id` | INT UNSIGNED | Foreign key to websites (nullable) |
| `created_at` | TIMESTAMP | Record creation time |
| `updated_at` | TIMESTAMP | Last update time |

### `event_occurrences`
Date/time occurrences for events (one event can have multiple dates).

| Column | Type | Description |
|--------|------|-------------|
| `id` | INT UNSIGNED | Auto-increment primary key |
| `event_id` | INT UNSIGNED | Foreign key to events |
| `start_date` | DATE | Start date |
| `start_time` | VARCHAR(20) | Start time (e.g., "7pm") |
| `end_date` | DATE | End date (nullable) |
| `end_time` | VARCHAR(20) | End time (nullable) |
| `sort_order` | INT UNSIGNED | Order of occurrences |

### `event_urls`
Source URLs for events.

| Column | Type | Description |
|--------|------|-------------|
| `id` | INT UNSIGNED | Auto-increment primary key |
| `event_id` | INT UNSIGNED | Foreign key to events |
| `url` | VARCHAR(2000) | Source URL |
| `sort_order` | INT UNSIGNED | Order of URLs |

### `tags`
Unique tag values shared by locations and events.

| Column | Type | Description |
|--------|------|-------------|
| `id` | INT UNSIGNED | Auto-increment primary key |
| `name` | VARCHAR(100) | Tag name (unique) |

### `location_tags`
Many-to-many relationship between locations and tags.

| Column | Type | Description |
|--------|------|-------------|
| `id` | INT UNSIGNED | Auto-increment primary key |
| `location_id` | INT UNSIGNED | Foreign key to locations |
| `tag_id` | INT UNSIGNED | Foreign key to tags |

### `event_tags`
Many-to-many relationship between events and tags.

| Column | Type | Description |
|--------|------|-------------|
| `id` | INT UNSIGNED | Auto-increment primary key |
| `event_id` | INT UNSIGNED | Foreign key to events |
| `tag_id` | INT UNSIGNED | Foreign key to tags |

### `crawl_runs`
Represents a daily crawl batch (corresponds to a YYYYMMDD folder in `event_data/processed/`).

| Column | Type | Description |
|--------|------|-------------|
| `id` | INT UNSIGNED | Auto-increment primary key |
| `run_date` | DATE | The date of the crawl run |
| `status` | ENUM | Status: running, completed, failed |
| `started_at` | TIMESTAMP | When the crawl started |
| `completed_at` | TIMESTAMP | When the crawl completed (nullable) |
| `notes` | TEXT | Optional notes |

### `crawl_results`
Per-website crawl output within a run (corresponds to a JSON file like `cocusocial.json`).

| Column | Type | Description |
|--------|------|-------------|
| `id` | INT UNSIGNED | Auto-increment primary key |
| `crawl_run_id` | INT UNSIGNED | Foreign key to crawl_runs |
| `website_id` | INT UNSIGNED | Matched website (nullable) |
| `filename` | VARCHAR(255) | Original filename |
| `event_count` | INT UNSIGNED | Number of events extracted |
| `status` | ENUM | Status: pending, crawled, extracted, processed, failed |
| `crawled_at` | TIMESTAMP | When HTML was crawled |
| `extracted_at` | TIMESTAMP | When events were extracted |
| `processed_at` | TIMESTAMP | When events were processed |
| `error_message` | TEXT | Error message if failed |
| `created_at` | TIMESTAMP | Record creation time |

### `crawl_events`
Individual events extracted from a crawl result (raw data before deduplication).

| Column | Type | Description |
|--------|------|-------------|
| `id` | INT UNSIGNED | Auto-increment primary key |
| `crawl_result_id` | INT UNSIGNED | Foreign key to crawl_results |
| `name` | VARCHAR(500) | Event name |
| `short_name` | VARCHAR(255) | Short display name |
| `description` | TEXT | Event description |
| `emoji` | VARCHAR(10) | Event emoji |
| `location_name` | VARCHAR(255) | Raw location name from crawl |
| `sublocation` | VARCHAR(255) | Room, floor, etc. |
| `lat` | DECIMAL(10,6) | Latitude |
| `lng` | DECIMAL(10,6) | Longitude |
| `url` | VARCHAR(2000) | Primary event URL |
| `raw_data` | JSON | Full JSON object from crawl |
| `created_at` | TIMESTAMP | Record creation time |

### `crawl_event_occurrences`
Date/time occurrences for crawl events.

| Column | Type | Description |
|--------|------|-------------|
| `id` | INT UNSIGNED | Auto-increment primary key |
| `crawl_event_id` | INT UNSIGNED | Foreign key to crawl_events |
| `start_date` | DATE | Start date |
| `start_time` | VARCHAR(20) | Start time |
| `end_date` | DATE | End date (nullable) |
| `end_time` | VARCHAR(20) | End time (nullable) |
| `sort_order` | INT UNSIGNED | Order of occurrences |

### `crawl_event_tags`
Tags for crawl events (raw strings, not normalized).

| Column | Type | Description |
|--------|------|-------------|
| `id` | INT UNSIGNED | Auto-increment primary key |
| `crawl_event_id` | INT UNSIGNED | Foreign key to crawl_events |
| `tag` | VARCHAR(100) | Raw tag string |

### `event_sources`
Links final events to the crawl events that contributed to them (for provenance tracking).

| Column | Type | Description |
|--------|------|-------------|
| `id` | INT UNSIGNED | Auto-increment primary key |
| `event_id` | INT UNSIGNED | Foreign key to events |
| `crawl_event_id` | INT UNSIGNED | Foreign key to crawl_events |
| `is_primary` | BOOLEAN | Is this the primary/first source |
| `created_at` | TIMESTAMP | Record creation time |

### `tag_rules`
Rules for processing tags extracted from events.

| Column | Type | Description |
|--------|------|-------------|
| `id` | INT UNSIGNED | Auto-increment primary key |
| `rule_type` | ENUM | Type: rewrite, exclude, or remove |
| `pattern` | VARCHAR(100) | Tag pattern to match (lowercase) |
| `replacement` | VARCHAR(100) | Replacement tag (only for rewrite rules) |
| `created_at` | TIMESTAMP | Record creation time |

Rule types:
- **rewrite**: Map a tag to a different/canonical form (e.g., "lgbtq+" → "LGBTQ")
- **exclude**: Filter out the tag entirely (e.g., generic "nyc", "events")
- **remove**: Skip the entire event if it has this tag (e.g., "canceled", "privateevent")

### `feedback`
User feedback submitted via the website.

| Column | Type | Description |
|--------|------|-------------|
| `id` | INT UNSIGNED | Auto-increment primary key |
| `message` | TEXT | Feedback message |
| `user_agent` | VARCHAR(500) | Browser user agent |
| `page_url` | VARCHAR(500) | Page URL where feedback was submitted |
| `created_at` | TIMESTAMP | Record creation time |

### `users`
Optional user accounts for tracking edits (authentication is optional).

| Column | Type | Description |
|--------|------|-------------|
| `id` | INT UNSIGNED | Auto-increment primary key |
| `email` | VARCHAR(255) | User email (unique) |
| `display_name` | VARCHAR(100) | Display name |
| `password_hash` | VARCHAR(255) | Bcrypt password hash |
| `is_admin` | BOOLEAN | Admin flag |
| `created_at` | TIMESTAMP | Account creation time |
| `last_login_at` | TIMESTAMP | Last login time |

### `edits`
Immutable edit log for tracking all changes to core tables. Used for sync and audit.

| Column | Type | Description |
|--------|------|-------------|
| `id` | INT UNSIGNED | Auto-increment primary key |
| `edit_uuid` | CHAR(36) | UUID for global uniqueness across databases |
| `table_name` | VARCHAR(50) | Table that was edited |
| `record_id` | INT UNSIGNED | ID of the edited record |
| `field_name` | VARCHAR(100) | Field name (NULL for INSERT/DELETE) |
| `action` | ENUM | INSERT, UPDATE, or DELETE |
| `old_value` | TEXT | Previous value (NULL for INSERT) |
| `new_value` | TEXT | New value (NULL for DELETE) |
| `source` | ENUM | Origin: local, website, or crawl |
| `user_id` | INT UNSIGNED | Foreign key to users (NULL if anonymous) |
| `editor_ip` | VARCHAR(45) | IP address for anonymous edits |
| `editor_user_agent` | VARCHAR(500) | Browser user agent |
| `editor_info` | VARCHAR(500) | Additional context (e.g., "crawl_run:123") |
| `created_at` | TIMESTAMP | When edit was created |
| `applied_at` | TIMESTAMP | When edit was applied (NULL if pending) |

### `sync_state`
Tracks sync progress between local and production databases.

| Column | Type | Description |
|--------|------|-------------|
| `id` | INT UNSIGNED | Auto-increment primary key |
| `source` | ENUM | Which database: local or website |
| `last_synced_edit_id` | INT UNSIGNED | Last edit ID synced from this source |
| `last_sync_at` | TIMESTAMP | When last sync occurred |

### `conflicts`
Pending conflicts for manual review during sync.

| Column | Type | Description |
|--------|------|-------------|
| `id` | INT UNSIGNED | Auto-increment primary key |
| `local_edit_id` | INT UNSIGNED | Foreign key to local edit |
| `website_edit_id` | INT UNSIGNED | Foreign key to website edit |
| `table_name` | VARCHAR(50) | Table with conflict |
| `record_id` | INT UNSIGNED | Record with conflict |
| `field_name` | VARCHAR(100) | Field with conflict |
| `local_value` | TEXT | Value from local database |
| `website_value` | TEXT | Value from website |
| `status` | ENUM | pending, resolved_local, resolved_website, resolved_merged |
| `resolved_value` | TEXT | Final resolved value |
| `resolved_by` | INT UNSIGNED | Foreign key to user who resolved |
| `resolved_at` | TIMESTAMP | When conflict was resolved |
| `created_at` | TIMESTAMP | When conflict was detected |

## Setup

### 1. Start XAMPP

Make sure Apache and MySQL are running in XAMPP Control Panel.

### 2. Restore from Backup (Recommended)

New developers should restore from a database backup to get all existing data:

```bash
# 1. Create the database
mysql -u root -e "CREATE DATABASE fomo CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"

# 2. Restore from backup
mysql -u root fomo < database/backups/fomo_backup_YYYYMMDD.sql

# 3. Run migrations if schema has changed since the backup
python database/migrate_schema.py
```

### Alternative: Create Empty Schema

If you need an empty database (e.g., for testing):

```bash
cd database
python setup.py
```

This creates the `fomo` database and all tables, but with no data.

Use `python setup.py --drop-tables` to drop and recreate all tables (WARNING: deletes all data).

### Creating Backups

```bash
# Windows (XAMPP)
"C:/xampp/mysql/bin/mysqldump.exe" -u root fomo > database/backups/fomo_backup_YYYYMMDD.sql

# Linux/Mac
mysqldump -u root fomo > database/backups/fomo_backup_YYYYMMDD.sql
```

### Production Environment

```bash
# Windows
set FOMO_ENV=production
python setup.py

# Unix/Mac
FOMO_ENV=production python setup.py
```

## Sample Queries

```sql
-- Get all locations in Brooklyn
SELECT l.*
FROM locations l
JOIN location_tags lt ON l.id = lt.location_id
JOIN tags t ON lt.tag_id = t.id
WHERE t.name = 'Brooklyn';

-- Search by name or alternate name
SELECT DISTINCT l.*
FROM locations l
LEFT JOIN location_alternate_names a ON l.id = a.location_id
WHERE l.name LIKE '%Library%' OR a.alternate_name LIKE '%Library%';

-- Get all tags for a location
SELECT t.name
FROM tags t
JOIN location_tags lt ON t.id = lt.tag_id
WHERE lt.location_id = 1;

-- Get upcoming events with their occurrences
SELECT e.name, e.emoji, eo.start_date, eo.start_time, e.location_name
FROM events e
JOIN event_occurrences eo ON e.id = eo.event_id
WHERE eo.start_date >= CURDATE()
ORDER BY eo.start_date, eo.start_time;

-- Get events by tag
SELECT DISTINCT e.*
FROM events e
JOIN event_tags et ON e.id = et.event_id
JOIN tags t ON et.tag_id = t.id
WHERE t.name = 'Theater';

-- Count events by location
SELECT e.location_name, COUNT(*) as event_count
FROM events e
GROUP BY e.location_name
ORDER BY event_count DESC
LIMIT 10;

-- Get websites with their crawl URLs
SELECT w.name, wu.url
FROM websites w
JOIN website_urls wu ON w.id = wu.website_id
ORDER BY w.name, wu.sort_order;

-- Find shared tags between locations and events
SELECT t.name,
       COUNT(DISTINCT lt.location_id) as location_count,
       COUNT(DISTINCT et.event_id) as event_count
FROM tags t
LEFT JOIN location_tags lt ON t.id = lt.tag_id
LEFT JOIN event_tags et ON t.id = et.tag_id
GROUP BY t.id, t.name
HAVING location_count > 0 AND event_count > 0
ORDER BY location_count + event_count DESC;

-- Get recent edits
SELECT e.table_name, e.record_id, e.action, e.field_name, e.source, e.created_at
FROM edits e
ORDER BY e.created_at DESC
LIMIT 20;

-- Get edit history for a specific record
SELECT e.action, e.field_name, e.old_value, e.new_value, e.source, e.created_at
FROM edits e
WHERE e.table_name = 'locations' AND e.record_id = 123
ORDER BY e.created_at DESC;

-- Get pending sync conflicts
SELECT c.table_name, c.record_id, c.field_name, c.local_value, c.website_value
FROM conflicts c
WHERE c.status = 'pending';
```

## Bidirectional Sync

The database supports bidirectional sync between local and production, with edit history and conflict resolution.

### How It Works

1. **Edit Logging**: All changes to core tables are logged in the `edits` table with a UUID
2. **Sync Protocol**: The `sync_bidirectional.py` script exchanges edit logs between databases
3. **Conflict Detection**: When the same field is edited in both databases, a conflict is created
4. **Manual Resolution**: Conflicts are reviewed and resolved via the admin UI

### Sync Commands

```bash
# Full bidirectional sync
python scripts/sync_bidirectional.py

# Preview what would be synced (dry run)
python scripts/sync_bidirectional.py --dry-run

# Only pull edits from production
python scripts/sync_bidirectional.py --pull-only

# Only push local edits to production
python scripts/sync_bidirectional.py --push-only

# Show sync status
python scripts/sync_bidirectional.py --status
```

### Environment Variables

Add to `.env` for sync:

```
PROD_API_URL=https://fomo.nyc/api
SYNC_API_KEY=your-secret-key
```

### Edit Logger (Python)

Use the edit logger to track changes in Python code:

```python
from database.edit_logger import EditLogger

# Create logger
logger = EditLogger(cursor, connection, source='local', editor_info='manual')

# Log an insert
logger.log_insert('locations', new_id, {'name': 'Central Park', 'lat': 40.785})

# Log an update
logger.log_update('locations', 123, 'name', 'Old Name', 'New Name')

# Log a delete
logger.log_delete('locations', 123, {'name': 'Central Park', ...})

# Get edits since ID
edits = logger.get_edits_since(100, source='website')
```

### Tracked Tables

The following tables have their edits logged:
- `locations`, `location_alternate_names`, `location_tags`
- `websites`, `website_urls`, `website_locations`, `website_tags`
- `events`, `event_occurrences`, `event_urls`, `event_tags`
- `tags`, `tag_rules`

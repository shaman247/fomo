# Fomo Admin Dashboard

A single-page admin interface for managing the fomo.nyc event aggregation system.

## Overview

The admin dashboard provides a unified view of:
- **Websites** - Event sources with crawl status and history
- **Locations** - Venues with coordinates and linked websites
- **Events** - Aggregated events from all sources
- **Tags** - Event categorization and tag statistics
- **Conflicts** - Sync conflict resolution between local and production databases
- **History** - Edit history viewer with revert capability

## Features

### Single-Page Navigation
All interactions (tab switching, sorting, filtering, pagination) happen via AJAX without page reloads. The URL remains static at `/admin/`.

### Detail Panel
Click any row to open a detail panel on the right showing comprehensive information. The panel supports:
- **Cross-entity navigation** - Click linked entities (locations, websites, tags, events) to navigate between them
- **History navigation** - Back/forward buttons (`<` `>`) and keyboard shortcuts
- **Persistent state** - Panel stays open when switching tabs or sorting

### Keyboard Shortcuts
| Key | Action |
|-----|--------|
| `Escape` | Close detail panel |
| `Alt + ←` | Navigate back in detail history |
| `Alt + →` | Navigate forward in detail history |

## File Structure

```
admin/
├── index.php            # Main SPA entry point
├── admin.js             # Client-side JavaScript
├── admin.css            # Styles
├── db_config.php        # Database connection and helpers
├── websites_detail.php  # Website detail fragment
├── locations_detail.php # Location detail fragment
├── events_detail.php    # Event detail fragment
├── tags_detail.php      # Tag detail fragment
├── conflicts.php        # Sync conflict review page
├── conflicts_api.php    # Conflict resolution API
├── history.php          # Edit history viewer
└── history_api.php      # Edit history API
```

## Architecture

### PHP Backend
- `index.php` handles both initial page load and AJAX requests (`?ajax=1`)
- AJAX requests return JSON with `toolbar`, `table`, `rowsData`, and metadata
- Detail pages return HTML fragments loaded into the detail panel

### JavaScript Frontend
- `tabState` tracks sort, filter, and pagination state per tab
- `tabCache` caches fetched tab data for instant switching
- `detailHistory` maintains navigation history for back/forward
- Prefetching loads other tabs in background after initial load

### CSS
- Dark theme with CSS custom properties
- Hidden scrollbars (content still scrollable)
- Responsive detail panel (fixed 420px width)

## Database Tables Used

- `websites` - Crawl sources
- `locations` - Venue data
- `events` - Deduplicated events
- `event_occurrences` - Event dates/times
- `event_tags` / `tags` - Tag associations
- `crawl_runs` / `crawl_results` - Crawl history
- `website_locations` - Website-location links
- `edits` - Immutable edit log for all changes
- `conflicts` - Pending sync conflicts for review
- `sync_state` - Tracks last synced edit ID per source
- `users` - Optional user accounts

## Conflict Resolution

The conflict resolution page (`/admin/conflicts.php`) allows you to review and resolve sync conflicts between local and production databases.

### Accessing Conflicts

Navigate to `/admin/conflicts.php` or use the API directly:

```
GET /admin/conflicts_api.php?action=list&status=pending
GET /admin/conflicts_api.php?action=get&id=123
POST /admin/conflicts_api.php?action=resolve
POST /admin/conflicts_api.php?action=batch_resolve
```

### Conflict States

- **pending** - Needs manual review
- **resolved_local** - Kept the local value
- **resolved_website** - Kept the website value
- **resolved_merged** - Used a custom merged value

### Resolution Options

1. **Keep Local** - Apply the local database value
2. **Keep Website** - Keep the production website value (no database change needed)
3. **Custom Merge** - Enter a custom merged value

### Batch Operations

Select multiple pending conflicts and resolve them all with the same choice (local or website).

## Edit History

The edit history page (`/admin/history.php`) shows a timeline of all changes across the system.

### Viewing History

- **Recent edits** - View all recent changes across tables
- **Record history** - View history for a specific record

### API Endpoints

```
GET /admin/history_api.php?table=locations&id=123  # History for specific record
GET /admin/history_api.php?recent=1                # Recent edits
GET /admin/history_api.php?recent=1&source=local   # Filter by source
GET /admin/history_api.php?recent=1&filter_table=events  # Filter by table
POST /admin/history_api.php?action=revert          # Revert an edit
```

### Reverting Edits

Click the revert button on any UPDATE edit to restore the previous value. This creates a new edit record logging the revert.

Note: INSERT reverts will delete the record. DELETE reverts are not supported (record data not preserved).

## Bidirectional Sync

The admin tools work with the bidirectional sync system. See `database/README.md` for full sync documentation.

### Quick Reference

```bash
# Check sync status
python scripts/sync_bidirectional.py --status

# Preview what would sync
python scripts/sync_bidirectional.py --dry-run

# Run full sync
python scripts/sync_bidirectional.py

# Pull only (from production)
python scripts/sync_bidirectional.py --pull-only

# Push only (to production)
python scripts/sync_bidirectional.py --push-only
```

After syncing, check `/admin/conflicts.php` to resolve any conflicts.

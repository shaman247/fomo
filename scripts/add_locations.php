#!/usr/bin/env php
<?php
/**
 * Add new locations to the local database
 *
 * Usage:
 *   php scripts/add_locations.php                    # Add to local database
 *   php scripts/add_locations.php --dry-run         # Show what would be added
 *
 * Edit the $new_locations array below to specify locations to add.
 *
 * CLEANUP: After a successful run, REMOVE the entries you just added from
 * $new_locations so the array stays empty between sessions. Stale entries
 * clutter dry-runs (everything reports "already exists") and obscure the
 * next addition. Re-running with the same entries is a no-op, but they
 * should still be deleted as part of finishing the task.
 */

// ============================================================================
// EDIT THIS ARRAY TO ADD NEW LOCATIONS
// ============================================================================
$new_locations = [
];

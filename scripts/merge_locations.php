#!/usr/bin/env php
<?php
/**
 * Merge duplicate locations into their canonical versions
 *
 * Usage:
 *   php scripts/merge_locations.php                    # Merge in local database
 *   php scripts/merge_locations.php --production       # Merge in production database
 *   php scripts/merge_locations.php --dry-run          # Show what would be merged
 *
 * This script:
 * 1. Updates all references to the duplicate location to point to the keeper
 * 2. Adds the duplicate's name as an alternate name (if not already present)
 * 3. Merges tags from duplicate to keeper
 * 4. Deletes the duplicate location
 */

// ============================================================================
// DUPLICATE PAIRS TO MERGE: [duplicate_id => keeper_id]
// The duplicate will be merged INTO the keeper, then deleted
// ============================================================================
$merge_pairs = [
    // === BATCH 1: Original user-identified duplicates (already merged) ===
    // 2623 => 222,    // Coney Island USA -> Coney Island
    // 2817 => 2215,   // The Forum at Columbia -> The Bollinger Forum
    // 2768 => 1529,   // The Morbid Anatomy Library -> Morbid Anatomy Library & Giftshop
    // 2777 => 2357,   // Brewer's Row -> Brewer's Row Beer Bar & Bottle Shop
    // 2713 => 451,    // Hunter College -> Kaye Playhouse at Hunter College
    // 2621 => 855,    // The Spare Room at The Gutter -> The Gutter
    // 2670 => 2414,   // Devoción (Williamsburg) -> Devocíon (Williamsburg)
    // 2648 => 2585,   // Jade -> Jade Bar

    // === BATCH 2: "The" prefix variations ===
    // 822 => 99,      // The Billie Holiday Theatre -> Billie Holiday Theatre - DONE
    // 830 => 186,     // The Center for Fiction -> Center for Fiction - DONE
    // 1868 => 865,    // Louis Armstrong House Museum -> The Louis Armstrong House Museum - DONE
    // 866 => 514,     // The Magnet Theater -> Magnet Theater - DONE
    // 1878 => 1267,   // The Museum of Food and Drink -> Museum of Food and Drink - DONE
    // 1886 => 610,    // The New York Public Library for... -> New York Public Library for... - DONE
    // 1271 => 899,    // Tenement Museum -> The Tenement Museum - DONE

    // === BATCH 3: Same location, name variations ===
    // 1233 => 20,     // A.I.R. -> A.I.R. Gallery - DONE
    // 1381 => 89,     // Bed Stuy Farmstand -> Bed-Stuy Farmstand - DONE
    // 2355 => 1090,   // The Tiny Cupboard -> The Tiny Cupboard Comedy Club - DONE
    // 2231 => 1424,   // Sound + Fury Brewery -> Sound + Fury Brewery and Kitchen - DONE
    // 2356 => 1434,   // Fifth Hammer Brewing -> Fifth Hammer Brewing Co. - DONE
    // 719 => 591,     // Rockefeller Park -> Nelson A. Rockefeller Park - DONE
    // 1890 => 605,    // NYSCI -> New York Hall of Science - DONE
    // 1478 => 833,    // City Reliquary Museum -> The City Reliquary - DONE
    // 2360 => 1318,   // Museum of Street Art -> Musem of Street Art (MoSA) - DONE
    // 1895 => 1560,   // The Renee and Chaim Gross Foundation -> Renee & Chaim Gross Foundation - DONE

    // === BATCH 4: Library Learning Center pairs ===
    // 277 => 276,     // Eastern Parkway Library -> Eastern Parkway Learning Center - DONE
    // 298 => 297,     // Flatbush Library -> Flatbush Learning Center - DONE

    // === BATCH 5: Same venue, different naming ===
    // 684 => 481,     // Prospect Park Bandshell -> Lena Horne Bandshell, Prospect Park - DONE
    // 2448 => 625,    // NYU Skirball Center -> NYU Skirball Center for the Performing Arts - DONE
    // 1019 => 816,    // Terrace Books -> Terrace Books (Community Bookstore annex) - DONE
    // 2483 => 2441,   // Residence Inn by Marriott Times Square -> Residence Inn Times Square - DONE

    // === BATCH 6: Playground/fieldhouse pair ===
    // 62 => 61,       // Austin J. McDonald Playground Fieldhouse -> Austin J. McDonald Playground - DONE

    // === BATCH 7: 620 Loft typo ===
    // 1446 => 1447,   // 610 Loft & Garden -> 620 Loft & Garden (typo fix) - DONE

    // === BATCH 8: Library consolidations ===
    189 => 151,     // Central Library -> Brooklyn Public Library (Central Library)
    190 => 151,     // Central Library Learning Center -> Brooklyn Public Library (Central Library)
    793 => 609,     // Stephen A. Schwarzman Building -> New York Public Library - Stephen A. Schwarzman Building
];

// ============================================================================
// DATABASE CONFIGURATION
// ============================================================================
$config = [
    'local' => [
        'host' => 'localhost',
        'port' => 3306,
        'dbname' => 'fomo',
        'user' => 'root',
        'password' => '',
    ],
    'production' => [
        'via_ssh' => true,
        'ssh_host' => '69.57.162.203',
        'ssh_port' => 21098,
        'ssh_user' => 'fomoowsq',
        'ssh_key' => __DIR__ . '/id_rsa_sync',
        'dbname' => 'fomoowsq_fomo',
        'user' => 'fomoowsq_root',
        'password' => 'REDACTED_DB_PASSWORD',
    ],
];

// ============================================================================
// SCRIPT LOGIC
// ============================================================================

$is_production = in_array('--production', $argv) || in_array('-p', $argv);
$is_dry_run = in_array('--dry-run', $argv) || in_array('-n', $argv);
$show_help = in_array('--help', $argv) || in_array('-h', $argv);

if ($show_help) {
    echo <<<HELP
Merge duplicate locations into their canonical versions

Usage:
  php scripts/merge_locations.php [options]

Options:
  --production, -p    Merge in production database (default: local)
  --dry-run, -n       Show what would be merged without making changes
  --help, -h          Show this help message

This script updates all foreign key references, merges tags and alternate names,
then deletes the duplicate location.

HELP;
    exit(0);
}

$env = $is_production ? 'production' : 'local';
$db_config = $config[$env];

echo "=== Merge Locations Script ===\n";
echo "Target: " . strtoupper($env) . " database\n";
echo "Mode: " . ($is_dry_run ? "DRY RUN (no changes will be made)" : "LIVE") . "\n";
echo "\n";

if (empty($merge_pairs)) {
    echo "No merge pairs defined.\n";
    exit(0);
}

// Connect to database
$port = $db_config['port'] ?? 3306;
try {
    $dsn = "mysql:host={$db_config['host']};port={$port};dbname={$db_config['dbname']};charset=utf8mb4";
    $pdo = new PDO($dsn, $db_config['user'], $db_config['password'], [
        PDO::ATTR_ERRMODE => PDO::ERRMODE_EXCEPTION,
        PDO::MYSQL_ATTR_INIT_COMMAND => "SET NAMES utf8mb4"
    ]);
    echo "Connected to $env database\n\n";
} catch (PDOException $e) {
    echo "Connection failed: " . $e->getMessage() . "\n";
    exit(1);
}

// Helper to get location info
function get_location($pdo, $id) {
    $stmt = $pdo->prepare("SELECT * FROM locations WHERE id = ?");
    $stmt->execute([$id]);
    return $stmt->fetch(PDO::FETCH_ASSOC);
}

// Process each merge pair
foreach ($merge_pairs as $dup_id => $keeper_id) {
    echo "----------------------------------------\n";

    $dup = get_location($pdo, $dup_id);
    $keeper = get_location($pdo, $keeper_id);

    if (!$dup) {
        echo "WARNING: Duplicate location ID $dup_id not found - skipping\n";
        continue;
    }
    if (!$keeper) {
        echo "WARNING: Keeper location ID $keeper_id not found - skipping\n";
        continue;
    }

    echo "Merging: \"{$dup['name']}\" (ID: $dup_id)\n";
    echo "   Into: \"{$keeper['name']}\" (ID: $keeper_id)\n";
    echo "\n";

    // Count references
    $tables = [
        'events' => 'location_id',
        'website_locations' => 'location_id',
        'location_tags' => 'location_id',
        'location_alternate_names' => 'location_id',
        'location_instagram' => 'location_id',
    ];

    foreach ($tables as $table => $column) {
        $stmt = $pdo->prepare("SELECT COUNT(*) FROM $table WHERE $column = ?");
        $stmt->execute([$dup_id]);
        $count = $stmt->fetchColumn();

        if ($count > 0) {
            echo "  $table: $count reference(s) to update\n";
        }
    }
    echo "\n";

    if ($is_dry_run) {
        echo "  [DRY RUN] Would merge and delete duplicate\n\n";
        continue;
    }

    try {
        $pdo->beginTransaction();

        // 1. Update events
        $stmt = $pdo->prepare("UPDATE events SET location_id = ? WHERE location_id = ?");
        $stmt->execute([$keeper_id, $dup_id]);
        $events_updated = $stmt->rowCount();

        // 2. Update website_locations (handle potential duplicates)
        $stmt = $pdo->prepare("DELETE wl1 FROM website_locations wl1
            INNER JOIN website_locations wl2
            ON wl1.website_id = wl2.website_id AND wl1.location_id = ? AND wl2.location_id = ?");
        $stmt->execute([$dup_id, $keeper_id]);

        $stmt = $pdo->prepare("UPDATE website_locations SET location_id = ? WHERE location_id = ?");
        $stmt->execute([$keeper_id, $dup_id]);
        $wl_updated = $stmt->rowCount();

        // 3. Merge location_tags (avoid duplicates)
        $stmt = $pdo->prepare("INSERT IGNORE INTO location_tags (location_id, tag_id)
            SELECT ?, tag_id FROM location_tags WHERE location_id = ?");
        $stmt->execute([$keeper_id, $dup_id]);
        $tags_merged = $stmt->rowCount();

        $stmt = $pdo->prepare("DELETE FROM location_tags WHERE location_id = ?");
        $stmt->execute([$dup_id]);

        // 4. Merge location_alternate_names
        // First, add the duplicate's main name as an alternate name for the keeper
        $stmt = $pdo->prepare("INSERT IGNORE INTO location_alternate_names (location_id, alternate_name) VALUES (?, ?)");
        $stmt->execute([$keeper_id, $dup['name']]);

        // Move other alternate names from duplicate to keeper
        $stmt = $pdo->prepare("INSERT IGNORE INTO location_alternate_names (location_id, alternate_name)
            SELECT ?, alternate_name FROM location_alternate_names WHERE location_id = ?");
        $stmt->execute([$keeper_id, $dup_id]);

        $stmt = $pdo->prepare("DELETE FROM location_alternate_names WHERE location_id = ?");
        $stmt->execute([$dup_id]);

        // 5. Merge location_instagram (avoid duplicates)
        $stmt = $pdo->prepare("INSERT IGNORE INTO location_instagram (location_id, instagram_id)
            SELECT ?, instagram_id FROM location_instagram WHERE location_id = ?");
        $stmt->execute([$keeper_id, $dup_id]);

        $stmt = $pdo->prepare("DELETE FROM location_instagram WHERE location_id = ?");
        $stmt->execute([$dup_id]);

        // 6. Delete the duplicate location
        $stmt = $pdo->prepare("DELETE FROM locations WHERE id = ?");
        $stmt->execute([$dup_id]);

        $pdo->commit();

        echo "  MERGED: events=$events_updated, website_locations=$wl_updated, tags_added=$tags_merged\n";
        echo "  DELETED: Location ID $dup_id\n";
        echo "  Added alternate name: \"{$dup['name']}\"\n\n";

    } catch (Exception $e) {
        $pdo->rollBack();
        echo "  ERROR: " . $e->getMessage() . "\n\n";
    }
}

echo "----------------------------------------\n";
echo "=== Merge Complete ===\n";

// Show final stats
$stmt = $pdo->query("SELECT COUNT(*) as total FROM locations");
$total = $stmt->fetchColumn();
echo "Total locations remaining: $total\n";

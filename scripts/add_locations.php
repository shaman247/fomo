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
$new_locations = [];


// Load .env file
function load_env($path) {
    if (!file_exists($path)) return;
    $lines = file($path, FILE_IGNORE_NEW_LINES | FILE_SKIP_EMPTY_LINES);
    foreach ($lines as $line) {
        if (strpos(trim($line), '#') === 0) continue;
        if (strpos($line, '=') === false) continue;
        list($name, $value) = explode('=', $line, 2);
        $name = trim($name);
        $value = trim($value, " \t\n\r\0\x0B\"'");
        if (!getenv($name)) putenv("$name=$value");
    }
}
load_env(__DIR__ . '/../.env');

$config = [
    'local' => [
        'host' => 'localhost',
        'port' => 3306,
        'dbname' => 'fomo',
        'user' => 'root',
        'password' => '',
    ],
];

// ============================================================================
// SCRIPT LOGIC (no need to edit below)
// ============================================================================

// Parse command line arguments
$is_dry_run = in_array('--dry-run', $argv) || in_array('-n', $argv);
$show_help = in_array('--help', $argv) || in_array('-h', $argv);

if ($show_help) {
    echo <<<HELP
Add new locations to the database

Usage:
  php scripts/add_locations.php [options]

Options:
  --dry-run, -n       Show what would be added without making changes
  --help, -h          Show this help message

Instructions:
  1. Edit the \$new_locations array at the top of this script
  2. Run with --dry-run first to verify
  3. Run without --dry-run to actually add the locations

Example location entry:
  [
      'name' => 'The Blue Note',
      'short_name' => 'Blue Note',        // Optional: shorter display name
      'description' => 'Legendary jazz club...',  // Optional: venue description
      'address' => '131 W 3rd St, New York, NY 10012',
      'lat' => 40.7308,
      'lng' => -74.0005,
      'emoji' => '🎷',
      'alt_emoji' => '🎵',                // Optional: alternative emoji
      'tags' => ['Jazz', 'Live Music', 'Manhattan', 'Greenwich Village'],  // Optional
  ]

Note: Instagram handles are stored separately in the instagram_accounts table.
Use location_instagram junction table to link locations to Instagram accounts.

HELP;
    exit(0);
}

$env = 'local';
$db_config = $config[$env];

echo "=== Add Locations Script ===\n";
echo "Target: " . strtoupper($env) . " database\n";
echo "Mode: " . ($is_dry_run ? "DRY RUN (no changes will be made)" : "LIVE") . "\n";
echo "\n";

if (empty($new_locations)) {
    echo "No locations to add. Edit the \$new_locations array in this script.\n";
    exit(0);
}

echo "Locations to add: " . count($new_locations) . "\n\n";

// Validate locations before connecting
$errors = [];
foreach ($new_locations as $i => $loc) {
    $idx = $i + 1;
    if (empty($loc['name'])) {
        $errors[] = "Location #$idx: 'name' is required";
    }
    if (!isset($loc['lat']) || !is_numeric($loc['lat'])) {
        $errors[] = "Location #$idx ({$loc['name']}): 'lat' must be a number";
    }
    if (!isset($loc['lng']) || !is_numeric($loc['lng'])) {
        $errors[] = "Location #$idx ({$loc['name']}): 'lng' must be a number";
    }
    if (empty($loc['emoji'])) {
        $errors[] = "Location #$idx ({$loc['name']}): 'emoji' is required";
    }
}

if (!empty($errors)) {
    echo "Validation errors:\n";
    foreach ($errors as $error) {
        echo "  - $error\n";
    }
    exit(1);
}

// Connect to database directly (local)
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

// Helper functions for database operations
function check_exists_pdo($pdo, $name) {
    $stmt = $pdo->prepare("SELECT id FROM locations WHERE name = ?");
    $stmt->execute([$name]);
    $row = $stmt->fetch(PDO::FETCH_ASSOC);
    return $row ? $row['id'] : null;
}

function insert_location_pdo($pdo, $loc) {
    $sql = "INSERT INTO locations (name, short_name, very_short_name, description, address, lat, lng, emoji, alt_emoji)
            VALUES (:name, :short_name, :very_short_name, :description, :address, :lat, :lng, :emoji, :alt_emoji)";
    $stmt = $pdo->prepare($sql);
    $stmt->execute([
        ':name' => $loc['name'],
        ':short_name' => $loc['short_name'] ?? null,
        ':very_short_name' => $loc['very_short_name'] ?? null,
        ':description' => $loc['description'] ?? null,
        ':address' => $loc['address'] ?? null,
        ':lat' => $loc['lat'],
        ':lng' => $loc['lng'],
        ':emoji' => $loc['emoji'],
        ':alt_emoji' => $loc['alt_emoji'] ?? null,
    ]);
    return $pdo->lastInsertId();
}

function add_tags_pdo($pdo, $location_id, $tags) {
    $new_tags = [];
    $existing_tags = [];

    foreach ($tags as $tag_name) {
        // Check if tag exists
        $stmt = $pdo->prepare("SELECT id FROM tags WHERE name = ?");
        $stmt->execute([$tag_name]);
        $row = $stmt->fetch(PDO::FETCH_ASSOC);

        if ($row) {
            $tag_id = $row['id'];
            $existing_tags[] = $tag_name;
        } else {
            $stmt = $pdo->prepare("INSERT INTO tags (name, type) VALUES (?, 'tag')");
            $stmt->execute([$tag_name]);
            $tag_id = $pdo->lastInsertId();
            $new_tags[] = $tag_name;
        }

        // Link tag to location
        $stmt = $pdo->prepare("INSERT INTO location_tags (location_id, tag_id) VALUES (?, ?)");
        $stmt->execute([$location_id, $tag_id]);
    }

    return ['existing' => $existing_tags, 'new' => $new_tags];
}

function get_stats_pdo($pdo) {
    $result = $pdo->query("SELECT COUNT(*) as total, MAX(id) as max_id FROM locations");
    return $result->fetch(PDO::FETCH_ASSOC);
}

// Check for duplicates
$duplicates = [];
foreach ($new_locations as $loc) {
    $existing_id = check_exists_pdo($pdo, $loc['name']);
    if ($existing_id) {
        $duplicates[] = "'{$loc['name']}' already exists (ID: $existing_id)";
    }
}

if (!empty($duplicates)) {
    echo "Warning - these locations already exist:\n";
    foreach ($duplicates as $dup) {
        echo "  - $dup\n";
    }
    echo "\n";
}

// Process each location
$added = 0;
$skipped = 0;

foreach ($new_locations as $loc) {
    // Check if already exists
    $existing_id = check_exists_pdo($pdo, $loc['name']);

    if ($existing_id) {
        echo "  SKIP: {$loc['name']} (already exists)\n";
        $skipped++;
        continue;
    }

    $tags = $loc['tags'] ?? [];

    if ($is_dry_run) {
        echo "  [DRY RUN] Would add: {$loc['name']} {$loc['emoji']}\n";
        echo "            Address: " . ($loc['address'] ?? 'N/A') . "\n";
        echo "            Coords: {$loc['lat']}, {$loc['lng']}\n";
        if (!empty($tags)) {
            echo "            Tags: " . implode(', ', $tags) . "\n";
        }
        $added++;
    } else {
        try {
            $new_id = insert_location_pdo($pdo, $loc);

            echo "  ADD: {$loc['name']} {$loc['emoji']} (ID: $new_id)\n";

            // Add tags
            if (!empty($tags)) {
                $tag_result = add_tags_pdo($pdo, $new_id, $tags);

                if (!empty($tag_result['existing'])) {
                    echo "       Tags (existing): " . implode(', ', $tag_result['existing']) . "\n";
                }
                if (!empty($tag_result['new'])) {
                    echo "       Tags (NEW): " . implode(', ', $tag_result['new']) . "\n";
                }
            }

            $added++;
        } catch (Exception $e) {
            echo "  ERROR adding {$loc['name']}: " . $e->getMessage() . "\n";
        }
    }
}

echo "\n";
echo "=== Summary ===\n";
echo "Added: $added\n";
echo "Skipped: $skipped\n";

if ($is_dry_run && $added > 0) {
    echo "\nRun without --dry-run to actually add these locations.\n";
}

// Show current totals
$stats = get_stats_pdo($pdo);
echo "\nDatabase now has {$stats['total']} locations (max ID: {$stats['max_id']})\n";

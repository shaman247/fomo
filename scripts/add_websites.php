#!/usr/bin/env php
<?php
/**
 * Add new websites to the database (local)
 *
 * Usage:
 *   php scripts/add_websites.php                    # Add to local database
 *   php scripts/add_websites.php --dry-run         # Show what would be added
 *
 * Edit the $new_websites array below to specify websites to add.
 *
 * CLEANUP: After a successful run, REMOVE the entries you just added from
 * $new_websites so the array stays empty between sessions. Stale entries
 * clutter dry-runs (everything reports "already exists") and obscure the
 * next addition. Re-running with the same entries is a no-op, but they
 * should still be deleted as part of finishing the task.
 */

// ============================================================================
// EDIT THIS ARRAY TO ADD NEW WEBSITES
// ============================================================================
$new_websites = [
];

// ============================================================================
// DATABASE CONFIGURATION
// ============================================================================

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
Add new websites to the database

Usage:
  php scripts/add_websites.php [options]

Options:
  --dry-run, -n       Show what would be added without making changes
  --help, -h          Show this help message

Instructions:
  1. Edit the \$new_websites array at the top of this script
  2. Run with --dry-run first to verify
  3. Run without --dry-run to actually add the websites

Example website entry:
  [
      'name' => 'Blue Note',
      'description' => 'Legendary jazz club...',  // Optional: organization description
      'base_url' => 'https://www.bluenotejazz.com/',  // Root domain (optional)
      'urls' => ['https://www.bluenotejazz.com/nyc/schedule'],  // Crawl URLs (optional)
      'crawl_frequency' => 4,      // Days between crawls (optional)
      'crawl_after' => '2026-06-01', // Don't crawl until this date (optional, for seasonal events)
      'keywords' => '&event_id=',  // URL keywords to follow (optional)
      'max_pages' => 50,           // Max pages to crawl (optional)
      'location' => 'Blue Note',   // Links to existing location (optional)
      'tags' => ['Jazz', 'Live Music'],  // Website tags (optional)
      'parent' => 'NYC Parks',     // Organizer root website this site belongs to,
                                   // by id or exact name (optional). Use when adding
                                   // another page/venue of an org we already track.
  ]

HELP;
    exit(0);
}

$env = 'local';
$db_config = $config[$env];

echo "=== Add Websites Script ===\n";
echo "Target: " . strtoupper($env) . " database\n";
echo "Mode: " . ($is_dry_run ? "DRY RUN (no changes will be made)" : "LIVE") . "\n";
echo "\n";

if (empty($new_websites)) {
    echo "No websites to add. Edit the \$new_websites array in this script.\n";
    exit(0);
}

echo "Websites to add: " . count($new_websites) . "\n\n";

// Validate websites before connecting
$errors = [];
foreach ($new_websites as $i => $site) {
    $idx = $i + 1;
    if (empty($site['name'])) {
        $errors[] = "Website #$idx: 'name' is required";
    }
    if (empty($site['base_url'])) {
        $errors[] = "Website #$idx ({$site['name']}): 'base_url' is required";
    }
}

if (!empty($errors)) {
    echo "Validation errors:\n";
    foreach ($errors as $error) {
        echo "  - $error\n";
    }
    exit(1);
}

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

// Collapse a URL to host+path for comparison: drop scheme, leading "www.", and a
// trailing slash, lowercased. So "https://qedastoria.com/" == "https://qedastoria.com".
function normalize_base_url($u) {
    $u = strtolower(trim((string)($u ?? '')));
    $u = preg_replace('#^https?://#', '', $u);
    $u = preg_replace('#^www\.#', '', $u);
    return rtrim($u, '/');
}

// Detect whether a website entry duplicates an existing one — by exact name OR by
// normalized base_url. Returns ['id' => int, 'reason' => string] or null. Name-only
// matching used to miss real dupes (a new "QED Astoria" pointed at qedastoria.com
// sailed past the existing "Q.E.D." website on the same domain, double-crawling it).
function check_website_exists_pdo($pdo, $site) {
    if (!is_array($site)) {
        $site = ['name' => $site];
    }

    if (!empty($site['name'])) {
        $stmt = $pdo->prepare("SELECT id FROM websites WHERE name = ?");
        $stmt->execute([$site['name']]);
        if ($row = $stmt->fetch(PDO::FETCH_ASSOC)) {
            return ['id' => $row['id'], 'reason' => "name matches existing website"];
        }
    }

    if (!empty($site['base_url'])) {
        $target = normalize_base_url($site['base_url']);
        if ($target !== '') {
            foreach ($pdo->query("SELECT id, name, base_url FROM websites WHERE base_url IS NOT NULL AND base_url != ''")->fetchAll(PDO::FETCH_ASSOC) as $r) {
                if (normalize_base_url($r['base_url']) === $target) {
                    return ['id' => $r['id'], 'reason' => "base_url matches existing website \"{$r['name']}\" ({$r['base_url']})"];
                }
            }
        }
    }

    return null;
}

function get_location_id_pdo($pdo, $name) {
    $stmt = $pdo->prepare("SELECT id FROM locations WHERE name = ?");
    $stmt->execute([$name]);
    $row = $stmt->fetch(PDO::FETCH_ASSOC);
    return $row ? $row['id'] : null;
}

// Resolve a 'parent' entry value (website id or exact name) to a website id.
// Returns null (with a warning printed by the caller) when unresolved.
function get_parent_website_id_pdo($pdo, $parent) {
    if (is_int($parent) || ctype_digit((string)$parent)) {
        $stmt = $pdo->prepare("SELECT id FROM websites WHERE id = ?");
        $stmt->execute([(int)$parent]);
    } else {
        $stmt = $pdo->prepare("SELECT id FROM websites WHERE name = ?");
        $stmt->execute([$parent]);
    }
    $row = $stmt->fetch(PDO::FETCH_ASSOC);
    return $row ? (int)$row['id'] : null;
}

function insert_website_pdo($pdo, $site, $parent_website_id = null) {
    $sql = "INSERT INTO websites (name, description, base_url, crawl_frequency, crawl_after, selector, keywords, max_pages, notes, parent_website_id)
            VALUES (:name, :description, :base_url, :crawl_frequency, :crawl_after, :selector, :keywords, :max_pages, :notes, :parent_website_id)";
    $stmt = $pdo->prepare($sql);
    $stmt->execute([
        ':name' => $site['name'],
        ':description' => $site['description'] ?? null,
        ':base_url' => $site['base_url'] ?? null,
        ':crawl_frequency' => $site['crawl_frequency'] ?? null,
        ':crawl_after' => $site['crawl_after'] ?? null,
        ':selector' => $site['selector'] ?? null,
        ':keywords' => $site['keywords'] ?? null,
        ':max_pages' => $site['max_pages'] ?? null,
        ':notes' => $site['notes'] ?? null,
        ':parent_website_id' => $parent_website_id,
    ]);
    return $pdo->lastInsertId();
}

function add_website_urls_pdo($pdo, $website_id, $urls) {
    $stmt = $pdo->prepare("INSERT INTO website_urls (website_id, url, sort_order) VALUES (?, ?, ?)");
    foreach ($urls as $i => $url) {
        $stmt->execute([$website_id, $url, $i]);
    }
}

function link_website_location_pdo($pdo, $website_id, $location_id) {
    $stmt = $pdo->prepare("INSERT INTO website_locations (website_id, location_id) VALUES (?, ?)");
    $stmt->execute([$website_id, $location_id]);
}

function add_website_tags_pdo($pdo, $website_id, $tags) {
    foreach ($tags as $tag) {
        $stmt = $pdo->prepare("INSERT INTO website_tags (website_id, tag) VALUES (?, ?)");
        $stmt->execute([$website_id, $tag]);
    }
}

function get_stats_pdo($pdo) {
    $result = $pdo->query("SELECT COUNT(*) as total, MAX(id) as max_id FROM websites");
    return $result->fetch(PDO::FETCH_ASSOC);
}

// Check for duplicates
$duplicates = [];
foreach ($new_websites as $site) {
    $match = check_website_exists_pdo($pdo, $site);
    if ($match) {
        $duplicates[] = "'{$site['name']}' — {$match['reason']} (ID: {$match['id']})";
    }
}

if (!empty($duplicates)) {
    echo "Warning - these websites already exist:\n";
    foreach ($duplicates as $dup) {
        echo "  - $dup\n";
    }
    echo "\n";
}

// Process each website
$added = 0;
$skipped = 0;

foreach ($new_websites as $site) {
    // Check if already exists
    $match = check_website_exists_pdo($pdo, $site);

    if ($match) {
        echo "  SKIP: {$site['name']} (already exists — {$match['reason']}, ID: {$match['id']})\n";
        $skipped++;
        continue;
    }

    // Check if location exists (if specified)
    $location_id = null;
    if (!empty($site['location'])) {
        $location_id = get_location_id_pdo($pdo, $site['location']);

        if (!$location_id) {
            echo "  WARNING: Location '{$site['location']}' not found for {$site['name']}\n";
        }
    }

    // Resolve parent organizer website (if specified)
    $parent_website_id = null;
    if (!empty($site['parent'])) {
        $parent_website_id = get_parent_website_id_pdo($pdo, $site['parent']);

        if (!$parent_website_id) {
            echo "  WARNING: Parent website '{$site['parent']}' not found for {$site['name']}\n";
        }
    }

    $tags = $site['tags'] ?? [];

    $urls = $site['urls'] ?? [];

    if ($is_dry_run) {
        echo "  [DRY RUN] Would add: {$site['name']}\n";
        if (!empty($site['base_url'])) {
            echo "            Base URL: {$site['base_url']}\n";
        }
        if (!empty($urls)) {
            foreach ($urls as $url) {
                echo "            Crawl URL: {$url}\n";
            }
        }
        if (!empty($site['crawl_frequency'])) {
            echo "            Crawl frequency: every {$site['crawl_frequency']} days\n";
        }
        if (!empty($site['crawl_after'])) {
            echo "            Crawl after: {$site['crawl_after']}\n";
        }
        if (!empty($site['max_pages'])) {
            echo "            Max pages: {$site['max_pages']}\n";
        }
        if ($location_id) {
            echo "            Location: {$site['location']} (ID: $location_id)\n";
        } elseif (!empty($site['location'])) {
            echo "            Location: {$site['location']} (NOT FOUND)\n";
        }
        if ($parent_website_id) {
            echo "            Parent organizer: {$site['parent']} (ID: $parent_website_id)\n";
        } elseif (!empty($site['parent'])) {
            echo "            Parent organizer: {$site['parent']} (NOT FOUND)\n";
        }
        if (!empty($tags)) {
            echo "            Tags: " . implode(', ', $tags) . "\n";
        }
        $added++;
    } else {
        try {
            $new_id = insert_website_pdo($pdo, $site, $parent_website_id);

            echo "  ADD: {$site['name']} (ID: $new_id)\n";
            if (!empty($site['base_url'])) {
                echo "       Base URL: {$site['base_url']}\n";
            }
            if ($parent_website_id) {
                echo "       Parent organizer: {$site['parent']} (ID: $parent_website_id)\n";
            }

            // Add crawl URLs
            if (!empty($urls)) {
                add_website_urls_pdo($pdo, $new_id, $urls);
                foreach ($urls as $url) {
                    echo "       Crawl URL: {$url}\n";
                }
            }

            // Link to location
            if ($location_id) {
                link_website_location_pdo($pdo, $new_id, $location_id);
                echo "       Location: {$site['location']} (ID: $location_id)\n";
            }

            // Add tags
            if (!empty($tags)) {
                add_website_tags_pdo($pdo, $new_id, $tags);
                echo "       Tags: " . implode(', ', $tags) . "\n";
            }

            $added++;
        } catch (Exception $e) {
            echo "  ERROR adding {$site['name']}: " . $e->getMessage() . "\n";
        }
    }
}

echo "\n";
echo "=== Summary ===\n";
echo "Added: $added\n";
echo "Skipped: $skipped\n";

if ($is_dry_run && $added > 0) {
    echo "\nRun without --dry-run to actually add these websites.\n";
}

// Show current totals
$stats = get_stats_pdo($pdo);
echo "\nDatabase now has {$stats['total']} websites (max ID: {$stats['max_id']})\n";

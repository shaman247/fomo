#!/usr/bin/env php
<?php
/**
 * Add new websites to the database (local or production)
 *
 * Usage:
 *   php scripts/add_websites.php                    # Add to local database
 *   php scripts/add_websites.php --production      # Add to production database
 *   php scripts/add_websites.php --dry-run         # Show what would be added
 *   php scripts/add_websites.php --production --dry-run
 *
 * Edit the $new_websites array below to specify websites to add.
 */

// ============================================================================
// EDIT THIS ARRAY TO ADD NEW WEBSITES
// ============================================================================
$new_websites = [
    // Websites added on 2026-01-19 - see git history
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
    'production' => [
        'via_ssh' => true,
        'ssh_host' => getenv('SSH_HOST') ?: '69.57.162.203',
        'ssh_port' => getenv('SSH_PORT') ?: 21098,
        'ssh_user' => getenv('SSH_USER') ?: 'fomoowsq',
        'ssh_key' => __DIR__ . '/' . (getenv('SSH_KEY') ?: 'id_rsa_sync'),
        'dbname' => getenv('PROD_DB_NAME') ?: die("Error: PROD_DB_NAME not set in .env\n"),
        'user' => getenv('PROD_DB_USER') ?: die("Error: PROD_DB_USER not set in .env\n"),
        'password' => getenv('PROD_DB_PASS') ?: die("Error: PROD_DB_PASS not set in .env\n"),
    ],
];

// ============================================================================
// SCRIPT LOGIC (no need to edit below)
// ============================================================================

// Parse command line arguments
$is_production = in_array('--production', $argv) || in_array('-p', $argv);
$is_dry_run = in_array('--dry-run', $argv) || in_array('-n', $argv);
$show_help = in_array('--help', $argv) || in_array('-h', $argv);

if ($show_help) {
    echo <<<HELP
Add new websites to the database

Usage:
  php scripts/add_websites.php [options]

Options:
  --production, -p    Add to production database (default: local)
  --dry-run, -n       Show what would be added without making changes
  --help, -h          Show this help message

Instructions:
  1. Edit the \$new_websites array at the top of this script
  2. Run with --dry-run first to verify
  3. Run without --dry-run to actually add the websites

ID Sync (Production):
  When adding to production, the script will:
  - Look up the website's ID in local database
  - Use that same ID in production to keep databases in sync
  - Skip if the website doesn't exist locally (add to local first!)
  - Error if the local ID is already used by a different website in production

Example website entry:
  [
      'name' => 'Blue Note',
      'description' => 'Legendary jazz club...',  // Optional: organization description
      'base_url' => 'https://www.bluenotejazz.com/',  // Root domain (optional)
      'urls' => ['https://www.bluenotejazz.com/nyc/schedule'],  // Crawl URLs (optional)
      'crawl_frequency' => 4,      // Days between crawls (optional)
      'keywords' => '&event_id=',  // URL keywords to follow (optional)
      'max_pages' => 50,           // Max pages to crawl (optional)
      'location' => 'Blue Note',   // Links to existing location (optional)
      'tags' => ['Jazz', 'Live Music'],  // Website tags (optional)
  ]

HELP;
    exit(0);
}

$env = $is_production ? 'production' : 'local';
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

// Helper function to run SQL via SSH for production
function run_ssh_query($config, $sql) {
    $escaped_password = str_replace(']', '\\]', $config['password']);
    $cmd = sprintf(
        'ssh -p %d -i %s -o StrictHostKeyChecking=no %s@%s %s 2>&1',
        $config['ssh_port'],
        escapeshellarg($config['ssh_key']),
        $config['ssh_user'],
        $config['ssh_host'],
        escapeshellarg("mariadb -u {$config['user']} -p{$escaped_password} {$config['dbname']} -N -e " . escapeshellarg($sql))
    );
    $output = shell_exec($cmd);
    return $output;
}

// Check if using SSH for production
$use_ssh = $is_production && !empty($db_config['via_ssh']);

if ($use_ssh) {
    echo "Connecting to production via SSH...\n";
    $test = run_ssh_query($db_config, "SELECT 1");
    if (trim($test) !== '1') {
        echo "Connection failed: $test\n";
        exit(1);
    }
    echo "Connected to $env database via SSH\n\n";
    $pdo = null;
} else {
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
}

// Helper functions for database operations
function escape_sql($value) {
    if ($value === null) return 'NULL';
    return "'" . addslashes($value) . "'";
}

function check_website_exists_pdo($pdo, $name) {
    $stmt = $pdo->prepare("SELECT id FROM websites WHERE name = ?");
    $stmt->execute([$name]);
    $row = $stmt->fetch(PDO::FETCH_ASSOC);
    return $row ? $row['id'] : null;
}

function check_website_exists_ssh($config, $name) {
    $sql = "SELECT id FROM websites WHERE name = " . escape_sql($name);
    $result = trim(run_ssh_query($config, $sql));
    return $result && is_numeric($result) ? $result : null;
}

function check_website_id_exists_ssh($config, $id) {
    $sql = "SELECT name FROM websites WHERE id = " . intval($id);
    $result = trim(run_ssh_query($config, $sql));
    return $result && strlen($result) > 0 ? $result : null;
}

function get_local_website_id($local_config, $name) {
    // Connect to local database to get the ID
    $port = $local_config['port'] ?? 3306;
    try {
        $dsn = "mysql:host={$local_config['host']};port={$port};dbname={$local_config['dbname']};charset=utf8mb4";
        $local_pdo = new PDO($dsn, $local_config['user'], $local_config['password'], [
            PDO::ATTR_ERRMODE => PDO::ERRMODE_EXCEPTION,
        ]);
        $stmt = $local_pdo->prepare("SELECT id FROM websites WHERE name = ?");
        $stmt->execute([$name]);
        $row = $stmt->fetch(PDO::FETCH_ASSOC);
        return $row ? $row['id'] : null;
    } catch (PDOException $e) {
        echo "  Warning: Could not connect to local database to get ID: " . $e->getMessage() . "\n";
        return null;
    }
}

function get_location_id_pdo($pdo, $name) {
    $stmt = $pdo->prepare("SELECT id FROM locations WHERE name = ?");
    $stmt->execute([$name]);
    $row = $stmt->fetch(PDO::FETCH_ASSOC);
    return $row ? $row['id'] : null;
}

function get_location_id_ssh($config, $name) {
    $sql = "SELECT id FROM locations WHERE name = " . escape_sql($name);
    $result = trim(run_ssh_query($config, $sql));
    return $result && is_numeric($result) ? $result : null;
}

function insert_website_pdo($pdo, $site) {
    $sql = "INSERT INTO websites (name, description, base_url, crawl_frequency, selector, keywords, max_pages, notes)
            VALUES (:name, :description, :base_url, :crawl_frequency, :selector, :keywords, :max_pages, :notes)";
    $stmt = $pdo->prepare($sql);
    $stmt->execute([
        ':name' => $site['name'],
        ':description' => $site['description'] ?? null,
        ':base_url' => $site['base_url'] ?? null,
        ':crawl_frequency' => $site['crawl_frequency'] ?? null,
        ':selector' => $site['selector'] ?? null,
        ':keywords' => $site['keywords'] ?? null,
        ':max_pages' => $site['max_pages'] ?? null,
        ':notes' => $site['notes'] ?? null,
    ]);
    return $pdo->lastInsertId();
}

function insert_website_ssh($config, $site, $explicit_id = null) {
    if ($explicit_id !== null) {
        // Insert with explicit ID to match local database
        $sql = sprintf(
            "INSERT INTO websites (id, name, description, base_url, crawl_frequency, selector, keywords, max_pages, notes) VALUES (%d, %s, %s, %s, %s, %s, %s, %s, %s); SELECT LAST_INSERT_ID();",
            intval($explicit_id),
            escape_sql($site['name']),
            escape_sql($site['description'] ?? null),
            escape_sql($site['base_url'] ?? null),
            $site['crawl_frequency'] ?? 'NULL',
            escape_sql($site['selector'] ?? null),
            escape_sql($site['keywords'] ?? null),
            $site['max_pages'] ?? 'NULL',
            escape_sql($site['notes'] ?? null)
        );
    } else {
        $sql = sprintf(
            "INSERT INTO websites (name, description, base_url, crawl_frequency, selector, keywords, max_pages, notes) VALUES (%s, %s, %s, %s, %s, %s, %s, %s); SELECT LAST_INSERT_ID();",
            escape_sql($site['name']),
            escape_sql($site['description'] ?? null),
            escape_sql($site['base_url'] ?? null),
            $site['crawl_frequency'] ?? 'NULL',
            escape_sql($site['selector'] ?? null),
            escape_sql($site['keywords'] ?? null),
            $site['max_pages'] ?? 'NULL',
            escape_sql($site['notes'] ?? null)
        );
    }
    $result = trim(run_ssh_query($config, $sql));
    return $result;
}

function add_website_urls_pdo($pdo, $website_id, $urls) {
    $stmt = $pdo->prepare("INSERT INTO website_urls (website_id, url, sort_order) VALUES (?, ?, ?)");
    foreach ($urls as $i => $url) {
        $stmt->execute([$website_id, $url, $i]);
    }
}

function add_website_urls_ssh($config, $website_id, $urls) {
    $values = [];
    foreach ($urls as $i => $url) {
        $values[] = "($website_id, " . escape_sql($url) . ", $i)";
    }
    if (!empty($values)) {
        $sql = "INSERT INTO website_urls (website_id, url, sort_order) VALUES " . implode(", ", $values);
        run_ssh_query($config, $sql);
    }
}

function link_website_location_pdo($pdo, $website_id, $location_id) {
    $stmt = $pdo->prepare("INSERT INTO website_locations (website_id, location_id) VALUES (?, ?)");
    $stmt->execute([$website_id, $location_id]);
}

function link_website_location_ssh($config, $website_id, $location_id) {
    $sql = "INSERT INTO website_locations (website_id, location_id) VALUES ($website_id, $location_id)";
    run_ssh_query($config, $sql);
}

function add_website_tags_pdo($pdo, $website_id, $tags) {
    foreach ($tags as $tag) {
        $stmt = $pdo->prepare("INSERT INTO website_tags (website_id, tag) VALUES (?, ?)");
        $stmt->execute([$website_id, $tag]);
    }
}

function add_website_tags_ssh($config, $website_id, $tags) {
    $values = [];
    foreach ($tags as $tag) {
        $values[] = "($website_id, " . escape_sql($tag) . ")";
    }
    if (!empty($values)) {
        $sql = "INSERT INTO website_tags (website_id, tag) VALUES " . implode(", ", $values);
        run_ssh_query($config, $sql);
    }
}

function get_stats_pdo($pdo) {
    $result = $pdo->query("SELECT COUNT(*) as total, MAX(id) as max_id FROM websites");
    return $result->fetch(PDO::FETCH_ASSOC);
}

function get_stats_ssh($config) {
    $result = run_ssh_query($config, "SELECT COUNT(*), MAX(id) FROM websites");
    $parts = explode("\t", trim($result));
    return ['total' => $parts[0] ?? '?', 'max_id' => $parts[1] ?? '?'];
}

// Check for duplicates
$duplicates = [];
foreach ($new_websites as $site) {
    $existing_id = $use_ssh
        ? check_website_exists_ssh($db_config, $site['name'])
        : check_website_exists_pdo($pdo, $site['name']);
    if ($existing_id) {
        $duplicates[] = "'{$site['name']}' already exists (ID: $existing_id)";
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
    $existing_id = $use_ssh
        ? check_website_exists_ssh($db_config, $site['name'])
        : check_website_exists_pdo($pdo, $site['name']);

    if ($existing_id) {
        echo "  SKIP: {$site['name']} (already exists)\n";
        $skipped++;
        continue;
    }

    // Check if location exists (if specified)
    $location_id = null;
    if (!empty($site['location'])) {
        $location_id = $use_ssh
            ? get_location_id_ssh($db_config, $site['location'])
            : get_location_id_pdo($pdo, $site['location']);

        if (!$location_id) {
            echo "  WARNING: Location '{$site['location']}' not found for {$site['name']}\n";
        }
    }

    $tags = $site['tags'] ?? [];

    $urls = $site['urls'] ?? [];

    // For production, look up the local ID to ensure sync
    $explicit_id = null;
    if ($use_ssh) {
        $local_id = get_local_website_id($config['local'], $site['name']);
        if ($local_id) {
            // Check if this ID is already in use in production
            $existing_name = check_website_id_exists_ssh($db_config, $local_id);
            if ($existing_name) {
                echo "  ERROR: Cannot add '{$site['name']}' - Local ID $local_id is already used by '$existing_name' in production.\n";
                echo "         Please resolve this ID conflict manually before continuing.\n";
                $skipped++;
                continue;
            }
            $explicit_id = $local_id;
            echo "  (Using local ID: $local_id)\n";
        } else {
            echo "  WARNING: Website '{$site['name']}' not found in local database.\n";
            echo "           You should add it to LOCAL first, then to production.\n";
            echo "           Skipping to prevent ID mismatch.\n";
            $skipped++;
            continue;
        }
    }

    if ($is_dry_run) {
        echo "  [DRY RUN] Would add: {$site['name']}\n";
        if ($explicit_id) {
            echo "            ID: $explicit_id (from local)\n";
        }
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
        if (!empty($site['max_pages'])) {
            echo "            Max pages: {$site['max_pages']}\n";
        }
        if ($location_id) {
            echo "            Location: {$site['location']} (ID: $location_id)\n";
        } elseif (!empty($site['location'])) {
            echo "            Location: {$site['location']} (NOT FOUND)\n";
        }
        if (!empty($tags)) {
            echo "            Tags: " . implode(', ', $tags) . "\n";
        }
        $added++;
    } else {
        try {
            $new_id = $use_ssh
                ? insert_website_ssh($db_config, $site, $explicit_id)
                : insert_website_pdo($pdo, $site);

            echo "  ADD: {$site['name']} (ID: $new_id)\n";
            if (!empty($site['base_url'])) {
                echo "       Base URL: {$site['base_url']}\n";
            }

            // Add crawl URLs
            if (!empty($urls)) {
                if ($use_ssh) {
                    add_website_urls_ssh($db_config, $new_id, $urls);
                } else {
                    add_website_urls_pdo($pdo, $new_id, $urls);
                }
                foreach ($urls as $url) {
                    echo "       Crawl URL: {$url}\n";
                }
            }

            // Link to location
            if ($location_id) {
                if ($use_ssh) {
                    link_website_location_ssh($db_config, $new_id, $location_id);
                } else {
                    link_website_location_pdo($pdo, $new_id, $location_id);
                }
                echo "       Location: {$site['location']} (ID: $location_id)\n";
            }

            // Add tags
            if (!empty($tags)) {
                if ($use_ssh) {
                    add_website_tags_ssh($db_config, $new_id, $tags);
                } else {
                    add_website_tags_pdo($pdo, $new_id, $tags);
                }
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
$stats = $use_ssh ? get_stats_ssh($db_config) : get_stats_pdo($pdo);
echo "\nDatabase now has {$stats['total']} websites (max ID: {$stats['max_id']})\n";

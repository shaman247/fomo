#!/usr/bin/env php
<?php
/**
 * Add new locations to the database (local or production)
 *
 * Usage:
 *   php scripts/add_locations.php                    # Add to local database
 *   php scripts/add_locations.php --production      # Add to production database
 *   php scripts/add_locations.php --dry-run         # Show what would be added
 *   php scripts/add_locations.php --production --dry-run
 *
 * Edit the $new_locations array below to specify locations to add.
 */

// ============================================================================
// EDIT THIS ARRAY TO ADD NEW LOCATIONS
// ============================================================================
$new_locations = [
];

$_done_2026_03_11 = [
    [
        'name' => 'Aperture Foundation',
        'description' => 'Photography-focused nonprofit gallery and publisher in Chelsea, hosting exhibitions, artist talks, and book launches.',
        'address' => '547 W 27th St, New York, NY 10001',
        'lat' => 40.75130,
        'lng' => -74.00435,
        'emoji' => '📷',
        'tags' => ['Manhattan', 'Chelsea', 'Art', 'Photography'],
    ],
    [
        'name' => 'The Windjammer',
        'description' => 'Neighborhood bar and live music venue in Ridgewood with a stage for bands, operating since 1982.',
        'address' => '5-52 Grandview Ave, Ridgewood, NY 11385',
        'lat' => 40.70915,
        'lng' => -73.90694,
        'emoji' => '🍹',
        'tags' => ['Queens', 'Ridgewood', 'Live Music', 'Bar'],
    ],
    [
        'name' => 'Chelsea Cannabis Co.',
        'description' => 'Licensed cannabis dispensary in Chelsea hosting community events, live jazz, and cultural programming.',
        'address' => '104 7th Ave, New York, NY 10011',
        'lat' => 40.74020,
        'lng' => -73.99883,
        'emoji' => '🍹',
        'tags' => ['Manhattan', 'Chelsea', 'Live Music'],
    ],
    [
        'name' => 'Bronx Council on the Arts',
        'description' => 'Nonprofit arts service organization headquartered in a renovated bank building, hosting forums, exhibitions, and community arts programming.',
        'address' => '2700 E Tremont Ave, Bronx, NY 10461',
        'lat' => 40.84253,
        'lng' => -73.84602,
        'emoji' => '🎨',
        'tags' => ['Bronx', 'Throggs Neck', 'Art', 'Community Space'],
    ],
    [
        'name' => 'Thomas Jefferson Recreation Center',
        'short_name' => 'Thomas Jefferson Rec Center',
        'description' => 'NYC Parks recreation center in East Harlem offering fitness programs, sports leagues, pool access, and community events.',
        'address' => '2180 1st Ave, New York, NY 10029',
        'lat' => 40.79365,
        'lng' => -73.93678,
        'emoji' => '🏊',
        'tags' => ['Manhattan', 'East Harlem', 'Recreation', 'Fitness'],
    ],
    [
        'name' => 'Hunts Point Recreation Center',
        'description' => 'NYC Parks recreation center in the Bronx offering fitness classes, sports programs, and community events.',
        'address' => '765 Manida St, Bronx, NY 10474',
        'lat' => 40.81496,
        'lng' => -73.88909,
        'emoji' => '🏋️',
        'tags' => ['Bronx', 'Hunts Point', 'Recreation', 'Fitness'],
    ],
    [
        'name' => 'Al Oerter Recreation Center',
        'description' => 'NYC Parks recreation center in Flushing Meadows-Corona Park offering youth sports leagues, fitness, and community programs.',
        'address' => '131-40 Fowler Ave, Flushing, NY 11355',
        'lat' => 40.75139,
        'lng' => -73.83389,
        'emoji' => '🏋️',
        'tags' => ['Queens', 'Flushing', 'Recreation', 'Fitness'],
    ],
    [
        'name' => 'Freshkills Park',
        'description' => 'Former landfill transformed into one of NYC\'s largest parks, offering nature walks, public art, and ecological programming on Staten Island.',
        'address' => '350 Wild Ave, Staten Island, NY 10314',
        'lat' => 40.58516,
        'lng' => -74.17868,
        'emoji' => '🌳',
        'tags' => ['Staten Island', 'Park', 'Nature', 'Outdoor'],
    ],
    [
        'name' => 'Forest Park',
        'description' => 'Large park in central Queens featuring hiking trails, a golf course, a bandshell, and seasonal nature programs.',
        'address' => 'Myrtle Ave & Union Tpke, Woodhaven, NY 11421',
        'lat' => 40.70423,
        'lng' => -73.84202,
        'emoji' => '🌳',
        'tags' => ['Queens', 'Woodhaven', 'Park', 'Nature', 'Outdoor'],
    ],
    [
        'name' => 'Sunset Park',
        'short_name' => 'Sunset Park (Park)',
        'description' => 'Hilltop park in Brooklyn offering panoramic views of the Manhattan skyline and New York Harbor, with playgrounds and seasonal events.',
        'address' => '43rd St & 7th Ave, Brooklyn, NY 11232',
        'lat' => 40.64874,
        'lng' => -74.00726,
        'emoji' => '🌳',
        'tags' => ['Brooklyn', 'Sunset Park', 'Park', 'Outdoor'],
    ],
    [
        'name' => 'Maria Hernandez Park',
        'description' => 'Community park in Bushwick hosting outdoor concerts, art events, and seasonal community programming.',
        'address' => 'Suydam St & Knickerbocker Ave, Brooklyn, NY 11237',
        'lat' => 40.70319,
        'lng' => -73.92381,
        'emoji' => '🌳',
        'tags' => ['Brooklyn', 'Bushwick', 'Park', 'Outdoor'],
    ],
    [
        'name' => 'Von Briesen Park',
        'description' => 'Waterfront park on the northeastern shore of Staten Island with views of the Verrazzano-Narrows Bridge and nature trails.',
        'address' => 'Bay St & North Rd, Staten Island, NY 10305',
        'lat' => 40.60735,
        'lng' => -74.05975,
        'emoji' => '🌳',
        'tags' => ['Staten Island', 'Park', 'Nature', 'Outdoor'],
    ],
    [
        'name' => 'Queensbridge Park',
        'description' => 'Waterfront park in Long Island City along the East River with sports facilities, playgrounds, and community events.',
        'address' => 'Vernon Blvd, Long Island City, NY 11101',
        'lat' => 40.75667,
        'lng' => -73.94861,
        'emoji' => '🌳',
        'tags' => ['Queens', 'Long Island City', 'Park', 'Outdoor'],
    ],
    [
        'name' => 'Oakwood Beach',
        'description' => 'Coastal beach and nature area on Staten Island\'s eastern shore, popular for beach cleanups and environmental education events.',
        'address' => 'Oakwood Beach, Staten Island, NY 10306',
        'lat' => 40.55261,
        'lng' => -74.11431,
        'emoji' => '🌳',
        'tags' => ['Staten Island', 'Park', 'Nature', 'Outdoor'],
    ],
    [
        'name' => 'Cottages Hill New Brighton Park',
        'description' => 'Community park in New Brighton, Staten Island with playgrounds and a community garden.',
        'address' => '171 Harvard Ave, Staten Island, NY 10301',
        'lat' => 40.63909,
        'lng' => -74.08972,
        'emoji' => '🌳',
        'tags' => ['Staten Island', 'New Brighton', 'Park', 'Outdoor'],
    ],
    [
        'name' => 'Uniondale Public Library',
        'description' => 'Public library in Uniondale, Nassau County, hosting community events, workshops, and auditions.',
        'address' => '400 Uniondale Ave, Uniondale, NY 11553',
        'lat' => 40.70623,
        'lng' => -73.59303,
        'emoji' => '📚',
        'tags' => ['Long Island', 'Nassau County', 'Library'],
    ],
    [
        'name' => 'AMC 34th Street 14',
        'description' => 'Multiplex movie theater near Penn Station in Midtown Manhattan.',
        'address' => '312 W 34th St, New York, NY 10001',
        'lat' => 40.75237,
        'lng' => -73.99467,
        'emoji' => '🎬',
        'tags' => ['Manhattan', 'Midtown', 'Film'],
    ],
    [
        'name' => 'The Door',
        'description' => 'Youth development center in SoHo serving young people ages 12-24 with arts programming, community events, and social services.',
        'address' => '555 Broome St, New York, NY 10013',
        'lat' => 40.72411,
        'lng' => -74.00556,
        'emoji' => '🫱🏾‍🫲🏼',
        'tags' => ['Manhattan', 'SoHo', 'Community Space', 'Youth'],
    ],
    [
        'name' => 'QUNO Quaker House',
        'short_name' => 'Quaker House',
        'description' => 'The Quaker United Nations Office near UN headquarters, hosting worship, lunch talks, and peace-focused community gatherings.',
        'address' => '777 United Nations Plaza, New York, NY 10017',
        'lat' => 40.75012,
        'lng' => -73.96930,
        'emoji' => '🕊️',
        'tags' => ['Manhattan', 'Turtle Bay', 'Quaker', 'Community Space'],
    ],
    [
        'name' => 'The Word Is Change',
        'description' => 'Independent bookstore in Bed-Stuy hosting author readings, book launches, and community literary events.',
        'address' => '368 Tompkins Ave, Brooklyn, NY 11216',
        'lat' => 40.68485,
        'lng' => -73.94455,
        'emoji' => '📚',
        'tags' => ['Brooklyn', 'Bedford-Stuyvesant', 'Books', 'Literature'],
    ],
    [
        'name' => 'Mingles Event Space',
        'description' => 'Nightlife venue and event space in the Bronx featuring Caribbean cuisine, DJ sets, and private event rentals.',
        'address' => '4012 Boston Rd, Bronx, NY 10475',
        'lat' => 40.88386,
        'lng' => -73.83249,
        'emoji' => '🪩',
        'tags' => ['Bronx', 'Co-op City', 'Nightlife', 'Event Space'],
    ],
    [
        'name' => 'Urbani Truffles',
        'description' => 'Italian truffle company\'s U.S. headquarters with a retail showroom hosting truffle tastings and culinary education events.',
        'address' => '10 West End Ave, New York, NY 10023',
        'lat' => 40.77207,
        'lng' => -73.98990,
        'emoji' => '🍱',
        'tags' => ['Manhattan', 'Lincoln Square', 'Food & Drink', 'Education'],
    ],
    [
        'name' => 'National Dance Institute',
        'short_name' => 'NDI',
        'description' => 'Renowned dance education organization in Harlem founded by Jacques d\'Amboise, offering youth dance programs and teacher workshops.',
        'address' => '217 W 147th St, New York, NY 10039',
        'lat' => 40.82377,
        'lng' => -73.93979,
        'emoji' => '🎭',
        'tags' => ['Manhattan', 'Harlem', 'Dance', 'Education'],
    ],
    [
        'name' => 'Mise-En Place',
        'short_name' => 'MIS-EN PLACE',
        'description' => 'Contemporary music performance space in Harlem, home of Ensemble Mise-En, hosting experimental concerts and international music festivals.',
        'address' => '45 St Nicholas Ave, New York, NY 10026',
        'lat' => 40.80015,
        'lng' => -73.95287,
        'emoji' => '🎭',
        'alt_names' => ['MIS-EN PLACE', 'MIS-EN_PLACE'],
        'tags' => ['Manhattan', 'Harlem', 'Live Music', 'Contemporary Music'],
    ],
    [
        'name' => 'The West Village Rehearsal Co-op',
        'description' => 'Subsidized shared rehearsal space for independent theater companies in the Meatpacking District, operated by IndieSpace.',
        'address' => '68 Gansevoort St, New York, NY 10014',
        'lat' => 40.73927,
        'lng' => -74.00760,
        'emoji' => '🎭',
        'tags' => ['Manhattan', 'Meatpacking District', 'Theatre', 'Rehearsal Space'],
    ],
    [
        'name' => 'Samsung Experience Store Queens Center',
        'short_name' => 'Samsung Experience Store',
        'description' => 'Samsung retail and experience store in Queens Center Mall hosting product launches, meet-and-greets, and interactive technology events.',
        'address' => '90-15 Queens Blvd, Elmhurst, NY 11373',
        'lat' => 40.73450,
        'lng' => -73.86986,
        'emoji' => '💻',
        'tags' => ['Queens', 'Elmhurst', 'Tech', 'Retail'],
    ],
    [
        'name' => 'Frank White Memorial Garden',
        'description' => 'Community garden in Hamilton Heights hosting composting workshops, environmental education, and neighborhood gatherings.',
        'address' => '506 W 143rd St, New York, NY 10031',
        'lat' => 40.82427,
        'lng' => -73.94983,
        'emoji' => '🌱',
        'tags' => ['Manhattan', 'Hamilton Heights', 'Garden', 'Community Space'],
    ],
    [
        'name' => 'NYU Tandon School of Engineering',
        'short_name' => 'NYU Tandon',
        'description' => 'NYU\'s engineering school in Downtown Brooklyn hosting tech talks, academic events, and community meetups.',
        'address' => '370 Jay St, Brooklyn, NY 11201',
        'lat' => 40.69315,
        'lng' => -73.98745,
        'emoji' => '🎓',
        'tags' => ['Brooklyn', 'Downtown Brooklyn', 'University', 'Tech'],
    ],
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
Add new locations to the database

Usage:
  php scripts/add_locations.php [options]

Options:
  --production, -p    Add to production database (default: local)
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

$env = $is_production ? 'production' : 'local';
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
    // Test connection
    $test = run_ssh_query($db_config, "SELECT 1");
    if (trim($test) !== '1') {
        echo "Connection failed: $test\n";
        exit(1);
    }
    echo "Connected to $env database via SSH\n\n";
    $pdo = null;  // Not used for SSH mode
} else {
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
}

// Helper functions for database operations
function escape_sql($value) {
    if ($value === null) return 'NULL';
    return "'" . addslashes($value) . "'";
}

function check_exists_pdo($pdo, $name) {
    $stmt = $pdo->prepare("SELECT id FROM locations WHERE name = ?");
    $stmt->execute([$name]);
    $row = $stmt->fetch(PDO::FETCH_ASSOC);
    return $row ? $row['id'] : null;
}

function check_exists_ssh($config, $name) {
    $sql = "SELECT id FROM locations WHERE name = " . escape_sql($name);
    $result = trim(run_ssh_query($config, $sql));
    return $result && is_numeric($result) ? $result : null;
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

function insert_location_ssh($config, $loc) {
    $sql = sprintf(
        "INSERT INTO locations (name, short_name, very_short_name, description, address, lat, lng, emoji, alt_emoji) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s); SELECT LAST_INSERT_ID();",
        escape_sql($loc['name']),
        escape_sql($loc['short_name'] ?? null),
        escape_sql($loc['very_short_name'] ?? null),
        escape_sql($loc['description'] ?? null),
        escape_sql($loc['address'] ?? null),
        $loc['lat'],
        $loc['lng'],
        escape_sql($loc['emoji']),
        escape_sql($loc['alt_emoji'] ?? null)
    );
    $result = trim(run_ssh_query($config, $sql));
    return $result;
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
            $stmt = $pdo->prepare("INSERT INTO tags (name) VALUES (?)");
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

function add_tags_ssh($config, $location_id, $tags) {
    $new_tags = [];
    $existing_tags = [];

    // Build a single SQL to insert tags and link them
    $tag_values = [];
    foreach ($tags as $tag_name) {
        $tag_values[] = "(" . escape_sql($tag_name) . ")";
    }

    // Insert tags (ignore duplicates)
    $sql = "INSERT IGNORE INTO tags (name) VALUES " . implode(", ", $tag_values);
    run_ssh_query($config, $sql);

    // Link tags to location
    $tag_list = implode(", ", array_map('escape_sql', $tags));
    $sql = "INSERT INTO location_tags (location_id, tag_id) SELECT $location_id, id FROM tags WHERE name IN ($tag_list)";
    run_ssh_query($config, $sql);

    // Get which tags are new vs existing (approximate - all count as existing for SSH)
    return ['existing' => $tags, 'new' => []];
}

function get_stats_pdo($pdo) {
    $result = $pdo->query("SELECT COUNT(*) as total, MAX(id) as max_id FROM locations");
    return $result->fetch(PDO::FETCH_ASSOC);
}

function get_stats_ssh($config) {
    $result = run_ssh_query($config, "SELECT COUNT(*), MAX(id) FROM locations");
    $parts = explode("\t", trim($result));
    return ['total' => $parts[0] ?? '?', 'max_id' => $parts[1] ?? '?'];
}

// Check for duplicates
$duplicates = [];
foreach ($new_locations as $loc) {
    $existing_id = $use_ssh
        ? check_exists_ssh($db_config, $loc['name'])
        : check_exists_pdo($pdo, $loc['name']);
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
    $existing_id = $use_ssh
        ? check_exists_ssh($db_config, $loc['name'])
        : check_exists_pdo($pdo, $loc['name']);

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
            $new_id = $use_ssh
                ? insert_location_ssh($db_config, $loc)
                : insert_location_pdo($pdo, $loc);

            echo "  ADD: {$loc['name']} {$loc['emoji']} (ID: $new_id)\n";

            // Add tags
            if (!empty($tags)) {
                $tag_result = $use_ssh
                    ? add_tags_ssh($db_config, $new_id, $tags)
                    : add_tags_pdo($pdo, $new_id, $tags);

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
$stats = $use_ssh ? get_stats_ssh($db_config) : get_stats_pdo($pdo);
echo "\nDatabase now has {$stats['total']} locations (max ID: {$stats['max_id']})\n";

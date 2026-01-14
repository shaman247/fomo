#!/usr/bin/env php
<?php
/**
 * Archive Outdated Events Script
 *
 * One-off script to archive all active events where ALL their crawl sources
 * are from out-of-date crawls (i.e., there is a newer crawl from that source).
 *
 * An event will only be archived if:
 * - For EVERY website that has ever referenced this event (via event_sources),
 *   the most recent crawl from that website does NOT include this event
 * - At least one of those websites has been successfully crawled
 *
 * Usage:
 *   php scripts/archive_outdated_events.php [--dry-run] [--verbose]
 *
 * Options:
 *   --dry-run    Show what would be archived without making changes
 *   --verbose    Show detailed information about each event
 */

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
// SCRIPT LOGIC (no need to edit below)
// ============================================================================

// Parse command-line arguments
$is_production = in_array('--production', $argv) || in_array('-p', $argv);
$dryRun = in_array('--dry-run', $argv);
$verbose = in_array('--verbose', $argv);

if (in_array('--help', $argv) || in_array('-h', $argv)) {
    $usage = <<<'USAGE'
Archive Outdated Events Script

One-off script to archive all active events where ALL their crawl sources
are from out-of-date crawls (i.e., there is a newer crawl from that source).

Usage:
  php scripts/archive_outdated_events.php [options]

Options:
  --production    Use production database (default: local)
  --dry-run       Show what would be archived without making changes
  --verbose       Show detailed information about each event
  --help, -h      Show this help message

USAGE;
    echo $usage;
    exit(0);
}

$env = $is_production ? 'production' : 'local';
$db_config = $config[$env];

echo "Archive Outdated Events Script\n";
echo str_repeat("=", 80) . "\n";
echo "Environment: " . strtoupper($env) . "\n";

if ($dryRun) {
    echo "🔍 DRY RUN MODE - No changes will be made\n";
}
echo "\n";

try {
    // Connect to database
    if ($is_production && $db_config['via_ssh']) {
        // For production, establish SSH tunnel
        echo "Establishing SSH tunnel to production database...\n";
        $local_port = 33060 + rand(0, 999); // Random port to avoid conflicts
        $ssh_cmd = sprintf(
            'ssh -i %s -p %d -L %d:localhost:3306 -N %s@%s > /dev/null 2>&1 & echo $!',
            escapeshellarg($db_config['ssh_key']),
            $db_config['ssh_port'],
            $local_port,
            escapeshellarg($db_config['ssh_user']),
            escapeshellarg($db_config['ssh_host'])
        );
        $ssh_pid = trim(shell_exec($ssh_cmd));
        if (!$ssh_pid) {
            throw new Exception("Failed to establish SSH tunnel");
        }
        echo "SSH tunnel established (PID: $ssh_pid) on port $local_port\n\n";
        sleep(2); // Give the tunnel time to establish

        // Connect via tunnel
        $dsn = sprintf('mysql:host=127.0.0.1;port=%d;dbname=%s;charset=utf8mb4',
            $local_port, $db_config['dbname']);
        $pdo = new PDO($dsn, $db_config['user'], $db_config['password']);

        // Register shutdown function to close tunnel
        register_shutdown_function(function() use ($ssh_pid) {
            shell_exec("kill $ssh_pid 2>/dev/null");
        });
    } else {
        // Local connection
        $dsn = sprintf('mysql:host=%s;port=%d;dbname=%s;charset=utf8mb4',
            $db_config['host'], $db_config['port'], $db_config['dbname']);
        $pdo = new PDO($dsn, $db_config['user'], $db_config['password']);
    }

    $pdo->setAttribute(PDO::ATTR_ERRMODE, PDO::ERRMODE_EXCEPTION);

    // First, get list of events that will be archived to check for upcoming ones
    echo "Finding events to archive...\n\n";

    $query = "
        SELECT e.id, e.name,
               (SELECT MIN(eo.start_date)
                FROM event_occurrences eo
                WHERE eo.event_id = e.id
                  AND eo.start_date >= CURDATE()) as next_occurrence,
               GROUP_CONCAT(DISTINCT w.name ORDER BY w.name SEPARATOR ', ') as source_websites
        FROM events e
        -- Get all websites that have ever referenced this event
        LEFT JOIN event_sources es ON es.event_id = e.id
        LEFT JOIN crawl_events ce ON es.crawl_event_id = ce.id
        LEFT JOIN crawl_results cr ON ce.crawl_result_id = cr.id
        LEFT JOIN websites w ON cr.website_id = w.id
        WHERE e.archived = FALSE
          -- At least one source website has been successfully crawled
          AND EXISTS (
              SELECT 1
              FROM event_sources es2
              JOIN crawl_events ce2 ON es2.crawl_event_id = ce2.id
              JOIN crawl_results cr2 ON ce2.crawl_result_id = cr2.id
              WHERE es2.event_id = e.id
                AND cr2.status IN ('processed', 'extracted')
                AND cr2.processed_at IS NOT NULL
          )
          -- For EVERY website that references this event, event is missing from latest crawl
          AND NOT EXISTS (
              SELECT 1
              FROM event_sources es3
              JOIN crawl_events ce3 ON es3.crawl_event_id = ce3.id
              JOIN crawl_results cr3 ON ce3.crawl_result_id = cr3.id
              WHERE es3.event_id = e.id
                -- This source is from the latest crawl of its website
                AND cr3.processed_at = (
                    SELECT MAX(cr4.processed_at)
                    FROM crawl_results cr4
                    WHERE cr4.website_id = cr3.website_id
                      AND cr4.status IN ('processed', 'extracted')
                      AND cr4.processed_at IS NOT NULL
                )
          )
        GROUP BY e.id, e.name
        ORDER BY next_occurrence IS NULL DESC, next_occurrence ASC, e.name
    ";

    $stmt = $pdo->query($query);
    $events_to_archive = $stmt->fetchAll(PDO::FETCH_ASSOC);

    if (empty($events_to_archive)) {
        echo "✓ No events found that need archiving.\n";
        exit(0);
    }

    echo "Found " . count($events_to_archive) . " event(s) to archive:\n\n";

    $upcoming_count = 0;
    $past_count = 0;

    foreach ($events_to_archive as $event) {
        $is_upcoming = !empty($event['next_occurrence']);

        if ($is_upcoming) {
            $upcoming_count++;
            $indicator = "⚠️";
        } else {
            $past_count++;
            $indicator = "  ";
        }

        $date_info = $is_upcoming
            ? "Next: " . date('Y-m-d', strtotime($event['next_occurrence']))
            : "No upcoming dates";

        echo "$indicator Event ID {$event['id']}: {$event['name']}\n";
        echo "   $date_info\n";

        if ($verbose) {
            echo "   Sources: " . ($event['source_websites'] ?: 'Unknown') . "\n";
        }

        echo "\n";
    }

    echo str_repeat("-", 80) . "\n";
    echo "Total: " . count($events_to_archive) . " events\n";
    echo "  - Past events: $past_count\n";
    echo "  - Upcoming events: $upcoming_count\n";

    if ($upcoming_count > 0) {
        echo "\n⚠️  WARNING: $upcoming_count upcoming event(s) will be archived.\n";
        echo "   This may indicate crawl failures or legitimate event changes.\n";
    }

    echo "\n";

    // Perform the archiving unless in dry-run mode
    if (!$dryRun) {
        echo "Archiving events...\n";

        $updateQuery = "
            UPDATE events e
            SET archived = TRUE
            WHERE e.archived = FALSE
              -- At least one source website has been successfully crawled
              AND EXISTS (
                  SELECT 1
                  FROM event_sources es
                  JOIN crawl_events ce ON es.crawl_event_id = ce.id
                  JOIN crawl_results cr ON ce.crawl_result_id = cr.id
                  WHERE es.event_id = e.id
                    AND cr.status IN ('processed', 'extracted')
                    AND cr.processed_at IS NOT NULL
              )
              -- For EVERY website that references this event, event is missing from latest crawl
              AND NOT EXISTS (
                  SELECT 1
                  FROM event_sources es2
                  JOIN crawl_events ce2 ON es2.crawl_event_id = ce2.id
                  JOIN crawl_results cr2 ON ce2.crawl_result_id = cr2.id
                  WHERE es2.event_id = e.id
                    -- This source is from the latest crawl of its website
                    AND cr2.processed_at = (
                        SELECT MAX(cr3.processed_at)
                        FROM crawl_results cr3
                        WHERE cr3.website_id = cr2.website_id
                          AND cr3.status IN ('processed', 'extracted')
                          AND cr3.processed_at IS NOT NULL
                    )
              )
        ";

        $stmt = $pdo->exec($updateQuery);

        echo "✓ Successfully archived " . count($events_to_archive) . " event(s).\n";
    } else {
        echo "Dry run complete. Use without --dry-run to archive these events.\n";
    }

} catch (PDOException $e) {
    echo "❌ Database error: " . $e->getMessage() . "\n";
    exit(1);
} catch (Exception $e) {
    echo "❌ Error: " . $e->getMessage() . "\n";
    exit(1);
}

echo "\n✓ Done.\n";

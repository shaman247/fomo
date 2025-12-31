<?php
/**
 * Website Detail API
 *
 * Returns HTML fragment with detailed website information.
 */

header('Content-Type: text/html; charset=utf-8');

if (!isset($_GET['id']) || !is_numeric($_GET['id'])) {
    echo '<p style="color:#c8535b">Invalid website ID</p>';
    exit;
}

$website_id = (int) $_GET['id'];

// Database configuration
$env = getenv('FOMO_ENV') ?: 'local';

$db_configs = [
    'local' => [
        'host' => 'localhost',
        'database' => 'fomo',
        'user' => 'root',
        'password' => ''
    ],
    'production' => [
        'host' => 'localhost',
        'database' => 'fomoowsq_fomo',
        'user' => 'fomoowsq_root',
        'password' => 'REDACTED_DB_PASSWORD'
    ]
];

$config = $db_configs[$env] ?? $db_configs['local'];

try {
    $pdo = new PDO(
        "mysql:host={$config['host']};dbname={$config['database']};charset=utf8mb4",
        $config['user'],
        $config['password'],
        [PDO::ATTR_ERRMODE => PDO::ERRMODE_EXCEPTION]
    );
} catch (PDOException $e) {
    echo '<p style="color:#c8535b">Database error</p>';
    exit;
}

// Get website details
$stmt = $pdo->prepare("
    SELECT w.*,
           (SELECT COUNT(*) FROM website_urls wu WHERE wu.website_id = w.id) as url_count
    FROM websites w
    WHERE w.id = ?
");
$stmt->execute([$website_id]);
$website = $stmt->fetch(PDO::FETCH_ASSOC);

if (!$website) {
    echo '<p style="color:#c8535b">Website not found</p>';
    exit;
}

// Get URLs
$urls = $pdo->prepare("SELECT url, sort_order FROM website_urls WHERE website_id = ? ORDER BY sort_order");
$urls->execute([$website_id]);
$urls = $urls->fetchAll(PDO::FETCH_ASSOC);

// Get locations
$locations = $pdo->prepare("
    SELECT l.id, l.name, l.lat, l.lng
    FROM website_locations wl
    JOIN locations l ON wl.location_id = l.id
    WHERE wl.website_id = ?
");
$locations->execute([$website_id]);
$locations = $locations->fetchAll(PDO::FETCH_ASSOC);

// Get recent crawl history (last 10)
$crawl_history = $pdo->prepare("
    SELECT cr.id, cr.status, cr.event_count, cr.error_message,
           cr.crawled_at, cr.extracted_at, cr.processed_at,
           crun.run_date,
           LENGTH(cr.crawled_content) as content_size,
           LENGTH(cr.extracted_content) as extracted_size
    FROM crawl_results cr
    JOIN crawl_runs crun ON cr.crawl_run_id = crun.id
    WHERE cr.website_id = ?
    ORDER BY crun.run_date DESC
    LIMIT 10
");
$crawl_history->execute([$website_id]);
$crawl_history = $crawl_history->fetchAll(PDO::FETCH_ASSOC);

// Helper
function h($str) { return htmlspecialchars($str ?? '', ENT_QUOTES, 'UTF-8'); }
function formatBytes($bytes) {
    if (!$bytes) return '-';
    if ($bytes < 1024) return $bytes . ' B';
    if ($bytes < 1048576) return round($bytes / 1024, 1) . ' KB';
    return round($bytes / 1048576, 1) . ' MB';
}

$daysAgo = $website['last_crawled_at']
    ? (new DateTime($website['last_crawled_at']))->diff(new DateTime())->days
    : null;
?>

<div class="detail-section">
    <h3>Configuration</h3>
    <dl class="detail-grid">
        <dt>ID</dt><dd><?= $website['id'] ?></dd>
        <dt>Frequency</dt><dd><?= $website['crawl_frequency'] ?: 7 ?> days</dd>
        <dt>Last Crawl</dt>
        <dd>
            <?php if ($daysAgo !== null): ?>
                <?= $daysAgo === 0 ? 'Today' : ($daysAgo === 1 ? 'Yesterday' : $daysAgo . ' days ago') ?>
                <span style="color:var(--secondary-text)">(<?= date('M j, Y', strtotime($website['last_crawled_at'])) ?>)</span>
            <?php else: ?>
                Never
            <?php endif; ?>
        </dd>
        <dt>Disabled</dt><dd><?= $website['disabled'] ? 'Yes' : 'No' ?></dd>
        <?php if ($website['selector']): ?>
        <dt>Selector</dt><dd><code class="config-value"><?= h($website['selector']) ?></code></dd>
        <?php endif; ?>
        <?php if ($website['num_clicks']): ?>
        <dt>Clicks</dt><dd><?= $website['num_clicks'] ?></dd>
        <?php endif; ?>
        <?php if ($website['max_pages']): ?>
        <dt>Max Pages</dt><dd><?= $website['max_pages'] ?></dd>
        <?php endif; ?>
        <dt>Created</dt><dd style="color:var(--secondary-text)"><?= date('M j, Y', strtotime($website['created_at'])) ?></dd>
    </dl>
</div>

<?php if (!empty($urls)): ?>
<div class="detail-section">
    <h3>URLs (<?= count($urls) ?>)</h3>
    <ul class="url-list">
        <?php foreach ($urls as $url): ?>
        <li><a href="<?= h($url['url']) ?>" target="_blank"><?= h($url['url']) ?></a></li>
        <?php endforeach; ?>
    </ul>
</div>
<?php endif; ?>

<?php if (!empty($locations)): ?>
<div class="detail-section">
    <h3>Locations (<?= count($locations) ?>)</h3>
    <ul class="url-list">
        <?php foreach ($locations as $loc): ?>
        <li>
            <?= h($loc['name']) ?>
            <?php if ($loc['lat'] && $loc['lng']): ?>
            <span style="color:var(--secondary-text);font-size:11px">(<?= round($loc['lat'], 4) ?>, <?= round($loc['lng'], 4) ?>)</span>
            <?php endif; ?>
        </li>
        <?php endforeach; ?>
    </ul>
</div>
<?php endif; ?>

<?php if ($website['keywords']): ?>
<div class="detail-section">
    <h3>Keywords</h3>
    <p><code class="config-value"><?= h($website['keywords']) ?></code></p>
</div>
<?php endif; ?>

<?php if ($website['notes']): ?>
<div class="detail-section">
    <h3>Notes</h3>
    <p style="font-size:12px;white-space:pre-wrap"><?= h($website['notes']) ?></p>
</div>
<?php endif; ?>

<?php if (!empty($crawl_history)): ?>
<div class="detail-section">
    <h3>Crawl History</h3>
    <div class="crawl-history">
        <?php foreach ($crawl_history as $crawl): ?>
        <div class="crawl-item">
            <span class="date"><?= date('M j', strtotime($crawl['run_date'])) ?></span>
            <?php
            $badge_class = [
                'processed' => 'processed',
                'failed' => 'failed',
                'crawled' => 'crawled',
                'extracted' => 'extracted',
                'pending' => 'never'
            ][$crawl['status']] ?? 'never';
            ?>
            <span class="badge badge-<?= $badge_class ?>"><?= ucfirst($crawl['status']) ?></span>
            <span class="events"><?= $crawl['event_count'] !== null ? $crawl['event_count'] . ' events' : '-' ?></span>
            <span style="color:var(--secondary-text);font-size:11px">
                <?= formatBytes($crawl['content_size']) ?>
            </span>
        </div>
        <?php if ($crawl['status'] === 'failed' && $crawl['error_message']): ?>
        <div class="error-msg" style="margin:-4px 0 8px 80px;font-size:10px"><?= h(substr($crawl['error_message'], 0, 300)) ?></div>
        <?php endif; ?>
        <?php endforeach; ?>
    </div>
</div>
<?php endif; ?>

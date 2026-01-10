<?php
/**
 * Website Detail API
 *
 * Returns HTML fragment with detailed website information.
 */

header('Content-Type: text/html; charset=utf-8');
require_once 'db_config.php';

if (!isset($_GET['id']) || !is_numeric($_GET['id'])) {
    echo '<p style="color:#c8535b">Invalid website ID</p>';
    exit;
}

$website_id = (int) $_GET['id'];

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

?>

<div class="detail-section">
    <h3>Configuration</h3>
    <dl class="detail-grid">
        <dt>ID</dt><dd><?= $website['id'] ?></dd>
        <?php if ($website['base_url']): ?>
        <dt>Website</dt><dd><a href="<?= h($website['base_url']) ?>" target="_blank" style="color:var(--accent-color);text-decoration:none"><?= h($website['base_url']) ?></a></dd>
        <?php endif; ?>
        <dt>Frequency</dt><dd><?= $website['crawl_frequency'] ? $website['crawl_frequency'] . ' days' : 'Default' ?></dd>
        <dt>Last Crawl</dt>
        <dd><?= $website['last_crawled_at'] ? date('M j, Y', strtotime($website['last_crawled_at'])) : 'Never' ?></dd>
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
<details class="detail-section" open>
    <summary><h3>URLs (<?= count($urls) ?>)</h3></summary>
    <ul class="url-list">
        <?php foreach ($urls as $url): ?>
        <li><a href="<?= h($url['url']) ?>" target="_blank"><?= h($url['url']) ?></a></li>
        <?php endforeach; ?>
    </ul>
</details>
<?php endif; ?>

<?php if (!empty($locations)): ?>
<details class="detail-section" open>
    <summary><h3>Locations (<?= count($locations) ?>)</h3></summary>
    <ul class="item-list">
        <?php foreach ($locations as $loc): ?>
        <li>
            <a href="javascript:void(0)" onclick="openDetail('locations', <?= $loc['id'] ?>, '<?= h(addslashes($loc['name'])) ?>')"><?= h($loc['name']) ?></a>
            <?php if ($loc['lat'] && $loc['lng']): ?>
            <span style="color:var(--secondary-text);font-size:11px">(<?= round($loc['lat'], 4) ?>, <?= round($loc['lng'], 4) ?>)</span>
            <?php endif; ?>
        </li>
        <?php endforeach; ?>
    </ul>
</details>
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
<details class="detail-section" open>
    <summary><h3>Crawl History (<?= count($crawl_history) ?>)</h3></summary>
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
</details>
<?php endif; ?>

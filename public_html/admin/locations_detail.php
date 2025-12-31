<?php
/**
 * Location Detail API
 *
 * Returns HTML fragment with detailed location information.
 */

header('Content-Type: text/html; charset=utf-8');
require_once 'db_config.php';

if (!isset($_GET['id']) || !is_numeric($_GET['id'])) {
    echo '<p style="color:#c8535b">Invalid location ID</p>';
    exit;
}

$location_id = (int) $_GET['id'];

// Get location details
$stmt = $pdo->prepare("
    SELECT l.*
    FROM locations l
    WHERE l.id = ?
");
$stmt->execute([$location_id]);
$location = $stmt->fetch(PDO::FETCH_ASSOC);

if (!$location) {
    echo '<p style="color:#c8535b">Location not found</p>';
    exit;
}

// Get linked websites
$websites = $pdo->prepare("
    SELECT w.id, w.name, w.disabled,
           (SELECT cr.status FROM crawl_results cr
            JOIN crawl_runs crun ON cr.crawl_run_id = crun.id
            WHERE cr.website_id = w.id
            ORDER BY crun.run_date DESC LIMIT 1) as latest_status
    FROM websites w
    JOIN website_locations wl ON w.id = wl.website_id
    WHERE wl.location_id = ?
    ORDER BY w.name
");
$websites->execute([$location_id]);
$websites = $websites->fetchAll(PDO::FETCH_ASSOC);

// Get recent events at this location
$events = $pdo->prepare("
    SELECT ce.id, ce.name, ceo.start_date, ceo.start_time
    FROM crawl_events ce
    JOIN crawl_results cr ON ce.crawl_result_id = cr.id
    JOIN website_locations wl ON cr.website_id = wl.website_id
    LEFT JOIN crawl_event_occurrences ceo ON ce.id = ceo.crawl_event_id
    WHERE wl.location_id = ?
    AND cr.status = 'processed'
    AND ceo.start_date >= CURDATE()
    ORDER BY ceo.start_date, ceo.start_time
    LIMIT 15
");
$events->execute([$location_id]);
$events = $events->fetchAll(PDO::FETCH_ASSOC);

// Get popular tags at this location
$tags = $pdo->prepare("
    SELECT cet.tag, COUNT(*) as count
    FROM crawl_event_tags cet
    JOIN crawl_events ce ON cet.crawl_event_id = ce.id
    JOIN crawl_results cr ON ce.crawl_result_id = cr.id
    JOIN website_locations wl ON cr.website_id = wl.website_id
    WHERE wl.location_id = ?
    AND cr.status = 'processed'
    GROUP BY cet.tag
    ORDER BY count DESC
    LIMIT 10
");
$tags->execute([$location_id]);
$tags = $tags->fetchAll(PDO::FETCH_ASSOC);
?>

<div class="detail-section">
    <h3>Details</h3>
    <dl class="detail-grid">
        <dt>ID</dt><dd><?= $location['id'] ?></dd>
        <dt>Name</dt><dd><?= h($location['name']) ?></dd>
        <?php if ($location['emoji']): ?>
        <dt>Emoji</dt><dd><?= $location['emoji'] ?></dd>
        <?php endif; ?>
        <?php if ($location['address']): ?>
        <dt>Address</dt><dd><?= h($location['address']) ?></dd>
        <?php endif; ?>
        <?php if ($location['lat'] && $location['lng']): ?>
        <dt>Coordinates</dt>
        <dd>
            <a href="https://www.google.com/maps?q=<?= $location['lat'] ?>,<?= $location['lng'] ?>"
               target="_blank" style="color:var(--accent-color);text-decoration:none">
                <?= round($location['lat'], 5) ?>, <?= round($location['lng'], 5) ?>
            </a>
        </dd>
        <?php else: ?>
        <dt>Coordinates</dt><dd style="color:var(--warning)">Not set</dd>
        <?php endif; ?>
        <dt>Created</dt><dd style="color:var(--secondary-text)"><?= date('M j, Y', strtotime($location['created_at'])) ?></dd>
    </dl>
</div>

<?php if (!empty($websites)): ?>
<div class="detail-section">
    <h3>Linked Websites (<?= count($websites) ?>)</h3>
    <ul class="item-list">
        <?php foreach ($websites as $w): ?>
        <li>
            <?= h($w['name']) ?>
            <?php if ($w['disabled']): ?>
                <span style="color:var(--secondary-text);font-size:10px">(disabled)</span>
            <?php endif; ?>
            <?php if ($w['latest_status'] === 'failed'): ?>
                <span style="color:var(--danger);font-size:10px">(failed)</span>
            <?php endif; ?>
        </li>
        <?php endforeach; ?>
    </ul>
</div>
<?php endif; ?>

<?php if (!empty($tags)): ?>
<div class="detail-section">
    <h3>Popular Tags</h3>
    <div style="display:flex;flex-wrap:wrap;gap:4px">
        <?php foreach ($tags as $tag): ?>
        <span style="background:var(--tertiary-bg);padding:2px 8px;border-radius:3px;font-size:11px">
            <?= h($tag['tag']) ?> <span style="color:var(--secondary-text)">(<?= $tag['count'] ?>)</span>
        </span>
        <?php endforeach; ?>
    </div>
</div>
<?php endif; ?>

<?php if (!empty($events)): ?>
<div class="detail-section">
    <h3>Upcoming Events</h3>
    <ul class="event-list">
        <?php foreach ($events as $e): ?>
        <li>
            <div><?= h($e['name']) ?></div>
            <div class="date">
                <?= date('M j', strtotime($e['start_date'])) ?>
                <?= $e['start_time'] ? date('g:ia', strtotime($e['start_time'])) : '' ?>
            </div>
        </li>
        <?php endforeach; ?>
    </ul>
</div>
<?php elseif (empty($websites)): ?>
<div class="detail-section">
    <p style="color:var(--secondary-text);font-size:12px">No websites linked to this location</p>
</div>
<?php else: ?>
<div class="detail-section">
    <p style="color:var(--secondary-text);font-size:12px">No upcoming events</p>
</div>
<?php endif; ?>

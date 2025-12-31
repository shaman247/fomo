<?php
/**
 * Tag Detail API
 *
 * Returns HTML fragment with detailed tag information.
 */

header('Content-Type: text/html; charset=utf-8');
require_once 'db_config.php';

if (!isset($_GET['tag']) || empty($_GET['tag'])) {
    echo '<p style="color:#c8535b">Invalid tag</p>';
    exit;
}

$tag = $_GET['tag'];

// Get tag statistics
$stats = $pdo->prepare("
    SELECT
        COUNT(DISTINCT cet.crawl_event_id) as event_count,
        COUNT(DISTINCT cr.website_id) as website_count,
        MIN(ceo.start_date) as first_event,
        MAX(ceo.start_date) as last_event,
        SUM(CASE WHEN ceo.start_date >= CURDATE() THEN 1 ELSE 0 END) as upcoming_count
    FROM crawl_event_tags cet
    JOIN crawl_events ce ON cet.crawl_event_id = ce.id
    JOIN crawl_results cr ON ce.crawl_result_id = cr.id
    LEFT JOIN crawl_event_occurrences ceo ON ce.id = ceo.crawl_event_id
    WHERE cet.tag = ? AND cr.status = 'processed'
");
$stats->execute([$tag]);
$stats = $stats->fetch(PDO::FETCH_ASSOC);

if (!$stats || $stats['event_count'] == 0) {
    echo '<p style="color:#c8535b">Tag not found</p>';
    exit;
}

// Get websites using this tag
$websites = $pdo->prepare("
    SELECT w.id, w.name, COUNT(DISTINCT ce.id) as event_count
    FROM websites w
    JOIN crawl_results cr ON w.id = cr.website_id
    JOIN crawl_events ce ON cr.id = ce.crawl_result_id
    JOIN crawl_event_tags cet ON ce.id = cet.crawl_event_id
    WHERE cet.tag = ? AND cr.status = 'processed'
    GROUP BY w.id, w.name
    ORDER BY event_count DESC
    LIMIT 10
");
$websites->execute([$tag]);
$websites = $websites->fetchAll(PDO::FETCH_ASSOC);

// Get locations using this tag
$locations = $pdo->prepare("
    SELECT l.id, l.name, COUNT(DISTINCT ce.id) as event_count
    FROM locations l
    JOIN website_locations wl ON l.id = wl.location_id
    JOIN crawl_results cr ON wl.website_id = cr.website_id
    JOIN crawl_events ce ON cr.id = ce.crawl_result_id
    JOIN crawl_event_tags cet ON ce.id = cet.crawl_event_id
    WHERE cet.tag = ? AND cr.status = 'processed'
    GROUP BY l.id, l.name
    ORDER BY event_count DESC
    LIMIT 10
");
$locations->execute([$tag]);
$locations = $locations->fetchAll(PDO::FETCH_ASSOC);

// Get related tags (co-occurring tags)
$related = $pdo->prepare("
    SELECT cet2.tag, COUNT(*) as count
    FROM crawl_event_tags cet1
    JOIN crawl_event_tags cet2 ON cet1.crawl_event_id = cet2.crawl_event_id
    WHERE cet1.tag = ? AND cet2.tag != ?
    GROUP BY cet2.tag
    ORDER BY count DESC
    LIMIT 10
");
$related->execute([$tag, $tag]);
$related = $related->fetchAll(PDO::FETCH_ASSOC);

// Get upcoming events with this tag
$events = $pdo->prepare("
    SELECT ce.id, ce.name, ceo.start_date, ceo.start_time, l.name as location_name
    FROM crawl_events ce
    JOIN crawl_results cr ON ce.crawl_result_id = cr.id
    JOIN crawl_event_tags cet ON ce.id = cet.crawl_event_id
    LEFT JOIN crawl_event_occurrences ceo ON ce.id = ceo.crawl_event_id
    LEFT JOIN website_locations wl ON cr.website_id = wl.website_id
    LEFT JOIN locations l ON wl.location_id = l.id
    WHERE cet.tag = ?
    AND cr.status = 'processed'
    AND ceo.start_date >= CURDATE()
    ORDER BY ceo.start_date, ceo.start_time
    LIMIT 15
");
$events->execute([$tag]);
$events = $events->fetchAll(PDO::FETCH_ASSOC);
?>

<div class="detail-section">
    <h3>Statistics</h3>
    <dl class="detail-grid">
        <dt>Total Events</dt><dd><?= number_format($stats['event_count']) ?></dd>
        <dt>Upcoming</dt><dd style="color:var(--accent-color)"><?= $stats['upcoming_count'] ?></dd>
        <dt>Sources</dt><dd><?= $stats['website_count'] ?></dd>
        <dt>First Seen</dt><dd style="color:var(--secondary-text)"><?= $stats['first_event'] ? date('M j, Y', strtotime($stats['first_event'])) : '-' ?></dd>
        <dt>Last Event</dt><dd style="color:var(--secondary-text)"><?= $stats['last_event'] ? date('M j, Y', strtotime($stats['last_event'])) : '-' ?></dd>
    </dl>
</div>

<?php if (!empty($websites)): ?>
<div class="detail-section">
    <h3>Top Sources</h3>
    <ul class="item-list">
        <?php foreach ($websites as $w): ?>
        <li>
            <?= h($w['name']) ?>
            <span style="color:var(--secondary-text);font-size:11px">(<?= $w['event_count'] ?> events)</span>
        </li>
        <?php endforeach; ?>
    </ul>
</div>
<?php endif; ?>

<?php if (!empty($locations)): ?>
<div class="detail-section">
    <h3>Top Locations</h3>
    <ul class="item-list">
        <?php foreach ($locations as $l): ?>
        <li>
            <?= h($l['name']) ?>
            <span style="color:var(--secondary-text);font-size:11px">(<?= $l['event_count'] ?> events)</span>
        </li>
        <?php endforeach; ?>
    </ul>
</div>
<?php endif; ?>

<?php if (!empty($related)): ?>
<div class="detail-section">
    <h3>Related Tags</h3>
    <div style="display:flex;flex-wrap:wrap;gap:4px">
        <?php foreach ($related as $r): ?>
        <span style="background:var(--tertiary-bg);padding:2px 8px;border-radius:3px;font-size:11px">
            <?= h($r['tag']) ?> <span style="color:var(--secondary-text)">(<?= $r['count'] ?>)</span>
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
                <?php if ($e['location_name']): ?>
                    <span style="color:var(--secondary-text)">@ <?= h($e['location_name']) ?></span>
                <?php endif; ?>
            </div>
        </li>
        <?php endforeach; ?>
    </ul>
</div>
<?php else: ?>
<div class="detail-section">
    <p style="color:var(--secondary-text);font-size:12px">No upcoming events with this tag</p>
</div>
<?php endif; ?>

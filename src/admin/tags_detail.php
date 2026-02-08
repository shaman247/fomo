<?php
/**
 * Tag Detail API
 *
 * Returns HTML fragment with detailed tag information.
 */

header('Content-Type: text/html; charset=utf-8');
require_once 'db_config.php';

if (!isset($_GET['tag']) || empty($_GET['tag'])) {
    echo '<p class="error-inline">Invalid tag</p>';
    exit;
}

$tag = $_GET['tag'];

// Get tag statistics
$stats = $pdo->prepare("
    SELECT
        COUNT(DISTINCT et.event_id) as event_count,
        COUNT(DISTINCT e.website_id) as website_count,
        MIN(eo.start_date) as first_event,
        MAX(eo.start_date) as last_event,
        SUM(CASE WHEN eo.start_date >= CURDATE() THEN 1 ELSE 0 END) as upcoming_count
    FROM tags t
    JOIN event_tags et ON t.id = et.tag_id
    JOIN events e ON et.event_id = e.id
    LEFT JOIN event_occurrences eo ON e.id = eo.event_id
    WHERE t.name = ?
");
$stats->execute([$tag]);
$stats = $stats->fetch(PDO::FETCH_ASSOC);

if (!$stats || $stats['event_count'] == 0) {
    echo '<p class="error-inline">Tag not found</p>';
    exit;
}

// Get websites using this tag
$websites = $pdo->prepare("
    SELECT w.id, w.name, COUNT(DISTINCT e.id) as event_count
    FROM websites w
    JOIN events e ON w.id = e.website_id
    JOIN event_tags et ON e.id = et.event_id
    JOIN tags t ON et.tag_id = t.id
    WHERE t.name = ?
    GROUP BY w.id, w.name
    ORDER BY event_count DESC
    LIMIT 10
");
$websites->execute([$tag]);
$websites = $websites->fetchAll(PDO::FETCH_ASSOC);

// Get locations using this tag
$locations = $pdo->prepare("
    SELECT l.id, l.name, COUNT(DISTINCT e.id) as event_count
    FROM locations l
    JOIN events e ON l.id = e.location_id
    JOIN event_tags et ON e.id = et.event_id
    JOIN tags t ON et.tag_id = t.id
    WHERE t.name = ?
    GROUP BY l.id, l.name
    ORDER BY event_count DESC
    LIMIT 10
");
$locations->execute([$tag]);
$locations = $locations->fetchAll(PDO::FETCH_ASSOC);

// Get related tags (co-occurring tags)
$related = $pdo->prepare("
    SELECT t2.name as tag, COUNT(*) as count
    FROM event_tags et1
    JOIN tags t1 ON et1.tag_id = t1.id
    JOIN event_tags et2 ON et1.event_id = et2.event_id
    JOIN tags t2 ON et2.tag_id = t2.id
    WHERE t1.name = ? AND t2.name != ?
    GROUP BY t2.id, t2.name
    ORDER BY count DESC
    LIMIT 10
");
$related->execute([$tag, $tag]);
$related = $related->fetchAll(PDO::FETCH_ASSOC);

// Get upcoming events with this tag
$events = $pdo->prepare("
    SELECT e.id, e.name, eo.start_date, eo.start_time, l.name as location_name
    FROM events e
    JOIN event_tags et ON e.id = et.event_id
    JOIN tags t ON et.tag_id = t.id
    LEFT JOIN event_occurrences eo ON e.id = eo.event_id
    LEFT JOIN locations l ON e.location_id = l.id
    WHERE t.name = ?
    AND eo.start_date >= CURDATE()
    ORDER BY eo.start_date, eo.start_time
    LIMIT 15
");
$events->execute([$tag]);
$events = $events->fetchAll(PDO::FETCH_ASSOC);
?>

<div class="detail-section">
    <h3>Statistics</h3>
    <dl class="detail-grid">
        <dt>Total Events</dt><dd><?= number_format($stats['event_count']) ?></dd>
        <dt>Upcoming</dt><dd class="text-success"><?= $stats['upcoming_count'] ?></dd>
        <dt>Sources</dt><dd><?= $stats['website_count'] ?></dd>
        <dt>First Seen</dt><dd class="muted"><?= formatShortDate($stats['first_event']) ?></dd>
        <dt>Last Event</dt><dd class="muted"><?= formatShortDate($stats['last_event']) ?></dd>
    </dl>
</div>

<?php if (!empty($websites)): ?>
<details class="detail-section" open>
    <summary><h3>Top Sources (<?= count($websites) ?>)</h3></summary>
    <ul class="item-list">
        <?php foreach ($websites as $w): ?>
        <li>
            <?= detailLink('websites', $w['id'], $w['name']) ?>
            <span class="text-muted-sm">(<?= $w['event_count'] ?> events)</span>
        </li>
        <?php endforeach; ?>
    </ul>
</details>
<?php endif; ?>

<?php if (!empty($locations)): ?>
<details class="detail-section" open>
    <summary><h3>Top Locations (<?= count($locations) ?>)</h3></summary>
    <ul class="item-list">
        <?php foreach ($locations as $l): ?>
        <li>
            <?= detailLink('locations', $l['id'], $l['name']) ?>
            <span class="text-muted-sm">(<?= $l['event_count'] ?> events)</span>
        </li>
        <?php endforeach; ?>
    </ul>
</details>
<?php endif; ?>

<?php if (!empty($related)): ?>
<details class="detail-section" open>
    <summary><h3>Related Tags (<?= count($related) ?>)</h3></summary>
    <div class="tag-container">
        <?php foreach ($related as $r): ?>
        <?= detailLink('tags', $r['tag'], $r['tag'], h($r['tag']) . ' <span class="muted">(' . $r['count'] . ')</span>', 'tag-link-sm') ?>
        <?php endforeach; ?>
    </div>
</details>
<?php endif; ?>

<?php if (!empty($events)): ?>
<details class="detail-section" open>
    <summary><h3>Upcoming Events (<?= count($events) ?>)</h3></summary>
    <ul class="event-list">
        <?php foreach ($events as $e): ?>
        <li>
            <div><?= detailLink('events', $e['id'], $e['name'], null, 'event-link') ?></div>
            <div class="date">
                <?= formatDateOnly($e['start_date']) ?>
                <?= formatTime($e['start_time']) ?>
                <?php if ($e['location_name']): ?>
                    <span class="muted">@ <?= h($e['location_name']) ?></span>
                <?php endif; ?>
            </div>
        </li>
        <?php endforeach; ?>
    </ul>
</details>
<?php else: ?>
<div class="detail-section">
    <p class="empty-state">No upcoming events with this tag</p>
</div>
<?php endif; ?>

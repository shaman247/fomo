<?php
/**
 * Location Detail API
 *
 * Returns HTML fragment with detailed location information.
 */

header('Content-Type: text/html; charset=utf-8');
require_once 'db_config.php';

if (!isset($_GET['id']) || !is_numeric($_GET['id'])) {
    echo '<p class="error-inline">Invalid location ID</p>';
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
    echo '<p class="error-inline">Location not found</p>';
    exit;
}

// Get alternate names
$alternateNames = $pdo->prepare("
    SELECT alternate_name
    FROM location_alternate_names
    WHERE location_id = ?
    ORDER BY alternate_name
");
$alternateNames->execute([$location_id]);
$alternateNames = $alternateNames->fetchAll(PDO::FETCH_COLUMN);

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

// Get upcoming events at this location (non-archived)
$events = $pdo->prepare("
    SELECT e.id, e.name, e.archived,
           GROUP_CONCAT(
               CONCAT(eo.start_date, '|', COALESCE(eo.start_time, ''))
               ORDER BY eo.start_date, eo.start_time
               SEPARATOR ';;'
           ) as occurrences
    FROM events e
    JOIN event_occurrences eo ON e.id = eo.event_id
    WHERE e.location_id = ?
    AND e.archived = 0
    AND eo.start_date >= CURDATE()
    GROUP BY e.id, e.name, e.archived
    ORDER BY MIN(eo.start_date), MIN(eo.start_time)
");
$events->execute([$location_id]);
$events = $events->fetchAll(PDO::FETCH_ASSOC);

// Get archived events at this location
$archivedEvents = $pdo->prepare("
    SELECT e.id, e.name, e.archived,
           GROUP_CONCAT(
               CONCAT(eo.start_date, '|', COALESCE(eo.start_time, ''))
               ORDER BY eo.start_date, eo.start_time
               SEPARATOR ';;'
           ) as occurrences
    FROM events e
    JOIN event_occurrences eo ON e.id = eo.event_id
    WHERE e.location_id = ?
    AND e.archived = 1
    GROUP BY e.id, e.name, e.archived
    ORDER BY MIN(eo.start_date) DESC, MIN(eo.start_time) DESC
");
$archivedEvents->execute([$location_id]);
$archivedEvents = $archivedEvents->fetchAll(PDO::FETCH_ASSOC);

// Get location's own tags
$locationTags = $pdo->prepare("
    SELECT t.id, t.name
    FROM location_tags lt
    JOIN tags t ON lt.tag_id = t.id
    WHERE lt.location_id = ?
    ORDER BY t.name
");
$locationTags->execute([$location_id]);
$locationTags = $locationTags->fetchAll(PDO::FETCH_ASSOC);

// Get tags from events at this location
$eventTags = $pdo->prepare("
    SELECT t.name as tag, COUNT(*) as count
    FROM event_tags et
    JOIN events e ON et.event_id = e.id
    JOIN tags t ON et.tag_id = t.id
    WHERE e.location_id = ?
    GROUP BY t.id, t.name
    ORDER BY count DESC
");
$eventTags->execute([$location_id]);
$eventTags = $eventTags->fetchAll(PDO::FETCH_ASSOC);

// Get websites that provide events at this location
$eventWebsites = $pdo->prepare("
    SELECT w.id, w.name, COUNT(*) as count
    FROM events e
    JOIN websites w ON e.website_id = w.id
    WHERE e.location_id = ?
    GROUP BY w.id, w.name
    ORDER BY count DESC
");
$eventWebsites->execute([$location_id]);
$eventWebsites = $eventWebsites->fetchAll(PDO::FETCH_ASSOC);
?>

<div class="detail-section">
    <h3>Details</h3>
    <dl class="detail-grid">
        <dt>ID</dt><dd><?= $location['id'] ?></dd>
        <dt>Name</dt><dd><?= h($location['name']) ?></dd>
        <?php if ($location['short_name']): ?>
        <dt>Short Name</dt><dd><?= h($location['short_name']) ?></dd>
        <?php endif; ?>
        <?php if ($location['very_short_name']): ?>
        <dt>Very Short</dt><dd><?= h($location['very_short_name']) ?></dd>
        <?php endif; ?>
        <?php if (!empty($alternateNames)): ?>
        <dt>Alt Names</dt><dd><?= h(implode(', ', $alternateNames)) ?></dd>
        <?php endif; ?>
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
               target="_blank" class="event-link">
                <?= round($location['lat'], 5) ?>, <?= round($location['lng'], 5) ?>
            </a>
        </dd>
        <?php else: ?>
        <dt>Coordinates</dt><dd class="text-warning">Not set</dd>
        <?php endif; ?>
        <dt>Created</dt><dd class="muted"><?= formatShortDate($location['created_at']) ?></dd>
    </dl>
</div>

<?php if ($location['description']): ?>
<div class="detail-section">
    <h3>Description</h3>
    <p class="detail-description"><?= h($location['description']) ?></p>
</div>
<?php endif; ?>

<details class="detail-section" open>
    <summary><h3>Linked Websites (<?= count($websites) ?>)</h3></summary>
    <?php if (!empty($websites)): ?>
    <ul class="item-list">
        <?php foreach ($websites as $w): ?>
        <li>
            <?= detailLink('websites', $w['id'], $w['name']) ?>
            <?php if ($w['disabled']): ?><span class="text-muted-xs">(disabled)</span><?php endif; ?>
            <?php if ($w['latest_status'] === 'failed'): ?><span class="text-muted-xs error-inline">(failed)</span><?php endif; ?>
        </li>
        <?php endforeach; ?>
    </ul>
    <?php else: ?>
    <p class="empty-state">None</p>
    <?php endif; ?>
</details>

<?php if (!empty($locationTags)): ?>
<details class="detail-section" open>
    <summary><h3>Location Tags (<?= count($locationTags) ?>)</h3></summary>
    <div class="tag-container">
        <?php foreach ($locationTags as $tag): ?>
        <?= detailLink('tags', $tag['name'], $tag['name'], null, 'tag-link') ?>
        <?php endforeach; ?>
    </div>
</details>
<?php endif; ?>

<?php if (!empty($eventTags)): ?>
<details class="detail-section" open>
    <summary><h3>Event Tags (<?= count($eventTags) ?>)</h3></summary>
    <div class="tag-container">
        <?php foreach ($eventTags as $tag): ?>
        <?= detailLink('tags', $tag['tag'], $tag['tag'], h($tag['tag']) . ' <span class="muted">(' . $tag['count'] . ')</span>', 'tag-link') ?>
        <?php endforeach; ?>
    </div>
</details>
<?php endif; ?>

<?php if (!empty($eventWebsites)): ?>
<details class="detail-section" open>
    <summary><h3>Event Websites (<?= count($eventWebsites) ?>)</h3></summary>
    <div class="tag-container">
        <?php foreach ($eventWebsites as $w): ?>
        <?= detailLink('websites', $w['id'], $w['name'], h($w['name']) . ' <span class="muted">(' . $w['count'] . ')</span>', 'tag-link') ?>
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
            <div class="date"><?= formatOccurrences($e['occurrences']) ?></div>
        </li>
        <?php endforeach; ?>
    </ul>
</details>
<?php elseif (empty($websites)): ?>
<div class="detail-section">
    <p class="empty-state">No websites linked to this location</p>
</div>
<?php else: ?>
<div class="detail-section">
    <p class="empty-state">No upcoming events</p>
</div>
<?php endif; ?>

<?php if (!empty($archivedEvents)): ?>
<details class="detail-section">
    <summary><h3>Archived Events (<?= count($archivedEvents) ?>)</h3></summary>
    <ul class="event-list">
        <?php foreach ($archivedEvents as $e): ?>
        <li>
            <div>
                <?= detailLink('events', $e['id'], $e['name'], null, 'event-link') ?>
                <span class="text-muted-xs">(archived)</span>
            </div>
            <div class="date"><?= formatOccurrences($e['occurrences']) ?></div>
        </li>
        <?php endforeach; ?>
    </ul>
</details>
<?php endif; ?>

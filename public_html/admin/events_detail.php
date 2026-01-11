<?php
/**
 * Event Detail API
 *
 * Returns HTML fragment with detailed event information.
 * Queries the final `events` table and shows contributing crawl_events.
 */

header('Content-Type: text/html; charset=utf-8');
require_once 'db_config.php';

if (!isset($_GET['id']) || !is_numeric($_GET['id'])) {
    echo '<p style="color:#c8535b">Invalid event ID</p>';
    exit;
}

$event_id = (int) $_GET['id'];

// Get event details with first occurrence
$stmt = $pdo->prepare("
    SELECT e.*,
           w.id as website_id, w.name as website_name,
           l.id as loc_id, l.name as loc_name, l.address, l.emoji as loc_emoji,
           eo.start_date, eo.end_date, eo.start_time, eo.end_time
    FROM events e
    LEFT JOIN websites w ON e.website_id = w.id
    LEFT JOIN locations l ON e.location_id = l.id
    LEFT JOIN event_occurrences eo ON e.id = eo.event_id
    WHERE e.id = ?
    ORDER BY eo.start_date
    LIMIT 1
");
$stmt->execute([$event_id]);
$event = $stmt->fetch(PDO::FETCH_ASSOC);

if (!$event) {
    echo '<p style="color:#c8535b">Event not found</p>';
    exit;
}

// Get all occurrences for this event
$occurrences = $pdo->prepare("
    SELECT start_date, end_date, start_time, end_time
    FROM event_occurrences
    WHERE event_id = ?
    ORDER BY start_date, start_time
");
$occurrences->execute([$event_id]);
$occurrences = $occurrences->fetchAll(PDO::FETCH_ASSOC);

// Get tags for this event
$tags = $pdo->prepare("
    SELECT t.name
    FROM event_tags et
    JOIN tags t ON et.tag_id = t.id
    WHERE et.event_id = ?
    ORDER BY t.name
");
$tags->execute([$event_id]);
$tags = $tags->fetchAll(PDO::FETCH_COLUMN);

// Get URLs for this event
$urls = $pdo->prepare("SELECT url FROM event_urls WHERE event_id = ? ORDER BY sort_order");
$urls->execute([$event_id]);
$urls = $urls->fetchAll(PDO::FETCH_COLUMN);

// Get contributing crawl events via event_sources
$sources = $pdo->prepare("
    SELECT
        ce.id,
        ce.name,
        ce.url,
        ce.emoji,
        ceo.start_date,
        ceo.start_time,
        es.is_primary,
        w.name as website_name,
        crun.run_date
    FROM event_sources es
    JOIN crawl_events ce ON es.crawl_event_id = ce.id
    JOIN crawl_results cr ON ce.crawl_result_id = cr.id
    JOIN crawl_runs crun ON cr.crawl_run_id = crun.id
    LEFT JOIN websites w ON cr.website_id = w.id
    LEFT JOIN crawl_event_occurrences ceo ON ce.id = ceo.crawl_event_id
    WHERE es.event_id = ?
    GROUP BY ce.id
    ORDER BY es.is_primary DESC, crun.run_date DESC
");
$sources->execute([$event_id]);
$sources = $sources->fetchAll(PDO::FETCH_ASSOC);

// Format date/time
function formatDateTime($date, $time) {
    if (!$date) return '-';
    $dt = new DateTime($date);
    $result = $dt->format('l, F j, Y');
    if ($time) {
        $result .= ' at ' . htmlspecialchars($time);
    }
    return $result;
}

function formatShortDate($date) {
    if (!$date) return '-';
    return date('M j, Y', strtotime($date));
}
?>

<div class="detail-section">
    <h3>Event Details</h3>
    <dl class="detail-grid">
        <dt>ID</dt><dd><?= $event['id'] ?></dd>
        <dt>Name</dt><dd style="white-space:normal"><?= h($event['name']) ?></dd>
        <?php if ($event['short_name']): ?>
        <dt>Short Name</dt><dd><?= h($event['short_name']) ?></dd>
        <?php endif; ?>
        <?php if ($event['emoji']): ?>
        <dt>Emoji</dt><dd><?= $event['emoji'] ?></dd>
        <?php endif; ?>
        <?php if ($event['sublocation']): ?>
        <dt>Sublocation</dt><dd><?= h($event['sublocation']) ?></dd>
        <?php endif; ?>
        <dt>Status</dt>
        <dd>
            <?php if ($event['archived']): ?>
                <span style="color:#c8535b;font-weight:bold">⚠️ Archived</span>
                <span style="color:var(--secondary-text);font-size:11px">(hidden from public site)</span>
            <?php else: ?>
                <span style="color:#4CAF50">✓ Active</span>
            <?php endif; ?>
        </dd>
    </dl>
</div>

<?php if (count($occurrences) > 0): ?>
<details class="detail-section" open>
    <summary><h3>Dates (<?= count($occurrences) ?>)</h3></summary>
    <ul style="list-style:none;font-size:12px;max-height:150px;overflow-y:auto">
        <?php foreach ($occurrences as $occ): ?>
        <li style="padding:4px 0;border-bottom:1px solid var(--border-color)">
            <strong><?= formatShortDate($occ['start_date']) ?></strong>
            <?php if ($occ['start_time']): ?>
                <span style="color:var(--secondary-text)">at <?= h($occ['start_time']) ?></span>
            <?php endif; ?>
            <?php if ($occ['end_date'] && $occ['end_date'] !== $occ['start_date']): ?>
                <span style="color:var(--secondary-text)">- <?= formatShortDate($occ['end_date']) ?></span>
            <?php endif; ?>
            <?php if ($occ['end_time']): ?>
                <span style="color:var(--secondary-text)">to <?= h($occ['end_time']) ?></span>
            <?php endif; ?>
        </li>
        <?php endforeach; ?>
    </ul>
</details>
<?php endif; ?>

<div class="detail-section">
    <h3>Location</h3>
    <dl class="detail-grid">
        <?php if ($event['loc_name']): ?>
        <dt>Venue</dt><dd><?= $event['loc_emoji'] ?? '' ?> <a href="javascript:void(0)" onclick="openDetail('locations', <?= $event['loc_id'] ?>, '<?= h(addslashes($event['loc_name'])) ?>')" class="event-link"><?= h($event['loc_name']) ?></a></dd>
        <?php if ($event['address']): ?>
        <dt>Address</dt><dd style="white-space:normal"><?= h($event['address']) ?></dd>
        <?php endif; ?>
        <?php elseif ($event['location_name']): ?>
        <dt>Venue</dt><dd style="color:var(--warning)"><?= h($event['location_name']) ?> <span style="font-size:10px">(unmatched)</span></dd>
        <?php else: ?>
        <dt>Venue</dt><dd style="color:var(--secondary-text)">Not specified</dd>
        <?php endif; ?>
        <?php if ($event['lat'] && $event['lng']): ?>
        <dt>Coordinates</dt><dd style="font-family:monospace;font-size:11px"><?= round($event['lat'], 5) ?>, <?= round($event['lng'], 5) ?></dd>
        <?php endif; ?>
    </dl>
</div>

<?php if (!empty($tags)): ?>
<details class="detail-section" open>
    <summary><h3>Tags (<?= count($tags) ?>)</h3></summary>
    <div style="display:flex;flex-wrap:wrap;gap:4px">
        <?php foreach ($tags as $tag): ?>
        <a href="javascript:void(0)" onclick="openDetail('tags', '<?= h(addslashes($tag)) ?>', '<?= h(addslashes($tag)) ?>')"
           style="background:var(--tertiary-bg);padding:2px 8px;border-radius:6px;font-size:11px;text-decoration:none;color:inherit">
            <?= h($tag) ?>
        </a>
        <?php endforeach; ?>
    </div>
</details>
<?php endif; ?>

<?php if ($event['description']): ?>
<div class="detail-section">
    <h3>Description</h3>
    <p style="font-size:12px;white-space:pre-wrap;line-height:1.5;max-height:200px;overflow-y:auto"><?= h($event['description']) ?></p>
</div>
<?php endif; ?>

<?php if (!empty($urls)): ?>
<details class="detail-section" open>
    <summary><h3>Links (<?= count($urls) ?>)</h3></summary>
    <ul style="list-style:none;font-size:12px">
        <?php foreach ($urls as $url): ?>
        <li style="padding:3px 0">
            <a href="<?= h($url) ?>" target="_blank" class="event-link" style="word-break:break-all">
                <?= h($url) ?>
            </a>
        </li>
        <?php endforeach; ?>
    </ul>
</details>
<?php endif; ?>

<?php if ($event['website_name']): ?>
<div class="detail-section">
    <h3>Primary Source</h3>
    <dl class="detail-grid">
        <dt>Website</dt><dd><a href="javascript:void(0)" onclick="openDetail('websites', <?= $event['website_id'] ?>, '<?= h(addslashes($event['website_name'])) ?>')" class="event-link"><?= h($event['website_name']) ?></a></dd>
    </dl>
</div>
<?php endif; ?>

<?php if (!empty($sources)): ?>
<details class="detail-section" open>
    <summary><h3>Contributing Crawl Events (<?= count($sources) ?>)</h3></summary>
    <ul style="list-style:none;font-size:12px;max-height:200px;overflow-y:auto">
        <?php foreach ($sources as $src): ?>
        <li style="padding:6px 0;border-bottom:1px solid var(--border-color)">
            <div style="display:flex;align-items:center;gap:6px">
                <?php if ($src['is_primary']): ?>
                <span style="background:var(--accent-color);color:#000;padding:1px 5px;border-radius:6px;font-size:9px;font-weight:600">PRIMARY</span>
                <?php endif; ?>
                <span style="color:var(--secondary-text)">#<?= $src['id'] ?></span>
                <?php if ($src['emoji']): ?>
                <span><?= $src['emoji'] ?></span>
                <?php endif; ?>
            </div>
            <div style="margin-top:3px;white-space:normal"><?= h($src['name']) ?></div>
            <div style="margin-top:3px;color:var(--secondary-text);font-size:11px">
                <?= h($src['website_name'] ?? 'Unknown source') ?>
                &bull; Crawled <?= formatShortDate($src['run_date']) ?>
                <?php if ($src['start_date']): ?>
                &bull; Event date: <?= formatShortDate($src['start_date']) ?>
                <?php endif; ?>
            </div>
            <?php if ($src['url']): ?>
            <div style="margin-top:3px">
                <a href="<?= h($src['url']) ?>" target="_blank" class="event-link" style="font-size:11px;word-break:break-all">
                    <?= h(strlen($src['url']) > 60 ? substr($src['url'], 0, 60) . '...' : $src['url']) ?>
                </a>
            </div>
            <?php endif; ?>
        </li>
        <?php endforeach; ?>
    </ul>
</details>
<?php endif; ?>

<div class="detail-section">
    <h3>Metadata</h3>
    <dl class="detail-grid">
        <dt>Created</dt><dd style="color:var(--secondary-text)"><?= date('M j, Y g:ia', strtotime($event['created_at'])) ?></dd>
        <dt>Updated</dt><dd style="color:var(--secondary-text)"><?= date('M j, Y g:ia', strtotime($event['updated_at'])) ?></dd>
    </dl>
</div>

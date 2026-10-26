<?php
/**
 * Analytics Sink
 *
 * Receives the frontend Analytics beacons (src/js/core/analytics.js) and adds
 * them to one JSON file of daily totals per city-timezone day, OUTSIDE the web
 * root: <parent of DOCUMENT_ROOT>/analytics/YYYY-MM-DD.json, or the directory
 * in the FOMO_ANALYTICS_DIR environment variable. Read it with
 * scripts/analytics_report.py.
 *
 * POST /api/analytics.php   (text/plain JSON body, as sendBeacon sends it)
 *   {type: "view", platform, dpr, tz, viewport, screen, wd, path, bundle, ctz, ref, utm, shared, lang}
 *   {type: "engage", ctz, platform, viewport, screen, wd, seconds, counts: {action: n}, firsts: [action]}
 *   {type: "timing", ctz, platform, viewport, screen, wd, markersMs (null = hidden before markers), source: network|cache}
 * Response: 204 for accepted/dropped beacons.
 *
 * Only counters are stored: no per-visit rows, no IP addresses, no visitor IDs.
 * The user agent is reduced to browser/OS family on arrival. Automated traffic
 * (beacon_traffic(): crawlers, webdriver, phone-UA renderers with desktop-size
 * viewports) is kept, but in its own "automated" section with the same shape
 * plus a "reason" breakdown, so it never mixes into the real totals. Each
 * dimension keeps at most MAX_KEYS values (the rest fold into "(other)"), so a
 * day file stays small. Day files written before 2026-10-25 counted known bots
 * only, in a top-level "bots" number.
 */

require __DIR__ . '/beacon_lib.php';

const MAX_BODY_BYTES = 4096;
const GLOBAL_PER_HOUR = 30000;
const MAX_KEYS = 100;
const MAX_SECONDS_PER_BEACON = 1800;
const ACTIONS = [
    'event_link', 'outbound', 'popup_open', 'list_toggle', 'list_event_open', 'tag_click', 'search',
    'filter_topic', 'filter_venue', 'filter_format', 'filter_area', 'date_change', 'theme_change',
    'share', 'feedback_open', 'engaged_10s', 'engaged_60s', 'engaged_5m',
];
const PLATFORMS = ['web', 'pwa', 'ios-app', 'android-app'];
// Time-to-markers buckets: [upper bound in ms, label].
const MARKER_BUCKETS = [[1000, '<1s'], [2000, '1-2s'], [4000, '2-4s'], [6000, '4-6s'], [8000, '6-8s'],
    [12000, '8-12s'], [20000, '12-20s'], [PHP_INT_MAX, '20s+']];

beacon_require_same_origin_post();
$data = beacon_read_json(MAX_BODY_BYTES);
$type = $data['type'] ?? '';
if (!in_array($type, ['view', 'engage', 'timing'], true)) {
    http_response_code(400);
    exit;
}

$ua = $_SERVER['HTTP_USER_AGENT'] ?? '';
[$traffic, $trafficReason] = beacon_traffic($ua, $data);

// Days follow the city's timezone (sent by the bundle from config), not UTC.
$zone = in_array($data['ctz'] ?? '', DateTimeZone::listIdentifiers(), true) ? $data['ctz'] : 'UTC';
$now = new DateTime('now', new DateTimeZone($zone));
$day = $now->format('Y-m-d');

$dir = beacon_data_dir('FOMO_ANALYTICS_DIR', 'analytics');
$lock = $dir !== '' ? beacon_lock($dir) : null;
if (!$lock) {
    http_response_code(204);
    exit;
}

$hourKey = gmdate('YmdH');
$limit = beacon_read_state("$dir/ratelimit.json", []);
if (($limit['hour'] ?? '') !== $hourKey) $limit = ['hour' => $hourKey, 'total' => 0];
if ($limit['total'] >= GLOBAL_PER_HOUR) {
    beacon_unlock($lock);
    http_response_code(204);
    exit;
}
$limit['total']++;
beacon_write_state("$dir/ratelimit.json", $limit);

$path = "$dir/$day.json";
$section_skeleton = ['views' => 0, 'engage_beacons' => 0, 'seconds' => 0, 'dims' => [], 'actions' => [], 'views_with' => []];
$stats = beacon_read_state($path, ['date' => $day, 'timezone' => $zone] + $section_skeleton);
$stats['automated'] = ($stats['automated'] ?? []) + $section_skeleton;

/** Increment $stats[$group][$dim][$key], folding new keys past MAX_KEYS into "(other)". */
function bump(&$stats, $group, $dim, $key, $by = 1) {
    $key = (string)$key === '' ? '(none)' : (string)$key;
    $bucket = &$stats[$group][$dim];
    if (!isset($bucket[$key]) && count($bucket ?? []) >= MAX_KEYS) $key = '(other)';
    $bucket[$key] = ($bucket[$key] ?? 0) + $by;
}

function pick($value, $pattern, $fallback = '') {
    return is_string($value) && preg_match($pattern, $value) ? $value : $fallback;
}

function ua_family($ua) {
    $os = preg_match('/iPhone|iPad|iPod/', $ua) ? 'iOS' : (preg_match('/Android/', $ua) ? 'Android'
        : (preg_match('/Windows/', $ua) ? 'Windows' : (preg_match('/Mac OS X|Macintosh/', $ua) ? 'macOS'
        : (preg_match('/CrOS/', $ua) ? 'ChromeOS' : (preg_match('/Linux/', $ua) ? 'Linux' : 'Other')))));
    $browser = preg_match('/Edg\//', $ua) ? 'Edge' : (preg_match('/OPR\//', $ua) ? 'Opera'
        : (preg_match('/SamsungBrowser/', $ua) ? 'Samsung' : (preg_match('/Firefox|FxiOS/', $ua) ? 'Firefox'
        : (preg_match('/Chrome|CriOS/', $ua) ? 'Chrome' : (preg_match('/Safari/', $ua) ? 'Safari' : 'Other')))));
    if (preg_match('/; wv\)|FBAN|FBAV|Instagram/', $ua)) $browser .= ' (in-app)';
    return [$browser, $os];
}

$platform = in_array($data['platform'] ?? '', PLATFORMS, true) ? $data['platform'] : 'web';

// Real and automated traffic share one shape; only the section differs.
if ($traffic === 'automated') {
    $section = &$stats['automated'];
    bump($section, 'dims', 'reason', $trafficReason);
} else {
    $section = &$stats;
}

if ($type === 'view') {
    $section['views']++;
    [$browser, $os] = ua_family($ua);
    $width = preg_match('/^(\d{1,5})x\d{1,5}$/', $data['viewport'] ?? '', $m) ? (int)$m[1] : 0;
    $dpr = is_numeric($data['dpr'] ?? null) ? round((float)$data['dpr'], 2) : 0;
    bump($section, 'dims', 'platform', $platform);
    bump($section, 'dims', 'device', $width === 0 ? 'unknown' : ($width < 600 ? 'phone' : ($width < 1024 ? 'tablet' : 'desktop')));
    bump($section, 'dims', 'browser', $browser);
    bump($section, 'dims', 'os', $os);
    bump($section, 'dims', 'dpr', $dpr ? rtrim(rtrim(number_format($dpr, 2, '.', ''), '0'), '.') : 'unknown');
    bump($section, 'dims', 'tz', pick($data['tz'] ?? '', '~^[\w+\-/]{1,64}$~', 'unknown'));
    bump($section, 'dims', 'lang', pick($data['lang'] ?? '', '/^[a-z]{2}$/', 'unknown'));
    bump($section, 'dims', 'referrer', strtolower(pick($data['ref'] ?? '', '/^[A-Za-z0-9.-]{1,100}$/')));
    bump($section, 'dims', 'utm_source', strtolower(pick($data['utm'] ?? '', '/^[\w.-]{1,40}$/')));
    bump($section, 'dims', 'path', beacon_clean_text($data['path'] ?? '', 100));
    bump($section, 'dims', 'bundle', pick($data['bundle'] ?? '', '/^[\w.-]{1,16}$/', 'unknown'));
    bump($section, 'dims', 'hour', $now->format('H'));
    bump($section, 'dims', 'shared_link', empty($data['shared']) ? 'no' : 'yes');
} elseif ($type === 'timing') {
    // markers_<source>: how long first (network) and repeat (cache) visits took to show markers.
    $ms = is_numeric($data['markersMs'] ?? null) ? (int)$data['markersMs'] : -1;
    if ($ms < 0) {
        bump($section, 'dims', 'markers_outcome', 'left before markers');
    } else {
        $source = in_array($data['source'] ?? '', ['network', 'cache'], true) ? $data['source'] : 'unknown';
        $label = '20s+';
        foreach (MARKER_BUCKETS as [$limit, $name]) {
            if ($ms < $limit) { $label = $name; break; }
        }
        bump($section, 'dims', 'markers_outcome', 'shown');
        bump($section, 'dims', "markers_$source", $label);
    }
} else {
    $section['engage_beacons']++;
    $seconds = is_numeric($data['seconds'] ?? null) ? (int)$data['seconds'] : 0;
    $seconds = max(0, min($seconds, MAX_SECONDS_PER_BEACON));
    $section['seconds'] += $seconds;
    bump($section, 'dims', 'seconds_by_platform', $platform, $seconds);
    foreach ((is_array($data['counts'] ?? null) ? $data['counts'] : []) as $action => $n) {
        if (in_array($action, ACTIONS, true) && is_numeric($n)) {
            bump($section, 'actions', 'all', $action, max(0, min((int)$n, 500)));
        }
    }
    foreach ((is_array($data['firsts'] ?? null) ? array_unique($data['firsts']) : []) as $action) {
        if (in_array($action, ACTIONS, true)) bump($section, 'views_with', 'all', $action);
    }
}

unset($section);
beacon_write_state($path, $stats);
beacon_unlock($lock);
http_response_code(204);

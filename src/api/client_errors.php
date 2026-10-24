<?php
/**
 * Client Error Sink
 *
 * Receives the frontend ErrorReporter's beacons (src/js/core/errorReporter.js)
 * and appends one JSON line per report to a log OUTSIDE the web root:
 * <parent of DOCUMENT_ROOT>/client_errors/client_errors.log, or the directory
 * in the FOMO_CLIENT_ERROR_DIR environment variable. Read it with
 * scripts/client_errors.py.
 *
 * POST /api/client_errors.php   (text/plain JSON body, as sendBeacon sends it)
 * Response: 204 always for accepted/dropped reports (beacons ignore the body).
 *
 * Rate-limited per client (hashed, never stored raw) and globally per hour;
 * the log rotates once at LOG_MAX_BYTES. No IP addresses are written.
 */

const MAX_BODY_BYTES = 8192;
const PER_CLIENT_PER_HOUR = 20;
const GLOBAL_PER_HOUR = 500;
const LOG_MAX_BYTES = 5 * 1024 * 1024;

header('Cache-Control: no-store');

if ($_SERVER['REQUEST_METHOD'] !== 'POST') {
    http_response_code(405);
    exit;
}

// Beacons are same-origin; refuse cross-site posts when the browser says so.
$origin = $_SERVER['HTTP_ORIGIN'] ?? '';
$host = strtolower(preg_replace('/:\d+$/', '', $_SERVER['HTTP_HOST'] ?? ''));
if ($origin !== '' && $origin !== 'null' && strtolower((string)parse_url($origin, PHP_URL_HOST)) !== $host) {
    http_response_code(403);
    exit;
}

$raw = file_get_contents('php://input', false, null, 0, MAX_BODY_BYTES + 1);
if ($raw === false || strlen($raw) > MAX_BODY_BYTES) {
    http_response_code(413);
    exit;
}
$data = json_decode($raw, true);
if (!is_array($data) || !isset($data['message']) || !is_string($data['message'])) {
    http_response_code(400);
    exit;
}

/** Cut any URL to its file name (keeping :line:col), strip control chars, truncate. */
function clean_text($value, $max, $multiline = false) {
    if (!is_string($value)) return '';
    $value = preg_replace_callback('~\b(?:https?|file|blob|webpack|[a-z]+-extension)://[^\s()\'"<>]*~i', function ($m) {
        $url = $m[0];
        $suffix = preg_match('/[?#].*?((?::\d+){1,2})$/', $url, $pos) ? $pos[1] : '';
        $url = preg_replace('/[?#].*$/', '', $url) . $suffix;
        return substr($url, strrpos($url, '/') + 1);
    }, $value);
    $value = preg_replace($multiline ? '/[^\P{C}\n]+/u' : '/\p{C}+/u', ' ', $value) ?? '';
    return mb_substr($value, 0, $max);
}

$entry = [
    't' => gmdate('Y-m-d\TH:i:s\Z'),
    'kind' => in_array($data['kind'] ?? '', ['error', 'rejection', 'console'], true) ? $data['kind'] : 'other',
    'message' => clean_text($data['message'], 300),
    'source' => clean_text($data['source'] ?? '', 120),
    'stack' => clean_text($data['stack'] ?? '', 800, true),
    'bundle' => preg_match('/^[\w.-]{1,16}$/', $data['bundle'] ?? '') ? $data['bundle'] : '',
    'dpr' => is_numeric($data['dpr'] ?? null) ? round((float)$data['dpr'], 3) : null,
    'tz' => preg_match('~^[\w+\-/]{1,64}$~', $data['tz'] ?? '') ? $data['tz'] : '',
    'viewport' => preg_match('/^\d{1,5}x\d{1,5}$/', $data['viewport'] ?? '') ? $data['viewport'] : '',
    'ua' => clean_text($_SERVER['HTTP_USER_AGENT'] ?? '', 300),
    'path' => clean_text($data['path'] ?? '', 100),
];
if ($entry['message'] === '') {
    http_response_code(400);
    exit;
}

$docRoot = rtrim($_SERVER['DOCUMENT_ROOT'] ?? '', '/');
$logDir = getenv('FOMO_CLIENT_ERROR_DIR') ?: ($docRoot !== '' ? dirname($docRoot) . '/client_errors' : '');
if ($logDir === '' || (!is_dir($logDir) && !@mkdir($logDir, 0700, true))) {
    error_log('client_errors.php: log directory unavailable');
    http_response_code(204);
    exit;
}

// One lock serializes the rate-limit state and the append.
$lock = @fopen("$logDir/.lock", 'c');
if (!$lock || !flock($lock, LOCK_EX)) {
    http_response_code(204);
    exit;
}

$hour = gmdate('YmdH');
$statePath = "$logDir/ratelimit.json";
$state = json_decode((string)@file_get_contents($statePath), true);
if (!is_array($state) || ($state['hour'] ?? '') !== $hour) {
    $state = ['hour' => $hour, 'total' => 0, 'clients' => []];
}
// Hourly-salted hash: rate-limits a client without keeping its address.
$client = substr(hash('sha256', $hour . ($_SERVER['REMOTE_ADDR'] ?? '') . ($_SERVER['HTTP_USER_AGENT'] ?? '')), 0, 16);
$clientCount = $state['clients'][$client] ?? 0;

if ($state['total'] < GLOBAL_PER_HOUR && $clientCount < PER_CLIENT_PER_HOUR) {
    $state['total']++;
    $state['clients'][$client] = $clientCount + 1;
    $logPath = "$logDir/client_errors.log";
    if (@filesize($logPath) > LOG_MAX_BYTES) {
        @rename($logPath, "$logPath.1");
    }
    @file_put_contents($logPath, json_encode($entry, JSON_UNESCAPED_SLASHES | JSON_UNESCAPED_UNICODE) . "\n", FILE_APPEND);
    @file_put_contents($statePath, json_encode($state));
}

flock($lock, LOCK_UN);
fclose($lock);
http_response_code(204);

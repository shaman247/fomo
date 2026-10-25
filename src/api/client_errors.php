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
 * Every report is kept and tagged "traffic": "real" or "automated" (with a
 * "traffic_reason", see beacon_traffic()), so automated renderers stay visible
 * without drowning real errors: each class has its own hourly cap. Also
 * rate-limited per client (hashed, never stored raw); the log rotates once at
 * LOG_MAX_BYTES. No IP addresses are written.
 */

require __DIR__ . '/beacon_lib.php';

const MAX_BODY_BYTES = 8192;
const PER_CLIENT_PER_HOUR = 20;
const GLOBAL_PER_HOUR = ['real' => 500, 'automated' => 200];
const LOG_MAX_BYTES = 5 * 1024 * 1024;

beacon_require_same_origin_post();
$data = beacon_read_json(MAX_BODY_BYTES);
if (!isset($data['message']) || !is_string($data['message'])) {
    http_response_code(400);
    exit;
}

$ua = $_SERVER['HTTP_USER_AGENT'] ?? '';
[$traffic, $trafficReason] = beacon_traffic($ua, $data);

$entry = [
    't' => gmdate('Y-m-d\TH:i:s\Z'),
    'traffic' => $traffic,
    'traffic_reason' => $trafficReason,
    'kind' => in_array($data['kind'] ?? '', ['error', 'rejection', 'console'], true) ? $data['kind'] : 'other',
    'message' => beacon_clean_text($data['message'], 300),
    'source' => beacon_clean_text($data['source'] ?? '', 120),
    'stack' => beacon_clean_text($data['stack'] ?? '', 800, true),
    'bundle' => preg_match('/^[\w.-]{1,16}$/', $data['bundle'] ?? '') ? $data['bundle'] : '',
    'platform' => preg_match('/^[a-z-]{1,16}$/', $data['platform'] ?? '') ? $data['platform'] : '',
    'dpr' => is_numeric($data['dpr'] ?? null) ? round((float)$data['dpr'], 3) : null,
    'tz' => preg_match('~^[\w+\-/]{1,64}$~', $data['tz'] ?? '') ? $data['tz'] : '',
    'viewport' => preg_match('/^\d{1,5}x\d{1,5}$/', $data['viewport'] ?? '') ? $data['viewport'] : '',
    'screen' => preg_match('/^\d{1,5}x\d{1,5}$/', $data['screen'] ?? '') ? $data['screen'] : '',
    'hidden' => ($data['hidden'] ?? false) === true,
    'since_load' => is_numeric($data['sinceLoad'] ?? null) ? max(0, (int)$data['sinceLoad']) : null,
    'ua' => beacon_clean_text($ua, 300),
    'path' => beacon_clean_text($data['path'] ?? '', 100),
];
if ($entry['message'] === '') {
    http_response_code(400);
    exit;
}

$logDir = beacon_data_dir('FOMO_CLIENT_ERROR_DIR', 'client_errors');
$lock = $logDir !== '' ? beacon_lock($logDir) : null;
if (!$lock) {
    http_response_code(204);
    exit;
}

$hour = gmdate('YmdH');
$statePath = "$logDir/ratelimit.json";
$state = beacon_read_state($statePath, []);
if (($state['hour'] ?? '') !== $hour || !is_array($state['totals'] ?? null)) {
    $state = ['hour' => $hour, 'totals' => ['real' => 0, 'automated' => 0], 'clients' => []];
}
// Hourly-salted hash: rate-limits a client without keeping its address.
$client = substr(hash('sha256', $hour . ($_SERVER['REMOTE_ADDR'] ?? '') . ($_SERVER['HTTP_USER_AGENT'] ?? '')), 0, 16);
$clientCount = $state['clients'][$client] ?? 0;

if ($state['totals'][$traffic] < GLOBAL_PER_HOUR[$traffic] && $clientCount < PER_CLIENT_PER_HOUR) {
    $state['totals'][$traffic]++;
    $state['clients'][$client] = $clientCount + 1;
    $logPath = "$logDir/client_errors.log";
    if (@filesize($logPath) > LOG_MAX_BYTES) {
        @rename($logPath, "$logPath.1");
    }
    @file_put_contents($logPath, json_encode($entry, JSON_UNESCAPED_SLASHES | JSON_UNESCAPED_UNICODE) . "\n", FILE_APPEND);
    @file_put_contents($statePath, json_encode($state));
}

beacon_unlock($lock);
http_response_code(204);

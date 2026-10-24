<?php
/**
 * Shared helpers for the first-party beacon endpoints (client_errors.php,
 * analytics.php): same-origin POST checks, bounded JSON bodies, URL scrubbing,
 * the private data directory outside the web root, and an exclusive lock.
 * Defines functions only; requesting it directly returns 404.
 */

if (realpath($_SERVER['SCRIPT_FILENAME'] ?? '') === __FILE__) {
    http_response_code(404);
    exit;
}

/** Allow only same-origin POSTs; exits with 405/403 otherwise. */
function beacon_require_same_origin_post() {
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
}

/** Decode a JSON object body of at most $maxBytes; exits with 413/400 otherwise. */
function beacon_read_json($maxBytes) {
    $raw = file_get_contents('php://input', false, null, 0, $maxBytes + 1);
    if ($raw === false || strlen($raw) > $maxBytes) {
        http_response_code(413);
        exit;
    }
    $data = json_decode($raw, true);
    if (!is_array($data)) {
        http_response_code(400);
        exit;
    }
    return $data;
}

/** Cut any URL to its file name (keeping :line:col), strip control chars, truncate. */
function beacon_clean_text($value, $max, $multiline = false) {
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

/**
 * The beacon's private directory: $envVar if set, else <parent of DOCUMENT_ROOT>/$name.
 * Returns '' when it can't be created (callers then drop the beacon silently).
 */
function beacon_data_dir($envVar, $name) {
    $docRoot = rtrim($_SERVER['DOCUMENT_ROOT'] ?? '', '/');
    $dir = getenv($envVar) ?: ($docRoot !== '' ? dirname($docRoot) . '/' . $name : '');
    if ($dir === '' || (!is_dir($dir) && !@mkdir($dir, 0700, true))) {
        error_log("beacon: data directory for $name unavailable");
        return '';
    }
    return $dir;
}

/** Take the directory's exclusive lock; returns the handle, or null. Release with beacon_unlock(). */
function beacon_lock($dir) {
    $lock = @fopen("$dir/.lock", 'c');
    if (!$lock || !flock($lock, LOCK_EX)) return null;
    return $lock;
}

function beacon_unlock($lock) {
    flock($lock, LOCK_UN);
    fclose($lock);
}

/** Read a JSON state file, or $default when missing/corrupt. */
function beacon_read_state($path, $default) {
    $state = json_decode((string)@file_get_contents($path), true);
    return is_array($state) ? $state : $default;
}

/** Write a JSON state file atomically (temp file + rename). */
function beacon_write_state($path, $state) {
    $tmp = $path . '.tmp';
    if (@file_put_contents($tmp, json_encode($state, JSON_UNESCAPED_SLASHES | JSON_UNESCAPED_UNICODE)) !== false) {
        @rename($tmp, $path);
    }
}

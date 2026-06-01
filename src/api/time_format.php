<?php
/**
 * Canonical time-format helpers — PHP mirror of pipeline/processor.py::_standardize_time.
 *
 * Canonical format: compact lowercase 12-hour with no space and no colon-zero.
 *   '7pm', '7:30pm', '11am', '12am' (midnight), '12pm' (noon).
 * Empty / sentinel inputs normalize to ''.
 * Ambiguous inputs (bare HH:MM with HH 1-11, bare HH 1-11 without leading zero)
 * are returned with whitespace/case normalized but otherwise unchanged so manual
 * review can find them via grep.
 *
 * Keep this in sync with pipeline/processor.py::_standardize_time.
 */

function _canonical_time(int $h, int $mi, bool $isPm): string {
    $suffix = $isPm ? 'pm' : 'am';
    return $mi === 0 ? "{$h}{$suffix}" : sprintf("%d:%02d%s", $h, $mi, $suffix);
}

function standardize_time($timeStr): string {
    if ($timeStr === null) return '';
    $s = strtolower(trim((string)$timeStr));
    // Strip whitespace, dots, underscores ('9_pm' -> '9pm').
    $s = str_replace([' ', '.', '_'], '', $s);
    // Collapse single-digit zero minutes ('7:0pm' -> '7pm').
    $s = preg_replace('/:0(?!\d)/', '', $s);

    static $sentinels = [
        '', 'allday', 'allday/varies', 'varioustimes', 'multipletimes', 'tba',
        'tbd', 'none', 'close', 'closing', 'late', 'tbc', 'ongoing', 'sundown',
        'sunrise', 'sunset', 'dusk', 'dawn',
    ];
    if (in_array($s, $sentinels, true)) return '';

    // Strip US timezone suffixes (1pmest, 7pmet, etc.)
    $s = preg_replace('/(est|edt|pst|pdt|mst|mdt|cst|cdt|et|pt|mt|ct)$/', '', $s);
    if ($s === '') return '';

    // 12-hour form: '7pm', '7:30pm'
    if (preg_match('/^(\d{1,2})(?::(\d{2}))?(am|pm)$/', $s, $m)) {
        $h = (int)$m[1];
        $mi = isset($m[2]) && $m[2] !== '' ? (int)$m[2] : 0;
        if ($h >= 1 && $h <= 12 && $mi >= 0 && $mi <= 59) {
            return _canonical_time($h, $mi, $m[3] === 'pm');
        }
        return $s;  // malformed (e.g. '13pm'); preserve so it's findable
    }

    // HH:MM
    if (preg_match('/^(\d{1,2}):(\d{2})$/', $s, $m)) {
        $h = (int)$m[1];
        $mi = (int)$m[2];
        if ($h >= 0 && $h <= 23 && $mi >= 0 && $mi <= 59) {
            if ($h === 0) return _canonical_time(12, $mi, false);
            if ($h === 12) return _canonical_time(12, $mi, true);
            if ($h >= 13) return _canonical_time($h - 12, $mi, true);
            return $s;  // ambiguous (h=1..11 no AM/PM); preserve
        }
    }

    // Bare HH
    if (preg_match('/^(\d{1,2})$/', $s, $m)) {
        $raw = $m[1];
        $h = (int)$raw;
        if ($h >= 0 && $h <= 23) {
            $hasLeadingZero = strlen($raw) >= 2 && $raw[0] === '0';
            if ($h === 0) return '12am';
            if ($h === 12) return '12pm';
            if ($h >= 13) return _canonical_time($h - 12, 0, true);
            if ($hasLeadingZero) return _canonical_time($h, 0, false);
            return $s;  // bare 1-12 without leading zero; preserve
        }
    }

    return $s;  // unrecognized; preserve
}

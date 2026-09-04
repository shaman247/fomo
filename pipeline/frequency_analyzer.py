"""
Adaptive crawl frequency analyzer.

Analyzes historical crawl data to recommend optimal crawl frequencies
for each website, ensuring coverage of events in the next 2 weeks.

Two key signals for frequency:
1. Posting lead time — how far in advance a site posts new events.
   If P25 lead time is 8 days, we'd crawl every ~4 days to catch them
   (subject to a hard 3-day floor — see MIN_FREQUENCY).
2. Event horizon — how far into the future a crawl's events reach.
   If a crawl only shows events 5 days out, we must crawl within 5 days
   or we'll have a coverage gap.

The binding constraint is whichever requires more frequent crawling.

Periodicity (for crawl_after):
    For sites with repeating active/dormant cycles in their crawl history
    (annual festivals, seasonal venues), the analyzer also predicts the
    next active window and sets `crawl_after` so the scheduler skips the
    site entirely during the predicted dormant period — saving crawl
    budget that would otherwise be wasted at the MAX_FREQUENCY ceiling.

Standalone usage:
    python frequency_analyzer.py                  # Apply adjustments
    python frequency_analyzer.py --dry-run        # Report only, no changes
    python frequency_analyzer.py --ids 123,456    # Analyze specific websites
    python frequency_analyzer.py --verbose        # Show detailed metrics

Integration:
    Called as step in main.py after merge/archive.
"""

import argparse
import sys
from datetime import date, timedelta

import db

# Minimum completed crawls before auto-adjusting
MIN_CRAWL_HISTORY = 3

# Frequency bounds (days). The floor is 3 days: even sites that post events with
# very short lead times don't warrant crawling more often than every 3 days.
MIN_FREQUENCY = 3
MAX_FREQUENCY = 90
DEFAULT_FREQUENCY = 7

# Maximum change factor per adjustment (prevent oscillation)
MAX_CHANGE_FACTOR = 2.0

# Lookback window for historical analysis (days)
ANALYSIS_WINDOW_DAYS = 90

# Lead time percentile for "safe minimum" calculation
LEAD_TIME_PERCENTILE = 25

# Crawl at least this many times within the shortest typical posting window
LEAD_TIME_DIVISOR = 2

# Consecutive crawls with no new events before relaxing frequency
STALE_CRAWL_THRESHOLD = 3

# Multiplier when site is stale
STALE_FREQUENCY_MULTIPLIER = 1.5

# Very stale: consecutive crawls with no new events before aggressive relaxation
VERY_STALE_CRAWL_THRESHOLD = 10

# Buffer days subtracted from event horizon for safety margin
HORIZON_BUFFER_DAYS = 1

# Minimum new-event rate (new events / crawls) below which we ignore lead times
# and relax frequency. Prevents 1 event in 40 crawls from keeping freq at 1d.
MIN_USEFUL_EVENT_RATE = 0.1

# ---- Periodicity detection ----
# Won't trigger until we accumulate enough history. Annual patterns need ~1+ year
# of data; shorter cycles (60-180d) can be detected sooner.
PERIODICITY_MIN_CRAWLS = 10                 # Need this many processed crawls
PERIODICITY_MIN_HISTORY_DAYS = 120          # Need at least this much calendar span
PERIODICITY_MIN_PERIOD_DAYS = 60            # Don't predict cycles shorter than 2 months
PERIODICITY_TOLERANCE_DAYS = 45             # Cycle length can vary by this much
PERIODICITY_WINDOW_GAP_TOLERANCE_DAYS = 21  # Brief dormant breaks don't split a window
PERIODICITY_RECENT_DORMANT_CRAWLS = 3       # Last N crawls must all be zero
PERIODICITY_LEAD_BUFFER_DAYS = 30           # Start crawling this much before predicted next active


def _in_clause(ids):
    return ','.join(['%s'] * len(ids))


def _load_lead_times(cursor, website_ids):
    """website_id -> sorted lead times (days) for events found in the window.

    Lead time = event start_date - crawl date (when the event was first
    discovered). Only primary sources, only events still in the future at
    crawl time.
    """
    cursor.execute(f"""
        SELECT cr.website_id, DATEDIFF(ceo.start_date, DATE(cr.crawled_at)) as lead_time_days
        FROM event_sources es
        JOIN crawl_events ce ON es.crawl_event_id = ce.id
        JOIN crawl_results cr ON ce.crawl_result_id = cr.id
        JOIN crawl_event_occurrences ceo ON ceo.crawl_event_id = ce.id
        WHERE es.is_primary = TRUE
          AND cr.website_id IN ({_in_clause(website_ids)})
          AND cr.crawled_at >= DATE_SUB(NOW(), INTERVAL %s DAY)
          AND ceo.start_date >= DATE(cr.crawled_at)
        ORDER BY cr.website_id, lead_time_days
    """, (*website_ids, ANALYSIS_WINDOW_DAYS))
    out = {}
    for wid, lead in cursor.fetchall():
        out.setdefault(wid, []).append(lead)
    return out


def _load_event_horizons(cursor, website_ids):
    """website_id -> sorted horizons (days from each processed crawl to its
    furthest-future event)."""
    cursor.execute(f"""
        SELECT cr.website_id, MAX(DATEDIFF(ceo.start_date, DATE(cr.crawled_at))) as horizon_days
        FROM crawl_results cr
        JOIN crawl_events ce ON ce.crawl_result_id = cr.id
        JOIN crawl_event_occurrences ceo ON ceo.crawl_event_id = ce.id
        WHERE cr.website_id IN ({_in_clause(website_ids)})
          AND cr.status = 'processed'
          AND cr.crawled_at >= DATE_SUB(NOW(), INTERVAL %s DAY)
          AND ceo.start_date >= DATE(cr.crawled_at)
        GROUP BY cr.website_id, cr.id
        HAVING horizon_days IS NOT NULL
        ORDER BY cr.website_id, horizon_days
    """, (*website_ids, ANALYSIS_WINDOW_DAYS))
    out = {}
    for wid, horizon in cursor.fetchall():
        out.setdefault(wid, []).append(horizon)
    return out


def _load_new_event_rates(cursor, website_ids):
    """website_id -> dict(total_crawls, crawls_with_new_events, rate, crawls).

    A crawl "found new events" when it discovered events starting within 14
    days of the crawl date — fresh events we would actually have missed.
    `crawls` is ordered most recent first (consumed by _compute_stability).
    """
    cursor.execute(f"""
        SELECT cr.website_id, cr.id, cr.crawled_at, cr.event_count,
               COUNT(DISTINCT CASE WHEN es.is_primary = TRUE AND ceo.id IS NOT NULL
                     THEN es.event_id END) as new_events
        FROM crawl_results cr
        LEFT JOIN crawl_events ce ON ce.crawl_result_id = cr.id
        LEFT JOIN crawl_event_occurrences ceo ON ceo.crawl_event_id = ce.id
            AND ceo.start_date BETWEEN DATE(cr.crawled_at)
                AND DATE_ADD(DATE(cr.crawled_at), INTERVAL 14 DAY)
        LEFT JOIN event_sources es ON es.crawl_event_id = ce.id
        WHERE cr.website_id IN ({_in_clause(website_ids)})
          AND cr.status = 'processed'
          AND cr.crawled_at >= DATE_SUB(NOW(), INTERVAL %s DAY)
        GROUP BY cr.website_id, cr.id
        ORDER BY cr.website_id, cr.crawled_at DESC
    """, (*website_ids, ANALYSIS_WINDOW_DAYS))
    by_site = {}
    for wid, _cr_id, crawled_at, event_count, new_events in cursor.fetchall():
        by_site.setdefault(wid, []).append(
            {'crawled_at': crawled_at, 'event_count': event_count, 'new_events': new_events})
    out = {}
    for wid in website_ids:
        crawls = by_site.get(wid, [])
        total = len(crawls)
        with_new = sum(1 for c in crawls if c['new_events'] > 0)
        out[wid] = {
            'total_crawls': total,
            'crawls_with_new_events': with_new,
            'rate': with_new / total if total > 0 else 0.0,
            'crawls': crawls,
        }
    return out


def _load_content_staleness(cursor, website_ids, recent=30):
    """website_id -> number of consecutive recent crawls whose content size
    equals the most recent crawl's (counting back from the newest, up to the
    last `recent` crawls). Same size strongly correlates with identical
    content — the page hasn't changed, so those crawls were pure waste."""
    cursor.execute(f"""
        SELECT website_id, LENGTH(crawled_content) as content_size
        FROM crawl_results
        WHERE website_id IN ({_in_clause(website_ids)})
          AND status = 'processed'
          AND crawled_at >= DATE_SUB(NOW(), INTERVAL %s DAY)
        ORDER BY website_id, id DESC
    """, (*website_ids, ANALYSIS_WINDOW_DAYS))
    sizes_by_site = {}
    for wid, size in cursor.fetchall():
        sizes = sizes_by_site.setdefault(wid, [])
        if len(sizes) < recent:
            sizes.append(size)
    out = {}
    for wid, sizes in sizes_by_site.items():
        consecutive_same = 0
        for i in range(1, len(sizes)):
            if sizes[i] == sizes[0]:
                consecutive_same += 1
            else:
                break
        out[wid] = consecutive_same
    return out


def _load_has_upcoming(cursor, website_ids):
    """Set of website_ids with active events starting in the next 14 days."""
    cursor.execute(f"""
        SELECT DISTINCT e.website_id FROM events e
        JOIN event_occurrences eo ON e.id = eo.event_id
        WHERE e.website_id IN ({_in_clause(website_ids)})
          AND e.archived = FALSE
          AND eo.start_date BETWEEN CURDATE() AND DATE_ADD(CURDATE(), INTERVAL 14 DAY)
    """, tuple(website_ids))
    return {row[0] for row in cursor.fetchall()}


def _load_crawl_histories(cursor, website_ids):
    """website_id -> chronological [(date, event_count)] over the FULL processed
    history (periodicity needs as much history as possible, not just the
    analysis window)."""
    cursor.execute(f"""
        SELECT website_id, DATE(crawled_at), event_count
        FROM crawl_results
        WHERE website_id IN ({_in_clause(website_ids)}) AND status = 'processed'
        ORDER BY website_id, crawled_at
    """, tuple(website_ids))
    out = {}
    for wid, d, count in cursor.fetchall():
        out.setdefault(wid, []).append((d, count))
    return out


def _load_metrics(cursor, website_ids):
    """Run the six per-metric queries once over all analyzed websites.

    Replaces six queries per website (~13k round trips per run) with six
    GROUP BY / IN(...) queries. Returns website_id -> dict of raw metric inputs.
    """
    if not website_ids:
        return {}
    lead_times = _load_lead_times(cursor, website_ids)
    horizons = _load_event_horizons(cursor, website_ids)
    new_event_rates = _load_new_event_rates(cursor, website_ids)
    staleness = _load_content_staleness(cursor, website_ids)
    has_upcoming = _load_has_upcoming(cursor, website_ids)
    histories = _load_crawl_histories(cursor, website_ids)
    return {
        wid: {
            'lead_times': lead_times.get(wid, []),
            'horizons': horizons.get(wid, []),
            'new_event_data': new_event_rates[wid],
            'content_staleness': staleness.get(wid, 0),
            'has_upcoming': wid in has_upcoming,
            'crawl_history': histories.get(wid, []),
        }
        for wid in website_ids
    }


def _compute_stability(new_event_data):
    """
    Check how many consecutive recent crawls found zero new events.

    Uses the crawl list from _compute_new_event_rate (most recent first).
    """
    consecutive_no_new = 0
    for crawl in new_event_data['crawls']:
        if crawl['new_events'] == 0:
            consecutive_no_new += 1
        else:
            break

    return {
        'consecutive_no_new': consecutive_no_new,
    }


def _compute_content_staleness(cursor, website_id):
    """
    Count consecutive recent crawls with identical content size.

    Same content size strongly correlates with identical content — the page
    hasn't changed between crawls, making subsequent crawls pure waste.

    Returns the number of consecutive recent crawls with the same content size
    (counting back from the most recent crawl).
    """
    cursor.execute("""
        SELECT LENGTH(crawled_content) as content_size
        FROM crawl_results
        WHERE website_id = %s
          AND status = 'processed'
          AND crawled_at >= DATE_SUB(NOW(), INTERVAL %s DAY)
        ORDER BY id DESC
        LIMIT 30
    """, (website_id, ANALYSIS_WINDOW_DAYS))

    sizes = [row[0] for row in cursor.fetchall()]
    if len(sizes) < 2:
        return 0

    consecutive_same = 0
    for i in range(1, len(sizes)):
        if sizes[i] == sizes[0]:
            consecutive_same += 1
        else:
            break

    return consecutive_same


def _has_upcoming_events(cursor, website_id):
    """Check if a website has active events starting in the next 14 days."""
    cursor.execute("""
        SELECT COUNT(*) FROM events e
        JOIN event_occurrences eo ON e.id = eo.event_id
        WHERE e.website_id = %s
          AND e.archived = FALSE
          AND eo.start_date BETWEEN CURDATE() AND DATE_ADD(CURDATE(), INTERVAL 14 DAY)
    """, (website_id,))
    return cursor.fetchone()[0] > 0


def _percentile(sorted_values, pct):
    """Compute the given percentile from a sorted list. Returns None if empty."""
    if not sorted_values:
        return None
    index = max(0, int(len(sorted_values) * pct / 100) - 1)
    return sorted_values[index]


def _find_active_windows(crawl_history, gap_tolerance_days=PERIODICITY_WINDOW_GAP_TOLERANCE_DAYS):
    """
    Find continuous active windows in a chronological crawl history.

    An active window is a sequence of crawls with event_count > 0, possibly
    interrupted by brief dormant gaps (<= gap_tolerance_days). Longer dormant
    runs close the current window.

    Args:
        crawl_history: list of (date, event_count) tuples, sorted by date.
        gap_tolerance_days: max consecutive dormant days that don't split a window.

    Returns:
        list of (start_date, end_date) tuples.
    """
    windows = []
    current_start = None
    current_end = None

    for d, event_count in crawl_history:
        if event_count > 0:
            if current_start is None:
                current_start = d
            current_end = d
        elif current_start is not None and (d - current_end).days > gap_tolerance_days:
            windows.append((current_start, current_end))
            current_start = None
            current_end = None

    if current_start is not None:
        windows.append((current_start, current_end))

    return windows


def _detect_periodicity_from_history(crawl_history, today):
    """
    Detect repeating active-window patterns in a crawl history.

    Pure function — no DB access — for testability.

    Args:
        crawl_history: list of (date, event_count) tuples, sorted ascending.
        today: reference date (typically date.today()).

    Returns:
        dict with:
          period_days, last_active_start, next_predicted_start,
          crawl_after, cycles_observed, total_windows
        — or None if no reliable pattern.
    """
    if len(crawl_history) < PERIODICITY_MIN_CRAWLS:
        return None

    history_span_days = (crawl_history[-1][0] - crawl_history[0][0]).days
    if history_span_days < PERIODICITY_MIN_HISTORY_DAYS:
        return None

    windows = _find_active_windows(crawl_history)
    if len(windows) < 2:
        return None

    gaps = [(windows[i][0] - windows[i - 1][0]).days for i in range(1, len(windows))]

    # Only consider gaps that look like real cycles (sub-MIN_PERIOD gaps may just be
    # noise within an active window that the gap-tolerance didn't bridge).
    cycle_gaps = [g for g in gaps if g >= PERIODICITY_MIN_PERIOD_DAYS]
    if not cycle_gaps:
        return None

    mean_gap = sum(cycle_gaps) / len(cycle_gaps)

    # All cycle gaps must cluster tightly — otherwise it's not really periodic.
    if not all(abs(g - mean_gap) <= PERIODICITY_TOLERANCE_DAYS for g in cycle_gaps):
        return None

    # Confidence guard: a single observed gap is only trusted at annual-ish
    # lengths (where the prior is strong — yearly festivals, seasonal venues).
    # Shorter "1-gap" patterns (e.g. one quarterly-looking gap) are too easy
    # to find coincidentally; require 2+ confirming cycles.
    annual_range = (310, 410)
    if len(cycle_gaps) < 2 and not (annual_range[0] <= mean_gap <= annual_range[1]):
        return None

    # Only set crawl_after if the site is currently dormant. If recent crawls
    # show activity, the site is in its active window and should keep being crawled.
    recent = crawl_history[-PERIODICITY_RECENT_DORMANT_CRAWLS:]
    if any(event_count > 0 for _, event_count in recent):
        return None

    period_days = round(mean_gap)
    last_window_start = windows[-1][0]
    next_predicted = last_window_start + timedelta(days=period_days)
    proposed_crawl_after = next_predicted - timedelta(days=PERIODICITY_LEAD_BUFFER_DAYS)

    # If the predicted reactivation is in the past or imminent, don't set
    # crawl_after — the site is overdue and should be crawled normally.
    if proposed_crawl_after <= today:
        return None

    return {
        'period_days': period_days,
        'last_active_start': last_window_start,
        'next_predicted_start': next_predicted,
        'crawl_after': proposed_crawl_after,
        'cycles_observed': len(cycle_gaps),
        'total_windows': len(windows),
    }


def _recommend_frequency(lead_times, horizons, new_event_data, stability,
                         has_upcoming, current_frequency, content_staleness=0):
    """
    Recommend a crawl frequency based on analyzed metrics.

    Two signals determine the base frequency:
    1. Lead time: freq <= P25_lead_time / 2 (catch new events before they happen)
    2. Horizon: freq < P25_horizon (re-crawl before current event window expires)

    The binding constraint (smaller value) wins.

    Then:
    3. Override if new-event rate is too low (lead times from rare events shouldn't
       keep frequency high — 1 event in 40 crawls doesn't justify daily crawling)
    4. Adjust up if site is stable with no new events
    5. Aggressively relax if very stale (10+ consecutive crawls with no new events)
    6. Set to MAX if no upcoming events and no short-lead history
    7. Clamp to [MIN, MAX] days
    8. Limit change to 2x in either direction (relaxed to 4x for very stale sites)
    """
    current = current_frequency or DEFAULT_FREQUENCY
    reasons = []

    # Compute P25 values
    p25_lead_time = _percentile(lead_times, LEAD_TIME_PERCENTILE)
    p25_horizon = _percentile(horizons, LEAD_TIME_PERCENTILE)

    # Check if new-event rate is too low to trust lead time signal.
    # A site that produced 1 event in 40 crawls shouldn't stay at 1d just because
    # that one event had a 2-day lead time.
    low_yield = (new_event_data['total_crawls'] >= 10
                 and new_event_data['rate'] < MIN_USEFUL_EVENT_RATE)

    # Frequency from lead time signal
    freq_from_lead = None
    if p25_lead_time is not None and not low_yield:
        freq_from_lead = max(MIN_FREQUENCY, p25_lead_time // LEAD_TIME_DIVISOR)

    # Frequency from horizon signal
    freq_from_horizon = None
    if p25_horizon is not None and not low_yield:
        freq_from_horizon = max(MIN_FREQUENCY, p25_horizon - HORIZON_BUFFER_DAYS)

    if freq_from_lead is not None and freq_from_horizon is not None:
        recommended = min(freq_from_lead, freq_from_horizon)
        if freq_from_horizon < freq_from_lead:
            reasons.append(f"Horizon P25: {p25_horizon}d -> freq: {freq_from_horizon}d "
                           f"(tighter than lead time {freq_from_lead}d)")
        else:
            reasons.append(f"P25 lead time: {p25_lead_time}d -> freq: {freq_from_lead}d")
    elif freq_from_lead is not None:
        recommended = freq_from_lead
        reasons.append(f"P25 lead time: {p25_lead_time}d -> freq: {freq_from_lead}d")
    elif freq_from_horizon is not None:
        recommended = freq_from_horizon
        reasons.append(f"Horizon P25: {p25_horizon}d -> freq: {freq_from_horizon}d")
    else:
        # No usable lead time or horizon data (either missing or low-yield override)
        if low_yield:
            rate_pct = f"{new_event_data['rate']:.0%}"
            recommended = max(DEFAULT_FREQUENCY, current)
            reasons.append(f"Low yield: {rate_pct} new-event rate over "
                           f"{new_event_data['total_crawls']} crawls")
        elif new_event_data['total_crawls'] >= MIN_CRAWL_HISTORY and new_event_data['rate'] == 0:
            recommended = max(current + 1, min(int(current * STALE_FREQUENCY_MULTIPLIER), MAX_FREQUENCY))
            reasons.append(f"No new events in {new_event_data['total_crawls']} crawls")
        else:
            return {
                'frequency': current,
                'reason': 'Insufficient data',
                'changed': False,
                'metrics': {'lead_times_count': 0, 'horizons_count': 0},
            }

    # Stability adjustment — relax frequency for stale sites
    if stability['consecutive_no_new'] >= STALE_CRAWL_THRESHOLD:
        # Use max(current + 1, ...) so 1d sites can actually increase (1*1.5 rounds to 1)
        adjusted = max(recommended + 1, int(recommended * STALE_FREQUENCY_MULTIPLIER))
        if adjusted > recommended:
            reasons.append(f"{stability['consecutive_no_new']} stale crawls, "
                           f"{recommended}d -> {adjusted}d")
            recommended = adjusted

    # Content staleness — if page content hasn't changed, recrawling is waste
    if content_staleness >= VERY_STALE_CRAWL_THRESHOLD:
        content_floor = max(recommended, DEFAULT_FREQUENCY)
        if content_floor > recommended:
            reasons.append(f"{content_staleness} identical-content crawls, "
                           f"{recommended}d -> {content_floor}d")
            recommended = content_floor

    # No upcoming events with no short-lead history
    if not has_upcoming and lead_times and min(lead_times) > 7:
        recommended = MAX_FREQUENCY
        reasons.append(f"No upcoming events, min lead {min(lead_times)}d")

    # Clamp to bounds
    recommended = max(MIN_FREQUENCY, min(MAX_FREQUENCY, recommended))

    # Limit change rate — but allow faster relaxation for very stale sites
    very_stale = stability['consecutive_no_new'] >= VERY_STALE_CRAWL_THRESHOLD
    change_factor = MAX_CHANGE_FACTOR * 2 if very_stale else MAX_CHANGE_FACTOR

    if current > 0:
        # Floor the increase ceiling at MIN_FREQUENCY so the change-rate clamp can
        # never pull a recommendation back below the floor (e.g. a legacy 1d site
        # whose 2x ceiling would otherwise be 2d jumps straight to the 3d floor).
        max_new = max(MIN_FREQUENCY, int(current * change_factor))
        min_new = max(MIN_FREQUENCY, int(current / MAX_CHANGE_FACTOR))
        if recommended > max_new:
            reasons.append(f"Clamped {recommended}d -> {max_new}d "
                           f"(max {int(change_factor)}x increase)")
            recommended = max_new
        elif recommended < min_new:
            reasons.append(f"Clamped {recommended}d -> {min_new}d (max 2x decrease)")
            recommended = min_new

    metrics = {
        'lead_times_count': len(lead_times),
        'p25_lead_time': p25_lead_time,
        'min_lead_time': min(lead_times) if lead_times else None,
        'median_lead_time': lead_times[len(lead_times) // 2] if lead_times else None,
        'horizons_count': len(horizons),
        'p25_horizon': p25_horizon,
        'min_horizon': min(horizons) if horizons else None,
        'median_horizon': horizons[len(horizons) // 2] if horizons else None,
        'new_event_rate': new_event_data['rate'],
        'consecutive_no_new': stability['consecutive_no_new'],
        'content_staleness': content_staleness,
        'has_upcoming': has_upcoming,
    }

    return {
        'frequency': recommended,
        'reason': '; '.join(reasons),
        'changed': recommended != current,
        'metrics': metrics,
    }


def analyze_frequencies(cursor, connection, website_ids=None, dry_run=False, verbose=False):
    """
    Analyze and optionally adjust crawl frequencies for eligible websites.

    Args:
        cursor: Database cursor
        connection: Database connection
        website_ids: Optional list of website IDs to analyze
        dry_run: If True, print recommendations without applying
        verbose: If True, print detailed metrics per website

    Returns:
        dict with analyzed, adjusted, skipped counts and details list
    """
    # Get eligible websites. `crawl_after` is pulled so we can skip sites that
    # already have a future skip-until date set (manually or by a prior run).
    filter_sql = ''
    params = ()
    if website_ids:
        placeholders = ','.join(['%s'] * len(website_ids))
        filter_sql = f'\n              AND w.id IN ({placeholders})'
        params = tuple(website_ids)
    cursor.execute(f"""
        SELECT w.id, w.name, w.crawl_frequency, w.crawl_frequency_locked, w.crawl_after,
               (SELECT COUNT(*) FROM crawl_results cr
                WHERE cr.website_id = w.id
                  AND cr.status = 'processed'
                  AND cr.crawled_at >= DATE_SUB(NOW(), INTERVAL {ANALYSIS_WINDOW_DAYS} DAY)) as crawl_count
        FROM websites w
        WHERE w.disabled = FALSE{filter_sql}
        ORDER BY w.name
    """, params)

    websites = []
    for row in cursor.fetchall():
        websites.append({
            'id': row[0],
            'name': row[1],
            'crawl_frequency': row[2],
            'locked': bool(row[3]),
            'crawl_after': row[4],
            'crawl_count': row[5],
        })

    results = {
        'analyzed': 0,
        'adjusted': 0,
        'skipped': 0,
        'crawl_after_set': 0,
        'details': [],
    }

    today = date.today()

    # Pass 1: apply the skip guards, collecting the websites to analyze.
    eligible = []
    for w in websites:
        name = w['name']
        current_freq = w['crawl_frequency'] or DEFAULT_FREQUENCY
        current_crawl_after = w['crawl_after']

        # Skip locked websites
        if w['locked']:
            if verbose:
                print(f"  Skipped {name}: frequency locked")
            results['skipped'] += 1
            continue

        # Skip sites already gated by a future crawl_after — manual or prior-run.
        # Re-evaluating them is unsafe because we have no fresh data to override with.
        if current_crawl_after is not None and current_crawl_after > today:
            if verbose:
                print(f"  Skipped {name}: crawl_after={current_crawl_after} (future)")
            results['skipped'] += 1
            continue

        # Skip websites with manually set high frequencies (seasonal/annual events)
        if current_freq > MAX_FREQUENCY:
            if verbose:
                print(f"  Skipped {name}: frequency {current_freq}d exceeds max ({MAX_FREQUENCY}d)")
            results['skipped'] += 1
            continue

        # Skip websites with insufficient history
        if w['crawl_count'] < MIN_CRAWL_HISTORY:
            if verbose:
                print(f"  Skipped {name}: only {w['crawl_count']} crawls (need {MIN_CRAWL_HISTORY})")
            results['skipped'] += 1
            continue

        eligible.append(w)

    # Pass 2: load every metric for the eligible set in six bulk queries, then
    # score each website from the in-memory inputs.
    metrics = _load_metrics(cursor, [w['id'] for w in eligible])

    for w in eligible:
        wid = w['id']
        name = w['name']
        current_freq = w['crawl_frequency'] or DEFAULT_FREQUENCY
        m_in = metrics[wid]

        lead_times = m_in['lead_times']
        horizons = m_in['horizons']
        new_event_data = m_in['new_event_data']
        stability = _compute_stability(new_event_data)
        has_upcoming = m_in['has_upcoming']
        content_staleness = m_in['content_staleness']
        periodicity = _detect_periodicity_from_history(m_in['crawl_history'], today)

        recommendation = _recommend_frequency(
            lead_times, horizons, new_event_data, stability, has_upcoming, current_freq,
            content_staleness=content_staleness
        )

        results['analyzed'] += 1
        new_freq = recommendation['frequency']
        new_crawl_after = periodicity['crawl_after'] if periodicity else None

        detail = {
            'website_id': wid,
            'name': name,
            'old_frequency': current_freq,
            'new_frequency': new_freq,
            'changed': recommendation['changed'],
            'reason': recommendation['reason'],
            'metrics': recommendation['metrics'],
            'periodicity': periodicity,
            'new_crawl_after': new_crawl_after,
        }
        results['details'].append(detail)

        # Apply frequency change
        if recommendation['changed']:
            results['adjusted'] += 1
            prefix = "[DRY RUN] " if dry_run else ""
            print(f"  {prefix}{name}: {current_freq}d -> {new_freq}d ({recommendation['reason']})")

            if not dry_run:
                cursor.execute(
                    "UPDATE websites SET crawl_frequency = %s WHERE id = %s",
                    (new_freq, wid)
                )
                connection.commit()
        elif verbose:
            print(f"  {name}: {current_freq}d (no change — {recommendation['reason']})")

        # Apply crawl_after from periodicity detection (independent of frequency change)
        if new_crawl_after is not None:
            results['crawl_after_set'] += 1
            prefix = "[DRY RUN] " if dry_run else ""
            print(f"  {prefix}{name}: crawl_after -> {new_crawl_after} "
                  f"(period {periodicity['period_days']}d, "
                  f"{periodicity['cycles_observed']} cycle(s); "
                  f"next active ~{periodicity['next_predicted_start']})")

            if not dry_run:
                cursor.execute(
                    "UPDATE websites SET crawl_after = %s WHERE id = %s",
                    (new_crawl_after, wid)
                )
                connection.commit()

        if verbose and (recommendation['metrics'].get('lead_times_count', 0) > 0
                        or recommendation['metrics'].get('horizons_count', 0) > 0):
            m = recommendation['metrics']
            if m['lead_times_count'] > 0:
                print(f"    Lead times: {m['lead_times_count']} samples, "
                      f"min={m['min_lead_time']}d, P25={m['p25_lead_time']}d, "
                      f"median={m['median_lead_time']}d")
            if m['horizons_count'] > 0:
                print(f"    Horizons: {m['horizons_count']} crawls, "
                      f"min={m['min_horizon']}d, P25={m['p25_horizon']}d, "
                      f"median={m['median_horizon']}d")
            print(f"    New event rate: {m['new_event_rate']:.0%}, "
                  f"consecutive stale: {m['consecutive_no_new']}, "
                  f"content stale: {m.get('content_staleness', 0)}, "
                  f"upcoming: {'yes' if m['has_upcoming'] else 'no'}")

    return results


def parse_args():
    parser = argparse.ArgumentParser(
        description='Analyze and adjust website crawl frequencies',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python frequency_analyzer.py                  # Apply adjustments
  python frequency_analyzer.py --dry-run        # Report only
  python frequency_analyzer.py --ids 941,942    # Specific websites
  python frequency_analyzer.py --verbose        # Detailed metrics
  python frequency_analyzer.py --dry-run -v     # Full report, no changes
        """
    )
    parser.add_argument(
        '--dry-run', '-d',
        action='store_true',
        help='Print recommendations without applying changes'
    )
    parser.add_argument(
        '--ids',
        type=str,
        help='Comma-separated list of website IDs to analyze'
    )
    parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        help='Show detailed metrics for each website'
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()

    website_ids = None
    if args.ids:
        website_ids = [int(id.strip()) for id in args.ids.split(',')]

    connection = db.create_connection()
    if not connection:
        print("Failed to connect to database")
        sys.exit(1)

    cursor = connection.cursor(buffered=True)

    try:
        print(f"{'='*60}")
        print("CRAWL FREQUENCY ANALYSIS")
        if args.dry_run:
            print("  (Dry run -- no changes will be applied)")
        print(f"{'='*60}\n")

        results = analyze_frequencies(
            cursor, connection,
            website_ids=website_ids,
            dry_run=args.dry_run,
            verbose=args.verbose
        )

        print(f"\n{'='*60}")
        print("SUMMARY")
        print(f"{'='*60}")
        print(f"  Analyzed:        {results['analyzed']}")
        print(f"  Frequency adj:   {results['adjusted']}")
        print(f"  crawl_after set: {results['crawl_after_set']}")
        print(f"  Skipped:         {results['skipped']}")
        if args.dry_run:
            print(f"\n  (Dry run -- no changes applied)")
    finally:
        cursor.close()
        connection.close()

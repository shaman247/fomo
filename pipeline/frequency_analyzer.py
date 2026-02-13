"""
Adaptive crawl frequency analyzer.

Analyzes historical crawl data to recommend optimal crawl frequencies
for each website, ensuring coverage of events in the next 2 weeks.

Two key signals:
1. Posting lead time — how far in advance a site posts new events.
   If P25 lead time is 5 days, we need to crawl every ~2 days to catch them.
2. Event horizon — how far into the future a crawl's events reach.
   If a crawl only shows events 5 days out, we must crawl within 5 days
   or we'll have a coverage gap.

The binding constraint is whichever requires more frequent crawling.

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

import db

# Minimum completed crawls before auto-adjusting
MIN_CRAWL_HISTORY = 3

# Frequency bounds (days)
MIN_FREQUENCY = 1
MAX_FREQUENCY = 14
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

# Buffer days subtracted from event horizon for safety margin
HORIZON_BUFFER_DAYS = 1


def _compute_lead_times(cursor, website_id):
    """
    Compute posting lead times for a website.

    Lead time = event start_date - crawl date (when event was first discovered).
    Only considers primary sources and events that were in the future at crawl time.

    Returns sorted list of lead time values in days (ascending).
    """
    cursor.execute("""
        SELECT DATEDIFF(ceo.start_date, DATE(cr.crawled_at)) as lead_time_days
        FROM event_sources es
        JOIN crawl_events ce ON es.crawl_event_id = ce.id
        JOIN crawl_results cr ON ce.crawl_result_id = cr.id
        JOIN crawl_event_occurrences ceo ON ceo.crawl_event_id = ce.id
        WHERE es.is_primary = TRUE
          AND cr.website_id = %s
          AND cr.crawled_at >= DATE_SUB(NOW(), INTERVAL %s DAY)
          AND ceo.start_date >= DATE(cr.crawled_at)
        ORDER BY lead_time_days
    """, (website_id, ANALYSIS_WINDOW_DAYS))

    return [row[0] for row in cursor.fetchall()]


def _compute_event_horizon(cursor, website_id):
    """
    Compute the event horizon for each crawl — how far into the future
    a crawl's events reach.

    For each processed crawl, finds the max start_date across all events
    and computes days from the crawl date to that furthest event.

    Returns sorted list of horizon values in days (ascending).
    """
    cursor.execute("""
        SELECT MAX(DATEDIFF(ceo.start_date, DATE(cr.crawled_at))) as horizon_days
        FROM crawl_results cr
        JOIN crawl_events ce ON ce.crawl_result_id = cr.id
        JOIN crawl_event_occurrences ceo ON ceo.crawl_event_id = ce.id
        WHERE cr.website_id = %s
          AND cr.status = 'processed'
          AND cr.crawled_at >= DATE_SUB(NOW(), INTERVAL %s DAY)
          AND ceo.start_date >= DATE(cr.crawled_at)
        GROUP BY cr.id
        HAVING horizon_days IS NOT NULL
        ORDER BY horizon_days
    """, (website_id, ANALYSIS_WINDOW_DAYS))

    return [row[0] for row in cursor.fetchall()]


def _compute_new_event_rate(cursor, website_id):
    """
    Compute the fraction of recent crawls that discovered new near-term events.

    Only counts new events whose start_date is within 14 days of the crawl date.
    This measures how often a crawl yields fresh events we'd actually miss.

    Returns dict with total_crawls, crawls_with_new_events, rate,
    and per-crawl details ordered most recent first.
    """
    cursor.execute("""
        SELECT cr.id, cr.crawled_at, cr.event_count,
               COUNT(DISTINCT CASE WHEN es.is_primary = TRUE AND ceo.id IS NOT NULL
                     THEN es.event_id END) as new_events
        FROM crawl_results cr
        LEFT JOIN crawl_events ce ON ce.crawl_result_id = cr.id
        LEFT JOIN crawl_event_occurrences ceo ON ceo.crawl_event_id = ce.id
            AND ceo.start_date BETWEEN DATE(cr.crawled_at)
                AND DATE_ADD(DATE(cr.crawled_at), INTERVAL 14 DAY)
        LEFT JOIN event_sources es ON es.crawl_event_id = ce.id
        WHERE cr.website_id = %s
          AND cr.status = 'processed'
          AND cr.crawled_at >= DATE_SUB(NOW(), INTERVAL %s DAY)
        GROUP BY cr.id
        ORDER BY cr.crawled_at DESC
    """, (website_id, ANALYSIS_WINDOW_DAYS))

    rows = cursor.fetchall()
    crawls = [{'crawled_at': r[1], 'event_count': r[2], 'new_events': r[3]} for r in rows]
    total = len(crawls)
    with_new = sum(1 for c in crawls if c['new_events'] > 0)

    return {
        'total_crawls': total,
        'crawls_with_new_events': with_new,
        'rate': with_new / total if total > 0 else 0.0,
        'crawls': crawls,
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


def _recommend_frequency(lead_times, horizons, new_event_data, stability, has_upcoming, current_frequency):
    """
    Recommend a crawl frequency based on analyzed metrics.

    Two signals determine the base frequency:
    1. Lead time: freq <= P25_lead_time / 2 (catch new events before they happen)
    2. Horizon: freq < P25_horizon (re-crawl before current event window expires)

    The binding constraint (smaller value) wins.

    Then:
    3. Adjust up if site is stable with no new events
    4. Set to MAX if no upcoming events and no short-lead history
    5. Clamp to [MIN, MAX] days
    6. Limit change to 2x in either direction
    """
    current = current_frequency or DEFAULT_FREQUENCY
    reasons = []

    # Compute P25 values
    p25_lead_time = _percentile(lead_times, LEAD_TIME_PERCENTILE)
    p25_horizon = _percentile(horizons, LEAD_TIME_PERCENTILE)

    # Frequency from lead time signal
    freq_from_lead = None
    if p25_lead_time is not None:
        freq_from_lead = max(MIN_FREQUENCY, p25_lead_time // LEAD_TIME_DIVISOR)

    # Frequency from horizon signal
    freq_from_horizon = None
    if p25_horizon is not None:
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
        # No lead time or horizon data
        if new_event_data['total_crawls'] >= MIN_CRAWL_HISTORY and new_event_data['rate'] == 0:
            recommended = min(int(current * STALE_FREQUENCY_MULTIPLIER), MAX_FREQUENCY)
            reasons.append(f"No new events in {new_event_data['total_crawls']} crawls")
        else:
            return {
                'frequency': current,
                'reason': 'Insufficient data',
                'changed': False,
                'metrics': {'lead_times_count': 0, 'horizons_count': 0},
            }

    # Stability adjustment
    if stability['consecutive_no_new'] >= STALE_CRAWL_THRESHOLD:
        adjusted = int(recommended * STALE_FREQUENCY_MULTIPLIER)
        if adjusted > recommended:
            reasons.append(f"{stability['consecutive_no_new']} stale crawls, "
                           f"{recommended}d -> {adjusted}d")
            recommended = adjusted

    # No upcoming events with no short-lead history
    if not has_upcoming and lead_times and min(lead_times) > 7:
        recommended = MAX_FREQUENCY
        reasons.append(f"No upcoming events, min lead {min(lead_times)}d")

    # Clamp to bounds
    recommended = max(MIN_FREQUENCY, min(MAX_FREQUENCY, recommended))

    # Limit change rate
    if current > 0:
        max_new = int(current * MAX_CHANGE_FACTOR)
        min_new = max(MIN_FREQUENCY, int(current / MAX_CHANGE_FACTOR))
        if recommended > max_new:
            reasons.append(f"Clamped {recommended}d -> {max_new}d (max 2x increase)")
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
    # Get eligible websites
    if website_ids:
        placeholders = ','.join(['%s'] * len(website_ids))
        cursor.execute(f"""
            SELECT w.id, w.name, w.crawl_frequency, w.crawl_frequency_locked,
                   (SELECT COUNT(*) FROM crawl_results cr
                    WHERE cr.website_id = w.id
                      AND cr.status = 'processed'
                      AND cr.crawled_at >= DATE_SUB(NOW(), INTERVAL {ANALYSIS_WINDOW_DAYS} DAY)) as crawl_count
            FROM websites w
            WHERE w.disabled = FALSE
              AND w.id IN ({placeholders})
            ORDER BY w.name
        """, website_ids)
    else:
        cursor.execute(f"""
            SELECT w.id, w.name, w.crawl_frequency, w.crawl_frequency_locked,
                   (SELECT COUNT(*) FROM crawl_results cr
                    WHERE cr.website_id = w.id
                      AND cr.status = 'processed'
                      AND cr.crawled_at >= DATE_SUB(NOW(), INTERVAL {ANALYSIS_WINDOW_DAYS} DAY)) as crawl_count
            FROM websites w
            WHERE w.disabled = FALSE
            ORDER BY w.name
        """)

    websites = []
    for row in cursor.fetchall():
        websites.append({
            'id': row[0],
            'name': row[1],
            'crawl_frequency': row[2],
            'locked': bool(row[3]),
            'crawl_count': row[4],
        })

    results = {
        'analyzed': 0,
        'adjusted': 0,
        'skipped': 0,
        'details': [],
    }

    for w in websites:
        wid = w['id']
        name = w['name']
        current_freq = w['crawl_frequency'] or DEFAULT_FREQUENCY

        # Skip locked websites
        if w['locked']:
            if verbose:
                print(f"  Skipped {name}: frequency locked")
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

        # Analyze
        lead_times = _compute_lead_times(cursor, wid)
        horizons = _compute_event_horizon(cursor, wid)
        new_event_data = _compute_new_event_rate(cursor, wid)
        stability = _compute_stability(new_event_data)
        has_upcoming = _has_upcoming_events(cursor, wid)

        recommendation = _recommend_frequency(
            lead_times, horizons, new_event_data, stability, has_upcoming, current_freq
        )

        results['analyzed'] += 1
        new_freq = recommendation['frequency']

        detail = {
            'website_id': wid,
            'name': name,
            'old_frequency': current_freq,
            'new_frequency': new_freq,
            'changed': recommendation['changed'],
            'reason': recommendation['reason'],
            'metrics': recommendation['metrics'],
        }
        results['details'].append(detail)

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
        print(f"  Analyzed: {results['analyzed']}")
        print(f"  Adjusted: {results['adjusted']}")
        print(f"  Skipped:  {results['skipped']}")
        if args.dry_run:
            print(f"\n  (Dry run -- no changes applied)")
    finally:
        cursor.close()
        connection.close()

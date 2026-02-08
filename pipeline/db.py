"""
Database operations for the event processing pipeline.

Handles all database connections and CRUD operations for:
- Crawl runs and results
- Websites and their crawl status
- Crawl events (raw extracted data)
"""

import json
import os
import sys

try:
    import mysql.connector
    from mysql.connector import Error
except ImportError:
    print("Error: mysql-connector-python is required.")
    print("Install it with: pip install mysql-connector-python")
    sys.exit(1)


# Database Configuration
DB_CONFIG = {
    'local': {
        'host': 'localhost',
        'database': 'fomo',
        'user': 'root',
        'password': ''
    },
    'production': {
        'host': 'localhost',
        'database': 'fomoowsq_fomo',
        'user': 'fomoowsq_root',
        'password': 'REDACTED_DB_PASSWORD'
    }
}


def get_db_config():
    """Get database config based on environment."""
    env = os.environ.get('FOMO_ENV', 'local')
    if env not in DB_CONFIG:
        env = 'local'
    return DB_CONFIG[env]


def create_connection():
    """Create database connection."""
    config = get_db_config()
    try:
        return mysql.connector.connect(
            host=config['host'],
            database=config['database'],
            user=config['user'],
            password=config['password']
        )
    except Error as e:
        print(f"Error connecting to database: {e}")
        return None


def _parse_url_data(url_string):
    """Parse URL data from concatenated format 'url:::js_code|||url:::js_code|||...'"""
    urls = []
    for item in url_string.split('|||'):
        parts = item.split(':::', 1)
        url = parts[0]
        js_code = parts[1] if len(parts) > 1 and parts[1] else None
        urls.append({'url': url, 'js_code': js_code})
    return urls


def get_websites_due_for_crawling(cursor, website_ids=None):
    """
    Get websites that are due for crawling based on crawl_frequency.

    Args:
        cursor: Database cursor
        website_ids: Optional list of website IDs to filter by. If provided,
                     only these websites are returned (ignoring crawl_frequency).

    Returns websites where:
    - disabled = FALSE
    - crawl_after is NULL or in the past
    - last_crawled_at is NULL, OR
    - NOW() - last_crawled_at > crawl_frequency days
    """
    if website_ids:
        # When specific IDs are provided, ignore crawl_frequency
        placeholders = ','.join(['%s'] * len(website_ids))
        cursor.execute(f"""
            SELECT w.id, w.name, w.crawl_frequency, w.selector, w.num_clicks,
                   w.keywords, w.max_pages, w.max_batches, w.notes,
                   w.delay_before_return_html, w.content_filter_threshold, w.scan_full_page,
                   w.remove_overlay_elements, w.javascript_enabled, w.text_mode, w.light_mode,
                   w.use_stealth, w.scroll_delay, w.crawl_timeout, w.process_images, w.base_url,
                   GROUP_CONCAT(CONCAT(wu.url, ':::', IFNULL(wu.js_code, '')) ORDER BY wu.sort_order SEPARATOR '|||') as urls
            FROM websites w
            LEFT JOIN website_urls wu ON w.id = wu.website_id
            WHERE w.id IN ({placeholders})
            GROUP BY w.id
            HAVING urls IS NOT NULL
            ORDER BY w.id ASC
        """, website_ids)
    else:
        cursor.execute("""
            SELECT w.id, w.name, w.crawl_frequency, w.selector, w.num_clicks,
                   w.keywords, w.max_pages, w.max_batches, w.notes,
                   w.delay_before_return_html, w.content_filter_threshold, w.scan_full_page,
                   w.remove_overlay_elements, w.javascript_enabled, w.text_mode, w.light_mode,
                   w.use_stealth, w.scroll_delay, w.crawl_timeout, w.process_images, w.base_url,
                   GROUP_CONCAT(CONCAT(wu.url, ':::', IFNULL(wu.js_code, '')) ORDER BY wu.sort_order SEPARATOR '|||') as urls
            FROM websites w
            LEFT JOIN website_urls wu ON w.id = wu.website_id
            WHERE w.disabled = FALSE
              AND (w.crawl_after IS NULL OR w.crawl_after <= CURDATE())
              AND (w.force_crawl = TRUE
                   OR w.last_crawled_at IS NULL
                   OR DATEDIFF(NOW(), w.last_crawled_at) >= COALESCE(w.crawl_frequency, 7))
            GROUP BY w.id
            HAVING urls IS NOT NULL
            ORDER BY w.force_crawl DESC, w.last_crawled_at ASC
        """)

    websites = []
    for row in cursor.fetchall():
        website = {
            'id': row[0],
            'name': row[1],
            'crawl_frequency': row[2] or 7,
            'selector': row[3],
            'num_clicks': row[4] or 2,
            'keywords': row[5],
            'max_pages': row[6] or 30,
            'max_batches': row[7],
            'notes': row[8],
            'delay_before_return_html': row[9],
            'content_filter_threshold': row[10],
            'scan_full_page': row[11],
            'remove_overlay_elements': row[12],
            'javascript_enabled': row[13],
            'text_mode': row[14],
            'light_mode': row[15],
            'use_stealth': row[16],
            'scroll_delay': float(row[17]) if row[17] is not None else None,
            'crawl_timeout': row[18],
            'process_images': row[19],
            'base_url': row[20],
            'urls': _parse_url_data(row[21]) if row[21] else []
        }
        websites.append(website)

    return websites


def get_or_create_crawl_run(cursor, connection, run_date):
    """Get or create a crawl run for the given date."""
    cursor.execute("SELECT id FROM crawl_runs WHERE run_date = %s", (run_date,))
    result = cursor.fetchone()
    if result:
        return result[0]

    cursor.execute(
        "INSERT INTO crawl_runs (run_date, status, started_at) VALUES (%s, 'running', NOW())",
        (run_date,)
    )
    connection.commit()
    return cursor.lastrowid


def create_crawl_result(cursor, connection, crawl_run_id, website_id, filename):
    """Create a new crawl result record."""
    cursor.execute(
        """INSERT INTO crawl_results (crawl_run_id, website_id, filename, status, created_at)
           VALUES (%s, %s, %s, 'pending', NOW())
           ON DUPLICATE KEY UPDATE status = 'pending'""",
        (crawl_run_id, website_id, filename)
    )
    connection.commit()

    cursor.execute(
        "SELECT id FROM crawl_results WHERE crawl_run_id = %s AND filename = %s",
        (crawl_run_id, filename)
    )
    return cursor.fetchone()[0]


def update_crawl_result(cursor, connection, crawl_result_id, status, **kwargs):
    """
    Generic update function for crawl results.

    Args:
        cursor: Database cursor
        connection: Database connection
        crawl_result_id: ID of the crawl result to update
        status: New status value
        **kwargs: Additional fields to update (content, event_count, error_message)
    """
    updates = ["status = %s"]
    params = [status]

    # Map status to timestamp field
    timestamp_map = {
        'crawled': 'crawled_at',
        'extracted': 'extracted_at',
        'processed': 'processed_at'
    }
    if status in timestamp_map:
        updates.append(f"{timestamp_map[status]} = NOW()")

    # Handle optional fields
    if 'content' in kwargs:
        if status == 'crawled':
            updates.append("crawled_content = %s")
        elif status == 'extracted':
            updates.append("extracted_content = %s")
        params.append(kwargs['content'])

    if 'event_count' in kwargs:
        updates.append("event_count = %s")
        params.append(kwargs['event_count'])

    if 'error_message' in kwargs:
        updates.append("error_message = %s")
        error_msg = kwargs['error_message']
        params.append(error_msg[:65535] if error_msg else None)

    params.append(crawl_result_id)

    cursor.execute(
        f"UPDATE crawl_results SET {', '.join(updates)} WHERE id = %s",
        tuple(params)
    )
    connection.commit()


def update_crawl_result_crawled(cursor, connection, crawl_result_id, content):
    """Update crawl result with crawled content."""
    update_crawl_result(cursor, connection, crawl_result_id, 'crawled', content=content)


def update_crawl_result_extracted(cursor, connection, crawl_result_id, content):
    """Update crawl result with extracted content."""
    update_crawl_result(cursor, connection, crawl_result_id, 'extracted', content=content)


def update_crawl_result_processed(cursor, connection, crawl_result_id, event_count):
    """Update crawl result as processed."""
    update_crawl_result(cursor, connection, crawl_result_id, 'processed', event_count=event_count)


def update_crawl_result_failed(cursor, connection, crawl_result_id, error_message):
    """Update crawl result as failed."""
    update_crawl_result(cursor, connection, crawl_result_id, 'failed', error_message=error_message)


def update_website_last_crawled(cursor, connection, website_id):
    """Update the last_crawled_at timestamp for a website and reset force_crawl flag."""
    cursor.execute(
        "UPDATE websites SET last_crawled_at = NOW(), force_crawl = FALSE WHERE id = %s",
        (website_id,)
    )
    connection.commit()


def complete_crawl_run(cursor, connection, crawl_run_id):
    """Mark a crawl run as completed."""
    cursor.execute(
        "UPDATE crawl_runs SET status = 'completed', completed_at = NOW() WHERE id = %s",
        (crawl_run_id,)
    )
    connection.commit()


def get_incomplete_crawl_results(cursor):
    """
    Get crawl results that need reprocessing.

    Returns results that are:
    - In 'crawled' status (need extraction)
    - In 'extracted' status (need processing)
    - In 'failed' status but have crawled_content (extraction failed, can retry)

    Returns results from any crawl run, not just today's.
    """
    cursor.execute("""
        SELECT cr.id, cr.status, cr.website_id, cr.crawl_run_id,
               w.name, w.notes, crun.run_date,
               CASE
                   WHEN cr.status = 'failed' AND cr.crawled_content IS NOT NULL
                        AND cr.extracted_content IS NULL THEN 'crawled'
                   WHEN cr.status = 'failed' AND cr.extracted_content IS NOT NULL THEN 'extracted'
                   ELSE cr.status
               END as effective_status
        FROM crawl_results cr
        JOIN websites w ON cr.website_id = w.id
        JOIN crawl_runs crun ON cr.crawl_run_id = crun.id
        WHERE w.disabled = FALSE
          AND (
              cr.status IN ('crawled', 'extracted')
              OR (cr.status = 'failed' AND cr.crawled_content IS NOT NULL)
          )
        ORDER BY cr.status, crun.run_date DESC
    """)

    results = []
    for row in cursor.fetchall():
        results.append({
            'crawl_result_id': row[0],
            'status': row[7],  # Use effective_status for processing
            'original_status': row[1],
            'website_id': row[2],
            'crawl_run_id': row[3],
            'name': row[4],
            'notes': row[5],
            'run_date': row[6]
        })

    return results


def get_crawled_content(cursor, crawl_result_id):
    """Get crawled content for a crawl result."""
    cursor.execute(
        "SELECT crawled_content FROM crawl_results WHERE id = %s",
        (crawl_result_id,)
    )
    result = cursor.fetchone()
    return result[0] if result else None


def get_existing_upcoming_events(cursor, website_id):
    """
    Get existing upcoming events from a website for inclusion in extraction prompt.

    Returns active (non-archived) events with occurrences from today onwards,
    formatted as JSON-compatible dicts.
    """
    cursor.execute("""
        SELECT
            e.id, e.name, e.description,
            l.name as location, e.sublocation,
            GROUP_CONCAT(
                JSON_OBJECT(
                    'start_date', eo.start_date,
                    'start_time', eo.start_time,
                    'end_date', eo.end_date,
                    'end_time', eo.end_time
                )
                ORDER BY eo.start_date
            ) as occurrences_json,
            GROUP_CONCAT(DISTINCT eu.url ORDER BY eu.sort_order) as urls,
            GROUP_CONCAT(DISTINCT t.name ORDER BY t.name) as tags,
            e.emoji
        FROM events e
        LEFT JOIN locations l ON e.location_id = l.id
        LEFT JOIN event_occurrences eo ON e.id = eo.event_id
        LEFT JOIN event_urls eu ON e.id = eu.event_id
        LEFT JOIN event_tags et ON e.id = et.event_id
        LEFT JOIN tags t ON et.tag_id = t.id
        WHERE e.website_id = %s
          AND e.archived = FALSE
          AND eo.start_date >= CURDATE()
        GROUP BY e.id, e.name, e.description, l.name, e.sublocation, e.emoji
        ORDER BY MIN(eo.start_date)
    """, (website_id,))

    events = []
    for row in cursor.fetchall():
        event = {
            'id': row[0],
            'name': row[1],
            'description': row[2],
            'location': row[3],
            'sublocation': row[4],
            'occurrences': json.loads(f"[{row[5]}]") if row[5] else [],
            'urls': row[6].split(',') if row[6] else [],
            'hashtags': row[7].split(',') if row[7] else [],
            'emoji': row[8]
        }
        events.append(event)

    return events


def archive_outdated_events(cursor, connection, website_id):
    """
    Archive events that are no longer found in recent crawls from ANY of their source websites.

    An event is archived only if:
    - For EVERY website that has ever referenced this event (via event_sources),
      the most recent crawl from that website does NOT include this event
    - At least one of those websites has been successfully crawled

    This ensures events referenced by multiple websites are only archived when
    ALL sources stop listing them, not just one.

    Logs a warning when upcoming events are archived (rare occurrence that may indicate
    crawl failures or legitimate event changes).

    Args:
        cursor: Database cursor
        connection: Database connection
        website_id: ID of the website that was just crawled (used to find related events)

    Returns:
        Number of events archived
    """
    # Shared WHERE clause for identifying events to archive.
    # An event qualifies when:
    # 1. It has a source from the website we just crawled
    # 2. No source website's latest crawl still references it
    # 3. At least one source website has been successfully crawled
    archive_where = """
        e.archived = FALSE
          AND EXISTS (
              SELECT 1
              FROM event_sources es
              JOIN crawl_events ce ON es.crawl_event_id = ce.id
              JOIN crawl_results cr ON ce.crawl_result_id = cr.id
              WHERE es.event_id = e.id
                AND cr.website_id = %s
          )
          AND NOT EXISTS (
              SELECT 1
              FROM event_sources es
              JOIN crawl_events ce ON es.crawl_event_id = ce.id
              JOIN crawl_results cr ON ce.crawl_result_id = cr.id
              WHERE es.event_id = e.id
                AND cr.processed_at = (
                    SELECT MAX(cr2.processed_at)
                    FROM crawl_results cr2
                    WHERE cr2.website_id = cr.website_id
                      AND cr2.status IN ('processed', 'extracted')
                      AND cr2.processed_at IS NOT NULL
                )
          )
          AND EXISTS (
              SELECT 1
              FROM event_sources es
              JOIN crawl_events ce ON es.crawl_event_id = ce.id
              JOIN crawl_results cr ON ce.crawl_result_id = cr.id
              WHERE es.event_id = e.id
                AND cr.status IN ('processed', 'extracted')
                AND cr.processed_at IS NOT NULL
          )
    """

    # First, identify events that will be archived to check for upcoming ones
    cursor.execute(f"""
        SELECT e.id, e.name,
               (SELECT MIN(eo.start_date)
                FROM event_occurrences eo
                WHERE eo.event_id = e.id
                  AND eo.start_date >= CURDATE()) as next_occurrence
        FROM events e
        WHERE {archive_where}
    """, (website_id,))

    events_to_archive = cursor.fetchall()
    upcoming_events = [(event_id, name, next_occ) for event_id, name, next_occ in events_to_archive if next_occ]

    # Perform the actual archiving
    cursor.execute(f"""
        UPDATE events e
        SET archived = TRUE
        WHERE {archive_where}
    """, (website_id,))

    archived_count = cursor.rowcount
    connection.commit()

    return archived_count, upcoming_events


def get_extracted_content(cursor, crawl_result_id):
    """Get extracted content and website_id for a crawl result."""
    cursor.execute(
        "SELECT extracted_content, website_id FROM crawl_results WHERE id = %s",
        (crawl_result_id,)
    )
    result = cursor.fetchone()
    return (result[0], result[1]) if result else (None, None)


def get_all_locations(cursor):
    """
    Get all locations with their alternate names for location matching.

    Returns a list of dicts with: id, name, short_name, address, lat, lng, emoji, alternate_names, website_scoped_names
    - alternate_names: list of global alternate names (no website_id)
    - website_scoped_names: dict mapping website_id -> list of alternate names
    """
    # Get all locations
    cursor.execute("""
        SELECT id, name, short_name, address, lat, lng, emoji
        FROM locations
        WHERE lat IS NOT NULL AND lng IS NOT NULL
    """)

    locations = {}
    for row in cursor.fetchall():
        locations[row[0]] = {
            'id': row[0],
            'name': row[1],
            'short_name': row[2],
            'address': row[3],
            'lat': float(row[4]) if row[4] else None,
            'lng': float(row[5]) if row[5] else None,
            'emoji': row[6],
            'alternate_names': [],
            'website_scoped_names': {}
        }

    # Get all alternate names (both global and website-scoped)
    cursor.execute("""
        SELECT location_id, alternate_name, website_id
        FROM location_alternate_names
    """)

    for row in cursor.fetchall():
        location_id, alternate_name, website_id = row
        if location_id in locations:
            if website_id is None:
                locations[location_id]['alternate_names'].append(alternate_name)
            else:
                locations[location_id]['website_scoped_names'].setdefault(website_id, []).append(alternate_name)

    return list(locations.values())


def get_tag_rules(cursor):
    """
    Get tag processing rules from the database.

    Returns a dict with:
    - 'rewrite': dict mapping pattern -> replacement
    - 'exclude': list of patterns to filter out
    - 'remove': list of patterns that indicate event should be skipped
    """
    rules = {'rewrite': {}, 'exclude': [], 'remove': []}

    cursor.execute("""
        SELECT rule_type, pattern, replacement
        FROM tag_rules
        ORDER BY rule_type, pattern
    """)

    for row in cursor.fetchall():
        rule_type, pattern, replacement = row
        if rule_type == 'rewrite':
            rules['rewrite'][pattern] = replacement
        elif rule_type == 'exclude':
            rules['exclude'].append(pattern)
        elif rule_type == 'remove':
            rules['remove'].append(pattern)

    return rules


def get_websites_with_tags(cursor):
    """
    Get all websites with their URLs and extra tags.

    Returns a dict mapping URL (lowercase, no trailing slash) to list of extra tags.
    """
    cursor.execute("""
        SELECT wu.url, wt.tag
        FROM website_urls wu
        JOIN websites w ON wu.website_id = w.id
        LEFT JOIN website_tags wt ON w.id = wt.website_id
        WHERE w.disabled = FALSE
        ORDER BY wu.website_id, wu.sort_order
    """)

    websites_map = {}
    for row in cursor.fetchall():
        url, tag = row
        normalized_url = url.rstrip('/').lower()
        if normalized_url not in websites_map:
            websites_map[normalized_url] = []
        if tag:
            websites_map[normalized_url].append(tag)

    return websites_map

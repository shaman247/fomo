"""
Database operations for the event processing pipeline.

Handles all database connections and CRUD operations for:
- Crawl runs and results
- Websites and their crawl status
- Crawl events (raw extracted data)
"""

import hashlib
import json
import os
import re
import sys

try:
    import mysql.connector
    from mysql.connector import Error
except ImportError:
    print("Error: mysql-connector-python is required.")
    print("Install it with: pip install mysql-connector-python")
    sys.exit(1)

from constants import MAX_PAGES_DEFAULT


def compute_content_hash(content):
    """SHA-256 hash of crawled content for change detection."""
    if content is None:
        return None
    if isinstance(content, str):
        content = content.encode('utf-8')
    return hashlib.sha256(content).hexdigest()


# Database Configuration
DB_CONFIG = {
    'local': {
        'host': 'localhost',
        'database': 'fomo',
        'user': 'root',
        'password': ''
    },
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
            password=config['password'],
            # Bound the connect phase so an unreachable/hung DB fails fast
            # instead of blocking a worker indefinitely (default is unbounded).
            connection_timeout=30,
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
                   w.use_stealth, w.headed, w.user_agent, w.scroll_delay, w.crawl_timeout, w.process_images, w.base_url,
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
                   w.use_stealth, w.headed, w.user_agent, w.scroll_delay, w.crawl_timeout, w.process_images, w.base_url,
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
            'max_pages': row[6] or MAX_PAGES_DEFAULT,
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
            'headed': row[17],
            'user_agent': row[18],
            'scroll_delay': float(row[19]) if row[19] is not None else None,
            'crawl_timeout': row[20],
            'process_images': row[21],
            'base_url': row[22],
            'urls': _parse_url_data(row[23]) if row[23] else []
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
            updates.append("content_hash = %s")
            params.append(kwargs['content'])
            params.append(compute_content_hash(kwargs['content']))
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


def find_prior_crawl_with_same_content(cursor, crawl_result_id):
    """
    Find the most recent prior crawl_result for the same website that has the
    same content_hash and was successfully processed.

    Returns the prior crawl_result_id if found, otherwise None.

    Used to short-circuit extraction when a crawl produces identical content
    to a previous successful crawl — we copy its events instead of re-running
    the AI extractor.
    """
    cursor.execute("""
        SELECT cr_prior.id
        FROM crawl_results cr_curr
        JOIN crawl_results cr_prior
          ON cr_prior.website_id = cr_curr.website_id
         AND cr_prior.content_hash = cr_curr.content_hash
         AND cr_prior.id < cr_curr.id
         AND cr_prior.status = 'processed'
         AND cr_prior.event_count IS NOT NULL
        WHERE cr_curr.id = %s AND cr_curr.content_hash IS NOT NULL
        ORDER BY cr_prior.id DESC
        LIMIT 1
    """, (crawl_result_id,))
    row = cursor.fetchone()
    if not row:
        return None
    return row[0] if not isinstance(row, dict) else row['id']


def copy_crawl_events(cursor, connection, src_crawl_result_id, dst_crawl_result_id):
    """
    Copy all crawl_events (and their occurrences) from one crawl_result to another.

    Used when a fresh crawl produced identical content to a previous successful
    crawl — we reuse the prior extraction without re-calling Gemini.

    Returns the number of crawl_events copied.
    """
    # Map old crawl_event ids → new ones so we can copy occurrences
    cursor.execute("""
        SELECT id, name, short_name, description, emoji, location_name, sublocation,
               location_id, url, raw_data, content_hash
        FROM crawl_events
        WHERE crawl_result_id = %s
        ORDER BY id
    """, (src_crawl_result_id,))
    src_events = cursor.fetchall()

    if not src_events:
        return 0

    id_map = {}
    for row in src_events:
        # Support both tuple and dict cursors
        if isinstance(row, dict):
            (src_id, name, short_name, description, emoji, location_name,
             sublocation, location_id, url, raw_data, ce_content_hash) = (
                row['id'], row['name'], row['short_name'], row['description'],
                row['emoji'], row['location_name'], row['sublocation'],
                row['location_id'], row['url'], row['raw_data'], row['content_hash']
            )
        else:
            (src_id, name, short_name, description, emoji, location_name,
             sublocation, location_id, url, raw_data, ce_content_hash) = row

        cursor.execute("""
            INSERT INTO crawl_events
                (crawl_result_id, name, short_name, description, emoji,
                 location_name, sublocation, location_id, url, raw_data,
                 content_hash, created_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
        """, (dst_crawl_result_id, name, short_name, description, emoji,
              location_name, sublocation, location_id, url, raw_data,
              ce_content_hash))
        id_map[src_id] = cursor.lastrowid

    # Copy occurrences
    if id_map:
        placeholders = ','.join(['%s'] * len(id_map))
        cursor.execute(f"""
            SELECT crawl_event_id, start_date, start_time, end_date, end_time, sort_order
            FROM crawl_event_occurrences
            WHERE crawl_event_id IN ({placeholders})
        """, tuple(id_map.keys()))
        occs = cursor.fetchall()

        for occ in occs:
            if isinstance(occ, dict):
                src_event_id = occ['crawl_event_id']
                values = (id_map[src_event_id], occ['start_date'], occ['start_time'],
                          occ['end_date'], occ['end_time'], occ['sort_order'])
            else:
                src_event_id, start_date, start_time, end_date, end_time, sort_order = occ
                values = (id_map[src_event_id], start_date, start_time, end_date, end_time, sort_order)

            cursor.execute("""
                INSERT INTO crawl_event_occurrences
                    (crawl_event_id, start_date, start_time, end_date, end_time, sort_order)
                VALUES (%s, %s, %s, %s, %s, %s)
            """, values)

    connection.commit()
    return len(src_events)


def set_batch_job_name(cursor, connection, crawl_result_ids, batch_job_name):
    """Tag crawl results with their Gemini batch job name for crash recovery."""
    if not crawl_result_ids:
        return
    placeholders = ','.join(['%s'] * len(crawl_result_ids))
    cursor.execute(
        f"UPDATE crawl_results SET batch_job_name = %s WHERE id IN ({placeholders})",
        (batch_job_name, *crawl_result_ids)
    )
    connection.commit()


def clear_batch_job_name(cursor, connection, crawl_result_ids):
    """Clear batch job name after results have been processed."""
    if not crawl_result_ids:
        return
    placeholders = ','.join(['%s'] * len(crawl_result_ids))
    cursor.execute(
        f"UPDATE crawl_results SET batch_job_name = NULL WHERE id IN ({placeholders})",
        tuple(crawl_result_ids)
    )
    connection.commit()


def get_pending_batch_jobs(cursor):
    """Find crawl results with in-flight batch jobs (for crash recovery).

    Returns dict of {batch_job_name: [crawl_result_id, ...]} for crawl results
    that have a batch_job_name set but haven't been extracted yet.
    """
    cursor.execute("""
        SELECT batch_job_name, GROUP_CONCAT(id) as crid_list
        FROM crawl_results
        WHERE batch_job_name IS NOT NULL
          AND status IN ('crawled', 'failed')
          AND extracted_content IS NULL
        GROUP BY batch_job_name
    """)
    result = {}
    for row in cursor.fetchall():
        result[row[0]] = [int(x) for x in row[1].split(',')]
    return result


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


def get_incomplete_crawl_results(cursor, website_ids=None):
    """
    Get crawl results that need reprocessing.

    Returns results that are:
    - In 'crawled' status (need extraction)
    - In 'extracted' status (need processing)
    - In 'failed' status but have crawled_content (extraction failed, can retry)

    Args:
        cursor: DB cursor
        website_ids: Optional list of website IDs to restrict to.
                     If None, returns results from any crawl run.
    """
    query = """
        SELECT cr.id, cr.status, cr.website_id, cr.crawl_run_id,
               w.name, w.notes, crun.run_date,
               CASE
                   WHEN cr.status = 'failed' AND cr.crawled_content IS NOT NULL
                        AND cr.extracted_content IS NULL THEN 'crawled'
                   WHEN cr.status = 'failed' AND cr.extracted_content IS NOT NULL THEN 'extracted'
                   ELSE cr.status
               END as effective_status,
               cr.batch_job_name
        FROM crawl_results cr
        JOIN websites w ON cr.website_id = w.id
        JOIN crawl_runs crun ON cr.crawl_run_id = crun.id
        WHERE w.disabled = FALSE
          AND (
              cr.status IN ('crawled', 'extracted')
              OR (cr.status = 'failed' AND cr.crawled_content IS NOT NULL)
          )
    """
    params = []
    if website_ids:
        placeholders = ','.join(['%s'] * len(website_ids))
        query += f" AND cr.website_id IN ({placeholders})"
        params.extend(website_ids)
    query += " ORDER BY cr.status, crun.run_date DESC"
    cursor.execute(query, params)

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
            'run_date': row[6],
            'batch_job_name': row[8]
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
                DISTINCT JSON_OBJECT(
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
    - For events with future occurrences: a 14-day grace period applies — the event
      is only archived if its most recent source crawl is older than 14 days.
      This prevents premature archiving of events on rotating calendars that don't
      always list events far in advance.

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
    # 4. Either has no future dates, or last source crawl is 14+ days old (grace period)
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
          AND (
              -- No future occurrences: archive immediately (past events)
              NOT EXISTS (
                  SELECT 1 FROM event_occurrences eo
                  WHERE eo.event_id = e.id AND eo.start_date >= CURDATE()
              )
              OR
              -- Has future occurrences: only archive after 14-day grace period
              -- (handles rotating calendars that don't always list far-out events)
              NOT EXISTS (
                  SELECT 1
                  FROM event_sources es
                  JOIN crawl_events ce ON es.crawl_event_id = ce.id
                  JOIN crawl_results cr ON ce.crawl_result_id = cr.id
                  WHERE es.event_id = e.id
                    AND cr.processed_at >= DATE_SUB(NOW(), INTERVAL 14 DAY)
              )
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


def get_website_locations_map(cursor):
    """
    Build a map of website_id -> [location_info] from website_locations table.

    Returns dict mapping website_id to list of location dicts with id, name, lat, lng, emoji.
    Only includes locations with valid coordinates.
    """
    cursor.execute("""
        SELECT wl.website_id, l.id, l.name, l.lat, l.lng, l.emoji
        FROM website_locations wl
        JOIN locations l ON wl.location_id = l.id
        WHERE l.lat IS NOT NULL AND l.lng IS NOT NULL
    """)

    result = {}
    for row in cursor.fetchall():
        website_id = row[0]
        loc_info = {
            'id': row[1],
            'name': row[2],
            'lat': float(row[3]) if row[3] else None,
            'lng': float(row[4]) if row[4] else None,
            'emoji': row[5]
        }
        result.setdefault(website_id, []).append(loc_info)

    return result


def _load_generic_location_names():
    """Load geotag names from tags.json as a set of generic location names.

    These are neighborhood/borough/region names that are too vague to be useful
    as event locations — events with these as their only location info should be
    detail-crawled to find the specific venue.
    """
    import json, os
    import city_config
    tags_path = os.path.join(os.path.dirname(__file__), '..', 'src', 'data', 'tags.json')
    try:
        with open(tags_path) as f:
            data = json.load(f)
        names = {name.lower() for name in data.get('geotags', [])}
        # Add common city-level names not in geotags (from city config)
        names.update(city_config.generic_location_names())
        return names
    except (FileNotFoundError, json.JSONDecodeError):
        return set()


def get_detail_crawl_candidates(cursor, website_ids=None):
    """Find crawl_events needing a detail crawl, filtered to individual event URLs.

    Finds unmerged crawl_events with missing descriptions, locations, or only
    generic location names (neighborhoods/boroughs) that have an event URL,
    then filters out listing-page URLs (shared by multiple events or matching
    the website's source URLs).

    Args:
        cursor: DB cursor
        website_ids: Optional list of website IDs to restrict to. When given,
                     only the website filter changes — the same staleness guards
                     (detail_crawl_attempts < 2, crawled within 14 days) still
                     apply, so a manual `--ids` run does NOT re-crawl the entire
                     historical backlog of orphaned/exhausted crawl_events.

    Returns list of (ce_id, name, url, website_id) tuples, deduped so each
    distinct (website_id, url) is crawled at most once per run.
    """
    generic_locations = _load_generic_location_names()

    # Query includes location_name so we can filter generic names in Python.
    # has_occurrences flag lets us detect events whose listing page provided
    # no date — those need a detail crawl too, not just events missing a description.
    if website_ids:
        placeholders = ','.join(['%s'] * len(website_ids))
        query = f"""
            SELECT ce.id, ce.name, ce.url, cr.website_id, ce.location_name, ce.description,
                   EXISTS(SELECT 1 FROM crawl_event_occurrences ceo WHERE ceo.crawl_event_id = ce.id) AS has_occurrences
            FROM crawl_events ce
            JOIN crawl_results cr ON ce.crawl_result_id = cr.id
            JOIN websites w ON cr.website_id = w.id
            LEFT JOIN event_sources es ON ce.id = es.crawl_event_id
            WHERE ce.url IS NOT NULL AND ce.url != ''
            AND es.id IS NULL
            AND w.skip_reenrichment = 0
            AND ce.detail_crawl_attempts < 2
            AND cr.crawled_at >= DATE_SUB(NOW(), INTERVAL 14 DAY)
            AND cr.website_id IN ({placeholders})
        """
        cursor.execute(query, list(website_ids))
    else:
        cursor.execute("""
            SELECT ce.id, ce.name, ce.url, cr.website_id, ce.location_name, ce.description,
                   EXISTS(SELECT 1 FROM crawl_event_occurrences ceo WHERE ceo.crawl_event_id = ce.id) AS has_occurrences
            FROM crawl_events ce
            JOIN crawl_results cr ON ce.crawl_result_id = cr.id
            JOIN websites w ON cr.website_id = w.id
            LEFT JOIN event_sources es ON ce.id = es.crawl_event_id
            WHERE ce.url IS NOT NULL AND ce.url != ''
            AND es.id IS NULL
            AND w.skip_reenrichment = 0
            AND ce.detail_crawl_attempts < 2
            AND cr.crawled_at >= DATE_SUB(NOW(), INTERVAL 14 DAY)
        """)
    rows = cursor.fetchall()

    # Filter to events that actually need detail crawling
    def needs_detail_crawl(location_name, description, has_occurrences):
        if not has_occurrences:
            return True
        if description == 'No description available.':
            return True
        if not location_name or location_name == 'Not specified':
            return True
        if location_name.lower() in generic_locations:
            return True
        return False

    candidates = [
        (ce_id, name, url, website_id)
        for ce_id, name, url, website_id, location_name, description, has_occurrences in rows
        if needs_detail_crawl(location_name, description, has_occurrences)
    ]

    if not candidates:
        return []

    # Count distinct event names per (website_id, url) — true listing pages have
    # multiple distinct events sharing one URL. Same name across crawl runs is
    # just a recurring event, not a listing page. Strip trailing parenthetical
    # suffixes (e.g. "(postponed)", "(rescheduled)") so a renamed recurring
    # event isn't mistaken for a listing page.
    _suffix_re = re.compile(r'\s*\([^)]*\)\s*$')
    def _norm_name(n):
        n = (n or '').strip().lower()
        # Strip up to 2 trailing parenthetical suffixes
        for _ in range(2):
            stripped = _suffix_re.sub('', n)
            if stripped == n:
                break
            n = stripped
        return n

    url_name_sets = {}
    for _, name, url, website_id in candidates:
        key = (website_id, url.rstrip('/'))
        url_name_sets.setdefault(key, set()).add(_norm_name(name))

    # Cache source/listing URLs per website
    source_url_cache = {}

    events_to_enrich = []
    skipped_shared = 0
    skipped_dup_url = 0
    # Crawl each distinct (website_id, url) at most once. After the listing-page
    # filter below, every remaining URL maps to a single event name, so any
    # duplicates here are the SAME recurring event captured across multiple crawl
    # runs (e.g. an exhibit re-extracted weekly that never merged). Fetching the
    # URL once and letting the merger collapse the duplicates avoids re-crawling
    # the same page N times — the backlog that made `--ids` runs crawl for hours.
    seen_urls = set()
    for ce_id, name, url, website_id in candidates:
        norm_url = url.rstrip('/')
        # Skip URLs that have multiple distinct event names (real listing pages)
        if len(url_name_sets.get((website_id, norm_url), set())) > 1:
            skipped_shared += 1
            continue
        # Skip URLs matching the website's source/listing URLs
        if website_id not in source_url_cache:
            cursor.execute(
                "SELECT url FROM website_urls WHERE website_id = %s",
                (website_id,),
            )
            source_url_cache[website_id] = {
                row[0].rstrip('/') for row in cursor.fetchall()
            }
        if norm_url in source_url_cache[website_id]:
            continue
        # Collapse same-URL duplicates to a single fetch per run.
        if (website_id, norm_url) in seen_urls:
            skipped_dup_url += 1
            continue
        seen_urls.add((website_id, norm_url))
        events_to_enrich.append((ce_id, name, url, website_id))

    if skipped_shared:
        print(f"  Skipped {skipped_shared} events with shared/listing URLs")
    if skipped_dup_url:
        print(f"  Skipped {skipped_dup_url} duplicate same-URL events (one fetch per URL)")

    return events_to_enrich


def get_website_crawl_settings(cursor, website_ids):
    """Load crawl and browser settings for the given website IDs.

    Returns dict mapping website_id to settings dict with keys:
    delay_before_return_html, content_filter_threshold, scan_full_page,
    remove_overlay_elements, scroll_delay, text_mode, light_mode,
    use_stealth, headed, user_agent.
    """
    if not website_ids:
        return {}

    placeholders = ','.join(['%s'] * len(website_ids))
    cursor.execute(f"""
        SELECT id, delay_before_return_html, content_filter_threshold,
               scan_full_page, remove_overlay_elements, scroll_delay,
               text_mode, light_mode, use_stealth, headed, user_agent
        FROM websites WHERE id IN ({placeholders})
    """, list(website_ids))

    settings = {}
    for row in cursor.fetchall():
        settings[row[0]] = {
            'delay_before_return_html': row[1],
            'content_filter_threshold': row[2],
            'scan_full_page': row[3],
            'remove_overlay_elements': row[4],
            'scroll_delay': float(row[5]) if row[5] is not None else None,
            'text_mode': row[6] if row[6] is not None else True,
            'light_mode': row[7] if row[7] is not None else True,
            'use_stealth': row[8] if row[8] is not None else False,
            'headed': row[9] if row[9] is not None else False,
            'user_agent': row[10],
        }

    return settings


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


def build_tag_ancestor_map(cursor):
    """Build a complete map: normalized_tag_name -> set of ancestor tag names.

    Loads all tag_hierarchy rows and computes transitive closure via BFS.
    Returns (ancestor_map, root_tags) where:
      - ancestor_map: dict mapping normalized_tag_name -> set of ancestor tag names
      - root_tags: set of normalized names for root tags (no parents, excl. Free/Virtual)
    """
    CROSS_CUTTING = {'free', 'virtual'}

    # Load all hierarchy edges with tag names
    cursor.execute("""
        SELECT p.name AS parent_name, c.name AS child_name
        FROM tag_hierarchy th
        JOIN tags p ON th.parent_tag_id = p.id
        JOIN tags c ON th.child_tag_id = c.id
    """)
    edges = cursor.fetchall()

    # Build direct parent map: normalized_child -> set of parent names
    direct_parents = {}
    all_children = set()
    all_parents = set()
    for row in edges:
        parent_name = row['parent_name'] if isinstance(row, dict) else row[0]
        child_name = row['child_name'] if isinstance(row, dict) else row[1]
        child_key = child_name.lower().replace(' ', '')
        all_children.add(child_key)
        all_parents.add(parent_name.lower().replace(' ', ''))
        if child_key not in direct_parents:
            direct_parents[child_key] = set()
        direct_parents[child_key].add(parent_name)

    # Compute transitive closure via BFS: for each tag, find ALL ancestors
    ancestor_map = {}
    for child_key in direct_parents:
        ancestors = set()
        queue = list(direct_parents[child_key])
        while queue:
            parent = queue.pop(0)
            if parent in ancestors:
                continue
            ancestors.add(parent)
            parent_key = parent.lower().replace(' ', '')
            for grandparent in direct_parents.get(parent_key, set()):
                if grandparent not in ancestors:
                    queue.append(grandparent)
        ancestor_map[child_key] = ancestors

    # Root tags: tags that are parents but never children (excl. cross-cutting)
    root_keys = all_parents - all_children
    root_tags = {k for k in root_keys if k not in CROSS_CUTTING and k != 'other'}

    return ancestor_map, root_tags


def get_tag_aliases(cursor):
    """Get tag aliases as a dict mapping normalized alias -> canonical tag name.

    Used during tag processing to replace alias tags with their canonical form.
    """
    cursor.execute("""
        SELECT ta.alias, t.name
        FROM tag_aliases ta
        JOIN tags t ON ta.tag_id = t.id
    """)
    return {
        row[0].lower().replace(' ', ''): row[1]
        for row in cursor.fetchall()
    }


def get_tag_aliases_for_export(cursor):
    """Get tag aliases grouped by canonical tag name.

    Returns dict mapping tag_name -> [alias1, alias2, ...] for tag hierarchy export.
    """
    cursor.execute("""
        SELECT t.name, ta.alias
        FROM tag_aliases ta
        JOIN tags t ON ta.tag_id = t.id
        ORDER BY t.name, ta.alias
    """)
    aliases_by_tag = {}
    for row in cursor.fetchall():
        tag_name = row[0]
        alias = row[1]
        aliases_by_tag.setdefault(tag_name, []).append(alias)
    return aliases_by_tag


def get_tag_disambiguations(cursor):
    """Load context-aware disambiguation rules for ambiguous tag names.

    Returns dict mapping normalized alias -> list of rules sorted by priority desc:
        {'avantgarde': [
            {'ctx_name': 'music', 'target_name': 'Avant Garde / Music', 'priority': 100},
            {'ctx_name': None,    'target_name': 'Avant Garde / Art',   'priority': 0},
        ], ...}
    ctx_name is normalized (lowercase, no spaces) for direct comparison against
    co-tag normalized forms / ancestor sets.
    """
    cursor.execute("""
        SELECT d.ambiguous_alias, ctx.name AS ctx_name, tgt.name AS target_name, d.priority
        FROM tag_disambiguations d
        LEFT JOIN tags ctx ON d.context_tag_id = ctx.id
        JOIN tags tgt ON d.target_tag_id = tgt.id
        ORDER BY d.ambiguous_alias, d.priority DESC
    """)
    rules = {}
    for row in cursor.fetchall():
        alias = row[0]
        ctx_name = row[1].lower().replace(' ', '') if row[1] else None
        target_name = row[2]
        priority = row[3]
        rules.setdefault(alias, []).append({
            'ctx_name': ctx_name,
            'target_name': target_name,
            'priority': priority,
        })
    return rules


def get_all_tags_with_metadata(cursor):
    """Get all tags with hierarchy metadata.

    Returns list of dicts: {id, name, emoji, is_quick_filter, display_order, type}
    """
    cursor.execute("""
        SELECT id, name, emoji, is_quick_filter, display_order, type
        FROM tags
        ORDER BY display_order IS NULL, display_order, name
    """)
    def _row_get(row, key_or_index, index):
        return row[key_or_index] if isinstance(row, dict) else row[index]

    return [
        {
            'id': _row_get(row, 'id', 0),
            'name': _row_get(row, 'name', 1),
            'emoji': _row_get(row, 'emoji', 2),
            'is_quick_filter': bool(_row_get(row, 'is_quick_filter', 3)),
            'display_order': _row_get(row, 'display_order', 4),
            'type': _row_get(row, 'type', 5)
        }
        for row in cursor.fetchall()
    ]


def upsert_event_tags(cursor, event_id, tag_names, replace=False):
    """Set tags for an event. If replace=True, deletes existing tags first."""
    if replace:
        cursor.execute("DELETE FROM event_tags WHERE event_id = %s", (event_id,))
    for tag in tag_names:
        if not tag:
            continue
        cursor.execute("SELECT id FROM tags WHERE name = %s", (tag[:100],))
        row = cursor.fetchone()
        tag_id = row[0] if row else None
        if not tag_id:
            # Novel AI-emitted tags are search-only keywords. They become
            # curated ('tag') only when explicitly promoted into the hierarchy
            # (see scripts/populate_tag_hierarchy.py).
            cursor.execute("INSERT INTO tags (name, type) VALUES (%s, 'keyword')", (tag[:100],))
            tag_id = cursor.lastrowid
        cursor.execute(
            "INSERT IGNORE INTO event_tags (event_id, tag_id) VALUES (%s, %s)",
            (event_id, tag_id)
        )


def get_tag_hierarchy_for_export(cursor):
    """Get tag hierarchy data formatted for JSON export.

    Returns (tags_list, keywords_list) where:
      - tags_list: list of dicts with name, parents, and optional emoji/quickFilter/order
      - keywords_list: list of keyword tag names
    """
    def _get(row, key, index):
        return row[key] if isinstance(row, dict) else row[index]

    # Get all tags with type='tag' and their parents
    cursor.execute("""
        SELECT t.id, t.name, t.emoji, t.is_quick_filter, t.display_order
        FROM tags t
        WHERE t.type = 'tag'
        ORDER BY t.display_order IS NULL, t.display_order, t.name
    """)
    tag_rows = cursor.fetchall()

    # Get all hierarchy edges
    cursor.execute("""
        SELECT p.name AS parent_name, c.name AS child_name
        FROM tag_hierarchy th
        JOIN tags p ON th.parent_tag_id = p.id
        JOIN tags c ON th.child_tag_id = c.id
    """)
    edges = cursor.fetchall()

    # Build parent map: tag_name -> [parent_names]
    parents_of = {}
    for row in edges:
        parent_name = _get(row, 'parent_name', 0)
        child_name = _get(row, 'child_name', 1)
        parents_of.setdefault(child_name, []).append(parent_name)

    # Build tags list
    tags_list = []
    for row in tag_rows:
        name = _get(row, 'name', 1)
        emoji = _get(row, 'emoji', 2)
        is_quick_filter = _get(row, 'is_quick_filter', 3)
        display_order = _get(row, 'display_order', 4)

        entry = {'name': name}
        parents = parents_of.get(name, [])
        entry['parents'] = sorted(parents)
        if emoji:
            entry['emoji'] = emoji
        if is_quick_filter:
            entry['quickFilter'] = True
        if display_order is not None:
            entry['order'] = display_order
        tags_list.append(entry)

    return tags_list

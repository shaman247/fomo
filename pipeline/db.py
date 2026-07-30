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

from constants import MAX_PAGES_DEFAULT, FUTURE_WINDOW_DAYS


def compute_content_hash(content):
    """SHA-256 hash of crawled content for change detection."""
    if content is None:
        return None
    if isinstance(content, str):
        content = content.encode('utf-8')
    return hashlib.sha256(content).hexdigest()


def _col(row, key, index):
    """Read a column from either a dict cursor row (by key) or a tuple row (by index)."""
    return row[key] if isinstance(row, dict) else row[index]


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


_WEBSITES_DUE_SELECT = """
    SELECT w.id, w.name, w.crawl_frequency, w.selector, w.num_clicks,
           w.keywords, w.max_pages, w.max_batches, w.notes,
           w.delay_before_return_html, w.content_filter_threshold, w.scan_full_page,
           w.remove_overlay_elements, w.javascript_enabled, w.text_mode, w.light_mode,
           w.use_stealth, w.headed, w.user_agent, w.scroll_delay, w.crawl_timeout, w.process_images, w.base_url,
           GROUP_CONCAT(CONCAT(wu.url, ':::', IFNULL(wu.js_code, '')) ORDER BY wu.sort_order SEPARATOR '|||') as urls
    FROM websites w
    LEFT JOIN website_urls wu ON w.id = wu.website_id
"""


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
        cursor.execute(_WEBSITES_DUE_SELECT + f"""
            WHERE w.id IN ({placeholders})
            GROUP BY w.id
            HAVING urls IS NOT NULL
            ORDER BY w.id ASC
        """, website_ids)
    else:
        cursor.execute(_WEBSITES_DUE_SELECT + """
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
    if status == 'crawled':
        # A fresh crawl reuses the same row within a crawl run (unique_run_file),
        # so the previous cycle's merge stamp no longer describes this content.
        updates.append("merged_at = NULL")

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
    return _col(row, 'id', 0)


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


def get_stranded_merge_summary(cursor, website_ids=None):
    """Find recently-processed crawl_results whose crawl_events never merged.

    A row qualifies when the crawl_result is 'processed' but still has at least
    one crawl_event with no event_sources link and a present/future occurrence —
    i.e. extraction succeeded but the merge tail never ran for it (interrupted
    run or lost lock race). These are exactly the rows the next merge pass picks
    up; this just makes them visible (and lets --merge-only report its scope).

    Two deliberate scope bounds keep by-design skips out of the report:
    - last 7 days only (older unmerged residue would already have been retried
      by the nightly merges — it isn't "stranded", it's declined);
    - the occurrence window mirrors the merger's valid-occurrence filter
      (start within FUTURE_WINDOW_DAYS and start/end not entirely past) — CEs
      whose dates are all beyond the window are deferred by design and merge
      on their own once the dates approach.

    Returns a list of (crawl_result_id, website_id, website_name, processed_at,
    unmerged_event_count) tuples.
    """
    query = """
        SELECT cr.id, cr.website_id, w.name, cr.processed_at, COUNT(DISTINCT ce.id)
        FROM crawl_results cr
        JOIN websites w ON cr.website_id = w.id
        JOIN crawl_events ce ON ce.crawl_result_id = cr.id
        LEFT JOIN event_sources es ON es.crawl_event_id = ce.id
        WHERE cr.status = 'processed'
          AND cr.processed_at >= DATE_SUB(NOW(), INTERVAL 7 DAY)
          AND es.id IS NULL
          AND EXISTS (
              SELECT 1 FROM crawl_event_occurrences ceo
              WHERE ceo.crawl_event_id = ce.id
                AND ceo.start_date <= DATE_ADD(CURDATE(), INTERVAL %s DAY)
                AND (ceo.start_date >= CURDATE()
                     OR (ceo.end_date IS NOT NULL AND ceo.end_date >= CURDATE()))
          )
    """
    params = [FUTURE_WINDOW_DAYS]
    if website_ids:
        placeholders = ','.join(['%s'] * len(website_ids))
        query += f" AND cr.website_id IN ({placeholders})"
        params.extend(website_ids)
    query += " GROUP BY cr.id, cr.website_id, w.name, cr.processed_at ORDER BY cr.processed_at"
    cursor.execute(query, params)
    return cursor.fetchall()


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


def build_archival_temps(cursor):
    """Precompute the two heavy shared sets the archival query needs, ONCE per run.

    `archive_outdated_events` is called once per crawled website (hundreds per run).
    Two of its subqueries are identical across every website and, evaluated inline,
    dominate the cost: the per-website "latest processed crawl" (a nested
    MAX(processed_at) that full-scans crawl_results) and the "has a current/future
    occurrence" check (a full scan of event_occurrences). Materializing both into
    small indexed TEMPORARY tables once turns each per-website query from a ~35s
    scan into a ~1s indexed lookup (measured: 47min → ~5min for a full run).

    Correctness: these are exact equivalents of the inline subqueries they replace,
    and they are stable for the duration of Step 6 — the merge tail holds the
    advisory write lock and no crawls are added during archival, so a snapshot taken
    once is identical to re-deriving it per website. CURDATE() is likewise constant
    within a run.

    DISABLED websites are excluded from _ws_latest. `_ws_latest` exists to answer
    "is this event still listed by the crawl that most recently spoke for its
    source website?" — a question only an ENABLED website can keep answering. A
    disabled website is never crawled again, so its final crawl freezes as
    `latest` forever and the archival query's "no source website's latest crawl
    still references this event" condition can never be satisfied again: every
    event that website ever sourced becomes permanently unarchivable (measured:
    431 non-archived events across 25 disabled websites). Dropping disabled
    websites here changes nothing for enabled ones — their rows are identical —
    and only affects events that have a disabled website among their sources.
    The JOIN also drops crawl_results whose website row no longer exists, which
    is the same "no live website speaks for this" case.

    Events left with NO enabled source website at all are not reachable from this
    per-website pass (see archive_dead_source_events).
    """
    cursor.execute("DROP TEMPORARY TABLE IF EXISTS _ws_latest")
    cursor.execute("""
        CREATE TEMPORARY TABLE _ws_latest (website_id INT UNSIGNED PRIMARY KEY, latest DATETIME(6))
        SELECT cr.website_id, MAX(cr.processed_at) AS latest
        FROM crawl_results cr
        JOIN websites w ON w.id = cr.website_id
        WHERE cr.status IN ('processed', 'extracted')
          AND cr.processed_at IS NOT NULL
          AND cr.website_id IS NOT NULL
          AND (w.disabled = FALSE OR w.disabled IS NULL)
        GROUP BY cr.website_id
    """)
    cursor.execute("DROP TEMPORARY TABLE IF EXISTS _evt_future")
    cursor.execute("""
        CREATE TEMPORARY TABLE _evt_future (event_id INT UNSIGNED PRIMARY KEY)
        SELECT DISTINCT event_id
        FROM event_occurrences
        WHERE start_date >= CURDATE()
           OR (end_date IS NOT NULL AND end_date >= CURDATE())
    """)


def drop_archival_temps(cursor):
    """Drop the archival helper temp tables built by build_archival_temps."""
    cursor.execute("DROP TEMPORARY TABLE IF EXISTS _ws_latest")
    cursor.execute("DROP TEMPORARY TABLE IF EXISTS _evt_future")


def archive_outdated_events(cursor, connection, website_id, temps_built=False):
    """
    Archive events that are no longer found in recent crawls from ANY of their source websites.

    An event is archived only if:
    - For EVERY website that has ever referenced this event (via event_sources),
      the most recent crawl from that website does NOT include this event
    - At least one of those websites has been successfully crawled
    - For events with future occurrences, THREE guards must all pass:
      1. 14-day grace period — the event's most recent supporting crawl is older
         than 14 days. Prevents premature archiving on rotating calendars that
         don't always list events far in advance.
      2. Fresh-crawl count — this website has completed >= 2 successful crawls
         since the event was last seen. On frequently-crawled sites the 14-day
         grace already implies many misses, but on monthly/annual-cadence sites
         14 days can pass with a single fresh crawl — one extraction miss would
         archive a live event without this guard.
      3. No recent 'start_too_future' rejection matching the event's name from
         this website. When all of an event's occurrences sit beyond
         FUTURE_WINDOW_DAYS the processor rejects the extraction, so the event
         never gets a fresh event_sources link even though it IS still listed
         on the page — without this guard such events age past the grace period
         and get archived while still published (e.g. Storm King's September
         program each June).

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

    Note:
        Reads the _ws_latest / _evt_future temp tables. When called standalone
        (temps_built=False, the default) it builds and drops them itself. In the
        per-website archival loop the caller builds them once via
        build_archival_temps() and passes temps_built=True so the hundreds of
        calls share one snapshot.
    """
    if not temps_built:
        build_archival_temps(cursor)

    # Shared WHERE clause for identifying events to archive.
    # An event qualifies when:
    # 1. It has a source from the website we just crawled
    # 2. No source website's latest crawl still references it
    # 3. At least one source website has been successfully crawled
    # 4. Either has no future dates, or all three future-event guards pass
    #    (14-day grace, >=2 fresh crawls since last seen, no too-future rejection)
    # Takes the website_id parameter THREE times (in order).
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
              -- No source website's LATEST crawl still references this event.
              -- _ws_latest (built once per run) holds MAX(processed_at) per website
              -- over status IN ('processed','extracted') AND processed_at IS NOT NULL
              -- — the exact value the inline correlated MAX used to compute per row.
              SELECT 1
              FROM event_sources es
              JOIN crawl_events ce ON es.crawl_event_id = ce.id
              JOIN crawl_results cr ON ce.crawl_result_id = cr.id
              JOIN _ws_latest wl ON wl.website_id = cr.website_id
              WHERE es.event_id = e.id
                AND cr.processed_at = wl.latest
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
              -- No current/future occurrences: archive immediately (past events).
              -- "Current" includes an on-view exhibition whose opening date has
              -- already passed but whose closing date (end_date) is today or later
              -- — matching how the merge-load and existing-event queries define a
              -- live occurrence (start_date OR end_date >= cutoff). Without the
              -- end_date arm, a still-on-view exhibition with a past opening date
              -- falls into this branch and is archived immediately, skipping the
              -- 14-day grace that long-running shows depend on.
              -- _evt_future (built once per run) = event_ids with a current/future
              -- occurrence (start_date >= today OR end_date >= today) — the exact
              -- set the inline event_occurrences NOT EXISTS tested per event.
              NOT EXISTS (
                  SELECT 1 FROM _evt_future f WHERE f.event_id = e.id
              )
              OR
              (
                  -- Has current/future occurrences: only archive after 14-day grace
                  -- period (handles rotating calendars that don't always list far-out events)
                  NOT EXISTS (
                      SELECT 1
                      FROM event_sources es
                      JOIN crawl_events ce ON es.crawl_event_id = ce.id
                      JOIN crawl_results cr ON ce.crawl_result_id = cr.id
                      WHERE es.event_id = e.id
                        AND cr.processed_at >= DATE_SUB(NOW(), INTERVAL 14 DAY)
                  )
                  -- ... AND this website has had >= 2 successful crawls since the
                  -- event was last seen (a wall-clock grace alone is zero-tolerance
                  -- on monthly-cadence sites: one missed extraction would archive)
                  AND (
                      SELECT COUNT(*)
                      FROM crawl_results crn
                      WHERE crn.website_id = %s
                        AND crn.status IN ('processed', 'extracted')
                        AND crn.processed_at IS NOT NULL
                        AND crn.processed_at > COALESCE((
                            SELECT MAX(cr3.processed_at)
                            FROM event_sources es3
                            JOIN crawl_events ce3 ON es3.crawl_event_id = ce3.id
                            JOIN crawl_results cr3 ON ce3.crawl_result_id = cr3.id
                            WHERE es3.event_id = e.id
                              AND cr3.processed_at IS NOT NULL
                        ), '1970-01-01')
                  ) >= 2
                  -- ... AND the extractor didn't recently reject this event as
                  -- start_too_future (beyond FUTURE_WINDOW_DAYS = still on the page,
                  -- just too far out to re-link; treat as present, don't archive)
                  AND NOT EXISTS (
                      SELECT 1
                      FROM extraction_rejections er
                      WHERE er.website_id = %s
                        AND er.rejection_type = 'start_too_future'
                        AND er.created_at >= DATE_SUB(NOW(), INTERVAL 14 DAY)
                        AND er.event_name = e.name
                  )
              )
          )
    """
    archive_params = (website_id, website_id, website_id)

    # First, identify events that will be archived to check for upcoming ones
    cursor.execute(f"""
        SELECT e.id, e.name,
               (SELECT MIN(eo.start_date)
                FROM event_occurrences eo
                WHERE eo.event_id = e.id
                  AND eo.start_date >= CURDATE()) as next_occurrence
        FROM events e
        WHERE {archive_where}
    """, archive_params)

    events_to_archive = cursor.fetchall()
    upcoming_events = [(event_id, name, next_occ) for event_id, name, next_occ in events_to_archive if next_occ]

    # Perform the actual archiving by filtering on the id set the SELECT already
    # materialized, instead of re-evaluating the heavy correlated-subquery
    # archive_where a second time. This relies on the candidate set being stable
    # between the SELECT and the UPDATE: they run back-to-back on a single
    # connection with no intervening commit, and the merge tail holds the
    # advisory write_lock during archival (CLAUDE.md forbids concurrent
    # pipelines), so no concurrent writer can flip an event into or out of the
    # archive-qualifying set underneath us.
    ids = [r[0] for r in events_to_archive]
    archived_count = 0
    if ids:
        # Chunk the IN-list to stay under max_allowed_packet on large candidate sets.
        for start in range(0, len(ids), 1000):
            chunk = ids[start:start + 1000]
            placeholders = ','.join(['%s'] * len(chunk))
            cursor.execute(
                f"UPDATE events SET archived = TRUE WHERE id IN ({placeholders})",
                chunk
            )
            archived_count += cursor.rowcount

    connection.commit()

    if not temps_built:
        drop_archival_temps(cursor)

    return archived_count, upcoming_events


def archive_dead_source_events(cursor, connection, temps_built=False):
    """Archive events whose every source website is disabled ("no live source").

    `archive_outdated_events` is driven by the website that was just crawled: its
    first condition is "this event has a source from website X". An event whose
    only sources are disabled websites therefore never becomes a candidate —
    disabled websites are never crawled, so no loop iteration ever runs for them.
    Excluding disabled websites from _ws_latest (see build_archival_temps) fixes
    the *multi-source* case (an enabled sibling website can now archive the
    event), but an event with no enabled source at all needs this sweep, which is
    keyed on the event rather than on a website.

    Semantics, deliberately conservative:
    - Requires >= 1 event_sources row backed by a successful crawl. Events with
      NO event_sources rows at all are also permanently unarchivable (the same
      "has a source from website X" condition can never hold), but they are a
      different population — 720 non-archived events today, mostly events whose
      crawl history was pruned rather than events nobody lists any more — and
      archiving them is not this function's call to make. They are left alone.
    - Keeps the 14-day grace for events with a current/future occurrence, using
      the most recent supporting crawl from ANY source (the same rule as
      archive_outdated_events). A website disabled today therefore keeps its
      upcoming events for two more weeks, which is what makes a temporary
      disable-then-re-enable safe: the merger un-archives on re-match anyway.
    - The other two future-event guards do not apply: the fresh-crawl count is
      defined relative to a website that is still being crawled, and a
      start_too_future rejection can only be recorded by a website that is still
      being extracted. Neither can ever occur for a dead source.

    Returns (archived_count, upcoming_events) like archive_outdated_events.
    """
    if not temps_built:
        build_archival_temps(cursor)

    # Per-event source state, materialised once: how many of an event's source
    # websites are still enabled, whether any crawl actually succeeded, and when
    # it last saw the event. Restricted to non-archived events so this stays a
    # small scan rather than a walk of all event_sources ever written.
    cursor.execute("DROP TEMPORARY TABLE IF EXISTS _evt_src_state")
    cursor.execute("""
        CREATE TEMPORARY TABLE _evt_src_state (
            event_id INT UNSIGNED PRIMARY KEY,
            live_sources INT,
            supported INT,
            last_support DATETIME(6)
        )
        SELECT es.event_id,
               SUM(CASE WHEN (w.disabled = FALSE OR w.disabled IS NULL) THEN 1 ELSE 0 END) AS live_sources,
               SUM(CASE WHEN cr.status IN ('processed', 'extracted')
                         AND cr.processed_at IS NOT NULL THEN 1 ELSE 0 END) AS supported,
               MAX(cr.processed_at) AS last_support
        FROM event_sources es
        JOIN events e ON e.id = es.event_id AND e.archived = FALSE
        JOIN crawl_events ce ON ce.id = es.crawl_event_id
        JOIN crawl_results cr ON cr.id = ce.crawl_result_id
        JOIN websites w ON w.id = cr.website_id
        GROUP BY es.event_id
    """)

    cursor.execute("""
        SELECT e.id, e.name,
               (SELECT MIN(eo.start_date)
                FROM event_occurrences eo
                WHERE eo.event_id = e.id
                  AND eo.start_date >= CURDATE()) AS next_occurrence
        FROM events e
        JOIN _evt_src_state s ON s.event_id = e.id
        WHERE e.archived = FALSE
          AND s.live_sources = 0
          AND s.supported > 0
          AND (
              NOT EXISTS (SELECT 1 FROM _evt_future f WHERE f.event_id = e.id)
              OR s.last_support < DATE_SUB(NOW(), INTERVAL 14 DAY)
          )
    """)
    events_to_archive = cursor.fetchall()
    upcoming_events = [(event_id, name, next_occ)
                       for event_id, name, next_occ in events_to_archive if next_occ]

    ids = [row[0] for row in events_to_archive]
    archived_count = 0
    for start in range(0, len(ids), 1000):
        chunk = ids[start:start + 1000]
        placeholders = ','.join(['%s'] * len(chunk))
        cursor.execute(
            f"UPDATE events SET archived = TRUE WHERE id IN ({placeholders})",
            chunk
        )
        archived_count += cursor.rowcount

    connection.commit()

    cursor.execute("DROP TEMPORARY TABLE IF EXISTS _evt_src_state")
    if not temps_built:
        drop_archival_temps(cursor)

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
    """Geotag names as a set of generic location names (lowercased).

    These are neighborhood/borough/region names that are too vague to be useful
    as event locations — events with these as their only location info should be
    detail-crawled to find the specific venue. Sourced from the city config
    (config/<FOMO_CITY>.yaml: geotags + generic_location_names), the single home
    for the region's place names.
    """
    import city_config
    names = {name.lower() for name in city_config.geotags()}
    # Add common city-level names not in geotags (from city config).
    names.update(city_config.generic_location_names())
    return names


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


def normalize_tag_key(name):
    """Normalize a tag/ancestor/root name to its lookup key (lowercase, no spaces).

    Single source of truth for the tag-key normalization that the tag pipeline
    repeats across db/processor/merger. The `name or ''` guard yields '' for
    None; callers that must distinguish a NULL name keep their own conditional.
    """
    return (name or '').lower().replace(' ', '')


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
        parent_name = _col(row, 'parent_name', 0)
        child_name = _col(row, 'child_name', 1)
        child_key = normalize_tag_key(child_name)
        all_children.add(child_key)
        all_parents.add(normalize_tag_key(parent_name))
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
            parent_key = normalize_tag_key(parent)
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
        normalize_tag_key(row[0]): row[1]
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
        ctx_name = normalize_tag_key(row[1]) if row[1] else None
        target_name = row[2]
        priority = row[3]
        rules.setdefault(alias, []).append({
            'ctx_name': ctx_name,
            'target_name': target_name,
            'priority': priority,
        })
    return rules


def upsert_event_tags(cursor, event_id, tag_names, replace=False):
    """Set tags for an event. If replace=True, deletes existing tags first.

    Pairs in event_tag_blocks are never (re-)inserted — a judged audit removed
    them as mis-applied, and that decision is binding across re-crawls."""
    cursor.execute("SELECT tag_id FROM event_tag_blocks WHERE event_id = %s", (event_id,))
    blocked = {row[0] for row in cursor.fetchall()}
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
        if tag_id in blocked:
            continue
        cursor.execute(
            "INSERT IGNORE INTO event_tags (event_id, tag_id) VALUES (%s, %s)",
            (event_id, tag_id)
        )


def is_country_flag_emoji(s):
    """True if s is composed solely of regional-indicator symbols (U+1F1E6–
    U+1F1FF), i.e. a country-flag emoji. These have no glyphs in Windows' system
    emoji font, so the frontend swaps them for `alt_emoji` (Utils.resolveDisplayEmoji).
    Mirrors the JS `isCountryFlagEmoji`."""
    if not s or len(s) < 2:
        return False
    return all(0x1F1E6 <= ord(ch) <= 0x1F1FF for ch in s)


def get_tag_hierarchy_for_export(cursor):
    """Get tag hierarchy data formatted for JSON export.

    Returns (tags_list, keywords_list) where:
      - tags_list: list of dicts with name, parents, and optional emoji/quickFilter/order
      - keywords_list: list of keyword tag names
    """
    # Get all tags with type='tag' and their parents
    cursor.execute("""
        SELECT t.id, t.name, t.emoji, t.is_quick_filter, t.display_order, t.alt_emoji
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
        parent_name = _col(row, 'parent_name', 0)
        child_name = _col(row, 'child_name', 1)
        parents_of.setdefault(child_name, []).append(parent_name)

    # Build tags list
    tags_list = []
    for row in tag_rows:
        name = _col(row, 'name', 1)
        emoji = _col(row, 'emoji', 2)
        is_quick_filter = _col(row, 'is_quick_filter', 3)
        display_order = _col(row, 'display_order', 4)
        alt_emoji = _col(row, 'alt_emoji', 5)

        entry = {'name': name}
        parents = parents_of.get(name, [])
        entry['parents'] = sorted(parents)
        if emoji:
            entry['emoji'] = emoji
        # alt_emoji is only a Windows fallback for flag emoji (which render as
        # letter boxes there) — pointless to ship otherwise.
        if alt_emoji and is_country_flag_emoji(emoji):
            entry['alt_emoji'] = alt_emoji
        if is_quick_filter:
            entry['quickFilter'] = True
        if display_order is not None:
            entry['order'] = display_order
        tags_list.append(entry)

    return tags_list

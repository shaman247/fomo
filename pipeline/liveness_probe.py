#!/usr/bin/env python3
"""
Dead-link liveness probe for events sitting in the archival grace window.

Why this exists
---------------
`db.archive_outdated_events` deliberately waits before archiving an event that
still has future dates: a 14-day grace, >= 2 fresh crawls that miss it, and no
source website whose latest crawl still references it. Those guards defend
against rotating calendars and extraction misses, but they also mean that when
a site *unpublishes* an event mid-run (parks.ny.gov, 2026-09-10: "NY State
Parks Shark Shack" vanished from the listing and its detail page began
answering 403 "Oops, lost your way?") the map keeps showing a dead link for the
rest of the event's run — and a stale sibling source on a 20-day cadence can
block archival for longer still.

A gone detail page is stronger evidence than a missed listing, so this step
turns that into a fast path: for every event the grace period is currently
holding open, fetch its own URL(s) through the crawl browser and archive it
immediately when every URL is confirmed dead.

What "in the grace window" means here
-------------------------------------
Active, not suppressed, with a current/future occurrence, and some ENABLED
source website has completed a crawl *after* the event was last confirmed by
ANY source and did not list it. A fresher confirmation from any website wins
(the event is not a candidate). Websites whose absence carries no evidence
(Instagram-only, `rotating_listing`; see `db.build_archival_temps`) and
websites flagged `skip_reenrichment` (detail pages known uncrawlable) never
count as the "dropper".

Verdicts
--------
Per URL: `dead` on HTTP 404/410, on a not-found page signature in the title
(any status — parks.ny.gov serves its tombstone as 403), on a soft-404 body
(`crawler._is_soft_404`), or on a redirect to the site root. `unknown` on a bot
challenge, a 401/403/429/5xx without a tombstone title, a timeout or fetch
error. Everything else is `alive`. Instagram/Facebook URLs are never probed.

An event is archived only when EVERY probed URL is dead AND the website's
control fetch passed.

Control fetch
-------------
A bot wall can answer every path identically (parks.ny.gov 403s curl for live
pages too; queenslibrary.org returns 200 "Request Rejected" for everything —
see the link-rot audit notes). So before any dead verdict for a website is
trusted, one URL that the same website's LATEST crawl lists for a still-active
event is fetched with the same browser settings. If that control does not come
back `alive`, the website is treated as walled for this run and its dead
verdicts are downgraded to `unknown`. No control URL available = no archival.

Budget
------
Bounded on purpose: at most MAX_EVENTS_PER_RUN events per run (soonest next
occurrence first), REPROBE_INTERVAL_DAYS between probes of the same event, a
concurrency cap and a wall-clock budget, so a walled or slow host cannot turn
the publish tail into a multi-hour step.

Usage
-----
Called from `main.run_publish_tail` right after the merge (the candidate set
depends on event_sources rows the merge just wrote, and archival must happen
under the publish lock). Standalone:

    ./venv/bin/python pipeline/liveness_probe.py --dry-run     # report only
    ./venv/bin/python pipeline/liveness_probe.py                # probe + archive
    ./venv/bin/python pipeline/liveness_probe.py --event-ids 1,2 --dry-run
"""

import argparse
import asyncio
import concurrent.futures
import sys
import time
from urllib.parse import urlparse

import db
import crawler

try:
    sys.path.insert(0, str(__import__('pathlib').Path(__file__).resolve().parent.parent / 'database'))
    from edit_logger import EditLogger
except ImportError:  # pragma: no cover
    EditLogger = None


MAX_EVENTS_PER_RUN = 100
MAX_EVENTS_PER_WEBSITE = 10  # one high-churn calendar must not starve the rest
MAX_URLS_PER_EVENT = 3
REPROBE_INTERVAL_DAYS = 7
CONCURRENCY = 8
FETCH_TIMEOUT = 60           # per-URL ceiling (seconds)
TIME_BUDGET = 900            # stop launching new fetches after this many seconds
SOFT_404_MAX_CHARS = 8000    # a tombstone page is short; real detail pages can be too,
                             # which is why a title marker is also required for 200s

# Title fragments that name a "this page is gone" template. Matched on the
# rendered <title> only (lower-cased), never on the body, so an event that
# merely mentions "not found" in its description cannot trip it. Deliberately
# generic — the mechanism is site-agnostic; a new tombstone phrasing is one
# entry here, the same way crawler.SOFT_404_MARKERS grows.
NOT_FOUND_TITLE_MARKERS = (
    "page not found",
    "not found",
    "lost your way",
    "404",
    "doesn't exist",
    "does not exist",
    "no longer available",
    "no longer exists",
    "page unavailable",
    "cannot be found",
    "can't be found",
    "page missing",
)

# Hosts whose pages are walled to any automated client; probing them can only
# ever return `unknown`, so skip the fetch.
NEVER_PROBE_HOSTS = ("instagram.com", "facebook.com", "fb.com")

_APOSTROPHES = str.maketrans({'’': "'", '‘': "'", 'ʼ': "'", '´': "'"})


# ── Candidate selection ─────────────────────────────────────────────────────

def _build_latest_merged_temps(cursor):
    """Per enabled, evidence-bearing website: its latest crawl_result that has
    actually been MERGED, plus the set of event URLs that crawl listed.

    `db.build_archival_temps` keys on processed_at, which is right for the
    archival pass (it runs after the merge that links those rows) but wrong for
    a probe that can run standalone while another session's pipeline sits
    between Step 4 and the merge: a processed-but-unmerged crawl has no
    event_sources rows yet, so EVERY event it lists looks dropped (measured
    2026-09-10: 882 unmerged crawl_events on w4 made 150 live BPL events look
    like candidates). `merged_at` is stamped at the end of merge_crawl_events,
    so keying on it means "the newest crawl whose absences are real".
    """
    cursor.execute("DROP TEMPORARY TABLE IF EXISTS _lp_latest")
    cursor.execute("""
        CREATE TEMPORARY TABLE _lp_latest (website_id INT UNSIGNED PRIMARY KEY, cr_id INT, latest DATETIME(6))
        SELECT cr.website_id, MAX(cr.id) AS cr_id, MAX(cr.processed_at) AS latest
        FROM crawl_results cr
        JOIN websites w ON w.id = cr.website_id
        LEFT JOIN _ws_no_absence_evidence nae ON nae.website_id = w.id
        WHERE cr.status IN ('processed', 'extracted')
          AND cr.processed_at IS NOT NULL
          AND cr.merged_at IS NOT NULL
          AND (w.disabled = FALSE OR w.disabled IS NULL)
          AND COALESCE(w.skip_reenrichment, 0) = 0
          AND nae.website_id IS NULL
        GROUP BY cr.website_id
    """)
    cursor.execute("DROP TEMPORARY TABLE IF EXISTS _lp_listed")
    cursor.execute("""
        CREATE TEMPORARY TABLE _lp_listed (website_id INT UNSIGNED, url VARCHAR(2000), INDEX (website_id, url(191)))
        SELECT l.website_id, ce.url
        FROM _lp_latest l
        JOIN crawl_events ce ON ce.crawl_result_id = l.cr_id
        WHERE ce.url IS NOT NULL AND ce.url != ''
    """)


def _drop_latest_merged_temps(cursor):
    cursor.execute("DROP TEMPORARY TABLE IF EXISTS _lp_latest")
    cursor.execute("DROP TEMPORARY TABLE IF EXISTS _lp_listed")


def get_candidates(cursor, event_ids=None, limit=MAX_EVENTS_PER_RUN, per_website=MAX_EVENTS_PER_WEBSITE):
    """Events the archival grace period is holding open, with their URLs.

    Returns a list of dicts: {event_id, name, website_id, next_occ, last_seen,
    dropper_latest, urls: [str, ...], still_listed: bool}. `website_id` is the
    enabled source whose latest merged crawl most recently missed the event;
    its browser settings are used for the probe and its latest crawl supplies
    the control URL. `still_listed` is True when that crawl DID list one of
    the event's URLs (under some other event row — a split series, a re-slug
    twin): the site has not dropped the page, so no fetch is needed and the
    verdict is `alive`.

    Builds and drops its temp tables itself (connection-scoped TEMPORARY
    tables; the merge tail has already dropped its own copy by the time this
    runs). Selection is round-robin across websites — soonest next occurrence
    first within a website, at most `per_website` per website — so one
    high-churn calendar cannot consume the whole budget.
    """
    db.build_archival_temps(cursor)
    _build_latest_merged_temps(cursor)
    try:
        # An explicit id list is a manual "probe these now": it bypasses the
        # grace-window test (d.latest > last_seen) and the re-probe interval,
        # but still requires a future occurrence, an evidence-bearing source
        # website (for browser settings + control URL), and active status.
        id_filter = ""
        params = []
        window_clause = "AND d.latest > lc.last_seen"
        reprobe_clause = """AND NOT EXISTS (
                  SELECT 1 FROM event_liveness_probes p
                  WHERE p.event_id = e.id
                    AND p.probed_at >= DATE_SUB(NOW(), INTERVAL %s DAY)
              )"""
        reprobe_params = [REPROBE_INTERVAL_DAYS]
        if event_ids:
            id_filter = f"AND e.id IN ({','.join(['%s'] * len(event_ids))})"
            params.extend(event_ids)
            window_clause = ""
            reprobe_clause = ""
            reprobe_params = []

        cursor.execute(f"""
            SELECT e.id, e.name,
                   lc.last_seen,
                   d.website_id, d.latest,
                   nxt.next_occ,
                   EXISTS (
                       SELECT 1 FROM event_urls eu
                       JOIN _lp_listed ll ON ll.website_id = d.website_id AND ll.url = eu.url
                       WHERE eu.event_id = e.id
                   ) AS still_listed
            FROM events e
            JOIN _evt_future f ON f.event_id = e.id
            JOIN (
                SELECT es.event_id, MAX(cr.processed_at) AS last_seen
                FROM event_sources es
                JOIN crawl_events ce ON ce.id = es.crawl_event_id
                JOIN crawl_results cr ON cr.id = ce.crawl_result_id
                WHERE cr.processed_at IS NOT NULL
                GROUP BY es.event_id
            ) lc ON lc.event_id = e.id
            JOIN (
                -- For each event, the evidence-bearing source website whose latest
                -- MERGED crawl is newest; a candidate only if that crawl is newer
                -- than the event's last confirmation anywhere (checked below).
                SELECT es.event_id, cr.website_id, l.latest,
                       ROW_NUMBER() OVER (PARTITION BY es.event_id ORDER BY l.latest DESC) AS rn
                FROM event_sources es
                JOIN crawl_events ce ON ce.id = es.crawl_event_id
                JOIN crawl_results cr ON cr.id = ce.crawl_result_id
                JOIN _lp_latest l ON l.website_id = cr.website_id
                GROUP BY es.event_id, cr.website_id, l.latest
            ) d ON d.event_id = e.id AND d.rn = 1
            LEFT JOIN (
                SELECT event_id, MIN(start_date) AS next_occ
                FROM event_occurrences
                WHERE start_date >= CURDATE()
                GROUP BY event_id
            ) nxt ON nxt.event_id = e.id
            WHERE e.archived = 0 AND e.suppressed = 0
              {window_clause}
              {reprobe_clause}
              {id_filter}
            ORDER BY nxt.next_occ IS NULL, nxt.next_occ, e.id
        """, reprobe_params + params)
        rows = cursor.fetchall()
    finally:
        _drop_latest_merged_temps(cursor)
        db.drop_archival_temps(cursor)

    if not rows:
        return []

    by_id = {}
    for eid, name, last_seen, ws_id, latest, next_occ, still_listed in rows:
        by_id[eid] = {
            'event_id': eid, 'name': name, 'website_id': ws_id,
            'last_seen': last_seen, 'dropper_latest': latest,
            'next_occ': next_occ, 'urls': [], 'still_listed': bool(still_listed),
        }
    for start in range(0, len(by_id), 1000):
        chunk = list(by_id.keys())[start:start + 1000]
        ph = ','.join(['%s'] * len(chunk))
        cursor.execute(
            f"SELECT event_id, url FROM event_urls WHERE event_id IN ({ph}) ORDER BY event_id, sort_order, id",
            chunk)
        for eid, url in cursor.fetchall():
            urls = by_id[eid]['urls']
            if url and _probeable(url) and url not in urls and len(urls) < MAX_URLS_PER_EVENT:
                urls.append(url)
    # A past dated-instance URL is only evidence together with its series page.
    for c in by_id.values():
        for u in list(c['urls']):
            parent = _series_parent(u)
            if parent and parent not in c['urls']:
                c['urls'].append(parent)

    # Round-robin across websites (rows are already soonest-first per website)
    # under a per-website cap, then the global cap. Still-listed events are
    # free (no fetch), so they do not count against either budget.
    per_site = {}
    free, queued = [], {}
    for c in by_id.values():
        if not c['urls']:
            continue
        if c['still_listed'] and not event_ids:
            free.append(c)
            continue
        c['still_listed'] = c['still_listed'] and not event_ids
        if per_site.get(c['website_id'], 0) >= per_website:
            continue
        per_site[c['website_id']] = per_site.get(c['website_id'], 0) + 1
        queued.setdefault(c['website_id'], []).append(c)
    picked = []
    while queued and len(picked) < limit:
        for ws_id in list(queued):
            if len(picked) >= limit:
                break
            picked.append(queued[ws_id].pop(0))
            if not queued[ws_id]:
                del queued[ws_id]
    return free + picked


_DATE_SEGMENT = __import__('re').compile(r'^\d{4}-\d{2}-\d{2}$')


def _series_parent(url, today=None):
    """For a dated-instance URL (Tribe/The Events Calendar style
    `/event/<slug>/2026-08-27/`) whose date is in the PAST, the undated series
    URL. A past instance page 404s as a matter of course once the date goes by,
    while the series may still be running — so the event is only dead if the
    series page is dead too. Returns None for any other URL shape.
    """
    import datetime
    parts = urlparse(url)
    segs = [x for x in parts.path.split('/') if x]
    if len(segs) < 2 or not _DATE_SEGMENT.match(segs[-1]):
        return None
    try:
        d = datetime.date.fromisoformat(segs[-1])
    except ValueError:
        return None
    if d >= (today or datetime.date.today()):
        return None
    return parts._replace(path='/' + '/'.join(segs[:-1]) + '/', query='', fragment='').geturl()


def _probeable(url):
    host = (urlparse(url).hostname or '').lower()
    return url.lower().startswith(('http://', 'https://')) and \
        not any(host == h or host.endswith('.' + h) for h in NEVER_PROBE_HOSTS)


def get_control_urls(cursor, website_ids, exclude_urls):
    """One known-live URL per website: an event URL from the website's LATEST
    processed crawl that is linked to a still-active event. Returns
    {website_id: url}; a website with no such URL is absent (=> never trusted).
    """
    controls = {}
    for ws_id in website_ids:
        cursor.execute("""
            SELECT ce.url
            FROM crawl_results cr
            JOIN crawl_events ce ON ce.crawl_result_id = cr.id
            JOIN event_sources es ON es.crawl_event_id = ce.id
            JOIN events e ON e.id = es.event_id
            WHERE cr.website_id = %s
              AND cr.id = (
                  SELECT MAX(cr2.id) FROM crawl_results cr2
                  WHERE cr2.website_id = %s AND cr2.status IN ('processed', 'extracted')
                    AND cr2.merged_at IS NOT NULL
              )
              AND e.archived = 0 AND e.suppressed = 0
              AND ce.url IS NOT NULL AND ce.url != ''
            ORDER BY ce.id DESC
            LIMIT 40
        """, (ws_id, ws_id))
        for (url,) in cursor.fetchall():
            if url in exclude_urls or not _probeable(url):
                continue
            # A listing URL (shared crawl target) is not a detail page; skip
            # anything that is one of the website's own crawl URLs.
            controls[ws_id] = url
            break
    if controls:
        ph = ','.join(['%s'] * len(controls))
        cursor.execute(
            f"SELECT website_id, url FROM website_urls WHERE website_id IN ({ph})",
            list(controls.keys()))
        listing = {}
        for ws_id, url in cursor.fetchall():
            listing.setdefault(ws_id, set()).add(url)
        for ws_id in list(controls):
            if controls[ws_id] in listing.get(ws_id, ()):
                del controls[ws_id]
    return controls


# ── Fetch + classify ────────────────────────────────────────────────────────

def classify(result_url, status, title, content, redirected_url, error=None):
    """Return (verdict, reason) for one fetched page. Pure; unit-testable."""
    if error:
        return 'unknown', f'fetch error: {error}'[:200]
    if status in (404, 410):
        return 'dead', f'http {status}'
    lowered_title = (title or '').lower().translate(_APOSTROPHES)
    title_hit = next((m for m in NOT_FOUND_TITLE_MARKERS if m in lowered_title), None)
    if content and crawler._is_bot_challenge(content):
        return 'unknown', 'bot challenge'
    if title_hit and (status is None or status >= 400 or len(content or '') <= SOFT_404_MAX_CHARS):
        return 'dead', f'not-found title "{title_hit}" (http {status})'
    if content and crawler._is_soft_404(content):
        return 'dead', 'soft-404 body'
    if redirected_url and redirected_url != result_url:
        src, dst = urlparse(result_url), urlparse(redirected_url)
        if src.netloc.lower() == dst.netloc.lower() and dst.path.strip('/') == '' and src.path.strip('/') != '':
            return 'dead', 'redirected to site root'
    if status is not None and (status in (401, 403, 429) or status >= 500):
        return 'unknown', f'http {status} without tombstone'
    if not content or len(content) <= crawler.MIN_EVENT_PAGE_SIZE:
        return 'unknown', 'empty body'
    return 'alive', f'http {status}'


async def _fetch(web_crawler, url, crawl_config):
    try:
        result = await asyncio.wait_for(
            web_crawler.arun(url=url, config=crawl_config), timeout=FETCH_TIMEOUT)
    except asyncio.TimeoutError:
        return {'url': url, 'error': f'timeout after {FETCH_TIMEOUT}s'}
    except Exception as e:
        return {'url': url, 'error': f'{type(e).__name__}: {e}'}
    content = ''
    if result.markdown:
        content = result.markdown.raw_markdown or result.markdown.fit_markdown or ''
    title = (result.metadata or {}).get('title') if isinstance(result.metadata, dict) else None
    return {
        'url': url,
        'status': result.status_code,
        'title': (title or '').strip()[:500],
        'content': content,
        'redirected_url': result.redirected_url,
        'error': None if result.success or result.status_code else (result.error_message or 'fetch failed')[:200],
    }


async def probe_urls(plan):
    """plan: {website_id: {'settings': {...}, 'urls': [..]}} → {url: fetch dict}.

    Network only — no DB access, so it can run on a private event loop in a
    worker thread when the caller is already inside a running loop.
    """
    from processor import managed_crawler
    out = {}
    started = time.monotonic()
    sem = asyncio.Semaphore(CONCURRENCY)

    batches = {}
    for ws_id, item in plan.items():
        key = crawler.get_browser_key(item['settings'])
        batches.setdefault(key, []).append(ws_id)

    for (text_mode, light_mode, use_stealth, headed, user_agent), ws_ids in batches.items():
        urls = [(ws_id, u) for ws_id in ws_ids for u in plan[ws_id]['urls']]
        if not urls:
            continue
        browser_config = crawler.get_browser_config(
            text_mode=text_mode, light_mode=light_mode,
            use_stealth=use_stealth, headed=headed, user_agent=user_agent)

        async def one(ws_id, url):
            async with sem:
                if time.monotonic() - started > TIME_BUDGET:
                    out[url] = {'url': url, 'error': 'time budget exhausted'}
                    return
                cfg = crawler.build_event_crawl_config(plan[ws_id]['settings'])
                out[url] = await _fetch(web_crawler, url, cfg)

        try:
            async with managed_crawler(browser_config) as web_crawler:
                await asyncio.gather(*(one(w, u) for w, u in urls), return_exceptions=True)
        except Exception as e:
            print(f"    ⚠️ probe browser batch failed ({type(e).__name__}: {e}); skipping batch")
            for _, u in urls:
                out.setdefault(u, {'url': u, 'error': f'browser batch failed: {type(e).__name__}'})
    return out


def _run_coro(coro):
    """Run a coroutine whether or not the caller already sits inside a loop.

    `run_publish_tail` is a sync function executed from within the async
    `run_pipeline`, where the loop is running but not awaiting us; asyncio.run
    would refuse. A one-off worker thread with its own loop sidesteps that.
    The coroutine touches no DB objects, so nothing is shared across threads.
    """
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
        return ex.submit(asyncio.run, coro).result()


# ── Orchestration ───────────────────────────────────────────────────────────

def run(cursor, connection, event_ids=None, limit=MAX_EVENTS_PER_RUN, dry_run=False, verbose=True,
        write_lock=None):
    """Probe grace-window events and archive the confirmed-dead ones.

    `write_lock`: optional zero-arg factory returning a context manager that
    holds the shared DB write lock. The publish tail already holds it and
    passes None; the standalone CLI passes `dblock.write_lock(...)` so the lock
    covers ONLY the write phase — the network phase can take minutes and must
    not block another session's merge (measured 2026-09-10: a standalone
    apply held the lock for the whole fetch while another run was mid-Step 5).

    Returns a stats dict: {candidates, probed, archived, dead, alive, unknown,
    walled_websites, archived_events: [(id, name, reason)]}.
    """
    stats = {'candidates': 0, 'probed': 0, 'archived': 0, 'dead': 0, 'alive': 0,
             'unknown': 0, 'walled_websites': [], 'archived_events': []}

    candidates = get_candidates(cursor, event_ids=event_ids, limit=limit)
    stats['candidates'] = len(candidates)
    if not candidates:
        if verbose:
            print("  No grace-window events to probe")
        return stats

    website_ids = sorted({c['website_id'] for c in candidates if not c['still_listed']})
    settings = db.get_website_crawl_settings(cursor, website_ids)
    candidate_urls = {u for c in candidates for u in c['urls']}
    controls = get_control_urls(cursor, website_ids, candidate_urls)

    plan = {}
    for c in candidates:
        if c['still_listed']:
            continue
        entry = plan.setdefault(c['website_id'], {'settings': settings.get(c['website_id'], {}), 'urls': []})
        for u in c['urls']:
            if u not in entry['urls']:
                entry['urls'].append(u)
    for ws_id, url in controls.items():
        entry = plan.setdefault(ws_id, {'settings': settings.get(ws_id, {}), 'urls': []})
        if url not in entry['urls']:
            entry['urls'].append(url)

    total_urls = sum(len(p['urls']) for p in plan.values())
    if verbose:
        print(f"  Probing {len(candidates)} grace-window event(s), {total_urls} URL(s) "
              f"across {len(plan)} website(s) ({len(controls)} control fetches)...")

    fetched = _run_coro(probe_urls(plan)) if plan else {}
    stats['probed'] = len(fetched)

    verdicts = {}
    for url, f in fetched.items():
        verdicts[url] = classify(url, f.get('status'), f.get('title'), f.get('content'),
                                 f.get('redirected_url'), f.get('error'))

    # Control gate: a website whose known-live page did not come back alive is
    # walled for this run — none of its dead verdicts can be trusted.
    walled = set()
    for ws_id in website_ids:
        ctl = controls.get(ws_id)
        if not ctl:
            walled.add(ws_id)
            if verbose:
                print(f"    w{ws_id}: no control URL available - dead verdicts not trusted")
            continue
        v, reason = verdicts.get(ctl, ('unknown', 'not fetched'))
        if v != 'alive':
            walled.add(ws_id)
            if verbose:
                print(f"    w{ws_id}: control {ctl} -> {v} ({reason}) - treating site as walled")
    stats['walled_websites'] = sorted(walled)

    import contextlib
    with (write_lock() if (write_lock and not dry_run) else contextlib.nullcontext()):
        return _apply_verdicts(cursor, connection, candidates, fetched, verdicts, walled, stats,
                               dry_run=dry_run, verbose=verbose)


def _apply_verdicts(cursor, connection, candidates, fetched, verdicts, walled, stats, dry_run, verbose):
    """Write phase: probe rows + archival. Caller holds the write lock (unless dry run)."""
    edit_logger = None
    if EditLogger and not dry_run:
        edit_logger = EditLogger(cursor, connection, source='crawl', editor_info='liveness_probe')

    to_archive = []
    still_listed = [c for c in candidates if c['still_listed']]
    if still_listed and verbose:
        print(f"    {len(still_listed)} event(s) still listed by the site under another row - alive without a fetch")
    for c in candidates:
        ws_id = c['website_id']
        if c['still_listed']:
            per_url = [(u, 'alive', 'still listed in latest crawl') for u in c['urls']]
        else:
            per_url = [(u, *verdicts.get(u, ('unknown', 'not fetched'))) for u in c['urls']]
        all_dead = all(v == 'dead' for _, v, _ in per_url)
        any_alive = any(v == 'alive' for _, v, _ in per_url)
        event_verdict = 'dead' if all_dead else ('alive' if any_alive else 'unknown')
        if event_verdict == 'dead' and ws_id in walled:
            event_verdict = 'unknown'
            per_url = [(u, 'unknown', f'walled site; was: {r}') for u, v, r in per_url]
        stats[event_verdict] += 1

        if verbose:
            nxt = c['next_occ'].isoformat() if c['next_occ'] else '-'
            print(f"    [{event_verdict:7}] event {c['event_id']} \"{c['name'][:60]}\" (next {nxt}, w{ws_id})")
            for u, v, r in per_url:
                f = fetched.get(u, {})
                t = f" title={f.get('title')!r}" if f.get('title') else ''
                print(f"              {v:7} {u}  [{r}{t}]")

        if not dry_run:
            for u, v, r in per_url:
                f = fetched.get(u, {})
                cursor.execute("""
                    INSERT INTO event_liveness_probes
                        (event_id, website_id, url, verdict, http_status, page_title, reason, archived)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """, (c['event_id'], ws_id, u[:2000], v, f.get('status'),
                      (f.get('title') or None), r[:200], 1 if event_verdict == 'dead' else 0))
        if event_verdict == 'dead':
            to_archive.append(c)

    if to_archive and not dry_run:
        for c in to_archive:
            cursor.execute("UPDATE events SET archived = TRUE WHERE id = %s AND archived = FALSE", (c['event_id'],))
            if cursor.rowcount:
                stats['archived'] += 1
                stats['archived_events'].append((c['event_id'], c['name'], 'all URLs dead'))
                if edit_logger:
                    edit_logger.log_update('events', c['event_id'], 'archived', False, True)
        connection.commit()
    elif to_archive:
        stats['archived_events'] = [(c['event_id'], c['name'], 'all URLs dead (dry run)') for c in to_archive]
    elif not dry_run:
        connection.commit()

    if verbose:
        print(f"  Liveness probe: {stats['dead']} dead, {stats['alive']} alive, {stats['unknown']} unknown"
              f"{' (dry run)' if dry_run else ''}; archived {stats['archived']}")
        if walled:
            print(f"    walled/untrusted websites this run: {', '.join('w%d' % w for w in sorted(walled))}")
    return stats


def main():
    parser = argparse.ArgumentParser(description='Probe grace-window events for dead links and archive them')
    parser.add_argument('--dry-run', action='store_true', help='Report verdicts; write nothing')
    parser.add_argument('--event-ids', type=str, help='Comma-separated event ids to restrict to')
    parser.add_argument('--limit', type=int, default=MAX_EVENTS_PER_RUN)
    args = parser.parse_args()
    event_ids = [int(x) for x in args.event_ids.split(',')] if args.event_ids else None

    import dblock
    connection = db.create_connection()
    if not connection:
        print("Failed to connect to database")
        return 1
    cursor = connection.cursor(buffered=True)
    try:
        stats = run(cursor, connection, event_ids=event_ids, limit=args.limit, dry_run=args.dry_run,
                    write_lock=lambda: dblock.write_lock(connection, label='liveness_probe'))
        for eid, name, reason in stats['archived_events']:
            print(f"  → {eid} {name}: {reason}")
        if stats['archived'] and not args.dry_run:
            print("\nArchived events are still in the last export; re-export and upload with:\n"
                  "  ./venv/bin/python pipeline/main.py --merge-only")
    finally:
        cursor.close()
        connection.close()
    return 0


if __name__ == '__main__':
    sys.exit(main())

"""
Event Processing Pipeline

Orchestrates the complete event processing workflow:

1. Crawl - Query websites table, crawl due sites, store in crawl_results
2. Extract - Use Gemini AI to extract structured event data
3. Process - Parse responses, enrich with location data, store in crawl_events
4. Detail Crawl - Crawl individual event URLs for missing descriptions
5. Merge - Deduplicate crawl_events into final events table
6. Export - Generate JSON files from events table for website
7. Upload - Push JSON files to FTP server

Usage:
    python main.py                     # Process all websites due for crawling
    python main.py --ids 941           # Process specific website ID(s)
    python main.py --ids 941,942,943   # Process multiple website IDs
    python main.py --limit 5           # Only crawl first 5 websites due
"""

import argparse
import asyncio
import os
import sys
import time
from datetime import datetime

# Force unbuffered stdout so pipeline progress is visible in real time,
# even when output is redirected to a file (line_buffering alone only works for TTYs)
if not os.environ.get('PYTHONUNBUFFERED'):
    sys.stdout.reconfigure(write_through=True)
    sys.stderr.reconfigure(write_through=True)

from crawl4ai import AsyncWebCrawler

import logging_utils
logging_utils.install()  # Prefix every log line with a timestamp for profiling

import db
import crawler
from crawler import get_browser_key
import extractor
import processor
import merger
import exporter
import uploader
import frequency_analyzer
import dblock

# Number of concurrent workers for crawling, extraction, and detail crawling
NUM_WORKERS = 10

# Publish-lock acquisition: each attempt blocks up to dblock.DEFAULT_TIMEOUT
# (600s); retry a few times before giving up so a busy-but-progressing
# concurrent session doesn't strand this run's merge.
PUBLISH_LOCK_ATTEMPTS = 3


def acquire_publish_lock(connection, attempts=PUBLISH_LOCK_ATTEMPTS,
                         timeout=dblock.DEFAULT_TIMEOUT):
    """Acquire the advisory write lock for the merge→export→upload tail.

    Blocks up to `timeout` seconds per attempt, `attempts` times, printing who
    holds the lock between attempts. The lock is MySQL-connection-scoped, so
    closing `connection` releases it on every exit path. Returns True/False.
    """
    lock_cur = connection.cursor()
    for attempt in range(1, attempts + 1):
        lock_cur.execute("SELECT GET_LOCK(%s, %s)", (dblock.LOCK_NAME, timeout))
        if (lock_cur.fetchone() or [0])[0] == 1:
            try:
                dblock._set_holder(connection, dblock.LOCK_NAME, "run_pipeline")
            except Exception:
                pass
            lock_cur.close()
            return True
        holder = dblock.acquired_by(connection)
        more = "; retrying..." if attempt < attempts else ""
        print(f"  Write lock busy (held by {holder or 'another session'}) — "
              f"attempt {attempt}/{attempts} timed out after {timeout}s{more}")
    lock_cur.close()
    return False


def _merge_only_hint(website_ids):
    """The recovery command to print when the merge tail couldn't run."""
    ids_arg = f" --ids {','.join(map(str, website_ids))}" if website_ids else ""
    return f"python pipeline/main.py --merge-only{ids_arg}"


async def run_pipeline(website_ids=None, limit=None, use_batch=None):
    """Execute the complete event processing pipeline.

    Args:
        website_ids: Optional list of website IDs to process. If None, processes
                     all websites due for crawling based on crawl_frequency.
        limit: Optional maximum number of websites to crawl.
        use_batch: If True, use Gemini Batch API for extraction (50% cheaper).
                   If None, defaults to False (sync API).
    """
    timer = logging_utils.StepTimer()

    def step(title):
        """Print a step header, reporting how long the previous step took."""
        result = timer.stop()
        if result is not None:
            name, elapsed = result
            print(f"  {name} took {logging_utils.format_duration(elapsed)}")
        print(f"\n{'='*60}")
        print(title)
        print(f"{'='*60}")
        timer.start(title)

    print(f"{'='*60}")
    print(f"EVENT PROCESSING PIPELINE")
    if website_ids:
        print(f"  Filtering to website IDs: {', '.join(map(str, website_ids))}")
    print(f"{'='*60}\n")

    # Connect to database
    connection = db.create_connection()
    if not connection:
        print("Failed to connect to database")
        return False

    cursor = connection.cursor(buffered=True)

    try:
        # Check for incomplete crawl results first
        step("STEP 0: Checking for Incomplete Crawl Results")

        incomplete_results = db.get_incomplete_crawl_results(cursor, website_ids=website_ids)
        incomplete_crawled = [r for r in incomplete_results if r['status'] == 'crawled']
        incomplete_extracted = [r for r in incomplete_results if r['status'] == 'extracted']

        def print_incomplete_status(results, action_needed):
            """Print status summary for a list of incomplete results."""
            retry_count = sum(1 for r in results if r.get('original_status') == 'failed')
            batch_count = sum(1 for r in results if r.get('batch_job_name'))
            incomplete_count = len(results) - retry_count
            status_parts = []
            if incomplete_count:
                status_parts.append(f"{incomplete_count} incomplete")
            if retry_count:
                status_parts.append(f"{retry_count} failed retries")
            if batch_count:
                status_parts.append(f"{batch_count} with in-flight batch")
            print(f"  - {len(results)} need {action_needed} ({', '.join(status_parts)})")
            for r in results:
                suffix = " [retry]" if r.get('original_status') == 'failed' else ""
                if r.get('batch_job_name'):
                    suffix += " [batch pending]"
                print(f"      {r['name']} (run: {r['run_date']}){suffix}")

        if incomplete_results:
            print(f"Found {len(incomplete_results)} crawl result(s) to process:")
            if incomplete_crawled:
                print_incomplete_status(incomplete_crawled, "extraction")
            if incomplete_extracted:
                print_incomplete_status(incomplete_extracted, "processing")
        else:
            print("No incomplete crawl results found.")

        # Stranded merges: extraction/processing succeeded in a prior run but the
        # merge tail never ran (interrupted run or lost lock race). This run's
        # merge picks them up automatically — surfacing them here so a sudden
        # batch of "old" events in the merge isn't a surprise.
        stranded = db.get_stranded_merge_summary(cursor, website_ids=website_ids)
        if stranded:
            total_unmerged = sum(r[4] for r in stranded)
            print(f"  - {len(stranded)} processed crawl result(s) from prior runs still have "
                  f"{total_unmerged} unmerged event(s) — this run's merge will include them:")
            for cr_id, w_id, w_name, processed_at, n in stranded[:10]:
                print(f"      cr={cr_id} w={w_id} {w_name} (processed {processed_at}, {n} unmerged)")
            if len(stranded) > 10:
                print(f"      ... and {len(stranded) - 10} more")

        # STEP 1: Get websites due for crawling
        step("STEP 1: Finding Websites Due for Crawling")

        websites = db.get_websites_due_for_crawling(cursor, website_ids)
        if limit and len(websites) > limit:
            print(f"Found {len(websites)} website(s) due, limiting to {limit}")
            websites = websites[:limit]
        elif website_ids:
            print(f"Found {len(websites)} website(s) matching specified IDs")
        else:
            print(f"Found {len(websites)} website(s) due for crawling")

        # Check if there's any work to do
        has_work = len(websites) > 0 or len(incomplete_results) > 0

        if not has_work:
            print("\nNo websites need crawling and no incomplete results to process.")
            print("Pipeline completed (no work to do).")
            return True

        for w in websites:
            print(f"  - {w['name']} ({len(w['urls'])} URL(s))")

        # Create crawl run
        run_date = datetime.now().date()
        run_date_str = run_date.strftime('%Y%m%d')
        crawl_run_id = db.get_or_create_crawl_run(cursor, connection, run_date)
        print(f"\nCrawl run ID: {crawl_run_id} ({run_date_str})")

        # STEP 2: Crawl websites
        step("STEP 2: Crawling Websites")

        # Group websites by browser settings so each group shares a browser instance
        website_batches = {}
        for website in websites:
            key = get_browser_key(website)
            website_batches.setdefault(key, []).append(website)

        crawl_results = []

        for (text_mode, light_mode, use_stealth, headed, user_agent), batch_websites in website_batches.items():
            if len(website_batches) > 1:
                stealth_str = ", stealth=True" if use_stealth else ""
                headed_str = ", headed=True" if headed and not use_stealth else ""
                ua_str = f", user_agent=..." if user_agent else ""
                print(f"\n  Batch: text_mode={text_mode}, light_mode={light_mode}{stealth_str}{headed_str}{ua_str} ({len(batch_websites)} sites)")

            browser_config = crawler.get_browser_config(text_mode=text_mode, light_mode=light_mode, use_stealth=use_stealth, headed=headed, user_agent=user_agent)

            # Stall protection: a single wedged site can hang Playwright's shared
            # browser below the asyncio layer, where crawl_website's own
            # wait_for cannot cancel it — poisoning the browser so every queued
            # worker also hangs and gather() never returns. A heartbeat-driven
            # watchdog SIGKILLs the wedged browser on stall so the batch aborts
            # instead of hanging the whole pipeline. Workers append to a shared
            # list as they finish, so an abort keeps already-completed crawls.
            STALL_TIMEOUT = 300  # 5 minutes with zero progress => kill browser & abort batch
            heartbeat = {'last': time.monotonic()}
            batch_results = []

            try:
                async with processor.managed_crawler(browser_config) as web_crawler:
                    # Worker pool pattern: maintain N concurrent crawlers at all times
                    queue = asyncio.Queue()

                    # Fill the queue with batch websites
                    for website in batch_websites:
                        await queue.put(website)

                    async def worker():
                        """Worker that continuously pulls from queue until empty."""
                        while True:
                            try:
                                website = queue.get_nowait()
                            except asyncio.QueueEmpty:
                                break

                            conn = db.create_connection()
                            if not conn:
                                queue.task_done()
                                continue
                            cur = conn.cursor(buffered=True)
                            try:
                                result_id = await crawler.crawl_website(
                                    web_crawler, website, cur, conn, crawl_run_id
                                )
                                if result_id:
                                    batch_results.append((result_id, website))
                            except Exception as e:
                                print(f"    - Error crawling {website['name']}: {e}")
                            finally:
                                heartbeat['last'] = time.monotonic()
                                cur.close()
                                conn.close()
                                queue.task_done()

                    async def crawl_watchdog(gather_task):
                        """Kill the wedged browser if no crawl completes for STALL_TIMEOUT."""
                        while not gather_task.done():
                            await asyncio.sleep(30)
                            idle = time.monotonic() - heartbeat['last']
                            if idle > STALL_TIMEOUT and not gather_task.done():
                                print(
                                    f"  ⚠️ WATCHDOG: crawl stalled — no progress for "
                                    f"{int(idle)}s ({len(batch_results)}/{len(batch_websites)} done). "
                                    f"Killing wedged browser and aborting this batch."
                                )
                                gather_task.cancel()
                                processor._kill_crawl_browsers()
                                return

                    # Start N workers; a watchdog aborts the batch if the browser wedges
                    gather_task = asyncio.gather(*[worker() for _ in range(NUM_WORKERS)], return_exceptions=True)
                    watchdog_task = asyncio.create_task(crawl_watchdog(gather_task))
                    try:
                        await gather_task
                    except asyncio.CancelledError:
                        print("  Crawl batch aborted; continuing with remaining batches.")
                    finally:
                        watchdog_task.cancel()
            except Exception as e:
                # managed_crawler bounds startup/teardown (and SIGKILLs a wedged
                # browser); this catches a re-raised startup failure so remaining
                # batches still run.
                print(f"  Crawl batch error ({type(e).__name__}: {e}); continuing with remaining batches.")

            crawl_results.extend(batch_results)

        print(f"\n✓ Crawled {len(crawl_results)} website(s)\n")

        # STEP 3: Extract events using Gemini AI
        step("STEP 3: Extracting Events with Gemini AI")

        extracted_results = []

        # Build list of all items to extract
        extraction_queue = []

        # Add incomplete 'crawled' results from previous runs
        for r in incomplete_crawled:
            extraction_queue.append({
                'crawl_result_id': r['crawl_result_id'],
                'name': r['name'],
                'notes': r.get('notes', ''),
                'run_date': r.get('run_date'),
                'source': 'incomplete'
            })

        # Add newly crawled results
        for crawl_result_id, website in crawl_results:
            extraction_queue.append({
                'crawl_result_id': crawl_result_id,
                'name': website['name'],
                'notes': website.get('notes', ''),
                'run_date': None,
                'source': 'new',
                'website': website,
                'use_vision': website.get('process_images') == 1,
                'base_url': website.get('base_url', ''),
                'max_batches': website.get('max_batches')
            })

        # Resolve batch mode: default to sync (no-batch) — use --batch to opt in
        effective_batch = bool(use_batch)

        batch_processed_crids = set()  # Track items handled by batch to avoid duplicates

        if extraction_queue and effective_batch:
            # Batch extraction path (Gemini Batch API — 50% cheaper)
            print(f"\n  Batch extracting events from {len(extraction_queue)} website(s)...")

            try:
                batch_results = await extractor.run_batch_extraction(extraction_queue)

                # Track all items processed by batch (success or fail)
                batch_processed_crids = {crid for crid, _ in batch_results}

                # Map successful results back to extraction_queue items
                success_crids = {crid for crid, success in batch_results if success}
                for item in extraction_queue:
                    crid = item['crawl_result_id']
                    if crid in success_crids:
                        if item['source'] == 'incomplete':
                            extracted_results.append((crid, {
                                'name': item['name'],
                                'notes': item['notes'],
                                'run_date': item['run_date']
                            }))
                        else:
                            extracted_results.append((crid, item['website']))

            except Exception as e:
                print(f"\n  Batch extraction failed: {e}")
                print(f"  Falling back to individual API calls...")
                effective_batch = False  # Fall through to sync path below

        # Sync extraction path — either primary or fallback from batch failure
        # Filter out items already processed by batch to avoid duplicates
        sync_queue = [item for item in extraction_queue
                       if item['crawl_result_id'] not in batch_processed_crids]

        if sync_queue and not effective_batch:
            # Sync extraction path (individual API calls)
            print(f"\n  Extracting events from {len(sync_queue)} website(s) with {NUM_WORKERS} workers...")

            extract_queue = asyncio.Queue()
            for item in sync_queue:
                await extract_queue.put(item)

            async def extract_worker():
                """Worker that continuously pulls from queue until empty."""
                results = []
                while True:
                    try:
                        item = extract_queue.get_nowait()
                    except asyncio.QueueEmpty:
                        break

                    conn = db.create_connection()
                    if not conn:
                        extract_queue.task_done()
                        continue
                    cur = conn.cursor(buffered=True)
                    try:
                        success = await extractor.extract_events(
                            cur, conn, item['crawl_result_id'],
                            item['name'], item['notes'],
                            use_vision=item.get('use_vision', False),
                            base_url=item.get('base_url', ''),
                            max_batches=item.get('max_batches')
                        )
                        if success:
                            if item['source'] == 'incomplete':
                                results.append((item['crawl_result_id'], {
                                    'name': item['name'],
                                    'notes': item['notes'],
                                    'run_date': item['run_date']
                                }))
                            else:
                                results.append((item['crawl_result_id'], item['website']))
                    except Exception as e:
                        print(f"    - Error extracting {item['name']}: {e}")
                    finally:
                        cur.close()
                        conn.close()
                        extract_queue.task_done()
                return results

            worker_results = await asyncio.gather(*[extract_worker() for _ in range(NUM_WORKERS)])

            for results in worker_results:
                extracted_results.extend(results)

        print(f"\n✓ Extracted events from {len(extracted_results)} website(s)\n")

        # STEP 4: Process responses
        step("STEP 4: Processing Responses")

        # Refresh connection to see data committed by extract workers
        cursor.close()
        connection.close()
        connection = db.create_connection()
        if not connection:
            print("Failed to reconnect to database")
            return False
        cursor = connection.cursor(buffered=True)

        total_events = 0

        # Build the per-run processing context ONCE and thread it through every
        # process_events call — locations/websites/tag data are immutable during
        # Step 4, so this avoids rebuilding all of them per crawl_result.
        proc_locations_map = proc_websites_map = proc_tag_context = None
        if incomplete_extracted or extracted_results:
            proc_locations_map = processor.build_locations_map(cursor)
            proc_websites_map = processor.build_websites_map(cursor)
            proc_tag_context = processor.load_tag_context(cursor)

        # First, process incomplete 'extracted' results from previous runs
        if incomplete_extracted:
            print(f"\n  Processing {len(incomplete_extracted)} incomplete 'extracted' result(s)...")
            for r in incomplete_extracted:
                print(f"  Processing {r['name']} (from {r['run_date']})...")
                # Use the run date from the original crawl
                original_run_date_str = r['run_date'].strftime('%Y%m%d')
                event_count = processor.process_events(
                    cursor, connection, r['crawl_result_id'],
                    r['name'], original_run_date_str,
                    locations_map=proc_locations_map,
                    websites_map=proc_websites_map,
                    tag_context=proc_tag_context,
                )
                total_events += event_count
                print(f"    - {event_count} events processed")

        # Then process newly extracted results
        for crawl_result_id, website in extracted_results:
            print(f"  Processing {website['name']}...")
            website_run_date = website.get('run_date')
            result_run_date_str = website_run_date.strftime('%Y%m%d') if website_run_date else run_date_str
            event_count = processor.process_events(
                cursor, connection, crawl_result_id,
                website['name'], result_run_date_str,
                locations_map=proc_locations_map,
                websites_map=proc_websites_map,
                tag_context=proc_tag_context,
            )
            total_events += event_count
            print(f"    - {event_count} events processed")

        print(f"\n✓ Processed {total_events} total events\n")

        # STEP 5: Detail-crawl individual event URLs for missing descriptions
        step("STEP 5: Crawling Event Details")

        candidates = db.get_detail_crawl_candidates(cursor, website_ids=website_ids)
        if candidates:
            detail_crawled = await processor.crawl_event_details(
                cursor, connection, candidates, NUM_WORKERS
            )
        else:
            print("  No events need detail crawling")
            detail_crawled = 0
        print(f"\n✓ Detail-crawled {detail_crawled} events\n")

        # Mark crawl run as completed
        db.complete_crawl_run(cursor, connection, crawl_run_id)

        # Serialize the mutate-and-publish tail (merge → export → upload → freq) so a
        # concurrent session can't write events / publish at the same time. The lock is
        # MySQL-connection-scoped, so the `finally: connection.close()` below releases it
        # on every exit path (success, error, abort). See pipeline/dblock.py.
        if not acquire_publish_lock(connection):
            print(f"\n✗ Could not acquire DB write lock after {PUBLISH_LOCK_ATTEMPTS} attempts "
                  f"(~{PUBLISH_LOCK_ATTEMPTS * dblock.DEFAULT_TIMEOUT // 60} min). Another session "
                  f"is publishing — aborting before merge to avoid a write conflict.\n"
                  f"  Crawled+extracted data is saved. Finish the merge/export/upload later with:\n"
                  f"    {_merge_only_hint(website_ids)}\n")
            return False

        # STEP 6: Merge crawl_events into final events table and archive outdated events
        step("STEP 6: Merging Crawl Events and Archiving Outdated Events")

        new_events, merged_events = merger.merge_crawl_events(cursor, connection, website_ids=website_ids)
        print(f"\n✓ Merged events ({new_events} new, {merged_events} merged)\n")

        # Classify event sections
        print(f"\n  Classifying event sections...")
        exporter.classify_event_sections(cursor, connection)

        # STEP 7: Export to JSON from events table
        step("STEP 7: Exporting Events to JSON")

        print("  Exporting events from database to JSON...")
        export_stats = exporter.export_events(cursor)
        exporter.export_tag_hierarchy(cursor)
        exporter.export_organizers(cursor, export_stats['organizer_root_ids'])

        print("\n✓ Event export completed\n")

        # STEP 8: Upload data files
        step("STEP 8: Uploading Data")

        success = uploader.upload(use_tls=False)

        if success:
            print("\n✓ Data upload completed\n")
        else:
            print("\n✗ Data upload failed\n")
            return False

        # STEP 9: Adjust crawl frequencies based on historical data
        step("STEP 9: Adjusting Crawl Frequencies")

        freq_results = frequency_analyzer.analyze_frequencies(cursor, connection)
        if freq_results['adjusted'] > 0:
            print(f"\n✓ Adjusted {freq_results['adjusted']} website frequency(s)\n")
        else:
            print(f"\nNo frequency adjustments needed\n")

        result = timer.stop()
        if result is not None:
            name, elapsed = result
            print(f"  {name} took {logging_utils.format_duration(elapsed)}")

        print(f"\n{'='*60}")
        print(f"PIPELINE COMPLETED SUCCESSFULLY")
        print(f"{'='*60}\n")

        # Show summary
        print("Summary:")
        print(f"  - Websites crawled: {len(crawl_results)}")
        if incomplete_crawled:
            print(f"  - Resumed extractions: {len(incomplete_crawled)}")
        if incomplete_extracted:
            print(f"  - Resumed processing: {len(incomplete_extracted)}")
        print(f"  - Events extracted: {len(extracted_results)}")
        print(f"  - Total events processed: {total_events}")

        # Step timings (slowest first) to surface bottlenecks
        print("\nStep timings (slowest first):")
        for name, secs in sorted(timer.steps, key=lambda s: s[1], reverse=True):
            print(f"  {logging_utils.format_duration(secs):>8}  {name}")
        print(f"  {'-'*8}")
        print(f"  {logging_utils.format_duration(timer.total):>8}  TOTAL")

        return True

    except KeyboardInterrupt:
        print("\n\nPipeline interrupted by user.")
        return False
    except Exception as e:
        print(f"\n\nPipeline Error: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        cursor.close()
        connection.close()


def run_merge_only(website_ids=None):
    """Run ONLY the merge → classify → export → upload tail. No crawling, no AI.

    Recovery path for interrupted runs: picks up crawl_results that were
    processed but whose crawl_events never merged (killed run, lost lock race)
    without re-crawling or re-paying extraction. Safe to run anytime — with no
    pending unmerged events it just re-exports and re-uploads.

    Returns True on success.
    """
    print(f"{'='*60}")
    print("EVENT PROCESSING PIPELINE — MERGE-ONLY MODE")
    if website_ids:
        print(f"  Filtering to website IDs: {', '.join(map(str, website_ids))}")
    print(f"{'='*60}\n")

    connection = db.create_connection()
    if not connection:
        print("Failed to connect to database")
        return False
    cursor = connection.cursor(buffered=True)

    try:
        stranded = db.get_stranded_merge_summary(cursor, website_ids=website_ids)
        if stranded:
            total_unmerged = sum(r[4] for r in stranded)
            print(f"Found {len(stranded)} crawl result(s) with {total_unmerged} unmerged event(s):")
            for cr_id, w_id, w_name, processed_at, n in stranded[:20]:
                print(f"  cr={cr_id} w={w_id} {w_name} (processed {processed_at}, {n} unmerged)")
            if len(stranded) > 20:
                print(f"  ... and {len(stranded) - 20} more")
        else:
            print("No unmerged crawl results pending — will still re-export and upload.")

        if not acquire_publish_lock(connection):
            print(f"\n✗ Could not acquire DB write lock after {PUBLISH_LOCK_ATTEMPTS} attempts. "
                  f"Another session is publishing — retry when it finishes "
                  f"(./venv/bin/python pipeline/dblock.py status).\n")
            return False

        print(f"\n{'='*60}\nMerging Crawl Events and Archiving Outdated Events\n{'='*60}")
        new_events, merged_events = merger.merge_crawl_events(cursor, connection, website_ids=website_ids)
        print(f"\n✓ Merged events ({new_events} new, {merged_events} merged)\n")

        print("  Classifying event sections...")
        exporter.classify_event_sections(cursor, connection)

        print(f"\n{'='*60}\nExporting Events to JSON\n{'='*60}")
        export_stats = exporter.export_events(cursor)
        exporter.export_tag_hierarchy(cursor)
        exporter.export_organizers(cursor, export_stats['organizer_root_ids'])
        print("\n✓ Event export completed\n")

        print(f"{'='*60}\nUploading Data\n{'='*60}")
        success = uploader.upload(use_tls=False)
        if not success:
            print("\n✗ Data upload failed\n")
            return False
        print("\n✓ Data upload completed\n")

        print(f"{'='*60}")
        print("MERGE-ONLY RUN COMPLETED SUCCESSFULLY")
        print(f"{'='*60}\n")
        return True

    except KeyboardInterrupt:
        print("\n\nMerge-only run interrupted by user.")
        return False
    except Exception as e:
        print(f"\n\nMerge-only Error: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        cursor.close()
        connection.close()


def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description='Event Processing Pipeline',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python main.py                     # Full run (uses sync API by default)
  python main.py --ids 941           # Specific website
  python main.py --batch             # Full run with Batch API (50% cheaper but slower)
  python main.py --limit 5           # Only crawl first 5 websites due
  python main.py --merge-only        # Just merge pending events + export + upload (no crawling)
        """
    )
    parser.add_argument(
        '--ids', '--website-ids',
        type=str,
        help='Comma-separated list of website IDs to process (ignores crawl_frequency)'
    )
    parser.add_argument(
        '--limit', '-n',
        type=int,
        help='Maximum number of websites to crawl'
    )
    parser.add_argument(
        '--merge-only',
        action='store_true',
        help='Skip crawl/extract/process; only merge pending crawl_events, then export + upload. '
             'Recovers interrupted runs without re-crawling.'
    )
    batch_group = parser.add_mutually_exclusive_group()
    batch_group.add_argument(
        '--batch',
        action='store_true', default=None,
        help='Use Gemini Batch API for extraction (50%% cheaper but can get stuck)'
    )
    batch_group.add_argument(
        '--no-batch',
        action='store_true', default=None,
        help='Use individual API calls for extraction (this is the default)'
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()

    website_ids = None
    if args.ids:
        website_ids = [int(id.strip()) for id in args.ids.split(',')]

    # Resolve batch mode from CLI flags
    if args.batch:
        use_batch = True
    elif args.no_batch:
        use_batch = False
    else:
        use_batch = None  # No explicit flag: run_pipeline defaults to sync

    if args.merge_only:
        success = run_merge_only(website_ids)
    else:
        success = asyncio.run(run_pipeline(website_ids, args.limit, use_batch))
    sys.exit(0 if success else 1)

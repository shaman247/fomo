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

# Number of concurrent workers for crawling, extraction, and detail crawling
NUM_WORKERS = 10


async def run_pipeline(website_ids=None, limit=None, use_batch=None):
    """Execute the complete event processing pipeline.

    Args:
        website_ids: Optional list of website IDs to process. If None, processes
                     all websites due for crawling based on crawl_frequency.
        limit: Optional maximum number of websites to crawl.
        use_batch: If True, use Gemini Batch API for extraction (50% cheaper).
                   If None, defaults to True for full runs, False for --ids runs.
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
                async with AsyncWebCrawler(config=browser_config) as web_crawler:
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
                # A killed/wedged browser can make the context manager teardown
                # raise — isolate it so remaining batches still run.
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
        if use_batch is not None:
            effective_batch = use_batch
        else:
            effective_batch = False

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

        # First, process incomplete 'extracted' results from previous runs
        if incomplete_extracted:
            print(f"\n  Processing {len(incomplete_extracted)} incomplete 'extracted' result(s)...")
            for r in incomplete_extracted:
                print(f"  Processing {r['name']} (from {r['run_date']})...")
                # Use the run date from the original crawl
                original_run_date_str = r['run_date'].strftime('%Y%m%d')
                event_count = processor.process_events(
                    cursor, connection, r['crawl_result_id'],
                    r['name'], original_run_date_str
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
                website['name'], result_run_date_str
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
        exporter.export_events(cursor)
        exporter.export_tag_hierarchy(cursor)
        exporter.export_organizers(cursor)

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
        use_batch = None  # Let run_pipeline decide based on whether --ids was used

    success = asyncio.run(run_pipeline(website_ids, args.limit, use_batch))
    sys.exit(0 if success else 1)

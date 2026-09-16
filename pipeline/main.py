"""
Event Processing Pipeline

Orchestrates the complete event processing workflow:

1. Crawl - Query websites table, crawl due sites, store in crawl_results
2. Extract - Queue source packets for the running agent; validate its structured results
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

import logging_utils
logging_utils.install()  # Prefix every log line with a timestamp for profiling

import db
import crawler
from crawler import get_browser_key
import extractor
import agent_extraction
import agent_run
from pathlib import Path
import shlex
import processor
import merger
import exporter
import uploader
import frequency_analyzer
import dblock
from preflight import run_disk_preflight

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


def run_public_dataset_export(cursor, force=False):
    """Public NDJSON dataset export → upload to public_html/exports/.

    The automatic weekly run was disabled 2026-09-12: the publish tail no
    longer calls this. It is only reached via `main.py --export-dataset`
    (force=True). The 7-day gate on the newest local dated snapshot in
    exports/ is kept for a future re-enable.
    """
    if not force and not exporter.should_export_public_dataset():
        return True

    print("  Weekly public dataset export is due — generating NDJSON snapshots...")
    stats = exporter.export_public_datasets(cursor)
    success = uploader.upload_public_dataset(
        stats['upcoming']['path'], stats['past']['path'], stats['manifest_path'])
    if success:
        print(f"\n✓ Public datasets uploaded ({stats['upcoming']['events']} upcoming, "
              f"{stats['past']['events']} past events)\n")
    else:
        # The dated upcoming snapshot is the scheduling state — discard it so
        # the gate stays open and the next pipeline run retries.
        os.remove(stats['upcoming']['path'])
        print("\n✗ Public dataset upload failed — snapshot discarded; "
              "will retry on the next pipeline run\n")
    return success


def run_export_dataset_only():
    """Standalone forced public dataset export (main.py --export-dataset)."""
    if not run_disk_preflight():
        return False
    connection = db.create_connection()
    if not connection:
        print("Failed to connect to database")
        return False
    cursor = connection.cursor(buffered=True)
    try:
        return run_public_dataset_export(cursor, force=True)
    finally:
        cursor.close()
        connection.close()


def _merge_only_hint(website_ids):
    """The recovery command to print when the merge tail couldn't run."""
    ids_arg = f" --ids {','.join(map(str, website_ids))}" if website_ids else ""
    return f"python pipeline/main.py --merge-only{ids_arg}"


def resume_command(work_dir):
    return f"./venv/bin/python pipeline/main.py --resume {shlex.quote(str(work_dir))}"


def report_agent_pending(work_dir):
    print("\nPIPELINE WAITING FOR AGENT EXTRACTION (exit 2)")
    print(f"Review pending packets: ./venv/bin/python pipeline/agent_extraction.py status --work-dir {shlex.quote(str(work_dir))}")
    print(f"After submitting complete responses, continue: {resume_command(work_dir)}")
    print("Processing/publication will continue only after required responses validate.")
    return None


def retire_ineligible_retries(work_dir, state, results):
    """Retire legacy failed fetches after verifying the saved source snapshot.

    Keep their IDs/reasons for run reporting and leave DB content/status intact.
    These are crawl failures, never accepted zero-event extractions.
    """
    rejected = [row for row in results if row.get('retry_exclusion_reason')]
    if not rejected:
        return results
    kept = [row for row in results if not row.get('retry_exclusion_reason')]
    retired = state.setdefault('retired_retries', [])
    for row in rejected:
        record = {key: row[key] for key in ('crawl_result_id', 'website_id', 'name',
                                            'source_hash', 'retry_exclusion_reason')}
        retired.append(record)
        print(f"  Retiring failed retry cr{row['crawl_result_id']} ({row['name']}): "
              f"{row['retry_exclusion_reason']}; original failure preserved")
    state['crawl_result_ids'] = [row['crawl_result_id'] for row in kept]
    state['source_hashes'] = {str(row['crawl_result_id']): row['source_hash'] for row in kept}
    state['website_ids'] = sorted({row['website_id'] for row in kept})
    agent_run.save(work_dir, state)
    return kept


async def run_pipeline(website_ids=None, limit=None, use_batch=None, *, work_dir=None, resume=False):
    """Run one resumable phase. None means agent work is pending (CLI exit 2)."""
    if not run_disk_preflight():
        return False
    if use_batch:
        raise ValueError('Model API batch mode was removed; use agent extraction packets')
    with agent_run.singleton():
        return await _run_pipeline(website_ids, limit, work_dir=work_dir, resume=resume)


async def _run_pipeline(website_ids=None, limit=None, *, work_dir=None, resume=False):
    """Execute the complete event processing pipeline.

    Args:
        website_ids: Optional list of website IDs to process. If None, processes
                     all websites due for crawling based on crawl_frequency.
        limit: Optional maximum number of websites to crawl.
        work_dir: Durable agent requests, responses, and run scope.
        resume: Continue exact saved crawl IDs without crawling listing pages again.
    """
    work_dir = Path(work_dir or agent_run.new_work_dir()).resolve()
    if resume:
        state = agent_run.load(work_dir)
        website_ids = state['website_ids']
        if state['phase'] == 'complete':
            print(f'Agent pipeline already completed: {work_dir}')
            return True
    else:
        if (work_dir / 'run.json').exists():
            raise ValueError(f'Run already exists; use --resume {work_dir}')
        state = {'version': 1, 'city': os.environ.get('FOMO_CITY', 'nyc'),
                 'reference_date': datetime.now().date().isoformat(),
                 'phase': 'crawling', 'website_ids': website_ids}
        agent_run.save(work_dir, state)
    agent_extraction.configure(work_dir)
    print(f'Agent extraction workspace: {work_dir}')
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

        if resume:
            saved_results = agent_run.read_results(cursor, state['crawl_result_ids'])
            agent_run.verify_sources(state, saved_results)
            saved_results = retire_ineligible_retries(work_dir, state, saved_results)
            website_ids = state['website_ids']
            incomplete_results = [r for r in saved_results if r['status'] in ('crawled', 'extracted')]
            if any(r['status'] not in ('crawled', 'extracted', 'processed') for r in saved_results):
                raise ValueError('Saved crawl results are not ready for extraction')
        else:
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

        websites = [] if resume else db.get_websites_due_for_crawling(cursor, website_ids)
        # Automatic runs finish stored crawls first. Explicit --ids retains its
        # force-recrawl contract (needed after a crawl/source fix); the new run
        # supersedes that site's old incomplete rows in this extraction scope.
        pending_website_ids = {r['website_id'] for r in incomplete_results}
        if not website_ids:
            websites = [w for w in websites if w['id'] not in pending_website_ids]
        if limit and len(websites) > limit:
            print(f"Found {len(websites)} website(s) due, limiting to {limit}")
            websites = websites[:limit]
        elif website_ids:
            print(f"Found {len(websites)} website(s) matching specified IDs")
        else:
            print(f"Found {len(websites)} website(s) due for crawling")
        if website_ids and not resume:
            recrawling = {w['id'] for w in websites}
            incomplete_results = [r for r in incomplete_results if r['website_id'] not in recrawling]
            incomplete_crawled = [r for r in incomplete_results if r['status'] == 'crawled']
            incomplete_extracted = [r for r in incomplete_results if r['status'] == 'extracted']

        # Check if there's any work to do
        has_work = resume or len(websites) > 0 or len(incomplete_results) > 0

        if not has_work:
            print("\nNo websites need crawling and no incomplete results to process.")
            print("Pipeline completed (no work to do).")
            state.update(phase='complete', crawl_result_ids=[], source_hashes={})
            agent_run.save(work_dir, state)
            return True

        for w in websites:
            print(f"  - {w['name']} ({len(w['urls'])} URL(s))")

        # Create crawl run
        run_date = datetime.fromisoformat(state['reference_date']).date()
        run_date_str = run_date.strftime('%Y%m%d')
        if resume:
            crawl_run_id = state['crawl_run_id']
        else:
            with dblock.write_lock(connection, label='agent_pipeline_start'):
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

        # Freeze exact crawl scope before any agent work. Resumes never query all
        # incomplete results or recrawl a listing page.
        if not resume:
            result_ids = sorted({r['crawl_result_id'] for r in incomplete_results}
                                | {crid for crid, _ in crawl_results})
            connection.commit()  # Refresh the snapshot after crawler worker commits.
            saved_results = agent_run.read_results(cursor, result_ids)
            website_ids = sorted({r['website_id'] for r in saved_results})
            state.update(crawl_run_id=crawl_run_id, crawl_result_ids=result_ids,
                         website_ids=website_ids,
                         source_hashes={str(r['crawl_result_id']): r['source_hash'] for r in saved_results},
                         phase='listing')
            agent_run.save(work_dir, state)

        if not saved_results:
            print('No successful crawl results to extract; publication skipped.')
            state['phase'] = 'crawl_failed' if websites else 'complete'
            agent_run.save(work_dir, state)
            return not bool(websites)

        step("STEP 3: Preparing / Applying Agent Extraction")
        extracted_results = []
        pending = []
        errors = []
        # Extraction now does local file I/O and validation. Serialize DB mutation
        # while independently reviewable requests accumulate across all websites.
        for item in saved_results:
            if item['status'] != 'crawled':
                continue
            try:
                with dblock.write_lock(connection, label='agent_extraction'):
                    connection.commit()
                    current = agent_run.read_results(cursor, [item['crawl_result_id']])
                    if current[0]['source_hash'] != item['source_hash']:
                        raise ValueError('Crawl source/context changed while preparing extraction')
                    success = await extractor.extract_events(
                        cursor, connection, item['crawl_result_id'], item['name'], item['notes'],
                        use_vision=item.get('use_vision', False))
                if success:
                    extracted_results.append((item['crawl_result_id'], item))
                else:
                    errors.append(item['crawl_result_id'])
            except agent_extraction.AgentExtractionPending as exc:
                connection.rollback()
                pending.append(exc)
            except Exception as exc:
                connection.rollback()
                errors.append(item['crawl_result_id'])
                print(f"  Extraction error for {item['name']}: {exc}")
        if errors:
            print(f"Extraction failed for crawl results {errors}; processing and publication stopped.")
            print(f"Repair the responses/source, then resume: {resume_command(work_dir)}")
            return False
        if pending:
            return report_agent_pending(work_dir)
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

        with dblock.write_lock(connection, label='agent_pipeline_process'):
            connection.commit()
            agent_run.verify_sources(state, agent_run.read_results(cursor, state['crawl_result_ids']))
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

            processed_results = agent_run.read_results(cursor, state['crawl_result_ids'])
            if any(r['status'] != 'processed' for r in processed_results):
                raise ValueError('Processing did not finish every saved crawl result; publication stopped')

        print(f"\n✓ Processed {total_events} total events\n")

        # STEP 5: Detail-crawl individual event URLs for missing descriptions
        step("STEP 5: Crawling Event Details")

        if 'detail_candidates' not in state:
            state['detail_candidates'] = (db.get_detail_crawl_candidates(cursor, website_ids=website_ids)
                                          if website_ids else [])
            state['phase'] = 'details'
            agent_run.save(work_dir, state)
        candidates = state['detail_candidates']
        if candidates and not state.get('details_complete'):
            try:
                detail_crawled = await processor.crawl_event_details(
                    cursor, connection, candidates, NUM_WORKERS, extraction_dir=work_dir)
            except agent_extraction.AgentExtractionPending:
                return report_agent_pending(work_dir)
        else:
            print("  No pending detail extraction")
            detail_crawled = 0
        state['details_complete'] = True
        agent_run.save(work_dir, state)
        print(f"\n✓ Detail-crawled {detail_crawled} events\n")

        # Serialize the mutate-and-publish tail (merge → export → upload → freq) so a
        # concurrent session can't write events / publish at the same time. The lock is
        # MySQL-connection-scoped, so the `finally: connection.close()` below releases it
        # on every exit path (success, error, abort). See pipeline/dblock.py.
        if not acquire_publish_lock(connection):
            print(f"\n✗ Could not acquire DB write lock after {PUBLISH_LOCK_ATTEMPTS} attempts "
                  f"(~{PUBLISH_LOCK_ATTEMPTS * dblock.DEFAULT_TIMEOUT // 60} min). Another session "
                  f"is publishing — aborting before merge to avoid a write conflict.\n"
                  f"  Crawled+extracted data is saved. Finish the merge/export/upload later with:\n"
                  f"    {resume_command(work_dir)}\n")
            return False

        # Validate crawl identity again under the publishing lock; another session
        # may have changed source rows while the agent reviewed its packets.
        connection.commit()
        agent_run.verify_sources(state, agent_run.read_results(cursor, state['crawl_result_ids']))
        state['phase'] = 'publishing'
        agent_run.save(work_dir, state)

        # STEPS 6-8: merge → classify → export → upload
        if not run_publish_tail(cursor, connection, website_ids,
                                banner=lambda i, title: step(f"STEP {6 + i}: {title}")):
            return False

        # STEP 9: Adjust crawl frequencies based on historical data
        step("STEP 9: Adjusting Crawl Frequencies")

        freq_results = frequency_analyzer.analyze_frequencies(cursor, connection)
        if freq_results['adjusted'] > 0:
            print(f"\n✓ Adjusted {freq_results['adjusted']} website frequency(s)\n")
        else:
            print(f"\nNo frequency adjustments needed\n")

        db.complete_crawl_run(cursor, connection, crawl_run_id)
        state['phase'] = 'complete'
        agent_run.save(work_dir, state)
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

        # Relative-drop detector: a partial crawl (a cold-start/hydration race
        # on the first URL, a CF challenge, an extraction outage) stores as
        # 'processed' and looks healthy — only the count against the previous
        # crawl gives it away. REPORT ONLY: ~1 in 5 hits is a legitimate drop
        # (season ended, calendar cleared), so this must never fail closed.
        try:
            drops = db.get_coverage_drop_report(cursor, crawl_run_id=crawl_run_id)
            for line in db.format_coverage_drop_report(drops):
                print(line)
        except Exception as e:
            print(f"  (coverage-drop check skipped: {e})")

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


def run_publish_tail(cursor, connection, website_ids, banner):
    """The publish tail shared by a full run and --merge-only:
    merge → classify sections → export JSON → upload.

    `banner(i, title)` prints the header for the i-th stage (merge, export,
    upload), so each caller keeps its own step-numbering/timing style. The
    caller must already hold the publish lock.

    Returns False when the upload failed (the run should stop), else True.
    """
    banner(0, "Merging Crawl Events and Archiving Outdated Events")
    new_events, merged_events = merger.merge_crawl_events(cursor, connection, website_ids=website_ids)
    print(f"\n✓ Merged events ({new_events} new, {merged_events} merged)\n")

    # Fast-path archival for events the grace period is holding open whose own
    # detail pages are confirmed gone (site unpublished them mid-run). Runs after
    # the merge because its candidate set depends on the event_sources rows the
    # merge just wrote; never touches an event a listing still shows.
    print("  Probing dead links for grace-window events...")
    try:
        import liveness_probe
        probe_stats = liveness_probe.run(cursor, connection)
        if probe_stats['archived']:
            print(f"  ✓ Liveness probe archived {probe_stats['archived']} event(s) with dead links")
    except Exception as e:
        connection.rollback()
        print(f"  ⚠️ Liveness probe failed ({type(e).__name__}: {e}); continuing without it")

    print("\n  Classifying event sections...")
    exporter.classify_event_sections(cursor, connection)

    from event_icon_review import refresh_review_state
    print("  Event icon review state:", refresh_review_state(cursor, apply=True))
    print("  Final icon choices are made by run-pipeline's agent review step "
          "(pipeline/event_icon_review.py prepare); heuristics are suggestions only.")
    from icon_catalog import flag_metadata
    flag_metadata(cursor)
    cursor.execute("SELECT COUNT(*) FROM icon_review_queue WHERE status='pending'")
    pending_icons = cursor.fetchone()[0]
    if pending_icons:
        print(f"  Icon artwork review: {pending_icons} unseen/unsupported emoji pending "
              "(review with pipeline/icon_catalog.py)")
    connection.commit()

    banner(1, "Exporting Events to JSON")
    print("  Exporting events from database to JSON...")
    export_stats = exporter.export_events(cursor)
    exporter.export_tag_hierarchy(cursor)
    exporter.export_organizers(cursor, export_stats['organizer_root_ids'])
    print("\n✓ Event export completed\n")

    banner(2, "Uploading Data")
    if not uploader.upload(use_tls=False):
        print("\n✗ Data upload failed\n")
        return False
    print("\n✓ Data upload completed\n")

    # The weekly public NDJSON dataset export is DISABLED (2026-09-12) — it no
    # longer runs automatically here. Run it by hand with --export-dataset.
    return True


def run_merge_only(website_ids=None):
    """Run ONLY the merge → classify → export → upload tail. No crawling, no AI.

    Recovery path for interrupted runs: picks up crawl_results that were
    processed but whose crawl_events never merged (killed run, lost lock race)
    without re-crawling or re-paying extraction. Safe to run anytime — with no
    pending unmerged events it just re-exports and re-uploads.

    Returns True on success.
    """
    if not run_disk_preflight():
        return False
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

        if not run_publish_tail(
                cursor, connection, website_ids,
                banner=lambda i, title: print(f"\n{'='*60}\n{title}\n{'='*60}")):
            return False

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
  python main.py                     # Crawl and prepare agent extraction packets
  python main.py --ids 941           # Specific website
  python main.py --resume DIR        # Apply agent responses and continue the saved run
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
    parser.add_argument(
        '--export-dataset',
        action='store_true',
        help='Force the public NDJSON dataset export + upload to public_html/exports/ '
             '(normally runs weekly as part of the pipeline tail), then exit.'
    )
    parser.add_argument('--work-dir', help='Directory for a new durable agent extraction run')
    parser.add_argument('--resume', metavar='DIR', help='Resume saved agent extraction without recrawling listings')
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()

    website_ids = None
    if args.ids:
        website_ids = [int(id.strip()) for id in args.ids.split(',')]

    if args.resume and (args.work_dir or args.ids or args.limit or args.merge_only or args.export_dataset):
        raise SystemExit('--resume uses its saved scope; do not combine it with other run modes or filters')
    if args.work_dir and (args.merge_only or args.export_dataset):
        raise SystemExit('--work-dir is only for a new crawl/extraction run')
    try:
        if args.export_dataset:
            with agent_run.singleton():
                success = run_export_dataset_only()
        elif args.merge_only:
            with agent_run.singleton():
                success = run_merge_only(website_ids)
        else:
            success = asyncio.run(run_pipeline(website_ids, args.limit,
                                               work_dir=args.resume or args.work_dir,
                                               resume=bool(args.resume)))
    except (ValueError, RuntimeError, OSError) as exc:
        print(f'Pipeline could not start: {exc}')
        success = False
    sys.exit(2 if success is None else (0 if success else 1))

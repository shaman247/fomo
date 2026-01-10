"""
Event Processing Pipeline

Orchestrates the complete event processing workflow:

1. Crawl - Query websites table, crawl due sites, store in crawl_results
2. Extract - Use Gemini AI to extract structured event data
3. Process - Parse responses, enrich with location data, store in crawl_events
4. Merge - Deduplicate crawl_events into final events table
5. Export - Generate JSON files from events table for website
6. Upload - Push JSON files to FTP server

Usage:
    python main.py                     # Process all websites due for crawling
    python main.py --ids 941           # Process specific website ID(s)
    python main.py --ids 941,942,943   # Process multiple website IDs
    python main.py --limit 5           # Only crawl first 5 websites due
"""

import argparse
import asyncio
import sys
from datetime import datetime

from crawl4ai import AsyncWebCrawler

import db
import crawler
import extractor
import processor
import merger
import exporter
import uploader


async def run_pipeline(website_ids=None, limit=None):
    """Execute the complete event processing pipeline.

    Args:
        website_ids: Optional list of website IDs to process. If None, processes
                     all websites due for crawling based on crawl_frequency.
        limit: Optional maximum number of websites to crawl.
    """
    print(f"{'='*60}")
    print("EVENT PROCESSING PIPELINE")
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
        print(f"{'='*60}")
        print("STEP 0: Checking for Incomplete Crawl Results")
        print(f"{'='*60}")

        incomplete_results = db.get_incomplete_crawl_results(cursor)
        incomplete_crawled = [r for r in incomplete_results if r['status'] == 'crawled']
        incomplete_extracted = [r for r in incomplete_results if r['status'] == 'extracted']

        # Count retries vs incomplete
        retry_crawled = [r for r in incomplete_crawled if r.get('original_status') == 'failed']
        retry_extracted = [r for r in incomplete_extracted if r.get('original_status') == 'failed']

        if incomplete_results:
            print(f"Found {len(incomplete_results)} crawl result(s) to process:")
            if incomplete_crawled:
                retry_count = len(retry_crawled)
                incomplete_count = len(incomplete_crawled) - retry_count
                status_parts = []
                if incomplete_count:
                    status_parts.append(f"{incomplete_count} incomplete")
                if retry_count:
                    status_parts.append(f"{retry_count} failed retries")
                print(f"  - {len(incomplete_crawled)} need extraction ({', '.join(status_parts)})")
                for r in incomplete_crawled:
                    suffix = " [retry]" if r.get('original_status') == 'failed' else ""
                    print(f"      {r['name']} (run: {r['run_date']}){suffix}")
            if incomplete_extracted:
                retry_count = len(retry_extracted)
                incomplete_count = len(incomplete_extracted) - retry_count
                status_parts = []
                if incomplete_count:
                    status_parts.append(f"{incomplete_count} incomplete")
                if retry_count:
                    status_parts.append(f"{retry_count} failed retries")
                print(f"  - {len(incomplete_extracted)} need processing ({', '.join(status_parts)})")
                for r in incomplete_extracted:
                    suffix = " [retry]" if r.get('original_status') == 'failed' else ""
                    print(f"      {r['name']} (run: {r['run_date']}){suffix}")
        else:
            print("No incomplete crawl results found.")

        # STEP 1: Get websites due for crawling
        print(f"\n{'='*60}")
        print("STEP 1: Finding Websites Due for Crawling")
        print(f"{'='*60}")

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
        print(f"\n{'='*60}")
        print("STEP 2: Crawling Websites")
        print(f"{'='*60}")

        browser_config = crawler.get_browser_config()

        crawl_results = []
        async with AsyncWebCrawler(config=browser_config) as web_crawler:
            # Worker pool pattern: maintain N concurrent crawlers at all times
            num_workers = 12
            queue = asyncio.Queue()

            # Fill the queue with all websites
            for website in websites:
                await queue.put(website)

            async def worker():
                """Worker that continuously pulls from queue until empty."""
                results = []
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
                            results.append((result_id, website))
                    except Exception as e:
                        print(f"    - Error crawling {website['name']}: {e}")
                    finally:
                        cur.close()
                        conn.close()
                        queue.task_done()
                return results

            # Start N workers and wait for all to complete
            worker_results = await asyncio.gather(*[worker() for _ in range(num_workers)])

            # Flatten results from all workers
            for results in worker_results:
                crawl_results.extend(results)

        print(f"\n✓ Crawled {len(crawl_results)} website(s)\n")

        # STEP 3: Extract events using Gemini AI
        print(f"{'='*60}")
        print("STEP 3: Extracting Events with Gemini AI")
        print(f"{'='*60}")

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
                'website': website
            })

        if extraction_queue:
            print(f"\n  Extracting events from {len(extraction_queue)} website(s) with {num_workers} workers...")

            # Worker pool pattern: maintain N concurrent extractors at all times
            extract_queue = asyncio.Queue()
            for item in extraction_queue:
                await extract_queue.put(item)

            async def extract_worker():
                """Worker that continuously pulls from queue until empty."""
                results = []
                while True:
                    try:
                        item = extract_queue.get_nowait()
                    except asyncio.QueueEmpty:
                        break

                    # Each worker gets its own connection to see latest committed data
                    conn = db.create_connection()
                    if not conn:
                        extract_queue.task_done()
                        continue
                    cur = conn.cursor(buffered=True)
                    try:
                        success = await extractor.extract_events(
                            cur, conn, item['crawl_result_id'],
                            item['name'], item['notes']
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

            # Start N workers and wait for all to complete
            worker_results = await asyncio.gather(*[extract_worker() for _ in range(num_workers)])

            # Flatten results from all workers
            for results in worker_results:
                extracted_results.extend(results)

        print(f"\n✓ Extracted events from {len(extracted_results)} website(s)\n")

        # STEP 4: Process responses
        print(f"{'='*60}")
        print("STEP 4: Processing Responses")
        print(f"{'='*60}")

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
            # Use the run date from the website dict if available (for resumed crawls)
            website_run_date = website.get('run_date')
            if website_run_date:
                result_run_date_str = website_run_date.strftime('%Y%m%d')
            else:
                result_run_date_str = run_date_str
            event_count = processor.process_events(
                cursor, connection, crawl_result_id,
                website['name'], result_run_date_str
            )
            total_events += event_count
            print(f"    - {event_count} events processed")

        print(f"\n✓ Processed {total_events} total events\n")

        # Mark crawl run as completed
        db.complete_crawl_run(cursor, connection, crawl_run_id)

        # STEP 5: Merge crawl_events into final events table
        print(f"{'='*60}")
        print("STEP 5: Merging Crawl Events to Final Events Table")
        print(f"{'='*60}")

        new_events, merged_events = merger.merge_crawl_events(cursor, connection)
        print(f"\n✓ Merged events ({new_events} new, {merged_events} merged)\n")

        # STEP 6: Export to JSON from events table
        print(f"{'='*60}")
        print("STEP 6: Exporting Events to JSON")
        print(f"{'='*60}")

        print("  Exporting events from database to JSON...")
        exporter.export_events(cursor)

        print("\n✓ Event export completed\n")

        # STEP 7: Upload data files
        print(f"{'='*60}")
        print("STEP 7: Uploading Data")
        print(f"{'='*60}")

        success = uploader.upload(use_tls=False)

        if success:
            print("\n✓ Data upload completed\n")
        else:
            print("\n✗ Data upload failed\n")
            return False

        print(f"{'='*60}")
        print("PIPELINE COMPLETED SUCCESSFULLY")
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
  python main.py                     # Process all websites due for crawling
  python main.py --ids 941           # Process specific website ID
  python main.py --ids 941,942,943   # Process multiple website IDs
  python main.py --limit 5           # Only crawl first 5 websites due
        """
    )
    parser.add_argument(
        '--ids',
        type=str,
        help='Comma-separated list of website IDs to process (ignores crawl_frequency)'
    )
    parser.add_argument(
        '--limit', '-n',
        type=int,
        help='Maximum number of websites to crawl'
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()

    website_ids = None
    if args.ids:
        website_ids = [int(id.strip()) for id in args.ids.split(',')]

    success = asyncio.run(run_pipeline(website_ids, args.limit))
    sys.exit(0 if success else 1)

"""
Event Processing Pipeline

This script orchestrates the complete event processing workflow:
1. Crawl websites for event information
2. Extract events using Gemini AI
3. Process responses and enrich with location data
4. Export events to JSON files
5. Upload exported JSON files to server

Configuration:
- FTP credentials should be set in .env file:
  FTP_HOST, FTP_USER, FTP_PASSWORD, FTP_REMOTE_DIR (optional)
"""

import asyncio
import os
import sys

# Get the directory where this script is located
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

# Add the script directory to Python path for imports
sys.path.insert(0, SCRIPT_DIR)

# Import the main functions from each processing script
import crawl_sites
import extract_events
import process_responses
import export_events
import upload_data


async def run_pipeline():
    """
    Execute the complete event processing pipeline.

    Orchestrates all 5 steps in sequence:
    1. Crawl websites for event content
    2. Extract events using Gemini AI
    3. Process and enrich event data
    4. Export to JSON files for website
    5. Upload to server via FTP

    Returns:
        bool: True if all steps complete successfully, False otherwise
    """
    print(f"{'='*60}")
    print("EVENT PROCESSING PIPELINE")
    print(f"{'='*60}\n")

    try:
        # STEP 1: Crawl websites for raw content
        print(f"{'='*60}")
        print("STEP 1: Crawling Websites")
        print(f"{'='*60}")
        await crawl_sites.main()
        print("\n✓ Crawling completed\n")

        # STEP 2: Extract structured event data using AI
        print(f"{'='*60}")
        print("STEP 2: Extracting Events with Gemini AI")
        print(f"{'='*60}")
        await extract_events.main()
        print("\n✓ Event extraction completed\n")

        # STEP 3: Process responses and enrich with location data
        print(f"{'='*60}")
        print("STEP 3: Processing Responses")
        print(f"{'='*60}")
        process_responses.main()
        print("\n✓ Response processing completed\n")

        # STEP 4: Export events and locations to JSON
        print(f"{'='*60}")
        print("STEP 4: Exporting Events to JSON")
        print(f"{'='*60}")
        export_events.main()
        print("\n✓ Event export completed\n")

        # STEP 5: Upload data files to server
        print(f"{'='*60}")
        print("STEP 5: Uploading Data")
        print(f"{'='*60}")
        success = upload_data.main(use_tls=False)

        if success:
            print("\n✓ Data upload completed\n")
        else:
            print("\n✗ Data upload failed\n")
            return False

        print(f"{'='*60}")
        print("PIPELINE COMPLETED SUCCESSFULLY")
        print(f"{'='*60}\n")
        return True

    except KeyboardInterrupt:
        print("\n\nPipeline interrupted by user.")
        return False
    except Exception as e:
        print(f"\n\nPipeline Error: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    # Run the async pipeline
    success = asyncio.run(run_pipeline())

    # Exit with appropriate code
    sys.exit(0 if success else 1)

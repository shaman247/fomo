"""
Event Processing Pipeline with FTP Upload

This script orchestrates the complete event processing workflow:
1. Crawl websites for event information
2. Extract events using Gemini AI
3. Process responses and enrich with location data
4. Export events to JSON files
5. Upload exported JSON files to FTP server

Configuration:
- FTP credentials should be set in .env file:
  FTP_HOST, FTP_USER, FTP_PASSWORD, FTP_REMOTE_DIR (optional)
"""

import asyncio
import os
import sys
from ftplib import FTP, FTP_TLS
from pathlib import Path
from dotenv import load_dotenv

# Get the directory where this script is located
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

# Add the script directory to Python path for imports
sys.path.insert(0, SCRIPT_DIR)

# Import the main functions from each processing script
import crawl_sites
import extract_events
import process_responses
import export_events


def upload_to_ftp(local_dir, remote_dir=None, use_tls=False):
    """
    Upload JSON files from local directory to FTP server.

    Args:
        local_dir: Local directory containing files to upload
        remote_dir: Remote directory on FTP server (optional)
        use_tls: Whether to use FTPS (FTP over TLS) instead of plain FTP
    """
    load_dotenv()

    ftp_host = os.getenv('FTP_HOST')
    ftp_user = os.getenv('FTP_USER')
    ftp_password = os.getenv('FTP_PASSWORD')
    ftp_remote_dir = remote_dir or os.getenv('FTP_REMOTE_DIR', '')

    if not all([ftp_host, ftp_user, ftp_password]):
        print("\nError: FTP credentials not found in .env file.")
        print("Please set FTP_HOST, FTP_USER, and FTP_PASSWORD in your .env file.")
        return False

    try:
        print(f"\n{'='*60}")
        print("STEP 5: Uploading to FTP Server")
        print(f"{'='*60}")
        print(f"Connecting to FTP server: {ftp_host}")

        # Connect to FTP server
        if use_tls:
            ftp = FTP_TLS(ftp_host)
            ftp.login(ftp_user, ftp_password)
            ftp.prot_p()  # Enable encryption for data transfer
        else:
            ftp = FTP(ftp_host)
            ftp.login(ftp_user, ftp_password)

        print(f"Successfully connected as {ftp_user}")

        # Change to remote directory if specified
        if ftp_remote_dir:
            try:
                ftp.cwd(ftp_remote_dir)
                print(f"Changed to remote directory: {ftp_remote_dir}")
            except Exception as e:
                print(f"Warning: Could not change to directory '{ftp_remote_dir}': {e}")
                print("Attempting to create directory...")
                try:
                    ftp.mkd(ftp_remote_dir)
                    ftp.cwd(ftp_remote_dir)
                    print(f"Created and changed to directory: {ftp_remote_dir}")
                except Exception as e2:
                    print(f"Error: Could not create directory: {e2}")
                    return False

        # Find all JSON files in the local directory
        local_path = Path(local_dir)
        if not local_path.exists():
            print(f"Error: Local directory '{local_dir}' does not exist.")
            return False

        json_files = list(local_path.glob('*.json'))

        if not json_files:
            print(f"Warning: No JSON files found in '{local_dir}'")
            return True

        print(f"\nFound {len(json_files)} JSON file(s) to upload:")

        # Upload each JSON file
        uploaded_count = 0
        for json_file in json_files:
            try:
                filename = json_file.name
                print(f"  - Uploading {filename}...", end=' ')

                with open(json_file, 'rb') as file:
                    ftp.storbinary(f'STOR {filename}', file)

                print("✓")
                uploaded_count += 1

            except Exception as e:
                print(f"✗ Error: {e}")

        print(f"\nSuccessfully uploaded {uploaded_count}/{len(json_files)} files")

        # Close FTP connection
        ftp.quit()
        return True

    except Exception as e:
        print(f"\nFTP Error: {e}")
        return False


async def run_pipeline():
    """
    Run the complete event processing pipeline.
    """
    print(f"{'='*60}")
    print("EVENT PROCESSING PIPELINE")
    print(f"{'='*60}\n")

    try:
        # STEP 1: Crawl websites
        print(f"{'='*60}")
        print("STEP 1: Crawling Websites")
        print(f"{'='*60}")
        await crawl_sites.main()
        print("\n✓ Crawling completed\n")

        # STEP 2: Extract events using Gemini
        print(f"{'='*60}")
        print("STEP 2: Extracting Events with Gemini AI")
        print(f"{'='*60}")
        await extract_events.main()
        print("\n✓ Event extraction completed\n")

        # STEP 3: Process responses and enrich data
        print(f"{'='*60}")
        print("STEP 3: Processing Responses")
        print(f"{'='*60}")
        process_responses.main()
        print("\n✓ Response processing completed\n")

        # STEP 4: Export events to JSON
        print(f"{'='*60}")
        print("STEP 4: Exporting Events to JSON")
        print(f"{'='*60}")
        export_events.main()
        print("\n✓ Event export completed\n")

        # STEP 5: Upload to FTP
        output_dir = os.path.join(SCRIPT_DIR, '..', 'public_html', 'data')
        success = upload_to_ftp(output_dir, use_tls=False)

        if success:
            print("\n✓ FTP upload completed\n")
        else:
            print("\n✗ FTP upload failed\n")
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

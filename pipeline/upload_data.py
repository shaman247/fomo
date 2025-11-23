"""
Data Upload Script

This script uploads event and location JSON files to an FTP server.

Configuration:
- FTP credentials should be set in .env file:
  FTP_HOST, FTP_USER, FTP_PASSWORD, FTP_REMOTE_DIR (optional)

Usage:
    python upload_data.py
"""

import os
import sys
from ftplib import FTP, FTP_TLS
from pathlib import Path
from dotenv import load_dotenv

# Get the directory where this script is located
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))


def main(remote_dir=None, use_tls=False):
    """
    Upload event and location JSON files from public_html/data/ to FTP server.

    Args:
        remote_dir: Remote directory on FTP server (optional)
        use_tls: Whether to use FTPS (FTP over TLS) instead of plain FTP

    Returns:
        bool: True if upload was successful, False otherwise
    """
    load_dotenv()

    # Local directory containing the data files
    local_dir = os.path.join(SCRIPT_DIR, '..', 'public_html', 'data')

    ftp_host = os.getenv('FTP_HOST')
    ftp_user = os.getenv('FTP_USER')
    ftp_password = os.getenv('FTP_PASSWORD')
    ftp_remote_dir = remote_dir or os.getenv('FTP_REMOTE_DIR', '')

    if not all([ftp_host, ftp_user, ftp_password]):
        print("\nError: FTP credentials not found in .env file.")
        print("Please set FTP_HOST, FTP_USER, and FTP_PASSWORD in your .env file.")
        return False

    try:
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

        # Find event and location JSON files in the local directory
        local_path = Path(local_dir)
        if not local_path.exists():
            print(f"Error: Local directory '{local_dir}' does not exist.")
            return False

        # Only upload events*.json and locations*.json files
        json_files = list(local_path.glob('events*.json')) + list(local_path.glob('locations*.json'))

        if not json_files:
            print(f"Warning: No event or location JSON files found in '{local_dir}'")
            return True

        print(f"\nFound {len(json_files)} file(s) to upload:")

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


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)

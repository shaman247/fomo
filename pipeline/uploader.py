"""
FTP Upload Module

Uploads event and location JSON files to an FTP server.

Configuration:
- FTP credentials in .env: FTP_HOST, FTP_USER, FTP_PASSWORD, FTP_REMOTE_DIR
"""

import os
import re
import sys
from ftplib import FTP, FTP_TLS
from pathlib import Path
from dotenv import load_dotenv

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))


def upload(remote_dir=None, use_tls=False):
    """
    Upload event and location JSON files to FTP server.

    Args:
        remote_dir: Remote directory on FTP server (optional)
        use_tls: Whether to use FTPS (FTP over TLS) instead of plain FTP

    Returns:
        bool: True if upload was successful, False otherwise
    """
    load_dotenv()

    # Local directory containing the data files
    local_dir = os.path.join(SCRIPT_DIR, '..', 'src', 'data')

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

        # Connect to FTP server. Pass a socket timeout so a stalled network
        # connection (control or data) raises instead of blocking the upload
        # step forever — ftplib defaults to no timeout.
        FTP_TIMEOUT = 120
        if use_tls:
            ftp = FTP_TLS(ftp_host, timeout=FTP_TIMEOUT)
            ftp.login(ftp_user, ftp_password)
            ftp.prot_p()  # Enable encryption for data transfer
        else:
            ftp = FTP(ftp_host, timeout=FTP_TIMEOUT)
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


def upload_public_dataset(upcoming_path, past_path=None, manifest_path=None,
                          retention=8, use_tls=False):
    """Upload public NDJSON dataset snapshots to public_html/exports/.

    Uses the PUBLIC_HTML_FTP_USER account (its login root IS public_html/, the
    same account scripts/upload_public_html.py uses — the data-file FTP_USER
    account is chrooted elsewhere and can't reach exports/).

    Stores the dated upcoming snapshot under its own name, refreshes the stable
    `events-upcoming.ndjson` alias, `events-past.ndjson`, and `manifest.json`
    via STOR-to-temp + rename (so a reader mid-download never sees a truncated
    file), then prunes dated snapshots beyond `retention`.

    Returns True on success.
    """
    load_dotenv()

    ftp_host = os.getenv('FTP_HOST')
    ftp_user = os.getenv('PUBLIC_HTML_FTP_USER')
    ftp_password = os.getenv('FTP_PASSWORD')

    if not all([ftp_host, ftp_user, ftp_password]):
        print("\nError: FTP credentials not found in .env file.")
        print("Please set FTP_HOST, PUBLIC_HTML_FTP_USER, and FTP_PASSWORD in your .env file.")
        return False

    if not os.path.exists(upcoming_path):
        print(f"Error: dataset file '{upcoming_path}' does not exist.")
        return False

    FTP_TIMEOUT = 120
    try:
        print(f"Connecting to FTP server: {ftp_host}")
        if use_tls:
            ftp = FTP_TLS(ftp_host, timeout=FTP_TIMEOUT)
            ftp.login(ftp_user, ftp_password)
            ftp.prot_p()
        else:
            ftp = FTP(ftp_host, timeout=FTP_TIMEOUT)
            ftp.login(ftp_user, ftp_password)
        print(f"Successfully connected as {ftp_user}")

        try:
            ftp.cwd('exports')
        except Exception:
            ftp.mkd('exports')
            ftp.cwd('exports')
            print("Created remote directory: exports")

        def store_atomic(path, remote_name):
            tmp_name = remote_name + '.tmp'
            with open(path, 'rb') as f:
                ftp.storbinary(f'STOR {tmp_name}', f)
            try:
                ftp.delete(remote_name)
            except Exception:
                pass  # first upload — nothing to replace
            ftp.rename(tmp_name, remote_name)
            print(f"  - Uploaded {remote_name} ✓")

        dated_name = os.path.basename(upcoming_path)
        store_atomic(upcoming_path, dated_name)
        store_atomic(upcoming_path, 'events-upcoming.ndjson')
        if past_path and os.path.exists(past_path):
            store_atomic(past_path, 'events-past.ndjson')
        if manifest_path and os.path.exists(manifest_path):
            store_atomic(manifest_path, 'manifest.json')

        # Prune dated snapshots beyond retention (newest kept — the dated
        # filename format sorts chronologically).
        dated_re = re.compile(r'^events-upcoming-\d{4}-\d{2}-\d{2}\.ndjson$')
        remote_dated = sorted(n for n in ftp.nlst() if dated_re.match(os.path.basename(n)))
        for old_name in remote_dated[:-retention] if retention else []:
            try:
                ftp.delete(old_name)
                print(f"  - Pruned {os.path.basename(old_name)}")
            except Exception as e:
                print(f"  - Warning: could not prune {old_name}: {e}")

        ftp.quit()
        return True

    except Exception as e:
        print(f"\nFTP Error (public dataset): {e}")
        return False


if __name__ == "__main__":
    success = upload()
    sys.exit(0 if success else 1)

"""
Public HTML Upload Script

This script uploads HTML, CSS, and JavaScript files from the public_html directory to an FTP server.
Images and fonts directories are excluded.

Smart Upload:
- Tracks file modification times in upload_state.json
- Only uploads files that have changed since the last upload
- Use --force to upload all files regardless of state

Configuration:
- FTP credentials should be set in .env file:
  FTP_HOST, PUBLIC_HTML_FTP_USER, FTP_PASSWORD, FTP_REMOTE_DIR (optional)

Usage:
    python upload_public_html.py          # Upload only changed files
    python upload_public_html.py --force  # Upload all files
"""

import json
import os
import sys
from ftplib import FTP, FTP_TLS
from pathlib import Path
from dotenv import load_dotenv


# Get the directory where this script is located
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
STATE_FILE = os.path.join(SCRIPT_DIR, 'upload_state.json')


def load_upload_state():
    """Load the previous upload state from JSON file."""
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, 'r') as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            return {}
    return {}


def save_upload_state(state):
    """Save the upload state to JSON file."""
    with open(STATE_FILE, 'w') as f:
        json.dump(state, f, indent=2, sort_keys=True)


def get_file_mtime(file_path):
    """Get file modification time as a float timestamp."""
    return os.path.getmtime(file_path)


def ensure_remote_directory(ftp, remote_path):
    """
    Ensure a remote directory exists, creating it if necessary.

    Args:
        ftp: FTP connection object
        remote_path: Path to the remote directory
    """
    if not remote_path:
        return

    parts = remote_path.strip('/').split('/')
    current_path = ''

    for part in parts:
        current_path = f"{current_path}/{part}" if current_path else part
        try:
            ftp.cwd(f"/{current_path}")
        except:
            try:
                ftp.mkd(f"/{current_path}")
                print(f"  Created directory: {current_path}")
            except Exception as e:
                print(f"  Warning: Could not create directory '{current_path}': {e}")


def upload_directory(ftp, local_dir, remote_dir, root_exclude_dirs=None, exclude_files=None,
                     is_root=True, previous_state=None, new_state=None, force=False):
    """
    Recursively upload directory contents to FTP server.

    Args:
        ftp: FTP connection object
        local_dir: Local directory path
        remote_dir: Remote directory path
        root_exclude_dirs: Set of directory names to exclude at root level only
        exclude_files: Set of relative file paths to exclude (e.g., 'data/events.full.json')
        is_root: Whether this is the root directory level
        previous_state: Dict of file paths to previous modification times
        new_state: Dict to populate with current file modification times
        force: If True, upload all files regardless of modification time

    Returns:
        tuple: (uploaded_count, skipped_count, total_count)
    """
    if root_exclude_dirs is None:
        root_exclude_dirs = set()
    if exclude_files is None:
        exclude_files = set()
    if previous_state is None:
        previous_state = {}
    if new_state is None:
        new_state = {}

    uploaded_count = 0
    skipped_count = 0
    total_count = 0

    local_path = Path(local_dir)

    # Ensure we're in the correct remote directory for this level
    if remote_dir:
        try:
            ftp.cwd(f"/{remote_dir}")
        except Exception as e:
            print(f"  Warning: Could not change to directory '{remote_dir}': {e}")

    # Separate files and directories
    items = sorted(local_path.iterdir())
    files = [item for item in items if item.is_file()]
    directories = [item for item in items if item.is_dir()]

    # Upload files first (before any directory changes)
    for item in files:
        filename = item.name
        remote_file_path = f"{remote_dir}/{filename}" if remote_dir else filename

        # Check if this file should be excluded
        if remote_file_path in exclude_files:
            print(f"  Skipping excluded file: {remote_file_path}")
            continue

        total_count += 1

        # Get current modification time
        current_mtime = get_file_mtime(item)
        previous_mtime = previous_state.get(remote_file_path)

        # Store the current mtime in new state
        new_state[remote_file_path] = current_mtime

        # Check if file has changed
        if not force and previous_mtime is not None and current_mtime == previous_mtime:
            skipped_count += 1
            continue

        try:
            status = "(new)" if previous_mtime is None else "(modified)"
            if force and previous_mtime is not None and current_mtime == previous_mtime:
                status = "(forced)"
            print(f"  - Uploading {remote_file_path} {status}...", end=' ', flush=True)

            with open(item, 'rb') as file:
                ftp.storbinary(f'STOR {filename}', file)

            print("✓")
            uploaded_count += 1

        except Exception as e:
            print(f"✗ Error: {e}")

    # Then process subdirectories
    for item in directories:
        # Skip excluded directories (only at root level)
        if is_root and item.name in root_exclude_dirs:
            print(f"  Skipping excluded directory: {item.name}/")
            continue

        subdir_name = item.name
        new_remote_dir = f"{remote_dir}/{subdir_name}" if remote_dir else subdir_name

        print(f"  Processing directory: {subdir_name}/")

        # Ensure remote subdirectory exists
        try:
            ftp.cwd(f"/{new_remote_dir}")
        except:
            try:
                ftp.mkd(f"/{new_remote_dir}")
                print(f"    Created remote directory: {new_remote_dir}")
            except Exception as e:
                print(f"    Warning: Could not create directory '{new_remote_dir}': {e}")

        # Upload subdirectory contents (not root level anymore)
        sub_uploaded, sub_skipped, sub_total = upload_directory(
            ftp, item, new_remote_dir, root_exclude_dirs, exclude_files,
            is_root=False, previous_state=previous_state, new_state=new_state, force=force
        )
        uploaded_count += sub_uploaded
        skipped_count += sub_skipped
        total_count += sub_total

        # Change back to current directory after processing subdirectory
        if remote_dir:
            try:
                ftp.cwd(f"/{remote_dir}")
            except Exception as e:
                print(f"  Warning: Could not change back to directory '{remote_dir}': {e}")

    return uploaded_count, skipped_count, total_count


def main(remote_dir=None, use_tls=False, force=False):
    """
    Upload public_html content to FTP server.

    Uploads files from:
    - public_html/ (root files)
    - public_html/api/
    - public_html/css/
    - public_html/js/ (including js/data/)
    - public_html/data/ (excluding event/location JSON files)

    Excludes (at root level only):
    - public_html/images/
    - public_html/fonts/

    Excludes (specific files):
    - public_html/data/events.full.json
    - public_html/data/events.init.json
    - public_html/data/locations.full.json
    - public_html/data/locations.init.json

    Args:
        remote_dir: Remote directory on FTP server (optional)
        use_tls: Whether to use FTPS (FTP over TLS) instead of plain FTP
        force: If True, upload all files regardless of modification time

    Returns:
        bool: True if upload was successful, False otherwise
    """
    load_dotenv()

    # Local directory containing the public_html files
    local_dir = os.path.join(SCRIPT_DIR, '..', 'public_html')

    ftp_host = os.getenv('FTP_HOST')
    ftp_user = os.getenv('PUBLIC_HTML_FTP_USER')
    ftp_password = os.getenv('FTP_PASSWORD')
    ftp_remote_dir = remote_dir or os.getenv('FTP_REMOTE_DIR', '')

    if not all([ftp_host, ftp_user, ftp_password]):
        print("\nError: FTP credentials not found in .env file.")
        print("Please set FTP_HOST, PUBLIC_HTML_FTP_USER, and FTP_PASSWORD in your .env file.")
        return False

    # Load previous upload state
    previous_state = load_upload_state()
    new_state = {}

    if force:
        print("Force mode: uploading all files regardless of changes")
    elif previous_state:
        print(f"Found previous upload state with {len(previous_state)} files tracked")
    else:
        print("No previous upload state found, will upload all files")

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
            ensure_remote_directory(ftp, ftp_remote_dir)
            ftp.cwd(f"/{ftp_remote_dir}")
            print(f"Changed to remote directory: {ftp_remote_dir}")

        # Check if local directory exists
        local_path = Path(local_dir)
        if not local_path.exists():
            print(f"Error: Local directory '{local_dir}' does not exist.")
            return False

        print(f"\nUploading files from: {local_dir}")
        print("Excluding: images/, fonts/ (at root only)")
        print("Excluding: data/events.*.json, data/locations.*.json")

        # Directories to exclude at root level only
        root_exclude_dirs = {'images', 'fonts'}

        # Specific files to exclude (relative paths from public_html)
        exclude_files = {
            'data/events.full.json',
            'data/events.init.json',
            'data/locations.full.json',
            'data/locations.init.json',
        }

        # Upload directory contents
        uploaded_count, skipped_count, total_count = upload_directory(
            ftp,
            local_dir,
            ftp_remote_dir,
            root_exclude_dirs,
            exclude_files,
            is_root=True,
            previous_state=previous_state,
            new_state=new_state,
            force=force
        )

        print(f"\nUploaded {uploaded_count} files, skipped {skipped_count} unchanged files ({total_count} total)")

        # Save the new state
        save_upload_state(new_state)
        print(f"Saved upload state to {STATE_FILE}")

        # Close FTP connection
        ftp.quit()
        return True

    except Exception as e:
        print(f"\nFTP Error: {e}")
        return False


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Upload public_html files to FTP server (smart upload - only changed files)"
    )
    parser.add_argument(
        '--force', '-f',
        action='store_true',
        help='Force upload all files, ignoring modification times'
    )
    parser.add_argument(
        '--tls',
        action='store_true',
        help='Use FTPS (FTP over TLS) instead of plain FTP'
    )
    parser.add_argument(
        '--remote-dir',
        help='Remote directory on FTP server (overrides FTP_REMOTE_DIR env var)'
    )

    args = parser.parse_args()

    success = main(remote_dir=args.remote_dir, use_tls=args.tls, force=args.force)
    sys.exit(0 if success else 1)

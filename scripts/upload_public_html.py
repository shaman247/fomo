"""
Upload Script

Builds the project and uploads dist/ to the server's public_html/ directory via FTP.

Smart Upload:
- Runs `npm run build` automatically before uploading
- Tracks file content hashes in upload_state.json
- Only uploads files whose content has changed since the last upload
- Use --force to upload all files regardless of state
- Use --skip-build to skip the build step
- Gates a changed app bundle (app.*.js or index.html differs from the last
  upload) on `npm test` + scripts/frontend_smoke.py; data-only uploads skip it.
  --skip-frontend-checks overrides the gate.

The similarity model (dist/data/similarity/) is never uploaded here: a new
generation goes live only through the gated `pipeline/similarity_publish.py`.

Configuration:
- FTP credentials should be set in .env file:
  FTP_HOST, PUBLIC_HTML_FTP_USER, FTP_PASSWORD, FTP_REMOTE_DIR (optional)

Usage:
    python upload_public_html.py                # Build + upload changed files
    python upload_public_html.py --force        # Build + upload all files
    python upload_public_html.py --skip-build   # Upload only (no build)
    python upload_public_html.py --skip-frontend-checks  # Upload a changed bundle untested
"""

import hashlib
import json
import os
import subprocess
import sys
import uuid
from ftplib import FTP, FTP_TLS
from pathlib import Path
from dotenv import load_dotenv


# Get the directory where this script is located
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
STATE_FILE = os.path.join(SCRIPT_DIR, 'upload_state.json')
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)
# Published only by pipeline/similarity_publish.py, after its release gates pass.
GATED_DIRS = ('data/similarity',)


def get_file_hash(file_path):
    """Get MD5 hash of file contents."""
    h = hashlib.md5()
    with open(file_path, 'rb') as f:
        for chunk in iter(lambda: f.read(8192), b''):
            h.update(chunk)
    return h.hexdigest()


def upload_file(ftp, local_path, filename):
    """Publish a complete file by renaming a temporary upload on the same server."""
    temporary = f'.{filename}.{uuid.uuid4().hex}.upload'
    try:
        with open(local_path, 'rb') as file:
            ftp.storbinary(f'STOR {temporary}', file)
        # Never fall back to deleting/overwriting the live file if rename fails.
        ftp.rename(temporary, filename)
    except Exception:
        try:
            ftp.delete(temporary)
        except Exception:
            pass
        raise


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


def upload_directory(ftp, local_dir, remote_dir, is_root=True,
                     previous_state=None, new_state=None, force=False, exclude=()):
    """
    Recursively upload directory contents to FTP server.
    Skips symlinks (dev mode artifacts).

    Args:
        ftp: FTP connection object
        local_dir: Local directory path
        remote_dir: Remote directory path
        is_root: Whether this is the root directory level
        previous_state: Dict of file paths to previous content hashes
        new_state: Dict to populate with current content hashes
        force: If True, upload all files regardless of content
        exclude: Local directories to leave untouched (their saved state is kept)

    Returns:
        tuple: (uploaded_count, skipped_count, total_count)
    """
    if previous_state is None:
        previous_state = {}
    if new_state is None:
        new_state = {}

    uploaded_count = 0
    skipped_count = 0
    total_count = 0

    local_path = Path(local_dir)

    # Skip symlinks (dev mode artifacts)
    if local_path.is_symlink():
        return 0, 0, 0

    # Ensure we're in the correct remote directory for this level
    ftp.cwd(f"/{remote_dir}")

    # Separate files and directories
    items = sorted(local_path.iterdir())
    files = [item for item in items if item.is_file()]
    directories = [item for item in items if item.is_dir() and not item.is_symlink()]

    excluded = {Path(path).resolve() for path in exclude}

    # Upload nested assets before pointers in this directory.
    for item in directories:
        subdir_name = item.name
        new_remote_dir = f"{remote_dir}/{subdir_name}" if remote_dir else subdir_name

        if item.resolve() in excluded:
            print(f"  Skipping gated directory: {subdir_name}/")
            new_state.update({k: v for k, v in previous_state.items() if k.startswith(f"{new_remote_dir}/")})
            continue

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

        # Upload subdirectory contents
        sub_uploaded, sub_skipped, sub_total = upload_directory(
            ftp, item, new_remote_dir,
            is_root=False, previous_state=previous_state, new_state=new_state, force=force,
            exclude=exclude
        )
        uploaded_count += sub_uploaded
        skipped_count += sub_skipped
        total_count += sub_total

        # Change back to current directory after processing subdirectory
        ftp.cwd(f"/{remote_dir}")

    # Publish parent files only after their nested assets are complete. In
    # particular, similarity/manifest.json must follow its generation directory.
    for item in files:
        filename = item.name
        remote_file_path = f"{remote_dir}/{filename}" if remote_dir else filename

        total_count += 1

        # Get current content hash
        current_hash = get_file_hash(item)
        previous_hash = previous_state.get(remote_file_path)

        # Check if file has changed
        if not force and previous_hash is not None and current_hash == previous_hash:
            new_state[remote_file_path] = current_hash
            skipped_count += 1
            continue

        try:
            status = "(new)" if previous_hash is None else "(modified)"
            if force and previous_hash is not None and current_hash == previous_hash:
                status = "(forced)"
            print(f"  - Uploading {remote_file_path} {status}...", end=' ', flush=True)

            upload_file(ftp, item, filename)
            new_state[remote_file_path] = current_hash

            print("✓")
            uploaded_count += 1

        except Exception as e:
            print(f"✗ Error: {e}")
            # Stop before publishing dependent files and leave the saved upload
            # state unchanged so the next run retries this failed publication.
            raise

    return uploaded_count, skipped_count, total_count


def run_build():
    """Run npm run build and return True if successful."""
    project_root = os.path.join(SCRIPT_DIR, '..')
    print("Running npm run build...")
    result = subprocess.run(
        ['npm', 'run', 'build'],
        cwd=project_root,
    )
    if result.returncode != 0:
        print("Build failed!")
        return False
    print("Build succeeded.\n")
    return True


def bundle_changed(local_dir, previous_state, remote_dir):
    """True when the app bundle (app.*.js or index.html) differs from the last upload.

    Bundle filenames are content-hashed, so a new app.<hash>.js name means new
    code; index.html covers markup and the bundle reference. Data, images and
    other assets don't count — daily data uploads stay fast.
    """
    prefix = f"{remote_dir}/" if remote_dir else ''
    local_path = Path(local_dir)
    local_bundles = {f"{prefix}{p.name}" for p in local_path.glob('app.*.js')}
    uploaded_bundles = {k for k in previous_state
                        if k.startswith(f"{prefix}app.") and k.endswith('.js') and '/' not in k[len(prefix):]}
    if local_bundles != uploaded_bundles:
        return True
    index = local_path / 'index.html'
    return index.exists() and previous_state.get(f"{prefix}index.html") != get_file_hash(index)


def run_frontend_checks(local_dir):
    """Run the JS unit tests and the browser smoke matrix; True if both pass."""
    venv_python = os.path.join(PROJECT_ROOT, 'venv', 'bin', 'python')
    python = venv_python if os.path.exists(venv_python) else sys.executable
    checks = [
        ('JS unit tests', ['npm', 'test', '--silent']),
        ('browser smoke matrix', [python, os.path.join(SCRIPT_DIR, 'frontend_smoke.py'), '--dist', local_dir]),
    ]
    for label, command in checks:
        print(f"Frontend gate: {label}...")
        if subprocess.run(command, cwd=PROJECT_ROOT).returncode != 0:
            print(f"\nFrontend gate FAILED ({label}); nothing uploaded.")
            print("Fix it, or re-run with --skip-frontend-checks to upload anyway.")
            return False
        print()
    print("Frontend gate passed.\n")
    return True


def main(remote_dir=None, use_tls=False, force=False, skip_build=False, skip_frontend_checks=False):
    """
    Build the project and upload dist/ contents to the server via FTP.

    Args:
        remote_dir: Remote directory on FTP server (optional)
        use_tls: Whether to use FTPS (FTP over TLS) instead of plain FTP
        force: If True, upload all files regardless of modification time
        skip_build: If True, skip the build step
        skip_frontend_checks: If True, upload a changed bundle without the test gate

    Returns:
        bool: True if upload was successful, False otherwise
    """
    load_dotenv()

    if not skip_build:
        if not run_build():
            return False

    local_dir = os.path.join(SCRIPT_DIR, '..', 'dist')

    ftp_host = os.getenv('FTP_HOST')
    ftp_user = os.getenv('PUBLIC_HTML_FTP_USER')
    ftp_password = os.getenv('FTP_PASSWORD')
    ftp_remote_dir = remote_dir or os.getenv('FTP_REMOTE_DIR', '')

    if not all([ftp_host, ftp_user, ftp_password]):
        print("\nError: FTP credentials not found in .env file.")
        print("Please set FTP_HOST, PUBLIC_HTML_FTP_USER, and FTP_PASSWORD in your .env file.")
        return False

    # Load previous upload state
    previous_state = {}
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, 'r') as f:
                previous_state = json.load(f)
        except (json.JSONDecodeError, IOError):
            pass
    new_state = {}

    new_bundle = bundle_changed(local_dir, previous_state, ftp_remote_dir)
    if new_bundle:
        if skip_frontend_checks:
            print("App bundle changed; frontend gate SKIPPED (--skip-frontend-checks)\n")
        elif not run_frontend_checks(local_dir):
            return False
    else:
        print("App bundle unchanged since last upload; frontend gate not needed")

    if force:
        print("Force mode: uploading all files")
    elif previous_state:
        print(f"Found previous upload state with {len(previous_state)} files tracked")
    else:
        print("No previous upload state found, will upload all files")

    try:
        print(f"Connecting to FTP server: {ftp_host}")

        # Connect to FTP server. Pass a socket timeout so a stalled network
        # connection (control or data) raises instead of blocking the upload
        # forever — ftplib defaults to no timeout.
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
            ensure_remote_directory(ftp, ftp_remote_dir)
            ftp.cwd(f"/{ftp_remote_dir}")
            print(f"Changed to remote directory: {ftp_remote_dir}")

        # Check if dist/ directory exists
        local_path = Path(local_dir)
        if not local_path.exists():
            print("Error: dist/ directory does not exist.")
            print("Hint: Run 'npm run build' first to generate the dist/ directory.")
            return False

        print(f"\nUploading files from: {local_dir}")

        # Upload directory contents
        uploaded_count, skipped_count, total_count = upload_directory(
            ftp,
            local_dir,
            ftp_remote_dir,
            is_root=True,
            previous_state=previous_state,
            new_state=new_state,
            force=force,
            exclude=[local_path / gated for gated in GATED_DIRS]
        )

        print(f"\nUploaded {uploaded_count} files, skipped {skipped_count} unchanged files ({total_count} total)")
        print("Similarity model not uploaded; publish it with pipeline/similarity_publish.py")

        # Save the new state
        with open(STATE_FILE, 'w') as f:
            json.dump(new_state, f, indent=2, sort_keys=True)
        print(f"Saved upload state to {STATE_FILE}")

        if new_bundle:
            bundle_hash = next((p.name[4:-3] for p in Path(local_dir).glob('app.*.js')), '')
            print("\nNew app bundle is live. Tomorrow, review what real devices report from it:")
            print(f"  ./venv/bin/python scripts/client_errors.py --days 1 --bundle {bundle_hash}")

        # Close FTP connection
        ftp.quit()
        return True

    except Exception as e:
        print(f"\nFTP Error: {e}")
        return False


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Build project and upload dist/ to FTP server (smart upload - only changed files)"
    )
    parser.add_argument(
        '--force', '-f',
        action='store_true',
        help='Force upload all files, ignoring content hashes'
    )
    parser.add_argument(
        '--skip-build',
        action='store_true',
        help='Skip the build step (upload existing dist/ as-is)'
    )
    parser.add_argument(
        '--skip-frontend-checks',
        action='store_true',
        help='Upload a changed app bundle without running npm test + the browser smoke matrix'
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

    success = main(remote_dir=args.remote_dir, use_tls=args.tls, force=args.force, skip_build=args.skip_build,
                   skip_frontend_checks=args.skip_frontend_checks)
    sys.exit(0 if success else 1)

#!/usr/bin/env python3
"""
Sync local database to production via SSH.

Exports local tables and imports them to the production server.
This is the opposite of sync_feedback.py - it pushes data UP to production.

Tables synced (source of truth lives locally):
- locations, location_tags, location_alternate_names, location_instagram
- websites, website_locations, website_tags, website_urls, website_instagram
- events, event_occurrences, event_tags, event_urls, event_sources
- tags, tag_rules, instagram_accounts
- crawl_runs, crawl_results, crawl_events, crawl_event_occurrences, crawl_event_tags

Tables NOT synced (production is source of truth):
- feedback (user submissions, synced DOWN via sync_feedback.py)

Usage:
    python scripts/sync_to_production.py
    python scripts/sync_to_production.py --dry-run  # Show what would be synced
    python scripts/sync_to_production.py --tables locations,tags  # Sync specific tables
    python scripts/sync_to_production.py --create-tables  # Include CREATE TABLE statements
    python scripts/sync_to_production.py --include-crawl  # Include crawl_* tables (large)

Requirements:
    - SSH access to production server
    - MySQL/MariaDB installed locally (XAMPP)
    - SSH key configured (or will prompt for password)

Environment variables (in .env):
    SSH_HOST - SSH hostname (e.g., server123.web-hosting.com)
    SSH_USER - SSH username (e.g., fomoowsq)
    SSH_PORT - SSH port (default: 21098 for Namecheap)
    SSH_KEY - Path to SSH private key (relative to project root)
    PROD_DB_NAME - Production database name
    PROD_DB_USER - Production database user
    PROD_DB_PASS - Production database password
"""

import argparse
import os
import sys
import subprocess
from pathlib import Path

# Add project root to path for .env loading
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv
load_dotenv(PROJECT_ROOT / '.env')

# SSH Configuration
SSH_HOST = os.getenv('SSH_HOST', '')
SSH_USER = os.getenv('SSH_USER', '')
SSH_PORT = os.getenv('SSH_PORT', '21098')
SSH_KEY = os.getenv('SSH_KEY', '')

# Production database (remote)
PROD_DB = {
    'name': os.getenv('PROD_DB_NAME', 'fomoowsq_fomo'),
    'user': os.getenv('PROD_DB_USER', 'fomoowsq_root'),
    'password': os.getenv('PROD_DB_PASS', ''),
}

# Local database (XAMPP)
LOCAL_DB = {
    'host': 'localhost',
    'name': 'fomo',
    'user': 'root',
    'password': '',
}

# Path to mysql executables (detect platform)
import platform
if platform.system() == 'Darwin':  # macOS
    MYSQL_PATH = os.getenv('MYSQL_PATH', '/Applications/XAMPP/xamppfiles/bin/mysql')
    MYSQLDUMP_PATH = os.getenv('MYSQLDUMP_PATH', '/Applications/XAMPP/xamppfiles/bin/mysqldump')
else:  # Windows
    MYSQL_PATH = os.getenv('MYSQL_PATH', r'C:\xampp\mysql\bin\mysql.exe')
    MYSQLDUMP_PATH = os.getenv('MYSQLDUMP_PATH', r'C:\xampp\mysql\bin\mysqldump.exe')

# Tables to sync (order matters for foreign key constraints)
SYNC_TABLES = [
    # Core reference tables first
    'tags',
    'tag_rules',
    'instagram_accounts',
    # User accounts (for edit tracking)
    'users',
    # Locations
    'locations',
    'location_tags',
    'location_alternate_names',
    'location_instagram',
    # Websites
    'websites',
    'website_locations',
    'website_tags',
    'website_urls',
    'website_instagram',
    # Events (depend on locations, websites, tags)
    'events',
    'event_occurrences',
    'event_tags',
    'event_urls',
    'event_sources',
    # Edit history and sync (depend on users)
    'edits',
    'sync_state',
    'conflicts',
]

# Crawl tables (optional, large)
CRAWL_TABLES = [
    'crawl_runs',
    'crawl_results',
    'crawl_events',
    'crawl_event_occurrences',
    'crawl_event_tags',
]


def run_command(cmd, capture_output=True, input_data=None, encoding='utf-8'):
    """Run a command and return output."""
    try:
        result = subprocess.run(
            cmd,
            capture_output=capture_output,
            text=True,
            input=input_data,
            shell=True,
            encoding=encoding,
            errors='replace'  # Replace undecodable bytes instead of failing
        )
        return result.returncode == 0, result.stdout, result.stderr
    except Exception as e:
        return False, '', str(e)


def get_ssh_opts():
    """Build SSH options string."""
    ssh_opts = f'-p {SSH_PORT}'
    if SSH_KEY:
        key_path = PROJECT_ROOT / SSH_KEY
        ssh_opts += f' -i "{key_path}"'
    return ssh_opts


def dump_local_tables(tables, create_tables=False, full_sync=False):
    """Dump specified tables from local database to a temp file.

    Args:
        tables: List of table names to dump
        create_tables: Include CREATE TABLE statements
        full_sync: If True, delete all data from tables first (makes local the source of truth)
    """
    print(f"Dumping {len(tables)} tables from local database...")

    tables_str = ' '.join(tables)
    temp_file = PROJECT_ROOT / 'scripts' / 'temp_sync.sql'

    # Build mysqldump options
    # --no-create-info: skip CREATE TABLE (unless --create-tables is used)
    # Write directly to file to avoid encoding issues with large dumps
    opts = ''
    if not create_tables:
        opts += ' --no-create-info'

    dump_cmd = (
        f'"{MYSQLDUMP_PATH}" -u {LOCAL_DB["user"]} '
        f'{LOCAL_DB["name"]} {tables_str} '
        f'{opts} '
        f'--result-file="{temp_file}"'
    )

    if LOCAL_DB['password']:
        dump_cmd = (
            f'"{MYSQLDUMP_PATH}" -u {LOCAL_DB["user"]} -p{LOCAL_DB["password"]} '
            f'{LOCAL_DB["name"]} {tables_str} '
            f'{opts} '
            f'--result-file="{temp_file}"'
        )

    success, _, stderr = run_command(dump_cmd)

    if not success:
        print(f"mysqldump failed: {stderr}")
        return None

    if not temp_file.exists() or temp_file.stat().st_size == 0:
        print("Warning: No data returned from dump")
        return None

    # If full_sync, prepend DELETE statements to clear tables first
    # Delete in reverse order to respect foreign key constraints
    if full_sync:
        print("Adding DELETE statements for full sync...")
        delete_statements = ["SET FOREIGN_KEY_CHECKS=0;"]
        for table in reversed(tables):
            delete_statements.append(f"DELETE FROM `{table}`;")
        delete_statements.append("SET FOREIGN_KEY_CHECKS=1;")
        delete_sql = "\n".join(delete_statements) + "\n\n"

        # Read existing dump and prepend delete statements
        with open(temp_file, 'r', encoding='utf-8', errors='replace') as f:
            dump_content = f.read()
        with open(temp_file, 'w', encoding='utf-8') as f:
            f.write(delete_sql + dump_content)

    size_mb = temp_file.stat().st_size / (1024 * 1024)
    print(f"Dump complete: {size_mb:.1f} MB")

    return temp_file


def count_rows_per_table(tables):
    """Get row counts for each table locally."""
    counts = {}
    for table in tables:
        mysql_cmd = f'"{MYSQL_PATH}" -u {LOCAL_DB["user"]} {LOCAL_DB["name"]} -N -e "SELECT COUNT(*) FROM {table}"'
        success, stdout, stderr = run_command(mysql_cmd)
        if success:
            counts[table] = stdout.strip()
        else:
            counts[table] = '?'
    return counts


def push_to_production(temp_file):
    """Push SQL dump file to production database via SSH."""
    print(f"Connecting to {SSH_USER}@{SSH_HOST}:{SSH_PORT}...")

    try:
        # Build the remote mysql command
        remote_cmd = (
            f"mysql -u {PROD_DB['user']} -p'{PROD_DB['password']}' {PROD_DB['name']}"
        )

        # Use scp to copy the file, then ssh to run mysql
        ssh_opts = get_ssh_opts()

        # First, copy the SQL file to remote
        print("Uploading SQL dump to production server...")
        scp_cmd = f'scp {ssh_opts.replace("-p", "-P")} "{temp_file}" {SSH_USER}@{SSH_HOST}:/tmp/sync_data.sql'
        success, _, stderr = run_command(scp_cmd)

        if not success:
            print(f"SCP failed: {stderr}")
            return False

        # Then run mysql on the remote server
        print("Importing data on production server...")
        ssh_cmd = f'ssh {ssh_opts} {SSH_USER}@{SSH_HOST} "{remote_cmd} < /tmp/sync_data.sql && rm /tmp/sync_data.sql"'
        success, _, stderr = run_command(ssh_cmd)

        if not success:
            print(f"Remote import failed: {stderr}")
            return False

        print("Import successful!")
        return True

    finally:
        # Clean up local temp file
        if temp_file.exists():
            temp_file.unlink()


def validate_config():
    """Validate required configuration."""
    errors = []

    if not SSH_HOST or not SSH_USER:
        errors.append("SSH_HOST and SSH_USER must be set in .env")

    if not PROD_DB['password']:
        errors.append("PROD_DB_PASS must be set in .env")

    if not Path(MYSQL_PATH).exists():
        errors.append(f"MySQL not found at {MYSQL_PATH}")

    if not Path(MYSQLDUMP_PATH).exists():
        errors.append(f"mysqldump not found at {MYSQLDUMP_PATH}")

    return errors


def main():
    parser = argparse.ArgumentParser(description='Sync local database to production')
    parser.add_argument('--dry-run', action='store_true',
                        help='Show what would be synced without actually syncing')
    parser.add_argument('--tables', type=str,
                        help='Comma-separated list of specific tables to sync')
    parser.add_argument('--create-tables', action='store_true',
                        help='Include CREATE TABLE statements (for new tables)')
    parser.add_argument('--include-crawl', action='store_true',
                        help='Include crawl_* tables (large, ~780k rows)')
    parser.add_argument('--full-sync', action='store_true',
                        help='Delete all data from tables before inserting (makes local the source of truth)')
    args = parser.parse_args()

    # Validate configuration
    errors = validate_config()
    if errors:
        print("Configuration errors:")
        for error in errors:
            print(f"  - {error}")
        print("\nAdd missing values to your .env file")
        sys.exit(1)

    # Determine which tables to sync
    all_valid_tables = SYNC_TABLES + CRAWL_TABLES
    if args.tables:
        tables = [t.strip() for t in args.tables.split(',')]
        # Validate table names
        invalid = [t for t in tables if t not in all_valid_tables]
        if invalid:
            print(f"Invalid table names: {', '.join(invalid)}")
            print(f"Valid tables: {', '.join(all_valid_tables)}")
            sys.exit(1)
    else:
        tables = SYNC_TABLES.copy()
        if args.include_crawl:
            tables.extend(CRAWL_TABLES)

    print(f"Tables to sync: {', '.join(tables)}")
    if args.full_sync:
        print("Mode: FULL SYNC (will DELETE all data first, local becomes source of truth)")
    elif args.create_tables:
        print("Mode: CREATE + INSERT (will create tables if missing)")
    else:
        print("Mode: INSERT only (will add/update rows but not delete)")
    print()

    # Show row counts
    print("Local row counts:")
    counts = count_rows_per_table(tables)
    for table, count in counts.items():
        print(f"  {table}: {count} rows")
    print()

    if args.dry_run:
        print("Dry run complete. Use without --dry-run to actually sync.")
        return

    # Confirm before syncing
    response = input("Proceed with sync to production? [y/N] ")
    if response.lower() != 'y':
        print("Sync cancelled.")
        return

    print()

    # Dump local tables to temp file
    dump_file = dump_local_tables(tables, create_tables=args.create_tables, full_sync=args.full_sync)
    if dump_file is None:
        sys.exit(1)

    # Push to production
    if push_to_production(dump_file):
        print(f"\nSync complete! {len(tables)} tables synced to production.")
    else:
        sys.exit(1)


if __name__ == '__main__':
    main()

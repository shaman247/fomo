#!/usr/bin/env python3
"""
Sync feedback from production database to local database via SSH.

Uses SSH to run mysqldump on the remote server and imports the data locally.

Usage:
    python scripts/sync_feedback.py

Requirements:
    - SSH access to production server
    - MySQL installed locally (XAMPP includes this)
    - SSH key configured or will prompt for password

Environment variables (in .env):
    SSH_HOST - SSH hostname (e.g., server123.web-hosting.com)
    SSH_USER - SSH username (e.g., fomoowsq)
    SSH_PORT - SSH port (default: 21098 for Namecheap)
    PROD_DB_NAME - Production database name
    PROD_DB_USER - Production database user
    PROD_DB_PASS - Production database password
"""

import os
import sys
import subprocess
import tempfile
from pathlib import Path

# Add project root to path for .env loading
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv
load_dotenv(PROJECT_ROOT / '.env')

# SSH Configuration
SSH_HOST = os.getenv('SSH_HOST', '')
SSH_USER = os.getenv('SSH_USER', '')
SSH_PORT = os.getenv('SSH_PORT', '21098')  # Namecheap default SSH port
SSH_KEY = os.getenv('SSH_KEY', '')  # Path to SSH private key (relative to project root)

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

# Path to mysql executable (XAMPP on Windows)
MYSQL_PATH = os.getenv('MYSQL_PATH', r'C:\xampp\mysql\bin\mysql.exe')


def run_command(cmd, capture_output=True, input_data=None):
    """Run a command and return output."""
    try:
        result = subprocess.run(
            cmd,
            capture_output=capture_output,
            text=True,
            input=input_data,
            shell=True
        )
        return result.returncode == 0, result.stdout, result.stderr
    except Exception as e:
        return False, '', str(e)


def dump_remote_feedback():
    """SSH into production and dump the feedback table."""
    print(f"Connecting to {SSH_USER}@{SSH_HOST}:{SSH_PORT}...")

    # Build mysqldump command to run remotely
    remote_cmd = (
        f"mysqldump -u {PROD_DB['user']} -p'{PROD_DB['password']}' "
        f"{PROD_DB['name']} feedback --no-create-info --replace"
    )

    # SSH command with optional key file
    ssh_opts = f'-p {SSH_PORT}'
    if SSH_KEY:
        key_path = PROJECT_ROOT / SSH_KEY
        ssh_opts += f' -i "{key_path}"'

    ssh_cmd = f'ssh {ssh_opts} {SSH_USER}@{SSH_HOST} "{remote_cmd}"'

    print("Dumping feedback table from production...")
    success, stdout, stderr = run_command(ssh_cmd)

    if not success:
        print(f"SSH/mysqldump failed: {stderr}")
        return None

    if not stdout.strip():
        print("No data returned (table might be empty)")
        return None

    return stdout


def import_to_local(sql_data):
    """Import SQL dump into local database."""
    print("Importing to local database...")

    # Filter out mysqldump warnings and MariaDB-specific lines from the SQL data
    lines = sql_data.split('\n')
    filtered_lines = []
    for line in lines:
        # Skip mysqldump warnings
        if line.startswith('mysqldump: [Warning]') or line.startswith('mysqldump:'):
            continue
        # Skip MariaDB sandbox mode line (causes "Unknown command '\-'" error in MySQL)
        if 'enable the sandbox mode' in line:
            continue
        filtered_lines.append(line)
    sql_data = '\n'.join(filtered_lines)

    # Write SQL to temp file (more reliable on Windows than piping)
    temp_file = PROJECT_ROOT / 'scripts' / 'temp_feedback.sql'
    try:
        with open(temp_file, 'w', encoding='utf-8') as f:
            f.write(sql_data)

        # Build mysql import command
        mysql_cmd = f'"{MYSQL_PATH}" -u {LOCAL_DB["user"]} {LOCAL_DB["name"]} < "{temp_file}"'

        if LOCAL_DB['password']:
            mysql_cmd = f'"{MYSQL_PATH}" -u {LOCAL_DB["user"]} -p{LOCAL_DB["password"]} {LOCAL_DB["name"]} < "{temp_file}"'

        success, stdout, stderr = run_command(mysql_cmd)

        if not success:
            print(f"Import failed: {stderr}")
            return False

        print("Import successful!")
        return True

    finally:
        # Clean up temp file
        if temp_file.exists():
            temp_file.unlink()


def count_local_feedback():
    """Count feedback entries in local database."""
    mysql_cmd = f'"{MYSQL_PATH}" -u {LOCAL_DB["user"]} {LOCAL_DB["name"]} -e "SELECT COUNT(*) FROM feedback"'
    success, stdout, stderr = run_command(mysql_cmd)

    if success:
        lines = stdout.strip().split('\n')
        if len(lines) > 1:
            return lines[1].strip()
    return '?'


def main():
    # Validate configuration
    if not SSH_HOST or not SSH_USER:
        print("Error: SSH_HOST and SSH_USER must be set in .env")
        print("\nAdd these to your .env file:")
        print("  SSH_HOST=server123.web-hosting.com")
        print("  SSH_USER=fomoowsq")
        print("  SSH_PORT=21098")
        print("  PROD_DB_NAME=fomoowsq_fomo")
        print("  PROD_DB_USER=fomoowsq_root")
        print("  PROD_DB_PASS=your_password")
        sys.exit(1)

    if not PROD_DB['password']:
        print("Error: PROD_DB_PASS must be set in .env")
        sys.exit(1)

    # Check if mysql exists
    if not Path(MYSQL_PATH).exists():
        print(f"Error: MySQL not found at {MYSQL_PATH}")
        print("Set MYSQL_PATH in .env if XAMPP is installed elsewhere")
        sys.exit(1)

    # Dump from production
    sql_data = dump_remote_feedback()
    if sql_data is None:
        sys.exit(1)

    # Import locally
    if import_to_local(sql_data):
        count = count_local_feedback()
        print(f"\nSync complete! Local database now has {count} feedback entries.")
    else:
        sys.exit(1)


if __name__ == '__main__':
    main()

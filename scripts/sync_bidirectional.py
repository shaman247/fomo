#!/usr/bin/env python3
"""
Bidirectional Database Sync

Syncs edits between local and production databases using the edit log.
Detects and queues conflicts for manual review.

Usage:
    python scripts/sync_bidirectional.py
    python scripts/sync_bidirectional.py --dry-run     # Show what would sync
    python scripts/sync_bidirectional.py --pull-only   # Only pull from production
    python scripts/sync_bidirectional.py --push-only   # Only push to production
    python scripts/sync_bidirectional.py --status      # Show sync status

Requirements:
    - SSH access to production server (or direct API access)
    - Local MySQL running (XAMPP)
"""

import argparse
import json
import os
import sys
from pathlib import Path
from datetime import datetime

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

try:
    import mysql.connector
    from mysql.connector import Error
except ImportError:
    print("Error: mysql-connector-python required")
    print("Install with: pip install mysql-connector-python")
    sys.exit(1)

try:
    import requests
except ImportError:
    print("Error: requests required")
    print("Install with: pip install requests")
    sys.exit(1)

from dotenv import load_dotenv
load_dotenv(PROJECT_ROOT / '.env')

# Import edit logger
sys.path.insert(0, str(PROJECT_ROOT / 'database'))
from edit_logger import EditLogger, get_edit_logger

# Configuration
LOCAL_DB = {
    'host': 'localhost',
    'database': 'fomo',
    'user': 'root',
    'password': ''
}

# Production API URL
PROD_API_URL = os.getenv('PROD_API_URL', 'https://fomo.nyc/api')
SYNC_API_KEY = os.getenv('SYNC_API_KEY', 'fomo-sync-key-change-in-production')


def create_connection():
    """Create local database connection."""
    try:
        return mysql.connector.connect(**LOCAL_DB)
    except Error as e:
        print(f"Error connecting to local database: {e}")
        return None


def get_local_edits_since(cursor, since_id: int, limit: int = 1000):
    """Get local edits since a given ID."""
    cursor.execute("""
        SELECT id, edit_uuid, table_name, record_id, field_name, action,
               old_value, new_value, source, user_id, editor_ip,
               editor_user_agent, editor_info, created_at, applied_at
        FROM edits
        WHERE id > %s AND source = 'local'
        ORDER BY id ASC
        LIMIT %s
    """, (since_id, limit))

    columns = [
        'id', 'edit_uuid', 'table_name', 'record_id', 'field_name', 'action',
        'old_value', 'new_value', 'source', 'user_id', 'editor_ip',
        'editor_user_agent', 'editor_info', 'created_at', 'applied_at'
    ]

    edits = []
    for row in cursor.fetchall():
        edit = dict(zip(columns, row))
        # Convert datetime to string for JSON
        if edit['created_at']:
            edit['created_at'] = edit['created_at'].isoformat()
        if edit['applied_at']:
            edit['applied_at'] = edit['applied_at'].isoformat()
        edits.append(edit)

    return edits


def get_sync_state(cursor, source: str):
    """Get last synced edit ID for a source."""
    cursor.execute("""
        SELECT last_synced_edit_id, last_sync_at
        FROM sync_state WHERE source = %s
    """, (source,))
    row = cursor.fetchone()
    if row:
        return {'last_edit_id': row[0] or 0, 'last_sync_at': row[1]}
    return {'last_edit_id': 0, 'last_sync_at': None}


def update_sync_state(cursor, connection, source: str, edit_id: int):
    """Update last synced edit ID for a source."""
    cursor.execute("""
        INSERT INTO sync_state (source, last_synced_edit_id, last_sync_at)
        VALUES (%s, %s, NOW())
        ON DUPLICATE KEY UPDATE last_synced_edit_id = %s, last_sync_at = NOW()
    """, (source, edit_id, edit_id))
    connection.commit()


def fetch_remote_edits(since_id: int, limit: int = 1000):
    """Fetch edits from production API."""
    try:
        response = requests.get(
            f"{PROD_API_URL}/sync.php",
            params={'since': since_id, 'source': 'website', 'limit': limit},
            headers={'X-Sync-Key': SYNC_API_KEY},
            timeout=30
        )
        response.raise_for_status()
        data = response.json()

        if not data.get('success'):
            print(f"API error: {data.get('error', 'Unknown error')}")
            return []

        return data.get('edits', [])

    except requests.RequestException as e:
        print(f"Error fetching remote edits: {e}")
        return []


def push_edits_to_remote(edits: list):
    """Push edits to production API."""
    if not edits:
        return {'applied': 0, 'skipped': 0, 'conflicts': 0}

    try:
        response = requests.post(
            f"{PROD_API_URL}/sync.php",
            json={'edits': edits},
            headers={
                'Content-Type': 'application/json',
                'X-Sync-Key': SYNC_API_KEY
            },
            timeout=60
        )
        response.raise_for_status()
        data = response.json()

        if not data.get('success'):
            print(f"API error: {data.get('error', 'Unknown error')}")
            return {'applied': 0, 'skipped': len(edits), 'conflicts': 0}

        return {
            'applied': data.get('applied', 0),
            'skipped': data.get('skipped', 0),
            'conflicts': data.get('conflicts', 0)
        }

    except requests.RequestException as e:
        print(f"Error pushing edits: {e}")
        return {'applied': 0, 'skipped': len(edits), 'conflicts': 0}


def check_for_conflict(cursor, incoming_edit: dict):
    """Check if an incoming edit conflicts with a local edit."""
    cursor.execute("""
        SELECT e.*, ss.last_synced_edit_id
        FROM edits e
        LEFT JOIN sync_state ss ON ss.source = 'website'
        WHERE e.table_name = %s
          AND e.record_id = %s
          AND e.field_name = %s
          AND e.source = 'local'
          AND e.id > COALESCE(ss.last_synced_edit_id, 0)
        ORDER BY e.id DESC
        LIMIT 1
    """, (
        incoming_edit['table_name'],
        incoming_edit['record_id'],
        incoming_edit.get('field_name')
    ))

    local_edit = cursor.fetchone()

    if local_edit and local_edit[7] != incoming_edit.get('new_value'):
        # Conflict detected
        return {
            'local_edit': local_edit,
            'remote_edit': incoming_edit
        }

    return None


def apply_edit(cursor, connection, edit: dict):
    """Apply an edit to the local database."""
    table_name = edit['table_name']
    record_id = edit['record_id']
    action = edit['action']

    # Validate table name
    valid_tables = [
        'locations', 'location_alternate_names', 'location_tags',
        'websites', 'website_urls', 'website_locations', 'website_tags',
        'events', 'event_occurrences', 'event_urls', 'event_tags',
        'tags', 'tag_rules'
    ]

    if table_name not in valid_tables:
        return False

    try:
        if action == 'UPDATE':
            field_name = edit.get('field_name')
            new_value = edit.get('new_value')

            if not field_name or not field_name.replace('_', '').isalnum():
                return False

            cursor.execute(
                f"UPDATE `{table_name}` SET `{field_name}` = %s WHERE id = %s",
                (new_value, record_id)
            )

        elif action == 'DELETE':
            cursor.execute(
                f"DELETE FROM `{table_name}` WHERE id = %s",
                (record_id,)
            )

        elif action == 'INSERT':
            # INSERT is more complex - skip for now
            return False

        # Record the edit
        cursor.execute("""
            INSERT INTO edits (
                edit_uuid, table_name, record_id, field_name, action,
                old_value, new_value, source, editor_info, applied_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, 'website', 'synced', NOW())
            ON DUPLICATE KEY UPDATE applied_at = NOW()
        """, (
            edit['edit_uuid'],
            table_name,
            record_id,
            edit.get('field_name'),
            action,
            edit.get('old_value'),
            edit.get('new_value')
        ))

        connection.commit()
        return True

    except Error as e:
        print(f"Error applying edit: {e}")
        connection.rollback()
        return False


def record_conflict(cursor, connection, local_edit, remote_edit):
    """Record a conflict for manual review."""
    # First insert the remote edit
    cursor.execute("""
        INSERT INTO edits (
            edit_uuid, table_name, record_id, field_name, action,
            old_value, new_value, source, editor_info
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, 'website', 'synced-conflict')
    """, (
        remote_edit['edit_uuid'],
        remote_edit['table_name'],
        remote_edit['record_id'],
        remote_edit.get('field_name'),
        remote_edit['action'],
        remote_edit.get('old_value'),
        remote_edit.get('new_value')
    ))
    remote_edit_id = cursor.lastrowid

    # Record the conflict
    local_edit_id = local_edit[0]  # id is first column
    cursor.execute("""
        INSERT INTO conflicts (
            local_edit_id, website_edit_id, table_name, record_id, field_name,
            local_value, website_value, status
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, 'pending')
    """, (
        local_edit_id,
        remote_edit_id,
        remote_edit['table_name'],
        remote_edit['record_id'],
        remote_edit.get('field_name'),
        local_edit[7],  # new_value
        remote_edit.get('new_value')
    ))

    connection.commit()


def show_status(cursor):
    """Show sync status."""
    print("\n=== Sync Status ===\n")

    # Sync state
    cursor.execute("SELECT source, last_synced_edit_id, last_sync_at FROM sync_state")
    rows = cursor.fetchall()
    print("Sync State:")
    if rows:
        for source, last_id, last_sync in rows:
            print(f"  {source}: last_edit_id={last_id or 0}, last_sync={last_sync or 'never'}")
    else:
        print("  No sync state recorded")

    # Edit counts
    cursor.execute("""
        SELECT source, COUNT(*) as count, MAX(id) as max_id
        FROM edits GROUP BY source
    """)
    rows = cursor.fetchall()
    print("\nEdit Counts:")
    if rows:
        for source, count, max_id in rows:
            print(f"  {source}: {count} edits, max_id={max_id}")
    else:
        print("  No edits recorded")

    # Pending conflicts
    cursor.execute("SELECT COUNT(*) FROM conflicts WHERE status = 'pending'")
    pending = cursor.fetchone()[0]
    print(f"\nPending Conflicts: {pending}")

    if pending > 0:
        cursor.execute("""
            SELECT table_name, record_id, field_name, local_value, website_value
            FROM conflicts WHERE status = 'pending' LIMIT 5
        """)
        print("\nRecent conflicts:")
        for row in cursor.fetchall():
            print(f"  {row[0]}.{row[1]}.{row[2]}")
            print(f"    local: {row[3][:50] if row[3] else 'null'}...")
            print(f"    website: {row[4][:50] if row[4] else 'null'}...")


def sync(dry_run=False, pull_only=False, push_only=False):
    """Run bidirectional sync."""
    connection = create_connection()
    if not connection:
        return False

    cursor = connection.cursor()

    try:
        # Get sync state
        local_state = get_sync_state(cursor, 'local')
        website_state = get_sync_state(cursor, 'website')

        print(f"Local last synced: {local_state['last_edit_id']}")
        print(f"Website last synced: {website_state['last_edit_id']}")

        # PULL: Get edits from production
        if not push_only:
            print("\n--- Pulling from production ---")
            remote_edits = fetch_remote_edits(website_state['last_edit_id'])
            print(f"Fetched {len(remote_edits)} edits from production")

            if remote_edits:
                applied = 0
                conflicts = 0
                skipped = 0

                for edit in remote_edits:
                    # Check for conflict
                    if edit['action'] == 'UPDATE':
                        conflict = check_for_conflict(cursor, edit)
                        if conflict:
                            if not dry_run:
                                record_conflict(cursor, connection,
                                              conflict['local_edit'], conflict['remote_edit'])
                            conflicts += 1
                            print(f"  Conflict: {edit['table_name']}.{edit['record_id']}.{edit.get('field_name')}")
                            continue

                    # Apply edit
                    if dry_run:
                        print(f"  Would apply: {edit['action']} {edit['table_name']}.{edit['record_id']}")
                        applied += 1
                    else:
                        if apply_edit(cursor, connection, edit):
                            applied += 1
                        else:
                            skipped += 1

                # Update sync state
                if not dry_run and remote_edits:
                    max_id = max(e['id'] for e in remote_edits)
                    update_sync_state(cursor, connection, 'website', max_id)

                print(f"Applied: {applied}, Conflicts: {conflicts}, Skipped: {skipped}")

        # PUSH: Send local edits to production
        if not pull_only:
            print("\n--- Pushing to production ---")
            local_edits = get_local_edits_since(cursor, local_state['last_edit_id'])
            print(f"Found {len(local_edits)} local edits to push")

            if local_edits:
                if dry_run:
                    for edit in local_edits:
                        print(f"  Would push: {edit['action']} {edit['table_name']}.{edit['record_id']}")
                    print(f"Would push {len(local_edits)} edits")
                else:
                    result = push_edits_to_remote(local_edits)
                    print(f"Applied: {result['applied']}, Skipped: {result['skipped']}, Conflicts: {result['conflicts']}")

                    # Update sync state
                    if result['applied'] > 0:
                        max_id = max(e['id'] for e in local_edits)
                        update_sync_state(cursor, connection, 'local', max_id)

        print("\n--- Sync complete ---")
        return True

    except Error as e:
        print(f"Database error: {e}")
        return False
    finally:
        cursor.close()
        connection.close()


def main():
    parser = argparse.ArgumentParser(description='Bidirectional database sync')
    parser.add_argument('--dry-run', action='store_true',
                        help='Show what would sync without actually syncing')
    parser.add_argument('--pull-only', action='store_true',
                        help='Only pull edits from production')
    parser.add_argument('--push-only', action='store_true',
                        help='Only push edits to production')
    parser.add_argument('--status', action='store_true',
                        help='Show sync status')
    args = parser.parse_args()

    if args.status:
        connection = create_connection()
        if connection:
            cursor = connection.cursor()
            show_status(cursor)
            cursor.close()
            connection.close()
        return

    if args.pull_only and args.push_only:
        print("Error: Cannot use --pull-only and --push-only together")
        sys.exit(1)

    success = sync(
        dry_run=args.dry_run,
        pull_only=args.pull_only,
        push_only=args.push_only
    )

    sys.exit(0 if success else 1)


if __name__ == '__main__':
    main()

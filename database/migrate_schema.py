#!/usr/bin/env python3
"""
Schema Migration Script

Compares the current database schema against schema.sql and applies any missing
columns, indexes, or tables.

Usage:
    python migrate_schema.py
    python migrate_schema.py --dry-run  # Show what would be changed without applying
"""

import argparse
import os
import re
import sys
from pathlib import Path

try:
    import mysql.connector
    from mysql.connector import Error
except ImportError:
    print("Error: mysql-connector-python is required.")
    print("Install it with: pip install mysql-connector-python")
    sys.exit(1)


# Database Configuration
DB_CONFIG = {
    'local': {
        'host': 'localhost',
        'database': 'fomo',
        'user': 'root',
        'password': ''
    },
    'production': {
        'host': 'localhost',
        'database': 'fomoowsq_fomo',
        'user': 'fomoowsq_root',
        'password': 'REDACTED_DB_PASSWORD'
    }
}

SCRIPT_DIR = Path(__file__).parent
SCHEMA_FILE = SCRIPT_DIR / 'schema.sql'


def get_db_config():
    """Get database config based on environment."""
    env = os.environ.get('FOMO_ENV', 'local')
    if env not in DB_CONFIG:
        env = 'local'
    return DB_CONFIG[env]


def create_connection():
    """Create database connection."""
    config = get_db_config()
    try:
        return mysql.connector.connect(
            host=config['host'],
            database=config['database'],
            user=config['user'],
            password=config['password']
        )
    except Error as e:
        print(f"Error connecting to database: {e}")
        return None


def get_current_schema(cursor):
    """Get current database schema as a structured dict."""
    schema = {'tables': {}}

    # Get all tables
    cursor.execute("""
        SELECT TABLE_NAME FROM information_schema.TABLES
        WHERE TABLE_SCHEMA = DATABASE() AND TABLE_TYPE = 'BASE TABLE'
    """)
    tables = [row[0] for row in cursor.fetchall()]

    for table in tables:
        schema['tables'][table] = {
            'columns': {},
            'indexes': {},
            'auto_increment': None
        }

        # Get columns
        cursor.execute("""
            SELECT COLUMN_NAME, COLUMN_TYPE, IS_NULLABLE, COLUMN_DEFAULT, EXTRA, COLUMN_COMMENT
            FROM information_schema.COLUMNS
            WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = %s
            ORDER BY ORDINAL_POSITION
        """, (table,))

        for row in cursor.fetchall():
            col_name = row[0]
            schema['tables'][table]['columns'][col_name] = {
                'type': row[1],
                'nullable': row[2] == 'YES',
                'default': row[3],
                'extra': row[4],
                'comment': row[5]
            }
            if 'auto_increment' in (row[4] or '').lower():
                schema['tables'][table]['auto_increment'] = col_name

        # Get indexes
        cursor.execute("""
            SELECT INDEX_NAME, GROUP_CONCAT(COLUMN_NAME ORDER BY SEQ_IN_INDEX) as columns,
                   NON_UNIQUE
            FROM information_schema.STATISTICS
            WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = %s
            GROUP BY INDEX_NAME, NON_UNIQUE
        """, (table,))

        for row in cursor.fetchall():
            schema['tables'][table]['indexes'][row[0]] = {
                'columns': row[1].split(','),
                'unique': row[2] == 0
            }

    return schema


def parse_schema_sql():
    """Parse schema.sql to extract expected schema."""
    with open(SCHEMA_FILE, 'r') as f:
        content = f.read()

    schema = {'tables': {}}

    # Find all CREATE TABLE statements
    table_pattern = re.compile(
        r'CREATE TABLE IF NOT EXISTS (\w+)\s*\((.*?)\)\s*ENGINE',
        re.DOTALL | re.IGNORECASE
    )

    for match in table_pattern.finditer(content):
        table_name = match.group(1)
        table_body = match.group(2)

        schema['tables'][table_name] = {
            'columns': {},
            'indexes': {},
            'auto_increment': None
        }

        # Parse columns and indexes from table body
        lines = [line.strip() for line in table_body.split('\n') if line.strip()]

        for line in lines:
            # Remove trailing comma
            line = line.rstrip(',')

            # Skip empty lines and comments
            if not line or line.startswith('--'):
                continue

            # Parse INDEX/KEY definitions
            idx_match = re.match(
                r'(?:UNIQUE\s+)?(?:INDEX|KEY)\s+(\w+)\s*\(([^)]+)\)',
                line, re.IGNORECASE
            )
            if idx_match:
                idx_name = idx_match.group(1)
                idx_cols = [c.strip().split('(')[0] for c in idx_match.group(2).split(',')]
                schema['tables'][table_name]['indexes'][idx_name] = {
                    'columns': idx_cols,
                    'unique': 'UNIQUE' in line.upper()
                }
                continue

            # Parse UNIQUE KEY
            unique_match = re.match(
                r'UNIQUE KEY\s+(\w+)\s*\(([^)]+)\)',
                line, re.IGNORECASE
            )
            if unique_match:
                idx_name = unique_match.group(1)
                idx_cols = [c.strip() for c in unique_match.group(2).split(',')]
                schema['tables'][table_name]['indexes'][idx_name] = {
                    'columns': idx_cols,
                    'unique': True
                }
                continue

            # Skip FOREIGN KEY definitions
            if line.upper().startswith('FOREIGN KEY'):
                continue

            # Parse column definitions
            col_match = re.match(
                r'(\w+)\s+([A-Z]+(?:\([^)]+\))?(?:\s+UNSIGNED)?)',
                line, re.IGNORECASE
            )
            if col_match:
                col_name = col_match.group(1)
                col_type = col_match.group(2).lower()

                # Check for AUTO_INCREMENT
                if 'auto_increment' in line.lower():
                    schema['tables'][table_name]['auto_increment'] = col_name

                # Check for NOT NULL
                nullable = 'NOT NULL' not in line.upper()

                # Extract default value
                default_match = re.search(r"DEFAULT\s+('.*?'|NULL|\d+|TRUE|FALSE|CURRENT_TIMESTAMP)", line, re.IGNORECASE)
                default = default_match.group(1) if default_match else None

                # Extract comment
                comment_match = re.search(r"COMMENT\s+'([^']*)'", line, re.IGNORECASE)
                comment = comment_match.group(1) if comment_match else ''

                schema['tables'][table_name]['columns'][col_name] = {
                    'type': col_type,
                    'nullable': nullable,
                    'default': default,
                    'comment': comment,
                    'full_definition': line
                }

    return schema


def generate_migrations(current, expected):
    """Compare schemas and generate migration SQL statements."""
    migrations = []

    # Check for missing tables
    for table_name in expected['tables']:
        if table_name not in current['tables']:
            migrations.append((
                f"Table {table_name} is missing - run setup.py or restore from backup",
                None  # Can't easily generate CREATE TABLE from parsed data
            ))
            continue

        current_table = current['tables'][table_name]
        expected_table = expected['tables'][table_name]

        # Check for missing columns
        prev_col = None
        for col_name, col_info in expected_table['columns'].items():
            if col_name not in current_table['columns']:
                # Build ADD COLUMN statement
                col_def = col_info['full_definition']
                # Remove trailing comma if present
                col_def = col_def.rstrip(',')

                after_clause = f" AFTER {prev_col}" if prev_col else " FIRST"
                sql = f"ALTER TABLE {table_name} ADD COLUMN {col_def}{after_clause}"

                migrations.append((
                    f"Add column {table_name}.{col_name}",
                    sql
                ))

            prev_col = col_name

        # Check for missing indexes
        for idx_name, idx_info in expected_table['indexes'].items():
            if idx_name not in current_table['indexes']:
                cols = ', '.join(idx_info['columns'])
                if idx_info['unique']:
                    sql = f"ALTER TABLE {table_name} ADD UNIQUE KEY {idx_name} ({cols})"
                else:
                    sql = f"ALTER TABLE {table_name} ADD INDEX {idx_name} ({cols})"

                migrations.append((
                    f"Add index {table_name}.{idx_name}",
                    sql
                ))

        # Check for AUTO_INCREMENT
        if expected_table['auto_increment'] and not current_table['auto_increment']:
            col_name = expected_table['auto_increment']
            # Get max ID first
            migrations.append((
                f"Convert {table_name}.{col_name} to AUTO_INCREMENT",
                f"__AUTO_INCREMENT__{table_name}__{col_name}"  # Special marker
            ))

    return migrations


def run_migrations(cursor, connection, migrations, dry_run=False):
    """Execute migration statements."""
    if not migrations:
        print("No migrations needed - schema is up to date.")
        return True

    print(f"{'[DRY RUN] ' if dry_run else ''}Found {len(migrations)} migration(s)...\n")

    for description, sql in migrations:
        if sql is None:
            print(f"  [SKIP] {description}")
            continue

        # Handle AUTO_INCREMENT specially
        if sql and sql.startswith('__AUTO_INCREMENT__'):
            _, table, col = sql.split('__')[2:5]
            cursor.execute(f"SELECT MAX(id) FROM {table}")
            max_id = cursor.fetchone()[0] or 0
            sql = f"ALTER TABLE {table} MODIFY {col} INT UNSIGNED NOT NULL AUTO_INCREMENT, AUTO_INCREMENT = {max_id + 1}"

        if dry_run:
            print(f"  [WOULD RUN] {description}")
            print(f"    SQL: {sql}")
        else:
            try:
                print(f"  - {description}...")
                cursor.execute(sql)
                connection.commit()
                print(f"    [OK]")
            except Error as e:
                print(f"    [ERROR] {e}")
                return False

    return True


def main():
    parser = argparse.ArgumentParser(description='Migrate database schema')
    parser.add_argument('--dry-run', action='store_true',
                        help='Show what would be changed without applying')
    args = parser.parse_args()

    print("Schema Migration")
    print("=" * 40)

    if not SCHEMA_FILE.exists():
        print(f"Error: schema.sql not found at {SCHEMA_FILE}")
        sys.exit(1)

    connection = create_connection()
    if not connection:
        sys.exit(1)

    cursor = connection.cursor()

    try:
        print("Parsing schema.sql...")
        expected_schema = parse_schema_sql()
        print(f"  Found {len(expected_schema['tables'])} tables in schema.sql")

        print("Reading current database schema...")
        current_schema = get_current_schema(cursor)
        print(f"  Found {len(current_schema['tables'])} tables in database")

        print("\nComparing schemas...")
        migrations = generate_migrations(current_schema, expected_schema)

        success = run_migrations(cursor, connection, migrations, dry_run=args.dry_run)

        if success:
            if args.dry_run:
                print("\n[DRY RUN] No changes made.")
            else:
                print("\n[OK] Migration complete!")
        else:
            print("\n[ERROR] Some migrations failed.")
            sys.exit(1)

    except Error as e:
        print(f"\nDatabase error: {e}")
        sys.exit(1)
    finally:
        cursor.close()
        connection.close()


if __name__ == '__main__':
    main()

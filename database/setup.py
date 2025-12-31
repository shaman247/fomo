#!/usr/bin/env python3
"""
Database Setup Script for fomo.nyc

Creates the database schema. Run this once when initially setting up the project.
For existing data, restore from a backup instead (see README.md).

Usage:
    python setup.py [--drop-tables]

Options:
    --drop-tables      Drop existing tables before creating (WARNING: deletes data)
"""

import argparse
import os
import sys
from pathlib import Path

try:
    import mysql.connector
    from mysql.connector import Error
except ImportError:
    print("Error: mysql-connector-python is required.")
    print("Install it with: pip install mysql-connector-python")
    sys.exit(1)


# Configuration - matches public_html/api/config.php
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

# Paths
SCRIPT_DIR = Path(__file__).parent
SCHEMA_FILE = SCRIPT_DIR / 'schema.sql'

# Tables in order for dropping (respects foreign keys)
ALL_TABLES = [
    # Crawl data (must be dropped before events)
    'event_sources',
    'crawl_event_tags',
    'crawl_event_occurrences',
    'crawl_events',
    'crawl_results',
    'crawl_runs',
    # Events
    'event_tags',
    'location_tags',
    'event_urls',
    'event_occurrences',
    'events',
    # Websites and locations
    'website_locations',
    'website_urls',
    'websites',
    'location_alternate_names',
    'locations',
    'tags'
]


def get_db_config():
    """Get database config based on environment."""
    env = os.environ.get('FOMO_ENV', 'local')
    if env not in DB_CONFIG:
        print(f"Warning: Unknown environment '{env}', using 'local'")
        env = 'local'
    return DB_CONFIG[env]


def create_connection(with_database=True):
    """Create database connection."""
    config = get_db_config()
    conn_params = {
        'host': config['host'],
        'user': config['user'],
        'password': config['password']
    }
    if with_database:
        conn_params['database'] = config['database']

    try:
        connection = mysql.connector.connect(**conn_params)
        return connection
    except Error as e:
        print(f"Error connecting to database: {e}")
        return None


def create_database():
    """Create database if it doesn't exist."""
    config = get_db_config()
    connection = create_connection(with_database=False)
    if not connection:
        return False

    try:
        cursor = connection.cursor()
        cursor.execute(
            f"CREATE DATABASE IF NOT EXISTS {config['database']} "
            "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
        )
        print(f"Database '{config['database']}' ready.")
        return True
    except Error as e:
        print(f"Error creating database: {e}")
        return False
    finally:
        cursor.close()
        connection.close()


def drop_tables(connection):
    """Drop all tables."""
    cursor = connection.cursor()
    try:
        for table in ALL_TABLES:
            cursor.execute(f"DROP TABLE IF EXISTS {table}")
            print(f"  Dropped table: {table}")
        connection.commit()
        return True
    except Error as e:
        print(f"Error dropping tables: {e}")
        return False
    finally:
        cursor.close()


def create_schema(connection):
    """Create tables from schema.sql."""
    cursor = connection.cursor()

    try:
        with open(SCHEMA_FILE, 'r') as f:
            schema_sql = f.read()

        # Remove SQL comments
        lines = []
        for line in schema_sql.split('\n'):
            # Remove full-line comments
            stripped = line.strip()
            if stripped.startswith('--'):
                continue
            # Remove inline comments
            if '--' in line:
                line = line[:line.index('--')]
            lines.append(line)
        schema_sql = '\n'.join(lines)

        # Split by semicolons and execute each statement
        statements = schema_sql.split(';')
        for statement in statements:
            statement = statement.strip()
            if not statement:
                continue
            if statement.upper().startswith('CREATE DATABASE'):
                continue
            if statement.upper().startswith('USE '):
                continue

            try:
                cursor.execute(statement)
            except Error as e:
                # Ignore "table already exists" errors
                if e.errno != 1050:
                    print(f"Warning: {e}")

        connection.commit()
        print("Schema created successfully.")
        return True
    except Error as e:
        print(f"Error creating schema: {e}")
        return False
    finally:
        cursor.close()


def show_stats(connection):
    """Show database statistics."""
    cursor = connection.cursor()
    try:
        tables = [
            ('locations', 'Locations'),
            ('websites', 'Websites'),
            ('events', 'Events'),
            ('tags', 'Unique tags'),
            ('crawl_runs', 'Crawl runs'),
            ('crawl_results', 'Crawl results'),
        ]

        print("\n--- Database Statistics ---")
        for table, label in tables:
            try:
                cursor.execute(f"SELECT COUNT(*) FROM {table}")
                count = cursor.fetchone()[0]
                print(f"{label}: {count}")
            except Error:
                pass  # Table might not exist

    except Error as e:
        print(f"Error getting stats: {e}")
    finally:
        cursor.close()


def main():
    parser = argparse.ArgumentParser(description='Setup fomo.nyc database schema')
    parser.add_argument('--drop-tables', action='store_true',
                        help='Drop existing tables before creating (WARNING: deletes data)')
    args = parser.parse_args()

    print("fomo.nyc Database Setup")
    print("=" * 40)

    # Create database if needed
    if not create_database():
        sys.exit(1)

    # Connect to database
    connection = create_connection()
    if not connection:
        sys.exit(1)

    try:
        # Drop tables if requested
        if args.drop_tables:
            print("\nDropping existing tables...")
            if not drop_tables(connection):
                sys.exit(1)

        # Create schema
        print("\nCreating schema...")
        if not create_schema(connection):
            sys.exit(1)

        # Show stats
        show_stats(connection)

        print("\nSetup complete!")
        print("\nTo populate the database, restore from a backup:")
        print("  mysql -u root fomo < database/backups/fomo_backup_YYYYMMDD.sql")

    finally:
        connection.close()


if __name__ == '__main__':
    main()

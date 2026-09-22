"""Transactional location consolidation, also used by scripts/merge_locations.php.

Only merge pairs whose venue identity has already been verified. Keeper metadata
is authoritative. Cached explicit IDs are repaired; unassigned text is retained
and remains resolvable through the duplicate's canonical-name alias.
"""

import argparse
from collections import Counter
from contextlib import nullcontext
import json
from pathlib import Path
import sys

from db import create_connection
from dblock import write_lock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'database'))
from edit_logger import EditLogger


def remap_json(raw, duplicate, keeper, old_name, new_name):
    """Change explicit location references, never arbitrary matching text/numbers."""
    if raw is None or raw == '':
        return raw
    value = json.loads(raw)

    def walk(node):
        if isinstance(node, list):
            for child in node:
                walk(child)
        elif isinstance(node, dict):
            ref = node.get('location_id')
            if type(ref) is int and ref == duplicate or isinstance(ref, str) and ref == str(duplicate):
                node['location_id'] = str(keeper) if isinstance(ref, str) else keeper
                for field in ('location', 'location_name'):
                    if node.get(field) == old_name:
                        node[field] = new_name
            for child in node.values():
                walk(child)

    before = json.dumps(value, ensure_ascii=False)
    walk(value)
    after = json.dumps(value, ensure_ascii=False)
    return raw if before == after else after


def merge_link_metadata(keeper, duplicate):
    existing, incoming = keeper.get('url'), duplicate.get('url')
    if existing and incoming and existing != incoming:
        raise ValueError(f"Website {keeper['website_id']} has conflicting location URLs: {existing!r} / {incoming!r}")
    return dict(is_primary=int(bool(keeper['is_primary'] or duplicate['is_primary'])),
                url=existing or incoming)


def validate_pairs(pairs):
    seen = set()
    for duplicate, keeper in pairs:
        if duplicate <= 0 or keeper <= 0 or duplicate == keeper:
            raise ValueError('Location IDs must be positive and distinct')
        if seen.intersection((duplicate, keeper)):
            raise ValueError('Use disjoint pairs; merge shared keepers or chains in separate invocations')
        seen.update((duplicate, keeper))


def plan_merge(cursor, duplicate, keeper):
    """Return row operations without writes. Caller owns transaction and lock."""
    def rows(sql, args=()):
        cursor.execute(sql, args)
        return cursor.fetchall()

    places = {r['id']: r for r in rows('SELECT * FROM locations WHERE id IN (%s,%s)', (duplicate, keeper))}
    if set(places) != {duplicate, keeper}:
        raise ValueError(f'Missing duplicate or keeper location: {duplicate}:{keeper}')
    old_name, new_name = places[duplicate]['name'], places[keeper]['name']
    operations = []

    def update(table, row, changes):
        changes = {k: v for k, v in changes.items() if row[k] != v}
        if changes:
            operations.append(dict(action='update', table=table, before=row, values=changes))

    def delete(table, row):
        operations.append(dict(action='delete', table=table, before=row))

    for row in rows('SELECT * FROM events WHERE location_id=%s', (duplicate,)):
        changes = dict(location_id=keeper)
        if row['location_name'] == old_name:
            changes['location_name'] = new_name
        update('events', row, changes)

    # Prefilter by key, then parse and compare IDs. This also repairs stale cache
    # references whose relational location_id was already cleared or repointed.
    pattern = '"location_id"[[:space:]]*:[[:space:]]*"?' + str(duplicate) + '"?[[:space:]]*[,}]'
    for table, field in (('crawl_events', 'raw_data'), ('crawl_results', 'extracted_content')):
        predicate = f'{field} REGEXP %s'
        args = (pattern,)
        if table == 'crawl_events':
            predicate = f'location_id=%s OR ({predicate})'
            args = (duplicate, pattern)
        for row in rows(f'SELECT * FROM {table} WHERE {predicate}', args):
            try:
                rewritten = remap_json(row[field], duplicate, keeper, old_name, new_name)
            except (ValueError, TypeError) as exc:
                raise ValueError(f"Invalid JSON in {table}.{field}, row {row['id']}") from exc
            changes = {field: rewritten}
            if table == 'crawl_events' and row['location_id'] == duplicate:
                changes['location_id'] = keeper
                if row['location_name'] == old_name:
                    changes['location_name'] = new_name
            update(table, row, changes)

    for row in rows('SELECT * FROM website_locations WHERE location_id=%s', (duplicate,)):
        collision = rows('SELECT * FROM website_locations WHERE location_id=%s AND website_id=%s',
                         (keeper, row['website_id']))
        if collision:
            update('website_locations', collision[0], merge_link_metadata(collision[0], row))
            delete('website_locations', row)
        else:
            update('website_locations', row, dict(location_id=keeper))

    for table, key in (('location_tags', 'tag_id'), ('location_instagram', 'instagram_id')):
        for row in rows(f'SELECT * FROM {table} WHERE location_id=%s', (duplicate,)):
            collision = rows(f'SELECT * FROM {table} WHERE location_id=%s AND {key}=%s', (keeper, row[key]))
            if collision:
                delete(table, row)
            else:
                update(table, row, dict(location_id=keeper))

    for row in rows('SELECT * FROM location_alternate_names WHERE location_id=%s ORDER BY id', (duplicate,)):
        # Use the database collation and null-safe scope equality, including
        # duplicate aliases within the source location itself.
        survivor = rows('''SELECT id FROM location_alternate_names
            WHERE location_id IN (%s,%s) AND alternate_name=%s AND website_id <=> %s
            ORDER BY (location_id=%s) DESC, id LIMIT 1''',
            (duplicate, keeper, row['alternate_name'], row['website_id'], keeper))[0]
        if survivor['id'] != row['id']:
            delete('location_alternate_names', row)
        else:
            update('location_alternate_names', row, dict(location_id=keeper))
    if old_name != new_name and not rows('''SELECT id FROM location_alternate_names
            WHERE location_id IN (%s,%s) AND alternate_name=%s AND website_id IS NULL''',
            (duplicate, keeper, old_name)):
        operations.append(dict(action='insert', table='location_alternate_names',
                               values=dict(location_id=keeper, alternate_name=old_name, website_id=None)))
    delete('locations', places[duplicate])
    return operations


def apply_plan(cursor, connection, operations):
    logger = EditLogger(cursor, connection, editor_info='merge_locations')
    for op in operations:
        table, action = op['table'], op['action']
        row, values = op.get('before', {}), op.get('values', {})
        keys = ('location_id', 'instagram_id') if table == 'location_instagram' else ('id',)
        where = ' AND '.join(f'{key}=%s' for key in keys)
        identity = tuple(row.get(key) for key in keys)
        if action == 'insert':
            cursor.execute(f"INSERT INTO {table} ({','.join(values)}) VALUES ({','.join(['%s'] * len(values))})", tuple(values.values()))
            logger.log_insert(table, cursor.lastrowid, values)
        elif action == 'delete':
            cursor.execute(f'DELETE FROM {table} WHERE {where}', identity)
            if cursor.rowcount != 1:
                raise RuntimeError(f'Merge lost its expected {table} row: {identity}')
            logger.log_delete(table, row.get('id'), row)
        else:
            cursor.execute(f"UPDATE {table} SET {','.join(f'{key}=%s' for key in values)} WHERE {where}",
                           tuple(values.values()) + identity)
            if cursor.rowcount != 1:
                raise RuntimeError(f'Merge lost its expected {table} row: {identity}')
            for field, value in values.items():
                logger.log_update(table, row.get('id'), field, row[field], value)


def merge_locations(connection, pairs, *, dry_run=False, lock_timeout=600):
    """Own one transaction for all pairs; refuse an existing caller transaction."""
    validate_pairs(pairs)
    if connection.in_transaction:
        raise ValueError('Use a fresh connection with no active transaction')
    context = nullcontext() if dry_run else write_lock(connection, timeout=lock_timeout, label='merge_locations')
    with context:
        cursor = None
        try:
            cursor = connection.cursor(dictionary=True)
            # MariaDB's compatibility version prefix confuses mysql.connector's
            # readonly version gate; issue supported SQL directly.
            cursor.execute('START TRANSACTION READ ONLY' if dry_run else 'START TRANSACTION')
            operations = []
            for duplicate, keeper in pairs:
                pair_operations = plan_merge(cursor, duplicate, keeper)
                operations.extend(pair_operations)
                # Different venue pairs can share one extraction cache. Plan
                # each against the preceding changes within this transaction.
                if not dry_run:
                    apply_plan(cursor, connection, pair_operations)
            if not dry_run:
                connection.commit()
            else:
                connection.rollback()
            return dict(dry_run=dry_run, pairs=pairs, changes=dict(Counter(
                f"{op['table']}.{op['action']}" for op in operations)))
        except BaseException:
            connection.rollback()
            raise
        finally:
            if cursor is not None:
                cursor.close()


def parse_pair(value):
    try:
        duplicate, keeper = map(int, value.split(':'))
        validate_pairs([(duplicate, keeper)])
        return duplicate, keeper
    except ValueError as exc:
        raise argparse.ArgumentTypeError('Expected positive, distinct DUPLICATE:KEEPER IDs') from exc


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pair', type=parse_pair, action='append', default=[], help='Verified duplicate:keeper IDs; repeat for disjoint pairs')
    parser.add_argument('--dry-run', '-n', action='store_true', help='Read-only preview, including cache and link changes')
    args = parser.parse_args()
    if not args.pair:
        print('No merge pairs configured. Use --pair DUPLICATE:KEEPER.')
        return 0
    from agent_run import singleton
    connection = None
    try:
        validate_pairs(args.pair)
        with nullcontext() if args.dry_run else singleton():
            connection = create_connection()
            result = merge_locations(connection, args.pair, dry_run=args.dry_run)
        print(json.dumps(result, indent=2))
        return 0
    except Exception as exc:
        print(f'Location merge failed: {exc}', file=sys.stderr)
        return 1
    finally:
        if connection is not None:
            connection.close()


if __name__ == '__main__':
    sys.exit(main())

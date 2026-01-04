"""
Edit Logger Module

Logs all changes to core tables for sync and audit purposes.
Each edit is stored as an immutable log entry with a UUID for global uniqueness.
"""

import uuid
from datetime import datetime
from typing import Optional, Dict, Any, List


class EditLogger:
    """
    Logs edits to the database for sync and audit tracking.

    Usage:
        logger = EditLogger(cursor, connection)
        logger.log_insert('locations', 123, {'name': 'Central Park', 'lat': 40.785091})
        logger.log_update('locations', 123, 'name', 'Central Park', 'Central Park NYC')
        logger.log_delete('locations', 123, {'name': 'Central Park', ...})
    """

    # Tables that should have edits logged
    TRACKED_TABLES = {
        'locations', 'location_alternate_names', 'location_tags',
        'websites', 'website_urls', 'website_locations', 'website_tags',
        'events', 'event_occurrences', 'event_urls', 'event_tags',
        'tags', 'tag_rules'
    }

    def __init__(self, cursor, connection, source: str = 'local', editor_info: str = None):
        """
        Initialize the edit logger.

        Args:
            cursor: Database cursor
            connection: Database connection
            source: Origin of edits ('local', 'website', or 'crawl')
            editor_info: Additional context (e.g., 'crawl_run:123', 'admin')
        """
        self.cursor = cursor
        self.connection = connection
        self.source = source
        self.editor_info = editor_info
        self.user_id = None
        self.editor_ip = None
        self.editor_user_agent = None

    def set_user_context(self, user_id: int = None, ip: str = None, user_agent: str = None):
        """Set user context for attribution."""
        self.user_id = user_id
        self.editor_ip = ip
        self.editor_user_agent = user_agent

    def _generate_uuid(self) -> str:
        """Generate a UUID for the edit."""
        return str(uuid.uuid4())

    def _serialize_value(self, value: Any) -> Optional[str]:
        """Convert a value to string for storage."""
        if value is None:
            return None
        if isinstance(value, (datetime,)):
            return value.isoformat()
        if isinstance(value, (dict, list)):
            import json
            return json.dumps(value, default=str)
        return str(value)

    def _insert_edit(self, table_name: str, record_id: int, field_name: Optional[str],
                     action: str, old_value: Any, new_value: Any) -> int:
        """Insert an edit record and return its ID."""
        edit_uuid = self._generate_uuid()

        self.cursor.execute("""
            INSERT INTO edits (
                edit_uuid, table_name, record_id, field_name, action,
                old_value, new_value, source, user_id, editor_ip,
                editor_user_agent, editor_info, applied_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
        """, (
            edit_uuid,
            table_name,
            record_id,
            field_name,
            action,
            self._serialize_value(old_value),
            self._serialize_value(new_value),
            self.source,
            self.user_id,
            self.editor_ip,
            self.editor_user_agent,
            self.editor_info
        ))

        return self.cursor.lastrowid

    def log_insert(self, table_name: str, record_id: int, record_data: Dict[str, Any]) -> int:
        """
        Log an INSERT operation.

        Args:
            table_name: Name of the table
            record_id: ID of the inserted record
            record_data: Dict of field names to values

        Returns:
            Edit ID
        """
        if table_name not in self.TRACKED_TABLES:
            return None

        return self._insert_edit(
            table_name=table_name,
            record_id=record_id,
            field_name=None,
            action='INSERT',
            old_value=None,
            new_value=record_data
        )

    def log_update(self, table_name: str, record_id: int, field_name: str,
                   old_value: Any, new_value: Any) -> int:
        """
        Log an UPDATE operation for a single field.

        Args:
            table_name: Name of the table
            record_id: ID of the updated record
            field_name: Name of the field that changed
            old_value: Previous value
            new_value: New value

        Returns:
            Edit ID
        """
        if table_name not in self.TRACKED_TABLES:
            return None

        # Don't log if value didn't actually change
        if self._serialize_value(old_value) == self._serialize_value(new_value):
            return None

        return self._insert_edit(
            table_name=table_name,
            record_id=record_id,
            field_name=field_name,
            action='UPDATE',
            old_value=old_value,
            new_value=new_value
        )

    def log_updates(self, table_name: str, record_id: int,
                    old_record: Dict[str, Any], new_record: Dict[str, Any]) -> List[int]:
        """
        Log UPDATE operations for multiple fields by comparing old and new records.

        Args:
            table_name: Name of the table
            record_id: ID of the updated record
            old_record: Dict of old field values
            new_record: Dict of new field values

        Returns:
            List of edit IDs
        """
        edit_ids = []

        for field_name, new_value in new_record.items():
            old_value = old_record.get(field_name)
            edit_id = self.log_update(table_name, record_id, field_name, old_value, new_value)
            if edit_id:
                edit_ids.append(edit_id)

        return edit_ids

    def log_delete(self, table_name: str, record_id: int, record_data: Dict[str, Any]) -> int:
        """
        Log a DELETE operation.

        Args:
            table_name: Name of the table
            record_id: ID of the deleted record
            record_data: Dict of field names to values (snapshot before deletion)

        Returns:
            Edit ID
        """
        if table_name not in self.TRACKED_TABLES:
            return None

        return self._insert_edit(
            table_name=table_name,
            record_id=record_id,
            field_name=None,
            action='DELETE',
            old_value=record_data,
            new_value=None
        )

    def get_edits_since(self, since_id: int = 0, source: str = None,
                        limit: int = 1000) -> List[Dict]:
        """
        Get edits since a given edit ID.

        Args:
            since_id: Return edits with ID > since_id
            source: Filter by source ('local', 'website', 'crawl')
            limit: Maximum number of edits to return

        Returns:
            List of edit dicts
        """
        sql = """
            SELECT id, edit_uuid, table_name, record_id, field_name, action,
                   old_value, new_value, source, user_id, editor_ip,
                   editor_user_agent, editor_info, created_at, applied_at
            FROM edits
            WHERE id > %s
        """
        params = [since_id]

        if source:
            sql += " AND source = %s"
            params.append(source)

        sql += " ORDER BY id ASC LIMIT %s"
        params.append(limit)

        self.cursor.execute(sql, params)

        columns = [
            'id', 'edit_uuid', 'table_name', 'record_id', 'field_name', 'action',
            'old_value', 'new_value', 'source', 'user_id', 'editor_ip',
            'editor_user_agent', 'editor_info', 'created_at', 'applied_at'
        ]

        edits = []
        for row in self.cursor.fetchall():
            edit = dict(zip(columns, row))
            # Convert datetime objects to ISO strings for serialization
            if edit['created_at']:
                edit['created_at'] = edit['created_at'].isoformat()
            if edit['applied_at']:
                edit['applied_at'] = edit['applied_at'].isoformat()
            edits.append(edit)

        return edits

    def get_record_history(self, table_name: str, record_id: int) -> List[Dict]:
        """
        Get edit history for a specific record.

        Args:
            table_name: Name of the table
            record_id: ID of the record

        Returns:
            List of edit dicts, newest first
        """
        self.cursor.execute("""
            SELECT e.id, e.edit_uuid, e.field_name, e.action,
                   e.old_value, e.new_value, e.source, e.editor_info,
                   e.created_at, u.display_name as user_name, u.email as user_email
            FROM edits e
            LEFT JOIN users u ON e.user_id = u.id
            WHERE e.table_name = %s AND e.record_id = %s
            ORDER BY e.created_at DESC
        """, (table_name, record_id))

        columns = [
            'id', 'edit_uuid', 'field_name', 'action', 'old_value', 'new_value',
            'source', 'editor_info', 'created_at', 'user_name', 'user_email'
        ]

        edits = []
        for row in self.cursor.fetchall():
            edit = dict(zip(columns, row))
            if edit['created_at']:
                edit['created_at'] = edit['created_at'].isoformat()
            edits.append(edit)

        return edits

    def apply_edit(self, edit: Dict) -> bool:
        """
        Apply an edit from another source to the local database.

        Args:
            edit: Edit dict from get_edits_since()

        Returns:
            True if successfully applied
        """
        table_name = edit['table_name']
        record_id = edit['record_id']
        action = edit['action']

        if table_name not in self.TRACKED_TABLES:
            return False

        try:
            if action == 'UPDATE':
                field_name = edit['field_name']
                new_value = edit['new_value']

                # Apply the update
                self.cursor.execute(
                    f"UPDATE {table_name} SET {field_name} = %s WHERE id = %s",
                    (new_value, record_id)
                )

            elif action == 'DELETE':
                self.cursor.execute(
                    f"DELETE FROM {table_name} WHERE id = %s",
                    (record_id,)
                )

            elif action == 'INSERT':
                # INSERT is more complex - need to handle the full record
                # For now, skip INSERT syncs (they should be handled differently)
                return False

            # Record that we applied this edit
            self.cursor.execute("""
                INSERT INTO edits (
                    edit_uuid, table_name, record_id, field_name, action,
                    old_value, new_value, source, editor_info, applied_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
                ON DUPLICATE KEY UPDATE applied_at = NOW()
            """, (
                edit['edit_uuid'],
                table_name,
                record_id,
                edit.get('field_name'),
                action,
                edit.get('old_value'),
                edit.get('new_value'),
                edit['source'],
                f"synced from {edit['source']}"
            ))

            return True

        except Exception as e:
            print(f"Error applying edit {edit['edit_uuid']}: {e}")
            return False


def get_edit_logger(cursor, connection, source: str = 'local',
                    editor_info: str = None) -> EditLogger:
    """
    Factory function to create an EditLogger.

    Args:
        cursor: Database cursor
        connection: Database connection
        source: Origin of edits ('local', 'website', or 'crawl')
        editor_info: Additional context string

    Returns:
        EditLogger instance
    """
    return EditLogger(cursor, connection, source=source, editor_info=editor_info)

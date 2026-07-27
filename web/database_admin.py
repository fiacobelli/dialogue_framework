"""Admin-facing database reports, table browsing, and exports."""

from __future__ import annotations

import sqlite3
from typing import Any

from . import database as db
from .database_common import _conn, get_db_path


ADMIN_TABLES = {
    'visits': {
        'label': 'Visits',
        'description': 'One row per interview session.',
        'order_by': 'updated_at DESC',
    },
    'messages': {
        'label': 'Messages',
        'description': 'User and assistant turns with timing and task metadata.',
        'order_by': 'created_at DESC',
    },
    'photos': {
        'label': 'Photos',
        'description': 'Uploaded photo metadata; image files are stored separately.',
        'order_by': 'uploaded_at DESC',
    },
    'donor_page_drafts': {
        'label': 'Donor Page Drafts',
        'description': 'Generated donor-page drafts and publication metadata.',
        'order_by': 'generated_at DESC',
    },
    'consents': {
        'label': 'Consents',
        'description': 'Recorded publication and workflow consent events.',
        'order_by': 'created_at DESC',
    },
    'turn_events': {
        'label': 'Client Events',
        'description': 'Browser/app-side events such as microphone and timing events.',
        'order_by': 'created_at DESC',
    },
    'audit_events': {
        'label': 'Audit Events',
        'description': 'Administrative unpublish/delete and lifecycle audit records.',
        'order_by': 'created_at DESC',
    },
}


def list_admin_tables() -> list[dict[str, str]]:
    """Return allowlisted database tables exposed through the admin UI."""
    return [{'name': name, **meta} for name, meta in ADMIN_TABLES.items()]


def _admin_table_meta(table_name: str) -> dict[str, str]:
    if table_name not in ADMIN_TABLES:
        raise ValueError('Unsupported admin table')
    return ADMIN_TABLES[table_name]


def _admin_table_columns(conn, table_name: str) -> list[str]:
    return [row['name'] for row in conn.execute(f'PRAGMA table_info({table_name})').fetchall()]


def get_admin_report() -> dict[str, Any]:
    """Return lightweight aggregate metrics for staff/research review."""
    with _conn() as c:
        totals = c.execute(
            """
            SELECT
                COUNT(*) AS total_sessions,
                SUM(CASE WHEN completed_at IS NOT NULL THEN 1 ELSE 0 END) AS completed_sessions,
                SUM(CASE WHEN publication_status = 'published' THEN 1 ELSE 0 END) AS published_pages,
                SUM(CASE WHEN publication_status = 'unpublished' THEN 1 ELSE 0 END) AS unpublished_pages,
                SUM(CASE WHEN publication_status = 'deleted' THEN 1 ELSE 0 END) AS deleted_sessions,
                SUM(CASE WHEN photo_count > 0 THEN 1 ELSE 0 END) AS sessions_with_photos,
                COALESCE(SUM(photo_count), 0) AS total_photo_slots,
                COALESCE(ROUND(AVG(total_user_turns), 1), 0) AS avg_user_turns,
                COALESCE(ROUND(AVG(total_assistant_turns), 1), 0) AS avg_assistant_turns
            FROM visits
            """
        ).fetchone()
        message_totals = c.execute(
            """
            SELECT
                COUNT(*) AS total_messages,
                SUM(CASE WHEN role = 'user' THEN 1 ELSE 0 END) AS user_messages,
                SUM(CASE WHEN role = 'assistant' THEN 1 ELSE 0 END) AS assistant_messages
            FROM messages
            """
        ).fetchone()
        phase_counts = c.execute(
            """
            SELECT COALESCE(phase, 'unknown') AS label, COUNT(*) AS count
            FROM visits
            GROUP BY COALESCE(phase, 'unknown')
            ORDER BY count DESC, label
            """
        ).fetchall()
        publication_counts = c.execute(
            """
            SELECT COALESCE(publication_status, 'unknown') AS label, COUNT(*) AS count
            FROM visits
            GROUP BY COALESCE(publication_status, 'unknown')
            ORDER BY count DESC, label
            """
        ).fetchall()
        photo_role_counts = c.execute(
            """
            SELECT COALESCE(photo_role, 'unknown') AS label, COUNT(*) AS count
            FROM photos
            WHERE deleted_at IS NULL
            GROUP BY COALESCE(photo_role, 'unknown')
            ORDER BY count DESC, label
            """
        ).fetchall()
    return {
        'totals': dict(totals),
        'message_totals': dict(message_totals),
        'phase_counts': [dict(row) for row in phase_counts],
        'publication_counts': [dict(row) for row in publication_counts],
        'photo_role_counts': [dict(row) for row in photo_role_counts],
        'recent_visits': db.list_admin_visits(limit=10),
        'tables': list_admin_tables(),
    }


def get_admin_table(table_name: str, *, limit: int = 100, offset: int = 0) -> dict[str, Any]:
    """Return a paginated allowlisted table view for admin browsing."""
    meta = _admin_table_meta(table_name)
    limit = max(1, min(int(limit), 500))
    offset = max(0, int(offset))
    with _conn() as c:
        columns = _admin_table_columns(c, table_name)
        total = c.execute(f'SELECT COUNT(*) AS n FROM {table_name}').fetchone()['n']
        rows = c.execute(
            f'SELECT * FROM {table_name} ORDER BY {meta["order_by"]} LIMIT ? OFFSET ?',
            (limit, offset),
        ).fetchall()
    return {
        'name': table_name,
        **meta,
        'columns': columns,
        'rows': [dict(row) for row in rows],
        'total': total,
        'limit': limit,
        'offset': offset,
        'start_index': offset + 1 if total else 0,
        'end_index': min(offset + len(rows), total),
        'next_offset': offset + limit if offset + limit < total else None,
        'prev_offset': max(0, offset - limit) if offset > 0 else None,
    }


def get_admin_table_export(table_name: str) -> tuple[list[str], list[dict[str, Any]]]:
    """Return all rows for an allowlisted table CSV export."""
    meta = _admin_table_meta(table_name)
    with _conn() as c:
        columns = _admin_table_columns(c, table_name)
        rows = c.execute(f'SELECT * FROM {table_name} ORDER BY {meta["order_by"]}').fetchall()
    return columns, [dict(row) for row in rows]


def create_admin_database_backup(destination_path: str) -> str:
    """Create a consistent SQLite backup file for admin download."""
    source_path = get_db_path()
    if not source_path:
        raise RuntimeError('Database path not configured')
    source = sqlite3.connect(source_path)
    destination = sqlite3.connect(destination_path)
    try:
        source.backup(destination)
    finally:
        destination.close()
        source.close()
    return destination_path

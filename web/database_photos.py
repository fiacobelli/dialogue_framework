"""Photo persistence helpers for microsite sessions."""

from __future__ import annotations

from typing import Any

from .database_common import _conn, _now, _normalized_photo_role, _uuid


def reserve_photo_slot(visit_id: str | None, session_id: str, max_photos: int) -> dict[str, Any] | None:
    """Atomically reserve the next available photo display slot for a visit."""
    if not visit_id or not session_id:
        return None
    now = _now()
    with _conn() as c:
        c.execute('BEGIN IMMEDIATE')
        active_rows = c.execute(
            """
            SELECT display_order
            FROM photos
            WHERE visit_id = ? AND deleted_at IS NULL
            ORDER BY display_order
            """,
            (visit_id,),
        ).fetchall()
        used_orders = {int(row['display_order']) for row in active_rows}
        if len(used_orders) >= max_photos:
            return None

        display_order = next((i for i in range(max_photos) if i not in used_orders), None)
        if display_order is None:
            return None

        stored_filename = f'{session_id}_{display_order}.jpg'
        photo_role = _normalized_photo_role(None, display_order)
        c.execute(
            'DELETE FROM photos WHERE visit_id = ? AND display_order = ? AND deleted_at IS NOT NULL',
            (visit_id, display_order),
        )
        c.execute(
            """
            INSERT INTO photos(
                id, visit_id, stored_filename, display_order, source, photo_role, uploaded_at
            ) VALUES (?,?,?,?,?,?,?)
            """,
            (_uuid(), visit_id, stored_filename, display_order, 'reserved', photo_role, now),
        )
        return {
            'stored_filename': stored_filename,
            'display_order': display_order,
            'photo_count': len(used_orders) + 1,
        }


def finalize_photo_upload(
    visit_id: str | None,
    stored_filename: str,
    *,
    source: str = 'unknown',
    mime_type: str | None = None,
    byte_size: int | None = None,
    sha256: str | None = None,
    width: int | None = None,
    height: int | None = None,
) -> int:
    """Mark a reserved photo as uploaded and return the finalized photo count."""
    if not visit_id:
        return 0
    now = _now()
    with _conn() as c:
        c.execute(
            """
            UPDATE photos
            SET source = ?,
                mime_type = ?,
                byte_size = ?,
                sha256 = ?,
                width = ?,
                height = ?,
                uploaded_at = ?
            WHERE visit_id = ?
              AND stored_filename = ?
              AND deleted_at IS NULL
            """,
            (source, mime_type, byte_size, sha256, width, height, now, visit_id, stored_filename),
        )
        count = c.execute(
            """
            SELECT COUNT(*) AS n
            FROM photos
            WHERE visit_id = ?
              AND deleted_at IS NULL
              AND COALESCE(source, '') <> 'reserved'
            """,
            (visit_id,),
        ).fetchone()['n']
        c.execute('UPDATE visits SET photo_count = ?, updated_at = ? WHERE id = ?', (count, now, visit_id))
    return int(count)


def release_photo_reservation(visit_id: str | None, stored_filename: str) -> None:
    """Release a reserved photo slot after validation or file processing fails."""
    if not visit_id:
        return
    with _conn() as c:
        c.execute(
            """
            DELETE FROM photos
            WHERE visit_id = ?
              AND stored_filename = ?
              AND source = 'reserved'
              AND deleted_at IS NULL
            """,
            (visit_id, stored_filename),
        )
        count = c.execute(
            """
            SELECT COUNT(*) AS n
            FROM photos
            WHERE visit_id = ?
              AND deleted_at IS NULL
              AND COALESCE(source, '') <> 'reserved'
            """,
            (visit_id,),
        ).fetchone()['n']
        c.execute('UPDATE visits SET photo_count = ?, updated_at = ? WHERE id = ?', (count, _now(), visit_id))


def list_visit_photo_filenames(visit_id: str | None) -> list[str]:
    """Return finalized, non-deleted photo filenames in display order."""
    if not visit_id:
        return []
    with _conn() as c:
        rows = c.execute(
            """
            SELECT stored_filename
            FROM photos
            WHERE visit_id = ?
              AND deleted_at IS NULL
              AND COALESCE(source, '') <> 'reserved'
            ORDER BY display_order
            """,
            (visit_id,),
        ).fetchall()
    return [row['stored_filename'] for row in rows]


def list_visit_photos(visit_id: str | None) -> list[dict[str, Any]]:
    """Return finalized, non-deleted photo records in display order."""
    if not visit_id:
        return []
    with _conn() as c:
        rows = c.execute(
            """
            SELECT stored_filename, display_order, source, mime_type, byte_size,
                   sha256, width, height, photo_role, caption, uploaded_at
            FROM photos
            WHERE visit_id = ?
              AND deleted_at IS NULL
              AND COALESCE(source, '') <> 'reserved'
            ORDER BY display_order
            """,
            (visit_id,),
        ).fetchall()
    result = []
    for row in rows:
        item = dict(row)
        item['photo_role'] = _normalized_photo_role(item.get('photo_role'), item.get('display_order'))
        result.append(item)
    return result


def update_visit_photo_metadata(visit_id: str | None, items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Update photo roles/order for active photos belonging to one visit."""
    if not visit_id:
        return []
    with _conn() as c:
        existing_rows = c.execute(
            """
            SELECT stored_filename
            FROM photos
            WHERE visit_id = ?
              AND deleted_at IS NULL
              AND COALESCE(source, '') <> 'reserved'
            ORDER BY display_order
            """,
            (visit_id,),
        ).fetchall()
        existing = [row['stored_filename'] for row in existing_rows]
        existing_set = set(existing)

        clean_items = []
        seen = set()
        for item in items or []:
            filename = str((item or {}).get('stored_filename') or '').strip()
            if filename not in existing_set or filename in seen:
                continue
            seen.add(filename)
            clean_items.append({
                'stored_filename': filename,
                'photo_role': _normalized_photo_role((item or {}).get('photo_role')),
                'caption': str((item or {}).get('caption') or '').strip()[:240],
            })

        for filename in existing:
            if filename not in seen:
                clean_items.append({
                    'stored_filename': filename,
                    'photo_role': _normalized_photo_role(None, len(clean_items)),
                    'caption': '',
                })

        now = _now()
        for index, item in enumerate(clean_items):
            c.execute(
                """
                UPDATE photos
                SET display_order = ?
                WHERE visit_id = ? AND stored_filename = ? AND deleted_at IS NULL
                """,
                (-(index + 1), visit_id, item['stored_filename']),
            )
        for index, item in enumerate(clean_items):
            c.execute(
                """
                UPDATE photos
                SET display_order = ?,
                    photo_role = ?,
                    caption = ?
                WHERE visit_id = ? AND stored_filename = ? AND deleted_at IS NULL
                """,
                (index, item['photo_role'], item['caption'], visit_id, item['stored_filename']),
            )
        c.execute('UPDATE visits SET updated_at = ? WHERE id = ?', (now, visit_id))

    return list_visit_photos(visit_id)

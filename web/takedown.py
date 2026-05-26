"""Shared donor-page takedown helpers."""

from __future__ import annotations

import os

from .config import MICROSITES_DIR, PHOTOS_DIR
from . import database as db
from . import session_store

LOGS_DIR = 'logs'


def delete_session(session_id: str, *, reason: str, actor: str) -> dict | None:
    """Delete public/private runtime artifacts and mark DB state deleted."""
    result = db.soft_delete_session(session_id, reason=reason, actor=actor)
    if not result:
        return None

    html_path = os.path.join(MICROSITES_DIR, f'{session_id}.html')
    removed_html = False
    try:
        if os.path.exists(html_path):
            os.remove(html_path)
            removed_html = True
    except OSError as e:
        result['html_remove_error'] = type(e).__name__
    result['removed_html'] = removed_html

    removed_photos = 0
    photo_remove_errors: list[dict[str, str]] = []
    for filename in result.get('photo_filenames') or []:
        photo_path = os.path.join(PHOTOS_DIR, filename)
        try:
            if os.path.exists(photo_path):
                os.remove(photo_path)
                removed_photos += 1
        except OSError as e:
            photo_remove_errors.append({'filename': filename, 'error': type(e).__name__})
    result['removed_photo_files'] = removed_photos
    if photo_remove_errors:
        result['photo_remove_errors'] = photo_remove_errors

    log_path = os.path.join(LOGS_DIR, f'interview_{session_id}.txt')
    removed_log = False
    try:
        if os.path.exists(log_path):
            os.remove(log_path)
            removed_log = True
    except OSError as e:
        result['log_remove_error'] = type(e).__name__
    result['removed_log'] = removed_log

    result.update(session_store.purge_session_artifacts(session_id))
    return result

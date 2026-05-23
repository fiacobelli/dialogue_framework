"""Shared donor-page takedown helpers."""

from __future__ import annotations

import os

from .config import MICROSITES_DIR
from . import database as db


def delete_session(session_id: str, *, reason: str, actor: str) -> dict | None:
    """Soft-delete DB state and remove generated public HTML if present."""
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
    return result

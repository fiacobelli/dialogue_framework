"""Shared SQLite helpers for microsite persistence."""

from __future__ import annotations

import hashlib
import json
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime
from typing import Any

_db_path: str | None = None

DEFAULT_PHOTO_ROLES = ('before', 'during', 'hope')
ALLOWED_PHOTO_ROLES = {'before', 'during', 'hope', 'general'}

ALLOWED_EVENT_TYPES = {
    'tts_started',
    'tts_ended',
    'vad_fired',
    'recognition_started',
    'recognition_ended',
    'empty_input',
    'typed_started',
    'typed_sent',
    'pause_clicked',
    'resume_clicked',
    'repeat_clicked',
    'skip_clicked',
    'mic_error',
    'vad_init',
    'vad_speech_end',
    'vad_misfire',
    'listening_started',
    'listening_ended',
    'transcribe_started',
    'transcribe_ended',
    'transcribe_error',
    'silence_timeout',
    'listening_idle_prompt',
    'post_speech_pause',
    'thinking_extended',
    'listening_aborted',
    'manual_done_clicked',
    'still_thinking_clicked',
    'try_again_clicked',
    'mic_preflight_started',
    'mic_preflight_result',
}

ALLOWED_EVENT_METADATA = {
    'source',
    'reason',
    'state',
    'duration_ms',
    'end_reason',
    'transcript_words',
    'count',
    'status',
    'secure_context',
    'speech_recognition_supported',
    'media_devices_supported',
    'vad_available',
    'permission_state',
    'audioinput_count',
    'device_labels_available',
    'active_track_state',
    'bluetooth_input_detected',
    'vad_segment_count',
    'speech_duration_ms',
    'time_to_first_speech_ms',
    'post_speech_pause_ms',
    'turn_elapsed_ms',
    'audio_duration_ms',
    'audio_bytes',
    'finalization_reason',
    'finalized_by',
    'idle_prompt_count',
    'transcribe_result',
    'error_name',
    'error_message',
}


def configure(path: str) -> None:
    """Set the SQLite database path."""
    global _db_path
    _db_path = path


def get_db_path() -> str | None:
    """Return the configured SQLite database path."""
    return _db_path


def _now() -> str:
    return datetime.utcnow().isoformat()


def _json(value: Any) -> str:
    return json.dumps(value if value is not None else {}, sort_keys=True)


def _uuid() -> str:
    return str(uuid.uuid4())


def _word_count(text: str | None) -> int:
    return len((text or '').split())


@contextmanager
def _conn():
    if not _db_path:
        raise RuntimeError('Database path not configured')
    conn = sqlite3.connect(_db_path)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA foreign_keys = ON')
    conn.execute('PRAGMA busy_timeout = 5000')
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def _ensure_columns(conn: sqlite3.Connection, table: str, columns: dict[str, str]) -> None:
    existing = {row['name'] for row in conn.execute(f'PRAGMA table_info({table})').fetchall()}
    for name, definition in columns.items():
        if name not in existing:
            conn.execute(f'ALTER TABLE {table} ADD COLUMN {name} {definition}')


def health_check() -> dict[str, Any]:
    """Return a minimal DB health summary for deployment checks."""
    with _conn() as c:
        c.execute('SELECT 1').fetchone()
        row = c.execute('SELECT COUNT(*) AS n FROM visits').fetchone()
    return {'ok': True, 'visits': int(row['n'])}


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode('utf-8')).hexdigest()


def _normalized_photo_role(role: str | None, display_order: int | None = None) -> str:
    role = (role or '').strip().lower()
    if role in ALLOWED_PHOTO_ROLES:
        return role
    if display_order is not None and 0 <= int(display_order) < len(DEFAULT_PHOTO_ROLES):
        return DEFAULT_PHOTO_ROLES[int(display_order)]
    return 'general'

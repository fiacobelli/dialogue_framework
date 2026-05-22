"""SQLite persistence for microsite interview analytics."""

from __future__ import annotations

import json
import os
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime
from typing import Any

_db_path: str | None = None

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
    'mic_error',
    'vad_init',
    'vad_speech_end',
    'vad_misfire',
    'silence_timeout',
}

ALLOWED_EVENT_METADATA = {'source', 'reason', 'state', 'duration_ms', 'end_reason', 'transcript_words', 'count'}


def configure(path: str) -> None:
    """Set the SQLite database path."""
    global _db_path
    _db_path = path


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


def init_db() -> None:
    """Create the database schema and idempotent indexes."""
    if not _db_path:
        raise RuntimeError('Database path not configured')
    os.makedirs(os.path.dirname(_db_path) or '.', exist_ok=True)
    with _conn() as c:
        c.execute('PRAGMA journal_mode = WAL')
        c.executescript(
            """
            CREATE TABLE IF NOT EXISTS visits (
                id TEXT PRIMARY KEY,
                session_id TEXT UNIQUE NOT NULL,
                language TEXT,
                avatar_id TEXT,
                avatar_profile_json TEXT DEFAULT '{}',
                phase TEXT DEFAULT 'WELCOME',
                awaiting TEXT,
                patient_display_name TEXT,
                patient_name_status TEXT,
                patient_name_source TEXT,
                current_step_id TEXT,
                last_task_type TEXT,
                last_decision_json TEXT DEFAULT '{}',
                story_complete INTEGER DEFAULT 0,
                photo_count INTEGER DEFAULT 0,
                draft_status TEXT DEFAULT 'none',
                total_user_turns INTEGER DEFAULT 0,
                total_assistant_turns INTEGER DEFAULT 0,
                user_agent TEXT,
                started_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                completed_at TEXT,
                published_at TEXT
            );

            CREATE TABLE IF NOT EXISTS messages (
                id TEXT PRIMARY KEY,
                visit_id TEXT NOT NULL,
                turn_number INTEGER NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                phase TEXT,
                awaiting TEXT,
                task_type TEXT,
                step_id TEXT,
                probe_depth INTEGER,
                followup_count INTEGER,
                sufficiency_reason TEXT,
                sufficiency_json TEXT DEFAULT '{}',
                input_modality TEXT,
                response_latency_ms INTEGER,
                answer_duration_ms INTEGER,
                answer_word_count INTEGER,
                answer_char_count INTEGER,
                speech_confidence REAL,
                no_response INTEGER DEFAULT 0,
                retry_count INTEGER DEFAULT 0,
                client_sent_at TEXT,
                llm_latency_ms INTEGER,
                tts_duration_ms INTEGER,
                message_word_count INTEGER,
                message_char_count INTEGER,
                created_at TEXT NOT NULL,
                FOREIGN KEY(visit_id) REFERENCES visits(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS turn_events (
                id TEXT PRIMARY KEY,
                visit_id TEXT NOT NULL,
                message_id TEXT,
                turn_number INTEGER,
                event_type TEXT NOT NULL,
                client_ts_ms INTEGER NOT NULL,
                metadata_json TEXT DEFAULT '{}',
                created_at TEXT NOT NULL,
                FOREIGN KEY(visit_id) REFERENCES visits(id) ON DELETE CASCADE,
                FOREIGN KEY(message_id) REFERENCES messages(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS photos (
                id TEXT PRIMARY KEY,
                visit_id TEXT NOT NULL,
                stored_filename TEXT NOT NULL,
                display_order INTEGER NOT NULL,
                source TEXT,
                mime_type TEXT,
                byte_size INTEGER,
                sha256 TEXT,
                width INTEGER,
                height INTEGER,
                uploaded_at TEXT NOT NULL,
                deleted_at TEXT,
                FOREIGN KEY(visit_id) REFERENCES visits(id) ON DELETE CASCADE,
                UNIQUE(visit_id, display_order)
            );

            CREATE TABLE IF NOT EXISTS donor_page_drafts (
                id TEXT PRIMARY KEY,
                visit_id TEXT NOT NULL,
                version INTEGER NOT NULL,
                status TEXT NOT NULL,
                name TEXT,
                headline TEXT,
                my_story TEXT,
                my_struggle TEXT,
                my_hope TEXT,
                content_json TEXT DEFAULT '{}',
                raw_llm_output TEXT,
                llm_model TEXT,
                prompt_version TEXT,
                generation_latency_ms INTEGER,
                published_url TEXT,
                html_path TEXT,
                generated_at TEXT NOT NULL,
                reviewed_at TEXT,
                published_at TEXT,
                FOREIGN KEY(visit_id) REFERENCES visits(id) ON DELETE CASCADE,
                UNIQUE(visit_id, version)
            );

            CREATE INDEX IF NOT EXISTS idx_visits_started_at ON visits(started_at);
            CREATE INDEX IF NOT EXISTS idx_visits_phase ON visits(phase);
            CREATE INDEX IF NOT EXISTS idx_visits_draft_status ON visits(draft_status);
            CREATE INDEX IF NOT EXISTS idx_visits_session_id ON visits(session_id);
            CREATE INDEX IF NOT EXISTS idx_messages_visit_turn ON messages(visit_id, turn_number);
            CREATE INDEX IF NOT EXISTS idx_messages_step_id ON messages(step_id);
            CREATE INDEX IF NOT EXISTS idx_messages_task_type ON messages(task_type);
            CREATE INDEX IF NOT EXISTS idx_messages_created_at ON messages(created_at);
            CREATE INDEX IF NOT EXISTS idx_events_visit_turn ON turn_events(visit_id, turn_number);
            CREATE INDEX IF NOT EXISTS idx_photos_visit ON photos(visit_id);
            CREATE INDEX IF NOT EXISTS idx_drafts_visit_version ON donor_page_drafts(visit_id, version);
            """
        )
        _ensure_columns(c, 'messages', {
            'outgoing_turn_id': 'TEXT',
            'asked_question_text': 'TEXT',
            'expected_answer_kind': 'TEXT',
            'delivery_validated': 'INTEGER',
            'answered_outgoing_turn_id': 'TEXT',
            'answered_question_text': 'TEXT',
        })


def _ensure_columns(conn: sqlite3.Connection, table: str, columns: dict[str, str]) -> None:
    existing = {row['name'] for row in conn.execute(f'PRAGMA table_info({table})').fetchall()}
    for name, definition in columns.items():
        if name not in existing:
            conn.execute(f'ALTER TABLE {table} ADD COLUMN {name} {definition}')


def create_visit(session_id: str, language: str, avatar_id: str, avatar_profile: dict, user_agent: str = '') -> str:
    now = _now()
    visit_id = _uuid()
    with _conn() as c:
        row = c.execute('SELECT id FROM visits WHERE session_id = ?', (session_id,)).fetchone()
        if row:
            return row['id']
        c.execute(
            """
            INSERT INTO visits(
                id, session_id, language, avatar_id, avatar_profile_json,
                phase, user_agent, started_at, updated_at
            ) VALUES (?,?,?,?,?,?,?,?,?)
            """,
            (visit_id, session_id, language, avatar_id, _json(avatar_profile),
             'WELCOME', user_agent, now, now),
        )
    return visit_id


def update_visit_from_info_state(visit_id: str | None, info_state) -> None:
    if not visit_id:
        return
    state = info_state.user.query('interview_state') or {}
    photos = info_state.user.query('photos') or []
    draft_status = info_state.user.query('microsite_draft_status') or 'none'
    phase = info_state.user.query('interview_phase') or state.get('phase') or 'WELCOME'
    completed = _now() if phase == 'COMPLETE' else None
    published = _now() if draft_status == 'published' else None
    with _conn() as c:
        c.execute(
            """
            UPDATE visits SET
                phase = ?,
                awaiting = ?,
                patient_display_name = ?,
                patient_name_status = ?,
                patient_name_source = ?,
                current_step_id = ?,
                last_task_type = ?,
                last_decision_json = ?,
                story_complete = ?,
                photo_count = ?,
                draft_status = ?,
                updated_at = ?,
                completed_at = COALESCE(?, completed_at),
                published_at = COALESCE(?, published_at)
            WHERE id = ?
            """,
            (
                phase,
                state.get('awaiting'),
                info_state.user.query('patient_name') or state.get('patient_name'),
                info_state.user.query('patient_name_status') or state.get('patient_name_status'),
                info_state.user.query('patient_name_source') or state.get('patient_name_source'),
                state.get('last_step_id'),
                state.get('last_task'),
                _json(state.get('last_decision')),
                1 if state.get('complete') else 0,
                len(photos),
                draft_status,
                _now(),
                completed,
                published,
                visit_id,
            ),
        )


def _next_turn_number(conn, visit_id: str) -> int:
    row = conn.execute('SELECT COALESCE(MAX(turn_number), 0) AS n FROM messages WHERE visit_id = ?', (visit_id,)).fetchone()
    return int(row['n']) + 1


def next_turn_number(visit_id: str | None) -> int:
    if not visit_id:
        return 1
    with _conn() as c:
        return _next_turn_number(c, visit_id)


def save_message(visit_id: str | None, role: str, content: str, *, turn_number: int | None = None, **meta) -> str | None:
    if not visit_id or not content:
        return None
    message_id = _uuid()
    now = _now()
    with _conn() as c:
        if turn_number is None:
            turn_number = _next_turn_number(c, visit_id)
        word_count = _word_count(content)
        char_count = len(content)
        c.execute(
            """
            INSERT INTO messages(
                id, visit_id, turn_number, role, content, phase, awaiting, task_type,
                step_id, probe_depth, followup_count, sufficiency_reason, sufficiency_json,
                input_modality, response_latency_ms, answer_duration_ms, answer_word_count,
                answer_char_count, speech_confidence, no_response, retry_count, client_sent_at,
                llm_latency_ms, tts_duration_ms, message_word_count, message_char_count,
                outgoing_turn_id, asked_question_text, expected_answer_kind, delivery_validated,
                answered_outgoing_turn_id, answered_question_text, created_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                message_id,
                visit_id,
                turn_number,
                role,
                content,
                meta.get('phase'),
                meta.get('awaiting'),
                meta.get('task_type'),
                meta.get('step_id'),
                meta.get('probe_depth'),
                meta.get('followup_count'),
                meta.get('sufficiency_reason'),
                _json(meta.get('sufficiency')),
                meta.get('input_modality'),
                meta.get('response_latency_ms'),
                meta.get('answer_duration_ms'),
                word_count if role == 'user' else None,
                char_count if role == 'user' else None,
                meta.get('speech_confidence'),
                1 if meta.get('no_response') else 0,
                meta.get('retry_count') or 0,
                meta.get('client_sent_at'),
                meta.get('llm_latency_ms'),
                meta.get('tts_duration_ms'),
                word_count,
                char_count,
                meta.get('outgoing_turn_id'),
                meta.get('asked_question_text'),
                meta.get('expected_answer_kind'),
                None if meta.get('delivery_validated') is None else (1 if meta.get('delivery_validated') else 0),
                meta.get('answered_outgoing_turn_id'),
                meta.get('answered_question_text'),
                now,
            ),
        )
        if role == 'user':
            c.execute('UPDATE visits SET total_user_turns = total_user_turns + 1, updated_at = ? WHERE id = ?', (now, visit_id))
        elif role == 'assistant':
            c.execute('UPDATE visits SET total_assistant_turns = total_assistant_turns + 1, updated_at = ? WHERE id = ?', (now, visit_id))
    return message_id


def save_turn_events(visit_id: str | None, message_id: str | None, turn_number: int | None, events: list[dict]) -> None:
    if not visit_id or not events:
        return
    rows = []
    for event in events:
        event_type = event.get('event_type') or event.get('type')
        client_ts_ms = event.get('client_ts_ms', event.get('ts'))
        if event_type not in ALLOWED_EVENT_TYPES or client_ts_ms is None:
            continue
        metadata = event.get('metadata') or {}
        safe_metadata = {k: metadata[k] for k in ALLOWED_EVENT_METADATA if k in metadata}
        rows.append((_uuid(), visit_id, message_id, turn_number, event_type, int(client_ts_ms), _json(safe_metadata), _now()))
    if not rows:
        return
    with _conn() as c:
        c.executemany(
            """
            INSERT INTO turn_events(id, visit_id, message_id, turn_number, event_type, client_ts_ms, metadata_json, created_at)
            VALUES (?,?,?,?,?,?,?,?)
            """,
            rows,
        )


def update_assistant_tts(visit_id: str | None, turn_number: int, tts_duration_ms: int | None) -> None:
    if not visit_id or tts_duration_ms is None or turn_number < 0:
        return
    with _conn() as c:
        c.execute(
            """
            UPDATE messages
            SET tts_duration_ms = ?
            WHERE visit_id = ? AND turn_number = ? AND role = 'assistant'
            """,
            (tts_duration_ms, visit_id, turn_number),
        )


def save_photo(visit_id: str | None, stored_filename: str, display_order: int, *, source: str = 'unknown',
               mime_type: str | None = None, byte_size: int | None = None, sha256: str | None = None,
               width: int | None = None, height: int | None = None) -> None:
    if not visit_id:
        return
    now = _now()
    with _conn() as c:
        c.execute(
            """
            INSERT OR IGNORE INTO photos(
                id, visit_id, stored_filename, display_order, source, mime_type,
                byte_size, sha256, width, height, uploaded_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?)
            """,
            (_uuid(), visit_id, stored_filename, display_order, source, mime_type,
             byte_size, sha256, width, height, now),
        )
        count = c.execute(
            'SELECT COUNT(*) AS n FROM photos WHERE visit_id = ? AND deleted_at IS NULL',
            (visit_id,),
        ).fetchone()['n']
        c.execute('UPDATE visits SET photo_count = ?, updated_at = ? WHERE id = ?', (count, now, visit_id))


def _next_draft_version(conn, visit_id: str) -> int:
    row = conn.execute(
        'SELECT COALESCE(MAX(version), 0) AS n FROM donor_page_drafts WHERE visit_id = ?',
        (visit_id,),
    ).fetchone()
    return int(row['n']) + 1


def save_draft(visit_id: str | None, result: dict, *, status: str = 'draft',
               generation_latency_ms: int | None = None, llm_model: str | None = None,
               prompt_version: str | None = None) -> int | None:
    if not visit_id:
        return None
    now = _now()
    with _conn() as c:
        version = _next_draft_version(c, visit_id)
        c.execute(
            """
            INSERT INTO donor_page_drafts(
                id, visit_id, version, status, name, headline, my_story, my_struggle,
                my_hope, content_json, raw_llm_output, llm_model, prompt_version,
                generation_latency_ms, published_url, html_path, generated_at, reviewed_at, published_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                _uuid(),
                visit_id,
                version,
                status,
                result.get('name'),
                result.get('headline'),
                result.get('my_story'),
                result.get('my_struggle'),
                result.get('my_hope'),
                _json({k: result.get(k) for k in ('headline', 'my_story', 'my_struggle', 'my_hope')}),
                result.get('content'),
                llm_model,
                prompt_version,
                generation_latency_ms,
                result.get('microsite_absolute_url'),
                result.get('microsite_url'),
                now,
                now if status in {'reviewed', 'published'} else None,
                now if status == 'published' else None,
            ),
        )
        c.execute(
            'UPDATE visits SET draft_status = ?, published_at = COALESCE(?, published_at), updated_at = ? WHERE id = ?',
            ('published' if status == 'published' else 'draft', now if status == 'published' else None, now, visit_id),
        )
    return version

"""SQLite persistence for microsite interview analytics."""

from __future__ import annotations

import os
import secrets
from datetime import datetime, timedelta
from typing import Any

from .database_common import (
    ALLOWED_EVENT_METADATA,
    ALLOWED_EVENT_TYPES,
    configure,
    get_db_path,
    health_check,
    _conn,
    _ensure_columns,
    _hash_token,
    _json,
    _now,
    _uuid,
    _word_count,
)
from .database_photos import (
    finalize_photo_upload,
    list_visit_photo_filenames,
    list_visit_photos,
    release_photo_reservation,
    reserve_photo_slot,
    save_photo,
    update_visit_photo_metadata,
)


def init_db() -> None:
    """Create the database schema and idempotent indexes."""
    db_path = get_db_path()
    if not db_path:
        raise RuntimeError('Database path not configured')
    os.makedirs(os.path.dirname(db_path) or '.', exist_ok=True)
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
                photo_requirement_status TEXT DEFAULT 'pending',
                draft_status TEXT DEFAULT 'none',
                publication_status TEXT DEFAULT 'not_published',
                publication_consent_version TEXT,
                publication_consented_at TEXT,
                total_user_turns INTEGER DEFAULT 0,
                total_assistant_turns INTEGER DEFAULT 0,
                user_agent TEXT,
                started_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                completed_at TEXT,
                published_at TEXT,
                unpublished_at TEXT,
                deleted_at TEXT
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
                photo_role TEXT,
                caption TEXT,
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

            CREATE TABLE IF NOT EXISTS consents (
                id TEXT PRIMARY KEY,
                visit_id TEXT NOT NULL,
                consent_type TEXT NOT NULL,
                consent_version TEXT NOT NULL,
                consented INTEGER NOT NULL,
                consent_text TEXT,
                actor TEXT,
                user_agent TEXT,
                created_at TEXT NOT NULL,
                FOREIGN KEY(visit_id) REFERENCES visits(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS audit_events (
                id TEXT PRIMARY KEY,
                visit_id TEXT,
                session_id TEXT,
                actor TEXT,
                action TEXT NOT NULL,
                reason TEXT,
                metadata_json TEXT DEFAULT '{}',
                created_at TEXT NOT NULL,
                FOREIGN KEY(visit_id) REFERENCES visits(id) ON DELETE SET NULL
            );

            CREATE TABLE IF NOT EXISTS upload_tokens (
                id TEXT PRIMARY KEY,
                visit_id TEXT NOT NULL,
                token_hash TEXT UNIQUE NOT NULL,
                purpose TEXT NOT NULL DEFAULT 'photo_upload',
                created_at TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                last_used_at TEXT,
                revoked_at TEXT,
                FOREIGN KEY(visit_id) REFERENCES visits(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS session_state (
                session_id TEXT PRIMARY KEY,
                visit_id TEXT,
                user_model_blob BLOB NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY(visit_id) REFERENCES visits(id) ON DELETE SET NULL
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
            CREATE INDEX IF NOT EXISTS idx_consents_visit_type ON consents(visit_id, consent_type);
            CREATE INDEX IF NOT EXISTS idx_audit_visit_created ON audit_events(visit_id, created_at);
            CREATE INDEX IF NOT EXISTS idx_upload_tokens_visit ON upload_tokens(visit_id, purpose, revoked_at);
            CREATE INDEX IF NOT EXISTS idx_session_state_visit ON session_state(visit_id);
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
        _ensure_columns(c, 'visits', {
            'photo_requirement_status': "TEXT DEFAULT 'pending'",
            'publication_status': "TEXT DEFAULT 'not_published'",
            'publication_consent_version': 'TEXT',
            'publication_consented_at': 'TEXT',
            'unpublished_at': 'TEXT',
            'deleted_at': 'TEXT',
        })
        _ensure_columns(c, 'photos', {
            'photo_role': 'TEXT',
            'caption': 'TEXT',
        })


def _ensure_columns(conn: sqlite3.Connection, table: str, columns: dict[str, str]) -> None:
    existing = {row['name'] for row in conn.execute(f'PRAGMA table_info({table})').fetchall()}
    for name, definition in columns.items():
        if name not in existing:
            conn.execute(f'ALTER TABLE {table} ADD COLUMN {name} {definition}')


def create_upload_token(visit_id: str | None, *, ttl_minutes: int = 480) -> dict[str, str] | None:
    """Create a time-limited token for mobile photo upload."""
    if not visit_id:
        return None
    now_dt = datetime.utcnow()
    token = secrets.token_urlsafe(32)
    row = {
        'token': token,
        'expires_at': (now_dt + timedelta(minutes=ttl_minutes)).isoformat(),
    }
    with _conn() as c:
        c.execute(
            """
            INSERT INTO upload_tokens(
                id, visit_id, token_hash, purpose, created_at, expires_at
            ) VALUES (?,?,?,?,?,?)
            """,
            (_uuid(), visit_id, _hash_token(token), 'photo_upload', now_dt.isoformat(), row['expires_at']),
        )
    return row


def validate_upload_token(visit_id: str | None, token: str | None, *, mark_used: bool = True) -> bool:
    """Return whether a mobile photo upload token is active for the visit."""
    if not visit_id or not token:
        return False
    now = _now()
    with _conn() as c:
        row = c.execute(
            """
            SELECT id
            FROM upload_tokens
            WHERE visit_id = ?
              AND token_hash = ?
              AND purpose = 'photo_upload'
              AND revoked_at IS NULL
              AND expires_at > ?
            """,
            (visit_id, _hash_token(token), now),
        ).fetchone()
        if not row:
            return False
        if mark_used:
            c.execute('UPDATE upload_tokens SET last_used_at = ? WHERE id = ?', (now, row['id']))
    return True


def revoke_upload_tokens(visit_id: str | None, *, reason: str = 'completed') -> None:
    """Revoke active upload tokens for a visit and audit the reason."""
    if not visit_id:
        return
    now = _now()
    with _conn() as c:
        c.execute(
            """
            UPDATE upload_tokens
            SET revoked_at = ?
            WHERE visit_id = ?
              AND purpose = 'photo_upload'
              AND revoked_at IS NULL
            """,
            (now, visit_id),
        )
        visit = c.execute('SELECT session_id FROM visits WHERE id = ?', (visit_id,)).fetchone()
        c.execute(
            """
            INSERT INTO audit_events(
                id, visit_id, session_id, actor, action, reason, metadata_json, created_at
            ) VALUES (?,?,?,?,?,?,?,?)
            """,
            (
                _uuid(),
                visit_id,
                visit['session_id'] if visit else None,
                'system',
                'revoke_upload_tokens',
                reason,
                _json({}),
                now,
            ),
        )


def save_consent(
    visit_id: str | None,
    consent_type: str,
    consent_version: str,
    consented: bool,
    *,
    consent_text: str = '',
    actor: str = 'patient',
    user_agent: str = '',
) -> str | None:
    """Persist a consent decision and mirror publication consent on the visit."""
    if not visit_id:
        return None
    now = _now()
    consent_id = _uuid()
    with _conn() as c:
        c.execute(
            """
            INSERT INTO consents(
                id, visit_id, consent_type, consent_version, consented,
                consent_text, actor, user_agent, created_at
            ) VALUES (?,?,?,?,?,?,?,?,?)
            """,
            (
                consent_id,
                visit_id,
                consent_type,
                consent_version,
                1 if consented else 0,
                consent_text,
                actor,
                user_agent,
                now,
            ),
        )
        if consent_type == 'publication' and consented:
            c.execute(
                """
                UPDATE visits
                SET publication_consent_version = ?,
                    publication_consented_at = ?,
                    updated_at = ?
                WHERE id = ?
                """,
                (consent_version, now, now, visit_id),
            )
    return consent_id


def save_session_state(session_id: str | None, user_model_blob: bytes, visit_id: str | None = None) -> bool:
    """Persist a serialized user model snapshot for restart-safe rehydration."""
    if not session_id or not user_model_blob:
        return False
    now = _now()
    with _conn() as c:
        c.execute(
            """
            INSERT INTO session_state(session_id, visit_id, user_model_blob, created_at, updated_at)
            VALUES(?,?,?,?,?)
            ON CONFLICT(session_id) DO UPDATE SET
                visit_id = excluded.visit_id,
                user_model_blob = excluded.user_model_blob,
                updated_at = excluded.updated_at
            """,
            (session_id, visit_id, user_model_blob, now, now),
        )
    return True


def load_session_state(session_id: str | None) -> bytes | None:
    """Return a serialized user model snapshot for a session, if available."""
    if not session_id:
        return None
    with _conn() as c:
        row = c.execute(
            'SELECT user_model_blob FROM session_state WHERE session_id = ?',
            (session_id,),
        ).fetchone()
    return bytes(row['user_model_blob']) if row else None


def is_session_deleted(session_id: str | None) -> bool:
    """Return whether a visit has been deleted and must not be rehydrated."""
    if not session_id:
        return False
    with _conn() as c:
        row = c.execute(
            """
            SELECT deleted_at, publication_status
            FROM visits
            WHERE session_id = ?
            """,
            (session_id,),
        ).fetchone()
    return bool(row and (row['deleted_at'] is not None or row['publication_status'] == 'deleted'))


def is_microsite_published(session_id: str) -> bool:
    """Return whether a session's public donor page should be served."""
    with _conn() as c:
        row = c.execute(
            """
            SELECT publication_status, draft_status, deleted_at
            FROM visits
            WHERE session_id = ?
            """,
            (session_id,),
        ).fetchone()
    return bool(
        row
        and row['deleted_at'] is None
        and row['publication_status'] == 'published'
        and row['draft_status'] == 'published'
    )


def is_photo_public(stored_filename: str) -> bool:
    """Return whether a stored photo belongs to a published, non-deleted page."""
    with _conn() as c:
        row = c.execute(
            """
            SELECT 1
            FROM photos p
            JOIN visits v ON v.id = p.visit_id
            WHERE p.stored_filename = ?
              AND p.deleted_at IS NULL
              AND v.deleted_at IS NULL
              AND v.publication_status = 'published'
              AND v.draft_status = 'published'
            LIMIT 1
            """,
            (stored_filename,),
        ).fetchone()
    return row is not None


def unpublish_session(session_id: str, reason: str = 'user_request', actor: str = 'patient') -> bool:
    """Mark a public donor page as unpublished so controlled routes stop serving it."""
    now = _now()
    with _conn() as c:
        row = c.execute('SELECT id FROM visits WHERE session_id = ?', (session_id,)).fetchone()
        if not row:
            return False
        visit_id = row['id']
        c.execute(
            """
            UPDATE visits
            SET publication_status = 'unpublished',
                draft_status = 'unpublished',
                unpublished_at = ?,
                updated_at = ?
            WHERE id = ?
            """,
            (now, now, visit_id),
        )
        c.execute(
            """
            UPDATE donor_page_drafts
            SET status = 'unpublished'
            WHERE visit_id = ? AND status = 'published'
            """,
            (visit_id,),
        )
        token_result = c.execute(
            """
            UPDATE upload_tokens
            SET revoked_at = ?
            WHERE visit_id = ?
              AND revoked_at IS NULL
            """,
            (now, visit_id),
        )
        c.execute(
            """
            INSERT INTO audit_events(
                id, visit_id, session_id, actor, action, reason, metadata_json, created_at
            ) VALUES (?,?,?,?,?,?,?,?)
            """,
            (
                _uuid(),
                visit_id,
                session_id,
                actor,
                'unpublish',
                reason,
                _json({'revoked_upload_tokens': token_result.rowcount}),
                now,
            ),
        )
    return True


def soft_delete_session(session_id: str, reason: str = 'user_request', actor: str = 'patient') -> dict[str, Any] | None:
    """Soft-delete a donor page, photos, drafts, and active upload tokens."""
    now = _now()
    with _conn() as c:
        row = c.execute(
            'SELECT id, publication_status, draft_status FROM visits WHERE session_id = ?',
            (session_id,),
        ).fetchone()
        if not row:
            return None
        visit_id = row['id']
        photos = c.execute(
            'SELECT stored_filename FROM photos WHERE visit_id = ? AND deleted_at IS NULL',
            (visit_id,),
        ).fetchall()
        photo_count = len(photos)
        c.execute('UPDATE photos SET deleted_at = ? WHERE visit_id = ? AND deleted_at IS NULL', (now, visit_id))
        c.execute("UPDATE donor_page_drafts SET status = 'deleted' WHERE visit_id = ?", (visit_id,))
        token_result = c.execute(
            """
            UPDATE upload_tokens
            SET revoked_at = ?
            WHERE visit_id = ?
              AND revoked_at IS NULL
            """,
            (now, visit_id),
        )
        snapshot_result = c.execute(
            'DELETE FROM session_state WHERE session_id = ? OR visit_id = ?',
            (session_id, visit_id),
        )
        c.execute(
            """
            UPDATE visits
            SET publication_status = 'deleted',
                draft_status = 'deleted',
                photo_count = 0,
                unpublished_at = COALESCE(unpublished_at, ?),
                deleted_at = ?,
                updated_at = ?
            WHERE id = ?
            """,
            (now, now, now, visit_id),
        )
        metadata = {
            'previous_publication_status': row['publication_status'],
            'previous_draft_status': row['draft_status'],
            'deleted_photos': photo_count,
            'revoked_upload_tokens': token_result.rowcount,
            'deleted_session_snapshots': snapshot_result.rowcount,
        }
        c.execute(
            """
            INSERT INTO audit_events(
                id, visit_id, session_id, actor, action, reason, metadata_json, created_at
            ) VALUES (?,?,?,?,?,?,?,?)
            """,
            (_uuid(), visit_id, session_id, actor, 'delete', reason, _json(metadata), now),
        )
    metadata['visit_id'] = visit_id
    metadata['photo_filenames'] = [row['stored_filename'] for row in photos]
    return metadata


def list_admin_visits(limit: int = 50) -> list[dict[str, Any]]:
    """Return recent sessions for the staff admin overview."""
    with _conn() as c:
        rows = c.execute(
            """
            SELECT
                id, session_id, phase, patient_display_name, draft_status,
                publication_status, photo_count, total_user_turns,
                total_assistant_turns, publication_consented_at,
                started_at, updated_at, completed_at, published_at, unpublished_at, deleted_at
            FROM visits
            ORDER BY updated_at DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return [dict(row) for row in rows]


def get_admin_visit(session_id: str) -> dict[str, Any] | None:
    """Return a detailed admin view for one session."""
    with _conn() as c:
        visit = c.execute('SELECT * FROM visits WHERE session_id = ?', (session_id,)).fetchone()
        if not visit:
            return None
        visit_id = visit['id']
        messages = c.execute(
            """
            SELECT turn_number, role, content, phase, awaiting, task_type,
                   step_id, input_modality, response_latency_ms,
                   answer_duration_ms, no_response, retry_count, created_at
            FROM messages
            WHERE visit_id = ?
            ORDER BY turn_number, created_at
            """,
            (visit_id,),
        ).fetchall()
        turn_events = c.execute(
            """
            SELECT turn_number, event_type, client_ts_ms, metadata_json, created_at
            FROM turn_events
            WHERE visit_id = ?
            ORDER BY created_at DESC, client_ts_ms DESC
            LIMIT 100
            """,
            (visit_id,),
        ).fetchall()
        photos = c.execute(
            """
            SELECT stored_filename, display_order, source, mime_type,
                   byte_size, width, height, photo_role, caption, uploaded_at, deleted_at
            FROM photos
            WHERE visit_id = ?
            ORDER BY display_order
            """,
            (visit_id,),
        ).fetchall()
        drafts = c.execute(
            """
            SELECT version, status, name, headline, published_url,
                   html_path, generated_at, reviewed_at, published_at
            FROM donor_page_drafts
            WHERE visit_id = ?
            ORDER BY version DESC
            """,
            (visit_id,),
        ).fetchall()
        consents = c.execute(
            """
            SELECT consent_type, consent_version, consented, actor, created_at
            FROM consents
            WHERE visit_id = ?
            ORDER BY created_at DESC
            """,
            (visit_id,),
        ).fetchall()
        audit_events = c.execute(
            """
            SELECT actor, action, reason, metadata_json, created_at
            FROM audit_events
            WHERE visit_id = ?
            ORDER BY created_at DESC
            """,
            (visit_id,),
        ).fetchall()
    return {
        'visit': dict(visit),
        'messages': [dict(row) for row in messages],
        'turn_events': [dict(row) for row in turn_events],
        'photos': [dict(row) for row in photos],
        'drafts': [dict(row) for row in drafts],
        'consents': [dict(row) for row in consents],
        'audit_events': [dict(row) for row in audit_events],
    }


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
                photo_requirement_status = ?,
                draft_status = ?,
                publication_status = COALESCE(?, publication_status),
                publication_consent_version = COALESCE(publication_consent_version, ?),
                publication_consented_at = COALESCE(publication_consented_at, ?),
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
                info_state.user.query('photo_requirement_status') or ('complete' if len(photos) >= 3 else 'pending'),
                draft_status,
                info_state.user.query('publication_status'),
                info_state.user.query('publication_consent_version'),
                info_state.user.query('publication_consented_at'),
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
    content_fields = (
        'headline',
        'short_intro',
        'personal_identity',
        'kidney_journey',
        'daily_impact',
        'transplant_hope',
        'donor_message',
        'my_story',
        'my_struggle',
        'my_hope',
        'evidence_hash',
        'evidence_snapshot',
        'review_edits',
    )
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
                _json({k: result.get(k) for k in content_fields}),
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
            """
            UPDATE visits
            SET draft_status = ?,
                publication_status = CASE WHEN ? = 'published' THEN 'published' ELSE publication_status END,
                published_at = COALESCE(?, published_at),
                updated_at = ?
            WHERE id = ?
            """,
            (
                'published' if status == 'published' else 'draft',
                status,
                now if status == 'published' else None,
                now,
                visit_id,
            ),
        )
    return version

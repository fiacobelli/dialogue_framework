"""Lightweight SQLite helpers for patient/visit tracking."""

import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime
from typing import Optional

_db_path: Optional[str] = None


def configure(path: str) -> None:
    """Set the database file path."""
    global _db_path
    _db_path = path


@contextmanager
def _conn():
    if not _db_path:
        raise RuntimeError('Database path not configured')
    conn = sqlite3.connect(_db_path)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA foreign_keys = ON')
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def _now() -> str:
    """Current UTC time as ISO 8601 string with microsecond precision."""
    return datetime.utcnow().isoformat()


def init_db() -> None:
    """Create tables if they do not exist (fresh install)."""
    with _conn() as c:
        c.executescript(
            """
            CREATE TABLE IF NOT EXISTS patients (
                phone_pin TEXT PRIMARY KEY,
                profile TEXT DEFAULT '{}',
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS visits (
                visit_id TEXT PRIMARY KEY,
                phone_pin TEXT NOT NULL,
                visit_number INTEGER NOT NULL,
                avatar_id TEXT,
                language TEXT,
                phase TEXT DEFAULT 'WELCOME',
                started_at TEXT DEFAULT CURRENT_TIMESTAMP,
                completed_at TEXT,
                user_agent TEXT,
                total_turns INTEGER DEFAULT 0,
                FOREIGN KEY(phone_pin) REFERENCES patients(phone_pin)
            );

            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                visit_id TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT,
                turn_number INTEGER,
                agent TEXT,
                voice TEXT,
                timestamp TEXT,
                input_modality TEXT,
                response_latency_ms INTEGER,
                response_latency_source TEXT,
                speech_confidence REAL,
                client_sent_at TEXT,
                llm_latency_ms INTEGER,
                question_category TEXT,
                probe_depth INTEGER,
                FOREIGN KEY(visit_id) REFERENCES visits(visit_id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS referrals (
                visit_id TEXT PRIMARY KEY,
                social_worker TEXT,
                dietitian TEXT,
                nephrologist TEXT,
                nurse_practitioner TEXT,
                verbal_summary TEXT,
                classified_at TEXT,
                FOREIGN KEY(visit_id) REFERENCES visits(visit_id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS info_state (
                phone_pin TEXT NOT NULL,
                data TEXT DEFAULT '{}',
                type TEXT NOT NULL,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (phone_pin, type),
                FOREIGN KEY(phone_pin) REFERENCES patients(phone_pin)
            );

            CREATE TABLE IF NOT EXISTS turn_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                visit_id TEXT NOT NULL,
                turn_number INTEGER NOT NULL,
                event_type TEXT NOT NULL,
                client_ts_ms INTEGER NOT NULL,
                metadata TEXT DEFAULT '{}',
                FOREIGN KEY(visit_id) REFERENCES visits(visit_id) ON DELETE CASCADE
            );
            """
        )


def migrate_db() -> None:
    """Apply schema migrations for existing databases.

    Each ALTER TABLE is wrapped in a try/except — SQLite raises an error
    if a column already exists, which we treat as a no-op (already migrated).
    Safe to call on every startup.
    """
    new_visit_cols = [
        "ALTER TABLE visits ADD COLUMN user_agent TEXT",
        "ALTER TABLE visits ADD COLUMN total_turns INTEGER DEFAULT 0",
    ]
    new_message_cols = [
        "ALTER TABLE messages ADD COLUMN input_modality TEXT",
        "ALTER TABLE messages ADD COLUMN response_latency_ms INTEGER",
        "ALTER TABLE messages ADD COLUMN response_latency_source TEXT",
        "ALTER TABLE messages ADD COLUMN speech_confidence REAL",
        "ALTER TABLE messages ADD COLUMN client_sent_at TEXT",
        "ALTER TABLE messages ADD COLUMN llm_latency_ms INTEGER",
        "ALTER TABLE messages ADD COLUMN question_category TEXT",
        "ALTER TABLE messages ADD COLUMN probe_depth INTEGER",
    ]
    new_tables = [
        """
        CREATE TABLE IF NOT EXISTS turn_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            visit_id TEXT NOT NULL,
            turn_number INTEGER NOT NULL,
            event_type TEXT NOT NULL,
            client_ts_ms INTEGER NOT NULL,
            metadata TEXT DEFAULT '{}',
            FOREIGN KEY(visit_id) REFERENCES visits(visit_id) ON DELETE CASCADE
        )
        """,
    ]

    with _conn() as c:
        for stmt in new_visit_cols + new_message_cols:
            try:
                c.execute(stmt)
            except sqlite3.OperationalError:
                pass  # column already exists
        for stmt in new_tables:
            c.execute(stmt)


def get_or_create_patient(phone_pin: str) -> None:
    now = _now()
    with _conn() as c:
        row = c.execute(
            'SELECT phone_pin FROM patients WHERE phone_pin = ?',
            (phone_pin,),
        ).fetchone()
        if row:
            c.execute(
                'UPDATE patients SET updated_at = ? WHERE phone_pin = ?',
                (now, phone_pin),
            )
            return
        c.execute(
            'INSERT INTO patients(phone_pin, created_at, updated_at) VALUES(?,?,?)',
            (phone_pin, now, now),
        )


def create_visit(phone_pin: str, avatar_id: str, language: str,
                 user_agent: str = None) -> tuple[str, int]:
    visit_id = str(uuid.uuid4())
    now = _now()
    with _conn() as c:
        next_number = c.execute(
            'SELECT COUNT(*) as count FROM visits WHERE phone_pin = ?',
            (phone_pin,),
        ).fetchone()['count'] + 1
        c.execute(
            'INSERT INTO visits(visit_id, phone_pin, visit_number, avatar_id, language, started_at, user_agent)'
            ' VALUES(?,?,?,?,?,?,?)',
            (visit_id, phone_pin, next_number, avatar_id, language, now, user_agent),
        )
    return visit_id, next_number


def save_message(visit_id: str, role: str, content: str, turn_number: int,
                 agent: str = None, voice: str = None,
                 input_modality: str = None, response_latency_ms: int = None,
                 response_latency_source: str = None,
                 speech_confidence: float = None, client_sent_at: str = None,
                 llm_latency_ms: int = None, question_category: str = None,
                 probe_depth: int = None) -> None:
    with _conn() as c:
        c.execute(
            """
            INSERT INTO messages(
                visit_id, role, content, turn_number, agent, voice, timestamp,
                input_modality, response_latency_ms, response_latency_source,
                speech_confidence, client_sent_at,
                llm_latency_ms, question_category, probe_depth
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (visit_id, role, content, turn_number, agent, voice, _now(),
             input_modality, response_latency_ms, response_latency_source,
             speech_confidence, client_sent_at,
             llm_latency_ms, question_category, probe_depth),
        )


def save_turn_events(visit_id: str, turn_number: int, events: list[dict]) -> None:
    """Bulk-insert browser-side turn events.

    Each event dict must have: event_type (str), client_ts_ms (int).
    Optional: metadata (dict, serialised to JSON).
    """
    import json
    if not events:
        return
    rows = []
    for e in events:
        event_type = e.get('event_type') or e.get('type')
        client_ts = e.get('client_ts_ms')
        if client_ts is None:
            client_ts = e.get('ts')
        if not event_type or client_ts is None:
            continue
        try:
            client_ts = int(round(float(client_ts)))
        except (TypeError, ValueError):
            continue
        metadata = e.get('metadata') or {}
        if not isinstance(metadata, dict):
            metadata = {'value': metadata}
        rows.append((visit_id, turn_number, event_type, client_ts, json.dumps(metadata)))
    if not rows:
        return
    with _conn() as c:
        c.executemany(
            'INSERT INTO turn_events(visit_id, turn_number, event_type, client_ts_ms, metadata)'
            ' VALUES(?,?,?,?,?)',
            rows,
        )


def update_visit_phase(visit_id: str, phase: str) -> None:
    completed = _now() if phase in {'REPORT', 'COMPLETE'} else None
    with _conn() as c:
        c.execute(
            'UPDATE visits SET phase = ?, completed_at = COALESCE(?, completed_at) WHERE visit_id = ?',
            (phase, completed, visit_id),
        )


def increment_visit_turns(visit_id: str) -> None:
    """Increment the total_turns counter for a visit."""
    with _conn() as c:
        c.execute(
            'UPDATE visits SET total_turns = total_turns + 1 WHERE visit_id = ?',
            (visit_id,),
        )


def save_info_state(phone_pin, beliefs, common_ground, user_model=None):
    import json
    now = _now()
    pairs = [('belief', beliefs), ('common_ground', common_ground)]
    if user_model is not None:
        pairs.append(('user_model', user_model))
    with _conn() as c:
        for type_, data in pairs:
            c.execute(
                """
                INSERT INTO info_state(phone_pin, data, type, updated_at)
                VALUES(?,?,?,?)
                ON CONFLICT(phone_pin, type) DO UPDATE SET
                    data = excluded.data,
                    updated_at = excluded.updated_at
                """,
                (phone_pin, json.dumps(data), type_, now),
            )


def load_info_state(phone_pin):
    import json
    with _conn() as c:
        rows = c.execute(
            'SELECT data, type FROM info_state WHERE phone_pin = ?',
            (phone_pin,),
        ).fetchall()
        if not rows:
            return None
        typed = {row['type']: json.loads(row['data']) for row in rows}
        return {
            'beliefs': typed.get('belief', {}),
            'common_ground': typed.get('common_ground', {}),
            'user_model': typed.get('user_model', {}),
        }


def save_referrals(visit_id: str, result: dict) -> None:
    with _conn() as c:
        c.execute(
            """
            INSERT INTO referrals(visit_id, social_worker, dietitian, nephrologist, nurse_practitioner, verbal_summary, classified_at)
            VALUES(?,?,?,?,?,?,?)
            ON CONFLICT(visit_id) DO UPDATE SET
                social_worker = excluded.social_worker,
                dietitian = excluded.dietitian,
                nephrologist = excluded.nephrologist,
                nurse_practitioner = excluded.nurse_practitioner,
                verbal_summary = excluded.verbal_summary,
                classified_at = excluded.classified_at
            """,
            (visit_id, result.get('social_worker'), result.get('dietitian'),
             result.get('nephrologist'), result.get('nurse_practitioner'),
             result.get('verbal_summary'), _now()),
        )

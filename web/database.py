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


def init_db() -> None:
    """Create tables if they do not exist."""
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
                timestamp TEXT DEFAULT CURRENT_TIMESTAMP,
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
            """
        )


def get_or_create_patient(phone_pin: str) -> None:
    now = datetime.utcnow().isoformat()
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


def create_visit(phone_pin: str, avatar_id: str, language: str) -> tuple[str, int]:
    visit_id = str(uuid.uuid4())
    with _conn() as c:
        next_number = c.execute(
            'SELECT COUNT(*) as count FROM visits WHERE phone_pin = ?',
            (phone_pin,),
        ).fetchone()['count'] + 1
        c.execute(
            'INSERT INTO visits(visit_id, phone_pin, visit_number, avatar_id, language) VALUES(?,?,?,?,?)',
            (visit_id, phone_pin, next_number, avatar_id, language),
        )
    return visit_id, next_number


def save_message(visit_id: str, role: str, content: str, turn_number: int,
                 agent: str = None, voice: str = None) -> None:
    with _conn() as c:
        c.execute(
            'INSERT INTO messages(visit_id, role, content, turn_number, agent, voice) VALUES(?,?,?,?,?,?)',
            (visit_id, role, content, turn_number, agent, voice),
        )


def update_visit_phase(visit_id: str, phase: str) -> None:
    completed = datetime.utcnow().isoformat() if phase in {'REPORT', 'COMPLETE'} else None
    with _conn() as c:
        c.execute(
            'UPDATE visits SET phase = ?, completed_at = COALESCE(?, completed_at) WHERE visit_id = ?',
            (phase, completed, visit_id),
        )


def save_info_state(phone_pin: str, beliefs: dict, common_ground: dict) -> None:
    import json
    now = datetime.utcnow().isoformat()
    with _conn() as c:
        for type_, data in (('belief', beliefs), ('common_ground', common_ground)):
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


def load_info_state(phone_pin: str) -> dict | None:
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
            (
                visit_id,
                result.get('social_worker'),
                result.get('dietitian'),
                result.get('nephrologist'),
                result.get('nurse_practitioner'),
                result.get('verbal_summary'),
                datetime.utcnow().isoformat(),
            ),
        )

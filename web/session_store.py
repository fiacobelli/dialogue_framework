"""Centralized session storage for the dialogue framework.

This module provides a shared in-process cache and can rehydrate sessions
from persisted user models after a service restart.
"""

from __future__ import annotations

import os
import pickle

from .config import USER_MODELS_DIR
from . import database as db

_sessions: dict[str, dict] = {}


def _user_model_path(session_id: str) -> str:
    return os.path.join(USER_MODELS_DIR, f'{session_id}.pkl')


def get_session(session_id: str) -> dict | None:
    """Get a session by ID."""
    return _sessions.get(session_id)


def set_session(session_id: str, session: dict) -> None:
    """Store a session."""
    _sessions[session_id] = session


def has_session(session_id: str) -> bool:
    """Check if a session exists."""
    return session_id in _sessions


def can_rehydrate_session(session_id: str) -> bool:
    """Return whether a persisted user model exists for a session."""
    if not session_id:
        return False
    return os.path.exists(_user_model_path(session_id)) or db.load_session_state(session_id) is not None


def persist_session_state(session_id: str, session: dict) -> bool:
    """Persist the session's user model to disk and SQLite."""
    if not session_id or not session:
        return False
    info_state = session.get('info_state')
    if not info_state:
        return False
    info_state.save_user_model()
    payload = pickle.dumps(info_state.user)
    try:
        return db.save_session_state(session_id, payload, info_state.user.query('visit_id'))
    except Exception:
        return False


def _restore_user_model_file(session_id: str) -> bool:
    """Restore the pickle file from SQLite when disk state is missing."""
    path = _user_model_path(session_id)
    if os.path.exists(path):
        return True
    payload = db.load_session_state(session_id)
    if not payload:
        return False
    os.makedirs(USER_MODELS_DIR, exist_ok=True)
    with open(path, 'wb') as f:
        f.write(payload)
    return True


def ensure_session(session_id: str) -> dict | None:
    """Return an active session, rehydrating from disk when possible."""
    if not session_id:
        return None
    session = get_session(session_id)
    if session:
        return session
    if not can_rehydrate_session(session_id):
        return None
    if not _restore_user_model_file(session_id):
        return None

    # Import lazily to avoid circular imports at module load time.
    from .session import create_session

    session = create_session(session_id)
    set_session(session_id, session)
    return session


def clear_sessions() -> None:
    """Clear in-memory sessions. Intended for tests and controlled maintenance."""
    _sessions.clear()


def all_sessions() -> dict:
    """Get all sessions (for debugging/admin)."""
    return _sessions

"""Centralized session storage for the dialogue framework.

This module provides a shared session store that can be accessed by
both the main app and blueprints.
"""

_sessions = {}


def get_session(session_id: str) -> dict | None:
    """Get a session by ID."""
    return _sessions.get(session_id)


def set_session(session_id: str, session: dict) -> None:
    """Store a session."""
    _sessions[session_id] = session


def has_session(session_id: str) -> bool:
    """Check if a session exists."""
    return session_id in _sessions


def all_sessions() -> dict:
    """Get all sessions (for debugging/admin)."""
    return _sessions

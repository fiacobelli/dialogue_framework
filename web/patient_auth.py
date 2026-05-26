"""Patient-session capability helpers.

The session id identifies the record. The patient token authorizes actions
from the browser that owns that session.
"""

from __future__ import annotations

import hmac
import secrets
from typing import Any

from flask import request

TOKEN_FIELD = 'patient_token'
HEADER_NAME = 'X-Patient-Session-Token'


def issue_patient_token(info_state) -> str:
    """Create and store a patient-session capability token if one is missing."""
    existing = info_state.user.query(TOKEN_FIELD)
    if existing:
        return existing
    token = secrets.token_urlsafe(32)
    info_state.user.update(TOKEN_FIELD, token)
    return token


def patient_token(info_state) -> str | None:
    """Return the stored patient token for URL generation."""
    return info_state.user.query(TOKEN_FIELD)


def request_patient_token(data: dict[str, Any] | None = None) -> str:
    """Read a patient token from JSON/form/query/header inputs."""
    data = data or {}
    return (
        str(data.get(TOKEN_FIELD) or '')
        or request.headers.get(HEADER_NAME, '')
        or request.form.get(TOKEN_FIELD, '')
        or request.args.get(TOKEN_FIELD, '')
    ).strip()


def is_patient_authorized(info_state, data: dict[str, Any] | None = None) -> bool:
    """Return whether the request carries the active patient-session token."""
    expected = patient_token(info_state)
    provided = request_patient_token(data)
    return bool(expected and provided and hmac.compare_digest(str(expected), provided))

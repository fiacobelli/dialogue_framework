"""Publication lifecycle API routes."""

from __future__ import annotations

import logging

from flask import Blueprint, jsonify, request

from .session_store import ensure_session, get_session, persist_session_state
from . import database as db
from . import takedown
from .structured_logging import log_event

publication_bp = Blueprint('publication', __name__, url_prefix='/api')
logger = logging.getLogger(__name__)


@publication_bp.route('/unpublish', methods=['POST'])
def unpublish_microsite():
    """Unpublish a donor page for the active session."""
    data = request.json or {}
    session_id = data.get('session_id')

    if not session_id or not ensure_session(session_id):
        return jsonify({'error': 'Invalid session'}), 400

    s = get_session(session_id)
    info_state = s['info_state']
    ok = db.unpublish_session(session_id, reason=data.get('reason') or 'user_request', actor='patient')
    if not ok:
        return jsonify({'error': 'not_found', 'message': 'No donor page session was found.'}), 404

    info_state.user.update('publication_status', 'unpublished')
    info_state.user.update('microsite_draft_status', 'unpublished')
    persist_session_state(session_id, s)
    log_event(logger, 'microsite_unpublished', session_id=session_id, reason=data.get('reason') or 'user_request')
    return jsonify({
        'status': 'unpublished',
        'message': 'The donor page is no longer public.',
    })


@publication_bp.route('/delete', methods=['POST'])
def delete_microsite():
    """Soft-delete a donor page for the active session."""
    data = request.json or {}
    session_id = data.get('session_id')

    if not session_id or not ensure_session(session_id):
        return jsonify({'error': 'Invalid session'}), 400

    s = get_session(session_id)
    info_state = s['info_state']
    result = takedown.delete_session(session_id, reason=data.get('reason') or 'user_request', actor='patient')
    if not result:
        return jsonify({'error': 'not_found', 'message': 'No donor page session was found.'}), 404

    info_state.user.update('publication_status', 'deleted')
    info_state.user.update('microsite_draft_status', 'deleted')
    info_state.user.update('photos', [])
    persist_session_state(session_id, s)
    log_event(
        logger,
        'microsite_deleted',
        session_id=session_id,
        reason=data.get('reason') or 'user_request',
        removed_html=result.get('removed_html', False),
        deleted_photos=result.get('deleted_photos', 0),
    )
    return jsonify({
        'status': 'deleted',
        'message': 'The donor page and uploaded photos are no longer public.',
        'removed_html': result.get('removed_html', False),
    })

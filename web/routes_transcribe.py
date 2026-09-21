"""Speech transcription routes for the microsite interview."""

from __future__ import annotations

import logging

from flask import Blueprint, jsonify, request
import requests as http_requests

from .config import GROQ_API_KEY, GROQ_WHISPER_URL
from .patient_auth import is_patient_authorized
from .session_store import ensure_session, get_session

transcribe_bp = Blueprint('transcribe', __name__, url_prefix='/api')
logger = logging.getLogger(__name__)

MAX_TRANSCRIBE_AUDIO_BYTES = 3 * 1024 * 1024
WHISPER_MODEL = 'whisper-large-v3-turbo'


@transcribe_bp.route('/transcribe', methods=['POST'])
def transcribe_audio():
    """Transcribe patient audio via Groq Whisper."""
    session_id = (request.form.get('session_id') or '').strip()
    if not session_id or not ensure_session(session_id):
        return jsonify({'error': 'unauthorized_session'}), 401

    session = get_session(session_id)
    if not is_patient_authorized(session['info_state']):
        return jsonify({'error': 'unauthorized_session'}), 401

    audio = request.files.get('audio')
    if not audio:
        return jsonify({'error': 'no_audio'}), 400

    audio_data = audio.read(MAX_TRANSCRIBE_AUDIO_BYTES + 1)
    if len(audio_data) > MAX_TRANSCRIBE_AUDIO_BYTES:
        return jsonify({'error': 'audio_too_large'}), 413

    if not GROQ_API_KEY:
        logger.error('transcribe_unavailable: GROQ_API_KEY is not configured')
        return jsonify({'error': 'transcription_unavailable'}), 503

    language = (request.form.get('language') or 'en').strip()[:8] or 'en'
    try:
        resp = http_requests.post(
            GROQ_WHISPER_URL,
            headers={'Authorization': f'Bearer {GROQ_API_KEY}'},
            files={'file': ('audio.wav', audio_data, 'audio/wav')},
            data={'model': WHISPER_MODEL, 'language': language},
            timeout=15,
        )
        resp.raise_for_status()
        transcript = resp.json().get('text', '').strip()
        return jsonify({'transcript': transcript})
    except Exception as exc:
        logger.warning('transcribe_error session_id=%s error=%s', session_id, exc)
        return jsonify({'error': 'transcribe_failed'}), 502

"""Core API routes blueprint for the SDoH screening framework."""

import json as _json
import logging
import re
import uuid
from flask import Blueprint, request, jsonify, Response

from strings import MSG, BELSTR
from .config import AVATAR_PROFILES, QUESTIONS_FILE
from .session import create_session
from .session_store import get_session, set_session, has_session
from . import report
from . import database as db
from . import email_sender
from .config import (
    EMAIL_ENABLED,
    SMTP_HOST,
    SMTP_PORT,
    EMAIL_SENDER,
    EMAIL_PASSWORD,
    EMAIL_RECIPIENTS,
)
from .screening_flow import (
    build_question_instructions_from_topics,
    build_screening_state,
    load_question_topics,
    select_topics,
)

logger = logging.getLogger(__name__)
api_bp = Blueprint('api', __name__, url_prefix='/api')


@api_bp.route('/session', methods=['POST'])
def new_session():
    """Create or resume a session. Returns opening prompt and phase."""
    data = request.json or {}
    patient_id = _sanitize_patient_id(data.get('patient_id'))
    lang = data.get('lang', 'en')
    avatar_id = data.get('avatar', 'black_female')

    session_id = patient_id or str(uuid.uuid4())
    set_session(session_id, create_session(session_id))

    s = get_session(session_id)
    info_state = s['info_state']
    goal_mgr = s['goal_mgr']

    user_agent = request.headers.get('User-Agent', '')
    screen_width = data.get('screen_width')
    screen_height = data.get('screen_height')
    if screen_width or screen_height:
        logger.debug('Session screen: %sx%s UA: %.120s', screen_width, screen_height, user_agent)

    avatar_profile = AVATAR_PROFILES.get(avatar_id, AVATAR_PROFILES['black_female'])
    if lang == 'en' and avatar_profile['lang'] != 'en':
        lang = avatar_profile['lang']

    info_state.user.update('language', lang)
    info_state.user.update('avatar', avatar_id)
    info_state.user.update('avatar_profile', avatar_profile)

    visit_number = 1
    if patient_id:
        db.get_or_create_patient(patient_id)
        visit_id, visit_number = db.create_visit(patient_id, avatar_id, lang, user_agent=user_agent)
        info_state.user.update('patient_pin', patient_id)
        info_state.user.update('visit_id', visit_id)
        info_state.user.update('visit_number', visit_number)
    else:
        info_state.user.update('visit_number', visit_number)

    prior_counts = db.get_asked_category_counts(patient_id) if patient_id else {}
    screening_topics = build_screening_topics(prior_counts, visit_number)
    question_block = build_question_instructions_from_topics(screening_topics)
    info_state.user.update('question_instructions', question_block)
    info_state.user.update('screening_state', build_screening_state(screening_topics))

    is_returning = visit_number > 1
    info_state.user.update('screening_phase', 'WELCOME')
    info_state.user.update('conversation_history', [])
    info_state.bel.add(BELSTR.DONE, False)
    info_state.save_user_model()

    avatar_name = avatar_profile.get('name', 'Assistant')
    opening = goal_mgr.get_opening(info_state, lang, avatar_name, is_returning=is_returning)

    return jsonify({
        'session_id': session_id,
        'prompt': opening,
        'phase': 'WELCOME',
        'returning': is_returning,
        'avatar': avatar_profile,
    })


@api_bp.route('/avatars')
def get_avatars():
    """Return available avatar profiles."""
    return jsonify(AVATAR_PROFILES)


@api_bp.route('/chat', methods=['POST'])
def chat():
    """Process user message and return LLM response."""
    data = request.json
    session_id = data.get('session_id')
    user_input = data.get('input', '').strip()

    if not session_id or not has_session(session_id):
        return jsonify({'error': 'Invalid session'}), 400

    s = get_session(session_id)
    info_state = s['info_state']
    goal = s['goal_mgr'].goal
    msg = s['msg']

    msg[MSG.ORIG_TEXT] = user_input
    msg[MSG.POSSIBLE_RESPONSES] = [(1.0, user_input)]
    msg['turn_meta'] = _turn_meta(data)

    goal.execute_goal(msg, info_state)

    phase = info_state.user.query('screening_phase') or 'WELCOME'
    prompt = msg.get(MSG.RESPONSE) or "Let's try that again. Please answer when you're ready."
    info_state.save_user_model()

    return jsonify({
        'prompt': prompt,
        'phase': phase,
        'done': phase in ['REPORT', 'COMPLETE'],
    })


_SENTENCE_BOUNDARY = re.compile(r'(?<=[.!?])\s+')


@api_bp.route('/chat/stream', methods=['POST'])
def chat_stream():
    """Stream LLM response as Server-Sent Events, one sentence per event."""
    data = request.json or {}
    session_id = data.get('session_id')
    user_input = data.get('input', '').strip()

    if not session_id or not has_session(session_id):
        return jsonify({'error': 'Invalid session'}), 400

    s = get_session(session_id)
    info_state = s['info_state']
    goal = s['goal_mgr'].goal
    msg = s['msg']

    msg[MSG.ORIG_TEXT] = user_input
    msg[MSG.POSSIBLE_RESPONSES] = [(1.0, user_input)]
    msg['turn_meta'] = _turn_meta(data)

    def generate():
        buffer = ''
        stream_gen = goal.execute_goal_stream(msg, info_state)
        try:
            for token in stream_gen:
                buffer += token
                while True:
                    m = _SENTENCE_BOUNDARY.search(buffer)
                    if not m:
                        break
                    sentence = buffer[:m.start()].strip()
                    buffer = buffer[m.end():]
                    if sentence:
                        yield f"data: {_json.dumps({'type': 'sentence', 'text': sentence})}\n\n"
        except Exception as e:
            logger.error("Stream error for session %s: %s", session_id, e, exc_info=True)
            stream_gen.close()
            yield f"data: {_json.dumps({'type': 'error', 'message': 'Streaming error'})}\n\n"
            return

        if buffer.strip():
            yield f"data: {_json.dumps({'type': 'sentence', 'text': buffer.strip()})}\n\n"

        phase = info_state.user.query('screening_phase') or 'WELCOME'
        info_state.save_user_model()
        yield f"data: {_json.dumps({'type': 'done', 'phase': phase, 'done': phase in ('REPORT', 'COMPLETE')})}\n\n"

    return Response(
        generate(),
        mimetype='text/event-stream',
        headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'},
    )


@api_bp.route('/classify', methods=['POST'])
def classify_responses():
    """Classify screening responses into professional referral buckets."""
    data = request.json
    session_id = data.get('session_id')

    if not session_id or not has_session(session_id):
        return jsonify({'error': 'Invalid session'}), 400

    s = get_session(session_id)
    info_state = s['info_state']
    provider = s['goal_mgr'].goal.llm

    try:
        result = report.classify(info_state, provider)
        visit_id = info_state.user.query('visit_id')
        patient_id = info_state.user.query('patient_pin')
        if visit_id:
            db.save_referrals(visit_id, result)
        email_sender.send_report(visit_id, result, patient_id, {
            'enabled': EMAIL_ENABLED,
            'host': SMTP_HOST,
            'port': SMTP_PORT,
            'sender': EMAIL_SENDER,
            'password': EMAIL_PASSWORD,
            'recipients': EMAIL_RECIPIENTS,
        })
        logger.info("Classification complete for session %s", session_id)
        return jsonify(result)
    except Exception as e:
        logger.error("Classification failed for session %s: %s", session_id, e, exc_info=True)
        return jsonify({
            'social_worker': 'Unable to classify - please review manually.',
            'dietitian': 'Unable to classify - please review manually.',
            'nephrologist': 'Unable to classify - please review manually.',
            'nurse_practitioner': 'Unable to classify - please review manually.',
            'verbal_summary': (
                'We will share your answers with your care team. '
                'Thank you for your time today, and take care of yourself.'
            ),
        })


def build_screening_topics(prior_counts: dict | None = None, visit_number: int = 1) -> list[dict]:
    """Pre-select structured topics for code-controlled screening flow."""
    return select_topics(load_question_topics(QUESTIONS_FILE), count=6,
                         prior_category_counts=prior_counts,
                         visit_number=visit_number)


def _turn_meta(data: dict) -> dict:
    return {
        'input_modality': data.get('input_modality'),
        'response_latency_ms': data.get('response_latency_ms'),
        'response_latency_source': data.get('response_latency_source'),
        'speech_confidence': data.get('speech_confidence'),
        'client_sent_at': data.get('client_sent_at'),
        'no_response': data.get('no_response', False),
        'events': data.get('events', []),
    }


def _sanitize_patient_id(value: str | None) -> str:
    if not value:
        return ''
    raw = value.strip().lower()
    name_part, sep, dob_part = raw.partition('-')
    safe_name = re.sub(r'[^a-z]', '', name_part)
    safe_dob = re.sub(r'[^0-9]', '', dob_part)
    if safe_name and safe_dob and _is_valid_dob(safe_dob):
        return f"{safe_name}-{safe_dob}"
    return ''


def _is_valid_dob(digits: str) -> bool:
    """Validate 8-digit MMDDYYYY string represents a real past date."""
    if len(digits) != 8:
        return False
    try:
        from datetime import datetime
        month = int(digits[0:2])
        day = int(digits[2:4])
        year = int(digits[4:8])
        datetime(year, month, day)
        return 1900 <= year <= datetime.now().year
    except ValueError:
        return False

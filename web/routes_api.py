"""Core API routes blueprint for the SDoH screening framework."""

import logging
import random
import re
from flask import Blueprint, request, jsonify
import uuid

logger = logging.getLogger(__name__)

from strings import MSG, BELSTR
from .config import AVATAR_PROFILES, QUESTIONS_FILE
from .session import create_session
from .session_store import get_session, set_session, has_session
from . import report
from . import database as db

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
    question_block = build_question_instructions()
    info_state.user.update('question_instructions', question_block)

    is_returning = visit_number > 1
    info_state.user.update('screening_phase', 'WELCOME')
    info_state.user.update('conversation_history', [])
    info_state.bel.add(BELSTR.DONE, False)
    info_state.save_user_model()

    phase = 'WELCOME'

    avatar_name = avatar_profile.get('name', 'Assistant')
    opening = goal_mgr.get_opening(info_state, lang, avatar_name, is_returning=is_returning)

    return jsonify({
        'session_id': session_id,
        'prompt': opening,
        'phase': phase,
        'returning': is_returning,
        'avatar': avatar_profile
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
    dialogue_mgr = s['dialogue_mgr']
    nlu = s['nlu']
    nlg = s['nlg']
    msg = s['msg']

    msg[MSG.POSSIBLE_RESPONSES] = [(1.0, user_input)]
    msg['turn_meta'] = {
        'input_modality':      data.get('input_modality'),
        'response_latency_ms': data.get('response_latency_ms'),
        'speech_confidence':   data.get('speech_confidence'),
        'client_sent_at':      data.get('client_sent_at'),
        'no_response':         data.get('no_response', False),
        'events':              data.get('events', []),
    }

    if nlu.check(msg):
        dialogue_mgr.manage(msg)

    phase = info_state.user.query('screening_phase') or 'WELCOME'
    done = phase in ['REPORT', 'COMPLETE']
    prompt = nlg.get_prompt(msg)

    info_state.save_user_model()

    return jsonify({
        'prompt': prompt,
        'phase': phase,
        'done': done
    })


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
        if visit_id:
            db.save_referrals(visit_id, result)
        logger.info("Classification complete for session %s", session_id)
        return jsonify(result)
    except Exception as e:
        logger.error("Classification failed for session %s: %s", session_id, e, exc_info=True)
        return jsonify({
            'social_worker': 'Unable to classify — please review manually.',
            'dietitian': 'Unable to classify — please review manually.',
            'nephrologist': 'Unable to classify — please review manually.',
            'nurse_practitioner': 'Unable to classify — please review manually.',
            'verbal_summary': 'We will share your answers with your care team. Thank you for your time today, and take care of yourself.'
        })
def _load_questions() -> tuple[str, list[str]]:
    """Load questions file and split into (preamble, [category_blocks])."""
    try:
        with open(QUESTIONS_FILE, 'r', encoding='utf-8') as f:
            text = f.read().strip()
    except FileNotFoundError:
        return '', []

    # First paragraph is the preamble; the rest are category blocks
    paragraphs = [p.strip() for p in text.split('\n\n') if p.strip()]
    if not paragraphs:
        return '', []
    return paragraphs[0], paragraphs[1:]


QUESTIONS_PREAMBLE, QUESTIONS_CATEGORIES = _load_questions()

# Sensitivity ranking: lower = less sensitive, higher = more sensitive.
# The LLM is instructed to cover topics in listed order, so sorting here
# ensures sessions always build from safe topics toward sensitive ones.
_SENSITIVITY_ORDER = {
    'Transportation': 1, 'Physical Activity': 2, 'Sleep': 3,
    'General Health': 4, 'Physical Functioning': 5, 'Pain': 6,
    'Kidney Symptoms': 7, 'Kidney Disease Burden': 8,
    'Kidney Disease Daily Life Impact': 9, 'Dialysis Care Satisfaction': 10,
    'Education': 11, 'Work Status': 12, 'Employment': 12,
    'Disabilities': 13, 'Family and Friends Satisfaction': 14,
    'Family and Community Support': 15, 'Utilities': 16,
    'Food': 17, 'Financial Strain': 18, 'Housing': 19,
    'Substance Use': 20, 'Interpersonal Safety': 21,
}

def _category_name(block: str) -> str:
    return block.split('\n')[0].rstrip(':').strip()


def build_question_instructions() -> str:
    """Pre-select exactly 6 random categories, sorted least-to-most sensitive.

    Random selection preserves research variability across sessions.
    Sensitivity sort ensures the LLM always builds rapport before
    reaching the most sensitive topics.
    """
    if not QUESTIONS_CATEGORIES:
        return QUESTIONS_PREAMBLE
    selected = random.sample(QUESTIONS_CATEGORIES, min(6, len(QUESTIONS_CATEGORIES)))
    selected.sort(key=lambda b: _SENSITIVITY_ORDER.get(_category_name(b), 99))
    return QUESTIONS_PREAMBLE + '\n\n' + '\n\n'.join(selected)


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
        day   = int(digits[2:4])
        year  = int(digits[4:8])
        dob = datetime(year, month, day)
        return 1900 <= year <= datetime.now().year
    except ValueError:
        return False

"""Core API routes blueprint for the SDoH screening framework."""

import logging
from flask import Blueprint, request, jsonify
import uuid

logger = logging.getLogger(__name__)

from strings import MSG
from .config import AVATAR_PROFILES, WELCOME_BACK
from .session import create_session
from .session_store import get_session, set_session, has_session
from . import report

api_bp = Blueprint('api', __name__, url_prefix='/api')


@api_bp.route('/session', methods=['GET', 'POST'])
def new_session():
    """Create or resume a session. Returns opening prompt and phase."""
    patient_id = None
    lang = request.args.get('lang', 'en')
    avatar_id = request.args.get('avatar', 'mary')

    if request.method == 'POST' and request.json:
        patient_id = request.json.get('patient_id')
        lang = request.json.get('lang', lang)
        avatar_id = request.json.get('avatar', avatar_id)

    session_id = patient_id or str(uuid.uuid4())
    set_session(session_id, create_session(session_id))

    s = get_session(session_id)
    info_state = s['info_state']
    goal_mgr = s['goal_mgr']

    avatar_profile = AVATAR_PROFILES.get(avatar_id, AVATAR_PROFILES['mary'])
    if lang == 'en' and avatar_profile['lang'] != 'en':
        lang = avatar_profile['lang']

    info_state.user.update('language', lang)
    info_state.user.update('avatar', avatar_id)
    info_state.user.update('avatar_profile', avatar_profile)
    info_state.save_user_model()

    phase = info_state.user.query('screening_phase') or 'WELCOME'
    is_returning = phase != 'WELCOME'

    avatar_name = avatar_profile.get('name', 'Assistant')
    opening = goal_mgr.get_opening(info_state, lang, avatar_name)
    if is_returning:
        opening = f"{WELCOME_BACK.get(lang, WELCOME_BACK['en'])} {opening}"

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

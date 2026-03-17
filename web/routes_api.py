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
from . import database as db

api_bp = Blueprint('api', __name__, url_prefix='/api')


@api_bp.route('/session', methods=['POST'])
def new_session():
    """Create or resume a session. Returns opening prompt and phase."""
    data = request.json or {}
    patient_id = (data.get('patient_id') or '').strip()
    lang = data.get('lang', 'en')
    avatar_id = data.get('avatar', 'mary')

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
    visit_number = 1
    if patient_id:
        db.get_or_create_patient(patient_id)
        visit_id, visit_number = db.create_visit(patient_id, avatar_id, lang)
        info_state.user.update('patient_pin', patient_id)
        info_state.user.update('visit_id', visit_id)
        info_state.user.update('visit_number', visit_number)
    else:
        info_state.user.update('visit_number', visit_number)
    question_block = build_question_instructions(visit_number)
    info_state.user.update('question_instructions', question_block)
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
VISIT_QUESTION_SETS = {
    1: [
        "What is your living situation today? Do you have a steady place to live?",
        "Within the past 12 months, have you worried that your food would run out before you got money to buy more?",
        "Over the past 2 weeks, how often have you felt down, depressed, or hopeless?",
        "Do you feel physically and emotionally safe where you currently live?",
        "In a typical week, how many days do you do any physical activity like walking or exercise?",
        "Do you need help with daily activities such as bathing, preparing meals, shopping, or managing medications?",
    ],
    2: [
        "Think about the place you live. Do you have problems with pests, mold, lead paint or pipes, lack of heat, appliances not working, smoke detectors missing, or water leaks?",
        "Within the past 12 months, did the food you bought just not last and you didn’t have money to get more?",
        "Has lack of transportation kept you from medical appointments, work, or getting the things you need?",
        "Are you worried that your utilities—like electric, gas, oil, or water—might be shut off in the next month?",
        "Within the past 12 months, has anyone hurt you or made you feel unsafe at home?",
        "How hard is it for you to pay for the basics like food, housing, medical care, and heat?",
    ],
}


def build_question_instructions(visit_number: int) -> str:
    questions = VISIT_QUESTION_SETS.get(visit_number)
    if not questions:
        # use the last defined set if visit exceeds configured ones
        max_visit = max(VISIT_QUESTION_SETS)
        questions = VISIT_QUESTION_SETS[max_visit]
        visit_number = max_visit

    base = (visit_number - 1) * 6
    lines = []
    if visit_number > 1:
        lines.append("You already completed the previous set of screening questions. Continue with the following ones and do not repeat earlier questions.")
    for idx, question in enumerate(questions, start=1):
        number = base + idx
        lines.append(f"{number}. \"{question}\"")
    return "\n".join(lines)

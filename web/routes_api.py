"""Core API routes blueprint for the dialogue framework."""

from flask import Blueprint, request, jsonify
import uuid

from strings import MSG
from .config import AVATAR_PROFILES, WELCOME_BACK, DEFAULT_AVATAR_ID, MAX_PHOTOS
from .session import create_session
from .session_store import get_session, set_session, has_session
from . import microsite
from . import database as db

api_bp = Blueprint('api', __name__, url_prefix='/api')


def _turn_meta(data: dict) -> dict:
    return {
        'input_modality': data.get('input_modality'),
        'response_latency_ms': data.get('response_latency_ms'),
        'answer_duration_ms': data.get('answer_duration_ms'),
        'speech_confidence': data.get('speech_confidence'),
        'client_sent_at': data.get('client_sent_at'),
        'retry_count': data.get('retry_count', 0),
        'no_response': data.get('no_response', False),
        'tts_duration_ms': data.get('tts_duration_ms'),
        'events': data.get('events', []),
    }


def _message_turn_number(info_state) -> int:
    history = info_state.user.query('conversation_history') or []
    return max(1, sum(1 for msg in history if msg.get('role') == 'user'))


def _sufficiency_meta(task: dict) -> tuple[str | None, dict | None]:
    decision = task.get('decision') or {}
    if isinstance(decision, dict) and 'sufficient' in decision:
        sufficiency = decision
    else:
        sufficiency = decision.get('sufficiency') if isinstance(decision, dict) else None
    if isinstance(sufficiency, dict):
        return sufficiency.get('reason'), sufficiency
    return None, None


def validate_generation_ready(info_state) -> tuple[bool, dict]:
    """Return whether the current session is allowed to generate a donor page."""
    state = info_state.user.query('interview_state') or {}
    phase = info_state.user.query('interview_phase') or state.get('phase')
    photos = info_state.user.query('photos') or []
    patient_name = info_state.user.query('patient_name') or state.get('patient_name')
    name_status = info_state.user.query('patient_name_status') or state.get('patient_name_status')

    missing = []
    if phase not in {'PHOTOS', 'COMPLETE'} or not state.get('complete'):
        missing.append('story_complete')
    if not patient_name or name_status not in {'confirmed', 'corrected'}:
        missing.append('confirmed_name')
    if len(photos) < MAX_PHOTOS:
        missing.append('photos')

    if missing:
        return False, {
            'error': 'generation_not_ready',
            'message': 'The donor page is not ready to generate yet.',
            'missing': missing,
            'photo_count': len(photos),
            'max_photos': MAX_PHOTOS,
            'phase': phase,
        }
    return True, {'name': patient_name}


@api_bp.route('/session', methods=['GET', 'POST'])
def new_session():
    """Create or resume a session. Returns opening prompt and phase."""
    patient_id = None
    lang = request.args.get('lang', 'en')
    avatar_id = request.args.get('avatar', DEFAULT_AVATAR_ID)

    if request.method == 'POST' and request.json:
        patient_id = request.json.get('patient_id')
        lang = request.json.get('lang', lang)
        avatar_id = request.json.get('avatar', avatar_id)

    session_id = patient_id or str(uuid.uuid4())
    set_session(session_id, create_session(session_id))

    s = get_session(session_id)
    info_state = s['info_state']
    goal_mgr = s['goal_mgr']

    if avatar_id not in AVATAR_PROFILES:
        avatar_id = DEFAULT_AVATAR_ID
    avatar_profile = AVATAR_PROFILES[avatar_id]
    if lang == 'en' and avatar_profile['lang'] != 'en':
        lang = avatar_profile['lang']

    info_state.user.update('language', lang)
    info_state.user.update('avatar', avatar_id)
    info_state.user.update('avatar_profile', avatar_profile)
    visit_id = db.create_visit(
        session_id,
        lang,
        avatar_id,
        avatar_profile,
        user_agent=request.headers.get('User-Agent', ''),
    )
    info_state.user.update('visit_id', visit_id)
    info_state.save_user_model()

    phase = info_state.user.query('interview_phase') or 'WELCOME'
    is_returning = phase != 'WELCOME'

    avatar_name = avatar_profile.get('name', 'Assistant')
    opening = goal_mgr.get_opening(
        info_state,
        lang,
        avatar_name,
        is_returning=is_returning,
    )
    if is_returning:
        opening = f"{WELCOME_BACK.get(lang, WELCOME_BACK['en'])} {opening}"
    db.save_message(
        visit_id,
        'assistant',
        opening,
        turn_number=0,
        phase='WELCOME',
        task_type='opening',
        input_modality='system',
        outgoing_turn_id=(info_state.user.query('interview_state') or {}).get('current_outgoing_turn', {}).get('outgoing_turn_id'),
        asked_question_text='What name would you like me to use for your donor page?',
        expected_answer_kind='name',
        delivery_validated=True,
    )
    db.update_visit_from_info_state(visit_id, info_state)

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
    data = request.json or {}
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
    msg['turn_meta'] = _turn_meta(data or {})

    if nlu.check(msg):
        dialogue_mgr.manage(msg)

    phase = info_state.user.query('interview_phase') or 'WELCOME'
    done = phase in ['PHOTOS', 'COMPLETE']
    prompt = nlg.get_prompt(msg)
    visit_id = info_state.user.query('visit_id')
    turn_number = _message_turn_number(info_state)
    task = msg.get('interview_task') or {}
    context = msg.get('interview_context') or {}
    state = info_state.user.query('interview_state') or {}
    step = task.get('step') or {}
    turn_meta = msg.get('turn_meta') or {}
    sufficiency_reason, sufficiency = _sufficiency_meta(task)
    db.update_assistant_tts(visit_id, turn_number - 1, turn_meta.get('tts_duration_ms'))

    user_message_id = db.save_message(
        visit_id,
        'user',
        user_input,
        turn_number=turn_number,
        phase=context.get('answered_phase') or phase,
        awaiting=context.get('answered_awaiting'),
        task_type=task.get('type'),
        step_id=context.get('answered_step_id') or state.get('last_step_id') or step.get('id'),
        answered_outgoing_turn_id=context.get('answered_outgoing_turn_id'),
        answered_question_text=context.get('answered_question_text'),
        delivery_validated=context.get('answered_delivery_validated'),
        probe_depth=1 if context.get('answered_awaiting') == 'followup_answer' else 0,
        followup_count=state.get('followup_count'),
        sufficiency_reason=sufficiency_reason,
        sufficiency=sufficiency,
        input_modality=turn_meta.get('input_modality'),
        response_latency_ms=turn_meta.get('response_latency_ms'),
        answer_duration_ms=turn_meta.get('answer_duration_ms'),
        speech_confidence=turn_meta.get('speech_confidence'),
        client_sent_at=turn_meta.get('client_sent_at'),
        retry_count=turn_meta.get('retry_count'),
        no_response=turn_meta.get('no_response'),
    )
    db.save_turn_events(visit_id, user_message_id, turn_number, turn_meta.get('events') or [])
    db.save_message(
        visit_id,
        'assistant',
        prompt,
        turn_number=turn_number,
        phase=phase,
        awaiting=state.get('awaiting'),
        task_type=task.get('type'),
        step_id=state.get('last_step_id') or step.get('id'),
        probe_depth=task.get('probe_depth'),
        followup_count=state.get('followup_count'),
        llm_latency_ms=msg.get('llm_latency_ms'),
        input_modality='system',
        outgoing_turn_id=(context.get('outgoing_turn') or {}).get('outgoing_turn_id'),
        asked_question_text=(context.get('outgoing_turn') or {}).get('asked_question_text'),
        expected_answer_kind=(context.get('outgoing_turn') or {}).get('expected_answer_kind'),
        delivery_validated=(context.get('outgoing_turn') or {}).get('delivery_validated'),
    )
    db.update_visit_from_info_state(visit_id, info_state)

    info_state.save_user_model()

    return jsonify({
        'prompt': prompt,
        'phase': phase,
        'done': done
    })


@api_bp.route('/generate', methods=['POST'])
def generate_microsite():
    """Generate microsite from conversation and photos."""
    data = request.json
    session_id = data.get('session_id')

    if not session_id or not has_session(session_id):
        return jsonify({'error': 'Invalid session'}), 400

    s = get_session(session_id)
    info_state = s['info_state']
    provider = s['goal_mgr'].goal.llm
    visit_id = info_state.user.query('visit_id')
    ready, detail = validate_generation_ready(info_state)
    if not ready:
        return jsonify(detail), 409

    name = detail['name']
    requested_name = data.get('name', '').strip()
    if requested_name and requested_name.lower() != 'patient' and requested_name != name:
        name = requested_name
        info_state.user.update('patient_name', name)
        info_state.user.update('patient_name_status', 'corrected')
        info_state.user.update('patient_name_source', 'manual_edit')

    try:
        import time
        t0 = time.perf_counter()
        result = microsite.generate(info_state, provider, name, session_id)
        latency = int((time.perf_counter() - t0) * 1000)
        db.save_draft(visit_id, result, status='draft', generation_latency_ms=latency)
        db.update_visit_from_info_state(visit_id, info_state)
        return jsonify(result)
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@api_bp.route('/publish', methods=['POST'])
def publish_microsite():
    """Publish a reviewed donor-page draft."""
    data = request.json or {}
    session_id = data.get('session_id')

    if not session_id or not has_session(session_id):
        return jsonify({'error': 'Invalid session'}), 400

    s = get_session(session_id)
    info_state = s['info_state']
    visit_id = info_state.user.query('visit_id')
    ready, detail = validate_generation_ready(info_state)
    if not ready:
        return jsonify(detail), 409

    try:
        result = microsite.publish(info_state, session_id, data.get('edits') or {})
        db.save_draft(visit_id, result, status='published')
        db.update_visit_from_info_state(visit_id, info_state)
        return jsonify(result)
    except ValueError as e:
        return jsonify({'error': 'draft_not_ready', 'message': str(e)}), 409
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

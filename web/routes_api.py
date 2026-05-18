"""Core API routes blueprint for the dialogue framework."""

from flask import Blueprint, request, jsonify
import uuid

from strings import MSG
from .config import AVATAR_PROFILES, WELCOME_BACK, DEFAULT_AVATAR_ID, MAX_PHOTOS
from .session import create_session
from .session_store import get_session, set_session, has_session
from . import microsite

api_bp = Blueprint('api', __name__, url_prefix='/api')


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

    phase = info_state.user.query('interview_phase') or 'WELCOME'
    done = phase in ['PHOTOS', 'COMPLETE']
    prompt = nlg.get_prompt(msg)

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
        result = microsite.generate(info_state, provider, name, session_id)
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
    ready, detail = validate_generation_ready(info_state)
    if not ready:
        return jsonify(detail), 409

    try:
        result = microsite.publish(info_state, session_id, data.get('edits') or {})
        return jsonify(result)
    except ValueError as e:
        return jsonify({'error': 'draft_not_ready', 'message': str(e)}), 409
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

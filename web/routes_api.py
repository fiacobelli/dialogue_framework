"""Core API routes blueprint for the dialogue framework."""

from flask import Blueprint, request, jsonify
from datetime import datetime
import logging
import subprocess
import uuid

from strings import MSG
from .config import AVATAR_PROFILES, WELCOME_BACK, DEFAULT_AVATAR_ID, MAX_PHOTOS
from .session import create_session
from .session_store import ensure_session, get_session, persist_session_state, set_session
from .interview_state import progress_snapshot
from . import microsite
from . import database as db
from .patient_auth import issue_patient_token, is_patient_authorized
from .structured_logging import log_event

api_bp = Blueprint('api', __name__, url_prefix='/api')
logger = logging.getLogger(__name__)


def _turn_meta(data: dict) -> dict:
    return {
        'input_modality': data.get('input_modality'),
        'response_latency_ms': data.get('response_latency_ms'),
        'answer_duration_ms': data.get('answer_duration_ms'),
        'speech_confidence': data.get('speech_confidence'),
        'client_sent_at': data.get('client_sent_at'),
        'retry_count': data.get('retry_count', 0),
        'no_response': data.get('no_response', False),
        'skip_requested': data.get('skip_requested', False),
        'tts_duration_ms': data.get('tts_duration_ms'),
        'events': data.get('events', []),
    }


NO_RESPONSE_INPUT = '[no speech detected]'
PUBLICATION_CONSENT_VERSION = 'publication-v1'
PUBLICATION_CONSENT_TEXT = (
    'I understand that publishing will create a public donor page that may include '
    'the public name, story, and photos I reviewed.'
)


def _sufficiency_meta(task: dict) -> tuple[str | None, dict | None]:
    decision = task.get('decision') or {}
    if isinstance(decision, dict) and 'sufficient' in decision:
        sufficiency = decision
    else:
        sufficiency = decision.get('sufficiency') if isinstance(decision, dict) else None
    if isinstance(sufficiency, dict):
        return sufficiency.get('reason'), sufficiency
    return None, None


def _git_commit() -> str | None:
    try:
        result = subprocess.run(
            ['git', 'rev-parse', '--short', 'HEAD'],
            check=True,
            capture_output=True,
            text=True,
            timeout=2,
        )
        return result.stdout.strip()
    except Exception:
        return None


def _progress(info_state, phase: str | None = None) -> dict:
    state = info_state.user.query('interview_state') or {}
    photos = info_state.user.query('photos') or []
    return progress_snapshot(state, phase or info_state.user.query('interview_phase'), len(photos))


def validate_generation_ready(info_state, allow_partial_photos: bool = False) -> tuple[bool, dict]:
    """Return whether the current session is allowed to generate a donor page."""
    state = info_state.user.query('interview_state') or {}
    phase = info_state.user.query('interview_phase') or state.get('phase')
    photos = info_state.user.query('photos') or []
    patient_name = info_state.user.query('patient_name') or state.get('patient_name')
    name_status = info_state.user.query('patient_name_status') or state.get('patient_name_status')
    photo_count = len(photos)
    photo_requirement_status = info_state.user.query('photo_requirement_status')
    partial_photos_confirmed = (
        photo_requirement_status == 'partial_confirmed'
        or (allow_partial_photos and 0 < photo_count < MAX_PHOTOS)
    )

    missing = []
    if phase not in {'PHOTOS', 'COMPLETE'} or not state.get('complete'):
        missing.append('story_complete')
    if not patient_name or name_status not in {'confirmed', 'corrected'}:
        missing.append('confirmed_name')
    if photo_count < MAX_PHOTOS and not partial_photos_confirmed:
        missing.append('photos')
    story_ready = microsite.story_evidence_ready(state)
    if not story_ready['ready']:
        missing.append('story_evidence')

    if missing:
        return False, {
            'error': 'generation_not_ready',
            'message': 'The donor page is not ready to generate yet.',
            'missing': missing,
            'missing_story_sections': story_ready['missing'],
            'photo_count': photo_count,
            'max_photos': MAX_PHOTOS,
            'partial_photos_allowed': photo_count > 0,
            'phase': phase,
        }
    return True, {
        'name': patient_name,
        'photo_requirement_status': 'partial_confirmed' if partial_photos_confirmed else 'complete',
    }


def validate_publication_consent(info_state, request_data: dict, user_agent: str = '') -> tuple[bool, dict]:
    """Persist and validate explicit consent before public publication."""
    visit_id = info_state.user.query('visit_id')
    consent = request_data.get('publication_consent') or {}
    consented = bool(consent.get('accepted'))
    if not consented:
        return False, {
            'error': 'publication_consent_required',
            'message': 'Please confirm that you understand this donor page may become public before publishing.',
            'consent_version': PUBLICATION_CONSENT_VERSION,
        }

    version = consent.get('version') or PUBLICATION_CONSENT_VERSION
    if version != PUBLICATION_CONSENT_VERSION:
        return False, {
            'error': 'publication_consent_version_mismatch',
            'message': 'Please review the latest publication consent before publishing.',
            'consent_version': PUBLICATION_CONSENT_VERSION,
        }

    consent_id = db.save_consent(
        visit_id,
        'publication',
        PUBLICATION_CONSENT_VERSION,
        True,
        consent_text=PUBLICATION_CONSENT_TEXT,
        actor='patient',
        user_agent=user_agent,
    )
    if not consent_id:
        return False, {
            'error': 'publication_consent_not_saved',
            'message': 'Publication consent could not be saved. Please try again.',
        }

    now = datetime.utcnow().isoformat()
    info_state.user.update('publication_consent_version', PUBLICATION_CONSENT_VERSION)
    info_state.user.update('publication_consented_at', now)
    return True, {
        'consent_id': consent_id,
        'consent_version': PUBLICATION_CONSENT_VERSION,
    }


@api_bp.route('/health')
def health():
    """Deployment health check for the microsite service."""
    db_status = db.health_check()
    return jsonify({
        'ok': True,
        'app': 'transplant-microsite',
        'commit': _git_commit(),
        'db': db_status,
        'time': datetime.utcnow().isoformat(),
    })


@api_bp.route('/session', methods=['GET', 'POST'])
def new_session():
    """Create a session. Returns opening prompt and phase."""
    lang = request.args.get('lang', 'en')
    avatar_id = request.args.get('avatar', DEFAULT_AVATAR_ID)

    data = request.get_json(silent=True) or {}
    participant_code = str(data.get('participant_code') or request.args.get('participant_code', '')).strip()
    if not participant_code.isdigit():
        return jsonify({'error': 'A numeric participant number is required'}), 400
    lang = data.get('lang', lang)
    avatar_id = data.get('avatar', avatar_id)

    session_id = str(uuid.uuid4())
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
    info_state.user.update('participant_code', participant_code)
    patient_token = issue_patient_token(info_state)
    visit_id = db.create_visit(
        session_id,
        lang,
        avatar_id,
        avatar_profile,
        participant_code=participant_code,
        user_agent=request.headers.get('User-Agent', ''),
    )
    info_state.user.update('visit_id', visit_id)
    persist_session_state(session_id, s)

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
        asked_question_text='What name would you like shown publicly on your donor page?',
        expected_answer_kind='name',
        delivery_validated=True,
    )
    db.update_visit_from_info_state(visit_id, info_state)

    return jsonify({
        'session_id': session_id,
        'prompt': opening,
        'phase': phase,
        'returning': is_returning,
        'avatar': avatar_profile,
        'progress': _progress(info_state, phase),
        'patient_token': patient_token,
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
    turn_meta = _turn_meta(data or {})
    no_response = bool(turn_meta.get('no_response'))
    nlu_input = NO_RESPONSE_INPUT if no_response and not user_input else user_input

    if not session_id or not ensure_session(session_id):
        return jsonify({'error': 'Invalid session'}), 400

    s = get_session(session_id)
    info_state = s['info_state']
    if not is_patient_authorized(info_state, data):
        return jsonify({'error': 'unauthorized_session'}), 403
    dialogue_mgr = s['dialogue_mgr']
    nlu = s['nlu']
    nlg = s['nlg']
    msg = s['msg']

    msg[MSG.POSSIBLE_RESPONSES] = [(1.0, nlu_input)]
    msg['turn_meta'] = turn_meta

    if nlu.check(msg):
        dialogue_mgr.manage(msg)

    phase = info_state.user.query('interview_phase') or 'WELCOME'
    done = phase in ['PHOTOS', 'COMPLETE']
    prompt = nlg.get_prompt(msg)
    visit_id = info_state.user.query('visit_id')
    turn_number = db.next_turn_number(visit_id)
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
        nlu_input,
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

    persist_session_state(session_id, s)

    return jsonify({
        'prompt': prompt,
        'phase': phase,
        'done': done,
        'progress': _progress(info_state, phase),
    })


@api_bp.route('/client-events', methods=['POST'])
def client_events():
    """Persist client-side operational events that are not tied to a user answer."""
    data = request.json or {}
    session_id = data.get('session_id')
    events = data.get('events') or []

    if not session_id or not ensure_session(session_id):
        return jsonify({'error': 'Invalid session'}), 400
    if not isinstance(events, list):
        return jsonify({'error': 'invalid_events'}), 400

    s = get_session(session_id)
    info_state = s['info_state']
    if not is_patient_authorized(info_state, data):
        return jsonify({'error': 'unauthorized_session'}), 403
    visit_id = info_state.user.query('visit_id')
    db.save_turn_events(visit_id, None, data.get('turn_number'), events)
    db.update_visit_from_info_state(visit_id, info_state)

    return jsonify({'status': 'ok'})


@api_bp.route('/generate', methods=['POST'])
def generate_microsite():
    """Generate microsite from conversation and photos."""
    data = request.json or {}
    session_id = data.get('session_id')

    if not session_id or not ensure_session(session_id):
        return jsonify({'error': 'Invalid session'}), 400

    s = get_session(session_id)
    info_state = s['info_state']
    if not is_patient_authorized(info_state, data):
        return jsonify({'error': 'unauthorized_session'}), 403
    provider = s['goal_mgr'].goal.llm
    visit_id = info_state.user.query('visit_id')
    allow_partial_photos = bool(data.get('allow_partial_photos'))
    ready, detail = validate_generation_ready(info_state, allow_partial_photos=allow_partial_photos)
    if not ready:
        return jsonify(detail), 409

    info_state.user.update('photo_requirement_status', detail.get('photo_requirement_status', 'complete'))

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
        result = microsite.generate(info_state, provider, name, session_id, s)
        latency = int((time.perf_counter() - t0) * 1000)
        db.save_draft(
            visit_id,
            result,
            status='draft',
            generation_latency_ms=latency,
            llm_model=result.get('llm_model'),
            prompt_version=result.get('prompt_version'),
        )
        db.update_visit_from_info_state(visit_id, info_state)
        log_event(
            logger,
            'microsite_draft_generated',
            session_id=session_id,
            visit_id=visit_id,
            latency_ms=latency,
            prompt_version=result.get('prompt_version'),
            llm_model=result.get('llm_model'),
            photo_count=len(result.get('photos') or []),
        )
        return jsonify(result)
    except microsite.MicrositeGenerationError as e:
        log_event(logger, 'microsite_generate_failed', level=logging.WARNING, session_id=session_id, error=e.error)
        return jsonify(e.to_response()), e.status_code
    except Exception as e:
        logger.exception('microsite_generate_unhandled_error session_id=%s', session_id)
        return jsonify({'error': str(e)}), 500

@api_bp.route('/publish', methods=['POST'])
def publish_microsite():
    """Publish a reviewed donor-page draft."""
    data = request.json or {}
    session_id = data.get('session_id')

    if not session_id or not ensure_session(session_id):
        return jsonify({'error': 'Invalid session'}), 400

    s = get_session(session_id)
    info_state = s['info_state']
    if not is_patient_authorized(info_state, data):
        return jsonify({'error': 'unauthorized_session'}), 403
    visit_id = info_state.user.query('visit_id')
    ready, detail = validate_generation_ready(info_state)
    if not ready:
        return jsonify(detail), 409
    consent_ready, consent_detail = validate_publication_consent(
        info_state,
        data,
        request.headers.get('User-Agent', ''),
    )
    if not consent_ready:
        return jsonify(consent_detail), 409

    try:
        result = microsite.publish(info_state, session_id, data.get('edits') or {}, s)
        info_state.user.update('publication_status', 'published')
        info_state.user.update('microsite_draft_status', 'published')
        db.save_draft(
            visit_id,
            result,
            status='published',
            llm_model=result.get('llm_model'),
            prompt_version=result.get('prompt_version'),
        )
        db.revoke_upload_tokens(visit_id, reason='published')
        db.update_visit_from_info_state(visit_id, info_state)
        log_event(
            logger,
            'microsite_published',
            session_id=session_id,
            visit_id=visit_id,
            prompt_version=result.get('prompt_version'),
            llm_model=result.get('llm_model'),
            photo_count=len(result.get('photos') or []),
        )
        result['public_qr_image'] = microsite.qr_data_url(result['microsite_absolute_url'])
        return jsonify(result)
    except microsite.MicrositeGenerationError as e:
        log_event(logger, 'microsite_publish_failed', level=logging.WARNING, session_id=session_id, error=e.error)
        return jsonify(e.to_response()), 409
    except ValueError as e:
        log_event(logger, 'microsite_publish_failed', level=logging.WARNING, session_id=session_id, error='draft_not_ready')
        return jsonify({'error': 'draft_not_ready', 'message': str(e)}), 409
    except Exception as e:
        logger.exception('microsite_publish_unhandled_error session_id=%s', session_id)
        return jsonify({'error': str(e)}), 500

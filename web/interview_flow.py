"""Deterministic donor-story interview flow helpers.

The LLM should make the interview sound natural, but code owns the
interview contract: intake, story order, follow-up depth, and completion.
"""

from __future__ import annotations

import re
from typing import Any


INTERVIEW_STEPS: list[dict[str, str]] = [
    {
        'id': 'personal_background',
        'phase': 'STORY',
        'question': 'Can you tell me a little about yourself and the roles or relationships that matter most in your life?',
        'focus': 'who the patient is as a person, including family, work, community, hobbies, values, or identity',
        'required': 'one concrete identity detail such as family role, work, community, hobby, value, or place',
    },
    {
        'id': 'medical_history',
        'phase': 'STORY',
        'question': 'When were you first diagnosed with kidney disease or kidney failure?',
        'focus': 'the beginning of the kidney disease journey',
        'required': 'diagnosis timing, dialysis timing, diagnosis context, or explicit uncertainty',
    },
    {
        'id': 'daily_life',
        'phase': 'STORY',
        'question': 'How has kidney failure affected your daily life, physically or emotionally?',
        'focus': 'dialysis, symptoms, daily limits, emotional burden, and what has changed',
        'required': 'a concrete daily-life impact such as schedule, fatigue, activity limits, emotions, work, family, or independence',
    },
    {
        'id': 'transplant_hope',
        'phase': 'STORY',
        'question': 'How would receiving a kidney transplant change your life?',
        'focus': 'specific hopes, activities, family moments, work, travel, energy, or independence',
        'required': 'a concrete life change, future goal, family moment, work, travel, activity, energy, or independence',
    },
    {
        'id': 'donor_message',
        'phase': 'STORY',
        'question': 'What would you want a potential donor to know about you as a person?',
        'focus': 'a direct message to potential donors and what makes the story personal',
        'required': 'a direct message, personal value, reason to consider donation, or explicit request for help',
    },
    {
        'id': 'support_network',
        'phase': 'STORY',
        'question': 'Do you have family, friends, or a community supporting you through this?',
        'focus': 'support network, community ties, and people who may be part of the story',
        'required': 'support people, support community, or an explicit statement that support is limited',
    },
    {
        'id': 'final_details',
        'phase': 'FINAL_DETAILS',
        'question': 'Is there anything else about your story, or any further details on something in particular, that you would like included?',
        'focus': 'final details, tone, quotes, photos, or personal stories before photo upload',
        'required': 'a final addition, tone preference, quote, story, or explicit nothing else',
    },
]

FINAL_PHOTOS_PROMPT = (
    "Thank you for sharing your story with me. "
    "The story part is complete, and the next step is to add up to three photos that you may want on your donor page."
)

SHORT_ANSWERS = {
    'yes', 'yeah', 'yep', 'yup', 'yea',
    'no', 'nah', 'nope',
    'ok', 'okay', 'alright', 'all right',
    'sure', 'fine', 'good', 'not really', 'none',
}

READY_TERMS = {'yes', 'yeah', 'yep', 'yup', 'ready', 'sure', 'ok', 'okay', 'start', 'begin', 'go ahead'}
NOT_READY_TERMS = {'no', 'not yet', 'not ready', 'wait', 'hold on', 'later', 'stop', 'pause'}
READINESS_QUESTION_TERMS = {'why', 'what for', 'what is this', 'how does this work', 'who will see', 'share'}

NAME_MARKERS = (
    r'my name is',
    r'i am',
    r"i'm",
    r'call me',
    r'name is',
)

REJECT_NAME_WORDS = {
    'hi', 'hello', 'hey', 'okay', 'ok', 'yes', 'no', 'ready', 'start', 'begin',
    'patient', 'name', 'is', 'me', 'my',
}

DETAIL_TERMS: dict[str, set[str]] = {
    'personal_background': {
        'mother', 'father', 'mom', 'dad', 'wife', 'husband', 'daughter', 'son',
        'sister', 'brother', 'family', 'friend', 'teacher', 'work', 'job',
        'church', 'community', 'chicago', 'hobby', 'music', 'cook', 'cooking',
        'school', 'grandkids', 'children', 'kids',
    },
    'medical_history': {
        'year', 'years', 'month', 'months', 'ago', 'diagnosed', 'dialysis',
        'kidney', 'failure', 'started', 'doctor', 'hospital',
    },
    'daily_life': {
        'dialysis', 'treatment', 'tired', 'fatigue', 'exhausted', 'drained', 'pain', 'work', 'walk',
        'drive', 'sleep', 'family', 'kids', 'children', 'cook', 'travel',
        'appointments', 'schedule', 'hours', 'week', 'emotionally', 'sad',
        'scared', 'independent', 'independence', 'activities',
    },
    'transplant_hope': {
        'energy', 'travel', 'work', 'family', 'kids', 'children', 'grandkids',
        'independent', 'independence', 'freedom', 'school', 'cook', 'walk',
        'drive', 'future', 'life', 'normal', 'healthy', 'hobbies',
    },
    'donor_message': {
        'know', 'person', 'family', 'help', 'chance', 'life', 'donor',
        'grateful', 'thank', 'hope', 'mother', 'father', 'kids', 'children',
    },
    'support_network': {
        'family', 'friend', 'friends', 'church', 'community', 'wife', 'husband',
        'mother', 'father', 'daughter', 'son', 'sister', 'brother', 'support',
        'help', 'drive', 'caregiver', 'alone',
    },
    'final_details': {
        'include', 'quote', 'photo', 'photos', 'story', 'message', 'tone',
        'nothing', 'none', 'no', 'everything', 'ready',
    },
}


def build_interview_state() -> dict[str, Any]:
    """Initial state stored in info_state.user."""
    return {
        'version': 2,
        'step_index': 0,
        'phase': 'INTRO',
        'awaiting': 'name',
        'followup_count': 0,
        'repair_count': 0,
        'last_task': 'opening',
        'last_step_id': None,
        'complete': False,
        'story_evidence': {},
        'thin_evidence': {},
        'patient_name': None,
        'patient_name_status': 'missing',
        'patient_name_source': None,
        'last_decision': None,
    }


def normalize_state(state: dict[str, Any] | None) -> dict[str, Any]:
    """Return a v2-compatible state, preserving safe values from older states."""
    base = build_interview_state()
    if not isinstance(state, dict):
        return base

    base.update(state)
    base['version'] = 2
    if base.get('awaiting') == 'story_answer':
        base['awaiting'] = 'main_answer'
    if base.get('phase') in {'WELCOME', 'BEFORE', 'DURING', 'HOPE'}:
        base['phase'] = 'INTRO' if base.get('awaiting') == 'name' else 'STORY'
    base.setdefault('followup_count', 0)
    base.setdefault('repair_count', 0)
    base.setdefault('story_evidence', {})
    base.setdefault('thin_evidence', {})
    base.setdefault('patient_name_status', 'missing')
    return base


def normalize_answer(text: str) -> str:
    text = (text or '').lower().strip()
    text = re.sub(r"[^a-z0-9'\s-]", ' ', text)
    text = re.sub(r'\s+', ' ', text)
    return text.strip()


def _name_from_tokens(raw: str) -> str | None:
    tokens = re.findall(r"[A-Za-z][A-Za-z'-]*", raw or '')
    usable = [t for t in tokens if t.lower() not in REJECT_NAME_WORDS]
    if not usable or len(usable) > 3:
        return None
    if any(len(t) < 2 for t in usable):
        return None
    return ' '.join(t.capitalize() for t in usable)


def extract_patient_name(text: str) -> dict[str, Any]:
    """Extract an explicit patient name without guessing."""
    raw = (text or '').strip()
    for marker in NAME_MARKERS:
        match = re.search(rf'\b{marker}\b\s*([A-Za-z][A-Za-z\'-]*(?:\s+[A-Za-z][A-Za-z\'-]*){{0,2}})?', raw, re.I)
        if match:
            candidate = (match.group(1) or '').strip()
            name = _name_from_tokens(candidate)
            if name:
                return {'name': name, 'status': 'captured', 'reason': 'explicit_marker'}
            return {'name': None, 'status': 'missing', 'reason': 'incomplete_marker'}

    name = _name_from_tokens(raw)
    if name and len(raw.split()) <= 3:
        return {'name': name, 'status': 'captured', 'reason': 'bare_name'}
    return {'name': None, 'status': 'missing', 'reason': 'no_clear_name'}


def readiness_decision(text: str) -> dict[str, Any]:
    normalized = normalize_answer(text)
    if not normalized:
        return {'ready': False, 'kind': 'unclear', 'matched': ''}
    if any(term in normalized for term in READINESS_QUESTION_TERMS):
        return {'ready': False, 'kind': 'question', 'matched': normalized}
    if any(term in normalized for term in NOT_READY_TERMS):
        return {'ready': False, 'kind': 'not_ready', 'matched': normalized}
    if any(term in normalized.split() or term in normalized for term in READY_TERMS):
        return {'ready': True, 'kind': 'ready', 'matched': normalized}
    return {'ready': False, 'kind': 'unclear', 'matched': normalized}


def current_step(state: dict[str, Any]) -> dict[str, str] | None:
    index = int(state.get('step_index') or 0)
    if 0 <= index < len(INTERVIEW_STEPS):
        return INTERVIEW_STEPS[index]
    return None


def _word_count(text: str) -> int:
    normalized = normalize_answer(text)
    return len(normalized.split()) if normalized else 0


def _has_explicit_none(text: str) -> bool:
    normalized = normalize_answer(text)
    return normalized in {'no', 'nope', 'none', 'nothing', 'not really', 'nothing else'}


def sufficiency_decision(step: dict[str, str] | None, text: str) -> dict[str, Any]:
    """Return whether an answer contains enough evidence for this story step."""
    if not step:
        return {'sufficient': True, 'reason': 'no_step', 'matched': None}

    step_id = step['id']
    normalized = normalize_answer(text)
    words = normalized.split()
    if not normalized:
        return {'sufficient': False, 'reason': 'empty', 'matched': None}
    if normalized in SHORT_ANSWERS:
        allowed_none = step_id in {'support_network', 'final_details'} and _has_explicit_none(normalized)
        return {'sufficient': allowed_none, 'reason': 'explicit_none' if allowed_none else 'short_answer', 'matched': normalized}

    terms = DETAIL_TERMS.get(step_id, set())
    matched = sorted(term for term in terms if re.search(rf'\b{re.escape(term)}\b', normalized))

    if step_id == 'medical_history':
        has_time = bool(re.search(r'\b(\d+|one|two|three|four|five|six|seven|eight|nine|ten)\s+(year|years|month|months)\s+ago\b', normalized))
        if has_time or 'diagnosed' in normalized or 'dialysis' in normalized:
            return {'sufficient': True, 'reason': 'medical_timing_or_context', 'matched': matched or normalized}

    if step_id in {'support_network', 'final_details'} and _has_explicit_none(normalized):
        return {'sufficient': True, 'reason': 'explicit_none', 'matched': normalized}

    if step_id == 'daily_life':
        broad_only = set(matched).issubset({'dialysis', 'treatment'}) if matched else False
        if broad_only:
            return {'sufficient': False, 'reason': 'broad_treatment_only', 'matched': matched}

    if matched and len(words) >= 6:
        return {'sufficient': True, 'reason': 'required_evidence', 'matched': matched}
    if len(words) >= 12:
        return {'sufficient': True, 'reason': 'word_count', 'matched': len(words)}
    return {'sufficient': False, 'reason': 'missing_required_evidence', 'matched': matched}


def _advance_step(state: dict[str, Any]) -> dict[str, str] | None:
    state['step_index'] = int(state.get('step_index') or 0) + 1
    state['followup_count'] = 0
    state['repair_count'] = 0
    return current_step(state)


def _task(task_type: str, state: dict[str, Any], **extra: Any) -> dict[str, Any]:
    phase = extra.pop('phase', state.get('phase', 'INTRO'))
    step = extra.get('step', current_step(state))
    state['last_task'] = task_type
    state['last_step_id'] = step.get('id') if step else None
    return {'type': task_type, 'phase': phase, 'step': step, **extra}


def decide_next_task(state: dict[str, Any], user_input: str = '') -> dict[str, Any]:
    """Update state and return the next code-owned task."""
    normalized = normalize_state(state)
    state.clear()
    state.update(normalized)
    if state.get('complete'):
        return _task('already_complete', state, phase='PHOTOS', step=None)

    awaiting = state.get('awaiting')

    if awaiting == 'name':
        name_result = extract_patient_name(user_input)
        state['last_decision'] = {'name': name_result}
        if not name_result['name']:
            state['phase'] = 'INTRO'
            state['awaiting'] = 'name'
            return _task('repair_name', state, phase='INTRO', step=None, decision=name_result)
        state['patient_name'] = name_result['name']
        state['patient_name_status'] = 'confirmed'
        state['patient_name_source'] = 'user_explicit'
        state['phase'] = 'INTRO'
        state['awaiting'] = 'readiness'
        return _task('ask_readiness', state, phase='INTRO', step=None, decision=name_result)

    if awaiting == 'readiness':
        decision = readiness_decision(user_input)
        state['last_decision'] = {'readiness': decision}
        if decision['ready']:
            state['phase'] = 'STORY'
            state['awaiting'] = 'main_answer'
            state['followup_count'] = 0
            step = current_step(state)
            return _task('ask_main', state, phase=step['phase'], step=step, decision=decision)
        if decision['kind'] == 'question':
            state['phase'] = 'INTRO'
            state['awaiting'] = 'readiness'
            return _task('answer_readiness_question', state, phase='INTRO', step=None, decision=decision)
        state['phase'] = 'INTRO'
        state['awaiting'] = 'readiness'
        return _task('ask_readiness', state, phase='INTRO', step=None, decision=decision)

    if awaiting in {'main_answer', 'followup_answer'}:
        step = current_step(state)
        decision = sufficiency_decision(step, user_input)
        state['last_decision'] = {'sufficiency': decision}
        if step:
            evidence = state.setdefault('story_evidence', {})
            evidence[step['id']] = {
                'answer': user_input,
                'sufficiency': decision,
                'followup_count': state.get('followup_count', 0),
            }

        if (
            awaiting == 'main_answer'
            and step
            and not decision['sufficient']
            and int(state.get('followup_count') or 0) < 1
        ):
            state['followup_count'] = int(state.get('followup_count') or 0) + 1
            state['awaiting'] = 'followup_answer'
            state['phase'] = step['phase']
            return _task('ask_followup', state, phase=step['phase'], step=step, decision=decision)

        if step and not decision['sufficient']:
            state.setdefault('thin_evidence', {})[step['id']] = decision

        next_step = _advance_step(state)
        if next_step:
            state['awaiting'] = 'main_answer'
            state['phase'] = next_step['phase']
            task_type = 'ask_final' if next_step['id'] == 'final_details' else 'ack_then_next'
            return _task(task_type, state, phase=next_step['phase'], step=next_step, decision=decision)

        state['awaiting'] = 'photos'
        state['phase'] = 'PHOTOS'
        state['complete'] = True
        return _task('close_to_photos', state, phase='PHOTOS', step=None, decision=decision)

    state['awaiting'] = 'name'
    state['phase'] = 'INTRO'
    return _task('repair_name', state, phase='INTRO', step=None, decision={'reason': 'unknown_state'})


def deterministic_response(task: dict[str, Any], state: dict[str, Any]) -> str | None:
    task_type = task.get('type')
    name = state.get('patient_name') or ''
    if task_type == 'repair_name':
        return "I want to make sure I get your name right for the donor page. What name would you like me to use?"
    if task_type == 'close_to_photos':
        return FINAL_PHOTOS_PROMPT
    if task_type == 'already_complete':
        return "The story interview is complete. You can continue with the photo step."
    if task_type == 'ask_readiness' and task.get('decision', {}).get('kind') == 'not_ready':
        return "That's okay. Take your time, and when you're ready, tell me you want to begin."
    if task_type == 'ask_readiness' and task.get('decision', {}).get('kind') == 'unclear':
        return "Before we start the story questions, are you ready to begin?"
    if task_type == 'answer_readiness_question':
        return (
            "This conversation helps create a donor page by collecting your story in your own words. "
            "You can skip anything or correct me at any point. Are you ready to begin?"
        )
    if task_type == 'ask_readiness' and name:
        return (
            f"Thank you, {name}. I'll ask about your life, your kidney journey, and what a transplant could mean for you. "
            "You can skip anything or correct me at any point. Are you ready to begin?"
        )
    return None


def build_runtime_directive(task: dict[str, Any]) -> str:
    """Render a turn-specific instruction block for the LLM."""
    task_type = task.get('type')
    step = task.get('step') or {}
    question = step.get('question', '')
    focus = step.get('focus', '')
    required = step.get('required', '')

    if task_type == 'ask_main':
        return (
            'RUNTIME TURN DIRECTIVE:\n'
            '- The patient is ready to begin the donor-story interview.\n'
            f'- Ask this donor-story question in natural conversational wording: "{question}"\n'
            f'- Listen for: {focus}.\n'
            '- Ask only one question.'
        )
    if task_type == 'ask_followup':
        return (
            'RUNTIME TURN DIRECTIVE:\n'
            '- The previous answer was too short or missing important story detail.\n'
            '- Briefly acknowledge what the patient said.\n'
            f'- Ask one open follow-up for the same topic: {focus}.\n'
            f'- The answer should help capture: {required}.\n'
            '- Begin with What, How, or Tell me about.\n'
            '- Do not move to a new topic. Ask only one question.'
        )
    if task_type in {'ack_then_next', 'ask_final'}:
        return (
            'RUNTIME TURN DIRECTIVE:\n'
            '- Briefly acknowledge what the patient just shared.\n'
            f'- Then ask this next donor-story question in natural conversational wording: "{question}"\n'
            f'- Listen for: {focus}.\n'
            '- Ask only one question.'
        )
    return (
        'RUNTIME TURN DIRECTIVE:\n'
        '- Output only patient-facing speech.\n'
        '- Ask only one question.'
    )

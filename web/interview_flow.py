"""Deterministic donor-story interview flow helpers.

The LLM should make the interview sound natural, but code owns the
interview contract: intake, story order, follow-up depth, and completion.
"""

from __future__ import annotations

import re
from typing import Any, Callable


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

PROGRESS_LABELS = {
    'INTRO': 'Getting started',
    'WELCOME': 'Getting started',
    'STORY': 'Story interview',
    'FINAL_DETAILS': 'Final story details',
    'PHOTOS': 'Adding photos',
    'COMPLETE': 'Review and publish',
}

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

NO_RESPONSE_SENTINEL = '[no speech detected]'

ACKNOWLEDGEMENT_ONLY = {
    'yes', 'yeah', 'yep', 'yup', 'yea',
    'ok', 'okay', 'alright', 'all right', 'sure',
    'fine', 'good', 'right', 'correct',
}

CLARIFICATION_REQUESTS = {
    'what', 'huh', 'sorry', 'repeat', 'repeat that', 'say that again',
    'can you repeat', 'could you repeat', 'what do you mean',
}

OPERATIONAL_ISSUE_TERMS = {
    'clunky', 'frustrating', 'super frustrating', 'microphone', 'mic',
    'not picking', 'picking stuff up', 'pick stuff up', 'not hearing',
    "didn't hear", 'did not hear', 'speak louder', 'repeat what you said',
    'try again', 'cutting me off', 'cuts me off', 'not responsive',
    'taking a while', 'too slow', 'slower', 'hear me',
}

SKIP_TERMS = {
    'skip',
    'skip this',
    'skip this question',
    'pass',
    'i pass',
    'next',
    'next question',
    'move on',
    'prefer not to answer',
    "i'd rather not answer",
    'rather not answer',
    'do not want to answer',
    "don't want to answer",
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

SECTION_TRANSITIONS: dict[str, str] = {
    'personal_background': "Let's start with who you are as a person.",
    'medical_history': "Now I want to understand the beginning of your kidney journey.",
    'daily_life': "Next, let's talk about what day-to-day life has been like.",
    'transplant_hope': "Now let's talk about what a transplant could make possible for you.",
    'donor_message': "Next, let's focus on what you would want a potential donor to understand.",
    'support_network': "I also want to understand who has been walking through this with you.",
    'final_details': "Before we move to photos, let's make sure we have not missed anything important.",
}

FOLLOWUP_QUESTIONS: dict[str, str] = {
    'personal_background': 'Could you tell me a little more about who you are outside of your illness?',
    'medical_history': 'Could you share a little more about when this kidney journey started for you?',
    'daily_life': 'Could you tell me more about how kidney failure affects your normal day?',
    'transplant_hope': 'Could you say more about what a transplant would help you do or feel again?',
    'donor_message': 'Could you tell me more about what you would want a potential donor to understand about you?',
    'support_network': 'Could you tell me a little more about who supports you, or whether support has been limited?',
    'final_details': 'Could you tell me what else you would like included, or say that there is nothing else?',
}

DEEPENING_MAX_PER_STEP = 1

CONTENT_STOPWORDS = {
    'a', 'an', 'and', 'are', 'as', 'at', 'be', 'been', 'but', 'by', 'can',
    'could', 'do', 'for', 'from', 'has', 'have', 'how', 'i', 'if', 'in',
    'is', 'it', 'me', 'my', 'of', 'or', 'that', 'the', 'this', 'to', 'want',
    'what', 'when', 'with', 'would', 'you', 'your',
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
        'skipped_steps': {},
        'thin_evidence': {},
        'deepening_count_by_step': {},
        'last_followup_kind': None,
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
    base.setdefault('skipped_steps', {})
    base.setdefault('thin_evidence', {})
    base.setdefault('deepening_count_by_step', {})
    base.setdefault('last_followup_kind', None)
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
    if not usable or len(usable) > 4:
        return None
    if any(len(t) < 2 for t in usable):
        return None
    return ' '.join(t.capitalize() for t in usable)


def extract_patient_name(text: str) -> dict[str, Any]:
    """Extract an explicit patient name without guessing."""
    raw = (text or '').strip()
    for marker in NAME_MARKERS:
        match = re.search(rf'\b{marker}\b\s*([A-Za-z][A-Za-z\'-]*(?:\s+[A-Za-z][A-Za-z\'-]*){{0,3}})?', raw, re.I)
        if match:
            candidate = (match.group(1) or '').strip()
            name = _name_from_tokens(candidate)
            if name:
                return {'name': name, 'status': 'captured', 'reason': 'explicit_marker'}
            return {'name': None, 'status': 'missing', 'reason': 'incomplete_marker'}

    name = _name_from_tokens(raw)
    if name and len(raw.split()) <= 4:
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


def progress_snapshot(state: dict[str, Any] | None, phase: str | None = None, photo_count: int = 0) -> dict[str, Any]:
    """Return patient-facing progress metadata for the current interview state."""
    state = normalize_state(state)
    phase = phase or state.get('phase') or 'INTRO'
    total = len(INTERVIEW_STEPS)
    step = current_step(state)
    step_index = int(state.get('step_index') or 0)
    story_step = min(max(step_index + 1, 1), total)

    if phase in {'WELCOME', 'INTRO'}:
        percent = 8 if state.get('awaiting') == 'name' else 14
        current = 0
    elif phase in {'STORY', 'FINAL_DETAILS'}:
        current = story_step
        percent = 15 + round((min(step_index, total - 1) / max(total - 1, 1)) * 65)
    elif phase == 'PHOTOS':
        current = total
        percent = min(92, 82 + max(0, min(photo_count, 3)) * 3)
    elif phase == 'COMPLETE':
        current = total
        percent = 100
    else:
        current = story_step if step else 0
        percent = 20

    return {
        'phase': phase,
        'label': PROGRESS_LABELS.get(phase, 'Interview'),
        'current_step': current,
        'total_steps': total,
        'current_step_id': step.get('id') if step else None,
        'current_step_question': step.get('question') if step else None,
        'percent': max(0, min(100, percent)),
    }


def _word_count(text: str) -> int:
    normalized = normalize_answer(text)
    return len(normalized.split()) if normalized else 0


def _has_explicit_none(text: str) -> bool:
    normalized = normalize_answer(text)
    if normalized in {'no', 'nope', 'none', 'nothing', 'not really', 'nothing else', 'no thank you', 'no thanks'}:
        return True
    none_patterns = (
        r'\bno\b.*\bnothing\b',
        r'\bno\b.*\bthank\b',
        r'\bno\b.*\bthanks\b',
        r'\bnothing\b.*\belse\b',
        r'\bnothing\b.*\breally\b',
        r'\bnot\b.*\breally\b',
        r'\bno\b.*\belse\b',
    )
    return any(re.search(pattern, normalized) for pattern in none_patterns)


def _is_operational_issue(text: str, turn_meta: dict[str, Any] | None = None) -> bool:
    normalized = normalize_answer(text)
    if not normalized:
        return False
    if any(term in normalized for term in OPERATIONAL_ISSUE_TERMS):
        return True

    turn_meta = turn_meta or {}
    try:
        retry_count = int(turn_meta.get('retry_count') or 0)
    except (TypeError, ValueError):
        retry_count = 0
    if retry_count < 2:
        return False

    events = turn_meta.get('events') or []
    empty_events = sum(1 for event in events if (event.get('type') or event.get('event_type')) == 'empty_input')
    if empty_events < 1:
        return False

    operational_words = {'hear', 'heard', 'listen', 'repeat', 'again', 'louder', 'slow', 'frustrating', 'work', 'working'}
    return bool(operational_words.intersection(normalized.split()))


def is_skip_intent(text: str, turn_meta: dict[str, Any] | None = None) -> bool:
    """Return whether the patient explicitly chose to skip the current story question."""
    turn_meta = turn_meta or {}
    if turn_meta.get('skip_requested'):
        return True
    normalized = normalize_answer(text)
    if not normalized:
        return False
    if normalized in SKIP_TERMS:
        return True
    return any(term in normalized for term in {
        'skip this question',
        'prefer not to answer',
        'rather not answer',
        'do not want to answer',
        "don't want to answer",
        'move on to the next',
    })


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
    if len(words) >= 12 and step_id not in {'daily_life', 'support_network', 'final_details'}:
        return {'sufficient': True, 'reason': 'word_count', 'matched': len(words)}
    return {'sufficient': False, 'reason': 'missing_required_evidence', 'matched': matched}


def _content_words(text: str) -> set[str]:
    words = set(normalize_answer(text).split())
    return {word for word in words if len(word) > 2 and word not in CONTENT_STOPWORDS}


def validate_deepening_decision(
    step: dict[str, str] | None,
    text: str,
    state: dict[str, Any],
    candidate: dict[str, Any] | None,
) -> dict[str, Any]:
    """Validate an LLM-proposed story-deepening follow-up against code-owned guardrails."""
    if not step:
        return {'should_deepen': False, 'reason': 'no_step', 'question': None, 'evidence_quote': ''}

    step_id = step['id']
    if step_id == 'final_details':
        return {'should_deepen': False, 'reason': 'final_details_no_deepening', 'question': None, 'evidence_quote': ''}

    counts = state.setdefault('deepening_count_by_step', {})
    if int(counts.get(step_id) or 0) >= DEEPENING_MAX_PER_STEP:
        return {'should_deepen': False, 'reason': 'deepening_limit_reached', 'question': None, 'evidence_quote': ''}

    if not isinstance(candidate, dict):
        return {'should_deepen': False, 'reason': 'invalid_planner_output', 'question': None, 'evidence_quote': ''}
    if not candidate.get('should_deepen'):
        return {
            'should_deepen': False,
            'reason': str(candidate.get('reason') or 'planner_declined')[:120],
            'question': None,
            'evidence_quote': str(candidate.get('evidence_quote') or '')[:180],
        }

    question = str(candidate.get('followup_question') or candidate.get('question') or '').strip()
    evidence_quote = str(candidate.get('evidence_quote') or '').strip()
    reason = str(candidate.get('reason') or 'planner_deepening')[:120]

    if not 20 <= len(question) <= 240:
        return {'should_deepen': False, 'reason': 'invalid_question_length', 'question': None, 'evidence_quote': evidence_quote}
    if question.count('?') != 1 or not question.endswith('?'):
        return {'should_deepen': False, 'reason': 'question_must_be_single_question', 'question': None, 'evidence_quote': evidence_quote}

    answer_words = _content_words(text)
    quote_words = _content_words(evidence_quote)
    question_words = _content_words(question)
    if not answer_words or not quote_words:
        return {'should_deepen': False, 'reason': 'missing_grounding_evidence', 'question': None, 'evidence_quote': evidence_quote}
    if not quote_words.issubset(answer_words):
        return {'should_deepen': False, 'reason': 'evidence_quote_not_in_answer', 'question': None, 'evidence_quote': evidence_quote}
    if not question_words.intersection(answer_words):
        return {'should_deepen': False, 'reason': 'question_not_grounded_in_answer', 'question': None, 'evidence_quote': evidence_quote}

    return {
        'should_deepen': True,
        'reason': reason,
        'question': question,
        'evidence_quote': evidence_quote,
    }


def can_request_deepening(step: dict[str, str] | None, state: dict[str, Any]) -> bool:
    if not step or step.get('id') == 'final_details':
        return False
    counts = state.setdefault('deepening_count_by_step', {})
    return int(counts.get(step['id']) or 0) < DEEPENING_MAX_PER_STEP


def no_deepening_decider(step: dict[str, str] | None, text: str, state: dict[str, Any]) -> dict[str, Any]:
    """Default planner for deterministic tests and degraded operation."""
    return {'should_deepen': False, 'reason': 'no_planner', 'question': None, 'evidence_quote': ''}


def input_guard_decision(step: dict[str, str] | None, text: str, turn_meta: dict[str, Any] | None = None) -> dict[str, Any]:
    """Detect non-answers before they can advance the story state."""
    normalized = normalize_answer(text)
    words = normalized.split()
    turn_meta = turn_meta or {}
    step_id = step.get('id') if step else None

    if turn_meta.get('no_response') or normalized == normalize_answer(NO_RESPONSE_SENTINEL) or not normalized:
        return {'repair': True, 'reason': 'empty_or_no_response', 'matched': normalized}

    if _is_operational_issue(normalized, turn_meta):
        return {'repair': True, 'reason': 'operational_issue', 'matched': normalized}

    if normalized in CLARIFICATION_REQUESTS or any(term == normalized for term in CLARIFICATION_REQUESTS):
        return {'repair': True, 'reason': 'clarification_request', 'matched': normalized}

    if len(words) <= 4 and any(term in normalized for term in CLARIFICATION_REQUESTS):
        return {'repair': True, 'reason': 'clarification_request', 'matched': normalized}

    explicit_none_allowed = step_id in {'support_network', 'final_details'} and _has_explicit_none(normalized)
    if normalized in ACKNOWLEDGEMENT_ONLY or (normalized in {'no', 'nah', 'nope'} and not explicit_none_allowed):
        return {'repair': True, 'reason': 'acknowledgement_only', 'matched': normalized}

    if len(words) <= 2 and not explicit_none_allowed:
        return {'repair': True, 'reason': 'too_short_fragment', 'matched': normalized}

    confidence = turn_meta.get('speech_confidence')
    try:
        low_confidence = confidence is not None and float(confidence) > 0 and float(confidence) < 0.45
    except (TypeError, ValueError):
        low_confidence = False
    if low_confidence and len(words) < 5:
        return {'repair': True, 'reason': 'low_confidence_fragment', 'matched': normalized}

    return {'repair': False, 'reason': 'answer_candidate', 'matched': normalized}


def _advance_step(state: dict[str, Any]) -> dict[str, str] | None:
    state['step_index'] = int(state.get('step_index') or 0) + 1
    state['followup_count'] = 0
    state['repair_count'] = 0
    state['last_followup_kind'] = None
    return current_step(state)


def _record_story_evidence(
    state: dict[str, Any],
    step: dict[str, str] | None,
    user_input: str,
    decision: dict[str, Any],
    answer_kind: str = 'main_answer',
) -> None:
    if not step:
        return
    entry = {
        'answer': user_input,
        'sufficiency': decision,
        'followup_count': state.get('followup_count', 0),
        'answer_kind': answer_kind,
        'followup_kind': state.get('last_followup_kind') if answer_kind == 'followup_answer' else None,
        'accepted': bool(decision.get('sufficient')),
    }
    evidence = state.setdefault('story_evidence', {})
    step_entries = evidence.setdefault(step['id'], [])
    if isinstance(step_entries, list):
        step_entries.append(entry)
    else:
        evidence[step['id']] = [step_entries, entry]


def _record_skipped_step(state: dict[str, Any], step: dict[str, str] | None, user_input: str, awaiting: str) -> None:
    if not step:
        return
    skipped = state.setdefault('skipped_steps', {})
    skipped[step['id']] = {
        'question': step.get('question'),
        'phase': step.get('phase'),
        'answer_kind': awaiting,
        'reason': 'patient_requested_skip',
        'utterance': user_input,
    }


def _task(task_type: str, state: dict[str, Any], **extra: Any) -> dict[str, Any]:
    phase = extra.pop('phase', state.get('phase', 'INTRO'))
    step = extra.get('step', current_step(state))
    state['last_task'] = task_type
    state['last_step_id'] = step.get('id') if step else None
    return {'type': task_type, 'phase': phase, 'step': step, **extra}


def decide_next_task(
    state: dict[str, Any],
    user_input: str = '',
    turn_meta: dict[str, Any] | None = None,
    deepening_decider: Callable[[dict[str, str] | None, str, dict[str, Any]], dict[str, Any]] | None = None,
) -> dict[str, Any]:
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
        if step and is_skip_intent(user_input, turn_meta):
            _record_skipped_step(state, step, user_input, awaiting)
            state['last_decision'] = {'skip': {'skipped': True, 'step_id': step['id']}}
            next_step = _advance_step(state)
            if next_step:
                state['awaiting'] = 'main_answer'
                state['phase'] = next_step['phase']
                return _task('skip_then_next', state, phase=next_step['phase'], step=next_step, skipped_step=step)

            state['awaiting'] = 'photos'
            state['phase'] = 'PHOTOS'
            state['complete'] = True
            return _task('skip_to_photos', state, phase='PHOTOS', step=None, skipped_step=step)

        guard = input_guard_decision(step, user_input, turn_meta)
        if guard['repair']:
            state['last_decision'] = {'input_guard': guard}
            state['repair_count'] = int(state.get('repair_count') or 0) + 1
            state['phase'] = step['phase'] if step else 'STORY'
            state['awaiting'] = awaiting
            return _task('repair_answer', state, phase=state['phase'], step=step, decision=guard)

        decision = sufficiency_decision(step, user_input)
        state['last_decision'] = {'sufficiency': decision}
        answered_followup_kind = state.get('last_followup_kind') if awaiting == 'followup_answer' else None
        _record_story_evidence(state, step, user_input, decision, awaiting)

        if (
            awaiting == 'main_answer'
            and step
            and not decision['sufficient']
            and int(state.get('followup_count') or 0) < 1
        ):
            state['followup_count'] = int(state.get('followup_count') or 0) + 1
            state['last_followup_kind'] = 'repair'
            state['awaiting'] = 'followup_answer'
            state['phase'] = step['phase']
            return _task('ask_followup', state, phase=step['phase'], step=step, decision=decision)

        if awaiting == 'main_answer' and step and decision['sufficient'] and can_request_deepening(step, state):
            planner = deepening_decider or no_deepening_decider
            try:
                candidate_deepening = planner(step, user_input, state)
            except Exception as e:
                candidate_deepening = {'should_deepen': False, 'reason': f'planner_error:{type(e).__name__}'}
            deepening = validate_deepening_decision(step, user_input, state, candidate_deepening)
            if deepening['should_deepen']:
                counts = state.setdefault('deepening_count_by_step', {})
                counts[step['id']] = int(counts.get(step['id']) or 0) + 1
                state['last_decision'] = {'sufficiency': decision, 'deepening': deepening}
                state['last_followup_kind'] = 'deepening'
                state['awaiting'] = 'followup_answer'
                state['phase'] = step['phase']
                return _task('ask_deepening', state, phase=step['phase'], step=step, decision=deepening, sufficiency=decision)

        if step and not decision['sufficient']:
            state.setdefault('thin_evidence', {})[step['id']] = decision

        next_step = _advance_step(state)
        if next_step:
            state['awaiting'] = 'main_answer'
            state['phase'] = next_step['phase']
            task_type = 'ask_final' if next_step['id'] == 'final_details' else 'ack_then_next'
            return _task(
                task_type,
                state,
                phase=next_step['phase'],
                step=next_step,
                decision=decision,
                answered_followup_kind=answered_followup_kind,
            )

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
    step = task.get('step') or {}
    step_id = step.get('id')
    question = step.get('question')
    if task_type == 'repair_name':
        return "I want to make sure I show your name correctly. What name would you like shown publicly on your donor page?"
    if task_type == 'close_to_photos':
        return FINAL_PHOTOS_PROMPT
    if task_type == 'already_complete':
        return "The story interview is complete. You can continue with the photo step."
    if task_type == 'skip_to_photos':
        return f"No problem, we can skip that. {FINAL_PHOTOS_PROMPT}"
    if task_type == 'skip_then_next' and question:
        return f"No problem, we can skip that. {SECTION_TRANSITIONS.get(step_id, 'Let us continue with the next part of your story')} {question}"
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
    if task_type == 'ask_main' and question:
        return f"{SECTION_TRANSITIONS.get(step_id, 'Let us continue with your story')} {question}"
    if task_type == 'ack_then_next' and question:
        prefix = 'That gives this part of your story more depth.' if task.get('answered_followup_kind') == 'deepening' else 'Thank you for sharing that.'
        return f"{prefix} {SECTION_TRANSITIONS.get(step_id, 'Let us continue with the next part of your story')} {question}"
    if task_type == 'ask_final' and question:
        prefix = 'That gives this part of your story more depth.' if task.get('answered_followup_kind') == 'deepening' else 'Thank you, that helps tell your story.'
        return f"{prefix} {SECTION_TRANSITIONS.get(step_id, 'Before we move on,')} {question}"
    if task_type == 'ask_followup' and step_id:
        return f"I want to make sure I capture this part clearly. {FOLLOWUP_QUESTIONS.get(step_id, question)}"
    if task_type == 'ask_deepening':
        deepening_question = (task.get('decision') or {}).get('question')
        if deepening_question:
            return deepening_question
    if task_type == 'repair_answer' and question:
        decision = task.get('decision') or {}
        if decision.get('reason') == 'clarification_request':
            return f"Sure. I was asking about this part of your donor story: {question}"
        if decision.get('reason') == 'empty_or_no_response':
            return f"I did not catch that clearly. Please try again: {question}"
        if decision.get('reason') == 'operational_issue':
            return f"I am sorry, it sounds like the microphone had trouble. Let's try the same question again: {question}"
        return f"I only caught a little of that. {question}"
    return None


def expected_question_text(task: dict[str, Any]) -> str | None:
    """Return the exact question the backend expects this task to deliver."""
    task_type = task.get('type')
    step = task.get('step') or {}
    if task_type in {'ask_main', 'ack_then_next', 'ask_final', 'repair_answer', 'skip_then_next'}:
        return step.get('question')
    if task_type == 'ask_followup':
        return FOLLOWUP_QUESTIONS.get(step.get('id')) or step.get('question')
    if task_type == 'ask_deepening':
        return (task.get('decision') or {}).get('question')
    if task_type == 'repair_name':
        return 'What name would you like shown publicly on your donor page?'
    if task_type in {'ask_readiness', 'answer_readiness_question'}:
        return 'Are you ready to begin?'
    return None


def expected_answer_kind(task: dict[str, Any], state: dict[str, Any]) -> str | None:
    task_type = task.get('type')
    if task_type == 'repair_name':
        return 'name'
    if task_type in {'ask_readiness', 'answer_readiness_question'}:
        return 'readiness'
    if task_type in {'ask_main', 'ack_then_next', 'ask_final', 'repair_answer', 'skip_then_next'}:
        return state.get('awaiting') or 'main_answer'
    if task_type in {'ask_followup', 'ask_deepening'}:
        return 'followup_answer'
    return None


def build_outgoing_turn_contract(task: dict[str, Any], state: dict[str, Any], response: str, turn_id: str) -> dict[str, Any]:
    """Record what the user actually received and what answer is expected next."""
    question = expected_question_text(task)
    step = task.get('step') or {}
    delivery_validated = bool(question and question in response)
    return {
        'outgoing_turn_id': turn_id,
        'asked_step_id': step.get('id'),
        'asked_question_text': question,
        'expected_answer_kind': expected_answer_kind(task, state),
        'delivered_phase': task.get('phase'),
        'delivery_validated': delivery_validated,
        'task_type': task.get('type'),
    }


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
    if task_type == 'ask_deepening':
        return (
            'RUNTIME TURN DIRECTIVE:\n'
            '- The previous answer was usable, but included an important story detail worth understanding more deeply.\n'
            '- Stay on the same topic.\n'
            '- Ask the provided story-deepening follow-up question exactly.\n'
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

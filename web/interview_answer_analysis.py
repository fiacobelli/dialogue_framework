"""Answer parsing and guardrails for the donor-story interview flow."""

from __future__ import annotations

import re
from typing import Any

from .interview_flow_config import (
    ACKNOWLEDGEMENT_ONLY,
    CLARIFICATION_REQUESTS,
    CONTENT_STOPWORDS,
    DEEPENING_MAX_PER_STEP,
    DETAIL_TERMS,
    NAME_MARKERS,
    NOT_READY_TERMS,
    NO_RESPONSE_SENTINEL,
    OPERATIONAL_ISSUE_TERMS,
    READINESS_QUESTION_TERMS,
    READY_TERMS,
    REJECT_NAME_WORDS,
    SHORT_ANSWERS,
    SKIP_TERMS,
)


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

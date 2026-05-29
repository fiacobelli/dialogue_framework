"""Single answer-decision path for the donor-story interview."""

from __future__ import annotations

import re
from typing import Any

from .interview_flow_config import (
    ACKNOWLEDGEMENT_ONLY,
    CLARIFICATION_REQUESTS,
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


PRIOR_REFERENCE_PATTERNS = (
    r'\bi (already|previously) (said|mentioned|told|answered)\b',
    r'\bi did (say|mention|tell|answer) (that|this|it)\b',
    r'\b(as|like) i (said|mentioned|told you)\b',
    r'\bmentioned it before\b',
    r'\bsaid it before\b',
    r'\balready (said|mentioned|answered|told you)\b',
    r'\bi literally told you\b',
)

CRISIS_PATTERNS = (
    r'\bkill myself\b',
    r'\bend my life\b',
    r'\bhurt myself\b',
    r'\bsuicidal\b',
    r'\bdo not want to live\b',
    r"\bdon't want to live\b",
)


def normalize_answer(text: str) -> str:
    text = (text or '').lower().strip()
    text = re.sub(r"[^a-z0-9'\s-]", ' ', text)
    return re.sub(r'\s+', ' ', text).strip()


def _name_from_tokens(raw: str) -> str | None:
    tokens = re.findall(r"[A-Za-z][A-Za-z'-]*", raw or '')
    usable = [t for t in tokens if t.lower() not in REJECT_NAME_WORDS]
    if len(usable) % 2 == 0 and usable[:len(usable) // 2] == usable[len(usable) // 2:]:
        usable = usable[:len(usable) // 2]
    if not usable or len(usable) > 4:
        return None
    if any(len(t) < 2 for t in usable):
        return None
    return ' '.join(t.capitalize() for t in usable)


def extract_patient_name(text: str) -> dict[str, Any]:
    """Extract a public display name from natural patient wording."""
    raw = (text or '').strip()
    for marker in (*NAME_MARKERS, r'i would like to use', r'i want to use', r'use'):
        if re.search(rf'\b{marker}\b\s*$', raw, re.I):
            return {'name': None, 'status': 'missing', 'reason': 'incomplete_marker'}
        match = re.search(
            rf'\b{marker}\b\s*([A-Za-z][A-Za-z\'-]*(?:\s+[A-Za-z][A-Za-z\'-]*){{0,3}})(?=[.!?,]|$)',
            raw,
            re.I,
        )
        if match:
            name = _name_from_tokens((match.group(1) or '').strip())
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
    if normalized in {
        'no', 'nah', 'nope', 'none', 'nothing', 'not really', 'nothing else',
        'no thank you', 'no thanks', 'no that is all', 'no that is enough',
        'that is all', 'that is enough', 'that covers it', 'i am good',
        "i'm good", 'im good', 'nah i am good', 'nah im good',
    }:
        return True
    return any(re.search(pattern, normalized) for pattern in (
        r'\bno\b.*\bnothing\b',
        r'\bno\b.*\bthank\b',
        r'\bno\b.*\bthanks\b',
        r'\bno\b.*\b(that is|thats|that\'s)\b.*\b(all|enough)\b',
        r'\bnothing\b.*\belse\b',
        r'\bnothing\b.*\breally\b',
        r'\bnot\b.*\breally\b',
        r'\bno\b.*\belse\b',
        r'\b(that is|thats|that\'s)\b.*\b(all|enough|fine|good)\b',
        r'\b(that|this)\b.*\bcovers\b.*\bit\b',
        r'\bi\b.*\b(am|m)\b.*\bgood\b',
        r'\bnah\b.*\bgood\b',
        r"\bi'?m done\b",
    ))


def _is_short_section_evidence(step_id: str | None, normalized: str) -> bool:
    """Allow concise but meaningful answers without treating them as mic failures."""
    if not step_id or not normalized:
        return False
    if step_id == 'medical_history':
        return bool(re.search(r'\b(19|20)\d{2}\b', normalized))
    short_terms = {
        'personal_background': {
            'father', 'mother', 'mom', 'dad', 'grandmother', 'grandfather',
            'grandma', 'grandpa', 'wife', 'husband', 'teacher', 'barber',
            'veteran', 'driver', 'nurse', 'student',
        },
        'daily_life': {'tired', 'fatigue', 'exhausted', 'pain', 'sad', 'scared', 'drained'},
        'transplant_hope': {'energy', 'freedom', 'independence', 'independent', 'travel', 'work'},
        'donor_message': {'grateful', 'hopeful', 'family', 'chance', 'help'},
        'support_network': {
            'family', 'wife', 'husband', 'mother', 'father', 'mom', 'dad',
            'daughter', 'son', 'sister', 'brother', 'church', 'friends',
        },
    }
    terms = short_terms.get(step_id, set())
    return any(re.search(rf'\b{re.escape(term)}\b', normalized) for term in terms)


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


def _pushback_detected(text: str) -> bool:
    normalized = normalize_answer(text)
    return bool(normalized and any(re.search(pattern, normalized) for pattern in PRIOR_REFERENCE_PATTERNS))


def _crisis_detected(text: str) -> bool:
    normalized = normalize_answer(text)
    return any(re.search(pattern, normalized) for pattern in CRISIS_PATTERNS)


def _accepted_evidence_for_step(state: dict[str, Any], step_id: str | None) -> list[dict[str, Any]]:
    if not step_id:
        return []
    entries = (state.get('story_evidence') or {}).get(step_id) or []
    if isinstance(entries, dict):
        entries = [entries]
    return [entry for entry in entries if isinstance(entry, dict) and entry.get('accepted')]


def policy_from_frame(
    step: dict[str, str] | None,
    state: dict[str, Any],
    turn_meta: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Map semantic NLU evidence into a bounded policy decision."""
    frame = (turn_meta or {}).get('evidence_interpretation_shadow') or {}
    if not frame.get('valid'):
        return None
    step_id = step.get('id') if step else None
    current = frame.get('current_step') if isinstance(frame.get('current_step'), dict) else {}
    status = current.get('status')
    summary = current.get('summary')
    confidence = current.get('confidence') or 0
    prior = _accepted_evidence_for_step(state, step_id)

    if frame.get('already_answered_current') and prior:
        return {
            'sufficient': True,
            'action': 'accept_and_advance',
            'record_current_answer': False,
            'usable_evidence': True,
            'prior_evidence_used': True,
            'pushback_detected': True,
            'reason': 'semantic_prior_evidence',
            'matched': summary,
            'semantic_confidence': confidence,
        }
    if status in {'sufficient', 'explicit_none'} and confidence >= 0.55:
        return {
            'sufficient': True,
            'action': 'accept_and_advance',
            'record_current_answer': True,
            'usable_evidence': True,
            'prior_evidence_used': False,
            'pushback_detected': False,
            'reason': f'semantic_{status}',
            'matched': summary,
            'semantic_confidence': confidence,
        }
    if status in {'thin', 'not_addressed'} and confidence >= 0.55:
        return {
            'sufficient': False,
            'action': 'ask_followup',
            'record_current_answer': False,
            'usable_evidence': False,
            'prior_evidence_used': False,
            'pushback_detected': False,
            'reason': f'semantic_{status}',
            'matched': summary,
            'semantic_confidence': confidence,
        }
    return None


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
    short_section_evidence = _is_short_section_evidence(step_id, normalized)
    if normalized in ACKNOWLEDGEMENT_ONLY or (normalized in {'no', 'nah', 'nope'} and not explicit_none_allowed):
        return {'repair': True, 'reason': 'acknowledgement_only', 'matched': normalized}
    if len(words) <= 2 and not explicit_none_allowed and not short_section_evidence:
        return {'repair': True, 'reason': 'too_short_fragment', 'matched': normalized}

    try:
        confidence = turn_meta.get('speech_confidence')
        low_confidence = confidence is not None and float(confidence) > 0 and float(confidence) < 0.45
    except (TypeError, ValueError):
        low_confidence = False
    if low_confidence and len(words) < 5:
        return {'repair': True, 'reason': 'low_confidence_fragment', 'matched': normalized}
    return {'repair': False, 'reason': 'answer_candidate', 'matched': normalized}


def sufficiency_decision(step: dict[str, str] | None, text: str) -> dict[str, Any]:
    """Leniently decide whether an answer has usable donor-story evidence."""
    if not step:
        return {'sufficient': True, 'reason': 'no_step', 'matched': None}
    step_id = step['id']
    normalized = normalize_answer(text)
    words = normalized.split()
    if not normalized:
        return {'sufficient': False, 'reason': 'empty', 'matched': None}
    if step_id in {'support_network', 'final_details'} and _has_explicit_none(normalized):
        return {'sufficient': True, 'reason': 'explicit_none', 'matched': normalized}
    if _is_short_section_evidence(step_id, normalized):
        return {'sufficient': True, 'reason': 'short_section_evidence', 'matched': normalized}
    if normalized in SHORT_ANSWERS:
        return {'sufficient': False, 'reason': 'short_answer', 'matched': normalized}

    terms = DETAIL_TERMS.get(step_id, set())
    matched = sorted(term for term in terms if re.search(rf'\b{re.escape(term)}\b', normalized))
    if step_id == 'medical_history':
        has_time = bool(re.search(r'\b(\d+|one|two|three|four|five|six|seven|eight|nine|ten)\s+(year|years|month|months)\s+ago\b', normalized))
        if has_time or 'diagnosed' in normalized or 'dialysis' in normalized or len(words) >= 10:
            return {'sufficient': True, 'reason': 'medical_timing_or_context', 'matched': matched or normalized}
    if step_id == 'daily_life' and matched and set(matched).issubset({'dialysis', 'treatment'}):
        return {'sufficient': False, 'reason': 'broad_treatment_only', 'matched': matched}
    if matched and len(words) >= 5:
        return {'sufficient': True, 'reason': 'current_evidence', 'matched': matched}
    if len(words) >= 7 and step_id != 'final_details':
        return {'sufficient': True, 'reason': 'current_evidence_word_count', 'matched': len(words)}
    return {'sufficient': False, 'reason': 'thin_answer_followup', 'matched': matched}


def classify_story_answer(
    step: dict[str, str] | None,
    text: str,
    state: dict[str, Any],
    turn_meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Single owner for story-answer decisions."""
    step_id = step.get('id') if step else None
    pushback = _pushback_detected(text)
    prior = _accepted_evidence_for_step(state, step_id)

    if _crisis_detected(text):
        return {
            'sufficient': False,
            'action': 'safety_response',
            'record_current_answer': False,
            'usable_evidence': False,
            'prior_evidence_used': False,
            'pushback_detected': pushback,
            'reason': 'safety_crisis',
            'question': 'Would you like to pause here?',
        }

    semantic_decision = policy_from_frame(step, state, turn_meta)
    if semantic_decision:
        semantic_decision['pushback_detected'] = semantic_decision.get('pushback_detected') or pushback
        return semantic_decision

    guard = input_guard_decision(step, text, turn_meta)
    if guard['repair']:
        if pushback and prior:
            return {
                'sufficient': True,
                'action': 'accept_and_advance',
                'record_current_answer': False,
                'usable_evidence': True,
                'prior_evidence_used': True,
                'pushback_detected': True,
                'reason': 'prior_evidence_pushback',
                'matched': guard['matched'],
            }
        return {
            'sufficient': False,
            'action': 'ask_followup',
            'record_current_answer': False,
            'usable_evidence': False,
            'prior_evidence_used': False,
            'pushback_detected': pushback,
            'reason': guard['reason'],
            'matched': guard['matched'],
        }

    decision = sufficiency_decision(step, text)
    if decision['sufficient']:
        return {
            **decision,
            'action': 'accept_and_advance',
            'record_current_answer': True,
            'usable_evidence': True,
            'prior_evidence_used': False,
            'pushback_detected': pushback,
        }
    if pushback and prior:
        return {
            'sufficient': True,
            'action': 'accept_and_advance',
            'record_current_answer': False,
            'usable_evidence': True,
            'prior_evidence_used': True,
            'pushback_detected': True,
            'reason': 'prior_evidence_pushback',
            'matched': decision.get('matched'),
        }
    return {
        **decision,
        'action': 'ask_followup',
        'record_current_answer': False,
        'usable_evidence': False,
        'prior_evidence_used': False,
        'pushback_detected': pushback,
    }

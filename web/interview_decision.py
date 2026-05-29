"""Single answer-decision path for the donor-story interview.

Normal patient meaning must come from semantic NLU. This module only maps a
validated NLU frame to bounded state-machine decisions and keeps non-language
system guards such as missing audio and crisis safety.
"""

from __future__ import annotations

import re
from typing import Any

from .interview_flow_config import NO_RESPONSE_SENTINEL


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


def is_skip_intent(text: str, turn_meta: dict[str, Any] | None = None) -> bool:
    """Only an explicit UI skip event can skip a required story section."""
    return bool((turn_meta or {}).get('skip_requested'))


def _crisis_detected(text: str, turn_meta: dict[str, Any] | None = None) -> bool:
    frame = (turn_meta or {}).get('evidence_interpretation_shadow') or {}
    safety = frame.get('safety') if isinstance(frame.get('safety'), dict) else {}
    try:
        confidence = float(safety.get('confidence') or 0)
    except (TypeError, ValueError):
        confidence = 0
    if safety.get('crisis') and confidence >= 0.55:
        return True

    # Safety remains a deterministic guard; it is not used for ordinary flow.
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

    try:
        input_confidence = float(frame.get('input_quality_confidence') or 0)
    except (TypeError, ValueError):
        input_confidence = 0
    input_quality = frame.get('input_quality')
    if input_quality in {'clarification', 'operational_issue', 'non_answer', 'unclear'} and input_confidence >= 0.55:
        return {
            'sufficient': False,
            'action': 'ask_followup',
            'record_current_answer': False,
            'usable_evidence': False,
            'prior_evidence_used': False,
            'pushback_detected': False,
            'reason': f'semantic_{input_quality}',
            'matched': frame.get('repair_hint') or input_quality,
            'semantic_confidence': input_confidence,
        }

    step_id = step.get('id') if step else None
    current = frame.get('current_step') if isinstance(frame.get('current_step'), dict) else {}
    status = current.get('status')
    summary = current.get('summary')
    try:
        confidence = float(current.get('confidence') or 0)
    except (TypeError, ValueError):
        confidence = 0
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
    """Detect system-level input failures without guessing patient meaning."""
    normalized = normalize_answer(text)
    words = normalized.split()
    turn_meta = turn_meta or {}

    if turn_meta.get('no_response') or normalized == normalize_answer(NO_RESPONSE_SENTINEL) or not normalized:
        return {'repair': True, 'reason': 'empty_or_no_response', 'matched': normalized}

    try:
        confidence = turn_meta.get('speech_confidence')
        low_confidence = confidence is not None and float(confidence) > 0 and float(confidence) < 0.45
    except (TypeError, ValueError):
        low_confidence = False
    if low_confidence and len(words) < 5:
        return {'repair': True, 'reason': 'low_confidence_fragment', 'matched': normalized}
    return {'repair': False, 'reason': 'answer_candidate', 'matched': normalized}


def classify_story_answer(
    step: dict[str, str] | None,
    text: str,
    state: dict[str, Any],
    turn_meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Single owner for story-answer decisions."""
    if _crisis_detected(text, turn_meta):
        return {
            'sufficient': False,
            'action': 'safety_response',
            'record_current_answer': False,
            'usable_evidence': False,
            'prior_evidence_used': False,
            'pushback_detected': False,
            'reason': 'safety_crisis',
            'question': 'Would you like to pause here?',
        }

    semantic_decision = policy_from_frame(step, state, turn_meta)
    if semantic_decision:
        return semantic_decision

    guard = input_guard_decision(step, text, turn_meta)
    if guard['repair']:
        return {
            'sufficient': False,
            'action': 'ask_followup',
            'record_current_answer': False,
            'usable_evidence': False,
            'prior_evidence_used': False,
            'pushback_detected': False,
            'reason': guard['reason'],
            'matched': guard['matched'],
        }

    return {
        'sufficient': False,
        'action': 'ask_followup',
        'record_current_answer': False,
        'usable_evidence': False,
        'prior_evidence_used': False,
        'pushback_detected': False,
        'reason': 'semantic_nlu_required',
        'matched': None,
    }
